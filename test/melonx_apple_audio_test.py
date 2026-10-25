"""Run the actual selected Apple session against a timed AVFoundation double.

The control compiles the unmodified upstream session. The same producer
schedule must expose underflow there and preserve every PCM frame after the
fix. This is a scheduling regression test, not a physical speaker test.
"""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_apple_audio import apply

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
upstream_inputs = paths + [
    'src/Ryujinx.Audio.Backends.Apple/Native/AVFoundation.cs',
    'src/Ryujinx.Library/Library.cs',
]
reports = []
with tempfile.TemporaryDirectory(prefix='melonx-apple-audio-') as temporary:
    work = Path(temporary)
    for old in [True, False]:
        case = work / ('control' if old else 'fixed')
        source = case / 'source'
        for name in upstream_inputs:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, target)
        if not old:
            apply(source)
        for name in paths:
            shutil.copyfile(source / name, case / Path(name).name)
        shutil.copyfile(ROOT / 'native/melonx/EmbeddedAddonSelection.cs', case / 'EmbeddedAddonSelection.cs')
        shutil.copyfile(ROOT / 'test/melonx_apple_audio/AVFoundationDouble.cs', case / 'AVFoundationDouble.cs')
        shutil.copyfile(ROOT / 'test/melonx_apple_audio/Program.cs', case / 'Program.cs')
        (case / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416</NoWarn>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        result = subprocess.run(['dotnet', 'run', '--project', str(case / 'test.csproj'), '-c', 'Release', '--', 'control' if old else 'fixed'],
                                capture_output=True, text=True, timeout=120)
        print(result.stdout, flush=True)
        if result.returncode: print(result.stderr, flush=True)
        result.check_returncode()
        reports.append(json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{'))))
inputs = ['build-utils/melonx/adapt_apple_audio.py', 'build-utils/melonx/prepare_embedded.py',
          'native/melonx/EmbeddedAddonSelection.cs', 'native/melonx/EmbeddedAddons.cs',
          'native/melonx/EmbeddedContent.cs', 'test/melonx_apple_audio_test.py',
          'test/melonx_apple_audio/AVFoundationDouble.cs', 'test/melonx_apple_audio/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               avFoundationDouble=True, backend='AppleHardwareDeviceDriver',
               inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p:hashlib.sha256((SOURCE/p).read_bytes()).hexdigest() for p in upstream_inputs})
out = ROOT / 'dist/melonx/apple-audio-update-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2)+'\n')
