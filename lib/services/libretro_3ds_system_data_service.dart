import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:io' as io show ZLibDecoder;
import 'dart:isolate';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:archive/archive_io.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:path/path.dart' as p;

import 'diagnostics_directory.dart';
import 'libretro_3ds_containers.dart';
import 'libretro_core_option_store.dart' show LibretroSessionProbe;
import 'libretro_internal_service.dart';
import 'logger_service.dart';

/// What one element of an import source is, once recognized by its content
/// and its relative path (never by the name of the container alone).
enum Libretro3dsItemKind {
  /// `sysdata/keys.txt` (also accepted as `aes_keys.txt`): key file in the
  /// core's own sectioned format (`:AES`, `:RSA`, `:ECC`). A present file
  /// replaces the keys built into the core, so it is installed only with
  /// `includeKeys` and only when the core would read AES keys from it.
  keys,

  /// `sysdata/seeddb.bin`: title seeds.
  seeddb,

  /// CFG save `nand/data/<id0>/sysdata/00010017/00000000/config`
  /// (0x8000 bytes), installed under the destination id0. It identifies
  /// the console (ConsoleUniqueID blocks, user name, birthday): console
  /// data, installed only with `includeConsoleUnique`.
  config,

  /// NAND title content `nand/<id0>/title/<high>/<low>/content/...`,
  /// installed under the destination id0. A title is installed or refused
  /// as a unit (its whole `content` folder).
  title,

  /// Console-unique data (`SecureInfo_A`, `LocalFriendCodeSeed_B`,
  /// `movable.sed`, `otp.bin`, `mcu.dat`): identifies the console, excluded
  /// unless `includeConsoleUnique`. The first four are also read from the
  /// sections of a GodMode9 `essential.exefs`, each checked against the
  /// SHA-256 its header records.
  consoleUnique,

  /// Listed, never copied.
  ignored,

  /// Refused with a [Libretro3dsRejection].
  rejected,
}

/// Why an element (or a whole container) is refused.
enum Libretro3dsRejection {
  /// Raw NAND image (`nand.bin`, `*.img`, `ctrnand*`, `twln*`, or an `NCSD`
  /// header): encrypted per console, never read by the core. GodMode9's
  /// `essential.exefs` is not one: its console files are read
  /// ([Libretro3dsEssentialExefs]).
  rawNandImage,

  /// 7z, rar, gzip, xz, bzip2, zstd or tar, chosen or inside the chosen
  /// folder or ZIP: only ZIP is decoded (surface kept small on purpose). A
  /// ZIP inside them is listed apart ([Libretro3dsIgnoreReason.nestedArchive]).
  unsupportedArchive,

  /// More entries than the limit (ZIP or folder walk).
  tooManyEntries,

  /// More bytes in total than the limit.
  tooLarge,

  /// One file larger than the per-file limit.
  fileTooLarge,

  /// `..`, absolute path, drive letter, NUL or empty segment.
  unsafeEntry,

  /// Symbolic link entry (ZIP `isSymbolicLink` or mode `0xA000`, or a link
  /// in a folder).
  symbolicLink,

  /// Content does not match the recognized file (size, header, text),
  /// an unreadable or corrupt ZIP, an encrypted entry, or a duplicate target.
  invalid,

  /// A NAND title without a valid `.tmd` and `.app`, or with one of its
  /// files refused: a title is installed or refused as a whole.
  incompleteTitle,

  /// A game, demo, update or DLC title (an SD card category, as the core's
  /// `GetTitleMediaType` decides): never installed into the NAND.
  sdTitle,

  /// A ZIP entry compressed with another method than stored (0) or
  /// deflate (8): its bytes would otherwise be copied undecoded.
  unsupportedCompression,

  /// A key file the core would read no AES key from: no `:AES` section
  /// (Citra-era `aes_keys.txt`), a byte-order mark or CRLF line ends before
  /// the section header. Installed, it would replace the built-in keys with
  /// nothing.
  keysFormat,

  /// Title content in an encrypted NCCH (no `NoCrypto` flag): the core
  /// refuses every encrypted NCCH whatever keys are installed
  /// ([Libretro3dsNcch]), so the title is not installed.
  encryptedContent,

  /// A system file of a picked folder that is still in iCloud Drive: iOS
  /// lists it as its placeholder `.<name>.icloud`, whose content is not the
  /// file's (Build 449). Downloading the folder in Files first makes it
  /// readable.
  notDownloaded,
}

/// Why an element is listed but never copied.
enum Libretro3dsIgnoreReason {
  /// Not one of the recognized system files.
  notRecognized,

  /// A folder deeper than [Libretro3dsImportLimits.maxFolderDepth] levels:
  /// not read.
  tooDeep,

  /// A console file the core never reads: the boot ROMs (`boot9.bin`,
  /// `boot11.bin`), the New 3DS key sector (`sector0x96.bin`,
  /// `secret_sector.bin`) and the `essential.exefs` sections other than the
  /// four console files (NAND header, NAND CID, HWCAL).
  notNeeded,

  /// A ZIP archive inside the chosen folder or ZIP (an Azahar user folder
  /// can hold a `nand.zip` of its own `nand` folder): not opened, never
  /// refused as an unsupported archive (Build 454). It can be chosen on its
  /// own as a ZIP source.
  nestedArchive,
}

/// What an install does with a recognized element.
enum Libretro3dsPlanAction {
  /// The destination does not exist.
  create,

  /// The destination exists with different content; it is moved into the
  /// backup first (for a title, its whole `content` folder).
  replace,

  /// The destination exists with the same size and SHA-256 (for a title,
  /// the same file set with the same contents).
  skipIdentical,
}

/// Final state of one plan element after [Libretro3dsSystemDataService.install].
enum Libretro3dsInstallStatus {
  installed,
  replaced,
  skippedIdentical,

  /// Keys or console data left out by the install flags.
  excluded,
  ignored,
  rejected,

  /// Staging, verification, backup or rename failed (raw detail attached).
  failed,

  /// Moved into place (or into the backup) earlier in the same pass, then
  /// put back as it was after a later failure.
  rolledBack,

  /// Not reached because an earlier element failed.
  notAttempted,
}

/// Why an operation is refused before touching any file.
enum Libretro3dsSystemDataError {
  /// A libretro session is active or launching, or the probe failed
  /// ([Libretro3dsSystemDataException.sessionUnknown]).
  sessionActive,

  /// No complete backup exists under `Backups/Azahar`.
  noBackup,

  /// The newest backup does not match its manifest (or holds no file):
  /// nothing restored.
  backupDamaged,

  /// An interrupted import or restore could not be undone: nothing new is
  /// written until it is.
  unfinishedPass,
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
  const Libretro3dsSystemDataException(
    this.error, {
    this.technicalDetail,
    this.sessionUnknown = false,
  });

  final Libretro3dsSystemDataError error;
  final String? technicalDetail;

  /// [Libretro3dsSystemDataError.sessionActive] because the session probe
  /// itself failed: nobody knows whether a game runs, so nothing is written.
  final bool sessionUnknown;

  @override
  String toString() =>
      'Libretro3dsSystemDataException(${error.name}'
      '${technicalDetail == null ? '' : ': $technicalDetail'})';
}

/// Bounds of an analysis (ZIP, folder, plain files).
class Libretro3dsImportLimits {
  const Libretro3dsImportLimits({
    this.maxZipEntries = 2000,
    this.maxZipRawEntries = 100000,
    this.maxTotalBytes = 1 << 30,
    this.maxFileBytes = 512 << 20,
    this.maxFolderEntries = 5000,
    this.maxFolderDepth = 8,
    this.maxKeysBytes = 64 << 10,
    this.maxSeeddbBytes = 1 << 20,
    this.maxConsoleUniqueBytes = 1 << 20,
    this.maxAnalysisHashBytes = 64 << 20,
  });

  /// Entries an analysis reads or lists, once the folders that never hold
  /// system data (`sdmc`, `Nintendo 3DS`, `cache`, `states`…) are pruned.
  final int maxZipEntries;

  /// Entries of the archive's directory, pruned ones included.
  final int maxZipRawEntries;

  /// Bytes of the recognized files (ignored and pruned entries excluded).
  final int maxTotalBytes;

  /// Bytes of one recognized file.
  final int maxFileBytes;
  final int maxFolderEntries;
  final int maxFolderDepth;
  final int maxKeysBytes;
  final int maxSeeddbBytes;
  final int maxConsoleUniqueBytes;

  /// Recognized files up to this size are hashed at analysis; a larger
  /// title file is compared by size and modification time instead, and its
  /// staged copy validated again.
  final int maxAnalysisHashBytes;
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

  /// The CFG save and the five console-unique files: everything an import
  /// leaves out unless the console data box is checked.
  List<Libretro3dsInventoryFile> get consoleData => [config, ...consoleUnique];
  bool get anyConsoleData => consoleData.any((file) => file.exists);
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
    this.ignoreReason,
    this.action,
    this.exists = false,
    this.identical = false,
    this.technicalDetail,
    this.sourceHash,
    this.titleKey,
    _ItemLocator? locator,
    String? consoleCrypto,
  }) : _locator = locator,
       _consoleCrypto = consoleCrypto;

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

  /// Set for [Libretro3dsItemKind.ignored].
  final Libretro3dsIgnoreReason? ignoreReason;

  /// Null for ignored and rejected elements. A title's files share the
  /// action of their title.
  final Libretro3dsPlanAction? action;
  final int size;

  /// The destination file exists.
  final bool exists;

  /// The destination has the same size and SHA-256.
  final bool identical;

  /// Raw diagnostic of a rejection (or of an ignored folder).
  final String? technicalDetail;

  /// SHA-256 (hex) of the source computed during analysis; null only for a
  /// title file larger than [Libretro3dsImportLimits.maxAnalysisHashBytes].
  final String? sourceHash;

  /// `<high>/<low>` of a NAND title file.
  final String? titleKey;

  final _ItemLocator? _locator;

  /// Console key fingerprint of a title whose contents Azahar encrypted for
  /// their console ([Libretro3dsSystemDataService.consoleCryptoFingerprint]);
  /// kept in memory only, never written to the journal.
  final String? _consoleCrypto;

  /// A file of a NAND title whose contents Azahar encrypted for the console
  /// they come from: the core reads them only with that console's
  /// `otp.bin`, so the title is installed only when that file is installed
  /// or comes with the import and the console data
  /// ([Libretro3dsImportPlan.consoleOtpReady]).
  bool get consoleEncrypted => _consoleCrypto != null;

  bool get installable =>
      action != null && action != Libretro3dsPlanAction.skipIdentical;

  /// Identifies the console (CFG save or console-unique file).
  bool get isConsoleData =>
      kind == Libretro3dsItemKind.consoleUnique ||
      kind == Libretro3dsItemKind.config;
}

/// Result of [Libretro3dsSystemDataService.analyze]: plain data, safe to
/// hand back from an isolate.
class Libretro3dsImportPlan {
  const Libretro3dsImportPlan({
    required this.userDirectory,
    required this.sources,
    required this.items,
    this.retiredTargets = const <String>[],
    this.consoleOtpInstalled = false,
  });

  /// Absolute path of the destination user directory at analysis time.
  final String userDirectory;

  /// `sysdata/otp.bin` (0x100 bytes) was installed at analysis time.
  final bool consoleOtpInstalled;

  /// Source paths as given.
  final List<String> sources;
  final List<Libretro3dsImportItem> items;

  /// Installed files of the titles this plan replaces that the import does
  /// not bring again: they go to the backup with the rest of the old title.
  final List<String> retiredTargets;

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

  /// Whether the core will have an `otp.bin` to read the console-encrypted
  /// titles with: already installed, or installed by this import with the
  /// console data. The install checks the installed file again.
  bool consoleOtpReady({required bool includeConsoleUnique}) =>
      consoleOtpInstalled || (includeConsoleUnique && installsConsoleOtp);

  /// This import brings an `otp.bin` to install with the console data.
  bool get installsConsoleOtp => installable.any(
    (item) =>
        item.kind == Libretro3dsItemKind.consoleUnique &&
        item.relativeTarget == Libretro3dsSystemDataService.otpTarget,
  );
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
    this.retired = const <String>[],
    this.missing = const <String>[],
    this.recovery,
  });

  /// `yyyyMMdd-HHmmss` (UTC) of this pass.
  final String stamp;

  /// In plan order.
  final List<Libretro3dsInstallResult> results;

  /// A failure happened and the elements committed before it were put back.
  final bool rolledBack;

  /// `Backups/Azahar/<stamp>` when at least one file was replaced and the
  /// pass completed (a rolled-back pass leaves no backup: its originals went
  /// back by rename).
  final String? backupDirectory;

  /// `Documents/Diagnostics/libretro-3ds-import-<stamp>.jsonl` when written.
  final String? journalPath;

  /// Raw detail of the first failure.
  final String? failure;

  /// Files of replaced titles the import did not bring again, moved to the
  /// backup with the rest of the old title (relative to the user directory).
  final List<String> retired;

  /// Files or title folders of the user directory that are missing after a
  /// failure that could not be fully undone (their originals stay in the
  /// pass's backup folder).
  final List<String> missing;

  /// What an interrupted earlier pass left and this pass first undid.
  final Libretro3dsRecoveryReport? recovery;

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
    this.rolledBack = false,
    this.failure,
    this.missing = const <String>[],
    this.recovery,
  });

  /// The backup that was restored.
  final String backupDirectory;

  /// Where the files overwritten by the restore were moved first (a new
  /// complete backup, which becomes the newest).
  final String? currentBackupDirectory;
  final List<Libretro3dsRestoreResult> results;
  final String? journalPath;

  /// The restore failed and what it had moved was put back.
  final bool rolledBack;

  /// Raw detail of the failure.
  final String? failure;

  /// Live paths missing after a failure that could not be fully undone.
  final List<String> missing;

  /// What an interrupted earlier pass left and this restore first undid.
  final Libretro3dsRecoveryReport? recovery;

  int get restoredCount => results.where((result) => result.restored).length;
  int get failedCount => results.length - restoredCount;

  /// At least one file came back and none failed: the only state the page
  /// reports as "restored" (a restore of 0 files is an error).
  bool get succeeded => !rolledBack && restoredCount > 0 && failedCount == 0;
}

/// One file of a backup, as its manifest records it.
class Libretro3dsBackupFile {
  const Libretro3dsBackupFile({
    required this.relativePath,
    required this.size,
    required this.sha256,
  });

  /// Relative to the user directory (and to the backup folder), raw.
  final String relativePath;
  final int size;
  final String sha256;
}

/// A complete backup: a manifest of every backed-up file (path, size,
/// SHA-256) and a completion marker written last.
class Libretro3dsBackup {
  const Libretro3dsBackup({
    required this.path,
    required this.name,
    required this.kind,
    required this.createdAt,
    required this.files,
    required this.units,
  });

  /// Absolute path of `Backups/Azahar/<name>`.
  final String path;

  /// `yyyyMMdd-HHmmss[-n]` (UTC).
  final String name;

  /// `import` or `restore`: the pass that moved these files out.
  final String kind;

  /// When the pass ran (UTC).
  final DateTime createdAt;
  final List<Libretro3dsBackupFile> files;

  /// What the pass moved out: files and whole title `content` folders
  /// (relative to the user directory).
  final List<({String target, bool dir})> units;

  int get bytes => files.fold(0, (total, file) => total + file.size);
}

/// How an interrupted pass was dealt with.
enum Libretro3dsRecoveryOutcome {
  /// Nothing had been committed: every original went back by rename and
  /// the files moved in were taken out.
  rolledBack,

  /// The pass had committed: only its last steps (backup marker, staging
  /// removal) were done.
  completed,

  /// Undone as far as possible, and closed: an original was gone
  /// ([Libretro3dsRecoveredPass.missing]) or the user directory already held
  /// something where an original belongs ([Libretro3dsRecoveredPass.kept],
  /// both kept). Retrying would change nothing, so nothing is blocked.
  partial,

  /// A step could not be taken (an I/O error) or the pass journal is not
  /// valid: the pass stays open, is tried again next time, and new passes
  /// are refused meanwhile.
  failed,
}

/// One interrupted pass found by [Libretro3dsSystemDataService.recoverUnfinished].
class Libretro3dsRecoveredPass {
  const Libretro3dsRecoveredPass({
    required this.name,
    required this.kind,
    required this.outcome,
    this.restored = const <String>[],
    this.removed = const <String>[],
    this.missing = const <String>[],
    this.kept = const <String>[],
    this.technicalDetail,
  });

  /// Backup folder name of the pass.
  final String name;

