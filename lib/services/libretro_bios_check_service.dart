import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;
import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../repositories/game_repository.dart';
import '../repositories/system_repository.dart';
import 'libretro_bios_catalog.dart';
import 'libretro_core_catalog.dart';
import 'libretro_internal_service.dart';
import 'logger_service.dart';

/// Result of one file of the BIOS checker.
enum LibretroBiosStatus {
  /// Size and checksum match a published dump (or, for an FBNeo set, every
  /// member the core uses matches by CRC).
  verified,

  /// The file is where the core reads it, but its checksum is not one of the
  /// references (another revision, a hacked or bad dump, a file of another
  /// region saved under this name).
  presentUnverified,

  /// Missing while the console or a game of the library needs it.
  missingRequired,

  /// Missing, and nothing needs it now.
  missingOptional,

  /// Present but provably unusable: empty, unreadable, shorter than what the
  /// core reads, wrong header, not a ZIP archive, essential members missing.
  invalid,
}

/// How much the file is needed now, for the level shown next to it.
enum LibretroBiosNeed {
  required,

  /// Needed by games of the library ([LibretroBiosEntryResult.condition]).
  requiredFor,

  /// The core runs without it, less faithfully (PS1 BIOS of a region whose
  /// discs start with OpenBIOS).
  recommended,

  /// Needed only by games the library does not hold (yet).
  onlyFor,
  optional,
  bundled,
}

/// A message of the checker: a LibretroLocale key and its placeholders
/// (paths, file names, option keys: technical values, never translated).
class LibretroBiosNote {
  const LibretroBiosNote(this.key, [this.arguments = const <String, String>{}]);

  final String key;
  final Map<String, String> arguments;

  @override
  bool operator ==(Object other) =>
      other is LibretroBiosNote &&
      other.key == key &&
      other.arguments.length == arguments.length &&
      other.arguments.entries.every((entry) => arguments[entry.key] == entry.value);

  @override
  int get hashCode => Object.hash(key, Object.hashAllUnordered(arguments.entries.map((e) => '${e.key}=${e.value}')));

  @override
  String toString() => '$key$arguments';
}

/// A member of a ZIP archive, from its central directory.
class LibretroBiosZipEntry {
  const LibretroBiosZipEntry(this.name, this.crc, this.size);

  final String name;
  final int crc;
  final int size;
}

/// What the checker knows about one file: checksums, the first bytes the
/// validators read and, for a ZIP archive, its members (read without
/// decompressing). Cached by size and modification time.
class LibretroBiosFileFacts {
  const LibretroBiosFileFacts({
    required this.size,
    required this.modifiedMs,
    this.md5,
    this.sha1,
    this.sha256,
    required this.head,
    this.zipMembers,
    this.zipMagic = false,
    this.unreadable = false,
    this.tooLarge = false,
  });

  factory LibretroBiosFileFacts.fromJson(Map<String, dynamic> json) => LibretroBiosFileFacts(
        size: json['size'] as int,
        modifiedMs: json['mtime'] as int,
        md5: json['md5'] as String?,
        sha1: json['sha1'] as String?,
        sha256: json['sha256'] as String?,
        head: base64Decode(json['head'] as String? ?? ''),
        zipMembers: json['zip'] == null
            ? null
            : <LibretroBiosZipEntry>[
                for (final member in json['zip'] as List)
                  LibretroBiosZipEntry(member[0] as String, member[1] as int, member[2] as int),
              ],
        zipMagic: json['magic'] == true,
        unreadable: json['unreadable'] == true,
        tooLarge: json['large'] == true,
      );

  /// Size of the bytes read (the stat size when the file was not read).
  final int size;
  final int modifiedMs;
  final String? md5;
  final String? sha1;
  final String? sha256;
  final Uint8List head;
  final List<LibretroBiosZipEntry>? zipMembers;

  /// The file starts with a ZIP signature.
  final bool zipMagic;
  final bool unreadable;

  /// Over [LibretroBiosCheckService.maxHashedBytes]: not hashed.
  final bool tooLarge;

  Map<String, Object?> toJson() => <String, Object?>{
        'size': size,
        'mtime': modifiedMs,
        if (md5 != null) 'md5': md5,
        if (sha1 != null) 'sha1': sha1,
        if (sha256 != null) 'sha256': sha256,
        'head': base64Encode(head),
        if (zipMembers != null)
          'zip': <List<Object>>[
            for (final member in zipMembers!) <Object>[member.name, member.crc, member.size],
          ],
        if (zipMagic) 'magic': true,
        if (unreadable) 'unreadable': true,
        if (tooLarge) 'large': true,
      };
}

/// A file to hash, with the stat values the cache is keyed by.
class LibretroBiosHashRequest {
  const LibretroBiosHashRequest(this.path, this.size, this.modifiedMs);

  final String path;
  final int size;
  final int modifiedMs;
}

/// Hashes files and returns their facts by path. The default one runs
/// [LibretroBiosCheckService.hashFilesSync] in a background isolate.
typedef LibretroBiosHasher = Future<Map<String, LibretroBiosFileFacts>> Function(
    List<LibretroBiosHashRequest> requests);

/// The folders and build facts one check reads.
class LibretroBiosEnvironment {
  const LibretroBiosEnvironment({
    required this.systemDirectory,
    required this.configDirectory,
    required this.cacheFile,
    this.documentsDirectory,
    this.availableCores,
    this.bundledSha256 = const <String, String>{},
  });

  /// `Documents/Libretro/System`, the folder every core reads.
  final String systemDirectory;

  /// `Documents/Libretro/Config`: stored core options (`<core>.json`).
  final String configDirectory;

  /// `Library/Caches/Libretro/bios-check-v1.json`, the only file written.
  final String cacheFile;

  /// Shown as "RewindBox" (Files › On My iPhone › RewindBox).
  final String? documentsDirectory;

  /// Cores packaged in this build; null when unknown (every core).
  final Set<String>? availableCores;

  /// SHA-256 of the system files NeoStation ships
  /// (`Runner.app/Libretro-native-identity.json`), by path below
  /// `LibretroSystem`.
  final Map<String, String> bundledSha256;
}

/// A game of the library, as far as the checker needs it.
class LibretroBiosGame {
  const LibretroBiosGame({required this.system, required this.path, required this.name});

  /// NeoStation system key (`LibretroInternalService.systemKey`).
  final String system;
  final String path;
  final String name;

  String get extension {
    final value = p.extension(name.isEmpty ? path : name).toLowerCase();
    return value.startsWith('.') ? value.substring(1) : value;
  }
}

/// A copy of a file the core reads.
class LibretroBiosFoundFile {
  const LibretroBiosFoundFile({
    required this.path,
    required this.displayPath,
    required this.name,
    this.location,
    this.byChecksum = false,
    this.crcIgnored = false,
    this.onlyCore,
  });

  final String path;
  final String displayPath;
  final String name;
  final LibretroBiosLocation? location;

  /// Found by Beetle PSX's checksum scan of the System root.
  final bool byChecksum;

  /// In a folder whose member CRCs the core does not check.
  final bool crcIgnored;

  /// Only this core reads it under this name (PicoDrive's Mega-CD names).
  final String? onlyCore;
}

