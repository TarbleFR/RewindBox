#!/usr/bin/env python3
"""Generate NeoStation's catalog of RetroArch slang shaders.

    tools/shaders/build_slang_catalog.py \
        --slang-shaders CHECKOUT --shader-previews CHECKOUT --tool NEOSHADER_TOOL \
        [--metal-results metal-validation.json] [--output-directory DIR] [--report REPORT.md]

Both checkouts must be at the commits pinned below (libretro/slang-shaders
and libretro/shader-previews). Every preset of the repository is
classified; the presets of the user-facing categories are compiled with the
same core the application runs (neoshader-tool: preset rules, glslang,
reflection, SPIRV-Cross -> MSL for iOS). A preset enters the catalog only
when that succeeds and, once a Metal validation file from the macOS CI is
given, when its passes also compiled for iOS and rendered with Metal.
Everything else goes to the diagnostics file with its reason.

Each entry lists every file it needs (preset chain, sources, includes,
textures) with its size and SHA-256, so the application downloads exactly
those files from the pinned commit and refuses any other content. Cost
classes come from known figures of each preset (see cost()), never from a
guess. Previews are mapped from shader-previews by path.
"""
import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

SLANG_REPOSITORY = 'https://github.com/libretro/slang-shaders'
SLANG_COMMIT = 'e1d75632a205c70f14a4cc947c46d5abb7b3f7f1'
SLANG_DATE = '2026-10-08'
PREVIEWS_REPOSITORY = 'https://github.com/libretro/shader-previews'
PREVIEWS_COMMIT = '2adabb17c594c0eafd58bac2d3c93a1a9d4e7631'
COMPILER = 'glslang 16.3.0 + SPIRV-Cross (Khronos vulkan-sdk-1.4.350.1), MSL 2.4'

CATEGORIES = ('crt', 'scanlines', 'lcd', 'pixel-art', 'upscaling', 'sharpen', 'anti-aliasing', 'ntsc-pal',
              'color', 'retro', 'vhs', 'other')

# Folders whose presets are not offered, with the stable reason shown in the
# developer diagnostics.
EXCLUDED_FOLDERS = {
    'bezel': 'EXCLUDED_BEZEL_LAYOUT',      # full-TV bezels; NeoStation draws the game in its own area (skins)
    'hdr': 'EXCLUDED_HDR_OUTPUT',          # HDR swapchain uniforms; NeoStation presents SDR BGRA8
    'stereoscopic-3d': 'EXCLUDED_STEREO',  # needs a stereoscopic display mode
    'subframe-bfi': 'EXCLUDED_SUBFRAMES',  # needs sub-frame presentation (RetroArch's BFI)
    'test': 'EXCLUDED_TEST_PATTERN',       # developer test patterns
    'nes_raw_palette': 'EXCLUDED_RAW_PALETTE',  # needs the core's raw NES palette output
    'spec': 'EXCLUDED_TEST_PATTERN',
}

FOLDER_CATEGORIES = {
    'crt': 'crt', 'scanlines': 'scanlines', 'handheld': 'lcd', 'pixel-art-scaling': 'pixel-art',
    'edge-smoothing': 'upscaling', 'interpolation': 'upscaling', 'sharpen': 'sharpen', 'deblur': 'sharpen',
    'anti-aliasing': 'anti-aliasing', 'ntsc': 'ntsc-pal', 'pal': 'ntsc-pal', 'vhs': 'vhs', 'film': 'retro',
    'cel': 'retro', 'dithering': 'retro', 'gpu': 'retro', 'blurs': 'other', 'motionblur': 'other',
    'denoisers': 'other', 'deinterlacing': 'other', 'downsample': 'other', 'border': 'other', 'warp': 'other',
    'linear': 'other', 'anamorphic': 'other', 'motion-interpolation': 'other', 'auto-box': 'other',
    'quad': 'other', 'procedural': 'other',
}

