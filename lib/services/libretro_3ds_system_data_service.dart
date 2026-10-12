import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:io' as io show ZLibDecoder;
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:archive/archive_io.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:path/path.dart' as p;

import 'diagnostics_directory.dart';
import 'libretro_core_option_store.dart' show LibretroSessionProbe;
import 'libretro_internal_service.dart';
import 'logger_service.dart';

/// What one element of an import source is, once recognized by its content
/// and its relative path (never by the name of the container alone).
enum Libretro3dsItemKind {
  /// `sysdata/keys.txt` (also accepted as `aes_keys.txt`): AES key file,
  /// optional with the built-in key blob of the core. Installed only with
  /// `includeKeys`.
  keys,

  /// `sysdata/seeddb.bin`: title seeds.
  seeddb,

  /// CFG save `nand/data/<id0>/sysdata/00010017/00000000/config`
  /// (0x8000 bytes), installed under the destination id0.
  config,

  /// NAND title content `nand/<id0>/title/<high>/<low>/content/...`,
  /// installed under the destination id0.
  title,

  /// Console-unique data (`SecureInfo_A`, `LocalFriendCodeSeed_B`,
  /// `movable.sed`, `otp.bin`, `mcu.dat`): identifies the console, excluded
  /// unless `includeConsoleUnique`.
  consoleUnique,

  /// Listed, never copied.
  ignored,

  /// Refused with a [Libretro3dsRejection].
  rejected,
}

/// Why an element (or a whole container) is refused.
enum Libretro3dsRejection {
  /// Raw NAND image (`nand.bin`, `*.img`, `ctrnand*`, `twln*`,
  /// `essential.exefs`, or an `NCSD` header): encrypted per console, never
  /// read by the core.
  rawNandImage,

  /// 7z, rar, gzip, xz, bzip2, zstd, tar or a nested archive: only ZIP is
  /// decoded (surface kept small on purpose).
  unsupportedArchive,

  /// More entries than the limit (ZIP or folder walk).
  tooManyEntries,

  /// More bytes in total than the limit.
  tooLarge,

  /// One file larger than the per-file limit.
  fileTooLarge,

  /// `..`, absolute path, drive letter, backslash, NUL or empty segment.
  unsafeEntry,

  /// Symbolic link entry (ZIP `isSymbolicLink` or mode `0xA000`, or a link
  /// in a folder).
  symbolicLink,

  /// Content does not match the recognized file (size, header, text),
  /// an unreadable or corrupt ZIP, an encrypted entry, or a duplicate target.
  invalid,
}

/// What an install does with a recognized element.
enum Libretro3dsPlanAction {
  /// The destination does not exist.
  create,

  /// The destination exists with different content; it is backed up first.
  replace,

  /// The destination exists with the same size and SHA-256.
  skipIdentical,
}

/// Final state of one plan element after [Libretro3dsSystemDataService.install].
enum Libretro3dsInstallStatus {
  installed,
  replaced,
  skippedIdentical,

  /// Keys or console-unique data left out by the install flags.
  excluded,
  ignored,
  rejected,

  /// Staging, verification, backup or rename failed (raw detail attached).
  failed,

  /// Installed earlier in the same pass, then put back after a later
  /// failure (replaced files restored from this pass's backup, created files
  /// removed).
  rolledBack,

  /// Not reached because an earlier element failed.
  notAttempted,
}

/// Why an operation is refused before touching any file.
enum Libretro3dsSystemDataError {
  /// A libretro session is active or launching (or the probe failed).
  sessionActive,

  /// No backup folder exists under `Backups/Azahar`.
  noBackup,
}

/// Region fonts the core has no open-source replacement for, as NAND
/// titles `0004009b/<low>` (`00014002` is the shared standard font).
enum Libretro3dsRegionFont {
  chn('00014102'),
  kor('00014202'),
  twn('00014302');

  const Libretro3dsRegionFont(this.titleLow);

  /// Low title id under `title/0004009b/`.
  final String titleLow;
}

/// How a source path was read.
enum Libretro3dsSourceKind { zip, folder, file }

/// Typed refusal; [technicalDetail] is a raw diagnostic, never a user
/// message.
class Libretro3dsSystemDataException implements Exception {
  const Libretro3dsSystemDataException(this.error, {this.technicalDetail});

  final Libretro3dsSystemDataError error;
  final String? technicalDetail;

  @override
  String toString() =>
      'Libretro3dsSystemDataException(${error.name}'
      '${technicalDetail == null ? '' : ': $technicalDetail'})';
}

/// Bounds of an analysis (ZIP, folder, plain files).
class Libretro3dsImportLimits {
  const Libretro3dsImportLimits({
    this.maxZipEntries = 2000,
    this.maxTotalBytes = 1 << 30,
    this.maxFileBytes = 512 << 20,
    this.maxFolderEntries = 5000,
    this.maxFolderDepth = 8,
    this.maxKeysBytes = 64 << 10,
    this.maxSeeddbBytes = 1 << 20,
    this.maxConsoleUniqueBytes = 1 << 20,
  });

  final int maxZipEntries;
  final int maxTotalBytes;
  final int maxFileBytes;
  final int maxFolderEntries;
  final int maxFolderDepth;
  final int maxKeysBytes;
  final int maxSeeddbBytes;
  final int maxConsoleUniqueBytes;
}

/// One file of the user directory, as the inventory sees it (read only).
class Libretro3dsInventoryFile {
  const Libretro3dsInventoryFile({
    required this.relativePath,
    required this.exists,
    required this.size,
  });

  /// Relative to the user directory, raw (never translated).
  final String relativePath;
  final bool exists;
  final int size;
}

/// Read-only state of `Saves/Azahar/Azahar` (nothing is created).
class Libretro3dsInventory {
  const Libretro3dsInventory({
    required this.userDirectory,
    required this.exists,
    required this.keys,
    required this.seeddb,
    required this.config,
    required this.titleCount,
    required this.titleFileCount,
    required this.titleBytes,
    required this.fonts,
    required this.consoleUnique,
  });

  /// Absolute path of the core's user directory.
  final String userDirectory;
  final bool exists;
  final Libretro3dsInventoryFile keys;
  final Libretro3dsInventoryFile seeddb;
  final Libretro3dsInventoryFile config;

  /// Distinct `<high>/<low>` NAND titles with at least one content file.
  final int titleCount;

  /// Content files of those titles.
  final int titleFileCount;
  final int titleBytes;

  /// Presence of each region font title (`.app` under its `content`).
  final Map<Libretro3dsRegionFont, bool> fonts;

  /// The five console-unique files, in [Libretro3dsSystemDataService.consoleUniqueTargets] order.
  final List<Libretro3dsInventoryFile> consoleUnique;

  bool get anyConsoleUnique => consoleUnique.any((file) => file.exists);
  bool get allFontsPresent => fonts.values.every((present) => present);
}

/// One element of an import plan.
class Libretro3dsImportItem {
  const Libretro3dsImportItem._({
    required this.sourceName,
    required this.sourceEntry,
    required this.sourceKind,
    required this.kind,
    required this.size,
    this.relativeTarget,
    this.rejection,
    this.action,
    this.exists = false,
    this.identical = false,
    this.technicalDetail,
    this.sourceHash,
    _ItemLocator? locator,
  }) : _locator = locator;

  /// Base name of the container (ZIP, folder or file), raw.
  final String sourceName;

  /// Path inside the container as found (the file name for a plain file),
  /// raw.
  final String sourceEntry;
  final Libretro3dsSourceKind sourceKind;
  final Libretro3dsItemKind kind;

  /// Destination relative to the user directory, raw; null for
  /// [Libretro3dsItemKind.ignored] and for a rejected container.
  final String? relativeTarget;
  final Libretro3dsRejection? rejection;

  /// Null for ignored and rejected elements.
  final Libretro3dsPlanAction? action;
  final int size;

  /// The destination file exists.
  final bool exists;

  /// The destination has the same size and SHA-256.
  final bool identical;

  /// Raw diagnostic of a rejection.
  final String? technicalDetail;

  /// SHA-256 (hex) of the source when it was computed during analysis.
  final String? sourceHash;

  final _ItemLocator? _locator;

  bool get installable =>
      action != null && action != Libretro3dsPlanAction.skipIdentical;
}

