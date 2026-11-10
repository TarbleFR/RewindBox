import 'package:neostation/services/game_box/game_box_media.dart';

/// Pictures a library import writes before any scrape: the console's own
/// title icon, copied where a cover (and, for PS3, a screenshot) belongs.
///
/// They stand in for missing media, so every scrape mode replaces them with
/// the first real one, and "New content only" never counts them as content
/// already present (docs/game-box-3d.md § 18).
class ScrapeMediaPlaceholder {
  ScrapeMediaPlaceholder._();

  /// Size of a PS3 `ICON0.PNG`, which the RPCS3 library copies to `box2d`
  /// and `screenshots` (Sony's format: always 320 × 176).
  static const int ps3IconWidth = 320;
  static const int ps3IconHeight = 176;

  /// Largest side of a Switch title icon (256 × 256 JPEG in the NACP) copied
  /// to `box2d` by the MeloNX import. A Switch case cover is portrait.
  static const int switchIconMaxSide = 512;

  /// Whether the picture at [path] is an imported console icon standing in
  /// for the ScreenScraper media type [mediaType] of [systemFolder].
  static bool isPlaceholder(String systemFolder, String mediaType, String path) {
    final folder = systemFolder.toLowerCase();
    if (folder != 'ps3' && folder != 'switch') return false;
    if (mediaType != 'box2D' && mediaType != 'ss') return false;
    final size = GameBoxImageSize.of(path);
    if (size == null) return false;
    final w = size.width.round(), h = size.height.round();
    if (folder == 'ps3') return w == ps3IconWidth && h == ps3IconHeight;
    return mediaType == 'box2D' && w == h && w <= switchIconMaxSide;
  }
}
