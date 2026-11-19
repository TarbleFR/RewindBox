import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/s2arm_prototype"))
from shader_session_metrics import summarize


class SessionMetricsTests(unittest.TestCase):
    def test_course_windows_keep_all_frames_and_unknown_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            host = Path(directory) / "host.log"
            def row(start, end, asset, n):
                return (f"RewindBox course metrics frames={start}..{end} asset={asset} samples={n} "
                        "interval_ms=511.100 over100=1 over500=1 pso_wait_ms=12.250 shared_library_wait_ms=0.400 "
                        "xlate_wait_ms=2.000 xlate_ms=3.000 msl_count=1 msl_ms=4.000 texture_upload_ms=5.020 "
                        "texture_gpu_completed_ms=0.300")
            text = "\n".join((row(1, 4, "unknown", 1), row(1, 4, "FirstCircuit_A_00[Game03]", 3),
                              row(5, 8, "unknown", 1)))
            host.write_text(text)
            result = summarize(host, [], 0, 99)["courseAssetWindows"]
            self.assertEqual(result["incompleteWindows"], [[5, 8]])
            self.assertEqual(result["completeIntervalsByAsset"]["unknown"]["samples"], 1)
            self.assertEqual(result["completeIntervalsByAsset"]["FirstCircuit_A_00[Game03]"]["texture_upload_ms"], 5.02)
            self.assertEqual(summarize(host, [], 2, 6)["courseAssetWindows"]["completeIntervalsByAsset"], {})
            host.write_text(text + "\n" + row(1, 4, "unknown", 1))
            with self.assertRaisesRegex(ValueError, "Duplicate course"):
                summarize(host, [], 0, 99)

    def test_complete_windows_and_timed_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            host = Path(directory) / "host.log"
            lines = [
                "RewindBox frame intervals 1..2: 2 samples, 300000002 ns, above 100/200/500 ms 2/0/0",
                "RewindBox frame intervals 3..3: 1 samples, 500000001 ns, above 100/200/500 ms 1/1/1",
                "[longframe] frame 3 (0.80 s) whole frame 500.0 ms; outside submit/present 409.2 ms, longest 301.0 ms over 3 gaps",
                "RewindBox reference: encoder bound exact prewarmed PSO " + "abcde" * 8 + " at frame 2"]
            host.write_text("\n".join(lines))
            report = summarize(host, [], 1, 3)
            win = report["completeHostWindows"]
            self.assertEqual((win["samples"], win["over100Ms"], win["over200Ms"], win["over500Ms"]), (3, 3, 1, 1))
            self.assertEqual(win["averageFPS"], 3.75)
            self.assertEqual(report["selectedLoggedFrames"]["submitGaps"][3]["longestMs"], 301.)
            self.assertEqual(len(report["referenceBinds"]), 1)
            self.assertIsNone(summarize(host, [], 2, 2)["completeHostWindows"])
            host.write_text("\n".join(lines + lines[:1]))
            with self.assertRaisesRegex(ValueError, "Overlapping"):
                summarize(host, [], 1, 3)

    def test_real_object_reuse_and_sampled_governor_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            host = Path(directory) / "host.log"
            host.write_text(
                "RewindBox PSO transitions: 3 promoted, 1 warmed Metal objects bound\n"
                "RewindBox PSO transitions: 17 first-used, 3 promoted, 2 published, 1 warmed Metal objects bound, 1 published but unused\n"
                "RewindBox: existing Metal source library reused for another shader identity: 4\n"
                "RewindBox: existing Metal source library reused for another shader identity: 6\n"
                "RewindBox: speculative shader work on one worker: fair (thermal state 1, -1 MB left before the process limit (-1 unknown), Low Power Mode 0; 1 changes; patch 0121)\n"
                "RewindBox: speculative shader work held: memory (thermal state 1, 0 MB left before the process limit (-1 unknown), Low Power Mode 0; 2 changes; patch 0121)\n"
                "RewindBox PSO transitions: 1 promoted, 0 warmed Metal objects bound\n")
            sample = summarize(host, [], 10, 20)["wholeLog"]
            self.assertEqual(sample["lastReportedSourceLibraryReuses"], 6)
            self.assertEqual(sample["completedPredictionSessions"],
                             [{"firstUsed": 17, "promoted": 3, "published": 2, "bound": 1, "publishedUnused": 1}])
            self.assertEqual(sample["lastUnfinishedPredictionSample"], {"promoted": 1, "bound": 0})
            self.assertEqual([(change["level"], change["headroomMiB"]) for change in sample["loggedGovernorChanges"]],
                             [("ONE", None), ("HOLD", 0)])

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
