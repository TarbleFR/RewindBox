// Nintendo 3DS system page (docs/libretro-3ds-system-settings.md § 3.4 and
// § 6.4): the three selectors read and write Config/Azahar.json through the
// option store (the "Automatic" language is the absence of a stored value;
// any other absent value is the core's own default, named neutrally), a
// fixed region shows the "language ignored" warning with the back-to-Auto
// button, a running game refuses the write and the page says so without
// pretending it saved (an unknown session state has its own text and code),
// the Indonesian UI announces its English fallback, the inventory lists the
// files of Saves/Azahar/Azahar (the CFG save with the console data), the
// import assistant analyzes a ZIP into a plan whose two boxes start
// unchecked (keys and console data shown as left out until checked) and
// installs on confirmation, a failed pass says what was put back, the last
// complete backup can be restored after a confirmation naming its date, an
// interrupted pass is recovered when the page opens, and the controller
// (arrow keys, Enter, Backspace) drives the page and its choice dialog.
// Every root is a temporary folder; the method channels of the libretro
// bridge (isSessionActive), path_provider and gamepads are mocked.
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

/// keys.txt as the core reads it: keys only under the `:AES` header.
Uint8List _keysText() => Uint8List.fromList(utf8.encode(
      ':AES\n'
      'slot0x2CKeyX=0123456789ABCDEF0123456789ABCDEF\n'
      'generatorConstant=00112233445566778899AABBCCDDEEFF\n',
    ));

