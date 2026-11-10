"""Bounded native input ownership edits against the exact pinned source."""
from adapt_session import once


def apply(source):
    library = source / 'src/Ryujinx.Library/Library.cs'
    once(library, '''            string name = Marshal.PtrToStringAnsi(namePtr);
            string inputId = idPtr.ToInt64().ToString("X");''', '''            return AttachGamepadCore(Marshal.PtrToStringAnsi(namePtr), idPtr, playerIndex, controllerType);
        }

        private static nint AttachGamepadCore(string name, nint idPtr, int playerIndex, ControllerType controllerType)
        {
            string inputId = idPtr.ToInt64().ToString("X");''')
    once(library, '''        public static void DetachGamepad(nint idPtr)
        {
            lock (inputConfigurationLock)''', '''        public static void DetachGamepad(nint idPtr) => DetachGamepadCore(idPtr);

        private static void DetachGamepadCore(nint idPtr)
        {
            lock (inputConfigurationLock)''')
    once(library, '''            EnsureKeyboardFallback();

            Logger.SetEnable''', '''            lock (inputConfigurationLock) EnsureKeyboardFallback();

            Logger.SetEnable''')
    driver = source / 'src/Ryujinx.Input.Native/NativeGamepadDriver.cs'
    once(driver, '                    yield return gamepad;', '                    yield return new EmbeddedNativeGamepadLease(gamepad);')
    once(driver, '                    return gamepad;', '                    return new EmbeddedNativeGamepadLease(gamepad);')
    once(driver, '                return _gamepads.Values.FirstOrDefault(g => g.Id == id);', '''                var pad = _gamepads.Values.FirstOrDefault(g => g.Id == id);
                return pad == null ? null : new EmbeddedNativeGamepadLease(pad);''')
    pad = source / 'src/Ryujinx.Input.Native/NativeGamepad.cs'
    once(pad, '''        public GamepadStateSnapshot GetStateSnapshot()
        {
            return IGamepad.GetStateSnapshot(this);
        }''', '''        public GamepadStateSnapshot GetStateSnapshot()
        {
            // NpadManager polls this up to once per millisecond. Copy the state
            // under one lock instead of reacquiring it for every button/axis;
            // an input update cannot split the snapshot across two states.
            lock (_stateLock)
            {
                GamepadStateSnapshot snapshot = default;
                snapshot.SetStick(StickInputId.Left, _stickStates[0], _stickStates[1]);
                snapshot.SetStick(StickInputId.Right, _stickStates[2], _stickStates[3]);

                for (GamepadButtonInputId inputId = GamepadButtonInputId.A; inputId < GamepadButtonInputId.Count; inputId++)
                {
                    snapshot.SetPressed(inputId, _buttonStates[(int)inputId]);
                }

                return snapshot;
            }
        }''')
    once(pad, '''                int size = Marshal.SizeOf(typeof(RumbleData));
                nint ptr = Marshal.AllocHGlobal(size);
                try\x20
                {
                    Marshal.StructureToPtr(rumbleData, ptr, false);
                    CallbackRegistry.Invoke($"rumble-{Id}", (byte*)ptr, size);
                }\x20
                finally
                {
                    Marshal.FreeHGlobal(ptr);
                }''', '''                // CallbackRegistry consumes this borrowed buffer synchronously
                // (and copies it for a managed callback). RumbleData is packed
                // and unmanaged, so its stack bytes are already the native ABI.
                CallbackRegistry.Invoke($"rumble-{Id}", (byte*)&rumbleData, sizeof(RumbleData));''')
    return [driver, pad]
