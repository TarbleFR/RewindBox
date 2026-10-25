#!/usr/bin/env python3
"""Run the actual adapted driver, pad, lease, snapshots and callbacks on .NET.

Only unused configuration data shapes are stubbed; input/ownership behavior is
the pinned production code, including the original shared-pad disconnect bug.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / 'build-utils/melonx'))
from adapt_input import apply

inputs = [
    'src/Ryujinx.Input.Native/NativeGamepad.cs', 'src/Ryujinx.Input.Native/NativeGamepadDriver.cs',
    *['src/Ryujinx.Input/' + name + '.cs' for name in ['IGamepad', 'IGamepadDriver',
      'GamepadButtonInputId', 'GamepadFeaturesFlag', 'StickInputId', 'MotionInputId',
      'GamepadStateSnapshot', 'HighDefinitionRumble']],
    'src/Ryujinx.Common/Memory/IArray.cs', 'src/Ryujinx.Common/Memory/StructArrayHelpers.cs',
    'src/Ryujinx.Common/Callbacks/CallbackRegistry.cs',
]
with tempfile.TemporaryDirectory(prefix='melonx-input-') as temporary:
    work = Path(temporary)
    stage = work / 'source'
    # Apply the same exact driver adaptation as the full engine build. Library
    # is present for its audited helper extraction but is not compiled here.
    for name in [*inputs, 'src/Ryujinx.Library/Library.cs']:
        dest = stage / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((source / name).read_bytes())
    apply(stage)
    files = []
    for i, name in enumerate(inputs):
        dest = work / f'Input{i}.cs'
        dest.write_bytes((stage / name).read_bytes())
        files.append(dest)
    (work / 'Lease.cs').write_bytes((root / 'native/melonx/EmbeddedNativeGamepadLease.cs').read_bytes())
    (work / 'Config.cs').write_text('''namespace Ryujinx.Common.Configuration.Hid { public class InputConfig {} }
namespace Ryujinx.Common.Configuration.Hid.Controller {
 public class StandardControllerInputConfig : Ryujinx.Common.Configuration.Hid.InputConfig { public float TriggerThreshold { get; set; } }
}''')
    (work / 'Input.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup>
<ItemGroup><Compile Include="*.cs" /></ItemGroup></Project>''')
    (work / 'Program.cs').write_text(r'''using System;
using System.Linq;
using System.Threading.Tasks;
using Ryujinx.Input;
using Ryujinx.Input.Native;
using Ryujinx.Common.Callbacks;
int cases = 0;
void Check(bool value) { if (!value) throw new Exception("Input assertion failed"); cases++; }
using var driver = new NativeGamepadDriver();
NativeGamepadDriver.AttachGamepad("Original touch", (nint)1);
var probe = driver.GetGamepad("1");
var game = driver.GetGamepad("1");
Check(probe.IsConnected && game.IsConnected && !ReferenceEquals(probe, game));
probe.Dispose(); // Actual HandlePlayerConfiguration probe-dispose behavior.
Check(!probe.IsConnected && game.IsConnected && driver.GetGamepad("1").IsConnected);
var mapping = new[] {GamepadButtonInputId.A,GamepadButtonInputId.B,GamepadButtonInputId.X,GamepadButtonInputId.Y,
 GamepadButtonInputId.Back,GamepadButtonInputId.Guide,GamepadButtonInputId.Start,GamepadButtonInputId.LeftStick,
 GamepadButtonInputId.RightStick,GamepadButtonInputId.LeftShoulder,GamepadButtonInputId.RightShoulder,
 GamepadButtonInputId.DpadUp,GamepadButtonInputId.DpadDown,GamepadButtonInputId.DpadLeft,GamepadButtonInputId.DpadRight,
 GamepadButtonInputId.LeftTrigger,GamepadButtonInputId.RightTrigger};
for(int button=0;button<mapping.Length;button++) {
 NativeGamepadDriver.ResetState((nint)1); NativeGamepadDriver.SetButtonState((nint)1,button,1);
 var snapshot=game.GetStateSnapshot();
 Check(snapshot.IsPressed(mapping[button]) && !probe.IsPressed(mapping[button]));
}
NativeGamepadDriver.SetStickAxis((nint)1,1,0.25f,-0.75f);
NativeGamepadDriver.SetStickAxis((nint)1,2,3f,-3f);
Check(game.GetStick(StickInputId.Left)==(0.25f,-0.75f) && game.GetStick(StickInputId.Right)==(1f,-1f));
var enumerated = driver.GetGamepads().Single(); enumerated.Dispose();
Check(!enumerated.IsConnected && game.IsConnected);
int rumbles=0; CallbackRegistry.RegisterManagedCallback("rumble-1", _ => rumbles++);
game.Rumble(0.5f,0.2f,20); probe.Rumble(1,1,10); Check(rumbles==1);
game.Dispose(); var reopened=driver.GetGamepad("1");
Check(!game.IsConnected && reopened.IsConnected);
NativeGamepadDriver.DetachGamepad((nint)1);
Check(!reopened.IsConnected && driver.GetGamepad("1")==null && driver.GamepadsIds.Length==0);
NativeGamepadDriver.AttachGamepad("Next session",(nint)1); var next=driver.GetGamepad("1");
Check(next.IsConnected && !next.IsPressed(GamepadButtonInputId.A) && !reopened.IsConnected);
reopened.Dispose(); Check(next.IsConnected);
NativeGamepadDriver.ResetState((nint)1);
Check(next.GetStick(StickInputId.Left)==(0f,0f) && next.GetStick(StickInputId.Right)==(0f,0f));
Parallel.For(0,1000,i=>{using var handle=driver.GetGamepad("1");NativeGamepadDriver.SetButtonState((nint)1,i%17,(byte)(i%2));});
Check(next.IsConnected);
driver.Dispose(); Check(!next.IsConnected);
Console.WriteLine($"Production native input ownership: {cases} cases passed.");
''')
    result = subprocess.run(['dotnet', 'run', '--project', str(work / 'Input.csproj'), '-c', 'Release'],
                            check=True, capture_output=True, text=True, timeout=120)
    print(result.stdout, end='')
out = root / 'dist/melonx/input-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(dict(productionInputs={p: hashlib.sha256((source/p).read_bytes()).hexdigest() for p in inputs},
    adapterInputs={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
      [root/'native/melonx/EmbeddedNativeGamepadLease.cs', root/'build-utils/melonx/adapt_input.py',Path(__file__)]},
    result=result.stdout.strip(), gameplayTested=False), indent=2)+'\n')