/// Result of [Libretro3dsSystemDataService.analyze]: plain data, safe to
/// hand back from an isolate.
class Libretro3dsImportPlan {
  const Libretro3dsImportPlan({
    required this.userDirectory,
    required this.sources,
    required this.items,
  });

  /// Absolute path of the destination user directory at analysis time.
  final String userDirectory;

  /// Source paths as given.
  final List<String> sources;
  final List<Libretro3dsImportItem> items;

  Iterable<Libretro3dsImportItem> get recognized => items.where(
    (item) =>
        item.kind != Libretro3dsItemKind.ignored &&
        item.kind != Libretro3dsItemKind.rejected,
  );
  Iterable<Libretro3dsImportItem> get rejected =>
      items.where((item) => item.kind == Libretro3dsItemKind.rejected);
  Iterable<Libretro3dsImportItem> get ignored =>
      items.where((item) => item.kind == Libretro3dsItemKind.ignored);

  /// Elements an install would write with both flags set.
  Iterable<Libretro3dsImportItem> get installable =>
      items.where((item) => item.installable);

  bool get hasRecognized => recognized.isNotEmpty;

  int get installableBytes =>
      installable.fold(0, (total, item) => total + item.size);
}

/// Per-element outcome of an install.
class Libretro3dsInstallResult {
  const Libretro3dsInstallResult({
    required this.item,
    required this.status,
    this.backupPath,
    this.technicalDetail,
  });

  final Libretro3dsImportItem item;
  final Libretro3dsInstallStatus status;

  /// Absolute path of the backup of the replaced file (raw).
  final String? backupPath;

  /// Raw failure code/detail.
  final String? technicalDetail;
}

/// Outcome of [Libretro3dsSystemDataService.install].
class Libretro3dsInstallReport {
  const Libretro3dsInstallReport({
    required this.stamp,
    required this.results,
    required this.rolledBack,
    this.backupDirectory,
    this.journalPath,
    this.failure,
  });

  /// `yyyyMMdd-HHmmss` (UTC) of this pass.
  final String stamp;

  /// In plan order.
  final List<Libretro3dsInstallResult> results;

  /// A failure happened and the elements committed before it were put back.
  final bool rolledBack;

  /// `Backups/Azahar/<stamp>` when at least one file was replaced.
  final String? backupDirectory;

  /// `Documents/Diagnostics/libretro-3ds-import-<stamp>.jsonl` when written.
  final String? journalPath;

  /// Raw detail of the first failure.
  final String? failure;

  int count(Libretro3dsInstallStatus status) =>
      results.where((result) => result.status == status).length;

  bool get succeeded =>
      !rolledBack && count(Libretro3dsInstallStatus.failed) == 0;
}

/// Per-file outcome of a restore.
class Libretro3dsRestoreResult {
  const Libretro3dsRestoreResult({
    required this.relativePath,
    required this.restored,
    this.technicalDetail,
  });

  final String relativePath;
  final bool restored;
  final String? technicalDetail;
}

/// Outcome of [Libretro3dsSystemDataService.restoreLastBackup].
class Libretro3dsRestoreReport {
  const Libretro3dsRestoreReport({
    required this.backupDirectory,
    required this.results,
    this.currentBackupDirectory,
    this.journalPath,
  });

  /// The backup that was restored.
  final String backupDirectory;

  /// Where the files overwritten by the restore were copied first.
  final String? currentBackupDirectory;
  final List<Libretro3dsRestoreResult> results;
  final String? journalPath;

  int get restoredCount => results.where((result) => result.restored).length;
  int get failedCount => results.length - restoredCount;
}

/// Nintendo 3DS system data of the embedded azahar core: read-only
/// inventory of `Documents/Libretro/Saves/Azahar/Azahar`, analysis of
/// ZIP / folder / file sources into a typed plan, staged and verified
/// install with per-file backups, and restore of the last backup.
///
/// Writes only under `Saves/Azahar` (user directory and staging),
/// `Backups/Azahar` and `Documents/Diagnostics`. The user directory is
/// created at install only. Install and restore are refused while a libretro
/// session is active or launching, through the same probe as
/// `LibretroCoreOptionStore`.
class Libretro3dsSystemDataService {
  Libretro3dsSystemDataService({
    Future<Directory> Function()? savesDirectory,
    Future<Directory> Function()? backupsDirectory,
    Future<Directory> Function()? diagnosticsDirectory,
    LibretroSessionProbe? sessionProbe,
    this.limits = const Libretro3dsImportLimits(),
    this.now = DateTime.now,
    this.beforeCommit,
  }) : savesDirectory =
           savesDirectory ?? LibretroInternalService.savesDirectory,
       backupsDirectory = backupsDirectory ?? _defaultBackupsDirectory,
       diagnosticsDirectory =
           diagnosticsDirectory ?? DiagnosticsDirectory.directory,
       sessionProbe = sessionProbe ?? LibretroInternalBridge.isSessionActive;

  /// Folder of the core under `Saves` and `Backups` (its `SafeFolderName`).
  static const String coreFolderName = 'Azahar';

  /// id0 of the destination NAND (Citra/Azahar layout).
  static const String destinationId0 = '00000000000000000000000000000000';

  static const String keysTarget = 'sysdata/keys.txt';
  static const String seeddbTarget = 'sysdata/seeddb.bin';
  static const String configTarget =
      'nand/data/$destinationId0/sysdata/00010017/00000000/config';
  static const String titleRoot = 'nand/$destinationId0/title';

  /// Console-unique files by lower-case base name → destination.
  static const Map<String, String> consoleUniqueTargets = {
    'secureinfo_a': 'nand/rw/sys/SecureInfo_A',
    'localfriendcodeseed_b': 'nand/rw/sys/LocalFriendCodeSeed_B',
    'movable.sed': 'nand/private/movable.sed',
    'otp.bin': 'sysdata/otp.bin',
    'mcu.dat': 'sysdata/mcu.dat',
  };

  /// Prefix of the staging folder created beside the user directory.
  static const String stagingPrefix = '.neostation-3ds-import-';

  /// Prefix of the staging folder of a restore.
  static const String restoreStagingPrefix = '.neostation-3ds-restore-';

  /// `Documents/Diagnostics/<prefix><stamp>.jsonl`.
  static const String journalPrefix = 'libretro-3ds-import-';

  /// CFG save size and header bounds (`SaveFileConfig`).
  static const int configFileSize = 0x8000;
  static const int configMaxBlockEntries = 1479;

  /// Folders of a Citra/Azahar user directory that never hold system data.
  static const Set<String> _prunedFolders = {
    'sdmc',
    'cache',
    'states',
    'shaders',
    'log',
    'logs',
    'dump',
    'screenshots',
    'load',
    'cheats',
    '__macosx',
    '.git',
  };

  static final RegExp _hex32 = RegExp(r'^[0-9a-f]{32}$');
  static final RegExp _hex8 = RegExp(r'^[0-9a-f]{8}$');
  static final RegExp _titleFile = RegExp(r'^[0-9a-f]{1,8}\.(app|tmd|cmd)$');
  static final RegExp _keyLine = RegExp(r'^[A-Za-z0-9_]+=[0-9A-Fa-f]+$');
  static final RegExp _keyName = RegExp(
    r'^(slot0x[0-9A-Fa-f]{2}Key[XYN]?|generator|common\d+)=',
    caseSensitive: false,
  );
  static final RegExp _backupName = RegExp(r'^(\d{8}-\d{6})(?:-(\d+))?$');

  static final _log = LoggerService.instance;

  /// `Documents/Libretro/Saves` in production.
  final Future<Directory> Function() savesDirectory;

  /// `Documents/Libretro/Backups/Azahar` in production.
  final Future<Directory> Function() backupsDirectory;

  /// `Documents/Diagnostics` in production (created on first use).
  final Future<Directory> Function() diagnosticsDirectory;
  final LibretroSessionProbe sessionProbe;
  final Libretro3dsImportLimits limits;
  final DateTime Function() now;

  /// Test hook run just before each element is moved into place; throwing
  /// simulates a commit failure.
  @visibleForTesting
  final Future<void> Function(String relativeTarget)? beforeCommit;

