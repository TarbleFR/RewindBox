import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart' show PlatformException;
import 'package:flutter_localization/flutter_localization.dart';
import 'package:path/path.dart' as path;
import 'package:rpcs3_internal_bridge/rpcs3_internal_bridge.dart';

import '../l10n/rpcs3_ui_locale.dart';
import 'logger_service.dart';
import 'rpcs3_disc_image.dart';
import 'rpcs3_internal_service.dart';
import 'rpcs3_library_service.dart';
import 'storage/storage_import_activity.dart';

class Rpcs3ContentImportProgress {
  const Rpcs3ContentImportProgress({
    required this.itemName,
    required this.itemIndex,
    required this.itemCount,
    required this.current,
    required this.total,
    required this.detail,
  });

  final String itemName;
  final int itemIndex;
  final int itemCount;
  final int current;
  final int total;
  final String detail;

  double? get fraction {
    if (total <= 0) return null;
    return (current / total).clamp(0.0, 1.0).toDouble();
  }
}

/// Game import result that also tells whether the library refresh failed after
/// the games were installed (they ARE installed, only the list is stale).
class Rpcs3GamesImportResult extends Rpcs3ImportResult {
  const Rpcs3GamesImportResult({
    required super.imported,
    required super.rejected,
    super.errors,
    this.libraryRefreshError,
  });

  /// Localized sentence, or null when the library was refreshed.
  final String? libraryRefreshError;
}

/// Pure helpers shared by the two PS3 import entry points. They take a
/// translator so they can run without a BuildContext (and in unit tests).
abstract final class Rpcs3ImportMessages {
  /// The game file types the PS3 import reads, as shown after a refusal.
  static const String acceptedGameTypes = '.pkg, .iso, .zip';

  /// Splits the picked paths. Returns the unsupported file names.
  static List<String> classifySelection(
    List<String> selected,
    Map<String, String> keysByStem,
    List<String> gamePaths,
  ) {
    final unsupported = <String>[];
    for (final filePath in selected) {
      final extension = path.extension(filePath).toLowerCase();
      // Build 554: Redump disc keys ship as .dkey as well as .key; a .dkey
      // picked with its ISO used to be rejected as an unsupported game.
      if (extension == '.key' || extension == '.dkey') {
        keysByStem[path.withoutExtension(filePath).toLowerCase()] = filePath;
      } else if (const {'.pkg', '.zip', '.iso'}.contains(extension)) {
        gamePaths.add(filePath);
      } else {
        unsupported.add(path.basename(filePath));
      }
    }
    return unsupported;
  }

  /// One refusal line per picked disc key file when no game file was picked
  /// (`Game.key` and `Game.dkey` are two files, so two lines).
  static List<String> keysOnlyRefusals(
    List<String> selected,
    List<String> gamePaths,
    String Function(String key) t,
  ) {
    if (gamePaths.isNotEmpty) return const [];
    final reason = t('keysOnlySelected');
    return [
      for (final filePath in selected)
        if (const {'.key', '.dkey'}.contains(
          path.extension(filePath).toLowerCase(),
        ))
          '${path.basename(filePath)} — $reason',
    ];
  }

  /// Refused files a notice names before it sums up the rest; a longer list
  /// is shown in full by the report dialog of the two PS3 import entries.
  static const int noticeLines = 5;

  /// "N file(s) not imported:" then up to [maxLines] lines and "and N more".
  static String refusalSummary(
    List<String> errors,
    String Function(String key) t, {
    int maxLines = noticeLines,
  }) {
    final header = t('refusedHeader').replaceAll('{count}', '${errors.length}');
    final lines = <String>[header, ...errors.take(maxLines)];
    if (errors.length > maxLines) {
      lines.add(
        t('refusedMore').replaceAll('{count}', '${errors.length - maxLines}'),
      );
    }
    return lines.join('\n');
  }

  /// Localized sentence for a picker / disk-space failure, or null when the
  /// error is not one of the known cases.
  static String? describeKnownError(
    Object error,
    String Function(String key) t,
  ) {
    if (error is PlatformException) {
      switch (error.code) {
        case 'PICKER_BUSY':
          return t('pickerBusy');
        case 'NO_ROOT_VC':
          return t('pickerNoRoot');
        case 'EMPTY_PATH':
          return t('pickerEmptyPath');
      }
      return null;
    }
    if (error is FileSystemException && error.osError?.errorCode == 28) {
      return t('noSpace');
    }
    return null;
  }

