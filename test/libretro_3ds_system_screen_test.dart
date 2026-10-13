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
// bridge (isSessionActive), path_provider and gamepads are mocked, the
// bridge with the bytes Flutter's iOS engine sends (Build 454). The whole
// import of the maintainer's video (Azahar folder, its nand and sysdata
// folders, the sysdata files, nand.zip) runs to the refreshed inventory.
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
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

import 'libretro_session_envelopes.dart';

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

const _materialTexts = _AnyLocaleDelegate<MaterialLocalizations>(
  DefaultMaterialLocalizations.load,
);
const _cupertinoTexts = _AnyLocaleDelegate<CupertinoLocalizations>(
  DefaultCupertinoLocalizations.load,
);

Uint8List _bytes(int seed, int length) => Uint8List.fromList(
  List<int>.generate(length, (i) => (seed * 31 + i * 7) & 0xff),
);

/// One answer of the bridge as bytes (test/libretro_session_envelopes.dart).
ByteData _envelope(String hex) => ByteData.sublistView(
  Uint8List.fromList(<int>[
    for (var index = 0; index < hex.length; index += 2)
      int.parse(hex.substring(index, index + 2), radix: 16),
  ]),
);

/// keys.txt as the core reads it: keys only under the `:AES` header.
Uint8List _keysText() => Uint8List.fromList(
  utf8.encode(
    ':AES\n'
    'slot0x2CKeyX=0123456789ABCDEF0123456789ABCDEF\n'
    'generatorConstant=00112233445566778899AABBCCDDEEFF\n',
  ),
);

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

/// NCCH title content: a random 0x100-byte signature, then `NCCH`, with
/// the NoCrypto bit the core requires (Build 448: an encrypted NCCH is
/// refused at import, see libretro_3ds_system_data_service_test.dart).
Uint8List _app(int seed, int length) {
  final out = _bytes(seed, length)..setAll(0x100, utf8.encode('NCCH'));
  if (length > 0x18F) out[0x18F] |= 0x04;
  return out;
}

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

