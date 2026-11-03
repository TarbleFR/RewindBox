#!/usr/bin/env python3
"""Frame-time report of one MeloNX session from the RewindBox diagnostics journals.

    python3 tools/melonx/frame_report.py MeloNX-performance.log MeloNX-core.log --pid 66181 [--stderr MeloNX-stderr.log]
        [--from 40 --to 100] [--passes]

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
- MeloNX-core.log: the last DMA summary line (from build 623 it counts the deferred read-backs, their
  declines and the first-access flushes) and every attribution line of the Hogwarts DMA policy.
- Per core window and over the chosen seconds, milliseconds per presented frame of each wait and of
  the render thread's own work: GPU-thread waits for the render thread (syncInvoke, the read-back
  flushes), queue backpressure, render-thread fence waits (bufferReadback), render-thread work (busy
  minus fence waits) and pipeline builds. These overlap across threads and are never summed.
- From build 623, the render thread's 5 s lines in MeloNX-core.log ("Render thread commands over"):
  the command types ranked by time over all windows and over the slow ones (game FPS below the
  median), with milliseconds per presented frame.
- From build 623, the Vulkan backend's 5 s lines in MeloNX-core.log ("Vulkan render stages over"): per
  presented frame, the draw preparation (pipelines, barriers, descriptor updates, auto-flushes, the
  rest), render passes begun (and begun again on the same framebuffer), command buffer submissions
  (and their queue part) and the presentation (image acquisition, queue present).
- With --stderr, from build 623, MoltenVK's statistics (every 300 presented frames): per frame, GPU
  execution of the Metal command buffers, Metal encoding on MoltenVK's submission thread, drawable
  waits, and command buffers per frame. The statistics accumulate over a device's life: the report
  takes the difference between two consecutive summaries.
- Per presented frame and per game frame (the per-second engine rates summed over a window), and a
  ceiling per resource (1000 / its own busy milliseconds per frame): the GPU thread, the render
  thread, MoltenVK's encoding and the GPU. The lowest ceiling is the limit to remove next.
- With --passes, a pass of at least 120 s also gets its first and last 60 s reported apart (the
  start and the end of a route, across the thermal drift).

With --passes, each stretch of play between two paused stretches is also reported on its own (the
RewindBox pause writes "paused" on every per-second line). The device-test protocol pauses before
and after each 60 s pass, so startup, menus and loading before the first pause are left out.
"""
import argparse
from datetime import datetime, timedelta
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


def seconds_in(seconds, stamp, window_ms):
    """The per-second lines inside the window that ends at the stamp."""
    end = stamp[:19]
    begin = (datetime.fromisoformat(end) - timedelta(milliseconds=window_ms)).isoformat()[:19]
    return [s for s in seconds if begin < s['stamp'][:19] <= end]


def frames_in(seconds, stamp, window_ms):
    """Frames presented during the window that ends at the stamp (the per-second lines inside it)."""
    return sum(s['presented'] for s in seconds_in(seconds, stamp, window_ms))


def game_frames_in(seconds, stamp, window_ms):
    """Distinct game frames during the window: the per-second engine rates summed."""
    return sum(s['fps'] for s in seconds_in(seconds, stamp, window_ms))


STAGE_LINE = re.compile(
    r'Vulkan render stages over (?P<window>[\d.]+) ms, (?P<frames>\d+) frames: draw prepare (?P<prepares>\d+) calls '
    r'(?P<prepare>[\d.]+) ms \(not ready (?P<notReady>\d+); pipelines (?P<pipelines>\d+) calls (?P<pipeline>[\d.]+) ms, '
    r'barriers (?P<barriers>[\d.]+) ms, descriptors (?P<descriptors>[\d.]+) ms, auto-flushes (?P<autoFlushes>\d+) calls '
    r'(?P<autoFlush>[\d.]+) ms\); (?:compute prepare (?P<computes>\d+) calls (?P<compute>[\d.]+) ms \(pipelines '
    r'(?P<computePipelines>\d+) calls (?P<computePipeline>[\d.]+) ms, barriers (?P<computeBarriers>[\d.]+) ms, descriptors '
    r'(?P<computeDescriptors>[\d.]+) ms; dispatches (?P<dispatches>\d+), render passes ended (?P<dispatchPassEnds>\d+)\); )?'
    r'render passes (?P<passes>\d+) begun (?P<pass>[\d.]+) ms \(same framebuffer again '
    r'(?P<resumes>\d+)\); submits (?P<submits>\d+) calls (?P<submit>[\d.]+) ms \(queue (?P<queue>[\d.]+) ms\); fence waits '
    r'on the render thread: buffer writes (?P<writeWaits>\d+) calls (?P<writeWait>[\d.]+) ms, reads (?P<readWaits>\d+) calls '
    r'(?P<readWait>[\d.]+) ms; on other threads (?P<otherWaits>\d+) calls (?P<otherWait>[\d.]+) ms; present '
    r'(?P<presents>\d+) calls (?P<present>[\d.]+) ms \(acquire (?P<acquire>[\d.]+) ms, queue present (?P<queuePresent>[\d.]+) ms\)')


