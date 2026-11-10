#!/usr/bin/env python3
"""adapt_audio_start_deferred on the final preparation, against the Core 677 postimage as control.

An audio output created while iOS refuses to start AVAudioEngine no longer throws (the IPA 674 Hogwarts abort): the
session keeps its prepared engine and the deferred restart starts it once iOS allows it, without losing queued PCM.
Control: the final preparation with the adapter reversed (melonx_adapter_control), which must be the Core 677 bytes.
Executed (test/melonx_audio_start_deferred with test/melonx_apple_audio/AVFoundationDouble.cs) for control and
candidate on the variant's real final Apple session and driver. Writes dist/melonx/audio-start-deferred-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control as control_tools  # noqa: E402
import adapt_audio_start_deferred as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
SESSION = 'src/Ryujinx.Audio.Backends.Apple/AppleHardwareDeviceSession.cs'
COMPILED = [
    SESSION,
    'src/Ryujinx.Audio.Backends.Apple/AppleHardwareDeviceDriver.cs',
    'src/Ryujinx.Audio.Backends.Apple/AppleAudioBuffer.cs',
    'src/Ryujinx.Audio/Backends/Common/HardwareDeviceSessionOutputBase.cs',
    'src/Ryujinx.Audio/Backends/Common/BackendHelper.cs',
    'src/Ryujinx.Audio/Common/AudioBuffer.cs',
    'src/Ryujinx.Audio/Common/SampleFormat.cs',
    'src/Ryujinx.Audio/Integration/IHardwareDeviceDriver.cs',
    'src/Ryujinx.Audio/Integration/IHardwareDeviceSession.cs',
]
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


temporary = tempfile.TemporaryDirectory(prefix='melonx-audio-start-deferred-')
WORK = Path(temporary.name).resolve()
CONTROL = WORK / 'control'
for name in adapter.BASELINE:
    (CONTROL / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FINAL_SOURCE / name, CONTROL / name)

# --- Control: the adapter reversed must be the Core 677 bytes; forward reproduces the final preparation ---
control_tools._reverse('adapt_audio_start_deferred', CONTROL)
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 677 postimage: ' + name)
forward = WORK / 'forward'
for name in adapter.BASELINE:
    (forward / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL / name, forward / name)
changed = sorted(str(p.relative_to(forward)) for p in adapter.apply(forward))
check(changed == sorted(adapter.BASELINE), 'the adapter changes only its file')
for name in adapter.BASELINE:
    check((forward / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
drift = WORK / 'drift'
(drift / SESSION).parent.mkdir(parents=True, exist_ok=True)
(drift / SESSION).write_bytes((CONTROL / SESSION).read_bytes() + b'\n// unreviewed drift\n')
try:
    adapter.apply(drift)
    refused = False
except AssertionError:
    refused = True
check(refused, 'a drifted session file is refused')

# --- Static: the exact scope ---
final = (FINAL_SOURCE / SESSION).read_text(encoding='utf-8-sig')
control = (CONTROL / SESSION).read_text(encoding='utf-8-sig')
check(final.replace(adapter.START_NEW, adapter.START_OLD) == control, 'the session differs only by the start-failure branch')
check('throw new InvalidOperationException("Failed to initialize AVFoundation audio objects.");' in final,
      'a failure to create the AVFoundation objects still throws')
check(final.count('AVAudioEngine failed to start') == 0 and control.count('AVAudioEngine failed to start') == 1,
      'the start failure no longer throws')

# --- Executed: control and candidate on the real final session and driver ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
reports, compiled = {}, {}
for variant in ('control', 'candidate'):
    tree = CONTROL if variant == 'control' else FINAL_SOURCE
    fixture = WORK / ('fixture-' + variant)
    fixture.mkdir()
    for name in COMPILED:
        shutil.copyfile((tree if name == SESSION else FINAL_SOURCE) / name, fixture / Path(name).name)
    shutil.copyfile(ROOT / 'native/melonx/EmbeddedAudioPacing.cs', fixture / 'EmbeddedAudioPacing.cs')
    shutil.copyfile(ROOT / 'test/melonx_apple_audio/AVFoundationDouble.cs', fixture / 'AVFoundationDouble.cs')
    shutil.copyfile(ROOT / 'test/melonx_audio_start_deferred/Program.cs', fixture / 'Program.cs')
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit>'
        '<NoWarn>CA1416;CS0649;CS0414;CS0169;CS0067</NoWarn></PropertyGroup></Project>\n')
    build = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                           capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if build.returncode:
        print('\n'.join(line for line in build.stdout.splitlines() if ': error ' in line)[:6000], flush=True)
    check(build.returncode == 0, variant + ' fixture builds with the real final session')
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant],
                         capture_output=True, text=True, timeout=600, env=environment, cwd=fixture)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' fixture runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
    compiled[variant] = {p.name: sha(p) for p in sorted(fixture.glob('*.cs'))}
    print(variant + ': ' + json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
check(c['refusedAtCreation']['created'] is False and
      c['refusedAtCreation']['exception'].startswith('InvalidOperationException: AVAudioEngine failed to start'),
      'control (Core 677): a refused engine start at creation throws (the IPA 674 abort)')
kr = k['refusedAtCreation']
check(kr['created'] and kr['playedWhileRefused'] == 0 and not kr['runningWhileRefused'],
      'candidate: the session is created; nothing is played or falsely consumed while iOS refuses')
check(kr['runningAfterPoll'], 'candidate: consumer polling starts the engine once iOS allows it')
check(kr['played'] == 960 and kr['pcmIntact'], 'candidate: every queued frame plays, in order, after the deferred start')
check(c['startedAtCreation'] == k['startedAtCreation'] and k['startedAtCreation']['played'] == 960 and
      k['startedAtCreation']['pcmIntact'] and k['startedAtCreation']['starts'] == 1,
      'an engine that starts at creation behaves exactly as before')

inputs = ['build-utils/melonx/adapt_audio_start_deferred.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_audio_start_deferred_test.py', 'test/melonx_audio_start_deferred/Program.cs',
          'test/melonx_apple_audio/AVFoundationDouble.cs', 'native/melonx/EmbeddedAudioPacing.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               postimages={n: sha(FINAL_SOURCE / n) for n in adapter.BASELINE}, reports=reports, compiledSources=compiled,
               sdk=sdk, host=platform.system(), physicalDeviceTested=False, gameTested=False, avFoundationDouble=True,
               inputs={n: sha(ROOT / n) for n in inputs},
               limitation='Real final Apple session and driver against the AVFoundation double. Why iOS refused the engine '
                          'on the device (memory pressure, an interruption) is not reproduced.')
out = ROOT / 'dist/melonx/audio-start-deferred-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
