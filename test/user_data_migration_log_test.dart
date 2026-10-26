import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/user_data_location_service.dart';
import 'package:path/path.dart' as p;

/// The log the app is writing follows a user-data migration: the lines
/// logged during it are kept, nothing is left in the old folder, and the
/// next lines are written in the new one.
void main() {
  late Directory tmp;
  late Directory source;
  late Directory dest;
  late File log;
  final logger = LoggerService.instance;

  setUp(() {
    tmp = Directory.systemTemp.createTempSync('neostation_migrate_log_');
    source = Directory(p.join(tmp.path, 'old'))..createSync();
    dest = Directory(p.join(tmp.path, 'new'))..createSync();
    log = File(p.join(source.path, 'app.log'))
      ..writeAsStringSync('before the migration\n');
    File(p.join(source.path, 'app.log.old')).writeAsStringSync('rotated\n');
    File(p.join(source.path, 'config.json')).writeAsStringSync('{}');
    logger.attachFileForTesting(log);
  });

  tearDown(() {
    logger.attachFileForTesting(File(p.join(tmp.path, 'detached.log')));
    tmp.deleteSync(recursive: true);
  });

  test('the live log moves with its lines and is written there next', () async {
    logger.i('just before');
    await UserDataLocationService.migrateData(
      sourceUserDataPath: source.path,
      sourceMediaPath: p.join(source.path, 'media'),
      destPath: dest.path,
    );
    logger.i('after the migration');

    final moved = File(p.join(dest.path, 'app.log'));
    expect(logger.logFilePath, moved.path);
    expect(log.existsSync(), isFalse, reason: 'no log left in the old folder');
    final text = moved.readAsStringSync();
    expect(text, startsWith('before the migration\n'));
    final order = [
      'just before',
      'Migration: 2 files copied',
      'Migration: source cleaned up',
      'after the migration',
    ].map(text.indexOf).toList();
    expect(order.every((i) => i >= 0), isTrue, reason: text);
    expect(order, [...order]..sort());
    // Rotated logs and other owned files still move as before.
    expect(
      File(p.join(dest.path, 'app.log.old')).readAsStringSync(),
      'rotated\n',
    );
    expect(File(p.join(dest.path, 'config.json')).existsSync(), isTrue);
    expect(source.listSync(), isEmpty);
  });

  test('an aborted migration keeps the log where it was', () async {
    // A directory where config.json should go makes its copy fail.
    Directory(p.join(dest.path, 'config.json')).createSync();
    await expectLater(
      UserDataLocationService.migrateData(
        sourceUserDataPath: source.path,
        sourceMediaPath: p.join(source.path, 'media'),
        destPath: dest.path,
      ),
      throwsA(isA<Exception>()),
    );
    logger.i('after the failure');
    expect(logger.logFilePath, log.path);
    expect(log.readAsStringSync(), contains('after the failure'));
    expect(File(p.join(dest.path, 'app.log')).existsSync(), isFalse);
  });

  test('a log that cannot be written at the destination is not moved', () {
    final blocker = File(p.join(dest.path, 'blocker'))..writeAsStringSync('');
    expect(
      () => logger.moveLogFile(p.join(blocker.path, 'app.log')),
      throwsA(isA<FileSystemException>()),
    );
    logger.i('still here');
    expect(logger.logFilePath, log.path);
    expect(log.readAsStringSync(), contains('still here'));
  });
}
