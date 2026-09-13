import copy
import importlib.util
from pathlib import Path
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("installer", ROOT / "installer/bootstrap-dnscrypt.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DNSCryptInstallerTest(unittest.TestCase):
    def setUp(self):
        self.config = tomllib.loads((ROOT / "installer/dnscrypt.toml.example").read_text())

    def test_rejects_open_acl(self):
        for network in ("0.0.0.0/0", "::/0"):
            config = copy.deepcopy(self.config)
            config["clients"].append(network)
            with self.assertRaises(ValueError):
                module.render(config)

    def test_rejects_injection_and_wrong_family(self):
        for key, value in (("instance", "../../etc"), ("provider", 'bad"\n[quic]'),
                           ("ipv4", "::1"), ("ipv6", "0.0.0.0")):
            config = dict(self.config, **{key: value})
            with self.assertRaises(ValueError):
                module.render(config)

    def test_missing_loopback_and_host_bits(self):
        for networks in (["198.51.96.0/21"], ["127.0.0.1/32", "::1/128", "198.51.100.10/21"]):
            with self.assertRaises(ValueError):
                module.render(dict(self.config, clients=networks))

    def test_render_both_instance_names_preserves_policy(self):
        for instance in ("isp-dnscrypt", "isp-dnscrypt-test"):
            rendered = module.render(dict(self.config, instance=instance))
            config = tomllib.loads(rendered[f"etc/{instance}.toml"])
            self.assertEqual(config["upstream_addrs"], ["127.0.0.1:53"])
            self.assertEqual(config["state_file"], f"/var/lib/{instance}/encrypted-dns.state")
            self.assertFalse(config["dnscrypt"]["no_logs"])
            self.assertFalse(config["dnscrypt"]["no_filters"])
            self.assertFalse(config["anonymized_dns"]["enabled"])
            self.assertNotIn("upstream_addr", config["quic"])
            for text in rendered.values():
                self.assertNotIn("@INSTANCE@", text)
            nft = rendered[f"etc/nftables.d/{instance}.nft"]
            self.assertNotIn("flush ruleset", nft)
            self.assertIn("counter drop", nft)
            self.assertIn(f"Requires={instance}-firewall.service", rendered[f"etc/systemd/system/{instance}.service"])

    def test_bind_parser_rejects_symbolic_or_duplicate_acls(self):
        for text in ('acl "klienci_sieci" { any; };',
                     'acl "klienci_sieci" { 127.0.0.1; }; acl "klienci_sieci" { ::1; };'):
            with self.assertRaises(ValueError):
                module.bind_acl(text)
        nets = module.bind_acl('// comment\nacl "klienci_sieci" { 127.0.0.1; /* x */ ::1; };')
        self.assertEqual(len(nets), 2)

    def test_existing_install_refused_before_download_or_commands(self):
        with patch.object(module.Path, "exists", return_value=True), \
             patch.object(module, "run") as run, \
             patch.object(module.urllib.request, "urlopen") as download:
            with self.assertRaisesRegex(ValueError, "already installed"):
                module.install(self.config, module.render(self.config))
            run.assert_not_called()
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
