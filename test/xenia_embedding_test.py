#!/usr/bin/env python3
"""What XeniOS's app layer does for a running game, RewindBox's embedding does.

XeniOS's app layer (src/xenia/ui/ios/app/ios_app_delegate.mm and its view
controllers) is not compiled into XeniaCore. Every IOSWindowedAppContext
callback it installs is either installed by the facade
(packages/xenia_internal_bridge/core/XeniaCore.mm) or listed below with the
reason it is not needed; a new upstream app-layer callback fails this test
until it is decided. Device findings it guards: the title screen that never
passed START (no profile, sign-in prompt answered as cancelled), guest prompts
presented on a controller in no window, no rumble, a pad drop that let the
game run, edge swipes that left the game.

Usage: test/xenia_embedding_test.py [--upstream <XeniOS checkout>]
"""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = None
if '--upstream' in sys.argv:
    index = sys.argv.index('--upstream')
    UPSTREAM = Path(sys.argv[index + 1])
    del sys.argv[index:index + 2]

CORE = ROOT / 'packages/xenia_internal_bridge/core/XeniaCore.mm'
INPUT = ROOT / 'packages/xenia_internal_bridge/core/XeniaCoreInput.h'
BRIDGE = ROOT / 'packages/xenia_internal_bridge/ios/Classes/XeniaInternalBridgePlugin.mm'
PODSPEC = ROOT / 'packages/xenia_internal_bridge/ios/xenia_internal_bridge.podspec'

# App-layer callbacks the facade installs.
FACADE_SETS = {
    'set_metal_view', 'set_view_controller', 'set_game_exited_callback',
    'set_game_launch_failed_callback', 'set_game_stop_stuck_callback',
    'set_signin_ui_prompt_callback', 'set_message_box_prompt_callback',
    'set_keyboard_prompt_callback',
}
# App-layer callbacks left unset, and why (an unset one answers its prompt as
# cancelled at once, which is what the title gets from a declined dialog).
NOT_NEEDED = {
    'set_achievement_notification_callback': 'no achievement toasts in RewindBox yet',
    'set_achievements_ui_prompt_callback': 'no achievements screen; the guest gets a cancel',
    'set_gamer_card_ui_prompt_callback': 'no Live profiles; the guest gets a cancel',
    'set_online_panel_prompt_callback': 'XeniOS online services are off in the embedding',
    'set_profile_services_ready_callback': 'only refreshes XeniOS profile UI',
    'set_touch_runtime_model': 'RewindBox has its own touch controls (XeniaTouchControls)',
}


class FacadeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = CORE.read_text()
        cls.input = INPUT.read_text()
        init = cls.core.index('bool InitializeOnMain(std::string* failure) {')
        cls.init = cls.core[init:cls.core.index('\n}\n', init)]

    def test_every_title_prompt_has_an_answer(self):
        for line in (
            'g_context->set_signin_ui_prompt_callback(',
            'g_context->set_message_box_prompt_callback(PromptMessageBox);',
            'g_context->set_keyboard_prompt_callback(PromptKeyboard);',
            'g_vibration_sink = ForwardVibration;',
            'InstallLifecycleObservers();',
        ):
            self.assertIn(line, self.init)
        # Installed before OnInitialize starts the emulator thread.
        self.assertLess(self.init.index('InstallLifecycleObservers();'), self.init.index('g_app->OnInitialize()'))

    def test_a_profile_is_signed_in_without_a_screen(self):
        sign_in = self.core[self.core.index('bool SignInProfileOnMain(uint32_t user_index) {'):]
        sign_in = sign_in[:sign_in.index('\n}\n')]
        for step in ('g_context->ListProfiles()', 'g_context->CreateProfile(gamertag)',
                     'g_context->SignInProfile(xuid, slot)', 'std::string("RewindBox")'):
            self.assertIn(step, sign_in)
        kernel = self.core[self.core.index('void NeoXeniaNotifyKernelReady() {'):]
        self.assertIn('SignInProfileOnMain(0);', kernel[:kernel.index('\n}\n')])
        launched = self.core[self.core.index('void NeoXeniaNotifyTitleLaunched() {'):]
        launched = launched[:launched.index('\n}\n')]
        self.assertIn('SignInProfileOnMain(0);', launched)
        self.assertLess(launched.index('SignInProfileOnMain(0);'), launched.index('SetTitleState(TitleState::kRunning);'))

    def test_guest_prompts_are_shown_on_a_window(self):
        for name in ('bool PromptMessageBox(', 'bool PromptKeyboard('):
            body = self.core[self.core.index(name):]
            body = body[:body.index('\n}\n')]
            self.assertIn('XeniaPresentGuestPrompt(PromptRoot(), alert,', body)
            self.assertNotIn('g_host_controller', body)
            self.assertIn('dispatch_semaphore_wait(done, DISPATCH_TIME_FOREVER);', body)
        root = self.core[self.core.index('UIViewController* PromptRoot() {'):]
        self.assertIn('g_view.window', root[:root.index('\n}\n')])
        stop = self.core[self.core.index('void RequestStop(void) {'):]
        stop = stop[:stop.index('\n}\n')]
        self.assertLess(stop.index('XeniaCancelGuestAlerts(PromptRoot());'), stop.index('TerminateCurrentGame();'))

    def test_rumble_is_forwarded_when_it_changes(self):
        set_state = self.input[self.input.index('X_RESULT SetState(uint32_t user_index, xe::hid::X_INPUT_VIBRATION* vibration)'):]
        set_state = set_state[:set_state.index('\n  }\n')]
        self.assertIn('g_vibration.exchange(packed, std::memory_order_relaxed) != packed && g_vibration_sink', set_state)
        self.assertIn('Emit("vibration", std::to_string(left) + "," + std::to_string(right));', self.core)

    def test_background_holds_until_the_pause_settles(self):
        observers = self.core[self.core.index('void InstallLifecycleObservers() {'):]
        observers = observers[:observers.index('\n}\n')]
        for step in ('UIApplicationDidEnterBackgroundNotification', 'IOSAudioSessionNoteBackgrounded()',
                     'beginBackgroundTaskWithName', 'RunWhenEmulationPauseSettled',
                     'UIApplicationDidBecomeActiveNotification', 'IOSAudioSessionRestoreIfNeeded('):
            self.assertIn(step, observers)

    @unittest.skipUnless(UPSTREAM, 'pass --upstream <XeniOS checkout>')
    def test_every_app_layer_callback_is_decided(self):
        header = (UPSTREAM / 'src/xenia/ui/ios/app/windowed_app_context_ios.h').read_text()
        setters = set(re.findall(r'void (set_[a-z_]+)\(', header))
        core_app = (UPSTREAM / 'src/xenia/app/xenia_main_ios.mm').read_text()
        app_layer = {setter for setter in setters if f'{setter}(' not in core_app}
        undecided = app_layer - FACADE_SETS - set(NOT_NEEDED)
        self.assertFalse(undecided, f'app-layer callbacks with no decision: {sorted(undecided)}')
        for setter in FACADE_SETS:
            self.assertIn(f'{setter}(', self.core, setter)


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = BRIDGE.read_text()

    def test_edge_swipes_reach_the_game_first(self):
        self.assertIn('- (UIRectEdge)preferredScreenEdgesDeferringSystemGestures { return UIRectEdgeAll; }',
                      self.bridge)
        self.assertIn('[self setNeedsUpdateOfScreenEdgesDeferringSystemGestures];', self.bridge)

    def test_every_controller_is_read_and_a_drop_pauses(self):
        self.assertNotIn('GCController.current.extendedGamepad', self.bridge)
        poll = self.bridge[self.bridge.index('- (void)pollInput {'):]
        poll = poll[:poll.index('\n}\n')]
        self.assertIn('for (GCController* connected in GCController.controllers) {', poll)
        self.assertIn('controller = XeniaMergePads(controller, XeniaReadPad(pad));', poll)
        self.assertIn('name:GCControllerDidDisconnectNotification', self.bridge)
        drop = self.bridge[self.bridge.index('- (void)controllerDisconnected:(NSNotification*)notification {'):]
        drop = drop[:drop.index('\n}\n')]
        self.assertIn('[self openMenu];', drop)

    def test_rumble_is_played_on_the_pad(self):
        deliver = self.bridge[self.bridge.index('- (void)deliverEvent:(NSString*)event transaction:(uint64_t)transaction message:(NSString*)message {'):]
        deliver = deliver[:deliver.index('\n}\n')]
        self.assertLess(deliver.index('[event isEqualToString:@"vibration"]'),
                        deliver.index('invokeMethod:@"sessionEvent"'))
        self.assertIn('[target.haptics createEngineWithLocality:GCHapticsLocalityDefault]', self.bridge)
        stop = self.bridge[self.bridge.index('- (void)stopInput {'):]
        self.assertIn('[self stopHaptics];', stop[:stop.index('\n}\n')])
        self.assertIn("'CoreHaptics'", PODSPEC.read_text())


if __name__ == '__main__':
    unittest.main()
