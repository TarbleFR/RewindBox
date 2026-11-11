import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/xenia_locale.dart';
import 'package:neostation/widgets/switch_playlist_empty_state.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The playlist empty state: Switch shows its title only; Xbox 360 adds the
/// XeniOS hint that says how to import (docs/xenios-playlist.md § User flow).
void main() {
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('fr', AppLocale.fr)],
      initLanguageCode: 'fr',
    );
  });

  Future<void> pump(WidgetTester tester, {String? hint}) => tester.pumpWidget(
    ScreenUtilInit(
      designSize: const Size(1280, 720),
      builder: (context, child) => MaterialApp(
        locale: const Locale('fr'),
        localizationsDelegates:
            FlutterLocalization.instance.localizationsDelegates,
        supportedLocales: FlutterLocalization.instance.supportedLocales,
        home: Scaffold(
          body: SwitchPlaylistEmptyState(
            systemName: 'XB360',
            onBack: () {},
            hint: hint,
          ),
        ),
      ),
    ),
  );

  testWidgets('without a hint (Switch): the title only', (tester) async {
    await pump(tester);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('switch-playlist-empty')), findsOneWidget);
    expect(find.textContaining('XB360'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('switch-playlist-empty-hint')),
      findsNothing,
    );
  });

  testWidgets('with the Xbox 360 hint: shown under the title', (tester) async {
    final hint = XeniaLocale.values['fr']!['emptyBody']!;
    await pump(tester, hint: hint);
    await tester.pumpAndSettle();
    final title = tester.getCenter(find.textContaining('XB360'));
    final shown = tester.getCenter(
      find.byKey(const ValueKey('switch-playlist-empty-hint')),
    );
    expect(find.text(hint), findsOneWidget);
    expect(
      shown.dy,
      greaterThan(title.dy),
      reason: 'the hint sits under the title',
    );
  });

  test(
    'the Xbox 360 hint exists in the 12 locales and names the folder import',
    () {
      expect(XeniaLocale.values.length, 12);
      for (final entry in XeniaLocale.values.entries) {
        expect(entry.value['emptyBody'], isNotEmpty, reason: entry.key);
      }
      expect(XeniaLocale.values['en']!['emptyBody'], contains('default.xex'));
    },
  );
}
