#!/usr/bin/env python3
"""Behavioral tests for527 journal windows, aggregation and measurement scope."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('cell527_analyzer', ROOT / 'tools/rpcs3/analyze_cell527_logs.py')
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


def event(marker, fields, timestamp=10, build='527', pid=42, prefix='TID:7: ', stage='core_log'):
    return dict(timestamp=timestamp, build=build, pid=pid, stage=stage,
                message=prefix + marker + ' ' + fields)


def frame(window, histogram='10000:1', intervals=1, timestamp=10, **kwargs):
    return event('FRAMEPROF527', f'session=1 window={window} phase=guest_unclassified '
        f'intervals={intervals} unavailable=0 total_interval_ms=10 window_ms=5000 '
        f'median_ms=999 p95_ms=999 p99_ms=999 max_ms=100 over50ms=0 over100ms=0 '
        f'histogram_upper_us={histogram}', timestamp=timestamp, **kwargs)


class JournalAnalyzerTests(unittest.TestCase):
    def analyze(self, entries, phases=(), mirror=None):
        with tempfile.TemporaryDirectory(prefix='cell527-journal-') as tmp:
            first = Path(tmp) / 'diagnostic.jsonl'
            first.write_text(''.join(json.dumps(row) + '\n' for row in entries))
            paths = [first]
            if mirror is not None:
                second = Path(tmp) / 'milestones.jsonl'
                second.write_text(''.join(json.dumps(row) + '\n' for row in mirror))
                paths.append(second)
            return ANALYZER.analyze(paths, phases)

    def test_histograms_merge_with_sample_weights_and_never_average_reported_quantiles(self):
        result = self.analyze([frame(1, '10000:99', 99), frame(2, '100000:1', 1, timestamp=15)])
        group = result['groups'][0]
        self.assertEqual(group['intervals'], 100)
        self.assertEqual(group['frame_quantile_upper_bound_ms'], {'50': 10, '95': 10, '99': 10})
        self.assertEqual(group['histogram_upper_us'], {10000: 99, 100000: 1})
        self.assertNotEqual(group['frame_quantile_upper_bound_ms']['95'], 999)

    def test_mirrors_deduplicate_by_explicit_window_ignoring_prefix_stage_and_timestamp(self):
        original = [frame(1), event('WAITPROF527', 'session=1 window=1 pipeline_queue=2:20:12', 10.02)]
        mirrored = [dict(row, timestamp=row['timestamp'] + .03, stage='milestone',
                         message=row['message'].replace('TID:7: ', 'forwarded: ')) for row in original]
        result = self.analyze(original, mirror=mirrored)
        self.assertEqual(result['duplicate_rows'], 2)
        self.assertEqual(result['groups'][0]['frame_windows'], 1)
        self.assertEqual(result['groups'][0]['waits']['pipeline_queue']['count'], 2)

    def test_phase_boundary_rejects_entire_window_including_reports(self):
        entries = [frame(1, timestamp=10), frame(2, timestamp=15),
            event('WAITPROF527', 'session=1 window=1 cpu_gpu_fence=3:10:6', 10.01),
            event('WAITPROF527', 'session=1 window=2 cpu_gpu_fence=1:2:2', 15.01)]
        result = self.analyze(entries, [dict(name='gameplay', start=7, end=16)])
        self.assertEqual(result['rejected']['straddled_or_unlabelled_window'], 1)
        self.assertEqual(result['groups'][0]['frame_windows'], 1)
        self.assertEqual(result['groups'][0]['waits']['cpu_gpu_fence']['count'], 1)
        self.assertEqual(result['groups'][0]['phase'], 'gameplay')

    def test526_without_new_metrics_remains_unmeasured(self):
        result = self.analyze([dict(timestamp=10, build='526', pid=1,
            message='fps=35 process_resident=12345', stage='performance_sample')])
        self.assertEqual(result['groups'], [])
        self.assertEqual(result['observed_builds'], ['526'])
        self.assertEqual(result['builds_without_527_metrics'], ['526'])

    def test_negative_or_nonfinite_waits_are_rejected(self):
        for value in ('1:-2:1', '1:2:-1', '1:nan:1', '1:inf:1', '-1:0:0', '1.5:2:2'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.analyze([frame(1), event('WAITPROF527', f'session=1 window=1 cpu_gpu_fence={value}', 10.01)])

    def test_two_jit_windows_sum_costs_but_keep_metadata_and_duration_maxima(self):
        result = self.analyze([frame(1), frame(2, timestamp=15),
            event('JITPUB527', 'session=1 window=1 calls=3 empty_calls=1 deferred_calls=0 history_ranges=100 dirty_ranges=3 '
                'flushed_bytes=64 total_ms=10 max_ms=7 retained_metadata_bytes=120 peak_metadata_bytes=200', 10.01),
            event('JITPUB527', 'session=1 window=2 calls=2 empty_calls=0 deferred_calls=1 history_ranges=200 dirty_ranges=2 '
                'flushed_bytes=32 total_ms=5 max_ms=4 retained_metadata_bytes=80 peak_metadata_bytes=180', 15.01)])
        jit = result['groups'][0]['jit']
        self.assertEqual(jit['calls'], 5)
        self.assertEqual(jit['total_ms'], 15)
        self.assertEqual(jit['max_ms'], 7)
        self.assertEqual(jit['historical_range_visits_avoided'], 295)
        self.assertEqual(jit['retained_metadata_bytes_observed_max'], 120)
        self.assertEqual(jit['peak_metadata_bytes_observed_max'], 200)

    def test_memory_counts_and_peaks_keep_session_scope(self):
        result = self.analyze([frame(1), frame(2, timestamp=15),
            event('MEMPROF527', 'session=1 window=1 valid=1 samples=10 footprint=100 resident=80 compressed=20 virtual=1000 '
                'peak_footprint=900 peak_resident=700 peak_compressed=50 peak_virtual=2000', 10.01),
            event('MEMPROF527', 'session=1 window=2 valid=1 samples=20 footprint=110 resident=90 compressed=10 virtual=900 '
                'peak_footprint=900 peak_resident=700 peak_compressed=50 peak_virtual=2000', 15.01)],
            [dict(name='gameplay', start=0, end=20)])
        memory = result['groups'][0]['memory']
        self.assertEqual(memory['reports'], 2)
        self.assertEqual(memory['valid_instant_reports'], 2)
        self.assertEqual(memory['session_valid_samples_observed_max'], 20)
        self.assertEqual(memory['reported_instant_max']['footprint'], 110)
        self.assertEqual(memory['session_sampled_peaks']['footprint'], 900)
        self.assertIn('may predate this phase', memory['session_sampled_peaks_scope'])
        self.assertNotIn('phase_sampled_max', memory)
        self.assertNotIn('valid_samples', memory)

    def test_out_of_order_records_associate_with_their_own_window(self):
        result = self.analyze([event('WAITPROF527', 'session=1 window=2 llvm_budget_cv=2:9:6', 9),
            frame(1, timestamp=10), frame(2, timestamp=15),
            event('WAITPROF527', 'session=1 window=1 llvm_budget_cv=1:3:3', 16)])
        self.assertEqual(result['groups'][0]['waits']['llvm_budget_cv']['count'], 3)
        self.assertEqual(result['groups'][0]['window_association_modes'], ['explicit_session_window'])
        self.assertEqual(result['rejected'], {})

    def test_conflicting_mirror_rejects_whole_window(self):
        result = self.analyze([frame(1)], mirror=[frame(1, histogram='10000:2', intervals=2)])
        self.assertEqual(result['groups'], [])
        self.assertEqual(result['rejected']['conflicting_duplicate_window'], 1)

    def test_window_identity_separates_sessions_and_processes(self):
        result = self.analyze([frame(1), frame(1, pid=43),
            event('FRAMEPROF527', frame(1)['message'].split('FRAMEPROF527 ', 1)[1].replace('session=1', 'session=2'))])
        self.assertEqual(len(result['groups']), 3)
        self.assertEqual(result['duplicate_rows'], 0)


if __name__ == '__main__':
    unittest.main()
