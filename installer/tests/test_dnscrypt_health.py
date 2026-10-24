import importlib.machinery
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
loader = importlib.machinery.SourceFileLoader('health', str(ROOT / 'scripts/check-dnscrypt-renewal'))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.secret = Ed25519PrivateKey.generate()
        self.key = self.secret.public_key().public_bytes_raw()
        self.now = 1000000
        self.raw = self.make_cert(self.now - 60, self.now + 86340)

    def make_cert(self, start, end):
        body = bytes(40) + struct.pack('!III', 1, start, end)
        return b'DNSC\x00\x02\x00\x00' + self.secret.sign(body) + body

    def state(self, raw):
        parts = {'cert_magic': list(raw[:4]), 'es_version': list(raw[4:6]),
                 'minor_version': list(raw[6:8]), 'signature': list(raw[8:72]),
                 'inner': {k: list(raw[a:b]) for k, a, b in (
                     ('resolver_pk', 72, 104), ('client_magic', 104, 112),
                     ('serial', 112, 116), ('ts_start', 116, 120), ('ts_end', 120, 124))}}
        return {'provider_kp': {'pk': list(self.key)}, 'dnscrypt_encryption_params_set': [{'dnscrypt_cert': parts}]}

    def disk(self, raw, age=0, state=None):
        fake = unittest.mock.Mock()
        fake.stat.return_value.st_mtime = self.now - age
        fake.read_text.return_value = ''
        with patch.object(m.tomllib, 'loads', return_value=state or self.state(raw)):
            return m.disk_state(fake, self.key, self.now)

    def test_valid_disk_and_signed_certificate(self):
        self.assertEqual(self.disk(self.raw), {self.raw})
        self.assertEqual(m.certificate(self.raw, self.key, self.now)[0], self.now - 60)

    def test_stale_state_and_stalled_rotation_even_after_touch(self):
        with self.assertRaisesRegex(m.HealthError, 'not saved'):
            self.disk(self.raw, age=36001)
        with self.assertRaisesRegex(m.HealthError, 'no certificate rotation'):
            self.disk(self.make_cert(self.now - 36001, self.now + 50000))

    def test_expired_and_near_expiry(self):
        for start, end, message in ((self.now - 86401, self.now - 1, 'no valid'),
                                     (self.now - 60, self.now + 43199, 'less than 12h')):
            with self.assertRaisesRegex(m.HealthError, message):
                self.disk(self.make_cert(start, end))

    def test_provider_change_and_bad_signature(self):
        state = self.state(self.raw)
        state['provider_kp']['pk'] = list(bytes(32))
        with self.assertRaisesRegex(m.HealthError, 'identity differs'):
            self.disk(self.raw, state=state)
        with self.assertRaisesRegex(m.HealthError, 'signature'):
            m.certificate(self.raw[:-1] + bytes([self.raw[-1] ^ 1]), self.key, self.now)

    def test_live_mismatch_and_all_listeners_both_transports(self):
        config = {'state_file': '/unused', 'dnscrypt': {'provider_name': 'example.net'},
                  'listen_addrs': [{'local': '127.0.0.1:8443'}, {'local': '[::1]:8443'}]}
        with patch.object(m.time, 'time', return_value=self.now), \
             patch.object(m, 'disk_state', return_value={self.raw}), \
             patch.object(m, 'query', return_value={self.raw}) as query:
            m.check(config, self.key)
            self.assertEqual(query.call_count, 4)
            query.return_value = {self.make_cert(self.now, self.now + 86400)}
            with self.assertRaisesRegex(m.HealthError, 'differ'):
                m.check(config, self.key)

    def test_rotation_serves_newest_while_state_keeps_previous(self):
        config = {'state_file': '/unused', 'dnscrypt': {'provider_name': 'example.net'},
                  'listen_addrs': [{'local': '127.0.0.1:8443'}]}
        newest = self.make_cert(self.now, self.now + 86400)
        with patch.object(m.time, 'time', return_value=self.now), \
             patch.object(m, 'disk_state', return_value={self.raw, newest}), \
             patch.object(m, 'query', return_value={newest}) as query:
            m.check(config, self.key)
            query.return_value = {self.raw}
            with self.assertRaisesRegex(m.HealthError, 'newest persisted'):
                m.check(config, self.key)
            query.return_value = set()
            with self.assertRaises(m.HealthError):
                m.check(config, self.key)

    def test_dns_response_parser_rejects_truncation_and_wrong_id(self):
        question = b'\x01a\x00\x00\x10\x00\x01'
        record = bytes([124]) + self.raw
        packet = struct.pack('!6H', 42, 0x8180, 1, 1, 0, 0) + question
        packet += b'\xc0\x0c' + struct.pack('!HHIH', 16, 1, 60, len(record)) + record
        self.assertEqual(m.parse_response(packet, 42), {self.raw})
        for cut in range(len(packet)):
            with self.assertRaises(m.HealthError):
                m.parse_response(packet[:cut], 42)
        with self.assertRaises(m.HealthError):
            m.parse_response(packet, 43)

    def test_initialization_never_overwrites_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            pin = Path(directory) / 'pin'
            pin.write_text('existing identity')
            config = Path(directory) / 'config'
            config.write_text('state_file="unused"')
            with patch.object(m.sys, 'argv', ['check', '--config', str(config), '--provider-key', str(pin), '--initialize-pin']), \
                 patch.object(m.Path, 'read_text', side_effect=['state_file="unused"', 'state']), \
                 patch.object(m.tomllib, 'loads', side_effect=[{'state_file': 'unused'}, self.state(self.raw)]), \
                 patch.object(m, 'check', return_value=80000):
                self.assertEqual(m.main(), 1)
            self.assertEqual(pin.read_text(), 'existing identity')


if __name__ == '__main__':
    unittest.main()
