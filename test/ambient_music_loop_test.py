#!/usr/bin/env python3
"""Ambient music loop (Build 448): the bundled asset, rendered by SoLoud.

1. The asset is the reproducible output of
   tools/ambient_music/build_ambient_music_asset.py: Ogg Vorbis, 44.1 kHz
   stereo, exactly 2 539 957 frames (final granule position), the size and
   SHA-256 that HomeMusicService pins for its cached copy.
2. test/native/ambient_music_loop_harness.cpp is compiled against the
   flutter_soloud sources resolved by `flutter pub get` (the same SoLoud the
   app links) and renders the loop through SoLoud's mixer:
   - 21 loops (20 min 10 s) in the app's 2048-frame blocks, streamed
     (LoadMode.disk, what the app uses) and in memory;
   - 3 loops in odd blocks (512, 997 frames), so a seam falls inside, at
     the start and at the end of a mix call;
   - resumes after a seek (start, middle, 0.5 s before the seam), as after
     a game, across 2 seams.
   Every sample must equal the decoded asset (one-sample mixer delay, centre
   pan gain): no gap, no repeat, no click; the only silent sample is the
   mixer's first.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / 'assets/sounds/once_upon_a_time_loop.ogg'
HARNESS = ROOT / 'test/native/ambient_music_loop_harness.cpp'
SERVICE = ROOT / 'lib/services/home_music_service.dart'
REPORT = ROOT / 'tools/ambient_music/build_report.json'

FRAMES = 2_539_957
ASSET_BYTES = 1_752_020
ASSET_SHA256 = '86a12b262f8e959c387180b735cdf69521a9042657f1d64c8f835ce3199d20b9'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit('FAIL: ' + message)


def ogg_pages(data: bytes):
    offset = 0
    while offset < len(data):
        require(data[offset:offset + 4] == b'OggS', f'no Ogg page at {offset}')
        granule = struct.unpack_from('<q', data, offset + 6)[0]
        segments = data[offset + 26]
        table = data[offset + 27:offset + 27 + segments]
        body = offset + 27 + segments
        yield granule, data[body:body + sum(table)]
        offset = body + sum(table)


def check_asset() -> None:
    data = ASSET.read_bytes()
    require(len(data) == ASSET_BYTES, f'asset size {len(data)}')
    require(hashlib.sha256(data).hexdigest() == ASSET_SHA256, 'asset SHA-256 differs')
    pages = list(ogg_pages(data))
    header = pages[0][1]
    require(header[:7] == b'\x01vorbis', 'not a Vorbis stream')
    channels = header[11]
    rate = struct.unpack_from('<I', header, 12)[0]
    require((channels, rate) == (2, 44100), f'{channels} channels at {rate} Hz')
    require(pages[-1][0] == FRAMES, f'final granule {pages[-1][0]} instead of {FRAMES}')
    report = json.loads(REPORT.read_text())
    require(report['assetSha256'] == ASSET_SHA256, 'build report and asset disagree')
    require(report['loopFrames'] == FRAMES, 'build report loop length')
    service = SERVICE.read_text()
    require(f'bundledTrackBytes = {ASSET_BYTES:_}'.replace('_', '') in service.replace('_', ''),
            'HomeMusicService does not pin the asset size')
    require(f"bundledTrackSha256Prefix = '{ASSET_SHA256[:8]}'" in service,
            'HomeMusicService does not pin the asset SHA-256 prefix')
    require("'assets/sounds/once_upon_a_time_loop.ogg'" in service, 'asset path')
    require('LoadMode.disk' in service, 'the bundled loop must be streamed from disk')
    print(f'asset: Vorbis 44.1 kHz stereo, {FRAMES} frames, {ASSET_BYTES} bytes, SHA-256 {ASSET_SHA256[:12]}…')


def soloud_root() -> Path:
    config = json.loads((ROOT / '.dart_tool/package_config.json').read_text())
    for package in config['packages']:
        if package['name'] == 'flutter_soloud':
            uri = package['rootUri']
            path = Path(uri[len('file://'):]) if uri.startswith('file://') else (ROOT / '.dart_tool' / uri).resolve()
            return path / 'src/soloud'
    raise SystemExit('FAIL: flutter_soloud is not resolved (run flutter pub get)')


def build(directory: Path) -> Path:
    soloud = soloud_root()
    compiler = os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++')
    require(compiler is not None, 'no C++ compiler')
    shim = directory / 'dr_mp3_impl.cpp'
    # dr_impl.cpp leaves dr_mp3's implementation to the plugin's own unit.
    shim.write_text('#define DR_MP3_IMPLEMENTATION\n#include "dr_mp3.h"\n')
    sources = sorted(str(p) for p in (soloud / 'src/core').glob('*.cpp'))
    wav = soloud / 'src/audiosource/wav'
    sources += [str(wav / 'soloud_wav.cpp'), str(wav / 'soloud_wavstream.cpp'), str(wav / 'dr_impl.cpp'),
                str(wav / 'stb_vorbis.c'), str(soloud / 'src/backend/null/soloud_null.cpp')]
    objects = []
    for index, source in enumerate(sources + [str(shim), str(HARNESS)]):
        language = ['-x', 'c'] if source.endswith('.c') else ['-x', 'c++', '-std=c++17']
        obj = directory / f'{index}.o'
        subprocess.run([compiler, *language, '-O2', '-DWITH_NULL', f'-I{soloud / "include"}', f'-I{wav}',
                        '-w', '-c', source, '-o', str(obj)], check=True)
        objects.append(str(obj))
    binary = directory / 'ambient_music_loop_harness'
    subprocess.run([compiler, *objects, '-o', str(binary), '-lpthread'], check=True)
    return binary


def run(binary: Path, mode: str, loops: int, block: int) -> list[dict]:
    result = subprocess.run([str(binary), mode, str(ASSET), str(loops), str(block)],
                            capture_output=True, text=True)
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    for line in lines:
        print(json.dumps(line))
    require(result.returncode == 0, f'{mode} {loops}x{block}: harness status {result.returncode}\n{result.stderr}')
    return lines


def main() -> int:
    check_asset()
    with tempfile.TemporaryDirectory(prefix='neostation-ambient-loop-') as directory:
        binary = build(Path(directory))
        long_runs = run(binary, 'loop', 21, 2048)
        require({r['source'] for r in long_runs} == {'disk', 'memory'}, 'both load modes')
        for r in long_runs:
            require(r['frames'] == FRAMES, 'decoded length')
            require(r['seconds'] >= 20 * 60, 'at least 20 minutes rendered')
            # The voice decodes ahead of the mixer: the last rewind may be
            # counted before its first sample is mixed.
            require(r['loopCountReported'] in (20, 21), f"{r['source']}: {r['loopCountReported']} seams crossed")
            require(r['worstAbsError'] < 1e-6, f"{r['source']}: sample error {r['worstAbsError']}")
            require(r['longestSilentRun'] == 1, f"{r['source']}: silent run {r['longestSilentRun']}")
            require(abs(r['gainL'] - 0.5 ** 0.5) < 1e-4 and abs(r['gainR'] - 0.5 ** 0.5) < 1e-4, 'pan gain')
        for block in (512, 997):
            for r in run(binary, 'loop', 3, block):
                require(r['loopCountReported'] in (2, 3) and r['worstAbsError'] < 1e-6, f'block {block}')
                require(r['longestSilentRun'] == 1, f'block {block}: silent run')
        seeks = run(binary, 'seek', 2, 2048)
        require(len(seeks) == 3, 'three resume positions')
        for r in seeks:
            require(r['landedFrame'] is not None, 'seek landing point not found')
            require(abs(r['landedFrame'] - r['requestedFrame']) <= 4096, 'seek landed far from the request')
            require(r['worstAbsError'] < 1e-6, f"resume at {r['requestedFrame']}: error {r['worstAbsError']}")
            require(r['loopCountReported'] >= 1, 'a seam crossed after the resume')
    print('PASS: ambient loop exact over 21 loops (20 min 10 s), odd blocks and resumes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
