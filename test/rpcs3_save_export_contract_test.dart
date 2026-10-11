// Source contract of the game-save exchange (Build 442): the manager's two
// buttons go through Rpcs3SaveExchangeService (ZIP export in Files with a
// share action, staged import with a replace prompt and a report), the
// startup housekeeping only ensures the Files folders, the playlist popup
// still exposes no save action and the iOS Files sharing flags stay set.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('RPCS3 game-save exchange contract', () {
    final service = File(
      'lib/services/rpcs3_internal_service.dart',
    ).readAsStringSync();
    final exchange = File(
      'lib/services/rpcs3_save_exchange_service.dart',
    ).readAsStringSync();
    final menu = File(
      'lib/widgets/rpcs3_internal_playlist_actions.dart',
    ).readAsStringSync();
    final manager = File(
      'lib/screens/rpcs3_manager_screen.dart',
    ).readAsStringSync();
    final iosConfiguration = File(
      'build-utils/configure_dolphin_ios_v2.py',
    ).readAsStringSync();

    // Files workspace: folders and README only, created where they were.
    for (final token in [
      'getApplicationDocumentsDirectory()',
      "path.join(documents.path, 'RPCS3')",
      "'Import/Game Saves'",
      "'Import/Savestates'",
      "'Export/Game Saves'",
      "'Export/Savestates'",
      'README.txt',
      'synchronizeFilesWorkspace',
      'static Future<T> runSaveExchange<T>(Future<T> Function() body)',
      'Rpcs3SaveExchangeService',
    ]) {
      expect(service, contains(token), reason: token);
    }
    expect(service, isNot(contains("path.join(documents.path, 'Data')")));
    for (final token in [
      'consumeSource',
      '_copyTree',
      '_copyReplacing',
      'neostation-import-backup',
      'neostation-sync-tmp',
      '.Saves.previous',
      "'savestates'",
    ]) {
      expect(service, isNot(contains(token)), reason: token);
    }
    final startup = service.substring(
      service.indexOf('synchronizeFilesWorkspace() async {'),
      service.indexOf('static String _saves('),
    );
    for (final token in ['delete(', '.copy(', 'rename(', 'dataDirectory()']) {
      expect(startup, isNot(contains(token)), reason: 'startup $token');
    }
    expect(startup, contains('await filesWorkspaceDirectory();'));
    expect(service, contains('await synchronizeFilesWorkspace();'));

    // Busy guard: same checks as deleteInstalledGame, translated reason.
    final guard = service.substring(
      service.indexOf('static Future<T> runSaveExchange<T>'),
      service.indexOf('/// Thin wrapper kept for the dormant playlist branches'),
    );
    for (final token in [
      'GameLaunchManager().isActive',
      '_libraryMutationInProgress ||',
      '_runtimePreparation != null',
      'Rpcs3RuntimePhase.importingContent',
      'emulation != 0 && emulation != 1',
      "_saves('busyGameRunning')",
      "_saves('busyLibrary')",
      '_libraryMutationInProgress = true;',
      '_libraryMutationInProgress = false;',
    ]) {
      expect(guard, contains(token), reason: 'guard $token');
    }

    // The exchange service: ZIP in Files, staging beside savedata, backups
    // outside the Core tree, vfs guard, exact user, no hardcoded path.
    for (final token in [
      "import 'package:archive/archive_io.dart';",
      'ZipFileEncoder',
      'ZipDecoder',
      "static const String savedataFolderName = 'savedata';",
      'Rpcs3RapLicenceService.activeUserId',
      'Rpcs3RapLicenceService.storageRedirection',
      "static const String backupFolderName = 'SaveBackups';",
      "static const String stagingPrefix = '.neostation-save-import-';",
      "static const String exportFilePrefix = 'RPCS3-saves-';",
      r"RegExp(r'^[A-Za-z0-9_\-]{1,32}$')",
      'followLinks: false',
      'isSymbolicLink',
      'static const int defaultMaxEntries = 2000;',
      'static const int defaultMaxTotalBytes = 1 << 30;',
      'static const int defaultMaxFileBytes = 512 << 20;',
      'staged.rename(target.path)',
      'target.rename(destination.path)',
      "allowedExtensions: const ['zip']",
      'Rpcs3InternalBridge.pickGameFolderOpenInPlace()',
      'Rpcs3InternalBridge.releaseScopedResources()',
      'Rpcs3InternalService.runSaveExchange',
    ]) {
      expect(exchange, contains(token), reason: token);
    }
    expect(exchange, isNot(contains('/var/mobile')));
    expect(exchange, isNot(contains('Application Support/NeoStation')));
    expect(exchange, isNot(contains("'savestates'")));

    // Manager: service flows, report dialogs, share sheet; old copy gone.
    for (final token in [
      'rpcs3-manager-export-saves',
      'rpcs3-manager-import-saves',
      'Rpcs3SaveExchangeService.instance.exportGuarded()',
      'Rpcs3SaveExchangeService.instance.importGuarded(',
      'showRpcs3SaveImportSourceDialog(context)',
      'showRpcs3SaveReplaceDialog(context, conflicts)',
      'showRpcs3SaveImportReport(context, report)',
      'showRpcs3SaveExportReport(context, result, onShare: _shareExport)',
      'SharePlus.instance.share(',
      "XFile(zipPath, mimeType: 'application/zip')",
      "_t('exportSaves')",
      "_t('importSaves')",
    ]) {
      expect(manager, contains(token), reason: token);
    }
    expect(manager, isNot(contains('exportSaveData()')));
    expect(manager, isNot(contains('importSaveDataFromFiles()')));

    // The playlist popup exposes no save action.
    expect(menu, isNot(contains("value: 'saves'")));
    expect(menu, isNot(contains("value: 'restoreSaves'")));

    // Files sharing stays enabled on iOS.
    expect(iosConfiguration, contains("payload['UIFileSharingEnabled'] = True"));
    expect(
      iosConfiguration,
      contains("payload['LSSupportsOpeningDocumentsInPlace'] = True"),
    );
  });
}
