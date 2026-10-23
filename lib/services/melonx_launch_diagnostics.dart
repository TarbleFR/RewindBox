import 'dart:convert';

import 'logger_service.dart';

/// Only diagnostic fields cross this boundary. Key values and decrypted data
/// are never accepted; long hexadecimal values are redacted defensively.
abstract final class MelonxLaunchDiagnostics {
  static String safe(String text) => text
      .replaceAll(
        RegExp(r'\b[0-9a-f]{32,}\b', caseSensitive: false),
        '[redacted]',
      )
      .replaceAll(
        RegExp(
          r'^\s*[a-z0-9_]+\s*=\s*[^\r\n]+',
          caseSensitive: false,
          multiLine: true,
        ),
        '[redacted key entry]',
      );

  static String details(Map<String, dynamic> result) => safe(
    jsonEncode({
      for (final key in [
        'stage',
        'error',
        'errorCode',
        'nativeStatus',
        'diagnostic',
        'sessionActive',
        'requiresRestart',
      ])
        if (result[key] != null) key: result[key],
    }),
  );

  static void record(
    String stage,
    String status, [
    Map<String, dynamic> fields = const {},
  ]) {
    final record = <String, dynamic>{
      'timestamp': DateTime.now().toUtc().toIso8601String(),
      'stage': stage,
      'status': status,
      for (final key in [
        'pid',
        'attempt',
        'gamePath',
        'bytes',
        'error',
        'errorCode',
        'nativeStatus',
        'diagnostic',
        'sessionActive',
        'requiresRestart',
      ])
        if (fields[key] != null) key: fields[key],
    };
    final text = '[MeloNX:launch] ${safe(jsonEncode(record))}';
    if (status == 'failed' || status == 'quarantined') {
      LoggerService.instance.e(text);
    } else {
      LoggerService.instance.i(text);
    }
  }
}
