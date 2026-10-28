/// Shared vocabulary of the Cheats & Enhancements catalogue.
///
/// Every engine adapter maps its native format (Atmosphere cheats, RPCS3
/// patch.yml, PCSX2 pnach, Dolphin GameSettings) onto these types so the
/// interface and the store never depend on one emulator.
library;

/// The tab an entry is listed under. It follows the author's own label and
/// never claims a measured effect.
enum EnhancementCategory {
  cheat,
  fps,
  ultrawide,
  graphics,
  textures,
  performance;

  static EnhancementCategory? parse(String? value) {
    for (final category in values) {
      if (category.name == value) return category;
    }
    return null;
  }
}

/// Embedded engines with a catalogue adapter. Libretro is listed for its
/// HD textures and its in-game cheat menu only.
enum EnhancementEngine { melonx, rpcs3, armsx2, dolphin, libretro }

/// Lifecycle of one entry for one game.
enum EnhancementStatus {
  /// In the catalogue; nothing written for this game yet.
  available,

  /// Its native files are written, but the engine will not apply it.
  installed,

  /// The engine applies it at the next start of the game.
  active,

  /// This game's edition, version or image cannot use it.
  incompatible,
}

/// Why an entry or a whole game cannot be offered.
enum EnhancementProblem {
  none,
  unsupportedSystem,
  identityUnavailable,
  imageFormat,
  versionUnknown,
  versionMismatch,
  revisionMismatch,
  userFilePresent,
  notInCatalogue,
}

/// One catalogue source with the attribution shown to the player.
class EnhancementSource {
  const EnhancementSource({
    required this.id,
    required this.name,
    required this.url,
    required this.license,
    required this.revision,
    required this.engines,
  });

  final String id;
  final String name;
  final String url;
  final String license;
  final String revision;
  final List<String> engines;

  factory EnhancementSource.fromJson(Map<String, dynamic> json) =>
      EnhancementSource(
        id: json['id']?.toString() ?? '',
        name: json['name']?.toString() ?? '',
        url: json['url']?.toString() ?? '',
        license: json['license']?.toString() ?? '',
        revision: json['revision']?.toString() ?? '',
        engines: [
          for (final engine in (json['engines'] as List? ?? const []))
            engine.toString(),
        ],
      );
}

/// The identity an engine matches enhancements against.
///
/// [key] is the catalogue key: a Switch Title ID, a PS3 or PS2 serial, or a
/// Dolphin game ID. [version] is the PS3 APP_VER or the Switch display
/// version; [crc] the PS2 boot ELF CRC; [revision] the disc revision.
class EnhancementGameIdentity {
  const EnhancementGameIdentity({
    required this.engine,
    required this.key,
    this.title = '',
    this.version,
    this.crc,
    this.revision,
    this.problem = EnhancementProblem.none,
    this.aliases = const [],
  });

  const EnhancementGameIdentity.unavailable(
    this.engine,
    this.problem, {
    this.title = '',
  }) : key = '',
       version = null,
       crc = null,
       revision = null,
       aliases = const [];

  final EnhancementEngine engine;
  final String key;
  final String title;
  final String? version;
  final String? crc;
  final int? revision;
  final EnhancementProblem problem;

  /// Other catalogue keys the engine may load for this game (a Switch
  /// collection's sub-programs), checked after [key].
  final List<String> aliases;

  bool get known => key.isNotEmpty && problem == EnhancementProblem.none;

  /// Key of this game in the enhancement state store.
  String get storeKey => '${engine.name}:$key${crc == null ? '' : '_$crc'}';

  Map<String, Object?> toJson() => {
    'engine': engine.name,
    'key': key,
    'title': title,
    if (version != null) 'version': version,
    if (crc != null) 'crc': crc,
    if (revision != null) 'revision': revision,
  };
}

/// One enhancement as the interface shows it for one game.
class EnhancementItem {
  const EnhancementItem({
    required this.id,
    required this.engine,
    required this.category,
    required this.name,
    required this.sourceId,
    required this.status,
    this.description = '',
    this.author = '',
    this.compatibility = '',
    this.version = '',
    this.exclusiveGroup = '',
    this.requiresRestart = true,
    this.problem = EnhancementProblem.none,
    this.payload = const {},
  });

  final String id;
  final EnhancementEngine engine;
  final EnhancementCategory category;
  final String name;
  final String sourceId;
  final EnhancementStatus status;
  final String description;
  final String author;

  /// Which identities the native engine matches (Build IDs, versions, CRC).
  final String compatibility;

  /// The entry's own version (patch version) or the catalogue revision.
  final String version;

  /// Entries sharing a non-empty group are mutually exclusive.
  final String exclusiveGroup;
  final bool requiresRestart;
  final EnhancementProblem problem;

  /// The catalogue record, read only by the adapter that produced it.
  final Map<String, dynamic> payload;

  bool get canActivate => status != EnhancementStatus.incompatible;

  EnhancementItem copyWith({
    EnhancementStatus? status,
    EnhancementProblem? problem,
  }) => EnhancementItem(
    id: id,
    engine: engine,
    category: category,
    name: name,
    sourceId: sourceId,
    status: status ?? this.status,
    description: description,
    author: author,
    compatibility: compatibility,
    version: version,
    exclusiveGroup: exclusiveGroup,
    requiresRestart: requiresRestart,
    problem: problem ?? this.problem,
    payload: payload,
  );
}

/// Every enhancement of one game, ready for the interface.
class EnhancementGameView {
  const EnhancementGameView({
    required this.identity,
    required this.items,
    required this.catalogueRevision,
    this.installed = false,
    this.downloaded = false,
    this.credits = const [],
  });

  final EnhancementGameIdentity identity;
  final List<EnhancementItem> items;
  final String catalogueRevision;

  /// Native files of this game are written by RewindBox.
  final bool installed;

  /// The catalogue shard of this game is cached locally.
  final bool downloaded;
  final List<String> credits;

  List<EnhancementItem> inCategory(EnhancementCategory category) =>
      items.where((item) => item.category == category).toList(growable: false);

  int countIn(EnhancementCategory category) =>
      items.where((item) => item.category == category).length;

  int get activeCount =>
      items.where((item) => item.status == EnhancementStatus.active).length;
}

/// Raised when an operation must not write anything.
class EnhancementException implements Exception {
  const EnhancementException(this.code, [this.detail = '']);

  final String code;
  final String detail;

  @override
  String toString() => 'EnhancementException($code${detail.isEmpty ? '' : ': $detail'})';
}
