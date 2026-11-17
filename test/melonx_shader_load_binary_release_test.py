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
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
import adapt_shader_load_binary_release as adapter  # noqa: E402

FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
_HOLD = []
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
    texts = {}
    for name in adapter.BASELINE:
        final = (FINAL_SOURCE / name).read_text(encoding='utf-8-sig')
        check((work / name).read_text(encoding='utf-8-sig') == final, 'the control plus the adapter is the final file: ' + name)
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
out = ROOT / 'dist/melonx/shader-load-binary-release-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, control=control, candidate=candidate)))
