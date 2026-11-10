import 'dart:math' as math;

import 'package:neostation/services/game_box/game_box_art_fit.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_regions.dart';

/// Where a candidate scan comes from (docs/game-box-3d.md § 14).
enum GameBoxProvider {
  /// ScreenScraper: the main source (`box-2D`, `box-2D-back`, `box-2D-side`,
  /// `support-2D`, `box-texture` when its layout is recognised).
  screenscraper,

  /// GameTDB: PS3 and Switch complement, by product code (PS3 serial = RPCS3
  /// title id; Switch product code found by exact title).
  gametdb,

  /// MobyGames: optional, with the player's own API key.
  mobygames,

  /// A picture imported by the player (The Cover Project, own scan…).
  manual,
}

extension GameBoxProviderName on GameBoxProvider {
  String get id => name;

  String get label => switch (this) {
        GameBoxProvider.screenscraper => 'ScreenScraper',
        GameBoxProvider.gametdb => 'GameTDB',
        GameBoxProvider.mobygames => 'MobyGames',
        GameBoxProvider.manual => 'Import',
      };

  /// Credit kept with each adopted scan.
  String get attribution => switch (this) {
        GameBoxProvider.screenscraper => 'ScreenScraper (screenscraper.fr)',
        GameBoxProvider.gametdb => 'GameTDB (gametdb.com)',
        GameBoxProvider.mobygames => 'MobyGames (mobygames.com)',
        GameBoxProvider.manual => 'Import',
      };
}

/// One scan that could become a face of the box.
class GameBoxCandidate {
  const GameBoxCandidate({
    required this.provider,
    required this.kind,
    required this.type,
    required this.identity,
    this.nature = GameBoxArtNature.scan,
    this.region = '',
    this.edition,
    this.productId,
    this.url,
    this.width,
    this.height,
    this.quality = 1,
    this.format = 'jpg',
    this.byProduct = false,
    this.bytes,
  });

  final GameBoxProvider provider;

  /// Face it would fill; [GameBoxMediaKind.full] for a whole cover sheet.
  final GameBoxMediaKind kind;

  /// Provider type, prefixed (`gametdb:coverHQ`, `screenscraper:box-2D-back`).
  final String type;

  /// Stable identity at the provider (MD5, art path): used to skip a scan
  /// already refused or already on disk.
  final String identity;
  final GameBoxArtNature nature;

  /// Region code in ScreenScraper's vocabulary (`eu`, `uk`, `fr`, `us`, `jp`…).
  final String region;

  /// Edition label when the source tells one (alternate case version…).
  final String? edition;

  /// Product code of the scanned edition (PS3 serial, Switch product code).
  final String? productId;

  /// Download address. For ScreenScraper it carries the credentials and is
  /// kept in memory only, never written.
  final String? url;

  /// Native pixel size when the source states it.
  final int? width;
  final int? height;

  /// 3 = high quality (GameTDB HQ, original scan), 2 = medium, 1 = small.
  final int quality;
  final String format;

  /// The game was matched by its product code or checksum (not by title).
  final bool byProduct;

  /// File size stated by the source.
  final int? bytes;

  String? get language => GameBoxRegions.languageOfRegion(region);

  int get pixels => (width ?? 0) * (height ?? 0);

  @override
  String toString() => 'GameBoxCandidate(${provider.name} ${kind.name} $type $region ${width}x$height)';
}

/// What the player's copy is, for choosing among candidates.
class GameBoxEditionHint {
  const GameBoxEditionHint({
    this.gameRegions = const [],
    this.frontRegion,
    this.productId,
    this.regionPriority = const {},
    this.language,
  });

  /// Regions of the player's copy (ScreenScraper codes), best first.
  final List<String> gameRegions;

  /// Region of the front already shown, when its edition is known.
  final String? frontRegion;

  /// Product code of the player's copy (PS3 serial…).
  final String? productId;

  /// The scraper's region priority (higher is preferred).
  final Map<String, int> regionPriority;

