import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_addon_service.dart';
import 'library_catalog_feed.dart';
import 'logger_service.dart';

/// Content of one source file of `Documents/Library/Sources`.
@immutable
class LibrarySourceFileDescriptor {
  const LibrarySourceFileDescriptor({
    required this.id,
    required this.name,
    required this.version,
    this.language,
    this.origin,
  });

  factory LibrarySourceFileDescriptor.of(LibraryAddon addon) =>
      LibrarySourceFileDescriptor(
        id: addon.id,
        name: addon.name,
        version: addon.version,
        language: addon.language,
        origin: addon.repositoryOrigin,
      );

  /// Add-on id: the only field used to identify the source.
  final String id;
  final String name;
  final String version;
  final String? language;

  /// Catalogue or repository the source was installed from.
  final String? origin;

  /// The descriptor in [text], or null when [text] is not a NeoStation
  /// source file (no [LibrarySourceFiles.schema] marker, or no id): such a
  /// file is never written nor deleted by NeoStation.
  static LibrarySourceFileDescriptor? tryParse(String text) {
    final trimmed = text.trimLeft();
    if (!trimmed.startsWith('{')) return null;
    Object? decoded;
    try {
      decoded = jsonDecode(trimmed);
    } on FormatException {
      return null;
    }
    if (decoded is! Map || decoded['schema'] != LibrarySourceFiles.schema) {
      return null;
    }
    final id = decoded['id'];
    if (id is! String || id.trim().isEmpty) return null;
    String? stringOrNull(Object? value) => value is String ? value : null;
    return LibrarySourceFileDescriptor(
      id: id.trim(),
      name: stringOrNull(decoded['name']) ?? '',
      version: stringOrNull(decoded['version']) ?? '',
      language: stringOrNull(decoded['language']),
      origin: stringOrNull(decoded['origin']),
    );
  }

  Map<String, Object?> toJson() => <String, Object?>{
    'schema': LibrarySourceFiles.schema,
    'id': id,
    'name': name,
    'language': language,
    'version': version,
    'origin': origin,
  };

  /// File content: indented JSON and a final newline.
  String encode() =>
      '${const JsonEncoder.withIndent('  ').convert(toJson())}\n';

  bool sameContentAs(LibrarySourceFileDescriptor other) =>
      id == other.id &&
      name == other.name &&
      version == other.version &&
      language == other.language &&
      origin == other.origin;
}

/// Mirrors the installed Library sources as files in
/// `Documents/Library/Sources` (Files › NeoStation › Library › Sources), so
/// deleting a file there removes its source (Build 440, maintainer decision
/// of 11 October 2026). The app never shows, names or links this folder.
///
/// * One small JSON file per installed source the user can remove (never a
///   built-in one), named after the source and its language; NeoStation
///   identifies it by the id inside, so a renamed file keeps its source.
/// * NeoStation only writes or deletes files carrying [schema]; any other
///   file of the folder is left untouched.
/// * The ids whose file NeoStation wrote are remembered in the preferences
///   ([preferencesKey], id → file name). A missing file means "deleted by
///   the user" only for those ids; a source whose file was never written
///   gets one, so the first run after the update writes every file and
///   removes nothing.
/// * A deleted Sources folder removes every source whose file had been
///   written: NeoStation never deletes `Documents/Library` or `Sources`
///   itself (the local library only deletes book files inside `Books/` and
///   `Downloads/`), so a missing folder can only come from the user.
/// * Any listing or read failure changes nothing: a source is never removed
///   because of an I/O error.
/// * Sources are removed through [LibraryAddonService.removeMany], the same
///   path as the in-app removal: reading progress, favourites, downloads,
///   local books, catalogues and health reports are kept.
///
/// Passes are serialized and coalesced ([sync]); a call made from inside a
/// pass (the removal it triggers) returns at once.
class LibrarySourceFiles with WidgetsBindingObserver {
  LibrarySourceFiles(
    this._service, {
    Future<Directory> Function()? directory,
    this.followLifecycle = true,
  }) : _directory = directory ?? defaultDirectory;

