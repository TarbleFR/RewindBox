#!/usr/bin/env python3
"""Where the busiest threads were: the "[MeloNX:hot]" profiles of the RewindBox performance journal, with names.

    python3 tools/melonx/hot_spots.py MeloNX-performance.log --pid 51986 [--symbols Ryujinx.Library.symbols.txt[.gz]]
        [--image MeloNXCore] [--top 15] [--json]

The bridge (MeloNXHotSpots.swift) takes a profile after three per-second lines in a row under 26 FPS ("slow") or at
28.5 FPS and more ("base"): the six busiest threads read 300 times, 10 ms apart. Per thread it writes the samples found
running and waiting, and three lists of place:samples (a place is image+0xoffset, "jit" for translated guest code, or
"anon"): self= where the program counter was while running, stack= the places present anywhere in a running sample
(a caller's count includes its callees'), waiting= the same for the waiting samples.

For that PID, this prints each profile: per thread, the share of the samples running; where they are by image (jit, the
engine, each system library); and, with the Core's symbol map (the Ryujinx.Library.symbols.txt.gz of the Core artifact,
whose offsets are those of the image the journal calls MeloNXCore), the functions with the most self and stack samples.
Stack counts are per call site in the journal: two sites of one function in the same sample are both counted, so a
function's stack figure is an upper bound (never above the running samples in the report). Samples are 10 ms apart:
a share of the samples is a share of the 3 s, not a time measured per call.
"""
import argparse
import bisect
import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True

HEADER = re.compile(r'\[MeloNX:hot\] #(\d+) (slow|base) t=(\d+) fps=([\d.]+) (\d+) samples in (\d+) ms, (\d+) threads(?: context=(\{.*\}))?$')
THREAD = re.compile(r'\[MeloNX:hot\] #(\d+) (\S+) p(-?\d+) run=(\d+) wait=(\d+) missed=(\d+) self=(\S+) stack=(\S+) waiting=(\S+)$')


def places(text):
    if text == '-':
        return []
    out = []
    for entry in text.split(','):
        place, _, count = entry.rpartition(':')
        out.append((place, int(count)))
    return out


def read(path, pid):
    """The profiles of `pid`: [{number, kind, second, fps, samples, tookMs, threads: [...]}], in the journal's order."""
    profiles, current = [], None
    for line in Path(path).read_text(errors='replace').splitlines():
        header = HEADER.match(line)
        if header:
            context = json.loads(header.group(8)) if header.group(8) else {}
            current = None
            if str(context.get('pid')) == str(pid):
                current = dict(number=int(header.group(1)), kind=header.group(2), second=int(header.group(3)), fps=float(header.group(4)),
                               samples=int(header.group(5)), tookMs=int(header.group(6)), threads=[])
                profiles.append(current)
            continue
        thread = THREAD.match(line)
        if thread and current is not None and int(thread.group(1)) == current['number']:
            current['threads'].append(dict(name=thread.group(2), priority=int(thread.group(3)), run=int(thread.group(4)), wait=int(thread.group(5)),
                                           missed=int(thread.group(6)), own=places(thread.group(7)), stack=places(thread.group(8)),
                                           waiting=places(thread.group(9))))
    return profiles


class Symbols:
    """Text symbols of the Core's map (`address type name` lines), by address."""

    def __init__(self, path):
        opener = gzip.open if str(path).endswith('.gz') else open
        pairs = []
        with opener(path, 'rt', errors='replace') as stream:
            for line in stream:
                parts = line.rstrip('\n').split(' ', 2)
                if len(parts) == 3 and parts[1] in 'tTsS':
                    try:
                        pairs.append((int(parts[0], 16), parts[2]))
                    except ValueError:
                        pass
        pairs.sort()
        self.addresses = [address for address, _ in pairs]
        self.names = [name for _, name in pairs]

    def name(self, offset):
        index = bisect.bisect_right(self.addresses, offset) - 1
        return self.names[index] if index >= 0 else None