  /// The scraping language (`fr`…): within the player's edition, the print
  /// in that language comes first (docs/game-box-3d.md § 19).
  final String? language;

  /// Whether [region]'s print is in the scraping language (English, the
  /// default of most scans, gets no preference).
  bool prints(String? region) {
    final l = language;
    if (l == null || l.isEmpty || l == 'en' || region == null) return false;
    return GameBoxRegions.languageOfRegion(region) == l;
  }
}

/// Orders candidates: the right game and product first, then the edition
/// and region of the player's copy, then the exact kind of picture, and only
/// then quality and resolution. A larger scan never wins over the right
/// edition (docs/game-box-3d.md § 14).
class GameBoxCandidateRanking {
  GameBoxCandidateRanking._();

  static int score(GameBoxCandidate c, GameBoxEditionHint hint) {
    var s = 0;
    // 1. Product: the scan was listed for the player's product code.
    final product = hint.productId?.toUpperCase();
    if (product != null && product.isNotEmpty && c.productId?.toUpperCase() == product) {
      s += 100000;
    } else if (c.byProduct) {
      s += 60000;
    }
    // 2. Edition and region.
    s += 1000 * regionAffinity(c.region, hint.gameRegions);
    if (hint.frontRegion != null && GameBoxRegionFamily.same(c.region, hint.frontRegion!)) s += 800;
    // The print in the scraping language, within the edition: a France scan
    // for a European copy outranks the generic European one, never a scan
    // of another edition (an American copy keeps its American box).
    if (hint.prints(c.region) &&
        (hint.gameRegions.isEmpty || hint.gameRegions.any((g) => GameBoxRegionFamily.same(c.region, g)))) {
      s += 5000;
    }
    if (c.edition == null) s += 200; // the standard case before an alternate version
    // 3. Exact nature of the picture.
    s += switch (c.nature) {
      GameBoxArtNature.scan => 600,
      GameBoxArtNature.wrap => 400,
      GameBoxArtNature.framedCase => 100,
      GameBoxArtNature.render3d || GameBoxArtNature.promo => -100000,
    };
    // 4. Quality and resolution, as tie-breakers.
    s += 40 * c.quality;
    s += math.min(30, c.pixels ~/ 100000);
    s += (hint.regionPriority[c.region] ?? 0).clamp(0, 20);
    return s;
  }

  /// 0..12: how well [region] fits the player's [gameRegions].
  static int regionAffinity(String region, List<String> gameRegions) {
    if (gameRegions.isEmpty) return region == 'wor' ? 2 : 0;
    var best = 0;
    for (var i = 0; i < gameRegions.length; i++) {
      final g = gameRegions[i];
      final rank = math.max(0, 3 - i);
      if (g == region) {
        best = math.max(best, 9 + rank);
      } else if (GameBoxRegionFamily.same(region, g)) {
        best = math.max(best, 5 + rank);
      } else if (region == 'wor') {
        best = math.max(best, 3);
      }
    }
    return best;
  }

  /// [candidates] usable as faces, best first.
  static List<GameBoxCandidate> rank(Iterable<GameBoxCandidate> candidates, GameBoxEditionHint hint) {
    final list = [
      for (final c in candidates)
        if (c.nature != GameBoxArtNature.render3d && c.nature != GameBoxArtNature.promo) c,
    ];
    list.sort((a, b) => score(b, hint).compareTo(score(a, hint)));
    return preferReadable(list, hint);
  }

  /// Long side under which a scan is a thumbnail: its small print cannot be
  /// read, whatever the enlargement (docs/game-box-3d.md § 22).
  static const int thumbnailSide = 420;

  /// Whether [c] is a thumbnail: its stated size is small, or it is one of
  /// GameTDB's small templates (160 × 184 PS3 back, 340 × 184 sheet).
  static bool isThumbnail(GameBoxCandidate c) {
    final w = c.width, h = c.height;
    if (w != null && h != null) return math.max(w, h) < thumbnailSide;
    return c.provider == GameBoxProvider.gametdb && c.quality <= 1;
  }

