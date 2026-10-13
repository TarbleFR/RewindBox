#!/usr/bin/env python3
"""Generate NeoStation's catalog of Dolphin's official post-processing shaders.

    tools/shaders/build_dolphin_catalog.py --dolphin-ios CHECKOUT --tool NEOSHADER_TOOL \
        [--metal-results dolphin-metal-results.json] [--output-directory DIR]

The embedded Dolphin core reads its post-processing shaders from the Sys
folder the application ships (Data/Sys/Shaders of the DolphiniOS revision
the delivery pins) and from Dolphin's user folder (shaders the player
imports). This lists the official ones, nothing is downloaded: every file
is pinned by size and SHA-256, so the in-game page offers a shader as
verified only when the file the application ships is that very file.

Each shader is translated with the core NeoStation reproduces Dolphin's
Metal pipeline with (neoshader-tool dolphin: Dolphin's header and uniform
block, GLSL -> SPIR-V -> MSL for iOS); with the verdicts of the macOS CI
(test/neo_shader_kit_dolphin_test.py: iPhone Metal compiler, draw through
Dolphin's post-processing interface, visible change), an entry is
"rendered" only when it passed there. Dolphin's default pass, the
stereoscopic shaders (Anaglyph/, Passive/: NeoStation has no 3D mode) and
the failures go to the diagnostics file with their reason.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_slang_catalog import CATEGORIES, git_head, mentions  # noqa: E402

DOLPHIN_REPOSITORY = 'https://github.com/OatmealDome/dolphin-ios'
# DOLPHIN_SHA of .github/workflows/retroarch-delivery.yml: the core the
# application embeds and the Sys folder it ships.
DOLPHIN_COMMIT = '7cac54161659421ed95c2cd1c0b0746539a4cd38'
SHADERS = 'Data/Sys/Shaders'
COMPILER = 'glslang 16.3.0 + SPIRV-Cross (Khronos vulkan-sdk-1.4.350.1), MSL 2.3, Dolphin post-processing interface'
REPOSITORY_LICENSE = 'GPL-2.0-or-later'
# VideoCommon/PostProcessing.cpp: s_default_pixel_shader_name, never listed.
DEFAULT_SHADER = 'default_pre_post_process'
CATEGORY = {
    '16bit': 'retro', '32bit': 'retro', 'posterize': 'retro', 'posterize2': 'retro',
    'FXAA': 'anti-aliasing', 'integer_scaling': 'upscaling', 'nightvision2scanlines': 'scanlines',
    'AutoHDR': 'color', 'PerceptualHDR': 'color', 'grayscale': 'color', 'grayscale2': 'color', 'sepia': 'color',
    'invert': 'color', 'invert_blue': 'color', 'swap_RGB_BGR': 'color', 'swap_RGB_BRG': 'color',
    'swap_RGB_GBR': 'color', 'swap_RGB_GRB': 'color', 'swap_RGB_RBG': 'color', 'brighten': 'color',
    'darkerbrighter': 'color', 'primarycolors': 'color', 'sunset': 'color', 'cool1': 'color', 'mad_world': 'color',
    'toxic': 'color', 'nightvision': 'color', 'nightvision2': 'color', 'chrismas': 'color', 'fire': 'color',
    'fire2': 'color', 'firewater': 'color', 'spookey1': 'color', 'spookey2': 'color', 'acidmetal': 'color',
    'acidtrip': 'color', 'acidtrip2': 'color',
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def translate(tool, path):
    result = subprocess.run([str(tool), 'dolphin', str(path)], capture_output=True, text=True)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return {'ok': False, 'error': {'code': 'TOOL_FAILED', 'detail': result.stderr[-300:]}}
    return json.loads(lines[-1])


def tier(samples, loop):
    # One pass drawn at the screen size: texture reads per screen pixel.
    if samples <= 8 and not loop:
        return 'performance'
    if samples <= 32 and not loop:
        return 'balanced'
    return 'quality'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dolphin-ios', type=Path, required=True)
    parser.add_argument('--tool', type=Path, required=True)
    parser.add_argument('--metal-results', type=Path)
    parser.add_argument('--output-directory', type=Path,
                        default=Path(__file__).resolve().parents[2] / 'packages/neo_shader_kit/ios/Resources')
    arguments = parser.parse_args()

    checkout = arguments.dolphin_ios.resolve()
    if git_head(checkout) != DOLPHIN_COMMIT:
        raise SystemExit(f'dolphin-ios checkout is not {DOLPHIN_COMMIT}')
    root = checkout / SHADERS
    metal = None
    if arguments.metal_results:
        metal = json.loads(arguments.metal_results.read_text(encoding='utf-8'))
        if metal.get('dolphinRevision') != DOLPHIN_COMMIT:
            raise SystemExit('Metal results were produced for another Dolphin revision')

    excluded, entries, files = [], [], []
    for path in sorted(root.rglob('*.glsl'), key=lambda item: item.relative_to(root).as_posix().lower()):
        relative = path.relative_to(root).as_posix()
        name = path.stem
        if '/' in relative:
            excluded.append([relative, 'STEREOSCOPIC_ONLY', relative.split('/')[0]])
            continue
        if name == DEFAULT_SHADER:
            excluded.append([relative, 'DEFAULT_SHADER', ''])
            continue
        result = translate(arguments.tool, path)
        if not result['ok']:
            excluded.append([relative, result['error']['code'], result['error']['detail'][:300]])
            continue
        validation = 'translated'
        if metal is not None:
            verdict = metal.get('files', {}).get(relative)
            if verdict is None:
                excluded.append([relative, 'METAL_NOT_VALIDATED', ''])
                continue
            if verdict.get('sha256') not in (None, sha256(path)):
                excluded.append([relative, 'METAL_OTHER_FILE', 'validated file differs'])
                continue
            if verdict.get('status') != 'rendered':
                # The log's detail, else the reading of the sources recorded
                # next to the verdict (an HDR-only shader is a pass-through here).
                reason = verdict.get('detail') or verdict.get('analysis', '')
                excluded.append([relative, verdict.get('code', 'METAL_FAILED'), reason[:300]])
                continue
            validation = 'rendered'
        code = path.read_text(encoding='utf-8', errors='replace')
        authors, licence, notes = mentions(root, [relative])
        if 'hdr_output' in code or 'HDR' in name:
            notes.append('hdr-output')
        options = result.get('options', [])
        if any(option['type'] != 'bool' and len(option['values']) > 1 for option in options):
            notes.append('vector-options')
        if not licence:
            # The files state none: they are part of the Dolphin repository,
            # "licensed under the terms of the GNU General Public License,
            # version 2 or later" (Readme.md, COPYING).
            licence = REPOSITORY_LICENSE
            notes.append('repository-license')
        files.append([f'Shaders/{relative}', path.stat().st_size, sha256(path)])
        entries.append({
            'id': f'sys/{name}',
            'name': name,
            'category': CATEGORY.get(name, 'other'),
            'family': 'Sys/Shaders',
            'format': 'dolphin-glsl',
            'files': [len(files) - 1],
            'bundled': True,
            'passes': 1,
            'parameters': len(options),
            'cost': {'samples': result['samples'], 'loop': result['samplesInLoop'],
                     'tier': tier(result['samples'], result['samplesInLoop'])},
            'mentions': authors,
            'license': licence,
            'validation': validation,
            'options': options,
            'notes': notes,
        })

    catalog = {
        'schema': 1,
        'engine': 'dolphin',
        'format': 'dolphin-glsl',
        'source': {'name': 'DolphiniOS Data/Sys/Shaders', 'repository': DOLPHIN_REPOSITORY,
                   'commit': DOLPHIN_COMMIT, 'raw': ''},
        'compiler': COMPILER,
        'validation': metal.get('environment', '') if metal else 'SPIR-V -> MSL translation only',
        'categories': [category for category in CATEGORIES if any(entry['category'] == category for entry in entries)],
        'files': files,
        'entries': entries,
    }
    diagnostics = {'schema': 1, 'engine': 'dolphin', 'commit': DOLPHIN_COMMIT, 'excluded': sorted(excluded)}
    output = arguments.output_directory
    output.mkdir(parents=True, exist_ok=True)
    (output / 'dolphin-catalog.json').write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + '\n',
                                                 encoding='utf-8')
    (output / 'dolphin-catalog-diagnostics.json').write_text(
        json.dumps(diagnostics, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'catalog': len(entries), 'excluded': len(excluded),
                      'validation': dict(Counter(entry['validation'] for entry in entries)),
                      'reasons': dict(Counter(item[1] for item in excluded)),
                      'categories': dict(Counter(entry['category'] for entry in entries))}, indent=2))


if __name__ == '__main__':
    main()
