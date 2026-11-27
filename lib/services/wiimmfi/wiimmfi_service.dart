import 'dart:async';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;

import '../dolphin_internal_v2_service.dart';
import '../dolphin_system_files.dart';
import '../storage/storage_picker_copies.dart';
import 'wiimmfi_store.dart';

export 'wiimmfi_store.dart' show WiimmfiException;

abstract final class WiimmfiService {
  static final importPhase = ValueNotifier<String>('idle');
  static bool _cancelRequested = false;
  static const _channel = MethodChannel('neostation/dolphin_internal');
  static Future<WiimmfiStore> _store() async => WiimmfiStore(
    Directory(
      p.join(
        (await DolphinInternalV2Service.rootDirectory()).path,
        'Metadata',
        'Wiimmfi',
      ),
    ),
  );

  static Future<Map<String, dynamic>> settings() async =>
      (await _store()).load();

  static Future<Map<String, dynamic>> status() async {
    try {
      final root = await DolphinInternalV2Service.rootDirectory();
      return await _channel.invokeMapMethod<String, dynamic>('wiimmfiStatus', {
            'nandDirectory': p.join(root.path, 'User', 'Wii'),
          }) ??
          {'supported': false, 'nandRecognized': false};
    } on MissingPluginException {
      return {'supported': false, 'nandRecognized': false};
    }
  }

  static Future<void> setEnabled(bool value) =>
      DolphinInternalV2Service.withSystemMutation(() async {
        if (value && (await status())['supported'] != true) {
          throw const WiimmfiException('engineUnavailable');
        }
        final store = await _store();
        await store.save({...await store.load(), 'enabled': value});
      });

  static Future<void> clear() =>
      DolphinInternalV2Service.withSystemMutation(() async {
        await (await _store()).clear();
      });

  static Future<void> cancelImport() async {
    if (importPhase.value == 'committing' || importPhase.value == 'idle') {
      return;
    }
    _cancelRequested = true;
    await _channel.invokeMethod<void>('wiimmfiCancelImport');
  }

  static Future<Map<String, dynamic>?> importProgress() async {
    if (importPhase.value != 'native') {
      return {'phase': 'importNand', 'percent': null};
    }
    return _channel.invokeMapMethod<String, dynamic>('wiimmfiImportProgress');
  }

