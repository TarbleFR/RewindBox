import 'dart:convert';
import 'dart:io';

import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:path/path.dart' as p;

import 'libretro_internal_service.dart';
import 'logger_service.dart';

/// Answers whether the embedded libretro host owns a session right now
/// (the `launching` window included), as `LibretroInternalBridge.isSessionActive`.
typedef LibretroSessionProbe = Future<bool> Function();

/// Why a store write was refused.
enum LibretroCoreOptionStoreError {
  /// A libretro session is active (or launching): the native
  /// `LibretroCoreOptions` owns `Config/<core>.json` and saves it during the
  /// session, so a Dart write would be lost or would clobber it. Also used
  /// when the probe itself fails: a write is never attempted on an unknown
  /// session state.
  sessionActive,
}

/// Typed refusal of [LibretroCoreOptionStore.write]; [technicalDetail] is a
/// raw diagnostic (never a user message).
class LibretroCoreOptionStoreException implements Exception {
  const LibretroCoreOptionStoreException(this.error, {this.technicalDetail});

  final LibretroCoreOptionStoreError error;
  final String? technicalDetail;

  @override
  String toString() =>
      'LibretroCoreOptionStoreException(${error.name}'
      '${technicalDetail == null ? '' : ': $technicalDetail'})';
}

/// Dart side of the per-core option file `Documents/Libretro/Config/<core>.json`
/// written by the native `LibretroCoreOptions` (`{"values": {key: value}}`,
/// read by `LibretroCoreHost loadCore:`). One file per core library name,
/// no per-game scope.
///
/// Reads tolerate a missing or unreadable file (empty map) and ignore
/// non-string values, exactly as the native loader does. Writes merge key by
/// key (a null value removes the key, unknown keys are preserved), go through
/// `<name>.json.tmp` then a rename, and are refused while a session is
/// active or launching ([LibretroCoreOptionStoreError.sessionActive]).
class LibretroCoreOptionStore {
  LibretroCoreOptionStore({
    Future<Directory> Function()? configDirectory,
    LibretroSessionProbe? sessionProbe,
  }) : configDirectory =
           configDirectory ?? LibretroInternalService.configDirectory,
       sessionProbe = sessionProbe ?? LibretroInternalBridge.isSessionActive;

  /// `library_name` the azahar core declares (`[HOST] loaded Azahar …`,
  /// `corename` of the core info fixture): its file is `Config/Azahar.json`.
  static const String azaharLibraryName = 'Azahar';

  /// Top-level key of the native store format.
  static const String valuesKey = 'values';

  /// Suffix of the temporary file of an atomic write.
  static const String temporarySuffix = '.tmp';

  static const JsonEncoder _encoder = JsonEncoder.withIndent('  ');
  static final _log = LoggerService.instance;

  /// `Documents/Libretro/Config` in production.
  final Future<Directory> Function() configDirectory;

  /// `LibretroInternalBridge.isSessionActive` in production.
  final LibretroSessionProbe sessionProbe;

  /// `SafeFolderName` of `LibretroCoreHost.m`: `/`, `\` and `:` become `_`,
  /// an empty result becomes `core`.
  static String safeFolderName(String name) {
    final safe = name.replaceAll(RegExp(r'[/\\:]'), '_');
    return safe.isEmpty ? 'core' : safe;
  }

  /// File name of a core's option store: `<SafeFolderName(name)>.json`.
  static String libraryFileName(String libraryName) =>
      '${safeFolderName(libraryName)}.json';

  /// Decodes the native format: the `values` map, string values only.
  static Map<String, String> decode(String json) {
    final decoded = jsonDecode(json);
    final values = decoded is Map ? decoded[valuesKey] : null;
    final result = <String, String>{};
    if (values is Map) {
      for (final entry in values.entries) {
        final key = entry.key;
        final value = entry.value;
        if (key is String && value is String) result[key] = value;
      }
    }
    return result;
  }

  /// Encodes [values] in the native format (`{"values": {...}}`, pretty
  /// printed, keys sorted for a stable file).
  static String encode(Map<String, String> values) {
    final sorted = Map<String, String>.fromEntries(
      values.entries.toList()..sort((a, b) => a.key.compareTo(b.key)),
    );
    return _encoder.convert(<String, Object>{valuesKey: sorted});
  }

  /// Absolute path of the option file of [libraryName].
  Future<String> filePath(String libraryName) async =>
      p.join((await configDirectory()).path, libraryFileName(libraryName));

  /// Stored options of [libraryName]; empty when the file is absent or
  /// unreadable (the native loader starts empty in the same cases).
  Future<Map<String, String>> read(String libraryName) async {
    final file = File(await filePath(libraryName));
    if (!await file.exists()) return <String, String>{};
    try {
      return decode(await file.readAsString());
    } catch (error) {
      _log.w('LibretroCoreOptionStore: ${file.path} unreadable: $error');
      return <String, String>{};
    }
  }

  /// Merges [changes] into the stored options of [libraryName] and returns
  /// the stored map after the write. A null value removes its key; keys not
  /// in [changes] are kept as they are. Written through `<name>.json.tmp`
  /// then renamed over the store. Throws [LibretroCoreOptionStoreException]
  /// with [LibretroCoreOptionStoreError.sessionActive] while a session is
  /// active or launching, or when the probe fails, before touching any file.
  Future<Map<String, String>> write(
    String libraryName,
    Map<String, String?> changes,
  ) async {
    await _refuseWhenSessionActive();
    final current = await read(libraryName);
    for (final change in changes.entries) {
      final value = change.value;
      if (value == null) {
        current.remove(change.key);
      } else {
        current[change.key] = value;
      }
    }
    final target = File(await filePath(libraryName));
    final temporary = File('${target.path}$temporarySuffix');
    await target.parent.create(recursive: true);
    try {
      await temporary.writeAsString(encode(current), flush: true);
      await temporary.rename(target.path);
    } catch (_) {
      try {
        if (await temporary.exists()) await temporary.delete();
      } catch (_) {}
      rethrow;
    }
    return current;
  }

  Future<void> _refuseWhenSessionActive() async {
    final bool active;
    try {
      active = await sessionProbe();
    } catch (error) {
      throw LibretroCoreOptionStoreException(
        LibretroCoreOptionStoreError.sessionActive,
        technicalDetail: 'isSessionActive probe failed: $error',
      );
    }
    if (active) {
      throw const LibretroCoreOptionStoreException(
        LibretroCoreOptionStoreError.sessionActive,
      );
    }
  }
}
