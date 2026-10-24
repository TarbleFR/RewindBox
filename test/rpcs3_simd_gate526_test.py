#!/usr/bin/env python3
"""Exercise the production SDK gate and its compiler-dependency exclusion check.

Mocked commands validate orchestration only. A small real compiler smoke test
separately verifies -MD/-MF emission with -fsyntax-only, including inactive versus
active includes. Neither is an iPhone gameplay test.
"""
import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rpcs3_gate526', ROOT / 'build-utils/rpcs3_core_syntax_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def mock_gate(directory, *, legacy=None, missing_dependency=None, omit_unit=None, compiler_failure=None):
    entries = []
    flags = {}
    for name in sorted(gate.UNITS - ({omit_unit} if omit_unit else set())):
        flags[name] = ['-fno-exceptions', '-fexceptions'] if name == 'SourceClient.cpp' else ['-fexceptions']
        entries.append({'file': '/core/rpcs3/Emu/RSX/VK/vkutils/memory.cpp' if name == 'memory.cpp' else name,
            'directory': str(directory), 'arguments': ['clang++', '--target=arm64-apple-ios16.3',
                '-std=c++23', *flags[name], '-DREQUIRED=1', '-c', name, '-o', name + '.o',
                '-MD', '-MF', name + '.old.d', '-MT', 'old.o', '@' + name + '.o.modmap']})
    database = directory / 'compile_commands.json'
    database.write_text(json.dumps(entries))
    # Seed stale, forbidden evidence: each compiler invocation must replace it.
    stale = directory / 'rpcs3-native-simd-dependencies'
    stale.mkdir()
    for name in gate.NATIVE_SIMD_UNITS:
        (stale / (name + '.d')).write_text('stale.o: /old/sse2neon.h\n')
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[0] == 'cmake':
            assert not any(c[0] == 'clang++' for c in calls)
            for name in flags:
                (directory / (name + '.o.modmap')).write_text('-DREAL_MAP_GENERATED=1')
            return subprocess.CompletedProcess(args, 0)
        name = next(name for name in flags if name in args)
        response = next(arg[1:] for arg in args if arg.startswith('@'))
        assert (directory / response).read_text() == '-DREAL_MAP_GENERATED=1'
        assert '--target=arm64-apple-ios16.3' in args and '-std=c++23' in args
        assert '-DREQUIRED=1' in args and '-fsyntax-only' in args
        assert '-c' not in args and '-o' not in args
        assert [a for a in args if a in ('-fexceptions', '-fno-exceptions')] == flags[name]
        if name in gate.NATIVE_SIMD_UNITS:
            assert args.count('-MD') == args.count('-MF') == args.count('-MT') == 1
            dependency = Path(args[args.index('-MF') + 1])
            assert dependency.is_absolute() and not dependency.exists(), 'Stale evidence must be removed'
            if name != missing_dependency:
                dependency.write_text(name + '.o: ' + name + ' /core/rpcs3/util/simd.hpp \\\n /SDK/usr/include/arm_neon.h' + (' /core/rpcs3/Emu/CPU/sse2neon.h' if name == legacy else '') + '\n')
        else:
            assert '-MD' not in args and '-MF' not in args and '-MT' not in args
        return subprocess.CompletedProcess(args, int(name == compiler_failure))
    output = io.StringIO()
    error = None
    with patch.object(gate.subprocess, 'run', side_effect=run), redirect_stdout(output):
        try:
            gate.main(database)
        except RuntimeError as failure:
            error = str(failure)
    return calls, error, output.getvalue()


def orchestration_cases(directory):
    expected = {'SPUInterpreter.cpp', 'BufferUtils.cpp', 'ProgramStateCache.cpp', 'RSXTexture.cpp', 'FPToCFG.cpp'}
    assert gate.NATIVE_SIMD_UNITS == expected and len(gate.UNITS) == 47
    cases = []
    for name, options, message in (
        ('native-no-legacy', {}, None),
        ('active-legacy-rejected', {'legacy': 'SPUInterpreter.cpp'}, 'Legacy SSE compatibility header is active'),
        ('missing-dependency-rejected', {'missing_dependency': 'RSXTexture.cpp'}, 'Missing compiler dependency file'),
        ('missing-unit-rejected', {'omit_unit': 'FPToCFG.cpp'}, 'Missing startup units'),
        ('compiler-failure-preserved', {'compiler_failure': 'SPUInterpreter.cpp'}, 'iOS syntax errors in: SPUInterpreter.cpp'),
    ):
        work = directory / name
        work.mkdir()
        calls, error, output = mock_gate(work, **options)
        if message:
            assert error and message in error, (name, error)
        else:
            assert error is None, error
            assert output.count('PASS native SIMD dependency closure:') == 5
        if name == 'missing-unit-rejected':
            assert not calls, 'A missing source must fail before compilation'
        else:
            assert calls[0][0] == 'cmake' and len(calls) == 48
            assert len([c for c in calls if '-MD' in c]) == 5, 'No redundant preprocessing invocation'
        cases.append(name)
    return cases


def compiler_cases(directory):
    compiler = shlex.split(os.environ.get('CXX', 'c++'))
    assert shutil.which(compiler[0]), 'A real host C++ compiler is required'
    source = directory / 'dependency-smoke.cpp'
    (directory / 'sse2neon.h').write_text('#pragma once\n')
    source.write_text('#if LEGACY_ACTIVE\n#include "sse2neon.h"\n#endif\nint native_simd_probe;\n')
    cases = []
    for active in (0, 1):
        dependency = directory / ('compiler-' + str(active) + '.d')
        args = compiler + ['-fsyntax-only', '-MD', '-MF', str(dependency), '-MT', 'probe.o',
                           '-DLEGACY_ACTIVE=' + str(active), str(source)]
        if sdk := os.environ.get('HOST_MACOS_SDK'):
            args += ['-isysroot', sdk]
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        assert result.returncode == 0, result.stdout.decode()
        assert dependency.is_file() and source.name in dependency.read_text()
        try:
            gate.verify_native_simd_dependencies(dependency)
            assert active == 0, 'An actually included legacy header passed'
        except RuntimeError as error:
            assert active == 1 and 'Legacy SSE compatibility header is active' in str(error)
        cases.append('real-compiler-' + ('active-rejected' if active else 'inactive-accepted'))
    return cases, subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    assert args.source.is_dir()
    with tempfile.TemporaryDirectory(prefix='rpcs3-simd-gate526-') as temporary:
        work = Path(temporary)
        cases = orchestration_cases(work)
        real, compiler = compiler_cases(work)
    report = dict(passed=True, cases=cases + real, compiler=compiler, syntaxUnits=len(gate.UNITS),
        dependencyConsumers=sorted(gate.NATIVE_SIMD_UNITS), redundantPreprocessPasses=0,
        moduleMapsGeneratedByCmake=True, mockOrchestration=True,
        realCompilerDependencySmoke=True, physicalDeviceTested=False)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