  static Future<bool>
  importBootMii() => DolphinInternalV2Service.withSystemMutation(() async {
    _cancelRequested = false;
    importPhase.value = 'selecting';
    try {
      if ((await status())['supported'] != true) {
        throw const WiimmfiException('engineUnavailable');
      }
      final selection = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: const ['bin'],
        allowMultiple: true,
        withData: false,
      );
      if (selection == null) return false;
      if (_cancelRequested) throw const WiimmfiException('cancelled');
      File? nand;
      File? keys;
      final copies = <File, int>{};
      try {
        for (final pick in selection.files) {
          if (pick.path == null) throw const WiimmfiException('invalidNand');
          final file = File(pick.path!);
          final size = await file.length();
          copies[file] = size;
          if ((size == 0x21000000 || size == 0x21000400) && nand == null) {
            nand = file;
          } else if (size == 0x400 && keys == null) {
            keys = file;
          } else {
            throw const WiimmfiException('invalidNand');
          }
        }
        if (nand == null ||
            (await nand.length() == 0x21000000 && keys == null)) {
          throw const WiimmfiException('keysRequired');
        }
        final root = await DolphinInternalV2Service.rootDirectory();
        final current = Directory(p.join(root.path, 'User', 'Wii'));
        await DolphinSystemFiles.replaceSnapshot(current, (stage) async {
          if (_cancelRequested) throw const WiimmfiException('cancelled');
          importPhase.value = 'native';
          final outcome = await _channel.invokeMethod<int>('wiimmfiImport', {
            'imagePath': nand!.path,
            'keysPath': keys?.path,
            'stageDirectory': stage.path,
          });
          if (outcome != 0) {
            throw WiimmfiException(outcome == 1 ? 'cancelled' : 'invalidNand');
          }
          if (_cancelRequested) throw const WiimmfiException('cancelled');
          importPhase.value = 'preserving';
          await preserveWiiSaveData(current, stage);
          // Preserve console credentials privately; no contents enter logs or config.
          await _channel.invokeMethod<void>('wiimmfiProtectNand', {
            'directory': stage.path,
          });
          if (_cancelRequested) throw const WiimmfiException('cancelled');
          importPhase.value = 'committing';
          return 1;
        });
        return true;
      } finally {
        for (final entry in copies.entries) {
          await StoragePickerCopies.discardAfterVerifiedImport(
            entry.key.path,
            expectedLength: entry.value,
          );
        }
      }
    } finally {
      importPhase.value = 'idle';
    }
  });

  static Future<Map<String, dynamic>> identity(String gamePath) async {
    final value = await _channel.invokeMapMethod<String, dynamic>(
      'saveIdentity',
      {'gamePath': gamePath, 'system': 'wii'},
    );
    if (value == null ||
        value['system'] != 'wii' ||
        value['revision'] is! int ||
        !RegExp(r'^[A-Z0-9]{6}$').hasMatch('${value['gameId']}')) {
      throw const WiimmfiException('gameUnknown');
    }
    return value;
  }

  /// Explicit user declaration, never a claim that the security patch was
  /// certified by RewindBox. Hash the exact image and bind its native metadata.
  static Future<void> registerPatchedImage(String gamePath) =>
      DolphinInternalV2Service.withSystemMutation(() async {
        final library = await DolphinInternalV2Service.libraryDirectory('wii');
        final file = File(gamePath);
        if (!p.isWithin(
          await library.resolveSymbolicLinks(),
          await file.resolveSymbolicLinks(),
        )) {
          throw const WiimmfiException('unsafePath');
        }
        final meta = await identity(gamePath);
        final digest = (await sha256.bind(file.openRead()).first).toString();
        final store = await _store();
        final state = await store.load();
        final images = Map<String, dynamic>.from(state['images'] as Map);
        images[p.normalize(p.absolute(gamePath))] = {
          ...meta,
          'sha256': digest,
          'size': await file.length(),
          'patchVerification': 'userDeclaredOfficial',
          'registeredAt': DateTime.now().toUtc().toIso8601String(),
        };
        await store.save({...state, 'images': images});
      });

  static Future<bool> prepareLaunch(String gamePath, {bool? requested}) async {
    if (requested == false) {
      if ((await status())['supported'] != true) {
        throw const WiimmfiException('engineUnavailable');
      }
      return false;
    }
    final state = await settings();
    if (state['enabled'] != true) {
      if (requested == true) throw const WiimmfiException('disabled');
      return false;
    }
    final receipt = (state['images'] as Map)[p.normalize(p.absolute(gamePath))];
    if (receipt is! Map) {
      if (requested == true) throw const WiimmfiException('patchRequired');
      return false;
    }
    final readiness = await status();
    if (readiness['supported'] != true) {
      throw const WiimmfiException('engineUnavailable');
    }
    if (readiness['nandRecognized'] != true) {
      throw const WiimmfiException('nandMissing');
    }
    final meta = await identity(gamePath);
    if (meta['gameId'] != receipt['gameId'] ||
        meta['revision'] != receipt['revision'] ||
        meta['region'] != receipt['region'] ||
        (await sha256.bind(File(gamePath).openRead()).first).toString() !=
            receipt['sha256']) {
      throw const WiimmfiException('imageChanged');
    }
    return true;
  }

  static DateTime? _diagnosticDate;
  static Map<String, dynamic>? _diagnostic;
  static Future<Map<String, dynamic>>? _diagnosticInFlight;
  static Future<Map<String, dynamic>> diagnose() async {
    if ((await settings())['enabled'] != true) {
      throw const WiimmfiException('disabled');
    }
    if (_diagnosticDate != null &&
        DateTime.now().difference(_diagnosticDate!) <
            const Duration(minutes: 5)) {
      return _diagnostic!;
    }
    return _diagnosticInFlight ??= _probe().whenComplete(
      () => _diagnosticInFlight = null,
    );
  }

  static Future<Map<String, dynamic>> _probe() async {
    final result = <String, dynamic>{
      ...await status(),
      'dns': 'unknown',
      'website': 'unknown',
      'authentication': 'notTested',
      'matchmaking': 'notTested',
      'players': null,
      'servers': 'unknown',
    };
    try {
      final addresses = await InternetAddress.lookup(
        'wiimmfi.de',
      ).timeout(const Duration(seconds: 8));
      result['dns'] = addresses.isEmpty ? 'failed' : 'resolved';
      final client = HttpClient()
        ..connectionTimeout = const Duration(seconds: 8);
      try {
        final request = await client
            .headUrl(Uri.https('wiimmfi.de', '/'))
            .timeout(const Duration(seconds: 8));
        request.followRedirects = false;
        final response = await request.close().timeout(
          const Duration(seconds: 8),
        );
        result['website'] =
            response.statusCode >= 200 && response.statusCode < 400
            ? 'reachable'
            : 'unknown';
        result['httpStatus'] = response.statusCode;
      } finally {
        client.close(force: true);
      }
    } catch (_) {
      /* No raw URLs, addresses, console identities or network errors logged. */
    }
    _diagnosticDate = DateTime.now().toUtc();
    result['checkedAt'] = _diagnosticDate!.toIso8601String();
    return _diagnostic = result;
  }
}