def report_render_stages(lines, chosen):
    """The Vulkan render thread's stages per presented frame, per 5 s line and over all of them; returns the totals."""
    begin, finish = min(s['stamp'] for s in chosen)[:19], max(s['stamp'] for s in chosen)[:19]
    parsed = []
    for value in lines:
        match = STAGE_LINE.search(value['diagnostic'])
        if match and begin <= value['timestamp'][:19] <= finish:
            numbers = {key: float(v) if v is not None else 0.0 for key, v in match.groupdict().items()}
            parsed.append((value['timestamp'][11:19], numbers))
    if not parsed:
        return None

    def describe(n, frames):
        rest = n['prepare'] - n['pipeline'] - n['barriers'] - n['descriptors'] - n['autoFlush']
        return (f"draw prepare {n['prepare'] / frames:.1f} ms in {n['prepares'] / frames:.0f} draws (pipelines "
                f"{n['pipeline'] / frames:.2f}, barriers {n['barriers'] / frames:.2f}, descriptors {n['descriptors'] / frames:.2f}, "
                f"auto-flushes {n['autoFlush'] / frames:.2f}, rest {rest / frames:.2f}; not ready {n['notReady'] / frames:.1f}), "
                f"compute prepare {n['compute'] / frames:.1f} ms in {n['dispatches'] / frames:.0f} dispatches (pipelines "
                f"{n['computePipeline'] / frames:.2f}, barriers {n['computeBarriers'] / frames:.2f}, descriptors "
                f"{n['computeDescriptors'] / frames:.2f}; render passes ended {n['dispatchPassEnds'] / frames:.0f}), "
                f"render passes {n['passes'] / frames:.0f} begun {n['pass'] / frames:.2f} ms (same framebuffer again "
                f"{n['resumes'] / frames:.0f}), submits {n['submits'] / frames:.1f} = {n['submit'] / frames:.2f} ms (queue "
                f"{n['queue'] / frames:.2f}), fence waits on the render thread {n['writeWait'] / frames:.2f} ms for "
                f"{n['writeWaits'] / frames:.0f} buffer writes and {n['readWait'] / frames:.2f} ms for {n['readWaits'] / frames:.1f} reads, "
                f"on other threads {n['otherWait'] / frames:.2f} ms for {n['otherWaits'] / frames:.1f}, "
                f"present {n['present'] / frames:.2f} ms (acquire {n['acquire'] / frames:.2f}, "
                f"queue present {n['queuePresent'] / frames:.2f})")

    print('Vulkan render stages per presented frame (render thread; the draw preparation and submissions run inside the '
          'command times above):')
    for stamp, n in parsed:
        if n['frames']:
            print(f"  {stamp} ({n['frames']:.0f} frames in {n['window'] / 1000:.1f} s): {describe(n, n['frames'])}")
    totals = {key: sum(n[key] for _, n in parsed) for key in parsed[0][1]}
    if totals['frames']:
        print(f"  over these lines ({totals['frames']:.0f} frames): {describe(totals, totals['frames'])}")
    return totals


