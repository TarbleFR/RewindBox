import 'package:flutter/services.dart';
import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';

import 'libretro_core_catalog.dart';
import 'libretro_internal_service.dart';

class LibretroCoreBuildInfo {
  const LibretroCoreBuildInfo._(this.name, this.version);

  final String name;
  final String version;

  static final _cache = <String, Future<LibretroCoreBuildInfo?>>{};
  static Future<Set<String>?>? _installedCores;

  /// An empty map means this build omitted every core for the playlist.
  /// Null means the installation could not supply its build metadata.
  static Future<Map<String, LibretroCoreBuildInfo>?> forSystem(String systemKey) async {
    final cores = LibretroCoreCatalog.coresFor(systemKey);
    final builds = await Future.wait([
      for (final core in cores) _cache.putIfAbsent(core.id, () => _read(core.id)),
    ]);
    final result = <String, LibretroCoreBuildInfo>{
      for (final (index, build) in builds.indexed)
        cores[index].id: ?build,
    };
    if (result.isNotEmpty) return result;
    final installed = await (_installedCores ??= _listInstalledCores());
    if (installed == null || cores.any((core) => installed.contains(core.id))) return null;
    return result;
  }

  static Future<Set<String>?> _listInstalledCores() async {
    try {
      return (await LibretroInternalBridge.availableCores()).toSet();
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }

  static Future<LibretroCoreBuildInfo?> _read(String coreId) async {
    final identity = await LibretroInternalService.bundledCollectionIdentity;
    final records = identity is Map ? identity['cores'] : null;
    final record = records is List
        ? records.whereType<Map>().where((row) => row['id'] == coreId).firstOrNull
        : null;
    final release = _version(record?['version']);
    final Map<String, String>? binary;
    try {
      binary = await LibretroInternalBridge.coreBuildInfo(coreId, inspectBinary: release == null);
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
    if (binary == null) return null;

    final compiledName = binary['name']?.trim();
    final name = compiledName != null && compiledName.isNotEmpty
        ? compiledName
        : LibretroCoreCatalog.cores[coreId]?.displayName ?? coreId;
    if (release != null) return LibretroCoreBuildInfo._(name, release);

    final version = _version(binary['version']);
    final revision = record?['sourceRevision'] ?? record?['sourceCommit'];
    String? build;
    if (revision is String && RegExp(r'^[0-9a-fA-F]{40}$').hasMatch(revision)) {
      if (version == null || !version.toLowerCase().contains(revision.substring(0, 7).toLowerCase())) {
        build = 'Git ${revision.substring(0, 12)}';
      }
    } else if (version == null || !RegExp(r'[0-9a-fA-F]{7,}').hasMatch(version)) {
      // Some buildbot nightlies report only the upstream release; the
      // collection records the exact build even when no Git hash is supplied.
      final digest = record?['sha256'];
      if (digest is String && RegExp(r'^[0-9a-fA-F]{64}$').hasMatch(digest)) {
        build = 'SHA-256 ${digest.substring(0, 12)}';
      }
    }
    final details = [?version, ?build];
    return details.isEmpty ? null : LibretroCoreBuildInfo._(name, details.join(' · '));
  }

  static String? _version(Object? value) {
    if (value is! String) return null;
    final text = value.trim();
    const placeholders = {'', '0', 'unknown', 'svn', 'git', 'nightly', 'dev', 'n/a'};
    return placeholders.contains(text.toLowerCase()) ? null : text;
  }
}
