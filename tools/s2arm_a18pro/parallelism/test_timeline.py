from io import StringIO
import unittest

from timeline import read_trace, summarize


class TraceTest(unittest.TestCase):
    def parse(self, *rows):
        return summarize(read_trace(StringIO("\n".join("[rb-parallel] v=1 session=4 " + row for row in rows))))

    def test_callback_order_overlap_and_truncation(self):
        def cb(frame, serial, cpu, gpu):
            return (f"event=cb frame={frame} cb={serial} sub=9 seg=0 metal=4 reason=flush "
                    f"prep_start_s={cpu[0]} prep_end_s={cpu[1]} prep_thread_ns=200000 "
                    f"status=ok gpu_start_s={gpu[0]} gpu_end_s={gpu[1]}")

        summary, trace = self.parse(
            "event=begin from=8 frames=600 cb_cap=16384 present_cap=4096",
            "event=present frame=9 ticket=21 resource=2 enqueue_s=1.080 status=shown present_s=1.100",
            "event=limit stream=cb cap=16384",
            cb(9, 3, (1.020, 1.060), (1.060, 1.081)),
            cb(8, 1, (1.001, 1.010), (1.011, 1.042)),
            cb(8, 2, (1.010, 1.020), (1.030, 1.050)),
            "event=window_end cb_reserved=3 present_reserved=3 cb_limited=1 present_limited=0",
            "event=present frame=8 ticket=20 resource=1 enqueue_s=1.060 status=shown present_s=1.082")
        result = summary[4]
        self.assertAlmostEqual(result["frames"][0]["next_frame_overlap_ms"], 30)
        self.assertAlmostEqual(result["frames"][0]["gpu_envelope_union_ms"], 39)
        self.assertAlmostEqual(result["consecutive_presentation_interval_ms"]["p99"], 18)
        self.assertEqual(result["limits_reported"], ["cb"])
        self.assertFalse(result["reservations_match_callbacks"])
        self.assertTrue(all(isinstance(event["tid"], int) for event in trace["traceEvents"]))

    def test_display_stall_across_coalesced_or_unobserved_tickets(self):
        summary, _ = self.parse(
            "event=present frame=14 ticket=34 resource=2 enqueue_s=1.020 status=shown present_s=1.110",
            "event=present frame=12 ticket=32 resource=3 enqueue_s=1.010 status=unshown",
            "event=present frame=11 ticket=31 resource=2 enqueue_s=1.000 status=shown present_s=1.010")
        result = summary[4]
        self.assertEqual(result["consecutive_presentation_intervals"], 0)
        self.assertAlmostEqual(result["observed_display_interval_ms"]["p99"], 100)
        self.assertEqual(result["observed_display_intervals_crossing_frame_or_ticket_gaps"], 1)

    def test_missing_is_distinct_from_zero(self):
        cb = "event=cb frame=4 cb=8 sub=1 seg=0 metal=3 reason=flush prep_start_s=1 prep_end_s=2"
        summary, _ = self.parse(cb + " status=missing", "event=present frame=4 ticket=3 resource=1 enqueue_s=2 status=unshown")
        self.assertIsNone(summary[4]["observed_overlap_ms"])
        self.assertEqual(summary[4]["unshown_callbacks"], 1)
        self.assertIsNone(summary[4]["frames"][0]["producer_thread_cpu_ms"])
        with self.assertRaises(ValueError):
            self.parse(cb + " status=ok gpu_start_s=1.5 gpu_end_s=2.5")
        with self.assertRaises(ValueError):
            self.parse(cb + " status=error", cb + " status=error")


if __name__ == "__main__":
    unittest.main()