DETAIL_LINE = re.compile(
    r'Vulkan pass and GPU detail over (?P<window>[\d.]+) ms, (?P<frames>\d+) frames: same framebuffer again after '
    r'(?P<resumes>.*?); in-pass read barriers deferred (?P<deferred>\d+), kept for attachments (?P<kept>\d+); compute '
    r'descriptors by program size: up to 32 (?P<smallCalls>\d+) calls (?P<small>[\d.]+) ms, up to 256 (?P<mediumCalls>\d+) '
    r'calls (?P<medium>[\d.]+) ms, larger (?P<largeCalls>\d+) calls (?P<large>[\d.]+) ms \(largest (?P<largest>\d+)\); '
    r'exceptions (?P<exceptions>\d+)(?P<kinds> \(first: .*?\))?(?:; descriptor template fallbacks (?P<fallbacks>[^;]*))?'
    r'(?:; texture arrays: (?P<arrays>[^;]*))?; GPU (?P<gpu>.*)$')
GPU_BUSY = re.compile(r'busy (?P<busy>[\d.]+) ms per frame \((?P<share>\d+) % of (?P<span>\d+) ms\) in (?P<buffers>\d+) '
                      r'command buffers, longest (?P<longest>[\d.]+) ms')
# Build 631 and later: the template fallbacks by set and the texture array descriptor writes (EncodingPolicy).
FALLBACKS = re.compile(r'(?P<uniform>\d+)/(?P<storage>\d+)/(?P<texture>\d+)/(?P<image>\d+) \(uniform/storage/texture/image\)')
ARRAYS = re.compile(
    r'whole writes (?P<whole>\d+) \((?P<wholeElements>\d+) elements\), range writes (?P<ranges>\d+) \((?P<rangeElements>\d+) '
    r'elements, (?P<kept>\d+) kept\), write time (?P<writeMs>[\d.]+) ms, reference passes (?P<passes>\d+) \((?P<references>\d+) '
    r'references, (?P<referenceMs>[\d.]+) ms\), current binds (?P<current>\d+), sets added (?P<added>\d+), delivered path '
    r'(?P<delivered>\d+)')
ARRAY_KEYS = ('whole', 'wholeElements', 'ranges', 'rangeElements', 'kept', 'writeMs', 'passes', 'references', 'referenceMs',
              'current', 'added', 'delivered')


