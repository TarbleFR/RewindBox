#!/usr/bin/env python3
"""First visible Flutter frame after a native game returns, using real bodies.

Compile the production manager, dialog listener, cleanup and route removal in
Flutter. Only emulator/audio/I/O and the unrelated metadata artwork are doubled.
Run the old dialog as a negative control in the same test executable. No cores
or native teardown code are changed or rebuilt for this UI-only regression.
"""
import ast
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from rpcs3_atomic_startup_test import extract_function

ROOT = Path(__file__).resolve().parents[1]
BASE = '9429a1627a2f72dddc07a5fe3c4cda35cdbd7db9'
DIALOG = 'lib/widgets/game_launch_dialog.dart'


def main():
    # Share the existing controllable native/audio dependencies, not its tests.
    tree = ast.parse((ROOT / 'test/game_audio_handoff_test.py').read_text())
    fixture = next(ast.literal_eval(n.value) for n in tree.body
                   if isinstance(n, ast.Assign) and any(
                       isinstance(t, ast.Name) and t.id == 'fixture' for t in n.targets))
    fixture = fixture.replace("import 'package:flutter/widgets.dart';",
                              "import 'package:flutter/material.dart';")
    fixture = fixture.replace('static bool get isIOS => true;',
                              'static bool isIOS = true;')
    fixture = fixture.replace('class GameService {', '''class GameService {
  static int cleanupCalls = 0;
  static Completer<void>? cleanup;
  static Future<void> endGameSession() async {
    cleanupCalls++;
    await cleanup?.future;
  }
''')
    manager = (ROOT / 'lib/services/game_launch_manager.dart').read_text()
    manager = re.sub(r'^import .*;\n', '', manager, flags=re.M)
    candidates = re.search(r'_embeddedIOSSessionExecutables = <String>\{(.*?)\};',
                           manager, re.S).group(1)
    executables = re.findall(r"'(ios_\w+)'", candidates)
    assert set(executables) == {'ios_libretro_internal', 'ios_dolphin_internal',
                               'ios_armsx2_internal', 'ios_rpcs3_internal',
                               'ios_dusklight_internal'}
    locale_paths = sorted((ROOT / 'lib/l10n').glob('app_locale_*.dart'))
    assert len(locale_paths) == 12, locale_paths
    translations = {}
    for path in locale_paths:
        translations[path.stem] = {}
        for key in ('launchingGame', 'gameExecuting', 'closingGame'):
            found = re.search(r'AppLocale\.' + key + r":\s*'([^'\n]+)'", path.read_text())
            assert found and found.group(1).strip(), (path, key)
            translations[path.stem][key] = found.group(1)
    fr = translations['app_locale_fr']
    localization = '''
abstract final class AppLocale {
  static const launchingGame = 'launchingGame';
  static const gameExecuting = 'gameExecuting';
  static const closingGame = 'closingGame';
}
extension TestLocale on String {
  String getString(BuildContext context) => ''' + json.dumps(fr, ensure_ascii=False) + '''[this]!;
}
'''
    source = (ROOT / DIALOG).read_text()
    baseline = subprocess.check_output(['git', 'show', BASE + ':' + DIALOG],
                                       cwd=ROOT, text=True)
    listener = extract_function(source, 'void _onManagerChanged()')
    old_listener = extract_function(baseline, 'void _onManagerChanged()')
    code = fixture + localization + manager + r'''
class ReturnDialog extends StatefulWidget {
  final bool baseline;
  final VoidCallback onGameClosed;
  const ReturnDialog({super.key, required this.baseline, required this.onGameClosed});
  @override State<ReturnDialog> createState() => ReturnDialogState();
}
class ReturnDialogState extends State<ReturnDialog> {
  bool _cleanupStarted = false, _closeCalled = false, _onGameClosedFired = false;
  String _gameStatus = '';
  @override void initState() {
    super.initState();
    GameLaunchManager().addListener(changed);
  }
  void changed() => widget.baseline ? oldChanged() : _onManagerChanged();
  @override void dispose() {
    GameLaunchManager().removeListener(changed);
    GameLaunchManager().onDialogDisposed();
    super.dispose();
  }
  @override Widget build(BuildContext context) => Material(child: Text(_gameStatus));
'''
    code += listener + '\n' + old_listener.replace('void _onManagerChanged()', 'void oldChanged()', 1)
    code += '\n' + extract_function(source, 'Future<void> _performCleanup()')
    code += '\n' + extract_function(source, 'void _closeDialog()') + '\n}\n'
    code += r'''
void main() {
  final manager = GameLaunchManager();
  Future<void> prepare(WidgetTester tester) async {
    Platform.isIOS = true;
    GameService.cleanupCalls = 0;
    GameService.cleanup = Completer<void>();
    AudioPolicyService().activation = null;
    AudioPolicyService().active = false;
    MusicPlayerService().playing = true;
    MusicPlayerService().wasPlaying = false;
    MusicPlayerService().failResume = false;
    await manager.beginSession();
  }
  Future<void> exercise(WidgetTester tester, String exe, {bool baseline = false,
      bool desktop = false}) async {
    debugPrint('RETURN_CASE $exe baseline=$baseline desktop=$desktop begin');
    await prepare(tester);
    Platform.isIOS = !desktop;
    final navigator = GlobalKey<NavigatorState>();
    int closed = 0;
    await tester.pumpWidget(MaterialApp(navigatorKey: navigator,
      home: const Scaffold(body: Text('library'))));
    navigator.currentState!.push(PageRouteBuilder<void>(
      transitionDuration: Duration.zero, reverseTransitionDuration: Duration.zero,
      pageBuilder: (_, __, ___) => ReturnDialog(baseline: baseline,
        onGameClosed: () { closed++; })));
    await tester.pump();
    manager.notifyListeners();
    await tester.pump();
    expect(find.text(AppLocale.launchingGame.getString(
      tester.element(find.byType(ReturnDialog)))), findsOneWidget);
    final native = PageRouteBuilder<void>(transitionDuration: Duration.zero,
      reverseTransitionDuration: Duration.zero,
      pageBuilder: (_, __, ___) => const ColoredBox(color: Colors.black));
    navigator.currentState!.push(native);
    await tester.pump();
    manager.onGameStarted(emulatorExe: exe);
    await tester.pump();
    expect(manager.phase, GameLaunchPhase.playing);
    expect(manager.canDismiss, desktop);
    // Remove only the native cover, before an end event or any poll arrives:
    // exactly the first frame visible in the maintainer's video.
    navigator.currentState!.removeRoute(native);
    await tester.pump();
    final context = tester.element(find.byType(ReturnDialog));
    final expected = (baseline || desktop) ? AppLocale.gameExecuting : AppLocale.closingGame;
    expect(find.text(expected.getString(context)), findsOneWidget);
    if (!baseline && !desktop) {
      expect(find.text(AppLocale.gameExecuting.getString(context)), findsNothing);
    }
    expect(manager.phase, GameLaunchPhase.playing);
    expect(GameService.cleanupCalls, 0);
    expect(closed, 0);
    expect(AudioPolicyService().active, isFalse);
    expect(MusicPlayerService().playing, isFalse);
    // A back/A event behind native gameplay must still not finalize iOS.
    if (!desktop) {
      manager.userDismiss();
      expect(manager.phase, GameLaunchPhase.playing);
    }
    // Definitive native end: the unchanged manager and dialog own cleanup.
    manager._triggerClose();
    manager._triggerClose();
    await tester.pump();
    expect(find.text(AppLocale.closingGame.getString(context)), findsOneWidget);
    expect(GameService.cleanupCalls, 1);
    expect(closed, 0);
    expect(AudioPolicyService().active, isFalse);
    GameService.cleanup!.complete();
    await tester.pump();
    if (desktop) await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    await flush();
    expect(find.byType(ReturnDialog), findsNothing);
    expect(find.text('library'), findsOneWidget);
    expect(closed, 1);
    expect(manager.phase, isNull);
    expect(MusicPlayerService().playing, isTrue);
    await tester.pump(const Duration(seconds: 5));
    expect(GameService.cleanupCalls, 1);
    await tester.pumpWidget(const SizedBox());
    GameService.cleanup = null;
    debugPrint('RETURN_CASE $exe baseline=$baseline desktop=$desktop passed');
  }
'''
    # The production manager is a singleton and retains its completed audio
    # finalization Future. Keep sequential returns in ONE FakeAsync zone,
    # like one running app, rather than awaiting a Future from a dead test zone.
    code += "testWidgets('thirteen return and cleanup scenarios in one app clock', (tester) async {\n"
    for exe in executables:
        code += f"await exercise(tester, '{exe}', baseline: true);\n"
        code += f"await exercise(tester, '{exe}');\n"
    code += "await exercise(tester, 'retroarch', desktop: true);\n}, timeout: const Timeout(Duration(minutes: 2)));\n}\n"
    with tempfile.TemporaryDirectory(prefix='neostation-close-status-') as directory:
        work = Path(directory)
        (work / 'test').mkdir()
        (work / 'pubspec.yaml').write_text('''name: neostation_close_status_harness
environment:
  sdk: '>=3.9.2 <4.0.0'
dependencies:
  flutter:
    sdk: flutter
dev_dependencies:
  flutter_test:
    sdk: flutter
''')
        (work / 'test/close_status_test.dart').write_text(code)
        subprocess.run([os.environ.get('FLUTTER_BIN', 'flutter'), 'test',
                        '--reporter', 'expanded'], cwd=work, check=True)
    result = {'result': 'passed', 'source': os.environ.get('GITHUB_SHA', 'local'),
              'baseline': BASE, 'embeddedExecutables': executables,
              'baselineReproductions': 6, 'correctedReturnCases': 6,
              'desktopCases': 1, 'locales': translations,
              'cleanupBeforeNativeEnd': False, 'physicalDeviceValidated': False}
    output = ROOT / 'build/close-status/verdict.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
