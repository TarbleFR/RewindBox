"""The controller manager keeps its own copy of the input configuration list instead of the library's.

IPA 726 (12 Nov; private journals, not in the repository): closing a Switch game ended with
`System.InvalidOperationException: Collection was modified; enumeration operation may not execute.` at
Ryujinx.Input.HLE.NpadManager.Update, on the window's main loop, two seconds after the host began the close. The
engine therefore could not prove that the session had ended (EmbeddedSessionCoordinator state 4, "Session termination
is unproven"), the close was quarantined and every later launch was refused until RewindBox was restarted, whatever
the engine (Black Ops II on PS3 in that report).

Mechanism (upstream MeloNX): Ryujinx.Library keeps the controllers in one List<InputConfig> (_inputConfiguration) and
hands that same object to NpadManager (WindowBase.Initialize, then ReloadConfiguration at every attach and detach),
which stores it as its own `_inputConfig` and enumerates it under its own lock on every frame (Update), and in
RefreshInputConfigForHLE, UnblockInputUpdates and GetPlayerInputConfigByIndex. The library changes the list under a
different lock (inputConfigurationLock): AttachGamepadCore and DetachGamepadCore call RemoveAll and Add on it before
they call ReloadConfiguration, so the change happens while the frame's enumeration may be in progress. The host
detaches its pads when a session closes (MeloNXInputRouter.close) while the engine's main loop still runs: List's
version check then throws in the middle of Update. The window of time is a few microseconds per frame, which is why
the failure is rare and does not depend on the game.

Change (NpadManager.cs only; every title): ReloadConfiguration copies the list it is given, under the manager's lock,
reads its entries from that copy and keeps the copy. Every enumeration of the manager then reads a list that only the
manager creates and nothing else can change. Every caller already passes the complete list each time it changes it
(the library after each attach and detach; the manager itself, with its own list, on a driver's connect and
disconnect), so the configuration the manager applies is the same, entry for entry and in the same order. Not changed:
the library, its lock, the order of its calls, and the copy's absence of effect on the library's list.

Not a way of hiding the failure: no exception is caught or reclassified here; the race no longer exists. Proof:
test/melonx_npad_config_snapshot_test.py on the real NpadManager (the control throws the same exception in the same
interleaving, the candidate never does, and both assign the same controllers). Fail closed on drift: the file must be
the Core 735 preparation's (upstream; no other adapter edits it).
"""
import hashlib
from adapt_session import once

NPAD = 'src/Ryujinx.Input/HLE/NpadManager.cs'
BASELINE = {
    NPAD: '0e54f0fad2439e189ad401160228a99da4aedfc2df8a0610e6175daa02409dd5',
}
MARKER = 'RewindBox (adapt_npad_config_snapshot)'

RELOAD_OLD = '''        public void ReloadConfiguration(List<InputConfig> inputConfig, bool enableKeyboard, bool enableMouse)
        {
            lock (_lock)
            {
                NpadController[] oldControllers = _controllers.ToArray();

                List<InputConfig> validInputs = [];

                foreach (InputConfig inputConfigEntry in inputConfig)
                {'''
RELOAD_NEW = '''        public void ReloadConfiguration(List<InputConfig> inputConfig, bool enableKeyboard, bool enableMouse)
        {
            lock (_lock)
            {
                // RewindBox (adapt_npad_config_snapshot): the manager reads and keeps its own copy. The caller's list is
                // the library's, which it changes under another lock (attach, detach) while Update enumerates.
                List<InputConfig> ownedConfig = new(inputConfig);

                NpadController[] oldControllers = _controllers.ToArray();

                List<InputConfig> validInputs = [];

                foreach (InputConfig inputConfigEntry in ownedConfig)
                {'''
STORE_OLD = '''                _inputConfig = inputConfig;
                _enableKeyboard = enableKeyboard;'''
STORE_NEW = '''                _inputConfig = ownedConfig;
                _enableKeyboard = enableKeyboard;'''
PAIRS = [(NPAD, RELOAD_OLD, RELOAD_NEW), (NPAD, STORE_OLD, STORE_NEW)]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
