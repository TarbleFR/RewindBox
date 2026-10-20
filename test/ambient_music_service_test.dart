import 'dart:async';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/frontend_media_gate.dart';
import 'package:neostation/services/home_music_service.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

/// The shared SoLoud engine, recorded.
class FakeBackend implements AmbientMusicBackend {
  final events = <String>[];
  bool ready = false;
  int _next = 1;
  final Map<int, Duration> positions = <int, Duration>{};
  final Set<int> voices = <int>{};

  @override
  bool get engineReady => ready;

  @override
  Future<void> prepareEngine() async {
    ready = true;
  }

  @override
  Future<Object> load(String path, {required bool stream}) async {
    events.add('load ${p.basename(path)} ${stream ? 'disk' : 'memory'}');
    return 'source:$path';
  }

  @override
  Object play(
    Object source, {
    required double volume,
    required Duration start,
  }) {
    final voice = _next++;
    voices.add(voice);
    positions[voice] = start;
    events.add('play $voice at ${start.inMilliseconds} volume $volume');
    return voice;
  }

  @override
  void fade(Object voice, double volume, Duration duration) {
    events.add(
      'fade $voice to ${volume.toStringAsFixed(4)} in ${duration.inMilliseconds}',
    );
  }

  @override
  Duration position(Object voice) => positions[voice as int] ?? Duration.zero;

  @override
  Future<void> stop(Object voice) async {
    voices.remove(voice);
    events.add('stop $voice');
  }

  @override
  Future<void> dispose(Object source) async {
    events.add('dispose');
  }
}

/// The Music player: playing, and ducked under an audible preview video.
class FakeUserMusic extends ChangeNotifier {
  bool playing = false;
  bool ducked = false;

