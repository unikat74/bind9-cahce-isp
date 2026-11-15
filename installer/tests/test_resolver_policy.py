import configparser
import importlib.util
from pathlib import Path
import subprocess
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('resolver_install', ROOT / 'installer/bootstrap-resolver-policy.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ResolverPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = tomllib.loads((ROOT / 'installer/profiles/fione.toml').read_text())

    def test_same_limits_logs_and_separate_ntp_acl_for_both_sites(self):
        for site in ['fuz', 'fione', 'cybermax']:
            config = tomllib.loads((ROOT / 'installer/profiles' / (site + '.toml')).read_text())
            files = m.render(config)
            opts = files['etc/bind/named.conf.resolver-policy']
            for value in ['max-cache-size 2G;', 'recursive-clients 10000;', 'tcp-clients 1000;',
                          'allow-query { klienci_sieci; };']:
                self.assertIn(value, opts)
            self.assertNotIn('versions ', files['etc/bind/named.conf.logging'])
            for value in ['daily', 'maxsize 20M', 'rotate 7', 'delaycompress', 'rndc reconfig']:
                self.assertIn(value, files['etc/logrotate-isp-dns.conf'])
            nft = files['etc/nftables.conf']
            self.assertNotIn('flush ruleset', nft)
            self.assertIn('ntp_clients4', nft)
            self.assertIn('188.137.37.190/32', nft)
            self.assertNotIn('dport 22', nft)
            self.assertIn('OnCalendar=hourly', files['etc/systemd/system/isp-dns-logrotate.timer'])
        self.assertNotIn('172.17.0.0/16', m.render(self.config)['etc/chrony/conf.d/isp-clients.conf'])
        self.assertIn('172.31.254.3/32', m.render(self.config)['etc/chrony/conf.d/isp-clients.conf'])

    def test_ssh_only_exception_does_not_expand_dns_or_ntp(self):
        files = m.render(self.config)
        self.assertIn('78.31.90.144/32', files['etc/fail2ban/jail.d/sshd.local'])
        self.assertNotIn('78.31.90.144/32', files['etc/nftables.conf'])
        c = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(';',))
        c.read_string(files['etc/fail2ban/jail.d/sshd.local'])
        self.assertEqual(c['sshd']['bantime'], '1h')
        self.assertEqual(c['sshd-ip6']['bantime'], '1d')
        for jail, expected in [('sshd', [1, 0]), ('sshd-ip6', [0, 1])]:
            for ip, code in zip(['192.0.2.254', '2001:db8::f2b'], expected):
                command = c[jail]['ignorecommand'].replace('<ip>', ip)
                self.assertEqual(subprocess.run(command, shell=True, capture_output=True).returncode, code)

    def test_reject_open_acls_and_invalid_forwarders(self):
        for field, value in [('clients', ['0.0.0.0/0']), ('ntp_clients', ['::/0']),
                             ('administrators', ['::/0']), ('forwarders', ['bad;reload']),
                             ('forwarders', ['127.0.0.1']), ('forwarders', [])]:
            with self.assertRaises(ValueError):
                m.render(dict(self.config, **{field: value}))

    def test_preserves_tls_rpz_and_unrelated_zone_options(self):
        original = '''// options { ignored comment }
acl "klienci_sieci" { 78.31.88.0/21; };
tls "my-tls" { cert-file "/etc/bind/brace}file.pem"; };
options {
 tcp-clients 750;
 allow-query { any; };
 response-policy { zone "rpz.hazard.mf.gov.pl" policy given; } break-dnssec yes;
 listen-on port 853 tls "my-tls" { any; };
};
zone "other" { type primary; allow-transfer { none; }; file "/etc/bind/other"; };
'''
        result = m.apply_options(original, self.config)
        self.assertNotIn('tcp-clients 750', result)
        self.assertIn('listen-on port 853 tls "my-tls" { any; };', result)
        self.assertIn('response-policy { zone "rpz.hazard.mf.gov.pl" policy given; } break-dnssec yes;', result)
        self.assertIn('zone "other" { type primary; allow-transfer { none; };', result)
        self.assertEqual(m.apply_options(result, self.config), result)

    def test_migrates_legacy_clients_acl_without_leaving_duplicate_acls(self):
        original = 'acl clients { 78.31.88.0/21; }; options { allow-query { clients; }; recursion yes; };'
        result = m.apply_options(original, self.config)
        self.assertNotIn('acl clients', result)
        self.assertEqual(m.common.bind_acl(result), set(m.policy.networks(self.config['clients'] + self.config['administrators'] + ['127.0.0.1/32', '::1/128'])))
        self.assertIn('acl "klienci_sieci"', result)

    def test_refuses_removing_existing_client(self):
        text = 'acl "klienci_sieci" { 192.0.2.0/24; }; options { recursion yes; };'
        with self.assertRaisesRegex(ValueError, 'remove existing'):
            m.apply_options(text, self.config)

    def test_rpz_keys_are_separate_in_both_templates(self):
        for role in ['dns1', 'dns2']:
            text = (ROOT / 'bind' / role / 'named.conf.rpz').read_text()
            threatfox, hazard = text.split('zone "rpz.hazard.mf.gov.pl"')
            self.assertIn('key "threatfox-rpz-xfr";', threatfox)
            self.assertNotIn('key "threatfox-rpz-xfr";', hazard)
            self.assertIn('key "hazard-rpz-xfr";', hazard)
            if role == 'dns2':
                self.assertIn('allow-notify { key "threatfox-rpz-xfr"; };', threatfox)
                self.assertIn('allow-notify { key "hazard-rpz-xfr"; };', hazard)

    def test_schedules_and_doq_health_are_consistent(self):
        threatfox = (ROOT / 'systemd/threatfox-rpz.timer').read_text()
        self.assertIn('03:17:00 Europe/Warsaw', threatfox)
        self.assertIn('RandomizedDelaySec=20m', threatfox)
        hazard = (ROOT / 'systemd/hazard-rpz.timer').read_text()
        self.assertIn('06:00:00 Europe/Warsaw', hazard)
        self.assertIn('18:00:00 Europe/Warsaw', hazard)
        doq = m.load('bootstrap-doq')
        cfg = dict(instance='isp-dnscrypt', provider='dns.example.net', ipv4='192.0.2.10',
                   ipv6='2001:db8::10', clients=['127.0.0.1/32', '::1/128', '192.0.2.0/24', '2001:db8::/48'])
        self.assertIn('checkName="localhost."', doq.render(cfg)['etc/dnsdist/dnsdist.conf'])