  /// [b] is a print of the same edition as [a]: the same game found by its
  /// product code or checksum, in the same region family.
  static bool sameEdition(GameBoxCandidate a, GameBoxCandidate b) {
    final product = a.productId != null && a.productId!.toUpperCase() == b.productId?.toUpperCase();
    return (product || b.byProduct) && GameBoxRegionFamily.same(a.region, b.region);
  }

  /// [ranked] with every thumbnail placed after the readable scans of the
  /// same face and edition, when a face is chosen (missing, or picked in the
  /// list): a readable back of the copy outranks its thumbnail, never a scan
  /// of another edition, and never when the thumbnail is printed in the
  /// scraping language and the readable scan is not (a French print stays
  /// first). A face already on disk is never swapped for this: it is
  /// corrected instead (docs/game-box-3d.md § 22).
  static List<GameBoxCandidate> preferReadable(List<GameBoxCandidate> ranked, GameBoxEditionHint hint) {
    final list = [...ranked];
    for (var i = 0; i < list.length; i++) {
      final c = list[i];
      if (!isThumbnail(c)) continue;
      final language = hint.prints(c.region);
      // A readable scan of the same face, or a full sheet that holds it.
      final j = list.indexWhere(
        (o) =>
            (o.kind == c.kind || o.kind == GameBoxMediaKind.full) &&
            !isThumbnail(o) &&
            sameEdition(c, o) &&
            (!language || hint.prints(o.region)),
        i + 1,
      );
      if (j > i) list.insert(i, list.removeAt(j));
    }
    return list;
  }
}

/// Regions that print the same edition family.
class GameBoxRegionFamily {
  GameBoxRegionFamily._();

  static const _europe = {
    'eu', 'uk', 'fr', 'de', 'sp', 'it', 'nl', 'pt', 'se', 'dk', 'no', 'fi', 'ch', 'cz', 'hu', 'pl',
    'gr', 'be', 'at', 'ie', 'ru', 'tr', 'sk',
  };
  static const _oceania = {'au', 'nz'};
  static const _america = {'us', 'ca', 'mx', 'br', 'ame'};
  static const _asia = {'jp', 'kr', 'cn', 'tw', 'asi', 'hk'};

  static String of(String region) {
    if (_europe.contains(region)) return 'europe';
    if (_oceania.contains(region)) return 'oceania';
    if (_america.contains(region)) return 'america';
    if (_asia.contains(region)) return region; // each Asian edition is its own
    return region;
  }

  static bool same(String a, String b) => a == b || of(a) == of(b);
}

/// GameTDB vocabulary: languages of its art folders, ids and types.
class GameTdb {
  GameTdb._();

  static const String site = 'https://www.gametdb.com';
  static const String art = 'https://art.gametdb.com';

  /// GameTDB platform folder of a NeoStation system, when supported. GameTDB
  /// lists GameCube games with the Wii's (docs/game-box-3d.md § 25).
  static String? platformOf(String? systemId) => switch ((systemId ?? '').toLowerCase()) {
        'ps3' => 'ps3',
        'switch' => 'switch',
        'wii' || 'gc' || 'triforce' => 'wii',
        'wiiu' => 'wiiu',
        'ds' => 'ds',
        '3ds' => '3ds',
        _ => null,
      };

  /// Page path of a platform (`PS3`, `Switch`, `Wii`, `WiiU`, `DS`, `3DS`).
  static String pagePlatform(String platform) => switch (platform) {
        'ps3' => 'PS3',
        'switch' => 'Switch',
        'wii' => 'Wii',
        'wiiu' => 'WiiU',
        'ds' => 'DS',
        '3ds' => '3DS',
        final other => other,
      };

  /// Name of a platform's title list (`switchtdb.txt`, `wiitdb.txt`…).
  static String titlesFile(String platform) => '${platform}tdb.txt';

