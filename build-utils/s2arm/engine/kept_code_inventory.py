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

`--check` makes the inventory a blocking check (s2arm-engine.yml runs it before the licence collection):
- a package with kept code must be in PACKAGE_TEXTS, which names the texts of Legal/S2Arm that cover it (the collector,
  collect_licenses.py, writes them); a kept package that is not listed fails;
- every archive of the final link (and the obj_app objects, the SDK stubs, the linker's own) must match a rule of
  NATIVE_RULES, which names the texts that cover it, or records that none is needed (compiler-rt, system libraries).
Packages without kept code are listed in the output, never a failure. `--from-json INVENTORY --link-map MAP` repeats the
check on an inventory written earlier (the map may be gzip-compressed); the exit status is 1 on any failure, and every
failure is printed.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path

NATIVE_PROBES = {
    'deko3d texture layout (port, zlib)': re.compile(r'(^|[/_(])nvn_tex(\.c)?\.o\b|deko3d', re.IGNORECASE),
}


# Packages with kept code (run 43122083170 of s2arm-engine.yml): package id -> texts of Legal/S2Arm that cover it.
PACKAGE_TEXTS = {
    'Gommon': ('dotnet/Gommon/content/LICENSE',),
    'Open.Nat.V2': ('dotnet/Open.Nat.V2/LICENSE',),
    'Ryujinx.LibHac': ('dotnet/Ryujinx.LibHac/LICENSE',),
    'System.IO.Hashing': ('dotnet/System.IO.Hashing/THIRD-PARTY-NOTICES.TXT', 'System.IO.Hashing/LICENSE.TXT'),
    'Humanizer.Core': ('Humanizer/license.txt',),
    'Microsoft.IO.RecyclableMemoryStream': ('RecyclableMemoryStream/LICENSE',),
    'NetCoreServer': ('NetCoreServer/LICENSE',),
    'MsgPack.Cli': ('MsgPack.Cli/LICENSE.txt',),
}
S2ARM_TEXTS = ('S2Arm/LICENSE', 'S2Arm/NOTICE')
RUNTIME_TEXTS = ('dotnet/Microsoft.NETCore.App.Runtime.NativeAOT.ios-arm64/LICENSE.TXT',
                 'dotnet/Microsoft.NETCore.App.Runtime.NativeAOT.ios-arm64/THIRD-PARTY-NOTICES.TXT')
# Linked native groups: (pattern on the archive path, or the object path for loose objects; texts; note).
NATIVE_RULES = (
    (r'(^|/)libs2a_cs\.a$', S2ARM_TEXTS + ('Ryujinx/LICENSE.txt',) + RUNTIME_TEXTS, 'services library: S2Arm, Ryujinx, .NET runtime, packages'),
    (r'(^|/)libnvn\.a$', S2ARM_TEXTS + ('deko3d/LICENSE', 'MacNativeGames/LICENSE', 'direct-graphics-layer/LICENSE',
                                         'nvn.h/NOTICE.txt'), 'S2Arm nvn, deko3d nvn_tex, nvn_bcdec, direct graphics layer, nvn.h'),
    (r'(^|/)libdsx\.a$', ('SPIRV-Cross/LICENSE',) + S2ARM_TEXTS, 'SPIRV-Cross and S2Arm'),
    (r'(^|/)libglx\.a$', ('glslang/LICENSE.txt',) + S2ARM_TEXTS, 'glslang and S2Arm gl_xlate'),
    (r'(^|/)libnxgal\.a$', S2ARM_TEXTS + ('D3D11-tessellator/NOTICE.txt',), 'S2Arm and the D3D11 tessellator reference'),
    (r'(^|/)obj_app/[^/]+\.o$', S2ARM_TEXTS, 'S2Arm application objects'),
    (r'(^|/)libs2a_dav1d\.a$', ('dav1d/COPYING',), 'dav1d'),
    (r'(^|/)libs2a_vpx\.a$', ('libvpx/LICENSE', 'libvpx/PATENTS'), 'libvpx'),
    (r'(^|/)libs2a_opus\.a$', ('opus/COPYING',), 'opus'),
    (r'microsoft\.netcore\.app\.runtime\.nativeaot\.ios-arm64/[^/]+/runtimes/ios-arm64/native/lib[^/]+\.a$', RUNTIME_TEXTS,
     '.NET runtime natives'),
    (r'(^|/)libclang_rt\.ios\.a$', (), 'LLVM compiler-rt, Apache-2.0 WITH LLVM-exception: no notice required for compiled object code'),
    (r'\.tbd$|/usr/lib/system/|/System/Library/|^linker synthesized$', (), 'system, not distributed'),
)


def native_group(path: str) -> str:
    """The archive (path before the member) or the loose object a map line names."""
    return path.split('(', 1)[0] if '(' in path else path


def link_groups(map_text: str) -> list[str]:
    groups = []
    in_objects = False
    for line in map_text.splitlines():
        if line.startswith('# Object files:'):
            in_objects = True
            continue
        if in_objects and line.startswith('#'):
            break
        match = re.match(r'\[\s*\d+\]\s+(.*)$', line) if in_objects else None
        if match and native_group(match.group(1)) not in groups:
            groups.append(native_group(match.group(1)))
    return groups


def check(report: dict, map_text: str) -> tuple[list[str], list[str]]:
    """(failures, lines of what is covered or absent) for an inventory report and the final link's map."""
    failures, lines = [], []
    for name, entry in sorted(report['managed'].items()):
        if not entry['kept']:
            lines.append(f"absent  {name} {entry['version']}: no kept code")
        elif name in PACKAGE_TEXTS:
            lines.append(f"kept    {name} {entry['version']}: " + ', '.join(PACKAGE_TEXTS[name]))
        else:
            failures.append(f"package {name} {entry['version']} has kept code and no licence entry (PACKAGE_TEXTS)")
    unmatched_texts = {}
    for group in link_groups(map_text):
        rule = next((item for item in NATIVE_RULES if re.search(item[0], group)), None)
        if rule is None:
            failures.append(f"linked group {group} matches no licence rule (NATIVE_RULES)")
        else:
            unmatched_texts[rule[0]] = rule
    for pattern, texts, note in unmatched_texts.values():
        lines.append(f"linked  {note}: " + (', '.join(texts) if texts else 'no text'))
    return failures, lines


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


def licence_material(nuget: Path, managed_report: dict) -> dict:
    """For each package with kept code: the nuspec's licence fields and the licence-like files the package carries."""
    result = {}
    for name, entry in managed_report.items():
        if not entry['kept']:
            continue
        folder = nuget / name.lower() / entry['version'].lower()
        nuspec = next(iter(sorted(folder.glob('*.nuspec'))), None) if folder.is_dir() else None
        text = nuspec.read_text(errors='replace') if nuspec else ''
        def field(tag):
            match = re.search(r'<%s\b([^>]*)>(.*?)</%s>' % (tag, tag), text, re.S)
            return dict(attributes=match.group(1).strip(), value=match.group(2).strip()) if match else None
        repository = re.search(r'<repository\b([^>]*)/?>', text)
        files = sorted(str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file() and
                       re.search(r'licen[cs]e|notice|copying|third.?party', p.name, re.I)) if folder.is_dir() else []
        result[name] = dict(version=entry['version'], folder=folder.is_dir(), license=field('license'),
                            licenseUrl=field('licenseUrl'), repository=repository.group(1).strip() if repository else None,
                            files=files)
    return result


def read_map(path: Path) -> str:
    if path.suffix == '.gz':
        return gzip.decompress(path.read_bytes()).decode(errors='replace')
    return path.read_text(errors='replace')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--services-nm', type=Path)
    parser.add_argument('--assets', type=Path, action='append', default=[])
    parser.add_argument('--link-map', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--nuget', type=Path, help='NuGet packages folder: report the licence material of kept packages')
    parser.add_argument('--check', action='store_true', help='exit 1 when kept code has no licence entry')
    parser.add_argument('--from-json', type=Path, help='with --check: an inventory written earlier instead of --services-nm')
    args = parser.parse_args(argv)
    if args.from_json and not args.check:
        parser.error('--from-json needs --check')
    if not args.from_json and not (args.services_nm and args.out):
        parser.error('--services-nm and --out are required unless --from-json is given')
    map_text = read_map(args.link_map)
    if args.from_json:
        report = json.loads(args.from_json.read_text())
    else:
        names = symbol_names(args.services_nm.read_text(errors='replace'))
        found = packages(args.assets)
        report = dict(servicesSymbols=len(names), assetsFiles=[str(p) for p in args.assets],
                      managed=managed(names, found), native=native(map_text))
        if args.nuget:
            report['licenceMaterial'] = licence_material(args.nuget, report['managed'])
        args.out.write_text(json.dumps(report, indent=1, default=sorted) + '\n')
        kept = sorted(name for name, entry in report['managed'].items() if entry['kept'])
        print(f"kept-code inventory: {len(names)} services symbols, {len(found)} packages, {len(kept)} with kept code")
        for name, entry in report['native']['probes'].items():
            print(f"  {name}: linked={entry['linked']} " + ', '.join(f"{o['path']} ({o['symbols']})" for o in entry['objects']))
    if not args.check:
        return 0
    failures, lines = check(report, map_text)
    print('\n'.join(lines))
    for failure in failures:
        print('FAIL ' + failure)
    print(f"kept-code check: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
