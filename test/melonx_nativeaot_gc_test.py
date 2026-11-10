#!/usr/bin/env python3
"""The patched NativeAOT workstation GC route (adapt_nativeaot_gc_runtime, nativeaot-gc-rebuild, fetch_nativeaot_gc).

Usage: melonx_nativeaot_gc_test.py --prepared <Core 658 prepared MeloNX tree>
                                   --runtime-source <dotnet/runtime v10.0.0 tree holding src/coreclr/gc and
                                                     src/coreclr/nativeaot/Runtime (a sparse checkout is enough)>
                                   --packs <directory with ios-arm64.nupkg and iossimulator-arm64.nupkg, the
                                            Microsoft.NETCore.App.Runtime.NativeAOT.<rid> 10.0.0 packages>
Needs clang (arm64-apple-ios target), llvm-ar, llvm-ranlib and dotnet ($DOTNET). No macOS, no device.

Checks:
- source: the pinned gc.cpp / gcenv.ee.cpp bytes hold the race (workstation start check `!!bgc_thread`, the 20000 ms
  idle exit, bgc_thread set by bgc_thread_stub, NativeAOT CreateThread signalling before the start routine runs, the
  do_pre_gc stamp of the background slot), and the patch applies to them, changes exactly that check to
  `bgc_thread_running` and adds the marker, nothing else;
- marker: compiled for arm64-apple-ios it is a no-dead-strip local symbol (nativeaot_gc_archive.symbols);
- packs: the nupkgs and their libRuntime.WorkstationGC.a are the pinned bytes (81 Mach-O arm64 members, gcwks.cpp.o
  digest, platform); the archive reader agrees with llvm-ar's member list; a splice that replaces gcwks.cpp.o by an
  object without the GC's definitions is refused by compare(), one that puts the same object back is accepted;
- fetch: a template pin is refused; a filled pin with a synthetic artifact is accepted and places both libraries, a
  tampered artifact, library or pin is refused;
- adapter: applied to a copy of the prepared tree it changes only Ryujinx.Library.csproj, once, and the MSBuild target
  (run with stub ILCompiler items by dotnet msbuild) replaces the runtime pack's library by the patched one among the
  linker inputs, and fails for a missing pin digest, other patched bytes, a missing patched library, other runtime
  pack bytes, server GC, an unknown RuntimeIdentifier and a duplicated input.
Writes dist/melonx/nativeaot-gc-checks.json.
"""
import argparse
import collections
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import nativeaot_gc_archive as archive  # noqa: E402
import fetch_nativeaot_gc  # noqa: E402
import adapt_nativeaot_gc_runtime  # noqa: E402

PIN = json.loads((ROOT / 'build-utils/melonx/nativeaot-gc-rebuild.json').read_text())
TEMPLATE = ROOT / 'build-utils/melonx/nativeaot-gc-rebuild-pin.template.json'
DOTNET = os.environ.get('DOTNET', 'dotnet')
CSPROJ = 'src/Ryujinx.Library/Ryujinx.Library.csproj'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def refused(function, *args):
    try:
        function(*args)
    except (AssertionError, SystemExit, KeyError) as error:
        return str(error) or type(error).__name__
    return None


