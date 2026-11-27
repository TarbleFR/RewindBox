"""Portable fixtures based on the S2Arm NVN log formats, with synthetic values."""
import unittest
from wait_summary import summarize


def snapshot(frame, n):
    return (f"[rb-cpu-gpu-sync] cumulative frame={frame} queue_wait_records={n} queue_wait_drains={n} "
            f"queue_wait_drain_ms={n}.125 allocator_wait_ms={n}.250 allocator_reset_deferred={n} "
            f"visibility_reserves={n} pieces_without_visibility={n} visibility_waits={n} "
            f"visibility_wait_ms={n}.625 visibility_failures=0")


def piece(submission, n):
    return (f"[rb-piece] up to submission {submission}: {n} pieces handed over without waiting for the encode "
            f"thread, {n} submit calls waited for it once at their end ({n}.75 ms in all)")


BEGIN = "[rb-parallel] v=1 session=9 event=begin from=100 frames=600 cb_cap=16384 present_cap=4096"
CPU = ("[nvn] thread cores up to frame 600: encode thread 1.22 ms a frame, 80% on performance cores; "
       "present thread 0.30 ms a frame, 2% on performance cores (s2a_qos.h table)")
LONG = ("[longframe] frame 599 (10.50 s) whole frame 33.3 ms, submit+present 8.8 ms, GPU 6.5 ms; "
        "presenting thread blocked on the submit lock -1.0 ms, GPU fences 2.0 ms, the encode thread 3.0 ms, "
        "readbacks and upload slots 0.0 ms, owed cross-queue fences 0.5 ms; drawables 0.3 ms")
STOP = "[rb-replay] stopped: submitted=130 completed=130 admission_wait_ms=33.125"


class Waits(unittest.TestCase):
    def test_scopes_and_deltas(self):
        result = summarize([BEGIN, snapshot(300, 2), piece(3000, 10), LONG, CPU,
                            snapshot(600, 5), piece(6000, 20), STOP])
        self.assertEqual(result["trace_session_id"], 9)
        a, b = result["sync_report_windows"]
        self.assertIsNone(a["window_delta"])
        self.assertEqual(b["previous_report_frame_label"], 300)
        self.assertEqual(b["window_delta"]["queue_wait_drain_ms"], 3)
        self.assertEqual(b["window_delta"]["queue_wait_records"], 3)
        self.assertEqual(result["submission_report_windows"][1]["window_delta"]["accounted_encode_wait_ms"], 10)
        self.assertEqual(result["replay_worker_stop"]["replay_join_ms"], 33.125)
        self.assertEqual(result["thread_cpu_windows"][0]["end_frame"], 600)
        w = result["presenting_thread_long_frames"][0]["presenting_thread_waits"]
        self.assertIsNone(w["submit_lock_ms"])
        self.assertEqual(w["gpu_fences_ms"], 2)
        self.assertEqual(w["readback_or_upload_slot_ms"], 0)

    def test_partial_or_older_capture(self):
        result = summarize([LONG.partition("; presenting thread blocked")[0]])
        self.assertIsNone(result["presenting_thread_long_frames"][0]["presenting_thread_waits"])
        self.assertIsNone(result["trace_session_id"])
        self.assertIsNone(result["replay_worker_stop"])

    def test_reject_resets_duplicates_and_malformed(self):
        for lines in ([BEGIN, BEGIN, CPU], [BEGIN, STOP, STOP], [snapshot(300, 3), snapshot(600, 2)],
                      [piece(3000, 1), piece(3000, 2)], [CPU, CPU], [LONG, LONG], [STOP, BEGIN],
                      [snapshot(300, 1).replace("queue_wait_drains=1", "queue_wait_drains=-1")],
                      [snapshot(300, 1) + " allocator_wait_ms=nan"], [LONG.replace("GPU fences 2.0", "GPU fences nan")],
                      [STOP.replace("completed=130", "completed=131")], [BEGIN]):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                summarize(lines)


if __name__ == "__main__":
    unittest.main()
