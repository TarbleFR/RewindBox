using System;
using System.Runtime.InteropServices;
using Ryujinx.Common.Configuration.Hid;
using Ryujinx.Input.Native;

namespace Ryujinx.Library;

partial class Library
{
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_input_abi")]
    public static int EmbeddedInputAbi() => 1;

    private static int EmbeddedInputAction(long generation, int pad, Action action)
    {
        if (pad < 1 || pad > 8) return 1;
        try { return EmbeddedSessions.WithInputs(generation, action) ? 0 : 2; }
        catch (Exception error) { Console.Error.WriteLine(error); return 3; }
    }

    // Pad IDs are small stable slot tokens, never foreign object pointers.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_input_attach")]
    public static int EmbeddedInputAttach(long generation, int pad, nint nameUtf8, int player)
    {
        if (player < 0 || player > 7 || nameUtf8 == 0) return 1;
        return EmbeddedInputAction(generation, pad, () =>
        {
            string name = Marshal.PtrToStringUTF8(nameUtf8);
            if (string.IsNullOrWhiteSpace(name) || name.Length > 256) throw new ArgumentException("Invalid pad name.");
            if (AttachGamepadCore(name, (nint)pad, player, ControllerType.ProController) == 0)
                throw new InvalidOperationException("Cannot attach controller.");
        });
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_input_detach")]
    public static int EmbeddedInputDetach(long generation, int pad) =>
        EmbeddedInputAction(generation, pad, () => DetachGamepadCore((nint)pad));

    // Button indices follow the original MeloNX 17-button native mapping.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_input_button")]
    public static int EmbeddedInputButton(long generation, int pad, int button, int pressed)
    {
        if (button < 0 || button > 16 || (pressed != 0 && pressed != 1)) return 1;
        return EmbeddedInputAction(generation, pad, () => NativeGamepadDriver.SetButtonState((nint)pad, button, (byte)pressed));
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_input_stick")]
    public static int EmbeddedInputStick(long generation, int pad, int stick, float x, float y)
    {
        if ((stick != 1 && stick != 2) || !float.IsFinite(x) || !float.IsFinite(y)) return 1;
        return EmbeddedInputAction(generation, pad, () => NativeGamepadDriver.SetStickAxis((nint)pad, stick, x, y));
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_input_reset")]
    public static int EmbeddedInputReset(long generation, int pad) =>
        EmbeddedInputAction(generation, pad, () => NativeGamepadDriver.ResetState((nint)pad));
}
