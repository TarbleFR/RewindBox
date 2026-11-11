import 'dart:io';

import 'package:path/path.dart' as path;

/// What makes a console recognisable in a library folder.
class InspectionSystem {
  const InspectionSystem({
    required this.id,
    required this.name,
    required this.folderNames,
    required this.extensions,
    this.recursive = true,
    this.importOnly = false,
  });

  final String id;

  /// The playlist as the user knows it ("Game Boy Advance").
  final String name;

  /// The folder names the scanner accepts for this console, primary first.
  final List<String> folderNames;

  /// File types of its games: lowercase, without the dot.
  final Set<String> extensions;

  /// Whether the scanner also reads the sub-folders of the console folder.
  final bool recursive;

  /// The console keeps its games in RewindBox's own storage (GameCube, Wii
  /// and PlayStation 2 on iOS): a library folder is not read for it, its
  /// games are added from the console's playlist.
  final bool importOnly;

  String get primaryFolder => folderNames.first;
}

/// A folder of the library that belongs to a console: its games go to that
/// console's playlist.
class InspectedConsoleFolder {
  const InspectedConsoleFolder({
    required this.system,
    required this.folderName,
    required this.games,
    required this.examples,
    required this.otherFiles,
  });

  final InspectionSystem system;

  /// The folder as it is spelled on the device.
  final String folderName;

  /// Files the console reads.
  final int games;

  /// The first few of them, without their extension.
  final List<String> examples;

  /// Files of a type the console does not read (they are left out).
  final int otherFiles;
}

/// A folder of the library that no console claims: nothing in it is read.
class InspectedUnknownFolder {
  const InspectedUnknownFolder({
    required this.folderName,
    required this.files,
    this.suggestion,
  });

  final String folderName;
  final int files;

  /// The console whose games these files look like, when one stands out.
  final InspectionSystem? suggestion;
}

/// What RewindBox will read in a library folder, before anything is added:
/// which folder feeds which playlist, and what is left out with the reason.
///
/// A library folder holds one folder per console, named after the console
/// ("snes", "gba", …). A wrong folder, or a console folder under another
/// name, used to be accepted in silence and simply showed no game.
class LibraryFolderInspection {
  const LibraryFolderInspection({
    required this.root,
    required this.consoles,
    required this.unknownFolders,
    required this.looseGames,
    required this.truncated,
    this.pickedConsole,
  });

  final String root;
  final List<InspectedConsoleFolder> consoles;
  final List<InspectedUnknownFolder> unknownFolders;

  /// Game files lying directly in [root]: no console folder, so not read.
  final int looseGames;

  /// The folder holds more entries than [LibraryFolderInspector.entryLimit]:
  /// the counts are lower bounds.
  final bool truncated;

  /// The picked folder is itself the folder of one console (the user chose
  /// `gba` instead of the folder that contains it): nothing can be read
  /// from it as a library, and the report says which folder to choose.
  final InspectedConsoleFolder? pickedConsole;

  /// Whether at least one console folder was found.
  bool get recognised => consoles.isNotEmpty;

  /// Console folders the scanner reads (not [InspectionSystem.importOnly]).
  Iterable<InspectedConsoleFolder> get scanned =>
      consoles.where((console) => !console.system.importOnly);

  /// Console folders found but kept in RewindBox's own storage.
  Iterable<InspectedConsoleFolder> get importOnly =>
      consoles.where((console) => console.system.importOnly);

  /// Games that will appear in a playlist once the folder is added.
  int get games => scanned.fold(0, (sum, console) => sum + console.games);

  /// Playlists that receive at least one game.
  int get playlists =>
      scanned.where((console) => console.games > 0).map((console) => console.system.id).toSet().length;
}

abstract final class LibraryFolderInspector {
  /// Entries read per folder before the inspection stops counting.
  static const int entryLimit = 20000;

  /// Game names shown per console.
  static const int exampleLimit = 3;

  /// Share of a folder's files that must point to one console before it is
  /// suggested for an unrecognised folder.
  static const double suggestionShare = 0.6;

  /// RetroArch's own folders: they hold no game and are not reported as
  /// unrecognised console folders.
  static const Set<String> infrastructureFolders = <String>{
    'assets',
    'autoconfig',
    'cheats',
    'config',
    'cores',
    'database',
    'filters',
    'info',
    'logs',
    'overlays',
    'playlists',
    'saves',
    'screenshots',
    'shaders',
    'states',
    'system',
    'thumbnails',
  };

  static String _extension(String file) {
    final extension = path.extension(file).toLowerCase();
    return extension.startsWith('.') ? extension.substring(1) : extension;
  }

  static bool _hidden(String entity) => path.basename(entity).startsWith('.');

