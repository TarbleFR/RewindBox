#!/usr/bin/env python3
"""Compiles and runs engine patch 0014 on .NET (Linux x64): the harness of test/s2arm_romfs_index_harness.

    s2arm_romfs_index_dotnet.py TOOLS S2ARM_CHECKOUT [--perf TREE]

TOOLS: a folder made by build-utils/s2arm/engine/dotnet_tools.py (Roslyn, the .NET reference assemblies and runtime).
S2ARM_CHECKOUT: a git checkout of S2Arm that holds the pinned commit (tools/s2arm_prototype/pin.json).

The two patched sources are made in a temporary folder: RomFsIndex.cs and Application.cs of the pinned commit with patch
0014 applied (the only patch of the series that touches them). RomFsIndex.cs is compiled whole. Of Application.cs, which
needs the rest of the services, the pieces that use the index are taken verbatim: the block that chooses between index
and directory build, RomFsFromDirectory, and LazyHostFile. LibHac is the package of S2Arm's own tree.
Prints one JSON line; exit 1 when a check fails. test/s2arm_romfs_index_test.py calls this when S2ARM_DOTNET_TOOLS and
S2ARM_UPSTREAM are set. It is not part of any build: s2arm-engine.yml compiles the engine (NativeAOT, iOS).
"""
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'test/s2arm_romfs_index_harness'
PATCH = ROOT / 'build-utils/s2arm/engine/patches/0014-guest-romfs-index-written-at-the-first-start.patch'
SOURCES = ('services/S2A.Services/RomFsIndex.cs', 'services/S2A.Services/Application.cs')
WRAPPER = '''using LibHac;
using LibHac.Common;
using LibHac.Fs;
using LibHac.Fs.Fsa;
using LibHac.Fs.Shim;
using LibHac.Loader;
using LibHac.Ncm;
using LibHac.Ns;
using LibHac.Tools.FsSystem;
using LibHac.Tools.FsSystem.RomFs;
using Microsoft.Win32.SafeHandles;
using System;
using System.Buffers;
using System.Collections.Generic;
using System.IO;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using ApplicationId = LibHac.Ncm.ApplicationId;
using Path = System.IO.Path;

namespace S2A.Services
{
    public static unsafe class Application
    {
        public static void Reset2() => LazyHostFile.CloseAll();   // harness only

        // harness: the block of Application.Register between "string index = ..." and SetRomFs, verbatim
        public static IStorage HarnessRegisterRomFs(string programDir)
        {
            string romfs = Path.Combine(programDir, "romfs");
            {
'''
RUNTIME_CONFIG = {'runtimeOptions': {'tfm': 'net10.0', 'framework': {'name': 'Microsoft.NETCore.App', 'version': '10.0.0'},
                                     'configProperties': {'System.Globalization.Invariant': True, 'System.GC.Server': False}}}


def fail(message):
    print(json.dumps({'result': 'failed', 'why': message}))
    sys.exit(1)


def between(text, start, end, include_end=False):
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b + (len(end) if include_end else 0)]


def patched_sources(checkout: Path, work: Path):
    pin = json.loads((ROOT / 'tools/s2arm_prototype/pin.json').read_text(encoding='utf-8'))['s2arm']['commit']
    listed = subprocess.run(['git', '-C', str(checkout), 'ls-tree', '-r', '--name-only', pin, 'compat/packages'], capture_output=True, text=True)
    if listed.returncode:
        fail(f'{checkout} does not hold the pinned S2Arm commit {pin}: {listed.stderr.strip()[-200:]}')
    libhac = [name for name in listed.stdout.split() if re.fullmatch(r'compat/packages/ryujinx\.libhac\.[0-9A-Za-z.-]+\.nupkg', name)]
    if len(libhac) != 1:
        fail(f'expected one LibHac package in compat/packages of the pinned commit: {libhac}')
    archive = subprocess.run(['git', '-C', str(checkout), 'archive', pin, *SOURCES, libhac[0]], capture_output=True)
    if archive.returncode:
        fail('git archive of the pinned sources failed: ' + archive.stderr.decode(errors='replace')[-200:])
    tree = work / 'tree'
    tree.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(tree, filter='data')
    subprocess.run(['git', 'init', '-q', str(tree)], check=True)
    applied = subprocess.run(['git', '-C', str(tree), 'apply', str(PATCH)], capture_output=True, text=True)
    if applied.returncode:
        fail('patch 0014 does not apply on the pinned sources: ' + applied.stderr[-300:])
    with zipfile.ZipFile(tree / libhac[0]) as package:
        dll = [name for name in package.namelist() if name.endswith('/LibHac.dll')]
        if not dll:
            fail('the LibHac package holds no LibHac.dll')
        (work / 'LibHac.dll').write_bytes(package.read(sorted(dll)[-1]))
    index = (tree / SOURCES[0]).read_text(encoding='utf-8')
    application = (tree / SOURCES[1]).read_text(encoding='utf-8')
    block = between(application, '                string index = Path.Combine(programDir, RomFsIndex.FileName);', '                device.Configuration.VirtualFileSystem.SetRomFs(pid, image);')
    from_directory = between(application, '        // 解开的 RomFS 目录 → RomFS 镜像', '            return builder.Build();\n        }\n', include_end=True)
    rest = application[application.index('    // 只读、按需打开的宿主文件'):]
    (work / 'RomFsIndex.cs').write_text(index, encoding='utf-8')
    (work / 'AppBlock.cs').write_text(WRAPPER + block + '                return image;\n            }\n        }\n\n' + from_directory + '    }\n\n' + rest, encoding='utf-8')
    return pin


