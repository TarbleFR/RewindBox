// Removal of Dusklight, KartPad and the Ports playlist
// (docs/ports-removal-2026-10-20.md): when the database copy that precedes the
// prune is postponed, the former Ports rows stay in data.sqlite. A game from
// them must then be refused with a translated message, without reaching
// another emulator, a RetroArch link or the share sheet, and without touching
// the game file. Driven through the real GameLaunchService.launchGame. Test
// host only: no iPhone claim.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/services/game/game_launch_service.dart';
import 'package:neostation/services/game/game_session_manager.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory scratch;

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [
        MapLocale('en', AppLocale.en),
        MapLocale('fr', AppLocale.fr),
      ],
      initLanguageCode: 'en',
    );
  });

  setUp(() async {
    scratch = await Directory.systemTemp.createTemp('retired-ports-launch-');
  });

  tearDown(() async {
    await scratch.delete(recursive: true);
  });

  for (final (language, expected) in [
    ('en', AppLocale.en[AppLocale.noEmulator]),
    ('fr', AppLocale.fr[AppLocale.noEmulator]),
  ]) {
    testWidgets('a former Ports game is refused ($language)', (tester) async {
      FlutterLocalization.instance.translate(language);
      final file = File(
        p.join(scratch.path, 'Ports', 'Dusklight', 'Games', 'GZ2E01.iso'),
      )..createSync(recursive: true);
      file.writeAsBytesSync(List<int>.filled(32, 3));
      final system = SystemModel(
        id: 'ports',
        folderName: 'ports',
        realName: 'Ports',
        iconImage: '',
        color: '#000000',
      );
      final game = GameModel(
        romname: 'GZ2E01.iso',
        realname: 'Twilight Princess',
        name: 'Twilight Princess',
        year: '',
        developer: '',
        publisher: '',
        genre: '',
        players: '',
        rating: 0,
        romPath: file.path,
      );
      late BuildContext context;
      await tester.pumpWidget(
        MaterialApp(
          locale: Locale(language),
          localizationsDelegates:
              FlutterLocalization.instance.localizationsDelegates,
          supportedLocales: FlutterLocalization.instance.supportedLocales,
          home: Builder(
            builder: (built) {
              context = built;
              return const SizedBox();
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(Localizations.localeOf(context).languageCode, language);

      final result = (await tester.runAsync(
        () => GameLaunchService.launchGame(context, system, game),
      ))!;

      expect(result.success, isFalse);
      expect(expected, isA<String>());
      expect(result.errorMessage, expected);
      expect(result.errorDetails, contains('Ports playlist'));
      expect(result.errorDetails, contains(file.path));
      expect(GameSessionManager.isGameLaunchInProgress, isFalse);
      expect(file.lengthSync(), 32, reason: 'the game file is never touched');
    });
  }
}