  /// Marker of the files NeoStation writes.
  static const String schema = 'neostation.library.source-file.v1';

  /// Folder name inside `Documents/Library`.
  static const String folderName = 'Sources';

  /// Preferences key of the files written by NeoStation (id → file name).
  static const String preferencesKey = 'neostation_library_source_files_v1';

  /// Bigger files are never NeoStation source files and are not read.
  static const int maxFileBytes = 64 * 1024;

  static const String _temporaryPrefix = '.neostation-source-';
  static const String _temporarySuffix = '.tmp';
  static const int _maxBaseNameBytes = 180;
  static const int _maxNameAttempts = 32;

  /// The folder is mirrored on iOS only (Files app).
  static bool get supportedByPlatform =>
      debugSupportedByPlatformOverride ?? (!kIsWeb && Platform.isIOS);

  /// Replaces the platform check of [supportedByPlatform] (tests: builds
  /// the app's [LibraryAddonService.instance] as on iOS).
  @visibleForTesting
  static bool? debugSupportedByPlatformOverride;

  /// `Documents/Library/Sources` of the app.
  static Future<Directory> defaultDirectory() async {
    final documents = await getApplicationDocumentsDirectory();
    return Directory(p.join(documents.path, 'Library', folderName));
  }

  static final LoggerService _log = LoggerService.instance;
  static final Object _passZoneKey = Object();

  final LibraryAddonService _service;
  final Future<Directory> Function() _directory;

  /// Reconcile when the app comes back to the foreground.
  final bool followLifecycle;

  final StreamController<Set<String>> _removals =
      StreamController<Set<String>>.broadcast();
  bool _observing = false;
  bool _requested = false;
  final List<String> _reasons = <String>[];
  Future<void>? _draining;

  /// Passes run so far (tests).
  @visibleForTesting
  int passCount = 0;

  /// Passes running at the same time right now (tests; never above 1).
  @visibleForTesting
  int activePasses = 0;

  /// Ids of the sources removed because their file was deleted, once per
  /// pass that removed something.
  Stream<Set<String>> get removals => _removals.stream;

  /// True inside a pass (and in what it awaits).
  bool get isReconciling => identical(Zone.current[_passZoneKey], this);

  /// Starts following the app lifecycle and runs the first pass.
  Future<void> start() {
    _observe();
    return sync(reason: 'first load');
  }

  /// Reconciles the installed sources with the folder. Never throws.
  ///
  /// Calls made while a pass runs share one more pass, started when it
  /// ends; calls made from inside a pass return at once.
  Future<void> sync({String reason = 'request'}) {
    if (isReconciling) return Future<void>.value();
    _requested = true;
    if (!_reasons.contains(reason)) _reasons.add(reason);
    return _draining ??= _drain();
  }

  /// Stops following the app lifecycle (tests).
  @visibleForTesting
  void dispose() {
    if (_observing) {
      WidgetsBinding.instance.removeObserver(this);
      _observing = false;
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(sync(reason: 'resume'));
    }
  }

  void _observe() {
    if (_observing || !followLifecycle) return;
    try {
      WidgetsBinding.instance.addObserver(this);
      _observing = true;
    } on Object {
      // No Flutter binding (pure Dart): the other triggers still apply.
    }
  }

  Future<void> _drain() async {
    try {
      while (_requested) {
        _requested = false;
        final reason = _reasons.join(', ');
        _reasons.clear();
        await runZoned(
          () => _passSafely(reason),
          zoneValues: <Object?, Object?>{_passZoneKey: this},
        );
      }
    } finally {
      _draining = null;
    }
  }

  Future<void> _passSafely(String reason) async {
    passCount++;
    activePasses++;
    try {
      await _pass(reason);
    } on Object catch (error, stackTrace) {
      _log.e(
        'Library source files: pass failed ($reason), nothing more changed',
        error: error,
        stackTrace: stackTrace,
      );
    } finally {
      activePasses--;
    }
  }