  static Future<Directory> _defaultBackupsDirectory() async => Directory(
    p.join(
      (await LibretroInternalService.rootDirectory()).path,
      'Backups',
      coreFolderName,
    ),
  );

  // ---------------------------------------------------------------------
  // Roots
  // ---------------------------------------------------------------------

  /// `<savesDirectory>/Azahar/Azahar`, created only by [install].
  Future<Directory> userDirectory() async => Directory(
    p.join((await savesDirectory()).path, coreFolderName, coreFolderName),
  );

  /// Backups by stamp, newest first (never deleted by the app).
  Future<List<Directory>> backups() async {
    final root = await backupsDirectory();
    if (!await root.exists()) return const [];
    final found = <(String, int, Directory)>[];
    await for (final entity in root.list(followLinks: false)) {
      if (entity is! Directory) continue;
      final match = _backupName.firstMatch(p.basename(entity.path));
      if (match == null) continue;
      found.add((
        match.group(1)!,
        int.tryParse(match.group(2) ?? '1') ?? 1,
        entity,
      ));
    }
    found.sort((a, b) {
      final byStamp = b.$1.compareTo(a.$1);
      return byStamp != 0 ? byStamp : b.$2.compareTo(a.$2);
    });
    return [for (final entry in found) entry.$3];
  }

  // ---------------------------------------------------------------------
  // Inventory (read only)
  // ---------------------------------------------------------------------

  Future<Libretro3dsInventory> inventory() async {
    final user = await userDirectory();
    final exists = await user.exists();

    Future<Libretro3dsInventoryFile> status(String relative) async {
      final file = File(p.joinAll([user.path, ...relative.split('/')]));
      if (!exists || !await file.exists()) {
        return Libretro3dsInventoryFile(
          relativePath: relative,
          exists: false,
          size: 0,
        );
      }
      return Libretro3dsInventoryFile(
        relativePath: relative,
        exists: true,
        size: await file.length(),
      );
    }

    var titleCount = 0;
    var titleFileCount = 0;
    var titleBytes = 0;
    final fonts = {
      for (final font in Libretro3dsRegionFont.values) font: false,
    };
    final titles = Directory(p.joinAll([user.path, ...titleRoot.split('/')]));
    if (exists && await titles.exists()) {
      final seen = <String>{};
      await for (final entity in titles.list(
        recursive: true,
        followLinks: false,
      )) {
        if (entity is! File) continue;
        final relative = p
            .split(p.relative(entity.path, from: titles.path))
            .map((segment) => segment.toLowerCase())
            .toList();
        // <high>/<low>/content/<file> or <high>/<low>/content/cmd/<file>.
        if (relative.length < 4 || relative[2] != 'content') continue;
        if (!_hex8.hasMatch(relative[0]) || !_hex8.hasMatch(relative[1])) {
          continue;
        }
        if (!_titleFile.hasMatch(relative.last)) continue;
        if (seen.add('${relative[0]}/${relative[1]}')) titleCount++;
        titleFileCount++;
        titleBytes += await entity.length();
        if (relative[0] == '0004009b' && relative.last.endsWith('.app')) {
          for (final font in Libretro3dsRegionFont.values) {
            if (relative[1] == font.titleLow) fonts[font] = true;
          }
        }
      }
    }

    return Libretro3dsInventory(
      userDirectory: user.path,
      exists: exists,
      keys: await status(keysTarget),
      seeddb: await status(seeddbTarget),
      config: await status(configTarget),
      titleCount: titleCount,
      titleFileCount: titleFileCount,
      titleBytes: titleBytes,
      fonts: fonts,
      consoleUnique: [
        for (final target in consoleUniqueTargets.values) await status(target),
      ],
    );
  }

  // ---------------------------------------------------------------------
  // Analysis
  // ---------------------------------------------------------------------

  /// Analyzes [sources] (each a ZIP, a folder or a plain file) against the
  /// current user directory. Read only.
  Future<Libretro3dsImportPlan> analyze(List<String> sources) async =>
      analyzeSources(
        sources,
        userDirectory: (await userDirectory()).path,
        limits: limits,
      );

  /// [analyze] with an explicit destination, usable from `Isolate.run`.
  static Future<Libretro3dsImportPlan> analyzeSources(
    List<String> sources, {
    required String userDirectory,
    Libretro3dsImportLimits limits = const Libretro3dsImportLimits(),
  }) async {
    final context = _AnalysisContext(
      userDirectory: userDirectory,
      limits: limits,
    );
    for (final source in sources) {
      final name = p.basename(source);
      try {
        final type = await FileSystemEntity.type(source, followLinks: false);
        switch (type) {
          case FileSystemEntityType.directory:
            await _analyzeFolder(Directory(source), name, context);
          case FileSystemEntityType.file:
            await _analyzeFile(File(source), name, context);
          case FileSystemEntityType.link:
            context.add(
              _rejectedContainer(
                name,
                Libretro3dsSourceKind.file,
                Libretro3dsRejection.symbolicLink,
                source,
              ),
            );
          default:
            context.add(
              _rejectedContainer(
                name,
                Libretro3dsSourceKind.file,
                Libretro3dsRejection.invalid,
                'not found: $name',
              ),
            );
        }
      } catch (error) {
        context.add(
          _rejectedContainer(
            name,
            Libretro3dsSourceKind.file,
            Libretro3dsRejection.invalid,
            _detail(error),
          ),
        );
      }
    }
    context.items.sort(_planOrder);
    return Libretro3dsImportPlan(
      userDirectory: userDirectory,
      sources: List.unmodifiable(sources),
      items: List.unmodifiable(context.items),
    );
  }

  static int _planOrder(Libretro3dsImportItem a, Libretro3dsImportItem b) {
    int rank(Libretro3dsImportItem item) => switch (item.kind) {
      Libretro3dsItemKind.config => 0,
      Libretro3dsItemKind.seeddb => 1,
      Libretro3dsItemKind.keys => 2,
      Libretro3dsItemKind.title => 3,
      Libretro3dsItemKind.consoleUnique => 4,
      Libretro3dsItemKind.ignored => 5,
      Libretro3dsItemKind.rejected => 6,
    };
    final byKind = rank(a).compareTo(rank(b));
    if (byKind != 0) return byKind;
    final byTarget = (a.relativeTarget ?? '').compareTo(b.relativeTarget ?? '');
    if (byTarget != 0) return byTarget;
    final bySource = a.sourceName.compareTo(b.sourceName);
    return bySource != 0 ? bySource : a.sourceEntry.compareTo(b.sourceEntry);
  }

  static Libretro3dsImportItem _rejectedContainer(
    String name,
    Libretro3dsSourceKind kind,
    Libretro3dsRejection rejection,
    String? detail,
  ) => Libretro3dsImportItem._(
    sourceName: name,
    sourceEntry: name,
    sourceKind: kind,
    kind: Libretro3dsItemKind.rejected,
    rejection: rejection,
    size: 0,
    technicalDetail: detail,
  );

  static Future<void> _analyzeFile(
    File file,
    String name,
    _AnalysisContext context,
  ) async {
    final length = await file.length();
    final head = await _readPrefix(file, 0x200);
    if (_isZipSignature(head)) {
      await _analyzeZip(file, name, context);
      return;
    }
    final archive = _otherArchiveSignature(head, name);
    if (archive != null) {
      context.add(
        _rejectedContainer(
          name,
          Libretro3dsSourceKind.file,
          Libretro3dsRejection.unsupportedArchive,
          archive,
        ),
      );
      return;
    }
    await _classify(
      _PlainSourceFile(file, name, length, Libretro3dsSourceKind.file),
      containerName: name,
      sourceKind: Libretro3dsSourceKind.file,
      context: context,
    );
  }