class LibretroBiosEntryResult {
  const LibretroBiosEntryResult({
    required this.entry,
    required this.status,
    required this.need,
    required this.neededNow,
    required this.cores,
    required this.expected,
    this.found,
    this.copies = const <LibretroBiosFoundFile>[],
    this.facts,
    this.matchedDump,
    this.notes = const <LibretroBiosNote>[],
  });

  final LibretroBiosEntry entry;
  final LibretroBiosStatus status;
  final LibretroBiosNeed need;

  /// The console or a game of the library cannot run without it.
  final bool neededNow;

  /// Cores of this build that read it.
  final List<String> cores;

  /// Where the cores look, in order: a display path, or null for "the folder
  /// of the games".
  final List<String?> expected;

  /// The copy the core uses.
  final LibretroBiosFoundFile? found;

  /// Every copy found (FBNeo collects them all).
  final List<LibretroBiosFoundFile> copies;
  final LibretroBiosFileFacts? facts;
  final LibretroBiosDump? matchedDump;
  final List<LibretroBiosNote> notes;

  LibretroBiosCondition? get condition => entry.condition;
}

class LibretroBiosConsoleResult {
  const LibretroBiosConsoleResult({
    required this.id,
    required this.name,
    required this.available,
    required this.entries,
    required this.notes,
    required this.ready,
    this.gateNote,
  });

  /// Key of `LibretroCoreCatalog.consoles`.
  final String id;

  /// Product name, never translated.
  final String name;

  /// A core of this console is packaged in this build.
  final bool available;
  final List<LibretroBiosEntryResult> entries;
  final List<LibretroBiosNote> notes;

  /// NeoStation's own launch rule (PlayStation), met or not.
  final LibretroBiosNote? gateNote;

  /// Nothing needed is missing or unusable and the launch rule is met.
  final bool ready;

  /// What to fix before every game of the console can start: each missing
  /// required file and each unusable needed one, with NeoStation's launch
  /// rule counted once when it is not met (any one of its files is enough,
  /// so its rows are not counted again on top of it).
  int get problems {
    final gateMissing = gateNote?.key == 'biosGateMissing';
    final files = entries
        .where((result) =>
            !(gateMissing && result.entry.gate != null) &&
            (result.status == LibretroBiosStatus.missingRequired ||
                (result.status == LibretroBiosStatus.invalid && result.neededNow)))
        .length;
    return files + (gateMissing ? 1 : 0);
  }
}

class LibretroBiosReport {
  const LibretroBiosReport({
    required this.consoles,
    required this.examinedFiles,
    required this.hashedFiles,
    required this.cachedFiles,
    required this.elapsed,
    this.libraryUnavailable = false,
  });

  final List<LibretroBiosConsoleResult> consoles;

  /// Files whose checksums were needed.
  final int examinedFiles;

  /// Of those, read and hashed in this check.
  final int hashedFiles;

  /// Of those, taken from the cache (unchanged size and date).
  final int cachedFiles;
  final Duration elapsed;

  /// The library could not be read: conditional files are shown as not
  /// needed.
  final bool libraryUnavailable;

  Iterable<LibretroBiosEntryResult> get entries =>
      consoles.where((console) => console.available).expand((console) => console.entries);

  Map<LibretroBiosStatus, int> get counts => <LibretroBiosStatus, int>{
        for (final status in LibretroBiosStatus.values)
          status: entries.where((result) => result.status == status).length,
      };

  int get readyConsoles => consoles.where((console) => console.available && console.ready).length;
  int get availableConsoles => consoles.where((console) => console.available).length;
}

/// Read-only BIOS checker of the embedded libretro cores (Settings › Tools ›
/// BIOS checker).
///
/// It compares [LibretroBiosCatalog] with the System folder, the folders of
/// the games for the cores that look there, and the stored core options. It
/// never creates, renames, moves or deletes anything in System, Saves,
/// Config or the libraries: its only write is its checksum cache in
/// `Library/Caches/Libretro`. File names are compared exactly, from
/// directory listings (iOS file systems are case sensitive, test hosts
/// often are not). Files are hashed in a background isolate, once per size
/// and modification date. It never blocks a launch: the launch rules stay
/// in `LibretroInternalService.launch`.
class LibretroBiosCheckService {
  LibretroBiosCheckService({
    Future<LibretroBiosCatalog> Function()? catalog,
    Future<LibretroBiosEnvironment> Function()? environment,
    Future<List<LibretroBiosGame>> Function(Set<String> systems)? library,
    LibretroBiosHasher? hasher,
  })  : _catalog = catalog ?? LibretroBiosCatalog.load,
        _environment = environment ?? productionEnvironment,
        _library = library ?? loadLibraryGames,
        _hasher = hasher ?? isolateHasher;

  static final _log = LoggerService.instance;

  static const String cacheFileName = 'bios-check-v1.json';
  static const int cacheSchema = 1;

  /// Files over this size are not hashed (BIOS files are at most a few MiB).
  static const int maxHashedBytes = 64 * 1024 * 1024;

  /// Bytes of each file kept for the header checks.
  static const int headBytes = 512;

  /// Depth of the System scan for files saved in another folder.
  static const int maxScanDepth = 3;
  static const int maxScannedFiles = 5000;
  static const Duration listTimeout = Duration(seconds: 5);

  final Future<LibretroBiosCatalog> Function() _catalog;
  final Future<LibretroBiosEnvironment> Function() _environment;
  final Future<List<LibretroBiosGame>> Function(Set<String> systems) _library;
  final LibretroBiosHasher _hasher;
  LibretroBiosCatalog? _loadedCatalog;

  /// Checks every console. [libraryRoots] are the registered ROM folders;
  /// their console folders are where FBNeo and Snes9x also look.
  Future<LibretroBiosReport> check({Iterable<String> libraryRoots = const <String>[]}) async {
    final watch = Stopwatch()..start();
    final catalog = _loadedCatalog ??= await _catalog();
    final environment = await _environment();
    final scan = _Scan(catalog, environment, libraryRoots.toList(growable: false), _hasher);
    final needed = scan.librarySystems();
    var libraryUnavailable = false;
    try {
      scan.games = needed.isEmpty ? const <LibretroBiosGame>[] : await _library(needed);
    } catch (error) {
      _log.w('BIOS checker: library unavailable: $error');
      libraryUnavailable = true;
      scan.games = const <LibretroBiosGame>[];
    }
    final consoles = await scan.run();
    watch.stop();
    return LibretroBiosReport(
      consoles: consoles,
      examinedFiles: scan.examined,
      hashedFiles: scan.hashed,
      cachedFiles: scan.cached,
      elapsed: watch.elapsed,
      libraryUnavailable: libraryUnavailable,
    );
  }

  /// The app's folders, cores and shipped system files. Creates nothing.
  static Future<LibretroBiosEnvironment> productionEnvironment() async {
    final documents = await getApplicationDocumentsDirectory();
    final cache = await LibretroInternalService.cacheDirectory();
    Set<String>? cores;
    try {
      final list = await LibretroInternalBridge.availableCores();
      if (list.isNotEmpty) cores = list.toSet();
    } catch (error) {
      _log.w('BIOS checker: embedded cores unknown: $error');
    }
    return LibretroBiosEnvironment(
      systemDirectory: (await LibretroInternalService.systemDirectory()).path,
      configDirectory: (await LibretroInternalService.configDirectory()).path,
      cacheFile: p.join(cache.path, cacheFileName),
      documentsDirectory: documents.path,
      availableCores: cores,
      bundledSha256: await _bundledIdentity(),
    );
  }