  /// Whether [id] has the form of a GameTDB id listed for [platform].
  static bool isListedId(String platform, String id) => switch (platform) {
        'switch' => switchId.hasMatch(id),
        'wii' || 'wiiu' => nintendoDiscId.hasMatch(id),
        'ds' || '3ds' => nintendoCardId.hasMatch(id),
        'ps3' => ps3Id.hasMatch(id),
        _ => false,
      };

  /// A Wii, GameCube or Wii U id (`RSBP01`, `AMKP01`).
  static final RegExp nintendoDiscId = RegExp(r'^[A-Z0-9]{6}$');

  /// A DS or 3DS game code (`AMCP`, `AMKP`).
  static final RegExp nintendoCardId = RegExp(r'^[A-Z0-9]{4}$');

  /// A PS3 serial as RPCS3 reports it (`BLES00510`, `NPUB30899`).
  static final RegExp ps3Id = RegExp(r'^[A-Z]{4}[0-9]{5}$');

  /// A Switch product code core (`AUZPA`).
  static final RegExp switchId = RegExp(r'^[A-Z0-9]{5}$');

  /// ScreenScraper region of a GameTDB art language.
  static String regionOf(String lang) => switch (lang.toUpperCase()) {
        'EN' => 'uk',
        'US' => 'us',
        'FR' => 'fr',
        'DE' => 'de',
        'ES' => 'sp',
        'IT' => 'it',
        'NL' => 'nl',
        'PT' => 'pt',
        'RU' => 'ru',
        'JA' => 'jp',
        'KO' => 'kr',
        'ZH' => 'cn',
        'AU' => 'au',
        'NZ' => 'nz',
        'CA' => 'ca',
        'MX' => 'mx',
        'CH' => 'ch',
        'SE' => 'se',
        'DK' => 'dk',
        'NO' => 'no',
        'FI' => 'fi',
        'CZ' => 'cz',
        'HU' => 'hu',
        'PL' => 'pl',
        final other => other.toLowerCase(),
      };

  /// Region of a PS3 serial: its third letter (E Europe, U America, J Japan,
  /// A Asia, K Korea, H Hong Kong).
  static List<String> regionsOfPs3Serial(String serial) {
    if (!ps3Id.hasMatch(serial)) return const [];
    return switch (serial[2]) {
      'E' => const ['eu'],
      'U' => const ['us'],
      'J' => const ['jp'],
      'A' => const ['asi'],
      'K' => const ['kr'],
      'H' => const ['asi'],
      _ => const [],
    };
  }

  static final RegExp _artUrl =
      RegExp(r'https://art\.gametdb\.com/(ps3|switch|wii|wiiu|ds|3ds)/([A-Za-z]+)/([A-Z]{2,4})/([A-Z0-9]+)\.(jpg|png)');
  static final RegExp _caseColor =
      RegExp(r">case\s*</td>\s*<td[^>]*>\s*<table[^>]*bgcolor='#([0-9a-fA-F]{6})'", multiLine: true);

  /// Candidates listed on a GameTDB game page ([html]) for [id], and the case
  /// colour the page shows, if any. 3D renders (`box`), cartridge photos and
  /// other games' thumbnails are left out.
  static ({List<GameBoxCandidate> candidates, String? caseColor}) parsePage(String html, String id) {
    final seen = <String>{};
    final out = <GameBoxCandidate>[];
    for (final m in _artUrl.allMatches(html)) {
      final platform = m.group(1)!;
      final type = m.group(2)!;
      final lang = m.group(3)!;
      final gameId = m.group(4)!;
      final ext = m.group(5)!;
      if (gameId != id) continue;
      final key = '$platform/$type/$lang/$gameId.$ext';
      if (!seen.add(key)) continue;
      final c = _candidate(platform, type, lang, gameId, ext);
      if (c != null) out.add(c);
    }
    final color = _caseColor.firstMatch(html)?.group(1)?.toLowerCase();
    return (candidates: out, caseColor: color);
  }

