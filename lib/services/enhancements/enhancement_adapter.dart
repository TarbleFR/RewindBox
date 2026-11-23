import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import '../../models/game_model.dart';
import 'enhancement_catalog.dart';
import 'enhancement_models.dart';
import 'enhancement_store.dart';

/// One embedded engine's view of the catalogue.
///
/// An adapter writes only formats its engine already reads at boot, records
/// every file or line it adds in the [EnhancementGameState], and can always
/// return the engine to its previous configuration from that record.
abstract class EnhancementAdapter {
  EnhancementEngine get engine;

  /// Whether a game of [systemFolder] runs on this adapter's engine.
  bool handles(String systemFolder);

  /// Reads the identity the engine matches: never guessed from a title.
  Future<EnhancementGameIdentity> identify(GameModel game, String systemFolder);

  /// The catalogue record(s) of [identity] merged into one map, or null.
  Future<Map<String, dynamic>?> loadRecord(
    EnhancementCatalog catalog,
    EnhancementGameIdentity identity, {
    bool download = true,
    EnhancementProgress? onProgress,
  }) => catalog.record(
    engine,
    identity.key,
    download: download,
    onProgress: onProgress,
  );

  /// Whether the catalogue lists [identity] at all (no download).
  Future<bool> listed(EnhancementCatalog catalog, EnhancementGameIdentity identity) async =>
      (await catalog.index()).contains(engine, identity.key);

  /// Every entry of [record] with its status for this game.
  List<EnhancementItem> items(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState? state,
  );

  List<String> credits(Map<String, dynamic> record) => const [];

  /// Updates [state] from the engine's own files before items are listed,
  /// so a choice made in an in-game menu is shown as it is. Returns true
  /// when [state] changed.
  Future<bool> sync(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
  ) async => false;

  /// Writes the native files so that exactly [active] entries apply.
  /// Called with the full record; installs the payload when needed.
  Future<void> apply(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
    Set<String> active,
  );

  /// Removes everything recorded in [state]; the engine is as before.
  Future<void> remove(EnhancementGameState state);

  /// Status shared by adapters whose payload is written on install.
  static EnhancementStatus statusOf(String id, EnhancementGameState? state) {
    if (state == null) return EnhancementStatus.available;
    if (state.active.contains(id)) return EnhancementStatus.active;
    return state.installed ? EnhancementStatus.installed : EnhancementStatus.available;
  }
}

/// Per-entry flags of the catalogue (`flags`: sorted, present only when not
/// empty), set by tools/enhancements from the entry's name and its author's
/// notes. Every adapter copies them into its item's payload (`flags`) for the
/// page's warnings.
abstract final class EnhancementFlags {
  /// The author says the code can crash or freeze the game.
  static const crashRisk = 'crashRisk';

  /// The code writes the game's own value (`Default 30 FPS`).
  static const restoresDefault = 'default';

  /// Needs the expanded 8 GB DRAM layout, which RewindBox does not offer.
  static const dram8gb = 'dram8gb';

  /// Experimental, work in progress, beta or untested.
  static const experimental = 'experimental';

  /// Renders 2160 lines or more (4K, 8K).
  static const heavy = 'heavy';

  /// An FPS-category entry that does not raise the frame-rate limit (a
  /// dynamic-resolution target, an FPS counter).
  static const noRefresh = 'noRefresh';

  /// The flags of a catalogue entry.
  static List<String> of(Map<String, dynamic> entry) => [
    for (final flag in (entry['flags'] as List? ?? const []))
      if (flag is String && flag.isNotEmpty) flag,
  ];

  /// The payload field of an entry's flags; empty when it has none.
  static Map<String, dynamic> payload(Map<String, dynamic> entry) {
    final flags = of(entry);
    return flags.isEmpty ? const {} : {'flags': flags};
  }

  /// The flags an adapter put in [item]'s payload.
  static List<String> ofItem(EnhancementItem item) => of(item.payload);
}

/// Small file helpers shared by adapters.
abstract final class EnhancementFiles {
  static String digest(List<int> bytes) => sha256.convert(bytes).toString();

  static Future<String?> digestOf(File file) async =>
      await file.exists() ? digest(await file.readAsBytes()) : null;

  static Future<void> writeAtomically(File file, List<int> bytes) async {
    await file.parent.create(recursive: true);
    final temporary = File('${file.path}.rewindbox-partial');
    await temporary.writeAsBytes(bytes, flush: true);
    await temporary.rename(file.path);
  }

  static Future<String> writeText(File file, String text) async {
    final bytes = utf8.encode(text);
    await writeAtomically(file, bytes);
    return digest(bytes);
  }

  /// Deletes [file] only while it still holds the bytes RewindBox wrote.
  static Future<bool> deleteIfOwned(File file, String expectedDigest) async {
    final actual = await digestOf(file);
    if (actual == null) return true;
    if (actual != expectedDigest) return false;
    await file.delete();
    return true;
  }

  static Future<String> readText(File file) async =>
      await file.exists() ? await file.readAsString() : '';

  static Future<void> deleteEmptyParents(Directory directory, Directory stop) async {
    var current = directory;
    while (current.path.length > stop.path.length && current.path.startsWith(stop.path)) {
      if (!await current.exists()) {
        current = current.parent;
        continue;
      }
      if (await current.list().isEmpty) {
        await current.delete();
        current = current.parent;
      } else {
        break;
      }
    }
  }
}