def check_source(runtime):
    gc = (runtime / 'src/coreclr/gc/gc.cpp').read_bytes()
    aot = (runtime / 'src/coreclr/nativeaot/Runtime/gcenv.ee.cpp').read_bytes()
    check(sha(gc) == PIN['sourceSha256']['src/coreclr/gc/gc.cpp'], 'gc.cpp is not the pinned v10.0.0 bytes')
    check(sha(aot) == PIN['sourceSha256']['src/coreclr/nativeaot/Runtime/gcenv.ee.cpp'], 'gcenv.ee.cpp differs')
    text, stub = gc.decode(), aot.decode()
    check(text.count('do_concurrent_p = (!!bgc_thread && commit_mark_array_bgc_init());') == 1, 'WKS start check')
    check('                                             20000,\n' in text, 'the 20 s workstation BGC thread wait')
    check(text.count('if (!keep_bgc_threads_p)') == 1 and 'bgc_thread_running = FALSE;\n                bgc_thread = 0;' in text,
          'the idle exit clears bgc_thread_running and bgc_thread')
    check('heap->bgc_thread = GCToEEInterface::GetThread();' in text, 'bgc_thread is set by the new thread')
    check('gh->bgc_thread_running = GCToEEInterface::CreateThread(gh->bgc_thread_stub, gh, true, ".NET BGC");' in text,
          'bgc_thread_running is set from CreateThread')
    check('last_bgc_info_index = !last_bgc_info_index;\n        last_bgc_info[last_bgc_info_index].index = settings.gc_index;' in text,
          'do_pre_gc stamps the next background slot when settings.concurrent')
    decision = text.index('keep_bgc_threads_p = TRUE;')
    pre_gc, start = text.index('        do_pre_gc();\n', decision), text.index('do_concurrent_p = (!!bgc_thread')
    check(decision < pre_gc < start, 'decision, then do_pre_gc, then the start check (the equal-index signature)')
    signal, routine = stub.index('pStartContext->m_ThreadStartedEvent.Set();\n\n            STRESS_LOG_RESERVE_MEM'), \
        stub.index('realStartRoutine(realContext);\n\n            return 0;\n        };\n\n    if (!PalStartBackgroundGCThread(threadStub, &threadStubArgs))')
    check(signal < routine, 'NativeAOT CreateThread signals before the start routine (bgc_thread_stub) runs')
    with tempfile.TemporaryDirectory() as temporary:
        tree = Path(temporary)
        (tree / 'src/coreclr/gc').mkdir(parents=True)
        (tree / 'src/coreclr/gc/gc.cpp').write_bytes(gc)
        patch = ROOT / PIN['patch']
        check(sha(patch.read_bytes()) == PIN['patchSha256'], 'the patch differs from its pin')
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=tree, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=tree, check=True)
        patched = (tree / 'src/coreclr/gc/gc.cpp').read_text()
    check(patched.count('do_concurrent_p = (bgc_thread_running && commit_mark_array_bgc_init());') == 1 and
          '(!!bgc_thread &&' not in patched, 'the patch makes the upstream change')
    check(patched.count(PIN['marker']) == 1, 'the patch adds the marker once')
    before, after = collections.Counter(text.splitlines()), collections.Counter(patched.splitlines())
    removed, added = list((before - after).elements()), list((after - before).elements())
    check(removed == ['            do_concurrent_p = (!!bgc_thread && commit_mark_array_bgc_init());'],
          f'the patch removes only the start check: {removed}')
    check(len(added) == 8 and sum('rewindbox_gc_patch_marker' in line for line in added) == 1,
          f'the patch adds the fixed check and the marker block only: {added}')


TRIPLES = {'ios-arm64': 'arm64-apple-ios12.2', 'iossimulator-arm64': 'arm64-apple-ios14.0-simulator'}


def marker_object(directory, name='gcwks.cpp.o', rid='ios-arm64'):
    source = directory / 'marker.cpp'
    source.write_text('namespace WKS {\n__attribute__((used)) static const char rewindbox_gc_patch_marker[] =\n'
                      f'    "{PIN["marker"]}";\nint rewindbox_probe(int x) {{ return x + 1; }}\n}}\n')
    target = directory / name
    subprocess.run(['clang++', '-target', TRIPLES[rid], '-O2', '-Wall', '-Werror', '-c', str(source),
                    '-o', str(target)], check=True)
    return target


