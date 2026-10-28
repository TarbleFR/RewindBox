import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/rpcs3_config_adapter.dart';
import 'package:neostation/services/rpcs3_game_profile_database.dart';
import 'package:rpcs3_internal_bridge/rpcs3_internal_bridge.dart';

@immutable
class Rpcs3GameProfile {
  const Rpcs3GameProfile({required this.serial, required this.settings});

  final String serial;
  final Map<String, String> settings;

  String toRpcs3Yaml([String base = '']) =>
      Rpcs3ConfigAdapter.mergeScalarOverrides(base, _yamlOverrides(settings));

  static Map<List<String>, String> _yamlOverrides(
    Map<String, String> settings,
  ) {
    final result = <List<String>, String>{};
    for (final entry in settings.entries) {
      final yamlPath = switch (entry.key) {
        'cpu.ppu_decoder' => const <String>['Core', 'PPU Decoder'],
        'cpu.spu_decoder' => const <String>['Core', 'SPU Decoder'],
        'cpu.ppu_profiler' => const <String>['Core', 'PPU Profiler'],
        'cpu.spu_block_size' => const <String>['Core', 'SPU Block Size'],
        'cpu.spu_xfloat_accuracy' => const <String>[
          'Core',
          'SPU XFloat Accuracy',
        ],
        'cpu.preferred_spu_threads' => const <String>[
          'Core',
          'Preferred SPU Threads',
        ],
        'advanced.llvm_precompilation' => const <String>[
          'Core',
          'LLVM Precompilation',
        ],
        'advanced.accurate_spu_reservations' => const <String>[
          'Core',
          'Accurate SPU Reservations',
        ],
        'emulator.max_llvm_threads' => const <String>[
          'Core',
          'Max LLVM Compile Threads',
        ],
        'gpu.shader_mode' => const <String>['Video', 'Shader Mode'],
        'gpu.shader_precision' => const <String>['Video', 'Shader Precision'],
        'gpu.write_color_buffers' => const <String>[
          'Video',
          'Write Color Buffers',
        ],
        'gpu.resolution_scale' => const <String>['Video', 'Resolution Scale'],
        'gpu.frame_limit' => const <String>['Video', 'Frame limit'],
        'gpu.multithreaded_rsx' => const <String>[
          'Video',
          'Multithreaded RSX',
        ],
        'gpu.async_texture_uploads' => const <String>[
          'Video',
          'Vulkan',
          'Asynchronous Texture Streaming',
        ],
        'experimental.mobile_spu_scheduling' => const <String>[
          'iOS Experimental',
          'Mobile SPU Compile Scheduling',
        ],
        'experimental.fps_optimization_batch' => const <String>[
          'iOS Experimental',
          'FPS Optimization Batch',
        ],
        'experimental.fifo_cache_size' => const <String>[
          'iOS Experimental',
          'RSX FIFO Read Cache',
        ],
        'experimental.getllar_backoff' => const <String>[
          'iOS Experimental',
          'GETLLAR Mobile Backoff',
        ],
        'experimental.gow3_mlaa_bypass' => const <String>[
          'iOS Experimental',
          'God of War III MLAA Bypass',
        ],
        'experimental.moltenvk_async_submits' => const <String>[
          'iOS Experimental',
          'MoltenVK Asynchronous Submits',
        ],
        _ => throw StateError(
          'Unsupported managed RPCS3 setting: ${entry.key}',
        ),
      };
      result[yamlPath] = entry.value;
    }
    return result;
  }
}

@immutable
class Rpcs3ResolvedProfile {
  const Rpcs3ResolvedProfile({
    required this.serial,
    required this.config,
    required this.family,
    required this.hasDatabaseRecommendation,
    required this.hasIndividualOverride,
  });

  final String serial;
  final String config;
  final Rpcs3ProfileFamily family;
  final bool hasDatabaseRecommendation;
  final bool hasIndividualOverride;

  bool get isManaged => config.trim().isNotEmpty;
}

/// Resolves `global -> family/GameDB -> title override`. Explicit user edits
/// are a separate native layer and are replayed last by the RPCS3 iOS core.
abstract final class Rpcs3GameProfileService {
  static final LoggerService _log = LoggerService.instance;
  static final RegExp _serialPattern = RegExp(r'^[A-Z0-9]{9,16}$');

