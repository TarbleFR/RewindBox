#!/usr/bin/env python3
"""Exercise the evidence wrapper through its public command-line entry points."""

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts/ai-output.py"


class OutputEvidenceTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([sys.executable, str(TOOL), *map(str, args)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def run_child(self, directory, code, *args):
        result = self.invoke("run", "--log-dir", directory, "--", sys.executable, "-c", code, *args)
        receipt_path = Path(next(line.removeprefix("Receipt: ")
                                 for line in result.stdout.splitlines() if line.startswith("Receipt: ")))
        receipt = json.loads(receipt_path.read_text())
        return result, receipt

    def test_success_and_stderr_are_preserved_without_interpreting_keywords(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, receipt = self.run_child(tmp,
                "import os; os.write(1,b'PASS first\\n'); os.write(2,b'warning stderr\\n')")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(receipt["return_code"], 0)
            self.assertEqual(Path(receipt["log_path"]).read_bytes(), b"PASS first\nwarning stderr\n")
            self.assertIn("child exit 0", result.stdout)

    def test_nonzero_status_survives_without_error_keywords(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, receipt = self.run_child(tmp, "print('last diagnostic'); raise SystemExit(7)")
            self.assertEqual(result.returncode, 7)
            self.assertEqual(receipt["return_code"], 7)
            self.assertIn("child exit 7", result.stdout)
            self.assertIn("last diagnostic", result.stdout)
            self.assertEqual(receipt["matching_lines"], 0)

    def test_binary_output_and_hash_remain_exact(self):
        payload = b"bad utf8 \xff\x00\xfe\n"
        with tempfile.TemporaryDirectory() as tmp:
            result, receipt = self.run_child(tmp, f"import os; os.write(1,{payload!r})")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(Path(receipt["log_path"]).read_bytes(), payload)
            self.assertEqual(receipt["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(receipt["bytes"], len(payload))

    def test_large_output_retains_first_last_matches_and_bounds_the_excerpt(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, receipt = self.run_child(tmp,
                "for i in range(5000): print('ERROR marker_%d '%i + 'x'*400)")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(receipt["lines"], 5000)
            self.assertEqual(receipt["matching_lines"], 5000)
            self.assertIn("marker_0 ", result.stdout)
            self.assertIn("marker_4999 ", result.stdout)
            self.assertLess(len(result.stdout), 10000)
            self.assertGreater(receipt["unselected_lines"], 4900)
            self.assertGreater(Path(receipt["log_path"]).stat().st_size, 2000000)

    def test_huge_unbroken_line_and_fragment_boundary_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, receipt = self.run_child(tmp,
                "import os; os.write(1,b'x'*65534+b'ERROR boundary_marker'+b'y'*1000000)")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(receipt["lines"], 1)
            self.assertEqual(receipt["matching_lines"], 1)
            self.assertIn("boundary_marker", result.stdout)
            self.assertLess(len(result.stdout), 2000)

    def test_success_or_warning_noise_does_not_displace_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, receipt = self.run_child(tmp,
                "print('PASS success\\nwarning diagnostic\\n'*100, end=''); "
                "print('ERROR decisive_failure'); print('OK done\\nSKIP optional\\n'*100, end='')")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(receipt["matching_lines"], 1)
            self.assertIn("decisive_failure", result.stdout)

    def test_unique_runs_and_shell_metacharacters_stay_literal(self):
        with tempfile.TemporaryDirectory() as tmp:
            argument = "literal ; $HOME $(echo unsafe) & name with spaces"
            one, first = self.run_child(tmp, "import sys; print(sys.argv[1])", argument)
            two, second = self.run_child(tmp, "print('other')")
            self.assertEqual((one.returncode, two.returncode), (0, 0))
            self.assertNotEqual(first["log_path"], second["log_path"])
            self.assertEqual(Path(first["log_path"]).read_text().strip(), argument)

    def test_existing_log_is_read_only_and_outcome_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.log"
            path.write_bytes(b"ERROR expected test case\n")
            before = path.stat()
            result = self.invoke("file", path)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), b"ERROR expected test case\n")
            self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
            self.assertIn("command outcome unknown", result.stdout)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["source.log"])

    def test_missing_command_produces_a_failure_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.invoke("run", "--log-dir", tmp, "--", str(Path(tmp)/"missing-command"))
            self.assertEqual(result.returncode, 127)
            receipt = json.loads(next(Path(tmp).glob("*/receipt.json")).read_text())
            self.assertIsNotNone(receipt["launch_error"])
            self.assertEqual(Path(receipt["log_path"]).read_bytes(), b"")
            self.assertIn("could not start", result.stdout)

    @unittest.skipUnless(os.name == "posix", "POSIX signal exit status")
    def test_child_signal_status_is_preserved(self):
        for child_signal in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(signal=child_signal), tempfile.TemporaryDirectory() as tmp:
                result, receipt = self.run_child(tmp,
                    f"import os; os.kill(os.getpid(),{child_signal})")
                self.assertEqual(result.returncode, -child_signal)
                self.assertEqual(receipt["return_code"], -child_signal)

    @unittest.skipUnless(os.name == "posix", "POSIX interrupt delivery")
    def test_interruption_retains_partial_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready = Path(tmp) / "ready"
            code = "import os,time,pathlib; os.write(1,b'partial output\\n'); pathlib.Path(__import__('sys').argv[1]).touch(); time.sleep(30)"
            process = subprocess.Popen([sys.executable, str(TOOL), "run", "--log-dir", tmp,
                "--", sys.executable, "-c", code, str(ready)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(ready.exists())
                process.send_signal(signal.SIGINT)
                stdout, _ = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 130)
                receipt = json.loads(next(Path(tmp).glob("*/receipt.json")).read_text())
                self.assertTrue(receipt["interrupted"])
                self.assertEqual(Path(receipt["log_path"]).read_bytes(), b"partial output\n")
                self.assertIn(b"partial output retained", stdout)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    unittest.main()
