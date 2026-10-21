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
    return [driver]
