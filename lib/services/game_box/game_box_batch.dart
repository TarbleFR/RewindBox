import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/services/game_box/game_box_fetcher.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_service.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/services/game_box/game_box_sources.dart';

/// What the box-faces step did for one game of a batch scrape.
class GameBoxBatchOutcome {
  const GameBoxBatchOutcome({
    this.adopted = const {},
    this.missing = const {},
    this.statuses = const {},
  });

  static const none = GameBoxBatchOutcome();

  /// Faces added or improved, with the source each one came from.
  final Map<GameBoxMediaKind, GameBoxProvider> adopted;

  /// Faces still missing (or refused) after every source was asked.
  final Set<GameBoxMediaKind> missing;

  final Map<GameBoxProvider, GameBoxSourceStatus> statuses;
}

/// [GameBoxCancel] that also stops when the scrape is stopped.
class GameBoxBatchCancel extends GameBoxCancel {
  GameBoxBatchCancel(this._stopped);
  final bool Function()? _stopped;

  @override
  bool get cancelled => super.cancelled || (_stopped?.call() ?? false);
}

/// The box faces of the ScreenScraper batch run (docs/game-box-3d.md § 18):
/// after ScreenScraper's own download, the faces the media choices ask for
/// that are still missing, refused or an imported icon are completed by the
/// same ranked sources as the per-game "Box media" sheet — ScreenScraper's
/// other scans, GameTDB, MobyGames with the player's key — and nothing
/// chosen by hand is replaced.
class GameBoxBatch {
  GameBoxBatch._();

  static const _faces = [
    GameBoxMediaKind.front,
    GameBoxMediaKind.back,
    GameBoxMediaKind.spine,
    GameBoxMediaKind.support,
  ];

  /// The faces the scraper's media choices ask for: the cover with
  /// "Box 2D", the back, spine and support with "Box faces".
  static Set<GameBoxMediaKind> kindsOf(Iterable<String> enabledTypes) => {
        if (enabledTypes.contains('box2D')) GameBoxMediaKind.front,
        if (enabledTypes.contains('boxFaces')) ...const [
          GameBoxMediaKind.back,
          GameBoxMediaKind.spine,
          GameBoxMediaKind.support,
        ],
      };

  /// ScreenScraper media settings the plain download must not write: faces
  /// with a provenance record — chosen by hand, or adopted by the ranked
  /// sources — belong to the box-media service.
  static Set<String> ownedTypes(GameBoxLocalMedia local) => {
        for (final kind in _faces)
          if (local.recordOf(kind) != null) kind == GameBoxMediaKind.front ? 'box2D' : kind.screenScraperType,
      };

  /// The library game a batch row stands for.
  static GameModel gameOf({
    required String romName,
    required String appSystemId,
    required String systemFolder,
    String? romPath,
    String? name,
    String? titleId,
    String? titleName,
  }) {
    final shown = (name?.trim().isNotEmpty ?? false) ? name!.trim() : FileProvider.stripRomExtension(romName);
    return GameModel(
      romname: romName,
      realname: shown,
      name: shown,
      year: '',
      developer: '',
      publisher: '',
      genre: '',
      players: '',
      rating: 0,
      romPath: romPath,
      systemId: appSystemId,
      systemFolderName: systemFolder,
      titleId: titleId,
      titleName: titleName,
    );
  }

  /// One box-media step at a time: GameTDB pages and MobyGames' rate limit
  /// are shared by the scrape's threads.
  static Future<void> _tail = Future<void>.value();

  static Future<T> _serial<T>(Future<T> Function() run) {
    final result = _tail.then((_) => run());
    _tail = result.then((_) {}, onError: (_) {});
    return result;
  }

  /// Completes the faces among [kinds] that need it for [ctx].
  ///
  /// [screenScraperListing] is ScreenScraper's answer the batch already has
  /// (no request); with [askScreenScraper] and no listing, ScreenScraper is
  /// asked once. [extraSources] adds GameTDB, then MobyGames for the faces
  /// GameTDB did not have when the player saved a key.
  static Future<GameBoxBatchOutcome> complete(
    GameBoxSearchContext ctx, {
    required Set<GameBoxMediaKind> kinds,
    GameBoxScreenScraperListing? screenScraperListing,
    bool askScreenScraper = false,
    bool extraSources = true,
    GameBoxCancel? cancel,
    bool upgradeLanguage = false,
  }) async {
    if (kinds.isEmpty) return GameBoxBatchOutcome.none;
    final needed = await GameBoxMediaService.facesToComplete(ctx, kinds, upgradeLanguage: upgradeLanguage);
    if (needed.isEmpty || (cancel?.cancelled ?? false)) return GameBoxBatchOutcome.none;
    return _serial(() async {
      final adopted = <GameBoxMediaKind, GameBoxProvider>{};
      final statuses = <GameBoxProvider, GameBoxSourceStatus>{};
      var remaining = needed;
      var game = ctx;
      var listing = screenScraperListing;

      // ScreenScraper first, once: its answer feeds every later phase.
      if (listing == null && askScreenScraper) {
        final found = await GameBoxMediaService.search(
          game,
          providers: const {GameBoxProvider.screenscraper},
          cancel: cancel,
        );
        statuses.addAll(found.statuses);
        listing = found.listing;
      }
      // A game never scraped is still named after its file; GameTDB matches
      // Switch titles exactly, so ScreenScraper's name is used for it.
      final title = listing?.title;
      if (title != null && game.game.name == FileProvider.stripRomExtension(game.game.romname)) {
        game = GameBoxSearchContext(
          game: game.game.copyWith(name: title, realname: title),
          systemFolder: game.systemFolder,
          fileProvider: game.fileProvider,
          profile: game.profile,
          appSystemId: game.appSystemId,
        );
      }

      Future<void> run(Set<GameBoxProvider> providers) async {
        final found = await GameBoxMediaService.search(
          game,
          providers: providers,
          cancel: cancel,
          screenScraperListing: listing,
        );
        for (final e in found.statuses.entries) {
          if (providers.contains(e.key)) statuses[e.key] = e.value;
        }
        final report = await GameBoxMediaService.complete(
          game,
          search: found,
          cancel: cancel,
          kinds: remaining,
          upgradeLanguage: upgradeLanguage,
        );
        adopted.addAll(report.adoptedBy);
        remaining = {
          for (final kind in remaining)
            if (!adopted.containsKey(kind) && report.outcomes[kind] != GameBoxFaceOutcome.kept) kind,
        };
      }

      await run({if (extraSources) GameBoxProvider.gametdb});
      if (extraSources &&
          remaining.isNotEmpty &&
          !(cancel?.cancelled ?? false) &&
          await GameBoxPreferences.mobyGamesKey() != null) {
        await run(const {GameBoxProvider.mobygames});
      }
      return GameBoxBatchOutcome(adopted: adopted, missing: remaining, statuses: statuses);
    });
  }
}
