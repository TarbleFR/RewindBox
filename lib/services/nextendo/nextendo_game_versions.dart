import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

import 'nextendo_bcat.dart';
import 'nextendo_catalog.dart';
import 'nextendo_config.dart';
import 'nextendo_service.dart';

/// How a game's installed version stands against Nextendo's signed catalog.
enum NextendoVersionStatus {
  /// The installed version is one the catalog accepts: the game can go online.
  matches,

  /// The catalog accepts other versions only: install the update it names.
  mismatch,

  /// An update is installed but its version is not known yet (the engine in
  /// this build does not report an update's version).
  installedUnknown,

  /// Nextendo's catalog does not list the game.
  notListed,

  /// Listed, but Nextendo has switched online play off for it for now.
  disabled,

  /// No valid catalog could be loaded (no connection and none kept).
  catalogUnavailable,
}

/// What can be read about one Switch game's version for Nextendo Network.
class NextendoGameVersionInfo {
  const NextendoGameVersionInfo({
    required this.titleId,
    required this.baseVersion,
    required this.updateVersion,
    required this.updateInstalled,
    required this.requirement,
    required this.status,
    required this.bcatKept,
  });

  final String titleId;
  final String? baseVersion; // the game file's own version
  final String? updateVersion; // the selected update's version, when known
  final bool updateInstalled;
  final NextendoGameRequirement? requirement;
  final NextendoVersionStatus status;

  /// The game's BCAT delivery data is kept on the device ([NextendoBcat]).
  final bool bcatKept;

  /// The version the game runs at: the update's when one is installed.
  String? get installedVersion => updateInstalled ? updateVersion : baseVersion;

  /// Compares [installed] with the catalog's accepted versions, exactly.
  static NextendoVersionStatus statusOf({
    required NextendoCatalog? catalog,
    required NextendoGameRequirement? requirement,
    required String? installed,
  }) {
    if (catalog == null) return NextendoVersionStatus.catalogUnavailable;
    if (requirement == null) return NextendoVersionStatus.notListed;
    if (!requirement.enabled) return NextendoVersionStatus.disabled;
    if (installed == null || installed.isEmpty) return NextendoVersionStatus.installedUnknown;
    return requirement.accepted.contains(installed.trim()) ? NextendoVersionStatus.matches : NextendoVersionStatus.mismatch;
  }
}

/// Reads a game's installed version (base file, selected update) and compares
/// it with Nextendo's catalog. The engine reports the base file's version
/// (`metadata`) and, from the engine lot of 17 November on, the selected
/// update's (`inspectUpdate`, `displayVersion`); an older engine leaves the
/// update's version unknown. Never throws.
abstract final class NextendoGameVersions {
  static final _titleId = RegExp(r'^[0-9a-f]{16}$');

  static Future<NextendoGameVersionInfo?> read({
    required String gamePath,
    required Directory root,
    required Future<Map<String, dynamic>> Function(String method, {String? filePath, String? titleId}) content,
    Future<NextendoCatalog?> Function()? catalog,
  }) async {
    try {
      final metadata = await content('metadata', filePath: gamePath);
      final titleId = '${metadata['titleId'] ?? ''}'.toLowerCase();
      if (!_titleId.hasMatch(titleId)) return null;
      final base = _version(metadata['version']);
      final update = await _selectedUpdate(root, titleId);
      String? updateVersion;
      if (update != null) {
        try {
          updateVersion = _version((await content('inspectUpdate', filePath: update, titleId: titleId))['displayVersion']);
        } on Object {
          updateVersion = null;
        }
      }
      final loaded = await (catalog ?? (() => NextendoCatalogStore.current()))();
      final requirement = loaded?.forTitle(titleId);
      final installed = update != null ? updateVersion : base;
      return NextendoGameVersionInfo(
        titleId: titleId,
        baseVersion: base,
        updateVersion: updateVersion,
        updateInstalled: update != null,
        requirement: requirement,
        status: NextendoGameVersionInfo.statusOf(catalog: loaded, requirement: requirement, installed: installed),
        bcatKept: await NextendoBcat.folder(root, titleId).exists(),
      );
    } on Object {
      return null;
    }
  }

  /// For a game's page: only a signed-in player's view refreshes the catalog
  /// (at most every six hours); anyone else sees the card only when a catalog
  /// is already kept, and nothing contacts Nextendo for them.
  static Future<NextendoGameVersionInfo?> forLibrary({
    required String gamePath,
    required Directory root,
    required Future<Map<String, dynamic>> Function(String method, {String? filePath, String? titleId}) content,
    NextendoService? service,
    SharedPreferences? preferences,
  }) async {
    try {
      final prefs = preferences ?? await SharedPreferences.getInstance();
      final config = await NextendoConfig.load(prefs);
      final signedIn = config.canSignIn && await (service ?? NextendoService.instance).restore(config) != null;
      final kept = NextendoCatalogStore.stored(prefs);
      if (!signedIn && kept == null) return null;
      return await read(
        gamePath: gamePath,
        root: root,
        content: content,
        catalog: signedIn ? () => NextendoCatalogStore.current(preferences: prefs) : () async => kept,
      );
    } on Object {
      return null;
    }
  }

  static String? _version(Object? value) {
    final text = value?.toString().replaceAll('\u0000', '').trim() ?? '';
    return text.isEmpty || text.length > 32 ? null : text;
  }

  /// The selected update of `<root>/games/<titleId>/updates.json` (relative to
  /// [root]), when its file exists.
  static Future<String?> _selectedUpdate(Directory root, String titleId) async {
    final file = File(p.join(root.path, 'games', titleId, 'updates.json'));
    if (!await file.exists() || await file.length() > 1024 * 1024) return null;
    final decoded = jsonDecode(await file.readAsString());
    final selected = decoded is Map ? decoded['selected'] : null;
    if (selected is! String || selected.isEmpty) return null;
    final absolute = p.isAbsolute(selected) ? selected : p.normalize(p.join(root.path, selected));
    if (!p.isWithin(root.path, absolute)) return null;
    return await File(absolute).exists() ? absolute : null;
  }
}