  static Future<void> _analyzeZip(
    File file,
    String name,
    _AnalysisContext context,
  ) async {
    final limits = context.limits;
    void reject(Libretro3dsRejection rejection, [String? detail]) {
      context.add(
        _rejectedContainer(name, Libretro3dsSourceKind.zip, rejection, detail),
      );
    }

    final InputFileStream input;
    try {
      input = InputFileStream(file.path);
    } catch (error) {
      reject(Libretro3dsRejection.invalid, _detail(error));
      return;
    }
    try {
      final decoder = ZipDecoder();
      final Archive archive;
      try {
        archive = decoder.decodeStream(input);
      } catch (error) {
        reject(Libretro3dsRejection.invalid, _detail(error));
        return;
      }
      if (decoder.directory.filePosition < 0) {
        reject(Libretro3dsRejection.invalid, 'no central directory');
        return;
      }
      if (archive.length > limits.maxZipEntries) {
        reject(
          Libretro3dsRejection.tooManyEntries,
          '${archive.length} entries',
        );
        return;
      }
      var declaredTotal = 0;
      for (final entry in archive.files) {
        final unsafe = _unsafeEntryName(entry.name);
        if (unsafe != null) {
          reject(Libretro3dsRejection.unsafeEntry, '$unsafe: ${entry.name}');
          return;
        }
        if (entry.isSymbolicLink || (entry.mode & 0xF000) == 0xA000) {
          reject(Libretro3dsRejection.symbolicLink, entry.name);
          return;
        }
        if (entry.isFile) {
          if (entry.size > limits.maxFileBytes) {
            reject(
              Libretro3dsRejection.fileTooLarge,
              '${entry.name}: ${entry.size} bytes',
            );
            return;
          }
          declaredTotal += entry.size;
        }
      }
      if (declaredTotal > limits.maxTotalBytes) {
        reject(Libretro3dsRejection.tooLarge, '$declaredTotal bytes');
        return;
      }
      for (final entry in archive.files) {
        if (!entry.isFile) continue;
        if (_isNoise(entry.name)) continue;
        await _classify(
          _ZipSourceFile(file.path, entry),
          containerName: name,
          sourceKind: Libretro3dsSourceKind.zip,
          context: context,
        );
      }
    } finally {
      await input.close();
    }
  }

  static Future<void> _analyzeFolder(
    Directory root,
    String name,
    _AnalysisContext context,
  ) async {
    final limits = context.limits;
    final found = <_PlainSourceFile>[];
    final links = <String>[];
    var entries = 0;

    Future<bool> visit(Directory directory, int depth) async {
      await for (final entity in directory.list(followLinks: false)) {
        if (++entries > limits.maxFolderEntries) return false;
        final relative = p
            .split(p.relative(entity.path, from: root.path))
            .join('/');
        if (entity is Link) {
          links.add(relative);
          continue;
        }
        if (entity is Directory) {
          if (_prunedFolders.contains(p.basename(entity.path).toLowerCase())) {
            continue;
          }
          if (depth < limits.maxFolderDepth &&
              !await visit(entity, depth + 1)) {
            return false;
          }
          continue;
        }
        if (entity is! File) continue;
        if (_isNoise(relative)) continue;
        found.add(
          _PlainSourceFile(
            entity,
            relative,
            await entity.length(),
            Libretro3dsSourceKind.folder,
          ),
        );
      }
      return true;
    }

    final bool complete;
    try {
      complete = await visit(root, 1);
    } catch (error) {
      context.add(
        _rejectedContainer(
          name,
          Libretro3dsSourceKind.folder,
          Libretro3dsRejection.invalid,
          _detail(error),
        ),
      );
      return;
    }
    if (!complete) {
      context.add(
        _rejectedContainer(
          name,
          Libretro3dsSourceKind.folder,
          Libretro3dsRejection.tooManyEntries,
          'more than ${limits.maxFolderEntries} entries',
        ),
      );
      return;
    }
    for (final link in links) {
      context.add(
        Libretro3dsImportItem._(
          sourceName: name,
          sourceEntry: link,
          sourceKind: Libretro3dsSourceKind.folder,
          kind: Libretro3dsItemKind.rejected,
          rejection: Libretro3dsRejection.symbolicLink,
          size: 0,
          technicalDetail: link,
        ),
      );
    }
    for (final file in found) {
      await _classify(
        file,
        containerName: name,
        sourceKind: Libretro3dsSourceKind.folder,
        context: context,
      );
    }
  }

  /// Recognizes one file by its relative path, validates its content,
  /// compares it with the destination and records the item.
  static Future<void> _classify(
    _SourceFile source, {
    required String containerName,
    required Libretro3dsSourceKind sourceKind,
    required _AnalysisContext context,
  }) async {
    final limits = context.limits;
    final entry = source.entryName;
    final recognition = _recognize(entry);

    Libretro3dsImportItem item({
      required Libretro3dsItemKind kind,
      String? target,
      Libretro3dsRejection? rejection,
      Libretro3dsPlanAction? action,
      bool exists = false,
      bool identical = false,
      String? detail,
      String? hash,
    }) => Libretro3dsImportItem._(
      sourceName: containerName,
      sourceEntry: entry,
      sourceKind: sourceKind,
      kind: kind,
      relativeTarget: target,
      rejection: rejection,
      action: action,
      size: source.size,
      exists: exists,
      identical: identical,
      technicalDetail: detail,
      sourceHash: hash,
      locator: source.locator,
    );

    void rejected(
      Libretro3dsRejection rejection,
      String detail, {
      String? target,
    }) {
      context.add(
        item(
          kind: Libretro3dsItemKind.rejected,
          target: target,
          rejection: rejection,
          detail: detail,
        ),
      );
    }

    if (recognition.rejection != null) {
      rejected(recognition.rejection!, entry);
      return;
    }

    // Content before path: a raw NAND image or a nested archive is refused
    // whatever it is called.
    final Uint8List head;
    try {
      head = await source.prefix(0x200);
    } catch (error) {
      rejected(Libretro3dsRejection.invalid, _detail(error));
      return;
    }
    if (_isNcsdImage(head)) {
      rejected(Libretro3dsRejection.rawNandImage, 'NCSD header: $entry');
      return;
    }
    final archive = _isZipSignature(head)
        ? 'zip'
        : _otherArchiveSignature(head, entry);
    if (archive != null) {
      rejected(Libretro3dsRejection.unsupportedArchive, '$archive: $entry');
      return;
    }

    final kind = recognition.kind;
    final target = recognition.target;
    if (kind == Libretro3dsItemKind.ignored || target == null) {
      context.add(item(kind: Libretro3dsItemKind.ignored));
      return;
    }

    if (source.size > limits.maxFileBytes) {
      rejected(
        Libretro3dsRejection.fileTooLarge,
        '$entry: ${source.size} bytes',
        target: target,
      );
      return;
    }
    final String? invalid;
    try {
      invalid = await _validateContent(kind, source, head, limits);
    } catch (error) {
      rejected(Libretro3dsRejection.invalid, _detail(error), target: target);
      return;
    }
    if (invalid != null) {
      rejected(Libretro3dsRejection.invalid, invalid, target: target);
      return;
    }
    if (!context.claim(target)) {
      rejected(
        Libretro3dsRejection.invalid,
        'duplicate target $target in ${context.ownerOf(target)}',
        target: target,
      );
      return;
    }
    if (context.recognizedBytes + source.size > limits.maxTotalBytes) {
      rejected(
        Libretro3dsRejection.tooLarge,
        'more than ${limits.maxTotalBytes} bytes selected',
        target: target,
      );
      return;
    }
    context.recognizedBytes += source.size;
    context.owners[target] = containerName;

    final destination = File(
      p.joinAll([context.userDirectory, ...target.split('/')]),
    );
    var exists = false;
    var identical = false;
    String? hash;
    try {
      exists = await destination.exists();
      if (exists && await destination.length() == source.size) {
        hash = await source.contentSha256();
        identical = hash == await _fileSha256(destination);
      }
    } catch (error) {
      rejected(Libretro3dsRejection.invalid, _detail(error), target: target);
      return;
    }
    context.add(
      item(
        kind: kind,
        target: target,
        action: identical
            ? Libretro3dsPlanAction.skipIdentical
            : exists
            ? Libretro3dsPlanAction.replace
            : Libretro3dsPlanAction.create,
        exists: exists,
        identical: identical,
        hash: hash,
      ),
    );
  }

