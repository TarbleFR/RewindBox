import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/services/libretro_core_build_info.dart';
import 'package:neostation/widgets/libretro_engine_panel.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('fr', AppLocale.fr)],
      initLanguageCode: 'fr',
    );
  });

  testWidgets(
    'a playlist shows the versions of its actual default and alternative cores',
    (tester) async {
      const channel = MethodChannel('neostation/libretro_internal');
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(channel, (call) async {
        if (call.method == 'availableCores') {
          return ['genesis_plus_gx', 'genesis_plus_gx_wide', 'mesen'];
        }
        expect(call.method, 'coreBuildInfo');
        final arguments = call.arguments as Map;
        expect(arguments['inspectBinary'], isTrue);
        return switch (arguments['coreId']) {
          'genesis_plus_gx' => {'name': 'Genesis Plus GX', 'version': '1.7.4'},
          'genesis_plus_gx_wide' => {
            'name': 'Genesis Plus GX',
            'version': '2.0.1',
          },
          'mesen' => {'name': 'Mesen test build', 'version': '0.9.9'},
          _ => null,
        };
      });
      addTearDown(() => messenger.setMockMethodCallHandler(channel, null));

      Future<void> show(String system) async {
        // The immutable collection identity is read from the installed bundle.
        final builds = await tester.runAsync(
          () => LibretroCoreBuildInfo.forSystem(system),
        );
        await tester.pumpWidget(
          ScreenUtilInit(
            designSize: const Size(640, 480),
            builder: (_, _) => MaterialApp(
              locale: const Locale('fr'),
              supportedLocales: const [Locale('fr')],
              localizationsDelegates: [
                ...FlutterLocalization.instance.localizationsDelegates,
                ...GlobalMaterialLocalizations.delegates,
              ],
              home: Scaffold(
                body: LibretroEngineIdentityTile(
                  systemKey: system,
                  coreBuilds: builds,
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
      }

      await show('md');
      String identity() =>
          (tester.widget<ListTile>(find.byType(ListTile)).subtitle! as Text)
              .data!;
      expect(
        identity(),
        'Embarqué dans RewindBox · Genesis Plus GX (par défaut) · Version 1.7.4\n'
        'Genesis Plus GX Wide · Version 2.0.1',
      );
      expect(find.textContaining('PicoDrive'), findsNothing);

      // Only the alternative is present in this playlist.
      await show('nes');
      expect(
        find.text('Embarqué dans RewindBox · Mesen test build · Version 0.9.9'),
        findsOneWidget,
      );
      expect(find.textContaining('Nestopia'), findsNothing);

      await show('snes');
      expect(
        find.text('Non incluse dans cette version de RewindBox'),
        findsOneWidget,
      );
      expect(find.byIcon(Icons.check_circle), findsNothing);
    },
  );
}
