using System.Numerics;
using System.Threading;
using Ryujinx.Common.Configuration.Hid;

namespace Ryujinx.Input.Native;

// GetGamepad opens a consumer handle. Only the driver owns the connection.
// Disposing a configuration probe/Npad handle must not unplug that connection.
internal sealed class EmbeddedNativeGamepadLease : IGamepad, IHighDefinitionRumbleGamepad
{
    private readonly NativeGamepad _pad;
    private int _closed;
    internal EmbeddedNativeGamepadLease(NativeGamepad pad) { _pad = pad; }
    public string Id => _pad.Id;
    public string Name => _pad.Name;
    public GamepadFeaturesFlag Features => _pad.Features;
    public bool IsConnected => Volatile.Read(ref _closed) == 0 && _pad.IsConnected;
    public bool IsPressed(GamepadButtonInputId id) => IsConnected && _pad.IsPressed(id);
    public (float, float) GetStick(StickInputId id) => IsConnected ? _pad.GetStick(id) : (0, 0);
    public Vector3 GetMotionData(MotionInputId id) => IsConnected ? _pad.GetMotionData(id) : Vector3.Zero;
    public void SetTriggerThreshold(float threshold) { if (IsConnected) _pad.SetTriggerThreshold(threshold); }
    public void SetConfiguration(InputConfig config) { if (IsConnected) _pad.SetConfiguration(config); }
    public void SetLed(uint color) { if (IsConnected) _pad.SetLed(color); }
    public GamepadStateSnapshot GetStateSnapshot() => IGamepad.GetStateSnapshot(this);
    public GamepadStateSnapshot GetMappedStateSnapshot() => GetStateSnapshot();
    public void Rumble(float low, float high, uint duration) { if (IsConnected) _pad.Rumble(low, high, duration); }
    public void Rumble(GamepadVibrationValue left, GamepadVibrationValue right, uint duration)
    { if (IsConnected) _pad.Rumble(left, right, duration); }
    public void Dispose() => Interlocked.Exchange(ref _closed, 1);
}
