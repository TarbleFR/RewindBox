// Before every PS3 firmware installation or reinstallation, NeoStation shows
// the Get More RAM information (Build 482): the maintainer's sentence, the
// procedure of that app, the distinction with the PS3UPDAT.PUP file and an
// explicit Back / Continue choice. Back never opens the firmware picker;
// Continue opens it. The twelve-language catalogue is complete, and no RPCS3
// Core or JIT channel is reached in either case.
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:file_picker/src/platform/file_picker_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/rpcs3_firmware_locale.dart';
import 'package:neostation/screens/rpcs3_manager_screen.dart';
import 'package:neostation/widgets/rpcs3_firmware_preflight_dialog.dart';
import 'package:neostation/widgets/rpcs3_internal_playlist_actions.dart';
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';

/// Files sheet that records every firmware picker request and cancels it.
class _CancelledPicker extends FilePickerPlatform {
  final List<String> requests = <String>[];

  @override
  Future<FilePickerResult?> pickFiles({
    String? dialogTitle,
    String? initialDirectory,
    FileType type = FileType.any,
    List<String>? allowedExtensions,
    Function(FilePickerStatus)? onFileLoading,
    int compressionQuality = 0,
    bool allowMultiple = false,
    bool withData = false,
    bool withReadStream = false,
    bool lockParentWindow = false,
    bool readSequential = false,
    bool cancelUploadOnWindowBlur = true,
    AndroidSAFOptions? androidSafOptions,
  }) async {
    requests.add('${allowedExtensions?.join(',')}:$dialogTitle');
    return null;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final placeholders = RegExp(r'\{\w+\}');
  final english = Rpcs3FirmwareLocale.values['en']!;

  group('twelve-language catalogue', () {
    test('covers exactly the twelve NeoStation languages', () {
      expect(
        Rpcs3FirmwareLocale.values.keys.toSet(),
        AppLocale.supportedLanguages.keys.toSet(),
      );
      expect(Rpcs3FirmwareLocale.values, hasLength(12));
    });

    for (final entry in Rpcs3FirmwareLocale.values.entries) {
      test('${entry.key}: complete, placeholders kept, no English fallback',
          () {
        expect(entry.value.keys.toSet(), english.keys.toSet());
        for (final message in english.entries) {
          final translated = entry.value[message.key]!;
          expect(translated.trim(), isNotEmpty, reason: message.key);
          expect(
            placeholders.allMatches(translated).map((m) => m[0]).toSet(),
            placeholders.allMatches(message.value).map((m) => m[0]).toSet(),
            reason: '${entry.key}:${message.key}',
          );
          if (entry.key != 'en') {
            expect(translated, isNot(message.value),
                reason: '${entry.key}:${message.key}');
          }
          // Product and file names stay as they are in every language.
          if (message.value.contains('Get More RAM')) {
            expect(translated, contains('Get More RAM'), reason: message.key);
          }
          if (message.value.contains('PS3UPDAT.PUP')) {
            expect(translated, contains('PS3UPDAT.PUP'), reason: message.key);
          }
        }
      });
    }

    test('the French lead is the maintainer\'s sentence', () {
      expect(
        Rpcs3FirmwareLocale.values['fr']!['preflightLead'],
        'Avant d’installer le firmware PS3 dans NeoStation, installez '
        'l’application Get More RAM, ou réinstallez-la si nécessaire, puis '
        'suivez sa procédure. Revenez ensuite dans NeoStation pour poursuivre '
        'l’installation du firmware.',
      );
      expect(
        Rpcs3FirmwareLocale.getMoreRamUrl,
        'https://github.com/hugeBlack/GetMoreRam',
      );
    });

    test('script and regional Chinese settings select Traditional Chinese', () {
      final traditional =
          Rpcs3FirmwareLocale.values['zh_Hant']!['preflightTitleInstall'];
      for (final locale in <Locale>[
        const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
        const Locale('zh', 'TW'),
        const Locale('zh', 'HK'),
        const Locale('zh', 'MO'),
        const Locale('zh_Hant'),
      ]) {
        expect(Rpcs3FirmwareLocale.localeKey(locale), 'zh_Hant',
            reason: '$locale');
        expect(
          Rpcs3FirmwareLocale.forLocale(locale, 'preflightTitleInstall'),
          traditional,
        );
      }
      for (final locale in <Locale>[
        const Locale('zh'),
        const Locale('zh', 'CN'),
        const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hans'),
      ]) {
        expect(Rpcs3FirmwareLocale.localeKey(locale), 'zh', reason: '$locale');
      }
      expect(Rpcs3FirmwareLocale.localeKey(const Locale('xx')), 'en');
    });
  });

  group('dialog', () {
    Future<bool?> open(
      WidgetTester tester, {
      required bool reinstall,
      Locale locale = const Locale('en'),
      Future<bool> Function(Uri uri)? openUrl,
    }) async {
      bool? result;
      var opened = false;
      await tester.pumpWidget(
        MaterialApp(
          locale: locale,
          supportedLocales: const [Locale('en'), Locale('fr')],
          localizationsDelegates: GlobalMaterialLocalizations.delegates,
          home: Builder(
            builder: (context) => Scaffold(
              body: Center(
                child: ElevatedButton(
                  key: const ValueKey('open'),
                  onPressed: () async {
                    opened = true;
                    result = await showRpcs3FirmwarePreflight(
                      context,
                      reinstall: reinstall,
                      openUrl: openUrl,
                    );
                  },
                  child: const Text('open'),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.byKey(const ValueKey('open')));
      await tester.pumpAndSettle();
      expect(opened, isTrue);
      expect(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-dialog')),
        findsOneWidget,
      );
      return result;
    }

    testWidgets('first installation: steps, distinction, Back returns false',
        (tester) async {
      bool? result;
      await open(tester, reinstall: false).then((_) {});
      expect(find.text('Before installing the PS3 firmware'), findsOneWidget);
      expect(find.text(english['preflightLead']!), findsOneWidget);
      for (var step = 1; step <= 5; step++) {
        expect(find.text(english['preflightStep$step']!), findsOneWidget);
        expect(find.text('$step.'), findsOneWidget);
      }
      expect(find.text(english['preflightDistinction']!), findsOneWidget);
      expect(find.text(english['preflightNoCheck']!), findsOneWidget);
      expect(find.text(Rpcs3FirmwareLocale.getMoreRamUrl), findsOneWidget);
      expect(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-continue')),
        findsOneWidget,
      );
      // The result of showRpcs3FirmwarePreflight is observed through the
      // dialog's own pop: Back pops false, which the caller maps to "stay".
      final navigator = tester.state<NavigatorState>(find.byType(Navigator));
      final element = tester.element(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-back')),
      );
      final route = ModalRoute.of(element)!;
      route.popped.then((value) => result = value as bool?);
      await tester.tap(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-back')),
      );
      await tester.pumpAndSettle();
      expect(result, isFalse);
      expect(navigator.canPop(), isFalse);
      expect(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-dialog')),
        findsNothing,
      );
    });

    testWidgets('reinstallation title, Continue returns true', (tester) async {
      bool? result;
      await open(tester, reinstall: true);
      expect(
        find.text('Before reinstalling the PS3 firmware'),
        findsOneWidget,
      );
      final element = tester.element(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-continue')),
      );
      ModalRoute.of(element)!.popped.then((value) => result = value as bool?);
      await tester.tap(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-continue')),
      );
      await tester.pumpAndSettle();
      expect(result, isTrue);
    });

    testWidgets('the page link opens the verified address, failure is shown',
        (tester) async {
      final opened = <Uri>[];
      await open(
        tester,
        reinstall: false,
        openUrl: (uri) async {
          opened.add(uri);
          return opened.length == 1;
        },
      );
      // The link sits below the fold of the scrollable content.
      await tester.ensureVisible(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-open')),
      );
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-open')),
      );
      await tester.pumpAndSettle();
      expect(opened, [Uri.parse('https://github.com/hugeBlack/GetMoreRam')]);
      expect(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-open-failed')),
        findsNothing,
      );
      await tester.tap(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-open')),
      );
      await tester.pumpAndSettle();
      expect(opened, hasLength(2));
      expect(
        find.text(
          'The page could not be opened. Address: '
          'https://github.com/hugeBlack/GetMoreRam',
        ),
        findsOneWidget,
      );
    });

    testWidgets('French shows the maintainer\'s sentence', (tester) async {
      await open(tester, reinstall: false, locale: const Locale('fr'));
      expect(find.text('Avant d’installer le firmware PS3'), findsOneWidget);
      expect(
        find.text(Rpcs3FirmwareLocale.values['fr']!['preflightLead']!),
        findsOneWidget,
      );
      expect(find.text('Retour'), findsOneWidget);
      expect(find.text('Continuer vers le fichier du firmware'), findsOneWidget);
    });
  });

  group('firmware flows', () {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    const paths = MethodChannel('plugins.flutter.io/path_provider');
    const core = MethodChannel('neostation/rpcs3_internal');
    const jit = MethodChannel('neostation/rpcs3_jit');
    const gamepads = MethodChannel('xyz.luan/gamepads');
    late Directory support;
    late File versionFile;
    late FilePickerPlatform originalPicker;
    late _CancelledPicker picker;
    final nativeCalls = <String>[];

    setUp(() async {
      support = await Directory.systemTemp.createTemp('rpcs3-preflight-');
      versionFile = File(
        path.join(support.path, 'NeoStation', 'RPCS3', 'Data', 'dev_flash',
            'vsh', 'etc', 'version.txt'),
      );
      nativeCalls.clear();
      SharedPreferences.setMockInitialValues({});
      messenger.setMockMethodCallHandler(paths, (_) async => support.path);
      messenger.setMockMethodCallHandler(gamepads, (_) async => <dynamic>[]);
      for (final channel in [core, jit]) {
        messenger.setMockMethodCallHandler(channel, (call) async {
          nativeCalls.add('${channel.name}/${call.method}');
          throw PlatformException(code: 'runtimeMustRemainDormant');
        });
      }
      originalPicker = FilePickerPlatform.instance;
      picker = _CancelledPicker();
      FilePickerPlatform.instance = picker;
    });

    tearDown(() async {
      FilePickerPlatform.instance = originalPicker;
      for (final channel in [paths, core, jit, gamepads]) {
        messenger.setMockMethodCallHandler(channel, null);
      }
      await support.delete(recursive: true);
    });

    Future<void> writeVersion() async {
      await versionFile.parent.create(recursive: true);
      await versionFile.writeAsString('release:04.9100:\n');
    }

    /// Filesystem work completes on the real event loop and widget work on
    /// the test clock: alternate both until [done].
    Future<void> settle(WidgetTester tester, bool Function() done) async {
      for (var frame = 0; !done() && frame < 300; frame++) {
        await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 5)),
        );
        await tester.pump(const Duration(milliseconds: 16));
      }
      expect(done(), isTrue, reason: 'the awaited state must be reached');
      await tester.pumpAndSettle();
    }

    Future<void> openLibrary(WidgetTester tester) async {
      final states = <bool>[];
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) {
              ScreenUtil.init(context, designSize: const Size(800, 600));
              return Scaffold(
                body: Rpcs3InternalPlaylistActions(
                  onLibraryChanged: () async {},
                  onFirmwareChanged: states.add,
                  onBack: () {},
                ),
              );
            },
          ),
        ),
      );
      await settle(tester, () => states.isNotEmpty);
    }