def check_packs(packs, scratch):
    libraries = {}
    for rid, pack in PIN['runtimePacks'].items():
        nupkg = (packs / f'{rid}.nupkg').read_bytes()
        check(sha(nupkg) == pack['nupkgSha256'], f'{rid}: nupkg digest')
        with zipfile.ZipFile(packs / f'{rid}.nupkg') as content:
            data = content.read(f'runtimes/{rid}/native/{PIN["library"]}')
            nuspec = next(content.read(n).decode() for n in content.namelist() if n.endswith('.nuspec'))
        check('commit="' + pack['sourceCommit'].split()[-1] + '"' in nuspec, f'{rid}: pack source commit')
        check(sha(data) == pack['librarySha256'] and len(data) == pack['libraryBytes'], f'{rid}: library digest')
        objects = archive.objects(data)
        check(len(objects) == pack['members'], f'{rid}: member count')
        check(all(archive.macho(body)['cpu'] == 'arm64' and archive.macho(body)['buildVersion']['platform'] ==
                  pack['platform'] for body in objects.values()), f'{rid}: every member is Mach-O arm64 {pack["platform"]}')
        check(sha(objects[PIN['member']]) == pack['memberSha256'], f'{rid}: gcwks.cpp.o digest')
        check(PIN['marker'].encode() not in data, f'{rid}: no marker in the runtime pack')
        library = scratch / f'{rid}.a'
        library.write_bytes(data)
        listed = subprocess.run(['llvm-ar', 't', str(library)], capture_output=True, text=True, check=True).stdout.split()
        check(listed == list(objects), f'{rid}: the reader agrees with llvm-ar')
        table = archive.symbol_table(data)
        check(set(table.values()) <= set(objects) and
              archive.symbols(objects[PIN['member']])['strong'] <= {s for s, m in table.items() if m == PIN['member']},
              f'{rid}: the symbol table lists every strong definition of gcwks.cpp.o')
        libraries[rid] = data
    marker = archive.symbols(marker_object(scratch).read_bytes())
    check(any('rewindbox_gc_patch_marker' in name for name in marker['noDeadStripLocal']),
          'the marker compiles to a no-dead-strip symbol for arm64-apple-ios')
    return libraries


def splice(scratch, official, member_path, name):
    library = scratch / name
    library.write_bytes(official)
    subprocess.run(['llvm-ar', 'r', str(library), member_path.name], cwd=member_path.parent, check=True)
    subprocess.run(['llvm-ranlib', str(library)], check=True)
    return library.read_bytes()


def check_splice(libraries, scratch):
    member = PIN['member']
    same_dir, wrong_dir = scratch / 'same', scratch / 'wrong'
    same_dir.mkdir()
    wrong_dir.mkdir()
    official = libraries['ios-arm64']
    (same_dir / member).write_bytes(archive.objects(official)[member])
    same = splice(scratch, official, same_dir / member, 'same.a')
    check(archive.compare(official, same, member) == [], 'putting the same GC object back is accepted')
    wrong = splice(scratch, official, marker_object(wrong_dir), 'wrong.a')
    problems = archive.compare(official, wrong, member)
    check(any('strong definitions differ' in p for p in problems), f'an object without the GC is refused: {problems}')
    check(not any(p.startswith('member differs') for p in problems), 'the other members stay identical')
    names = [n for _, n, _ in archive.members(wrong) if not n.startswith('__.SYMDEF')]
    check(names == list(archive.objects(official)), 'ar r keeps the member order')
    synthetic = {}
    for rid, data in libraries.items():
        directory = scratch / f'marker-{rid}'
        directory.mkdir()
        synthetic[rid] = splice(scratch, data, marker_object(directory, rid=rid), f'synthetic-{rid}.a')
    return synthetic


