import 'dart:ui';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/l10n/melonx_library_locale.dart';
import 'package:neostation/services/melonx_embedded_library_service.dart';
import 'package:neostation/services/melonx_internal_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'update and DLC IDs normalize to the base game, invalid IDs are refused',
    () {
      expect(
        MelonxEmbeddedLibraryService.baseTitleId('0100123456780800'),
        '0100123456780000',
      );
      expect(
        MelonxEmbeddedLibraryService.baseTitleId('0100123456781001'),
        '0100123456780000',
      );
      for (final value in [
        '',
        '../system',
        '01001234567800000',
        'Z100123456780000',
      ]) {
        expect(
          () => MelonxEmbeddedLibraryService.baseTitleId(value),
          throwsFormatException,
        );
      }
    },
  );
  test('native add-on inspection receives the selected base title and failures propagate', () async {
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    addTearDown(
      () => messenger.setMockMethodCallHandler(
        MelonxInternalService.channel,
        null,
      ),
    );
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
      call,
    ) async {
      expect(call.method, 'inspectUpdate');
      expect(call.arguments, {
        'path': '/Documents/personal.nsp',
        'titleId': '0100123456780000',
      });
      return {
        'success': false,
        'diagnostic': 'Package belongs to another game',
      };
    });
    await expectLater(
      MelonxInternalService.content(
        'inspectUpdate',
        filePath: '/Documents/personal.nsp',
        titleId: '0100123456780000',
      ),
      throwsStateError,
    );
  });
  test('per-game graphics survive an iOS container change and remain distinct across folders', () async {
    SharedPreferences.setMockInitialValues({});
    await MelonxInternalService.saveGraphics(
      '/private/app/OLD/Documents/a/game.nro',
      {'resolution': 0.5, 'asyncShaders': true},
    );
    expect(
      await MelonxInternalService.graphicsForGame(
        '/private/app/NEW/Documents/a/game.nro',
      ),
      {'resolution': 0.5, 'asyncShaders': true},
    );
    expect(
      await MelonxInternalService.graphicsForGame(
        '/private/app/NEW/Documents/b/game.nro',
      ),
      isEmpty,
    );
  });
  test('all Switch library actions are available in the same twelve languages as the controls', () {
    expect(MelonxLibraryLocale.values.length, 12);
    final keys = MelonxLibraryLocale.values['en']!.keys.toSet();
    for (final value in MelonxLibraryLocale.values.values) {
      expect(value.keys.toSet(), keys);
      expect(value.values.every((s) => s.isNotEmpty), isTrue);
    }
    expect(MelonxLibraryLocale.text(const Locale('zh', 'TW'), 'Import'), '匯入');
    expect(
      MelonxLibraryLocale.text(const Locale('fr'), 'Import firmware'),
      'Importer un firmware',
    );
  });
}
