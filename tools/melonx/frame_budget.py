#!/usr/bin/env python3
"""Per-frame time budget of one MeloNX session against a frame-time target, from the RewindBox performance journal.

    python3 tools/melonx/frame_budget.py MeloNX-performance.log --pid 49375 --window 52-72 --window 88- [--exclude 197-205]
        [--target-fps 30] [--json]

For that PID only, over each window of seconds (t= values of the per-second lines, both ends included, paused seconds
left out), from the presentation gaps of the journal (gaps=: every interval between two presented frames, in ms, written
on the line of the second in which the later frame was presented; the first frame after a pause starts a new series, so
the pause itself is not a gap):

- frames (the gaps), their total time, the mean, median, p95 and p99 frame time, the longest;
- gaps over 50, 100, 500 and 1000 ms, and gaps over 100 ms per minute of the window;
- the excess over the target: mean - target, in ms per frame, and its split, each class counted once:
      stutters     sum of (gap - target) over the gaps above 100 ms, divided by all the frames of the window;
      slow frames  the same over the gaps above the target and up to 100 ms;
      fast frames  the same over the gaps at or below the target (zero or negative);
  the three add up to the excess exactly;
- the engine's game FPS (distinct game frames, fps= first value): mean and median over the seconds of the window;
- the footprint (max) and the device memory available (min), from mem=;
- where the journal has them (bridge of lot 10 and 11): the memory activity of the process (vm=: MiB newly compressed
  and pages decompressed, 16 KiB each, over the window; decompressed pages per line, median and maximum; page-ins) and
  how its CPU time was served (hw=: medians of the clock in GHz, of the instructions per cycle, of the share on
  performance cores and of the time ready without a core, both per cent of the CPU time used), with the instructions
  executed per presented frame (clock x instructions per cycle x CPU time of each line, summed, over the frames);
  and, for the threads cpu= lists in at least a quarter of the window's lines, their median share of a core and (pc=)
  the median per cent of their CPU time spent on performance cores.

The journal rounds a gap to the millisecond and the display shows a frame on a refresh: a gap within 1 ms of a multiple
of 1000/60 ms is taken as that multiple (33 -> 33.33), so a frame on target contributes zero, not -0.33. A journal line
can cover more than one second when the process stalls: its gaps are all on that line, none is lost.

--exclude removes seconds from every window (an interval that has another, known cause, reported apart).
The figures are end to end per presented frame; thread times are not in this report and must never be added to it.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from playability_verdict import percentile, read  # noqa: E402

REFRESH = 1000 / 60


def exact(gap):
    """The gap on the display's grid when the journal's rounded value is within 1 ms of a refresh multiple."""
    multiple = round(gap / REFRESH)
    return multiple * REFRESH if multiple >= 1 and abs(multiple * REFRESH - gap) < 1 else float(gap)


def budget(seconds, first, last, target, excluded=()):
    chosen = [s for s in seconds if s['t'] >= first and (last is None or s['t'] <= last) and not s['paused']
              and not any(a <= s['t'] <= b for a, b in excluded)]
    gaps = [exact(gap) for s in chosen for gap in s['gaps']]
    if not gaps:
        return dict(window=[first, last], frames=0)
    frames, total = len(gaps), sum(gaps)
    mean = total / frames

    def share(selected):
        return sum(gap - target for gap in selected) / frames

    stutters = [gap for gap in gaps if gap > 100.5]
    slow = [gap for gap in gaps if target + 0.5 < gap <= 100.5]
    fast = [gap for gap in gaps if gap <= target + 0.5]
    rates = [s['fps'] for s in chosen if s['fps'] is not None]
    footprints = [s['footprint'] for s in chosen if s['footprint'] is not None]
    devices = [s['device'] for s in chosen if s['device'] is not None and s['device'] >= 0]
    minutes = total / 60000

    def parts(key, index):
        values = []
        for s in chosen:
            fields = s.get(key)
            if fields and index < len(fields):
                try:
                    values.append(float(fields[index]))
                except ValueError:
                    pass  # "-": the journal could not tell
        return values

    memory = service = None
    decompressed = parts('vm', 1)
    if decompressed:
        memory = dict(lines=len(decompressed), compressedMiB=round(sum(parts('vm', 0))), decompressedMiB=round(sum(decompressed) * 16 / 1024),
                      decompressedPagesMedian=round(statistics.median(decompressed)), decompressedPagesMax=round(max(decompressed)),
                      pageIns=round(sum(parts('vm', 3))))
    clock = parts('hw', 0)
    if clock:
        def median(index):
            values = parts('hw', index)
            return round(statistics.median(values), 2) if values else None

        # Instructions of a line: clock (cycles per ns of CPU time) x instructions per cycle x CPU time (cpu= is per cent of
        # one core over the line, taken as one second).
        executed = 0.0
        for s in chosen:
            fields = s.get('hw')
            try:
                executed += float(fields[0]) * 1e9 * float(fields[1]) * s['cpu'] / 100
            except (TypeError, ValueError, IndexError):
                pass
        service = dict(lines=len(clock), clockGHzMedian=median(0), instructionsPerCycleMedian=median(1), performanceCoresPercentMedian=median(2),
                       readyWithoutACorePercentMedian=median(3), instructionsPerFrameMillions=round(executed / frames / 1e6) if executed else None)
    listed = {}
    for s in chosen:
        shares = s.get('pc') or []
        for index, (name, core, priority) in enumerate(s.get('threads') or []):
            entry = listed.setdefault(name, dict(core=[], performance=[], priority=set()))
            entry['core'].append(core)
            entry['priority'].add(priority)
            if index < len(shares) and shares[index].isdigit():
                entry['performance'].append(int(shares[index]))
    threads = [dict(name=name, lines=len(entry['core']), corePercentMedian=statistics.median(entry['core']),
                    priorities=sorted(entry['priority']),
                    performanceCoresPercentMedian=statistics.median(entry['performance']) if entry['performance'] else None)
               for name, entry in listed.items() if len(entry['core']) * 4 >= len(chosen)]
    threads.sort(key=lambda entry: -entry['corePercentMedian'] * entry['lines'])
    return dict(threads=threads or None, memoryActivity=memory, cpuService=service, window=[first, last if last is not None else chosen[-1]['t']], lines=len(chosen), frames=frames,
                seconds=round(total / 1000, 1), meanMs=round(mean, 1), medianMs=round(statistics.median(gaps), 1),
                p95Ms=round(percentile(gaps, 95), 1), p99Ms=round(percentile(gaps, 99), 1), maxMs=round(max(gaps)),
                presentedFps=round(1000 / mean, 1),
                over50=sum(1 for gap in gaps if gap > 50.5), over100=len(stutters), over500=sum(1 for gap in gaps if gap > 500),
                over1000=sum(1 for gap in gaps if gap > 1000), over100PerMinute=round(len(stutters) / minutes, 1),
                targetMs=round(target, 2), excessMs=round(mean - target, 1),
                stutterMs=round(share(stutters), 1), stutterSeconds=round(sum(stutters) / 1000, 1),
                slowMs=round(share(slow), 1), slowFrames=len(slow), fastMs=round(share(fast), 1), fastFrames=len(fast),
                gameFpsMean=round(statistics.fmean(rates), 1) if rates else None,
                gameFpsMedian=round(statistics.median(rates), 1) if rates else None,
                footprintMaxMiB=max(footprints) if footprints else None, deviceAvailableMinPercent=min(devices) if devices else None)


def span(text):
    first, _, last = text.partition('-')
    return int(first), int(last) if last else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('performance')
    parser.add_argument('--pid', required=True)
    parser.add_argument('--window', action='append', required=True, help='first-last seconds (t=), last optional: 88- is to the end')
    parser.add_argument('--exclude', action='append', default=[], help='first-last seconds left out of every window')
    parser.add_argument('--target-fps', type=float, default=30)
    parser.add_argument('--json', action='store_true')
    arguments = parser.parse_args()
    seconds, ended = read(arguments.performance, arguments.pid)
    if not seconds:
        raise SystemExit(f'no per-second line for pid {arguments.pid}')
    target = 1000 / arguments.target_fps
    excluded = [span(text) for text in arguments.exclude]
    assert all(b is not None for _, b in excluded), 'an excluded interval needs both ends'
    results = [budget(seconds, *span(text), target, excluded) for text in arguments.window]
    if arguments.json:
        print(json.dumps(dict(pid=arguments.pid, lastSecond=seconds[-1]['t'], ended=ended, excluded=excluded, windows=results), indent=1))
        return
    print(f'pid {arguments.pid}: {len(seconds)} per-second lines, last t={seconds[-1]["t"]}, '
          f'{"end line present" if ended else "no end line"}; target {target:.2f} ms'
          + (f'; excluded {", ".join(f"{a}-{b}" for a, b in excluded)}' if excluded else ''))
    for r in results:
        if not r['frames']:
            print(f't={r["window"][0]}-{r["window"][1]}: no presented frame')
            continue
        print(f't={r["window"][0]}-{r["window"][1]}: {r["frames"]} frames in {r["seconds"]} s; mean {r["meanMs"]} ms '
              f'({r["presentedFps"]} presented FPS), median {r["medianMs"]}, p95 {r["p95Ms"]}, p99 {r["p99Ms"]}, max {r["maxMs"]} ms')
        print(f'    excess {r["excessMs"]:+} ms per frame = stutters {r["stutterMs"]:+} ({r["over100"]} gaps over 100 ms, '
              f'{r["stutterSeconds"]} s) + slow frames {r["slowMs"]:+} ({r["slowFrames"]}) + fast frames {r["fastMs"]:+} ({r["fastFrames"]})')
        print(f'    gaps over 50/100/500/1000 ms: {r["over50"]}/{r["over100"]}/{r["over500"]}/{r["over1000"]}; '
              f'{r["over100PerMinute"]} over 100 ms per minute; game FPS mean {r["gameFpsMean"]}, median {r["gameFpsMedian"]}; '
              f'footprint max {r["footprintMaxMiB"]} MiB, device available min {r["deviceAvailableMinPercent"]} %')
        if r['memoryActivity']:
            m = r['memoryActivity']
            print(f'    memory activity (vm=, {m["lines"]} lines): {m["compressedMiB"]} MiB compressed, {m["decompressedMiB"]} MiB decompressed; '
                  f'pages decompressed per line median {m["decompressedPagesMedian"]}, max {m["decompressedPagesMax"]}; {m["pageIns"]} page-ins')
        if r['threads'] and any(entry['performanceCoresPercentMedian'] is not None for entry in r['threads']):
            print('    threads (cpu=, pc=; medians): ' + '; '.join(
                f'{entry["name"]} {entry["corePercentMedian"]:g} % of a core at priority {"/".join(str(p) for p in entry["priorities"])}, '
                + (f'{entry["performanceCoresPercentMedian"]:g} % on performance cores' if entry['performanceCoresPercentMedian'] is not None else 'share unknown')
                for entry in r['threads']))
        if r['cpuService']:
            c = r['cpuService']
            print(f'    CPU service (hw=, {c["lines"]} lines, medians): clock {c["clockGHzMedian"]} GHz, {c["instructionsPerCycleMedian"]} instructions '
                  f'per cycle, {c["performanceCoresPercentMedian"]} % on performance cores, {c["readyWithoutACorePercentMedian"]} % ready without '
                  f'a core; about {c["instructionsPerFrameMillions"]} million instructions per frame')


if __name__ == '__main__':
    main()