def report_render_detail(lines, chosen):
    """Build 628 and later: the commands that ended the passes begun again, the in-pass read barriers, the compute
    descriptor updates by program size, the exceptions and the GPU's busy time (Metal command buffers, merged). Build 631
    and later: the descriptor template fallbacks and the texture array descriptor writes."""
    begin, finish = min(s['stamp'] for s in chosen)[:19], max(s['stamp'] for s in chosen)[:19]
    parsed = []
    for value in lines:
        match = DETAIL_LINE.search(value['diagnostic'])
        if match and begin <= value['timestamp'][:19] <= finish:
            parsed.append((value['timestamp'][11:19], match))
    if not parsed:
        return None
    totals = dict(frames=0, deferred=0, kept=0, exceptions=0, gpuFrames=0, gpuBusy=0.0, encodingFrames=0)
    resumes, compute, kinds, gpu_states = {}, {}, [], set()
    fallbacks = dict(uniform=0, storage=0, texture=0, image=0)
    arrays = {key: 0.0 for key in ARRAY_KEYS}
    print('Vulkan pass and GPU detail per presented frame (build 628 and later):')
    for stamp, m in parsed:
        frames = int(m['frames'])
        if not frames:
            continue
        totals['frames'] += frames
        for key in ('deferred', 'kept', 'exceptions'):
            totals[key] += int(m[key])
        for part in m['resumes'].split(', '):
            name, _, count = part.rpartition(' ')
            if name and count.isdigit():
                resumes[name] = resumes.get(name, 0) + int(count)
        for size in ('small', 'medium', 'large'):
            calls, ms = compute.get(size, (0, 0.0))
            compute[size] = (calls + int(m[size + 'Calls']), ms + float(m[size]))
        if m['kinds']:
            kinds.append(m['kinds'][9:-1])
        busy = GPU_BUSY.fullmatch(m['gpu'])
        if busy:
            totals['gpuFrames'] += frames
            totals['gpuBusy'] += float(busy['busy']) * frames
        else:
            gpu_states.add(m['gpu'])
        encoding = ''
        fallback = FALLBACKS.fullmatch(m['fallbacks'] or '')
        array = ARRAYS.fullmatch(m['arrays'] or '')
        if fallback and array:
            # Build 631 and later: template fallbacks, and the texture array descriptor writes (EncodingPolicy).
            totals['encodingFrames'] += frames
            for key in fallbacks:
                fallbacks[key] += int(fallback[key])
            for key in ARRAY_KEYS:
                arrays[key] += float(array[key])
            encoding = (f"; template fallbacks {fallback['uniform']}/{fallback['storage']}/{fallback['texture']}/"
                        f"{fallback['image']}; arrays: whole writes {int(array['whole']) / frames:.2f} "
                        f"({int(array['wholeElements']) / frames:.0f} elements), range writes {int(array['ranges']) / frames:.2f} "
                        f"({int(array['rangeElements']) / frames:.0f} elements), {float(array['writeMs']) / frames:.2f} ms, "
                        f"reference passes {int(array['passes']) / frames:.1f} ({float(array['referenceMs']) / frames:.2f} ms), "
                        f"sets added {array['added']}, delivered path {array['delivered']}")
        print(f"  {stamp} ({frames} frames): resumed after {m['resumes']}; in-pass read barriers deferred "
              f"{int(m['deferred']) / frames:.1f}, kept {int(m['kept']) / frames:.1f}; compute descriptors "
              f"{float(m['small']) / frames:.1f} / {float(m['medium']) / frames:.1f} / {float(m['large']) / frames:.1f} ms "
              f"(up to 32 / 256 / larger, largest {m['largest']}); exceptions {m['exceptions']}{encoding}; GPU {m['gpu']}")
    frames = totals['frames'] or 1
    ranked = ', '.join(f'{name} {count / frames:.1f}' for name, count in sorted(resumes.items(), key=lambda item: -item[1])[:6])
    print(f"  over these lines ({totals['frames']} frames): passes begun again on the same framebuffer, per frame, after "
          f"{ranked or 'none'}; in-pass read barriers deferred {totals['deferred'] / frames:.1f} and kept for attachments "
          f"{totals['kept'] / frames:.1f} per frame; compute descriptors per frame: " +
          ', '.join(f"{label} {compute[size][1] / frames:.1f} ms in {compute[size][0] / frames:.1f} dispatches"
                    for size, label in (('small', 'up to 32'), ('medium', 'up to 256'), ('large', 'larger'))) +
          f"; exceptions {totals['exceptions']}")
    if totals['encodingFrames']:
        per = totals['encodingFrames']
        written = arrays['wholeElements'] + arrays['rangeElements']
        print(f"  descriptor encoding over {per} frames (build 631 and later): template fallbacks per frame "
              f"{fallbacks['uniform'] / per:.1f} uniform, {fallbacks['storage'] / per:.1f} storage, {fallbacks['texture'] / per:.1f} "
              f"texture, {fallbacks['image'] / per:.1f} image; texture array sets written whole {arrays['whole'] / per:.2f} and by "
              f"range {arrays['ranges'] / per:.2f} per frame, {written / per:.0f} elements written and {arrays['kept'] / per:.0f} "
              f"kept per frame, {arrays['writeMs'] / per:.2f} ms; reference passes {arrays['passes'] / per:.1f} per frame "
              f"({arrays['references'] / max(1.0, arrays['passes']):.0f} references each, {arrays['referenceMs'] / per:.2f} ms); "
              f"current binds {arrays['current'] / per:.1f}; sets added {arrays['added']:.0f}; delivered path "
              f"{arrays['delivered']:.0f}")
        totals.update(fallbacks=fallbacks, arrays=arrays)
    for kind in kinds:
        print(f'  exception kinds: {kind}')
    if totals['gpuFrames']:
        totals['gpu'] = totals['gpuBusy'] / totals['gpuFrames']
        print(f"  GPU busy (Metal command buffers, merged): {totals['gpu']:.1f} ms per frame over {totals['gpuFrames']} frames")
    elif gpu_states:
        print(f"  GPU busy: {', '.join(sorted(gpu_states))}")
    return totals