  // This list remains intentionally small: it contains iOS evidence or a
  // platform-independent guest-timing fix, never speculative desktop tweaks.
  static const Map<String, Map<String, String>> _serialOverrides = {
    // Dynasty Warriors 6: the iOS ARM64 PPU LLVM path terminated during boot.
    'BLES00215': {
      'cpu.ppu_decoder': 'Interpreter (static)',
      'advanced.llvm_precompilation': 'false',
      'emulator.max_llvm_threads': '0',
      'experimental.mobile_spu_scheduling': 'Automatic',
      'cpu.spu_block_size': 'Safe',
    },
    'BLUS30110': {
      'cpu.ppu_decoder': 'Interpreter (static)',
      'advanced.llvm_precompilation': 'false',
      'emulator.max_llvm_threads': '0',
      'experimental.mobile_spu_scheduling': 'Automatic',
      'cpu.spu_block_size': 'Safe',
    },

    // God of War III: retain RPCS3's WCB/Ultra/Mega recommendations and add
    // the guarded ARM64 batch already instrumented by Build 256.
    'BCUS98111': _godOfWarIII,
    'BCES00510': _godOfWarIII,
    'BCES00799': _godOfWarIII,
    'BCJS37001': _godOfWarIII,
    'BCAS25003': _godOfWarIII,
    'BCKS15003': _godOfWarIII,

    // Dragon Ball Z HD Collection (BLES01658) has no title profile again.
    // Build 551 gave it asynchronous MoltenVK submits, asynchronous texture
    // streaming, the 4 KiB FIFO cache and the ARM64 batch, none of which had
    // ever run on the iPhone: every 551 boot (Dragon Ball Z twice, God of War
    // III once, 26 October 2026 logs) ended within 0.4 s of boot return,
    // before the PPU modules were loaded, while 545 and 547 reached that point
    // 0.40-0.44 s after boot return with the global profile. It runs the
    // global profile it ran on 547 (31-35 fps, no crash); a lever comes back
    // only alone and with device evidence.

    // Call of Duty: Black Ops II (BLES01717), build 583 iPhone logs: the
    // game is SPU-bound (3.6-4.3 SPU cores, RSX thread 0.15-0.18 core). In
    // the game scenes its SPUs store 1.1-6.3 million data-changing PUTLLC per
    // 5 s window; with "Accurate SPU Reservations" (Core default true) each
    // one takes the exclusive writer lock that parks every running PPU
    // thread: 0.74-2.9 s of writer-lock acquisition per window on the SPUs,
    // 4,000-9,500 PPU waits for 0.3-0.9 s (RANGELOCKPROF wl_putllc,
    // WAITPROF527 vm_range_episode). The frame rate follows them: 47-61 fps
    // under 0.4 million heavy PUTLLC per window, 24-29 fps around 1.2
    // million, 6-22 fps above 2.4 million. The relaxed path keeps the
    // reservation protocol; a change confined to one 16-byte lane is a
    // compare-and-swap under a range lock, without the writer lock. Same
    // choice as God of War III since Build 412; the official RPCS3 entry of
    // the title (SPU Block Size Safe, ZCULL) does not ask for accurate
    // reservations. Measured on the next run by the same counters.
    'BLES01717': {'advanced.accurate_spu_reservations': 'false'},

    // ARMSX3 issue #77 is guest pacing rather than an Android driver hack.
    // PS3 Native honours the title's alternate-vblank flip cadence.
    'BLUS31213': {'gpu.frame_limit': 'PS3 Native'},
    'BLES01935': {'gpu.frame_limit': 'PS3 Native'},
  };

