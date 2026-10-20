import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/legal_credits_locale.dart';
import 'package:neostation/screens/settings_screen/legal_credits_dialog.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('Libretro notices and Azahar license are available offline', () async {
    final credits = await rootBundle.loadString(
      'assets/legal/libretro/LIBRETRO_CORES.md',
    );
    // 14 cores, 30 with the sixteen of lot 1, 34 with the four of lot 2
    // (14 October 2026), then 35 with Mesen (20 October 2026, NES HD packs).
    expect(credits, contains('35 iOS ARM64 libretro core binaries'));
    expect(credits, contains('Mesen'));
    expect(credits, contains('Snes9x'));
    expect(credits, contains('Beetle PCE Fast'));
    expect(credits, contains('Uzem'));
    expect(credits, contains('FreeIntv'));
    expect(credits, contains('Beetle PC-FX'));
    expect(credits, contains('FinalBurn Neo'));
    expect(credits, contains('GPLv3 or later'));
    final license = await rootBundle.loadString(
      'assets/legal/libretro/azahar-LICENSE.txt',
    );
    expect(license, contains('Version 3, 29 June 2007'));
  });

  testWidgets('Embedded-core notice is translated in all twelve locales', (
    tester,
  ) async {
    const locales = [
      Locale('en'), Locale('es'), Locale('ru'), Locale('zh'),
      Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      Locale('pt'), Locale('fr'), Locale('de'), Locale('it'),
      Locale('id'), Locale('ja'), Locale('ko'),
    ];
    final labels = <String>{};
    for (final locale in locales) {
      await tester.pumpWidget(MaterialApp(
        locale: locale,
        supportedLocales: locales,
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: Builder(builder: (context) {
          final label = LegalCreditsLocale.embeddedCoreLicenses(context);
          labels.add(label);
          return Text(label);
        }),
      ));
      await tester.pumpAndSettle();
    }
    expect(labels.length, 12, reason: 'No locale should fall back to English');
    expect(labels, contains('Cœurs embarqués : chaque cœur conserve sa propre licence.'));
    expect(labels, contains('內建核心：每個核心均保留其自身授權。'));
  });

  testWidgets('Libretro credit opens the bundled core notices', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (context) => Scaffold(
        body: TextButton(
          onPressed: () => LegalCreditsDialog.show(context),
          child: const Text('Credits'),
        ),
      )),
    ));
    await tester.tap(find.text('Credits'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('RetroArch / libretro'), 250,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('External integration; upstream licenses apply'), findsNothing);
    expect(find.textContaining('Embedded cores:'), findsOneWidget);
    await tester.runAsync(() async {
      await tester.tap(find.text('RetroArch / libretro'));
      // Wait for the real bundle I/O outside the widget test's fake clock.
      await rootBundle.loadString('assets/legal/libretro/LIBRETRO_CORES.md');
    });
    await tester.pumpAndSettle();
    expect(find.byType(SelectableText), findsOneWidget);
    expect(tester.widget<SelectableText>(find.byType(SelectableText)).data,
        contains('Source provenance and known limitation'));
  });
}
