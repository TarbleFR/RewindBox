/// BIOS and system files the embedded libretro cores read, as recorded in
/// `assets/data/libretro_bios_requirements.json` (libretro core-info,
/// System.dat, the libretro documentation and the core sources; the JSON
/// keeps the references). The same file is read by
/// `test/libretro_bios_requirements_test.py`, which checks it against the
/// pinned `.info` data and, on CI, against the pinned core binaries.
///
/// The catalog only describes files: the checker
/// (`libretro_bios_check_service.dart`) compares it with what is on disk.
library;

import 'dart:convert';

import 'package:flutter/services.dart' show AssetBundle, rootBundle;

/// How a core needs a file.
enum LibretroBiosLevel {
  /// Needed for every game of the console (the NeoStation PS1 launch rule).
  required,

  /// Needed only for some games (Mega-CD discs, FDS, Satellaview, Neo Geo...).
  conditional,

  /// Never needed; the core has a built-in replacement or an option uses it.
  optional,

  /// Supplied by NeoStation itself (the PPSSPP support files).
  bundled,
}

/// Where a core looks for a file, relative to the libretro System folder or
/// in the folder of the game being launched.
class LibretroBiosLocation {
  const LibretroBiosLocation._(this.raw, this.subdirectory, this.gameFolder);

  /// `system`, `system/<sub>[/<sub>]` or `gameFolder`.
  factory LibretroBiosLocation.parse(String raw) {
    if (raw == 'gameFolder') return LibretroBiosLocation._(raw, const <String>[], true);
    if (raw == 'system') return LibretroBiosLocation._(raw, const <String>[], false);
    if (raw.startsWith('system/')) {
      final parts = raw.substring('system/'.length).split('/').where((part) => part.isNotEmpty).toList();
      if (parts.isNotEmpty) return LibretroBiosLocation._(raw, List<String>.unmodifiable(parts), false);
    }
    throw FormatException('Unknown BIOS location $raw');
  }

  final String raw;

  /// Folders below System, with their exact case (iOS file systems are case
  /// sensitive).
  final List<String> subdirectory;
  final bool gameFolder;

  @override
  bool operator ==(Object other) => other is LibretroBiosLocation && other.raw == raw;

  @override
  int get hashCode => raw.hashCode;

  @override
  String toString() => raw;
}

/// A published dump of a file: size and checksums (System.dat, core-info
/// notes or the core documentation). Hex strings are lowercase.
class LibretroBiosDump {
  const LibretroBiosDump({
    required this.size,
    this.crc,
    this.md5,
    this.sha1,
    required this.label,
    required this.source,
  });

  factory LibretroBiosDump.fromJson(Map<String, dynamic> json) => LibretroBiosDump(
        size: json['size'] as int,
        crc: (json['crc'] as String?)?.toLowerCase(),
        md5: (json['md5'] as String?)?.toLowerCase(),
        sha1: (json['sha1'] as String?)?.toLowerCase(),
        label: json['label'] as String,
        source: json['source'] as String,
      );

  final int size;
  final String? crc;
  final String? md5;
  final String? sha1;

  /// Technical name of the dump, shown untranslated in the details.
  final String label;
  final String source;

  /// Same size and the same MD5 or SHA-1.
  bool matches({required int size, String? md5, String? sha1}) {
    if (size != this.size) return false;
    if (this.md5 != null && md5 != null && this.md5 == md5) return true;
    if (this.sha1 != null && sha1 != null && this.sha1 == sha1) return true;
    return false;
  }

  /// Same size and CRC-32 (a member of a ZIP archive, read without
  /// decompressing it).
  bool matchesCrc({required int size, required int crc}) =>
      this.crc != null && size == this.size && int.parse(this.crc!, radix: 16) == crc;
}

/// Games of the library that need a conditional file: games of one of
/// [systems] (NeoStation system keys), and with one of [extensions] when
/// the list is not empty.
class LibretroBiosGameClause {
  const LibretroBiosGameClause({required this.systems, this.extensions = const <String>{}});

  factory LibretroBiosGameClause.fromJson(Map<String, dynamic> json) => LibretroBiosGameClause(
        systems: _strings(json['systems']).map((system) => system.toLowerCase()).toSet(),
        extensions: _strings(json['extensions']).map((extension) => extension.toLowerCase()).toSet(),
      );

