#!/usr/bin/env python3
"""What the S2Arm engine really keeps of each third-party component, for its licence notices (main's rule, 11 Nov):
a component with kept code ships its text; a component with none is recorded as absent, this inventory as proof.

    kept_code_inventory.py --services-nm NM_TXT --assets PROJECT_ASSETS_JSON [--assets ...] \
        --link-map S2ArmEngine.map --out kept-code-inventory.json

- Managed code: NativeAOT names the code and data it compiles after their assembly (`<Assembly>_<Namespace>_...`, dots
  of the assembly name as `_`; System.Private.CoreLib is `S_P_CoreLib`). NM_TXT is `nm` (all symbols, local ones
  included) of the services library libs2a_cs.a. For every package of the restore (project.assets.json `libraries`, type
  package) and each runtime or compile assembly it brings, the symbols that start with that prefix are counted.
- Native code: the final link's map (`-Wl,-map`) lists every object file and archive member linked into S2ArmEngine;
  the objects whose path names a probe (deko3d's port lives in graphics/nvn/gfx/nvn/nvn_tex.c) are reported with the
  symbols the map gives them.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

NATIVE_PROBES = {
    'deko3d texture layout (port, zlib)': re.compile(r'(^|[/_])nvn_tex\.o\b|deko3d', re.IGNORECASE),
}


def symbol_names(nm_text: str) -> list[str]:
    names = []
    for line in nm_text.splitlines():
        parts = line.split()
        if parts and not line.endswith(':'):
            names.append(parts[-1])
    return names


def prefix_of(assembly: str) -> str:
    if assembly == 'System.Private.CoreLib':
        return 'S_P_CoreLib_'
    return re.sub(r'[^A-Za-z0-9]', '_', assembly) + '_'


def packages(assets_files: list[Path]) -> dict[str, dict]:
    found = {}
    for path in assets_files:
        data = json.loads(path.read_text())
        for key, library in data.get('libraries', {}).items():
            if library.get('type') != 'package':
                continue
            name, _, version = key.partition('/')
            assemblies = sorted({Path(item).stem for item in library.get('files', ())
                                 if item.endswith('.dll') and item.split('/')[0] in ('lib', 'runtimes', 'ref')})
            entry = found.setdefault(name, dict(version=version, assemblies=set(), sources=set()))
            entry['assemblies'].update(assemblies)
            entry['sources'].add(str(path))
    return found


def managed(names: list[str], found: dict[str, dict]) -> dict[str, dict]:
    stripped = [name[1:] if name.startswith('_') else name for name in names]
    result = {}
    for package, entry in sorted(found.items()):
        per_assembly = {}
        for assembly in sorted(entry['assemblies']):
            prefix = prefix_of(assembly)
            hits = [name for name in stripped if name.startswith(prefix)]
            per_assembly[assembly] = dict(prefix=prefix, symbols=len(hits), sample=sorted(hits)[:5])
        result[package] = dict(version=entry['version'], kept=any(a['symbols'] for a in per_assembly.values()),
                               assemblies=per_assembly)
    return result


def native(map_text: str) -> dict[str, dict]:
    objects = {}
    section = None
    for line in map_text.splitlines():
        if line.startswith('# Object files:'):
            section = 'objects'
            continue
        if line.startswith('# Sections:') or line.startswith('# Symbols:'):
            section = 'symbols' if line.startswith('# Symbols:') else None
            continue
        if section == 'objects':
            match = re.match(r'\[\s*(\d+)\]\s+(.*)$', line)
            if match:
                objects[match.group(1)] = match.group(2)
    counts = {index: 0 for index in objects}
    samples = {index: [] for index in objects}
    in_symbols = False
    for line in map_text.splitlines():
        if line.startswith('# Symbols:'):
            in_symbols = True
            continue
        if in_symbols:
            match = re.match(r'0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+(\S+)', line)
            if match and match.group(1) in counts:
                counts[match.group(1)] += 1
                if len(samples[match.group(1)]) < 5:
                    samples[match.group(1)].append(match.group(2))
    report = {}
    for label, probe in NATIVE_PROBES.items():
        hits = [index for index, path in objects.items() if probe.search(path)]
        report[label] = dict(linked=bool(hits) and any(counts[i] for i in hits),
                             objects=[dict(path=objects[i], symbols=counts[i], sample=samples[i]) for i in hits])
    return dict(objectFiles=len(objects), probes=report)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--services-nm', type=Path, required=True)
    parser.add_argument('--assets', type=Path, action='append', default=[])
    parser.add_argument('--link-map', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    names = symbol_names(args.services_nm.read_text(errors='replace'))
    found = packages(args.assets)
    report = dict(servicesSymbols=len(names), assetsFiles=[str(p) for p in args.assets],
                  managed=managed(names, found), native=native(args.link_map.read_text(errors='replace')))
    args.out.write_text(json.dumps(report, indent=1, default=sorted) + '\n')
    kept = sorted(name for name, entry in report['managed'].items() if entry['kept'])
    print(f"kept-code inventory: {len(names)} services symbols, {len(found)} packages, {len(kept)} with kept code")
    for name, entry in report['native']['probes'].items():
        print(f"  {name}: linked={entry['linked']} " + ', '.join(f"{o['path']} ({o['symbols']})" for o in entry['objects']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
