// adapt_npad_config_snapshot: the real Ryujinx.Input NpadManager of one engine (control or candidate), driven with the
// library's own sequences of list changes (Ryujinx.Library AttachGamepadCore, DetachGamepadCore, EnsureKeyboardFallback,
// the session's Clear) and with a driver double. Prints one JSON line per scene.
//
// Scenes:
//   interleaved <op>   the manager enumerates its configuration (UnblockInputUpdates, under its lock, as Update does on
//                      every frame); inside that enumeration (the driver's Clear, called from the loop body) the fixture
//                      waits until another thread has made the library's change to the library's list (outside the
//                      manager's lock, as the library does) and has started the ReloadConfiguration that follows it;
//                      the enumeration then resumes. The outcome is what the enumeration threw, if anything.
//   sequential <op>    the same operations one after the other, nothing interleaved: the reference outcome.
//   sequence <steps> <seed>  a seeded script of attaches, detaches, absent pads, keyboard fallbacks and driver
//                      connect/disconnect events, each applied as the library applies it; a digest after every step.
// Nothing here measures or compares a duration; the only waits are on events, with a bound that fails the run.
using Ryujinx.Common.Configuration.Hid;
using Ryujinx.Common.Configuration.Hid.Controller;
using Ryujinx.Common.Configuration.Hid.Controller.Motion;
using Ryujinx.Common.Configuration.Hid.Keyboard;
using Ryujinx.Input;
using Ryujinx.Input.HLE;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using StickInputId = Ryujinx.Input.StickInputId;

sealed class FakePad : IGamepad
{
    readonly FakeDriver _driver;
    public FakePad(string id, FakeDriver driver) { Id = id; _driver = driver; }
    public GamepadFeaturesFlag Features => GamepadFeaturesFlag.None;
    public string Id { get; }
    public string Name => "fixture " + Id;
    public bool IsConnected => true;
    public bool IsPressed(GamepadButtonInputId inputId) => false;
    public (float, float) GetStick(StickInputId inputId) => (0, 0);
    public Vector3 GetMotionData(MotionInputId inputId) => Vector3.Zero;
    public void SetTriggerThreshold(float triggerThreshold) { }
    public void SetConfiguration(InputConfig configuration) => _driver.Log.Add("config " + Id + " " + configuration.PlayerIndex);
    public void SetLed(uint packedRgb) { }
    public void Rumble(float lowFrequency, float highFrequency, uint durationMs) { }
    public GamepadStateSnapshot GetMappedStateSnapshot() => default;
    public GamepadStateSnapshot GetStateSnapshot() => default;
    public void Dispose() => _driver.Log.Add("dispose " + Id);
}

sealed class FakeDriver : IGamepadDriver
{
    public readonly SortedSet<string> Present = new(StringComparer.Ordinal);
    public readonly List<string> Log = [];
    public Action InsideEnumeration;
    public FakeDriver(string name) { DriverName = name; }
    public string DriverName { get; }
    public ReadOnlySpan<string> GamepadsIds => Present.ToArray();
    public event Action<string> OnGamepadConnected;
    public event Action<string> OnGamepadDisconnected;
    public void Connect(string id) { Present.Add(id); OnGamepadConnected?.Invoke(id); }
    public void Disconnect(string id) { Present.Remove(id); OnGamepadDisconnected?.Invoke(id); }
    public IGamepad GetGamepad(string id)
    {
        Log.Add("open " + id + (Present.Contains(id) ? "" : " absent"));
        return Present.Contains(id) ? new FakePad(id, this) : null;
    }
    public IEnumerable<IGamepad> GetGamepads() => Present.Select(id => (IGamepad)new FakePad(id, this)).ToArray();
    public void Clear()
    {
        Log.Add("clear");
        Action inside = InsideEnumeration;
        InsideEnumeration = null;
        inside?.Invoke();
    }
    public void Dispose() { }
}

static class Program
{
    const int MaxControllers = 9;
    static readonly TimeSpan Bound = TimeSpan.FromSeconds(60);
    static readonly FieldInfo ControllersField = typeof(NpadManager).GetField("_controllers", BindingFlags.Instance | BindingFlags.NonPublic);
    static readonly FieldInfo ConfigField = typeof(NpadManager).GetField("_inputConfig", BindingFlags.Instance | BindingFlags.NonPublic);
    static readonly FieldInfo BlockedField = typeof(NpadManager).GetField("_blockInputUpdates", BindingFlags.Instance | BindingFlags.NonPublic);

    static InputConfig Pad(string id, PlayerIndex player) => new StandardControllerInputConfig
    {
        Version = InputConfig.CurrentVersion, Backend = InputBackendType.GamepadSDL2, Id = id, Name = "fixture " + id,
        ControllerType = ControllerType.ProController, PlayerIndex = player,
        Motion = new StandardMotionConfigController { MotionBackend = MotionInputBackendType.GamepadDriver, EnableMotion = false },
    };