  /// SHA-256 of the files below `Runner.app/LibretroSystem`, from the
  /// identity the delivery workflow embeds next to the executable.
  static Future<Map<String, String>> _bundledIdentity() async {
    if (!Platform.isIOS) return const <String, String>{};
    try {
      final file = File(p.join(p.dirname(Platform.resolvedExecutable), 'Libretro-native-identity.json'));
      final json = jsonDecode(await file.readAsString());
      final files = (json as Map)['files'];
      if (files is! Map) return const <String, String>{};
      const prefix = 'LibretroSystem/';
      return <String, String>{
        for (final entry in files.entries)
          if (entry.key.toString().startsWith(prefix) && entry.value is String)
            entry.key.toString().substring(prefix.length): (entry.value as String).toLowerCase(),
      };
    } catch (error) {
      _log.w('BIOS checker: bundled identity unreadable: $error');
      return const <String, String>{};
    }
  }

  /// Games of [systems] in the library, read from the database.
  static Future<List<LibretroBiosGame>> loadLibraryGames(Set<String> systems) async {
    final games = <LibretroBiosGame>[];
    for (final system in await SystemRepository.getDetectedSystems()) {
      final key = LibretroInternalService.systemKey(system);
      final id = system.id;
      if (!systems.contains(key) || id == null || system.romCount == 0) continue;
      for (final game in await GameRepository.getGamesBySystem(id)) {
        games.add(LibretroBiosGame(system: key, path: game.romPath, name: game.filename));
      }
    }
    return games;
  }

  /// Hashes in a background isolate.
  static Future<Map<String, LibretroBiosFileFacts>> isolateHasher(List<LibretroBiosHashRequest> requests) {
    if (requests.isEmpty) return Future<Map<String, LibretroBiosFileFacts>>.value(const <String, LibretroBiosFileFacts>{});
    return Isolate.run(() => hashFilesSync(requests));
  }

  /// Reads and hashes [requests] (MD5, SHA-1, SHA-256, the first bytes and
  /// the ZIP central directory). Never throws: an unreadable file is
  /// reported as such.
  static Map<String, LibretroBiosFileFacts> hashFilesSync(List<LibretroBiosHashRequest> requests) => <String, LibretroBiosFileFacts>{
        for (final request in requests) request.path: hashFileSync(request),
      };

  static LibretroBiosFileFacts hashFileSync(LibretroBiosHashRequest request) {
    try {
      if (request.size > maxHashedBytes) {
        final file = File(request.path).openSync();
        try {
          final head = file.readSync(headBytes);
          return LibretroBiosFileFacts(
            size: request.size,
            modifiedMs: request.modifiedMs,
            head: head,
            zipMagic: _zipMagic(head),
            tooLarge: true,
          );
        } finally {
          file.closeSync();
        }
      }
      final bytes = File(request.path).readAsBytesSync();
      final head = Uint8List.fromList(bytes.sublist(0, math.min(headBytes, bytes.length)));
      return LibretroBiosFileFacts(
        size: bytes.length,
        modifiedMs: request.modifiedMs,
        md5: crypto.md5.convert(bytes).toString(),
        sha1: crypto.sha1.convert(bytes).toString(),
        sha256: crypto.sha256.convert(bytes).toString(),
        head: head,
        zipMembers: zipCentralDirectory(bytes),
        zipMagic: _zipMagic(bytes),
      );
    } catch (_) {
      return LibretroBiosFileFacts(
        size: request.size,
        modifiedMs: request.modifiedMs,
        head: Uint8List(0),
        unreadable: true,
      );
    }
  }

  static bool _zipMagic(List<int> bytes) =>
      bytes.length >= 4 && bytes[0] == 0x50 && bytes[1] == 0x4b && (bytes[2] == 3 || bytes[2] == 5) && (bytes[3] == 4 || bytes[3] == 6);

  /// Members of a ZIP archive from its central directory, without
  /// decompressing anything; null when it is not a readable ZIP (ZIP64
  /// archives included, which no BIOS set needs).
  static List<LibretroBiosZipEntry>? zipCentralDirectory(Uint8List bytes) {
    if (bytes.length < 22) return null;
    final data = ByteData.sublistView(bytes);
    var end = -1;
    final lowest = math.max(0, bytes.length - 22 - 0xffff);
    for (var index = bytes.length - 22; index >= lowest; index--) {
      if (data.getUint32(index, Endian.little) == 0x06054b50) {
        end = index;
        break;
      }
    }
    if (end < 0) return null;
    final count = data.getUint16(end + 10, Endian.little);
    final size = data.getUint32(end + 12, Endian.little);
    final offset = data.getUint32(end + 16, Endian.little);
    if (count == 0xffff || offset == 0xffffffff || offset + size > bytes.length) return null;
    final members = <LibretroBiosZipEntry>[];
    var position = offset;
    for (var index = 0; index < count; index++) {
      if (position + 46 > bytes.length || data.getUint32(position, Endian.little) != 0x02014b50) return null;
      final crc = data.getUint32(position + 16, Endian.little);
      final length = data.getUint32(position + 24, Endian.little);
      final nameLength = data.getUint16(position + 28, Endian.little);
      final extraLength = data.getUint16(position + 30, Endian.little);
      final commentLength = data.getUint16(position + 32, Endian.little);
      if (position + 46 + nameLength > bytes.length) return null;
      final name = utf8.decode(bytes.sublist(position + 46, position + 46 + nameLength), allowMalformed: true);
      if (!name.endsWith('/')) members.add(LibretroBiosZipEntry(name, crc, length));
      position += 46 + nameLength + extraLength + commentLength;
    }
    return members;
  }
}

/// A file seen in a listing.
class _Listed {
  const _Listed(this.path, this.name, this.isDirectory);

  final String path;
  final String name;
  final bool isDirectory;
}

/// A candidate copy before hashing.
class _Candidate {
  const _Candidate(this.path, this.name, this.location, {this.onlyCore, this.crcIgnored = false});

  final String path;
  final String name;
  final LibretroBiosLocation location;
  final String? onlyCore;
  final bool crcIgnored;
}

/// One check: listings, stats and facts are read once.
class _Scan {
  _Scan(this.catalog, this.environment, this.libraryRoots, this.hasher);

  static final _log = LoggerService.instance;
  static const int _psxSmall = 512 * 1024;
  static const int _psxLarge = 1024 * 1024;

  final LibretroBiosCatalog catalog;
  final LibretroBiosEnvironment environment;
  final List<String> libraryRoots;
  final LibretroBiosHasher hasher;
  List<LibretroBiosGame> games = const <LibretroBiosGame>[];

  final Map<String, Future<Map<String, _Listed>?>> _listings = <String, Future<Map<String, _Listed>?>>{};
  final Map<String, FileStat?> _stats = <String, FileStat?>{};
  final Map<String, LibretroBiosFileFacts> _facts = <String, LibretroBiosFileFacts>{};
  final List<_Listed> _systemFiles = <_Listed>[];
  Map<String, String> _options = const <String, String>{};

