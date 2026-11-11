#!/usr/bin/env python3
"""Compare the whole production timer manager, including its actual worker.

Host time and precise sleep events are controlled boundaries. No timer-manager
statement is replaced in either compiled version. Direct list checks exercise
captured identity; the real worker also runs cancellation/rearm/rollover cases.

Core gate form (Core 733): melonx_kernel_timer_allocations_test.py <delivered prepared tree> --candidate-source <final
preparation>. adapt_host_thread_class adds one statement to the worker's body (the class request, first thing). The
delivered timer manager and the final one are compiled whole with the same fixture and run the same cases: the final
file is the delivered one plus that statement, its functional digest is the delivered one's, and it allocates nothing
per arm or cancellation either. The helper it calls is a counting double here (its own gate is host-thread-class).
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_kernel_timer_allocations import apply

FILE = 'src/Ryujinx.HLE/HOS/Kernel/Common/KTimeManager.cs'
SUPPORT = ['src/Ryujinx.HLE/HOS/Kernel/Common/IKFutureSchedulerObject.cs',
           'src/Ryujinx.Common/PreciseSleep/IPreciseSleepEvent.cs']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())


def run_fixture(work, variant):
    (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit>
</PropertyGroup><ItemGroup><Compile Remove="source/**/*.cs" /></ItemGroup></Project>''')
    (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
    environment = os.environ.copy()
    environment.update(DOTNET_TieredCompilation='0', DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
    result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work), '-c', 'Release', '-v', 'q', '--', variant],
                            cwd=work, env=environment, capture_output=True, text=True, timeout=600)
    if result.returncode:
        print(result.stdout + result.stderr)
        result.check_returncode()
    return json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))


if '--candidate-source' in sys.argv:
    # Core gate form: the delivered timer manager against the final preparation's.
    sys.path.insert(0, str(ROOT / 'test'))
    import adapt_host_thread_class as thread_class
    FINAL = Path(sys.argv[sys.argv.index('--candidate-source') + 1]).resolve()
    delivered, final = (SOURCE / FILE).read_text(encoding='utf-8-sig'), (FINAL / FILE).read_text(encoding='utf-8-sig')
    pairs = [(old, new) for name, old, new in thread_class.PAIRS if name == FILE]
    assert len(pairs) == 1 and delivered.count(pairs[0][0]) == 1 and delivered.replace(*pairs[0]) == final, \
        'the final timer manager is the delivered one plus the class request'
    assert final.count(thread_class.CALL) == 1 and 'HostThreadClass' not in delivered
    for path in SUPPORT:
        assert digest(SOURCE / path) == digest(FINAL / path), 'support file differs: ' + path
    reports = {}
    with tempfile.TemporaryDirectory(prefix='melonx-kernel-timer-') as temporary:
        for side, tree in (('delivered', SOURCE), ('final', FINAL)):
            work = Path(temporary).resolve() / side
            work.mkdir()
            shutil.copyfile(tree / FILE, work / 'KTimeManager.cs')
            for relative in SUPPORT:
                shutil.copyfile(tree / relative, work / Path(relative).name)
            shutil.copyfile(ROOT / 'test/melonx_kernel_timer_allocations/Program.cs', work / 'Program.cs')
            (work / 'HostThreadClass.cs').write_text(
                'namespace Ryujinx.Common\n{\n    public static class HostThreadClass\n    {\n        public static int Requests;\n'
                '        public static bool RaiseCurrentThread() { System.Threading.Interlocked.Increment(ref Requests); return false; }\n    }\n}\n')
            reports[side] = run_fixture(work, 'candidate')
    d, f = reports['delivered'], reports['final']
    assert f['functionalDigest'] == d['functionalDigest'], 'the final timer manager behaves as the delivered one'
    assert f['allocatedBytes'] == d['allocatedBytes'] == 0 and f['waitingSlotBytes'] == d['waitingSlotBytes'] == 32
    for report in reports.values():
        assert len(report['cancellation']) == 24 and all(item['allocatedBytes'] == 0 for item in report['cancellation'])
    assert f['checks'] == d['checks'] and f['scenarios'] == d['scenarios']
    report = dict(result='passed', finalPreparationBound=True, sourceKind='deliveredPreparedWithFinalCandidate', physicalDeviceTested=False,
                  productionTimerWorkerExecuted=True, sameFunctionalDigest=True, checks=f['checks'], scenarios=f['scenarios'],
                  reports=reports, sdk=pin['dotnet'], tieredCompilation=False,
                  boundaries='controlled clock, precise sleep event and kernel lock container; the class request is a counting double',
                  preimages={FILE: digest(SOURCE / FILE)}, postimages={FILE: digest(FINAL / FILE)},
                  supportInputs={path: digest(FINAL / path) for path in SUPPORT},
                  inputs={str(path.relative_to(ROOT)): digest(path) for path in [
                      ROOT / 'build-utils/melonx/adapt_host_thread_class.py', Path(__file__),
                      ROOT / 'test/melonx_kernel_timer_allocations/Program.cs']})
    output = ROOT / 'dist/melonx/kernel-timer-allocations-checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(result='passed', checks=f['checks'], scenarios=f['scenarios'])))
    raise SystemExit(0)

CORE84_ADAPTER_BLOB = 'fb98972df6ff638638a041eec45ac6b790b26ea0'
historical_adapter = subprocess.check_output(['git', '-C', str(ROOT), 'cat-file', 'blob', CORE84_ADAPTER_BLOB])
assert hashlib.sha1(b'blob ' + str(len(historical_adapter)).encode() + b'\0' + historical_adapter).hexdigest() == CORE84_ADAPTER_BLOB
historical_namespace = {}
exec(compile(historical_adapter, 'core84/adapt_kernel_timer_allocations.py', 'exec'), historical_namespace)
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == pin['revision']
assert not subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--', FILE, *SUPPORT], text=True).strip()
reports, postimages = {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-kernel-timer-') as temporary:
    for variant in ('control', 'core84', 'candidate'):
        work = Path(temporary) / variant
        source = work / 'source'
        target = source / FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / FILE, target)
        if variant == 'candidate':
            apply(source)
        elif variant == 'core84':
            historical_namespace['apply'](source)
        postimages[variant] = {FILE: digest(target)}
        shutil.copyfile(target, work / 'KTimeManager.cs')
        for relative in SUPPORT:
            shutil.copyfile(SOURCE / relative, work / Path(relative).name)
        shutil.copyfile(ROOT / 'test/melonx_kernel_timer_allocations/Program.cs', work / 'Program.cs')
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit>
</PropertyGroup><ItemGroup><Compile Remove="source/**/*.cs" /></ItemGroup></Project>''')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        environment = os.environ.copy()
        environment.update(DOTNET_TieredCompilation='0', DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work), '-c', 'Release', '-v', 'q', '--', variant],
            cwd=work, env=environment, capture_output=True, text=True, timeout=180)
        if result.returncode:
            print(result.stdout + result.stderr)
            result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
assert reports['control']['functionalDigest'] == reports['candidate']['functionalDigest']
assert reports['core84']['functionalDigest'] == reports['candidate']['functionalDigest']
assert reports['control']['allocatedBytes'] == reports['control']['armOperations'] * 32
assert reports['candidate']['allocatedBytes'] == 0
assert reports['control']['waitingSlotBytes'] == 8 and reports['candidate']['waitingSlotBytes'] == 32
assert reports['core84']['allocatedBytes'] == 0 and reports['core84']['waitingSlotBytes'] == 32
for report in reports.values():
    assert len(report['cancellation']) == 24
    assert all(item['allocatedBytes'] == 0 for item in report['cancellation'])
report = dict(result='passed', upstreamRevision=pin['revision'], reports=reports,
              sdk=pin['dotnet'], tieredCompilation=False, historicalAdapterBlob=CORE84_ADAPTER_BLOB,
              historicalAdapterSha256=hashlib.sha256(historical_adapter).hexdigest(),
              physicalDeviceTested=False, productionTimerWorkerExecuted=True,
              boundaries='controlled clock, precise sleep event and kernel lock container',
              postimages=postimages,
              upstreamInputs={path: digest(SOURCE / path) for path in [FILE, *SUPPORT]},
              inputs={str(path.relative_to(ROOT)): digest(path) for path in [
                  ROOT / 'build-utils/melonx/adapt_kernel_timer_allocations.py',
                  Path(__file__), ROOT / 'test/melonx_kernel_timer_allocations/Program.cs']})
output = ROOT / 'dist/melonx/kernel-timer-allocations-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