  static GameBoxCandidate? _candidate(String platform, String type, String lang, String id, String ext) {
    final alternate = type.endsWith('B') && type != 'B';
    final base = alternate ? type.substring(0, type.length - 1) : type;
    final quality = base.endsWith('HQ')
        ? 3
        : base.endsWith('M')
            ? 2
            : 1;
    final family = base.replaceAll(RegExp(r'(HQ|M)$'), '');
    final GameBoxMediaKind kind;
    var nature = GameBoxArtNature.scan;
    switch (family) {
      case 'cover':
        kind = GameBoxMediaKind.front;
      case 'back':
        kind = GameBoxMediaKind.back;
      case 'coverfull':
        kind = GameBoxMediaKind.full;
        nature = GameBoxArtNature.wrap;
      case 'disc':
        kind = GameBoxMediaKind.support;
      case 'label':
        kind = GameBoxMediaKind.support;
      default:
        // `box` (a 3D render), `cart` (a photo), `latest`…: never a face.
        return null;
    }
    final (w, h) = templateSize(platform, family, quality);
    return GameBoxCandidate(
      provider: GameBoxProvider.gametdb,
      kind: kind,
      type: 'gametdb:$type',
      identity: 'gametdb:$platform/$type/$lang/$id',
      nature: nature,
      region: regionOf(lang),
      edition: alternate ? 'B' : null,
      productId: id,
      url: '$art/$platform/$type/$lang/$id.$ext',
      width: w,
      height: h,
      quality: quality,
      format: ext,
      byProduct: true,
    );
  }

  /// Sizes of GameTDB's normalised templates, measured on downloads
  /// (1 Nov 2026); null where not measured.
  static (int?, int?) templateSize(String platform, String family, int quality) {
    if (platform == 'switch') {
      return switch ((family, quality)) {
        ('cover' || 'back', 3) => (1166, 1888),
        ('cover' || 'back', 2) => (352, 570),
        ('cover' || 'back', 1) => (160, 260),
        ('coverfull', 3) => (2454, 1888),
        ('coverfull', 1) => (340, 262),
        _ => (null, null),
      };
    }
    if (platform == 'ps3') {
      return switch ((family, quality)) {
        ('cover' || 'back', 3) => (928, 1080),
        ('cover' || 'back', 2) => (350, 408),
        ('cover' || 'back', 1) => (160, 184),
        ('coverfull', 3) => (2000, 1080),
        _ => (null, null),
      };
    }
    // Measured on downloads, 2 Nov 2026 (§ 25).
    if (platform == 'wii') {
      return switch ((family, quality)) {
        ('cover', 1) => (160, 224),
        ('coverfull', 3) => (1024, 680),
        ('coverfull', 1) => (512, 340),
        _ => (null, null),
      };
    }
    if (platform == 'wiiu') {
      return switch ((family, quality)) {
        ('cover' || 'back', 3) => (768, 1080),
        ('cover' || 'back', 2) => (350, 500),
        ('cover' || 'back', 1) => (160, 224),
        ('coverfull', 3) => (1632, 1080),
        ('coverfull', 2) => (752, 500),
        ('coverfull', 1) => (340, 224),
        _ => (null, null),
      };
    }
    if (platform == 'ds' || platform == '3ds') {
      return switch ((family, quality)) {
        ('cover' || 'back', 3) => (768, 680),
        ('cover' || 'back', 2) => (400, 352),
        ('cover' || 'back', 1) => (160, 144),
        ('coverfull', 3) => (1616, 680),
        ('coverfull', 2) => (856, 352),
        ('coverfull', 1) => (340, 144),
        _ => (null, null),
      };
    }
    return (null, null);
  }

  /// Product codes listed in a GameTDB title list (`ID = Title`) of
  /// [platform] whose title is exactly [title] once case, accents,
  /// punctuation and trademark signs are ignored. Several codes can share a
  /// title (regional prints).
  static List<String> idsForTitle(String titlesTxt, String title, {String platform = 'switch'}) {
    final wanted = normalizeTitle(title);
    if (wanted.isEmpty) return const [];
    final ids = <String>[];
    for (final line in titlesTxt.split('\n')) {
      final eq = line.indexOf(' = ');
      if (eq <= 0) continue;
      final id = line.substring(0, eq).trim();
      if (!isListedId(platform, id)) continue;
      if (normalizeTitle(line.substring(eq + 3)) == wanted) ids.add(id);
    }
    return ids;
  }