  int examined = 0;
  int hashed = 0;
  int cached = 0;

  bool _available(String core) => environment.availableCores?.contains(core) ?? true;

  List<String> _cores(LibretroBiosEntry entry) => entry.cores.where(_available).toList(growable: false);

  /// Systems whose games decide conditional and regional files, and whose
  /// folders are game folders.
  Set<String> librarySystems() => <String>{
        for (final entry in catalog.entries) ...[
          ...?entry.condition?.games.expand((clause) => clause.systems),
          ...?entry.condition?.possibleIn,
          ...entry.gameFolderSystems,
          if (entry.regional) for (final console in entry.consoles) ..._consoleSystems(console),
        ],
      };

  static Iterable<String> _consoleSystems(String console) => LibretroCoreCatalog.systems.entries
      .where((binding) => binding.value.console == console)
      .map((binding) => binding.key);

  Future<List<LibretroBiosConsoleResult>> run() async {
    _options = await _readOptions();
    final visible = catalog.entries.where((entry) => _cores(entry).isNotEmpty).toList(growable: false);

    // Copies where the cores read them.
    final candidates = <String, List<_Candidate>>{};
    for (final entry in visible) {
      candidates[entry.id] = await _candidates(entry);
      if (entry.level == LibretroBiosLevel.bundled &&
          entry.locations.any((location) => !location.gameFolder) &&
          await _systemSubdirectory(entry.locations.firstWhere((location) => !location.gameFolder).subdirectory) != null) {
        _bundledFolders.add(entry.id);
      }
    }
    await _scanSystem();
    // Copies in other game folders than the ones the core reads.
    for (final entry in visible) {
      if (!entry.locations.any((location) => location.gameFolder)) continue;
      final taken = candidates[entry.id]!.map((candidate) => candidate.path).toSet();
      final names = entry.allNames(environment.availableCores).map((name) => name.toLowerCase()).toSet();
      final copies = <String>[];
      for (final folder in await _systemGameFolders(entry)) {
        final listing = await _list(folder);
        if (listing == null) continue;
        for (final name in listing.keys.toList()..sort()) {
          final child = listing[name]!;
          if (!child.isDirectory && names.contains(name.toLowerCase()) && !taken.contains(child.path)) {
            copies.add(child.path);
          }
        }
      }
      _otherFolderCopies[entry.id] = copies;
    }

    // Facts of every candidate, of the System files that could be a copy
    // saved under another name, and of the PS1 checksum scan.
    final knownSizes = catalog.knownSizes;
    final wanted = <String>{
      for (final list in candidates.values)
        for (final candidate in list) candidate.path,
      for (final file in _systemFiles)
        if (knownSizes.contains((await _stat(file.path))?.size)) file.path,
    };
    await _loadFacts(wanted);

    final gateNames = <String>{
      for (final entry in visible)
        if (entry.gate == 'psx')
          for (final core in _cores(entry)) ...?LibretroCoreCatalog.cores[core]?.biosAnyOf,
    };
    final systemListing = await _list(environment.systemDirectory) ?? const <String, _Listed>{};
    final gateMet = gateNames.where((name) => systemListing[name]?.isDirectory == false).toList(growable: false);

    final results = <String, LibretroBiosEntryResult>{};
    final present = <String, bool>{};
    for (final entry in visible) {
      present[entry.id] =
          candidates[entry.id]!.any((candidate) => candidate.onlyCore == null) || _checksumCopy(entry) != null;
    }
    for (final entry in visible) {
      results[entry.id] = _evaluate(entry, candidates[entry.id]!, gateNames, gateMet, present);
    }

    final consoles = <LibretroBiosConsoleResult>[];
    for (final console in LibretroCoreCatalog.consoles.values) {
      final coreIds = <String>{
        for (final binding in LibretroCoreCatalog.systems.values)
          if (binding.console == console.id) ...<String>[binding.coreId, ...binding.alternatives],
      };
      final available = coreIds.any(_available);
      final entries = <LibretroBiosEntryResult>[
        for (final entry in visible)
          if (entry.consoles.contains(console.id)) results[entry.id]!,
      ];
      LibretroBiosNote? gateNote;
      var gateOk = true;
      if (entries.any((result) => result.entry.gate == 'psx')) {
        gateOk = gateMet.isNotEmpty;
        gateNote = gateOk
            ? LibretroBiosNote('biosGateOk', <String, String>{'file': gateMet.first})
            : LibretroBiosNote('biosGateMissing', <String, String>{'files': gateNames.join(', ')});
      }
      final problems = entries.any((result) =>
          result.status == LibretroBiosStatus.missingRequired ||
          (result.status == LibretroBiosStatus.invalid && result.neededNow));
      consoles.add(LibretroBiosConsoleResult(
        id: console.id,
        name: console.name,
        available: available,
        entries: available ? entries : const <LibretroBiosEntryResult>[],
        notes: <LibretroBiosNote>[
          if (!available) const LibretroBiosNote('biosCoreUnavailable'),
          for (final key in catalog.consoles[console.id]?.noteKeys ?? const <String>[]) LibretroBiosNote(key),
        ],
        gateNote: available ? gateNote : null,
        ready: available && !problems && gateOk,
      ));
    }
    await _writeCache();
    return consoles;
  }

  // ---------------------------------------------------------------- reading

  /// Exact names of a folder; null when it cannot be read.
  Future<Map<String, _Listed>?> _list(String directory) => _listings[directory] ??= _readListing(directory);

  Future<Map<String, _Listed>?> _readListing(String directory) async {
    try {
      final listed = <String, _Listed>{};
      await for (final entity in Directory(directory).list(followLinks: false).timeout(LibretroBiosCheckService.listTimeout)) {
        final name = p.basename(entity.path);
        var isDirectory = entity is Directory;
        if (entity is Link) {
          isDirectory = await FileSystemEntity.isDirectory(entity.path);
        }
        listed[name] = _Listed(entity.path, name, isDirectory);
      }
      return listed;
    } catch (error) {
      if (error is! PathNotFoundException) _log.w('BIOS checker: $directory unreadable: $error');
      return null;
    }
  }

  Future<FileStat?> _stat(String path) async {
    if (_stats.containsKey(path)) return _stats[path];
    try {
      final stat = await File(path).stat();
      return _stats[path] = stat.type == FileSystemEntityType.notFound ? null : stat;
    } catch (_) {
      return _stats[path] = null;
    }
  }

  /// A folder below System, following each name exactly.
  Future<String?> _systemSubdirectory(List<String> parts) async {
    var directory = environment.systemDirectory;
    for (final part in parts) {
      final listing = await _list(directory);
      final child = listing?[part];
      if (child == null || !child.isDirectory) return null;
      directory = child.path;
    }
    return directory;
  }

  /// Folders a core reads as "the folder of the game" for [entry]: those of
  /// the games that need it when the library holds some (the core looks
  /// next to the game being launched), else those of the games of its
  /// systems and the console folders of the registered libraries.
  Future<List<String>> _gameFolders(LibretroBiosEntry entry) async {
    final needing = (_conditionGames(entry) ?? const <LibretroBiosGame>[]).where(_local).toList(growable: false);
    if (needing.isNotEmpty) {
      return (<String>{for (final game in needing) p.normalize(p.dirname(game.path))}.toList())..sort();
    }
    return _systemGameFolders(entry);
  }

