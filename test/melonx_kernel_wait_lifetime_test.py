#!/usr/bin/env python3
"""Execute production kernel wait/list/refcount bodies with controlled scheduling.

The event objects, thread/process host and scheduler are test boundaries. The
entire KSynchronization, KSynchronizationObject, KAutoObject and ObjectPool and
the complete production WaitSynchronization overload execute without rewriting.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_kernel_wait_lifetime import apply, WAIT_SIGNATURE

FILES = [
    'src/Ryujinx.HLE/HOS/Kernel/Common/KSynchronizationObject.cs',
    'src/Ryujinx.HLE/HOS/Kernel/Threading/KSynchronization.cs',
    'src/Ryujinx.HLE/HOS/Kernel/SupervisorCall/Syscall.cs',
]
SUPPORT = [
    'src/Ryujinx.HLE/HOS/Kernel/Common/KAutoObject.cs',
    'src/Ryujinx.HLE/HOS/Kernel/Threading/ThreadSchedState.cs',
    'src/Ryujinx.Common/Pools/ObjectPool.cs',
    *['src/Ryujinx.Horizon.Common/' + name for name in [
        'Result.cs', 'KernelResult.cs', 'ResultNames.cs',
        'InvalidResultException.cs', 'ThreadTerminatedException.cs']],
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def method(text):
    assert text.count(WAIT_SIGNATURE) == 1
    start = text.index(WAIT_SIGNATURE)
    return text[start:text.index('\n        [Svc(0x19)]', start)]


pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == pin['revision']
assert not subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--', *FILES, *SUPPORT], text=True).strip()
reports, compiled, postimages = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-kernel-wait-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary) / variant
        source = work / 'source'
        for relative in FILES:
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            apply(source)
        postimages[variant] = {name: digest(source / name) for name in FILES}
        for relative in FILES[:2]:
            shutil.copyfile(source / relative, work / Path(relative).name)
        syscall_method = method((source / FILES[2]).read_text())
        generated = '''using System;
using Ryujinx.HLE.HOS.Kernel.Common;
using Ryujinx.HLE.HOS.Kernel.Threading;
using Ryujinx.HLE.HOS.Kernel.Process;
using Ryujinx.Horizon.Common;
namespace Ryujinx.HLE.HOS.Kernel.SupervisorCall {
class Syscall {
private readonly KernelContext _context;
public Syscall(KernelContext context) { _context = context; }
''' + syscall_method + '\n}}\n'
        (work / 'Syscall.cs').write_text(generated)
        for relative in SUPPORT:
            shutil.copyfile(SOURCE / relative, work / Path(relative).name)
        shutil.copyfile(ROOT / 'test/melonx_kernel_wait_lifetime/Program.cs', work / 'Program.cs')
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit>
</PropertyGroup><ItemGroup><Compile Remove="source/**/*.cs" /></ItemGroup></Project>''')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        result = subprocess.run(['dotnet', 'run', '--project', str(work), '-c', 'Release', '-v', 'q', '--', variant], cwd=work, capture_output=True, text=True, timeout=180)
        if result.returncode:
            print(result.stdout + result.stderr)
            result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        compiled[variant] = {'waitSynchronizationMethodSha256': hashlib.sha256(syscall_method.encode()).hexdigest(),
                             'compiledSyscallSha256': digest(work / 'Syscall.cs'),
                             'programSha256': digest(work / 'Program.cs')}
assert reports['control']['functionalDigest'] == reports['candidate']['functionalDigest']
assert reports['control']['retainedWaitNodes'] and not reports['candidate']['retainedWaitNodes']
assert reports['control']['retainedWaitSlots'] and not reports['candidate']['retainedWaitSlots']
assert reports['control']['retainedSignaledObject'] and not reports['candidate']['retainedSignaledObject']
report = dict(result='passed', upstreamRevision=pin['revision'], reports=reports,
              physicalDeviceTested=False, schedulerBoundary='controlled; production wait/list/refcount algorithms',
              compiledInputs=compiled, postimages=postimages,
              upstreamInputs={path: digest(SOURCE / path) for path in [*FILES, *SUPPORT]},
              inputs={str(path.relative_to(ROOT)): digest(path) for path in [
                  ROOT / 'build-utils/melonx/adapt_kernel_wait_lifetime.py',
                  Path(__file__), ROOT / 'test/melonx_kernel_wait_lifetime/Program.cs']})
output = ROOT / 'dist/melonx/kernel-wait-lifetime-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