  /// Kind and destination of a relative path (case-insensitive, any
  /// container prefix tolerated, `sdmc` trees ignored).
  static _Recognition _recognize(String relativePath) {
    final segments = relativePath
        .split('/')
        .where((segment) => segment.isNotEmpty)
        .map((segment) => segment.toLowerCase())
        .toList();
    if (segments.isEmpty) return const _Recognition.ignored();
    final name = segments.last;

    if (_isRawNandName(name)) {
      return const _Recognition.rejected(Libretro3dsRejection.rawNandImage);
    }
    if (segments.any(
      (segment) => segment == 'sdmc' || segment == 'nintendo 3ds',
    )) {
      return const _Recognition.ignored();
    }
    if (name == 'keys.txt' || name == 'aes_keys.txt') {
      return const _Recognition(Libretro3dsItemKind.keys, keysTarget);
    }
    if (name == 'seeddb.bin') {
      return const _Recognition(Libretro3dsItemKind.seeddb, seeddbTarget);
    }
    final consoleUnique = consoleUniqueTargets[name];
    if (consoleUnique != null) {
      return _Recognition(Libretro3dsItemKind.consoleUnique, consoleUnique);
    }
    if (name == 'config') {
      // data/<id0>/sysdata/00010017/00000000/config, or the file alone.
      final n = segments.length;
      if (n == 1 ||
          (n >= 6 &&
              segments[n - 2] == '00000000' &&
              segments[n - 3] == '00010017' &&
              segments[n - 4] == 'sysdata' &&
              _hex32.hasMatch(segments[n - 5]) &&
              segments[n - 6] == 'data')) {
        return const _Recognition(Libretro3dsItemKind.config, configTarget);
      }
      return const _Recognition.ignored();
    }
    if (_titleFile.hasMatch(name)) {
      // title/<high>/<low>/content/<file> or .../content/cmd/<file>.
      final n = segments.length;
      final inCmd = n >= 6 && segments[n - 2] == 'cmd';
      final contentAt = inCmd ? n - 3 : n - 2;
      if (contentAt >= 3 &&
          segments[contentAt] == 'content' &&
          _hex8.hasMatch(segments[contentAt - 1]) &&
          _hex8.hasMatch(segments[contentAt - 2]) &&
          segments[contentAt - 3] == 'title' &&
          (!inCmd || name.endsWith('.cmd'))) {
        final high = segments[contentAt - 2];
        final low = segments[contentAt - 1];
        final tail = inCmd ? 'cmd/$name' : name;
        return _Recognition(
          Libretro3dsItemKind.title,
          '$titleRoot/$high/$low/content/$tail',
        );
      }
      return const _Recognition.ignored();
    }
    return const _Recognition.ignored();
  }

  static bool _isRawNandName(String lowerName) =>
      lowerName == 'nand.bin' ||
      lowerName.endsWith('.img') ||
      lowerName.startsWith('ctrnand') ||
      lowerName.startsWith('twln') ||
      lowerName == 'essential.exefs';

  /// Entries never listed: `__MACOSX`, Finder/Explorer metadata.
  static bool _isNoise(String relativePath) {
    final segments = relativePath.split('/').where((s) => s.isNotEmpty);
    if (segments.isEmpty) return true;
    if (segments.any((segment) => segment.toLowerCase() == '__macosx')) {
      return true;
    }
    final name = segments.last.toLowerCase();
    return name == '.ds_store' ||
        name == 'thumbs.db' ||
        name == 'desktop.ini' ||
        name.startsWith('._');
  }

  /// Null when the content matches [kind]; else a raw reason.
  static Future<String?> _validateContent(
    Libretro3dsItemKind kind,
    _SourceFile source,
    Uint8List head,
    Libretro3dsImportLimits limits,
  ) async {
    final size = source.size;
    switch (kind) {
      case Libretro3dsItemKind.keys:
        if (size > limits.maxKeysBytes) return 'keys file of $size bytes';
        final bytes = await source.prefix(size);
        return _validateKeysText(bytes);
      case Libretro3dsItemKind.seeddb:
        if (size > limits.maxSeeddbBytes) return 'seeddb of $size bytes';
        if (size < 16 || (size - 16) % 32 != 0) {
          return 'seeddb size $size is not 16 + 32·n';
        }
        final count = ByteData.sublistView(head).getUint32(0, Endian.little);
        final entries = (size - 16) ~/ 32;
        if (count > entries) return 'seeddb declares $count of $entries seeds';
        return null;
      case Libretro3dsItemKind.config:
        if (size != configFileSize) {
          return 'config of $size bytes, expected $configFileSize';
        }
        final view = ByteData.sublistView(head);
        final totalEntries = view.getUint16(0, Endian.little);
        final dataOffset = view.getUint16(2, Endian.little);
        if (totalEntries > configMaxBlockEntries) {
          return 'config total_entries $totalEntries';
        }
        if (dataOffset > configFileSize) {
          return 'config data_entries_offset 0x${dataOffset.toRadixString(16)}';
        }
        return null;
      case Libretro3dsItemKind.title:
        if (size == 0) return 'empty title file';
        return null;
      case Libretro3dsItemKind.consoleUnique:
        if (size == 0) return 'empty file';
        if (size > limits.maxConsoleUniqueBytes) {
          return 'console file of $size bytes';
        }
        return null;
      case Libretro3dsItemKind.ignored:
      case Libretro3dsItemKind.rejected:
        return null;
    }
  }

  /// ASCII text, `name=hex` lines (comments and blank lines allowed), at
  /// least one `slot0x..`, `generator` or `commonN` key.
  static String? _validateKeysText(Uint8List bytes) {
    if (bytes.isEmpty) return 'empty keys file';
    for (final byte in bytes) {
      if (byte == 0 ||
          byte > 0x7E ||
          (byte < 0x20 && byte != 0x0A && byte != 0x0D && byte != 0x09)) {
        return 'keys file is not ASCII text';
      }
    }
    final text = ascii.decode(bytes);
    var known = 0;
    for (final rawLine in const LineSplitter().convert(text)) {
      final line = rawLine.trim();
      if (line.isEmpty || line.startsWith('#') || line.startsWith(';')) {
        continue;
      }
      if (!_keyLine.hasMatch(line)) return 'keys line is not name=hex';
      if (_keyName.hasMatch(line)) known++;
    }
    return known == 0 ? 'no slot0x/generator/common key' : null;
  }

  static bool _isZipSignature(Uint8List head) =>
      head.length >= 4 &&
      head[0] == 0x50 &&
      head[1] == 0x4B &&
      ((head[2] == 0x03 && head[3] == 0x04) ||
          (head[2] == 0x05 && head[3] == 0x06) ||
          (head[2] == 0x07 && head[3] == 0x08));

  /// Name of a non-ZIP archive format by signature (or by extension when
  /// the signature is unknown), else null.
  static String? _otherArchiveSignature(Uint8List head, String name) {
    bool starts(List<int> magic) {
      if (head.length < magic.length) return false;
      for (var index = 0; index < magic.length; index++) {
        if (head[index] != magic[index]) return false;
      }
      return true;
    }

    if (starts(const [0x37, 0x7A, 0xBC, 0xAF, 0x27, 0x1C])) return '7z';
    if (starts(const [0x52, 0x61, 0x72, 0x21, 0x1A, 0x07])) return 'rar';
    if (starts(const [0x1F, 0x8B])) return 'gzip';
    if (starts(const [0xFD, 0x37, 0x7A, 0x58, 0x5A, 0x00])) return 'xz';
    if (starts(const [0x42, 0x5A, 0x68])) return 'bzip2';
    if (starts(const [0x28, 0xB5, 0x2F, 0xFD])) return 'zstd';
    if (head.length >= 0x106 &&
        head[0x101] == 0x75 &&
        head[0x102] == 0x73 &&
        head[0x103] == 0x74 &&
        head[0x104] == 0x61 &&
        head[0x105] == 0x72) {
      return 'tar';
    }
    final lower = name.toLowerCase();
    for (final extension in const [
      '.7z',
      '.rar',
      '.zip',
      '.tar',
      '.tgz',
      '.gz',
      '.xz',
      '.bz2',
      '.zst',
    ]) {
      if (lower.endsWith(extension)) return 'archive extension $extension';
    }
    return null;
  }

  /// `NCSD` at 0x100: a full NAND image.
  static bool _isNcsdImage(Uint8List head) =>
      head.length >= 0x104 &&
      head[0x100] == 0x4E &&
      head[0x101] == 0x43 &&
      head[0x102] == 0x53 &&
      head[0x103] == 0x44;