  static bool _local(LibretroBiosGame game) => game.path.isNotEmpty && !game.path.contains('://');

  /// Folders of the games of [entry]'s systems and the console folders of
  /// the registered libraries.
  Future<List<String>> _systemGameFolders(LibretroBiosEntry entry) async {
    final folders = <String>{};
    final systems = entry.gameFolderSystems;
    for (final game in games) {
      if (systems.contains(game.system) && _local(game)) folders.add(p.normalize(p.dirname(game.path)));
    }
    for (final root in libraryRoots) {
      if (root.isEmpty || root.contains('://')) continue;
      final normalized = p.normalize(root);
      if (systems.contains(p.basename(normalized).toLowerCase())) folders.add(normalized);
      final listing = await _list(normalized);
      if (listing == null) continue;
      for (final child in listing.values) {
        if (child.isDirectory && systems.contains(child.name.toLowerCase())) folders.add(p.normalize(child.path));
      }
    }
    return folders.toList()..sort();
  }

  Future<List<_Candidate>> _candidates(LibretroBiosEntry entry) async {
    final found = <_Candidate>[];
    final cores = _cores(entry).toSet();
    for (final location in entry.locations) {
      final directories = location.gameFolder
          ? await _gameFolders(entry)
          : <String>[if (await _systemSubdirectory(location.subdirectory) case final String directory) directory];
      for (final directory in directories) {
        final listing = await _list(directory);
        if (listing == null) continue;
        final crcIgnored = entry.crcIgnoredLocations.contains(location);
        for (final name in entry.names) {
          final hit = listing[name];
          if (hit != null && !hit.isDirectory) found.add(_Candidate(hit.path, name, location, crcIgnored: crcIgnored));
        }
        for (final core in entry.coreNames.entries) {
          if (!cores.contains(core.key)) continue;
          for (final name in core.value) {
            if (entry.names.contains(name)) continue;
            final hit = listing[name];
            if (hit != null && !hit.isDirectory) {
              found.add(_Candidate(hit.path, name, location, onlyCore: core.key, crcIgnored: crcIgnored));
            }
          }
        }
      }
    }
    return found;
  }

  /// Files of System up to [LibretroBiosCheckService.maxScanDepth] folders
  /// deep, without the PPSSPP support files.
  Future<void> _scanSystem() async {
    Future<void> walk(String directory, int depth) async {
      if (_systemFiles.length >= LibretroBiosCheckService.maxScannedFiles) return;
      final listing = await _list(directory);
      if (listing == null) return;
      final names = listing.keys.toList()..sort();
      for (final name in names) {
        final child = listing[name]!;
        if (child.isDirectory) {
          if (depth == 0 && name == 'PPSSPP') continue;
          if (depth < LibretroBiosCheckService.maxScanDepth) await walk(child.path, depth + 1);
        } else if (_systemFiles.length < LibretroBiosCheckService.maxScannedFiles) {
          _systemFiles.add(child);
        }
      }
    }

    await walk(environment.systemDirectory, 0);
  }

  /// Stored core options of every core (`Config/*.json` `values`).
  Future<Map<String, String>> _readOptions() async {
    final options = <String, String>{};
    final listing = await _list(environment.configDirectory);
    if (listing == null) return options;
    final names = listing.keys.where((name) => name.toLowerCase().endsWith('.json')).toList()..sort();
    for (final name in names) {
      final file = listing[name]!;
      if (file.isDirectory) continue;
      try {
        final json = jsonDecode(await File(file.path).readAsString());
        final values = json is Map ? json['values'] : null;
        if (values is Map) {
          for (final entry in values.entries) {
            if (entry.value is String) options[entry.key.toString()] = entry.value as String;
          }
        }
      } catch (error) {
        _log.w('BIOS checker: core options ${file.path} unreadable: $error');
      }
    }
    return options;
  }

  // ----------------------------------------------------------- hash cache

  String _cacheKey(String path) {
    final system = environment.systemDirectory;
    if (p.isWithin(system, path)) return 'system:${p.relative(path, from: system).replaceAll(r'\', '/')}';
    return 'path:$path';
  }

  Map<String, dynamic> _cache = <String, dynamic>{};
  final Map<String, Object?> _usedCache = <String, Object?>{};
  bool _cacheChanged = false;

  Future<void> _readCache() async {
    try {
      final json = jsonDecode(await File(environment.cacheFile).readAsString());
      if (json is Map && json['schema'] == LibretroBiosCheckService.cacheSchema && json['files'] is Map) {
        _cache = (json['files'] as Map).cast<String, dynamic>();
      }
    } catch (_) {
      _cache = <String, dynamic>{};
    }
  }

  Future<void> _loadFacts(Set<String> paths) async {
    await _readCache();
    final requests = <LibretroBiosHashRequest>[];
    final keys = <String, String>{};
    for (final path in paths.toList()..sort()) {
      final stat = await _stat(path);
      if (stat == null) continue;
      examined++;
      final key = _cacheKey(path);
      keys[path] = key;
      final modified = stat.modified.millisecondsSinceEpoch;
      final entry = _cache[key];
      if (entry is Map) {
        try {
          final facts = LibretroBiosFileFacts.fromJson(entry.cast<String, dynamic>());
          if (facts.modifiedMs == modified && _statSize(stat) == _cachedStatSize(entry, facts)) {
            _facts[path] = facts;
            _usedCache[key] = entry;
            cached++;
            continue;
          }
        } catch (_) {
          // Unreadable cache entry: hashed again.
        }
      }
      requests.add(LibretroBiosHashRequest(path, stat.size, modified));
    }
    if (requests.isNotEmpty) {
      final fresh = await hasher(requests);
      for (final request in requests) {
        final facts = fresh[request.path];
        if (facts == null) continue;
        hashed++;
        _facts[request.path] = facts;
        if (!facts.unreadable) {
          _usedCache[keys[request.path]!] = <String, Object?>{...facts.toJson(), 'stat': request.size};
          _cacheChanged = true;
        }
      }
    }
    if (_usedCache.length != _cache.length) _cacheChanged = true;
  }

  static int _statSize(FileStat stat) => stat.size;
  static int _cachedStatSize(Map<dynamic, dynamic> entry, LibretroBiosFileFacts facts) =>
      entry['stat'] is int ? entry['stat'] as int : facts.size;

  Future<void> _writeCache() async {
    if (!_cacheChanged) return;
    try {
      final file = File(environment.cacheFile);
      await file.parent.create(recursive: true);
      final temporary = File('${environment.cacheFile}.tmp');
      await temporary.writeAsString(jsonEncode(<String, Object?>{
        'schema': LibretroBiosCheckService.cacheSchema,
        'files': _usedCache,
      }));
      await temporary.rename(file.path);
    } catch (error) {
      _log.w('BIOS checker: cache not saved: $error');
    }
  }

  // ------------------------------------------------------------ decisions

  String _display(String path) {
    final documents = environment.documentsDirectory;
    if (documents != null && p.isWithin(documents, path)) {
      return 'RewindBox/${p.relative(path, from: documents).replaceAll(r'\', '/')}';
    }
    return path;
  }