  void set({bool? playing, bool? ducked}) {
    this.playing = playing ?? this.playing;
    this.ducked = ducked ?? this.ducked;
    notifyListeners();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FakeBackend backend;
  late FrontendMediaGate gate;
  late ValueNotifier<bool> session;
  late FakeUserMusic userMusic;
  late Directory custom;

  HomeMusicService create() => HomeMusicService.forTesting(
    backend: backend,
    gate: gate,
    session: session,
    sessionActive: () => session.value,
    userMusic: userMusic,
    userMusicPlaying: () => userMusic.playing,
    userMusicDucked: () => userMusic.ducked,
    bundledTrackPath: () async => '/bundle/once_upon_a_time_loop.ogg',
    customDirectory: () async => custom,
  );

  /// Waits for every queued playback update.
  Future<void> settle(HomeMusicService service) => service.setMainMenuActive(false);

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    backend = FakeBackend();
    gate = FrontendMediaGate();
    session = ValueNotifier<bool>(false);
    userMusic = FakeUserMusic();
    custom = Directory.systemTemp.createTempSync('neostation-ambient-');
  });

  tearDown(() {
    if (custom.existsSync()) custom.deleteSync(recursive: true);
  });

  test('a new install plays the bundled loop, streamed, with a fade-in', () async {
    final service = create();
    await service.attachFrontend();

    expect(service.enabled, isTrue);
    expect(service.volume, HomeMusicService.defaultVolume);
    expect(service.hasMusic, isFalse);
    expect(backend.events, <String>[
      'load once_upon_a_time_loop.ogg disk',
      'play 1 at 0 volume 0.0',
      'fade 1 to 0.2500 in 1200',
    ]);
    expect(service.isPlaying, isTrue);
  });

  test('nothing plays before the frontend is shown', () async {
    final service = create();
    await service.init();
    await service.setMainMenuActive(false);
    expect(backend.events, isEmpty);
  });

  test('tab changes and the Systems menu visibility never restart it', () async {
    final service = create();
    await service.attachFrontend();
    final before = List<String>.of(backend.events);
    for (final visible in <bool>[false, true, false, false, true]) {
      await service.setMainMenuActive(visible);
    }
    expect(backend.events, before);
  });

  test('a game launch fades it out before the handoff, keeps it stopped '
      'during the game and resumes where it stopped', () async {
    final service = create();
    await service.attachFrontend();
    backend.positions[1] = const Duration(seconds: 12);
    backend.events.clear();

    // GameService.beginLaunchPending holds the gate; the launch awaits quiet.
    final quiet = gate.hold('gameSession');
    session.value = true; // GameLaunchManager.beginSession
    await quiet;
    expect(backend.events, <String>[
      'fade 1 to 0.0000 in 500',
      'stop 1',
      'dispose',
    ]);
    expect(service.isPlaying, isFalse);

    // The native session ends: the gate is released before the audio
    // session is restored; the manager is still active, nothing restarts.
    backend.events.clear();
    gate.release('gameSession');
    await settle(service);
    expect(backend.events, isEmpty);

    // GameLaunchManager._finalize restored the audio session, then ended.
    session.value = false;
    await settle(service);
    expect(backend.events, <String>[
      'load once_upon_a_time_loop.ogg disk',
      'play 2 at 12000 volume 0.0',
      'fade 2 to 0.2500 in 1600',
    ]);
  });

  test('an external launch: stopped in the background, back on return', () async {
    final service = create();
    await service.attachFrontend();
    backend.positions[1] = const Duration(seconds: 30);
    await gate.hold('gameSession');
    session.value = true;
    // RetroArch takes the foreground; the session ends in the background.
    service.didChangeAppLifecycleState(AppLifecycleState.hidden);
    service.didChangeAppLifecycleState(AppLifecycleState.paused);
    gate.release('gameSession');
    session.value = false;
    await settle(service);
    expect(service.isPlaying, isFalse);
    backend.events.clear();

    service.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settle(service);
    expect(backend.events, <String>[
      'load once_upon_a_time_loop.ogg disk',
      'play 2 at 30000 volume 0.0',
      'fade 2 to 0.2500 in 1600',
    ]);
  });

  test('a cancelled launch fades it back in instead of cutting it', () async {
    final service = create();
    await service.attachFrontend();
    backend.events.clear();
    final quiet = gate.hold('gameSession');
    // The launch fails during the fade: released before it ends.
    await Future<void>.delayed(const Duration(milliseconds: 100));
    gate.release('gameSession');
    await quiet;
    await settle(service);
    expect(backend.events, <String>[
      'fade 1 to 0.0000 in 500',
      'fade 1 to 0.2500 in 1200',
    ]);
    expect(service.isPlaying, isTrue);

    // Released before the fade even started: nothing audible changes.
    backend.events.clear();
    final instant = gate.hold('gameSession');
    gate.release('gameSession');
    await instant;
    await settle(service);
    expect(backend.events, isEmpty);
  });

  test('the switch fades it out, is kept, and a restart honours it', () async {
    final service = create();
    await service.attachFrontend();
    backend.events.clear();
    await service.setEnabled(false);
    expect(backend.events, <String>['fade 1 to 0.0000 in 500', 'stop 1', 'dispose']);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getBool(HomeMusicService.enabledPreferenceKey), isFalse);

    backend = FakeBackend();
    final restarted = create();
    await restarted.attachFrontend();
    expect(restarted.enabled, isFalse);
    expect(backend.events, isEmpty);

    await restarted.setEnabled(true);
    expect(backend.events.first, 'load once_upon_a_time_loop.ogg disk');
    expect(prefs.getBool(HomeMusicService.enabledPreferenceKey), isTrue);
  });

  test('Build 447 menu-music preferences: only a switched-off chosen track '
      'stays off', () {
    bool resolve(bool? stored, bool? legacy, bool chosen) =>
        HomeMusicService.resolveEnabled(
          stored: stored,
          legacyEnabled: legacy,
          hadChosenTrack: chosen,
        );
    expect(resolve(null, null, false), isTrue, reason: 'new install');
    // Build 447 wrote false whenever no file had been chosen.
    expect(resolve(null, false, false), isTrue);
    expect(resolve(null, false, true), isFalse);
    expect(resolve(null, true, true), isTrue);
    expect(resolve(false, true, true), isFalse, reason: 'own key wins');
    expect(resolve(true, false, true), isTrue, reason: 'own key wins');
  });

  test('a chosen file that was switched off stays off and keeps its file', () async {
    final file = File(p.join(custom.path, 'main_menu_music.mp3'))
      ..writeAsBytesSync(<int>[0, 1, 2]);
    SharedPreferences.setMockInitialValues(<String, Object>{
      HomeMusicService.legacyEnabledPreferenceKey: false,
      'neostation_home_music_path': file.path,
      'neostation_home_music_name': 'theme.mp3',
    });
    final service = create();
    await service.attachFrontend();
    expect(service.enabled, isFalse);
    expect(service.hasMusic, isTrue);
    expect(service.selectedFileName, 'theme.mp3');
    expect(backend.events, isEmpty);
    expect(file.existsSync(), isTrue);
    // The legacy key is read, never rewritten.
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getBool(HomeMusicService.legacyEnabledPreferenceKey), isFalse);
    expect(prefs.getBool(HomeMusicService.enabledPreferenceKey), isNull);
  });

  test('a chosen file replaces the loop (in memory); removing it brings the '
      'loop back', () async {
    final file = File(p.join(custom.path, 'main_menu_music.flac'))
      ..writeAsBytesSync(<int>[0, 1, 2]);
    SharedPreferences.setMockInitialValues(<String, Object>{
      HomeMusicService.legacyEnabledPreferenceKey: true,
      'neostation_home_music_path': file.path,
      'neostation_home_music_name': 'mine.flac',
    });
    final service = create();
    await service.attachFrontend();
    expect(backend.events.first, 'load main_menu_music.flac memory');
    backend.events.clear();

    await service.clearMusic();
    expect(backend.events, <String>[
      'fade 1 to 0.0000 in 500',
      'stop 1',
      'dispose',
      'load once_upon_a_time_loop.ogg disk',
      'play 2 at 0 volume 0.0',
      'fade 2 to 0.2500 in 1200',
    ]);
    expect(file.existsSync(), isFalse);
    expect(service.hasMusic, isFalse);
    expect(service.enabled, isTrue);
  });

  test('volume: its own setting, a squared gain, kept and clamped', () async {
    expect(HomeMusicService.gainFor(0.5), 0.25);
    expect(HomeMusicService.gainFor(1.0), 1.0);
    expect(HomeMusicService.gainFor(0.0), closeTo(0.0025, 1e-9));
    final service = create();
    await service.attachFrontend();
    backend.events.clear();

    await service.setVolume(0.8, persist: false);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getDouble(HomeMusicService.volumePreferenceKey), isNull);
    await service.setVolume(0.8);
    expect(prefs.getDouble(HomeMusicService.volumePreferenceKey), 0.8);
    await service.setVolume(0);
    expect(service.volume, HomeMusicService.minVolume);
    expect(backend.events, <String>[
      'fade 1 to 0.6400 in 150',
      'fade 1 to 0.0025 in 150',
    ]);

    backend = FakeBackend();
    final restarted = create();
    await restarted.attachFrontend();
    expect(restarted.volume, HomeMusicService.minVolume);
    expect(backend.events.last, 'fade 1 to 0.0025 in 1200');
  });

  test('it yields to the Music player and goes silent under an audible '
      'preview', () async {
    final service = create();
    await service.attachFrontend();
    backend.positions[1] = const Duration(seconds: 5);
    backend.events.clear();

    userMusic.set(ducked: true);
    await settle(service);
    userMusic.set(ducked: false);
    await settle(service);
    expect(backend.events, <String>[
      'fade 1 to 0.0000 in 300',
      'fade 1 to 0.2500 in 300',
    ]);

    backend.events.clear();
    userMusic.set(playing: true);
    await settle(service);
    expect(backend.events, <String>['fade 1 to 0.0000 in 500', 'stop 1', 'dispose']);
    backend.events.clear();
    userMusic.set(playing: false);
    await settle(service);
    expect(backend.events, <String>[
      'load once_upon_a_time_loop.ogg disk',
      'play 2 at 5000 volume 0.0',
      'fade 2 to 0.2500 in 1600',
    ]);
  });

  test('released engine: the position is kept and the dead voice is never '
      'touched', () async {
    final service = create();
    await service.attachFrontend();
    backend.positions[1] = const Duration(seconds: 40);
    backend.events.clear();

    // MusicPlayerService.appPaused releases the engine before this service
    // sees the lifecycle change.
    service.handleEngineTearingDown();
    backend.ready = false;
    service.didChangeAppLifecycleState(AppLifecycleState.paused);
    await settle(service);
    expect(backend.events, isEmpty);

    service.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settle(service);
    expect(backend.events, <String>[
      'load once_upon_a_time_loop.ogg disk',
      'play 2 at 40000 volume 0.0',
      'fade 2 to 0.2500 in 1600',
    ]);
  });

  test('Control Center (inactive) does not interrupt it', () async {
    final service = create();
    await service.attachFrontend();
    backend.events.clear();
    service.didChangeAppLifecycleState(AppLifecycleState.inactive);
    service.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await settle(service);
    expect(backend.events, isEmpty);
  });

  test('side sessions (Wii Menu, ARMSX2 BIOS) hold it until their end', () async {
    final service = create();
    await service.attachFrontend();
    backend.events.clear();
    final ended = Completer<void>();
    final launched = await service.holdForSideSession<bool>(
      launch: () async {
        expect(backend.events, <String>['fade 1 to 0.0000 in 500', 'stop 1', 'dispose']);
        return true;
      },
      started: (result) => result,
      ended: () => ended.future,
    );
    expect(launched, isTrue);
    await settle(service);
    expect(service.isPlaying, isFalse);
    ended.complete();
    await Future<void>.delayed(Duration.zero);
    await settle(service);
    expect(service.isPlaying, isTrue);

    // A launch that opens no session gives the music back at once.
    await service.holdForSideSession<bool>(
      launch: () async => false,
      started: (result) => result,
      ended: () => Completer<void>().future,
    );
    await settle(service);
    expect(service.isPlaying, isTrue);
  });

  test('shared engine restart: cut without fade, back after the session', () async {
    final service = create();
    await service.attachFrontend();
    session.value = true;
    await gate.hold('gameSession');
    gate.release('gameSession');
    backend.events.clear();
    await service.beforeSharedEngineRestart();
    await service.afterSharedEngineRestart();
    expect(backend.events, isEmpty, reason: 'still in the game session');
    session.value = false;
    await settle(service);
    expect(backend.events.where((e) => e.startsWith('play')), hasLength(1));
  });
}