  /// Ids of a title list that begin with [prefix] (a Wii U disc gives its
  /// 4-character product code; GameTDB lists it with its company code).
  static List<String> idsWithPrefix(String titlesTxt, String prefix, {required String platform}) {
    final ids = <String>[];
    for (final line in titlesTxt.split('\n')) {
      final eq = line.indexOf(' = ');
      if (eq <= 0) continue;
      final id = line.substring(0, eq).trim();
      if (id.startsWith(prefix) && isListedId(platform, id)) ids.add(id);
    }
    return ids;
  }

  /// Title reduced for exact comparison.
  static String normalizeTitle(String title) {
    var t = title.toLowerCase();
    // Bracketed tags of file names and NeoStation titles: [0100…][v0], (USA).
    t = t.replaceAll(RegExp(r'\[[^\]]*\]|\([^)]*\)'), ' ');
    const accents = {
      'à': 'a', 'á': 'a', 'â': 'a', 'ä': 'a', 'ã': 'a', 'å': 'a', 'ç': 'c', 'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
      'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i', 'ñ': 'n', 'ò': 'o', 'ó': 'o', 'ô': 'o', 'ö': 'o', 'õ': 'o', 'ù': 'u',
      'ú': 'u', 'û': 'u', 'ü': 'u', 'ý': 'y', 'ÿ': 'y', 'œ': 'oe', 'æ': 'ae',
    };
    final b = StringBuffer();
    for (final ch in t.split('')) {
      b.write(accents[ch] ?? ch);
    }
    t = b.toString().replaceAll('&', ' and ').replaceAll(RegExp(r'[™®©]'), '');
    t = t.replaceAll(RegExp(r'[^a-z0-9+]+'), ' ').trim();
    return t.replaceAll(RegExp(r'\s+'), ' ');
  }
}

/// MobyGames API v1 (optional provider, the player's own key; one request
/// per second at most).
class MobyGames {
  MobyGames._();

  static const String api = 'https://api.mobygames.com/v1';

  /// Minimum delay between two requests.
  static const Duration interval = Duration(milliseconds: 1100);

  /// Platform names as MobyGames lists them (`/platforms`), by system id.
  static String? platformNameOf(String? systemId) => switch ((systemId ?? '').toLowerCase()) {
        'ps3' => 'PlayStation 3',
        'switch' => 'Nintendo Switch',
        '3ds' => 'Nintendo 3DS',
        'ds' => 'Nintendo DS',
        'gbc' => 'Game Boy Color',
        'gb' => 'Game Boy',
        'gba' => 'Game Boy Advance',
        'ps2' => 'PlayStation 2',
        'ps1' => 'PlayStation',
        'psp' => 'PSP',
        'vita' => 'PS Vita',
        'wii' => 'Wii',
        'wiiu' => 'Wii U',
        'gc' => 'GameCube',
        'n64' => 'Nintendo 64',
        'snes' => 'SNES',
        'nes' => 'NES',
        'md' || 'genesis' => 'Genesis',
        'sat' => 'SEGA Saturn',
        'dc' => 'Dreamcast',
        _ => null,
      };

  /// Faces of the box in MobyGames' `scan_of` vocabulary.
  static GameBoxMediaKind? kindOfScan(String scanOf) => switch (scanOf.trim().toLowerCase()) {
        'front cover' => GameBoxMediaKind.front,
        'back cover' => GameBoxMediaKind.back,
        'spine/sides' || 'spine' => GameBoxMediaKind.spine,
        'media' => GameBoxMediaKind.support,
        _ => null,
      };