  /// What a picked folder lacks to be a decrypted PS3 game, for the user.
  ///
  /// Two layouts are accepted: the disc layout (`PS3_GAME/PARAM.SFO` and
  /// `PS3_GAME/USRDIR/EBOOT.BIN`) and the flat one (`PARAM.SFO` and
  /// `USRDIR/EBOOT.BIN`). The answer follows the layout the folder started:
  /// a folder with `PS3_GAME` is told what that folder lacks, a folder with
  /// one of the two flat files is told the other one, and a folder with
  /// neither is told the two files of the disc layout.
  static String missingInGameFolder(String root) {
    bool has(String relative) =>
        File(path.joinAll(<String>[root, ...relative.split('/')])).existsSync();

    const flat = <String>['PARAM.SFO', 'USRDIR/EBOOT.BIN'];
    const disc = <String>['PS3_GAME/PARAM.SFO', 'PS3_GAME/USRDIR/EBOOT.BIN'];
    final hasGameDir = Directory(path.join(root, 'PS3_GAME')).existsSync();
    final startedFlat = !hasGameDir && flat.any(has);
    final expected = startedFlat ? flat : disc;
    return expected.where((relative) => !has(relative)).join(', ');
  }
}

/// RPCS3-only content importer.
///
/// iOS document URLs are opened in-place and kept security-scoped until the
/// Core finishes consuming them. This avoids FilePicker's intermediate copies
/// for multi-gigabyte PS3 content and restores the unpacked/decrypted folder
/// workflow supported by the standalone RPCS3 iOS application.
class Rpcs3ContentImportService {
  Rpcs3ContentImportService._();

  static final LoggerService _log = LoggerService.instance;

  static String get _localeTag =>
      FlutterLocalization.instance.currentLocale?.toLanguageTag() ?? 'en';
  static String _ui(String key) =>
      Rpcs3UiLocale.textForLocale(_localeTag, key);

  /// Set by [importExtractedGameFolder] when the game was installed but the
  /// library list could not be refreshed afterwards (null otherwise).
  static String? lastFolderRefreshError;

  static final _progressController =
      StreamController<Rpcs3ContentImportProgress>.broadcast(sync: true);

  static Stream<Rpcs3ContentImportProgress> get progress =>
      _progressController.stream;

  static String _itemName = '';
  static int _itemIndex = 0;
  static int _itemCount = 0;

  static void _emit({
    int current = 0,
    int total = 0,
    String detail = '',
  }) {
    _progressController.add(
      Rpcs3ContentImportProgress(
        itemName: _itemName,
        itemIndex: _itemIndex,
        itemCount: _itemCount,
        current: current,
        total: total,
        detail: detail,
      ),
    );
  }

  static Future<T> _withNativeProgress<T>(Future<T> Function() action) async {
    final subscription = Rpcs3InternalBridge.installProgress.listen((event) {
      _emit(
        current: event.current,
        total: event.total,
        detail: event.detail,
      );
    });
    try {
      return await action();
    } finally {
      await subscription.cancel();
    }
  }

  /// Build 251: the embedded Core already validates every ISO9660 extent and
  /// reports a precise failure when the selected/provider-backed image ends
  /// before a referenced game file. Treat only those integrity failures as a
  /// request for a fresh document selection; ordinary import errors remain
  /// terminal and are returned to the caller as before.
  static bool _isIncompleteIsoFailure(Object? rawMessage) {
    final message = rawMessage?.toString().toLowerCase() ?? '';
    return message.contains('truncated or corrupt') ||
        message.contains('incomplete or corrupt') ||
        message.contains('requires iso bytes through') ||
        message.contains('re-import this title from a complete iso');
  }