  List<String?> _expected(LibretroBiosEntry entry) => <String?>[
        for (final location in entry.locations)
          location.gameFolder
              ? null
              : _display(p.joinAll(<String>[environment.systemDirectory, ...location.subdirectory, entry.names.first])),
      ];

  LibretroBiosFoundFile _found(_Candidate candidate) => LibretroBiosFoundFile(
        path: candidate.path,
        displayPath: _display(candidate.path),
        name: candidate.name,
        location: candidate.location,
        crcIgnored: candidate.crcIgnored,
        onlyCore: candidate.onlyCore,
      );

  /// Beetle PSX's checksum scan: a 512 KiB or 1 MiB file of the System root
  /// with the region's SHA-1.
  LibretroBiosFoundFile? _checksumCopy(LibretroBiosEntry entry) {
    if (!entry.psxChecksumScan) return null;
    final sha1s = entry.knownDumps.map((dump) => dump.sha1).whereType<String>().toSet();
    for (final file in _systemFiles) {
      if (!p.equals(p.dirname(file.path), environment.systemDirectory)) continue;
      final facts = _facts[file.path];
      if (facts == null || (facts.size != _psxSmall && facts.size != _psxLarge)) continue;
      if (facts.sha1 != null && sha1s.contains(facts.sha1)) {
        return LibretroBiosFoundFile(
          path: file.path,
          displayPath: _display(file.path),
          name: file.name,
          location: LibretroBiosLocation.parse('system'),
          byChecksum: true,
        );
      }
    }
    return null;
  }

  bool _clauseMatches(LibretroBiosGameClause clause, LibretroBiosGame game) =>
      clause.systems.contains(game.system) && (clause.extensions.isEmpty || clause.extensions.contains(game.extension));

  /// Games of the library that need [entry]; null when the library cannot
  /// tell (no clause).
  List<LibretroBiosGame>? _conditionGames(LibretroBiosEntry entry) {
    final condition = entry.condition;
    if (condition == null || condition.games.isEmpty) return null;
    return games.where((game) => condition.games.any((clause) => _clauseMatches(clause, game))).toList(growable: false);
  }

  /// The library holds games that may need [entry] without telling which
  /// ([LibretroBiosCondition.possibleIn]).
  bool _possibleGames(LibretroBiosEntry entry) {
    final systems = entry.condition?.possibleIn ?? const <String>{};
    return systems.isNotEmpty && games.any((game) => systems.contains(game.system));
  }

  /// Games of [entry]'s region need it; untagged games need some member of
  /// its group when none is present.
  bool _regionNeeds(LibretroBiosEntry entry, List<LibretroBiosGame> relevant, Map<String, bool> present) {
    if (relevant.isEmpty) return false;
    final region = entry.region;
    var untagged = false;
    for (final game in relevant) {
      final regions = catalog.regionsOf(p.basename(game.name.isEmpty ? game.path : game.name));
      if (region != null && regions.contains(region)) return true;
      if (regions.isEmpty) untagged = true;
    }
    if (!untagged) return false;
    final group = entry.group;
    final groupPresent = catalog.entries.any((other) =>
        other.group != null && other.group == group && (present[other.id] ?? false));
    return !groupPresent;
  }

  LibretroBiosEntryResult _evaluate(
    LibretroBiosEntry entry,
    List<_Candidate> candidates,
    Set<String> gateNames,
    List<String> gateMet,
    Map<String, bool> present,
  ) {
    final notes = <LibretroBiosNote>[];
    final cores = _cores(entry);

    // How much it is needed now.
    var need = LibretroBiosNeed.optional;
    var neededNow = false;
    switch (entry.level) {
      case LibretroBiosLevel.required:
        if (entry.gate == 'psx' && gateMet.isNotEmpty) {
          // NeoStation's rule is met; Beetle wants the BIOS of the disc's
          // region and otherwise starts the disc with OpenBIOS.
          final systems = _consoleSystems(entry.consoles.first).toSet();
          final regionGames = !entry.regional
              ? const <LibretroBiosGame>[]
              : games.where((game) =>
                  systems.contains(game.system) &&
                  catalog.regionsOf(p.basename(game.name.isEmpty ? game.path : game.name)).contains(entry.region));
          if (regionGames.isNotEmpty && !catalog.openBiosFallback) {
            need = LibretroBiosNeed.required;
            neededNow = true;
          } else {
            need = LibretroBiosNeed.recommended;
          }
        } else {
          need = LibretroBiosNeed.required;
          neededNow = true;
        }
      case LibretroBiosLevel.conditional:
        final relevant = _conditionGames(entry);
        if (relevant == null || relevant.isEmpty) {
          need = LibretroBiosNeed.onlyFor;
          final unknown = relevant == null || _possibleGames(entry);
          notes.add(LibretroBiosNote(unknown ? 'biosConditionUnknown' : 'biosConditionUnmet'));
        } else if (!entry.regional || _regionNeeds(entry, relevant, present)) {
          need = LibretroBiosNeed.requiredFor;
          neededNow = true;
          notes.add(LibretroBiosNote('biosConditionMet', <String, String>{'count': '${relevant.length}'}));
        } else {
          need = LibretroBiosNeed.onlyFor;
          notes.add(const LibretroBiosNote('biosRegionNotNeeded'));
        }
      case LibretroBiosLevel.optional:
        need = LibretroBiosNeed.optional;
      case LibretroBiosLevel.bundled:
        need = LibretroBiosNeed.bundled;
    }

    // Option gates (core options that make the core read the file).
    final gates = entry.optionGates.where((gate) => _available(gate.core)).toList(growable: false);
    if (gates.isNotEmpty) {
      final open = gates.where((gate) => gate.isOn(_options)).toList(growable: false);
      if (open.isNotEmpty) {
        notes.add(LibretroBiosNote('biosOptionOn', <String, String>{'option': open.first.all.last.keys.first}));
      } else {
        notes.add(LibretroBiosNote('biosOptionOff', <String, String>{'option': gates.first.firstOff(_options)!.keys.first}));
      }
    }
    for (final key in entry.noteKeys) {
      notes.add(LibretroBiosNote(key));
    }

    final expected = _expected(entry);

    // Bundled files: present unless the folder is incomplete.
    if (entry.level == LibretroBiosLevel.bundled) {
      return _evaluateBundled(entry, candidates, cores, expected, notes);
    }

    final defaults = candidates.where((candidate) => candidate.onlyCore == null).toList(growable: false);
    final others = candidates.where((candidate) => candidate.onlyCore != null).toList(growable: false);
    LibretroBiosFoundFile? used = defaults.isEmpty ? null : _found(defaults.first);
    final copies = <LibretroBiosFoundFile>[for (final candidate in defaults) _found(candidate)];
    if (used == null && entry.psxChecksumScan) {
      used = _checksumCopy(entry);
      if (used != null) {
        copies.add(used);
        notes.add(LibretroBiosNote('biosFoundByChecksum', <String, String>{'name': used.name}));
      }
    }

    if (entry.gate == 'psx' && gateMet.isEmpty) {
      notes.add(LibretroBiosNote('biosGroupOneOf', <String, String>{'files': gateNames.join(', ')}));
      final gateName = entry.names.firstWhere(gateNames.contains, orElse: () => '');
      if (used != null && gateName.isNotEmpty && used.name != gateName) {
        notes.add(LibretroBiosNote('biosRename', <String, String>{'found': used.name, 'name': gateName}));
      }
    }

    if (used == null) {
      for (final other in others) {
        notes.add(LibretroBiosNote('biosOnlyCore', <String, String>{
          'name': other.name,
          'core': LibretroCoreCatalog.cores[other.onlyCore]?.displayName ?? other.onlyCore!,
        }));
      }
      final elsewhere = _elsewhere(entry, candidates);
      if (elsewhere != null) {
        notes.add(LibretroBiosNote('biosFoundElsewhere', <String, String>{
          'path': _display(elsewhere),
          'expected': expected.whereType<String>().isEmpty ? entry.names.first : expected.whereType<String>().first,
        }));
      }
      if (entry.gate == 'psx' && gateMet.isNotEmpty && catalog.openBiosFallback) {
        notes.add(const LibretroBiosNote('biosOpenBiosFallback'));
      }
      if (entry.perConsoleDump) notes.add(const LibretroBiosNote('biosNotVerifiable'));
      return LibretroBiosEntryResult(
        entry: entry,
        status: neededNow ? LibretroBiosStatus.missingRequired : LibretroBiosStatus.missingOptional,
        need: need,
        neededNow: neededNow,
        cores: cores,
        expected: expected,
        notes: notes,
      );
    }

    if (entry.lookupAll) return _evaluateSet(entry, copies, cores, expected, notes, need, neededNow);

    final facts = _facts[used.path];
    final verdict = _verdict(entry, used, facts);
    notes.addAll(verdict.notes);
    return LibretroBiosEntryResult(
      entry: entry,
      status: verdict.status,
      need: need,
      neededNow: neededNow,
      cores: cores,
      expected: expected,
      found: used,
      copies: copies,
      facts: facts,
      matchedDump: verdict.dump,
      notes: notes,
    );
  }