  Future<void> _pass(String reason) async {
    final Directory folder;
    final SharedPreferences preferences;
    final Map<String, String> written;
    try {
      folder = await _directory();
      preferences = await SharedPreferences.getInstance();
      written = _readWritten(preferences);
      // Sources must be loaded before anything is compared with them.
      await _service.load();
    } on Object catch (error) {
      _log.w('Library source files: not checked ($reason): $error');
      return;
    }

    final listing = await _list(folder);
    if (listing == null) return;

    // Installed sources, taken after the I/O so the decisions below and the
    // removal see the same list.
    final installed = <String, LibraryAddon>{
      for (final addon in _service.addons)
        if (isUserRemovable(addon)) addon.id: addon,
    };

    final namesById = <String, List<String>>{};
    for (final entry in listing.ours.entries) {
      (namesById[entry.value.id] ??= <String>[]).add(entry.key);
    }
    final taken = <String>{
      for (final name in listing.names) name.toLowerCase(),
    };

    final next = Map<String, String>.of(written);
    final toRemove = <String>{};
    final toWrite = <LibraryAddon>[];
    final toRewrite = <String, LibraryAddon>{};
    final toDelete = <String>[];
    var renamed = 0;

    for (final addon in installed.values) {
      final names = namesById[addon.id];
      if (names != null && names.isNotEmpty) {
        final keep = _preferredName(names, written[addon.id], addon);
        if (written.containsKey(addon.id) && written[addon.id] != keep) {
          renamed++;
        }
        next[addon.id] = keep;
        for (final name in names) {
          if (name != keep) toDelete.add(name);
        }
        final expected = LibrarySourceFileDescriptor.of(addon);
        if (!listing.ours[keep]!.sameContentAs(expected)) {
          toRewrite[keep] = addon;
        }
      } else if (written.containsKey(addon.id)) {
        // Its file was written and is gone: the user deleted it.
        toRemove.add(addon.id);
      } else {
        toWrite.add(addon);
      }
    }
    for (final entry in namesById.entries) {
      if (installed.containsKey(entry.key)) continue;
      // Removed in the app (or installed elsewhere): the file goes too.
      toDelete.addAll(entry.value);
    }
    // Uninstalled ids are forgotten; the ones being removed are forgotten
    // once their removal succeeded.
    next.removeWhere((id, _) => !installed.containsKey(id));

    final removed = <String>{};
    if (toRemove.isNotEmpty) {
      final before = {for (final addon in _service.addons) addon.id};
      try {
        await _service.removeMany(toRemove);
      } on Object catch (error) {
        _log.w('Library source files: sources not removed: $error');
      }
      final after = {for (final addon in _service.addons) addon.id};
      for (final id in toRemove) {
        if (before.contains(id) && !after.contains(id)) removed.add(id);
        // Still installed (the removal failed): checked again next time.
        if (!after.contains(id)) next.remove(id);
      }
    }

    var deleted = 0;
    for (final name in toDelete) {
      try {
        // Its name stays taken for this pass: another entry the file
        // system sees as the same name may still be there.
        await File(p.join(folder.path, name)).delete();
        deleted++;
      } on FileSystemException catch (error) {
        _log.w('Library source files: $name not deleted: $error');
      }
    }

    var created = 0;
    if (toWrite.isNotEmpty) {
      try {
        await folder.create(recursive: true);
      } on FileSystemException catch (error) {
        _log.w('Library source files: folder not created: $error');
        toWrite.clear();
      }
    }
    for (final addon in toWrite) {
      final name = await _freeFileName(folder, addon, taken);
      // Not written this time: still "never written", so nothing is removed.
      if (name == null) continue;
      if (await _write(folder, name, addon)) {
        taken.add(name.toLowerCase());
        next[addon.id] = name;
        created++;
      }
    }
    var rewritten = 0;
    for (final entry in toRewrite.entries) {
      if (await _write(folder, entry.key, entry.value)) rewritten++;
    }

    if (!mapEquals(next, written)) {
      try {
        await preferences.setString(preferencesKey, jsonEncode(next));
      } on Object catch (error) {
        _log.w('Library source files: state not saved: $error');
      }
    }

    final changes = <String>[
      if (removed.isNotEmpty)
        'removed ${removed.length} source(s) whose file was deleted '
            '(${removed.join(', ')})',
      if (created > 0) 'wrote $created file(s)',
      if (rewritten > 0) 'updated $rewritten file(s)',
      if (deleted > 0) 'deleted $deleted file(s)',
      if (renamed > 0) 'kept $renamed renamed file(s)',
    ];
    if (changes.isNotEmpty) {
      _log.i(
        'Library source files ($reason, ${installed.length} installed'
        '${listing.folderMissing ? ', folder missing' : ''}): '
        '${changes.join('; ')}',
      );
    }
    if (removed.isNotEmpty) {
      _removals.add(Set<String>.unmodifiable(removed));
    }
  }

