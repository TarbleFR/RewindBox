import 'dusklight_game_identity.dart';

/// Canonical identity for a title owned by NeoStation's Ports playlist.
///
/// The playlist is shared, but scraping must use the source console/game
/// identity of each embedded port rather than treating every title as
/// Dusklight/Twilight Princess.
class PortGameIdentity {
  const PortGameIdentity({
    required this.discId,
    required this.title,
    required this.displayTitle,
    required this.screenScraperSystemId,
  });

  final String discId;
  final String title;
  final String displayTitle;
  final int screenScraperSystemId;

  static Future<PortGameIdentity?> read(String gamePath) async {
    final dusklight = await DusklightGameIdentity.read(gamePath);
    if (dusklight == null) return null;
    return PortGameIdentity(
      discId: dusklight.discId,
      title: DusklightGameIdentity.title,
      displayTitle: DusklightGameIdentity.displayTitle,
      screenScraperSystemId: dusklight.screenScraperSystemId,
    );
  }
}
