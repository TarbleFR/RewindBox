#!/usr/bin/env python3
"""A host memory warning at 8-12 % device available runs the flush-free trim (adapt_host_warning_trim).

Usage: melonx_host_warning_trim_test.py <Core 658 prepared MeloNX tree>
       melonx_host_warning_trim_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the Core 658 preparation and builds the production Ryujinx.Graphics.Gpu assembly.
Static checks bind that GpuContext.cs equals the preparation once the adapter's two replacements are undone, that
CheckHostMemory (the periodic trim at 7 % or less) is unchanged, and, in the preparation, that host reports reach
TrimCaches (Switch.ProcessFrame) and that the comfortable-headroom trim of a short device is the freeOnly one. The
executed fixture compiles TrimCaches and its constants unchanged from the control and from the candidate, with doubles
of the caches, HostMemoryBudget and the logger, over a table of reports (pid 11152's memoryWarning at device 11 % and
2102 MiB headroom first): the two differ only at device 8-12 % with a comfortable headroom, where the candidate runs
the freeOnly trim. No device. Writes dist/melonx/host-warning-trim-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_host_warning_trim', _HOLD)
import adapt_host_warning_trim  # noqa: E402
from adapt_host_warning_trim import apply, BASELINE  # noqa: E402

CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def trim_members(text):
    """TrimCaches with the constants and field before it, and the device constants after it, as compiled."""
    start = text.index('        private const ulong TrimMiB')
    trim = member(text, 'public void TrimCaches(MemoryPressureLevel level)')
    end = text.index(trim) + len(trim)
    constants = text[text.index('        private const int DeviceShortPercent = 7;'):text.index('        private const int DeviceCriticalPercent')]
    return text[start:end] + '\n\n' + constants


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 658 preparation: ' + name)

# Why, in the preparation: host reports reach TrimCaches; the periodic trim is gated at DeviceShortPercent.
switch = (SOURCE / 'src/Ryujinx.HLE/Switch.cs').read_text(encoding='utf-8-sig')
check('MemoryPressureLevel pressure = MemoryPressureMonitor.ConsumePendingLevel();' in switch and 'Gpu.TrimCaches(pressure);' in switch,
      'host reports reach TrimCaches on the GPU thread')
passthrough = (SOURCE / 'src/Ryujinx.Library/UnmanagedPassthrough.cs').read_text(encoding='utf-8-sig')
check('EntryPoint = "report_memory_pressure"' in passthrough, 'the host memoryWarning export')

replacements = []
original_once = adapt_host_warning_trim.once
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-host-warning-trim-') as temporary:
    work = Path(temporary).resolve() / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)

    def recording_once(path, old, new):
        replacements.append((old, new))
        original_once(path, old, new)

    adapt_host_warning_trim.once = recording_once
    try:
        changed = apply(work)
    finally:
        adapt_host_warning_trim.once = original_once
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
    if FINAL_PREPARATION:
        for name in BASELINE:
            check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    control = (SOURCE / CONTEXT).read_text(encoding='utf-8-sig')
    candidate = (work / CONTEXT).read_text(encoding='utf-8-sig')
    undone = candidate
    for old, new in reversed(replacements):
        check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
        undone = undone.replace(new, old)
    check(undone == control and len(replacements) == 2, 'GpuContext.cs is the preparation but the adapter\'s two replacements')
    check(member(candidate, 'public void CheckHostMemory()') == member(control, 'public void CheckHostMemory()') and
          'device >= 0 && device <= DeviceShortPercent && now - _lastDeviceShortTrim >= DeviceShortTrimIntervalMs' in candidate,
          'the periodic trim (7 % or less every 10 s) is unchanged')
    trim = member(candidate, 'public void TrimCaches(MemoryPressureLevel level)')
    check('bool deviceShort = device >= 0 && device <= HostReportedDeviceShortPercent;' in trim and
          'bool freeOnly = deviceShort && available >= ComfortableHeadroomBytes;' in trim and
          'private const int HostReportedDeviceShortPercent = 12;' in candidate, 'host reports: device short up to 12 %; freeOnly with comfortable headroom')

    result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'), '-c', 'Release', '-nologo',
                             '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Gpu builds with the adapter')

    for variant, text in (('control', control), ('candidate', candidate)):
        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        shutil.copyfile(ROOT / 'test/melonx_host_warning_trim/Program.cs', fixture / 'Program.cs')
        (fixture / 'Trim.cs').write_text('using Ryujinx.Common.Logging;\nusing Ryujinx.Memory;\nusing System;\n\n'
                                         'namespace Ryujinx.Graphics.Gpu\n{\n    public partial class GpuContextUnderTest\n    {\n'
                                         + trim_members(text) + '\n    }\n}\n')
        (fixture / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
</PropertyGroup></Project>
''')
        build = subprocess.run([DOTNET, 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'], cwd=fixture,
                               capture_output=True, text=True, timeout=600, env=environment)
        if build.returncode:
            print(build.stdout[-4000:], build.stderr[-2000:], flush=True)
        check(build.returncode == 0, 'fixture builds: ' + variant)
        run = subprocess.run([DOTNET, 'bin/Release/net10.0/Probe.dll'], cwd=fixture, capture_output=True, text=True, timeout=120, env=environment)
        check(run.returncode == 0, 'fixture runs: ' + variant + run.stderr[-2000:])
        reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])

FREE_ONLY = 'textures Warning freeOnly=True | buffers Warning'
FULL_WARNING = 'textures Warning freeOnly=False | buffers Warning'
FULL_CRITICAL = 'textures Critical freeOnly=False | buffers Critical'
expected_control = [' | ', ' | ', ' | ', ' | ', ' | ', FREE_ONLY, ' | ', FULL_WARNING, FULL_CRITICAL, ' | ', ' | ']
expected_candidate = [FREE_ONLY, FREE_ONLY, FREE_ONLY, ' | ', ' | ', FREE_ONLY, ' | ', FULL_WARNING, FULL_CRITICAL, 'textures Critical freeOnly=True | buffers Critical', ' | ']
# Critical at device 11 % with comfortable headroom: control ignores it (device not short); candidate trims freeOnly at Critical.
for variant, expected in (('control', expected_control), ('candidate', expected_candidate)):
    calls = [r['calls'] for r in reports[variant]]
    check(calls == expected, variant + ' trims: ' + json.dumps(calls))
    check(all(r['secondWithin2s'] == 0 for r in reports[variant]), 'a second report within 2 s does nothing: ' + variant)
first = reports['candidate'][0]
check('device 11% available, released 40 MiB of GPU caches; device short only' in first['log'],
      'the pid 11152 memoryWarning now logs a flush-free trim: ' + first['log'])
check('Ignoring Warning host memory pressure with 2102 MiB' in reports['control'][0]['log'], 'control ignored it: ' + reports['control'][0]['log'])
differing = [i for i in range(len(expected_control)) if expected_control[i] != expected_candidate[i]]
check(all(reports['candidate'][i]['device'] in range(8, 13) and reports['candidate'][i]['availableMiB'] >= 768 for i in differing),
      'the variants differ only at device 8-12 % with a comfortable headroom')

inputs = ['build-utils/melonx/adapt_host_warning_trim.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_adapter_control.py',
          'test/melonx_host_warning_trim_test.py', 'test/melonx_host_warning_trim/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               sdk=sdk, reports=reports, physicalDeviceTested=False, productionGpuAssemblyBuilt=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='How much a host-reported trim frees at 8-12 % device available, and whether the textures come back, is known only from a device run.')
out = ROOT / 'dist/melonx/host-warning-trim-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
