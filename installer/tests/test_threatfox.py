from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "scripts/update-threatfox-rpz").read_text()
FILTER = SCRIPT.split('<<\'PY\'\n', 1)[1].split('\nPY\n', 1)[0]


class ThreatFoxFilterTest(unittest.TestCase):
    def run_filter(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feed"
            path.write_text(text)
            result = subprocess.run([sys.executable, "-c", FILTER, str(path)],
                                    capture_output=True, text=True)
            return result, path.read_text()

    def test_wire_boundary_and_other_records_preserved(self):
        # The relative name itself fits; adding the RPZ suffix hits 255/256.
        name = ".".join(["a" * 63] * 3 + ["b" * 38])
        valid = name + " CNAME .\n"
        invalid = name + "b CNAME .\n"
        header = "$TTL 30\n@ SOA ns. hostmaster. 1 300 1800 604800 30\n NS localhost.\n"
        result, output = self.run_filter(header + valid + invalid + "ok.example CNAME .\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, header + valid + "ok.example CNAME .\n")
        self.assertIn("wire=256", result.stderr)
        self.assertIn("skipped 1", result.stderr)

    def test_absolute_name_does_not_get_suffix_and_long_label_is_skipped(self):
        absolute = ".".join(["a" * 63] * 3 + ["b" * 61]) + ". CNAME .\n"
        result, output = self.run_filter(absolute + "x" * 64 + ".example CNAME .\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(output, absolute)
        self.assertIn("max-label=64", result.stderr)

    def test_unexpected_origin_fails_without_rewriting_input(self):
        text = "$ORIGIN other.\nexample CNAME .\n"
        result, output = self.run_filter(text)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output, text)

    def test_deployed_copy_matches_source(self):
        self.assertEqual(SCRIPT, (ROOT / "servers/dns1/usr/local/sbin/update-threatfox-rpz").read_text())