  /// ScreenScraper region of a MobyGames country name.
  static String regionOfCountry(String country) => switch (country.trim().toLowerCase()) {
        'united states' => 'us',
        'canada' => 'ca',
        'united kingdom' => 'uk',
        'france' => 'fr',
        'germany' => 'de',
        'spain' => 'sp',
        'italy' => 'it',
        'netherlands' => 'nl',
        'portugal' => 'pt',
        'russia' => 'ru',
        'japan' => 'jp',
        'south korea' => 'kr',
        'china' => 'cn',
        'taiwan' => 'tw',
        'australia' => 'au',
        'new zealand' => 'nz',
        'brazil' => 'br',
        'sweden' => 'se',
        'worldwide' => 'wor',
        _ => 'eu',
      };

  /// Candidates of a `/games/{id}/platforms/{pid}/covers` answer.
  static List<GameBoxCandidate> parseCovers(Map<String, dynamic> json, {required String gameId}) {
    final out = <GameBoxCandidate>[];
    final groups = json['cover_groups'];
    if (groups is! List) return out;
    for (var g = 0; g < groups.length; g++) {
      final group = groups[g];
      if (group is! Map) continue;
      final rawCountries = group['countries'];
      final countries = rawCountries is List
          ? [for (final c in rawCountries) c.toString()]
          : (rawCountries?.toString() ?? '').split(',').map((s) => s.trim()).where((s) => s.isNotEmpty).toList();
      final region = countries.isEmpty ? 'wor' : regionOfCountry(countries.first);
      final comments = group['comments']?.toString().trim();
      final covers = group['covers'];
      if (covers is! List) continue;
      for (final cover in covers) {
        if (cover is! Map) continue;
        final kind = kindOfScan(cover['scan_of']?.toString() ?? '');
        final image = cover['image']?.toString() ?? '';
        if (kind == null || !image.startsWith('https://')) continue;
        final w = int.tryParse(cover['width']?.toString() ?? '');
        final h = int.tryParse(cover['height']?.toString() ?? '');
        out.add(GameBoxCandidate(
          provider: GameBoxProvider.mobygames,
          kind: kind,
          type: 'mobygames:${cover['scan_of']}',
          identity: 'mobygames:${Uri.tryParse(image)?.path ?? image}',
          region: region,
          edition: (comments == null || comments.isEmpty) ? null : comments,
          productId: 'moby:$gameId/$g',
          url: image,
          width: w,
          height: h,
          quality: (w ?? 0) >= 1000 ? 3 : 2,
          format: image.toLowerCase().endsWith('.png') ? 'png' : 'jpg',
        ));
      }
    }
    return out;
  }
}

/// ScreenScraper candidates and full-size addresses.
class ScreenScraperBoxSource {
  ScreenScraperBoxSource._();

  /// Media types of the box read from `jeuInfos.php` (docs/game-box-3d.md
  /// § 14).
  static const types = {'box-2D', 'box-2D-back', 'box-2D-side', 'support-2D', 'box-texture'};

  /// The address of a scan without `maxwidth` / `maxheight`: a thumbnail size
  /// set elsewhere never limits a scan meant to be read.
  static String fullSize(String url) {
    final uri = Uri.tryParse(url);
    if (uri == null || uri.queryParameters.isEmpty) return url;
    final params = Map<String, String>.from(uri.queryParameters)
      ..remove('maxwidth')
      ..remove('maxheight');
    return uri.replace(queryParameters: params).toString();
  }

  /// Candidate of one `jeuInfos.php` media entry ([entry] already parsed).
  static GameBoxCandidate candidate(GameBoxMediaEntry entry, String url, {required bool byProduct, String? gameId}) {
    final nature = entry.kind == GameBoxMediaKind.full ? GameBoxArtNature.wrap : GameBoxArtNature.scan;
    return GameBoxCandidate(
      provider: GameBoxProvider.screenscraper,
      kind: entry.kind,
      type: 'screenscraper:${entry.kind.screenScraperType}',
      identity: 'screenscraper:${entry.identity}',
      nature: nature,
      region: entry.region,
      productId: gameId == null ? null : 'ss:$gameId',
      url: fullSize(url),
      quality: 2,
      format: entry.format,
      byProduct: byProduct,
      bytes: entry.size,
    );
  }
}