  static Future<Rpcs3ImportResult> importGames() => StorageImportActivity.run(() async {
    var imported = 0;
    var rejected = 0;
    final errors = <String>[];
    var pendingIncompleteErrors = <String>[];
    String? refreshError;

    // An incomplete ISO is never accepted into the library. Once the Core
    // rejects it, release the security-scoped URLs and immediately present a
    // fresh picker. Cancelling that second picker records the rejected ISO and
    // returns normally instead of leaving a half-imported game behind.
    while (true) {
      final selected = await Rpcs3InternalBridge.pickGameFilesOpenInPlace();
      if (selected == null || selected.isEmpty) {
        if (pendingIncompleteErrors.isNotEmpty) {
          rejected += pendingIncompleteErrors.length;
          errors.addAll(pendingIncompleteErrors);
        }
        return Rpcs3GamesImportResult(
          imported: imported,
          rejected: rejected,
          errors: errors,
          libraryRefreshError: refreshError,
        );
      }

      final selectedKeys = <String, String>{};
      final gamePaths = <String>[];
      final unsupported = Rpcs3ImportMessages.classifySelection(
        selected,
        selectedKeys,
        gamePaths,
      );
      for (final name in unsupported) {
        rejected++;
        // The accepted types follow the sentence: a refusal that only says
        // "unsupported" leaves the user guessing what to pick instead.
        errors.add(
          '$name — ${_ui('unsupportedGameFormat')} '
          '(${Rpcs3ImportMessages.acceptedGameTypes})',
        );
        _log.w('RPCS3 import: $name is not a PS3 game file.');
      }
      _log.i(
        'RPCS3 import: ${selected.length} file(s) picked, '
        '${gamePaths.length} game file(s), ${selectedKeys.length} disc key(s).',
      );

      if (gamePaths.isEmpty) {
        await Rpcs3InternalBridge.releaseScopedResources();
        // Only disc keys were picked: say why nothing was imported.
        final keyOnly = Rpcs3ImportMessages.keysOnlyRefusals(
          selected,
          gamePaths,
          _ui,
        );
        rejected += keyOnly.length;
        errors.addAll(keyOnly);
        if (pendingIncompleteErrors.isNotEmpty) {
          rejected += pendingIncompleteErrors.length;
          errors.addAll(pendingIncompleteErrors);
        }
        return Rpcs3GamesImportResult(
          imported: imported,
          rejected: rejected,
          errors: errors,
          libraryRefreshError: refreshError,
        );
      }

      var importedThisSelection = 0;
      final incompleteErrors = <String>[];
      try {
        await Rpcs3InternalService.ensureManagementInitialized();
        _itemCount = gamePaths.length;

        for (var index = 0; index < gamePaths.length; index++) {
          final filePath = gamePaths[index];
          final name = path.basename(filePath);
          _itemName = name;
          _itemIndex = index + 1;
          _emit(detail: 'Preparing $name…');

          final extension = path.extension(filePath).toLowerCase();
          final report = await _withNativeProgress(() async {
            if (extension == '.pkg') {
              return Rpcs3InternalBridge.installPackage(filePath);
            }
            if (extension == '.zip') {
              return Rpcs3InternalBridge.installZip(filePath);
            }

            final stem = path.withoutExtension(filePath).toLowerCase();
            final keyPath =
                selectedKeys[stem] ??
                await Rpcs3DiscImage.findDiscKey(filePath);
            _log.i(
              'RPCS3 import: $name with disc key '
              '${keyPath == null ? 'none' : path.basename(keyPath)}.',
            );
            return Rpcs3InternalBridge.installIso(
              filePath,
              keyPath: keyPath,
            );
          });

          if (report['success'] == true) {
            imported++;
            importedThisSelection++;
            _log.i('RPCS3 import: $name imported.');
            _emit(current: 1, total: 1, detail: '$name imported.');
            continue;
          }

          final nativeMessage = report['message']?.toString();
          final message = nativeMessage ?? 'RPCS3 import failed.';
          // The reason used to reach only a snackbar: keep it in app.log.
          _log.e('RPCS3 import: $name rejected: $message');
          final reason = (nativeMessage == null || nativeMessage.isEmpty)
              ? _ui('importFailedShort')
              : '${_ui('importFailedShort')} $nativeMessage';
          final formatted = '$name — $reason';
          if (extension == '.iso' && _isIncompleteIsoFailure(message)) {
            incompleteErrors.add(formatted);
            _emit(detail: _ui('incompleteIso'));
          } else {
            rejected++;
            errors.add(formatted);
          }
        }

        if (importedThisSelection > 0) {
          // The games are installed at this point: a failing refresh must not
          // turn the import into a reported failure.
          try {
            await Rpcs3LibraryService.syncInternalLibrary();
            // A refresh that failed for an earlier selection of this import
            // (incomplete-ISO re-pick) is repaired by this one.
            refreshError = null;
          } catch (error) {
            _log.e('RPCS3 import: library refresh failed: $error');
            refreshError = _ui(
              'libraryRefreshFailed',
            ).replaceAll('{error}', '$error');
          }
        }
      } finally {
        _itemName = '';
        _itemIndex = 0;
        _itemCount = 0;
        await Rpcs3InternalBridge.releaseScopedResources();
      }

      if (incompleteErrors.isEmpty) {
        return Rpcs3GamesImportResult(
          imported: imported,
          rejected: rejected,
          errors: errors,
          libraryRefreshError: refreshError,
        );
      }

      // Replacing the selection resolves the previous incomplete-image error.
      // If the user cancels the fresh picker, the pending error is surfaced in
      // the result so both RPCS3 manager entry points still report the rejection.
      pendingIncompleteErrors = incompleteErrors;
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
  });

  static Future<String?> _resolveUnpackedGameFolder(String selectedPath) async {
    bool directLayout(String root) {
      return File(path.join(root, 'PARAM.SFO')).existsSync() &&
          File(path.join(root, 'USRDIR', 'EBOOT.BIN')).existsSync();
    }

    bool discLayout(String root) {
      return File(path.join(root, 'PS3_GAME', 'PARAM.SFO')).existsSync() &&
          File(
            path.join(root, 'PS3_GAME', 'USRDIR', 'EBOOT.BIN'),
          ).existsSync();
    }

    if (directLayout(selectedPath) || discLayout(selectedPath)) {
      return selectedPath;
    }

    // Some decrypted dumps add one wrapper directory around PS3_GAME. A child
    // remains within the exact security scope granted for the selected folder.
    final root = Directory(selectedPath);
    if (await root.exists()) {
      final children = await root
          .list(followLinks: false)
          .where((entry) => entry is Directory)
          .cast<Directory>()
          .take(16)
          .toList();
      for (final child in children) {
        if (directLayout(child.path) || discLayout(child.path)) {
          return child.path;
        }
      }
    }
    return null;
  }

  static Future<bool> importExtractedGameFolder() => StorageImportActivity.run(() async {
    final selected = await Rpcs3InternalBridge.pickGameFolderOpenInPlace();
    lastFolderRefreshError = null;
    if (selected == null || selected.isEmpty) return false;

    try {
      final folder = await _resolveUnpackedGameFolder(selected);
      if (folder == null) {
        throw Rpcs3InternalException(
          'invalidGameFolder',
          _ui('folderNotGame')
              .replaceAll('{folder}', path.basename(selected))
              .replaceAll(
                '{missing}',
                Rpcs3ImportMessages.missingInGameFolder(selected),
              ),
        );
      }

      await Rpcs3InternalService.ensureManagementInitialized();
      _itemName = path.basename(folder);
      _itemIndex = 1;
      _itemCount = 1;
      _emit(detail: 'Preparing decrypted game folder…');

      final report = await _withNativeProgress(
        () => Rpcs3InternalBridge.installFolder(folder),
      );
      if (report['success'] != true) {
        final nativeMessage = report['message']?.toString();
        throw Rpcs3InternalException(
          'gameImportFailed',
          (nativeMessage == null || nativeMessage.isEmpty)
              ? _ui('folderRejected')
              : '${_ui('folderRejected')} $nativeMessage',
        );
      }

      // The game is installed: a failing refresh is reported, not thrown.
      try {
        await Rpcs3LibraryService.syncInternalLibrary();
      } catch (error) {
        _log.e('RPCS3 import: library refresh failed: $error');
        lastFolderRefreshError = _ui(
          'libraryRefreshFailed',
        ).replaceAll('{error}', '$error');
      }
      _emit(current: 1, total: 1, detail: 'Game folder imported.');
      return true;
    } finally {
      _itemName = '';
      _itemIndex = 0;
      _itemCount = 0;
      await Rpcs3InternalBridge.releaseScopedResources();
    }
  });
}
