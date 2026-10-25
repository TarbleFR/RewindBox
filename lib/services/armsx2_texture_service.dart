import 'package:armsx2_internal_bridge/armsx2_internal_bridge.dart';
import 'package:path/path.dart' as path;

import 'armsx2_internal_service.dart';

/// HD texture packs of the embedded ARMSX2 engine (Build 485), from a PS2
/// game's settings. The native store (Armsx2TextureBridge.mm) installs packs
/// into `ARMSX2/textures/<serial>/replacements`, the folder the engine reads,
/// and keeps NeoStation's per-game choice; ARMSX2Core writes that choice into
/// the game's settings when the game starts. Every call answers the store's
/// map: "success" and, on failure, an "error" key (see [Armsx2TextureErrors]).
abstract class Armsx2TextureClient {
  /// game (serial, source, region, version), pack (installed, counts,
  /// formats, enabled, iniEnabled), formats (device), sessionActive.
  Future<Map<String, dynamic>> status(String gamePath);

  /// Opens Files, then inspects the chosen folder or archive (nothing written).
  Future<Map<String, dynamic>> pick(String gamePath, {required bool folder});

  Future<Map<String, dynamic>> install(
    String token, {
    required bool allowMismatch,
  });

  Future<void> cancel(String token);

  /// Releases an inspected or installed import.
  Future<void> discard(String token);

  Future<Map<String, dynamic>> setEnabled(String gamePath, bool enabled);

  Future<Map<String, dynamic>> remove(String gamePath);

  /// {token, fraction (0..1, or -1 when unknown), phase}.
  Stream<Map<String, dynamic>> get progress;
}

class Armsx2TextureChannelClient implements Armsx2TextureClient {
  const Armsx2TextureChannelClient();

  Future<Map<String, Object?>> _game(String gamePath) async => {
    'gamePath': path.normalize(gamePath),
    'dataPath': (await Armsx2InternalService.rootDirectory()).path,
  };

  @override
  Future<Map<String, dynamic>> status(String gamePath) async =>
      Armsx2InternalBridge.texture('textureStatus', await _game(gamePath));

  @override
  Future<Map<String, dynamic>> pick(
    String gamePath, {
    required bool folder,
  }) async => Armsx2InternalBridge.texture('texturePick', {
    ...await _game(gamePath),
    'kind': folder ? 'folder' : 'archive',
  });

  @override
  Future<Map<String, dynamic>> install(
    String token, {
    required bool allowMismatch,
  }) => Armsx2InternalBridge.texture('textureInstall', {
    'token': token,
    'allowMismatch': allowMismatch,
  });

  @override
  Future<void> cancel(String token) =>
      Armsx2InternalBridge.texture('textureCancel', {'token': token});

  @override
  Future<void> discard(String token) =>
      Armsx2InternalBridge.texture('textureDiscard', {'token': token});

  @override
  Future<Map<String, dynamic>> setEnabled(
    String gamePath,
    bool enabled,
  ) async => Armsx2InternalBridge.texture('textureSetEnabled', {
    ...await _game(gamePath),
    'enabled': enabled,
  });

  @override
  Future<Map<String, dynamic>> remove(String gamePath) async =>
      Armsx2InternalBridge.texture('textureRemove', await _game(gamePath));

  @override
  Stream<Map<String, dynamic>> get progress =>
      Armsx2InternalBridge.textureProgress;
}

/// Catalogue keys (Armsx2TextureLocale) of the store's error keys.
abstract final class Armsx2TextureErrors {
  static const keys = <String, String>{
    'format': 'errFormat',
    'zstdNeedsGame': 'errZstdNeedsGame',
    'unsafe': 'errUnsafe',
    'entries': 'errEntries',
    'multipleSerials': 'errMultipleSerials',
    'fileTooLarge': 'errFileTooLarge',
    'duplicate': 'errDuplicate',
    'noTextures': 'errNoTextures',
    'noNamedTextures': 'errNoNamedTextures',
    'space': 'errSpace',
    'encrypted': 'errEncrypted',
    'split': 'errSplit',
    'method': 'errMethod',
    'invalid': 'errInvalid',
    'unreadable': 'errUnreadable',
    'write': 'errWrite',
    'cancelled': 'errCancelled',
    'gameUnknown': 'errGameUnknown',
    'sessionActive': 'errSessionActive',
    'changed': 'errChanged',
    'missing': 'errMissing',
  };

  static String keyFor(Object? error) => keys[error] ?? 'errFailed';
}