  final Set<String> systems;
  final Set<String> extensions;
}

class LibretroBiosCondition {
  const LibretroBiosCondition({
    required this.key,
    this.arguments = const <String, String>{},
    this.games = const <LibretroBiosGameClause>[],
  });

  factory LibretroBiosCondition.fromJson(Map<String, dynamic> json) => LibretroBiosCondition(
        key: json['key'] as String,
        arguments: <String, String>{
          for (final entry in ((json['args'] as Map?) ?? const <String, Object?>{}).entries)
            entry.key.toString(): entry.value.toString(),
        },
        games: <LibretroBiosGameClause>[
          for (final clause in (json['games'] as List?) ?? const <Object?>[])
            LibretroBiosGameClause.fromJson((clause as Map).cast<String, dynamic>()),
        ],
      );

  /// LibretroLocale key naming the games that need the file.
  final String key;

  /// Placeholders of [key] (product names, never translated).
  final Map<String, String> arguments;

  /// Empty when the library cannot tell (arcade boards): the file then stays
  /// optional, with the condition shown.
  final List<LibretroBiosGameClause> games;
}

/// One core option value test: the first of [keys] found in the stored core
/// options (`Config/*.json`), else [defaultValue], must be one of [enabled].
class LibretroBiosOptionCondition {
  const LibretroBiosOptionCondition({
    required this.keys,
    required this.enabled,
    required this.defaultValue,
  });

  factory LibretroBiosOptionCondition.fromJson(Map<String, dynamic> json) => LibretroBiosOptionCondition(
        keys: _strings(json['keys']),
        enabled: _strings(json['enabled']).toSet(),
        defaultValue: json['default'] as String,
      );

  final List<String> keys;
  final Set<String> enabled;
  final String defaultValue;

  bool isOn(Map<String, String> options) {
    for (final key in keys) {
      final value = options[key];
      if (value != null) return enabled.contains(value);
    }
    return enabled.contains(defaultValue);
  }
}

/// A core reads the file only when every condition of [all] holds.
class LibretroBiosOptionGate {
  const LibretroBiosOptionGate({required this.core, required this.all});

  factory LibretroBiosOptionGate.fromJson(Map<String, dynamic> json) => LibretroBiosOptionGate(
        core: json['core'] as String,
        all: <LibretroBiosOptionCondition>[
          for (final condition in json['all'] as List)
            LibretroBiosOptionCondition.fromJson((condition as Map).cast<String, dynamic>()),
        ],
      );

  final String core;
  final List<LibretroBiosOptionCondition> all;

  bool isOn(Map<String, String> options) => all.every((condition) => condition.isOn(options));

  /// First condition that does not hold, null when the gate is open.
  LibretroBiosOptionCondition? firstOff(Map<String, String> options) {
    for (final condition in all) {
      if (!condition.isOn(options)) return condition;
    }
    return null;
  }
}

/// A member a ZIP set must contain, identified by CRC-32 as FBNeo finds it.
class LibretroBiosZipMember {
  const LibretroBiosZipMember({required this.name, required this.crc});

  factory LibretroBiosZipMember.fromJson(Map<String, dynamic> json) => LibretroBiosZipMember(
        name: json['name'] as String,
        crc: int.parse(json['crc'] as String, radix: 16),
      );

  final String name;
  final int crc;
}

/// A check that proves a file unusable when it fails. Only checks the core
/// sources establish are listed: anything else stays "present, not
/// verified".
sealed class LibretroBiosValidator {
  const LibretroBiosValidator();

  factory LibretroBiosValidator.fromJson(Map<String, dynamic> json) {
    switch (json['type']) {
      case 'minSize':
        return LibretroBiosMinSize(json['size'] as int);
      case 'header':
        return LibretroBiosHeader(json['offset'] as int, json['ascii'] as String);
      case 'firstWordIn':
        return LibretroBiosFirstWord(<int>{
          for (final value in json['values'] as List) int.parse(value as String, radix: 16),
        });
      case 'zipMembers':
        return LibretroBiosZipMembers(
          essential: <LibretroBiosZipMember>[
            for (final member in (json['essential'] as List?) ?? const <Object?>[])
              LibretroBiosZipMember.fromJson((member as Map).cast<String, dynamic>()),
          ],
          recommended: <LibretroBiosZipMember>[
            for (final member in (json['recommended'] as List?) ?? const <Object?>[])
              LibretroBiosZipMember.fromJson((member as Map).cast<String, dynamic>()),
          ],
        );
    }
    throw FormatException('Unknown BIOS validator ${json['type']}');
  }

