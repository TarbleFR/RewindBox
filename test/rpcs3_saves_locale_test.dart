// Every text of the game-save exchange exists in NeoStation's twelve
// languages, keeps its placeholders, is really translated, selects
// Traditional Chinese from the script, the region or a language tag, and
// the report dialogs show only catalog texts around the raw names.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/rpcs3_saves_locale.dart';
import 'package:neostation/l10n/rpcs3_ui_locale.dart';
import 'package:neostation/services/rpcs3_save_exchange_service.dart';
import 'package:neostation/widgets/rpcs3_save_exchange_dialogs.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final placeholders = RegExp(r'\{\w+\}');
  final english = Rpcs3SavesLocale.values['en']!;

  setUpAll(() {
    // The dialogs' controller layer lists controllers: none here.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('xyz.luan/gamepads'),
          (call) async => <dynamic>[],
        );
  });

  test('covers exactly the twelve NeoStation languages', () {
    expect(
      Rpcs3SavesLocale.values.keys.toSet(),
      AppLocale.supportedLanguages.keys.toSet(),
    );
    expect(Rpcs3SavesLocale.values, hasLength(12));
  });

  for (final entry in Rpcs3SavesLocale.values.entries) {
    test('${entry.key}: complete, placeholders kept, no English fallback', () {
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
          expect(
            translated,
            isNot(message.value),
            reason: '${entry.key}:${message.key}',
          );
        }
      }
    });
  }

  test('the manager labels now name game saves, in every language', () {
    for (final language in AppLocale.supportedLanguages.keys) {
      for (final key in ['exportSaves', 'importSaves']) {
        final label = Rpcs3UiLocale.textForLocale(language, key);
        expect(label, isNot(contains('avestate')), reason: '$language:$key');
        expect(label, isNot(contains('+')), reason: '$language:$key');
        if (language != 'en') {
          expect(
            label,
            isNot(Rpcs3UiLocale.textForLocale('en', key)),
            reason: '$language:$key',
          );
        }
      }
    }
    expect(Rpcs3UiLocale.textForLocale('en', 'exportSaves'), 'Export game saves');
    expect(Rpcs3UiLocale.textForLocale('en', 'importSaves'), 'Import game saves');
  });

  test('the busy message says the game must be closed first', () {
    expect(
      english['busyGameRunning'],
      'A PS3 game is running. Close it first: RPCS3 may be writing a save.',
    );
    expect(
      Rpcs3SavesLocale.values['fr']!['busyGameRunning'],
      'Un jeu PS3 est en cours. Fermez-le d’abord : RPCS3 est peut-être en train d’écrire une sauvegarde.',
    );
  });

  test('script and regional Chinese settings select Traditional Chinese', () {
    final traditional = Rpcs3SavesLocale.values['zh_Hant']!['importSourceTitle'];
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
      const Locale('zh_Hant'),
    ]) {
      expect(Rpcs3SavesLocale.localeKey(locale), 'zh_Hant', reason: '$locale');
      expect(
        Rpcs3SavesLocale.forLocale(locale, 'importSourceTitle'),
        traditional,
      );
    }
    for (final locale in <Locale>[
      const Locale('zh'),
      const Locale('zh', 'CN'),
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hans'),
    ]) {
      expect(Rpcs3SavesLocale.localeKey(locale), 'zh', reason: '$locale');
    }
    expect(
      traditional,
      isNot(Rpcs3SavesLocale.values['zh']!['importSourceTitle']),
    );
    for (final tag in ['zh-Hant-TW', 'zh_TW', 'zh-HK', 'zh_Hant', 'zh-MO']) {
      expect(Rpcs3SavesLocale.localeKeyForTag(tag), 'zh_Hant', reason: tag);
    }
    for (final tag in ['zh', 'zh-CN', 'zh-Hans-CN']) {
      expect(Rpcs3SavesLocale.localeKeyForTag(tag), 'zh', reason: tag);
    }
    expect(Rpcs3SavesLocale.localeKeyForTag('fr-FR'), 'fr');
    expect(Rpcs3SavesLocale.localeKeyForTag('pt_BR'), 'pt');
    expect(Rpcs3SavesLocale.localeKeyForTag('nl'), 'en');
    expect(
      Rpcs3SavesLocale.textForLocale('de', 'cancel'),
      Rpcs3SavesLocale.values['de']!['cancel'],
    );
  });

  test('unknown languages fall back to English, placeholders filled', () {
    expect(Rpcs3SavesLocale.localeKey(const Locale('nl')), 'en');
    expect(
      Rpcs3SavesLocale.format(const Locale('fr'), 'exportSummary', {
        'saves': 2,
        'files': 7,
        'size': '1.2 MB',
      }),
      'Sauvegardes : 2 • Fichiers : 7 • Taille : 1.2 MB',
    );
  });

  // Every report line, in every language, comes from the catalog: rows of
  // all statuses and rejections are rendered and their visible text checked
  // against the catalog values of that language.
  for (final language in Rpcs3SavesLocale.values.keys) {
    testWidgets('$language: the import report shows only catalog texts', (
      tester,
    ) async {
      final locale = language == 'zh_Hant'
          ? const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')
          : Locale(language);
      final report = Rpcs3SaveImportReport(
        sourceKind: Rpcs3SaveImportSourceKind.zipFile,
        sourceName: 'RPCS3-saves-20261011-153012.zip',
        entries: [
          for (final rejection in Rpcs3SaveRejection.values)
            if (rejection != Rpcs3SaveRejection.conflictKept)
              Rpcs3SaveImportEntry(
                name: 'REJECTED-${rejection.name}',
                status: Rpcs3SaveImportStatus.rejected,
                rejection: rejection,
                technicalDetail: 'detail ${rejection.name}',
              ),
          const Rpcs3SaveImportEntry(
            name: 'BLES01234-SAVE',
            title: 'Imported Title',
            status: Rpcs3SaveImportStatus.imported,
            fileCount: 3,
            byteCount: 5300,
          ),
          const Rpcs3SaveImportEntry(
            name: 'NPUB30000-AUTO',
            title: 'Replaced Title',
            status: Rpcs3SaveImportStatus.replaced,
            fileCount: 2,
            byteCount: 100,
            backupPath: '/backup',
          ),
          const Rpcs3SaveImportEntry(
            name: 'BLUS30000-PRESENT',
            status: Rpcs3SaveImportStatus.alreadyPresent,
            fileCount: 1,
            byteCount: 10,
          ),
          const Rpcs3SaveImportEntry(
            name: 'BLUS30001-KEPT',
            status: Rpcs3SaveImportStatus.kept,
            rejection: Rpcs3SaveRejection.conflictKept,
            fileCount: 1,
            byteCount: 10,
          ),
        ],
      );
      await tester.pumpWidget(
        MaterialApp(
          locale: locale,
          supportedLocales: [locale],
          localizationsDelegates: GlobalMaterialLocalizations.delegates,
          home: Scaffold(body: Rpcs3SaveImportReportDialog(report: report)),
        ),
      );
      final catalog = Rpcs3SavesLocale.values[language]!;
      String fill(String key, Map<String, Object> values) {
        var text = catalog[key]!;
        values.forEach((k, v) => text = text.replaceAll('{$k}', '$v'));
        return text;
      }

      final rejectedCount = Rpcs3SaveRejection.values.length - 1;
      expect(find.text(catalog['importTitle']!), findsOneWidget);
      expect(
        find.text(
          [
            fill('countImported', {'count': 1}),
            fill('countReplaced', {'count': 1}),
            fill('countAlreadyPresent', {'count': 1}),
            fill('countKept', {'count': 1}),
            fill('countRejected', {'count': rejectedCount}),
          ].join(' • '),
        ),
        findsOneWidget,
      );
      expect(
        find.text(
          fill('importSourceLabel', {'name': 'RPCS3-saves-20261011-153012.zip'}),
        ),
        findsOneWidget,
      );
      for (final key in [
        'reasonInvalidName',
        'reasonInvalidParamSfo',
        'reasonDuplicate',
        'reasonConflictKept',
        'reasonStorageRedirected',
        'reasonUnsafeEntry',
        'reasonSymbolicLink',
        'reasonInvalidArchive',
        'reasonNoSave',
        'reasonUnreadable',
        'reasonCorruptData',
        'reasonWriteFailed',
        'statusImported',
        'statusReplaced',
        'statusAlreadyPresent',
        'statusKept',
        'backupKept',
        'importDestination',
        'close',
      ]) {
        expect(find.text(catalog[key]!), findsOneWidget, reason: key);
      }
      expect(
        find.text(catalog['statusRejected']!),
        findsNWidgets(rejectedCount),
      );
      expect(
        find.text(
          fill('reasonTooManyEntries', {
            'max': Rpcs3SaveExchangeService.defaultMaxEntries,
          }),
        ),
        findsOneWidget,
      );
      expect(
        find.text(
          fill('reasonTooLarge', {
            'max': Rpcs3SaveExchangeService.defaultMaxTotalLabel,
          }),
        ),
        findsOneWidget,
      );
      expect(
        find.text(
          fill('reasonFileTooLarge', {
            'max': Rpcs3SaveExchangeService.defaultMaxFileLabel,
          }),
        ),
        findsOneWidget,
      );
      expect(
        find.text(fill('itemSize', {'files': 3, 'size': '5.3 KB'})),
        findsOneWidget,
      );
      expect(find.text('Imported Title'), findsOneWidget);
      expect(find.text('BLES01234-SAVE'), findsOneWidget);
      expect(find.text('detail unsafeEntry'), findsOneWidget);
    });
  }

  testWidgets('the export report names the Files location and the archive', (
    tester,
  ) async {
    const result = Rpcs3SaveExportResult(
      zipPath: '/Documents/RPCS3/Export/Game Saves/RPCS3-saves-20261011-153012.zip',
      saveCount: 2,
      fileCount: 7,
      byteCount: 1200000,
      directories: ['BLES01234-SAVE', 'NPUB30000-AUTO'],
      skipped: [
        Rpcs3SaveImportEntry(
          name: 'bad name!',
          status: Rpcs3SaveImportStatus.rejected,
          rejection: Rpcs3SaveRejection.invalidDirectoryName,
        ),
      ],
      otherUsersWithSaves: ['00000002'],
    );
    var shared = '';
    await tester.pumpWidget(
      MaterialApp(
        locale: const Locale('fr'),
        supportedLocales: const [Locale('fr')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: Scaffold(
          body: Rpcs3SaveExportReportDialog(
            result: result,
            onShare: (path) async => shared = path,
          ),
        ),
      ),
    );
    final fr = Rpcs3SavesLocale.values['fr']!;
    expect(find.text(fr['exportTitle']!), findsOneWidget);
    expect(
      find.text('Sauvegardes : 2 • Fichiers : 7 • Taille : 1.2 MB'),
      findsOneWidget,
    );
    expect(
      find.text(
        'Fichiers › Sur mon iPhone › NeoStation › RPCS3 › Export › Game Saves › RPCS3-saves-20261011-153012.zip',
      ),
      findsOneWidget,
    );
    expect(find.text(fr['exportShareHint']!), findsOneWidget);
    expect(find.text('BLES01234-SAVE'), findsOneWidget);
    expect(
      find.text(fr['exportSkipped']!.replaceAll('{count}', '1')),
      findsOneWidget,
    );
    expect(find.text('bad name!'), findsOneWidget);
    expect(
      find.text(fr['exportOtherUsers']!.replaceAll('{users}', '00000002')),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const ValueKey('rpcs3-saves-share')));
    await tester.pump();
    expect(shared, result.zipPath);
  });

  testWidgets('the source dialog offers the three sources and cancel', (
    tester,
  ) async {
    Rpcs3SaveImportSourceKind? chosen;
    var closed = false;
    await tester.pumpWidget(
      MaterialApp(
        locale: const Locale('en'),
        supportedLocales: const [Locale('en')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: FilledButton(
                onPressed: () async {
                  chosen = await showRpcs3SaveImportSourceDialog(context);
                  closed = true;
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    for (final key in [
      'rpcs3-saves-source-files',
      'rpcs3-saves-source-zip',
      'rpcs3-saves-source-folder',
      'rpcs3-saves-source-cancel',
    ]) {
      expect(find.byKey(ValueKey(key)), findsOneWidget, reason: key);
    }
    expect(find.text(english['sourceFilesFolderHint']!), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('rpcs3-saves-source-zip')));
    await tester.pumpAndSettle();
    expect(chosen, Rpcs3SaveImportSourceKind.zipFile);
    expect(closed, isTrue);
  });

  testWidgets('the replace prompt defaults to keeping the installed saves', (
    tester,
  ) async {
    bool? answer;
    await tester.pumpWidget(
      MaterialApp(
        locale: const Locale('en'),
        supportedLocales: const [Locale('en')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: FilledButton(
                onPressed: () async {
                  answer = await showRpcs3SaveReplaceDialog(context, const []);
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text(english['replaceTitle']!), findsOneWidget);
    expect(find.text(english['replaceBody']!.replaceAll('{count}', '0')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('rpcs3-saves-keep')));
    await tester.pumpAndSettle();
    expect(answer, isFalse);
  });
}
