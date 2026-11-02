#!/usr/bin/env python3
"""Frame-time report of one MeloNX session from the RewindBox diagnostics journals.

    python3 tools/melonx/frame_report.py MeloNX-performance.log MeloNX-core.log --pid 66181 [--from 40 --to 100] [--passes]

Reads, for that PID only:
- MeloNX-performance.log per-second lines: engine game FPS (distinct game frames), presented
  frames, and from build 620 on the presentation gaps (gaps=..., long=over50/over100), from which
  p50/p95/p99 frame times and pauses over 50 and 100 ms are computed over the chosen seconds
  (t= values, seconds since the controls were installed). Older builds have no gap list: the
  report then says so and gives only per-second rates.
- the 5.1 s core-performance windows that end inside the chosen seconds: GPU-thread time in the
  DMA engine, texture flush actions (count, time), render-thread syncs, buffer read-backs and
  pipeline builds. Durations are nested (a flush action runs inside the DMA engine and waits in
  syncInvoke), so they are listed side by side, never summed.
- MeloNX-core.log: the last DMA summary line and every attribution line of the Hogwarts DMA policy.

With --passes, each stretch of play between two paused stretches is also reported on its own (the
RewindBox pause writes "paused" on every per-second line). The device-test protocol pauses before
and after each 60 s pass, so startup, menus and loading before the first pause are left out.
"""
import argparse
import json
import re
import statistics


def percentile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, round(q / 100 * (len(ordered) - 1))))
    return ordered[index]


def passes(seconds):
    """The unpaused stretches that have a paused stretch on both sides, in order."""
    found, current, opened = [], [], False
    for second in seconds:
        if second['paused']:
            if opened and current:
                found.append(current)
            current, opened = [], True
        elif opened:
            current.append(second)
    return found