  /// Bytes of the file start the validator reads (0 when none).
  int get headBytes => 0;
}

/// The core reads exactly [size] bytes and rejects a shorter file.
class LibretroBiosMinSize extends LibretroBiosValidator {
  const LibretroBiosMinSize(this.size);
  final int size;
}

/// The core rejects the file unless [ascii] is at [offset].
class LibretroBiosHeader extends LibretroBiosValidator {
  const LibretroBiosHeader(this.offset, this.ascii);
  final int offset;
  final String ascii;

  @override
  int get headBytes => offset + ascii.length;
}

/// The core rejects the file unless its first big-endian word is one of
/// [values] (the byte orders of the 64DD IPL).
class LibretroBiosFirstWord extends LibretroBiosValidator {
  const LibretroBiosFirstWord(this.values);
  final Set<int> values;

  @override
  int get headBytes => 4;
}

/// ZIP set whose [essential] members (by CRC) the core cannot do without;
/// [recommended] members are used by default but have alternatives.
class LibretroBiosZipMembers extends LibretroBiosValidator {
  const LibretroBiosZipMembers({required this.essential, required this.recommended});
  final List<LibretroBiosZipMember> essential;
  final List<LibretroBiosZipMember> recommended;
}

class LibretroBiosEntry {
  const LibretroBiosEntry({
    required this.id,
    required this.consoles,
    required this.cores,
    required this.names,
    this.coreNames = const <String, List<String>>{},
    required this.locations,
    this.lookupAll = false,
    this.crcIgnoredLocations = const <LibretroBiosLocation>{},
    this.gameFolderSystems = const <String>{},
    required this.level,
    this.gate,
    this.group,
    this.region,
    this.regional = false,
    this.condition,
    this.optionGates = const <LibretroBiosOptionGate>[],
    this.knownDumps = const <LibretroBiosDump>[],
    this.hashVaries = false,
    this.perConsoleDump = false,
    this.validators = const <LibretroBiosValidator>[],
    this.psxChecksumScan = false,
    this.bundledPath,
    this.bundledRequired = false,
    this.noteKeys = const <String>[],
    this.binaryStrings = const <String, List<String>>{},
    this.sources = const <String>[],
  });

  factory LibretroBiosEntry.fromJson(Map<String, dynamic> json) {
    final level = LibretroBiosLevel.values.byName(json['level'] as String);
    final condition = json['condition'] == null
        ? null
        : LibretroBiosCondition.fromJson((json['condition'] as Map).cast<String, dynamic>());
    if (level == LibretroBiosLevel.conditional && condition == null) {
      throw FormatException('${json['id']}: a conditional file needs its condition');
    }
    return LibretroBiosEntry(
      id: json['id'] as String,
      consoles: _strings(json['consoles']),
      cores: _strings(json['cores']),
      names: _strings(json['names']),
      coreNames: <String, List<String>>{
        for (final entry in ((json['coreNames'] as Map?) ?? const <String, Object?>{}).entries)
          entry.key.toString(): _strings(entry.value),
      },
      locations: _strings(json['locations']).map(LibretroBiosLocation.parse).toList(growable: false),
      lookupAll: json['lookup'] == 'all',
      crcIgnoredLocations: _strings(json['crcIgnoredLocations']).map(LibretroBiosLocation.parse).toSet(),
      gameFolderSystems: _strings(json['gameFolderSystems']).map((system) => system.toLowerCase()).toSet(),
      level: level,
      gate: json['gate'] as String?,
      group: json['group'] as String?,
      region: json['region'] as String?,
      regional: json['regional'] == true,
      condition: condition,
      optionGates: <LibretroBiosOptionGate>[
        for (final gate in (json['optionGates'] as List?) ?? const <Object?>[])
          LibretroBiosOptionGate.fromJson((gate as Map).cast<String, dynamic>()),
      ],
      knownDumps: <LibretroBiosDump>[
        for (final dump in (json['knownDumps'] as List?) ?? const <Object?>[])
          LibretroBiosDump.fromJson((dump as Map).cast<String, dynamic>()),
      ],
      hashVaries: json['hashVaries'] == true,
      perConsoleDump: json['perConsoleDump'] == true,
      validators: <LibretroBiosValidator>[
        for (final validator in (json['validators'] as List?) ?? const <Object?>[])
          LibretroBiosValidator.fromJson((validator as Map).cast<String, dynamic>()),
      ],
      psxChecksumScan: json['psxChecksumScan'] == true,
      bundledPath: json['bundledPath'] as String?,
      bundledRequired: json['bundledRequired'] == true,
      noteKeys: _strings(json['noteKeys']),
      binaryStrings: <String, List<String>>{
        for (final entry in ((json['binaryStrings'] as Map?) ?? const <String, Object?>{}).entries)
          entry.key.toString(): _strings(entry.value),
      },
      sources: _strings(json['sources']),
    );
  }

