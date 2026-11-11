import 'dart:io';

import 'package:path/path.dart' as path;

import '../data/datasources/sqlite_service.dart';
import '../models/system_model.dart';
import 'dolphin_internal_v2_service.dart';
import 'library_folder_inspection.dart';

/// What the screens that add a library folder share: the consoles the
/// inspection recognises, a readable name for a folder, and the check that
/// a picked folder really opens.
abstract final class LibraryFolderLinker {
  /// Folder names that are no console (virtual playlists).
  static const Set<String> virtualFolders = <String>{'all', 'android', 'favorites', 'recent', 'steam'};

  /// Console folders shown as examples when nothing was recognised.
  static const List<String> preferredExamples = <String>['snes', 'gba', 'nes', 'psx', 'n64', 'megadrive', 'nds'];

  /// The consoles of [systems] as the inspection needs them, with their file
  /// types read from the database. On iOS, GameCube, Wii and PlayStation 2
  /// keep their games in RewindBox's own storage: a library folder is not
  /// read for them ([InspectionSystem.importOnly]).
  static Future<List<InspectionSystem>> inspectionSystems(
    List<SystemModel> systems, {
    bool? ios,
    Future<Set<String>> Function(String systemId)? extensionsOf,
  }) async {
    final onIos = ios ?? Platform.isIOS;
    final read = extensionsOf ?? SqliteService.getExtensionsForSystem;
    final result = <InspectionSystem>[];
    for (final system in systems) {
      final id = system.id;
      final folder = system.folderName.trim().toLowerCase();
      if (id == null || folder.isEmpty || virtualFolders.contains(folder)) continue;
      final extensions = await read(id);
      if (extensions.isEmpty) continue;
      result.add(InspectionSystem(
        id: id,
        name: system.realName,
        folderNames: <String>[system.folderName, ...system.folders],
        extensions: extensions.map((extension) => extension.toLowerCase()).toSet(),
        recursive: system.recursiveScan,
        importOnly: onIos && (DolphinInternalV2Service.isDolphinSystem(folder) || folder == 'ps2'),
      ));
    }
    return result;
  }

  /// A few real console folder names, the best known first.
  static List<String> exampleFolders(List<InspectionSystem> systems, {int count = 5}) {
    final primaries = <String>[for (final system in systems) system.primaryFolder];
    final examples = <String>[
      for (final name in preferredExamples)
        if (primaries.contains(name)) name,
    ];
    for (final name in primaries) {
      if (examples.length >= count) break;
      if (!examples.contains(name)) examples.add(name);
    }
    return examples.take(count).toList();
  }

  /// A folder as the user knows it in the Files app, without the container
  /// path: "On My iPhone › Roms" is `…/File Provider Storage/Roms` on disk.
  static String describe(String folder) {
    final normalized = path.posix.normalize(folder);
    List<String> after(String marker) => normalized
        .substring(normalized.indexOf(marker) + marker.length)
        .split('/')
        .where((segment) => segment.isNotEmpty)
        .toList();

    List<String> segments;
    if (normalized.contains('/File Provider Storage/')) {
      segments = after('/File Provider Storage/');
    } else if (normalized.endsWith('/File Provider Storage')) {
      segments = const <String>[];
    } else if (normalized.contains('/com~apple~CloudDocs/')) {
      segments = <String>['iCloud Drive', ...after('/com~apple~CloudDocs/')];
    } else if (normalized.contains('/Documents/')) {
      segments = after('/Documents/');
    } else {
      final all = normalized.split('/').where((segment) => segment.isNotEmpty).toList();
      segments = all.length <= 2 ? all : all.sublist(all.length - 2);
    }
    if (segments.isEmpty) return path.posix.basename(normalized);
    return segments.join(' › ');
  }

  /// Throws a [FileSystemException] when [folder] does not open: a picked
  /// folder whose access was not really granted must not be registered as a
  /// library (it would show no game and no reason).
  static Future<void> ensureReadable(
    String folder, {
    Duration timeout = const Duration(seconds: 15),
  }) async {
    final directory = Directory(folder);
    if (!await directory.exists().timeout(timeout, onTimeout: () => false)) {
      throw FileSystemException('The folder does not open', folder);
    }
    try {
      await directory.list(followLinks: false).take(1).drain<void>().timeout(timeout);
    } on FileSystemException {
      rethrow;
    } catch (error) {
      throw FileSystemException('The folder is not readable: $error', folder);
    }
  }
}
