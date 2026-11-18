#!/usr/bin/env python3
"""adapt_shader_load_binary_release on the final preparation, against its predecessor as control.

Usage: melonx_shader_load_binary_release_test.py <predecessor preparation> --candidate-source <final preparation>

Static: only ParallelDiskCacheLoader.cs and DiskCacheHostStorage.cs change, their replacements applied once to the
control give the final files and reverse to them; the loader keeps no host code for a program created from the host
cache, keeps it for a translated one, and reads the kept-out code back before the rebuild clears the files; the
storage's read back opens both host files once and reads only (no write, no clear). Built: the production
Ryujinx.Graphics.Gpu of the candidate. Executed: the production loader (control and candidate) against the controlled
boundaries of test/melonx_shader_loader_lifetime (copied in test/melonx_shader_load_binary_release, with a host cache
that makes a program's host code again from its index): 120 programs of 1 MiB from the host cache leave about 120 MiB
reachable at the end of the load in the control and about none in the candidate; a corrupted-file rebuild writes every
program with the same host code as the control (sha256 per program), the read back before the files are cleared; a
code that cannot be read back is written without host code. No device. Writes dist/melonx/shader-load-binary-release-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, postimage, use_authenticated_libhac_feed  # noqa: E402
import adapt_shader_load_binary_release as adapter  # noqa: E402

FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
_HOLD = []
if '--cached-stages' in sys.argv:
    # Compare the two production Release assemblies on an authenticated 779 preparation and its candidate.
    import xml.etree.ElementTree as ET
    import statistics
    import adapt_cached_shader_stages as stages
    before = Path(sys.argv[1]).resolve()
    assert all(hashlib.sha256((before / n).read_bytes()).hexdigest() == h for n, h in stages.BASELINE.items())
    dotnet = os.environ.get('DOTNET', 'dotnet')
    probe = ROOT / 'test/melonx_shader_load_binary_release/CacheStages.cs'
    asset = 'src/Ryujinx.Graphics.Vulkan/Shaders/SpirvBinaries/'
    results = []
    with tempfile.TemporaryDirectory(prefix='melonx-cache-stages-') as directory:
        for name, tree in [('control', before), ('candidate', FINAL_SOURCE)]:
            work = Path(directory) / name
            work.mkdir()
            shutil.copyfile(probe, work / probe.name)
            project = ET.Element('Project', Sdk='Microsoft.NET.Sdk')
            props = ET.SubElement(project, 'PropertyGroup')
            for prop, value in dict(OutputType='Exe', TargetFramework='net10.0', ImplicitUsings='enable',
                                    NuGetAudit='false', DefineConstants='CANDIDATE' if name == 'candidate' else '').items():
                ET.SubElement(props, prop).text = value
            refs = ET.SubElement(project, 'ItemGroup')
            for dep in ('Ryujinx.Graphics.Vulkan', 'Ryujinx.Graphics.Gpu'):
                ET.SubElement(refs, 'ProjectReference', Include=str(tree / 'src' / dep / (dep + '.csproj')))
            csproj = work / 'probe.csproj'
            ET.ElementTree(project).write(csproj)
            shutil.copyfile(tree / 'global.json', work / 'global.json')
            feed = os.environ.get('MELONX_LOCAL_NUGET_CONFIG')
            restore = [dotnet, 'restore', str(csproj), '-m:1', '-p:NuGetAudit=false']
            if feed: restore.extend(['--configfile', feed])
            subprocess.run(restore, cwd=work, check=True)
            subprocess.run([dotnet, 'build', str(csproj), '-c', 'Release', '--no-restore', '-m:1'], cwd=work, check=True)
        # Both libraries are built before timing. Alternate the process order to limit warm-up bias.
        trials = {'control': [], 'candidate': []}
        for name in ('control', 'candidate', 'candidate', 'control'):
            work = Path(directory) / name
            run = subprocess.check_output([dotnet, str(work / 'bin/Release/net10.0/probe.dll'),
                str(before / (asset + 'ColorBlitVertex.spv')), str(before / (asset + 'ColorBlitFragment.spv')),
                str(before / (asset + 'ChangeBufferStride.spv'))],
                cwd=work, text=True, env=dict(os.environ, DOTNET_TieredCompilation='0'))
            trials[name].append(json.loads(run.strip()))
        for name in ('control', 'candidate'):
            first, second = trials[name]
            assert {k: v for k, v in first.items() if k != 'runs'} == {k: v for k, v in second.items() if k != 'runs'}
            results.append({**first, 'runs': first['runs'] + second['runs']})
    old, new = results
    assert all(old[key] == new[key] for key in ('digest', 'original', 'textIdentity', 'computeIdentity', 'records'))
    assert [r['checksum'] for r in old['runs']] == [r['checksum'] for r in new['runs']]
    assert max(r['allocated'] for r in new['runs']) < min(r['allocated'] for r in old['runs']) // 100
    print(json.dumps(dict(result='passed', results=results, medianMs=[statistics.median(r['ms'] for r in x['runs']) for x in results])))
    sys.exit(0)

SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_shader_load_binary_release', _HOLD)
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_shader_load_binary_release'
FILES = json.loads((ROOT / 'test/melonx_shader_loader_lifetime/baseline_sources.json').read_text())
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


check(FINAL_PREPARATION, 'the candidate is the final preparation containing the adapter')
for name, expected in adapter.BASELINE.items():
    check(sha(SOURCE / name) == expected, 'control is the predecessor preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-shader-load-') as temporary:
    temporary = Path(temporary).resolve()
    work = temporary / 'candidate-tree'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)
    changed = adapter.apply(work)
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(adapter.BASELINE), 'the adapter changes its two files only')
    expected = temporary / 'postimage'
    postimage('adapt_shader_load_binary_release', FINAL_SOURCE, expected)
    texts = {}
    for name in adapter.BASELINE:
        final = (expected / name).read_text(encoding='utf-8-sig')
        check((work / name).read_text(encoding='utf-8-sig') == final, 'the control plus the adapter matches its exact postimage: ' + name)
        control_text = (SOURCE / name).read_text(encoding='utf-8-sig')
        reverted = final
        for file, old, new in reversed(adapter.PAIRS):
            if file == name:
                check(reverted.count(new) == 1 and control_text.count(old) == 1, 'each replacement once: ' + name)
                reverted = reverted.replace(new, old)
        check(reverted == control_text, 'the replacements reverse to the control: ' + name)
        texts[name] = final
    loader, storage = texts[adapter.LOADER], texts[adapter.STORAGE]
    check('byte[] binaryCode = entry.IsBinary ? null : entry.BinaryCode ?? entry.CachedProgram.HostProgram.GetBinary();' in loader and
          loader.index('RestoreReleasedHostCode();') < loader.index('_hostStorage.ClearSharedCache();') <
          loader.index('_hostStorage.ClearHostCache(_context);'),
          'no host code kept for a cached program; read back before the rebuild clears the files')
    method = storage[storage.index('public byte[][] ReadHostCodesForRebuild('):storage.index('private (byte[], CachedShaderStage[]) ReadHostCode(')]
    check(method.count('writable: false') == 2 and 'writable: true' not in method and 'Clear' not in method and
          'Write' not in method and 'BinarySerializer.ReadCompressed(dataFileStream, hostCode);' in method,
          'the read back opens both host files once, read-only')

    result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=3600, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Gpu builds with the adapter')
    shutil.rmtree(work)

    for variant, tree in (('control', SOURCE), ('candidate', FINAL_SOURCE)):
        run_dir = temporary / variant
        for relative in FILES:
            target = run_dir / 'source' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tree / relative, target)
            if relative == adapter.LOADER:
                code = target.read_text()
                entry = 'private void ProcessAsyncQueue(object state)\n        {'
                assert code.count(entry) == 1
                code = code.replace(entry, entry + '\n            System.Threading.Interlocked.Increment(ref global::Program.WorkerStarts);')
                starts = [line for line in code.splitlines() if '.Start(_cancellationToken);' in line]
                assert len(starts) == 1
                target.write_text(code.replace(starts[0], '                global::Program.BeforeStart();\n' + starts[0]))
        (run_dir / 'global.json').write_text('{"sdk":{"version":"10.0.100","rollForward":"disable"}}')
        (run_dir / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        for name in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(FIXTURE / name, run_dir / name)
        includes = ''.join(f'<Compile Include="source/{relative}" />' for relative in FILES)
        (run_dir / 'Check.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<EnableDefaultCompileItems>false</EnableDefaultCompileItems><Nullable>disable</Nullable><ServerGarbageCollection>false</ServerGarbageCollection>
<NoWarn>CS0649;CS9113;CS0162</NoWarn><DefineConstants>{'CANDIDATE' if variant == 'candidate' else ''}</DefineConstants></PropertyGroup>
<ItemGroup>{includes}<Compile Include="Program.cs"/><Compile Include="Boundaries.cs"/></ItemGroup>
</Project>''')
        build = subprocess.run([DOTNET, 'build', 'Check.csproj', '-c', 'Release', '--nologo', '-v:q'], cwd=run_dir, env=environment,
                               text=True, capture_output=True, timeout=600)
        if build.returncode:
            print(build.stdout[-4000:], build.stderr[-2000:], flush=True)
        check(build.returncode == 0, variant + ': the production loader builds against the boundaries')
        run = subprocess.run([DOTNET, 'bin/Release/net10.0/Check.dll'], cwd=run_dir, env=environment, text=True,
                             capture_output=True, timeout=300)
        if run.returncode:
            print(run.stdout[-3000:], run.stderr[-3000:], flush=True)
        check(run.returncode == 0, variant + ': the fixture runs')
        reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])['report']

control, candidate = reports['control'], reports['candidate']
check(control['memoryListedCodes'] == 120 and control['memoryRetainedMiB'] >= 115,
      'control: the 120 MiB of host code stay reachable until the load ends: ' + str(control))
check(candidate['memoryListedCodes'] == 0 and candidate['memoryRetainedMiB'] <= 8,
      'candidate: no host code reachable at the end of the load: ' + str(candidate))
check(control['rebuildReadBackCalls'] == 0 and candidate['rebuildReadBackCalls'] == 1 and candidate['rebuildReadBackPrograms'] == 8 and
      candidate['rebuildClearsBeforeReadBack'] == 0, 'the rebuild reads the 8 codes back once, before any clear: ' + str(candidate))
check(control['missingWritten'] == 'code,code,code,code,code,code,code,code' and
      candidate['missingWritten'] == 'code,code,code,none,code,code,code,code', 'a code that cannot be read back is written without host code')

inputs = ['build-utils/melonx/adapt_shader_load_binary_release.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_adapter_control.py',
          'test/melonx_shader_load_binary_release_test.py', 'test/melonx_shader_load_binary_release/Program.cs',
          'test/melonx_shader_load_binary_release/Boundaries.cs', 'test/melonx_shader_loader_lifetime/baseline_sources.json']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl',
               postimages={p: sha(FINAL_SOURCE / p) for p in adapter.BASELINE}, sdk=sdk, reports=reports,
               shaderLoadBinaryRelease=dict(executed=True, controlRetainedMiB=control['memoryRetainedMiB'],
                                            candidateRetainedMiB=candidate['memoryRetainedMiB']),
               physicalDeviceTested=False, productionGpuAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Host CoreCLR on Linux; the loader runs against controlled storage, renderer and translator boundaries; '
                          'the sizes on a device are those of its cache (no device measurement)')
if FINAL_PREPARATION and 'ArraySegment<byte> BinarySegment' in (FINAL_SOURCE / 'src/Ryujinx.Graphics.GAL/ShaderSource.cs').read_text():
    import adapt_cached_shader_stages as stages
    prior, bound = control_source(FINAL_SOURCE, 'adapt_cached_shader_stages', _HOLD)
    assert bound
    run = subprocess.run([sys.executable, __file__, str(prior), '--candidate-source', str(FINAL_SOURCE), '--cached-stages'],
                         check=True, capture_output=True, text=True)
    for field in ('emptyWorkerStarts', 'warmWorkerStarts', 'cancelledWorkerStarts'):
        check(control[field] == 8 and candidate[field] == 0, field + ': workers start only for guest work')
    check(control['guestWorkerStarts'] == candidate['guestWorkerStarts'] == 8, 'cold translation executes with all eight workers')
    receipt['cachedStages'] = json.loads(run.stdout.splitlines()[-1])
    receipt['postimages'].update({p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in stages.BASELINE})
    for p in ('build-utils/melonx/adapt_cached_shader_stages.py', 'test/melonx_shader_load_binary_release/CacheStages.cs'):
        receipt['inputs'][p] = hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
receipt['checks'] = checks
out = ROOT / 'dist/melonx/shader-load-binary-release-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, control=control, candidate=candidate)))