  /// A copy saved in another folder or under another case or name: same
  /// name ignoring case, or the checksum of one of the entry's dumps.
  String? _elsewhere(LibretroBiosEntry entry, List<_Candidate> candidates) {
    final other = _otherFolderCopies[entry.id];
    if (other != null && other.isNotEmpty) return other.first;
    final taken = candidates.map((candidate) => candidate.path).toSet();
    final names = entry.allNames(environment.availableCores).map((name) => name.toLowerCase()).toSet();
    for (final file in _systemFiles) {
      if (taken.contains(file.path)) continue;
      if (names.contains(file.name.toLowerCase())) return file.path;
    }
    for (final file in _systemFiles) {
      if (taken.contains(file.path)) continue;
      final facts = _facts[file.path];
      if (facts == null || facts.md5 == null) continue;
      if (entry.knownDumps.any((dump) => dump.matches(size: facts.size, md5: facts.md5, sha1: facts.sha1))) {
        return file.path;
      }
    }
    return null;
  }

  _Verdict _verdict(LibretroBiosEntry entry, LibretroBiosFoundFile copy, LibretroBiosFileFacts? facts) {
    if (facts == null || facts.unreadable) {
      return const _Verdict(LibretroBiosStatus.invalid, <LibretroBiosNote>[LibretroBiosNote('biosInvalidUnreadable')]);
    }
    if (facts.size == 0) {
      return const _Verdict(LibretroBiosStatus.invalid, <LibretroBiosNote>[LibretroBiosNote('biosInvalidEmpty')]);
    }
    final archive = copy.name.toLowerCase().endsWith('.zip');
    if (archive && !facts.zipMagic) {
      return const _Verdict(LibretroBiosStatus.invalid, <LibretroBiosNote>[LibretroBiosNote('biosInvalidArchive')]);
    }
    if (!archive) {
      for (final validator in entry.validators) {
        final failure = _validate(validator, facts);
        if (failure != null) return _Verdict(LibretroBiosStatus.invalid, <LibretroBiosNote>[failure]);
      }
    }
    final notes = <LibretroBiosNote>[];
    if (copy.onlyCore != null) {
      notes.add(LibretroBiosNote('biosOnlyCore', <String, String>{
        'name': copy.name,
        'core': LibretroCoreCatalog.cores[copy.onlyCore]?.displayName ?? copy.onlyCore!,
      }));
    }
    for (final dump in entry.knownDumps) {
      if (dump.matches(size: facts.size, md5: facts.md5, sha1: facts.sha1)) {
        return _Verdict(LibretroBiosStatus.verified, notes, dump);
      }
    }
    // A zipped copy (PicoDrive): its member, by CRC.
    if (archive && facts.zipMembers != null) {
      for (final member in facts.zipMembers!) {
        for (final dump in entry.knownDumps) {
          if (dump.matchesCrc(size: member.size, crc: member.crc)) {
            return _Verdict(LibretroBiosStatus.verified, notes, dump);
          }
        }
      }
    }
    if (entry.perConsoleDump) {
      return _Verdict(LibretroBiosStatus.presentUnverified, <LibretroBiosNote>[...notes, const LibretroBiosNote('biosNotVerifiable')]);
    }
    for (final other in catalog.entries) {
      if (other.id == entry.id) continue;
      for (final dump in other.knownDumps) {
        if (dump.matches(size: facts.size, md5: facts.md5, sha1: facts.sha1)) {
          return _Verdict(LibretroBiosStatus.presentUnverified, <LibretroBiosNote>[
            ...notes,
            LibretroBiosNote('biosIdentifiedAs', <String, String>{'name': other.names.first}),
          ]);
        }
      }
    }
    if (facts.tooLarge) {
      return _Verdict(LibretroBiosStatus.presentUnverified, <LibretroBiosNote>[...notes, const LibretroBiosNote('biosHashUnknown')]);
    }
    return _Verdict(LibretroBiosStatus.presentUnverified, <LibretroBiosNote>[
      ...notes,
      LibretroBiosNote(entry.hashVaries ? 'biosHashVaries' : 'biosHashUnknown'),
    ]);
  }

  /// The failure a validator proves, null when the file passes.
  LibretroBiosNote? _validate(LibretroBiosValidator validator, LibretroBiosFileFacts facts) {
    switch (validator) {
      case LibretroBiosMinSize(:final size):
        if (facts.size < size) {
          return LibretroBiosNote('biosInvalidSize', <String, String>{'expected': '$size', 'actual': '${facts.size}'});
        }
      case LibretroBiosHeader(:final offset, :final ascii):
        final expected = ascii.codeUnits;
        if (facts.head.length < offset + expected.length) return const LibretroBiosNote('biosInvalidHeader');
        for (var index = 0; index < expected.length; index++) {
          if (facts.head[offset + index] != expected[index]) return const LibretroBiosNote('biosInvalidHeader');
        }
      case LibretroBiosFirstWord(:final values):
        if (facts.head.length < 4) return const LibretroBiosNote('biosInvalidHeader');
        final word = (facts.head[0] << 24) | (facts.head[1] << 16) | (facts.head[2] << 8) | facts.head[3];
        if (!values.contains(word)) return const LibretroBiosNote('biosInvalidHeader');
      case LibretroBiosZipMembers():
        // Checked over every copy of the set (_evaluateSet).
        break;
    }
    return null;
  }