  /// Reads [root] one level deep, then each console folder (and each
  /// unrecognised folder, to count what is left out). Nothing is written.
  static Future<LibraryFolderInspection> inspect(
    String root,
    List<InspectionSystem> systems, {
    int entryLimit = LibraryFolderInspector.entryLimit,
  }) async {
    final byFolder = <String, InspectionSystem>{};
    final owners = <String, Set<String>>{};
    for (final system in systems) {
      for (final name in system.folderNames) {
        final key = name.trim().toLowerCase();
        if (key.isNotEmpty) byFolder.putIfAbsent(key, () => system);
      }
      for (final extension in system.extensions) {
        owners.putIfAbsent(extension, () => <String>{}).add(system.id);
      }
    }
    final byId = <String, InspectionSystem>{for (final system in systems) system.id: system};

    var truncated = false;
    final directories = <Directory>[];
    var looseGames = 0;
    // Files lying directly in the picked folder (see `pickedConsole`).
    final ownGames = <String>[];
    var seen = 0;
    await for (final entity in Directory(root).list(followLinks: false)) {
      if (++seen > entryLimit) {
        truncated = true;
        break;
      }
      if (_hidden(entity.path)) continue;
      if (entity is Directory) {
        directories.add(entity);
      } else if (entity is File) {
        ownGames.add(entity.path);
        if (owners.containsKey(_extension(entity.path))) looseGames++;
      }
    }
    directories.sort((a, b) => path.basename(a.path).toLowerCase().compareTo(path.basename(b.path).toLowerCase()));

    final consoles = <InspectedConsoleFolder>[];
    final unknown = <InspectedUnknownFolder>[];
    for (final directory in directories) {
      final name = path.basename(directory.path);
      final system = byFolder[name.toLowerCase()];
      final files = <String>[];
      var count = 0;
      try {
        await for (final entity in directory.list(recursive: system?.recursive ?? true, followLinks: false)) {
          if (++count > entryLimit) {
            truncated = true;
            break;
          }
          if (entity is File && !_hidden(entity.path)) files.add(entity.path);
        }
      } on FileSystemException {
        // An unreadable folder counts for nothing; the scan skips it too.
      }
      if (system != null) {
        final games = files.where((file) => system.extensions.contains(_extension(file))).toList()..sort();
        consoles.add(InspectedConsoleFolder(
          system: system,
          folderName: name,
          games: games.length,
          examples: [for (final game in games.take(exampleLimit)) path.basenameWithoutExtension(game)],
          otherFiles: files.length - games.length,
        ));
        continue;
      }
      if (infrastructureFolders.contains(name.toLowerCase())) continue;
      // Only a file type that a single console reads can name that console.
      final votes = <String, int>{};
      var gameLike = 0;
      for (final file in files) {
        final consolesOfType = owners[_extension(file)];
        if (consolesOfType == null) continue;
        gameLike++;
        if (consolesOfType.length == 1) {
          votes.update(consolesOfType.single, (value) => value + 1, ifAbsent: () => 1);
        }
      }
      InspectionSystem? suggestion;
      if (votes.isNotEmpty) {
        final best = votes.entries.reduce((a, b) => b.value > a.value ? b : a);
        if (best.value >= gameLike * suggestionShare) suggestion = byId[best.key];
      }
      // A folder without any game-like file is not a console folder under
      // another name: it is not reported.
      if (gameLike > 0) {
        unknown.add(InspectedUnknownFolder(folderName: name, files: gameLike, suggestion: suggestion));
      }
    }
    // No console folder inside, and the picked folder bears the name of a
    // console: its own games lie directly in it.
    InspectedConsoleFolder? pickedConsole;
    final own = consoles.isEmpty ? byFolder[path.basename(path.normalize(root)).toLowerCase()] : null;
    if (own != null) {
      // A recursive console reads its sub-folders too (one folder per game).
      var files = ownGames;
      if (own.recursive) {
        files = <String>[];
        var count = 0;
        try {
          await for (final entity in Directory(root).list(recursive: true, followLinks: false)) {
            if (++count > entryLimit) {
              truncated = true;
              break;
            }
            if (entity is File && !_hidden(entity.path)) files.add(entity.path);
          }
        } on FileSystemException {
          // Unreadable: the own files found above stay the answer.
          files = ownGames;
        }
      }
      final games = files.where((file) => own.extensions.contains(_extension(file))).toList()..sort();
      // A folder bearing a console's alias ("Nintendo") that holds no game
      // of that console is a library with console folders under other names.
      if (games.isNotEmpty) {
        pickedConsole = InspectedConsoleFolder(
          system: own,
          folderName: path.basename(path.normalize(root)),
          games: games.length,
          examples: [for (final game in games.take(exampleLimit)) path.basenameWithoutExtension(game)],
          otherFiles: files.length - games.length,
        );
      }
    }
    return LibraryFolderInspection(
      root: root,
      consoles: consoles,
      unknownFolders: unknown,
      looseGames: looseGames,
      truncated: truncated,
      pickedConsole: pickedConsole,
    );
  }
}
