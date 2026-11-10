#!/usr/bin/env python3
"""Compare the whole production timer manager, including its actual worker.

Host time and precise sleep events are controlled boundaries. No timer-manager
statement is replaced in either compiled version. Direct list checks exercise
captured identity; the real worker also runs cancellation/rearm/rollover cases.
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