  static String? _unsafeEntryName(String name) {
    if (name.isEmpty) return 'empty name';
    if (name.contains('\\')) return 'backslash';
    if (name.contains('\u0000')) return 'NUL character';
    if (name.startsWith('/')) return 'absolute path';
    if (RegExp(r'^[A-Za-z]:').hasMatch(name)) return 'drive letter';
    final segments = name.split('/');
    for (var index = 0; index < segments.length; index++) {
      final segment = segments[index];
      if (segment == '..') return 'parent reference';
      if (segment == '.') return 'current directory reference';
      if (segment.isEmpty && index != segments.length - 1) {
        return 'empty segment';
      }
    }
    return null;
  }

  // ---------------------------------------------------------------------
  // Install
  // ---------------------------------------------------------------------

  /// Installs the installable elements of [plan]: staging beside the user
  /// directory, byte-for-byte verification (size + SHA-256), backup of each
  /// replaced file under `Backups/Azahar/<stamp>/<relative path>`, then one
  /// rename per file. On a failure the elements already moved in this pass
  /// are put back (from this pass's backup, or removed when created) and
  /// the report says so. Refused while a session is active or launching.
  Future<Libretro3dsInstallReport> install(
    Libretro3dsImportPlan plan, {
    bool includeConsoleUnique = false,
    bool includeKeys = false,
  }) async {
    await _refuseWhenSessionActive();
    final stamp = _stamp(now());
    final user = await userDirectory();
    final backupsRoot = (await backupsDirectory()).path;
    final staging = Directory(p.join(user.parent.path, '$stagingPrefix$stamp'));
    final journal = _Journal(
      this,
      '$journalPrefix$stamp.jsonl',
      redactions: _redactions(
        user,
        backupsRoot,
        staging,
        sources: plan.sources,
      ),
    );
    journal.add({
      'event': 'install',
      'stamp': stamp,
      'sources': [for (final source in plan.sources) p.basename(source)],
      'includeConsoleUnique': includeConsoleUnique,
      'includeKeys': includeKeys,
    });

    final results = List<Libretro3dsInstallResult?>.filled(
      plan.items.length,
      null,
    );
    final pending = <_Pending>[];
    for (var index = 0; index < plan.items.length; index++) {
      final item = plan.items[index];
      Libretro3dsInstallStatus? status;
      switch (item.kind) {
        case Libretro3dsItemKind.ignored:
          status = Libretro3dsInstallStatus.ignored;
        case Libretro3dsItemKind.rejected:
          status = Libretro3dsInstallStatus.rejected;
        case Libretro3dsItemKind.keys:
          if (!includeKeys) status = Libretro3dsInstallStatus.excluded;
        case Libretro3dsItemKind.consoleUnique:
          if (!includeConsoleUnique) status = Libretro3dsInstallStatus.excluded;
        case Libretro3dsItemKind.seeddb:
        case Libretro3dsItemKind.config:
        case Libretro3dsItemKind.title:
          break;
      }
      if (status == null &&
          item.action == Libretro3dsPlanAction.skipIdentical) {
        status = Libretro3dsInstallStatus.skippedIdentical;
      }
      if (status == null &&
          (item.relativeTarget == null || item._locator == null)) {
        status = Libretro3dsInstallStatus.rejected;
      }
      if (status != null) {
        results[index] = Libretro3dsInstallResult(item: item, status: status);
        continue;
      }
      pending.add(_Pending(index, item));
    }

    var rolledBack = false;
    String? failure;
    Directory? backupDirectory;
    try {
      // Stage and verify everything first: a staging failure (disk full,
      // unreadable source) leaves the user directory untouched.
      var staged = true;
      if (pending.isNotEmpty) {
        try {
          await user.create(recursive: true);
          await staging.create(recursive: true);
        } catch (error) {
          failure = _detail(error);
          staged = false;
          for (final entry in pending) {
            results[entry.index] = Libretro3dsInstallResult(
              item: entry.item,
              status: Libretro3dsInstallStatus.failed,
              technicalDetail: failure,
            );
          }
        }
      }
      if (staged) {
        for (final entry in pending) {
          final item = entry.item;
          final stagedFile = File(
            p.joinAll([staging.path, ...item.relativeTarget!.split('/')]),
          );
          try {
            final hash = await _stage(item._locator!, stagedFile);
            final verified = await _fileSha256(stagedFile);
            if (await stagedFile.length() != item.size || verified != hash) {
              throw FileSystemException(
                'staged copy differs from the source',
                stagedFile.path,
              );
            }
            if (item.sourceHash != null && item.sourceHash != hash) {
              throw FileSystemException(
                'source changed since analysis',
                stagedFile.path,
              );
            }
            entry.staged = stagedFile;
          } catch (error) {
            staged = false;
            failure ??= _detail(error);
            results[entry.index] = Libretro3dsInstallResult(
              item: item,
              status: Libretro3dsInstallStatus.failed,
              technicalDetail: _detail(error),
            );
          }
        }
      }
      if (!staged) {
        for (final entry in pending) {
          results[entry.index] ??= Libretro3dsInstallResult(
            item: entry.item,
            status: Libretro3dsInstallStatus.notAttempted,
            technicalDetail: failure,
          );
        }
      } else {
        final committed = <_Pending>[];
        for (var at = 0; at < pending.length; at++) {
          final entry = pending[at];
          final item = entry.item;
          final target = File(
            p.joinAll([user.path, ...item.relativeTarget!.split('/')]),
          );
          try {
            await beforeCommit?.call(item.relativeTarget!);
            String? backup;
            if (await target.exists()) {
              backupDirectory ??= await _newBackupDirectory(stamp);
              backup = p.joinAll([
                backupDirectory.path,
                ...item.relativeTarget!.split('/'),
              ]);
              await _copyVerified(target, File(backup));
            } else {
              await target.parent.create(recursive: true);
            }
            await entry.staged!.rename(target.path);
            entry.backup = backup;
            committed.add(entry);
            results[entry.index] = Libretro3dsInstallResult(
              item: item,
              status: backup == null
                  ? Libretro3dsInstallStatus.installed
                  : Libretro3dsInstallStatus.replaced,
              backupPath: backup,
            );
          } catch (error) {
            failure = _detail(error);
            results[entry.index] = Libretro3dsInstallResult(
              item: item,
              status: Libretro3dsInstallStatus.failed,
              technicalDetail: failure,
            );
            for (final later in pending.sublist(at + 1)) {
              results[later.index] = Libretro3dsInstallResult(
                item: later.item,
                status: Libretro3dsInstallStatus.notAttempted,
                technicalDetail: failure,
              );
            }
            rolledBack = true;
            for (final done in committed.reversed) {
              final doneTarget = File(
                p.joinAll([user.path, ...done.item.relativeTarget!.split('/')]),
              );
              String? restoreError;
              try {
                if (done.backup != null) {
                  await _copyVerified(File(done.backup!), doneTarget);
                } else if (await doneTarget.exists()) {
                  await doneTarget.delete();
                }
              } catch (restore) {
                restoreError = _detail(restore);
                _log.e(
                  'Libretro3dsImport[${done.item.relativeTarget}] rollback '
                  'failed: $restoreError',
                );
              }
              results[done.index] = Libretro3dsInstallResult(
                item: done.item,
                status: restoreError == null
                    ? Libretro3dsInstallStatus.rolledBack
                    : Libretro3dsInstallStatus.failed,
                backupPath: done.backup,
                technicalDetail: restoreError ?? failure,
              );
            }
            break;
          }
        }
      }
    } finally {
      await _deleteQuietly(staging);
    }

    final finalResults = [
      for (var index = 0; index < plan.items.length; index++)
        results[index] ??
            Libretro3dsInstallResult(
              item: plan.items[index],
              status: Libretro3dsInstallStatus.notAttempted,
              technicalDetail: failure,
            ),
    ];
    for (final result in finalResults) {
      journal.add({
        'event': 'item',
        'kind': result.item.kind.name,
        'target': result.item.relativeTarget,
        'source': result.item.sourceName,
        'size': result.item.size,
        'status': result.status.name,
        if (result.backupPath != null)
          'backup': p.relative(result.backupPath!, from: backupsRoot),
        'detail': ?result.technicalDetail,
      });
    }
    journal.add({
      'event': 'end',
      'rolledBack': rolledBack,
      'failure': ?failure,
      'counts': {
        for (final status in Libretro3dsInstallStatus.values)
          status.name: finalResults.where((r) => r.status == status).length,
      },
    });
    final journalPath = await journal.write();
    final report = Libretro3dsInstallReport(
      stamp: stamp,
      results: finalResults,
      rolledBack: rolledBack,
      backupDirectory: backupDirectory?.path,
      journalPath: journalPath,
      failure: failure,
    );
    _log.i(
      'Libretro3dsImport $stamp: installed ${report.count(Libretro3dsInstallStatus.installed)}, '
      'replaced ${report.count(Libretro3dsInstallStatus.replaced)}, '
      'failed ${report.count(Libretro3dsInstallStatus.failed)}'
      '${rolledBack ? ', rolled back' : ''}',
    );
    return report;
  }