    // Library.KeyboardInputConfig: the fallback for Player1 when the list is empty (EnsureKeyboardFallback).
    static InputConfig Keyboard() => new StandardKeyboardInputConfig
    {
        Version = InputConfig.CurrentVersion, Backend = InputBackendType.WindowKeyboard, Id = "0", Name = "keyboard",
        ControllerType = ControllerType.ProController, PlayerIndex = PlayerIndex.Player1,
    };

    sealed class Rig
    {
        public readonly FakeDriver Keyboards = new("keyboard"), Gamepads = new("gamepad"), Mice = new("mouse");
        public readonly NpadManager Manager;
        public readonly List<InputConfig> Library = [];   // Library._inputConfiguration
        public Rig()
        {
            Keyboards.Present.Add("0");
            Manager = new NpadManager(Keyboards, Gamepads, Mice);
        }

        public void EnsureKeyboardFallback()
        {
            if (Library.Count > 0) return;
            Library.Add(Keyboard());
        }

        // AttachGamepadCore, from its RemoveAll: the list is changed, then the manager is given it.
        public void Attach(string id, PlayerIndex player)
        {
            Library.RemoveAll(c => c.PlayerIndex == player || c.Id == id);
            Library.Add(Pad(id, player));
            EnsureKeyboardFallback();
            Manager.ReloadConfiguration(Library, false, false);
        }

        // DetachGamepadCore, from its RemoveAll.
        public void Detach(string id)
        {
            int removed = Library.RemoveAll(c => c.Id == id);
            if (removed > 0)
            {
                EnsureKeyboardFallback();
                Manager.ReloadConfiguration(Library, false, false);
            }
        }

        public Dictionary<string, object> Digest()
        {
            NpadController[] controllers = (NpadController[])ControllersField.GetValue(Manager);
            List<InputConfig> owned = (List<InputConfig>)ConfigField.GetValue(Manager);
            return new Dictionary<string, object>
            {
                ["controllers"] = controllers.Select(c => c == null ? "-" : c.Id + "@" + c.GamepadDriver?.DriverName).ToArray(),
                ["byPlayer"] = Enumerable.Range(0, MaxControllers).Select(i => Manager.GetPlayerInputConfigByIndex(i)?.Id ?? "-").ToArray(),
                ["config"] = owned.Select(c => c.Id + ":" + c.PlayerIndex + ":" + c.GetType().Name).ToArray(),
                ["blocked"] = (bool)BlockedField.GetValue(Manager),
                ["driverLog"] = Gamepads.Log.Concat(Keyboards.Log.Select(e => "kb " + e)).ToArray(),
            };
        }

        public bool SharesLibraryList => ReferenceEquals(ConfigField.GetValue(Manager), Library);
        public bool HoldsLibraryEntries => ((List<InputConfig>)ConfigField.GetValue(Manager)).SequenceEqual(Library);
    }

    // The library's change for one operation, made to the library's list only (the manager's reload follows).
    static void Change(Rig rig, string op)
    {
        switch (op)
        {
            case "detach": rig.Library.RemoveAll(c => c.Id == "B"); rig.EnsureKeyboardFallback(); break;
            case "attach": rig.Gamepads.Present.Add("D"); rig.Library.RemoveAll(c => c.PlayerIndex == PlayerIndex.Player2 || c.Id == "D");
                           rig.Library.Add(Pad("D", PlayerIndex.Player2)); rig.EnsureKeyboardFallback(); break;
            case "detachLast": rig.Library.RemoveAll(c => c.Id != "A"); rig.Library.RemoveAll(c => c.Id == "A"); rig.EnsureKeyboardFallback(); break;
            case "clear": rig.Library.Clear(); break;   // the session's end (EmbeddedPrepare, LoadApplicationOwned); no reload follows
            default: throw new ArgumentException(op);
        }
    }

    static Rig Opened()
    {
        Rig rig = new();
        foreach (string id in new[] { "A", "B", "C" }) rig.Gamepads.Present.Add(id);
        rig.Attach("A", PlayerIndex.Player1);
        rig.Attach("B", PlayerIndex.Player2);
        rig.Attach("C", PlayerIndex.Player3);
        rig.Manager.BlockInputUpdates();
        rig.Gamepads.Log.Clear();
        rig.Keyboards.Log.Clear();
        return rig;
    }

    static string Describe(Exception error) => error == null ? null : error.GetType().FullName + ": " + error.Message;