  /// FBNeo: the core collects every copy of the set and takes each member
  /// it needs by CRC from any of them; patched copies are used as they are.
  LibretroBiosEntryResult _evaluateSet(
    LibretroBiosEntry entry,
    List<LibretroBiosFoundFile> copies,
    List<String> cores,
    List<String?> expected,
    List<LibretroBiosNote> notes,
    LibretroBiosNeed need,
    bool neededNow,
  ) {
    final usable = <LibretroBiosFoundFile>[];
    final crcs = <int>{};
    var unchecked = false;
    var patched = false;
    LibretroBiosNote? lastFailure;
    LibretroBiosDump? dump;
    for (final copy in copies) {
      final facts = _facts[copy.path];
      final lower = copy.name.toLowerCase();
      if (facts == null || facts.unreadable) {
        lastFailure = const LibretroBiosNote('biosInvalidUnreadable');
        continue;
      }
      if (facts.size == 0) {
        lastFailure = const LibretroBiosNote('biosInvalidEmpty');
        continue;
      }
      if (lower.endsWith('.7z')) {
        usable.add(copy);
        unchecked = true;
        continue;
      }
      if (!facts.zipMagic) {
        lastFailure = const LibretroBiosNote('biosInvalidArchive');
        continue;
      }
      usable.add(copy);
      if (copy.crcIgnored) patched = true;
      final members = facts.zipMembers;
      if (members == null) {
        unchecked = true;
      } else {
        crcs.addAll(members.map((member) => member.crc));
      }
      dump ??= entry.knownDumps.where((known) => known.matches(size: facts.size, md5: facts.md5, sha1: facts.sha1)).firstOrNull;
    }
    if (usable.isEmpty) {
      return LibretroBiosEntryResult(
        entry: entry,
        status: LibretroBiosStatus.invalid,
        need: need,
        neededNow: neededNow,
        cores: cores,
        expected: expected,
        found: copies.first,
        copies: copies,
        facts: _facts[copies.first.path],
        notes: <LibretroBiosNote>[...notes, ?lastFailure],
      );
    }
    final used = usable.first;
    final status = <LibretroBiosNote>[];
    if (patched) status.add(const LibretroBiosNote('biosPatchedCopy'));
    if (unchecked) status.add(const LibretroBiosNote('biosArchiveNotChecked'));
    var result = LibretroBiosStatus.presentUnverified;
    final members = entry.validators.whereType<LibretroBiosZipMembers>().firstOrNull;
    if (dump != null) {
      result = LibretroBiosStatus.verified;
    } else if (members != null) {
      final missingEssential = members.essential.where((member) => !crcs.contains(member.crc)).toList();
      final missingRecommended = members.recommended.where((member) => !crcs.contains(member.crc)).toList();
      if (missingEssential.isNotEmpty && !patched && !unchecked) {
        result = LibretroBiosStatus.invalid;
        status.add(LibretroBiosNote('biosInvalidMembers', <String, String>{
          'files': missingEssential.map((member) => member.name).join(', '),
        }));
      } else if (missingEssential.isEmpty && missingRecommended.isEmpty) {
        result = LibretroBiosStatus.verified;
        status.add(const LibretroBiosNote('biosMembersVerified'));
      } else if (missingEssential.isEmpty) {
        status.add(LibretroBiosNote('biosArchiveMissingRecommended', <String, String>{
          'files': missingRecommended.map((member) => member.name).join(', '),
        }));
      } else {
        status.add(const LibretroBiosNote('biosHashVaries'));
      }
    } else {
      status.add(LibretroBiosNote(entry.hashVaries ? 'biosHashVaries' : 'biosHashUnknown'));
    }
    if (usable.length > 1) status.add(LibretroBiosNote('biosCopies', <String, String>{'count': '${usable.length}'}));
    return LibretroBiosEntryResult(
      entry: entry,
      status: result,
      need: need,
      neededNow: neededNow,
      cores: cores,
      expected: expected,
      found: used,
      copies: copies,
      facts: _facts[used.path],
      matchedDump: dump,
      notes: <LibretroBiosNote>[...notes, ...status],
    );
  }

  /// PPSSPP's support files: NeoStation copies its own folder at the next
  /// PSP launch when `System/PPSSPP` is absent, and never completes an
  /// existing one.
  LibretroBiosEntryResult _evaluateBundled(
    LibretroBiosEntry entry,
    List<_Candidate> candidates,
    List<String> cores,
    List<String?> expected,
    List<LibretroBiosNote> notes,
  ) {
    final folderPresent = candidates.isNotEmpty || _bundledFolders.contains(entry.id);
    if (candidates.isEmpty) {
      final incomplete = folderPresent;
      return LibretroBiosEntryResult(
        entry: entry,
        status: incomplete && entry.bundledRequired ? LibretroBiosStatus.missingRequired : LibretroBiosStatus.missingOptional,
        need: LibretroBiosNeed.bundled,
        neededNow: incomplete && entry.bundledRequired,
        cores: cores,
        expected: expected,
        notes: <LibretroBiosNote>[
          ...notes,
          LibretroBiosNote(incomplete ? 'biosPpssppIncomplete' : 'biosPpssppInstalledOnLaunch'),
        ],
      );
    }
    final used = _found(candidates.first);
    final facts = _facts[used.path];
    if (facts == null || facts.unreadable || facts.size == 0) {
      final verdict = _verdict(entry, used, facts);
      return LibretroBiosEntryResult(
        entry: entry,
        status: verdict.status,
        need: LibretroBiosNeed.bundled,
        neededNow: entry.bundledRequired,
        cores: cores,
        expected: expected,
        found: used,
        copies: <LibretroBiosFoundFile>[used],
        facts: facts,
        notes: <LibretroBiosNote>[...notes, ...verdict.notes],
      );
    }
    final bundled = entry.bundledPath == null ? null : environment.bundledSha256[entry.bundledPath];
    if (bundled != null && facts.sha256 == bundled) {
      return LibretroBiosEntryResult(
        entry: entry,
        status: LibretroBiosStatus.verified,
        need: LibretroBiosNeed.bundled,
        neededNow: entry.bundledRequired,
        cores: cores,
        expected: expected,
        found: used,
        copies: <LibretroBiosFoundFile>[used],
        facts: facts,
        notes: <LibretroBiosNote>[...notes, const LibretroBiosNote('biosBundledMatch')],
      );
    }
    final verdict = _verdict(entry, used, facts);
    return LibretroBiosEntryResult(
      entry: entry,
      status: verdict.status,
      need: LibretroBiosNeed.bundled,
      neededNow: entry.bundledRequired,
      cores: cores,
      expected: expected,
      found: used,
      copies: <LibretroBiosFoundFile>[used],
      facts: facts,
      matchedDump: verdict.dump,
      notes: <LibretroBiosNote>[...notes, ...verdict.notes],
    );
  }

  /// Bundled entries whose folder exists (`System/PPSSPP`), read in [run].
  final Set<String> _bundledFolders = <String>{};

  /// Copies of a game-folder file in game folders the core does not read
  /// for the games that need it, by entry.
  final Map<String, List<String>> _otherFolderCopies = <String, List<String>>{};
}

class _Verdict {
  const _Verdict(this.status, this.notes, [this.dump]);

  final LibretroBiosStatus status;
  final List<LibretroBiosNote> notes;
  final LibretroBiosDump? dump;
}
