import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

import '../logger_service.dart';

/// What RewindBox wrote for one game: the record that makes every native
/// change reversible without guessing.
class EnhancementGameState {
  EnhancementGameState({
    required this.storeKey,
    required this.engine,
    required this.key,
    this.title = '',
    this.version,
    this.installed = false,
    Set<String>? active,
    Map<String, String>? files,
    Map<String, dynamic>? data,
    this.catalogueRevision = '',
    this.updatedAt,
  }) : active = active ?? <String>{},
       files = files ?? <String, String>{},
       data = data ?? <String, dynamic>{};

  final String storeKey;
  final String engine;
  final String key;
  String title;

  /// Game version when the state was last written; a later difference is
  /// shown so the player can review entries after a game update.
  String? version;
  bool installed;
  final Set<String> active;

  /// Absolute path -> SHA-256 of every whole file RewindBox created.
  final Map<String, String> files;

  /// Adapter-owned facts (lines added to shared files, previous values).
  final Map<String, dynamic> data;
  String catalogueRevision;
  DateTime? updatedAt;

  bool get isEmpty => !installed && active.isEmpty && files.isEmpty;

  Map<String, Object?> toJson() => {
    'engine': engine,
    'key': key,
    'title': title,
    if (version != null) 'version': version,
    'installed': installed,
    'active': active.toList()..sort(),
    'files': files,
    'data': data,
    'catalogueRevision': catalogueRevision,
    if (updatedAt != null) 'updatedAt': updatedAt!.toUtc().toIso8601String(),
  };

  factory EnhancementGameState.fromJson(String storeKey, Map<String, dynamic> json) =>
      EnhancementGameState(
        storeKey: storeKey,
        engine: json['engine']?.toString() ?? '',
        key: json['key']?.toString() ?? '',
        title: json['title']?.toString() ?? '',
        version: json['version']?.toString(),
        installed: json['installed'] == true,
        active: {
          for (final id in (json['active'] as List? ?? const [])) id.toString(),
        },
        files: {
          for (final entry in (json['files'] as Map? ?? const {}).entries)
            entry.key.toString(): entry.value.toString(),
        },
        data: Map<String, dynamic>.from(json['data'] as Map? ?? const {}),
        catalogueRevision: json['catalogueRevision']?.toString() ?? '',
        updatedAt: DateTime.tryParse(json['updatedAt']?.toString() ?? ''),
      );
}

/// Persistent, serialized record of every game's enhancement state.
///
/// One small JSON file, written atomically; operations run one at a time so
/// two quick toggles can never interleave their native writes.
class EnhancementStore {
  EnhancementStore({Future<Directory> Function()? root}) : _root = root ?? defaultRoot;

  static final EnhancementStore instance = EnhancementStore();

  final Future<Directory> Function() _root;
  final _log = LoggerService.instance;
  Map<String, EnhancementGameState>? _games;
  Future<void> _queue = Future.value();

  static Future<Directory> defaultRoot() async {
    final support = await getApplicationSupportDirectory();
    final root = Directory(path.join(support.path, 'RewindBox', 'Enhancements'));
    await root.create(recursive: true);
    return root;
  }

  Future<File> _file() async => File(path.join((await _root()).path, 'state.json'));

  Future<Map<String, EnhancementGameState>> _load() async {
    final loaded = _games;
    if (loaded != null) return loaded;
    final games = <String, EnhancementGameState>{};
    final file = await _file();
    if (await file.exists()) {
      try {
        final json = jsonDecode(await file.readAsString());
        if (json is Map && json['schema'] == 1 && json['games'] is Map) {
          for (final entry in (json['games'] as Map).entries) {
            if (entry.value is Map) {
              games[entry.key.toString()] = EnhancementGameState.fromJson(
                entry.key.toString(),
                Map<String, dynamic>.from(entry.value as Map),
              );
            }
          }
        }
      } catch (error) {
        // Keep the damaged file for inspection; never overwrite it blindly.
        final damaged = File('${file.path}.damaged');
        await file.copy(damaged.path);
        _log.e('Enhancements: state unreadable, kept at ${damaged.path}', error: error);
      }
    }
    return _games = games;
  }

  Future<void> _save(Map<String, EnhancementGameState> games) async {
    final file = await _file();
    await file.parent.create(recursive: true);
    final temporary = File('${file.path}.partial');
    final payload = {
      'schema': 1,
      'games': {
        for (final entry in games.entries)
          if (!entry.value.isEmpty) entry.key: entry.value.toJson(),
      },
    };
    await temporary.writeAsString(
      const JsonEncoder.withIndent(' ').convert(payload),
      flush: true,
    );
    await temporary.rename(file.path);
  }

  /// Runs [body] alone against the current states, then saves them.
  Future<T> transaction<T>(Future<T> Function(Map<String, EnhancementGameState> games) body) {
    final completer = Completer<T>();
    _queue = _queue.then((_) async {
      try {
        final games = await _load();
        final result = await body(games);
        games.removeWhere((_, state) => state.isEmpty);
        await _save(games);
        completer.complete(result);
      } catch (error, stack) {
        completer.completeError(error, stack);
      }
    });
    return completer.future;
  }

  Future<EnhancementGameState?> game(String storeKey) async {
    await _queue;
    return (await _load())[storeKey];
  }

  Future<List<EnhancementGameState>> all() async {
    await _queue;
    final games = (await _load()).values.toList()
      ..sort((a, b) => a.title.toLowerCase().compareTo(b.title.toLowerCase()));
    return games;
  }
}
