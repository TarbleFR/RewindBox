#!/usr/bin/env python3
"""The Core's audio diagnostics reach the device logs (REWINDBOX_AUDIO_DIAGNOSTICS_EXPORT_641).

IPA 640 (4 November 2026): the maintainer heard audio stutters in Assassin's Creed, and the device logs held no
runtime audio counter. The Core already writes three cumulative audio lines at notice level, each at most once per
2 s: cellAudio queue diagnostics and cellAudio producer diagnostics (rpcs3/Emu/Cell/Modules/cellAudio.cpp,
audio_ringbuffer::log_diagnostics) and RemoteIO diagnostics (rpcs3/Emu/Audio/IOS/IOSAudioBackend.cpp,
IOSAudioBackend::log_diagnostics). The host log callback (Rpcs3InternalBridgePlugin.mm) drops every notice line that
is not a profiler line, so none of them was written. Core 641 gives them the COREPROF AUDIO641 prefix the host
already admits (the host bridge is unchanged: its bytes are pinned by the MoltenVK dependency evidence). This test:
- reads the three format strings from the canonical Core delta: each starts with its COREPROF marker, and the old
  unprefixed formats are gone;
- compiles the host's real `const BOOL profiler = ...;` expression and evaluates it on the three real messages
  (admitted), on the old formats (dropped, the IPA 640 defect) and on an ordinary audio notice (still dropped).
No device or audio-quality claim.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
PATCH = ROOT / 'build-utils/rpcs3/embedded-core.patch'
MARKERS = ('COREPROF AUDIO641 part=queue cumulative ', 'COREPROF AUDIO641 part=producer cumulative ',
           'COREPROF AUDIO641 part=remoteio cumulative ')
OLD = ('cellAudio queue diagnostics: ', 'cellAudio producer diagnostics: ', 'RemoteIO diagnostics: ')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit('FAIL: ' + message)


def main() -> None:
    patch = PATCH.read_text('utf-8', 'surrogateescape')
    for marker in MARKERS:
        formats = re.findall(r'^\+.*\.notice\("(' + re.escape(marker) + r'[^"]*)"', patch, re.M)
        require(len(formats) == 1, 'one Core notice format starts with ' + repr(marker) + f' (found {len(formats)})')
    for old in OLD:
        require(not re.findall(r'^\+.*\.notice\("' + re.escape(old), patch, re.M), 'the unprefixed format remains: ' + old)
    host = HOST.read_text('utf-8', 'surrogateescape')
    match = re.search(r'const BOOL profiler =(.*?);\n', host, re.S)
    require(match is not None, 'the host profiler expression')
    expression = re.sub(r'//[^\n]*', '', match.group(1))
    require(host[match.end():].lstrip().startswith('// Core already emits bounded video archive'),
            'the profiler expression is the one the level filter reads')
    require('if (level > 2 && !profiler && !videoArchive) return;' in host, 'notice lines need the profiler test')
    messages = {
        'COREPROF AUDIO641 part=queue cumulative requested_frames=1 delivered_frames=1 starved_frames=0': 1,
        'COREPROF AUDIO641 part=producer cumulative no_port_silence=0 untouched_silence=0': 1,
        'COREPROF AUDIO641 part=remoteio cumulative callbacks=10 requested_frames=5120 filler_frames=20': 1,
        'cellAudio queue diagnostics: cumulative requested_frames=1 delivered_frames=1 starved_frames=0': 0,
        'RemoteIO diagnostics: cumulative callbacks=10 requested_frames=5120 filler_frames=20': 0,
        'cellAudio: audio_out_configure(): unchanged': 0,
        'RemoteIO output component is available': 0,
    }
    source = ['#include <cstdio>', '#include <cstring>', 'typedef bool BOOL;', 'static int admitted(const char* message) {',
              f'  const BOOL profiler ={expression};', '  return profiler ? 1 : 0;', '}', 'int main() {', '  int failures = 0;']
    for message, expected in messages.items():
        literal = message.replace('\\', '\\\\').replace('"', '\\"')
        source.append(f'  if (admitted("{literal}") != {expected}) {{ std::printf("wrong: %s\\n", "{literal}"); failures++; }}')
    source += ['  std::printf("{\\"failures\\": %d}\\n", failures);', '  return failures != 0;', '}']
    with tempfile.TemporaryDirectory(prefix='audio-export-641-') as temporary:
        cpp = Path(temporary) / 'admission.cpp'
        cpp.write_text('\n'.join(source) + '\n')
        binary = Path(temporary) / 'admission'
        compiler = 'clang++' if subprocess.run(['which', 'clang++'], capture_output=True).returncode == 0 else 'g++'
        built = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(binary)],
                               capture_output=True, text=True)
        require(built.returncode == 0, 'compile the host expression:\n' + built.stderr[-2000:])
        run = subprocess.run([str(binary)], capture_output=True, text=True)
        require(run.returncode == 0, 'host admission:\n' + run.stdout)
    print('PASS: the three Core 641 audio diagnostics are admitted by the real host filter; the old formats and ordinary audio notices are dropped')


if __name__ == '__main__':
    sys.exit(main())