def summarize(chosen, indent=''):
    rates = [s['fps'] for s in chosen if s['fps'] > 0]
    presented = sum(s['presented'] for s in chosen)
    print(indent + (f"Game FPS (distinct game frames, per-second engine rate): mean {statistics.mean(rates):.1f}, "
                    f"median {statistics.median(rates):.1f}, min {min(rates):.1f}" if rates else 'Game FPS: none'))
    print(indent + f"Presented frames: {presented} in {len(chosen)} s ({presented / max(1, len(chosen)):.1f}/s); "
          f"thermal states {sorted({s['thermal'] for s in chosen})}")
    gaps = [g for s in chosen if s['gaps'] for g in s['gaps']]
    if any(s['gaps'] is not None for s in chosen):
        over50 = sum(s['over50'] or 0 for s in chosen)
        over100 = sum(s['over100'] or 0 for s in chosen)
        print(indent + f"Frame time (presentation gaps, {len(gaps)} frames): p50 {percentile(gaps, 50)} ms, "
              f"p95 {percentile(gaps, 95)} ms, p99 {percentile(gaps, 99)} ms, max {max(gaps) if gaps else None} ms; "
              f"pauses over 50 ms {over50}, over 100 ms {over100}; frames at or under 33.4 ms {sum(1 for g in gaps if g <= 33.4)}")
    else:
        print(indent + 'Frame time: this build has no presentation gap list (build 620 and later have it); '
              f"longest gap per second: max {max(s['maxGap'] for s in chosen):.1f} ms")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('performance')
    parser.add_argument('core')
    parser.add_argument('--pid', required=True)
    parser.add_argument('--from', dest='start', type=int, default=None, help='first second (t=) included')
    parser.add_argument('--to', dest='end', type=int, default=None, help='last second (t=) included')
    parser.add_argument('--passes', action='store_true', help='also report each stretch between two paused stretches')
    args = parser.parse_args()
    marker = f'"pid":"{args.pid}"'
    seconds, windows, context = [], [], None
    for line in open(args.performance, encoding='utf-8', errors='replace'):
        if marker not in line:
            continue
        if line.startswith('[MeloNX:perf] t='):
            body = line.split(' context=')[0]
            stamp = json.loads(line.split(' context=', 1)[1])
            context = context or stamp
            t = int(re.search(r' t=(\d+)', body).group(1))
            fps = re.search(r' fps=([\d.]+)/', body)
            pres = re.search(r' pres=(\d+)/([\d.]+)/(\d+)/(\d+)', body)
            gaps = re.search(r' gaps=([\d,]+)', body)
            long_gaps = re.search(r' long=(\d+)/(\d+)', body)
            seconds.append(dict(t=t, fps=float(fps.group(1)) if fps else 0.0, presented=int(pres.group(1)) if pres else 0,
                                maxGap=float(pres.group(2)) if pres else 0.0,
                                gaps=[int(v) for v in gaps.group(1).split(',')] if gaps else None,
                                over50=int(long_gaps.group(1)) if long_gaps else None,
                                over100=int(long_gaps.group(2)) if long_gaps else None,
                                thermal=re.search(r' th=(\w+)', body).group(1) if ' th=' in body else '?',
                                paused=body.rstrip().endswith(' paused'),
                                stamp=stamp.get('timestamp', '')))
        elif line.startswith('[MeloNX:core-performance]'):
            value = json.loads(line.split('] ', 1)[1])
            data = json.loads(value['diagnostic'])
            if data.get('schema') == 1 and 'gpuWork' in data:
                windows.append((value.get('timestamp', ''), data))
    if not seconds:
        raise SystemExit('No per-second line for PID ' + args.pid)
    first = args.start if args.start is not None else min(s['t'] for s in seconds if s['fps'] > 0)
    last = args.end if args.end is not None else max(s['t'] for s in seconds)
    chosen = [s for s in seconds if first <= s['t'] <= last]
    print(f"Session PID {args.pid}: build {context.get('build')}, Core {context.get('coreSource', '')[:12]}, "
          f"title {context.get('titleId')}; seconds {first}..{last} ({len(chosen)} lines)")
    summarize(chosen)
    if args.passes:
        found = passes(chosen)
        print(f'Passes between two paused stretches: {len(found)}')
        for number, stretch in enumerate(found, 1):
            print(f"Pass {number}: seconds {stretch[0]['t']}..{stretch[-1]['t']} ({len(stretch)} s), "
                  f"{stretch[0]['stamp'][11:19]}..{stretch[-1]['stamp'][11:19]} UTC")
            summarize(stretch, '  ')
    print('Core windows ending inside these seconds (5.1 s; nested durations, never summed):')
    begin, finish = min(s['stamp'] for s in chosen), max(s['stamp'] for s in chosen)
    for stamp, data in windows:
        if not begin <= stamp[:19] + 'Z' <= finish:
            continue
        g, p, c = data['gpuWork'], data['phases'], data['counts']
        print(f"  {stamp[11:19]} GPU thread {p['gpuDispatch'][1]:.0f} ms | dma {g['dma'][1]:.0f} ms, texture flush actions "
              f"{g['texFlushAction'][0]} = {g['texFlushAction'][1]:.0f} ms | render-thread syncs {p['syncInvoke'][1]:.0f} ms | "
              f"buffer read-backs {p['bufferReadback'][0]} = {p['bufferReadback'][1]:.0f} ms | pipeline builds "
              f"{p['graphicsPipelineBuild'][0]} = {p['graphicsPipelineBuild'][1]:.0f} ms | render thread busy "
              f"{p['renderDrain'][1]:.0f} ms, idle {p['renderIdle'][1]:.0f} ms | draws {c['draws']}")
    summary, attributions = None, []
    for line in open(args.core, encoding='utf-8', errors='replace'):
        if f'"pid":{args.pid},' not in line:
            continue
        if 'DMA guest-memory copies:' in line:
            summary = line
        elif any(key in line for key in ('DMA slow source read #', 'DMA GPU source copy', 'DMA region upload',
                                         'DMA float GPU copy', 'Background pipeline compile missed', 'ServiceNv Wait')):
            attributions.append(line)
    if summary:
        print('Last DMA summary:', json.loads(summary.split('] ', 1)[1])['diagnostic'])
    for line in attributions:
        value = json.loads(line.split('] ', 1)[1])
        print(f"  {value['timestamp'][11:23]} {value['diagnostic']}")


if __name__ == '__main__':
    main()
