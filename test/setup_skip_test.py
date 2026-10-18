#!/usr/bin/env python3
"""Compile the real setup footer/actions in Flutter; double only services/I/O.

The old iOS footer is a negative control. No emulator, native test, scanner or
previously successful UI suite is rerun for this optional first-run action.
"""
import ast
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from rpcs3_atomic_startup_test import extract_function

ROOT = Path(__file__).resolve().parents[1]
BASE = 'b8f5d81416c977cb165b4050f4349b33b8e84977'
WIZARD = 'lib/widgets/setup_wizard.dart'


def main():
    source = (ROOT / WIZARD).read_text()
    baseline = subprocess.check_output(['git', 'show', BASE + ':' + WIZARD],
                                       cwd=ROOT, text=True)
    locales = {}
    for path in sorted((ROOT / 'lib/l10n').glob('app_locale_*.dart')):
        match = re.search(r"AppLocale\.skipForNow:\s*('(?:\\.|[^'])*')", path.read_text())
        assert match, path
        locales[path.stem.removeprefix('app_locale_')] = ast.literal_eval(match.group(1))
    assert set(locales) == {'en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'ja', 'ko', 'zh', 'zh_hant', 'id'}
    assert all(locales.values()) and locales['zh'] != locales['zh_hant']
    # The unchanged production dispatcher must still select Traditional Chinese.
    dispatcher = (ROOT / 'lib/l10n/app_locale.dart').read_text()
    assert 'Hant' in dispatcher and 'zh_hant' in dispatcher
    code = r'''
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class Platform { static bool isIOS = true, isAndroid = false; }
extension Scale on num { double get r => toDouble(); }
class Provider {
  static final values = <Type, ChangeNotifier>{};
  static T of<T>(BuildContext context, {bool listen = true}) => values[T] as T;
}
extension Read on BuildContext { T read<T>() => Provider.of<T>(this, listen: false); }
class Consumer<T extends ChangeNotifier> extends StatelessWidget {
  final Widget Function(BuildContext, T, Widget?) builder;
  const Consumer({super.key, required this.builder});
  @override Widget build(BuildContext context) => AnimatedBuilder(
    animation: Provider.values[T]!, builder: (context, _) => builder(context, Provider.of<T>(context), null));
}
class Config { String? romFolder; final romFolders = <String>[]; }
class SqliteConfigProvider extends ChangeNotifier {
  final config = Config();
  bool scanCompleted = false;
  int scans = 0, saves = 0, consumed = 0;
  Future<void> scanSystems() async { scans++; }
  void completeScan() { scanCompleted = true; notifyListeners(); }
  void consumeStartupScan() { consumed++; }
  Future<void> saveConfig() async { saves++; }
}
class NeoAssetsProvider extends ChangeNotifier {
  bool hasActiveTheme = false, loading = false;
  final themes = <String>[];
}
class Log { void w(String value) {} }
class GamepadNavigation {
  final VoidCallback onNavigateUp, onNavigateDown, onSelectItem, onBack;
  GamepadNavigation({required this.onNavigateUp, required this.onNavigateDown,
    required this.onSelectItem, required this.onBack});
  void initialize() {} void activate() {}
}
abstract final class AppLocale {
  static const next = 'next';
  static const skipForNow = 'skipForNow';
}
String locale = 'fr';
'''
    code += 'const skipLabels = ' + json.dumps(locales, ensure_ascii=False) + ';\n'
    code += r'''
extension Localized on String {
  String getString(BuildContext context) => this == AppLocale.skipForNow ? skipLabels[locale]! : 'Next';
}
class Wizard extends StatefulWidget {
  final bool baseline;
  final VoidCallback onComplete;
  const Wizard({super.key, this.baseline = false, required this.onComplete});
  @override State<Wizard> createState() => WizardState();
}
class WizardState extends State<Wizard> {
  int _currentStep = Platform.isAndroid ? 2 : 1;
  bool _storageGranted = false, _needsAccessibility = false, _accessibilityGranted = false;
  bool _isSelectingFolder = false, _isSelectingUserDataFolder = false;
  bool _isImportingEsde = false, _isDownloadingArt = false, _finishing = false;
  bool get _accessibilityDone => !_needsAccessibility || _accessibilityGranted;
  dynamic _esdeResult;
  final _log = Log();
  GamepadNavigation? _gamepadNav;
  int pickerCalls = 0, libraryChoiceCalls = 0;
  void _moveIosLibraryChoice(int delta) {}
  Future<void> _refreshPermissionStates() async {}
  Future<void> _handlePermissionAction() async {}
  Future<void> _runIosLibraryChoice() async { libraryChoiceCalls++; }
  Future<void> _selectFolder() async { pickerCalls++; }
  Future<void> _runWizardEsdeImport() async {}
  Future<void> _downloadWizardArtPack() async {}
  String _getButtonText() => 'Continue';
  @override void initState() { super.initState(); _initGamepad(); }
  @override Widget build(BuildContext context) => Material(child: Column(
    mainAxisSize: MainAxisSize.min, children: [Text('step:$_currentStep'),
      widget.baseline ? oldFooter(Theme.of(context)) : _buildNavigationButtons(Theme.of(context))]));
'''
    code += source[source.index('  int get _stepUserData'):source.index('  @override\n  void initState()')]
    code += source[source.index('  bool get _skipBlocked'):source.index('  void _handleSkip()')]
    for signature in ('void _handleSkip()', 'void _initGamepad()',
                      'Widget _buildNavigationButtons(ThemeData theme)',
                      'Future<void> _handleMainAction()', 'Future<void> _finishSetup()'):
        code += extract_function(source, signature) + '\n'
    code += extract_function(baseline, 'Widget _buildNavigationButtons(ThemeData theme)').replace(
        '_buildNavigationButtons(', 'oldFooter(', 1) + '\n}\n'
    code += r'''
void main() {
  testWidgets('optional iOS library step, real navigation/actions and busy ownership', (tester) async {
    Future<(GlobalKey<WizardState>, SqliteConfigProvider)> open({bool old = false,
        VoidCallback? completed, double width = 390, String language = 'fr'}) async {
      await tester.pumpWidget(const SizedBox());
      locale = language;
      tester.view.resetPhysicalSize();
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = Size(width, width < 600 ? 844 : 390);
      final provider = SqliteConfigProvider();
      Provider.values[SqliteConfigProvider] = provider;
      Provider.values[NeoAssetsProvider] = NeoAssetsProvider();
      final key = GlobalKey<WizardState>();
      await tester.pumpWidget(MaterialApp(home: Scaffold(body: Align(
        alignment: Alignment.center, child: Wizard(key: key, baseline: old,
          onComplete: completed ?? () {})))));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      return (key, provider);
    }
    TextButton skip() => tester.widget<TextButton>(find.byType(TextButton));
    Platform.isIOS = true;
    // Exactly the missing action: the old footer has no touch skip on iOS.
    await open(old: true);
    expect(find.text(skipLabels['fr']!), findsNothing);
    debugPrint('SETUP_CASE old-ios-skip-hidden passed');

    int completed = 0;
    final (key, provider) = await open(completed: () { completed++; });
    expect(find.text(skipLabels['fr']!), findsOneWidget);
    await tester.tap(find.byType(TextButton));
    await tester.pump();
    final state = key.currentState!;
    expect(state._currentStep, state._stepScanning);
    state._gamepadNav!.onBack(); // Repeated B must not start a second scan.
    await tester.pump();
    expect(provider.scans, 1);
    expect(provider.config.romFolders, isEmpty);
    expect(provider.config.romFolder, isNull);
    expect(state.pickerCalls, 0);
    expect(state.libraryChoiceCalls, 0);
    expect(tester.widget<ElevatedButton>(find.byType(ElevatedButton)).onPressed, isNull);
    provider.completeScan();
    await tester.pump();
    await tester.tap(find.byType(ElevatedButton));
    await tester.pump();
    expect(state._currentStep, state._stepArtPack);
    expect(provider.consumed, 1);
    // Finishing without a ROM folder is allowed; no fabricated folder is saved.
    await tester.tap(find.byType(TextButton));
    await tester.pump();
    state._gamepadNav!.onBack();
    await tester.pump();
    expect(provider.saves, 1);
    expect(completed, 1);
    expect(provider.config.romFolders, isEmpty);
    debugPrint('SETUP_CASE ios-touch-skip-scan-next-finish passed');

    final (padKey, padProvider) = await open();
    padKey.currentState!._gamepadNav!.onBack();
    await tester.pump();
    expect(padKey.currentState!._currentStep, 2);
    expect(padProvider.scans, 1);
    expect(padKey.currentState!.pickerCalls, 0);
    debugPrint('SETUP_CASE ios-gamepad-skip passed');

    final (busyKey, busyProvider) = await open();
    final busy = busyKey.currentState!;
    for (final flag in ['picker', 'userdata', 'import', 'download', 'finish']) {
      busy.setState(() {
        busy._isSelectingFolder = flag == 'picker';
        busy._isSelectingUserDataFolder = flag == 'userdata';
        busy._isImportingEsde = flag == 'import';
        busy._isDownloadingArt = flag == 'download';
        busy._finishing = flag == 'finish';
      });
      await tester.pump();
      expect(skip().onPressed, isNull, reason: flag);
      busy._gamepadNav!.onBack();
      expect(busy._currentStep, 1, reason: flag);
      expect(busyProvider.scans, 0, reason: flag);
    }
    debugPrint('SETUP_CASE busy-touch-and-gamepad-blocked passed');

    final (goneKey, goneProvider) = await open();
    goneKey.currentState!._handleSkip();
    await tester.pumpWidget(const SizedBox());
    expect(goneProvider.scans, 0); // No post-frame work for a disposed wizard.
    expect(tester.takeException(), isNull);
    debugPrint('SETUP_CASE disposed-post-frame-cancelled passed');

    for (final language in skipLabels.keys) {
      final width = language == 'fr' || language == 'zh_hant' ? 320.0 : 844.0;
      await open(language: language, width: width);
      expect(find.text(skipLabels[language]!), findsOneWidget);
      expect(skip().onPressed, isNotNull);
      expect(tester.takeException(), isNull);
    }
    debugPrint('SETUP_CASE twelve-locales-portrait-landscape passed');

    Platform.isIOS = false;
    Platform.isAndroid = true;
    await open();
    expect(skip().onPressed, isNotNull);
    Platform.isAndroid = false;
    await open();
    expect(find.byType(TextButton), findsNothing);
    debugPrint('SETUP_CASE android-desktop-footer-preserved passed');
    await tester.pumpWidget(const SizedBox());
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  }, timeout: const Timeout(Duration(minutes: 2)));
}
'''
    # Only the images' bytes are substituted, so the actual footer layout runs.
    png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jA9kAAAAASUVORK5CYII='
    import base64
    with tempfile.TemporaryDirectory(prefix='neostation-setup-skip-') as directory:
        work = Path(directory)
        (work / 'test').mkdir()
        images = work / 'assets/images/gamepad'
        images.mkdir(parents=True)
        for button in ('A', 'B'):
            (images / f'Xbox_{button}_button.png').write_bytes(base64.b64decode(png))
        (work / 'pubspec.yaml').write_text('''name: neostation_setup_skip_harness
environment:
  sdk: '>=3.9.2 <4.0.0'
dependencies:
  flutter:
    sdk: flutter
dev_dependencies:
  flutter_test:
    sdk: flutter
flutter:
  assets:
    - assets/images/gamepad/
''')
        (work / 'test/setup_skip_test.dart').write_text(code)
        subprocess.run([os.environ.get('FLUTTER_BIN', 'flutter'), 'test',
                        '--reporter', 'expanded'], cwd=work, check=True)
    output = ROOT / 'build/setup-skip/verdict.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        'result': 'passed', 'source': os.environ.get('GITHUB_SHA', 'local'),
        'baseline': BASE, 'wizardSHA256': hashlib.sha256(source.encode()).hexdigest(),
        'cases': ['old-ios-skip-hidden', 'ios-touch-skip-scan-next-finish',
                  'ios-gamepad-skip', 'busy-touch-and-gamepad-blocked',
                  'disposed-post-frame-cancelled', 'twelve-locales-portrait-landscape',
                  'android-desktop-footer-preserved'],
        'locales': locales, 'externalFolderChosen': False,
        'physicalDeviceValidated': False,
    }, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