def check_fetch(synthetic, scratch):
    check('incomplete' in (refused(fetch_nativeaot_gc.load_pins, ROOT / 'build-utils/melonx/nativeaot-gc-rebuild.json',
                                   TEMPLATE) or ''), 'the template pin is refused')
    check('missing' in (refused(fetch_nativeaot_gc.load_pins, ROOT / 'build-utils/melonx/nativeaot-gc-rebuild.json',
                                scratch / 'absent.json') or ''), 'an absent pin is refused')
    artifact = scratch / 'artifact.zip'
    identity = {'pin': PIN, 'patchSha256': PIN['patchSha256'],
                'libraries': {rid: {'patched': {'sha256': sha(data)}} for rid, data in synthetic.items()}}
    with zipfile.ZipFile(artifact, 'w') as content:
        content.writestr('identity.json', json.dumps(identity))
        for rid, data in synthetic.items():
            content.writestr(f'{rid}/{PIN["library"]}', data)
    pin = json.loads(TEMPLATE.read_text())
    pin.update(run=1, job=2, headSha='0' * 40, artifact=3, artifactName='synthetic', artifactBytes=artifact.stat().st_size,
               artifactDigest='sha256:' + sha(artifact.read_bytes()))
    for rid, data in synthetic.items():
        pin['libraries'][rid].update(sha256=sha(data), bytes=len(data))
    pin_path = scratch / 'pin.json'
    pin_path.write_text(json.dumps(pin))
    source_pin = ROOT / 'build-utils/melonx/nativeaot-gc-rebuild.json'
    prepared, work = scratch / 'prepared', scratch / 'work'
    fetch_nativeaot_gc.fetch(prepared, artifact, source_pin, pin_path, work)
    for rid, data in synthetic.items():
        placed = prepared / fetch_nativeaot_gc.DESTINATION / rid / PIN['library']
        check(placed.read_bytes() == data, f'{rid}: the pinned library is placed')
    receipt = json.loads((work / 'identity.json').read_text())
    check(set(receipt['libraries']) == set(PIN['runtimePacks']), 'the fetch receipt names both libraries')
    tampered = scratch / 'tampered.zip'
    tampered.write_bytes(artifact.read_bytes() + b'\0')
    check(refused(fetch_nativeaot_gc.fetch, scratch / 'p2', tampered, source_pin, pin_path, scratch / 'w2') is not None
          and not (scratch / 'p2').exists(), 'a tampered artifact is refused before anything is written')
    for mutate, label in ((lambda p: p['libraries']['ios-arm64'].update(sha256='1' * 64), 'other library digest'),
                          (lambda p: p.update(revision='0' * 40), 'other runtime revision'),
                          (lambda p: p['libraries']['ios-arm64'].update(officialSha256='2' * 64), 'other runtime pack')):
        other = copy.deepcopy(pin)
        mutate(other)
        other_path = scratch / 'other-pin.json'
        other_path.write_text(json.dumps(other))
        check(refused(fetch_nativeaot_gc.fetch, scratch / 'p3', artifact, source_pin, other_path, scratch / 'w3')
              is not None and not (scratch / 'p3').exists(), 'refused: ' + label)
    official_source = scratch / 'official-source-pin.json'
    official = json.loads(source_pin.read_text())
    official['runtimePacks']['ios-arm64']['members'] = 80
    official_source.write_text(json.dumps(official))
    check(refused(fetch_nativeaot_gc.fetch, scratch / 'p4', artifact, official_source, pin_path, scratch / 'w4')
          is not None and not (scratch / 'p4').exists(), 'refused: a library without the pack member list')


STUB = '''<Project>
  <PropertyGroup>
    <RuntimeIdentifier Condition=" '$(RuntimeIdentifier)' == '' ">ios-arm64</RuntimeIdentifier>
    <IlcSdkPath>{pack}/</IlcSdkPath>
    <LinkLog>{log}</LinkLog>
  </PropertyGroup>
  <!-- The ILCompiler's SetupOSSpecificProps (Microsoft.NETCore.Native.Unix.targets 10.0.0), reduced to the items the
       RewindBox target reads and edits. -->
  <Target Name="SetupOSSpecificProps">
    <PropertyGroup>
      <FullRuntimeName>libRuntime.WorkstationGC</FullRuntimeName>
      <FullRuntimeName Condition=" '$(ServerGarbageCollection)' == 'true' ">libRuntime.ServerGC</FullRuntimeName>
    </PropertyGroup>
    <ItemGroup>
      <NativeLibrary Include="$(IlcSdkPath)libSystem.Native.a" />
      <NativeLibrary Include="$(IlcSdkPath)libbootstrapperdll.o" />
      <NativeLibrary Include="$(IlcSdkPath)$(FullRuntimeName).a" />
      <NativeLibrary Include="$(IlcSdkPath)$(FullRuntimeName).a" Condition=" '$(Duplicate)' == 'true' " />
      <NativeLibrary Include="$(IlcSdkPath)libeventpipe-disabled.a" />
      <NativeLibrary Include="$(IlcSdkPath)libaotminipal.a" />
      <LinkerArg Include="-gz=zlib" />
      <LinkerArg Include="@(NativeLibrary)" />
      <LinkerArg Include="-isysroot &quot;/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk&quot;" />
      <LinkerArg Include="-Wl,-install_name,&quot;@rpath/Ryujinx.Library.dylib&quot;" />
    </ItemGroup>
  </Target>
{target}
  <Target Name="Link" DependsOnTargets="SetupOSSpecificProps">
    <WriteLinesToFile File="$(LinkLog)" Lines="@(LinkerArg)" Overwrite="true" />
    <WriteLinesToFile File="$(LinkLog).native" Lines="@(NativeLibrary)" Overwrite="true" />
  </Target>
'''