MVK_HEADER = re.compile(r'Performance statistics reporting every: (\d+) frames, avg FPS: ([\d.]+), elapsed time: ([\d.]+) seconds')
MVK_TRACKER = re.compile(r'\[mvk-info\]\s+(?P<name>\S.*?)(?: performance)?\s+avg: (?P<avg>[\d.]+) ?(?P<unit>[A-Za-z]*), '
                         r'latest: .*?count: (?P<count>\d+)')
# The RewindBox MoltenVK rebuild (build-utils/melonx/moltenvk/): counts since the previous summary, in both walks.
MVK_WALK = re.compile(r'\[mvk-info\]\s+Argument buffer resource usage \(RewindBox\)\s+(?P<mode>\w+) walk, '
                      r'encodes: (?P<encodes>\d+), elements: (?P<elements>\d+), dirty: (?P<dirty>\d+), '
                      r'useResource: (?P<calls>\d+), skipped: (?P<skipped>\d+), tessellation: (?P<tessellation>\d+), '
                      r'time: (?P<ms>[\d.]+) ms')
WALK_KEYS = ('encodes', 'elements', 'dirty', 'calls', 'skipped', 'tessellation')
MVK_NAMES = {'gpu': 'Execute a MTLCommandBuffer on GPU', 'encode': 'Encode VkCommandBuffer to MTLCommandBuffer',
             'submit': 'vkQueueSubmit() encoding to MTLCommandBuffers', 'drawable': 'Retrieve a CAMetalDrawable from CAMetalLayer',
             'present': 'Present swapchains in on GPU', 'retrieve': 'Retrieve a MTLCommandBuffer', 'interval': 'Frame interval'}


def read_moltenvk(path, pid):
    """MoltenVK's summaries for that PID, in order: each a dict of tracker name to (average, count)."""
    marker, summaries = f'"pid":"{pid}"', []
    for line in open(path, encoding='utf-8', errors='replace'):
        if marker not in line or '[mvk-info]' not in line:
            continue
        header = MVK_HEADER.search(line)
        if header:
            summaries.append(dict(frames=int(header.group(1)), elapsed=float(header.group(3)), trackers={}))
            continue
        walk = MVK_WALK.search(line)
        if walk:
            if summaries:
                summaries[-1]['walk'] = dict(mode=walk.group('mode'), ms=float(walk.group('ms')),
                                             **{key: int(walk.group(key)) for key in WALK_KEYS})
            continue
        tracker = MVK_TRACKER.search(line)
        if tracker and tracker.group('unit') in ('ms', ''):
            name = tracker.group('name').strip()
            # A summary whose header is missing or worded otherwise starts where a tracker repeats.
            if not summaries or name in summaries[-1]['trackers']:
                summaries.append(dict(frames=0, elapsed=float('nan'), trackers={}))
            summaries[-1]['trackers'][name] = (float(tracker.group('avg')), int(tracker.group('count')))
    return summaries