  /// `import` or `restore`.
  final String kind;
  final Libretro3dsRecoveryOutcome outcome;

  /// Originals moved back into the user directory.
  final List<String> restored;

  /// Files or folders the pass had moved in, taken out again.
  final List<String> removed;

  /// User paths still missing (their originals stay in the backup folder).
  final List<String> missing;

  /// Paths left in the backup folder because the user directory holds
  /// something there too (nothing is overwritten).
  final List<String> kept;
  final String? technicalDetail;
}

/// What [Libretro3dsSystemDataService.recoverUnfinished] found and did.
class Libretro3dsRecoveryReport {
  const Libretro3dsRecoveryReport({
    this.passes = const <Libretro3dsRecoveredPass>[],
    this.removedStaging = const <String>[],
    this.journalPath,
  });

  final List<Libretro3dsRecoveredPass> passes;

  /// Staging folders (names) of interrupted passes removed.
  final List<String> removedStaging;
  final String? journalPath;

  bool get isEmpty => passes.isEmpty && removedStaging.isEmpty;
  bool get failed =>
      passes.any((pass) => pass.outcome == Libretro3dsRecoveryOutcome.failed);
  bool get rolledBack => passes.any(
    (pass) => pass.outcome == Libretro3dsRecoveryOutcome.rolledBack,
  );
  bool get partial =>
      passes.any((pass) => pass.outcome == Libretro3dsRecoveryOutcome.partial);
  List<String> get missing => [for (final pass in passes) ...pass.missing];
  List<String> get kept => [for (final pass in passes) ...pass.kept];
}

