// Nintendo 3DS system page (docs/libretro-3ds-system-settings.md § 3.4):
// the three selectors read and write Config/Azahar.json through the option
// store (the "Automatic" language is the absence of a stored value), a
// fixed region shows the "language ignored" warning with the back-to-Auto
// button, a running game refuses the write and the page says so without
// pretending it saved, the Indonesian UI announces its English fallback,
// the inventory lists the files of Saves/Azahar/Azahar, the import
// assistant analyzes a ZIP into a plan whose two boxes start unchecked and
// installs on confirmation, the last backup can be restored, and the
// controller (arrow keys, Enter, Backspace) drives the page and its choice
// dialog. Every root is a temporary folder; the method channels of the
// libretro bridge (isSessionActive), path_provider and gamepads are mocked.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive_io.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/screens/libretro/libretro_3ds_system_screen.dart';
import 'package:neostation/screens/libretro/libretro_library_actions.dart';
import 'package:neostation/services/libretro_3ds_system_data_service.dart';
import 'package:neostation/services/libretro_core_option_store.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:path/path.dart' as p;

const _gamepads = MethodChannel('xyz.luan/gamepads');
const _paths = MethodChannel('plugins.flutter.io/path_provider');
const _bridge = MethodChannel('neostation/libretro_internal');

/// id0 of the dump; the install moves titles under the destination id0.
const String _sourceId0 = 'a1b2c3d4e5f60718293a4b5c6d7e8f90';

/// Loads the default (English) Material or Cupertino texts for any locale,
/// so the page can be pumped under every NeoStation locale.
class _AnyLocaleDelegate<T> extends LocalizationsDelegate<T> {
  const _AnyLocaleDelegate(this._load);

  final Future<T> Function(Locale locale) _load;

  @override
  bool isSupported(Locale locale) => true;

  @override
  Future<T> load(Locale locale) => _load(locale);

  @override
  bool shouldReload(covariant LocalizationsDelegate<T> old) => false;
}

const _materialTexts = _AnyLocaleDelegate<MaterialLocalizations>(DefaultMaterialLocalizations.load);
const _cupertinoTexts = _AnyLocaleDelegate<CupertinoLocalizations>(DefaultCupertinoLocalizations.load);

Uint8List _bytes(int seed, int length) =>
    Uint8List.fromList(List<int>.generate(length, (i) => (seed * 31 + i * 7) & 0xff));

Uint8List _keysText() => Uint8List.fromList(utf8.encode(
      'slot0x2CKeyX=0123456789ABCDEF0123456789ABCDEF\n'
      'generator=00112233445566778899AABBCCDDEEFF\n',
    ));

Uint8List _seeddb(int count) {
  final out = Uint8List(16 + 32 * count);
  ByteData.sublistView(out).setUint32(0, count, Endian.little);
  out.setAll(16, _bytes(5, 32 * count));
  return out;
}

Uint8List _config() {
  final out = Uint8List(Libretro3dsSystemDataService.configFileSize);
  out.setAll(4, _bytes(9, out.length - 4));
  ByteData.sublistView(out)
    ..setUint16(0, 10, Endian.little)
    ..setUint16(2, 0x455C, Endian.little);
  return out;
}