def report_moltenvk(summaries):
    """Per interval between two summaries: GPU execution, Metal encoding and drawable waits per frame; returns the totals."""
    if not summaries:
        print('MoltenVK statistics: none for this PID (build 623 and later log them every 300 presented frames to stderr)')
        return None
    print('MoltenVK statistics per presented frame (GPU execution of the Metal command buffers, Metal encoding on '
          "MoltenVK's submission thread):")
    previous, totals = {}, {}
    for summary in summaries:
        trackers = summary['trackers']
        interval = trackers.get(MVK_NAMES['interval'])
        if previous and interval and interval[1] < previous.get(MVK_NAMES['interval'], (0, 0))[1]:
            previous = {}   # a new device: its statistics start again
        delta = {}
        for key, name in MVK_NAMES.items():
            if name in trackers:
                avg, count = trackers[name]
                old_avg, old_count = previous.get(name, (0.0, 0))
                delta[key] = (avg * count - old_avg * old_count, count - old_count)
        frames = delta.get('interval', (0, summary['frames']))[1] or summary['frames']
        if frames:
            for key, (total, count) in delta.items():
                t, c = totals.get(key, (0.0, 0))
                totals[key] = (t + total, c + count)
            totals['frames'] = totals.get('frames', 0) + frames
            gpu, encode = delta.get('gpu', (0.0, 0)), delta.get('encode', (0.0, 0))
            print(f"  at {summary['elapsed']:.0f} s of MoltenVK time ({frames} frames, mean interval {delta.get('interval', (0.0, 1))[0] / frames:.1f} ms): "
                  f"GPU {gpu[0] / frames:.1f} ms in {gpu[1] / frames:.1f} command buffers, Metal encoding {encode[0] / frames:.1f} ms, "
                  f"vkQueueSubmit {delta.get('submit', (0.0, 0))[0] / frames:.1f} ms, drawable {delta.get('drawable', (0.0, 0))[0] / frames:.1f} ms")
            walk = summary.get('walk')
            if walk:
                for key in ('ms', *WALK_KEYS):
                    totals['walk_' + key] = totals.get('walk_' + key, 0) + walk[key]
                totals['walk_frames'] = totals.get('walk_frames', 0) + frames
                totals.setdefault('walk_modes', set()).add(walk['mode'])
                print(f"    argument buffer usage ({walk['mode']} walk): {walk['ms'] / frames:.2f} ms per frame in "
                      f"{walk['encodes'] / frames:.1f} encodes, {walk['elements'] / frames:.0f} elements, "
                      f"{walk['dirty'] / frames:.0f} dirty, useResource {walk['calls'] / frames:.0f} made and "
                      f"{walk['skipped'] / frames:.0f} skipped, tessellation {walk['tessellation'] / frames:.1f}")
        previous = trackers
    names = sorted(set().union(*(s['trackers'] for s in summaries)))
    print('  trackers seen: ' + '; '.join(names))
    if totals.get('walk_frames'):
        frames = totals['walk_frames']
        print(f"  argument buffer usage over {frames} frames ({'/'.join(sorted(totals['walk_modes']))} walk): "
              f"{totals['walk_ms'] / frames:.2f} ms per frame of Metal encoding, {totals['walk_elements'] / frames:.0f} "
              f"elements and {totals['walk_dirty'] / frames:.0f} dirty, useResource {totals['walk_calls'] / frames:.0f} "
              f"made and {totals['walk_skipped'] / frames:.0f} skipped per frame")
    return totals


def ceilings(windows_per_frame, stages, moltenvk, label='all windows', render_commands=None, detail=None):
    """1000 / busy milliseconds per frame of each resource, from what was measured; the lowest is the limit."""
    found = []
    if windows_per_frame:
        frames = sum(f for f, _, _ in windows_per_frame)
        total = lambda key: sum(p[key][1] for _, p, _ in windows_per_frame)
        gpu_thread = (total('gpuDispatch') - total('syncInvoke') - total('queueBackpressure')) / frames
        found.append(('GPU thread (its own work: dispatch minus its waits for the render thread)', gpu_thread))
        if stages and stages.get('frames') and render_commands and render_commands.get('frames'):
            # Build 623 and later: the render thread's command time minus its own fence and image waits (bufferReadback
            # also holds other threads' waits, such as a guest thread reading a deferred read-back).
            waits = (stages['writeWait'] + stages['readWait'] + stages['acquire']) / stages['frames']
            render = render_commands['busy'] / render_commands['frames'] - waits
            found.append(('render thread (its own work: command time minus its fence and image waits)', render))
        else:
            render = (total('renderDrain') - total('bufferReadback')) / frames
            found.append(('render thread (its own work: busy minus fence waits)', render))
        waits = total('syncInvoke') / frames
        if waits > 1:
            found.append(('GPU thread with its render-thread waits (read-back flushes and syncs)', gpu_thread + waits))
    if moltenvk and moltenvk.get('frames'):
        frames = moltenvk['frames']
        if 'encode' in moltenvk:
            found.append(("MoltenVK's Metal encoding (its submission thread)", moltenvk['encode'][0] / frames))
        if 'gpu' in moltenvk and not (detail and detail.get('gpu')):
            # MoltenVK counts from the commit to the completion handler: queue wait included, so an upper bound only.
            found.append(('GPU upper bound (MoltenVK command buffer commit to completion, queue wait included)',
                          moltenvk['gpu'][0] / frames))
    if detail and detail.get('gpu'):
        found.append(('GPU (Metal command buffers busy, overlapping ones merged)', detail['gpu']))
    if not found:
        return
    print(f'Ceilings over {label} (1000 / busy ms per presented frame; the lowest is the limit to remove next):')
    for name, ms in sorted(found, key=lambda item: -item[1]):
        print(f"  {name}: {ms:.1f} ms per frame -> {1000 / ms if ms > 0 else float('inf'):.1f} FPS")


