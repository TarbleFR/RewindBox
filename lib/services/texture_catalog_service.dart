import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:neo_texture_catalog/neo_texture_catalog.dart';
import 'package:path/path.dart' as path;

import '../l10n/texture_catalog_locale.dart';
import '../models/game_model.dart';
import '../models/system_model.dart';
import '../repositories/game_repository.dart';
import 'armsx2_internal_service.dart';
import 'dolphin_internal_v2_service.dart';
import 'libretro_core_catalog.dart';
import 'libretro_internal_service.dart';
import 'logger_service.dart';

/// Opens the shared HD textures page (neo_texture_catalog) for a console of
/// the library or for one game. Each engine's folders come from the service
/// that launches it, never from a container path written here.
abstract final class TextureCatalogService {
  static final _log = LoggerService.instance;

  /// ps2, gc, wii, psp, 3ds, n64, ps1 or nes for the systems whose embedded
  /// engine replaces textures (ARMSX2, Dolphin, PPSSPP, Azahar,
  /// Mupen64Plus-Next, Beetle PSX HW, Mesen); null for every other one.
  static String? textureSystem(String folderName) {
    final folder = folderName.toLowerCase();
    if (folder == 'ps2') return 'ps2';
    if (folder == 'ps1' || folder == 'psx' || folder == 'playstation') return 'ps1';
    if (folder == 'gc' || folder == 'ngc' || folder == 'gamecube') return 'gc';
    if (folder == 'wii') return 'wii';
    if (folder == 'psp' || folder == 'pspminis') return 'psp';
    if (folder == '3ds' || folder == 'n3ds') return '3ds';
    if (folder == 'n64') return 'n64';
    if (folder == 'nes' || folder == 'fc' || folder == 'famicom' || folder == 'fds' || folder == 'nes-hacks') return 'nes';
    return null;
  }

  /// Systems whose switch is a libretro core option, kept per game.
  static bool _libretro(String textureSystem) =>
      textureSystem == 'psp' || textureSystem == '3ds' || textureSystem == 'n64' || textureSystem == 'ps1' ||
      textureSystem == 'nes';

  /// Tests stand in for iOS; null means the real platform.
  @visibleForTesting
  static bool? debugIsIOS;
  static bool get _isIOS => debugIsIOS ?? Platform.isIOS;

  static bool supports(String folderName) => _isIOS && textureSystem(folderName) != null;

  static Future<Map<String, Object?>> _directories() async {
    final dolphinRoot = await DolphinInternalV2Service.rootDirectory();
    return {
      'dolphinUser': path.join(dolphinRoot.path, 'User'),
      'armsx2Data': (await Armsx2InternalService.rootDirectory()).path,
      'libretroSaves': (await LibretroInternalService.savesDirectory()).path,
      'libretroConfig': (await LibretroInternalService.configDirectory()).path,
      'libretroSystem': (await LibretroInternalService.systemDirectory()).path,
    };
  }

  static String _locale() {
    final locale = FlutterLocalization.instance.currentLocale ?? const Locale('en');
    return TextureCatalogLocale.nativeLocale(locale);
  }

  /// The libretro per-game options key of a game (`<system>/<rom name>`).
  static String _gameKey(String systemFolder, String romname) =>
      '${LibretroCoreCatalog.canonicalSystem(folderName: systemFolder)}/$romname';

  /// NES packs are read by Mesen only: the page shows whether a game starts
  /// with it, and switching a pack on selects it ([selectCore]).
  static bool _choosesCore(String textureSystem) => textureSystem == 'nes';

  /// The core a game starts with: its own choice, else its system's default.
  static Future<String?> _coreFor(String systemKey, String romname) async {
    final binding = LibretroCoreCatalog.bindingFor(systemKey);
    if (binding == null) return null;
    final choice = await LibretroInternalService.coreChoiceFor(systemKey, romname);
    return choice != null && binding.alternatives.contains(choice) ? choice : binding.coreId;
  }

  /// The page's request to start a game (`<system>/<rom name>`) with [core]:
  /// recorded as that game's engine choice when its system offers the core.
  @visibleForTesting
  static Future<bool> selectCore(String gameKey, String core) async {
    final slash = gameKey.indexOf('/');
    if (slash <= 0 || slash == gameKey.length - 1) return false;
    final systemKey = gameKey.substring(0, slash), romname = gameKey.substring(slash + 1);
    final binding = LibretroCoreCatalog.bindingFor(systemKey);
    if (binding == null || !binding.alternatives.contains(core)) return false;
    try {
      await LibretroInternalService.setCoreChoice(systemKey, romname, core);
      _log.i('HD textures: $gameKey now starts with $core');
      return true;
    } catch (error) {
      _log.w('HD textures: engine choice of $gameKey not saved: $error');
      return false;
    }
  }

  static bool _selectorReady = false;
  static void _registerSelector() {
    if (_selectorReady) return;
    _selectorReady = true;
    NeoTextureCatalog.setCoreSelector(selectCore);
  }

  /// A game's page: its file identifies it (the engine's own record first).
  static Future<bool> openGame({required SystemModel system, required GameModel game}) async {
    final folder = game.systemFolderName ?? system.folderName;
    final textureSystem = TextureCatalogService.textureSystem(folder);
    final romPath = game.romPath;
    if (!_isIOS || textureSystem == null || romPath == null || !romPath.startsWith('/')) return false;
    try {
      _registerSelector();
      final systemKey = LibretroInternalService.systemKey(system);
      final core = _choosesCore(textureSystem) ? await _coreFor(systemKey, game.romname) : null;
      return await NeoTextureCatalog.open({
        'system': textureSystem,
        'locale': _locale(),
        'title': game.name,
        'gamePath': romPath,
        if (_libretro(textureSystem)) 'gameKey': '$systemKey/${game.romname}',
        'libretroCore': ?core,
        ...await _directories(),
      });
    } catch (error) {
      _log.w('HD textures page unavailable for ${game.romname}: $error');
      return false;
    }
  }

  /// A console's page: its catalogue, its installed packs, and the packs for
  /// the games of this console in the library.
  /// [systemFolder]: the library folder whose games are listed;
  /// [consoleKey]: the console it belongs to when it is an alias folder.
  static Future<bool> openConsole(String systemFolder, {String? consoleKey}) async {
    final textureSystem = TextureCatalogService.textureSystem(consoleKey ?? systemFolder);
    if (!_isIOS || textureSystem == null) return false;
    try {
      _registerSelector();
      final rows = await GameRepository.loadGamesForSystem(systemFolder);
      final systemKey = LibretroCoreCatalog.canonicalSystem(folderName: consoleKey ?? systemFolder);
      final games = <Map<String, Object?>>[];
      for (final row in rows.take(3000)) {
        if (!row.romPath.startsWith('/')) continue;
        final core = _choosesCore(textureSystem) ? await _coreFor(systemKey, row.romname) : null;
        games.add({
          'path': row.romPath,
          'title': row.realName?.trim().isNotEmpty == true ? row.realName : row.romname,
          if (_libretro(textureSystem)) 'gameKey': _gameKey(consoleKey ?? systemFolder, row.romname),
          'libretroCore': ?core,
        });
      }
      return await NeoTextureCatalog.open({
        'system': textureSystem,
        'locale': _locale(),
        'games': games,
        ...await _directories(),
      });
    } catch (error) {
      _log.w('HD textures page unavailable for $systemFolder: $error');
      return false;
    }
  }
}