/// A full NAND image: 0x100 bytes of signature then `NCSD`.
Uint8List _ncsdImage() {
  final out = _bytes(42, 0x400);
  out.setAll(0x100, utf8.encode('NCSD'));
  return out;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final english = LibretroLocale.values['en']!;
  late Directory root;
  late Directory config;
  late Directory saves;
  late Directory backups;
  late Directory diagnostics;
  late LibretroCoreOptionStore store;
  late Libretro3dsSystemDataService service;
  var sessionActive = false;
  var sessionProbes = 0;

  String en(String key, [Map<String, Object?> values = const <String, Object?>{}]) =>
      LibretroLocale.format(const Locale('en'), key, values);

  File azaharJson() => File(p.join(config.path, LibretroCoreOptionStore.libraryFileName('Azahar')));
  Map<String, String> stored() =>
      azaharJson().existsSync() ? LibretroCoreOptionStore.decode(azaharJson().readAsStringSync()) : <String, String>{};
  void storeValues(Map<String, Object> values) {
    azaharJson().parent.createSync(recursive: true);
    azaharJson().writeAsStringSync(jsonEncode(<String, Object>{'values': values}));
  }

  Directory user() => Directory(p.join(saves.path, 'Azahar', 'Azahar'));
  File userFile(String relative) => File(p.joinAll([user().path, ...relative.split('/')]));
  void writeUser(String relative, List<int> bytes) =>
      userFile(relative)
        ..createSync(recursive: true)
        ..writeAsBytesSync(bytes);

  /// Synchronous on purpose: real asynchronous IO awaited directly in a
  /// widget test body never resumes (fake async zone).
  String writeZip(String name, Map<String, List<int>> entries) {
    final archive = Archive();
    for (final entry in entries.entries) {
      archive.add(ArchiveFile.bytes(entry.key, entry.value));
    }
    final file = File(p.join(root.path, 'sources', name))
      ..createSync(recursive: true)
      ..writeAsBytesSync(ZipEncoder().encodeBytes(archive));
    return file.path;
  }

  setUpAll(() {
    // Navigation sounds use an audio engine without a test double.
    SfxService().setEnabled(false);
  });

  setUp(() {
    sessionActive = false;
    sessionProbes = 0;
    root = Directory.systemTemp.createTempSync('libretro_3ds_screen_');
    final documents = Directory(p.join(root.path, 'Documents'));
    config = Directory(p.join(documents.path, 'Libretro', 'Config'));
    saves = Directory(p.join(documents.path, 'Libretro', 'Saves'))..createSync(recursive: true);
    backups = Directory(p.join(documents.path, 'Libretro', 'Backups', 'Azahar'));
    diagnostics = Directory(p.join(documents.path, 'Diagnostics'));
    messenger.setMockMethodCallHandler(_gamepads, (call) async => <dynamic>[]);
    messenger.setMockMethodCallHandler(_paths, (_) async => root.path);
    messenger.setMockMethodCallHandler(_bridge, (call) async {
      if (call.method == 'isSessionActive') {
        sessionProbes++;
        return sessionActive;
      }
      if (call.method == 'availableCores') return <String>[];
      return null;
    });
    // The store and the service ask the bridge, through the mocked channel,
    // whether a game runs: exactly what the app does.
    store = LibretroCoreOptionStore(
      configDirectory: () async => config,
      sessionProbe: LibretroInternalBridge.isSessionActive,
    );
    service = Libretro3dsSystemDataService(
      savesDirectory: () async => saves,
      backupsDirectory: () async => backups,
      diagnosticsDirectory: () async => diagnostics..createSync(recursive: true),
      sessionProbe: LibretroInternalBridge.isSessionActive,
    );
  });

  tearDown(() {
    messenger.setMockMethodCallHandler(_gamepads, null);
    messenger.setMockMethodCallHandler(_paths, null);
    messenger.setMockMethodCallHandler(_bridge, null);
    root.deleteSync(recursive: true);
  });

  /// The page reads and writes real files: each native step needs real time
  /// (runAsync) and each await a pump, so an import takes hundreds of
  /// rounds. Stops once [until] is on screen, fails after [budget].
  Future<void> settle(WidgetTester tester, Finder until, {Duration budget = const Duration(seconds: 90)}) async {
    final deadline = DateTime.now().add(budget);
    while (DateTime.now().isBefore(deadline)) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      await tester.pump();
      if (until.evaluate().isNotEmpty) {
        await tester.pump();
        return;
      }
    }
    fail('Timed out waiting for $until');
  }

  /// A few real-time rounds, for things that must not happen.
  Future<void> idle(WidgetTester tester) async {
    for (var round = 0; round < 10; round++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      await tester.pump();
    }
  }

  Widget app(Widget home, {Locale locale = const Locale('en')}) => ScreenUtilInit(
        designSize: const Size(600, 2000),
        builder: (context, _) => MaterialApp(
          locale: locale,
          supportedLocales: <Locale>[locale],
          localizationsDelegates: const <LocalizationsDelegate<Object?>>[_materialTexts, _cupertinoTexts],
          home: home,
        ),
      );

  Future<void> pumpPage(
    WidgetTester tester, {
    Locale locale = const Locale('en'),
    Map<String, String> languageNames = const <String, String>{},
    Future<List<String>?> Function()? pickFiles,
    Future<String?> Function()? pickFolder,
    bool injectAnalyze = true,
  }) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(app(
      Libretro3dsSystemScreen(
        store: store,
        dataService: service,
        languageNames: languageNames,
        pickFiles: pickFiles,
        pickFolder: pickFolder,
        analyze: injectAnalyze ? service.analyze : null,
      ),
      locale: locale,
    ));
    await settle(tester, find.byKey(const ValueKey('3ds-inventory-keys')));
  }

  String valueText(WidgetTester tester, String id) =>
      tester.widget<Text>(find.byKey(ValueKey('3ds-setting-$id-value'))).data!;

  String statusText(WidgetTester tester, String id) =>
      tester.widget<Text>(find.byKey(ValueKey('3ds-inventory-$id-status'))).data!;

  Future<void> choose(WidgetTester tester, String setting, String choice, Finder until) async {
    await tester.ensureVisible(find.byKey(ValueKey('3ds-setting-$setting')));
    await tester.tap(find.byKey(ValueKey('3ds-setting-$setting')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(ValueKey('3ds-choice-$choice')));
    await tester.tap(find.byKey(ValueKey('3ds-choice-$choice')));
    await settle(tester, until);
  }

  group('system', () {
    testWidgets('selectors show the core defaults, the Automatic language and the notes', (tester) async {
      await pumpPage(tester);
      expect(find.text(english['system3dsTitle']!), findsOneWidget);
      expect(find.text(english['setting3dsLanguage']!), findsOneWidget);
      expect(find.text(english['setting3dsRegion']!), findsOneWidget);
      expect(find.text(english['setting3dsModel']!), findsOneWidget);
      // Nothing stored: the launch default follows NeoStation's language
      // (English here), the region and the model are the core's own
      // defaults (first values).
      expect(valueText(tester, 'language'), en('lang3dsAutomatic', {'language': 'English'}));
      expect(valueText(tester, 'region'), english['region3dsAuto']);
      expect(valueText(tester, 'model'), english['model3dsNew']);
      expect(find.text(english['system3dsRestartHint']!), findsOneWidget);
      expect(find.text(english['system3dsLanguageAdjusted']!), findsOneWidget);
      expect(find.text(english['system3dsSavestateRegion']!), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-language-ignored')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-use-auto-region')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-language-fallback')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-session-error')), findsNothing);
      // Reading never creates the option file.
      expect(azaharJson().existsSync(), isFalse);
    });

    testWidgets('a fixed region is written through the store, warns, and the button puts Auto back',
        (tester) async {
      await pumpPage(tester);
      await choose(tester, 'region', 'Japan', find.byKey(const ValueKey('3ds-language-ignored')));
      expect(stored(), <String, String>{'citra_region_value': 'Japan'});
      expect(valueText(tester, 'region'), english['region3dsJapan']);
      // The raw stored pair stays visible under the translated label.
      expect(find.text('citra_region_value = Japan'), findsOneWidget);
      expect(find.text(english['system3dsLanguageIgnored']!), findsOneWidget);
      expect(find.text(english['system3dsSaved']!), findsOneWidget);
      // Writes happen only once the bridge said no game runs.
      expect(sessionProbes, greaterThanOrEqualTo(1));

      await tester.ensureVisible(find.byKey(const ValueKey('3ds-use-auto-region')));
      await tester.tap(find.byKey(const ValueKey('3ds-use-auto-region')));
      await settle(tester, find.text('citra_region_value = Auto'));
      expect(stored(), <String, String>{'citra_region_value': 'Auto'});
      expect(find.byKey(const ValueKey('3ds-language-ignored')), findsNothing);
      expect(valueText(tester, 'region'), english['region3dsAuto']);
    });

    testWidgets('a stored language is shown; Automatic removes only that key', (tester) async {
      storeValues(<String, Object>{'citra_language_value': 'Japanese', 'citra_use_virtual_sd': 'enabled'});
      await pumpPage(tester);
      expect(valueText(tester, 'language'), english['lang3dsJapanese']);
      expect(find.text('citra_language_value = Japanese'), findsOneWidget);

      await choose(tester, 'language', 'auto', find.text(english['system3dsSaved']!));
      expect(stored(), <String, String>{'citra_use_virtual_sd': 'enabled'});
      expect(valueText(tester, 'language'), en('lang3dsAutomatic', {'language': 'English'}));

      await choose(tester, 'language', 'Traditional Chinese', find.text('citra_language_value = Traditional Chinese'));
      expect(stored(), <String, String>{
        'citra_use_virtual_sd': 'enabled',
        'citra_language_value': 'Traditional Chinese',
      });
      expect(valueText(tester, 'language'), english['lang3dsZhHant']);
    });

    testWidgets('the model choice is stored and the hint says it needs a new session', (tester) async {
      await pumpPage(tester);
      await choose(tester, 'model', 'Old 3DS', find.text('citra_is_new_3ds = Old 3DS'));
      expect(stored(), <String, String>{'citra_is_new_3ds': 'Old 3DS'});
      expect(valueText(tester, 'model'), english['model3dsOld']);
      expect(english['system3dsRestartHint'], contains('the model at the next session'));
      expect(find.text(english['system3dsRestartHint']!), findsOneWidget);
    });

    testWidgets('a running game refuses the write: the page says so and shows nothing as saved',
        (tester) async {
      await pumpPage(tester);
      sessionActive = true;
      await choose(tester, 'region', 'Europe', find.byKey(const ValueKey('3ds-session-error')));
      expect(find.text(english['system3dsSessionActive']!), findsOneWidget);
      expect(find.text(english['system3dsSaved']!), findsNothing);
      expect(azaharJson().existsSync(), isFalse, reason: 'refused before touching any file');
      expect(valueText(tester, 'region'), english['region3dsAuto']);
      expect(find.byKey(const ValueKey('3ds-language-ignored')), findsNothing);

      // The game ended: the next write goes through and the error clears.
      sessionActive = false;
      await choose(tester, 'region', 'Europe', find.text('citra_region_value = Europe'));
      expect(find.byKey(const ValueKey('3ds-session-error')), findsNothing);
      expect(stored(), <String, String>{'citra_region_value': 'Europe'});
    });

    testWidgets('Indonesian announces its English fallback; French names itself', (tester) async {
      const names = <String, String>{'id': 'Bahasa Indonesia', 'fr': 'Français'};
      await pumpPage(tester, locale: const Locale('id'), languageNames: names);
      final id = LibretroLocale.values['id']!;
      expect(find.text(id['system3dsTitle']!), findsOneWidget);
      expect(
        valueText(tester, 'language'),
        LibretroLocale.format(const Locale('id'), 'lang3dsAutomatic', {'language': 'Bahasa Indonesia'}),
      );
      expect(
        find.text(LibretroLocale.format(const Locale('id'), 'lang3dsFallback', {'language': 'Bahasa Indonesia'})),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('3ds-language-fallback')), findsOneWidget);

      await pumpPage(tester, locale: const Locale('fr'), languageNames: names);
      expect(valueText(tester, 'language'), 'Automatique (langue de NeoStation : Français)');
      expect(find.byKey(const ValueKey('3ds-language-fallback')), findsNothing);
      expect(find.text('Système Nintendo 3DS'), findsOneWidget);

      // Without the app's language list, the console's own label names the
      // matching language.
      await pumpPage(tester, locale: const Locale('de'));
      expect(valueText(tester, 'language'), LibretroLocale.format(const Locale('de'), 'lang3dsAutomatic', {
        'language': LibretroLocale.values['de']!['lang3dsGerman'],
      }));
    });

    testWidgets('the page reads the store again when the app comes back to the foreground', (tester) async {
      await pumpPage(tester);
      // A game ended and stored its own choice meanwhile.
      storeValues(<String, Object>{'citra_region_value': 'Korea'});
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await settle(tester, find.text('citra_region_value = Korea'));
      expect(valueText(tester, 'region'), english['region3dsKorea']);
      expect(find.byKey(const ValueKey('3ds-language-ignored')), findsOneWidget);
    });
  });

  group('system data', () {
    testWidgets('the inventory lists every file with its raw path and status', (tester) async {
      writeUser(Libretro3dsSystemDataService.keysTarget, _keysText());
      writeUser(Libretro3dsSystemDataService.configTarget, _config());
      writeUser('${Libretro3dsSystemDataService.titleRoot}/0004009b/00014002/content/00000000.app', _bytes(1, 300));
      writeUser('${Libretro3dsSystemDataService.titleRoot}/0004009b/00014102/content/00000000.app', _bytes(2, 200));
      writeUser('${Libretro3dsSystemDataService.titleRoot}/0004009b/00014102/content/00000000.tmd', _bytes(3, 100));
      writeUser('nand/rw/sys/SecureInfo_A', _bytes(4, 273));
      await pumpPage(tester);

      expect(find.text(english['system3dsDataTitle']!), findsOneWidget);
      expect(find.text(libretroLibraryLocation(user().path)), findsOneWidget);
      expect(statusText(tester, 'keys'), '${english['system3dsPresent']} · ${_keysText().length} B');
      expect(find.text(Libretro3dsSystemDataService.keysTarget), findsOneWidget);
      expect(find.text(english['system3dsKeysOptional']!), findsOneWidget);
      expect(statusText(tester, 'seeddb'), english['system3dsAbsent']);
      expect(find.text(Libretro3dsSystemDataService.seeddbTarget), findsOneWidget);
      expect(statusText(tester, 'config'), '${english['system3dsPresent']} · 32.8 KB');
      expect(find.text(Libretro3dsSystemDataService.configTarget), findsOneWidget);
      // Two titles, three content files, 600 bytes.
      expect(find.text(en('system3dsTitles', {'count': 2, 'size': '600 B'})), findsOneWidget);
      expect(statusText(tester, 'titles'), '${english['system3dsPresent']} · 3');
      // CHN font present, KOR and TWN missing: the note says the core has
      // no replacement for them.
      expect(statusText(tester, 'fonts'), english['system3dsAbsent']);
      expect(find.text(english['system3dsFontsMissing']!), findsOneWidget);
      expect(
        find.text('${Libretro3dsSystemDataService.titleRoot}/0004009b/00014102 — ${english['system3dsPresent']}'),
        findsOneWidget,
      );
      expect(
        find.text('${Libretro3dsSystemDataService.titleRoot}/0004009b/00014202 — ${english['system3dsAbsent']}'),
        findsOneWidget,
      );
      expect(statusText(tester, 'console'), english['system3dsPresent']);
      expect(find.text('nand/rw/sys/SecureInfo_A — ${english['system3dsPresent']} · 273 B'), findsOneWidget);
      expect(find.text('nand/private/movable.sed — ${english['system3dsAbsent']}'), findsOneWidget);
      expect(find.text(english['system3dsNoDistribution']!), findsOneWidget);
      // No backup yet: the restore button waits and the page says why.
      expect(tester.widget<OutlinedButton>(find.byKey(const ValueKey('3ds-restore-backup'))).enabled, isFalse);
      expect(find.text(english['system3dsNoBackup']!), findsOneWidget);
    });

    testWidgets('an empty user directory reads as missing everywhere, without creating it', (tester) async {
      await pumpPage(tester);
      for (final id in <String>['keys', 'seeddb', 'config', 'fonts', 'console']) {
        expect(statusText(tester, id), english['system3dsAbsent'], reason: id);
      }
      expect(find.text(en('system3dsTitles', {'count': 0, 'size': '0 B'})), findsOneWidget);
      expect(user().existsSync(), isFalse);
    });

    testWidgets('the import assistant: source, plan with unchecked boxes, confirmation, result',
        (tester) async {
      final zip = writeZip('dump.zip', <String, List<int>>{
        'citra/sysdata/seeddb.bin': _seeddb(2),
        'citra/sysdata/aes_keys.txt': _keysText(),
        'citra/nand/$_sourceId0/title/0004009b/00014002/content/00000000.app': _bytes(7, 512),
        'citra/nand/rw/sys/SecureInfo_A': _bytes(8, 273),
        'citra/nand.bin': _ncsdImage(),
        'citra/readme.txt': utf8.encode('notes'),
      });
      var picks = 0;
      await pumpPage(tester, pickFiles: () async {
        picks++;
        return <String>[zip];
      });

      await tester.ensureVisible(find.byKey(const ValueKey('3ds-import')));
      await tester.tap(find.byKey(const ValueKey('3ds-import')));
      await tester.pumpAndSettle();
      expect(find.text(english['system3dsImportZip']!), findsOneWidget);
      expect(find.text(english['system3dsImportFolder']!), findsOneWidget);
      expect(find.text(english['system3dsImportFiles']!), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('3ds-import-zip')));
      await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
      expect(picks, 1);

      // The plan: created elements with their raw destination, the ignored
      // file, the refused raw NAND image with its translated reason.
      const seeddbTarget = Libretro3dsSystemDataService.seeddbTarget;
      const titleTarget = '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014002/content/00000000.app';
      expect(find.text(english['system3dsPlanCreate']!), findsOneWidget);
      expect(find.text('$seeddbTarget · 80 B'), findsOneWidget);
      expect(find.text('$titleTarget · 512 B'), findsOneWidget);
      expect(find.text('${Libretro3dsSystemDataService.keysTarget} · ${_keysText().length} B'), findsOneWidget);
      expect(find.text('nand/rw/sys/SecureInfo_A · 273 B'), findsOneWidget);
      expect(find.text(english['system3dsPlanIgnored']!), findsOneWidget);
      expect(find.text('citra/readme.txt · 5 B'), findsOneWidget);
      expect(find.text('citra/nand.bin'), findsOneWidget);
      expect(find.text(english['system3dsRejectedRawNand']!), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-plan-replace')), findsNothing);

      // Both boxes start unchecked: keys and console data are left out.
      final consoleBox = find.byKey(const ValueKey('3ds-include-console'));
      final keysBox = find.byKey(const ValueKey('3ds-include-keys'));
      expect(tester.widget<CheckboxListTile>(consoleBox).value, isFalse);
      expect(tester.widget<CheckboxListTile>(keysBox).value, isFalse);
      expect(find.text(english['system3dsIncludeConsoleData']!), findsOneWidget);
      expect(find.text(english['system3dsIncludeConsoleDataHelp']!), findsOneWidget);
      expect(find.text(english['system3dsIncludeKeys']!), findsOneWidget);
      expect(find.text(english['system3dsIncludeKeysHelp']!), findsOneWidget);
      expect(find.text('${english['system3dsConfirm']} (2)'), findsOneWidget);

      // Opting into the keys (advanced) adds them; console data stays out.
      await tester.ensureVisible(keysBox);
      await tester.tap(keysBox);
      await tester.pump();
      expect(tester.widget<CheckboxListTile>(keysBox).value, isTrue);
      expect(tester.widget<CheckboxListTile>(consoleBox).value, isFalse);
      expect(find.text('${english['system3dsConfirm']} (3)'), findsOneWidget);

      await tester.ensureVisible(find.byKey(const ValueKey('3ds-import-confirm')));
      await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
      await settle(tester, find.byKey(const ValueKey('3ds-import-close')));

      // The result, element by element.
      expect(find.text(english['system3dsInstalled']!), findsNWidgets(4), reason: 'title + 3 elements');
      expect(find.byKey(const ValueKey('3ds-result-$seeddbTarget')), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-result-nand/rw/sys/SecureInfo_A')), findsOneWidget);
      expect(find.text(english['system3dsSkipped']!), findsOneWidget, reason: 'console data left out');
      expect(find.text(english['system3dsRejectedRawNand']!), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-result-failure')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-result-backup')), findsNothing, reason: 'nothing replaced');

      expect(userFile(seeddbTarget).readAsBytesSync(), _seeddb(2));
      expect(userFile(titleTarget).readAsBytesSync(), _bytes(7, 512));
      expect(userFile(Libretro3dsSystemDataService.keysTarget).readAsBytesSync(), _keysText());
      expect(userFile('nand/rw/sys/SecureInfo_A').existsSync(), isFalse);
      expect(userFile('nand/$_sourceId0/title').existsSync(), isFalse, reason: 'installed under the destination id0');
      expect(Directory(p.join(saves.path, 'Azahar')).listSync().map((e) => p.basename(e.path)), <String>['Azahar'],
          reason: 'no staging folder left');
      expect(diagnostics.listSync().map((e) => p.basename(e.path)).single,
          startsWith(Libretro3dsSystemDataService.journalPrefix));

      await tester.tap(find.byKey(const ValueKey('3ds-import-close')));
      await settle(tester, find.text('${english['system3dsPresent']} · 80 B'));
      expect(statusText(tester, 'seeddb'), '${english['system3dsPresent']} · 80 B');
      expect(statusText(tester, 'keys'), '${english['system3dsPresent']} · ${_keysText().length} B');
      expect(statusText(tester, 'console'), english['system3dsAbsent']);
    });

    testWidgets('a second import replaces with a backup, in a separate isolate by default', (tester) async {
      writeUser(Libretro3dsSystemDataService.seeddbTarget, _seeddb(1));
      final zip = writeZip('seeds.zip', <String, List<int>>{'sysdata/seeddb.bin': _seeddb(3)});
      await pumpPage(tester, pickFiles: () async => <String>[zip], injectAnalyze: false);

      await tester.ensureVisible(find.byKey(const ValueKey('3ds-import')));
      await tester.tap(find.byKey(const ValueKey('3ds-import')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('3ds-import-files')));
      await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
      expect(find.text(english['system3dsPlanReplace']!), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-plan-create')), findsNothing);
      expect(find.text('${english['system3dsConfirm']} (1)'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
      await settle(tester, find.byKey(const ValueKey('3ds-import-close')));
      final backup = backups.listSync().whereType<Directory>().single;
      expect(
        find.text(en('system3dsReplaced', {'backup': '${p.basename(backup.path)}/sysdata/seeddb.bin'})),
        findsOneWidget,
      );
      expect(find.text(libretroLibraryLocation(backup.path)), findsOneWidget);
      expect(File(p.join(backup.path, 'sysdata', 'seeddb.bin')).readAsBytesSync(), _seeddb(1));
      expect(userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(), _seeddb(3));

      await tester.tap(find.byKey(const ValueKey('3ds-import-close')));
      await settle(tester, find.text('${english['system3dsPresent']} · 112 B'));
      expect(tester.widget<OutlinedButton>(find.byKey(const ValueKey('3ds-restore-backup'))).enabled, isTrue);
    });

    testWidgets('nothing recognized: the plan says so and offers no installation', (tester) async {
      final zip = writeZip('other.zip', <String, List<int>>{'notes/readme.txt': utf8.encode('x')});
      await pumpPage(tester, pickFiles: () async => <String>[zip]);
      await tester.ensureVisible(find.byKey(const ValueKey('3ds-import')));
      await tester.tap(find.byKey(const ValueKey('3ds-import')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('3ds-import-zip')));
      await settle(tester, find.byKey(const ValueKey('3ds-plan-nothing')));
      expect(find.text(english['system3dsNothingRecognized']!), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-import-confirm')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-include-console')), findsNothing);
      await tester.tap(find.byKey(const ValueKey('3ds-import-cancel')));
      await tester.pumpAndSettle();
      expect(user().existsSync(), isFalse);
    });

    testWidgets('a folder source goes through the folder picker; a cancelled picker changes nothing',
        (tester) async {
      final folder = Directory(p.join(root.path, 'sources', 'citra'))..createSync(recursive: true);
      File(p.join(folder.path, 'sysdata', 'seeddb.bin'))
        ..createSync(recursive: true)
        ..writeAsBytesSync(_seeddb(1));
      var folderPicks = 0;
      var filePicks = 0;
      await pumpPage(tester, pickFolder: () async {
        folderPicks++;
        return folderPicks == 1 ? null : folder.path;
      }, pickFiles: () async {
        filePicks++;
        return null;
      });

      await tester.ensureVisible(find.byKey(const ValueKey('3ds-import')));
      await tester.tap(find.byKey(const ValueKey('3ds-import')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('3ds-import-folder')));
      await idle(tester);
      expect(folderPicks, 1);
      expect(find.byKey(const ValueKey('3ds-progress')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-import-confirm')), findsNothing);

      await tester.tap(find.byKey(const ValueKey('3ds-import')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('3ds-import-files')));
      await idle(tester);
      expect(filePicks, 1);
      expect(find.byKey(const ValueKey('3ds-import-confirm')), findsNothing);

      await tester.tap(find.byKey(const ValueKey('3ds-import')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('3ds-import-folder')));
      await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
      expect(folderPicks, 2);
      expect(find.text('${Libretro3dsSystemDataService.seeddbTarget} · 48 B'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('3ds-import-cancel')));
      await tester.pumpAndSettle();
      expect(user().existsSync(), isFalse);
    });

    testWidgets('a running game refuses the installation after the plan, without any write', (tester) async {
      final zip = writeZip('seeds.zip', <String, List<int>>{'sysdata/seeddb.bin': _seeddb(1)});
      await pumpPage(tester, pickFiles: () async => <String>[zip]);
      await tester.ensureVisible(find.byKey(const ValueKey('3ds-import')));
      await tester.tap(find.byKey(const ValueKey('3ds-import')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('3ds-import-zip')));
      await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
      sessionActive = true;
      await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
      await settle(tester, find.byKey(const ValueKey('3ds-session-error')));
      expect(find.text(english['system3dsSessionActive']!), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-import-close')), findsNothing);
      expect(user().existsSync(), isFalse);
    });

    testWidgets('restoring the last backup asks first, copies it back and keeps a backup of the current file',
        (tester) async {
      writeUser(Libretro3dsSystemDataService.seeddbTarget, _seeddb(3));
      final backup = Directory(p.join(backups.path, '20250101-000000'));
      File(p.join(backup.path, 'sysdata', 'seeddb.bin'))
        ..createSync(recursive: true)
        ..writeAsBytesSync(_seeddb(1));
      await pumpPage(tester);
      expect(find.byKey(const ValueKey('3ds-no-backup')), findsNothing);

      await tester.ensureVisible(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.tap(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.pumpAndSettle();
      expect(find.text(english['system3dsRestoreBackup']!), findsNWidgets(3), reason: 'button, title, confirm');
      expect(find.text(english['cancel']!), findsOneWidget);
      await tester.tap(find.text(english['cancel']!));
      await idle(tester);
      expect(userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(), _seeddb(3));

      await tester.tap(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.pumpAndSettle();
      await tester.tap(find.text(english['system3dsRestoreBackup']!).last);
      await settle(tester, find.text(english['system3dsRestored']!));
      expect(userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(), _seeddb(1));
      final folders = backups.listSync().whereType<Directory>().map((e) => p.basename(e.path)).toList()..sort();
      expect(folders.length, 2, reason: 'the overwritten current file got its own backup');
      expect(folders.first, '20250101-000000');
      expect(File(p.join(backups.path, folders.last, 'sysdata', 'seeddb.bin')).readAsBytesSync(), _seeddb(3));
      await settle(tester, find.text('${english['system3dsPresent']} · 48 B'));
    });

    testWidgets('a running game refuses the restore', (tester) async {
      File(p.join(backups.path, '20250101-000000', 'sysdata', 'seeddb.bin'))
        ..createSync(recursive: true)
        ..writeAsBytesSync(_seeddb(1));
      await pumpPage(tester);
      sessionActive = true;
      await tester.ensureVisible(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.tap(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.pumpAndSettle();
      await tester.tap(find.text(english['system3dsRestoreBackup']!).last);
      await settle(tester, find.byKey(const ValueKey('3ds-session-error')));
      expect(find.text(english['system3dsRestored']!), findsNothing);
      expect(user().existsSync(), isFalse);
    });
  });

  group('controller', () {
    testWidgets('arrow keys move the focus, Enter opens and answers the choice dialog, Backspace leaves',
        (tester) async {
      tester.view.physicalSize = const Size(1200, 4000);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(app(
        Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => Libretro3dsSystemScreen(store: store, dataService: service),
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await settle(tester, find.byKey(const ValueKey('3ds-inventory-keys')));

      // True when the primary focus sits on or under the widget [finder]
      // finds (a button owns its focus node below it, a ListTile too).
      bool focused(Finder finder) {
        final target = finder.evaluate().single;
        final context = FocusManager.instance.primaryFocus?.context;
        if (context == null) return false;
        if (context == target) return true;
        var inside = false;
        context.visitAncestorElements((ancestor) {
          inside = ancestor == target;
          return !inside;
        });
        return inside;
      }

      // The page's navigation layer ignores input for a short grace period
      // after it is activated, and throttles repeated keys (real clock).
      Future<void> press(LogicalKeyboardKey key) async {
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 220)));
        await tester.sendKeyEvent(key);
        await tester.pump();
      }

      // The D-pad starts on the first control: the language selector.
      await press(LogicalKeyboardKey.arrowDown);
      expect(focused(find.byKey(const ValueKey('3ds-setting-language'))), isTrue);
      await press(LogicalKeyboardKey.arrowDown);
      expect(focused(find.byKey(const ValueKey('3ds-setting-region'))), isTrue);
      await press(LogicalKeyboardKey.arrowUp);
      expect(focused(find.byKey(const ValueKey('3ds-setting-language'))), isTrue);

      // Enter opens the choice dialog exactly once, on the current entry.
      await press(LogicalKeyboardKey.enter);
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byKey(const ValueKey('3ds-choice-auto')), findsOneWidget);
      expect(focused(find.byKey(const ValueKey('3ds-choice-auto'))), isTrue);
      await press(LogicalKeyboardKey.arrowDown);
      expect(focused(find.byKey(const ValueKey('3ds-choice-English'))), isTrue);
      await press(LogicalKeyboardKey.arrowDown);
      expect(focused(find.byKey(const ValueKey('3ds-choice-Japanese'))), isTrue);

      // Enter answers the dialog once: Flutter's own Enter activation is
      // switched off inside it, only the navigation layer answers, so the
      // page itself is not popped.
      await press(LogicalKeyboardKey.enter);
      await settle(tester, find.text('citra_language_value = Japanese'));
      // settle() never advances the fake clock: let the pop transition end.
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('3ds-choice-auto')), findsNothing);
      expect(find.byType(Libretro3dsSystemScreen), findsOneWidget);
      expect(stored(), <String, String>{'citra_language_value': 'Japanese'});

      // Backspace closes an open dialog, then the page. Down then up lands
      // on the language selector whether the focus came back to it or to
      // the page itself.
      await press(LogicalKeyboardKey.arrowDown);
      await press(LogicalKeyboardKey.arrowUp);
      expect(focused(find.byKey(const ValueKey('3ds-setting-language'))), isTrue);
      await press(LogicalKeyboardKey.enter);
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byKey(const ValueKey('3ds-choice-auto')), findsOneWidget);
      expect(focused(find.byKey(const ValueKey('3ds-choice-Japanese'))), isTrue, reason: 'the stored value');
      await press(LogicalKeyboardKey.backspace);
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byKey(const ValueKey('3ds-choice-auto')), findsNothing);
      expect(find.byType(Libretro3dsSystemScreen), findsOneWidget);
      expect(stored(), <String, String>{'citra_language_value': 'Japanese'});

      await press(LogicalKeyboardKey.backspace);
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(Libretro3dsSystemScreen), findsNothing);
      expect(find.text('open'), findsOneWidget);
    });
  });
}