  /// Every file of [folder] (names only) and the NeoStation source files
  /// among them; null when the folder (or its container) cannot be listed
  /// or one of its files cannot be read.
  Future<_Listing?> _list(Directory folder) async {
    try {
      final type = await FileSystemEntity.type(folder.path, followLinks: false);
      if (type == FileSystemEntityType.notFound) {
        // A missing Sources folder only counts when its container (the
        // app's Documents folder) is there.
        final documents = folder.parent.parent;
        final documentsType = await FileSystemEntity.type(
          documents.path,
          followLinks: false,
        );
        if (documentsType != FileSystemEntityType.directory) {
          _log.w('Library source files: Documents unavailable, not checked');
          return null;
        }
        // `type` also answers notFound when the folder could not be looked
        // up at all (permission, I/O error): only an error saying "no such
        // file or folder" means the user deleted it.
        if (!await _confirmedMissing(folder)) return null;
        return const _Listing(
          <String>[],
          <String, LibrarySourceFileDescriptor>{},
          folderMissing: true,
        );
      }
      if (type != FileSystemEntityType.directory) {
        _log.w('Library source files: ${folder.path} is not a folder');
        return null;
      }
      final names = <String>[];
      final ours = <String, LibrarySourceFileDescriptor>{};
      final leftovers = <File>[];
      await for (final entity in folder.list(followLinks: false)) {
        final name = p.basename(entity.path);
        names.add(name);
        if (entity is! File) continue;
        if (name.startsWith(_temporaryPrefix) &&
            name.endsWith(_temporarySuffix)) {
          leftovers.add(entity);
          continue;
        }
        if (name.startsWith('.')) continue;
        final length = await entity.length();
        if (length > maxFileBytes) continue;
        final bytes = await entity.readAsBytes();
        final descriptor = LibrarySourceFileDescriptor.tryParse(
          utf8.decode(bytes, allowMalformed: true),
        );
        if (descriptor != null) ours[name] = descriptor;
      }
      for (final leftover in leftovers) {
        // A write interrupted by the end of the process.
        try {
          await leftover.delete();
        } on FileSystemException {
          // Hidden in Files; tried again next time.
        }
      }
      names.sort();
      return _Listing(names, ours);
    } on Object catch (error) {
      _log.w('Library source files: folder not read, nothing changed: $error');
      return null;
    }
  }

  /// True only when listing [folder] fails because it does not exist
  /// (ENOENT; on Windows also "path not found"). A listing that works (the
  /// folder is there after all) or any other error leaves this pass without
  /// changes.
  static Future<bool> _confirmedMissing(Directory folder) async {
    try {
      await folder.list(followLinks: false).isEmpty;
      _log.w(
        'Library source files: ${folder.path} could not be looked up but '
        'can be listed, not checked',
      );
      return false;
    } on FileSystemException catch (error) {
      final code = error.osError?.errorCode;
      if (code != null && _notFoundErrorCodes.contains(code)) return true;
      _log.w('Library source files: folder not read, nothing changed: $error');
      return false;
    }
  }

