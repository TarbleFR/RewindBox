// Every text of the RAP licence import exists in NeoStation's twelve
// languages, keeps its placeholders, is really translated and selects
// Traditional Chinese from the script or the region.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/rpcs3_rap_locale.dart';
import 'package:neostation/services/rpcs3_rap_licence_service.dart';
import 'package:neostation/widgets/rpcs3_rap_import_report_dialog.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final placeholders = RegExp(r'\{\w+\}');
  final english = Rpcs3RapLocale.values['en']!;

  setUpAll(() {
    // The dialog's controller layer lists controllers: none here.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('xyz.luan/gamepads'),
          (call) async => <dynamic>[],
        );
  });

  test('covers exactly the twelve NeoStation languages', () {
    expect(
      Rpcs3RapLocale.values.keys.toSet(),
      AppLocale.supportedLanguages.keys.toSet(),
    );
    expect(Rpcs3RapLocale.values, hasLength(12));
  });

  for (final entry in Rpcs3RapLocale.values.entries) {
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

  test('the menu label is the one the maintainer asked for', () {
    expect(english['importRapLicenses'], 'Import RAP licenses');
    expect(
      Rpcs3RapLocale.values['fr']!['importRapLicenses'],
      'Importer des licences RAP',
    );
  });

  test('script and regional Chinese settings select Traditional Chinese', () {
    final traditional = Rpcs3RapLocale.values['zh_Hant']!['importRapLicenses'];
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
      const Locale('zh_Hant'),
    ]) {
      expect(Rpcs3RapLocale.localeKey(locale), 'zh_Hant', reason: '$locale');
      expect(
        Rpcs3RapLocale.forLocale(locale, 'importRapLicenses'),
        traditional,
      );
    }
    for (final locale in <Locale>[
      const Locale('zh'),
      const Locale('zh', 'CN'),
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hans'),
    ]) {
      expect(Rpcs3RapLocale.localeKey(locale), 'zh', reason: '$locale');
    }
    expect(
      traditional,
      isNot(Rpcs3RapLocale.values['zh']!['importRapLicenses']),
    );
  });

  test('unknown languages fall back to English, placeholders filled', () {
    expect(Rpcs3RapLocale.localeKey(const Locale('nl')), 'en');
    expect(
      Rpcs3RapLocale.format(const Locale('fr'), 'rapReasonSize', {'size': 17}),
      'Une licence RAP fait exactement 16 octets ; ce fichier en fait 17.',
    );
  });

  // Every report line, in every language, comes from the catalog: rows of
  // all statuses and reasons are rendered and their visible text checked
  // against the catalog values of that language.
  for (final language in Rpcs3RapLocale.values.keys) {
    testWidgets('$language: the report shows only catalog texts', (
      tester,
    ) async {
      final locale = language == 'zh_Hant'
          ? const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')
          : Locale(language);
      final report = Rpcs3RapImportReport([
        for (final rejection in Rpcs3RapRejection.values)
          Rpcs3RapImportEntry(
            fileName: 'file-${rejection.name}.rap',
            status: Rpcs3RapImportStatus.rejected,
            rejection: rejection,
            byteCount: 4096,
          ),
        const Rpcs3RapImportEntry(
          fileName: 'ep0001-bles00000_00-0123456789abcdef.rap',
          contentId: 'EP0001-BLES00000_00-0123456789ABCDEF',
          status: Rpcs3RapImportStatus.imported,
        ),
        const Rpcs3RapImportEntry(
          fileName: 'UP9000-NPUA80472_00-LITTLEBIGPLANET2.rap',
          contentId: 'UP9000-NPUA80472_00-LITTLEBIGPLANET2',
          status: Rpcs3RapImportStatus.replaced,
          backupPath: '/backup',
        ),
        const Rpcs3RapImportEntry(
          fileName: 'JP0001-BLJS00000_00-0000000000000000.rap',
          contentId: 'JP0001-BLJS00000_00-0000000000000000',
          status: Rpcs3RapImportStatus.alreadyPresent,
        ),
      ]);
      await tester.pumpWidget(
        MaterialApp(
          locale: locale,
          supportedLocales: [locale],
          localizationsDelegates: GlobalMaterialLocalizations.delegates,
          home: Scaffold(body: Rpcs3RapImportReportDialog(report: report)),
        ),
      );
      final catalog = Rpcs3RapLocale.values[language]!;
      String fill(String key, Map<String, Object> values) {
        var text = catalog[key]!;
        values.forEach((k, v) => text = text.replaceAll('{$k}', '$v'));
        return text;
      }

      expect(find.text(catalog['rapReportTitle']!), findsOneWidget);
      expect(
        find.text(
          [
            fill('rapCountImported', {'count': 1}),
            fill('rapCountReplaced', {'count': 1}),
            fill('rapCountAlreadyPresent', {'count': 1}),
            fill('rapCountRejected', {
              'count': Rpcs3RapRejection.values.length,
            }),
          ].join(' • '),
        ),
        findsOneWidget,
      );
      for (final key in [
        'rapReasonNotRap',
        'rapReasonUnreadable',
        'rapReasonSelectionConflict',
        'rapReasonConflictKept',
        'rapReasonStorageRedirected',
        'rapReasonWriteFailed',
        'rapStatusImported',
        'rapStatusReplaced',
        'rapStatusAlreadyPresent',
        'rapBackupKept',
        'rapClose',
      ]) {
        expect(find.text(catalog[key]!), findsOneWidget, reason: key);
      }
      expect(
        find.text(catalog['rapStatusRejected']!),
        findsNWidgets(Rpcs3RapRejection.values.length),
      );
      expect(
        find.text(
          fill('rapReasonContentId', {
            'example': Rpcs3RapLicenceService.exampleContentId,
          }),
        ),
        findsOneWidget,
      );
      expect(find.text(fill('rapReasonSize', {'size': 4096})), findsOneWidget);
      expect(
        find.text(
          fill('rapInstalledAs', {
            'name': 'EP0001-BLES00000_00-0123456789ABCDEF.rap',
          }),
        ),
        findsOneWidget,
      );
    });
  }
}
