"""Export complete 300-present windows from private host logs as aggregate CSV."""
import argparse
import csv
from pathlib import Path
import re
import sys
from statistics import median
from zipfile import ZipFile


PATTERNS = (
    (r"RewindBox frame intervals \d+\.\.(\d+): (\d+) samples, (\d+) ns, above 100/200/500 ms (\d+)/(\d+)/(\d+)",
     "interval_samples interval_ns gt100ms gt200ms gt500ms"),
    (r"frame interval up to frame (\d+): .*? p99 ([\d.]+) ms", "frame_ms_p99"),
    (r"displayed window up to frame (\d+): observed ([\d.]+) fps, (\d+) visible timestamps",
     "display_real_fps visible_timestamps"),
    (r"timing up to frame (\d+): frame time p50 ([\d.]+) / p95 ([\d.]+) / max ([\d.]+).*?GPU p50 ([\d.]+).*?thermal state (\d+)",
     "frame_ms_p50 frame_ms_p95 frame_ms_max gpu_ms_p50 thermal"),
    (r"translation up to frame (\d+): .*?CPU ([\d.]+) ms, (\d+) draws per frame",
     "submit_cpu_ms_mean draws_mean"),
    (r"on-screen up to frame (\d+): .*?footprint (\d+) MiB", "footprint_mib"),
    (r"displayed distribution up to frame (\d+): p50 ([\d.]+) p95 ([\d.]+) p99 ([\d.]+) ms; known (\d+)",
     "display_ms_p50 display_ms_p95 display_ms_p99 known_display"),
    (r"displayed streaks up to frame (\d+): covered ([\d.]+) s, missed slots (\d+) .*?late intervals (\d+)",
     "display_covered_s missed_slots late_intervals"),
    (r"pso-window-shaders\] frame=(\d+).*?draws_skipped_shlib=(\d+) draws_skipped_pso=(\d+) submit_msl_blocked_count=(\d+) submit_msl_blocked_ms=([\d.]+).*?submit_shared_wait_ms=([\d.]+)",
     "draws_skipped_shlib draws_skipped_pso submit_msl_blocked_count submit_msl_blocked_ms shared_wait_ms"),
    (r"same-pass feedback sampling up to frame (\d+): .*?④ snapshot (\d+) \(([\d.]+) MB copied\)",
     "snapshots snapshot_mib"),
    (r"\[rb-speed\] up to present (\d+): game speed ([\d.]+) %.*?; ([\d.]+) presents a second, at interval 1 / 2 / 3\+ (\d+) / (\d+) / (\d+).*?frame interpolation (on|off), (\d+) interpolated and (\d+) real frames shown",
     "game_speed_pct engine_fps interval1 interval2 interval3plus fi generated_shown real_shown_by_fi"),
)


LONG_FRAME = re.compile(r"\[longframe\] frame=(\d+) begin_ns=(\d+) end_ns=(\d+) cause=(\w+)")
LONG_FIELDS = ("logged_50ms", "logged_gt100ms", "logged_gt200ms", "logged_gt500ms", "logged_50ms_submit", "logged_50ms_guest_sync")


def long_frames(data):
    windows = {}
    seen = set()
    for match in LONG_FRAME.finditer(data):
        frame, start, end = map(int, match.groups()[:3])
        if frame in seen or end < start:
            raise ValueError(f"invalid long frame {frame}")
        seen.add(frame)
        row = windows.setdefault((frame + 299) // 300 * 300, [0] * len(LONG_FIELDS))
        ns = end - start
        row[0] += 1
        for i, threshold in enumerate((100, 200, 500), 1):
            row[i] += ns > threshold * 1_000_000
        row[4] += match[4] == "submit"
        row[5] += match[4] == "guest_sync"
    return windows


WAIT_FIELDS = ("wait_samples", "wait_address_signal_samples", "wait_selection_ms_p50", "wake_to_impl_return_ms_p50")


def sampled_waits(data):
    windows = {}
    for line in data.splitlines():
        if "[rb-mkw-wait-path]" not in line or "until_selection_ms=" not in line:
            continue
        fields = dict(re.findall(r"(\w+)=(\S+)", line))
        end = (int(fields["frame"]) + 299) // 300 * 300
        windows.setdefault(end, []).append((
            fields["svc"] == "0x34" and fields["waker_svc"] == "0x35",
            float(fields["until_selection_ms"]), float(fields["selection_to_impl_ms"])
        ))
    result = {}
    for end, rows in windows.items():
        signal, selection, resume = zip(*rows)
        result[end] = (len(rows), sum(signal), round(median(selection), 4), round(median(resume), 4))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("members", nargs="+")
    args = parser.parse_args()
    fields = [field for _, names in PATTERNS for field in names.split()]
    writer = csv.DictWriter(sys.stdout, ["log", "end_present", *fields, "generated_fps_approx", *LONG_FIELDS, *WAIT_FIELDS], lineterminator="\n")
    writer.writeheader()
    with ZipFile(args.archive) as archive:
        for member in args.members:
            data = archive.read(member).decode(errors="replace")
            long_by_window = long_frames(data)
            wait_by_window = sampled_waits(data)
            windows = {}
            for pattern, names in PATTERNS:
                for match in re.finditer(pattern, data):
                    frame, *values = match.groups()
                    row = windows.setdefault(int(frame), {})
                    for key, value in zip(names.split(), values, strict=True):
                        if key in row:
                            raise ValueError(f"Repeated {key} at frame {frame} in {member}")
                        row[key] = value
            for frame, row in sorted(windows.items()):
                if "engine_fps" not in row:
                    continue
                count = sum(int(row[x]) for x in ("interval1", "interval2", "interval3plus"))
                if count != 300:
                    continue
                row["generated_fps_approx"] = round(int(row["generated_shown"]) * float(row["engine_fps"]) / count, 2)
                if long_by_window:
                    row.update(zip(LONG_FIELDS, long_by_window.get(frame, [0] * len(LONG_FIELDS)), strict=True))
                if frame in wait_by_window:
                    row.update(zip(WAIT_FIELDS, wait_by_window[frame], strict=True))
                writer.writerow(dict(log=member, end_present=frame, **row))


if __name__ == "__main__":
    main()