# misc/, reshade/ and presets/ hold several kinds: classified by name.
NAME_RULES = (
    ('crt', r'crt|royale|lottes|geom|hyllian|guest|trinitron|aperture|phosphor|potato|gizmo|beam|kurozumi|tvout|monitor'),
    ('lcd', r'gameboy|\bgba\b|gbc|handheld|lcd|dot-matrix|frontlit|dmg'),
    ('ntsc-pal', r'ntsc|pal\b|composite|svideo|s-video'),
    ('vhs', r'vhs'),
    ('upscaling', r'xbr|scalefx|scalehq|mmpx|fsr|nedi|super-|jinc|lanczos|bicubic|interpolat|scale\d|hqx|xbrz'),
    ('sharpen', r'sharp|deblur|cas\b|adaptive'),
    ('anti-aliasing', r'fxaa|smaa|aa\b|antialias'),
    ('color', r'colou?r|grade|gamma|white_point|hue|chroma|tonemap|natural|palette|adjust|night|lut|levels|'
              r'saturation|contrast|bright|vibrance|curves|technicolor|sepia|black-and-white'),
    ('retro', r'ega|ascii|bead|cmyk|halftone|print|retro|3dfx|dither|grain|film|cel|toon|weave|pixel'),
    ('scanlines', r'scanline'),
)

# Attribution lines only: "Copyright (C) 2014 Name", "Author: Name",
# "by Name", "ported/adapted ... by Name". Licence boilerplate that merely
# contains these words is skipped.
AUTHOR_PATTERN = re.compile(
    r'copyright\s*(?:\(c\)|©)?\s*(?:19|20)\d\d|\(c\)\s*(?:19|20)\d\d|©\s*(?:19|20)\d\d|'
    r'\bauthors?\s*:|^by\s+\S+(?:\s+\S+){0,3}$|\b(?:ported|adapted|written|created|converted|translated|modified|'
    r'rewritten|optimized)\b[^.]{0,60}\bby\s+\S', re.IGNORECASE)
BOILERPLATE = re.compile(r'copyright notice|copyright holders|copyright laws|copyright interest|all copyright|'
                         r'permission notice|without warranty|liable for|the authors? (?:or|be)', re.IGNORECASE)
# A "by ..." line that continues a sentence ("by the aspect ratio...").
SENTENCE_WORDS = re.compile(r'\b(?:the|a|an|to|of|and|or|which|this|that|using|default|for|with|from|in|is|are)\b',
                            re.IGNORECASE)
EMAIL = re.compile(r'<?[\w.+-]+@[\w-]+(?:\.[\w-]+)+>?')
SHADERTOY = re.compile(r'shadertoy\.com', re.IGNORECASE)
LICENSES = (
    ('CC BY-NC-SA', re.compile(r'creative\s+commons.*non-?commercial.*share-?alike|cc\s*by-nc-sa', re.I)),
    ('CC BY-NC', re.compile(r'creative\s+commons.*non-?commercial|cc\s*by-nc', re.I)),
    ('GPL-3.0-or-later', re.compile(r'gnu general public license.*version 3|gplv3|gpl-3', re.I | re.S)),
    ('GPL-2.0-or-later', re.compile(r'gnu general public license|gplv2|gpl-2|\bgpl\b', re.I)),
    ('MIT', re.compile(r'\bmit license\b|permission is hereby granted, free of charge', re.I)),
    ('BSD', re.compile(r'\bbsd\b|redistribution and use in source and binary forms', re.I)),
    ('Unlicense', re.compile(r'unlicense', re.I)),
    ('Public domain', re.compile(r'public\s+domain', re.I)),
    ('Zlib', re.compile(r'zlib license|altered source versions must be plainly marked', re.I)),
)

# Reference scenario of the cost estimate: a 320x240 picture shown on a
# 1572x1179 screen area (4:3 at the height of a 6.1" iPhone in landscape).
REFERENCE_SOURCE = (320.0, 240.0)
REFERENCE_VIEWPORT = (1572.0, 1179.0)


def git_head(checkout):
    return subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                          text=True).stdout.strip()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_size(path):
    data = path.read_bytes()[:24]
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return struct.unpack('>II', data[16:24])


def classify(preset):
    parts = preset.split('/')
    top = parts[0] if len(parts) > 1 else '.'
    if top in EXCLUDED_FOLDERS:
        return None, EXCLUDED_FOLDERS[top]
    if '/refs/' in preset or preset.startswith('refs/'):
        return None, 'EXCLUDED_FRAGMENT'
    if top in FOLDER_CATEGORIES:
        return FOLDER_CATEGORIES[top], None
    name = preset.lower()
    for category, pattern in NAME_RULES:
        if re.search(pattern, name):
            return category, None
    return 'other', None