Uint8List _seeddb(int count, {int seed = 5}) {
  final out = Uint8List(16 + 32 * count);
  ByteData.sublistView(out).setUint32(0, count, Endian.little);
  out.setAll(16, _bytes(seed, 32 * count));
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

/// NCCH title content: a random 0x100-byte signature, then `NCCH`.
Uint8List _app(int seed, int length) => _bytes(seed, length)..setAll(0x100, utf8.encode('NCCH'));

/// Title metadata of title `<high>/<low>` (see the service test).
Uint8List _tmd(String high, String low) {
  final out = _bytes(3, 0x140 + 0x9C4 + 0x30);
  ByteData.sublistView(out)
    ..setUint32(0, 0x00010004, Endian.big)
    ..setUint32(0x140 + 0x4C, int.parse(high, radix: 16), Endian.big)
    ..setUint32(0x140 + 0x50, int.parse(low, radix: 16), Endian.big)
    ..setUint16(0x140 + 0x9E, 1, Endian.big);
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
  var probeFails = false;
  var sessionProbes = 0;
  var zipCounter = 0;

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

  Libretro3dsSystemDataService dataService({
    DateTime Function()? now,
    Future<void> Function(String relativeTarget)? beforeCommit,
  }) =>
      Libretro3dsSystemDataService(
        savesDirectory: () async => saves,
        backupsDirectory: () async => backups,
        diagnosticsDirectory: () async => diagnostics..createSync(recursive: true),
        sessionProbe: LibretroInternalBridge.isSessionActive,
        now: now ?? DateTime.now,
        beforeCommit: beforeCommit,
      );

  setUpAll(() {
    // Navigation sounds use an audio engine without a test double.
    SfxService().setEnabled(false);
  });

  setUp(() {
    sessionActive = false;
    probeFails = false;
    sessionProbes = 0;
    zipCounter = 0;
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
        if (probeFails) throw PlatformException(code: 'bridge-unavailable');
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
    service = dataService();
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

  /// A complete backup made the way the app makes one: [before] installed,
  /// then replaced by [after] (seed databases), both at [time]. Returns the
  /// backup.
  Future<Libretro3dsBackup> makeBackup(WidgetTester tester,
      {required Uint8List before, required Uint8List after, required DateTime time}) async {
    late Libretro3dsBackup backup;
    await tester.runAsync(() async {
      final dated = dataService(now: () => time);
      for (final bytes in <Uint8List>[before, after]) {
        final zip = writeZip('seeds-${zipCounter++}.zip', <String, List<int>>{'sysdata/seeddb.bin': bytes});
        await dated.install(await dated.analyze(<String>[zip]));
      }
      backup = (await dated.backups()).first;
    });
    return backup;
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
    Future<void> Function()? releaseFolder,
    Libretro3dsSystemDataService? data,
    bool injectAnalyze = true,
  }) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    final pageService = data ?? service;
    await tester.pumpWidget(app(
      Libretro3dsSystemScreen(
        // A new page each time (a second pump in one test opens it again).
        key: UniqueKey(),
        store: store,
        dataService: pageService,
        languageNames: languageNames,
        pickFiles: pickFiles,
        pickFolder: pickFolder,
        releaseFolder: releaseFolder,
        analyze: injectAnalyze ? pageService.analyze : null,
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

  Future<void> openImport(WidgetTester tester, String source) async {
    await tester.ensureVisible(find.byKey(const ValueKey('3ds-import')));
    await tester.tap(find.byKey(const ValueKey('3ds-import')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(ValueKey('3ds-import-$source')));
  }

  Finder within(String group, String text) =>
      find.descendant(of: find.byKey(ValueKey('3ds-plan-$group')), matching: find.text(text));

  group('system', () {
    testWidgets('selectors show the Automatic language, the core defaults neutrally, and the notes', (tester) async {
      await pumpPage(tester);
      expect(find.text(english['system3dsTitle']!), findsOneWidget);
      expect(find.text(english['setting3dsLanguage']!), findsOneWidget);
      expect(find.text(english['setting3dsRegion']!), findsOneWidget);
      expect(find.text(english['setting3dsModel']!), findsOneWidget);
      // Nothing stored: the launch default follows NeoStation's language
      // (English here). Contract change (item 10): an absent region or
      // model is the core's own default, which the page does not claim to
      // know (it showed "Automatic" and "New model", the first values).
      expect(valueText(tester, 'language'), en('lang3dsAutomatic', {'language': 'English'}));
      expect(valueText(tester, 'region'), english['setting3dsCoreDefault']);
      expect(valueText(tester, 'model'), english['setting3dsCoreDefault']);
      expect(find.text(english['system3dsRestartHint']!), findsOneWidget);
      expect(find.text(english['system3dsLanguageAdjusted']!), findsOneWidget);
      expect(find.text(english['system3dsSavestateRegion']!), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-language-ignored')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-use-auto-region')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-language-fallback')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-session-error')), findsNothing);
      // Reading never creates the option file.
      expect(azaharJson().existsSync(), isFalse);

      // The choice dialog marks no value when nothing is stored.
      await tester.ensureVisible(find.byKey(const ValueKey('3ds-setting-model')));
      await tester.tap(find.byKey(const ValueKey('3ds-setting-model')));
      await tester.pumpAndSettle();
      for (final value in <String>['New 3DS', 'Old 3DS']) {
        expect(tester.widget<ListTile>(find.byKey(ValueKey('3ds-choice-$value'))).selected, isFalse, reason: value);
      }
      await tester.tap(find.byKey(const ValueKey('3ds-choice-Old 3DS')));
      await settle(tester, find.text('citra_is_new_3ds = Old 3DS'));
      expect(valueText(tester, 'model'), english['model3dsOld']);
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
      // Item 10: still the neutral core default (nothing stored).
      expect(valueText(tester, 'region'), english['setting3dsCoreDefault']);
      expect(find.byKey(const ValueKey('3ds-language-ignored')), findsNothing);

      // The game ended: the next write goes through and the error clears.
      sessionActive = false;
      await choose(tester, 'region', 'Europe', find.text('citra_region_value = Europe'));
      expect(find.byKey(const ValueKey('3ds-session-error')), findsNothing);
      expect(stored(), <String, String>{'citra_region_value': 'Europe'});
    });

    testWidgets('a failed session check is not shown as a running game: own text, raw code apart (m6)',
        (tester) async {
      await pumpPage(tester);
      probeFails = true;
      await choose(tester, 'region', 'Korea', find.byKey(const ValueKey('3ds-session-unknown')));
      expect(find.text(english['system3dsSessionUnknown']!), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-session-error')), findsNothing);
      expect(find.textContaining('bridge-unavailable'), findsOneWidget, reason: 'the technical code is kept');
      expect(find.text(english['system3dsSaved']!), findsNothing);
      expect(azaharJson().existsSync(), isFalse);

      // The same for an import refused by the probe.
      final zip = writeZip('seeds.zip', <String, List<int>>{'sysdata/seeddb.bin': _seeddb(1)});
      probeFails = false;
      await tester.pumpAndSettle();
      await pumpPage(tester, pickFiles: () async => <String>[zip]);
      await openImport(tester, 'zip');
      await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
      probeFails = true;
      await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
      await settle(tester, find.byKey(const ValueKey('3ds-session-unknown')));
      expect(find.byKey(const ValueKey('3ds-session-error')), findsNothing);
      expect(user().existsSync(), isFalse);
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
      expect(valueText(tester, 'region'), 'Valeur propre au cœur');

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
      // m13: sizes from the project formatter, sentences from the catalog.
      expect(statusText(tester, 'keys'), en('system3dsPresentSize', {'size': '${_keysText().length} B'}));
      expect(en('system3dsPresentSize', {'size': '1 B'}), '${english['system3dsPresent']} · 1 B');
      expect(find.text(Libretro3dsSystemDataService.keysTarget), findsOneWidget);
      expect(find.text(english['system3dsKeysOptional']!), findsOneWidget);
      expect(statusText(tester, 'seeddb'), english['system3dsAbsent']);
      expect(find.text(Libretro3dsSystemDataService.seeddbTarget), findsOneWidget);
      // Contract change (m11): the CFG save identifies the console, so it is
      // listed with the console data (its own row is gone).
      expect(find.byKey(const ValueKey('3ds-inventory-config')), findsNothing);
      expect(
        find.text('${Libretro3dsSystemDataService.configTarget} — ${en('system3dsPresentSize', {'size': '32.8 KB'})}'),
        findsOneWidget,
      );
      // Two titles, three content files, 600 bytes.
      expect(find.text(en('system3dsTitles', {'count': 2, 'size': '600 B'})), findsOneWidget);
      expect(statusText(tester, 'titles'), en('system3dsPresentFiles', {'count': 3}));
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
      expect(find.text('nand/rw/sys/SecureInfo_A — ${en('system3dsPresentSize', {'size': '273 B'})}'), findsOneWidget);
      expect(find.text('nand/private/movable.sed — ${english['system3dsAbsent']}'), findsOneWidget);
      expect(find.text(english['system3dsNoDistribution']!), findsOneWidget);
      // No backup yet: the restore button waits and the page says why.
      expect(tester.widget<OutlinedButton>(find.byKey(const ValueKey('3ds-restore-backup'))).enabled, isFalse);
      expect(find.text(english['system3dsNoBackup']!), findsOneWidget);
    });

    testWidgets('an empty user directory reads as missing everywhere, without creating it', (tester) async {
      await pumpPage(tester);
      // 'config' left the list: the CFG save is a console data line (m11).
      for (final id in <String>['keys', 'seeddb', 'fonts', 'console']) {
        expect(statusText(tester, id), english['system3dsAbsent'], reason: id);
      }
      expect(
        find.text('${Libretro3dsSystemDataService.configTarget} — ${english['system3dsAbsent']}'),
        findsOneWidget,
      );
      expect(find.text(en('system3dsTitles', {'count': 0, 'size': '0 B'})), findsOneWidget);
      expect(user().existsSync(), isFalse);
    });

    testWidgets('the import assistant: source, plan with unchecked boxes, confirmation, result',
        (tester) async {
      final zip = writeZip('dump.zip', <String, List<int>>{
        'citra/sysdata/seeddb.bin': _seeddb(2),
        'citra/sysdata/aes_keys.txt': _keysText(),
        'citra/nand/$_sourceId0/title/0004009b/00014002/content/00000000.app': _app(7, 512),
        'citra/nand/$_sourceId0/title/0004009b/00014002/content/00000000.tmd': _tmd('0004009b', '00014002'),
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
      final keysLine = '${Libretro3dsSystemDataService.keysTarget} · ${_keysText().length} B';
      const consoleLine = 'nand/rw/sys/SecureInfo_A · 273 B';
      expect(find.text(english['system3dsPlanCreate']!), findsOneWidget);
      expect(find.text('$seeddbTarget · 80 B'), findsOneWidget);
      expect(find.text('$titleTarget · 512 B'), findsOneWidget);
      expect(find.text(keysLine), findsOneWidget);
      expect(find.text(consoleLine), findsOneWidget);
      // m6: keys and console data are listed as left out until checked.
      expect(within('excluded', keysLine), findsOneWidget);
      expect(within('excluded', consoleLine), findsOneWidget);
      expect(within('create', keysLine), findsNothing);
      expect(within('create', '$seeddbTarget · 80 B'), findsOneWidget);
      expect(find.text(english['system3dsPlanExcluded']!), findsOneWidget);
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
      // The count goes through the catalog (m13): seeddb and the title's
      // two files (the title is installed whole, m1b).
      expect(find.text(en('system3dsConfirm', {'count': 3})), findsOneWidget);

      // Opting into the keys (advanced) adds them; console data stays out.
      await tester.ensureVisible(keysBox);
      await tester.tap(keysBox);
      await tester.pump();
      expect(tester.widget<CheckboxListTile>(keysBox).value, isTrue);
      expect(tester.widget<CheckboxListTile>(consoleBox).value, isFalse);
      expect(find.text(en('system3dsConfirm', {'count': 4})), findsOneWidget);
      expect(within('create', keysLine), findsOneWidget);
      expect(within('excluded', keysLine), findsNothing);
      expect(within('excluded', consoleLine), findsOneWidget);

      await tester.ensureVisible(find.byKey(const ValueKey('3ds-import-confirm')));
      await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
      await settle(tester, find.byKey(const ValueKey('3ds-import-close')));

      // The result, element by element.
      expect(find.text(english['system3dsInstalled']!), findsNWidgets(5), reason: 'title + 4 elements');
      expect(find.byKey(const ValueKey('3ds-result-$seeddbTarget')), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-result-nand/rw/sys/SecureInfo_A')), findsOneWidget);
      expect(find.text(english['system3dsSkipped']!), findsOneWidget, reason: 'console data left out');
      expect(find.text(english['system3dsRejectedRawNand']!), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-result-failure')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-result-backup')), findsNothing, reason: 'nothing replaced');

      expect(userFile(seeddbTarget).readAsBytesSync(), _seeddb(2));
      expect(userFile(titleTarget).readAsBytesSync(), _app(7, 512));
      expect(userFile(Libretro3dsSystemDataService.keysTarget).readAsBytesSync(), _keysText());
      expect(userFile('nand/rw/sys/SecureInfo_A').existsSync(), isFalse);
      expect(userFile('nand/$_sourceId0/title').existsSync(), isFalse, reason: 'installed under the destination id0');
      expect(Directory(p.join(saves.path, 'Azahar')).listSync().map((e) => p.basename(e.path)), <String>['Azahar'],
          reason: 'no staging folder left');
      expect(diagnostics.listSync().map((e) => p.basename(e.path)).single,
          startsWith(Libretro3dsSystemDataService.journalPrefix));

      await tester.tap(find.byKey(const ValueKey('3ds-import-close')));
      await settle(tester, find.text(en('system3dsPresentSize', {'size': '80 B'})));
      expect(statusText(tester, 'seeddb'), en('system3dsPresentSize', {'size': '80 B'}));
      expect(statusText(tester, 'keys'), en('system3dsPresentSize', {'size': '${_keysText().length} B'}));
      expect(statusText(tester, 'console'), english['system3dsAbsent']);
    });

    testWidgets('a second import replaces with a backup, in a separate isolate by default', (tester) async {
      writeUser(Libretro3dsSystemDataService.seeddbTarget, _seeddb(1));
      final zip = writeZip('seeds.zip', <String, List<int>>{'sysdata/seeddb.bin': _seeddb(3)});
      await pumpPage(tester, pickFiles: () async => <String>[zip], injectAnalyze: false);

      await openImport(tester, 'files');
      await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
      expect(find.text(english['system3dsPlanReplace']!), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-plan-create')), findsNothing);
      expect(find.text(en('system3dsConfirm', {'count': 1})), findsOneWidget);

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
      await settle(tester, find.text(en('system3dsPresentSize', {'size': '112 B'})));
      expect(tester.widget<OutlinedButton>(find.byKey(const ValueKey('3ds-restore-backup'))).enabled, isTrue);
      expect(find.byKey(const ValueKey('3ds-last-backup')), findsOneWidget);
    });

    testWidgets('a failed pass says what was put back and what was not attempted (m6)', (tester) async {
      writeUser(Libretro3dsSystemDataService.seeddbTarget, _seeddb(1));
      const app = '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014002/content/00000000.app';
      const tmd = '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014002/content/00000000.tmd';
      final zip = writeZip('update.zip', <String, List<int>>{
        'sysdata/seeddb.bin': _seeddb(3),
        'title/0004009b/00014002/content/00000000.app': _app(1, 600),
        'title/0004009b/00014002/content/00000000.tmd': _tmd('0004009b', '00014002'),
      });
      final failing = dataService(beforeCommit: (target) async {
        if (target == app) throw StateError('simulated commit failure');
      });
      await pumpPage(tester, pickFiles: () async => <String>[zip], data: failing);
      await openImport(tester, 'zip');
      await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
      await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
      await settle(tester, find.byKey(const ValueKey('3ds-import-close')));

      expect(find.text(english['system3dsRolledBack']!), findsOneWidget, reason: 'the seed database');
      expect(find.text(english['system3dsNotAttempted']!), findsOneWidget, reason: 'the .tmd of the failed title');
      expect(find.byKey(const ValueKey('3ds-result-$app')), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-result-$tmd')), findsOneWidget);
      expect(find.textContaining('simulated commit failure'), findsWidgets);
      expect(find.byKey(const ValueKey('3ds-result-backup')), findsNothing, reason: 'a rolled-back pass leaves none');
      expect(userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(), _seeddb(1));
      expect(userFile(app).existsSync(), isFalse);
    });

    testWidgets('nothing recognized: the plan says so and offers no installation', (tester) async {
      final zip = writeZip('other.zip', <String, List<int>>{'notes/readme.txt': utf8.encode('x')});
      await pumpPage(tester, pickFiles: () async => <String>[zip]);
      await openImport(tester, 'zip');
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
      var releases = 0;
      await pumpPage(tester, pickFolder: () async {
        folderPicks++;
        return folderPicks == 1 ? null : folder.path;
      }, pickFiles: () async {
        filePicks++;
        return null;
      }, releaseFolder: () async => releases++);

      await openImport(tester, 'folder');
      await idle(tester);
      expect(folderPicks, 1);
      expect(find.byKey(const ValueKey('3ds-progress')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-import-confirm')), findsNothing);
      expect(releases, 0, reason: 'nothing was picked');

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
      expect(releases, 0, reason: 'still needed until the pass is over');
      await tester.tap(find.byKey(const ValueKey('3ds-import-cancel')));
      await idle(tester);
      expect(user().existsSync(), isFalse);
      // m12: the picked folder's bookmark does not outlive its import.
      expect(releases, 1);

      await tester.tap(find.byKey(const ValueKey('3ds-import')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('3ds-import-folder')));
      await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
      await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
      await settle(tester, find.byKey(const ValueKey('3ds-import-close')));
      expect(releases, 2, reason: 'released once the files are installed');
      expect(userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(), _seeddb(1));
    });

    testWidgets('a running game refuses the installation after the plan, without any write', (tester) async {
      final zip = writeZip('seeds.zip', <String, List<int>>{'sysdata/seeddb.bin': _seeddb(1)});
      await pumpPage(tester, pickFiles: () async => <String>[zip]);
      await openImport(tester, 'zip');
      await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
      sessionActive = true;
      await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
      await settle(tester, find.byKey(const ValueKey('3ds-session-error')));
      expect(find.text(english['system3dsSessionActive']!), findsOneWidget);
      expect(find.byKey(const ValueKey('3ds-import-close')), findsNothing);
      expect(user().existsSync(), isFalse);
    });

    testWidgets('restoring the last backup asks first, naming its date, copies it back and keeps a backup of the current file',
        (tester) async {
      final time = DateTime.utc(2025, 1, 1);
      final made = await makeBackup(tester, before: _seeddb(1), after: _seeddb(3), time: time);
      expect(made.name, '20250101-000000');
      expect(userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(), _seeddb(3));
      await pumpPage(tester);
      expect(find.byKey(const ValueKey('3ds-no-backup')), findsNothing);
      // m5: the restore row names the backup's date.
      final date = Libretro3dsSystemScreen.backupDate(time);
      expect(find.text(en('system3dsLastBackup', {'date': date})), findsOneWidget);

      await tester.ensureVisible(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.tap(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.pumpAndSettle();
      expect(find.text(english['system3dsRestoreBackup']!), findsNWidgets(3), reason: 'button, title, confirm');
      // m5: its own confirmation, with the date, saying added files stay.
      expect(find.text(en('system3dsRestoreConfirm', {'date': date})), findsOneWidget);
      expect(find.text(english['system3dsPlanReplace']!), findsNothing);
      expect(english['system3dsRestoreConfirm'], contains('are not removed'));
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
      await settle(tester, find.text(en('system3dsPresentSize', {'size': '48 B'})));
    });

    testWidgets('only a complete backup enables the restore; a damaged one is refused, never "restored" (M2)',
        (tester) async {
      // An empty newest folder (or one an interrupted pass left) is no
      // backup: before, it enabled the button and "restored" 0 files.
      Directory(p.join(backups.path, '29991231-235959')).createSync(recursive: true);
      await pumpPage(tester);
      expect(tester.widget<OutlinedButton>(find.byKey(const ValueKey('3ds-restore-backup'))).enabled, isFalse);
      expect(find.byKey(const ValueKey('3ds-no-backup')), findsOneWidget);

      final made = await makeBackup(tester, before: _seeddb(1), after: _seeddb(3), time: DateTime.utc(2025, 1, 1));
      // Same size, other bytes: listed, refused at the restore.
      File(p.join(made.path, 'sysdata', 'seeddb.bin')).writeAsBytesSync(_seeddb(1, seed: 7));
      await pumpPage(tester);
      expect(tester.widget<OutlinedButton>(find.byKey(const ValueKey('3ds-restore-backup'))).enabled, isTrue);
      await tester.ensureVisible(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.tap(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.pumpAndSettle();
      await tester.tap(find.text(english['system3dsRestoreBackup']!).last);
      await settle(tester, find.byKey(const ValueKey('3ds-action-error')));
      expect(find.text(english['system3dsBackupDamaged']!), findsOneWidget);
      expect(find.textContaining('sysdata/seeddb.bin'), findsWidgets, reason: 'the raw detail is kept apart');
      expect(find.text(english['system3dsRestored']!), findsNothing);
      expect(userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(), _seeddb(3));
    });

    testWidgets('a running game refuses the restore', (tester) async {
      await makeBackup(tester, before: _seeddb(1), after: _seeddb(3), time: DateTime.utc(2025, 1, 1));
      await pumpPage(tester);
      sessionActive = true;
      await tester.ensureVisible(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.tap(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.pumpAndSettle();
      await tester.tap(find.text(english['system3dsRestoreBackup']!).last);
      await settle(tester, find.byKey(const ValueKey('3ds-session-error')));
      expect(find.text(english['system3dsRestored']!), findsNothing);
      expect(userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(), _seeddb(3));
    });

    testWidgets('an interrupted pass is undone when the page opens, and the page says so (M3)', (tester) async {
      // What an import killed right after moving the original seed database
      // into its backup folder leaves: its write-ahead journal, the
      // original in the backup folder, its staging folder.
      final pass = Directory(p.join(backups.path, '20250102-000000'))..createSync(recursive: true);
      File(p.join(pass.path, 'sysdata', 'seeddb.bin'))
        ..createSync(recursive: true)
        ..writeAsBytesSync(_seeddb(1));
      final staging = Directory(p.join(saves.path, 'Azahar', '${Libretro3dsSystemDataService.stagingPrefix}20250102-000000'))
        ..createSync(recursive: true);
      File(p.join(pass.path, Libretro3dsSystemDataService.passLogName)).writeAsStringSync(
        '${jsonEncode(<String, Object>{
          'op': 'begin',
          'kind': 'import',
          'stamp': '20250102-000000',
          'pass': '20250102-000000',
          'staging': p.basename(staging.path),
          'units': <Object>[
            <String, Object>{'target': 'sysdata/seeddb.bin', 'dir': false},
          ],
        })}\n'
        '${jsonEncode(<String, Object>{'op': 'backup', 'unit': 0})}\n',
      );
      await pumpPage(tester);
      await settle(tester, find.byKey(const ValueKey('3ds-recovery')));
      expect(find.text(english['system3dsRecoveredUndone']!), findsOneWidget);
      expect(userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(), _seeddb(1));
      expect(pass.existsSync(), isFalse);
      expect(staging.existsSync(), isFalse);
      await settle(tester, find.text(en('system3dsPresentSize', {'size': '48 B'})));
      expect(statusText(tester, 'seeddb'), en('system3dsPresentSize', {'size': '48 B'}));
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
