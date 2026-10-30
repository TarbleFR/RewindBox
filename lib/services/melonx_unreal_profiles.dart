import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;

/// Owns one isolated LayeredFS experiment. No game/save/key or third-party mod
/// is rewritten. Native inspection supplies the actual title, project and roots.
class MelonxUnrealProfiles {
  MelonxUnrealProfiles(this.root);
  final Directory root;
  static const titleId = '0100f7e00c70e000';
  static const folder = 'RewindBox-Unreal-Experiment';
  static const manifest = 'rewindbox-unreal-profile.json';
  static const experiments = <String, (String, String, bool)>{
    'submitHint': ('fx.NiagaraGpuSubmitCommandHint', '0', false),
    'batchTicks': ('fx.Niagara.SystemSimulation.BatchGPUTickSubmit', '1', false),
    'effects': ('fx.Niagara.QualityLevel', '1', true),
    'translucency': ('r.SeparateTranslucency', '0', true),
    'motionBlur': ('r.MotionBlurQuality', '0', true),
    'depthOfField': ('r.DepthOfFieldQuality', '0', true),
    'resolution': ('r.ScreenPercentage', '75', true),
  };

  Future<String> _safe(String value) async {
    final base = p.normalize(p.absolute(root.path));
    final target = p.normalize(value);
    if (!p.isAbsolute(value) || !p.isWithin(base, target)) {
      throw const FormatException('The mods directory must stay inside MeloNX.');
    }
    var current = target;
    while (current != p.dirname(base)) {
      if (await FileSystemEntity.type(current, followLinks: false) == FileSystemEntityType.link) {
        throw const FormatException('A linked mods path requires manual handling.');
      }
      if (current == base) break;
      current = p.dirname(current);
    }
    return target;
  }