def family(preset):
    parent = preset.rsplit('/', 1)[0] if '/' in preset else ''
    return parent


def comment_lines(text, limit=120):
    lines = []
    for line in text.splitlines()[:limit]:
        stripped = line.strip()
        if stripped.startswith(('//', '/*', '*', '#')) or (lines and not stripped.startswith(('layout', 'void', 'vec', 'float', 'uniform'))):
            lines.append(stripped)
    return lines


def mentions(root, files):
    found, licence_text = [], []
    shadertoy = False
    for relative in files:
        if not relative.endswith(('.slang', '.inc', '.h', '.glsl')):
            continue
        text = (root / relative).read_text(encoding='utf-8', errors='replace')
        head = '\n'.join(text.splitlines()[:150])
        licence_text.append(head)
        shadertoy = shadertoy or bool(SHADERTOY.search(head))
        for line in comment_lines(text, 150):
            cleaned = re.sub(r'^[/*#\s]+', '', line).strip()
            cleaned = re.sub(r'[*/\s]+$', '', cleaned).strip()
            if not AUTHOR_PATTERN.search(cleaned) or BOILERPLATE.search(cleaned):
                continue
            if re.match(r'by\s', cleaned, re.IGNORECASE) and SENTENCE_WORDS.search(cleaned[3:]):
                continue
            cleaned = re.sub(r'\s{2,}', ' ', EMAIL.sub('', cleaned)).strip(' -,;:')
            if 3 <= len(cleaned) <= 140 and cleaned not in found:
                found.append(cleaned)
    licence = ''
    joined = '\n'.join(licence_text)
    for name, pattern in LICENSES:
        if pattern.search(joined):
            licence = name
            break
    notes = ['shadertoy-origin'] if shadertoy else []
    return found[:4], licence, notes


def pass_size(previous, kind, scale, absolute, viewport):
    if kind == 'viewport':
        return viewport * scale
    if kind == 'absolute':
        return float(absolute)
    return previous * scale


def cost(result):
    """Texture reads per screen pixel, weighted by each pass's pixel count.

    Known figures only: each pass's sampling instructions along its call
    graph (neoshader-tool) and the size of its output under the reference
    scenario, from the preset's scale rules (a last pass without scale draws
    at the screen size, any other one at its source size).
    """
    width, height = REFERENCE_SOURCE
    viewport_w, viewport_h = REFERENCE_VIEWPORT
    total = 0.0
    loop = False
    float_passes = 0
    passes = result['passes']
    for index, item in enumerate(passes):
        last = index == len(passes) - 1
        if item['scaleSet']:
            width = pass_size(width, item['scaleTypeX'], item['scaleX'], item['absoluteX'], viewport_w)
            height = pass_size(height, item['scaleTypeY'], item['scaleY'], item['absoluteY'], viewport_h)
        elif last:
            width, height = viewport_w, viewport_h
        total += item['samples'] * width * height / (viewport_w * viewport_h)
        loop = loop or item['samplesInLoop']
        if item['format'] in ('R16G16B16A16_SFLOAT', 'R32G32B32A32_SFLOAT', 'R16G16_SFLOAT', 'R32G32_SFLOAT',
                              'R16_SFLOAT', 'R32_SFLOAT'):
            float_passes += 1
    count = len(passes)
    history = result['historyDepth']
    if total <= 8 and count <= 2 and float_passes == 0 and history <= 1 and not loop:
        tier = 'performance'
    elif total <= 32 and count <= 6:
        tier = 'balanced'
    else:
        tier = 'quality'
    return round(total, 2), loop, float_passes, tier


