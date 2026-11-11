import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/rpcs3_game_profile_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('RPCS3 serial configuration profiles', () {
    test(
      'normalizes recognized RPCS3 serial families without using titles',
      () {
        for (final serial in <String>[
          'BLUS30110',
          'BLES00215',
          'BCUS98114',
          'BCES00001',
          'NPUB12345',
          'NPEB12345',
          'ABCD12345678',
        ]) {
          expect(Rpcs3GameProfileService.normalizeSerial(serial), serial);
        }
        expect(
          Rpcs3GameProfileService.normalizeSerial('bles00215'),
          'BLES00215',
        );
        expect(
          Rpcs3GameProfileService.normalizeSerial('Dynasty Warriors 6'),
          isNull,
        );
        expect(Rpcs3GameProfileService.normalizeSerial('../BLES00215'), isNull);
        expect(Rpcs3GameProfileService.normalizeSerial('BLES-00215'), isNull);
      },
    );

    test(
      'returns Dynasty Warriors 6 to PPU LLVM explicitly, only for its serials',
      () {
        final eu = Rpcs3GameProfileService.profileForSerial('BLES00215')!;
        final us = Rpcs3GameProfileService.profileForSerial('BLUS30110')!;
        final other = Rpcs3GameProfileService.profileForSerial('BLES00412')!;

        // Build 610: one variable changes; the other four values stay.
        for (final profile in [eu, us]) {
          expect(profile.settings, {
            'cpu.ppu_decoder': 'Recompiler (LLVM)',
            'advanced.llvm_precompilation': 'false',
            'emulator.max_llvm_threads': '0',
            'experimental.mobile_spu_scheduling': 'Automatic',
            'cpu.spu_block_size': 'Safe',
          });
        }
        expect(other.settings, isNot(contains('cpu.ppu_decoder')));
        expect(other.settings, isEmpty);
      },
    );

    test(
      'God of War III has no RewindBox title profile: the RPCS3 database is the reference',
      () {
        for (final serial in <String>[
          'BCUS98111', 'BCES00510', 'BCES00799',
          'BCJS37001', 'BCAS25003', 'BCKS15003',
        ]) {
          expect(
            Rpcs3GameProfileService.profileForSerial(serial)!.settings,
            isEmpty,
          );
        }
        for (final serial in <String>['BCUS98114', 'BLES00412', 'NPUB12345']) {
          expect(
            Rpcs3GameProfileService.profileForSerial(serial)!.settings,
            isEmpty,
          );
        }
      },
    );

    test('returns independent profile maps between games and launches', () {
      final first = Rpcs3GameProfileService.profileForSerial('BLES01717')!;
      first.settings['advanced.accurate_spu_reservations'] = 'false';
      expect(
        Rpcs3GameProfileService.profileForSerial('BLES01717')!
            .settings['advanced.accurate_spu_reservations'],
        'true',
      );
      expect(
        Rpcs3GameProfileService.profileForSerial('BCES00510')!.settings,
        isEmpty,
      );
    });

    test('merges title overrides into GameDB YAML keyed only by serial', () async {
      final payload = await Rpcs3GameProfileService.databasePayloadForSerials(
        <String>['BLES00215', 'Dynasty Warriors 6', 'BCAS20014'],
      );
      final root = jsonDecode(payload) as Map<String, dynamic>;
      final games = root['games'] as Map<String, dynamic>;

      expect(root['return_code'], 0);
      expect(games.keys, contains('BLES00215'));
      expect(games.keys, contains('BCAS20014'));
      expect(games, isNot(contains('Dynasty Warriors 6')));
      final bles = games['BLES00215'] as Map<String, dynamic>;
      final yaml = bles['config'] as String;
      expect(yaml, contains('Core:'));
      expect(yaml, contains('PPU Decoder: Recompiler (LLVM)'));
      expect(yaml, isNot(contains('Interpreter (static)')));
      expect(yaml, contains('SPU Block Size: Safe'));
      expect(yaml, contains('iOS Experimental:'));
      expect(yaml, isNot(contains('Video:')));
      expect(yaml, isNot(contains('Audio:')));
    });

    test('never publishes empty inherited-global entries', () async {
      final mixedPayload = await Rpcs3GameProfileService.databasePayloadForSerials(
        <String>['BLES00215', 'ABCD123456789'],
      );
      final mixedGames =
          (jsonDecode(mixedPayload) as Map<String, dynamic>)['games']
              as Map<String, dynamic>;

      expect(mixedGames.keys, orderedEquals(<String>['BLES00215']));
      for (final entry in mixedGames.values) {
        final config = (entry as Map<String, dynamic>)['config'];
        expect(config, isA<String>());
        expect(config, isNotEmpty);
      }

      final inheritedPayload =
          await Rpcs3GameProfileService.databasePayloadForSerials(
            <String>['ABCD123456789', 'ZZZZ123456789'],
          );
      final inheritedGames =
          (jsonDecode(inheritedPayload) as Map<String, dynamic>)['games']
              as Map<String, dynamic>;
      expect(inheritedGames, isEmpty);
    });

    test('God of War III publishes its RPCS3 database entry only', () async {
      final payload = await Rpcs3GameProfileService.databasePayloadForSerials(
        <String>['BCES00510'],
      );
      final games =
          (jsonDecode(payload) as Map<String, dynamic>)['games']
              as Map<String, dynamic>;
      final yaml =
          (games['BCES00510'] as Map<String, dynamic>)['config'] as String;

      // The official entry (api.rpcs3.net/config), nothing added.
      expect(yaml, contains('SPU Block Size: Mega'));
      expect(yaml, contains('Shader Precision: Ultra'));
      expect(yaml, contains('Write Color Buffers: true'));
      // IPA 724 (device): unplayable graphics with the entry's asynchronous
      // texture streaming; the iOS adapter no longer applies that one value.
      expect(yaml, isNot(contains('Asynchronous Texture Streaming')));
      expect(yaml, isNot(contains('Vulkan:')));
      // Maintainer, 10 November 2026: 100 % by default, no title profile.
      expect(yaml, isNot(contains('Resolution Scale')));
      expect(yaml, isNot(contains('Multithreaded RSX')));
      expect(yaml, isNot(contains('Accurate SPU Reservations')));
      expect(yaml, isNot(contains('Frame limit')));
      expect(yaml, isNot(contains('LLVM Precompilation')));
      expect(yaml, isNot(contains('MLAA')));
    });

    test(
      'Black Ops II keeps its official entry, accurate SPU reservations and a boot SPU warm-up',
      () async {
        // Build 658: the build 657 logs show a 40.8 s freeze under relaxed
        // reservations (busy SPUs and a spinning PPU on one queue word) and
        // 8.7 thousand SPU programs rebuilt at each first scene transition.
        final profile = Rpcs3GameProfileService.profileForSerial('BLES01717')!;
        expect(profile.settings, <String, String>{
          'advanced.accurate_spu_reservations': 'true',
          'advanced.llvm_precompilation': 'true',
          'experimental.spu_warmup_scope': 'All titles with metadata',
        });
        final payload = await Rpcs3GameProfileService.databasePayloadForSerials(
          <String>['BLES01717'],
        );
        final games =
            (jsonDecode(payload) as Map<String, dynamic>)['games']
                as Map<String, dynamic>;
        final yaml =
            (games['BLES01717'] as Map<String, dynamic>)['config'] as String;
        expect(yaml, contains('Accurate SPU Reservations: true'));
        expect(yaml, isNot(contains('Accurate SPU Reservations: false')));
        expect(yaml, contains('LLVM Precompilation: true'));
        expect(yaml, contains('SPU Warmup Scope: All titles with metadata'));
        expect(yaml, contains('SPU Block Size: Safe'));
        expect(yaml, contains('Accurate ZCULL stats: false'));
        expect(yaml, contains('Relaxed ZCULL Sync: false'));
        expect(yaml, isNot(contains('MoltenVK Asynchronous Submits')));
        // Core 932: the six serials of the RPCS3 compatibility list share the
        // database entry and receive the same correction (BLUS31011 used to
        // be left without it).
        for (final serial in <String>[
          'BLES01718',
          'BLES01719',
          'BLES01720',
          'BLUS31011',
          'BLUS31140',
        ]) {
          expect(
            Rpcs3GameProfileService.profileForSerial(serial)!.settings,
            profile.settings,
            reason: serial,
          );
        }
      },
    );

    test(
      "Assassin's Creed relaxes SPU reservations over the official entry",
      () async {
        // Build 589: the build 585 logs show Black Ops II's signature, about
        // one million data-changing PUTLLC per window under the writer lock.
        // Build 610: asynchronous texture streaming off again, as for God of
        // War III; the Core decides asynchronous MoltenVK submits.
        // Build 613: ZCULL accuracy Approximate (device result, BLES00158).
        for (final serial in <String>['BLES00158', 'BLUS30089']) {
          final profile = Rpcs3GameProfileService.profileForSerial(serial)!;
          expect(profile.settings, <String, String>{
            'advanced.accurate_spu_reservations': 'false',
            'gpu.async_texture_uploads': 'false',
            'gpu.zcull_accuracy': 'Approximate',
          });
          final payload =
              await Rpcs3GameProfileService.databasePayloadForSerials(
                <String>[serial],
              );
          final games =
              (jsonDecode(payload) as Map<String, dynamic>)['games']
                  as Map<String, dynamic>;
          final yaml =
              (games[serial] as Map<String, dynamic>)['config'] as String;
          expect(yaml, contains('Accurate SPU Reservations: false'));
          expect(yaml, contains('Multithreaded RSX: true'));
          expect(yaml, contains('Asynchronous Texture Streaming: false'));
          expect(yaml, isNot(contains('Asynchronous Texture Streaming: true')));
          // The official entry's "Relaxed ZCULL Sync: true" is replaced in
          // place, so the published entry holds a single value per key.
          expect(yaml, contains('Relaxed ZCULL Sync: false'));
          expect(yaml, isNot(contains('Relaxed ZCULL Sync: true')));
          expect(yaml, contains('Accurate ZCULL stats: false'));
          expect(yaml, isNot(contains('Accurate ZCULL stats: true')));
          expect('Relaxed ZCULL Sync:'.allMatches(yaml), hasLength(1));
          expect('Accurate ZCULL stats:'.allMatches(yaml), hasLength(1));
          expect(yaml, isNot(contains('MoltenVK Asynchronous Submits')));
        }
      },
    );

    test(
      "Assassin's Creed IV returns to PPU LLVM and keeps the official buffers",
      () async {
        // IPA 666 logs (BLES01882): under the official entry's static
        // interpreter the title-screen load froze after the intro; Build 643
        // logged no frame in 38 s. Only the decoder changes.
        for (final serial in <String>[
          'BLES01882',
          'BLES01883',
          'BLUS31193',
          'NPEB01396',
          'NPUB31246',
        ]) {
          expect(
            Rpcs3GameProfileService.profileForSerial(serial)!.settings,
            <String, String>{'cpu.ppu_decoder': 'Recompiler (LLVM)'},
          );
          final payload =
              await Rpcs3GameProfileService.databasePayloadForSerials(
                <String>[serial],
              );
          final games =
              (jsonDecode(payload) as Map<String, dynamic>)['games']
                  as Map<String, dynamic>;
          final yaml =
              (games[serial] as Map<String, dynamic>)['config'] as String;
          expect(yaml, contains('PPU Decoder: Recompiler (LLVM)'));
          expect(yaml, isNot(contains('Interpreter (static)')));
          expect('PPU Decoder:'.allMatches(yaml), hasLength(1));
          expect(yaml, contains('Read Color Buffers: true'));
          expect(yaml, contains('Write Color Buffers: true'));
        }
        // The same official entry also covers other games (Assassin's Creed
        // III among them) and BLES01884, which no source names: unchanged.
        for (final serial in <String>['BLES01884', 'BLUS30991', 'NPEB01099']) {
          expect(
            Rpcs3GameProfileService.profileForSerial(serial)!.settings,
            isEmpty,
          );
          final payload =
              await Rpcs3GameProfileService.databasePayloadForSerials(
                <String>[serial],
              );
          final games =
              (jsonDecode(payload) as Map<String, dynamic>)['games']
                  as Map<String, dynamic>;
          final yaml =
              (games[serial] as Map<String, dynamic>)['config'] as String;
          expect(yaml, contains('PPU Decoder: Interpreter (static)'));
        }
      },
    );

    test(
      'ZCULL accuracy expands to the two RPCS3 booleans the Core reads back',
      () {
        // Same table as the Core (RPCS3IOSZcullAccuracy.h): Precise =
        // (precise true, relaxed false), Approximate = (false, false),
        // Relaxed = (false, true).
        String yamlFor(String value) => Rpcs3GameProfile(
          serial: 'BLES00158',
          settings: <String, String>{'gpu.zcull_accuracy': value},
        ).toRpcs3Yaml();
        expect(yamlFor('Precise'), contains('Accurate ZCULL stats: true'));
        expect(yamlFor('Precise'), contains('Relaxed ZCULL Sync: false'));
        expect(yamlFor('Approximate'), contains('Accurate ZCULL stats: false'));
        expect(yamlFor('Approximate'), contains('Relaxed ZCULL Sync: false'));
        expect(yamlFor('Relaxed'), contains('Accurate ZCULL stats: false'));
        expect(yamlFor('Relaxed'), contains('Relaxed ZCULL Sync: true'));
        expect(() => yamlFor('Fast'), throwsStateError);
        // An install updated from an earlier build still holds the earlier
        // database entry (relaxed) and a refreshed official entry may bring it
        // back: the title value is merged over whichever base is present.
        const relaxedBase =
            'Video:\n  Accurate ZCULL stats: true\n  Relaxed ZCULL Sync: true\n';
        final merged = Rpcs3GameProfile(
          serial: 'BLES00158',
          settings: <String, String>{'gpu.zcull_accuracy': 'Approximate'},
        ).toRpcs3Yaml(relaxedBase);
        expect(merged, contains('Accurate ZCULL stats: false'));
        expect(merged, contains('Relaxed ZCULL Sync: false'));
        expect(merged, isNot(contains(': true')));
      },
    );

    test(
      'only Assassin\'s Creed receives the ZCULL value; other titles keep theirs',
      () async {
        final payload = await Rpcs3GameProfileService.databasePayloadForSerials(
          <String>['BLES01717', 'BCES00510', 'BCAS20066', 'BLES01658'],
        );
        final games =
            (jsonDecode(payload) as Map<String, dynamic>)['games']
                as Map<String, dynamic>;
        String yaml(String serial) =>
            (games[serial] as Map<String, dynamic>?)?['config'] as String? ??
            '';
        // Official entries stay as they are.
        expect(yaml('BLES01717'), contains('Relaxed ZCULL Sync: false'));
        expect(yaml('BCAS20066'), contains('Relaxed ZCULL Sync: true'));
        expect(yaml('BCES00510'), isNot(contains('ZCULL')));
        expect(yaml('BLES01658'), isNot(contains('ZCULL')));
        for (final serial in <String>['BLES01717', 'BCES00510', 'BCAS20066']) {
          expect(
            Rpcs3GameProfileService.profileForSerial(serial)!.settings,
            isNot(contains('gpu.zcull_accuracy')),
          );
        }
      },
    );

    test(
      'Dragon Ball Z HD Collection runs the global profile it ran on 547',
      () async {
        // Build 552: the 551 title profile (asynchronous submits and texture
        // streaming, FIFO 4 KiB, ARM64 batch) is withdrawn after the 551
        // boot crashes; no setting of this title may turn them back on.
        final profile = Rpcs3GameProfileService.profileForSerial('BLES01658')!;
        expect(profile.settings, isEmpty);
        final payload = await Rpcs3GameProfileService.databasePayloadForSerials(
          <String>['BLES01658'],
        );
        final games =
            (jsonDecode(payload) as Map<String, dynamic>)['games']
                as Map<String, dynamic>;
        final entry = games['BLES01658'] as Map<String, dynamic>?;
        final yaml = entry?['config'] as String? ?? '';
        expect(yaml, isNot(contains('MoltenVK Asynchronous Submits: Enabled')));
        expect(yaml, isNot(contains('Asynchronous Texture Streaming: true')));
        expect(yaml, isNot(contains('RSX FIFO Read Cache: 4 KiB')));
        expect(yaml, isNot(contains('FPS Optimization Batch: Enabled')));
      },
    );

    test(
      'launch delegates once to the runtime owner before boot without mutating settings',
      () {
        final launcher = File(
          'lib/services/rpcs3_launch_service.dart',
        ).readAsStringSync();
        // The single startup owner replaced the old launch-time profile
        // mutation in e4aa0a53. Serial recommendations are published by the
        // library; the Core applies them before explicit user overrides.
        const prepare =
            'await Rpcs3InternalService.ensureGameplayInitialized();';
        const boot = 'return await Rpcs3InternalService.launchTitle(';
        expect(prepare.allMatches(launcher), hasLength(1));
        expect(boot.allMatches(launcher), hasLength(1));
        expect(launcher.indexOf(prepare), lessThan(launcher.indexOf(boot)));
        expect(
          launcher,
          isNot(contains('Rpcs3GameProfileService.applyForLaunch')),
        );
        expect(launcher, isNot(contains('Rpcs3InternalBridge.setSetting(')));
        expect(
          launcher,
          isNot(contains('Rpcs3InternalBridge.setGameSetting(')),
        );
      },
    );

    test('runtime publishes local profiles after successful helper completion', () {
      final service = File(
        'lib/services/rpcs3_internal_service.dart',
      ).readAsStringSync();
      final startup = service.substring(
        service.indexOf('static Future<void> _initializeRuntime()'),
        service.indexOf('/// A Universal attach'),
      );
      const publish =
          'await Rpcs3GameProfileService.publishDetectedProfilesForReadyRuntime();';
      expect(publish.allMatches(service), hasLength(1));
      expect(
        startup.indexOf(
          'completionPending = false;',
          startup.indexOf("if (completion['success'] != true)"),
        ),
        lessThan(startup.indexOf(publish)),
      );
      expect(
        startup.indexOf(publish),
        lessThan(startup.indexOf('_initialized = true;')),
      );
      expect(
        startup.indexOf(publish),
        lessThan(startup.indexOf('Rpcs3RuntimePhase.ready')),
      );
    });

    test('offline publication survives a cold Core and omits inherited globals', () async {
      const channel = MethodChannel('neostation/rpcs3_tuning');
      final messenger = TestDefaultBinaryMessengerBinding
          .instance.defaultBinaryMessenger;
      final calls = <MethodCall>[];
      final accepted = <Map<String, dynamic>>[];
      var coreReady = false;
      var networkRequests = 0;
      messenger.setMockMethodCallHandler(channel, (call) async {
        calls.add(call);
        expect(call.method, 'updateConfigDatabase');
        if (!coreReady) {
          return <String, dynamic>{'success': false, 'message': 'Core not ready'};
        }
        final arguments = call.arguments as Map;
        accepted.add(
          jsonDecode(arguments['content'] as String) as Map<String, dynamic>,
        );
        return <String, dynamic>{'success': true};
      });
      addTearDown(() {
        messenger.setMockMethodCallHandler(channel, null);
        Rpcs3GameProfileService.noteDetectedSerials(const <String>[]);
      });
      // The God of War III serials the RPCS3 database holds (BCJS37001 has no
      // entry and no RewindBox profile any more).
      const serials = <String>[
        'BCUS98111', 'BCES00510', 'BCES00799',
        'BCAS25003', 'BCKS15003',
      ];
      Rpcs3GameProfileService.noteDetectedSerials(<String>[
        ...serials, 'ABCD123456789',
      ]);
      await HttpOverrides.runZoned(() async {
        // The common publisher must retain the detected titles when library
        // discovery happens before the Core is loaded.
        await Rpcs3GameProfileService.publishDetectedProfilesForReadyRuntime();
        expect(calls, hasLength(1));
        expect(accepted, isEmpty);
        coreReady = true;
        await Rpcs3GameProfileService.publishDetectedProfilesForReadyRuntime();
        expect(calls, hasLength(2));
        expect(accepted, hasLength(1));
        final games = accepted.single['games'] as Map<String, dynamic>;
        expect(games.keys, unorderedEquals(serials));
        for (final entry in games.values) {
          final yaml = (entry as Map<String, dynamic>)['config'] as String;
          expect(yaml, isNot(contains('LLVM Precompilation')));
          expect(yaml, contains('SPU Block Size: Mega'));
        }
        Rpcs3GameProfileService.noteDetectedSerials(<String>['ABCD123456789']);
        await Rpcs3GameProfileService.publishDetectedProfilesForReadyRuntime();
        expect(
          calls,
          hasLength(2),
          reason: 'an inherited-global-only set never overwrites the native database',
        );
        await Future<void>.delayed(Duration.zero);
      }, createHttpClient: (_) {
        networkRequests++;
        throw StateError('ready publication must remain offline');
      });
      expect(networkRequests, 0);
    });

    test('launch bypasses the native database for inherited-global serials', () {
      final source = File(
        'lib/services/rpcs3_game_profile_service.dart',
      ).readAsStringSync();
      final launchBody = source.substring(
        source.indexOf('static Future<Map<String, dynamic>> applyForLaunch'),
      );

      expect(launchBody, contains('if (!profile.isManaged)'));
      expect(launchBody, contains("'success': true"));
      expect(
        launchBody.indexOf('if (!profile.isManaged)'),
        lessThan(
          launchBody.indexOf('_detectedSerials.add(profile.serial)'),
        ),
      );
    });
  });
}
