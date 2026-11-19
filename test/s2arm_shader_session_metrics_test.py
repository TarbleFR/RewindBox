import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/s2arm_prototype"))
from shader_session_metrics import summarize


class SessionMetricsTests(unittest.TestCase):
    def test_shared_intervals_and_partial_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            host = root / "host.log"
            host.write_text("pipeline archive after the prewarm: 7 builds from the archive, 2 compiled\n")
            captures = []
            for name, frames in (("a", [(8, 100000), (9, 100001)]), ("b", [(9, 100001), (11, 0)])):
                path = root / name
                path.write_text("# microseconds to the next frame\n" + "".join(
                    f"{i} abcd " + "0 " * 15 + f"{us}\n" for i, us in frames))
                captures.append(path)
            result = summarize(host, captures, 0, 20)
            self.assertEqual(result["frameSignatureIntervals"]["observedIntervals"], 2)
            self.assertEqual(result["frameSignatureIntervals"]["over100Ms"], 1)
            self.assertEqual(result["sessionPrewarm"]["archive"]["strictHits"], 7)
            self.assertIsNone(result["selectedLoggedFrames"]["compilerTotalsOnTheseRows"])
            captures[1].write_text(captures[1].read_text().replace("100001", "200000"))
            with self.assertRaisesRegex(ValueError, "Inconsistent"):
                summarize(host, captures, 0, 20)


if __name__ == "__main__":
    unittest.main()