    static Dictionary<string, object> Interleaved(string op)
    {
        Rig rig = Opened();
        using ManualResetEventSlim inside = new(), changed = new();
        Exception enumeration = null, reload = null;
        rig.Gamepads.InsideEnumeration = () =>
        {
            inside.Set();
            if (!changed.Wait(Bound)) throw new TimeoutException("the library's change did not happen");
        };
        Thread frame = new(() => { try { rig.Manager.UnblockInputUpdates(); } catch (Exception error) { enumeration = error; } }) { Name = "frame" };
        frame.Start();
        if (!inside.Wait(Bound)) throw new TimeoutException("the enumeration did not start");
        Change(rig, op);
        // The library calls ReloadConfiguration right after its change, on its own thread: it waits for the manager's
        // lock, which the enumeration holds.
        // The session's Clear is followed by no reload (the window ends with the session).
        Thread library = new(() => { try { if (op != "clear") rig.Manager.ReloadConfiguration(rig.Library, false, false); } catch (Exception error) { reload = error; } }) { Name = "library" };
        library.Start();
        changed.Set();
        if (!frame.Join(Bound) || !library.Join(Bound)) throw new TimeoutException("a thread did not end");
        Dictionary<string, object> result = new()
        {
            ["scene"] = "interleaved", ["op"] = op, ["enumerationError"] = Describe(enumeration), ["reloadError"] = Describe(reload),
            ["digest"] = rig.Digest(), ["sharesLibraryList"] = rig.SharesLibraryList, ["holdsLibraryEntries"] = rig.HoldsLibraryEntries,
        };
        return result;
    }

    static Dictionary<string, object> Sequential(string op)
    {
        Rig rig = Opened();
        Exception enumeration = null, reload = null;
        try { rig.Manager.UnblockInputUpdates(); } catch (Exception error) { enumeration = error; }
        Change(rig, op);
        try { if (op != "clear") rig.Manager.ReloadConfiguration(rig.Library, false, false); } catch (Exception error) { reload = error; }
        return new Dictionary<string, object>
        {
            ["scene"] = "sequential", ["op"] = op, ["enumerationError"] = Describe(enumeration), ["reloadError"] = Describe(reload),
            ["digest"] = rig.Digest(), ["sharesLibraryList"] = rig.SharesLibraryList, ["holdsLibraryEntries"] = rig.HoldsLibraryEntries,
        };
    }

    static Dictionary<string, object> Sequence(int steps, int seed)
    {
        Random random = new(seed);
        Rig rig = new();
        string[] ids = ["A", "B", "C", "D", "E", "F"];
        foreach (string id in ids.Take(4)) rig.Gamepads.Present.Add(id);
        List<Dictionary<string, object>> trace = [];
        Dictionary<string, int> kinds = [];
        for (int step = 0; step < steps; step++)
        {
            string kind;
            int pick = random.Next(100);
            string id = ids[random.Next(ids.Length)];
            PlayerIndex player = (PlayerIndex)random.Next(9);
            if (pick < 40) { kind = rig.Gamepads.Present.Contains(id) ? "attach" : "attachAbsent"; rig.Attach(id, player); }
            else if (pick < 70) { kind = rig.Library.Any(c => c.Id == id) ? "detach" : "detachUnknown"; rig.Detach(id); }
            else if (pick < 80) { kind = "driverDisconnect"; rig.Gamepads.Disconnect(id); }
            else if (pick < 90) { kind = "driverConnect"; rig.Gamepads.Connect(id); }
            else if (pick < 95) { kind = "unblock"; rig.Manager.BlockInputUpdates(); rig.Manager.UnblockInputUpdates(); }
            else { kind = "detachAll"; foreach (string each in rig.Library.Select(c => c.Id).ToArray()) rig.Detach(each); }
            kinds[kind] = kinds.GetValueOrDefault(kind) + 1;
            Dictionary<string, object> digest = rig.Digest();
            trace.Add(new Dictionary<string, object>
            {
                ["i"] = step, ["k"] = kind, ["d"] = digest, ["shares"] = rig.SharesLibraryList, ["holds"] = rig.HoldsLibraryEntries,
            });
            rig.Gamepads.Log.Clear();
            rig.Keyboards.Log.Clear();
        }
        return new Dictionary<string, object>
        {
            ["scene"] = "sequence", ["seed"] = seed, ["kinds"] = kinds, ["steps"] = trace,
        };
    }

    static int Main(string[] args)
    {
        Dictionary<string, object> result = args[0] switch
        {
            "interleaved" => Interleaved(args[1]),
            "sequential" => Sequential(args[1]),
            "sequence" => Sequence(int.Parse(args[1]), int.Parse(args[2])),
            _ => throw new ArgumentException(args[0]),
        };
        Console.WriteLine(JsonSerializer.Serialize(result));
        return 0;
    }
}
