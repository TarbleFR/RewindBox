// Build 454: the libretro bridge's isSessionActive answer, as the bytes
// Flutter's iOS engine really sends (test/libretro_session_envelopes.dart,
// checked against the real plugin and Flutter.framework in the iOS Simulator
// by test/libretro_channel_codec_test.py), fed to the real MethodChannel at
// the byte level.
//
// Build 453 answered an int32 0 or 1: `invokeMethod<bool>` threw "type 'int'
// is not a subtype of type 'bool?' in type cast" and the 3DS system data
// import refused to run, "could not check whether a game is running". The
// earlier tests mocked the channel with Dart booleans (or injected a Dart
// closure), whose bytes are those of the fixed bridge: they never saw it.
//
// Covered with the production probe (no injected closure): the bridge (only
// a boolean counts; a non-boolean, null, an error or a missing plugin is
// never "no session"), the game-launch monitor (an unknown answer is never
// proof of exit), the 3DS system data service and the option store (refused
// while a game launches or runs, "unknown" with Build 453's answer, nothing
// written), the storage guard.
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive_io.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:neostation/services/embedded_ios_session_status.dart';
import 'package:neostation/services/libretro_3ds_system_data_service.dart';
import 'package:neostation/services/libretro_core_option_store.dart';
import 'package:neostation/services/storage/storage_cleanup_planner.dart';
import 'package:path/path.dart' as p;

import 'libretro_session_envelopes.dart';

const String _channelName = 'neostation/libretro_internal';
const StandardMethodCodec _codec = StandardMethodCodec();

ByteData _bytes(String hex) {
  final out = Uint8List(hex.length ~/ 2);
  for (var index = 0; index < out.length; index++) {
    out[index] = int.parse(hex.substring(index * 2, index * 2 + 2), radix: 16);
  }
  return ByteData.sublistView(out);
}

String _hex(ByteData data) => <String>[
  for (var index = 0; index < data.lengthInBytes; index++)
    data.getUint8(index).toRadixString(16).padLeft(2, '0'),
].join();