  static const Map<String, String> _godOfWarIII = {
    'cpu.ppu_decoder': 'Recompiler (LLVM)',
    'cpu.spu_decoder': 'Recompiler (LLVM)',
    'cpu.ppu_profiler': 'false',
    // Persist raw SPU metadata on the first run and rebuild those safe guest
    // blocks before gameplay on later runs. Host ARM64 machine code is not
    // persisted because it still embeds process-specific addresses.
    'advanced.llvm_precompilation': 'true',
    'cpu.spu_block_size': 'Mega',
    'cpu.spu_xfloat_accuracy': 'Approximate',
    'cpu.preferred_spu_threads': '0',
    // Build 411 iPhone logs (7 October 2026): in heavy scenes the PPU threads
    // were blocked 0.85 to 1.5 s per second behind the exclusive writer lock
    // that every data-changing SPU PUTLLC and every PUTLLUC takes while
    // "Accurate SPU Reservations" (Core default true) is on; the SPU threads
    // spin until both PPUs park. The relaxed path keeps the range-lock and
    // reservation protocol (single-lane CAS, direct SPURS stores) and bypasses
    // no DMA lock. Hypothesis measured on the next run by RANGELOCKPROF
    // wl_putllc/wl_store128 and the PPU range-wait time, not proven here.
    'advanced.accurate_spu_reservations': 'false',
    // Build 565 (maintainer decision, 27 October 2026): no 30 fps cap. The
    // PS3 game is not locked to 30 fps; RPCS3 limits it to the 60 Hz vblank
    // (Auto) like every other title, so it runs as fast as the device allows
    // up to 60 fps with its own timing. Explicit, so a published GameDB entry
    // cannot bring a lower limit back; a per-game user choice still wins.
    'gpu.frame_limit': 'Auto',
    'gpu.resolution_scale': '75',
    // Build 551: no shader mode is forced. "Async Recompiler" skips the draws
    // whose pipeline is still compiling; the maintainer excludes skipped
    // draws, so God of War III keeps the global (Legacy) mode.
    'gpu.multithreaded_rsx': 'true',
    // Build 552: asynchronous texture streaming stays off. In this RPCS3 it
    // turns on asynchronous compute on MoltenVK, whose separate transfer
    // queue keeps passthrough DMA (guest memory imported as Vulkan buffers)
    // and synchronizes both queues with Vulkan events. None of it has run on
    // the iPhone: every logged boot reports async_tex=false.
    'gpu.async_texture_uploads': 'false',
    'experimental.fps_optimization_batch': 'Enabled',
    'experimental.fifo_cache_size': '4 KiB',
    'experimental.getllar_backoff': 'Enabled',
    // Build 552 kept MoltenVK submits synchronous after the 551 boots ended
    // within 0.4 s of boot return, while the RSX thread flipped the shader
    // cache dialog. Build 587: the Core decides. With asynchronous submits,
    // MoltenVK 1.4.2 encodes on its own queue thread after vkQueueSubmit has
    // returned, and vkAcquireNextImageKHR releases, without a lock, the
    // drawable that a still-queued present and the render before it use. The
    // Core 587 now waits for the last queued present before every
    // acquisition, and its Automatic mode turns them on for God of War III
    // only while the title's last asynchronous boot finished (a boot that
    // did not finish returns it to synchronous submits for good).
    'experimental.moltenvk_async_submits': 'Automatic',
    // The Core recognizes only the two official MLAA SPU hashes for God of
    // War III 01.00/01.03. It cannot affect another SPU module or title.
    'experimental.gow3_mlaa_bypass': 'Enabled',
  };

  static final Set<String> _detectedSerials = <String>{};

  static String? normalizeSerial(String? value) {
    final serial = value?.trim().toUpperCase() ?? '';
    return _serialPattern.hasMatch(serial) ? serial : null;
  }

  /// Synchronous individual override lookup retained for settings UI/tests.
  static Rpcs3GameProfile? profileForSerial(String? rawSerial) {
    final serial = normalizeSerial(rawSerial);
    if (serial == null) return null;
    return Rpcs3GameProfile(
      serial: serial,
      settings: <String, String>{...?_serialOverrides[serial]},
    );
  }

  static Future<Rpcs3ResolvedProfile?> resolveProfile(
    String? rawSerial, {
    bool allowNetwork = false,
  }) async {
    final serial = normalizeSerial(rawSerial);
    if (serial == null) return null;
    final database = await Rpcs3GameProfileDatabase.entryFor(
      serial,
      allowNetwork: allowNetwork,
    );
    final individual = profileForSerial(serial)!;
    final config = individual.toRpcs3Yaml(database?.config ?? '');
    return Rpcs3ResolvedProfile(
      serial: serial,
      config: Rpcs3ConfigAdapter.hasUsefulSetting(config) ? config : '',
      family: database?.family ?? Rpcs3ProfileFamily.balanced,
      hasDatabaseRecommendation: database != null,
      hasIndividualOverride: individual.settings.isNotEmpty,
    );
  }