  /// errno ENOENT; ERROR_FILE_NOT_FOUND and ERROR_PATH_NOT_FOUND on Windows
  /// (where an invalid name is also reported as a missing path, with
  /// another code).
  static Set<int> get _notFoundErrorCodes =>
      !kIsWeb && Platform.isWindows ? const <int>{2, 3} : const <int>{2};

  /// Name of a new file for [addon] that no entry of [folder] already has
  /// as the file system sees names (APFS ignores Unicode normalization, the
  /// Files app may have created a case variant): renaming onto it never
  /// replaces another file. Null when a name cannot be looked up.
  Future<String?> _freeFileName(
    Directory folder,
    LibraryAddon addon,
    Set<String> takenLowerCase,
  ) async {
    for (var attempt = 0; attempt < _maxNameAttempts; attempt++) {
      final name = uniqueFileName(addon, takenLowerCase);
      final FileSystemEntityType type;
      try {
        type = await FileSystemEntity.type(
          p.join(folder.path, name),
          followLinks: false,
        );
      } on Object catch (error) {
        _log.w('Library source files: $name not checked: $error');
        return null;
      }
      if (type == FileSystemEntityType.notFound) return name;
      takenLowerCase.add(name.toLowerCase());
    }
    _log.w('Library source files: no free name for ${addon.id}');
    return null;
  }

  /// Writes the file of [addon] through a hidden temporary file, so a write
  /// cut short never leaves a partial file under a visible name.
  Future<bool> _write(Directory folder, String name, LibraryAddon addon) async {
    final temporary = File(
      p.join(
        folder.path,
        '$_temporaryPrefix${DateTime.now().microsecondsSinceEpoch}'
        '-${fileNameHash(addon.id)}$_temporarySuffix',
      ),
    );
    try {
      await temporary.writeAsString(
        LibrarySourceFileDescriptor.of(addon).encode(),
        flush: true,
      );
      await temporary.rename(p.join(folder.path, name));
      return true;
    } on FileSystemException catch (error) {
      _log.w('Library source files: $name not written: $error');
      try {
        if (await temporary.exists()) await temporary.delete();
      } on FileSystemException {
        // Removed by the next pass.
      }
      return false;
    }
  }

  /// The file kept for a source found in several files: the one NeoStation
  /// remembers, else the one with its usual name, else the first by name.
  static String _preferredName(
    List<String> names,
    String? remembered,
    LibraryAddon addon,
  ) {
    if (remembered != null && names.contains(remembered)) return remembered;
    final usual = '${baseFileName(addon)}.json'.toLowerCase();
    for (final name in names) {
      if (name.toLowerCase() == usual) return name;
    }
    return (List<String>.of(names)..sort()).first;
  }