  final String id;

  /// Keys of `LibretroCoreCatalog.consoles` the file belongs to.
  final List<String> consoles;

  /// Cores that read the file (ids of `LibretroCoreCatalog.cores`).
  final List<String> cores;

  /// Exact names, in the order the cores try them (case variants included).
  final List<String> names;

  /// Names only some cores read (PicoDrive's Mega-CD names), in their order.
  final Map<String, List<String>> coreNames;

  /// Where the cores look, in their order.
  final List<LibretroBiosLocation> locations;

  /// The core collects every copy it finds (FBNeo) instead of using the
  /// first one.
  final bool lookupAll;

  /// Locations whose copies the core uses without checking member CRCs
  /// (FBNeo's patched romsets).
  final Set<LibretroBiosLocation> crcIgnoredLocations;

  /// Systems whose game folders are a location of the file.
  final Set<String> gameFolderSystems;
  final LibretroBiosLevel level;

  /// NeoStation's own launch rule this file takes part in (`psx`: the names
  /// of `LibretroCore.biosAnyOf`).
  final String? gate;

  /// Files that replace one another (one region each).
  final String? group;

  /// `na`, `eu`, `jp` or `world`.
  final String? region;

  /// Needed only for games of [region]; games are matched by their region
  /// tags.
  final bool regional;
  final LibretroBiosCondition? condition;
  final List<LibretroBiosOptionGate> optionGates;
  final List<LibretroBiosDump> knownDumps;

  /// Several valid versions exist: an unknown checksum is expected.
  final bool hashVaries;

  /// Each console has its own copy (DS firmware): never verifiable.
  final bool perConsoleDump;
  final List<LibretroBiosValidator> validators;

  /// Beetle PSX also finds the file by its SHA-1 among the 512 KiB and
  /// 1 MiB files of the System root.
  final bool psxChecksumScan;

  /// Path below `Runner.app/LibretroSystem` of the copy NeoStation ships.
  final String? bundledPath;

  /// A bundled file the core cannot run without.
  final bool bundledRequired;
  final List<String> noteKeys;

  /// Strings each pinned core binary must contain (checked on CI).
  final Map<String, List<String>> binaryStrings;
  final List<String> sources;

  /// Every name a core of [availableCores] reads, default names first.
  List<String> allNames([Set<String>? availableCores]) => <String>{
        ...names,
        for (final entry in coreNames.entries)
          if (availableCores == null || availableCores.contains(entry.key)) ...entry.value,
      }.toList(growable: false);

  /// Bytes of the file start the validators read.
  int get headBytes => validators.fold(0, (bytes, validator) => validator.headBytes > bytes ? validator.headBytes : bytes);
}

/// Per-console texts (LibretroLocale keys).
class LibretroBiosConsoleInfo {
  const LibretroBiosConsoleInfo({this.noteKeys = const <String>[]});

  factory LibretroBiosConsoleInfo.fromJson(Map<String, dynamic> json) =>
      LibretroBiosConsoleInfo(noteKeys: _strings(json['noteKeys']));

  final List<String> noteKeys;
}

/// A firmware line of a core's `.info` that NeoStation deliberately does not
/// check, with the reason.
class LibretroBiosExclusion {
  const LibretroBiosExclusion({required this.core, required this.path, required this.reason});