  /// Copies the source of [locator] to [staged] and returns its SHA-256.
  static Future<String> _stage(_ItemLocator locator, File staged) async {
    await staged.parent.create(recursive: true);
    final sink = _DigestSink();
    final digest = sha256.startChunkedConversion(sink);
    final output = staged.openWrite();
    try {
      switch (locator.kind) {
        case Libretro3dsSourceKind.zip:
          final input = InputFileStream(locator.containerPath);
          try {
            final archive = ZipDecoder().decodeStream(input);
            final entry = archive.find(locator.entryName!);
            if (entry == null || !entry.isFile) {
              throw FileSystemException(
                'entry ${locator.entryName} missing',
                locator.containerPath,
              );
            }
            _readZipEntry(entry, (chunk) {
              digest.add(chunk);
              output.add(chunk);
              return true;
            });
          } finally {
            await input.close();
          }
        case Libretro3dsSourceKind.folder:
        case Libretro3dsSourceKind.file:
          await for (final chunk in File(locator.filePath!).openRead()) {
            final bytes = chunk is Uint8List
                ? chunk
                : Uint8List.fromList(chunk);
            digest.add(bytes);
            output.add(bytes);
          }
      }
      await output.flush();
    } finally {
      await output.close();
    }
    digest.close();
    return sink.value!.toString();
  }

  /// Copies [from] over [to] (parents created) and checks the length.
  static Future<void> _copyVerified(File from, File to) async {
    await to.parent.create(recursive: true);
    final copied = await from.copy(to.path);
    final expected = await from.length();
    final actual = await copied.length();
    if (actual != expected) {
      throw FileSystemException(
        'copy is $actual bytes, expected $expected',
        to.path,
      );
    }
  }

  Future<Directory> _newBackupDirectory(String stamp) async {
    final root = await backupsDirectory();
    await root.create(recursive: true);
    var directory = Directory(p.join(root.path, stamp));
    for (var index = 2; await directory.exists(); index++) {
      directory = Directory(p.join(root.path, '$stamp-$index'));
    }
    await directory.create();
    return directory;
  }

  // ---------------------------------------------------------------------
  // Restore
  // ---------------------------------------------------------------------

  /// Copies the newest backup back into the user directory, file by file
  /// (through staging and a rename), after copying each file it overwrites
  /// into a new backup. Throws [Libretro3dsSystemDataError.noBackup] when
  /// there is none; refused while a session is active or launching.
  Future<Libretro3dsRestoreReport> restoreLastBackup() async {
    await _refuseWhenSessionActive();
    final all = await backups();
    if (all.isEmpty) {
      throw const Libretro3dsSystemDataException(
        Libretro3dsSystemDataError.noBackup,
      );
    }
    final latest = all.first;
    final stamp = _stamp(now());
    final user = await userDirectory();
    final staging = Directory(
      p.join(user.parent.path, '$restoreStagingPrefix$stamp'),
    );
    final journal = _Journal(
      this,
      '$journalPrefix$stamp.jsonl',
      redactions: _redactions(user, (await backupsDirectory()).path, staging),
    );
    journal.add({
      'event': 'restore',
      'stamp': stamp,
      'backup': p.basename(latest.path),
    });

    final files = <File>[];
    await for (final entity in latest.list(
      recursive: true,
      followLinks: false,
    )) {
      if (entity is File) files.add(entity);
    }
    files.sort((a, b) => a.path.compareTo(b.path));

    final results = <Libretro3dsRestoreResult>[];
    Directory? currentBackup;
    try {
      await user.create(recursive: true);
      await staging.create(recursive: true);
      for (final file in files) {
        final relative = p
            .split(p.relative(file.path, from: latest.path))
            .join('/');
        final target = File(p.joinAll([user.path, ...relative.split('/')]));
        try {
          final stagedFile = File(
            p.joinAll([staging.path, ...relative.split('/')]),
          );
          await _copyVerified(file, stagedFile);
          if (await target.exists()) {
            currentBackup ??= await _newBackupDirectory(stamp);
            await _copyVerified(
              target,
              File(p.joinAll([currentBackup.path, ...relative.split('/')])),
            );
          } else {
            await target.parent.create(recursive: true);
          }
          await stagedFile.rename(target.path);
          results.add(
            Libretro3dsRestoreResult(relativePath: relative, restored: true),
          );
        } catch (error) {
          results.add(
            Libretro3dsRestoreResult(
              relativePath: relative,
              restored: false,
              technicalDetail: _detail(error),
            ),
          );
        }
      }
    } finally {
      await _deleteQuietly(staging);
    }
    for (final result in results) {
      journal.add({
        'event': 'item',
        'target': result.relativePath,
        'status': result.restored ? 'restored' : 'failed',
        'detail': ?result.technicalDetail,
      });
    }
    journal.add({
      'event': 'end',
      'restored': results.where((r) => r.restored).length,
      'failed': results.where((r) => !r.restored).length,
      if (currentBackup != null)
        'currentBackup': p.basename(currentBackup.path),
    });
    return Libretro3dsRestoreReport(
      backupDirectory: latest.path,
      currentBackupDirectory: currentBackup?.path,
      results: results,
      journalPath: await journal.write(),
    );
  }

  // ---------------------------------------------------------------------
  // Shared helpers
  // ---------------------------------------------------------------------

  /// Absolute roots → relative tokens, so the journal never holds an
  /// absolute path (longest prefix first). The parent of each source is
  /// redacted too: staging a plain file or a folder entry that vanished
  /// after analysis raises a [FileSystemException] carrying the absolute
  /// source path, which `_detail` keeps for the report.
  static Map<String, String> _redactions(
    Directory user,
    String backupsRoot,
    Directory staging, {
    Iterable<String> sources = const [],
  }) {
    final redactions = <String, String>{
      staging.path: '<staging>',
      user.path: 'Saves/$coreFolderName/$coreFolderName',
      backupsRoot: 'Backups/$coreFolderName',
      user.parent.parent.path: 'Saves',
    };
    for (final source in sources) {
      final parent = p.dirname(source);
      if (p.isAbsolute(parent) && parent != p.rootPrefix(parent)) {
        redactions.putIfAbsent(parent, () => '<sources>');
      } else if (p.isAbsolute(source)) {
        // Directly under the file system root: no parent prefix to strip.
        redactions.putIfAbsent(source, () => '<sources>/${p.basename(source)}');
      }
    }
    return redactions;
  }

  Future<void> _refuseWhenSessionActive() async {
    final bool active;
    try {
      active = await sessionProbe();
    } catch (error) {
      throw Libretro3dsSystemDataException(
        Libretro3dsSystemDataError.sessionActive,
        technicalDetail: 'isSessionActive probe failed: $error',
      );
    }
    if (active) {
      throw const Libretro3dsSystemDataException(
        Libretro3dsSystemDataError.sessionActive,
      );
    }
  }

  static Future<Uint8List> _readPrefix(File file, int count) async {
    final handle = await file.open();
    try {
      return await handle.read(count);
    } finally {
      await handle.close();
    }
  }

  static Future<String> _fileSha256(File file) async {
    final sink = _DigestSink();
    final digest = sha256.startChunkedConversion(sink);
    await for (final chunk in file.openRead()) {
      digest.add(chunk);
    }
    digest.close();
    return sink.value!.toString();
  }

