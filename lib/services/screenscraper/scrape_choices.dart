import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/repositories/scraper_repository.dart';
import 'package:neostation/services/logger_service.dart';

/// Scraper choices that change what a scrape fetches (docs/game-box-3d.md
/// § 18). `is_fully_scraped` means complete for the choices of the last
/// scrape: when one of them changes, completed games are opened again so
/// that "New content only" applies it; nothing is downloaded until it runs.
///
/// A media type added already reopens them in the repository; the region
/// order and the language do it here (the repository is a locked library
/// file, docs/retroarch-baseline-manifest.json).
class ScrapeChoices {
  ScrapeChoices._();

  static final _log = LoggerService.instance;

  /// Opens every completed game again for "New content only".
  static Future<int> reopenCompletedGames(String reason) async {
    try {
      final db = await SqliteService.getDatabase();
      final count = await db.update(
        'user_screenscraper_metadata',
        {
          'is_fully_scraped': 0,
          'updated_at': DateTime.now().toIso8601String(),
        },
        where: 'is_fully_scraped = ?',
        whereArgs: [1],
      );
      _log.i('Scraper: $reason; reopened $count completed game(s) for new_only.');
      return count;
    } catch (e) {
      _log.e('Scraper: reopening completed games failed: $e');
      return 0;
    }
  }

  /// Saves the region order; another order can choose other pictures.
  static Future<bool> saveRegionPriority(List<String> regions) async {
    final previous = await ScraperRepository.getRegionPriority();
    final saved = await ScraperRepository.saveRegionPriority(regions);
    if (saved && previous.join(',') != regions.join(',')) {
      await reopenCompletedGames('region priority changed');
    }
    return saved;
  }

  /// After the scraping language changed from [previous] to [current]:
  /// texts and pictures follow it.
  static Future<void> languageChanged(String? previous, String current) async {
    if (previous == null || previous.isEmpty || previous == current) return;
    await reopenCompletedGames('language changed');
  }
}
