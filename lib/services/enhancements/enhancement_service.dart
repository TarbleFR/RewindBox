import 'dart:io';

import '../../models/game_model.dart';
import '../logger_service.dart';
import '../texture_catalog_service.dart';
import 'adapters/armsx2_enhancement_adapter.dart';
import 'adapters/dolphin_enhancement_adapter.dart';
import 'adapters/melonx_enhancement_adapter.dart';
import 'adapters/rpcs3_enhancement_adapter.dart';
import 'enhancement_adapter.dart';
import 'enhancement_catalog.dart';
import 'enhancement_models.dart';
import 'enhancement_store.dart';

/// Entry point of the Cheats & Enhancements system.
///
/// Opens a game's enhancements, activates or deactivates them through the
/// game's engine adapter, and restores original configurations. Nothing here
/// runs when a game launches: every change is written to the engine's own
/// files beforehand and read by the engine at its next start.
class EnhancementService {
  EnhancementService({
    EnhancementCatalog? catalog,
    EnhancementStore? store,
    List<EnhancementAdapter>? adapters,
    bool Function(String systemFolder)? texturesSupported,
    bool Function()? embeddedEngines,
  }) : catalog = catalog ?? EnhancementCatalog.instance,
       store = store ?? EnhancementStore.instance,
       adapters =
           adapters ??
           [
             MelonxEnhancementAdapter(),
             Rpcs3EnhancementAdapter(),
             Armsx2EnhancementAdapter(),
             DolphinEnhancementAdapter(),
           ],
       _texturesSupported = texturesSupported ?? TextureCatalogService.supports,
       _embeddedEngines = embeddedEngines ?? (() => Platform.isIOS);

  static final EnhancementService instance = EnhancementService();

  final EnhancementCatalog catalog;
  final EnhancementStore store;
  final List<EnhancementAdapter> adapters;
  final bool Function(String systemFolder) _texturesSupported;

  /// The adapters' engines are embedded in the iOS application only.
  final bool Function() _embeddedEngines;
  final _log = LoggerService.instance;

  EnhancementAdapter? adapterFor(String systemFolder) {
    for (final adapter in adapters) {
      if (adapter.handles(systemFolder)) return adapter;
    }
    return null;
  }

  EnhancementAdapter? adapterForEngine(String engine) {
    for (final adapter in adapters) {
      if (adapter.engine.name == engine) return adapter;
    }
    return null;
  }

  bool supportsTextures(String systemFolder) => _texturesSupported(systemFolder);

  /// Whether the Cheats & Enhancements page has anything for this system.
  bool supports(String systemFolder) =>
      (_embeddedEngines() && adapterFor(systemFolder) != null) || supportsTextures(systemFolder);

  /// Lists a game's enhancements. With [download] false nothing is fetched:
  /// a game whose shard is not cached shows its counts and a download action.
  Future<EnhancementGameView> open(
    GameModel game,
    String systemFolder, {
    bool download = false,
    EnhancementProgress? onProgress,
  }) async {
    final index = await catalog.index();
    final adapter = adapterFor(systemFolder);
    if (adapter == null) {
      return EnhancementGameView(
        identity: EnhancementGameIdentity.unavailable(
          EnhancementEngine.libretro,
          EnhancementProblem.unsupportedSystem,
          title: game.name,
        ),
        items: const [],
        catalogueRevision: index.revision,
      );
    }
    final identity = await adapter.identify(game, systemFolder);
    if (!identity.known) {
      return EnhancementGameView(identity: identity, items: const [], catalogueRevision: index.revision);
    }
    if (!await adapter.listed(catalog, identity)) {
      return EnhancementGameView(
        identity: EnhancementGameIdentity(
          engine: identity.engine,
          key: identity.key,
          title: identity.title,
          version: identity.version,
          crc: identity.crc,
          revision: identity.revision,
          aliases: identity.aliases,
          problem: EnhancementProblem.notInCatalogue,
        ),
        items: const [],
        catalogueRevision: index.revision,
      );
    }
    final record = await adapter.loadRecord(
      catalog,
      identity,
      download: download,
      onProgress: onProgress,
    );
    final stored = await store.game(identity.storeKey);
    if (record == null) {
      return EnhancementGameView(
        identity: identity,
        items: const [],
        catalogueRevision: index.revision,
        installed: stored?.installed ?? false,
      );
    }
    final state =
        stored ??
        EnhancementGameState(
          storeKey: identity.storeKey,
          engine: identity.engine.name,
          key: identity.key,
        );
    final probe = EnhancementGameState.fromJson(state.storeKey, state.toJson());
    if (await adapter.sync(identity, record, probe) && stored != null) {
      // The engine's files are the truth (an in-game menu may have changed them).
      await store.transaction((games) async {
        final current = games[identity.storeKey];
        if (current != null) {
          current
            ..installed = probe.installed
            ..active.clear()
            ..active.addAll(probe.active);
        }
      });
    }
    return EnhancementGameView(
      identity: identity,
      items: adapter.items(identity, record, probe),
      catalogueRevision: index.revision,
      installed: probe.installed,
      downloaded: true,
      credits: adapter.credits(record),
    );
  }

