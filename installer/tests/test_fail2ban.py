import configparser
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class Fail2BanConfigTest(unittest.TestCase):
    def test_ssh_family_commands_survive_inline_comment_parsing(self):
        for host in ('dns1', 'dns2'):
            config = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(';',))
            config.read(ROOT / 'servers' / host / 'etc/fail2ban/jail.d/sshd.local')
            for jail, results in [('sshd', (1, 0)), ('sshd-ip6', (0, 1))]:
                for ip, expected in zip(('192.0.2.254', '2001:db8::f2b'), results):
                    command = config[jail]['ignorecommand'].replace('<ip>', ip)
                    actual = subprocess.run(command, shell=True, capture_output=True)
                    self.assertEqual(actual.returncode, expected, (host, jail, actual.stderr))
            self.assertIn('_COMM=sshd-session', config['sshd']['journalmatch'])
            self.assertIn('ignoreip', config['sshd-ip6'])
            self.assertEqual(config['sshd-ip6']['ignoreip'], config.defaults()['ignoreip'])

    def test_dns_ipv4_filter_does_not_capture_ipv6(self):
        for host in ('dns1', 'dns2'):
            text = (ROOT / 'servers' / host / 'etc/fail2ban/filter.d/named-cache-denied.conf').read_text()
            self.assertIn('<IP4>', text)
            self.assertNotIn('<HOST>', text)
