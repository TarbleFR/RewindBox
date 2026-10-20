#!/usr/bin/env python3
"""Contract between the libretro core catalog and the pinned core binaries.

Without --cores, checks that the catalog parses into one entry per packaged
core and that the parser still finds the option maps and curated settings.

With --cores DIR (the LibretroCores artifact), also requires that:
- every option key and value NeoStation sets (defaults, no-JIT overrides,
  options locked for the session, curated settings and their choices)
  exists in the core binary: the host silently ignores a value the core
  does not offer, which for a locked DS/3DS option would break the screen
  crop and the touch screen without any error;
- every option of a core that selects run-time code generation (dynarec,
  JIT, recompiler, CPU core or mode) has a no-JIT override, because iOS 26
  gives libretro cores no JIT and generated code would crash the session.
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Option-key prefixes declared by each packaged core.
PREFIXES = {
    'nestopia': ('nestopia_',),
    'snes9x': ('snes9x_',),
    'gambatte': ('gambatte_',),
    'mgba': ('mgba_',),
    'genesis_plus_gx': ('genesis_plus_gx_',),
    'genesis_plus_gx_wide': ('genesis_plus_gx_',),
    'picodrive': ('picodrive_',),
    'fbneo': ('fbneo-',),
    'desmume': ('desmume_',),
    'mupen64plus_next': ('mupen64plus-',),
    'mednafen_psx_hw': ('beetle_psx_hw_',),
    'mednafen_psx': ('beetle_psx_',),
    'ppsspp': ('ppsspp_',),
    'azahar': ('citra_', 'azahar_'),
    # Lot 1 (docs/libretro-consoles-lot1.md).
    'mednafen_pce_fast': ('pce_fast_', 'pce_'),
    'mednafen_wswan': ('wswan_',),
    'mednafen_ngp': ('ngp_',),
    'handy': ('handy_',),
    'mednafen_vb': ('vb_',),
    'stella': ('stella_',),
    'prosystem': ('prosystem_',),
    'a5200': ('a5200_',),
    'gearcoleco': ('gearcoleco_',),
    'pokemini': ('pokemini_',),
    'gw': ('gw_',),
    'sameduck': ('sameduck_',),
    'potator': ('potator_',),
    'ardens': ('ardens_',),
    'wasm4': ('wasm4_',),
    'uzem': ('uzem_',),
    # Lot 2 (docs/libretro-consoles-lot2.md).
    'freechaf': ('freechaf_',),
    'freeintv': ('freeintv_', 'default_p1_'),
    'o2em': ('o2em_',),
    'mednafen_pcfx': ('pcfx_',),
    # Lot 3: Mesen, the NES engine that reads HD packs (docs/hd-textures-nes-mesen.md).
    'mesen': ('mesen_',),
}
CODE_GENERATION = re.compile(r'dynarec|jit|recompil|cpucore|cpu_core|cpu_mode|(?:^|[_-])drc(?:$|[_-])', re.I)

# Curated in-game settings, exactly. The DeSmuME screen layout setting was
# removed on purpose: NeoStation now locks DeSmuME to stacked screens and
# arranges them itself, so it moved to LOCKED below. The three Azahar
# settings (system region, language and model, docs/libretro-3ds-system-
# settings.md § 3.1) are proven key by key and value by value in the pinned
# binary by binary_findings below, with --cores.
# Contract change (Build 455, docs/libretro-resolution.md): the three curated
# "Internal resolution" settings (Mupen64Plus-Next, Beetle PSX HW, PPSSPP)
# became the "Resolution and picture" page, fed by the RESOLUTION
# declarations below, which the binaries must hold in the same way.
CURATED = {
    ('azahar', 'citra_region_value'),
    ('azahar', 'citra_language_value'),
    ('azahar', 'citra_is_new_3ds'),
    ('azahar', 'citra_use_fastinterp'),
}
# Internal resolution option of each pinned core that has one, exactly
# (LibretroCore.resolution): its key, every value, the core's default and the
# core's library_name (which names Config/<library>.json) must be in the
# binary. The 2D cores have none.
RESOLUTION = {
    'desmume': ('DeSmuME', 'desmume_internal_resolution'),
    'mupen64plus_next': ('Mupen64Plus-Next', 'mupen64plus-43screensize'),
    'mednafen_psx_hw': ('Beetle PSX HW', 'beetle_psx_hw_internal_resolution'),
    'mednafen_psx': ('Beetle PSX', 'beetle_psx_internal_resolution'),
    'ppsspp': ('PPSSPP', 'ppsspp_internal_resolution'),
    'azahar': ('Azahar', 'citra_resolution_factor'),
}
# Options NeoStation locks for the session, exactly (screen crop, touch
# screen and sticks of the dual-screen consoles; the Azahar user folder
# kept under the libretro save directory, where the Nintendo 3DS page reads
# and installs the system files).
LOCKED = {
    'desmume': {
        'desmume_screens_layout': 'top/bottom',
        'desmume_screens_gap': '0',
        'desmume_pointer_type': 'touch',
        'desmume_pointer_mouse': 'enabled',
    },
    'azahar': {
        'citra_layout_option': 'default',
        'citra_swap_screen': 'Top',
        'citra_analog_function': 'c_stick',
        'citra_render_3d': 'off',
        'citra_use_libretro_save_path': 'LibRetro Default',
    },
    # Lot 1: the core's default "callback" audio needs
    # RETRO_ENVIRONMENT_SET_AUDIO_CALLBACK, which the host does not offer.
    'wasm4': {
        'wasm4_audio_type': 'normal',
    },
    # Build 489 (HD textures): <content>-texture-replacements read from the core's
    # save directory, where the catalogue installs it; never dumped; textures
    # decoded on demand within bounded VRAM/RAM caches.
    'mednafen_psx_hw': {
        'beetle_psx_hw_texture_directory': 'save',
        'beetle_psx_hw_dump_textures': 'disabled',
        'beetle_psx_hw_hd_caching_method': 'lazy',
        'beetle_psx_hw_hd_cache_vram_budget': '512',
        'beetle_psx_hw_hd_cache_ram_budget': '512',
    },
}
# The choices of every curated setting, exactly: the raw values the core
# offers, which the catalog must spell the same way (a misspelt choice is
# silently ignored by the host, like a locked value).
CURATED_CHOICES = {
    ('azahar', 'citra_region_value'): ['Auto', 'Japan', 'USA', 'Europe', 'Australia', 'China', 'Korea', 'Taiwan'],
    ('azahar', 'citra_language_value'): ['English', 'Japanese', 'French', 'Spanish', 'German', 'Italian', 'Dutch',
                                         'Portuguese', 'Russian', 'Korean', 'Traditional Chinese',
                                         'Simplified Chinese'],
    ('azahar', 'citra_is_new_3ds'): ['New 3DS', 'Old 3DS'],
    ('azahar', 'citra_use_fastinterp'): ['enabled', 'disabled'],
}


def require(condition, message):
    if not condition:
        raise SystemExit('libretro core options contract: ' + message)


def literal_map(block, name):
    match = re.search(name + r':\s*\{(.*?)\}', block, re.S)
    return dict(re.findall(r"'([^']*)'\s*:\s*'([^']*)'", match.group(1))) if match else {}


def catalog():
    text = (ROOT / 'lib/services/libretro_core_catalog.dart').read_text(encoding='utf-8')
    body = text[text.index('Map<String, LibretroCore> cores'):text.index('Map<String, LibretroSystemBinding> systems')]
    starts = list(re.finditer(r"^\s*'([a-z0-9_]+)': LibretroCore\(", body, re.M))
    cores = {}
    for index, start in enumerate(starts):
        stop = starts[index + 1].start() if index + 1 < len(starts) else len(body)
        block = body[start.end():stop]
        settings = [
            (match.group(1), re.findall(r"'([^']*)'", match.group(2)))
            for match in re.finditer(r"LibretroCuratedSetting\(\s*'([^']+)',\s*'[^']+',\s*\[(.*?)\]", block, re.S)
        ]
        cores[start.group(1)] = {
            'defaults': literal_map(block, 'optionDefaults'),
            'noJit': literal_map(block, 'noJitOverrides'),
            'locked': literal_map(block, 'lockedOptions'),
            'settings': settings,
            'resolution': resolution_declaration(block),
        }
    return cores


def resolution_declaration(block):
    """`resolution: LibretroResolutionDeclaration(...)` of a core block, None without."""
    match = re.search(r'resolution:\s*LibretroResolutionDeclaration\((.*?)\),\n', block, re.S)
    if match is None:
        return None
    declaration = match.group(1)
    values = re.search(r'values:\s*\[(.*?)\]', declaration, re.S)
    return {
        'library': re.search(r"libraryName:\s*'([^']+)'", declaration).group(1),
        'key': re.search(r"key:\s*'([^']+)'", declaration).group(1),
        'values': re.findall(r"'([^']*)'", values.group(1)) if values else [],
        'default': re.search(r"coreDefault:\s*'([^']*)'", declaration).group(1),
    }


def binary_findings(core_id, entry, data):
    findings = []
    present = lambda text: text.encode() + b'\0' in data
    required = dict(entry['defaults'])
    required.update(entry['noJit'])
    required.update(entry['locked'])
    for key, value in required.items():
        if not present(key):
            findings.append(f'{core_id}: option {key} is not declared by the core')
        elif not present(value):
            findings.append(f'{core_id}: value {value!r} of {key} is not offered by the core')
    for key, values in entry['settings']:
        if not present(key):
            findings.append(f'{core_id}: setting {key} is not declared by the core')
        findings += [f'{core_id}: choice {value!r} of {key} is not offered by the core'
                     for value in values if not present(value)]
    resolution = entry['resolution']
    if resolution is not None:
        if not present(resolution['library']):
            findings.append(f"{core_id}: library name {resolution['library']!r} is not in the core")
        if not present(resolution['key']):
            findings.append(f"{core_id}: resolution option {resolution['key']} is not declared by the core")
        findings += [f"{core_id}: resolution value {value!r} of {resolution['key']} is not offered by the core"
                     for value in resolution['values'] + [resolution['default']] if not present(value)]
    declared = set()
    for prefix in PREFIXES[core_id]:
        pattern = re.escape(prefix.encode()) + rb'[A-Za-z0-9_\-]+(?=\0)'
        declared |= {match.group(0).decode('ascii') for match in re.finditer(pattern, data)}
    for key in sorted(declared):
        if CODE_GENERATION.search(key) and key not in entry['noJit']:
            findings.append(f'{core_id}: {key} can enable generated code but has no no-JIT override')
    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cores', type=Path, help='LibretroCores artifact directory')
    args = parser.parse_args()
    cores = catalog()
    manifest = json.loads((ROOT / 'build-utils/libretro/cores.json').read_text(encoding='utf-8'))
    packaged = [core['id'] for core in manifest['cores']]
    require(sorted(cores) == sorted(packaged), f'catalog {sorted(cores)} differs from packaged {sorted(packaged)}')
    require(set(PREFIXES) == set(packaged), 'every packaged core needs its option prefixes')
    # Replaces the former ">= 4 curated settings" count: the exact set also
    # catches a setting that silently stops being parsed or offered.
    curated = {(core_id, key) for core_id, entry in cores.items() for key, _ in entry['settings']}
    require(curated == CURATED, f'curated settings {sorted(curated)} differ from {sorted(CURATED)}')
    require(all(values for entry in cores.values() for _, values in entry['settings']),
            'curated setting choices were not parsed')
    choices = {(core_id, key): values for core_id, entry in cores.items() for key, values in entry['settings']}
    for setting, expected in CURATED_CHOICES.items():
        require(choices.get(setting) == expected, f'choices of {setting} {choices.get(setting)} differ from {expected}')
    locked = {core_id: entry['locked'] for core_id, entry in cores.items() if entry['locked']}
    require(locked == LOCKED, f'locked options {locked} differ from {LOCKED}')
    resolution = {core_id: (entry['resolution']['library'], entry['resolution']['key'])
                  for core_id, entry in cores.items() if entry['resolution'] is not None}
    require(resolution == RESOLUTION, f'resolution declarations {resolution} differ from {RESOLUTION}')
    for core_id, entry in cores.items():
        declared = entry['resolution']
        if declared is not None:
            require(len(declared['values']) >= 2 and declared['default'] in declared['values'],
                    f'{core_id}: resolution values {declared["values"]} or default {declared["default"]!r} unparsed')
            # Build 455: native resolution by default, never a NeoStation
            # default above it (PPSSPP's former 960x544 is gone).
            require(declared['key'] not in entry['defaults'],
                    f"{core_id}: {declared['key']} has a NeoStation default; native is the default")
        overlap = set(entry['locked']) & (set(entry['defaults']) | set(entry['noJit']) |
                                          {key for key, _ in entry['settings']} |
                                          ({declared['key']} if declared else set()))
        require(not overlap, f'{core_id}: locked options {sorted(overlap)} are also defaults or settings')
    require(all(entry['noJit'] for core_id, entry in cores.items()
                if core_id in ('mupen64plus_next', 'ppsspp', 'desmume')),
            'no-JIT overrides were not parsed')
    require(cores['azahar']['defaults'].get('citra_use_fastinterp') == 'enabled',
            'FastInterp must default on without locking the user choice')
    require(not cores['azahar']['noJit'],
            'official iOS alpha compiles both JITs off and removes those options')
    if args.cores is None:
        print('Catalog parsed:', len(cores), 'cores; binary contract needs --cores')
        return
    identity = json.loads((args.cores / 'identity.json').read_text(encoding='utf-8'))
    require([core['id'] for core in identity['cores']] == packaged, 'artifact cores differ from the manifest')
    findings = []
    for core_id, entry in cores.items():
        binary = args.cores / 'Frameworks' / f'{core_id}_libretro.framework' / f'{core_id}_libretro'
        findings += binary_findings(core_id, entry, binary.read_bytes())
    require(not findings, '\n  ' + '\n  '.join(findings))
    print('Libretro core options match', len(cores), 'pinned binaries; code generation is overridden for',
          ', '.join(core_id for core_id, entry in cores.items() if entry['noJit']) + '; locked options checked for',
          ', '.join(sorted(locked)) + '; internal resolution checked for', ', '.join(sorted(resolution)))


if __name__ == '__main__':
    main()