def image_of(place):
    return place.split('+0x')[0] if '+0x' in place else place


def by_function(entries, image, symbols, limit=None):
    """place:samples of `image` summed per function (per place without a map), most samples first."""
    totals = defaultdict(int)
    for place, count in entries:
        if image_of(place) != image or '+0x' not in place:
            continue
        name = symbols.name(int(place.split('+0x')[1], 16)) if symbols else None
        totals[name or place] += count
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return ordered[:limit] if limit else ordered


def summarize(thread, image, symbols, top):
    run = thread['run']
    images = defaultdict(int)
    for place, count in thread['own']:
        images[image_of(place)] += count
    listed = sum(images.values())
    stack = [(name, min(count, run)) for name, count in by_function(thread['stack'], image, symbols, top)]
    waiting = defaultdict(int)
    for place, count in thread['waiting']:
        name = symbols.name(int(place.split('+0x')[1], 16)) if symbols and image_of(place) == image and '+0x' in place else None
        waiting[name or place] = max(waiting[name or place], count)
    return dict(name=thread['name'], priority=thread['priority'], run=run, wait=thread['wait'], missed=thread['missed'],
                runningPercent=round(100 * run / (run + thread['wait']), 1) if run + thread['wait'] else None,
                selfByImage=sorted(images.items(), key=lambda item: (-item[1], item[0])), selfListed=listed,
                selfFunctions=by_function(thread['own'], image, symbols, top), stackFunctions=stack,
                waitingPlaces=sorted(waiting.items(), key=lambda item: (-item[1], item[0]))[:top])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('performance')
    parser.add_argument('--pid', required=True)
    parser.add_argument('--symbols', help="the Core artifact's Ryujinx.Library.symbols.txt(.gz)")
    parser.add_argument('--image', default='MeloNXCore', help='the image the symbol map describes')
    parser.add_argument('--top', type=int, default=15)
    parser.add_argument('--json', action='store_true')
    arguments = parser.parse_args()
    profiles = read(arguments.performance, arguments.pid)
    if not profiles:
        raise SystemExit(f'no [MeloNX:hot] profile for pid {arguments.pid}')
    symbols = Symbols(arguments.symbols) if arguments.symbols else None
    results = [dict(number=p['number'], kind=p['kind'], second=p['second'], fps=p['fps'], samples=p['samples'], tookMs=p['tookMs'],
                    threads=[summarize(thread, arguments.image, symbols, arguments.top) for thread in p['threads']]) for p in profiles]
    if arguments.json:
        print(json.dumps(dict(pid=arguments.pid, image=arguments.image, named=symbols is not None, profiles=results), indent=1))
        return
    for profile in results:
        print(f'#{profile["number"]} {profile["kind"]} at t={profile["second"]} ({profile["fps"]} FPS): {profile["samples"]} samples in {profile["tookMs"]} ms')
        for thread in profile['threads']:
            total = thread['run'] + thread['wait']
            print(f'  {thread["name"]} (priority {thread["priority"]}): running {thread["run"]} of {total} samples'
                  + (f' ({thread["runningPercent"]} %)' if total else '') + (f', {thread["missed"]} reads missed' if thread['missed'] else ''))
            if thread['selfByImage']:
                print('    self, by image: ' + ', '.join(f'{image} {count}' for image, count in thread['selfByImage'])
                      + (f' (of {thread["run"]} running; the journal lists the most frequent places)' if thread['selfListed'] < thread['run'] else ''))
            for title, key in (('self', 'selfFunctions'), ('stack (callers include callees)', 'stackFunctions')):
                if thread[key]:
                    print(f'    {arguments.image} {title}:')
                    for name, count in thread[key]:
                        print(f'      {count:4d}  {name[:150]}')
            if thread['waitingPlaces']:
                print('    waiting in: ' + '; '.join(f'{name[:110]} {count}' for name, count in thread['waitingPlaces'][:6]))


if __name__ == '__main__':
    main()
