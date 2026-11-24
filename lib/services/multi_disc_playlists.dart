import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as path;

import 'libretro_internal_service.dart';
import 'logger_service.dart';

/// One game found on several discs in one folder: its discs in order and the
/// playlist that will list them.
@immutable
class MultiDiscGroup {
  const MultiDiscGroup({required this.directory, required this.playlistName, required this.discs});

  final String directory;

  /// `<game>.m3u`.
  final String playlistName;

  /// File names of the discs, disc 1 first.
  final List<String> discs;
}

/// Creates the `.m3u` playlist of a multi-disc game, so the library shows the
/// game once and the core can change discs (Change disc in the game menu).
///
/// A game is recognised by its file names, the way redump and No-Intro sets
/// name them: "Game (Disc 1).cue", "Game (Disc 2).cue"… (also "Disk", "CD",
/// "Disque", "Disco", "[Disc 1 of 3]"). Only disc images that open on their
/// own are listed (.cue, .chd, .ccd, .toc, .gdi, .cdi), never the .bin tracks a
/// cue sheet names. Nothing is created when:
/// - the numbers do not start at 1, repeat, or there is a single disc;
/// - the folder already has `<game>.m3u`, or another playlist names one of the discs;
/// - two files of different types claim the same disc (which one to list is not known).
/// The disc files are not moved or renamed. A memory card saved by playing a
/// disc on its own is copied (never moved) to the playlist's name in each
/// core's save folder, so the progress follows the game.
abstract final class MultiDiscPlaylists {
  static final _log = LoggerService.instance;

  static const Set<String> discExtensions = {'.cue', '.chd', '.ccd', '.toc', '.gdi', '.cdi'};

  static final RegExp _discToken = RegExp(
    r'\s*[\(\[]\s*(?:disc|disk|cd|disque|disco)\s*([0-9]{1,2})(?:\s*(?:of|/|sur|de)\s*[0-9]{1,2})?\s*[\)\]]',
    caseSensitive: false,
  );

  /// The multi-disc games among [fileNames] (names only, all in [directory]).
  static List<MultiDiscGroup> detect(String directory, Iterable<String> fileNames) {
    final groups = <String, ({String base, Map<int, List<String>> discs})>{};
    for (final name in fileNames) {
      final extension = path.extension(name).toLowerCase();
      if (!discExtensions.contains(extension)) continue;
      final stem = path.basenameWithoutExtension(name);
      final matches = _discToken.allMatches(stem).toList();
      if (matches.length != 1) continue;
      final number = int.parse(matches.single.group(1)!);
      final base = (stem.substring(0, matches.single.start) + stem.substring(matches.single.end))
          .replaceAll(RegExp(r'\s{2,}'), ' ')
          .trim();
      if (base.isEmpty) continue;
      final group = groups.putIfAbsent(base.toLowerCase(), () => (base: base, discs: {}));
      group.discs.putIfAbsent(number, () => []).add(name);
    }
    final found = <MultiDiscGroup>[];
    for (final group in groups.values) {
      final numbers = group.discs.keys.toList()..sort();
      if (numbers.length < 2 || numbers.first != 1) continue;
      if (numbers.last != numbers.length) continue; // a disc is missing
      if (group.discs.values.any((files) => files.length != 1)) continue;
      found.add(MultiDiscGroup(
        directory: directory,
        playlistName: '${group.base}.m3u',
        discs: [for (final number in numbers) group.discs[number]!.single],
      ));
    }
    found.sort((a, b) => a.playlistName.compareTo(b.playlistName));
    return found;
  }

  /// Creates the missing playlists for the games among [filePaths] (files of
  /// one system, possibly in several folders). Returns the paths created.
  static Future<List<String>> createMissing(Iterable<String> filePaths) async {
    final byDirectory = <String, List<String>>{};
    for (final file in filePaths) {
      byDirectory.putIfAbsent(path.dirname(file), () => []).add(path.basename(file));
    }
    final created = <String>[];
    for (final entry in byDirectory.entries) {
      final groups = detect(entry.key, entry.value);
      if (groups.isEmpty) continue;
      final listed = await _namesInPlaylists(entry.key, entry.value);
      for (final group in groups) {
        final playlist = File(path.join(group.directory, group.playlistName));
        try {
          if (await playlist.exists()) continue;
          if (group.discs.any((disc) => listed.contains(disc.toLowerCase()))) continue;
          final partial = File('${playlist.path}.partial');
          await partial.writeAsString('${group.discs.join('\n')}\n', flush: true);
          await partial.rename(playlist.path);
          created.add(playlist.path);
          _log.i('Multi-disc: ${group.playlistName} lists ${group.discs.length} discs');
          await _carrySaves(group);
        } catch (error) {
          _log.w('Multi-disc: ${group.playlistName} not created: $error');
        }
      }
    }
    return created;
  }

  /// Lower-case file names that the playlists already in [directory] list.
  static Future<Set<String>> _namesInPlaylists(String directory, List<String> names) async {
    final listed = <String>{};
    for (final name in names.where((name) => path.extension(name).toLowerCase() == '.m3u')) {
      try {
        final file = File(path.join(directory, name));
        if (await file.length() > 65536) continue;
        for (final line in await file.readAsLines()) {
          final trimmed = line.trim();
          if (trimmed.isNotEmpty && !trimmed.startsWith('#')) listed.add(path.basename(trimmed).toLowerCase());
        }
      } catch (_) {}
    }
    return listed;
  }

  /// Copies the most recent memory card of a disc played on its own to the
  /// playlist's name, in each core's save folder that has none yet.
  static Future<void> _carrySaves(MultiDiscGroup group) async {
    try {
      final saves = await LibretroInternalService.savesDirectory();
      if (!await saves.exists()) return;
      final target = path.basenameWithoutExtension(group.playlistName);
      await for (final core in saves.list(followLinks: false)) {
        if (core is! Directory) continue;
        File? newest;
        DateTime? newestTime;
        for (final disc in group.discs) {
          final save = File(path.join(core.path, '${path.basenameWithoutExtension(disc)}.srm'));
          if (!await save.exists()) continue;
          final modified = await save.lastModified();
          if (newestTime == null || modified.isAfter(newestTime)) {
            newest = save;
            newestTime = modified;
          }
        }
        final destination = File(path.join(core.path, '$target.srm'));
        if (newest == null || await destination.exists()) continue;
        await newest.copy(destination.path);
        _log.i('Multi-disc: ${path.basename(newest.path)} copied to ${path.basename(destination.path)}');
      }
    } catch (error) {
      _log.w('Multi-disc: memory cards of ${group.playlistName} not carried: $error');
    }
  }
}
