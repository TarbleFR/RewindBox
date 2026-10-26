"""Exercise the audio pacing counters on the adapted sources.

The DSP edit is checked in place on the upstream AudioProcessor; the counters,
the export and the adapted Apple session run against the timed AVFoundation
double. Measurement only: no PCM, timing or scheduling behaviour changes.
"""
from pathlib import Path
import hashlib, json, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_apple_audio import apply as adapt_apple_audio
from adapt_audio_pacing import apply as adapt_audio_pacing

processor = 'src/Ryujinx.Audio/Renderer/Dsp/AudioProcessor.cs'
paths = [
    'src/Ryujinx.Audio.Backends.Apple/AppleHardwareDeviceSession.cs',
    'src/Ryujinx.Audio.Backends.Apple/AppleHardwareDeviceDriver.cs',
    'src/Ryujinx.Audio.Backends.Apple/AppleAudioBuffer.cs',
    'src/Ryujinx.Audio/Backends/Common/HardwareDeviceSessionOutputBase.cs',
    'src/Ryujinx.Audio/Backends/Common/BackendHelper.cs',
    'src/Ryujinx.Audio/Common/AudioBuffer.cs',
    'src/Ryujinx.Audio/Common/SampleFormat.cs',
    'src/Ryujinx.Audio/Integration/IHardwareDeviceDriver.cs',
    'src/Ryujinx.Audio/Integration/IHardwareDeviceSession.cs',
]
upstream_inputs = paths + [processor,
    'src/Ryujinx.Audio.Backends.Apple/Native/AVFoundation.cs',
    'src/Ryujinx.Library/Library.cs',
]
with tempfile.TemporaryDirectory(prefix='melonx-audio-pacing-') as temporary:
    case = Path(temporary)
    source = case / 'source'
    for name in upstream_inputs:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, target)
    adapt_apple_audio(source)
    upstream = (SOURCE / processor).read_text(encoding='utf-8-sig')
    adapted = adapt_audio_pacing(source)
    assert [p.relative_to(source).as_posix() for p in adapted] == [processor, paths[0]]

    # The DSP edit only adds lines: removing them restores the upstream text.
    dsp = (source / processor).read_text(encoding='utf-8')
    added = ['                EmbeddedAudioPacing.DspSkipped(bufferedFrames - TargetBufferedFrames);\n',
             '            long due = _lastTime + increment;\n\n',
             '            // How late this period ended (a late wake-up or a busy producer).\n',
             '            EmbeddedAudioPacing.DspPeriod(timeNow - due);\n\n']
    restored = dsp
    for line in added:
        assert restored.count(line) == 1, line
        restored = restored.replace(line, '')
    assert restored == upstream.replace('\r\n', '\n') or restored == upstream, 'DSP pacing changed more than measurement lines'
    assert 'using Ryujinx.Common;' in dsp
    wait = re.search(r'long due = _lastTime \+ increment;\s+while \(timeNow < _lastTime \+ increment\)\s+\{[^}]*\}\s+'
                     r'// How late[^\n]*\n\s+EmbeddedAudioPacing\.DspPeriod\(timeNow - due\);\s+_lastTime \+= increment;', dsp)
    assert wait, 'Lateness is not measured around the wait loop'
    print('PASS DSP pacing measured around the unchanged wait loop', flush=True)

    # A completion that races a new buffer or a guest stop cannot be driven by
    # the double; the re-check must directly follow the completion's count.
    apple = (source / paths[0]).read_text(encoding='utf-8')
    completed = apple.index('EmbeddedAudioPacing.HostCompleted(ref _pacingStarvedSince, _queuedBuffers.IsEmpty && _started,')
    recheck = apple.index('if (!_queuedBuffers.IsEmpty || !_started) Ryujinx.Common.EmbeddedAudioPacing.HostIdle(ref _pacingStarvedSince);')
    assert completed < recheck < apple.index('AVFoundation.Release(buffer.NativeBuffer);', completed), 'starvation re-check missing'

    for name in paths:
        shutil.copyfile(source / name, case / Path(name).name)
    shutil.copyfile(ROOT / 'native/melonx/EmbeddedAudioPacing.cs', case / 'EmbeddedAudioPacing.cs')
    shutil.copyfile(ROOT / 'native/melonx/EmbeddedAudioPacingExport.cs', case / 'EmbeddedAudioPacingExport.cs')
    shutil.copyfile(ROOT / 'test/melonx_apple_audio/AVFoundationDouble.cs', case / 'AVFoundationDouble.cs')
    shutil.copyfile(ROOT / 'test/melonx_audio_pacing/Program.cs', case / 'Program.cs')
    (case / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416</NoWarn>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
    result = subprocess.run(['dotnet', 'run', '--project', str(case / 'test.csproj'), '-c', 'Release'],
                            capture_output=True, text=True, timeout=180)
    print(result.stdout, flush=True)
    if result.returncode: print(result.stderr, flush=True)
    result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    assert report['result'] == 'passed'
inputs = ['build-utils/melonx/adapt_audio_pacing.py', 'build-utils/melonx/adapt_apple_audio.py',
          'native/melonx/EmbeddedAudioPacing.cs', 'native/melonx/EmbeddedAudioPacingExport.cs',
          'test/melonx_audio_pacing_test.py', 'test/melonx_audio_pacing/Program.cs',
          'test/melonx_apple_audio/AVFoundationDouble.cs']
receipt = dict(result='passed', report=report, physicalDeviceTested=False, avFoundationDouble=True,
               inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p:hashlib.sha256((SOURCE/p).read_bytes()).hexdigest() for p in upstream_inputs})
out = ROOT / 'dist/melonx/audio-pacing-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2)+'\n')
print('PASS audio pacing counters, export and adapted Apple session', flush=True)