  factory LibretroBiosExclusion.fromJson(Map<String, dynamic> json) => LibretroBiosExclusion(
        core: json['core'] as String,
        path: json['path'] as String,
        reason: json['reason'] as String,
      );

  final String core;
  final String path;
  final String reason;
}

class LibretroBiosCatalog {
  const LibretroBiosCatalog({
    required this.schema,
    required this.openBiosFallback,
    required this.regionTags,
    required this.consoles,
    required this.entries,
    this.excluded = const <LibretroBiosExclusion>[],
  });

  factory LibretroBiosCatalog.parse(String source) {
    final json = (jsonDecode(source) as Map).cast<String, dynamic>();
    final schema = json['schema'] as int;
    if (schema != 1) throw FormatException('Unsupported BIOS catalog schema $schema');
    final flags = ((json['flags'] as Map?) ?? const <String, Object?>{}).cast<String, dynamic>();
    final entries = <LibretroBiosEntry>[
      for (final entry in json['entries'] as List) LibretroBiosEntry.fromJson((entry as Map).cast<String, dynamic>()),
    ];
    final ids = <String>{};
    for (final entry in entries) {
      if (!ids.add(entry.id)) throw FormatException('Duplicate BIOS entry ${entry.id}');
    }
    return LibretroBiosCatalog(
      schema: schema,
      openBiosFallback: flags['beetleOpenBiosFallback'] == true,
      regionTags: <String, Set<String>>{
        for (final entry in ((json['regionTags'] as Map?) ?? const <String, Object?>{}).entries)
          entry.key.toString(): _strings(entry.value).map((tag) => tag.toLowerCase()).toSet(),
      },
      consoles: <String, LibretroBiosConsoleInfo>{
        for (final entry in ((json['consoles'] as Map?) ?? const <String, Object?>{}).entries)
          entry.key.toString(): LibretroBiosConsoleInfo.fromJson((entry.value as Map).cast<String, dynamic>()),
      },
      entries: List<LibretroBiosEntry>.unmodifiable(entries),
      excluded: <LibretroBiosExclusion>[
        for (final exclusion in (json['excluded'] as List?) ?? const <Object?>[])
          LibretroBiosExclusion.fromJson((exclusion as Map).cast<String, dynamic>()),
      ],
    );
  }

  static const String assetPath = 'assets/data/libretro_bios_requirements.json';

  /// The catalog shipped with the app.
  static Future<LibretroBiosCatalog> load({AssetBundle? bundle}) async =>
      LibretroBiosCatalog.parse(await (bundle ?? rootBundle).loadString(assetPath));

  final int schema;

  /// The pinned Beetle PSX cores start a disc with their built-in OpenBIOS
  /// when no BIOS of its region is found (confirmed on CI against the pinned
  /// binaries).
  final bool openBiosFallback;

  /// Lowercase tags of game file names (`(USA)`, `(Europe)`...) per region.
  final Map<String, Set<String>> regionTags;
  final Map<String, LibretroBiosConsoleInfo> consoles;
  final List<LibretroBiosEntry> entries;
  final List<LibretroBiosExclusion> excluded;

  List<LibretroBiosEntry> entriesFor(String console) =>
      entries.where((entry) => entry.consoles.contains(console)).toList(growable: false);

  /// Sizes of every known dump: only files of these sizes are hashed when
  /// looking for a file saved under another name or in another folder.
  Set<int> get knownSizes => <int>{
        for (final entry in entries)
          for (final dump in entry.knownDumps) dump.size,
      };

  /// Regions whose tags appear in a game file name (`Game (USA, Europe).cue`).
  Set<String> regionsOf(String fileName) {
    final tokens = <String>{};
    for (final match in RegExp(r'\(([^)]*)\)').allMatches(fileName)) {
      for (final token in match.group(1)!.split(',')) {
        final trimmed = token.trim().toLowerCase();
        if (trimmed.isNotEmpty) tokens.add(trimmed);
      }
    }
    return <String>{
      for (final entry in regionTags.entries)
        if (entry.value.any(tokens.contains)) entry.key,
    };
  }
}

List<String> _strings(Object? value) =>
    value is List ? value.map((item) => item.toString()).toList(growable: false) : const <String>[];
