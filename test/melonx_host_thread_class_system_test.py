#!/usr/bin/env python3
"""The host thread class helper of adapt_host_thread_class against the system itself (macOS only; elsewhere: skipped).

The Core gate host-thread-class observes the helper's request through its seams and, on macOS, also made the engine's
own call on a thread of the gate's host runtime. Core CI run 42999377576 (macos-26, .NET 10.0.100) read there: the
helper answers false and the thread's class stays 0. This test separates the kinds of thread: the adapter's real helper
(extracted from adapt_host_thread_class.HELPER_NEW) and the raw system call are each run on
- a thread of the system (pthread_create with default attributes: what the threads of the NativeAOT runtime the Core
  ships with are), entering managed code through an unmanaged entry point;
- a thread the host runtime creates (new Thread), and one of its pool.
On a system thread the helper must put the thread in the user-interactive class (0x21) and say so. On the host
runtime's own threads the answer is reported as it is and must be coherent: true with 0x21, or false with the class
unchanged and one journal record. Writes dist/melonx/host-thread-class-system-checks.json.
"""
from pathlib import Path
import json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import adapt_host_thread_class as adapter  # noqa: E402

if platform.system() != 'Darwin':
    print(json.dumps(dict(result='skipped', reason='not macOS: the system call is Apple\'s')))
    raise SystemExit(0)
DOTNET = os.environ.get('DOTNET', 'dotnet')
helper = adapter.HELPER_NEW[adapter.HELPER_NEW.index(adapter.HELPER_BEGIN):adapter.HELPER_NEW.index(adapter.HELPER_END)]
work = Path(tempfile.mkdtemp(prefix='melonx-host-thread-class-system-')).resolve()
(work / 'Helper.cs').write_text('namespace Ryujinx.Common\n{\n' + helper + '}\n')
shutil.copyfile(ROOT / 'test/melonx_host_thread_class_system/Program.cs', work / 'Program.cs')
(work / 'Fixture.csproj').write_text(
    '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
    '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit>'
    '<NoWarn>CS0649;CS0414;CS0169;CS8632;SYSLIB1054</NoWarn></PropertyGroup></Project>\n')
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
run = subprocess.run([DOTNET, 'run', '--project', str(work), '-c', 'Release', '-v', 'q'], capture_output=True, text=True, timeout=900, env=environment, cwd=work)
print(run.stdout[-3000:], run.stderr[-2000:], flush=True)
assert run.returncode == 0, 'the fixture runs'
report = json.loads(next(line for line in reversed(run.stdout.splitlines()) if line.startswith('{')))
shutil.rmtree(work)
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


raw, system = report['systemThreadRaw'], report['systemThreadHelper']
check(raw['answer'] == 0 and raw['classAfter'] == 0x21 and raw['classBefore'] != 0x21, 'a system thread: the call is accepted: ' + json.dumps(raw))
check(system['answer'] is True and system['classAfter'] == 0x21 and system['classBefore'] != 0x21,
      'a system thread: the helper puts it in the user-interactive class: ' + json.dumps(system))
own = report['runtimeThreadHelper']
check((own['answer'] is True and own['classAfter'] == 0x21) or
      (own['answer'] is False and own['classAfter'] == own['classBefore'] and len(report['records']) == 1 and
       report['records'][0].startswith('hostThreadClass refused ') and '(adapt_host_thread_class)' in report['records'][0]),
      'a thread of this host runtime: granted, or refused with the class unchanged and one record: ' + json.dumps([own, report['records']]))
check(own['answer'] is True or report['runtimeThreadRaw']['answer'] != 0, 'a refusal by the helper is the system\'s refusal: ' + json.dumps(report['runtimeThreadRaw']))
receipt = dict(result='passed', checks=checks, report=report, physicalDeviceTested=False)
out = ROOT / 'dist/melonx/host-thread-class-system-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, systemThread=system, runtimeThread=own, runtimeThreadRaw=report['runtimeThreadRaw'],
                      poolThreadRaw=report['poolThreadRaw'], runtime=report['runtime'])))
