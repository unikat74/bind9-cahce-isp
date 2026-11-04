import importlib.util
import ipaddress
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'installer' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExtensionTests(unittest.TestCase):
    def test_protection_rejects_open_acl_and_requires_both_families(self):
        module = load('bootstrap-dns-protection')
        for nets in [[], ['0.0.0.0/0', '2001:db8::/48'], ['192.0.2.0/24', '::/0'], ['192.0.2.0/24']]:
            with self.assertRaises(ValueError):
                module.render(nets)

    def test_newly_trusted_clients_are_unbanned_without_clearing_other_bans(self):
        module = load('bootstrap-dns-protection')
        self.assertEqual(module.trusted_bans(['10.0.15.254', '10.0.16.1', '192.0.2.1', '2001:db8::2'],
                                            ['10.0.0.0/20']), ['10.0.15.254'])

    def test_protection_uses_supplied_networks_and_separates_rpz(self):
        module = load('bootstrap-dns-protection')
        files = module.render(['192.0.2.0/24', '2001:db8:1234::/48'])
        jail = files['etc/fail2ban/jail.d/named-cache-denied.local']
        self.assertIn('192.0.2.0/24', jail)
        self.assertNotIn('193.192.179.', jail)
        self.assertIn('2001:db8:1234::/48', jail)
        self.assertIn('category rpz { rpz_file; }', files['etc/bind/named.conf.logging'])
        self.assertNotIn('/var/log/named/rpz.log', jail)

    def test_doq_backend_preserves_client_address_and_uses_own_firewall(self):
        module = load('bootstrap-doq')
        config = dict(instance='isp-dnscrypt', provider='dns.example.net', ipv4='192.0.2.10',
                      ipv6='2001:db8::10', clients=['127.0.0.1/32', '::1/128', '192.0.2.0/24', '2001:db8::/48'])
        files = module.render(config)
        self.assertIn('useProxyProtocol=true', files['etc/dnsdist/dnsdist.conf'])
        self.assertIn('[2001:db8::10]:853', files['etc/dnsdist/dnsdist.conf'])
        self.assertNotIn('flush ruleset', files['etc/nftables.d/isp-doq.nft'])
        self.assertTrue(files['etc/nftables.d/isp-doq.nft'].startswith('destroy table inet isp_doq\n'))
        self.assertIn('udp dport 853 counter drop', files['etc/nftables.d/isp-doq.nft'])

    def test_acl_parser_accepts_new_clients_and_rejects_ambiguity(self):
        module = load('bootstrap-dnscrypt')
        expected = {ipaddress.ip_network('192.0.2.0/24')}
        for name in ['clients', '"clients"', '"klienci_sieci"']:
            self.assertEqual(module.bind_acl('acl ' + name + ' { 192.0.2.0/24; };'), expected)
        with self.assertRaises(ValueError):
            module.bind_acl('acl clients {192.0.2.0/24;}; acl "klienci_sieci" {192.0.2.0/24;};')


class ThreatFoxTopologyTests(unittest.TestCase):
    def test_primary_downloads_and_secondary_uses_authenticated_transfer(self):
        module = load('bootstrap-threatfox')
        primary = module.zone_text('primary', '193.192.179.12')
        secondary = module.zone_text('secondary', '193.192.179.11')
        self.assertIn('type primary;', primary)
        self.assertIn('allow-transfer { key "threatfox-rpz-xfr"; };', primary)
        self.assertIn('type secondary;', secondary)
        self.assertIn('primaries { 193.192.179.11 key "threatfox-rpz-xfr"; };', secondary)
        self.assertNotIn('/etc/threatfox.env', secondary)
        with self.assertRaises(ValueError):
            module.zone_text('primary', 'host; invalid')
