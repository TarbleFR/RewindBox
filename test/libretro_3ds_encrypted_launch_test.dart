import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/services/libretro_3ds_containers.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

/// Build 448: the 3DS core refuses every encrypted NCCH whatever keys are
/// installed (azahar `NCCHContainer::LoadHeader`, `ErrorEncrypted`), so an
/// encrypted game is refused before the session starts, with a translated
/// message and the header read as the technical detail; a decrypted game
/// and the formats the check does not read reach the core as before.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const paths = MethodChannel('plugins.flutter.io/path_provider');
  const bridge = MethodChannel('neostation/libretro_internal');
  late Directory root;
  final launches = <Map<Object?, Object?>>[];

  /// An NCCH header of [length] bytes: `NCCH` at 0x100, flags[7] at 0x18F.
  Uint8List ncch({required bool decrypted, int length = 0x200}) {
    final out = Uint8List(length);
    for (var i = 0; i < 0x100; i++) {
      out[i] = (i * 13 + 7) & 0xFF;
    }
    out.setAll(0x100, 'NCCH'.codeUnits);
    if (length > 0x18F) out[0x18F] = decrypted ? 0x04 : 0x00;
    return out;
  }

  /// An NCSD game (`.3ds`): `NCSD` at 0x100, partition 0 at media unit
  /// [unit] (0x200 bytes each), its NCCH there.
  Uint8List ncsd({required bool decrypted, int unit = 0x20}) {
    final out = Uint8List(unit * 0x200 + 0x400);
    out.setAll(0x100, 'NCSD'.codeUnits);
    ByteData.sublistView(out)
      ..setUint32(0x120, unit, Endian.little)
      ..setUint32(0x124, 2, Endian.little);
    out.setAll(unit * 0x200, ncch(decrypted: decrypted));
    return out;
  }

  File write(String name, List<int> bytes) =>
      File(p.join(root.path, 'roms', '3ds', name))
        ..createSync(recursive: true)
        ..writeAsBytesSync(bytes);

  SystemModel system() => SystemModel(
    id: '3ds',
    folderName: '3ds',
    realName: 'Nintendo 3DS',
    iconImage: '',
    color: '#000000',
  );

  GameModel game(File file) => GameModel(
    romname: p.basename(file.path),
    realname: p.basename(file.path),
    name: p.basenameWithoutExtension(file.path),
    year: '',
    developer: '',
    publisher: '',
    genre: '',
    players: '',
    rating: 0,
    romPath: file.path,
  );

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    root = await Directory.systemTemp.createTemp('libretro_3ds_encrypted_');
    launches.clear();
    messenger.setMockMethodCallHandler(paths, (_) async => root.path);
    messenger.setMockMethodCallHandler(bridge, (call) async {
      if (call.method == 'launch') {
        launches.add(Map<Object?, Object?>.from(call.arguments as Map));
        return <String, Object?>{
          'success': true,
          'libraryName': 'mock',
          'libraryVersion': '0',
        };
      }
      return null;
    });
  });

  tearDown(() {
    messenger.setMockMethodCallHandler(paths, null);
    messenger.setMockMethodCallHandler(bridge, null);
    root.deleteSync(recursive: true);
  });

  test(
    'the header check reads an NCSD at partition 0 and a bare NCCH',
    () async {
      final encryptedCart = write('cart.3ds', ncsd(decrypted: false));
      final decryptedCart = write('cart-decrypted.3ds', ncsd(decrypted: true));
      final encryptedCxi = write('game.cxi', ncch(decrypted: false));
      final decryptedCxi = write('game-decrypted.cxi', ncch(decrypted: true));
      expect(
        await Libretro3dsNcch.encryptedGameDetail(encryptedCart.path),
        allOf(
          contains('NCSD partition 0'),
          contains('0x4000'),
          contains('NoCrypto'),
        ),
      );
      expect(
        await Libretro3dsNcch.encryptedGameDetail(decryptedCart.path),
        isNull,
      );
      expect(
        await Libretro3dsNcch.encryptedGameDetail(encryptedCxi.path),
        contains('flags[7] 0x00'),
      );
      expect(
        await Libretro3dsNcch.encryptedGameDetail(decryptedCxi.path),
        isNull,
      );
    },
  );

  test('formats the check does not read are left to the core', () async {
    final homebrew = write('app.3dsx', <int>[
      ...'3DSX'.codeUnits,
      ...List<int>.filled(0x400, 1),
    ]);
    final compressed = write('game.zcci', <int>[
      ...'Z3DS'.codeUnits,
      ...List<int>.filled(0x400, 2),
    ]);
    final short = write('short.cxi', ncch(decrypted: false, length: 0x120));
    final pastEnd = write(
      'past-end.3ds',
      ncsd(decrypted: false).sublist(0, 0x1000),
    );
    for (final file in [homebrew, compressed, short, pastEnd]) {
      expect(
        await Libretro3dsNcch.encryptedGameDetail(file.path),
        isNull,
        reason: file.path,
      );
    }
    expect(
      await Libretro3dsNcch.encryptedGameDetail(
        p.join(root.path, 'missing.3ds'),
      ),
      isNull,
    );
  });

  test(
    'an encrypted 3DS game is refused before the session, translated',
    () async {
      final outcome = await LibretroInternalService.launch(
        system: system(),
        game: game(write('Encrypted.3ds', ncsd(decrypted: false))),
        locale: const Locale('fr'),
      );
      expect(outcome.success, isFalse);
      expect(outcome.errorCode, 'LIBRETRO_3DS_ENCRYPTED');
      expect(outcome.technicalDetails, contains('NoCrypto'));
      expect(launches, isEmpty, reason: 'the native session is never asked');
      for (final language in <String>[
        'en',
        'fr',
        'de',
        'es',
        'it',
        'pt',
        'ru',
        'id',
        'ja',
        'ko',
        'zh',
        'zh_Hant',
      ]) {
        final catalog = LibretroLocale.values[language]!;
        expect(catalog['error3dsEncrypted'], isNotNull, reason: language);
      }
      expect(
        LibretroLocale.launchError(const Locale('fr'), outcome.errorCode),
        LibretroLocale.values['fr']!['error3dsEncrypted'],
      );
      expect(
        LibretroLocale.launchError(
          const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
          outcome.errorCode,
        ),
        LibretroLocale.values['zh_Hant']!['error3dsEncrypted'],
      );
    },
  );

  test('a decrypted 3DS game reaches the core as before', () async {
    final outcome = await LibretroInternalService.launch(
      system: system(),
      game: game(write('Decrypted.3ds', ncsd(decrypted: true))),
      locale: const Locale('en'),
    );
    expect(outcome.success, isTrue);
    expect(launches.single['coreId'], 'azahar');
  });

  test('other consoles are never read by the 3DS check', () async {
    final outcome = await LibretroInternalService.launch(
      system: SystemModel(
        id: 'gba',
        folderName: 'gba',
        realName: 'GBA',
        iconImage: '',
        color: '#000000',
      ),
      // An NCCH-looking GBA file: only the 3DS core is checked.
      game: game(
        File(p.join(root.path, 'roms', 'gba', 'odd.gba'))
          ..createSync(recursive: true)
          ..writeAsBytesSync(ncch(decrypted: false)),
      ),
      locale: const Locale('en'),
    );
    expect(outcome.success, isTrue);
    expect(launches.single['coreId'], isNot('azahar'));
  });
}
