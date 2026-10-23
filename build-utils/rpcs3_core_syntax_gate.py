#!/usr/bin/env python3
"""Run startup syntax checks with the actual iOS flags and generated module maps."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

UNITS = {'TAR.cpp', 'memory.cpp', 'IOSTextureHash.cpp', 'JITIOS.cpp', 'JITASM.cpp', 'JITLLVM.cpp', 'PPUAnalyser.cpp',
         'PPUFunction.cpp', 'PPUThread.cpp', 'PPUTranslator.cpp',
         'SPUCommonRecompiler.cpp', 'SPULLVMRecompiler.cpp', 'SPUThread.cpp',
         'VKResourceManager.cpp',
         'BufferUtils.cpp', 'RSXFIFO.cpp', 'RPCS3IOS.cpp', 'RPCS3IOSPerformance.cpp', 'buffer_object.cpp',
         'RPCS3IOSFreezeDump.cpp',  # NEOSTATION_BUILD487_DIAGNOSTICS_V1
         'System.cpp', 'sys_game.cpp',  # NEOSTATION_BUILD487_DIAGNOSTICS_V1 (D3/D4)
         'overlay_home_menu_savestate.cpp', 'overlay_home_menu_main_menu.cpp',  # NEOSTATION_BUILD487_DIAGNOSTICS_V1 (D4)
         'RSXThread.cpp', 'sys_mutex.cpp',  # NEOSTATION_BUILD487_DIAGNOSTICS_V1 (D1/rsx counter, D5)
         'RPCS3IOSExperimentalPolicy.cpp', 'RPCS3IOSSettings.cpp', 'system_config_types.cpp',  # NEOSTATION_BUILD487_DIAGNOSTICS_V1 (L2/L3/L5/L9)
         'VKProgramPipeline.cpp', 'fsr_pass.cpp', 'SourceClient.cpp', 'cellVdec.cpp'}

def main(database: Path) -> None:
    build = database.resolve().parent
    entries = [entry for entry in json.loads(database.read_text())
               if Path(entry['file']).name in UNITS and
               (Path(entry['file']).name != 'memory.cpp' or entry['file'].replace('\\', '/').endswith('/Emu/RSX/VK/vkutils/memory.cpp'))]
    found = {Path(entry['file']).name for entry in entries}
    if found != UNITS:
        raise RuntimeError('Missing startup units: ' + str(UNITS - found))
    commands = []
    generated_maps = set()
    for entry in entries:
        args = entry.get('arguments') or shlex.split(entry['command'])
        for arg in args:
            if arg.startswith('@'):
                response = (Path(entry['directory']) / arg[1:]).resolve()
                if not response.exists():
                    if response.suffix != '.modmap':
                        raise RuntimeError(f'Missing compiler response file: {response}')
                    # CMake declares each .modmap as an output of CXX_DYNDEP.
                    # Generate it through Ninja, never replace it with an empty file.
                    generated_maps.add(str(response.relative_to(build)))
        result = []
        skip = False
        for arg in args:
            if skip:
                skip = False
                continue
            if arg in ('-o', '-MF', '-MT', '-MQ'):
                skip = True
                continue
            if arg in ('-c', '-MD', '-MMD'):
                continue
            result.append(arg)
        result.append('-fsyntax-only')
        commands.append((entry, result))
    if generated_maps:
        jobs = max(1, int(os.environ.get('BUILD_JOBS', '3')))
        print('Generate actual CMake module maps before syntax checking', flush=True)
        subprocess.run(['cmake', '--build', str(build), '--parallel', str(jobs),
                        '--target', *sorted(generated_maps)], check=True)
        for relative in generated_maps:
            if not (build / relative).is_file():
                raise RuntimeError(f'CMake did not generate required module map: {relative}')
    failed = []
    for entry, command in commands:
        print('iOS syntax gate:', Path(entry['file']).name, flush=True)
        result = subprocess.run(command, cwd=entry['directory'], check=False)
        if result.returncode:
            failed.append(Path(entry['file']).name)
    if failed:
        raise RuntimeError('iOS syntax errors in: ' + ', '.join(failed))
    print(f'PASS: actual compiler, target, flags and module maps for all {len(UNITS)} startup units')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: rpcs3_core_syntax_gate.py <compile_commands.json>')
    main(Path(sys.argv[1]))
