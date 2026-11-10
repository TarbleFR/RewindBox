#!/usr/bin/env python3
"""Execute one stick value from the native input export to the HID npad state on .NET.

Usage: melonx_stick_chain_test.py <prepared MeloNX Core source> [--artifacts <dir>]

The second player's report "left joystick didn't work in game" (Hogwarts Legacy, IPA 658) needs the Core side of the
input chain proven, not read. This builds the prepared Core's Ryujinx.Input.Native (with Ryujinx.Input, Ryujinx.HLE and
Ryujinx.Common) unchanged, then compiles a fixture with:
- native/melonx/EmbeddedInput.cs and native/melonx/EmbeddedSessionCoordinator.cs verbatim (the exports the iOS host
  calls through MeloNXRuntimeAPI: neostation_melonx_input_attach/stick/button/reset/detach), called through unmanaged
  function pointers exactly like the host;
- AttachGamepadCore, DetachGamepadCore, EnsureKeyboardFallback and HandlePlayerConfiguration extracted verbatim from
  the prepared Ryujinx.Library/Library.cs (the "Configuring 1 as ProController (Player1)" path in the player's logs);
- the real InputManager/NpadManager.ReloadConfiguration and, per update, the same NpadController calls that
  NpadManager.Update makes for Player1 (DriverConfigurationUpdate, UpdateUserConfiguration, Update,
  GetHLEInputState) and the real Hid.UpdateStickButtons.
Only the keyboard driver (unused for pad "1"), the window holder and the keyboard config are stubbed. The last hop,
NpadDevices.UpdateInput, copies GamepadInput.LStick/RStick into AnalogStickL/AnalogStickR; that copy is bound by text.
Prints the HLE state for each value and writes dist/melonx/stick-chain-checks.json. No device, no guest.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]).resolve()
reuse = Path(sys.argv[sys.argv.index('--artifacts') + 1]).resolve() if '--artifacts' in sys.argv else None
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def method(text, signature):
    """The whole method that starts with signature (balanced braces)."""
    begin = text.index(signature)
    index = text.index('{', begin) + 1
    depth = 1
    while depth:
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        index += 1
    return text[begin:index]


library = (source / 'src/Ryujinx.Library/Library.cs').read_text()
npad_devices = (source / 'src/Ryujinx.HLE/HOS/Services/Hid/HidDevices/NpadDevices.cs').read_text()
manager = (source / 'src/Ryujinx.Input/HLE/NpadManager.cs').read_text()
extracted = [method(library, s) for s in (
    'private static nint AttachGamepadCore(string name, nint idPtr, int playerIndex, ControllerType controllerType)',
    'private static void DetachGamepadCore(nint idPtr)',
    'private static void EnsureKeyboardFallback()',
    'private static InputConfig HandlePlayerConfiguration(')]
# The production update that this fixture repeats for Player1, and the HID copy it does not execute.
update = method(manager, 'public void Update(float aspectRatio = 1)')
check('DriverConfigurationUpdate(ref controller, inputConfig);\n\n                        controller.UpdateUserConfiguration(inputConfig);\n'
      '                        controller.Update();' in update and 'inputState = controller.GetHLEInputState();' in update and
      'inputState.Buttons |= _device.Hid.UpdateStickButtons(inputState.LStick, inputState.RStick);' in update and
      '_device.Hid.Npads.Update(_hleInputStates);' in update, 'NpadManager.Update no longer makes the calls this fixture repeats')
check('''AnalogStickL = new AnalogStickState
                {
                    X = state.LStick.Dx,
                    Y = state.LStick.Dy,
                },
                AnalogStickR = new AnalogStickState
                {
                    X = state.RStick.Dx,
                    Y = state.RStick.Dy,
                },''' in method(npad_devices, 'private void UpdateInput(GamepadInput state)'), 'HID copy of LStick/RStick changed')
check('DeadzoneLeft     = 0.0f,' in extracted[3] and 'RangeLeft        = 1.0f,' in extracted[3] and
      'Joystick      = ConfigStickInputId.Left,' in extracted[3] and 'Joystick      = ConfigStickInputId.Right,' in extracted[3],
      'controller configuration changed: re-read the expected values below')

PROGRAM = r'''using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using Ryujinx.Common.Configuration.Hid;
using Ryujinx.Common.Configuration.Hid.Controller;
using Ryujinx.HLE.HOS.Services.Hid;
using Ryujinx.Input;
using Ryujinx.Input.HLE;
using Ryujinx.Input.Native;
using Ryujinx.Library;
using PlayerIndex = Ryujinx.Common.Configuration.Hid.PlayerIndex;
using ControllerType = Ryujinx.Common.Configuration.Hid.ControllerType;

int cases = 0;
void Check(bool value, string what) { if (!value) throw new Exception("Stick chain: " + what); cases++; }
var hid = (Hid)RuntimeHelpers.GetUninitializedObject(typeof(Hid)); // UpdateStickButtons reads no instance state.
using var native = new NativeGamepadDriver();
var manager = new InputManager(new NoKeyboard(), native);
var npads = manager.CreateNpadManager();
Library.Prepare(manager, npads);
long generation = Library.Sessions.Prepare();
var controllers = (NpadController[])typeof(NpadManager).GetField("_controllers", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(npads);
var driverUpdate = typeof(NpadManager).GetMethod("DriverConfigurationUpdate", BindingFlags.NonPublic | BindingFlags.Instance);
GamepadInput Poll(PlayerIndex player) {
 // NpadManager.Update for one configured player, without the guest's shared memory.
 var config = Library.Configs.Single(c => c.PlayerIndex == player);
 var controller = controllers[(int)player];
 var args = new object[] { controller, config };
 driverUpdate.Invoke(npads, args); controller = (NpadController)args[0];
 controller.UpdateUserConfiguration(config); controller.Update();
 var state = controller.GetHLEInputState();
 state.Buttons |= hid.UpdateStickButtons(state.LStick, state.RStick);
 return state;
}
unsafe {
 delegate* unmanaged<long, int, nint, int, int> attach = &Library.EmbeddedInputAttach;
 delegate* unmanaged<long, int, int> detach = &Library.EmbeddedInputDetach;
 delegate* unmanaged<long, int, int> reset = &Library.EmbeddedInputReset;
 delegate* unmanaged<long, int, int, int, int> button = &Library.EmbeddedInputButton;
 delegate* unmanaged<long, int, int, float, float, int> stick = &Library.EmbeddedInputStick;
 int Attach(int pad, string name, int player) { var bytes = System.Text.Encoding.UTF8.GetBytes(name + "\0"); fixed (byte* p = bytes) return attach(generation, pad, (nint)p, player); }

 // MeloNXInputRouter.init: pad 1 for the touch overlay and the first controller, player 0.
 Check(Attach(1, "MeloNX touch / player 1", 0) == 0, "attach pad 1");
 var config = (StandardControllerInputConfig)Library.Configs.Single();
 Check(config.Id == "1" && config.PlayerIndex == PlayerIndex.Player1 && config.ControllerType == ControllerType.ProController, "pad 1 is ProController Player1");
 Check(config.DeadzoneLeft == 0 && config.DeadzoneRight == 0 && config.RangeLeft == 1 && config.RangeRight == 1, "deadzone 0, range 1 on both sticks");
 Check(config.LeftJoyconStick.Joystick == Ryujinx.Common.Configuration.Hid.Controller.StickInputId.Left &&
       config.RightJoyconStick.Joystick == Ryujinx.Common.Configuration.Hid.Controller.StickInputId.Right, "stick ids not swapped");
 Console.WriteLine($"config: {config.Id} {config.ControllerType} {config.PlayerIndex} deadzone {config.DeadzoneLeft}/{config.DeadzoneRight} range {config.RangeLeft}/{config.RangeRight}");

 // Rejections the host never sees today (MeloNXRuntimeAPI discarded the code before this lot).
 Check(stick(generation + 1, 1, 1, 1, 0) == 2, "stale generation is refused with 2");
 Check(stick(generation, 1, 3, 1, 0) == 1 && stick(generation, 1, 0, 1, 0) == 1 && stick(generation, 9, 1, 1, 0) == 1, "invalid stick or pad is refused with 1");
 Check(stick(generation, 1, 1, float.NaN, 0) == 1, "NaN refused");
 Check(Poll(PlayerIndex.Player1).LStick.Dx == 0, "refused writes left no state");

 // What MeloNXInputRouter.joystickMoved sends for a touch drag: (x, -y) of Melo-Controller's normalised position,
 // stick 1 = left, 2 = right; values already clamped to [-1, 1] by MeloNXRuntimeAPI.stick.
 var samples = new (string name, float x, float y)[] {
  ("up (finger up, UIKit y -1)", 0f, 1f), ("down", 0f, -1f), ("left", -1f, 0f), ("right", 1f, 0f),
  ("diagonal at the rim (0.848 per axis)", 0.848f, 0.848f), ("half right", 0.5f, 0f), ("just past touch deadzone", 0.0435f, 0f) };
 foreach (var sample in samples) {
  Check(stick(generation, 1, 1, sample.x, sample.y) == 0, "left stick accepted: " + sample.name);
  var state = Poll(PlayerIndex.Player1);
  Console.WriteLine($"left  {sample.name,-38} in ({sample.x,7:F4},{sample.y,7:F4}) -> LStick ({state.LStick.Dx,6},{state.LStick.Dy,6}) RStick ({state.RStick.Dx},{state.RStick.Dy}) stick buttons 0x{(ulong)state.Buttons:X}");
  double length = Math.Sqrt(sample.x * sample.x + sample.y * sample.y);
  double scale = length > 1 ? 1 / length : 1;
  Check(Math.Abs(state.LStick.Dx - sample.x * scale * short.MaxValue) <= 2 && Math.Abs(state.LStick.Dy - sample.y * scale * short.MaxValue) <= 2,
        "left value reaches LStick unchanged (clamped to the circle): " + sample.name);
  Check(state.RStick.Dx == 0 && state.RStick.Dy == 0, "left write leaves RStick at rest");
 }
 // The right stick is independent and does not disturb the held left value.
 Check(stick(generation, 1, 1, 0f, 1f) == 0 && stick(generation, 1, 2, -1f, 0f) == 0, "both sticks");
 var both = Poll(PlayerIndex.Player1);
 Console.WriteLine($"both  left up + right left -> LStick ({both.LStick.Dx},{both.LStick.Dy}) RStick ({both.RStick.Dx},{both.RStick.Dy}) stick buttons 0x{(ulong)both.Buttons:X}");
 Check(both.LStick.Dy == short.MaxValue && both.LStick.Dx == 0 && both.RStick.Dx == -short.MaxValue, "left and right held together");
 Check((both.Buttons & ControllerKeys.LStickUp) != 0 && (both.Buttons & ControllerKeys.RStickLeft) != 0, "stick direction buttons");
 // A button press while the stick is held (move and cast) leaves the stick untouched.
 Check(button(generation, 1, 0, 1) == 0, "A pressed");
 var casting = Poll(PlayerIndex.Player1);
 Check((casting.Buttons & ControllerKeys.A) != 0 && casting.LStick.Dy == short.MaxValue, "button press keeps the left stick");
 Check(button(generation, 1, 0, 0) == 0, "A released");
 // A second physical controller (MeloNXInputRouter.reconnect, slot 2 player 1) does not move Player1's sticks.
 Check(Attach(2, "Second controller", 1) == 0, "attach pad 2");
 Check(Library.Configs.Count == 2 && Library.Configs.Any(c => c.Id == "2" && c.PlayerIndex == PlayerIndex.Player2), "pad 2 is Player2");
 Check(Poll(PlayerIndex.Player1).LStick.Dy == short.MaxValue && Poll(PlayerIndex.Player2).LStick.Dy == 0, "pad 2 attach keeps Player1 left stick");
 Check(stick(generation, 2, 1, 1f, 0f) == 0 && Poll(PlayerIndex.Player1).LStick.Dx == 0 && Poll(PlayerIndex.Player2).LStick.Dx == short.MaxValue, "pad 2 left stick goes to Player2 only");
 Check(detach(generation, 2) == 0 && Library.Configs.Count == 1, "detach pad 2");
 Check(Poll(PlayerIndex.Player1).LStick.Dy == short.MaxValue, "pad 2 detach keeps Player1");
 // Pause and resume (MeloNXInputRouter.suspend) reset the pad; the next value is accepted again.
 Check(reset(generation, 1) == 0, "reset");
 var cleared = Poll(PlayerIndex.Player1);
 Check(cleared.LStick.Dx == 0 && cleared.LStick.Dy == 0 && cleared.RStick.Dx == 0 && cleared.Buttons == 0, "reset clears both sticks and buttons");
 Check(stick(generation, 1, 1, -1f, 0f) == 0 && Poll(PlayerIndex.Player1).LStick.Dx == -short.MaxValue, "left stick re-armed after reset");
 // After the session stops, writes are refused with 2 (the host counted none of these before this lot).
 Check(Library.Sessions.Stop(generation), "stop");
 Check(stick(generation, 1, 1, 1f, 0f) == 2 && button(generation, 1, 0, 1) == 2, "writes refused after stop");
}
Console.WriteLine($"Stick chain: {cases} cases passed.");

sealed class NoKeyboard : IGamepadDriver {
 public string DriverName => "none";
 public ReadOnlySpan<string> GamepadsIds => ReadOnlySpan<string>.Empty;
 public event Action<string> OnGamepadConnected { add { } remove { } }
 public event Action<string> OnGamepadDisconnected { add { } remove { } }
 public IGamepad GetGamepad(string id) => null;
 public IEnumerable<IGamepad> GetGamepads() => Array.Empty<IGamepad>();
 public void Dispose() { }
}
'''

SHIM = '''using System;
using System.Collections.Generic;
using System.Threading;
using Ryujinx.Common.Configuration.Hid;
using Ryujinx.Common.Configuration.Hid.Controller;
using Ryujinx.Common.Configuration.Hid.Controller.Motion;
using Ryujinx.Common.Configuration.Hid.Keyboard;
using Ryujinx.Common.Logging;
using Ryujinx.Input;
using Ryujinx.Input.HLE;
using Ryujinx.Input.Native;
using System.Runtime.InteropServices;
using ConfigGamepadInputId = Ryujinx.Common.Configuration.Hid.Controller.GamepadInputId;
using ConfigStickInputId = Ryujinx.Common.Configuration.Hid.Controller.StickInputId;

namespace Ryujinx.Library;

sealed class FixtureWindow { public NpadManager NpadManager; }

partial class Library
{
    private static readonly EmbeddedSessionCoordinator EmbeddedSessions = new();
    private static InputManager _inputManager;
    private static List<InputConfig> _inputConfiguration;
    private static readonly Lock inputConfigurationLock = new();
    private static bool _enableKeyboard = true;
    private static bool _enableMouse = false;
    private static FixtureWindow _window;
    internal static EmbeddedSessionCoordinator Sessions => EmbeddedSessions;
    internal static List<InputConfig> Configs => _inputConfiguration;
    internal static void Prepare(InputManager manager, NpadManager npads) { _inputManager = manager; _window = new FixtureWindow { NpadManager = npads }; }
    // Keyboard fallback only (never selected for pad ids); the production one reads the host's key table.
    public static StandardKeyboardInputConfig KeyboardInputConfig() => new() { Id = "0", PlayerIndex = PlayerIndex.Player1, ControllerType = ControllerType.JoyconPair };

''' + '\n\n'.join(extracted) + '''
}
'''


def build(artifacts):
    project = source / 'src/Ryujinx.Input.Native/Ryujinx.Input.Native.csproj'
    subprocess.run(['dotnet', 'build', str(project), '-c', 'Release', '--artifacts-path', str(artifacts), '-p:NuGetAudit=false',
                    '-nologo', '-v', 'quiet'], check=True, timeout=1800, capture_output=True, text=True)
    return artifacts / 'bin/Ryujinx.Input.Native/release'


with tempfile.TemporaryDirectory(prefix='melonx-stick-chain-') as temporary:
    work = Path(temporary)
    output = reuse / 'bin/Ryujinx.Input.Native/release' if reuse and (reuse / 'bin/Ryujinx.Input.Native/release').exists() else build(reuse or work / 'artifacts')
    fixture = work / 'fixture'
    fixture.mkdir()
    for name in ('EmbeddedInput.cs', 'EmbeddedSessionCoordinator.cs'):
        shutil.copyfile(ROOT / 'native/melonx' / name, fixture / name)
    (fixture / 'LibraryInput.cs').write_text(SHIM)
    (fixture / 'Program.cs').write_text(PROGRAM)
    references = ''.join(f'<Reference Include="{dll.stem}"><HintPath>{dll}</HintPath></Reference>'
                         for dll in sorted(output.glob('*.dll')))
    (fixture / 'Fixture.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS8632;CS0169;CS0414</NoWarn></PropertyGroup>
<ItemGroup>{references}</ItemGroup></Project>''')
    result = subprocess.run(['dotnet', 'run', '--project', str(fixture / 'Fixture.csproj'), '-c', 'Release'],
                            capture_output=True, text=True, timeout=600)
    print(result.stdout, end='')
    check(result.returncode == 0, 'fixture failed:\n' + result.stdout[-3000:] + result.stderr[-3000:])
    check('Configuring 1 as ProController (Player1)' in result.stdout, 'the production configuration line was not printed')
    passed = re.search(r'Stick chain: (\d+) cases passed\.', result.stdout)
    check(passed is not None, 'fixture summary missing')

out = ROOT / 'dist/melonx/stick-chain-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
inputs = ['src/Ryujinx.Library/Library.cs', 'src/Ryujinx.Input/HLE/NpadManager.cs', 'src/Ryujinx.Input/HLE/NpadController.cs',
          'src/Ryujinx.Input.Native/NativeGamepad.cs', 'src/Ryujinx.Input.Native/NativeGamepadDriver.cs',
          'src/Ryujinx.HLE/HOS/Services/Hid/HidDevices/NpadDevices.cs']
out.write_text(json.dumps(dict(
    coreInputs={p: hashlib.sha256((source / p).read_bytes()).hexdigest() for p in inputs},
    hostInputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                ['native/melonx/EmbeddedInput.cs', 'native/melonx/EmbeddedSessionCoordinator.cs', 'test/melonx_stick_chain_test.py']},
    staticChecks=checks, fixtureCases=int(passed.group(1)), result=result.stdout.strip().splitlines(),
    executed='prepared Core input projects built and run on .NET; HID shared memory and the guest not executed'), indent=2) + '\n')
print(f'PASS {checks} static checks; fixture {passed.group(1)} cases')
