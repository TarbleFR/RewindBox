#!/usr/bin/env python3
"""Read historical Metal encoder timings from an exported engine archive."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from statistics import median
import re
from zipfile import ZipFile

GAMES = {"Mario Kart World": "0400C3F00006E000", "Zelda": "0400486024DEC000",
         "Fire Emblem": "04007EF01F8AE000"}
ENCODER = re.compile(
    r"\[gpuprof\] F(\d+)\s+(\d+)\s+(\d+\.\d+) us (.+?) start ([-+]?\d+\.\d+) seg (\d+)"
)
RENDER = re.compile(r"render pass \d+ (\d+x\d+) colors (\d+) depth (\d+) loads \d+ draws (\d+)")


def union_us(intervals):
    end = float("-inf")
    length = 0.0
    for start, stop in sorted(intervals):
        length += max(0.0, stop - max(end, start))
        end = max(end, stop)
    return length


def summarize(archive, title_id):
    frames = defaultdict(dict)
    raw_atlas_passes = 0
    for path in archive.namelist():
        if title_id not in path or "/host-" not in path or not path.endswith(".log"):
            continue
        for line in archive.read(path).decode("utf-8", errors="replace").splitlines():
            match = ENCODER.search(line)
            if match:
                frame, index, duration, kind, start, _ = match.groups()
                render = RENDER.fullmatch(kind)
                if render and render[1] == "6144x6144":
                    raw_atlas_passes += 1
                frames[path, frame][int(index)] = (float(start), float(duration), render)

    depth_counts = Counter()
    depth_frame_us = []
    atlas_pass_us = []
    atlas_kinds = Counter()
    for encoders in frames.values():
        depth_intervals = []
        for start, duration, render in encoders.values():
            if not render:
                continue
            dimensions, colors, depth, draws = render.groups()
            if colors == "0" and depth == "1":
                depth_intervals.append((start, start + duration))
                depth_counts[dimensions] += 1
            if dimensions == "6144x6144":
                atlas_pass_us.append(duration)
                atlas_kinds[int(colors), int(depth), int(draws)] += 1
        if depth_intervals:
            depth_frame_us.append(union_us(depth_intervals))

    print(f"{len({path for path, _ in frames})} sessions, {len(frames)} captured frames")
    if depth_frame_us:
        print(f"{sum(depth_counts.values())} depth-only passes across {len(depth_frame_us)} frames")
        print(f"Observed per-frame depth-only interval union p50: {median(depth_frame_us):.1f} µs")
        print("Most frequent depth-only dimensions:", depth_counts.most_common(6))
    if atlas_pass_us:
        print(f"6144×6144 passes: {len(atlas_pass_us)} unique ({raw_atlas_passes} log rows), "
              f"p50 {median(atlas_pass_us):.1f} µs")
        print("6144×6144 pass counts by (color, depth, draws):", dict(atlas_kinds))


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("engine_export")
    args = parser.parse_args()
    with ZipFile(args.engine_export) as archive:
        for title, title_id in GAMES.items():
            print(title)
            summarize(archive, title_id)


if __name__ == "__main__":
    main()