/// seeddb.bin as the core reads it: a count, 12 bytes of padding, then 32
/// bytes per seed.
Uint8List _seeddb(int count) {
  final out = Uint8List(16 + 32 * count);
  ByteData.sublistView(out).setUint32(0, count, Endian.little);
  for (var index = 16; index < out.length; index++) {
    out[index] = (index * 7 + count) & 0xff;
  }
  return out;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final calls = <String>[];

  /// The bridge answers every isSessionActive call with [envelope], the
  /// bytes of one answer; the request must be the plain method call.
  void answer(ByteData? Function() envelope) {
    messenger.setMockMessageHandler(_channelName, (message) async {
      final call = _codec.decodeMethodCall(message);
      calls.add(call.method);
      expect(call.method, 'isSessionActive');
      expect(call.arguments, isNull);
      return envelope();
    });
  }

  void answerHex(String hex) => answer(() => _bytes(hex));

  setUp(calls.clear);
  tearDown(() => messenger.setMockMessageHandler(_channelName, null));

  group('the bytes on the wire', () {
    test('Dart booleans, which the earlier mocks returned, encode as the fixed '
        "bridge's answers; Build 453 sent integers", () {
      expect(
        _hex(_codec.encodeSuccessEnvelope(true)),
        fixedEnvelopes[envelopeRunning],
      );
      expect(
        _hex(_codec.encodeSuccessEnvelope(false)),
        fixedEnvelopes[envelopeIdle],
      );
      for (final state in fixedEnvelopes.keys) {
        final fixed = _codec.decodeEnvelope(_bytes(fixedEnvelopes[state]!));
        final build453 = _codec.decodeEnvelope(
          _bytes(build453Envelopes[state]!),
        );
        expect(fixed, isA<bool>(), reason: state);
        expect(build453, isA<int>(), reason: state);
        expect(build453, fixed == true ? 1 : 0, reason: state);
      }
    });
  });

  group('LibretroInternalBridge.isSessionActive', () {
    test('this tree: false with no session and once stopped, true while a game '
        'launches or runs', () async {
      const expected = <String, bool>{
        envelopeIdle: false,
        envelopeLaunching: true,
        envelopeRunning: true,
        envelopeStopped: false,
      };
      expect(expected.keys, fixedEnvelopes.keys);
      for (final state in expected.keys) {
        answerHex(fixedEnvelopes[state]!);
        expect(
          await LibretroInternalBridge.isSessionActive(),
          expected[state],
          reason: state,
        );
      }
      expect(calls, List<String>.filled(4, 'isSessionActive'));
    });

    test(
      "Build 453's answer: the cast of the video, now a probe failure, never "
      '"no session"',
      () async {
        const channel = MethodChannel(_channelName);
        for (final state in build453Envelopes.keys) {
          answerHex(build453Envelopes[state]!);
          // What Build 453's Dart side did with these bytes (the code shown
          // on the iPhone).
          await expectLater(
            channel.invokeMethod<bool>('isSessionActive'),
            throwsA(
              isA<TypeError>().having(
                (error) => '$error',
                'message',
                "type 'int' is not a subtype of type 'bool?' in type cast",
              ),
            ),
            reason: state,
          );
          await expectLater(
            LibretroInternalBridge.isSessionActive(),
            throwsA(
              isA<LibretroSessionProbeException>().having(
                (error) => error.answer,
                'answer',
                state == envelopeLaunching || state == envelopeRunning ? 1 : 0,
              ),
            ),
            reason: state,
          );
        }
        answerHex(build453Envelopes[envelopeIdle]!);
        await expectLater(
          LibretroInternalBridge.isSessionActive(),
          throwsA(
            predicate(
              (error) =>
                  '$error' ==
                  'LibretroSessionProbeException: non-boolean answer (int 0)',
            ),
          ),
        );
      },
    );

    test(
      'a null, a string, a native error or no plugin at all: never "no session"',
      () async {
        answer(() => _codec.encodeSuccessEnvelope(null));
        await expectLater(
          LibretroInternalBridge.isSessionActive(),
          throwsA(
            isA<LibretroSessionProbeException>().having(
              (error) => error.answer,
              'answer',
              isNull,
            ),
          ),
        );
        answer(() => _codec.encodeSuccessEnvelope('false'));
        await expectLater(
          LibretroInternalBridge.isSessionActive(),
          throwsA(isA<LibretroSessionProbeException>()),
        );
        answer(() => _codec.encodeErrorEnvelope(code: 'unavailable'));
        await expectLater(
          LibretroInternalBridge.isSessionActive(),
          throwsA(isA<PlatformException>()),
        );
        // No handler: the engine answers nothing.
        answer(() => null);
        await expectLater(
          LibretroInternalBridge.isSessionActive(),
          throwsA(isA<MissingPluginException>()),
        );
      },
    );
  });

  group('game launch monitoring (EmbeddedIOSSessionStatus)', () {
    test('only an explicit false ends the embedded libretro session; Build '
        "453's answer and unknown answers keep it running", () async {
      Future<bool> active() =>
          EmbeddedIOSSessionStatus.isActive('ios_libretro_internal');
      answerHex(fixedEnvelopes[envelopeIdle]!);
      expect(await active(), isFalse);
      answerHex(fixedEnvelopes[envelopeStopped]!);
      expect(await active(), isFalse);
      answerHex(fixedEnvelopes[envelopeLaunching]!);
      expect(await active(), isTrue);
      answerHex(fixedEnvelopes[envelopeRunning]!);
      expect(await active(), isTrue);
      // Build 453: the bool cast threw out of the monitor, whose poller
      // ended the game's frontend session a few seconds after its launch.
      for (final state in build453Envelopes.keys) {
        answerHex(build453Envelopes[state]!);
        expect(await active(), isTrue, reason: state);
      }
      answer(() => _codec.encodeSuccessEnvelope(null));
      expect(await active(), isTrue);
      answer(() => _codec.encodeErrorEnvelope(code: 'unavailable'));
      expect(await active(), isTrue);
      answer(() => null);
      expect(await active(), isTrue);
    });
  });

  group('3DS system data, options and storage with the production probe', () {
    late Directory root;
    late Directory saves;
    late Directory backups;
    late Directory config;
    late String zip;

    setUp(() {
      root = Directory.systemTemp.createTempSync('libretro_session_probe_');
      saves = Directory(p.join(root.path, 'Libretro', 'Saves'));
      backups = Directory(p.join(root.path, 'Libretro', 'Backups', 'Azahar'));
      config = Directory(p.join(root.path, 'Libretro', 'Config'));
      final archive = Archive()
        ..add(ArchiveFile.bytes('sysdata/seeddb.bin', _seeddb(2)));
      zip = p.join(root.path, 'sources', 'seeds.zip');
      File(zip)
        ..createSync(recursive: true)
        ..writeAsBytesSync(ZipEncoder().encodeBytes(archive));
    });

    tearDown(() => root.deleteSync(recursive: true));

    Directory user() => Directory(p.join(saves.path, 'Azahar', 'Azahar'));
    File seeddb() => File(
      p.joinAll([
        user().path,
        ...Libretro3dsSystemDataService.seeddbTarget.split('/'),
      ]),
    );

    // No sessionProbe: LibretroInternalBridge.isSessionActive, as in the app.
    Libretro3dsSystemDataService service() => Libretro3dsSystemDataService(
      savesDirectory: () async => saves,
      backupsDirectory: () async => backups,
      diagnosticsDirectory: () async =>
          Directory(p.join(root.path, 'Diagnostics'))..createSync(),
    );

    test('the import installs when no game runs (this tree, idle)', () async {
      answerHex(fixedEnvelopes[envelopeIdle]!);
      final data = service();
      expect((await data.recoverUnfinished()).isEmpty, isTrue);
      final report = await data.install(await data.analyze(<String>[zip]));
      expect(report.succeeded, isTrue);
      expect(seeddb().readAsBytesSync(), _seeddb(2));
      expect(calls, <String>['isSessionActive', 'isSessionActive']);
    });

    test('refused while a game launches or runs: "a game is running", nothing '
        'written', () async {
      for (final state in <String>[envelopeLaunching, envelopeRunning]) {
        answerHex(fixedEnvelopes[state]!);
        final data = service();
        final plan = await data.analyze(<String>[zip]);
        for (final action in <Future<Object?> Function()>[
          () => data.install(plan),
          data.recoverUnfinished,
          data.restoreLastBackup,
        ]) {
          await expectLater(
            action(),
            throwsA(
              isA<Libretro3dsSystemDataException>()
                  .having(
                    (error) => error.error,
                    'error',
                    Libretro3dsSystemDataError.sessionActive,
                  )
                  .having(
                    (error) => error.sessionUnknown,
                    'sessionUnknown',
                    isFalse,
                  ),
            ),
            reason: state,
          );
        }
        expect(user().existsSync(), isFalse, reason: state);
        expect(backups.existsSync(), isFalse, reason: state);
      }
    });

    test("Build 453's answer: unknown session state with the probe's detail, "
        'nothing written; the same import goes through once the answer is a '
        'boolean', () async {
      answerHex(build453Envelopes[envelopeIdle]!);
      final data = service();
      final plan = await data.analyze(<String>[zip]);
      await expectLater(
        data.install(plan),
        throwsA(
          isA<Libretro3dsSystemDataException>()
              .having(
                (error) => error.error,
                'error',
                Libretro3dsSystemDataError.sessionActive,
              )
              .having((error) => error.sessionUnknown, 'sessionUnknown', isTrue)
              .having(
                (error) => error.technicalDetail,
                'technicalDetail',
                'isSessionActive probe failed: '
                    'LibretroSessionProbeException: non-boolean answer '
                    '(int 0)',
              ),
        ),
      );
      expect(user().existsSync(), isFalse);

      answerHex(fixedEnvelopes[envelopeIdle]!);
      expect((await data.install(plan)).succeeded, isTrue);
      expect(seeddb().readAsBytesSync(), _seeddb(2));
    });

    test('the option store writes only on a boolean "no session"', () async {
      final store = LibretroCoreOptionStore(
        configDirectory: () async => config,
      );
      File azahar() => File(p.join(config.path, 'Azahar.json'));

      answerHex(fixedEnvelopes[envelopeRunning]!);
      await expectLater(
        store.write('Azahar', <String, String?>{
          'citra_region_value': 'Europe',
        }),
        throwsA(
          isA<LibretroCoreOptionStoreException>().having(
            (error) => error.technicalDetail,
            'technicalDetail',
            isNull,
          ),
        ),
      );
      answerHex(build453Envelopes[envelopeIdle]!);
      await expectLater(
        store.write('Azahar', <String, String?>{
          'citra_region_value': 'Europe',
        }),
        throwsA(
          isA<LibretroCoreOptionStoreException>().having(
            (error) => error.technicalDetail,
            'technicalDetail',
            'isSessionActive probe failed: '
                'LibretroSessionProbeException: non-boolean answer (int 0)',
          ),
        ),
      );
      expect(azahar().existsSync(), isFalse);

      answerHex(fixedEnvelopes[envelopeIdle]!);
      expect(
        await store.write('Azahar', <String, String?>{
          'citra_region_value': 'Europe',
        }),
        <String, String>{'citra_region_value': 'Europe'},
      );
      expect(azahar().existsSync(), isTrue);
    });

    test('the storage guard frees the libretro files only on a boolean "no '
        'session"', () async {
      StorageSessionGuard guard() => StorageSessionGuard(
        launchActive: () => false,
        dolphinMarkerPresent: () async => false,
        libretroJournalUnfinished: () async => false,
        importActive: () => false,
        libraryScanActive: () => false,
      );
      answerHex(fixedEnvelopes[envelopeIdle]!);
      var state = await guard().check();
      expect(state.libretroActive, isFalse);
      expect(state.probeErrors, isEmpty);

      answerHex(fixedEnvelopes[envelopeRunning]!);
      state = await guard().check();
      expect(state.libretroActive, isTrue);
      expect(state.probeErrors, isEmpty);

      answerHex(build453Envelopes[envelopeIdle]!);
      state = await guard().check();
      expect(state.libretroActive, isTrue);
      expect(
        state.probeErrors['libretroActive'],
        'LibretroSessionProbeException: non-boolean answer (int 0)',
      );
    });
  });
}