  Future<(String, List<String>)> _inspection(Map<String, dynamic> info) async {
    final project = info['project'];
    final roots = info['modRoots'];
    final base = info['baseConfiguration'] ?? '';
    if (info['success'] != true || info['available'] != true ||
        info['titleId']?.toString().toLowerCase() != titleId ||
        project is! String || !RegExp(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$').hasMatch(project) ||
        roots is! List || roots.isEmpty || roots.length > 2 ||
        base is! String || utf8.encode(base).length > 65536) {
      throw const FormatException('No unambiguous Hogwarts Unreal project was inspected.');
    }
    final checked = <String>[];
    for (final value in roots) {
      if (value is! String) throw const FormatException('Invalid mods directory.');
      final path = await _safe(value);
      if (p.basename(path).toLowerCase() != titleId || p.basename(p.dirname(path)).toLowerCase() != 'contents') {
        throw const FormatException('Invalid title directory.');
      }
      if (!checked.contains(path)) checked.add(path);
    }
    return (project, checked);
  }

  String _relative(Map<String, dynamic> info, String project) {
    final path = info['configurationPath'] ?? '$project/Config/UserEngine.ini';
    if (path is! String || !RegExp('^${RegExp.escape(project)}/Config/UserEngine\\.ini\$', caseSensitive: false).hasMatch(path)) {
      throw const FormatException('Invalid Unreal configuration path.');
    }
    return 'romfs/$path';
  }

  Future<Map<String, dynamic>?> current(Map<String, dynamic> info) async {
    final (_, roots) = await _inspection(info);
    return _owned(p.join(roots.first, folder));
  }

  Future<Map<String, dynamic>?> _owned(String own) async {
    await _safe(own);
    if (!await Directory(own).exists()) {
      if (await FileSystemEntity.type(own, followLinks: false) != FileSystemEntityType.notFound) {
        throw const FormatException('The experiment destination is occupied.');
      }
      return null;
    }
    final receiptFile = File(p.join(own, manifest));
    await _safe(receiptFile.path);
    if (!await receiptFile.exists() || await receiptFile.length() > 16384) {
      throw const FormatException('An existing unowned experiment folder will not be replaced.');
    }
    final decoded = jsonDecode(await receiptFile.readAsString());
    if (decoded is! Map || decoded['schema'] != 1 || decoded['titleId'] != titleId ||
        !experiments.containsKey(decoded['experiment']) || decoded['files'] is! Map) {
      throw const FormatException('The experiment ownership receipt is invalid.');
    }
    final receipt = Map<String, dynamic>.from(decoded);
    final files = Map<String, dynamic>.from(receipt['files'] as Map);
    final project = receipt['project'];
    if (project is! String || !RegExp(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$').hasMatch(project) ||
        files.length != 1 || !RegExp('^romfs/${RegExp.escape(project)}/Config/UserEngine\\.ini\$', caseSensitive: false).hasMatch(files.keys.single)) {
      throw const FormatException('The experiment file inventory is invalid.');
    }
    final found = <String>{};
    var visited = 0;
    await for (final entity in Directory(own).list(recursive: true, followLinks: false)) {
      if (++visited > 32 || entity is Link) throw const FormatException('The experiment folder was changed.');
      if (entity is File) found.add(p.relative(entity.path, from: own));
    }
    if (found.length != 2 || !found.contains(manifest) || !found.contains(files.keys.single)) {
      throw const FormatException('The experiment folder contains other files.');
    }
    for (final entry in files.entries) {
      final file = File(await _safe(p.join(own, entry.key)));
      if (await file.length() > 131072 || sha256.convert(await file.readAsBytes()).toString() != entry.value) {
        throw const FormatException('The installed experiment was edited; preserve it before changing it.');
      }
    }
    return receipt;
  }

  Future<void> _conflicts(List<String> roots, String project, String own) async {
    final suffix = '/romfs/$project/Config/UserEngine.ini'.toLowerCase();
    for (final path in roots) {
      if (!await Directory(path).exists()) continue;
      var count = 0;
      await for (final entity in Directory(path).list(recursive: true, followLinks: false)) {
        if (++count > 16384 || entity is Link) throw const FormatException('The mods inventory requires manual inspection.');
        if (entity.path == own || p.isWithin(own, entity.path)) continue;
        if (entity is File && (entity.path.toLowerCase().endsWith(suffix) ||
            p.basename(entity.path).toLowerCase() == 'romfs.bin')) {
          throw const FormatException('An existing mod may override this configuration. It will not be changed.');
        }
      }
    }
  }

  /// Caller must hold MelonxInternalService.editLibrary's native mutation gate.
  /// 'off' removes only a verified owned experiment, retaining its exact backup.
  Future<void> apply(Map<String, dynamic> info, String experiment) async {
    if (experiment != 'off' && !experiments.containsKey(experiment)) throw const FormatException('Unknown experiment.');
    final (project, roots) = await _inspection(info);
    final own = await _safe(p.join(roots.first, folder));
    final old = await _owned(own);
    if (experiment == 'off' && old == null) return;
    if (experiment != 'off') await _conflicts(roots, project, own);
    final nonce = DateTime.now().microsecondsSinceEpoch.toString();
    final backup = await _safe(p.join(root.path, 'UnrealProfileBackups', nonce));
    final stage = Directory(await _safe(p.join(root.path, '.rewindbox-unreal-stage-$nonce')));
    var previousMoved = false;
    try {
      if (experiment != 'off') {
        final choice = experiments[experiment]!;
        final relative = _relative(info, project);
        final base = info['baseConfiguration'] as String? ?? '';
        final bytes = utf8.encode('$base\n; RewindBox experimental override. Individual CVar support is unverified.\n[SystemSettings]\n${choice.$1}=${choice.$2}\n');
        final file = File(p.join(stage.path, relative));
        await file.parent.create(recursive: true);
        await file.writeAsBytes(bytes, flush: true);
        await File(p.join(stage.path, manifest)).writeAsString(jsonEncode({
          'schema': 1, 'titleId': titleId, 'project': project, 'experiment': experiment,
          'cvar': choice.$1, 'value': choice.$2, 'changesVisualQuality': choice.$3,
          'configurationLoadVerified': false, 'cvarSupportVerified': false,
          'baseConfigurationSHA256': sha256.convert(utf8.encode(base)).toString(),
          'files': {relative: sha256.convert(bytes).toString()},
        }), flush: true);
      }
      if (old != null) {
        await Directory(p.dirname(backup)).create(recursive: true);
        await Directory(own).rename(backup);
        previousMoved = true;
      }
      if (experiment != 'off') {
        await Directory(p.dirname(own)).create(recursive: true);
        await stage.rename(own);
      }
    } catch (_) {
      if (previousMoved && !await Directory(own).exists()) await Directory(backup).rename(own);
      rethrow;
    } finally {
      if (await stage.exists()) await stage.delete(recursive: true);
    }
  }
}