def check_adapter(prepared, synthetic, scratch):
    tree = scratch / 'tree'
    (tree / 'src/Ryujinx.Library').mkdir(parents=True)
    original = (prepared / CSPROJ).read_bytes()
    check(sha(original) == adapt_nativeaot_gc_runtime.BASELINE[CSPROJ], 'the prepared project is the Core 658 one')
    check(adapt_nativeaot_gc_runtime.OFFICIAL == {rid: p['librarySha256'] for rid, p in PIN['runtimePacks'].items()},
          'the adapter and the rebuild pin name the same runtime pack libraries')
    (tree / CSPROJ).write_bytes(original)
    check(adapt_nativeaot_gc_runtime.apply(tree) == [CSPROJ], 'the adapter edits only the project')
    adapted = (tree / CSPROJ).read_text()
    check(adapted.count('<Target Name="RewindBoxPatchedNativeAotGc" AfterTargets="SetupOSSpecificProps">') == 1 and
          adapted.endswith('</Project>\n') and adapted.count('</Project>') == 1, 'one target, one project end')
    check(adapted.replace(adapt_nativeaot_gc_runtime.TARGET, '</Project>') == original.decode(),
          'nothing else in the project changes')
    check(refused(adapt_nativeaot_gc_runtime.apply, tree) is not None, 'a second application is refused')
    start = adapted.index('  <!-- RewindBox (adapt_nativeaot_gc_runtime)')
    target = adapted[start:adapted.rindex('</Project>')]

    pack, patched_dir = scratch / 'pack', scratch / 'patched'
    for rid in PIN['runtimePacks']:
        (patched_dir / rid).mkdir(parents=True)
    pack.mkdir()
    official = {rid: (scratch / f'{rid}.a').read_bytes() for rid in PIN['runtimePacks']}

    def link(name, rid='ios-arm64', sha256=None, official_bytes=None, patched_bytes=None, extra=()):
        (pack / PIN['library']).write_bytes(official_bytes if official_bytes is not None else official[rid])
        for file in ('libSystem.Native.a', 'libbootstrapperdll.o', 'libeventpipe-disabled.a', 'libaotminipal.a',
                     'libRuntime.ServerGC.a'):
            (pack / file).write_bytes(b'stub')
        library = patched_dir / rid / PIN['library']
        library.parent.mkdir(parents=True, exist_ok=True)
        if patched_bytes is None:
            library.unlink(missing_ok=True)
        else:
            library.write_bytes(patched_bytes)
        log = scratch / f'{name}.log'
        project = scratch / f'{name}.proj'
        project.write_text(STUB.format(pack=pack, log=log, target=target) + '</Project>\n')
        args = [DOTNET, 'msbuild', str(project), '-t:Link', '-nologo', '-v:m', f'-p:RuntimeIdentifier={rid}',
                f'-p:RewindBoxNativeAotGcDirectory={patched_dir}/', *extra]
        if sha256 is not None:
            args.append(f'-p:RewindBoxNativeAotGcSha256={sha256}')
        result = subprocess.run(args, capture_output=True, text=True)
        lines = log.read_text().splitlines() if result.returncode == 0 else None
        return result.returncode, result.stdout + result.stderr, lines

    good = synthetic['ios-arm64']
    code, output, lines = link('ok', sha256=sha(good), patched_bytes=good)
    check(code == 0, 'the target links the pinned library: ' + output[-800:])
    patched_full = str((patched_dir / 'ios-arm64' / PIN['library']).resolve())
    check(patched_full in lines and str(pack / PIN['library']) not in lines and
          sum(line.endswith(PIN['library']) for line in lines) == 1, f'one GC library among the linker inputs: {lines}')
    expected = ['-gz=zlib', str(pack / 'libSystem.Native.a'), str(pack / 'libbootstrapperdll.o'), patched_full,
                str(pack / 'libeventpipe-disabled.a'), str(pack / 'libaotminipal.a'),
                '-isysroot "/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk"',
                '-Wl,-install_name,"@rpath/Ryujinx.Library.dylib"']
    check(lines == expected, f'the other linker inputs are kept, the GC library in place: {lines}')
    native = (scratch / 'ok.log.native').read_text().splitlines()
    check(native == expected[1:6], f'NativeLibrary keeps its order: {native}')
    check(patched_full in native and str(pack / PIN['library']) not in native, 'NativeLibrary names the patched library')
    check('RewindBox NativeAOT GC: linking' in output and sha(good) in output.lower(), 'the build log names the library')
    simulator = synthetic['iossimulator-arm64']
    code, output, _ = link('simulator', rid='iossimulator-arm64', sha256=sha(simulator), patched_bytes=simulator)
    check(code == 0, 'the simulator library links too: ' + output[-500:])
    failures = {
        'no pin digest': link('nopin', patched_bytes=good),
        'other patched bytes': link('otherpatched', sha256=sha(good), patched_bytes=good + b'\0'),
        'missing patched library': link('missing', sha256=sha(good)),
        'other runtime pack': link('otherpack', sha256=sha(good), patched_bytes=good, official_bytes=official['ios-arm64'] + b'\0'),
        'simulator pack for device': link('swapped', sha256=sha(good), patched_bytes=good, official_bytes=official['iossimulator-arm64']),
        'server GC': link('server', sha256=sha(good), patched_bytes=good, extra=['-p:ServerGarbageCollection=true']),
        'unknown runtime identifier': link('maccatalyst', rid='maccatalyst-arm64', sha256=sha(good), patched_bytes=good,
                                           official_bytes=official['ios-arm64']),
        'duplicated input': link('duplicate', sha256=sha(good), patched_bytes=good, extra=['-p:Duplicate=true']),
    }
    for label, (code, output, _) in failures.items():
        check(code != 0 and 'RewindBox NativeAOT GC:' in output, f'refused: {label}: {output[-400:]}')
    return {label: next((line.strip() for line in output.splitlines() if 'RewindBox NativeAOT GC:' in line), '')[:240]
            for label, (code, output, _) in failures.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', required=True, type=Path)
    parser.add_argument('--runtime-source', required=True, type=Path)
    parser.add_argument('--packs', required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='melonx-nativeaot-gc-') as temporary:
        scratch = Path(temporary)
        check_source(args.runtime_source)
        libraries = check_packs(args.packs, scratch)
        synthetic = check_splice(libraries, scratch)
        check_fetch(synthetic, scratch)
        refusals = check_adapter(args.prepared, synthetic, scratch)
    output = ROOT / 'dist/melonx/nativeaot-gc-checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'checks': checks, 'result': 'passed', 'refusals': refusals,
                                  'csprojBaseline': adapt_nativeaot_gc_runtime.BASELINE[CSPROJ],
                                  'patchSha256': PIN['patchSha256']}, indent=2) + '\n')
    print(f'{checks} checks passed')


if __name__ == '__main__':
    main()