  static void noteDetectedSerials(Iterable<String> serials) {
    _detectedSerials
      ..clear()
      ..addAll(serials.map(normalizeSerial).whereType<String>());
  }

  @visibleForTesting
  static Future<String> databasePayloadForSerials(
    Iterable<String> serials,
  ) async {
    final profiles = await Future.wait(
      serials.map((serial) => resolveProfile(serial)),
    );
    return _databasePayload(profiles.whereType<Rpcs3ResolvedProfile>());
  }

  static String _databasePayload(Iterable<Rpcs3ResolvedProfile> profiles) {
    final games = <String, dynamic>{};
    for (final profile in profiles) {
      if (!profile.isManaged) continue;
      games[profile.serial] = <String, String>{'config': profile.config};
    }
    return jsonEncode(<String, dynamic>{'return_code': 0, 'games': games});
  }

  static Future<Map<String, dynamic>> applyForLaunch(String rawSerial) async {
    final profile = await resolveProfile(rawSerial);
    if (profile == null) {
      return const <String, dynamic>{
        'success': false,
        'message': 'RPCS3 rejected the invalid PlayStation serial.',
      };
    }
    if (!profile.isManaged) {
      _log.i('RPCS3 ${profile.serial}: using RewindBox global iOS profile.');
      return <String, dynamic>{
        'success': true,
        'message': 'RPCS3 global iOS profile inherited for ${profile.serial}.',
      };
    }

    _detectedSerials.add(profile.serial);
    final resolved = await Future.wait(_detectedSerials.map(resolveProfile));
    final report = await Rpcs3InternalBridge.updateConfigDatabase(
      _databasePayload(resolved.whereType<Rpcs3ResolvedProfile>()),
    );
    if (report['success'] == true) {
      _log.i(
        'RPCS3 profile ready: ${profile.serial}; family=${profile.family.name}; '
        'database=${profile.hasDatabaseRecommendation}; '
        'individual=${profile.hasIndividualOverride}; user overrides remain last.',
      );
    }
    return report;
  }

  /// Publish offline profiles immediately, then refresh the official source in
  /// the background. Launch never waits on the network.
  static Future<void> publishDetectedProfilesIfReady() async {
    if (_detectedSerials.isEmpty) return;
    await _publishDetected(coreReady: false);
    unawaited(_refreshAndRepublish());
  }

  /// Flush library recommendations after the existing runtime owner has
  /// initialized the Core and completed JIT handoff. No network refresh is
  /// started here; earlier publication may have found the Core still unloaded.
  static Future<void> publishDetectedProfilesForReadyRuntime() =>
      _publishDetected(coreReady: true);

  // Build 541 logs showed only "unavailable" lines: the library scan publishes
  // before the Core is loaded (expected, retried after startup) and the later
  // successful publication logged nothing. Both outcomes are now explicit.
  static Future<void> _publishDetected({required bool coreReady}) async {
    try {
      final profiles = await Future.wait(_detectedSerials.map(resolveProfile));
      final managed = profiles
          .whereType<Rpcs3ResolvedProfile>()
          .where((profile) => profile.isManaged)
          .toList(growable: false);
      if (managed.isEmpty) return;
      final report = await Rpcs3InternalBridge.updateConfigDatabase(
        _databasePayload(managed),
      );
      final serials = managed.map((profile) => profile.serial).join(',');
      if (report['success'] == true) {
        _log.i(
          'RPCS3 GameDB published: ${managed.length} profile(s) [$serials].',
        );
      } else {
        final message = '${report['message'] ?? 'Core not ready'}';
        final deferred = !coreReady && message.contains('must be initialized');
        _log.i(
          deferred
              ? 'RPCS3 GameDB publication deferred until Core startup: $message'
              : 'RPCS3 GameDB publication failed: $message',
        );
      }
    } catch (error) {
      _log.i('RPCS3 GameDB publication unavailable: $error');
    }
  }

  static Future<void> _refreshAndRepublish() async {
    if (await Rpcs3GameProfileDatabase.refreshIfStale()) {
      await _publishDetected(coreReady: false);
    }
  }
}