def run_tool(tool, root, presets, jobs=None):
    """neoshader-tool slang-batch over `presets`, split across processes
    (each preset is compiled independently: the split changes no result)."""
    jobs = max(1, min(jobs or os.cpu_count() or 1, len(presets) or 1))
    with tempfile.TemporaryDirectory(prefix='slang-catalog-') as temporary:
        processes, outputs = [], []
        for index in range(jobs):
            chunk = presets[index::jobs]
            listing = Path(temporary) / f'presets-{index}.txt'
            output = Path(temporary) / f'results-{index}.jsonl'
            listing.write_text('\n'.join(chunk) + '\n', encoding='utf-8')
            processes.append(subprocess.Popen([str(tool), 'slang-batch', str(root), str(listing), str(output)]))
            outputs.append(output)
        for process in processes:
            if process.wait() != 0:
                raise SystemExit(f'neoshader-tool failed (exit {process.returncode})')
        results = {}
        for output in outputs:
            for line in output.read_text(encoding='utf-8').splitlines():
                if line.strip():
                    record = json.loads(line)
                    results[record['preset']] = record
        missing = [preset for preset in presets if preset not in results]
        if missing:
            raise SystemExit(f'{len(missing)} presets have no result, first: {missing[0]}')
        return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--slang-shaders', type=Path, required=True)
    parser.add_argument('--shader-previews', type=Path, required=True)
    parser.add_argument('--tool', type=Path, required=True)
    parser.add_argument('--metal-results', type=Path)
    parser.add_argument('--output-directory', type=Path,
                        default=Path(__file__).resolve().parents[2] / 'packages/neo_shader_kit/ios/Resources')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--results-cache', type=Path, help='Reuse or write the neoshader-tool results (JSON).')
    arguments = parser.parse_args()

    root = arguments.slang_shaders.resolve()
    previews = arguments.shader_previews.resolve()
    if git_head(root) != SLANG_COMMIT:
        raise SystemExit(f'slang-shaders checkout is not {SLANG_COMMIT}')
    if git_head(previews) != PREVIEWS_COMMIT:
        raise SystemExit(f'shader-previews checkout is not {PREVIEWS_COMMIT}')

    presets = sorted(path.relative_to(root).as_posix() for path in root.rglob('*.slangp') if '.git' not in path.parts)
    candidates, excluded = [], []
    categories = {}
    for preset in presets:
        category, reason = classify(preset)
        if category is None:
            excluded.append([preset, reason, ''])
        else:
            categories[preset] = category
            candidates.append(preset)

    if arguments.results_cache and arguments.results_cache.exists():
        results = json.loads(arguments.results_cache.read_text(encoding='utf-8'))
    else:
        results = run_tool(arguments.tool, root, candidates)
        if arguments.results_cache:
            arguments.results_cache.write_text(json.dumps(results), encoding='utf-8')

    metal = None
    if arguments.metal_results:
        metal = json.loads(arguments.metal_results.read_text(encoding='utf-8'))
        if metal.get('slangCommit') != SLANG_COMMIT:
            raise SystemExit('Metal results were produced for another slang-shaders commit')

    reference = previews / 'upscale-test.png'
    preview_files = [['upscale-test.png', reference.stat().st_size, sha256(reference)]]
    reference_size = png_size(reference)

    file_index, files = {}, []

    def index_of(relative):
        if relative not in file_index:
            path = root / relative
            file_index[relative] = len(files)
            files.append([relative, path.stat().st_size, sha256(path)])
        return file_index[relative]

    entries = []
    for preset in candidates:
        result = results.get(preset)
        if result is None:
            excluded.append([preset, 'NOT_COMPILED', ''])
            continue
        if not result['ok']:
            excluded.append([preset, result['error']['code'], result['error']['detail'][:300]])
            continue
        validation = 'translated'
        if metal is not None:
            verdict = metal.get('presets', {}).get(preset)
            if verdict is None:
                excluded.append([preset, 'METAL_NOT_VALIDATED', ''])
                continue
            if verdict.get('status') != 'rendered':
                excluded.append([preset, verdict.get('code', 'METAL_FAILED'), verdict.get('detail', '')[:300]])
                continue
            validation = 'rendered'
        missing = [relative for relative in result['files'] if not (root / relative).is_file()]
        if missing:
            excluded.append([preset, 'FILE_MISSING', ', '.join(missing)[:300]])
            continue
        samples, loop, float_passes, tier = cost(result)
        authors, licence, notes = mentions(root, result['files'])
        if not licence:
            notes.append('license-not-stated')
        preview_index = -1
        preview_path = previews / (preset[:-len('.slangp')] + '.png')
        if preview_path.is_file() and png_size(preview_path) is not None:
            preview_files.append([preview_path.relative_to(previews).as_posix(), preview_path.stat().st_size,
                                  sha256(preview_path)])
            preview_index = len(preview_files) - 1
        entries.append({
            'id': preset,
            'name': Path(preset).stem,
            'category': categories[preset],
            'family': family(preset),
            'files': [index_of(relative) for relative in result['files']],
            'passes': len(result['passes']),
            'luts': len(result['textures']),
            'parameters': len(result['parameters']),
            'history': result['historyDepth'],
            'feedback': sum(1 for item in result['passes'] if item['feedback']),
            'floatPasses': float_passes,
            'cost': {'samples': samples, 'loop': loop, 'tier': tier},
            'preview': preview_index,
            'mentions': authors,
            'license': licence,
            'validation': validation,
            'notes': notes,
        })

    catalog = {
        'schema': 1,
        'engine': 'libretro',
        'format': 'slang',
        'source': {'name': 'libretro/slang-shaders', 'repository': SLANG_REPOSITORY, 'commit': SLANG_COMMIT,
                   'date': SLANG_DATE, 'raw': f'https://raw.githubusercontent.com/libretro/slang-shaders/{SLANG_COMMIT}/'},
        'previews': {'name': 'libretro/shader-previews', 'repository': PREVIEWS_REPOSITORY, 'commit': PREVIEWS_COMMIT,
                     'raw': f'https://raw.githubusercontent.com/libretro/shader-previews/{PREVIEWS_COMMIT}/',
                     'reference': 0, 'scale': 8 if reference_size == (64, 64) else 0, 'files': preview_files},
        'compiler': COMPILER,
        'validation': metal.get('environment', '') if metal else 'SPIR-V -> MSL translation only',
        'categories': list(CATEGORIES),
        'files': files,
        'entries': entries,
    }
    diagnostics = {'schema': 1, 'engine': 'libretro', 'commit': SLANG_COMMIT, 'excluded': sorted(excluded)}
    output = arguments.output_directory
    output.mkdir(parents=True, exist_ok=True)
    (output / 'slang-catalog.json').write_text(json.dumps(catalog, separators=(',', ':'), ensure_ascii=False) + '\n',
                                               encoding='utf-8')
    (output / 'slang-catalog-diagnostics.json').write_text(
        json.dumps(diagnostics, separators=(',', ':'), ensure_ascii=False) + '\n', encoding='utf-8')

    per_category = Counter(entry['category'] for entry in entries)
    reasons = Counter(item[1] for item in excluded)
    tiers = Counter(entry['cost']['tier'] for entry in entries)
    summary = {
        'presets': len(presets), 'catalog': len(entries), 'excluded': len(excluded), 'files': len(files),
        'downloadBytes': sum(item[1] for item in files), 'previews': len(preview_files) - 1,
        'categories': dict(per_category), 'tiers': dict(tiers), 'reasons': dict(reasons),
    }
    print(json.dumps(summary, indent=2))
    if arguments.report:
        lines = ['# Catalogue slang — rapport de génération', '',
                 f'- Source : `{SLANG_REPOSITORY}` @ `{SLANG_COMMIT}` ({SLANG_DATE})',
                 f'- Aperçus : `{PREVIEWS_REPOSITORY}` @ `{PREVIEWS_COMMIT}`',
                 f'- Compilateur : {COMPILER}',
                 f'- Validation : {catalog["validation"]}', '',
                 f'Préréglages du dépôt : {len(presets)} ; au catalogue : {len(entries)} ; écartés : {len(excluded)}.', '',
                 '| Catégorie | Préréglages |', '|---|---:|']
        lines += [f'| {category} | {per_category.get(category, 0)} |' for category in CATEGORIES]
        lines += ['', '| Coût estimé | Préréglages |', '|---|---:|']
        lines += [f'| {tier} | {count} |' for tier, count in sorted(tiers.items())]
        lines += ['', '| Motif d’exclusion | Préréglages |', '|---|---:|']
        lines += [f'| `{reason}` | {count} |' for reason, count in reasons.most_common()]
        arguments.report.write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