  /// Streams the decompressed bytes of [entry] through [onChunk] until it
  /// returns false. Stored and deflated entries only; encrypted entries and
  /// other methods throw.
  static void _readZipEntry(
    ArchiveFile entry,
    bool Function(Uint8List chunk) onChunk,
  ) {
    final content = entry.rawContent;
    if (content is! ZipFile) {
      final bytes = entry.readBytes();
      if (bytes != null && bytes.isNotEmpty) onChunk(bytes);
      return;
    }
    if ((content.flags & 0x1) != 0) {
      throw FormatException('${entry.name}: encrypted entry');
    }
    final raw = content.getStream(decompress: false);
    raw.reset();
    const chunkSize = 256 * 1024;
    try {
      switch (content.compressionMethod) {
        case CompressionType.none:
          while (!raw.isEOS) {
            final chunk = raw
                .readBytes(math.min(chunkSize, raw.length))
                .toUint8List();
            if (chunk.isEmpty) break;
            if (!onChunk(chunk)) throw const _StopReading();
          }
        case CompressionType.deflate:
          final sink = io.ZLibDecoder(
            raw: true,
          ).startChunkedConversion(_ChunkSink(onChunk));
          while (!raw.isEOS) {
            final chunk = raw
                .readBytes(math.min(chunkSize, raw.length))
                .toUint8List();
            if (chunk.isEmpty) break;
            sink.add(chunk);
          }
          sink.close();
        default:
          throw FormatException(
            '${entry.name}: unsupported compression '
            '${content.compressionMethod.name}',
          );
      }
    } on _StopReading {
      // Early stop requested by the reader.
    } finally {
      raw.reset();
    }
  }

  static Future<void> _deleteQuietly(Directory directory) async {
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } catch (error) {
      _log.w(
        'Libretro3dsSystemData could not delete ${directory.path}: $error',
      );
    }
  }

  static String _two(int value) => value.toString().padLeft(2, '0');

  /// `yyyyMMdd-HHmmss` in UTC (staging, backup and journal names).
  static String _stamp(DateTime time) {
    final utc = time.toUtc();
    return '${utc.year}${_two(utc.month)}${_two(utc.day)}-'
        '${_two(utc.hour)}${_two(utc.minute)}${_two(utc.second)}';
  }

  static String _detail(Object error) {
    if (error is FileSystemException) {
      final os = error.osError;
      return [
        error.message,
        if (error.path != null) error.path!,
        if (os != null) '${os.message} (errno ${os.errorCode})',
      ].join(' • ');
    }
    return error.toString();
  }
}

// -----------------------------------------------------------------------
// Private types
// -----------------------------------------------------------------------

class _Recognition {
  const _Recognition(this.kind, this.target) : rejection = null;
  const _Recognition.ignored()
    : kind = Libretro3dsItemKind.ignored,
      target = null,
      rejection = null;
  const _Recognition.rejected(this.rejection)
    : kind = Libretro3dsItemKind.rejected,
      target = null;

  final Libretro3dsItemKind kind;
  final String? target;
  final Libretro3dsRejection? rejection;
}

/// Where the bytes of a plan element come from.
class _ItemLocator {
  const _ItemLocator.zip(this.containerPath, this.entryName)
    : kind = Libretro3dsSourceKind.zip,
      filePath = null;
  const _ItemLocator.file(this.filePath, {required this.kind})
    : containerPath = '',
      entryName = null;

  final Libretro3dsSourceKind kind;
  final String containerPath;
  final String? entryName;
  final String? filePath;
}

abstract class _SourceFile {
  String get entryName;
  int get size;
  _ItemLocator get locator;

  /// At most [count] leading bytes.
  Future<Uint8List> prefix(int count);

  /// SHA-256 (hex) of the whole content.
  Future<String> contentSha256();
}

class _PlainSourceFile implements _SourceFile {
  _PlainSourceFile(this.file, this.entryName, this.size, this.kind);

  final File file;
  @override
  final String entryName;
  @override
  final int size;
  final Libretro3dsSourceKind kind;

  @override
  _ItemLocator get locator => _ItemLocator.file(file.path, kind: kind);

  @override
  Future<Uint8List> prefix(int count) =>
      Libretro3dsSystemDataService._readPrefix(file, count);

  @override
  Future<String> contentSha256() =>
      Libretro3dsSystemDataService._fileSha256(file);
}

class _ZipSourceFile implements _SourceFile {
  _ZipSourceFile(this.containerPath, this.entry);

  final String containerPath;
  final ArchiveFile entry;

  @override
  String get entryName => entry.name;
  @override
  int get size => entry.size;
  @override
  _ItemLocator get locator => _ItemLocator.zip(containerPath, entry.name);

  @override
  Future<Uint8List> prefix(int count) async {
    final builder = BytesBuilder(copy: false);
    Libretro3dsSystemDataService._readZipEntry(entry, (chunk) {
      builder.add(chunk);
      return builder.length < count;
    });
    final bytes = builder.takeBytes();
    return bytes.length > count
        ? Uint8List.sublistView(bytes, 0, count)
        : bytes;
  }

  @override
  Future<String> contentSha256() async {
    final sink = _DigestSink();
    final digest = sha256.startChunkedConversion(sink);
    Libretro3dsSystemDataService._readZipEntry(entry, (chunk) {
      digest.add(chunk);
      return true;
    });
    digest.close();
    return sink.value!.toString();
  }
}

class _AnalysisContext {
  _AnalysisContext({required this.userDirectory, required this.limits});

  final String userDirectory;
  final Libretro3dsImportLimits limits;
  final List<Libretro3dsImportItem> items = [];
  final Set<String> _claimed = {};
  final Map<String, String> owners = {};
  int recognizedBytes = 0;

  void add(Libretro3dsImportItem item) => items.add(item);

  /// First source to name [target] wins; later ones are duplicates.
  bool claim(String target) => _claimed.add(target);

  String? ownerOf(String target) => owners[target];
}

class _Pending {
  _Pending(this.index, this.item);

  final int index;
  final Libretro3dsImportItem item;
  File? staged;
  String? backup;
}

class _DigestSink implements Sink<Digest> {
  Digest? value;

  @override
  void add(Digest data) => value = data;

  @override
  void close() {}
}

class _ChunkSink implements Sink<List<int>> {
  _ChunkSink(this.onChunk);

  final bool Function(Uint8List chunk) onChunk;

  @override
  void add(List<int> data) {
    if (data.isEmpty) return;
    final bytes = data is Uint8List ? data : Uint8List.fromList(data);
    if (!onChunk(bytes)) throw const _StopReading();
  }

  @override
  void close() {}
}

class _StopReading implements Exception {
  const _StopReading();
}

/// Buffered JSONL journal under `Documents/Diagnostics` (relative paths,
/// sizes and statuses only; never file contents). A journal failure never
/// fails the operation.
class _Journal {
  _Journal(this.service, this.fileName, {this.redactions = const {}});

  final Libretro3dsSystemDataService service;
  final String fileName;
  final Map<String, String> redactions;
  final List<String> _lines = [];

  void add(Map<String, Object?> event) =>
      _lines.add(jsonEncode(_redact(event)));

  Object? _redact(Object? value) {
    if (value is String) {
      var text = value;
      final roots = redactions.keys.toList()
        ..sort((a, b) => b.length.compareTo(a.length));
      for (final root in roots) {
        text = text.replaceAll(root, redactions[root]!);
      }
      return text;
    }
    if (value is Map) {
      return {
        for (final e in value.entries) e.key.toString(): _redact(e.value),
      };
    }
    if (value is List) return [for (final item in value) _redact(item)];
    return value;
  }

  Future<String?> write() async {
    try {
      final directory = await service.diagnosticsDirectory();
      await directory.create(recursive: true);
      final file = File(p.join(directory.path, fileName));
      // Appended: two passes in the same second share one journal file.
      await file.writeAsString(
        '${_lines.join('\n')}\n',
        mode: FileMode.append,
        flush: true,
      );
      return file.path;
    } catch (error) {
      Libretro3dsSystemDataService._log.w(
        'Libretro3dsSystemData journal $fileName not written: $error',
      );
      return null;
    }
  }
}