RENDER_LINE = re.compile(r'Render thread commands over ([\d.]+) ms: busy ([\d.]+) ms; top \(calls, ms\):(.*)')


def report_render_commands(lines, chosen):
    """Render-thread command types ranked by time, over every 5 s line and over the slow ones."""
    parsed = []
    for value in lines:
        match = RENDER_LINE.search(value['diagnostic'])
        if not match:
            continue
        stamp = value['timestamp'][:19]
        inside = [s for s in chosen if s['stamp'][:19] <= stamp and s['stamp'][:19] > (
            datetime.fromisoformat(stamp) - timedelta(milliseconds=float(match.group(1)))).isoformat()[:19]]
        if not inside:
            continue
        top = [entry.split() for entry in match.group(3).split(';') if entry.strip()]
        parsed.append(dict(frames=sum(s['presented'] for s in inside), busy=float(match.group(2)),
                           fps=statistics.mean(s['fps'] for s in inside), top={n: (int(c), float(ms)) for n, c, ms in top}))
    if not parsed:
        return None
    median = statistics.median(entry['fps'] for entry in parsed)
    for label, group in (('all windows', parsed), ('slow windows (game FPS below the median)', [e for e in parsed if e['fps'] < median])):
        frames = sum(e['frames'] for e in group)
        if not frames:
            continue
        names = {}
        for entry in group:
            for name, (calls, ms) in entry['top'].items():
                c, m = names.get(name, (0, 0.0))
                names[name] = (c + calls, m + ms)
        ranked = sorted(names.items(), key=lambda item: -item[1][1])[:10]
        print(f"Render thread, {label}: {len(group)} lines, {frames} frames, busy "
              f"{sum(e['busy'] for e in group) / frames:.1f} ms per frame; top commands (ms per frame, calls per frame):")
        for name, (calls, ms) in ranked:
            print(f"  {name}: {ms / frames:.2f} ms, {calls / frames:.0f} calls")
    return dict(busy=sum(e['busy'] for e in parsed), frames=sum(e['frames'] for e in parsed))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('performance')
    parser.add_argument('core')
    parser.add_argument('--pid', required=True)
    parser.add_argument('--stderr', help="MeloNX-stderr.log, for MoltenVK's statistics (build 623 and later)")
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
            if len(stretch) >= 120:
                summarize(stretch[:60], '    first 60 s: ')
                summarize(stretch[-60:], '    last 60 s: ')
    print('Core windows ending inside these seconds (5.1 s; nested durations, never summed):')
    per_frame, games, rates = [], [], []
    begin, finish = min(s['stamp'] for s in chosen), max(s['stamp'] for s in chosen)
    for stamp, data in windows:
        if not begin <= stamp[:19] + 'Z' <= finish:
            continue
        g, p, c = data['gpuWork'], data['phases'], data['counts']
        frames = frames_in(seconds, stamp, data.get('windowMs', 5100.0))
        game = game_frames_in(seconds, stamp, data.get('windowMs', 5100.0))
        if frames:
            per_frame.append((frames, p, g))
            games.append(game)
            rates.append(game / (data.get('windowMs', 5100.0) / 1000))
            print(f"  {stamp[11:19]} per presented frame ({frames} presented, {game:.0f} game frames): GPU-thread waits for the render thread "
                  f"{p['syncInvoke'][1] / frames:.1f} ms, queue backpressure {p['queueBackpressure'][1] / frames:.1f} ms, "
                  f"render-thread fence waits {p['bufferReadback'][1] / frames:.1f} ms, render-thread work "
                  f"{(p['renderDrain'][1] - p['bufferReadback'][1]) / frames:.1f} ms, pipeline builds "
                  f"{p['graphicsPipelineBuild'][1] / frames:.1f} ms, draws {c['draws'] / frames:.0f}")
        print(f"  {stamp[11:19]} GPU thread {p['gpuDispatch'][1]:.0f} ms | dma {g['dma'][1]:.0f} ms, texture flush actions "
              f"{g['texFlushAction'][0]} = {g['texFlushAction'][1]:.0f} ms | render-thread syncs {p['syncInvoke'][1]:.0f} ms | "
              f"buffer read-backs {p['bufferReadback'][0]} = {p['bufferReadback'][1]:.0f} ms | pipeline builds "
              f"{p['graphicsPipelineBuild'][0]} = {p['graphicsPipelineBuild'][1]:.0f} ms | render thread busy "
              f"{p['renderDrain'][1]:.0f} ms, idle {p['renderIdle'][1]:.0f} ms | draws {c['draws']}")
    if per_frame:
        frames = sum(f for f, _, _ in per_frame)
        total = lambda key: sum(p[key][1] for _, p, _ in per_frame)
        print(f"Over these windows, per presented frame ({frames} frames): GPU-thread waits for the render thread "
              f"{total('syncInvoke') / frames:.1f} ms, queue backpressure {total('queueBackpressure') / frames:.1f} ms, "
              f"render-thread fence waits {total('bufferReadback') / frames:.1f} ms, render-thread work "
              f"{(total('renderDrain') - total('bufferReadback')) / frames:.1f} ms, pipeline builds "
              f"{total('graphicsPipelineBuild') / frames:.1f} ms, texture flush actions "
              f"{sum(g['texFlushAction'][1] for _, _, g in per_frame) / frames:.1f} ms")
        game = sum(games)
        if game:
            print(f"  per game frame ({game:.0f} distinct game frames): GPU-thread waits for the render thread "
                  f"{total('syncInvoke') / game:.1f} ms, render-thread work {(total('renderDrain') - total('bufferReadback')) / game:.1f} ms, "
                  f"render-thread fence waits {total('bufferReadback') / game:.1f} ms, GPU-thread dispatch {total('gpuDispatch') / game:.1f} ms, "
                  f"GPU-thread waits for the guest {total('gpuFifoWait') / game:.1f} ms")
    summary, attributions, render_lines, stage_lines, detail_lines = None, [], [], [], []
    for line in open(args.core, encoding='utf-8', errors='replace'):
        if f'"pid":{args.pid},' not in line:
            continue
        if 'DMA guest-memory copies:' in line:
            summary = line
        elif 'Render thread commands over ' in line:
            render_lines.append(json.loads(line.split('] ', 1)[1]))
        elif 'Vulkan render stages over ' in line:
            stage_lines.append(json.loads(line.split('] ', 1)[1]))
        elif 'Vulkan pass and GPU detail over ' in line:
            detail_lines.append(json.loads(line.split('] ', 1)[1]))
        elif any(key in line for key in ('DMA slow source read #', 'DMA GPU source copy', 'DMA region upload',
                                         'DMA float GPU copy', 'DMA GPU region copy', 'DMA GPU read-back',
                                         'Background pipeline compile missed', 'ServiceNv Wait')):
            attributions.append(line)
    render_commands = report_render_commands(render_lines, chosen)
    stages = report_render_stages(stage_lines, chosen)
    detail = report_render_detail(detail_lines, chosen)
    moltenvk = report_moltenvk(read_moltenvk(args.stderr, args.pid)) if args.stderr else None
    ceilings(per_frame, stages, moltenvk, render_commands=render_commands, detail=detail)
    if len(per_frame) >= 4:
        median = statistics.median(rates)
        slow = [entry for entry, rate in zip(per_frame, rates) if rate < median]
        ceilings(slow, None, None, f'the slow windows ({len(slow)} with game FPS below the median {median:.1f}; '
                                   'MoltenVK rows are session-wide)')
    if summary:
        print('Last DMA summary:', json.loads(summary.split('] ', 1)[1])['diagnostic'])
    for line in attributions:
        value = json.loads(line.split('] ', 1)[1])
        print(f"  {value['timestamp'][11:23]} {value['diagnostic']}")


if __name__ == '__main__':
    main()
