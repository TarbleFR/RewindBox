#!/usr/bin/env python3
"""Who allocated the native heap: the "[MeloNX:heap]" lines of the RewindBox performance journal, with names.

    python3 tools/melonx/heap_report.py MeloNX-performance.log --pid 51986 [--symbols Ryujinx.Library.symbols.txt[.gz]]
        [--image MeloNXCore] [--map IMAGE=nm-output[.gz] ...] [--json]

For the first 120 s of a session the bridge (MeloNXHeapSampler.m, MeloNXHeapSample.swift) samples the process's malloc
calls by size (one block per 256 KiB allocated on average; a block of 256 KiB or more always) and writes, at the end
of that window, the 24 call stacks with the most bytes still allocated: live=MiB/samples total=MiB/samples and the
places of the call, innermost first (image+0xoffset, "jit", "anon").

For that PID, this prints each window: its totals, then per stack its live bytes, their share of the window's live
bytes, and the places, the engine's named with the Core's symbol map (the Ryujinx.Library.symbols.txt.gz of the Core
artifact). Another image's places are named with --map IMAGE=file, where file is `nm -n` of that image's binary as
built (for instance MeloNXMoltenVKStandalone=moltenvk.nm.txt: the IPA's copy has no local symbols left). It ends with
the live bytes by owner: the image of the first place that is not an allocation wrapper of the C++ or Swift runtime,
and, when the engine is in the stack, its outermost named function listed.
The figures are estimates from samples (a small block's sample stands for 256 KiB), for the window only: memory
allocated later in the session is not in them (the zones= field of the "[MeloNX:memory]" lines gives the heap's size
over time).
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hot_spots import Symbols, image_of  # noqa: E402

HEADER = re.compile(r'\[MeloNX:heap\] window (\d+) s \((\w+)\): live (\d+) MiB in (\d+) samples, allocated (\d+) MiB in (\d+), interval (\d+) KiB, '
                    r'(\d+) stacks, (\d+) dropped, (\d+) unwalked; zones=(\S+)(?: context=(\{.*\}))?$')
STACK = re.compile(r'\[MeloNX:heap\] #(\d+) live=(\d+)/(\d+) total=(\d+)/(\d+) stack=(\S+)$')
# Images whose frames only pass an allocation on.
WRAPPERS = ('libc++abi.dylib', 'libc++.1.dylib', 'libswiftCore.dylib', 'libsystem_c.dylib', 'libobjc.A.dylib', 'libsystem_blocks.dylib')


def read(path, pid):
    windows, current = [], None
    for line in Path(path).read_text(errors='replace').splitlines():
        header = HEADER.match(line)
        if header:
            context = json.loads(header.group(12)) if header.group(12) else {}
            current = None
            if str(context.get('pid')) == str(pid):
                current = dict(seconds=int(header.group(1)), reason=header.group(2), liveMiB=int(header.group(3)), liveSamples=int(header.group(4)),
                               allocatedMiB=int(header.group(5)), allocatedSamples=int(header.group(6)), intervalKiB=int(header.group(7)),
                               stacksRecorded=int(header.group(8)), dropped=int(header.group(9)), unwalked=int(header.group(10)),
                               zones=header.group(11), stacks=[])
                windows.append(current)
            continue
        stack = STACK.match(line)
        if stack and current is not None and int(stack.group(1)) == len(current['stacks']) + 1:
            current['stacks'].append(dict(liveMiB=int(stack.group(2)), liveSamples=int(stack.group(3)), totalMiB=int(stack.group(4)),
                                          totalSamples=int(stack.group(5)), places=[] if stack.group(6) == '-' else stack.group(6).split('<')))
        elif not line.startswith('[MeloNX:heap] #'):
            current = None if line.startswith('[MeloNX:heap]') else current
    return windows


def named(place, image, symbols):
    """`symbols` is the engine's map (for `image`) or a dictionary of maps by image."""
    maps = symbols if isinstance(symbols, dict) else {image: symbols} if symbols else {}
    table = maps.get(image_of(place))
    if table and '+0x' in place:
        return table.name(int(place.split('+0x')[1], 16)) or place
    return place