/// A content of title `<high>/<low>` as Azahar stores it once encrypted for
/// [console] in the legacy form: a decrypted NCCH (its size at 0x104, the
/// title id at 0x118, zeros at 0x120) XORed with that console's keystream,
/// the same for every file (Build 451, see the service test).
Uint8List _consoleEncrypted(String high, String low, int length, int console) {
  final out = _app(length & 0xff, length);
  ByteData.sublistView(out)
    ..setUint32(0x104, length ~/ 0x200, Endian.little)
    ..setUint32(0x118, int.parse(low, radix: 16), Endian.little)
    ..setUint32(0x11C, int.parse(high, radix: 16), Endian.little);
  out.fillRange(0x120, 0x130, 0);
  final keystream = math.Random(console);
  for (var index = 0; index < out.length; index++) {
    out[index] ^= keystream.nextInt(256);
  }
  return out;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
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

  /// The bytes the bridge answers isSessionActive with (Build 454): those
  /// Flutter's iOS engine sends for the fixed plugin, or [build453Envelopes].
  /// The state is [envelopeRunning] while [sessionActive], else
  /// [envelopeIdle], unless [answerState] names another one.
  var answers = fixedEnvelopes;
  String? answerState;

  String en(
    String key, [
    Map<String, Object?> values = const <String, Object?>{},
  ]) => LibretroLocale.format(const Locale('en'), key, values);

  File azaharJson() => File(
    p.join(config.path, LibretroCoreOptionStore.libraryFileName('Azahar')),
  );
  Map<String, String> stored() => azaharJson().existsSync()
      ? LibretroCoreOptionStore.decode(azaharJson().readAsStringSync())
      : <String, String>{};
  void storeValues(Map<String, Object> values) {
    azaharJson().parent.createSync(recursive: true);
    azaharJson().writeAsStringSync(
      jsonEncode(<String, Object>{'values': values}),
    );
  }

  Directory user() => Directory(p.join(saves.path, 'Azahar', 'Azahar'));
  File userFile(String relative) =>
      File(p.joinAll([user().path, ...relative.split('/')]));
  void writeUser(String relative, List<int> bytes) => userFile(relative)
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
  }) => Libretro3dsSystemDataService(
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
    answers = fixedEnvelopes;
    answerState = null;
    root = Directory.systemTemp.createTempSync('libretro_3ds_screen_');
    final documents = Directory(p.join(root.path, 'Documents'));
    config = Directory(p.join(documents.path, 'Libretro', 'Config'));
    saves = Directory(p.join(documents.path, 'Libretro', 'Saves'))
      ..createSync(recursive: true);
    backups = Directory(
      p.join(documents.path, 'Libretro', 'Backups', 'Azahar'),
    );
    diagnostics = Directory(p.join(documents.path, 'Diagnostics'));
    messenger.setMockMethodCallHandler(_gamepads, (call) async => <dynamic>[]);
    messenger.setMockMethodCallHandler(_paths, (_) async => root.path);
    // The bridge answers with the bytes Flutter's iOS engine sends
    // (test/libretro_session_envelopes.dart, checked against the real plugin
    // in the iOS Simulator), not with Dart values: Build 453's integers went
    // through mocks that returned Dart booleans unseen.
    messenger.setMockMessageHandler(_bridge.name, (message) async {
      final call = _bridge.codec.decodeMethodCall(message);
      if (call.method == 'isSessionActive') {
        sessionProbes++;
        if (probeFails) {
          return _bridge.codec.encodeErrorEnvelope(code: 'bridge-unavailable');
        }
        final state =
            answerState ?? (sessionActive ? envelopeRunning : envelopeIdle);
        return _envelope(answers[state]!);
      }
      if (call.method == 'availableCores') {
        return _bridge.codec.encodeSuccessEnvelope(<String>[]);
      }
      return _bridge.codec.encodeSuccessEnvelope(null);
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
    messenger.setMockMessageHandler(_bridge.name, null);
    root.deleteSync(recursive: true);
  });

  /// The page reads and writes real files: each native step needs real time
  /// (runAsync) and each await a pump, so an import takes hundreds of
  /// rounds. Stops once [until] is on screen, fails after [budget].
  Future<void> settle(
    WidgetTester tester,
    Finder until, {
    Duration budget = const Duration(seconds: 90),
  }) async {
    final deadline = DateTime.now().add(budget);
    while (DateTime.now().isBefore(deadline)) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 5)),
      );
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
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 5)),
      );
      await tester.pump();
    }
  }

  /// A complete backup made the way the app makes one: [before] installed,
  /// then replaced by [after] (seed databases), both at [time]. Returns the
  /// backup.
  Future<Libretro3dsBackup> makeBackup(
    WidgetTester tester, {
    required Uint8List before,
    required Uint8List after,
    required DateTime time,
  }) async {
    late Libretro3dsBackup backup;
    await tester.runAsync(() async {
      final dated = dataService(now: () => time);
      for (final bytes in <Uint8List>[before, after]) {
        final zip = writeZip('seeds-${zipCounter++}.zip', <String, List<int>>{
          'sysdata/seeddb.bin': bytes,
        });
        await dated.install(await dated.analyze(<String>[zip]));
      }
      backup = (await dated.backups()).first;
    });
    return backup;
  }

  Widget app(Widget home, {Locale locale = const Locale('en')}) =>
      ScreenUtilInit(
        designSize: const Size(600, 2000),
        builder: (context, _) => MaterialApp(
          locale: locale,
          supportedLocales: <Locale>[locale],
          localizationsDelegates: const <LocalizationsDelegate<Object?>>[
            _materialTexts,
            _cupertinoTexts,
          ],
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
    bool startImport = false,
  }) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    final pageService = data ?? service;
    await tester.pumpWidget(
      app(
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
          startImport: startImport,
        ),
        locale: locale,
      ),
    );
    await settle(tester, find.byKey(const ValueKey('3ds-inventory-keys')));
  }

  String valueText(WidgetTester tester, String id) =>
      tester.widget<Text>(find.byKey(ValueKey('3ds-setting-$id-value'))).data!;

  String statusText(WidgetTester tester, String id) => tester
      .widget<Text>(find.byKey(ValueKey('3ds-inventory-$id-status')))
      .data!;

  Future<void> choose(
    WidgetTester tester,
    String setting,
    String choice,
    Finder until,
  ) async {
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

  Finder within(String group, String text) => find.descendant(
    of: find.byKey(ValueKey('3ds-plan-$group')),
    matching: find.text(text),
  );

  group('system', () {
    testWidgets(
      'selectors show the Automatic language, the core defaults neutrally, and the notes',
      (tester) async {
        await pumpPage(tester);
        expect(find.text(english['system3dsTitle']!), findsOneWidget);
        expect(find.text(english['setting3dsLanguage']!), findsOneWidget);
        expect(find.text(english['setting3dsRegion']!), findsOneWidget);
        expect(find.text(english['setting3dsModel']!), findsOneWidget);
        // Nothing stored: the launch default follows NeoStation's language
        // (English here). Contract change (item 10): an absent region or
        // model is the core's own default, which the page does not claim to
        // know (it showed "Automatic" and "New model", the first values).
        expect(
          valueText(tester, 'language'),
          en('lang3dsAutomatic', {'language': 'English'}),
        );
        expect(valueText(tester, 'region'), english['setting3dsCoreDefault']);
        expect(valueText(tester, 'model'), english['setting3dsCoreDefault']);
        expect(find.text(english['system3dsRestartHint']!), findsOneWidget);
        expect(
          find.text(english['system3dsLanguageAdjusted']!),
          findsOneWidget,
        );
        expect(find.text(english['system3dsSavestateRegion']!), findsOneWidget);
        expect(
          find.byKey(const ValueKey('3ds-language-ignored')),
          findsNothing,
        );
        expect(find.byKey(const ValueKey('3ds-use-auto-region')), findsNothing);
        expect(
          find.byKey(const ValueKey('3ds-language-fallback')),
          findsNothing,
        );
        expect(find.byKey(const ValueKey('3ds-session-error')), findsNothing);
        // Reading never creates the option file.
        expect(azaharJson().existsSync(), isFalse);

        // The choice dialog marks no value when nothing is stored.
        await tester.ensureVisible(
          find.byKey(const ValueKey('3ds-setting-model')),
        );
        await tester.tap(find.byKey(const ValueKey('3ds-setting-model')));
        await tester.pumpAndSettle();
        for (final value in <String>['New 3DS', 'Old 3DS']) {
          expect(
            tester
                .widget<ListTile>(find.byKey(ValueKey('3ds-choice-$value')))
                .selected,
            isFalse,
            reason: value,
          );
        }
        await tester.tap(find.byKey(const ValueKey('3ds-choice-Old 3DS')));
        await settle(tester, find.text('citra_is_new_3ds = Old 3DS'));
        expect(valueText(tester, 'model'), english['model3dsOld']);
      },
    );

    testWidgets(
      'a fixed region is written through the store, warns, and the button puts Auto back',
      (tester) async {
        await pumpPage(tester);
        await choose(
          tester,
          'region',
          'Japan',
          find.byKey(const ValueKey('3ds-language-ignored')),
        );
        expect(stored(), <String, String>{'citra_region_value': 'Japan'});
        expect(valueText(tester, 'region'), english['region3dsJapan']);
        // The raw stored pair stays visible under the translated label.
        expect(find.text('citra_region_value = Japan'), findsOneWidget);
        expect(find.text(english['system3dsLanguageIgnored']!), findsOneWidget);
        expect(find.text(english['system3dsSaved']!), findsOneWidget);
        // Writes happen only once the bridge said no game runs.
        expect(sessionProbes, greaterThanOrEqualTo(1));

        await tester.ensureVisible(
          find.byKey(const ValueKey('3ds-use-auto-region')),
        );
        await tester.tap(find.byKey(const ValueKey('3ds-use-auto-region')));
        await settle(tester, find.text('citra_region_value = Auto'));
        expect(stored(), <String, String>{'citra_region_value': 'Auto'});
        expect(
          find.byKey(const ValueKey('3ds-language-ignored')),
          findsNothing,
        );
        expect(valueText(tester, 'region'), english['region3dsAuto']);
      },
    );

    testWidgets('a stored language is shown; Automatic removes only that key', (
      tester,
    ) async {
      storeValues(<String, Object>{
        'citra_language_value': 'Japanese',
        'citra_use_virtual_sd': 'enabled',
      });
      await pumpPage(tester);
      expect(valueText(tester, 'language'), english['lang3dsJapanese']);
      expect(find.text('citra_language_value = Japanese'), findsOneWidget);

      await choose(
        tester,
        'language',
        'auto',
        find.text(english['system3dsSaved']!),
      );
      expect(stored(), <String, String>{'citra_use_virtual_sd': 'enabled'});
      expect(
        valueText(tester, 'language'),
        en('lang3dsAutomatic', {'language': 'English'}),
      );

      await choose(
        tester,
        'language',
        'Traditional Chinese',
        find.text('citra_language_value = Traditional Chinese'),
      );
      expect(stored(), <String, String>{
        'citra_use_virtual_sd': 'enabled',
        'citra_language_value': 'Traditional Chinese',
      });
      expect(valueText(tester, 'language'), english['lang3dsZhHant']);
    });

    testWidgets(
      'the model choice is stored and the hint says it needs a new session',
      (tester) async {
        await pumpPage(tester);
        await choose(
          tester,
          'model',
          'Old 3DS',
          find.text('citra_is_new_3ds = Old 3DS'),
        );
        expect(stored(), <String, String>{'citra_is_new_3ds': 'Old 3DS'});
        expect(valueText(tester, 'model'), english['model3dsOld']);
        expect(
          english['system3dsRestartHint'],
          contains('the model at the next session'),
        );
        expect(find.text(english['system3dsRestartHint']!), findsOneWidget);
      },
    );

    testWidgets(
      'a running game refuses the write: the page says so and shows nothing as saved',
      (tester) async {
        await pumpPage(tester);
        sessionActive = true;
        await choose(
          tester,
          'region',
          'Europe',
          find.byKey(const ValueKey('3ds-session-error')),
        );
        expect(find.text(english['system3dsSessionActive']!), findsOneWidget);
        expect(find.text(english['system3dsSaved']!), findsNothing);
        expect(
          azaharJson().existsSync(),
          isFalse,
          reason: 'refused before touching any file',
        );
        // Item 10: still the neutral core default (nothing stored).
        expect(valueText(tester, 'region'), english['setting3dsCoreDefault']);
        expect(
          find.byKey(const ValueKey('3ds-language-ignored')),
          findsNothing,
        );

        // The game ended: the next write goes through and the error clears.
        sessionActive = false;
        await choose(
          tester,
          'region',
          'Europe',
          find.text('citra_region_value = Europe'),
        );
        expect(find.byKey(const ValueKey('3ds-session-error')), findsNothing);
        expect(stored(), <String, String>{'citra_region_value': 'Europe'});
      },
    );

    testWidgets(
      'a failed session check is not shown as a running game: own text, raw code apart (m6)',
      (tester) async {
        await pumpPage(tester);
        probeFails = true;
        await choose(
          tester,
          'region',
          'Korea',
          find.byKey(const ValueKey('3ds-session-unknown')),
        );
        expect(find.text(english['system3dsSessionUnknown']!), findsOneWidget);
        expect(find.byKey(const ValueKey('3ds-session-error')), findsNothing);
        expect(
          find.textContaining('bridge-unavailable'),
          findsOneWidget,
          reason: 'the technical code is kept',
        );
        expect(find.text(english['system3dsSaved']!), findsNothing);
        expect(azaharJson().existsSync(), isFalse);

        // The same for an import refused by the probe.
        final zip = writeZip('seeds.zip', <String, List<int>>{
          'sysdata/seeddb.bin': _seeddb(1),
        });
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
      },
    );

    testWidgets(
      'Indonesian announces its English fallback; French names itself',
      (tester) async {
        const names = <String, String>{
          'id': 'Bahasa Indonesia',
          'fr': 'Français',
        };
        await pumpPage(
          tester,
          locale: const Locale('id'),
          languageNames: names,
        );
        final id = LibretroLocale.values['id']!;
        expect(find.text(id['system3dsTitle']!), findsOneWidget);
        expect(
          valueText(tester, 'language'),
          LibretroLocale.format(const Locale('id'), 'lang3dsAutomatic', {
            'language': 'Bahasa Indonesia',
          }),
        );
        expect(
          find.text(
            LibretroLocale.format(const Locale('id'), 'lang3dsFallback', {
              'language': 'Bahasa Indonesia',
            }),
          ),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey('3ds-language-fallback')),
          findsOneWidget,
        );

        await pumpPage(
          tester,
          locale: const Locale('fr'),
          languageNames: names,
        );
        expect(
          valueText(tester, 'language'),
          'Automatique (langue de NeoStation : Français)',
        );
        expect(
          find.byKey(const ValueKey('3ds-language-fallback')),
          findsNothing,
        );
        expect(find.text('Système Nintendo 3DS'), findsOneWidget);
        expect(valueText(tester, 'region'), 'Valeur propre au cœur');

        // Without the app's language list, the console's own label names the
        // matching language.
        await pumpPage(tester, locale: const Locale('de'));
        expect(
          valueText(tester, 'language'),
          LibretroLocale.format(const Locale('de'), 'lang3dsAutomatic', {
            'language': LibretroLocale.values['de']!['lang3dsGerman'],
          }),
        );
      },
    );

    testWidgets(
      'the page reads the store again when the app comes back to the foreground',
      (tester) async {
        await pumpPage(tester);
        // A game ended and stored its own choice meanwhile.
        storeValues(<String, Object>{'citra_region_value': 'Korea'});
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.inactive,
        );
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        await settle(tester, find.text('citra_region_value = Korea'));
        expect(valueText(tester, 'region'), english['region3dsKorea']);
        expect(
          find.byKey(const ValueKey('3ds-language-ignored')),
          findsOneWidget,
        );
      },
    );
  });

  group('system data', () {
    testWidgets('the inventory lists every file with its raw path and status', (
      tester,
    ) async {
      writeUser(Libretro3dsSystemDataService.keysTarget, _keysText());
      writeUser(Libretro3dsSystemDataService.configTarget, _config());
      writeUser(
        '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014002/content/00000000.app',
        _bytes(1, 300),
      );
      writeUser(
        '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014102/content/00000000.app',
        _bytes(2, 200),
      );
      writeUser(
        '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014102/content/00000000.tmd',
        _bytes(3, 100),
      );
      writeUser('nand/rw/sys/SecureInfo_A', _bytes(4, 273));
      await pumpPage(tester);

      expect(find.text(english['system3dsDataTitle']!), findsOneWidget);
      expect(find.text(libretroLibraryLocation(user().path)), findsOneWidget);
      // m13: sizes from the project formatter, sentences from the catalog.
      expect(
        statusText(tester, 'keys'),
        en('system3dsPresentSize', {'size': '${_keysText().length} B'}),
      );
      expect(
        en('system3dsPresentSize', {'size': '1 B'}),
        '${english['system3dsPresent']} · 1 B',
      );
      expect(
        find.text(Libretro3dsSystemDataService.keysTarget),
        findsOneWidget,
      );
      expect(find.text(english['system3dsKeysOptional']!), findsOneWidget);
      expect(statusText(tester, 'seeddb'), english['system3dsAbsent']);
      expect(
        find.text(Libretro3dsSystemDataService.seeddbTarget),
        findsOneWidget,
      );
      // Contract change (m11): the CFG save identifies the console, so it is
      // listed with the console data (its own row is gone).
      expect(find.byKey(const ValueKey('3ds-inventory-config')), findsNothing);
      expect(
        find.text(
          '${Libretro3dsSystemDataService.configTarget} — ${en('system3dsPresentSize', {'size': '32.8 KB'})}',
        ),
        findsOneWidget,
      );
      // Two titles, three content files, 600 bytes.
      expect(
        find.text(en('system3dsTitles', {'count': 2, 'size': '600 B'})),
        findsOneWidget,
      );
      expect(
        statusText(tester, 'titles'),
        en('system3dsPresentFiles', {'count': 3}),
      );
      // CHN font present, KOR and TWN missing: the note says the core has
      // no replacement for them.
      expect(statusText(tester, 'fonts'), english['system3dsAbsent']);
      expect(find.text(english['system3dsFontsMissing']!), findsOneWidget);
      expect(
        find.text(
          '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014102 — ${english['system3dsPresent']}',
        ),
        findsOneWidget,
      );
      expect(
        find.text(
          '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014202 — ${english['system3dsAbsent']}',
        ),
        findsOneWidget,
      );
      expect(statusText(tester, 'console'), english['system3dsPresent']);
      expect(
        find.text(
          'nand/rw/sys/SecureInfo_A — ${en('system3dsPresentSize', {'size': '273 B'})}',
        ),
        findsOneWidget,
      );
      expect(
        find.text('nand/private/movable.sed — ${english['system3dsAbsent']}'),
        findsOneWidget,
      );
      expect(find.text(english['system3dsNoDistribution']!), findsOneWidget);
      // No backup yet: the restore button waits and the page says why.
      expect(
        tester
            .widget<OutlinedButton>(
              find.byKey(const ValueKey('3ds-restore-backup')),
            )
            .enabled,
        isFalse,
      );
      expect(find.text(english['system3dsNoBackup']!), findsOneWidget);
    });

    testWidgets(
      'an empty user directory reads as missing everywhere, without creating it',
      (tester) async {
        await pumpPage(tester);
        // 'config' left the list: the CFG save is a console data line (m11).
        for (final id in <String>['keys', 'seeddb', 'fonts', 'console']) {
          expect(
            statusText(tester, id),
            english['system3dsAbsent'],
            reason: id,
          );
        }
        expect(
          find.text(
            '${Libretro3dsSystemDataService.configTarget} — ${english['system3dsAbsent']}',
          ),
          findsOneWidget,
        );
        expect(
          find.text(en('system3dsTitles', {'count': 0, 'size': '0 B'})),
          findsOneWidget,
        );
        expect(user().existsSync(), isFalse);
      },
    );

    testWidgets(
      'the import assistant: source, plan with unchecked boxes, confirmation, result',
      (tester) async {
        final zip = writeZip('dump.zip', <String, List<int>>{
          'citra/sysdata/seeddb.bin': _seeddb(2),
          'citra/sysdata/aes_keys.txt': _keysText(),
          'citra/nand/$_sourceId0/title/0004009b/00014002/content/00000000.app':
              _app(7, 512),
          'citra/nand/$_sourceId0/title/0004009b/00014002/content/00000000.tmd':
              _tmd('0004009b', '00014002'),
          'citra/nand/rw/sys/SecureInfo_A': _bytes(8, 273),
          'citra/nand.bin': _ncsdImage(),
          'citra/readme.txt': utf8.encode('notes'),
        });
        var picks = 0;
        await pumpPage(
          tester,
          pickFiles: () async {
            picks++;
            return <String>[zip];
          },
        );

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
        const titleTarget =
            '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014002/content/00000000.app';
        final keysLine =
            '${Libretro3dsSystemDataService.keysTarget} · ${_keysText().length} B';
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
        expect(
          find.text(english['system3dsIncludeConsoleData']!),
          findsOneWidget,
        );
        expect(
          find.text(english['system3dsIncludeConsoleDataHelp']!),
          findsOneWidget,
        );
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

        await tester.ensureVisible(
          find.byKey(const ValueKey('3ds-import-confirm')),
        );
        await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
        await settle(tester, find.byKey(const ValueKey('3ds-import-close')));

        // The result, element by element.
        expect(
          find.text(english['system3dsInstalled']!),
          findsNWidgets(5),
          reason: 'title + 4 elements',
        );
        expect(
          find.byKey(const ValueKey('3ds-result-$seeddbTarget')),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey('3ds-result-nand/rw/sys/SecureInfo_A')),
          findsOneWidget,
        );
        expect(
          find.text(english['system3dsSkipped']!),
          findsOneWidget,
          reason: 'console data left out',
        );
        expect(find.text(english['system3dsRejectedRawNand']!), findsOneWidget);
        expect(find.byKey(const ValueKey('3ds-result-failure')), findsNothing);
        expect(
          find.byKey(const ValueKey('3ds-result-backup')),
          findsNothing,
          reason: 'nothing replaced',
        );

        expect(userFile(seeddbTarget).readAsBytesSync(), _seeddb(2));
        expect(userFile(titleTarget).readAsBytesSync(), _app(7, 512));
        expect(
          userFile(Libretro3dsSystemDataService.keysTarget).readAsBytesSync(),
          _keysText(),
        );
        expect(userFile('nand/rw/sys/SecureInfo_A').existsSync(), isFalse);
        expect(
          userFile('nand/$_sourceId0/title').existsSync(),
          isFalse,
          reason: 'installed under the destination id0',
        );
        expect(
          Directory(
            p.join(saves.path, 'Azahar'),
          ).listSync().map((e) => p.basename(e.path)),
          <String>['Azahar'],
          reason: 'no staging folder left',
        );
        expect(
          diagnostics.listSync().map((e) => p.basename(e.path)).single,
          startsWith(Libretro3dsSystemDataService.journalPrefix),
        );

        await tester.tap(find.byKey(const ValueKey('3ds-import-close')));
        await settle(
          tester,
          find.text(en('system3dsPresentSize', {'size': '80 B'})),
        );
        expect(
          statusText(tester, 'seeddb'),
          en('system3dsPresentSize', {'size': '80 B'}),
        );
        expect(
          statusText(tester, 'keys'),
          en('system3dsPresentSize', {'size': '${_keysText().length} B'}),
        );
        expect(statusText(tester, 'console'), english['system3dsAbsent']);
      },
    );

    testWidgets(
      'a second import replaces with a backup, in a separate isolate by default',
      (tester) async {
        writeUser(Libretro3dsSystemDataService.seeddbTarget, _seeddb(1));
        final zip = writeZip('seeds.zip', <String, List<int>>{
          'sysdata/seeddb.bin': _seeddb(3),
        });
        await pumpPage(
          tester,
          pickFiles: () async => <String>[zip],
          injectAnalyze: false,
        );

        await openImport(tester, 'files');
        await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
        expect(find.text(english['system3dsPlanReplace']!), findsOneWidget);
        expect(find.byKey(const ValueKey('3ds-plan-create')), findsNothing);
        expect(find.text(en('system3dsConfirm', {'count': 1})), findsOneWidget);

        await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
        await settle(tester, find.byKey(const ValueKey('3ds-import-close')));
        final backup = backups.listSync().whereType<Directory>().single;
        expect(
          find.text(
            en('system3dsReplaced', {
              'backup': '${p.basename(backup.path)}/sysdata/seeddb.bin',
            }),
          ),
          findsOneWidget,
        );
        expect(find.text(libretroLibraryLocation(backup.path)), findsOneWidget);
        expect(
          File(p.join(backup.path, 'sysdata', 'seeddb.bin')).readAsBytesSync(),
          _seeddb(1),
        );
        expect(
          userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(),
          _seeddb(3),
        );

        await tester.tap(find.byKey(const ValueKey('3ds-import-close')));
        await settle(
          tester,
          find.text(en('system3dsPresentSize', {'size': '112 B'})),
        );
        expect(
          tester
              .widget<OutlinedButton>(
                find.byKey(const ValueKey('3ds-restore-backup')),
              )
              .enabled,
          isTrue,
        );
        expect(find.byKey(const ValueKey('3ds-last-backup')), findsOneWidget);
      },
    );

    testWidgets(
      'a failed pass says what was put back and what was not attempted (m6)',
      (tester) async {
        writeUser(Libretro3dsSystemDataService.seeddbTarget, _seeddb(1));
        const app =
            '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014002/content/00000000.app';
        const tmd =
            '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014002/content/00000000.tmd';
        final zip = writeZip('update.zip', <String, List<int>>{
          'sysdata/seeddb.bin': _seeddb(3),
          'title/0004009b/00014002/content/00000000.app': _app(1, 600),
          'title/0004009b/00014002/content/00000000.tmd': _tmd(
            '0004009b',
            '00014002',
          ),
        });
        final failing = dataService(
          beforeCommit: (target) async {
            if (target == app) throw StateError('simulated commit failure');
          },
        );
        await pumpPage(
          tester,
          pickFiles: () async => <String>[zip],
          data: failing,
        );
        await openImport(tester, 'zip');
        await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
        await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
        await settle(tester, find.byKey(const ValueKey('3ds-import-close')));

        expect(
          find.text(english['system3dsRolledBack']!),
          findsOneWidget,
          reason: 'the seed database',
        );
        expect(
          find.text(english['system3dsNotAttempted']!),
          findsOneWidget,
          reason: 'the .tmd of the failed title',
        );
        expect(find.byKey(const ValueKey('3ds-result-$app')), findsOneWidget);
        expect(find.byKey(const ValueKey('3ds-result-$tmd')), findsOneWidget);
        expect(find.textContaining('simulated commit failure'), findsWidgets);
        expect(
          find.byKey(const ValueKey('3ds-result-backup')),
          findsNothing,
          reason: 'a rolled-back pass leaves none',
        );
        expect(
          userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(),
          _seeddb(1),
        );
        expect(userFile(app).existsSync(), isFalse);
      },
    );

    testWidgets(
      'nothing recognized: the plan says so and offers no installation',
      (tester) async {
        final zip = writeZip('other.zip', <String, List<int>>{
          'notes/readme.txt': utf8.encode('x'),
        });
        await pumpPage(tester, pickFiles: () async => <String>[zip]);
        await openImport(tester, 'zip');
        await settle(tester, find.byKey(const ValueKey('3ds-plan-nothing')));
        expect(
          find.text(english['system3dsNothingRecognized']!),
          findsOneWidget,
        );
        expect(find.byKey(const ValueKey('3ds-import-confirm')), findsNothing);
        expect(find.byKey(const ValueKey('3ds-include-console')), findsNothing);
        await tester.tap(find.byKey(const ValueKey('3ds-import-cancel')));
        await tester.pumpAndSettle();
        expect(user().existsSync(), isFalse);
      },
    );

    // Build 452: opened from the 3DS import menu of the library (or after a
    // RetroArch copy was given an Azahar folder), the page starts its import
    // assistant by itself.
    testWidgets('opened for an import, the page starts the import assistant', (tester) async {
      await pumpPage(tester, startImport: true);
      await settle(tester, find.byKey(const ValueKey('3ds-import-folder')));
      expect(find.text(english['system3dsImportZip']!), findsOneWidget);
      expect(find.text(english['system3dsImportFolder']!), findsOneWidget);
      expect(find.text(english['system3dsImportFiles']!), findsOneWidget);
      // Backing out leaves the page as it is, nothing written.
      await tester.tapAt(const Offset(10, 10));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('3ds-import-folder')), findsNothing);
      expect(user().existsSync(), isFalse);
    });

    // Build 451: the system titles of an Azahar nand folder, encrypted for
    // their console, were all refused as invalid contents.
    const fontApp =
        '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014002/content/00000000.app';
    const miiApp =
        '${Libretro3dsSystemDataService.titleRoot}/0004009b/00010202/content/00000000.app';
    Map<String, List<int>> consoleTitles() => <String, List<int>>{
      'nand/$_sourceId0/title/0004009b/00014002/content/00000000.app':
          _consoleEncrypted('0004009b', '00014002', 0x1400, 1),
      'nand/$_sourceId0/title/0004009b/00014002/content/00000000.tmd': _tmd(
        '0004009b',
        '00014002',
      ),
      'nand/$_sourceId0/title/0004009b/00010202/content/00000000.app':
          _consoleEncrypted('0004009b', '00010202', 0x800, 1),
      'nand/$_sourceId0/title/0004009b/00010202/content/00000000.tmd': _tmd(
        '0004009b',
        '00010202',
      ),
    };
    Finder line(String group, String target) => find.descendant(
      of: find.byKey(ValueKey('3ds-plan-$group')),
      matching: find.textContaining('$target · '),
    );

    testWidgets(
      'titles encrypted for their console are left out with their reason '
      'without that console otp.bin (Build 451)',
      (tester) async {
        final zip = writeZip('azahar.zip', <String, List<int>>{
          ...consoleTitles(),
          'sysdata/seeddb.bin': _seeddb(2),
        });
        await pumpPage(tester, pickFiles: () async => <String>[zip]);
        await openImport(tester, 'zip');
        await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));

        final reason = english['system3dsConsoleEncrypted']!;
        expect(
          tester
              .widget<Text>(
                find.byKey(
                  const ValueKey('3ds-plan-excluded-console-encrypted'),
                ),
              )
              .data,
          reason,
        );
        expect(find.text(reason), findsOneWidget, reason: 'once per group');
        expect(line('excluded', fontApp), findsOneWidget);
        expect(line('excluded', miiApp), findsOneWidget);
        expect(line('create', fontApp), findsNothing);
        expect(find.byKey(const ValueKey('3ds-plan-rejected')), findsNothing);
        // No console data in this import: the box cannot bring an otp.bin.
        expect(
          tester
              .widget<CheckboxListTile>(
                find.byKey(const ValueKey('3ds-include-console')),
              )
              .onChanged,
          isNull,
        );
        expect(find.text(en('system3dsConfirm', {'count': 1})), findsOneWidget);

        await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
        await settle(tester, find.byKey(const ValueKey('3ds-import-close')));
        expect(
          find.byKey(const ValueKey('3ds-result-console-encrypted')),
          findsOneWidget,
        );
        expect(userFile(fontApp).existsSync(), isFalse);
        expect(
          userFile(Libretro3dsSystemDataService.seeddbTarget).existsSync(),
          isTrue,
        );
      },
    );

    testWidgets(
      'with that console otp.bin and the console data box, they are installed '
      '(Build 451)',
      (tester) async {
        final zip = writeZip('azahar.zip', <String, List<int>>{
          ...consoleTitles(),
          'sysdata/otp.bin': _bytes(12, 0x100),
        });
        await pumpPage(tester, pickFiles: () async => <String>[zip]);
        await openImport(tester, 'zip');
        await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
        expect(line('excluded', fontApp), findsOneWidget);
        expect(find.text(en('system3dsConfirm', {'count': 0})), findsOneWidget);

        final consoleBox = find.byKey(const ValueKey('3ds-include-console'));
        await tester.ensureVisible(consoleBox);
        await tester.tap(consoleBox);
        await tester.pump();
        expect(line('create', fontApp), findsOneWidget);
        expect(line('create', miiApp), findsOneWidget);
        expect(line('excluded', fontApp), findsNothing);
        expect(
          find.byKey(const ValueKey('3ds-plan-create-console-encrypted')),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey('3ds-plan-excluded-console-encrypted')),
          findsNothing,
        );
        // The two titles (four files) and the otp.bin.
        expect(find.text(en('system3dsConfirm', {'count': 5})), findsOneWidget);

        await tester.ensureVisible(
          find.byKey(const ValueKey('3ds-import-confirm')),
        );
        await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
        await settle(tester, find.byKey(const ValueKey('3ds-import-close')));
        expect(
          find.byKey(const ValueKey('3ds-result-console-encrypted')),
          findsNothing,
        );
        expect(
          userFile(fontApp).readAsBytesSync(),
          _consoleEncrypted('0004009b', '00014002', 0x1400, 1),
        );
        expect(userFile(miiApp).existsSync(), isTrue);
        expect(
          userFile(Libretro3dsSystemDataService.otpTarget).existsSync(),
          isTrue,
        );
      },
    );

    testWidgets(
      'files the core never reads are listed apart from unrecognized ones (Build 448)',
      (tester) async {
        final zip = writeZip('backup.zip', <String, List<int>>{
          'backup/boot9.bin': List<int>.filled(0x100, 1),
          'backup/notes.txt': utf8.encode('x'),
          'backup/sysdata/seeddb.bin': _seeddb(1),
        });
        await pumpPage(tester, pickFiles: () async => <String>[zip]);
        await openImport(tester, 'zip');
        await settle(tester, find.byKey(const ValueKey('3ds-plan-notneeded')));
        expect(
          within('notneeded', english['system3dsPlanNotNeeded']!),
          findsOneWidget,
        );
        expect(within('notneeded', 'backup/boot9.bin · 256 B'), findsOneWidget);
        expect(
          within('ignored', english['system3dsPlanIgnored']!),
          findsOneWidget,
        );
        expect(
          find.descendant(
            of: find.byKey(const ValueKey('3ds-plan-ignored')),
            matching: find.textContaining('backup/notes.txt'),
          ),
          findsOneWidget,
        );
        expect(
          find.descendant(
            of: find.byKey(const ValueKey('3ds-plan-ignored')),
            matching: find.textContaining('boot9.bin'),
          ),
          findsNothing,
        );
        await tester.tap(find.byKey(const ValueKey('3ds-import-cancel')));
        await tester.pumpAndSettle();
      },
    );

    testWidgets(
      'a folder source goes through the folder picker; a cancelled picker changes nothing',
      (tester) async {
        final folder = Directory(p.join(root.path, 'sources', 'citra'))
          ..createSync(recursive: true);
        File(p.join(folder.path, 'sysdata', 'seeddb.bin'))
          ..createSync(recursive: true)
          ..writeAsBytesSync(_seeddb(1));
        var folderPicks = 0;
        var filePicks = 0;
        var releases = 0;
        await pumpPage(
          tester,
          pickFolder: () async {
            folderPicks++;
            return folderPicks == 1 ? null : folder.path;
          },
          pickFiles: () async {
            filePicks++;
            return null;
          },
          releaseFolder: () async => releases++,
        );

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
        expect(
          find.text('${Libretro3dsSystemDataService.seeddbTarget} · 48 B'),
          findsOneWidget,
        );
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
        expect(
          userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(),
          _seeddb(1),
        );
      },
    );

    testWidgets(
      'a running game refuses the installation after the plan, without any write',
      (tester) async {
        final zip = writeZip('seeds.zip', <String, List<int>>{
          'sysdata/seeddb.bin': _seeddb(1),
        });
        await pumpPage(tester, pickFiles: () async => <String>[zip]);
        await openImport(tester, 'zip');
        await settle(tester, find.byKey(const ValueKey('3ds-import-confirm')));
        sessionActive = true;
        await tester.tap(find.byKey(const ValueKey('3ds-import-confirm')));
        await settle(tester, find.byKey(const ValueKey('3ds-session-error')));
        expect(find.text(english['system3dsSessionActive']!), findsOneWidget);
        expect(find.byKey(const ValueKey('3ds-import-close')), findsNothing);
        expect(user().existsSync(), isFalse);
      },
    );

    testWidgets(
      'restoring the last backup asks first, naming its date, copies it back and keeps a backup of the current file',
      (tester) async {
        final time = DateTime.utc(2025, 1, 1);
        final made = await makeBackup(
          tester,
          before: _seeddb(1),
          after: _seeddb(3),
          time: time,
        );
        expect(made.name, '20250101-000000');
        expect(
          userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(),
          _seeddb(3),
        );
        await pumpPage(tester);
        expect(find.byKey(const ValueKey('3ds-no-backup')), findsNothing);
        // m5: the restore row names the backup's date.
        final date = Libretro3dsSystemScreen.backupDate(time);
        expect(
          find.text(en('system3dsLastBackup', {'date': date})),
          findsOneWidget,
        );

        await tester.ensureVisible(
          find.byKey(const ValueKey('3ds-restore-backup')),
        );
        await tester.tap(find.byKey(const ValueKey('3ds-restore-backup')));
        await tester.pumpAndSettle();
        expect(
          find.text(english['system3dsRestoreBackup']!),
          findsNWidgets(3),
          reason: 'button, title, confirm',
        );
        // m5: its own confirmation, with the date, saying added files stay.
        expect(
          find.text(en('system3dsRestoreConfirm', {'date': date})),
          findsOneWidget,
        );
        expect(find.text(english['system3dsPlanReplace']!), findsNothing);
        expect(english['system3dsRestoreConfirm'], contains('are not removed'));
        expect(find.text(english['cancel']!), findsOneWidget);
        await tester.tap(find.text(english['cancel']!));
        await idle(tester);
        expect(
          userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(),
          _seeddb(3),
        );

        await tester.tap(find.byKey(const ValueKey('3ds-restore-backup')));
        await tester.pumpAndSettle();
        await tester.tap(find.text(english['system3dsRestoreBackup']!).last);
        await settle(tester, find.text(english['system3dsRestored']!));
        expect(
          userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(),
          _seeddb(1),
        );
        final folders =
            backups
                .listSync()
                .whereType<Directory>()
                .map((e) => p.basename(e.path))
                .toList()
              ..sort();
        expect(
          folders.length,
          2,
          reason: 'the overwritten current file got its own backup',
        );
        expect(folders.first, '20250101-000000');
        expect(
          File(
            p.join(backups.path, folders.last, 'sysdata', 'seeddb.bin'),
          ).readAsBytesSync(),
          _seeddb(3),
        );
        await settle(
          tester,
          find.text(en('system3dsPresentSize', {'size': '48 B'})),
        );
      },
    );

    testWidgets(
      'only a complete backup enables the restore; a damaged one is refused, never "restored" (M2)',
      (tester) async {
        // An empty newest folder (or one an interrupted pass left) is no
        // backup: before, it enabled the button and "restored" 0 files.
        Directory(
          p.join(backups.path, '29991231-235959'),
        ).createSync(recursive: true);
        await pumpPage(tester);
        expect(
          tester
              .widget<OutlinedButton>(
                find.byKey(const ValueKey('3ds-restore-backup')),
              )
              .enabled,
          isFalse,
        );
        expect(find.byKey(const ValueKey('3ds-no-backup')), findsOneWidget);

        final made = await makeBackup(
          tester,
          before: _seeddb(1),
          after: _seeddb(3),
          time: DateTime.utc(2025, 1, 1),
        );
        // Same size, other bytes: listed, refused at the restore.
        File(
          p.join(made.path, 'sysdata', 'seeddb.bin'),
        ).writeAsBytesSync(_seeddb(1, seed: 7));
        await pumpPage(tester);
        expect(
          tester
              .widget<OutlinedButton>(
                find.byKey(const ValueKey('3ds-restore-backup')),
              )
              .enabled,
          isTrue,
        );
        await tester.ensureVisible(
          find.byKey(const ValueKey('3ds-restore-backup')),
        );
        await tester.tap(find.byKey(const ValueKey('3ds-restore-backup')));
        await tester.pumpAndSettle();
        await tester.tap(find.text(english['system3dsRestoreBackup']!).last);
        await settle(tester, find.byKey(const ValueKey('3ds-action-error')));
        expect(find.text(english['system3dsBackupDamaged']!), findsOneWidget);
        expect(
          find.textContaining('sysdata/seeddb.bin'),
          findsWidgets,
          reason: 'the raw detail is kept apart',
        );
        expect(find.text(english['system3dsRestored']!), findsNothing);
        expect(
          userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(),
          _seeddb(3),
        );
      },
    );

    testWidgets('a running game refuses the restore', (tester) async {
      await makeBackup(
        tester,
        before: _seeddb(1),
        after: _seeddb(3),
        time: DateTime.utc(2025, 1, 1),
      );
      await pumpPage(tester);
      sessionActive = true;
      await tester.ensureVisible(
        find.byKey(const ValueKey('3ds-restore-backup')),
      );
      await tester.tap(find.byKey(const ValueKey('3ds-restore-backup')));
      await tester.pumpAndSettle();
      await tester.tap(find.text(english['system3dsRestoreBackup']!).last);
      await settle(tester, find.byKey(const ValueKey('3ds-session-error')));
      expect(find.text(english['system3dsRestored']!), findsNothing);
      expect(
        userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(),
        _seeddb(3),
      );
    });

    testWidgets(
      'an interrupted pass is undone when the page opens, and the page says so (M3)',
      (tester) async {
        // What an import killed right after moving the original seed database
        // into its backup folder leaves: its write-ahead journal, the
        // original in the backup folder, its staging folder.
        final pass = Directory(p.join(backups.path, '20250102-000000'))
          ..createSync(recursive: true);
        File(p.join(pass.path, 'sysdata', 'seeddb.bin'))
          ..createSync(recursive: true)
          ..writeAsBytesSync(_seeddb(1));
        final staging = Directory(
          p.join(
            saves.path,
            'Azahar',
            '${Libretro3dsSystemDataService.stagingPrefix}20250102-000000',
          ),
        )..createSync(recursive: true);
        File(
          p.join(pass.path, Libretro3dsSystemDataService.passLogName),
        ).writeAsStringSync(
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
        expect(
          userFile(Libretro3dsSystemDataService.seeddbTarget).readAsBytesSync(),
          _seeddb(1),
        );
        expect(pass.existsSync(), isFalse);
        expect(staging.existsSync(), isFalse);
        await settle(
          tester,
          find.text(en('system3dsPresentSize', {'size': '48 B'})),
        );
        expect(
          statusText(tester, 'seeddb'),
          en('system3dsPresentSize', {'size': '48 B'}),
        );
      },
    );
  });

  // Build 454: the maintainer's video of 13 October 2026. The Azahar folder,
  // then the files of its sysdata folder, were refused before any analysis:
  // the bridge answered isSessionActive with an int32, whose bool cast threw.
  // With the bytes the fixed bridge sends, every source of the video goes to
  // the installation and the refreshed inventory.
  group('the import of the video, with the bridge\'s real answers (Build 454)', () {
    const fontApp =
        '${Libretro3dsSystemDataService.titleRoot}/0004009b/00014002/content/00000000.app';
    const miiApp =
        '${Libretro3dsSystemDataService.titleRoot}/0004009b/00010202/content/00000000.app';
    const configTarget = Libretro3dsSystemDataService.configTarget;
    const otpTarget = Libretro3dsSystemDataService.otpTarget;
    const seeddbTarget = Libretro3dsSystemDataService.seeddbTarget;
    final consoleBox = find.byKey(const ValueKey('3ds-include-console'));
    final confirm = find.byKey(const ValueKey('3ds-import-confirm'));
    final close = find.byKey(const ValueKey('3ds-import-close'));

    /// movable.sed as the core loads it (`MovableSedFull`): 0x140 bytes
    /// starting with SEED.
    Uint8List movable() =>
        _bytes(20, 0x140)..setAll(0, utf8.encode('SEED'));

    /// The nand folder of an Azahar user folder: two system titles Azahar
    /// encrypted for the console (Build 451), the CFG save and three console
    /// files.
    Map<String, List<int>> nand() => <String, List<int>>{
      '$_sourceId0/title/0004009b/00014002/content/00000000.app':
          _consoleEncrypted('0004009b', '00014002', 0x1400, 1),
      '$_sourceId0/title/0004009b/00014002/content/00000000.tmd': _tmd(
        '0004009b',
        '00014002',
      ),
      '$_sourceId0/title/0004009b/00010202/content/00000000.app':
          _consoleEncrypted('0004009b', '00010202', 0x800, 1),
      '$_sourceId0/title/0004009b/00010202/content/00000000.tmd': _tmd(
        '0004009b',
        '00010202',
      ),
      'data/$_sourceId0/sysdata/00010017/00000000/config': _config(),
      'private/movable.sed': movable(),
      'rw/sys/SecureInfo_A': _bytes(21, 0x111),
      'rw/sys/LocalFriendCodeSeed_B': _bytes(22, 0x110),
    };

    /// The five files of its sysdata folder in the video.
    Map<String, List<int>> sysdata() => <String, List<int>>{
      'mac': _bytes(23, 17),
      'mcu.dat': _bytes(24, 24),
      'otp.bin': _bytes(12, 0x100),
      'play_time.bin': _bytes(25, 32),
      'seeddb.bin': _seeddb(2),
    };

    /// The maintainer's Azahar folder: cheats, config, log, nand, nand.zip,
    /// screenshots, sdmc, shaders and sysdata.
    String azaharFolder() {
      final folder = p.join(root.path, 'sources', 'Azahar');
      final files = <String, List<int>>{
        for (final entry in nand().entries) 'nand/${entry.key}': entry.value,
        for (final entry in sysdata().entries)
          'sysdata/${entry.key}': entry.value,
        'config/qt-config.ini': utf8.encode('[UI]\n'),
        'log/azahar_log.txt': utf8.encode('log'),
        'sdmc/Nintendo 3DS/$_sourceId0/readme.txt': utf8.encode('x'),
        'shaders/vulkan/pipeline.bin': _bytes(26, 64),
        'nand.zip': ZipEncoder().encodeBytes(
          Archive()
            ..add(ArchiveFile.bytes('nand/private/movable.sed', movable())),
        ),
      };
      for (final entry in files.entries) {
        File(p.joinAll([folder, ...entry.key.split('/')]))
          ..createSync(recursive: true)
          ..writeAsBytesSync(entry.value);
      }
      for (final empty in <String>['cheats', 'screenshots']) {
        Directory(p.join(folder, empty)).createSync(recursive: true);
      }
      return folder;
    }

    Finder line(String group, String target) => find.descendant(
      of: find.byKey(ValueKey('3ds-plan-$group')),
      matching: find.textContaining('$target · '),
    );

    String present(int size) =>
        en('system3dsPresentSize', {'size': '$size B'});

    Future<void> install(WidgetTester tester, {required int count}) async {
      expect(find.text(en('system3dsConfirm', {'count': count})), findsOneWidget);
      await tester.ensureVisible(confirm);
      await tester.tap(confirm);
      await settle(tester, close);
      expect(find.byKey(const ValueKey('3ds-result-failure')), findsNothing);
      expect(find.byKey(const ValueKey('3ds-result-missing')), findsNothing);
    }

    Future<void> checkConsoleData(WidgetTester tester) async {
      await tester.ensureVisible(consoleBox);
      await tester.tap(consoleBox);
      await tester.pump();
      expect(tester.widget<CheckboxListTile>(consoleBox).value, isTrue);
    }

    for (final source in <String>['folder', 'files']) {
      testWidgets(
        "the video, with Build 453's answer: the ${source == 'folder' ? 'Azahar folder' : 'sysdata files'} "
        'refused before any analysis, nothing written; with the fixed answer '
        'the same pick reaches the plan',
        (tester) async {
          answers = build453Envelopes;
          final azahar = azaharFolder();
          await pumpPage(
            tester,
            pickFolder: () async => azahar,
            pickFiles: () async => <String>[
              for (final name in sysdata().keys) p.join(azahar, 'sysdata', name),
            ],
            releaseFolder: () async {},
          );
          final probes = sessionProbes;
          await openImport(tester, source);
          await settle(tester, find.byKey(const ValueKey('3ds-session-unknown')));
          expect(sessionProbes, probes + 1);
          expect(find.text(english['system3dsSessionUnknown']!), findsOneWidget);
          expect(
            find.text(
              en('system3dsTechnicalCode', {
                'code':
                    'isSessionActive probe failed: LibretroSessionProbeException: '
                    'non-boolean answer (int 0)',
              }),
            ),
            findsOneWidget,
          );
          expect(find.byKey(const ValueKey('3ds-progress')), findsNothing);
          expect(confirm, findsNothing, reason: 'no analysis, no plan');
          expect(user().existsSync(), isFalse);
          expect(backups.existsSync(), isFalse);

          answers = fixedEnvelopes;
          await openImport(tester, source);
          await settle(tester, confirm);
          expect(find.byKey(const ValueKey('3ds-session-unknown')), findsNothing);
          expect(line('create', seeddbTarget), findsOneWidget);
          await tester.tap(find.byKey(const ValueKey('3ds-import-cancel')));
          await idle(tester);
          expect(user().existsSync(), isFalse);
        },
      );
    }

    testWidgets(
      'the Azahar folder: nand and sysdata installed with the console data, '
      'nand.zip listed apart, the inventory follows',
      (tester) async {
        final azahar = azaharFolder();
        var releases = 0;
        await pumpPage(
          tester,
          pickFolder: () async => azahar,
          releaseFolder: () async => releases++,
        );
        expect(statusText(tester, 'titles'), english['system3dsAbsent']);
        expect(statusText(tester, 'console'), english['system3dsAbsent']);

        await openImport(tester, 'folder');
        await settle(tester, confirm);
        // Before the box: the seed database only; the titles wait for the
        // console's otp.bin, which comes with the console data.
        expect(line('create', seeddbTarget), findsOneWidget);
        for (final target in <String>[
          fontApp,
          miiApp,
          configTarget,
          otpTarget,
          'sysdata/mcu.dat',
          'nand/private/movable.sed',
          'nand/rw/sys/SecureInfo_A',
          'nand/rw/sys/LocalFriendCodeSeed_B',
        ]) {
          expect(line('excluded', target), findsOneWidget, reason: target);
        }
        // nand.zip is not opened and says how to import it; mac and
        // play_time.bin are not recognized; nothing is refused.
        expect(
          find.descendant(
            of: find.byKey(const ValueKey('3ds-plan-ignored')),
            matching: find.textContaining('nand.zip · '),
          ),
          findsOneWidget,
        );
        expect(find.text(english['system3dsIgnoredNestedZip']!), findsOneWidget);
        expect(english['system3dsIgnoredNestedZip'], contains(english['system3dsImportZip']!));
        for (final name in <String>['sysdata/mac', 'sysdata/play_time.bin']) {
          expect(line('ignored', name), findsOneWidget, reason: name);
        }
        expect(find.byKey(const ValueKey('3ds-plan-rejected')), findsNothing);
        expect(find.text(english['system3dsRejectedArchive']!), findsNothing);
        expect(find.text(en('system3dsConfirm', {'count': 1})), findsOneWidget);

        await checkConsoleData(tester);
        for (final target in <String>[fontApp, miiApp, configTarget, otpTarget]) {
          expect(line('create', target), findsOneWidget, reason: target);
        }
        // Two titles (four files), the CFG save, five console files, seeddb.
        await install(tester, count: 11);
        expect(find.byKey(ValueKey('3ds-result-$fontApp')), findsOneWidget);
        expect(find.byKey(ValueKey('3ds-result-$otpTarget')), findsOneWidget);
        expect(find.byKey(const ValueKey('3ds-result-console-encrypted')), findsNothing);
        expect(find.byKey(const ValueKey('3ds-result-nand.zip')), findsNothing);
        expect(
          userFile(fontApp).readAsBytesSync(),
          _consoleEncrypted('0004009b', '00014002', 0x1400, 1),
        );
        expect(userFile(miiApp).existsSync(), isTrue);
        expect(userFile(configTarget).readAsBytesSync(), _config());
        expect(userFile(otpTarget).readAsBytesSync(), _bytes(12, 0x100));
        expect(userFile('sysdata/mcu.dat').readAsBytesSync(), _bytes(24, 24));
        expect(userFile('nand/private/movable.sed').readAsBytesSync(), movable());
        expect(userFile(seeddbTarget).readAsBytesSync(), _seeddb(2));
        expect(userFile('sysdata/mac').existsSync(), isFalse);
        expect(userFile('sysdata/play_time.bin').existsSync(), isFalse);
        expect(releases, 1, reason: 'the folder is released once installed');

        await tester.tap(close);
        await settle(
          tester,
          find.text(en('system3dsPresentFiles', {'count': 4})),
        );
        expect(statusText(tester, 'seeddb'), present(80));
        expect(
          statusText(tester, 'titles'),
          en('system3dsPresentFiles', {'count': 4}),
        );
        expect(statusText(tester, 'console'), english['system3dsPresent']);
        expect(find.text('$otpTarget — ${present(0x100)}'), findsOneWidget);
        expect(find.text('sysdata/mcu.dat — ${present(24)}'), findsOneWidget);
        expect(find.text('$configTarget — ${en('system3dsPresentSize', {'size': '32.8 KB'})}'), findsOneWidget);
        expect(find.byKey(const ValueKey('3ds-session-unknown')), findsNothing);
      },
    );

    testWidgets(
      'the nand folder, then the sysdata folder: the titles wait for the '
      "console's otp.bin, then install from nand",
      (tester) async {
        final azahar = azaharFolder();
        var picked = p.join(azahar, 'nand');
        await pumpPage(
          tester,
          pickFolder: () async => picked,
          releaseFolder: () async {},
        );

        // nand alone: no otp.bin anywhere, the titles are left out with
        // their reason; the CFG save and console files come with the box.
        await openImport(tester, 'folder');
        await settle(tester, confirm);
        expect(line('excluded', fontApp), findsOneWidget);
        await checkConsoleData(tester);
        expect(line('excluded', fontApp), findsOneWidget);
        expect(line('create', configTarget), findsOneWidget);
        await install(tester, count: 4);
        expect(find.byKey(const ValueKey('3ds-result-console-encrypted')), findsOneWidget);
        expect(userFile(fontApp).existsSync(), isFalse);
        expect(userFile(configTarget).existsSync(), isTrue);
        await tester.tap(close);
        await settle(tester, find.text('$configTarget — ${en('system3dsPresentSize', {'size': '32.8 KB'})}'));
        expect(statusText(tester, 'titles'), english['system3dsAbsent']);

        // sysdata: the seed database, and otp.bin and mcu.dat with the box.
        picked = p.join(azahar, 'sysdata');
        await openImport(tester, 'folder');
        await settle(tester, confirm);
        expect(line('create', seeddbTarget), findsOneWidget);
        expect(line('excluded', otpTarget), findsOneWidget);
        // Paths inside the chosen folder: its own name is not repeated.
        expect(line('ignored', 'mac'), findsOneWidget);
        expect(line('ignored', 'play_time.bin'), findsOneWidget);
        await checkConsoleData(tester);
        await install(tester, count: 3);
        expect(userFile(otpTarget).readAsBytesSync(), _bytes(12, 0x100));
        await tester.tap(close);
        await settle(tester, find.text('$otpTarget — ${present(0x100)}'));
        expect(statusText(tester, 'seeddb'), present(80));

        // nand again: the console's otp.bin is in place, the titles are
        // installed without the box; the console files are already there.
        picked = p.join(azahar, 'nand');
        await openImport(tester, 'folder');
        await settle(tester, confirm);
        expect(line('create', fontApp), findsOneWidget);
        expect(line('create', miiApp), findsOneWidget);
        expect(line('identical', configTarget), findsOneWidget);
        await install(tester, count: 4);
        expect(find.byKey(const ValueKey('3ds-result-console-encrypted')), findsNothing);
        await tester.tap(close);
        await settle(
          tester,
          find.text(en('system3dsPresentFiles', {'count': 4})),
        );
        expect(
          userFile(fontApp).readAsBytesSync(),
          _consoleEncrypted('0004009b', '00014002', 0x1400, 1),
        );
      },
    );

    testWidgets(
      'the five sysdata files of the video, picked as individual files',
      (tester) async {
        final azahar = azaharFolder();
        await pumpPage(
          tester,
          pickFiles: () async => <String>[
            for (final name in sysdata().keys) p.join(azahar, 'sysdata', name),
          ],
        );
        await openImport(tester, 'files');
        await settle(tester, confirm);
        expect(line('create', seeddbTarget), findsOneWidget);
        expect(line('excluded', otpTarget), findsOneWidget);
        expect(line('excluded', 'sysdata/mcu.dat'), findsOneWidget);
        expect(line('ignored', 'mac'), findsOneWidget);
        expect(line('ignored', 'play_time.bin'), findsOneWidget);
        expect(find.byKey(const ValueKey('3ds-plan-rejected')), findsNothing);
        await checkConsoleData(tester);
        await install(tester, count: 3);
        expect(userFile(seeddbTarget).readAsBytesSync(), _seeddb(2));
        expect(userFile(otpTarget).readAsBytesSync(), _bytes(12, 0x100));
        expect(userFile('sysdata/mcu.dat').readAsBytesSync(), _bytes(24, 24));
        await tester.tap(close);
        await settle(tester, find.text('$otpTarget — ${present(0x100)}'));
        expect(statusText(tester, 'seeddb'), present(80));
        expect(statusText(tester, 'console'), english['system3dsPresent']);
      },
    );

    testWidgets(
      "nand.zip, the ZIP of the nand folder, with the console's otp.bin in place",
      (tester) async {
        writeUser(otpTarget, _bytes(12, 0x100));
        final zip = writeZip('nand.zip', <String, List<int>>{
          for (final entry in nand().entries) 'nand/${entry.key}': entry.value,
        });
        await pumpPage(tester, pickFiles: () async => <String>[zip]);
        expect(statusText(tester, 'titles'), english['system3dsAbsent']);
        await openImport(tester, 'zip');
        await settle(tester, confirm);
        expect(line('create', fontApp), findsOneWidget);
        expect(line('create', miiApp), findsOneWidget);
        expect(line('excluded', configTarget), findsOneWidget);
        await checkConsoleData(tester);
        // Four title files, the CFG save and three console files.
        await install(tester, count: 8);
        await tester.tap(close);
        await settle(
          tester,
          find.text(en('system3dsPresentFiles', {'count': 4})),
        );
        expect(statusText(tester, 'console'), english['system3dsPresent']);
        expect(find.text('nand/private/movable.sed — ${present(0x140)}'), findsOneWidget);
      },
    );

    testWidgets(
      'while a game launches or runs the import is refused before the plan, '
      'nothing written; once it has stopped the import goes through',
      (tester) async {
        final azahar = azaharFolder();
        await pumpPage(
          tester,
          pickFolder: () async => azahar,
          releaseFolder: () async {},
        );
        for (final state in <String>[envelopeLaunching, envelopeRunning]) {
          answerState = state;
          final probes = sessionProbes;
          await openImport(tester, 'folder');
          await settle(tester, find.byKey(const ValueKey('3ds-session-error')));
          expect(sessionProbes, probes + 1, reason: state);
          expect(find.text(english['system3dsSessionActive']!), findsOneWidget);
          expect(find.byKey(const ValueKey('3ds-session-unknown')), findsNothing);
          expect(confirm, findsNothing, reason: state);
          expect(user().existsSync(), isFalse, reason: state);
          // The next pass clears the note.
          answerState = envelopeIdle;
          await openImport(tester, 'folder');
          await settle(tester, confirm);
          expect(find.byKey(const ValueKey('3ds-session-error')), findsNothing);
          await tester.tap(find.byKey(const ValueKey('3ds-import-cancel')));
          await idle(tester);
        }
        answerState = envelopeStopped;
        await openImport(tester, 'folder');
        await settle(tester, confirm);
        await install(tester, count: 1);
        expect(userFile(seeddbTarget).readAsBytesSync(), _seeddb(2));
      },
    );
  });

  group('controller', () {
    testWidgets(
      'arrow keys move the focus, Enter opens and answers the choice dialog, Backspace leaves',
      (tester) async {
        tester.view.physicalSize = const Size(1200, 4000);
        tester.view.devicePixelRatio = 2;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(
          app(
            Builder(
              builder: (context) => Scaffold(
                body: TextButton(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => Libretro3dsSystemScreen(
                        store: store,
                        dataService: service,
                      ),
                    ),
                  ),
                  child: const Text('open'),
                ),
              ),
            ),
          ),
        );
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
          await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 220)),
          );
          await tester.sendKeyEvent(key);
          await tester.pump();
        }

        // The D-pad starts on the first control: the language selector.
        await press(LogicalKeyboardKey.arrowDown);
        expect(
          focused(find.byKey(const ValueKey('3ds-setting-language'))),
          isTrue,
        );
        await press(LogicalKeyboardKey.arrowDown);
        expect(
          focused(find.byKey(const ValueKey('3ds-setting-region'))),
          isTrue,
        );
        await press(LogicalKeyboardKey.arrowUp);
        expect(
          focused(find.byKey(const ValueKey('3ds-setting-language'))),
          isTrue,
        );

        // Enter opens the choice dialog exactly once, on the current entry.
        await press(LogicalKeyboardKey.enter);
        await tester.pump(const Duration(milliseconds: 300));
        expect(find.byKey(const ValueKey('3ds-choice-auto')), findsOneWidget);
        expect(focused(find.byKey(const ValueKey('3ds-choice-auto'))), isTrue);
        await press(LogicalKeyboardKey.arrowDown);
        expect(
          focused(find.byKey(const ValueKey('3ds-choice-English'))),
          isTrue,
        );
        await press(LogicalKeyboardKey.arrowDown);
        expect(
          focused(find.byKey(const ValueKey('3ds-choice-Japanese'))),
          isTrue,
        );

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
        expect(
          focused(find.byKey(const ValueKey('3ds-setting-language'))),
          isTrue,
        );
        await press(LogicalKeyboardKey.enter);
        await tester.pump(const Duration(milliseconds: 300));
        expect(find.byKey(const ValueKey('3ds-choice-auto')), findsOneWidget);
        expect(
          focused(find.byKey(const ValueKey('3ds-choice-Japanese'))),
          isTrue,
          reason: 'the stored value',
        );
        await press(LogicalKeyboardKey.backspace);
        await tester.pump(const Duration(milliseconds: 300));
        expect(find.byKey(const ValueKey('3ds-choice-auto')), findsNothing);
        expect(find.byType(Libretro3dsSystemScreen), findsOneWidget);
        expect(stored(), <String, String>{'citra_language_value': 'Japanese'});

        await press(LogicalKeyboardKey.backspace);
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.byType(Libretro3dsSystemScreen), findsNothing);
        expect(find.text('open'), findsOneWidget);
      },
    );
  });
}