/// Nintendo 3DS system data of the embedded azahar core: read-only
/// inventory of `Documents/Libretro/Saves/Azahar/Azahar`, analysis of
/// ZIP / folder / file sources into a typed plan, and installs and restores
/// as crash-safe passes.
///
/// A pass stages and verifies everything (in a background isolate, by
/// SHA-256), then moves each existing destination into
/// `Backups/Azahar/<stamp>` by rename, then moves each staged element into
/// place by rename: no free space is needed and nothing is copied over a
/// live file. A write-ahead journal in the backup folder records each step
/// before it happens; an interrupted pass is undone (or finished, when it
/// had committed) by [recoverUnfinished], which install and restore run
/// first. Only a backup whose manifest and completion marker were written is
/// listed and restorable.
///
/// Writes only under `Saves/Azahar` (user directory and staging),
/// `Backups/Azahar` and `Documents/Diagnostics`. The user directory is
/// created at install only. Install, restore and recovery are refused while
/// a libretro session is active or launching, through the same probe as
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
    this.beforeBackup,
    this.beforeFinish,
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
    'otp.bin': otpTarget,
    'mcu.dat': 'sysdata/mcu.dat',
  };

  /// The console's OTP: the core derives from it the key of the title
  /// contents Azahar encrypted for that console
  /// ([consoleCryptoFingerprint]).
  static const String otpTarget = 'sysdata/otp.bin';

  /// Sizes the core accepts for the console-unique files it loads (azahar
  /// a5c3d4f8, `hw/unique_data.cpp`: `sizeof(SecureInfoA)` 0x111,
  /// `sizeof(LocalFriendCodeSeedB)` 0x110, `MovableSed` 0x120 or
  /// `MovableSedFull` 0x140; `file_sys/otp.cpp`: `sizeof(OTPBin)` 0x100).
  /// `mcu.dat` has no loader in those sources: only bounded.
  static const Map<String, List<int>> consoleUniqueSizes = {
    'nand/rw/sys/SecureInfo_A': [0x111],
    'nand/rw/sys/LocalFriendCodeSeed_B': [0x110],
    'nand/private/movable.sed': [0x120, 0x140],
    'sysdata/otp.bin': [0x100],
  };

  /// Prefix of the staging folder created beside the user directory.
  static const String stagingPrefix = '.neostation-3ds-import-';

  /// Prefix of the staging folder of a restore.
  static const String restoreStagingPrefix = '.neostation-3ds-restore-';

  /// `Documents/Diagnostics/<prefix><stamp>.jsonl`.
  static const String journalPrefix = 'libretro-3ds-import-';

  /// Write-ahead journal of a pass, at the top of its backup folder.
  static const String passLogName = '.neostation-pass.jsonl';

  /// Manifest of a backup: path, size and SHA-256 of each backed-up file.
  static const String manifestName = '.neostation-manifest.json';

  /// Completion marker, written last: only then is a backup listed.
  static const String completeMarkerName = '.neostation-complete.json';

  /// CFG save size and header bounds (`SaveFileConfig`).
  static const int configFileSize = 0x8000;
  static const int configMaxBlockEntries = 1479;

  /// `errno` of a rename across two volumes (Linux, macOS and iOS).
  static const int _exdev = 18;

  /// Folders that never hold NAND system data, pruned wherever they appear
  /// (also as the first folder of a ZIP).
  static const Set<String> _alwaysPruned = {
    'sdmc',
    'nintendo 3ds',
    '__macosx',
    '.git',
  };

  /// Folders of a Citra/Azahar user directory that never hold system data
  /// (compared in lower case). In a folder walk the picked folder itself is
  /// never pruned; in a ZIP whose entries all share one first folder, that
  /// folder is the picked one and is not pruned either.
  static const Set<String> _prunedFolders = {
    ..._alwaysPruned,
    'cache',
    'states',
    'shaders',
    'log',
    'logs',
    'dump',
    'screenshots',
    'load',
    'cheats',
  };

  static final RegExp _hex32 = RegExp(r'^[0-9a-f]{32}$');
  static final RegExp _hex8 = RegExp(r'^[0-9a-f]{8}$');
  static final RegExp _hex64 = RegExp(r'^[0-9a-f]{64}$');
  static final RegExp _titleFile = RegExp(r'^[0-9a-f]{1,8}\.(app|tmd|cmd)$');
  static final RegExp _backupName = RegExp(r'^(\d{8}-\d{6})(?:-(\d+))?$');

  /// `ParseKeySlotName` of the core: `slot0x<hex>Key<X|Y|N>`.
  static final RegExp _aesSlotName = RegExp(r'^slot0x([0-9A-Fa-f]+)Key[XYN]$');

  /// `HexToKey` of the core reads the first 32 hex digits.
  static final RegExp _aesKeyValue = RegExp(r'^[0-9A-Fa-f]{32}');

  static final _log = LoggerService.instance;

  /// Install, restore and recovery of this service run one at a time (the
  /// recovery a page starts when it opens and an import the user starts
  /// right away must not interleave their renames). Waiters complete their
  /// own completers, so no future crosses zones.
  bool _exclusiveBusy = false;
  final List<Completer<void>> _exclusiveWaiters = [];

  /// `Documents/Libretro/Saves` in production.
  final Future<Directory> Function() savesDirectory;

  /// `Documents/Libretro/Backups/Azahar` in production.
  final Future<Directory> Function() backupsDirectory;

  /// `Documents/Diagnostics` in production (created on first use).
  final Future<Directory> Function() diagnosticsDirectory;
  final LibretroSessionProbe sessionProbe;
  final Libretro3dsImportLimits limits;
  final DateTime Function() now;

  /// Test hook run for each file of an element just before the element is
  /// moved into place; throwing simulates a commit failure.
  @visibleForTesting
  final Future<void> Function(String relativeTarget)? beforeCommit;

  /// Test hook run just before an existing destination (a file or a
  /// title's `content` folder) is moved into the backup.
  @visibleForTesting
  final Future<void> Function(String relativeTarget)? beforeBackup;

  /// Test hook run once a pass has committed, before its backup is marked
  /// complete and its staging folder removed.
  @visibleForTesting
  final Future<void> Function()? beforeFinish;

  static Future<Directory> _defaultBackupsDirectory() async => Directory(
    p.join(
      (await LibretroInternalService.rootDirectory()).path,
      'Backups',
      coreFolderName,
    ),
  );

  Future<T> _exclusive<T>(Future<T> Function() body) async {
    while (_exclusiveBusy) {
      final waiter = Completer<void>();
      _exclusiveWaiters.add(waiter);
      await waiter.future;
    }
    _exclusiveBusy = true;
    try {
      return await body();
    } finally {
      _exclusiveBusy = false;
      if (_exclusiveWaiters.isNotEmpty) {
        _exclusiveWaiters.removeAt(0).complete();
      }
    }
  }

  // ---------------------------------------------------------------------
  // Roots
  // ---------------------------------------------------------------------

  /// `<savesDirectory>/Azahar/Azahar`, created only by [install].
  Future<Directory> userDirectory() async => Directory(
    p.join((await savesDirectory()).path, coreFolderName, coreFolderName),
  );

  /// Complete backups (manifest and completion marker present, every file
  /// of the manifest present with its size), newest first. Never deleted by
  /// the app. A folder without them (an interrupted or rolled-back pass, an
  /// older build) is not listed.
  Future<List<Libretro3dsBackup>> backups() async {
    final root = await backupsDirectory();
    if (!await root.exists()) return const [];
    final found = <(String, int, Libretro3dsBackup)>[];
    await for (final entity in root.list(followLinks: false)) {
      if (entity is! Directory) continue;
      final name = p.basename(entity.path);
      final match = _backupName.firstMatch(name);
      if (match == null) continue;
      final backup = await _readCompleteBackup(entity);
      if (backup == null) continue;
      found.add((
        match.group(1)!,
        int.tryParse(match.group(2) ?? '1') ?? 1,
        backup,
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
    await _settleTitles(context);
    context.items.sort(_planOrder);
    context.retired.sort();
    return Libretro3dsImportPlan(
      userDirectory: userDirectory,
      sources: List.unmodifiable(sources),
      items: List.unmodifiable(context.items),
      retiredTargets: List.unmodifiable(context.retired),
      consoleOtpInstalled: await _hasConsoleOtp(userDirectory),
    );
  }

  /// `sysdata/otp.bin` of [userDirectory] is a file of the size the core
  /// loads (`sizeof(OTPBin)`).
  static Future<bool> _hasConsoleOtp(String userDirectory) async {
    try {
      final file = File(p.joinAll([userDirectory, ...otpTarget.split('/')]));
      if (await FileSystemEntity.type(file.path, followLinks: false) !=
          FileSystemEntityType.file) {
        return false;
      }
      return consoleUniqueSizes[otpTarget]!.contains(await file.length());
    } catch (_) {
      return false;
    }
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
    final stat = await file.stat();
    final head = await _readPrefix(file, 0x200);
    if (_isZipSignature(head)) {
      await _analyzeZip(file, name, context);
      return;
    }
    // A recognized file is never sniffed for an archive signature: its own
    // header decides (an NCCH starts with a random RSA signature).
    final recognition = _recognize(
      name,
      sourceKind: Libretro3dsSourceKind.file,
    );
    if (recognition.kind == Libretro3dsItemKind.ignored) {
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
    }
    await _classify(
      _PlainSourceFile(
        file,
        name,
        stat.size,
        Libretro3dsSourceKind.file,
        stat.modified.millisecondsSinceEpoch,
      ),
      recognitionPath: name,
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

    final FileStat containerStat;
    final InputFileStream input;
    try {
      containerStat = await file.stat();
      input = InputFileStream(file.path);
    } catch (error) {
      reject(Libretro3dsRejection.invalid, _detail(error));
      return;
    }
    RandomAccessFile? headers;
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
      if (archive.length > limits.maxZipRawEntries) {
        reject(
          Libretro3dsRejection.tooManyEntries,
          '${archive.length} entries',
        );
        return;
      }
      // Names are normalized first (backslashes, leading "./"), then every
      // entry is checked: one dangerous name refuses the whole archive.
      final files = <(ArchiveFile, String)>[];
      for (final entry in archive.files) {
        final normalized = _normalizeZipName(entry.name);
        final unsafe = _unsafeEntryName(normalized);
        if (unsafe != null) {
          reject(Libretro3dsRejection.unsafeEntry, '$unsafe: ${entry.name}');
          return;
        }
        if (entry.isSymbolicLink || (entry.mode & 0xF000) == 0xA000) {
          reject(Libretro3dsRejection.symbolicLink, entry.name);
          return;
        }
        if (!entry.isFile || _isNoise(normalized)) continue;
        files.add((entry, normalized));
      }
      // Pruned folders (games of an SD card, caches, states…) count toward
      // no limit and are never read.
      final root = _commonRoot([for (final file in files) file.$2]);
      final considered = [
        for (final file in files)
          if (!_isPrunedPath(file.$2, rootSegment: root)) file,
      ];
      if (considered.length > limits.maxZipEntries) {
        reject(
          Libretro3dsRejection.tooManyEntries,
          '${considered.length} entries to read '
          '(${archive.length} in the archive)',
        );
        return;
      }
      // Size limits apply to the files that would be read: an unrecognized
      // or raw NAND entry is never decompressed beyond its head.
      var declaredTotal = 0;
      for (final (entry, normalized) in considered) {
        final recognition = _recognize(
          normalized,
          sourceKind: Libretro3dsSourceKind.zip,
        );
        if (recognition.kind == Libretro3dsItemKind.ignored ||
            recognition.kind == Libretro3dsItemKind.rejected) {
          continue;
        }
        if (entry.size > limits.maxFileBytes) {
          reject(
            Libretro3dsRejection.fileTooLarge,
            '$normalized: ${entry.size} bytes',
          );
          return;
        }
        declaredTotal += entry.size;
      }
      if (declaredTotal > limits.maxTotalBytes) {
        reject(Libretro3dsRejection.tooLarge, '$declaredTotal bytes');
        return;
      }
      headers = await file.open();
      for (final (entry, normalized) in considered) {
        await _classify(
          _ZipSourceFile(
            file.path,
            entry,
            normalized,
            containerStat.size,
            containerStat.modified.millisecondsSinceEpoch,
            await _zipEntryProblem(headers, entry),
          ),
          recognitionPath: normalized,
          containerName: name,
          sourceKind: Libretro3dsSourceKind.zip,
          context: context,
        );
      }
    } finally {
      await headers?.close();
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
    final tooDeep = <String>[];
    // iCloud Drive placeholders: (path of the file they stand for, their own
    // relative path).
    final notDownloaded = <(String, String)>[];
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
          if (depth < limits.maxFolderDepth) {
            if (!await visit(entity, depth + 1)) return false;
          } else {
            // Not read, but said: a dump picked a few folders too high.
            tooDeep.add(relative);
          }
          continue;
        }
        if (entity is! File) continue;
        final placeholderOf = _iCloudPlaceholderTarget(relative);
        if (placeholderOf != null) {
          notDownloaded.add((placeholderOf, relative));
          continue;
        }
        if (_isNoise(relative)) continue;
        final stat = await entity.stat();
        found.add(
          _PlainSourceFile(
            entity,
            relative,
            stat.size,
            Libretro3dsSourceKind.folder,
            stat.modified.millisecondsSinceEpoch,
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
    for (final folder in tooDeep) {
      context.add(
        Libretro3dsImportItem._(
          sourceName: name,
          sourceEntry: '$folder/',
          sourceKind: Libretro3dsSourceKind.folder,
          kind: Libretro3dsItemKind.ignored,
          ignoreReason: Libretro3dsIgnoreReason.tooDeep,
          size: 0,
          technicalDetail: 'deeper than ${limits.maxFolderDepth} folder levels',
        ),
      );
    }
    // A placeholder of a file the import would read is said, with what to
    // do; one of anything else stays unlisted, like the noise it stands for.
    for (final (logical, placeholder) in notDownloaded) {
      final recognition = _recognize(
        '$name/$logical',
        sourceKind: Libretro3dsSourceKind.folder,
      );
      if (recognition.kind == Libretro3dsItemKind.ignored ||
          recognition.kind == Libretro3dsItemKind.rejected ||
          _isNoise(logical)) {
        continue;
      }
      context.add(
        Libretro3dsImportItem._(
          sourceName: name,
          sourceEntry: logical,
          sourceKind: Libretro3dsSourceKind.folder,
          kind: Libretro3dsItemKind.rejected,
          rejection: Libretro3dsRejection.notDownloaded,
          size: 0,
          technicalDetail: placeholder,
        ),
      );
    }
    for (final file in found) {
      await _classify(
        file,
        // The picked folder's own name counts for the path rules: picking
        // the "title" folder itself is recognized.
        recognitionPath: '$name/${file.entryName}',
        containerName: name,
        sourceKind: Libretro3dsSourceKind.folder,
        context: context,
      );
    }
  }

  /// Recognizes one file by its relative path, validates its content and
  /// records it (titles are settled as units by [_settleTitles]).
  static Future<void> _classify(
    _SourceFile source, {
    required String recognitionPath,
    required String containerName,
    required Libretro3dsSourceKind sourceKind,
    required _AnalysisContext context,
  }) async {
    final limits = context.limits;
    final entry = source.entryName;
    final recognition = _recognize(recognitionPath, sourceKind: sourceKind);

    Libretro3dsImportItem item({
      required Libretro3dsItemKind kind,
      String? target,
      Libretro3dsRejection? rejection,
      Libretro3dsIgnoreReason? ignoreReason,
      Libretro3dsPlanAction? action,
      bool exists = false,
      bool identical = false,
      String? detail,
      String? hash,
      String? consoleCrypto,
    }) => Libretro3dsImportItem._(
      sourceName: containerName,
      sourceEntry: entry,
      sourceKind: sourceKind,
      kind: kind,
      relativeTarget: target,
      rejection: rejection,
      ignoreReason: ignoreReason,
      action: action,
      size: source.size,
      exists: exists,
      identical: identical,
      technicalDetail: detail,
      sourceHash: hash,
      titleKey: recognition.titleKey,
      locator: source.locator,
      consoleCrypto: consoleCrypto,
    );

    void rejected(
      Libretro3dsRejection rejection,
      String detail, {
      String? target,
      bool refusesTitle = true,
    }) {
      context.add(
        item(
          kind: Libretro3dsItemKind.rejected,
          target: target,
          rejection: rejection,
          detail: detail,
        ),
      );
      final key = recognition.titleKey;
      if (key != null && refusesTitle) {
        context.refuseTitle(key, '$entry: $detail');
      }
    }

    if (recognition.rejection != null) {
      rejected(recognition.rejection!, entry);
      return;
    }
    final kind = recognition.kind;
    final target = recognition.target;
    final problem = source.problem;
    if (problem != null) {
      rejected(problem.rejection, problem.detail, target: target);
      return;
    }
    if (recognition.essentialExefs) {
      await _classifyEssentialExefs(
        source,
        containerName: containerName,
        sourceKind: sourceKind,
        context: context,
      );
      return;
    }

    // A raw NAND image is refused whatever it is called.
    final Uint8List head;
    try {
      head = await source.prefix(0x200);
    } catch (error) {
      rejected(Libretro3dsRejection.invalid, _detail(error), target: target);
      return;
    }
    if (_isNcsdImage(head)) {
      rejected(
        Libretro3dsRejection.rawNandImage,
        'NCSD header: $entry',
        target: target,
      );
      return;
    }

    if (kind == Libretro3dsItemKind.ignored || target == null) {
      // Only an unrecognized file is sniffed for an archive signature. A ZIP
      // inside the chosen folder or ZIP is not opened, but it is no
      // unsupported archive either: listed apart, with the way to import it
      // (Build 454; before, "only ZIP archives are read" refused a nand.zip).
      if (_isZipSignature(head)) {
        context.add(
          item(
            kind: Libretro3dsItemKind.ignored,
            ignoreReason: Libretro3dsIgnoreReason.nestedArchive,
          ),
        );
        return;
      }
      final archive = _otherArchiveSignature(head, entry);
      if (archive != null) {
        rejected(Libretro3dsRejection.unsupportedArchive, '$archive: $entry');
        return;
      }
      context.add(
        item(
          kind: Libretro3dsItemKind.ignored,
          ignoreReason:
              recognition.ignoreReason ?? Libretro3dsIgnoreReason.notRecognized,
        ),
      );
      return;
    }
    if (recognition.sdTitle) {
      rejected(
        Libretro3dsRejection.sdTitle,
        'title ${recognition.titleKey} is an SD card title',
        target: target,
      );
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
    final _Refusal? refusal;
    String? consoleCrypto;
    try {
      refusal = await _validateContent(
        kind,
        source,
        head,
        limits,
        titleKey: recognition.titleKey,
        target: target,
        onConsoleCrypto: (fingerprint) => consoleCrypto = fingerprint,
      );
    } catch (error) {
      rejected(Libretro3dsRejection.invalid, _detail(error), target: target);
      return;
    }
    if (refusal != null) {
      rejected(refusal.rejection, refusal.detail, target: target);
      return;
    }
    if (!context.claim(target)) {
      // The first source naming a file wins; its title is still whole.
      rejected(
        Libretro3dsRejection.invalid,
        'duplicate target $target in ${context.ownerOf(target)}',
        target: target,
        refusesTitle: false,
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

    // Every recognized file is hashed now (a large title file excepted),
    // so a source changed after the analysis is caught before any commit.
    String? hash;
    if (kind != Libretro3dsItemKind.title ||
        source.size <= limits.maxAnalysisHashBytes) {
      try {
        hash = await source.contentSha256();
      } catch (error) {
        rejected(Libretro3dsRejection.invalid, _detail(error), target: target);
        return;
      }
    }

    if (kind == Libretro3dsItemKind.title) {
      context.titles
          .putIfAbsent(recognition.titleKey!, () => [])
          .add(_TitleFile(source, item, target, hash, consoleCrypto));
      return;
    }

    final destination = File(
      p.joinAll([context.userDirectory, ...target.split('/')]),
    );
    var exists = false;
    var identical = false;
    try {
      exists = await destination.exists();
      if (exists && await destination.length() == source.size) {
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

  /// Reads GodMode9's `essential.exefs` ([Libretro3dsEssentialExefs]): each
  /// section holding a console file the core reads is classified like the
  /// loose file (size, SEED magic, destination, duplicates, console-data
  /// box) and staged from its place in the file; a section whose recorded
  /// SHA-256 does not match is refused; a console section left blank and
  /// unhashed (the OTP of a locked console) has nothing to install; the
  /// other sections are listed as not needed. A file that is not an
  /// essential backup is refused whole.
  static Future<void> _classifyEssentialExefs(
    _SourceFile source, {
    required String containerName,
    required Libretro3dsSourceKind sourceKind,
    required _AnalysisContext context,
  }) async {
    final entry = source.entryName;
    void add(
      String sourceEntry,
      int size, {
      required Libretro3dsItemKind kind,
      Libretro3dsRejection? rejection,
      Libretro3dsIgnoreReason? ignoreReason,
      String? target,
      String? detail,
    }) => context.add(
      Libretro3dsImportItem._(
        sourceName: containerName,
        sourceEntry: sourceEntry,
        sourceKind: sourceKind,
        kind: kind,
        relativeTarget: target,
        rejection: rejection,
        ignoreReason: ignoreReason,
        size: size,
        technicalDetail: detail,
      ),
    );

    Libretro3dsEssentialExefsContent content;
    if (source.size > Libretro3dsEssentialExefs.maxBytes) {
      content = Libretro3dsEssentialExefsContent.refused(
        '${source.size} bytes, more than an essential backup',
      );
    } else {
      try {
        final bytes = await source.prefix(source.size);
        content = bytes.length == source.size
            ? Libretro3dsEssentialExefs.parse(bytes)
            : Libretro3dsEssentialExefsContent.refused(
                '${bytes.length} bytes read, ${source.size} declared',
              );
      } catch (error) {
        content = Libretro3dsEssentialExefsContent.refused(_detail(error));
      }
    }
    final refusal = content.problem;
    if (refusal != null) {
      add(
        entry,
        source.size,
        kind: Libretro3dsItemKind.rejected,
        rejection: Libretro3dsRejection.invalid,
        detail: '$entry: $refusal',
      );
      return;
    }
    for (final section in content.sections) {
      if (section.size == 0) continue;
      final sectionEntry = '$entry/${section.name}';
      final consoleFile = Libretro3dsEssentialExefs.consoleFiles[section.name];
      final target = consoleFile == null
          ? null
          : consoleUniqueTargets[consoleFile];
      if (section.problem != null) {
        add(
          sectionEntry,
          section.size,
          kind: Libretro3dsItemKind.rejected,
          rejection: Libretro3dsRejection.invalid,
          target: target,
          detail: section.problem,
        );
        continue;
      }
      if (consoleFile == null) {
        add(
          sectionEntry,
          section.size,
          kind: Libretro3dsItemKind.ignored,
          ignoreReason:
              Libretro3dsEssentialExefs.unusedSections.contains(section.name)
              ? Libretro3dsIgnoreReason.notNeeded
              : Libretro3dsIgnoreReason.notRecognized,
        );
        continue;
      }
      if (!section.hashed) {
        if (section.blank) continue;
        add(
          sectionEntry,
          section.size,
          kind: Libretro3dsItemKind.rejected,
          rejection: Libretro3dsRejection.invalid,
          target: target,
          detail: '${section.name}: no SHA-256 recorded in the header',
        );
        continue;
      }
      await _classify(
        _SliceSourceFile(source, section, sectionEntry),
        recognitionPath: consoleFile,
        containerName: containerName,
        sourceKind: sourceKind,
        context: context,
      );
    }
  }

  /// Installs or refuses each NAND title as a unit: at least one valid
  /// `.tmd` and one `.app`, no file of the title refused; the action of a
  /// title compares its whole destination `content` folder.
  static Future<void> _settleTitles(_AnalysisContext context) async {
    final keys = context.titles.keys.toList()..sort();
    // Contents without a readable header are kept only when the other
    // contents confirm one console key (Azahar's console encryption).
    final consoleKey = _consoleCryptoConsensus(
      context.titles.values.expand((files) => files),
    );
    for (final key in keys) {
      final files = context.titles[key]!;
      String? refusal = context.refusedTitles[key];
      final unconfirmed = {
        for (final file in files)
          if (file.consoleCrypto != null && file.consoleCrypto != consoleKey)
            file.target,
      };
      if (refusal == null && unconfirmed.isNotEmpty) {
        refusal = '${unconfirmed.first}: $_consoleCryptoUnconfirmed';
      }
      if (refusal == null &&
          !files.any((file) => file.target.endsWith('.tmd'))) {
        refusal = 'title $key has no .tmd';
      }
      if (refusal == null &&
          !files.any((file) => file.target.endsWith('.app'))) {
        refusal = 'title $key has no .app';
      }
      if (refusal != null) {
        for (final file in files) {
          final unreadable = unconfirmed.contains(file.target);
          context.add(
            file.item(
              kind: Libretro3dsItemKind.rejected,
              target: file.target,
              rejection: unreadable
                  ? Libretro3dsRejection.invalid
                  : Libretro3dsRejection.incompleteTitle,
              detail: unreadable
                  ? 'no NCCH header at 0x100 (nor a Z3DS or AZCR container): '
                        '$_consoleCryptoUnconfirmed'
                  : refusal,
            ),
          );
        }
        continue;
      }
      // One encrypted content makes the whole title depend on the OTP.
      final titleConsoleCrypto = files.any((file) => file.consoleCrypto != null)
          ? consoleKey
          : null;

      final contentTarget = '$titleRoot/$key/content';
      final content = p.joinAll([
        context.userDirectory,
        ...contentTarget.split('/'),
      ]);
      final existing = <String, File>{};
      var blocked = false;
      try {
        final type = await FileSystemEntity.type(content, followLinks: false);
        if (type == FileSystemEntityType.directory) {
          await for (final entity in Directory(
            content,
          ).list(recursive: true, followLinks: false)) {
            if (entity is Directory) continue;
            final relative = p
                .split(p.relative(entity.path, from: content))
                .join('/');
            if (entity is File) {
              existing['$contentTarget/$relative'] = entity;
            } else {
              existing['$contentTarget/$relative'] = File(entity.path);
              blocked = true;
            }
          }
        } else if (type != FileSystemEntityType.notFound) {
          // A file or a link where the folder should be: moved to the
          // backup like a different folder.
          blocked = true;
        }
      } catch (error) {
        for (final file in files) {
          context.add(
            file.item(
              kind: Libretro3dsItemKind.rejected,
              target: file.target,
              rejection: Libretro3dsRejection.invalid,
              detail: _detail(error),
            ),
          );
        }
        continue;
      }

      final identicalFiles = <String>{};
      for (final file in files) {
        final destination = existing[file.target];
        if (destination == null) continue;
        try {
          if (await destination.length() != file.source.size) continue;
          final hash = file.hash ?? await file.source.contentSha256();
          if (hash == await _fileSha256(destination)) {
            identicalFiles.add(file.target);
          }
        } catch (_) {
          // Unreadable destination: not identical, replaced with a backup.
        }
      }
      final incoming = {for (final file in files) file.target};
      final sameSet =
          existing.length == incoming.length &&
          incoming.every(existing.containsKey);
      final Libretro3dsPlanAction action;
      if (existing.isEmpty && !blocked) {
        action = Libretro3dsPlanAction.create;
      } else if (!blocked &&
          sameSet &&
          identicalFiles.length == incoming.length) {
        action = Libretro3dsPlanAction.skipIdentical;
      } else {
        action = Libretro3dsPlanAction.replace;
        context.retired.addAll(
          existing.keys.where((target) => !incoming.contains(target)),
        );
        if (blocked && existing.isEmpty) context.retired.add(contentTarget);
      }
      for (final file in files) {
        context.add(
          file.item(
            kind: Libretro3dsItemKind.title,
            target: file.target,
            action: action,
            exists: existing.containsKey(file.target),
            identical: identicalFiles.contains(file.target),
            hash: file.hash,
            consoleCrypto: titleConsoleCrypto,
          ),
        );
      }
    }
  }

  /// Why a content without a readable header is not kept.
  static const String _consoleCryptoUnconfirmed =
      'not confirmed as encrypted by Azahar for one console (no content of '
      'another title or size shares its keystream, or the contents disagree)';

  /// Kind and destination of a relative path (case-insensitive, any
  /// container prefix tolerated, `sdmc` trees ignored).
  static _Recognition _recognize(
    String relativePath, {
    required Libretro3dsSourceKind sourceKind,
  }) {
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
    if (segments.any(_alwaysPruned.contains)) {
      return const _Recognition.ignored();
    }
    if (name == Libretro3dsEssentialExefs.fileName) {
      return const _Recognition.essentialExefs();
    }
    if (_notNeededNames.contains(name)) {
      return const _Recognition.ignored(Libretro3dsIgnoreReason.notNeeded);
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
      // data/<id0>/sysdata/00010017/00000000/config, or the file picked on
      // its own (never a bare "config" inside a ZIP or a folder).
      final n = segments.length;
      if ((n == 1 && sourceKind == Libretro3dsSourceKind.file) ||
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
        return _Recognition.title(
          '$titleRoot/$high/$low/content/$tail',
          '$high/$low',
          sdTitle: !isNandTitle(high, low),
        );
      }
      return const _Recognition.ignored();
    }
    return const _Recognition.ignored();
  }

  /// Whether the core keeps title `<high>/<low>` in the NAND: azahar
  /// a5c3d4f8 `GetTitleMediaType` (`hle/service/am/am.cpp`) puts a title in
  /// the NAND when its platform is not CTR (0x0004), its category has the
  /// system (0x0010) or download-play (0x0001) bit, or its variation (low
  /// byte of the title id) has the system bit (0x02); every other title
  /// (applications 00040000, demos 00040002, updates 0004000e, DLC
  /// 0004008c…) belongs to the SD card.
  @visibleForTesting
  static bool isNandTitle(String high, String low) {
    final highValue = int.parse(high, radix: 16);
    final lowValue = int.parse(low, radix: 16);
    final platform = highValue >> 16;
    final category = highValue & 0xFFFF;
    final variation = lowValue & 0xFF;
    if (platform != 0x0004) return true;
    return (category & 0x0010) != 0 ||
        (category & 0x0001) != 0 ||
        (variation & 0x02) != 0;
  }

  static bool _isRawNandName(String lowerName) =>
      lowerName == 'nand.bin' ||
      lowerName.endsWith('.img') ||
      lowerName.startsWith('ctrnand') ||
      lowerName.startsWith('twln');

  /// Console files the core never reads (azahar a5c3d4f8 `hw/aes/key.cpp`
  /// reads its keys from `sysdata/keys.txt`, or from a blob built into the
  /// core when it was built with one, never from a boot ROM or the New 3DS
  /// key sector): listed, never copied.
  static const Set<String> _notNeededNames = {
    'boot9.bin',
    'boot11.bin',
    'sector0x96.bin',
    'secret_sector.bin',
  };

  /// Entries never listed: `__MACOSX`, Finder/Explorer metadata.
  /// The relative path of the file an iCloud Drive placeholder stands for
  /// (`dir/.config.icloud` → `dir/config`), or null for any other name.
  /// iOS keeps a file that is not downloaded as that hidden placeholder.
  static String? _iCloudPlaceholderTarget(String relativePath) {
    final segments = relativePath.split('/');
    final name = segments.last;
    if (name.length <= '..icloud'.length ||
        !name.startsWith('.') ||
        !name.toLowerCase().endsWith('.icloud')) {
      return null;
    }
    final original = name.substring(1, name.length - '.icloud'.length);
    if (original.isEmpty || original.startsWith('.')) return null;
    return [...segments.take(segments.length - 1), original].join('/');
  }

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

  /// First folder shared by every entry of a ZIP (the zipped folder
  /// itself), lower case; null when the entries do not share one.
  static String? _commonRoot(List<String> names) {
    String? root;
    for (final name in names) {
      final segments = name.split('/');
      if (segments.length < 2) return null;
      final first = segments.first.toLowerCase();
      if (root == null) {
        root = first;
      } else if (root != first) {
        return null;
      }
    }
    return root;
  }

  /// A ZIP entry inside a pruned folder ([_prunedFolders]); the shared
  /// first folder ([rootSegment]) is the zipped folder itself and only
  /// [_alwaysPruned] applies to it.
  static bool _isPrunedPath(String name, {required String? rootSegment}) {
    final segments = name.split('/');
    for (var index = 0; index < segments.length - 1; index++) {
      final segment = segments[index].toLowerCase();
      if (_alwaysPruned.contains(segment)) return true;
      if (index == 0 && rootSegment != null) continue;
      if (_prunedFolders.contains(segment)) return true;
    }
    return false;
  }

  /// Null when the content matches [kind]; else the refusal. A title `.app`
  /// without a readable header that may be a content Azahar encrypted for
  /// its console is handed to [onConsoleCrypto] with its fingerprint
  /// instead of being refused: only the other contents can confirm it
  /// ([_settleTitles]).
  static Future<_Refusal?> _validateContent(
    Libretro3dsItemKind kind,
    _SourceFile source,
    Uint8List head,
    Libretro3dsImportLimits limits, {
    String? titleKey,
    String? target,
    void Function(String fingerprint)? onConsoleCrypto,
  }) async {
    final size = source.size;
    _Refusal invalid(String detail) =>
        _Refusal(Libretro3dsRejection.invalid, detail);
    switch (kind) {
      case Libretro3dsItemKind.keys:
        if (size > limits.maxKeysBytes) {
          return invalid('keys file of $size bytes');
        }
        final reason = keysProblem(await source.prefix(size));
        return reason == null
            ? null
            : _Refusal(Libretro3dsRejection.keysFormat, reason);
      case Libretro3dsItemKind.seeddb:
        if (size > limits.maxSeeddbBytes) {
          return invalid('seeddb of $size bytes');
        }
        if (size < 16 || (size - 16) % 32 != 0) {
          return invalid('seeddb size $size is not 16 + 32·n');
        }
        final count = ByteData.sublistView(head).getUint32(0, Endian.little);
        final entries = (size - 16) ~/ 32;
        if (count > entries) {
          return invalid('seeddb declares $count of $entries seeds');
        }
        return null;
      case Libretro3dsItemKind.config:
        if (size != configFileSize) {
          return invalid('config of $size bytes, expected $configFileSize');
        }
        final view = ByteData.sublistView(head);
        final totalEntries = view.getUint16(0, Endian.little);
        final dataOffset = view.getUint16(2, Endian.little);
        if (totalEntries > configMaxBlockEntries) {
          return invalid('config total_entries $totalEntries');
        }
        if (dataOffset > configFileSize) {
          return invalid(
            'config data_entries_offset 0x${dataOffset.toRadixString(16)}',
          );
        }
        return null;
      case Libretro3dsItemKind.title:
        if (size == 0) return invalid('empty title file');
        final name = (target ?? source.entryName).toLowerCase();
        if (name.endsWith('.app')) {
          if (_isEncryptedContent(head, titleKey)) {
            return const _Refusal(
              Libretro3dsRejection.encryptedContent,
              'NCCH without the NoCrypto flag (encrypted content)',
            );
          }
          final problem = _contentProblem(head, titleKey);
          if (problem == null) return null;
          final fingerprint = onConsoleCrypto == null
              ? null
              : consoleCryptoFingerprint(head, size, titleKey);
          if (fingerprint == null) return invalid(problem);
          onConsoleCrypto!(fingerprint);
          return null;
        }
        if (name.endsWith('.tmd')) {
          final problem = tmdProblem(
            await source.prefix(0xC04),
            size,
            titleKey,
          );
          return problem == null ? null : invalid(problem);
        }
        return null;
      case Libretro3dsItemKind.consoleUnique:
        if (size == 0) return invalid('empty file');
        if (size > limits.maxConsoleUniqueBytes) {
          return invalid('console file of $size bytes');
        }
        final sizes = consoleUniqueSizes[target];
        if (sizes != null && !sizes.contains(size)) {
          return invalid(
            '${p.posix.basename(target!)} of $size bytes, expected '
            '${sizes.map((s) => '0x${s.toRadixString(16)}').join(' or ')}',
          );
        }
        if (target == 'nand/private/movable.sed' &&
            !_startsWith(head, 0, const [0x53, 0x45, 0x45, 0x44])) {
          return invalid('movable.sed has no SEED magic');
        }
        return null;
      case Libretro3dsItemKind.ignored:
      case Libretro3dsItemKind.rejected:
        return null;
    }
  }

  /// Null when the core can open [head] as title content: an `NCCH` header
  /// at 0x100, or the core's own containers for installed content, `Z3DS`
  /// (compressed) or `AZCR` (console-unique encryption) at 0 (azahar
  /// a5c3d4f8 `NCCHContainer::AutoOpenNCCHNCSD`). A DS title (TWL flag of
  /// the high id) holds no NCCH and is only required non-empty. The legacy
  /// console encryption, without a header, is recognized apart
  /// ([consoleCryptoFingerprint]).
  static String? _contentProblem(Uint8List head, String? titleKey) {
    final high = titleKey == null
        ? 0
        : int.parse(titleKey.split('/').first, radix: 16);
    if ((high & 0x8000) != 0) return null;
    if (_startsWith(head, 0x100, const [0x4E, 0x43, 0x43, 0x48])) return null;
    if (_startsWith(head, 0, const [0x5A, 0x33, 0x44, 0x53])) return null;
    if (_startsWith(head, 0, const [0x41, 0x5A, 0x43, 0x52])) return null;
    return 'no NCCH header at 0x100 (nor a Z3DS or AZCR container)';
  }

  /// Key-free fingerprint of a title content Azahar may have encrypted for
  /// its console in the legacy form the core still opens (azahar a5c3d4f8
  /// `CryptoIOFile::IsCryptoIOFile`, "Legacy mode": the whole file in
  /// AES-CTR, no `AZCR` header, with one key and one counter derived from
  /// the console's OTP for every file, `UniqueData::OpenUniqueCryptoFile`).
  /// Every NCCH holds in clear `NCCH` at 0x100, its size in 0x200-byte units
  /// at 0x104, its program id — the title id — at 0x118 and zeros at
  /// 0x120–0x12F: XORed with them, the stored bytes give the keystream at
  /// those offsets, the same for every content of one console whatever its
  /// title and size. The SHA-256 of those 32 keystream bytes is returned (no
  /// key material is kept). Null when [head] cannot be such a content: a
  /// DS title, a size that is not a whole number of 0x200-byte units, a
  /// head shorter than 0x130 bytes.
  @visibleForTesting
  static String? consoleCryptoFingerprint(
    Uint8List head,
    int size,
    String? titleKey,
  ) {
    if (titleKey == null || head.length < 0x130) return null;
    if (size < 0x200 || size % 0x200 != 0 || size ~/ 0x200 > 0xFFFFFFFF) {
      return null;
    }
    final parts = titleKey.split('/');
    final high = int.parse(parts.first, radix: 16);
    final low = int.parse(parts.last, radix: 16);
    if ((high & 0x8000) != 0) return null;
    final plain = Uint8List(0x30);
    plain.setAll(0, const [0x4E, 0x43, 0x43, 0x48]);
    ByteData.sublistView(plain)
      ..setUint32(0x04, size ~/ 0x200, Endian.little)
      ..setUint32(0x18, low, Endian.little)
      ..setUint32(0x1C, high, Endian.little);
    final keystream = <int>[
      for (var offset = 0x00; offset < 0x08; offset++)
        head[0x100 + offset] ^ plain[offset],
      for (var offset = 0x18; offset < 0x30; offset++)
        head[0x100 + offset] ^ plain[offset],
    ];
    return sha256.convert(keystream).toString();
  }

  /// The console key the contents Azahar encrypted for their console share,
  /// or null. Only agreement between contents of different titles or sizes
  /// confirms it (one content alone, or two copies of one header, checks
  /// nothing), and there must be one such key: contents of two consoles
  /// cannot both be read with one `otp.bin`.
  static String? _consoleCryptoConsensus(Iterable<_TitleFile> files) {
    final support = <String, Set<String>>{};
    for (final file in files) {
      final fingerprint = file.consoleCrypto;
      if (fingerprint == null) continue;
      final segments = file.target.split('/');
      support
          .putIfAbsent(fingerprint, () => <String>{})
          .add('${segments[3]}/${segments[4]}:${file.source.size}');
    }
    final confirmed = [
      for (final entry in support.entries)
        if (entry.value.length >= 2) entry.key,
    ];
    return confirmed.length == 1 ? confirmed.single : null;
  }

  /// An NCCH title content the core refuses as encrypted (azahar
  /// `NCCHContainer::LoadHeader`: no `NoCrypto` flag); a DS title holds no
  /// NCCH.
  static bool _isEncryptedContent(Uint8List head, String? titleKey) {
    final high = titleKey == null
        ? 0
        : int.parse(titleKey.split('/').first, radix: 16);
    return (high & 0x8000) == 0 && Libretro3dsNcch.isEncrypted(head);
  }

  /// Null when [prefix] (at least the first 0xC04 bytes of a [size]-byte
  /// file) is a title metadata file of title [titleKey], checked like azahar
  /// a5c3d4f8 `TitleMetadata::Load`: a known signature type, a body of
  /// 0x9C4 bytes after the aligned signature, every content chunk inside
  /// the file, and the title id of the body.
  @visibleForTesting
  static String? tmdProblem(Uint8List prefix, int size, String? titleKey) {
    if (prefix.length < 4) return 'tmd of $size bytes';
    final view = ByteData.sublistView(prefix);
    final signatureType = view.getUint32(0, Endian.big);
    final signatureSize = switch (signatureType) {
      0x10000 || 0x10003 => 0x200,
      0x10001 || 0x10004 => 0x100,
      0x10002 || 0x10005 => 0x3C,
      _ => 0,
    };
    if (signatureSize == 0) {
      return 'tmd signature type 0x${signatureType.toRadixString(16)}';
    }
    final bodyStart = (signatureSize + 4 + 0x3F) & ~0x3F;
    final bodyEnd = bodyStart + 0x9C4;
    if (size < bodyEnd || prefix.length < bodyEnd) {
      return 'tmd of $size bytes, body ends at 0x${bodyEnd.toRadixString(16)}';
    }
    final contentCount = view.getUint16(bodyStart + 0x9E, Endian.big);
    if (size < bodyEnd + contentCount * 0x30) {
      return 'tmd of $size bytes for $contentCount contents';
    }
    if (titleKey != null) {
      final high = view.getUint32(bodyStart + 0x4C, Endian.big);
      final low = view.getUint32(bodyStart + 0x50, Endian.big);
      final id =
          '${high.toRadixString(16).padLeft(8, '0')}/'
          '${low.toRadixString(16).padLeft(8, '0')}';
      if (id != titleKey) return 'tmd of title $id in folder $titleKey';
    }
    return null;
  }

  /// Null when the core would read at least one AES slot key from [bytes];
  /// else why not. Mirrors azahar a5c3d4f8 `LoadPresetKeys`
  /// (`hw/aes/key.cpp`): lines split on `\n` only, `#` comments, a line
  /// starting with `:` selects a section and only `:AES` lines are read, a
  /// key line is exactly `name=value` with a `slot0x<hex>Key<X|Y|N>` name
  /// (slot below 0x40) and at least 32 hex digits. A present keys.txt
  /// replaces the keys built into the core, so a file it reads nothing from
  /// is refused.
  @visibleForTesting
  static String? keysProblem(Uint8List bytes) {
    if (bytes.isEmpty) return 'empty keys file';
    final text = latin1.decode(bytes);
    var mode = '';
    var sections = 0;
    var keys = 0;
    for (final line in text.split('\n')) {
      if (line.isEmpty || line.startsWith('#')) continue;
      if (line.startsWith(':')) {
        mode = line.substring(1);
        if (mode == 'AES') sections++;
        continue;
      }
      if (mode != 'AES') continue;
      final parts = line.split('=');
      if (parts.length != 2) continue;
      final slot = _aesSlotName.firstMatch(parts[0]);
      if (slot == null || !_aesKeyValue.hasMatch(parts[1])) continue;
      if (int.parse(slot.group(1)!, radix: 16) < 0x40) keys++;
    }
    if (keys > 0) return null;
    if (text.startsWith('ï»¿:')) {
      return 'byte-order mark before the first section header';
    }
    if (text.contains(':AES\r')) {
      return 'CRLF line ends: ":AES" is not read as a section header';
    }
    if (sections == 0) {
      return 'no ":AES" section (Citra-era aes_keys.txt format)';
    }
    return 'no AES slot key under ":AES"';
  }

  static bool _startsWith(Uint8List bytes, int offset, List<int> magic) {
    if (bytes.length < offset + magic.length) return false;
    for (var index = 0; index < magic.length; index++) {
      if (bytes[offset + index] != magic[index]) return false;
    }
    return true;
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
    bool starts(List<int> magic) => _startsWith(head, 0, magic);

    if (starts(const [0x37, 0x7A, 0xBC, 0xAF, 0x27, 0x1C])) return '7z';
    if (starts(const [0x52, 0x61, 0x72, 0x21, 0x1A, 0x07])) return 'rar';
    if (starts(const [0x1F, 0x8B])) return 'gzip';
    if (starts(const [0xFD, 0x37, 0x7A, 0x58, 0x5A, 0x00])) return 'xz';
    if (starts(const [0x42, 0x5A, 0x68])) return 'bzip2';
    if (starts(const [0x28, 0xB5, 0x2F, 0xFD])) return 'zstd';
    if (_startsWith(head, 0x101, const [0x75, 0x73, 0x74, 0x61, 0x72])) {
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
      _startsWith(head, 0x100, const [0x4E, 0x43, 0x53, 0x44]);

  /// Backslashes become `/` and leading `./` segments go (PowerShell 5
  /// `Compress-Archive` writes both) before the traversal checks.
  static String _normalizeZipName(String name) {
    var normalized = name.replaceAll('\\', '/');
    while (normalized.startsWith('./')) {
      normalized = normalized.substring(2);
    }
    return normalized;
  }

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

  /// Why an entry cannot be read as is: encryption, or a compression method
  /// other than stored (0) or deflate (8) in the central directory or in
  /// the local header (archive 4.0.9 decodes unknown methods as stored).
  static Future<_Refusal?> _zipEntryProblem(
    RandomAccessFile headers,
    ArchiveFile entry,
  ) async {
    final content = entry.rawContent;
    if (content is! ZipFile) return null;
    final header = content.header;
    if ((content.flags & 0x1) != 0 ||
        ((header?.generalPurposeBitFlag ?? 0) & 0x1) != 0) {
      return _Refusal(Libretro3dsRejection.invalid, 'encrypted entry');
    }
    final central = header?.compressionMethod ?? -1;
    if (central != 0 && central != 8) {
      return _Refusal(
        Libretro3dsRejection.unsupportedCompression,
        'compression method $central',
      );
    }
    final offset = header?.localHeaderOffset;
    if (offset == null) return null;
    await headers.setPosition(offset);
    final local = await headers.read(30);
    final method = _localMethod(local);
    if (method == null) {
      return _Refusal(Libretro3dsRejection.invalid, 'no local header');
    }
    if (method != 0 && method != 8) {
      return _Refusal(
        Libretro3dsRejection.unsupportedCompression,
        'compression method $method',
      );
    }
    return null;
  }

  static int? _localMethod(Uint8List local) {
    if (local.length < 30) return null;
    final view = ByteData.sublistView(local);
    if (view.getUint32(0, Endian.little) != ZipFile.zipSignature) return null;
    return view.getUint16(8, Endian.little);
  }

  // ---------------------------------------------------------------------
  // Install
  // ---------------------------------------------------------------------

  /// Installs the installable elements of [plan] as one crash-safe pass:
  /// interrupted passes are recovered first; everything is staged beside
  /// the user directory and verified by SHA-256 against the analysis; each
  /// existing destination (a file, or a title's whole `content` folder) is
  /// moved into `Backups/Azahar/<stamp>/<relative path>` by rename, then
  /// each staged element is moved into place by rename. On a failure the
  /// pass is put back by renames (no copy, no free space needed) and its
  /// emptied backup folder removed. Refused while a session is active or
  /// launching.
  Future<Libretro3dsInstallReport> install(
    Libretro3dsImportPlan plan, {
    bool includeConsoleUnique = false,
    bool includeKeys = false,
  }) => _exclusive(() async {
    await _refuseWhenSessionActive();
    final recovery = await _recoverLocked();
    if (recovery.failed) {
      throw Libretro3dsSystemDataException(
        Libretro3dsSystemDataError.unfinishedPass,
        technicalDetail: _recoveryDetail(recovery),
      );
    }
    return _install(
      plan,
      includeConsoleUnique: includeConsoleUnique,
      includeKeys: includeKeys,
      recovery: recovery.isEmpty ? null : recovery,
    );
  });

  Future<Libretro3dsInstallReport> _install(
    Libretro3dsImportPlan plan, {
    required bool includeConsoleUnique,
    required bool includeKeys,
    required Libretro3dsRecoveryReport? recovery,
  }) async {
    final stamp = _stamp(now());
    final user = await userDirectory();
    final backupsRoot = (await backupsDirectory()).path;

    final results = List<Libretro3dsInstallResult?>.filled(
      plan.items.length,
      null,
    );
    // Titles Azahar encrypted for their console are read by the core with
    // that console's otp.bin only: installed now, or by this pass.
    final consoleOtpReady =
        (includeConsoleUnique && plan.installsConsoleOtp) ||
        await _hasConsoleOtp(user.path);
    final pendingFiles = <int>[];
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
        case Libretro3dsItemKind.config:
          if (!includeConsoleUnique) status = Libretro3dsInstallStatus.excluded;
        case Libretro3dsItemKind.title:
          if (item.consoleEncrypted && !consoleOtpReady) {
            status = Libretro3dsInstallStatus.excluded;
          }
        case Libretro3dsItemKind.seeddb:
          break;
      }
      if (status == null &&
          item.action == Libretro3dsPlanAction.skipIdentical) {
        status = Libretro3dsInstallStatus.skippedIdentical;
      }
      if (status == null &&
          (item.relativeTarget == null ||
              item._locator == null ||
              !_isSafeTarget(item.relativeTarget!) ||
              (item.kind == Libretro3dsItemKind.title &&
                  item.titleKey == null))) {
        status = Libretro3dsInstallStatus.rejected;
      }
      if (status != null) {
        results[index] = Libretro3dsInstallResult(item: item, status: status);
        continue;
      }
      pendingFiles.add(index);
    }

    // One unit per file, one per title (its whole content folder).
    final units = <_Unit>[];
    final titleUnits = <String, _Unit>{};
    for (final index in pendingFiles) {
      final item = plan.items[index];
      final file = _UnitFile(
        target: item.relativeTarget!,
        size: item.size,
        expectedHash: item.sourceHash,
        locator: item._locator,
        itemIndex: index,
        consoleCrypto: item._consoleCrypto,
      );
      if (item.kind == Libretro3dsItemKind.title) {
        final unit = titleUnits.putIfAbsent(item.titleKey!, () {
          final created = _Unit(
            target: '$titleRoot/${item.titleKey}/content',
            dir: true,
          );
          units.add(created);
          return created;
        });
        unit.files.add(file);
      } else {
        units.add(
          _Unit(target: item.relativeTarget!, dir: false)..files.add(file),
        );
      }
    }

    final journal = _Journal(
      this,
      '$journalPrefix$stamp.jsonl',
      redactions: _redactions(user, backupsRoot, sources: plan.sources),
    );
    journal.add({
      'event': 'install',
      'stamp': stamp,
      'sources': [for (final source in plan.sources) p.basename(source)],
      'includeConsoleUnique': includeConsoleUnique,
      'includeKeys': includeKeys,
    });

    _PassOutcome? outcome;
    if (units.isNotEmpty) {
      outcome = await _runPass(
        kind: 'import',
        stamp: stamp,
        user: user,
        units: units,
        stagingPrefixName: stagingPrefix,
        stage: (staging) => _stageImport(units, staging),
      );
    }

    var rolledBack = false;
    String? failure;
    String? backupDirectory;
    final retired = <String>[];
    final missing = <String>[];
    if (outcome != null) {
      failure = outcome.failure;
      rolledBack = outcome.rolledBack;
      missing.addAll(outcome.missing);
      if (outcome.committed && outcome.backupComplete) {
        backupDirectory = outcome.pass.path;
      }
      retired.addAll(outcome.retired);
      for (var at = 0; at < units.length; at++) {
        final unit = units[at];
        for (final file in unit.files) {
          final item = plan.items[file.itemIndex];
          final backupPath = p.joinAll([
            outcome.pass.path,
            ...file.target.split('/'),
          ]);
          final Libretro3dsInstallStatus status;
          String? detail;
          String? backup;
          if (outcome.committed) {
            final replaced =
                unit.backedUp &&
                (!unit.dir || outcome.backedUpFiles.contains(file.target));
            status = replaced
                ? Libretro3dsInstallStatus.replaced
                : Libretro3dsInstallStatus.installed;
            backup = replaced ? backupPath : null;
          } else {
            final state = outcome.unitStates[at];
            switch (state) {
              case _UnitState.failed:
                // A file of a failed title that did not fail itself was
                // not installed because of its title.
                status = file.failure != null
                    ? Libretro3dsInstallStatus.failed
                    : Libretro3dsInstallStatus.notAttempted;
                detail = file.failure ?? outcome.unitFailures[at] ?? failure;
              case _UnitState.rolledBack:
                status = Libretro3dsInstallStatus.rolledBack;
                detail = failure;
              case _UnitState.rollbackFailed:
                status = Libretro3dsInstallStatus.failed;
                detail = outcome.unitFailures[at] ?? failure;
              case _UnitState.notAttempted:
                status = Libretro3dsInstallStatus.notAttempted;
                detail = failure;
            }
          }
          results[file.itemIndex] = Libretro3dsInstallResult(
            item: item,
            status: status,
            backupPath: backup,
            technicalDetail: detail,
          );
        }
      }
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
    if (outcome != null) {
      journal.redactions[outcome.pass.path] =
          'Backups/$coreFolderName/${p.basename(outcome.pass.path)}';
      journal.redactions[outcome.staging.path] = '<staging>';
    }
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
    for (final target in retired) {
      journal.add({'event': 'retired', 'target': target});
    }
    journal.add({
      'event': 'end',
      'rolledBack': rolledBack,
      'failure': ?failure,
      if (missing.isNotEmpty) 'missing': missing,
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
      backupDirectory: backupDirectory,
      journalPath: journalPath,
      failure: failure,
      retired: List.unmodifiable(retired),
      missing: List.unmodifiable(missing),
      recovery: recovery,
    );
    _log.i(
      'Libretro3dsImport $stamp: installed ${report.count(Libretro3dsInstallStatus.installed)}, '
      'replaced ${report.count(Libretro3dsInstallStatus.replaced)}, '
      'failed ${report.count(Libretro3dsInstallStatus.failed)}'
      '${rolledBack ? ', rolled back' : ''}'
      '${missing.isEmpty ? '' : ', missing ${missing.join(', ')}'}',
    );
    return report;
  }

  /// Stages every file of [units] in a background isolate (bounded memory,
  /// written byte count checked against the declared size), then checks
  /// each staged copy against the analysis: same SHA-256, or for a large
  /// title file the same source size and modification time before and
  /// after, and a staged copy that validates again.
  Future<String?> _stageImport(List<_Unit> units, Directory staging) async {
    final jobs = <_StageJob>[];
    final files = <_UnitFile>[];
    for (final unit in units) {
      if (unit.dir) {
        await Directory(
          p.joinAll([staging.path, ...unit.target.split('/')]),
        ).create(recursive: true);
      }
      for (final file in unit.files) {
        final locator = file.locator!;
        jobs.add(
          _StageJob(
            staged: p.joinAll([staging.path, ...file.target.split('/')]),
            size: file.size,
            container: locator.kind == Libretro3dsSourceKind.zip
                ? locator.containerPath
                : null,
            entry: locator.entryName,
            file: locator.filePath,
            sliceStart: locator.sliceStart,
          ),
        );
        files.add(file);
      }
    }
    final before = [
      for (final file in files) await _sourceStamp(file.locator!),
    ];
    final outcomes = await _stageInBackground(jobs);
    String? failure;
    for (var index = 0; index < files.length; index++) {
      final file = files[index];
      final (hash, error) = outcomes[index];
      file.stagedHash = hash;
      String? problem = error;
      if (problem == null) {
        final expected = file.expectedHash;
        if (expected != null) {
          if (hash != expected) problem = 'source changed since analysis';
        } else {
          final locator = file.locator!;
          final after = await _sourceStamp(locator);
          if (before[index] != locator.stamp || after != locator.stamp) {
            problem = 'source changed since analysis';
          } else {
            problem = await _revalidateStaged(file, jobs[index].staged);
          }
        }
      }
      if (problem != null) {
        file.failure = problem;
        failure ??= problem;
      }
    }
    return failure;
  }

  /// Size and modification time of the file an element is read from (its
  /// ZIP for an entry), as recorded at analysis.
  static Future<String?> _sourceStamp(_ItemLocator locator) async {
    try {
      final path = locator.kind == Libretro3dsSourceKind.zip
          ? locator.containerPath
          : locator.filePath!;
      final stat = await File(path).stat();
      if (stat.type == FileSystemEntityType.notFound) return null;
      return '${stat.size}@${stat.modified.millisecondsSinceEpoch}';
    } catch (_) {
      return null;
    }
  }

  static Future<String?> _revalidateStaged(
    _UnitFile file,
    String staged,
  ) async {
    final source = _PlainSourceFile(
      File(staged),
      file.target,
      file.size,
      Libretro3dsSourceKind.file,
      0,
    );
    final segments = file.target.split('/');
    final titleKey = segments.length > 5 && file.target.startsWith(titleRoot)
        ? '${segments[3]}/${segments[4]}'
        : null;
    try {
      final head = await source.prefix(0x200);
      String? consoleCrypto;
      final refusal = await _validateContent(
        Libretro3dsItemKind.title,
        source,
        head,
        const Libretro3dsImportLimits(),
        titleKey: titleKey,
        target: file.target,
        onConsoleCrypto: (fingerprint) => consoleCrypto = fingerprint,
      );
      if (refusal != null) return refusal.detail;
      if (consoleCrypto != null && consoleCrypto != file.consoleCrypto) {
        return 'no NCCH header at 0x100 (nor a Z3DS or AZCR container): '
            '$_consoleCryptoUnconfirmed';
      }
      return null;
    } catch (error) {
      return _detail(error);
    }
  }

  // ---------------------------------------------------------------------
  // Pass engine (install and restore)
  // ---------------------------------------------------------------------

  /// One pass: backup folder and write-ahead journal, staging, backups of
  /// the existing destinations by rename, installs by rename, then the
  /// manifest's completion marker. Any failure before the commit record
  /// puts everything back by rename ([_rollback]).
  Future<_PassOutcome> _runPass({
    required String kind,
    required String stamp,
    required Directory user,
    required List<_Unit> units,
    required String stagingPrefixName,
    required Future<String?> Function(Directory staging) stage,
  }) async {
    final unitStates = List<_UnitState>.filled(
      units.length,
      _UnitState.notAttempted,
    );
    final unitFailures = <int, String>{};
    Directory? pass;
    Directory? staging;
    _PassLog? log;

    _PassOutcome abort(String failure, {int? failedUnit}) {
      if (failedUnit != null) {
        unitStates[failedUnit] = _UnitState.failed;
        unitFailures[failedUnit] = failure;
      }
      return _PassOutcome(
        pass: pass ?? Directory(''),
        staging: staging ?? Directory(''),
        committed: false,
        rolledBack: false,
        failure: failure,
        unitStates: unitStates,
        unitFailures: unitFailures,
      );
    }

    try {
      await user.create(recursive: true);
      pass = await _newPassDirectory(stamp);
      staging = Directory(
        p.join(user.parent.path, '$stagingPrefixName${p.basename(pass.path)}'),
      );
      if (await staging.exists()) await staging.delete(recursive: true);
      await staging.create(recursive: true);
      log = await _PassLog.open(File(p.join(pass.path, passLogName)));
      await log.add({
        'op': 'begin',
        'kind': kind,
        'stamp': stamp,
        'pass': p.basename(pass.path),
        'staging': p.basename(staging.path),
        'units': [
          for (final unit in units) {'target': unit.target, 'dir': unit.dir},
        ],
      });
    } catch (error) {
      final failure = _detail(error);
      for (var at = 0; at < units.length; at++) {
        unitStates[at] = _UnitState.failed;
        unitFailures[at] = failure;
        for (final file in units[at].files) {
          file.failure = failure;
        }
      }
      await log?.close();
      if (staging != null) await _deleteQuietly(staging);
      if (pass != null) await _deletePassIfEmpty(pass);
      return abort(failure);
    }

    // 1. Stage and verify everything: a failure leaves the user directory
    //    untouched.
    String? stageFailure;
    try {
      stageFailure = await stage(staging);
    } catch (error) {
      stageFailure = _detail(error);
    }
    if (stageFailure != null) {
      for (var at = 0; at < units.length; at++) {
        final failed = units[at].files.where((file) => file.failure != null);
        if (failed.isNotEmpty) {
          unitStates[at] = _UnitState.failed;
          unitFailures[at] = failed.first.failure!;
        }
      }
      if (!unitStates.contains(_UnitState.failed)) {
        unitStates[0] = _UnitState.failed;
        unitFailures[0] = stageFailure;
        for (final file in units[0].files) {
          file.failure = stageFailure;
        }
      }
      await log.add({'op': 'end', 'result': 'staging failed'});
      await log.close();
      await _deleteQuietly(staging);
      await _deletePassIfEmpty(pass);
      return abort(stageFailure);
    }

    // 2. Commit: every backup first, then every install.
    final backupIntents = <int>{};
    final installIntents = <int, List<_Expected>>{};
    var at = 0;
    // The file a test hook refused, when the failure is one file's.
    _UnitFile? failingFile;
    try {
      for (at = 0; at < units.length; at++) {
        final unit = units[at];
        final target = _userPath(user, unit.target);
        if (await FileSystemEntity.type(target, followLinks: false) ==
            FileSystemEntityType.notFound) {
          continue;
        }
        await log.add({'op': 'backup', 'unit': at});
        backupIntents.add(at);
        await beforeBackup?.call(unit.target);
        await _move(target, _userPath(pass, unit.target));
        unit.backedUp = true;
      }
      final manifestFiles = <Libretro3dsBackupFile>[];
      for (final unit in units.where((unit) => unit.backedUp)) {
        manifestFiles.addAll(await _hashTree(pass, unit.target));
      }
      if (units.any((unit) => unit.backedUp)) {
        await _writeManifest(pass, kind, stamp, units, manifestFiles);
        await log.add({'op': 'manifest'});
      }
      for (at = 0; at < units.length; at++) {
        final unit = units[at];
        final expected = [
          for (final file in unit.files)
            _Expected(file.target, file.size, file.stagedHash),
        ];
        await log.add({
          'op': 'install',
          'unit': at,
          'files': [for (final file in expected) file.toJson()],
        });
        installIntents[at] = expected;
        for (final file in unit.files) {
          failingFile = file;
          await beforeCommit?.call(file.target);
        }
        failingFile = null;
        final target = _userPath(user, unit.target);
        if (await FileSystemEntity.type(target, followLinks: false) !=
            FileSystemEntityType.notFound) {
          throw FileSystemException(
            'destination appeared during the install',
            target,
          );
        }
        await Directory(p.dirname(target)).create(recursive: true);
        await _move(_userPath(staging, unit.target), target);
        unit.installed = true;
      }
      await log.add({'op': 'committed'});

      // 3. Committed: mark the backup complete, then clean up.
      final backedUpFiles = {
        for (final file in manifestFiles) file.relativePath,
      };
      final retired = <String>[
        for (final unit in units.where((unit) => unit.backedUp && unit.dir))
          ...backedUpFiles.where(
            (path) =>
                path.startsWith('${unit.target}/') &&
                !unit.files.any((file) => file.target == path),
          ),
      ]..sort();
      await beforeFinish?.call();
      var backupComplete = false;
      String? warning;
      if (manifestFiles.isNotEmpty) {
        try {
          await _writeCompleteMarker(pass, manifestFiles);
          backupComplete = true;
        } catch (error) {
          // The pass is installed and its originals are in the backup
          // folder; the next recovery writes the marker again.
          warning = 'backup not marked complete: ${_detail(error)}';
          _log.w('Libretro3dsSystemData $warning');
        }
      }
      await _deleteQuietly(staging);
      if (backupComplete) {
        await log.add({'op': 'end', 'result': 'committed'});
        await log.close();
      } else if (manifestFiles.isEmpty) {
        await log.close();
        await _deletePassIfEmpty(pass);
      } else {
        await log.close();
      }
      return _PassOutcome(
        pass: pass,
        staging: staging,
        committed: true,
        rolledBack: false,
        backupComplete: backupComplete,
        failure: warning,
        unitStates: unitStates,
        unitFailures: unitFailures,
        backedUpFiles: backedUpFiles,
        retired: retired,
      );
    } catch (error) {
      final failure = _detail(error);
      final failedUnit = at < units.length ? at : null;
      if (failedUnit != null) {
        // One file refused: that file failed, the rest of its title was
        // not attempted; otherwise the whole element failed.
        for (final file
            in failingFile == null ? units[failedUnit].files : [failingFile]) {
          file.failure = failure;
        }
      }
      final rollback = await _rollback(
        user: user,
        pass: pass,
        staging: staging,
        units: [for (final unit in units) (target: unit.target, dir: unit.dir)],
        backupIntents: backupIntents,
        installIntents: installIntents,
      );
      for (var index = 0; index < units.length; index++) {
        if (index == failedUnit) {
          unitStates[index] = _UnitState.failed;
          unitFailures[index] = failure;
        } else if (backupIntents.contains(index) ||
            installIntents.containsKey(index)) {
          final problem = rollback.detailFor(units[index].target);
          unitStates[index] = problem == null
              ? _UnitState.rolledBack
              : _UnitState.rollbackFailed;
          if (problem != null) unitFailures[index] = problem;
        }
      }
      await _closeRolledBackPass(log, rollback, pass, staging);
      return _PassOutcome(
        pass: pass,
        staging: staging,
        committed: false,
        rolledBack: true,
        failure: failure,
        unitStates: unitStates,
        unitFailures: unitFailures,
        missing: rollback.missing,
      );
    }
  }

  /// Puts a pass back by rename, from the last unit to the first: an
  /// element moved in goes back to staging, an original moved into the
  /// backup goes back to the user directory. Nothing is overwritten: when
  /// both an original and something new are present, both stay and the
  /// path is reported.
  Future<_Rollback> _rollback({
    required Directory user,
    required Directory pass,
    required Directory staging,
    required List<({String target, bool dir})> units,
    required Set<int> backupIntents,
    required Map<int, List<_Expected>> installIntents,
  }) async {
    final result = _Rollback();
    for (var index = units.length - 1; index >= 0; index--) {
      final unit = units[index];
      final live = _userPath(user, unit.target);
      final installed = installIntents[index];
      if (installed != null) {
        final liveType = await FileSystemEntity.type(live, followLinks: false);
        final stagedPath = _userPath(staging, unit.target);
        final stagedType = await FileSystemEntity.type(
          stagedPath,
          followLinks: false,
        );
        if (liveType != FileSystemEntityType.notFound &&
            stagedType == FileSystemEntityType.notFound) {
          // Only what this pass moved in, byte for byte, is taken out:
          // anything changed or added since stays where it is.
          if (!await _isExactly(user, live, unit.dir, installed)) {
            result.notes[unit.target] =
                '${unit.target} changed since this pass installed it: kept';
            result.kept.add(unit.target);
            continue;
          }
          try {
            await _move(live, stagedPath);
            result.removed.add(unit.target);
          } catch (error) {
            result.problems[unit.target] = _detail(error);
            continue;
          }
        }
      }
      if (backupIntents.contains(index)) {
        final backup = _userPath(pass, unit.target);
        final backupType = await FileSystemEntity.type(
          backup,
          followLinks: false,
        );
        final liveType = await FileSystemEntity.type(live, followLinks: false);
        if (backupType != FileSystemEntityType.notFound) {
          if (liveType == FileSystemEntityType.notFound) {
            try {
              await _move(backup, live);
              result.restored.add(unit.target);
            } catch (error) {
              // Still in the backup folder: missing until a retry succeeds.
              result.problems[unit.target] = _detail(error);
              result.missing.add(unit.target);
            }
          } else {
            result.notes[unit.target] =
                'both the user directory and the backup hold ${unit.target}';
            result.kept.add(unit.target);
          }
        } else if (liveType == FileSystemEntityType.notFound) {
          result.notes[unit.target] = 'original of ${unit.target} not found';
          result.missing.add(unit.target);
        }
      }
    }
    return result;
  }

  // ---------------------------------------------------------------------
  // Recovery
  // ---------------------------------------------------------------------

  /// Finds passes an interruption (the app killed, the phone off) left
  /// unfinished and deals with them: a pass that had not committed is put
  /// back by renames from its journal; one that had committed gets its
  /// backup marked complete. Stale staging folders are then removed. Run
  /// when the page opens and before each install or restore; refused while
  /// a session is active or launching.
  Future<Libretro3dsRecoveryReport> recoverUnfinished() => _exclusive(() async {
    await _refuseWhenSessionActive();
    return _recoverLocked();
  });

  Future<Libretro3dsRecoveryReport> _recoverLocked() async {
    final user = await userDirectory();
    final savesCore = user.parent;
    final root = await backupsDirectory();
    final passes = <Libretro3dsRecoveredPass>[];
    final keepStaging = <String>{};
    if (await root.exists()) {
      final folders = <Directory>[];
      await for (final entity in root.list(followLinks: false)) {
        if (entity is Directory &&
            _backupName.hasMatch(p.basename(entity.path))) {
          folders.add(entity);
        }
      }
      folders.sort((a, b) => a.path.compareTo(b.path));
      for (final folder in folders) {
        final state = await _readPassLog(folder);
        if (state == null || state.ended) continue;
        final recovered = await _recoverPass(folder, state, user, savesCore);
        passes.add(recovered);
        if (recovered.outcome == Libretro3dsRecoveryOutcome.failed &&
            state.staging != null) {
          keepStaging.add(state.staging!);
        }
      }
    }
    final removedStaging = <String>[];
    if (await savesCore.exists()) {
      await for (final entity in savesCore.list(followLinks: false)) {
        if (entity is! Directory) continue;
        final name = p.basename(entity.path);
        if (!name.startsWith(stagingPrefix) &&
            !name.startsWith(restoreStagingPrefix)) {
          continue;
        }
        if (keepStaging.contains(name)) continue;
        try {
          await entity.delete(recursive: true);
          removedStaging.add(name);
        } catch (error) {
          _log.w('Libretro3dsSystemData could not remove $name: $error');
        }
      }
    }
    removedStaging.sort();
    if (passes.isEmpty && removedStaging.isEmpty) {
      return const Libretro3dsRecoveryReport();
    }
    final stamp = _stamp(now());
    final journal = _Journal(
      this,
      '$journalPrefix$stamp.jsonl',
      redactions: _redactions(user, root.path),
    );
    for (final pass in passes) {
      journal.add({
        'event': 'recovered',
        'pass': pass.name,
        'kind': pass.kind,
        'outcome': pass.outcome.name,
        'restored': pass.restored,
        'removed': pass.removed,
        if (pass.missing.isNotEmpty) 'missing': pass.missing,
        if (pass.kept.isNotEmpty) 'kept': pass.kept,
        'detail': ?pass.technicalDetail,
      });
    }
    if (removedStaging.isNotEmpty) {
      journal.add({'event': 'stagingRemoved', 'folders': removedStaging});
    }
    final report = Libretro3dsRecoveryReport(
      passes: List.unmodifiable(passes),
      removedStaging: List.unmodifiable(removedStaging),
      journalPath: await journal.write(),
    );
    _log.i(
      'Libretro3dsSystemData recovery: '
      '${[for (final pass in passes) '${pass.name} ${pass.outcome.name}'].join(', ')}'
      '${removedStaging.isEmpty ? '' : '; staging removed ${removedStaging.length}'}',
    );
    return report;
  }

  Future<Libretro3dsRecoveredPass> _recoverPass(
    Directory pass,
    _PassState state,
    Directory user,
    Directory savesCore,
  ) async {
    final name = p.basename(pass.path);
    final staging = state.staging == null
        ? Directory(p.join(savesCore.path, '${stagingPrefix}missing'))
        : Directory(p.join(savesCore.path, state.staging!));
    if (state.invalid != null) {
      return Libretro3dsRecoveredPass(
        name: name,
        kind: state.kind,
        outcome: Libretro3dsRecoveryOutcome.failed,
        technicalDetail: state.invalid,
      );
    }
    if (state.committed) {
      // Installed: only the marker and the cleanup were missing.
      try {
        final manifest = await _readManifest(pass);
        String? note;
        if (manifest != null && manifest.files.isNotEmpty) {
          for (final file in manifest.files) {
            final stat = await File(_userPath(pass, file.relativePath)).stat();
            if (stat.type != FileSystemEntityType.file ||
                stat.size != file.size) {
              note =
                  'backup file ${file.relativePath} differs from the manifest';
              break;
            }
          }
          if (note == null &&
              !await File(p.join(pass.path, completeMarkerName)).exists()) {
            await _writeCompleteMarker(pass, manifest.files);
          }
        } else if (state.backups.isNotEmpty) {
          note = 'no valid manifest';
        }
        await _deleteQuietly(staging);
        final log = await _PassLog.open(File(p.join(pass.path, passLogName)));
        await log.add({
          'op': 'end',
          'result': note == null
              ? 'recovered: completed'
              : 'recovered: committed, backup not complete',
        });
        await log.close();
        if (manifest == null || manifest.files.isEmpty) {
          await _deletePassIfEmpty(pass);
        }
        return Libretro3dsRecoveredPass(
          name: name,
          kind: state.kind,
          // A backup that no longer matches its manifest stays unlisted;
          // the installed files are what the pass committed.
          outcome: note == null
              ? Libretro3dsRecoveryOutcome.completed
              : Libretro3dsRecoveryOutcome.partial,
          technicalDetail: note,
        );
      } catch (error) {
        return Libretro3dsRecoveredPass(
          name: name,
          kind: state.kind,
          outcome: Libretro3dsRecoveryOutcome.failed,
          technicalDetail: _detail(error),
        );
      }
    }
    final rollback = await _rollback(
      user: user,
      pass: pass,
      staging: staging,
      units: state.units,
      backupIntents: state.backups,
      installIntents: state.installs,
    );
    _PassLog? log;
    try {
      log = await _PassLog.open(File(p.join(pass.path, passLogName)));
    } catch (_) {}
    final emptied = await _closeRolledBackPass(log, rollback, pass, staging);
    final details = [...rollback.problems.values, ...rollback.notes.values];
    return Libretro3dsRecoveredPass(
      name: name,
      kind: state.kind,
      outcome: rollback.retryable
          ? Libretro3dsRecoveryOutcome.failed
          : rollback.clean && emptied
          ? Libretro3dsRecoveryOutcome.rolledBack
          : Libretro3dsRecoveryOutcome.partial,
      restored: rollback.restored,
      removed: rollback.removed,
      missing: rollback.missing,
      kept: rollback.kept,
      technicalDetail: details.isEmpty
          ? (emptied ? null : 'backup folder still holds files')
          : details.join(' • '),
    );
  }

  /// After a rollback: a step that failed keeps the pass open (journal
  /// without end, staging kept) for the next recovery; otherwise the pass
  /// is closed, its staging removed and its folder deleted when it holds
  /// nothing but its metadata (an original kept apart stays there). True
  /// when the folder is gone.
  Future<bool> _closeRolledBackPass(
    _PassLog? log,
    _Rollback rollback,
    Directory pass,
    Directory staging,
  ) async {
    if (rollback.retryable) {
      try {
        await log?.add({'op': 'rollbackIncomplete'});
      } catch (_) {}
      await log?.close();
      return false;
    }
    try {
      await log?.add({
        'op': 'end',
        'result': rollback.clean ? 'rolled back' : 'rolled back with losses',
      });
    } catch (_) {}
    await log?.close();
    await _deleteQuietly(staging);
    return _deletePassIfEmpty(pass);
  }

  static String _recoveryDetail(Libretro3dsRecoveryReport report) => [
    for (final pass in report.passes)
      if (pass.outcome == Libretro3dsRecoveryOutcome.failed)
        '${pass.name}: ${pass.technicalDetail ?? 'not undone'}',
  ].join(' • ');

  // ---------------------------------------------------------------------
  // Restore
  // ---------------------------------------------------------------------

  /// Puts the newest complete backup back, as one crash-safe pass: every
  /// file is checked against the manifest first (nothing is written when
  /// one differs), copied into staging (the backup stays intact), the
  /// current files and title folders it replaces are moved into a new
  /// backup by rename, then the staged ones are moved into place. Files the
  /// restored pass had added (keys, console data, new titles) stay.
  /// Throws [Libretro3dsSystemDataError.noBackup] when there is none and
  /// [Libretro3dsSystemDataError.backupDamaged] when it does not match its
  /// manifest; refused while a session is active or launching.
  Future<Libretro3dsRestoreReport> restoreLastBackup() => _exclusive(() async {
    await _refuseWhenSessionActive();
    final recovery = await _recoverLocked();
    if (recovery.failed) {
      throw Libretro3dsSystemDataException(
        Libretro3dsSystemDataError.unfinishedPass,
        technicalDetail: _recoveryDetail(recovery),
      );
    }
    final all = await backups();
    if (all.isEmpty) {
      throw const Libretro3dsSystemDataException(
        Libretro3dsSystemDataError.noBackup,
      );
    }
    final latest = all.first;
    if (latest.files.isEmpty) {
      throw Libretro3dsSystemDataException(
        Libretro3dsSystemDataError.backupDamaged,
        technicalDetail: '${latest.name}: no file',
      );
    }
    for (final file in latest.files) {
      final source = File(_userPath(Directory(latest.path), file.relativePath));
      String? problem;
      try {
        if (await source.length() != file.size ||
            await _fileSha256(source) != file.sha256) {
          problem = 'content differs from the manifest';
        }
      } catch (error) {
        problem = _detail(error);
      }
      if (problem != null) {
        throw Libretro3dsSystemDataException(
          Libretro3dsSystemDataError.backupDamaged,
          technicalDetail: '${latest.name}/${file.relativePath}: $problem',
        );
      }
    }

    final stamp = _stamp(now());
    final user = await userDirectory();
    final backupsRoot = (await backupsDirectory()).path;
    final units = [
      for (final unit in latest.units)
        _Unit(target: unit.target, dir: unit.dir),
    ];
    for (final file in latest.files) {
      final unit = units.firstWhere(
        (unit) =>
            unit.target == file.relativePath ||
            (unit.dir && file.relativePath.startsWith('${unit.target}/')),
      );
      unit.files.add(
        _UnitFile(
          target: file.relativePath,
          size: file.size,
          expectedHash: file.sha256,
          locator: _ItemLocator.file(
            _userPath(Directory(latest.path), file.relativePath),
            kind: Libretro3dsSourceKind.file,
            stamp: null,
          ),
          itemIndex: -1,
        ),
      );
    }
    final journal = _Journal(
      this,
      '$journalPrefix$stamp.jsonl',
      redactions: _redactions(user, backupsRoot),
    );
    journal.add({'event': 'restore', 'stamp': stamp, 'backup': latest.name});
    final outcome = await _runPass(
      kind: 'restore',
      stamp: stamp,
      user: user,
      units: units,
      stagingPrefixName: restoreStagingPrefix,
      stage: (staging) => _stageRestore(units, staging),
    );
    journal.redactions[outcome.pass.path] =
        'Backups/$coreFolderName/${p.basename(outcome.pass.path)}';
    journal.redactions[outcome.staging.path] = '<staging>';

    final results = <Libretro3dsRestoreResult>[];
    for (var at = 0; at < units.length; at++) {
      for (final file in units[at].files) {
        results.add(
          Libretro3dsRestoreResult(
            relativePath: file.target,
            restored: outcome.committed,
            technicalDetail: outcome.committed
                ? null
                : file.failure ?? outcome.unitFailures[at] ?? outcome.failure,
          ),
        );
      }
    }
    for (final result in results) {
      journal.add({
        'event': 'item',
        'target': result.relativePath,
        'status': result.restored ? 'restored' : 'failed',
        'detail': ?result.technicalDetail,
      });
    }
    final currentBackup = outcome.committed && outcome.backupComplete
        ? outcome.pass.path
        : null;
    journal.add({
      'event': 'end',
      'restored': results.where((r) => r.restored).length,
      'failed': results.where((r) => !r.restored).length,
      'rolledBack': outcome.rolledBack,
      if (outcome.missing.isNotEmpty) 'missing': outcome.missing,
      if (currentBackup != null) 'currentBackup': p.basename(currentBackup),
    });
    return Libretro3dsRestoreReport(
      backupDirectory: latest.path,
      currentBackupDirectory: currentBackup,
      results: results,
      journalPath: await journal.write(),
      rolledBack: outcome.rolledBack,
      failure: outcome.committed ? null : outcome.failure,
      missing: outcome.missing,
      recovery: recovery.isEmpty ? null : recovery,
    );
  });

  Future<String?> _stageRestore(List<_Unit> units, Directory staging) async {
    final jobs = <_StageJob>[];
    final files = <_UnitFile>[];
    for (final unit in units) {
      if (unit.dir) {
        await Directory(
          _userPath(staging, unit.target),
        ).create(recursive: true);
      }
      for (final file in unit.files) {
        jobs.add(
          _StageJob(
            staged: _userPath(staging, file.target),
            size: file.size,
            file: file.locator!.filePath,
          ),
        );
        files.add(file);
      }
    }
    final outcomes = await _stageInBackground(jobs);
    String? failure;
    for (var index = 0; index < files.length; index++) {
      final (hash, error) = outcomes[index];
      files[index].stagedHash = hash;
      final problem =
          error ??
          (hash == files[index].expectedHash
              ? null
              : 'backup changed since it was verified');
      if (problem != null) {
        files[index].failure = problem;
        failure ??= problem;
      }
    }
    return failure;
  }

  // ---------------------------------------------------------------------
  // Backup folders: manifest, marker, journal
  // ---------------------------------------------------------------------

  Future<Directory> _newPassDirectory(String stamp) async {
    final root = await backupsDirectory();
    await root.create(recursive: true);
    var directory = Directory(p.join(root.path, stamp));
    for (var index = 2; await directory.exists(); index++) {
      directory = Directory(p.join(root.path, '$stamp-$index'));
    }
    await directory.create();
    return directory;
  }

  /// Files under [target] of [root] (or [target] itself), with size and
  /// SHA-256, relative to [root].
  static Future<List<Libretro3dsBackupFile>> _hashTree(
    Directory root,
    String target,
  ) async {
    final path = _userPath(root, target);
    final type = await FileSystemEntity.type(path, followLinks: false);
    final files = <File>[];
    if (type == FileSystemEntityType.directory) {
      await for (final entity in Directory(
        path,
      ).list(recursive: true, followLinks: false)) {
        if (entity is File) files.add(entity);
      }
    } else if (type == FileSystemEntityType.file) {
      files.add(File(path));
    }
    files.sort((a, b) => a.path.compareTo(b.path));
    return [
      for (final file in files)
        Libretro3dsBackupFile(
          relativePath: p
              .split(p.relative(file.path, from: root.path))
              .join('/'),
          size: await file.length(),
          sha256: await _fileSha256(file),
        ),
    ];
  }

  Future<void> _writeManifest(
    Directory pass,
    String kind,
    String stamp,
    List<_Unit> units,
    List<Libretro3dsBackupFile> files,
  ) async {
    final manifest = {
      'version': 1,
      'kind': kind,
      'stamp': stamp,
      'createdAt': now().toUtc().toIso8601String(),
      'units': [
        for (final unit in units.where((unit) => unit.backedUp))
          {'target': unit.target, 'dir': unit.dir},
      ],
      'files': [
        for (final file in files)
          {'path': file.relativePath, 'size': file.size, 'sha256': file.sha256},
      ],
    };
    await _writeAtomically(
      File(p.join(pass.path, manifestName)),
      utf8.encode(const JsonEncoder.withIndent('  ').convert(manifest)),
    );
  }

  static Future<void> _writeCompleteMarker(
    Directory pass,
    List<Libretro3dsBackupFile> files,
  ) async {
    final manifest = await File(p.join(pass.path, manifestName)).readAsBytes();
    await _writeAtomically(
      File(p.join(pass.path, completeMarkerName)),
      utf8.encode(
        jsonEncode({
          'version': 1,
          'manifestSha256': sha256.convert(manifest).toString(),
          'files': files.length,
          'bytes': files.fold(0, (total, file) => total + file.size),
        }),
      ),
    );
  }

  static Future<void> _writeAtomically(File file, List<int> bytes) async {
    final temporary = File('${file.path}.tmp');
    await temporary.writeAsBytes(bytes, flush: true);
    await temporary.rename(file.path);
  }

  /// The manifest of [pass], validated (known kind, safe relative paths
  /// under `sysdata/` or `nand/`, files inside a unit, units disjoint);
  /// null when absent or not valid.
  static Future<_Manifest?> _readManifest(Directory pass) async {
    final file = File(p.join(pass.path, manifestName));
    try {
      if (!await file.exists() || await file.length() > 16 << 20) return null;
      final bytes = await file.readAsBytes();
      final json = jsonDecode(utf8.decode(bytes));
      if (json is! Map || json['version'] != 1) return null;
      final kind = json['kind'];
      if (kind != 'import' && kind != 'restore') return null;
      final units = <({String target, bool dir})>[];
      for (final unit in json['units'] as List) {
        final target = (unit as Map)['target'];
        final dir = unit['dir'];
        if (target is! String || dir is! bool || !_isSafeTarget(target)) {
          return null;
        }
        units.add((target: target, dir: dir));
      }
      for (final a in units) {
        for (final b in units) {
          if (!identical(a, b) &&
              (a.target == b.target || b.target.startsWith('${a.target}/'))) {
            return null;
          }
        }
      }
      final files = <Libretro3dsBackupFile>[];
      for (final entry in json['files'] as List) {
        final path = (entry as Map)['path'];
        final size = entry['size'];
        final hash = entry['sha256'];
        if (path is! String ||
            size is! int ||
            size < 0 ||
            hash is! String ||
            !_hex64.hasMatch(hash) ||
            !_isSafeTarget(path) ||
            !units.any(
              (unit) =>
                  unit.target == path ||
                  (unit.dir && path.startsWith('${unit.target}/')),
            )) {
          return null;
        }
        files.add(
          Libretro3dsBackupFile(relativePath: path, size: size, sha256: hash),
        );
      }
      final createdAt =
          DateTime.tryParse(json['createdAt'] as String? ?? '')?.toUtc() ??
          _parseStamp(p.basename(pass.path)) ??
          DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
      return _Manifest(
        kind: kind as String,
        createdAt: createdAt,
        units: units,
        files: files,
        bytes: bytes,
      );
    } catch (_) {
      return null;
    }
  }

  static Future<Libretro3dsBackup?> _readCompleteBackup(Directory dir) async {
    try {
      final marker = File(p.join(dir.path, completeMarkerName));
      if (!await marker.exists() || await marker.length() > 64 << 10) {
        return null;
      }
      final json = jsonDecode(await marker.readAsString());
      if (json is! Map || json['version'] != 1) return null;
      final manifest = await _readManifest(dir);
      if (manifest == null || manifest.files.isEmpty) return null;
      if (sha256.convert(manifest.bytes).toString() != json['manifestSha256']) {
        return null;
      }
      for (final file in manifest.files) {
        final stat = await File(_userPath(dir, file.relativePath)).stat();
        if (stat.type != FileSystemEntityType.file || stat.size != file.size) {
          return null;
        }
      }
      return Libretro3dsBackup(
        path: dir.path,
        name: p.basename(dir.path),
        kind: manifest.kind,
        createdAt: manifest.createdAt,
        files: List.unmodifiable(manifest.files),
        units: List.unmodifiable(manifest.units),
      );
    } catch (_) {
      return null;
    }
  }

  static Future<_PassState?> _readPassLog(Directory pass) async {
    final file = File(p.join(pass.path, passLogName));
    try {
      if (!await file.exists()) return null;
      if (await file.length() > 16 << 20) {
        return _PassState()..invalid = 'pass journal too large';
      }
      final text = utf8.decode(await file.readAsBytes(), allowMalformed: true);
      final state = _PassState();
      for (final line in const LineSplitter().convert(text)) {
        if (line.trim().isEmpty) continue;
        Object? record;
        try {
          record = jsonDecode(line);
        } catch (_) {
          // A line cut by the interruption: its step never started.
          continue;
        }
        if (record is! Map) continue;
        switch (record['op']) {
          case 'begin':
            state.kind = record['kind'] as String? ?? 'import';
            final staging = record['staging'];
            if (staging is String &&
                !staging.contains('/') &&
                !staging.contains('\\') &&
                (staging.startsWith(stagingPrefix) ||
                    staging.startsWith(restoreStagingPrefix))) {
              state.staging = staging;
            }
            for (final unit in record['units'] as List? ?? const []) {
              final target = (unit as Map)['target'];
              final dir = unit['dir'];
              if (target is! String || dir is! bool || !_isSafeTarget(target)) {
                state.invalid = 'unsafe target in the pass journal';
                break;
              }
              state.units.add((target: target, dir: dir));
            }
            state.begun = true;
          case 'backup':
            final unit = record['unit'];
            if (unit is int) state.backups.add(unit);
          case 'install':
            final unit = record['unit'];
            final files = <_Expected>[];
            for (final file in record['files'] as List? ?? const []) {
              final expected = _Expected.fromJson(file);
              if (expected == null) {
                state.invalid ??= 'unreadable install record';
                break;
              }
              files.add(expected);
            }
            if (unit is int) state.installs[unit] = files;
          case 'committed':
            state.committed = true;
          case 'end':
            state.ended = true;
        }
      }
      if (!state.begun) {
        // The journal holds no complete first record: nothing was moved.
        state.units.clear();
      }
      final indexes = {...state.backups, ...state.installs.keys};
      if (indexes.any((index) => index < 0 || index >= state.units.length)) {
        state.invalid ??= 'unknown unit in the pass journal';
      }
      return state;
    } catch (error) {
      return _PassState()..invalid = _detail(error);
    }
  }

  /// Deletes [pass] when it holds nothing but its own metadata; true when
  /// it is gone.
  static Future<bool> _deletePassIfEmpty(Directory pass) async {
    try {
      if (!await pass.exists()) return true;
      await for (final entity in pass.list(
        recursive: true,
        followLinks: false,
      )) {
        if (entity is Directory) continue;
        final relative = p.relative(entity.path, from: pass.path);
        if (relative == passLogName ||
            relative == manifestName ||
            relative == '$manifestName.tmp' ||
            relative == completeMarkerName ||
            relative == '$completeMarkerName.tmp') {
          continue;
        }
        return false;
      }
      await pass.delete(recursive: true);
      return true;
    } catch (error) {
      _log.w('Libretro3dsSystemData could not remove ${pass.path}: $error');
      return false;
    }
  }

  /// Relative path NeoStation writes: `sysdata/…` or `nand/…`, no empty,
  /// `.` or `..` segment, no backslash or NUL.
  static bool _isSafeTarget(String target) {
    if (target.isEmpty ||
        target.startsWith('/') ||
        target.contains('\\') ||
        target.contains('\u0000')) {
      return false;
    }
    final segments = target.split('/');
    if (segments.first != 'sysdata' && segments.first != 'nand') return false;
    if (segments.length < 2) return false;
    return segments.every(
      (segment) => segment.isNotEmpty && segment != '.' && segment != '..',
    );
  }

  static DateTime? _parseStamp(String name) {
    final match = _backupName.firstMatch(name);
    if (match == null) return null;
    final stamp = match.group(1)!;
    return DateTime.utc(
      int.parse(stamp.substring(0, 4)),
      int.parse(stamp.substring(4, 6)),
      int.parse(stamp.substring(6, 8)),
      int.parse(stamp.substring(9, 11)),
      int.parse(stamp.substring(11, 13)),
      int.parse(stamp.substring(13, 15)),
    );
  }

  // ---------------------------------------------------------------------
  // Moves and staging
  // ---------------------------------------------------------------------

  static String _userPath(Directory root, String relative) =>
      p.joinAll([root.path, ...relative.split('/')]);

  /// Whether [live] holds exactly [expected]: the file (or, for a title,
  /// the folder's whole file set) with the same sizes and SHA-256.
  static Future<bool> _isExactly(
    Directory user,
    String live,
    bool dir,
    List<_Expected> expected,
  ) async {
    try {
      final found = <String, File>{};
      if (dir) {
        if (await FileSystemEntity.type(live, followLinks: false) !=
            FileSystemEntityType.directory) {
          return false;
        }
        await for (final entity in Directory(
          live,
        ).list(recursive: true, followLinks: false)) {
          if (entity is Directory) continue;
          if (entity is! File) return false;
          found[p.split(p.relative(entity.path, from: user.path)).join('/')] =
              entity;
        }
      } else {
        if (await FileSystemEntity.type(live, followLinks: false) !=
            FileSystemEntityType.file) {
          return false;
        }
        found[p.split(p.relative(live, from: user.path)).join('/')] = File(
          live,
        );
      }
      if (found.length != expected.length) return false;
      for (final file in expected) {
        final candidate = found[file.path];
        if (candidate == null || await candidate.length() != file.size) {
          return false;
        }
        if (file.sha256 != null &&
            await _fileSha256(candidate) != file.sha256) {
          return false;
        }
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Moves [from] to [to] by rename (parents created). Only when the two
  /// are on different volumes (EXDEV) is it a copy, checked file by file by
  /// SHA-256, then the source removed; a failed copy removes its partial
  /// result and leaves the source untouched.
  static Future<void> _move(String from, String to) async {
    final type = await FileSystemEntity.type(from, followLinks: false);
    if (type == FileSystemEntityType.notFound) {
      throw FileSystemException('nothing to move', from);
    }
    await Directory(p.dirname(to)).create(recursive: true);
    try {
      switch (type) {
        case FileSystemEntityType.directory:
          await Directory(from).rename(to);
        case FileSystemEntityType.link:
          await Link(from).rename(to);
        default:
          await File(from).rename(to);
      }
    } on FileSystemException catch (error) {
      if (error.osError?.errorCode != _exdev ||
          type == FileSystemEntityType.link) {
        rethrow;
      }
      try {
        await _copyTreeVerified(from, to, type);
      } catch (_) {
        await _deleteEntityQuietly(to);
        rethrow;
      }
      if (type == FileSystemEntityType.directory) {
        await Directory(from).delete(recursive: true);
      } else {
        await File(from).delete();
      }
    }
  }

  static Future<void> _copyTreeVerified(
    String from,
    String to,
    FileSystemEntityType type,
  ) async {
    if (type == FileSystemEntityType.directory) {
      await Directory(to).create(recursive: true);
      await for (final entity in Directory(from).list(followLinks: false)) {
        final child = p.join(to, p.basename(entity.path));
        if (entity is Directory) {
          await _copyTreeVerified(
            entity.path,
            child,
            FileSystemEntityType.directory,
          );
        } else if (entity is File) {
          await _copyTreeVerified(
            entity.path,
            child,
            FileSystemEntityType.file,
          );
        } else {
          throw FileSystemException('cannot copy a link', entity.path);
        }
      }
      return;
    }
    final source = File(from);
    final expected = await _fileSha256(source);
    await source.copy(to);
    final copied = File(to);
    if (await copied.length() != await source.length() ||
        await _fileSha256(copied) != expected) {
      throw FileSystemException('copy differs from the source', to);
    }
  }

  /// Staging worker (runs in a background isolate): each job is copied or
  /// inflated chunk by chunk into its staged file with `writeFromSync`, so
  /// memory stays bounded; the written byte count may never pass the
  /// declared size (a ZIP bomb stops at once). Returns (SHA-256, error).
  static List<(String?, String?)> _runStageJobs(List<_StageJob> jobs) {
    final results = List<(String?, String?)>.filled(jobs.length, (
      null,
      'not staged',
    ));
    final byContainer = <String, List<int>>{};
    for (var index = 0; index < jobs.length; index++) {
      final job = jobs[index];
      final container = job.container;
      if (container != null) {
        byContainer.putIfAbsent(container, () => []).add(index);
        continue;
      }
      try {
        results[index] = (
          _writeStaged(job, (emit) {
            final source = File(job.file!).openSync();
            try {
              while (true) {
                final chunk = source.readSync(256 << 10);
                if (chunk.isEmpty) break;
                emit(chunk);
              }
            } finally {
              source.closeSync();
            }
          }),
          null,
        );
      } catch (error) {
        results[index] = (null, _detail(error));
      }
    }
    for (final entry in byContainer.entries) {
      InputFileStream? input;
      RandomAccessFile? headers;
      try {
        input = InputFileStream(entry.key);
        final archive = ZipDecoder().decodeStream(input);
        headers = File(entry.key).openSync();
        for (final index in entry.value) {
          final job = jobs[index];
          try {
            final found = archive.find(job.entry!);
            if (found == null || !found.isFile) {
              throw FileSystemException(
                'entry ${job.entry} missing',
                entry.key,
              );
            }
            final content = found.rawContent;
            if (content is ZipFile) {
              final header = content.header;
              final central = header?.compressionMethod ?? -1;
              int? local;
              if (header != null) {
                headers.setPositionSync(header.localHeaderOffset);
                local = _localMethod(headers.readSync(30));
              }
              if ((content.flags & 0x1) != 0 ||
                  (central != 0 && central != 8) ||
                  (local != 0 && local != 8)) {
                throw FormatException(
                  '${job.entry}: compression method $central/$local '
                  'or encryption',
                );
              }
            }
            results[index] = (
              _writeStaged(job, (emit) {
                _readZipEntry(found, (chunk) {
                  emit(chunk);
                  return true;
                });
              }),
              null,
            );
          } catch (error) {
            results[index] = (null, _detail(error));
          }
        }
      } catch (error) {
        for (final index in entry.value) {
          if (results[index].$2 == 'not staged') {
            results[index] = (null, _detail(error));
          }
        }
      } finally {
        headers?.closeSync();
        input?.closeSync();
      }
    }
    return results;
  }

  /// Runs [jobs] in a background isolate. Static on purpose: the closure
  /// sent to the isolate captures nothing but the plain job list.
  static Future<List<(String?, String?)>> _stageInBackground(
    List<_StageJob> jobs,
  ) => Isolate.run(() => _runStageJobs(jobs));

  static String _writeStaged(
    _StageJob job,
    void Function(void Function(Uint8List chunk) emit) produce,
  ) {
    final out = File(job.staged);
    out.parent.createSync(recursive: true);
    final handle = out.openSync(mode: FileMode.writeOnly);
    final sink = _DigestSink();
    final digest = sha256.startChunkedConversion(sink);
    var written = 0;
    void accept(Uint8List chunk) {
      written += chunk.length;
      if (written > job.size) {
        throw FormatException(
          'more than the ${job.size} bytes declared',
          job.staged,
        );
      }
      digest.add(chunk);
      handle.writeFromSync(chunk);
    }

    // A slice (an essential.exefs section) keeps only its own bytes of the
    // source stream.
    final sliceStart = job.sliceStart;
    var position = 0;
    void acceptSlice(Uint8List chunk) {
      final start = sliceStart!;
      final chunkStart = position;
      position += chunk.length;
      final from = math.max(start, chunkStart);
      final to = math.min(start + job.size, position);
      if (from < to) {
        accept(
          Uint8List.sublistView(chunk, from - chunkStart, to - chunkStart),
        );
      }
    }

    try {
      produce(sliceStart == null ? accept : acceptSlice);
      if (written != job.size) {
        throw FormatException(
          '$written bytes, ${job.size} declared',
          job.staged,
        );
      }
      handle.flushSync();
    } finally {
      handle.closeSync();
    }
    digest.close();
    return sink.value!.toString();
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
    String backupsRoot, {
    Iterable<String> sources = const [],
  }) {
    final redactions = <String, String>{
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
        sessionUnknown: true,
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
    // 64 KiB of input: the inflater hands its output over in pieces of at
    // most 64 KiB, so even a maximal deflate ratio stays bounded per step.
    const chunkSize = 64 * 1024;
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

  static Future<void> _deleteEntityQuietly(String path) async {
    try {
      final type = await FileSystemEntity.type(path, followLinks: false);
      if (type == FileSystemEntityType.directory) {
        await Directory(path).delete(recursive: true);
      } else if (type != FileSystemEntityType.notFound) {
        await File(path).delete();
      }
    } catch (_) {}
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
  const _Recognition(this.kind, this.target)
    : rejection = null,
      titleKey = null,
      sdTitle = false,
      ignoreReason = null,
      essentialExefs = false;
  const _Recognition.title(this.target, this.titleKey, {required this.sdTitle})
    : kind = Libretro3dsItemKind.title,
      rejection = null,
      ignoreReason = null,
      essentialExefs = false;
  const _Recognition.ignored([
    this.ignoreReason = Libretro3dsIgnoreReason.notRecognized,
  ]) : kind = Libretro3dsItemKind.ignored,
       target = null,
       rejection = null,
       titleKey = null,
       sdTitle = false,
       essentialExefs = false;
  const _Recognition.rejected(this.rejection)
    : kind = Libretro3dsItemKind.rejected,
      target = null,
      titleKey = null,
      sdTitle = false,
      ignoreReason = null,
      essentialExefs = false;

  /// GodMode9's `essential.exefs`: a container of console files, read
  /// section by section (its size counts toward the limits like a
  /// console file).
  const _Recognition.essentialExefs()
    : kind = Libretro3dsItemKind.consoleUnique,
      target = null,
      rejection = null,
      titleKey = null,
      sdTitle = false,
      ignoreReason = null,
      essentialExefs = true;

  final Libretro3dsItemKind kind;
  final String? target;
  final Libretro3dsRejection? rejection;

  /// Why an ignored file is not copied.
  final Libretro3dsIgnoreReason? ignoreReason;
  final bool essentialExefs;

  /// `<high>/<low>` of a title file.
  final String? titleKey;

  /// The title belongs to the SD card ([Libretro3dsSystemDataService.isNandTitle]).
  final bool sdTitle;
}

class _Refusal {
  const _Refusal(this.rejection, this.detail);

  final Libretro3dsRejection rejection;
  final String detail;
}

/// Where the bytes of a plan element come from, and the size and
/// modification time of that file (the ZIP for an entry) at analysis.
class _ItemLocator {
  const _ItemLocator.zip(this.containerPath, this.entryName, {this.stamp})
    : kind = Libretro3dsSourceKind.zip,
      filePath = null,
      sliceStart = null;
  const _ItemLocator.file(this.filePath, {required this.kind, this.stamp})
    : containerPath = '',
      entryName = null,
      sliceStart = null;
  _ItemLocator._slice(_ItemLocator of, int start)
    : kind = of.kind,
      containerPath = of.containerPath,
      entryName = of.entryName,
      filePath = of.filePath,
      stamp = of.stamp,
      sliceStart = (of.sliceStart ?? 0) + start;

  /// The element's bytes from [start] on (as many as the element's size).
  _ItemLocator slice(int start) => _ItemLocator._slice(this, start);

  /// Offset of the element's first byte in the file or entry; null when
  /// the element is the whole file.
  final int? sliceStart;

  final Libretro3dsSourceKind kind;
  final String containerPath;

  /// Raw entry name, as the archive's directory spells it.
  final String? entryName;
  final String? filePath;

  /// `<size>@<modified ms>`.
  final String? stamp;
}

abstract class _SourceFile {
  String get entryName;
  int get size;
  _ItemLocator get locator;

  /// Why this entry cannot be read at all (ZIP method, encryption).
  _Refusal? get problem;

  /// At most [count] leading bytes.
  Future<Uint8List> prefix(int count);

  /// SHA-256 (hex) of the whole content; throws when the content is not
  /// exactly [size] bytes.
  Future<String> contentSha256();
}

class _PlainSourceFile implements _SourceFile {
  _PlainSourceFile(
    this.file,
    this.entryName,
    this.size,
    this.kind,
    this.modified,
  );

  final File file;
  @override
  final String entryName;
  @override
  final int size;
  final Libretro3dsSourceKind kind;
  final int modified;

  @override
  _ItemLocator get locator =>
      _ItemLocator.file(file.path, kind: kind, stamp: '$size@$modified');

  @override
  _Refusal? get problem => null;

  @override
  Future<Uint8List> prefix(int count) =>
      Libretro3dsSystemDataService._readPrefix(file, count);

  @override
  Future<String> contentSha256() async {
    final sink = _DigestSink();
    final digest = sha256.startChunkedConversion(sink);
    var read = 0;
    await for (final chunk in file.openRead()) {
      read += chunk.length;
      if (read > size) break;
      digest.add(chunk);
    }
    digest.close();
    if (read != size) {
      throw FileSystemException(
        'source is not $size bytes any more',
        file.path,
      );
    }
    return sink.value!.toString();
  }
}

/// One section of a container file (an `essential.exefs` section): read
/// from memory at analysis, staged from its place in the file.
class _SliceSourceFile implements _SourceFile {
  _SliceSourceFile(this.parent, this.section, this.entryName);

  final _SourceFile parent;
  final Libretro3dsExefsSection section;
  @override
  final String entryName;

  @override
  int get size => section.size;
  @override
  _ItemLocator get locator => parent.locator.slice(section.start);
  @override
  _Refusal? get problem => null;

  @override
  Future<Uint8List> prefix(int count) async => count >= section.size
      ? section.bytes
      : Uint8List.sublistView(section.bytes, 0, count);

  @override
  Future<String> contentSha256() async =>
      sha256.convert(section.bytes).toString();
}

class _ZipSourceFile implements _SourceFile {
  _ZipSourceFile(
    this.containerPath,
    this.entry,
    this.entryName,
    this.containerSize,
    this.containerModified,
    this.problem,
  );

  final String containerPath;
  final ArchiveFile entry;
  final int containerSize;
  final int containerModified;

  /// Normalized entry name.
  @override
  final String entryName;
  @override
  final _Refusal? problem;

  @override
  int get size => entry.size;
  @override
  _ItemLocator get locator => _ItemLocator.zip(
    containerPath,
    entry.name,
    stamp: '$containerSize@$containerModified',
  );

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
    var read = 0;
    Libretro3dsSystemDataService._readZipEntry(entry, (chunk) {
      read += chunk.length;
      if (read > size) {
        throw FormatException(
          '${entry.name}: more than the $size bytes declared',
        );
      }
      digest.add(chunk);
      return true;
    });
    digest.close();
    if (read != size) {
      throw FormatException('${entry.name}: $read bytes, $size declared');
    }
    return sink.value!.toString();
  }
}

/// A title file waiting for its title to be settled.
class _TitleFile {
  _TitleFile(
    this.source,
    this.item,
    this.target,
    this.hash,
    this.consoleCrypto,
  );

  final _SourceFile source;
  final Libretro3dsImportItem Function({
    required Libretro3dsItemKind kind,
    String? target,
    Libretro3dsRejection? rejection,
    Libretro3dsIgnoreReason? ignoreReason,
    Libretro3dsPlanAction? action,
    bool exists,
    bool identical,
    String? detail,
    String? hash,
    String? consoleCrypto,
  })
  item;
  final String target;
  final String? hash;

  /// Console key fingerprint of an `.app` without a readable NCCH header
  /// ([Libretro3dsSystemDataService.consoleCryptoFingerprint]); settled
  /// against the other contents of the import.
  final String? consoleCrypto;
}

class _AnalysisContext {
  _AnalysisContext({required this.userDirectory, required this.limits});

  final String userDirectory;
  final Libretro3dsImportLimits limits;
  final List<Libretro3dsImportItem> items = [];
  final Set<String> _claimed = {};
  final Map<String, String> owners = {};
  final Map<String, List<_TitleFile>> titles = {};
  final Map<String, String> refusedTitles = {};
  final List<String> retired = [];
  int recognizedBytes = 0;

  void add(Libretro3dsImportItem item) => items.add(item);

  /// First source to name [target] wins; later ones are duplicates.
  bool claim(String target) => _claimed.add(target);

  String? ownerOf(String target) => owners[target];

  /// One refused file refuses its whole title.
  void refuseTitle(String key, String reason) =>
      refusedTitles.putIfAbsent(key, () => reason);
}

/// One element of a pass: a file, or a title's whole `content` folder.
class _Unit {
  _Unit({required this.target, required this.dir});

  final String target;
  final bool dir;
  final List<_UnitFile> files = [];
  bool backedUp = false;
  bool installed = false;
}

class _UnitFile {
  _UnitFile({
    required this.target,
    required this.size,
    required this.expectedHash,
    required this.locator,
    required this.itemIndex,
    this.consoleCrypto,
  });

  final String target;
  final int size;
  final String? expectedHash;
  final _ItemLocator? locator;

  /// Console key fingerprint of the title, for a content Azahar encrypted
  /// for its console: the staged copy must still give it.
  final String? consoleCrypto;

  /// Index in the plan (-1 for a restore).
  final int itemIndex;
  String? failure;

  /// SHA-256 of the staged copy (what the install moves in).
  String? stagedHash;
}

/// A file an install moved in: path relative to the user directory, size
/// and SHA-256 of the staged copy.
class _Expected {
  const _Expected(this.path, this.size, this.sha256);

  final String path;
  final int size;
  final String? sha256;

  Map<String, Object?> toJson() => {
    'path': path,
    'size': size,
    'sha256': sha256,
  };

  static _Expected? fromJson(Object? json) {
    if (json is! Map) return null;
    final path = json['path'];
    final size = json['size'];
    final hash = json['sha256'];
    if (path is! String || size is! int || (hash != null && hash is! String)) {
      return null;
    }
    return _Expected(path, size, hash as String?);
  }
}

/// One staging job, plain data for the background isolate.
class _StageJob {
  const _StageJob({
    required this.staged,
    required this.size,
    this.container,
    this.entry,
    this.file,
    this.sliceStart,
  });

  final String staged;
  final int size;
  final String? container;
  final String? entry;
  final String? file;

  /// Offset of the [size] bytes to keep in the source; null for all of it.
  final int? sliceStart;
}

enum _UnitState { notAttempted, failed, rolledBack, rollbackFailed }

class _PassOutcome {
  _PassOutcome({
    required this.pass,
    required this.staging,
    required this.committed,
    required this.rolledBack,
    required this.unitStates,
    required this.unitFailures,
    this.failure,
    this.backupComplete = false,
    this.backedUpFiles = const {},
    this.retired = const [],
    this.missing = const [],
  });

  final Directory pass;
  final Directory staging;
  final bool committed;
  final bool rolledBack;
  final bool backupComplete;
  final String? failure;
  final List<_UnitState> unitStates;
  final Map<int, String> unitFailures;
  final Set<String> backedUpFiles;
  final List<String> retired;
  final List<String> missing;
}

class _Rollback {
  final List<String> restored = [];
  final List<String> removed = [];

  /// Originals found nowhere (permanent).
  final List<String> missing = [];

  /// Originals left in the backup because the user directory holds
  /// something at their place (permanent, nothing overwritten).
  final List<String> kept = [];

  /// Unit target → raw detail of a step that failed (may succeed later).
  final Map<String, String> problems = {};

  /// Unit target → raw detail of a permanent condition.
  final Map<String, String> notes = {};

  bool get retryable => problems.isNotEmpty;
  bool get clean => problems.isEmpty && missing.isEmpty && kept.isEmpty;
  String? detailFor(String target) => problems[target] ?? notes[target];
}

class _PassState {
  String kind = 'import';
  String? staging;
  bool begun = false;
  final List<({String target, bool dir})> units = [];
  final Set<int> backups = {};
  final Map<int, List<_Expected>> installs = {};
  bool committed = false;
  bool ended = false;
  String? invalid;
}

class _Manifest {
  const _Manifest({
    required this.kind,
    required this.createdAt,
    required this.units,
    required this.files,
    required this.bytes,
  });

  final String kind;
  final DateTime createdAt;
  final List<({String target, bool dir})> units;
  final List<Libretro3dsBackupFile> files;
  final Uint8List bytes;
}

/// Write-ahead journal of a pass: one JSON line per step, each flushed to
/// the file system before the step is taken.
class _PassLog {
  _PassLog._(this._handle);

  final RandomAccessFile _handle;
  bool _closed = false;

  static Future<_PassLog> open(File file) async =>
      _PassLog._(await file.open(mode: FileMode.append));

  Future<void> add(Map<String, Object?> record) async {
    await _handle.writeString('${jsonEncode(record)}\n');
    await _handle.flush();
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    try {
      await _handle.close();
    } catch (_) {}
  }
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
  _Journal(this.service, this.fileName, {Map<String, String>? redactions})
    : redactions = {...?redactions};

  final Libretro3dsSystemDataService service;
  final String fileName;
  final Map<String, String> redactions;
  final List<Map<String, Object?>> _events = [];

  void add(Map<String, Object?> event) => _events.add(event);

  Object? _redact(Object? value) {
    if (value is String) {
      var text = value;
      final roots = redactions.keys.where((root) => root.isNotEmpty).toList()
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
        '${[for (final event in _events) jsonEncode(_redact(event))].join('\n')}\n',
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
