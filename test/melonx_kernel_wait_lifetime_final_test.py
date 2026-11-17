#!/usr/bin/env python3
"""adapt_kernel_wait_lifetime's kernel wait bodies, executed again from the final preparation (fresh successor of the
historical kernel-wait-lifetime receipt).

Usage: melonx_kernel_wait_lifetime_final_test.py <delivered control> --candidate-source <final preparation>

The historical gate (test/melonx_kernel_wait_lifetime_test.py) runs on pristine upstream and applies the adapter. After
IPA 767, adapt_guest_break_context changes Syscall.cs, one of its three files, so the Core contract needs this gate on
the final source. Static: KSynchronizationObject.cs and KSynchronization.cs are the delivered control's; Syscall.cs is the
control's once adapt_guest_break_context's two replacements are undone (once each), so the WaitSynchronization overload
the historical gate adapted is the control's, unchanged. Executed: the historical harness
(test/melonx_kernel_wait_lifetime/Program.cs, unchanged) on the final preparation's two kernel files and its
WaitSynchronization body, with the control's support files: the same 181 scenarios give the historical functional digest
(the one pristine and adapted upstream both give), and no wait node, wait slot or signalled object is retained.
No device. Writes dist/melonx/kernel-wait-lifetime-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import adapt_guest_break_context as later  # noqa: E402
from adapt_kernel_wait_lifetime import WAIT_SIGNATURE  # noqa: E402

CONTROL = Path(sys.argv[1]).resolve()
FINAL = Path(sys.argv[sys.argv.index('--candidate-source') + 1]).resolve()
DOTNET = os.environ.get('DOTNET', 'dotnet')
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
# Historical receipt (pristine upstream 13700519, control and adapted candidate alike): 181 scenarios.
FUNCTIONAL_DIGEST = '928057C79853BDC1C84457F36318C99A5874376F75716E3DB8DD794C1D637AE8'
CLEANUPS = ('node.Value = null;', 'currentThread.SignaledObj = null;')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def method(text):
    check(text.count(WAIT_SIGNATURE) == 1, 'one WaitSynchronization overload')
    start = text.index(WAIT_SIGNATURE)
    return text[start:text.index('\n        [Svc(0x19)]', start)]


for name in FILES[:2]:
    check((FINAL / name).read_bytes() == (CONTROL / name).read_bytes(), 'the final kernel file is the delivered control\'s: ' + name)
check(CLEANUPS[0] in (FINAL / FILES[0]).read_text(encoding='utf-8-sig') and CLEANUPS[1] in (FINAL / FILES[1]).read_text(encoding='utf-8-sig'),
      'the adapter\'s node and signalled object cleanups are in the final files')
final_syscall = (FINAL / FILES[2]).read_text(encoding='utf-8-sig')
reverted = final_syscall
for _, old, new in reversed(later.PAIRS):
    check(reverted.count(new) == 1, 'adapt_guest_break_context applied once to Syscall.cs')
    reverted = reverted.replace(new, old)
control_syscall = (CONTROL / FILES[2]).read_text(encoding='utf-8-sig')
check(reverted == control_syscall, 'Syscall.cs is the delivered control plus adapt_guest_break_context only')
wait_method = method(final_syscall)
check(wait_method == method(control_syscall) and 'int processedHandles = 0;' in wait_method and 'finally' in wait_method,
      'the final WaitSynchronization overload is the adapted one, unchanged')

pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-kernel-wait-final-') as temporary:
    work = Path(temporary)
    for relative in FILES[:2]:
        shutil.copyfile(FINAL / relative, work / Path(relative).name)
    (work / 'Syscall.cs').write_text('''using System;
using Ryujinx.HLE.HOS.Kernel.Common;
using Ryujinx.HLE.HOS.Kernel.Threading;
using Ryujinx.HLE.HOS.Kernel.Process;
using Ryujinx.Horizon.Common;
namespace Ryujinx.HLE.HOS.Kernel.SupervisorCall {
class Syscall {
private readonly KernelContext _context;
public Syscall(KernelContext context) { _context = context; }
''' + wait_method + '\n}}\n')
    for relative in SUPPORT:
        shutil.copyfile(CONTROL / relative, work / Path(relative).name)
    shutil.copyfile(ROOT / 'test/melonx_kernel_wait_lifetime/Program.cs', work / 'Program.cs')
    (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit>
</PropertyGroup></Project>''')
    (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
    result = subprocess.run([DOTNET, 'run', '--project', str(work), '-c', 'Release', '-v', 'q', '--', 'candidate'], cwd=work,
                            capture_output=True, text=True, timeout=600, env=environment)
    if result.returncode:
        print(result.stdout[-4000:], result.stderr[-3000:], flush=True)
    check(result.returncode == 0, 'the historical harness runs on the final bodies')
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    compiled = {'waitSynchronizationMethodSha256': hashlib.sha256(wait_method.encode()).hexdigest(),
                'compiledSyscallSha256': digest(work / 'Syscall.cs'), 'programSha256': digest(work / 'Program.cs')}

check(report['scenarios'] == 181 and report['functionalDigest'] == FUNCTIONAL_DIGEST and report['productionWaitAlgorithmExecuted'],
      'the 181 scenarios give the historical functional digest: ' + str(report))
check(not report['retainedWaitNodes'] and not report['retainedWaitSlots'] and not report['retainedSignaledObject'],
      'no wait node, wait slot or signalled object retained: ' + str(report))

inputs = ['build-utils/melonx/adapt_kernel_wait_lifetime.py', 'build-utils/melonx/adapt_guest_break_context.py',
          'test/melonx_kernel_wait_lifetime_final_test.py', 'test/melonx_kernel_wait_lifetime/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparation',
               sdk=sdk, physicalDeviceTested=False, report=report, compiledInputs=compiled,
               kernelWaitLifetime=dict(executed=True, functionalDigest=report['functionalDigest']),
               schedulerBoundary='controlled; production wait/list/refcount algorithms',
               postimages={p: digest(FINAL / p) for p in FILES}, preimages={p: digest(CONTROL / p) for p in FILES},
               upstreamInputs={p: digest(CONTROL / p) for p in SUPPORT},
               inputs={p: digest(ROOT / p) for p in inputs})
out = ROOT / 'dist/melonx/kernel-wait-lifetime-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