  Future<Map<String, dynamic>> _record(
    EnhancementAdapter adapter,
    EnhancementGameIdentity identity,
    EnhancementProgress? onProgress,
  ) async {
    final record = await adapter.loadRecord(catalog, identity, onProgress: onProgress);
    if (record == null) throw const EnhancementException('not_in_catalogue');
    return record;
  }

  Future<void> _write(
    EnhancementAdapter adapter,
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    Set<String> Function(Set<String> current) nextActive,
  ) async {
    final revision = (await catalog.index()).revision;
    await store.transaction((games) async {
      final state = games[identity.storeKey] ??= EnhancementGameState(
        storeKey: identity.storeKey,
        engine: identity.engine.name,
        key: identity.key,
      );
      await adapter.sync(identity, record, state);
      final active = nextActive(Set.of(state.active));
      await adapter.apply(identity, record, state, active);
      state
        ..active.clear()
        ..active.addAll(active)
        ..title = identity.title
        ..version = identity.version
        ..catalogueRevision = revision
        ..updatedAt = DateTime.now();
    });
  }

  /// Turns one entry on or off. Entries sharing its exclusive group are
  /// turned off first, so two aspect ratios never apply together.
  Future<EnhancementGameView> setActive(
    GameModel game,
    String systemFolder,
    EnhancementGameView view,
    EnhancementItem item,
    bool enabled, {
    EnhancementProgress? onProgress,
  }) async {
    final adapter = adapterFor(systemFolder);
    if (adapter == null || !view.identity.known) {
      throw const EnhancementException('unsupported');
    }
    if (enabled && !item.canActivate) throw EnhancementException('incompatible', item.problem.name);
    final record = await _record(adapter, view.identity, onProgress);
    final exclusive = item.exclusiveGroup.isEmpty
        ? const <String>{}
        : {
            for (final other in view.items)
              if (other.exclusiveGroup == item.exclusiveGroup && other.id != item.id) other.id,
          };
    await _write(adapter, view.identity, record, (current) {
      if (enabled) {
        current
          ..removeAll(exclusive)
          ..add(item.id);
      } else {
        current.remove(item.id);
      }
      // Entries that no longer match this game are dropped, never kept on.
      final compatible = {for (final other in view.items) if (other.canActivate) other.id};
      return current.intersection(compatible.union({item.id}));
    });
    _log.i('Enhancements: ${item.id} ${enabled ? 'on' : 'off'} for ${view.identity.storeKey}');
    return open(game, systemFolder, download: true);
  }

  /// Writes a game's whole payload with nothing enabled yet.
  Future<EnhancementGameView> install(
    GameModel game,
    String systemFolder,
    EnhancementGameView view, {
    EnhancementProgress? onProgress,
  }) async {
    final adapter = adapterFor(systemFolder);
    if (adapter == null || !view.identity.known) throw const EnhancementException('unsupported');
    final record = await _record(adapter, view.identity, onProgress);
    final compatible = {for (final item in view.items) if (item.canActivate) item.id};
    await _write(adapter, view.identity, record, (current) => current.intersection(compatible));
    return open(game, systemFolder, download: true);
  }

  /// Removes every file and line RewindBox wrote for one game.
  Future<void> restore(String storeKey) => store.transaction((games) async {
    final state = games[storeKey];
    if (state == null) return;
    final adapter = adapterForEngine(state.engine);
    if (adapter == null) throw EnhancementException('unsupported', state.engine);
    await adapter.remove(state);
    games.remove(storeKey);
  });

  /// Restores the original configuration of every game.
  Future<int> restoreAll() async {
    var restored = 0;
    for (final state in await store.all()) {
      try {
        await restore(state.storeKey);
        restored++;
      } catch (error) {
        _log.e('Enhancements: restoring ${state.storeKey} failed', error: error);
      }
    }
    return restored;
  }

  Future<List<EnhancementGameState>> games() => store.all();
}