def main(argv):
    if len(argv) not in (3, 5) or (len(argv) == 5 and argv[3] != '--perf'):
        print(__doc__)
        return 2
    tools, checkout = Path(argv[1]).resolve(), Path(argv[2]).resolve()
    dotnet, csc = tools / 'dotnet', tools / 'csc/csc.dll'
    references = sorted((tools / 'ref').glob('*.dll'))
    if not dotnet.is_file() or not csc.is_file() or not references:
        fail(f'{tools} is not a folder made by build-utils/s2arm/engine/dotnet_tools.py')
    environment = dict(os.environ, DOTNET_ROOT=str(tools), DOTNET_gcServer='0', DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        pin = patched_sources(checkout, work)
        sources = [str(work / 'RomFsIndex.cs'), str(work / 'AppBlock.cs')] + [str(path) for path in sorted(HARNESS.glob('*.cs'))]
        out = work / 'out'
        out.mkdir()
        common = [str(dotnet), 'exec', str(csc), '-nologo', '-unsafe', '-nullable:disable', '-langversion:preview', '-nowarn:CS1701',
                  *['-r:' + str(path) for path in references], '-r:' + str(work / 'LibHac.dll')]
        # 1. the engine's two sources alone, every warning shown: none may be in the patched code (CS0649: the test hooks of LazyHostFile, unset here)
        library = subprocess.run([*common, '-target:library', '-warn:9', '-out:' + str(out / 'lib.dll'), str(work / 'RomFsIndex.cs'), str(work / 'AppBlock.cs'),
                                  str(HARNESS / 'Stubs.cs')], capture_output=True, text=True, env=environment, timeout=900)
        warnings = [line for line in (library.stdout + library.stderr).splitlines() if ('warning' in line or 'error' in line) and 'CS0649' not in line]
        if library.returncode or warnings:
            fail('the patched sources do not compile cleanly: ' + ' | '.join(warnings)[-900:])
        # 2. the harness
        program = subprocess.run([*common, '-target:exe', '-nowarn:CS0649', '-out:' + str(out / 'harness.dll'), *sources], capture_output=True, text=True, env=environment, timeout=900)
        if program.returncode:
            fail('the harness does not compile: ' + (program.stdout + program.stderr)[-900:])
        (out / 'LibHac.dll').write_bytes((work / 'LibHac.dll').read_bytes())
        (out / 'harness.runtimeconfig.json').write_text(json.dumps(RUNTIME_CONFIG), encoding='utf-8')
        results, lines = {}, []
        for name, arguments in (('walk', ['{run}']), ('review', ['extra', '{run}'])):
            run = work / ('run_' + name)
            run.mkdir()
            done = subprocess.run([str(dotnet), 'exec', str(out / 'harness.dll'), *[a.replace('{run}', str(run)) for a in arguments]], capture_output=True, text=True, env=environment,
                                  timeout=1800, cwd=out)
            text = done.stdout
            match = re.search(r'^RESULT checks=(\d+) fails=(\d+)$', text, re.M)
            failed = [line for line in text.splitlines() if line.startswith('FAIL ')]
            if not match or done.returncode or failed or int(match.group(2)):
                print('\n'.join(failed)[-2000:] or text[-2000:] or done.stderr[-2000:])
                fail(f'the {name} program failed')
            results[name] = int(match.group(1))
        if len(argv) == 5:
            for mode in ('old', 'write', 'read'):
                pack = Path(argv[4]).resolve()
                if mode == 'write':
                    for leftover in pack.glob('romfs.s2aidx*'):
                        leftover.unlink()
                done = subprocess.run([str(dotnet), 'exec', str(out / 'harness.dll'), 'perf', str(pack), mode], capture_output=True, text=True, env=environment, timeout=1800, cwd=out)
                lines.append(done.stdout.strip().splitlines()[0] if done.stdout.strip() else done.stderr.strip()[-200:])
        print(json.dumps({'result': 'passed', 'checks': sum(results.values()), 'programs': results, 's2arm': pin, 'perf': lines}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
