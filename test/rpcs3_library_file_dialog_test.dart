// Build 554: before RPCS3 copies a library-folder PS3 disc into its own
// library, the launcher says so (file, size, disc key) and lets the user
// decline; the copy then runs under a progress dialog that cannot be
// dismissed and closes when RPCS3 is done. Twelve languages.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/rpcs3_library_file_locale.dart';
import 'package:neostation/services/rpcs3_disc_image.dart';
import 'package:neostation/services/rpcs3_library_file_service.dart';
import 'package:neostation/widgets/rpcs3_library_file_install_dialog.dart';
import 'package:rpcs3_internal_bridge/rpcs3_internal_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final placeholders = RegExp(r'\{\w+\}');
  final english = Rpcs3LibraryFileLocale.values['en']!;

  group('twelve-language catalogue', () {
    test('covers exactly the twelve RewindBox languages', () {
      expect(
        Rpcs3LibraryFileLocale.values.keys.toSet(),
        AppLocale.supportedLanguages.keys.toSet(),
      );
    });

    for (final entry in Rpcs3LibraryFileLocale.values.entries) {
      test('${entry.key}: complete, placeholders kept, translated', () {
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
          // Product and file-type names stay as they are.
          for (final name in ['RPCS3', 'RewindBox', '.dkey', '.key', 'ISO']) {
            if (message.value.contains(name)) {
              expect(
                translated,
                contains(name),
                reason: '${entry.key}:${message.key}',
              );
            }
          }
        }
      });
    }

    test('every failure has its own text', () {
      final texts = {
        for (final failure in Rpcs3LibraryFileFailure.values)
          Rpcs3LibraryFileLocale.failure(const Locale('fr'), failure),
      };
      expect(texts, hasLength(Rpcs3LibraryFileFailure.values.length));
      expect(
        Rpcs3LibraryFileLocale.failure(
          const Locale('fr'),
          Rpcs3LibraryFileFailure.discKeyRequired,
        ),
        contains('.dkey'),
      );
    });

    test('script and regional Chinese settings select Traditional Chinese', () {
      for (final locale in <Locale>[
        const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
        const Locale('zh', 'TW'),
        const Locale('zh', 'HK'),
      ]) {
        expect(Rpcs3LibraryFileLocale.localeKey(locale), 'zh_Hant');
      }
      expect(Rpcs3LibraryFileLocale.localeKey(const Locale('zh')), 'zh');
      expect(Rpcs3LibraryFileLocale.localeKey(const Locale('xx')), 'en');
    });
  });

  Widget app(
    Widget Function(BuildContext context) button, {
    Locale locale = const Locale('fr'),
  }) => MaterialApp(
    locale: locale,
    supportedLocales: const [Locale('en'), Locale('fr')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    home: Builder(
      builder: (context) => Scaffold(body: Center(child: button(context))),
    ),
  );

  const plan = Rpcs3LibraryFilePlan(
    romPath:
        '/var/mobile/Documents/roms/ps3/Call of Duty - Black Ops (USA) (En,Fr).iso',
    sizeBytes: 12345678901,
    identity: Rpcs3DiscIdentity(
      titleId: 'BLUS30591',
      title: 'Call of Duty®: Black Ops',
      category: 'DG',
    ),
    keyPath:
        '/var/mobile/Documents/roms/ps3/Call of Duty - Black Ops (USA) (En,Fr).dkey',
  );

  group('prompt', () {
    Future<List<bool>> open(
      WidgetTester tester,
      Rpcs3LibraryFilePlan plan,
    ) async {
      final results = <bool>[];
      await tester.pumpWidget(
        app(
          (context) => ElevatedButton(
            key: const ValueKey('open'),
            onPressed: () async => results.add(
              await showRpcs3LibraryFileInstallPrompt(context, plan),
            ),
            child: const Text('open'),
          ),
        ),
      );
      await tester.tap(find.byKey(const ValueKey('open')));
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('rpcs3-library-file-prompt')),
        findsOneWidget,
      );
      return results;
    }

    testWidgets(
      'names the file, its size, the disc and its key; Install returns true',
      (tester) async {
        final results = await open(tester, plan);
        final fr = Rpcs3LibraryFileLocale.values['fr']!;
        expect(find.text(fr['promptTitle']!), findsOneWidget);
        expect(
          find.text(
            fr['promptBody']!
                .replaceAll(
                  '{file}',
                  'Call of Duty - Black Ops (USA) (En,Fr).iso',
                )
                .replaceAll('{size}', '12.3 GB'),
          ),
          findsOneWidget,
        );
        expect(
          find.text('Call of Duty®: Black Ops · BLUS30591'),
          findsOneWidget,
        );
        expect(
          find.text(
            'Clé de disque trouvée : Call of Duty - Black Ops (USA) (En,Fr).dkey',
          ),
          findsOneWidget,
        );
        await tester.tap(
          find.byKey(const ValueKey('rpcs3-library-file-install')),
        );
        await tester.pumpAndSettle();
        expect(results, [true]);
        expect(
          find.byKey(const ValueKey('rpcs3-library-file-prompt')),
          findsNothing,
        );
      },
    );

    testWidgets('Cancel returns false; no identity or key line when unknown', (
      tester,
    ) async {
      final results = await open(
        tester,
        const Rpcs3LibraryFilePlan(
          romPath: '/roms/ps3/Encrypted.iso',
          sizeBytes: 1000,
        ),
      );
      expect(
        find.byKey(const ValueKey('rpcs3-library-file-identity')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey('rpcs3-library-file-key')),
        findsNothing,
      );
      await tester.tap(find.byKey(const ValueKey('rpcs3-library-file-cancel')));
      await tester.pumpAndSettle();
      expect(results, [false]);
    });
  });

  testWidgets('progress follows RPCS3 and closes with the task', (
    tester,
  ) async {
    final events = StreamController<Rpcs3InstallProgress>.broadcast();
    final task = Completer<String>();
    final screen = <String>[];
    String? result;
    await tester.pumpWidget(
      app(
        (context) => ElevatedButton(
          key: const ValueKey('open'),
          onPressed: () async {
            result = await runWithRpcs3LibraryFileProgress(
              context,
              plan,
              () => task.future,
              progress: events.stream,
              keepScreenOn: () async {
                screen.add('on');
                return () async => screen.add('off');
              },
            );
          },
          child: const Text('open'),
        ),
      ),
    );
    await tester.tap(find.byKey(const ValueKey('open')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    final fr = Rpcs3LibraryFileLocale.values['fr']!;
    expect(
      find.byKey(const ValueKey('rpcs3-library-file-progress')),
      findsOneWidget,
    );
    expect(find.text(fr['progressTitle']!), findsOneWidget);
    expect(find.text(fr['progressPreparing']!), findsOneWidget);
    expect(find.text(fr['progressKeepOpen']!), findsOneWidget);
    expect(screen, ['on'], reason: 'the screen stays on while RPCS3 copies');

    events.add(
      const Rpcs3InstallProgress(
        current: 460,
        total: 1000,
        detail: 'Copying disc image',
      ),
    );
    await tester.pump();
    expect(find.text('46 %'), findsOneWidget);
    expect(find.text('Copying disc image'), findsOneWidget);

    // The back gesture does not close it while RPCS3 copies.
    final navigator = tester.state<NavigatorState>(
      find.byType(Navigator).first,
    );
    await navigator.maybePop();
    await tester.pump();
    expect(
      find.byKey(const ValueKey('rpcs3-library-file-progress')),
      findsOneWidget,
    );

    task.complete('BLUS30591');
    await tester.pumpAndSettle();
    expect(result, 'BLUS30591');
    expect(screen, ['on', 'off']);
    expect(
      find.byKey(const ValueKey('rpcs3-library-file-progress')),
      findsNothing,
    );
    await events.close();
  });
}