def owner(places, image, symbols):
    """(image of the first place that is not an allocation wrapper, the engine's outermost listed function or None)."""
    first = next((image_of(place) for place in places if image_of(place) not in WRAPPERS), image_of(places[0]) if places else '-')
    engine = [named(place, image, symbols) for place in places if image_of(place) == image]
    return first, engine[-1] if engine else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('performance')
    parser.add_argument('--pid', required=True)
    parser.add_argument('--symbols', help="the Core artifact's Ryujinx.Library.symbols.txt(.gz)")
    parser.add_argument('--image', default='MeloNXCore', help='the image the symbol map describes')
    parser.add_argument('--map', action='append', default=[], metavar='IMAGE=FILE', help='`nm -n` of another image, to name its places')
    parser.add_argument('--json', action='store_true')
    arguments = parser.parse_args()
    windows = read(arguments.performance, arguments.pid)
    if not windows:
        raise SystemExit(f'no [MeloNX:heap] window for pid {arguments.pid}')
    symbols = {}
    if arguments.symbols:
        symbols[arguments.image] = Symbols(arguments.symbols)
    for entry in arguments.map:
        name, _, path = entry.partition('=')
        if not name or not path:
            raise SystemExit('--map takes IMAGE=FILE')
        symbols[name] = Symbols(path)
    for window in windows:
        owners, engines = defaultdict(int), defaultdict(int)
        for stack in window['stacks']:
            stack['names'] = [named(place, arguments.image, symbols) for place in stack['places']]
            stack['livePercent'] = round(100 * stack['liveMiB'] / window['liveMiB'], 1) if window['liveMiB'] else None
            first, engine = owner(stack['places'], arguments.image, symbols)
            owners[first] += stack['liveMiB']
            if engine:
                engines[engine] += stack['liveMiB']
        listed = sum(stack['liveMiB'] for stack in window['stacks'])
        window['listedLiveMiB'] = listed
        window['liveByOwner'] = sorted(owners.items(), key=lambda item: (-item[1], item[0]))
        window['liveByEngineEntry'] = sorted(engines.items(), key=lambda item: (-item[1], item[0]))
    if arguments.json:
        print(json.dumps(dict(pid=arguments.pid, image=arguments.image, named=sorted(symbols), windows=windows), indent=1))
        return
    for window in windows:
        print(f'window of {window["seconds"]} s ({window["reason"]}): live {window["liveMiB"]} MiB in {window["liveSamples"]} samples, allocated '
              f'{window["allocatedMiB"]} MiB in {window["allocatedSamples"]}; one sample per {window["intervalKiB"]} KiB; {window["stacksRecorded"]} stacks, '
              f'{window["dropped"]} dropped, {window["unwalked"]} unwalked; zones {window["zones"]}')
        print(f'  the {len(window["stacks"])} stacks listed hold {window["listedLiveMiB"]} MiB of the live bytes')
        for index, stack in enumerate(window['stacks'], 1):
            share = f' ({stack["livePercent"]} %)' if stack['livePercent'] is not None else ''
            print(f'  #{index} live {stack["liveMiB"]} MiB{share} in {stack["liveSamples"]} samples; allocated {stack["totalMiB"]} MiB in {stack["totalSamples"]}')
            for name in stack['names']:
                print(f'       {name[:160]}')
        print('  live MiB by owner (first place that is not an allocation wrapper): ' + ', '.join(f'{name} {mib}' for name, mib in window['liveByOwner']))
        if window['liveByEngineEntry']:
            print(f'  live MiB by outermost {arguments.image} function listed:')
            for name, mib in window['liveByEngineEntry']:
                print(f'    {mib:5d}  {name[:150]}')


if __name__ == '__main__':
    main()