    Finder dialog() =>
        find.byKey(const ValueKey('rpcs3-firmware-preflight-dialog'));

    testWidgets(
        'first installation: Back keeps the gate without opening the picker; '
        'Continue opens the firmware picker once', (tester) async {
      await openLibrary(tester);
      expect(find.text('PS3 firmware required'), findsOneWidget);
      await tester.tap(
        find.byKey(const ValueKey('rpcs3-library-install-firmware')),
      );
      await tester.pumpAndSettle();
      expect(dialog(), findsOneWidget);
      expect(find.text('Before installing the PS3 firmware'), findsOneWidget);
      await tester.tap(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-back')),
      );
      await tester.pumpAndSettle();
      expect(dialog(), findsNothing);
      expect(picker.requests, isEmpty);
      expect(find.text('PS3 firmware required'), findsOneWidget);
      expect(nativeCalls, isEmpty);

      await tester.tap(
        find.byKey(const ValueKey('rpcs3-library-install-firmware')),
      );
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-continue')),
      );
      await settle(tester, () => picker.requests.isNotEmpty);
      expect(picker.requests, ['pup:Select official PS3UPDAT.PUP firmware']);
      expect(dialog(), findsNothing);
      // A cancelled picker leaves the gate and never wakes the Core or JIT.
      expect(find.text('PS3 firmware required'), findsOneWidget);
      expect(nativeCalls, isEmpty);
      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets(
        'reinstallation from the import menu shows the reinstall title first',
        (tester) async {
      await tester.runAsync(writeVersion);
      await openLibrary(tester);
      await tester.tap(find.byKey(const ValueKey('rpcs3-internal-import-menu')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Install PS3 firmware'));
      await tester.pumpAndSettle();
      expect(dialog(), findsOneWidget);
      expect(
        find.text('Before reinstalling the PS3 firmware'),
        findsOneWidget,
      );
      await tester.tap(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-back')),
      );
      await tester.pumpAndSettle();
      expect(picker.requests, isEmpty);
      await tester.tap(find.byKey(const ValueKey('rpcs3-internal-import-menu')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Install PS3 firmware'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-continue')),
      );
      await settle(tester, () => picker.requests.isNotEmpty);
      expect(picker.requests, hasLength(1));
      expect(nativeCalls, isEmpty);
      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('the RPCS3 manager asks before its firmware button acts',
        (tester) async {
      await tester.runAsync(writeVersion);
      await tester.pumpWidget(
        MaterialApp(
          home: Rpcs3ManagerScreen(onLibraryChanged: () async {}),
        ),
      );
      await settle(tester, () => find.text('4.91').evaluate().isNotEmpty);
      await settle(
        tester,
        () => tester
                .widget<FilledButton>(
                  find.byKey(const ValueKey('rpcs3-manager-firmware')),
                )
                .onPressed !=
            null,
      );
      await tester.tap(find.byKey(const ValueKey('rpcs3-manager-firmware')));
      await tester.pumpAndSettle();
      expect(dialog(), findsOneWidget);
      expect(
        find.text('Before reinstalling the PS3 firmware'),
        findsOneWidget,
      );
      await tester.tap(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-back')),
      );
      await tester.pumpAndSettle();
      expect(picker.requests, isEmpty);
      await tester.tap(find.byKey(const ValueKey('rpcs3-manager-firmware')));
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey('rpcs3-firmware-preflight-continue')),
      );
      await settle(tester, () => picker.requests.isNotEmpty);
      expect(picker.requests, hasLength(1));
      await tester.pumpWidget(const SizedBox.shrink());
    });
  });
}
