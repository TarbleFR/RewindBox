#!/usr/bin/env python3
"""Where the threads stood during a stall: the "[MeloNX:stall]" records of the RewindBox performance journal, named.

    python3 tools/melonx/stall_report.py MeloNX-performance.log --pid 17066 [--symbols Ryujinx.Library.symbols.txt[.gz]]
        [--image MeloNXCore] [--thread NeoStation.MeloNX.Render --thread GPU.MainThread ...] [--all] [--json]

The bridge's stall watch (MeloNXStallWatch, MeloNXPerfJournal.swift) writes two kinds of records, each a header and one
row per thread of the process: "#N.S" while one of the journal's own engine calls is in flight (300 ms, 1.3 s, 3.3 s),
and "#FN.S" while a running game has presented no frame (2, 5 and 12 s after its last one). A row gives the thread's
kernel state (R running, W waiting, ...), its CPU time (+ms since the previous record of the same stall), its program
counter, link register and return addresses, each as image+0xoffset.

For that PID, this prints each record's header and, for the engine's threads (the render thread, the GPU thread, the
pipeline and shader compile threads, by default; --thread for others, --all for every thread), the return addresses
named with the Core's symbol map (the Ryujinx.Library.symbols.txt.gz of the Core artifact the IPA carries, whose offsets
are those of the image the journal calls MeloNXCore). Addresses of other images stay image+0xoffset.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hot_spots import Symbols  # noqa: E402

LINE = re.compile(r'\[MeloNX:stall\] (#F?\d+(?:\.\d+)?) (.*?)(?: context=(\{.*\}))?$')
ROW = re.compile(r't(\d+) (\S+) ([A-Z?]\S*) s(\d+) p(-?\d+)/(-?\d+) c(\+?[\d.]+)(?: pc=(\S+) lr=(\S+))?(?: bt=(\S+))?$')
DEFAULT_THREADS = ('NeoStation.MeloNX.Render', 'GPU.MainThread', 'Vulkan_Pipeline_', 'Vulkan_Shader_', 'GPU.BackgroundDiskCach')


def read(path, pid):
    """The records of `pid` (every record when None), in the journal's order: [{label, header, end, rows: [...]}]. A header
    and an end line carry the session's context; the rows that follow a header carry none and belong to it."""
    records, current = [], None
    for line in Path(path).read_text(errors='replace').splitlines():
        match = LINE.match(line)
        if not match:
            continue
        label, text, context = match.group(1), match.group(2), match.group(3)
        row = ROW.match(text)
        if row and context is None:
            if current is not None and current['label'] == label:
                current['rows'].append(dict(id=int(row.group(1)), name=row.group(2), state=row.group(3), suspended=int(row.group(4)),
                                            priority=int(row.group(5)), current=int(row.group(6)), cpu=row.group(7),
                                            pc=row.group(8), lr=row.group(9), frames=row.group(10).split(',') if row.group(10) else []))
            continue
        current = None
        if pid is not None and (context is None or str(json.loads(context).get('pid')) != str(pid)):
            continue
        if text.startswith('end: '):
            for record in reversed(records):
                if record['label'].split('.')[0] == label:
                    record['end'] = text
                    break
            continue
        current = dict(label=label, header=text, end=None, rows=[])
        records.append(current)
    return records


def name(place, image, symbols):
    if place and symbols and place.startswith(image + '+0x'):
        found = symbols.name(int(place.split('+0x')[1], 16))
        if found:
            return found.removeprefix('_')
    return place


def report(records, image, symbols, threads, every):
    out = []
    for record in records:
        rows = [row for row in record['rows'] if every or any(row['name'].startswith(prefix[:24]) for prefix in threads)]
        out.append(dict(label=record['label'], header=record['header'], end=record['end'],
                        threads=[dict(id=row['id'], name=row['name'], state=row['state'], priority=row['priority'], cpu=row['cpu'],
                                      pc=name(row['pc'], image, symbols), frames=[name(place, image, symbols) for place in row['frames']])
                                 for row in rows]))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('journal')
    parser.add_argument('--pid', help='the session process (the context of the lines); every record when omitted')
    parser.add_argument('--symbols', help="the Core artifact's Ryujinx.Library.symbols.txt(.gz)")
    parser.add_argument('--image', default='MeloNXCore', help='the name the journal gives the Core image (default MeloNXCore)')
    parser.add_argument('--thread', action='append', help='a thread name prefix to print (repeatable; default: the engine threads)')
    parser.add_argument('--all', action='store_true', help='print every thread')
    parser.add_argument('--json', action='store_true')
    arguments = parser.parse_args()
    symbols = Symbols(arguments.symbols) if arguments.symbols else None
    result = report(read(arguments.journal, arguments.pid), arguments.image, symbols,
                    tuple(arguments.thread) if arguments.thread else DEFAULT_THREADS, arguments.all)
    if arguments.json:
        print(json.dumps(dict(pid=arguments.pid, named=symbols is not None, records=result), indent=1))
        return
    for record in result:
        print(f"{record['label']} {record['header']}" + (f"  [{record['end']}]" if record['end'] else ''))
        for thread in record['threads']:
            print(f"  t{thread['id']} {thread['name']} {thread['state']} p{thread['priority']} c{thread['cpu']} pc={thread['pc']}")
            for frame in thread['frames']:
                print(f"      {frame}")
    if not result:
        print('no stall record' + (f' for pid {arguments.pid}' if arguments.pid else ''))


if __name__ == '__main__':
    main()
