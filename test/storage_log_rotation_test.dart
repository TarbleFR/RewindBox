// Light maintenance, test J (docs/storage-audit-cleanup.md § 4 and § 6):
// engine logs are bounded at their documented points only. A Dolphin launch
// that names a new session log keeps the ten newest session logs and rotates
// dolphin-persistent.jsonl at 5 MiB like app.log; a KartPad launch keeps the
// ten newest runtime logs (*.log, console.txt) before any native call, and
// never while a session it started may still run. Links, folders and other
// names are never touched, and laying out the folders (what startup and the
// scanner call) deletes nothing. File-system behaviour on the test host only.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/dolphin_internal_v2_service.dart';
import 'package:neostation/services/kartpad_internal_service.dart';
import 'package:neostation/services/storage/storage_picker_copies.dart';
import 'package:path/path.dart' as p;

const _fiveMiB = 5 * 1024 * 1024;

/// Dolphin session logs as the service names them, never its persistent log.
final _sessionLog = RegExp(r'^dolphin-(?!persistent\.jsonl$).*\.jsonl$');

/// Mario Kart Wii PAL header KartPad accepts: RMCP01, disc 0, revision 0,
/// Wii magic at 0x18.
List<int> _kartPadDisc() {
  final bytes = Uint8List(4096)..setAll(0, ascii.encode('RMCP01'));
  ByteData.sublistView(bytes).setUint32(0x18, 0x5D1C9EA3);
  return bytes;
}

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = binding.defaultBinaryMessenger;
  const paths = MethodChannel('plugins.flutter.io/path_provider');
  const dolphin = MethodChannel('neostation/dolphin_internal');
  const kartPad = MethodChannel('neostation/kartpad_internal');
  const codec = StandardMethodCodec();
  final base = DateTime.now().subtract(const Duration(days: 30));

  late Directory scratch;
  late Directory documents;
  late Directory support;
  late Directory outside;

  setUpAll(() async {
    scratch = await Directory.systemTemp.createTemp('storage-log-rotation-');
    documents = Directory(p.join(scratch.path, 'Documents'))..createSync();
    support = Directory(p.join(scratch.path, 'Support'))..createSync();
    outside = Directory(p.join(scratch.path, 'Outside'))..createSync();
    messenger.setMockMethodCallHandler(paths, (call) async {
      return switch (call.method) {
        'getApplicationDocumentsDirectory' => documents.path,
        'getApplicationSupportDirectory' => support.path,
        _ => p.join(scratch.path, 'tmp'),
      };
    });
  });

  tearDownAll(() async {
    messenger.setMockMethodCallHandler(paths, null);
    await scratch.delete(recursive: true);
  });

  /// A [length]-byte file modified [minute] minutes after [base].
  File log(Directory folder, String name, int minute, [int length = 16]) {
    final file = File(p.join(folder.path, name))
      ..createSync(recursive: true)
      ..writeAsBytesSync(List<int>.filled(length, 0x41));
    file.setLastModifiedSync(base.add(Duration(minutes: minute)));
    return file;
  }

  Set<String> names(Directory folder) => {
    for (final entity in folder.listSync()) p.basename(entity.path),
  };

  String session(int day) =>
      'dolphin-2026-09-${day.toString().padLeft(2, '0')}T10-00-00.000000Z.jsonl';

  group('keepNewest', () {
    var count = 0;
    late Directory folder;

    setUp(() {
      folder = Directory(p.join(scratch.path, 'logs-${count++}'))..createSync();
    });

    test('the ten newest matching files stay; links, folders and other names '
        'are untouched', () async {
      final sessions = [
        for (var i = 1; i <= 15; i++) log(folder, session(i), 100 + i),
      ];
      final persistent = log(folder, 'dolphin-persistent.jsonl', 0);
      final previous = log(folder, 'dolphin-persistent.jsonl.old', 1);
      final notes = log(folder, 'notes.txt', 2);
      final target = log(outside, 'target-$count.jsonl', 3);
      final link = Link(p.join(folder.path, session(30)))
        ..createSync(target.path);
      final nested = Directory(p.join(folder.path, 'dolphin-folder.jsonl'))
        ..createSync();

      expect(
        await StorageLogRotation.keepNewest(
          folder,
          name: _sessionLog,
          keep: 10,
        ),
        5,
      );

      for (final old in sessions.take(5)) {
        expect(old.existsSync(), isFalse, reason: old.path);
      }
      for (final kept in sessions.skip(5)) {
        expect(kept.existsSync(), isTrue, reason: kept.path);
      }
      for (final other in [persistent, previous, notes, target]) {
        expect(other.existsSync(), isTrue, reason: other.path);
      }
      expect(link.existsSync(), isTrue);
      expect(nested.existsSync(), isTrue);
      expect(
        await StorageLogRotation.keepNewest(
          folder,
          name: _sessionLog,
          keep: 10,
        ),
        0,
        reason: 'already bounded',
      );
    });

    test('a String names one whole file; keep 0 removes every match', () async {
      final console = log(folder, 'console.txt', 1);
      final other = log(folder, 'old-console.txt', 0);
      expect(
        await StorageLogRotation.keepNewest(
          folder,
          name: 'console.txt',
          keep: 0,
        ),
        1,
      );
      expect(console.existsSync(), isFalse);
      expect(other.existsSync(), isTrue);
    });

    test('equal times keep the greatest name', () async {
      final older = log(folder, 'b-1.log', 5);
      final newer = log(folder, 'b-2.log', 5);
      expect(
        await StorageLogRotation.keepNewest(
          folder,
          name: RegExp(r'\.log$'),
          keep: 1,
        ),
        1,
      );
      expect(older.existsSync(), isFalse);
      expect(newer.existsSync(), isTrue);
    });

    test(
      'a negative keep, a missing folder or a linked folder change nothing',
      () async {
        final kept = log(folder, 'a.log', 0);
        final logs = RegExp(r'\.log$');
        expect(
          await StorageLogRotation.keepNewest(folder, name: logs, keep: -1),
          0,
        );
        expect(
          await StorageLogRotation.keepNewest(
            Directory(p.join(folder.path, 'missing')),
            name: logs,
            keep: 0,
          ),
          0,
        );
        final linked = Link(p.join(scratch.path, 'linked-$count'))
          ..createSync(folder.path);
        expect(
          await StorageLogRotation.keepNewest(
            Directory(linked.path),
            name: logs,
            keep: 0,
          ),
          0,
        );
        expect(kept.existsSync(), isTrue);
      },
    );
  });

  group('rotateAtSize', () {
    late Directory folder;

    setUp(() {
      folder = Directory(p.join(scratch.path, 'rotate'));
      if (folder.existsSync()) folder.deleteSync(recursive: true);
      folder.createSync();
    });

    test(
      '5 MiB stays; one byte more becomes .old, replacing the previous one',
      () async {
        final file = File(p.join(folder.path, 'dolphin-persistent.jsonl'))
          ..writeAsBytesSync(Uint8List(_fiveMiB));
        final old = File('${file.path}.old');
        await StorageLogRotation.rotateAtSize(file);
        expect(file.lengthSync(), _fiveMiB);
        expect(old.existsSync(), isFalse);

        old.writeAsStringSync('previous');
        file.writeAsBytesSync([1], mode: FileMode.append);
        await StorageLogRotation.rotateAtSize(file);
        expect(file.existsSync(), isFalse);
        expect(old.lengthSync(), _fiveMiB + 1);
      },
    );

    test('a link, a .old that is not a file or a missing file: nothing moves '
        'and nothing throws', () async {
      final target = File(p.join(outside.path, 'big.jsonl'))
        ..writeAsBytesSync(Uint8List(64));
      final link = Link(p.join(folder.path, 'linked.jsonl'))
        ..createSync(target.path);
      await StorageLogRotation.rotateAtSize(File(link.path), maxBytes: 10);
      expect(link.existsSync(), isTrue);
      expect(target.lengthSync(), 64);
      expect(File('${link.path}.old').existsSync(), isFalse);

      final blocked = File(p.join(folder.path, 'blocked.jsonl'))
        ..writeAsBytesSync(Uint8List(64));
      Directory('${blocked.path}.old').createSync();
      await StorageLogRotation.rotateAtSize(blocked, maxBytes: 10);
      expect(blocked.lengthSync(), 64);

      await StorageLogRotation.rotateAtSize(
        File(p.join(folder.path, 'missing.jsonl')),
        maxBytes: 10,
      );
    });
  });

  group('Dolphin session logs', () {
    late Directory logs;

    setUpAll(() {
      logs = Directory(p.join(support.path, 'NeoStation', 'Dolphin', 'Logs'));
      messenger.setMockMethodCallHandler(dolphin, (call) async {
        if (call.method == 'isRunning') return false;
        throw PlatformException(
          code: 'unexpectedNativeCall',
          message: call.method,
        );
      });
    });

    tearDownAll(() => messenger.setMockMethodCallHandler(dolphin, null));

    // A path outside the private library: the launch stops at its first
    // check, after naming its session log, without any native launch.
    Future<DolphinLaunchReport> launch() => DolphinInternalV2Service.launch(
      folderName: 'gc',
      gamePath: p.join(outside.path, 'Game.iso'),
    );

    test('laying out deletes nothing; a launch keeps the ten newest session '
        'logs, never the persistent log', () async {
      final sessions = [
        for (var i = 1; i <= 15; i++) log(logs, session(i), 100 + i),
      ];
      final persistent = log(logs, 'dolphin-persistent.jsonl', 0);
      final notes = log(logs, 'notes.txt', 1);
      final target = log(outside, 'linked.jsonl', 2);
      final link = Link(p.join(logs.path, session(30)))
        ..createSync(target.path);

      // What startup, the scanner and the import menu call.
      await DolphinInternalV2Service.ensureLayout();
      expect(sessions.every((file) => file.existsSync()), isTrue);

      final first = await launch();
      expect(first.failedStage, 'route.path_rejected');
      expect(p.dirname(first.logPath), logs.path);
      expect(File(first.logPath).existsSync(), isTrue, reason: 'the new log');
      expect(sessions.take(5).where((file) => file.existsSync()), isEmpty);
      expect(sessions.skip(5).every((file) => file.existsSync()), isTrue);
      expect(
        persistent.existsSync(),
        isTrue,
        reason: 'the oldest file, never a session log',
      );
      expect(notes.existsSync(), isTrue);
      expect(link.existsSync(), isTrue);
      expect(target.existsSync(), isTrue);

      // Ten kept again at the next launch: the oldest of the earlier ones goes.
      final second = await launch();
      expect(sessions[5].existsSync(), isFalse);
      expect(sessions.skip(6).every((file) => file.existsSync()), isTrue);
      expect(File(first.logPath).existsSync(), isTrue);
      expect(File(second.logPath).existsSync(), isTrue);
      expect(persistent.existsSync(), isTrue);
    });

    test('the persistent log is rotated above 5 MiB when a launch names a '
        'session log', () async {
      final persistent = File(p.join(logs.path, 'dolphin-persistent.jsonl'))
        ..writeAsBytesSync(Uint8List(_fiveMiB + 1));
      final old = File('${persistent.path}.old');

      await launch();
      expect(persistent.existsSync(), isFalse);
      expect(old.lengthSync(), _fiveMiB + 1);

      persistent.writeAsBytesSync(Uint8List(_fiveMiB));
      await launch();
      expect(persistent.lengthSync(), _fiveMiB, reason: 'not over the limit');
      expect(old.lengthSync(), _fiveMiB + 1);
    });
  });

  group('KartPad runtime logs', () {
    late Directory logs;
    late File game;
    var transaction = 0;

    /// The Logs folder as the native launch found it, one entry per launch.
    final atNativeLaunch = <Set<String>>[];

    Future<void> sessionEnded() async {
      final delivered = Completer<void>();
      await messenger.handlePlatformMessage(
        kartPad.name,
        codec.encodeMethodCall(
          MethodCall('sessionEnded', {
            'transaction': transaction,
            'exitReason': 'userReturn',
            'success': true,
            'runtimeReleased': true,
          }),
        ),
        (_) => delivered.complete(),
      );
      await delivered.future;
    }

    setUpAll(() async {
      await KartPadInternalService.ensureLayout();
      logs = await KartPadInternalService.logsDirectory();
      game = File(
        p.join(
          (await KartPadInternalService.gamesDirectory()).path,
          'Mario Kart Wii.iso',
        ),
      )..writeAsBytesSync(_kartPadDisc());
      messenger.setMockMethodCallHandler(kartPad, (call) async {
        if (call.method != 'launch') return true;
        transaction = (call.arguments as Map)['transaction'] as int;
        atNativeLaunch.add(names(logs));
        return {'success': true, 'stage': 'first_frame'};
      });
    });

    tearDownAll(() async {
      // The bridge keeps its session in statics: end the last one.
      if (transaction > 0) await sessionEnded();
      messenger.setMockMethodCallHandler(kartPad, null);
    });

    String run(int index) => 'run-${index.toString().padLeft(2, '0')}.log';

    test('the ten newest *.log and console.txt are kept before the native '
        'launch, and nothing while a session may run', () async {
      for (var i = 0; i < 12; i++) {
        log(logs, run(i), 10 + 2 * i);
      }
      log(logs, 'console.txt', 15);
      log(logs, 'BOOT.LOG', 5);
      log(logs, 'notes.md', 0);
      log(logs, 'crash.dmp', 1);
      final target = log(outside, 'target.log', 2);
      Link(p.join(logs.path, 'old.log')).createSync(target.path);
      Directory(p.join(logs.path, 'archive.log')).createSync();
      final everything = names(logs);

      // What startup and the import menu call.
      await KartPadInternalService.ensureLayout();
      expect(names(logs), everything);

      final first = await KartPadInternalService.launch(game.path);
      expect(first.success, isTrue);
      expect(atNativeLaunch, hasLength(1));
      final gone = {'BOOT.LOG', run(0), run(1), run(2)};
      expect(
        atNativeLaunch.single,
        everything.difference(gone),
        reason: 'bounded before the native launch, nothing else touched',
      );
      expect(target.existsSync(), isTrue);

      // The session runs (the bridge owns it) and the core writes: another
      // launch bounds nothing and the bridge refuses it.
      for (var i = 0; i < 3; i++) {
        log(logs, 'live-$i.log', 40 + i);
      }
      final during = names(logs);
      final second = await KartPadInternalService.launch(game.path);
      expect(second.errorCode, 'KARTPAD_SESSION_ACTIVE');
      expect(atNativeLaunch, hasLength(1));
      expect(names(logs), during);

      // Once the session has ended, the next launch bounds again.
      await sessionEnded();
      final third = await KartPadInternalService.launch(game.path);
      expect(third.success, isTrue);
      expect(atNativeLaunch, hasLength(2));
      expect(
        atNativeLaunch.last,
        during.difference({'console.txt', run(3), run(4)}),
      );
      expect(target.existsSync(), isTrue);
    });

    test('the bridge lifecycle log is bounded at launch, never during a '
        'session', () async {
      // Free the session the previous test left running.
      await sessionEnded();
      final root = (await KartPadInternalService.rootDirectory()).path;
      final lifecycle = File(p.join(root, 'neostation-kartpad-lifecycle.log'));
      final old = File('${lifecycle.path}.old');
      lifecycle.writeAsBytesSync(List<int>.filled(5 * 1024 * 1024 + 1, 0x61));

      final first = await KartPadInternalService.launch(game.path);
      expect(first.success, isTrue);
      expect(old.existsSync(), isTrue, reason: 'over 5 MiB: rotated like app.log');
      expect(old.lengthSync(), 5 * 1024 * 1024 + 1);
      expect(lifecycle.existsSync(), isFalse);

      // The session now runs: the next launch is refused and rotates nothing.
      lifecycle.writeAsBytesSync(List<int>.filled(5 * 1024 * 1024 + 7, 0x62));
      final second = await KartPadInternalService.launch(game.path);
      expect(second.errorCode, 'KARTPAD_SESSION_ACTIVE');
      expect(lifecycle.lengthSync(), 5 * 1024 * 1024 + 7);
      expect(old.lengthSync(), 5 * 1024 * 1024 + 1);
    });
  });
}