  static Map<String, String> _readWritten(SharedPreferences preferences) {
    final raw = preferences.getString(preferencesKey);
    if (raw == null || raw.isEmpty) return <String, String>{};
    Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      // Unknown: as if nothing had been written (nothing is removed).
      return <String, String>{};
    }
    if (decoded is! Map) return <String, String>{};
    return <String, String>{
      for (final entry in decoded.entries)
        if (entry.key is String && entry.value is String)
          entry.key as String: entry.value as String,
    };
  }

  /// Sources that get a file: everything the user installed (built-in
  /// sources cannot be removed and never get one).
  static bool isUserRemovable(LibraryAddon addon) =>
      !addon.isBuiltIn && !addon.origin.startsWith('builtin:');

  /// Usual file name of [addon] without extension: its name and language,
  /// made safe for iOS and the Files app.
  static String baseFileName(LibraryAddon addon) {
    final language = addon.language?.trim() ?? '';
    final label = language.isEmpty ? addon.name : '${addon.name} ($language)';
    final safe = sanitizeFileName(label);
    return safe.isEmpty ? sanitizeFileName(addon.id) : safe;
  }

  /// File name for [addon] not in [takenLowerCase] (names compared without
  /// case): the usual name, or a short suffix derived from the id.
  static String uniqueFileName(LibraryAddon addon, Set<String> takenLowerCase) {
    final base = baseFileName(addon);
    final hash = fileNameHash(addon.id);
    final candidates = <String>[
      '$base.json',
      '$base [${hash.substring(0, 4)}].json',
      '$base [$hash].json',
    ];
    for (final candidate in candidates) {
      if (!takenLowerCase.contains(candidate.toLowerCase())) return candidate;
    }
    for (var index = 2; ; index++) {
      final candidate = '$base [$hash] $index.json';
      if (!takenLowerCase.contains(candidate.toLowerCase())) return candidate;
    }
  }

  /// Text usable as a file name on iOS and in the Files app: no path
  /// separator, colon, control or invisible formatting character, no
  /// leading dot (hidden file), no trailing dot or space, at most
  /// [_maxBaseNameBytes] bytes of UTF-8. Empty when nothing is left.
  static String sanitizeFileName(String value) {
    final buffer = StringBuffer();
    for (final rune in value.runes) {
      buffer.write(_unsafeRune(rune) ? ' ' : String.fromCharCode(rune));
    }
    var name = buffer.toString().replaceAll(RegExp(r'\s+'), ' ').trim();
    name = name.replaceFirst(RegExp(r'^[.\s]+'), '');
    final limited = StringBuffer();
    var bytes = 0;
    for (final rune in name.runes) {
      final char = String.fromCharCode(rune);
      bytes += utf8.encode(char).length;
      if (bytes > _maxBaseNameBytes) break;
      limited.write(char);
    }
    name = limited.toString().replaceFirst(RegExp(r'[.\s]+$'), '');
    final stem = name.split('.').first.trim().toUpperCase();
    if (_reservedNames.contains(stem)) name = '${name}_';
    return name;
  }

  static bool _unsafeRune(int rune) =>
      rune < 0x20 ||
      (rune >= 0x7F && rune < 0xA0) ||
      rune == 0x2F || // /
      rune == 0x5C || // backslash
      rune == 0x3A || // :
      rune == 0x2A || // *
      rune == 0x3F || // ?
      rune == 0x22 || // "
      rune == 0x3C || // <
      rune == 0x3E || // >
      rune == 0x7C || // |
      (rune >= 0x200B && rune <= 0x200F) ||
      (rune >= 0x2028 && rune <= 0x202E) ||
      (rune >= 0x2060 && rune <= 0x2069) ||
      rune == 0xFEFF ||
      (rune >= 0xFFF0 && rune <= 0xFFFF);

  /// Device names refused by Windows (a file shared with a PC).
  static const Set<String> _reservedNames = <String>{
    'CON', 'PRN', 'AUX', 'NUL', //
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
  };

  /// Eight hexadecimal digits derived from [id] (FNV-1a), stable across runs.
  static String fileNameHash(String id) {
    var hash = 0x811C9DC5;
    for (final byte in utf8.encode(id)) {
      hash ^= byte;
      hash = (hash * 0x01000193) & 0xFFFFFFFF;
    }
    return hash.toRadixString(16).padLeft(8, '0');
  }

  /// Reaction of the app's service to a removal: the Library hub shows the
  /// catalogue feed ([LibraryCatalogFeed.instance], which LibraryScreen
  /// listens to); when it shows a removed source, the feed gets the new
  /// source list, as when the Library tab is opened again.
  static void refreshLibraryFeed(
    LibraryAddonService service,
    Set<String> removed,
  ) {
    final feed = LibraryCatalogFeed.instance;
    if (!removed.any((id) => feed.source(id) != null)) return;
    unawaited(
      feed.open(service.addons).catchError((Object error) {
        _log.w('Library source files: hub not refreshed: $error');
      }),
    );
  }
}

class _Listing {
  const _Listing(this.names, this.ours, {this.folderMissing = false});

  /// Every entry of the folder.
  final List<String> names;

  /// NeoStation source files: file name → content.
  final Map<String, LibrarySourceFileDescriptor> ours;
  final bool folderMissing;
}
