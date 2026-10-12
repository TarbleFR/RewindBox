import 'dart:async';
import 'dart:io';

import 'package:armsx2_internal_bridge/armsx2_internal_bridge.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter/widgets.dart';
import 'package:flutter_soloud/flutter_soloud.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'audio_policy_service.dart';
import 'config_service.dart';
import 'embedded_ios_session_status.dart';
import 'frontend_media_gate.dart';
import 'game_launch_manager.dart';
import 'logger_service.dart';
import 'music_player_service.dart';
import 'sfx_service.dart';
import 'storage/storage_import_activity.dart';

/// What [HomeMusicService] uses of the shared SoLoud engine. Tests replace it;
/// sources and voices are opaque values.
abstract class AmbientMusicBackend {
  /// The shared engine exists (sources and voices are valid only while it
  /// lives: it is released when the app goes to the background).
  bool get engineReady;

  /// Creates the shared engine if needed (through the SFX initialization
  /// path) and reasserts NeoStation's ambient audio category.
  Future<void> prepareEngine();

  /// [stream]: decoded from disk while playing (LoadMode.disk), otherwise
  /// decoded once in memory.
  Future<Object> load(String path, {required bool stream});

  /// A looping voice at [volume], started at [start] of the track.
  Object play(Object source, {required double volume, required Duration start});
  void fade(Object voice, double volume, Duration duration);
  Duration position(Object voice);
  Future<void> stop(Object voice);
  Future<void> dispose(Object source);
}

class _SoLoudAmbientBackend implements AmbientMusicBackend {
  const _SoLoudAmbientBackend();

  @override
  bool get engineReady => SoLoud.instance.isInitialized;

  @override
  Future<void> prepareEngine() async {
    // SFX owns the shared SoLoud initialization path. Once the engine is
    // ready, the ambience manages only its own source, voice and volume.
    await SfxService().init();
    // Returning from an embedded emulator does not necessarily generate an
    // iOS foreground transition. Reassert NeoStation's ambient category at
    // every start so the Ring/Silent switch always wins even if a native
    // game session previously selected `.playback`.
    await AudioPolicyService().restoreAfterSharedAudioEngineInitialization(
      reason: 'main-menu-music',
    );
  }

  @override
  Future<Object> load(String path, {required bool stream}) =>
      SoLoud.instance.loadFile(
        path,
        mode: stream ? LoadMode.disk : LoadMode.memory,
      );

  @override
  Object play(
    Object source, {
    required double volume,
    required Duration start,
  }) {
    final resume = start > Duration.zero;
    final voice = SoLoud.instance.play(
      source as AudioSource,
      volume: volume,
      looping: true,
      paused: resume,
    );
    if (resume) {
      SoLoud.instance.seek(voice, start);
      SoLoud.instance.setPause(voice, false);
    }
    // A SoundHandle is an extension type over its int id.
    return voice.id;
  }

  SoundHandle _handle(Object voice) => SoundHandle(voice as int);

  @override
  void fade(Object voice, double volume, Duration duration) {
    if (duration <= Duration.zero) {
      SoLoud.instance.setVolume(_handle(voice), volume);
    } else {
      SoLoud.instance.fadeVolume(_handle(voice), volume, duration);
    }
  }

  @override
  Duration position(Object voice) => SoLoud.instance.getPosition(_handle(voice));

  @override
  Future<void> stop(Object voice) => SoLoud.instance.stop(_handle(voice));

  @override
  Future<void> dispose(Object source) =>
      SoLoud.instance.disposeSource(source as AudioSource);
}

/// The track the ambience plays: the bundled loop or the user's file.
class _AmbientTrack {
  const _AmbientTrack(this.key, this.path, {required this.stream});

  /// Identifies the track for resume positions (the file path).
  final String key;
  final String path;
  final bool stream;
}

/// NeoStation's ambient music (Build 448): one manager for the whole
/// frontend.
///
/// - The default track is "Once Upon a Time (loop)" by TAD (OpenGameArt,
///   CC0), bundled as `assets/sounds/once_upon_a_time_loop.ogg`, built
///   sample-exact by `tools/ambient_music/build_ambient_music_asset.py` and
///   streamed from disk (a few kilobytes of memory); SoLoud loops it without
///   gap or click (test/ambient_music_loop_test.py renders 21 loops).
/// - A file chosen in Settings › Themes replaces it. NeoStation keeps a copy
///   in `<user-data>/menu_music` (a stored track never needs choosing again).
/// - Enabled by default; Settings › General › "Ambient music" turns it off
///   and sets its own volume, independent of the games and of the sound
///   effects. Both are kept in SharedPreferences.
/// - It plays in every section: changing tab or opening a game list never
///   restarts it. It yields to the Music player and goes silent while a game
///   preview video plays with sound.
/// - A game launch (embedded or external) fades it out before the handoff
///   through [FrontendMediaGate]; it stays stopped, its source released,
///   for the whole game, and fades back in, where it stopped, once the
///   [GameLaunchManager] session has restored the audio session.
/// - In the background the shared engine is released
///   ([MusicPlayerService.appPaused]); the position is kept and the
///   ambience fades back in on return.
class HomeMusicService extends ChangeNotifier with WidgetsBindingObserver {
  HomeMusicService._internal()
    : _backend = const _SoLoudAmbientBackend(),
      _gate = FrontendMediaGate.instance,
      _session = GameLaunchManager(),
      _sessionActive = (() => GameLaunchManager().isActive),
      _userMusic = MusicPlayerService(),
      _userMusicPlaying = (() => MusicPlayerService().isPlaying),
      _userMusicDucked = (() => MusicPlayerService().isDucked),
      _bundledTrackPath = _prepareBundledTrack,
      _customDirectory = _defaultCustomDirectory,
      _observeLifecycle = true;

  /// An isolated manager for tests: a fake engine, gate, game session and
  /// Music player.
  @visibleForTesting
  HomeMusicService.forTesting({
    required AmbientMusicBackend backend,
    required FrontendMediaGate gate,
    required Listenable session,
    required bool Function() sessionActive,
    required Listenable userMusic,
    required bool Function() userMusicPlaying,
    required bool Function() userMusicDucked,
    required Future<String> Function() bundledTrackPath,
    required Future<Directory> Function() customDirectory,
  }) : _backend = backend,
       _gate = gate,
       _session = session,
       _sessionActive = sessionActive,
       _userMusic = userMusic,
       _userMusicPlaying = userMusicPlaying,
       _userMusicDucked = userMusicDucked,
       _bundledTrackPath = bundledTrackPath,
       _customDirectory = customDirectory,
       _observeLifecycle = false;

  static final HomeMusicService _instance = HomeMusicService._internal();
  factory HomeMusicService() => _instance;

  /// Preferences (SharedPreferences, no database column).
  static const String enabledPreferenceKey = 'neostation_ambient_music_enabled';
  static const String volumePreferenceKey = 'neostation_ambient_music_volume';

  /// Before Build 448 the menu music needed a chosen file and its switch was
  /// written `false` whenever no file was chosen: only a `false` written
  /// next to a chosen file is a choice of the user. Read, never rewritten.
  static const String legacyEnabledPreferenceKey =
      'neostation_home_music_enabled';
  static const String _pathPreferenceKey = 'neostation_home_music_path';
  static const String _namePreferenceKey = 'neostation_home_music_name';
  static const String _directoryName = 'menu_music';
  static const List<String> _allowedExtensions = ['mp3', 'wav', 'ogg', 'flac'];

  /// The bundled loop and the identity of its cached copy.
  static const String bundledTrackAsset =
      'assets/sounds/once_upon_a_time_loop.ogg';
  static const String bundledTrackTitle = 'Once Upon a Time';
  static const String bundledTrackArtist = 'TAD';
  static const int bundledTrackBytes = 1752020;
  static const String bundledTrackSha256Prefix = '86a12b26';
  static const String _bundledCacheDirectory = 'ambient_music';

  /// Volume setting, 5 %–100 %. The voice gain is its square: equal steps
  /// of the setting sound like equal steps of loudness. 50 % (gain 0.25) is
  /// close to the former fixed menu-music gain (0.28).
  static const double defaultVolume = 0.5;
  static const double minVolume = 0.05;
  static const double maxVolume = 1.0;

  static const Duration fadeOut = Duration(milliseconds: 500);
  static const Duration startFadeIn = Duration(milliseconds: 1200);
  static const Duration resumeFadeIn = Duration(milliseconds: 1600);
  static const Duration volumeFade = Duration(milliseconds: 150);
  static const Duration duckFade = Duration(milliseconds: 300);

  /// How often a side session (Wii Menu) is probed for its end, as
  /// [GameLaunchManager] probes embedded games.
  static const Duration embeddedSessionProbe = Duration(seconds: 2);

  final AmbientMusicBackend _backend;
  final FrontendMediaGate _gate;
  final Listenable _session;
  final bool Function() _sessionActive;
  final Listenable _userMusic;
  final bool Function() _userMusicPlaying;
  final bool Function() _userMusicDucked;
  final Future<String> Function() _bundledTrackPath;
  final Future<Directory> Function() _customDirectory;
  final bool _observeLifecycle;

  final LoggerService _log = LoggerService.instance;

  Future<void>? _initialization;
  bool _initialized = false;
  bool _enabled = true;
  double _volume = defaultVolume;
  bool _frontendReady = false;
  bool _appActive = true;
  bool _sharedEngineRestarting = false;
  final Set<Object> _suspensions = <Object>{};

  String? _musicPath;
  String? _musicName;
  String? _bundledPath;

  // Playback, owned by the serialized reconciliation below.
  Object? _source;
  Object? _voice;
  String? _playingKey;
  double _appliedGain = 0;
  Duration _resumePosition = Duration.zero;
  String? _resumeKey;

  /// Bumped when the shared engine is released: every source and voice
  /// obtained before is invalid.
  int _engineEpoch = 0;

  Future<void> _queue = Future<void>.value();
  Future<void>? _pendingReconcile;

  bool get enabled => _enabled;

  /// Volume setting (5 %–100 %), not the voice gain.
  double get volume => _volume;

  /// A file chosen by the user replaces the bundled loop.
  bool get hasMusic =>
      _musicPath != null &&
      _musicPath!.isNotEmpty &&
      File(_musicPath!).existsSync();
  String? get selectedFileName => _musicName;

  /// The ambience is audible or fading in right now.
  bool get isPlaying => _voice != null;

  /// Voice gain for the current setting.
  static double gainFor(double volume) {
    final clamped = volume.clamp(minVolume, maxVolume).toDouble();
    return clamped * clamped;
  }

  /// Build 448 rule for a missing [enabledPreferenceKey]: enabled, unless
  /// the user had switched off a track they had chosen before.
  static bool resolveEnabled({
    required bool? stored,
    required bool? legacyEnabled,
    required bool hadChosenTrack,
  }) {
    if (stored != null) return stored;
    if (legacyEnabled == false && hadChosenTrack) return false;
    return true;
  }

  Future<void> init() => _initialization ??= _initialize();

  Future<void> _initialize() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _musicPath = prefs.getString(_pathPreferenceKey);
      _musicName = prefs.getString(_namePreferenceKey);
      final hadChosenTrack = _musicPath?.isNotEmpty ?? false;
      _enabled = resolveEnabled(
        stored: prefs.getBool(enabledPreferenceKey),
        legacyEnabled: prefs.getBool(legacyEnabledPreferenceKey),
        hadChosenTrack: hadChosenTrack,
      );
      final storedVolume = prefs.getDouble(volumePreferenceKey);
      _volume = (storedVolume ?? defaultVolume)
          .clamp(minVolume, maxVolume)
          .toDouble();

      await _migrateOrDiscoverMusic();

      if (!hasMusic) {
        // A chosen file that no longer exists: back to the bundled loop.
        _musicPath = null;
        _musicName = null;
        await prefs.remove(_pathPreferenceKey);
        await prefs.remove(_namePreferenceKey);
      }
    } catch (e) {
      _musicPath = null;
      _musicName = null;
      _log.w('[AmbientMusic] Could not load preferences: $e');
    }

    _initialized = true;
    if (_observeLifecycle) WidgetsBinding.instance.addObserver(this);
    _userMusic.addListener(_onDependencyChanged);
    _session.addListener(_onDependencyChanged);
    _gate.addListener(_onDependencyChanged);
    // Invoked synchronously when a game launch holds the gate: the fade-out
    // starts at once and the launch waits for it before the handoff.
    _gate.register(this, _fadeOutForLaunch);
    notifyListeners();
  }

  /// The frontend is on screen: the ambience may start (AppScreen).
  Future<void> attachFrontend() async {
    _frontendReady = true;
    await init();
    await _sync();
  }

  /// Kept for the Systems screen (locked to the Build 419 library baseline),
  /// which reports whether it is the visible menu. Since Build 448 the
  /// ambience follows the whole frontend, not one tab: a visible Systems
  /// menu only confirms that the frontend is ready, and leaving it changes
  /// nothing.
  Future<void> setMainMenuActive(bool value) async {
    if (value) _frontendReady = true;
    await init();
    await _sync();
  }

  /// Settings › General › "Ambient music".
  Future<void> setEnabled(bool value) async {
    await init();
    if (_enabled == value) return;
    _enabled = value;
    await _persist((prefs) => prefs.setBool(enabledPreferenceKey, value));
    notifyListeners();
    await _sync();
  }

  /// Settings › General › "Music volume". [persist] is false while a slider
  /// is dragged and true when it is released.
  Future<void> setVolume(double value, {bool persist = true}) async {
    await init();
    final clamped = value.clamp(minVolume, maxVolume).toDouble();
    final changed = clamped != _volume;
    _volume = clamped;
    if (persist) {
      await _persist((prefs) => prefs.setDouble(volumePreferenceKey, clamped));
    }
    if (!changed) return;
    notifyListeners();
    await _sync();
  }

  /// Opens the platform file picker, imports one supported audio file into
  /// NeoStation's user-data directory and plays it in place of the bundled
  /// loop.
  Future<bool> chooseMusic() async {
    await init();
    final imported = await _pickAndStoreMusic();
    if (!imported) return false;
    if (!_enabled) {
      _enabled = true;
      await _persist((prefs) => prefs.setBool(enabledPreferenceKey, true));
    }
    notifyListeners();
    await _sync();
    return true;
  }

  /// Removes the chosen file: the bundled loop plays again (the ambience
  /// switch is unchanged).
  Future<void> clearMusic() async {
    await init();
    final oldPath = _musicPath;
    _musicPath = null;
    _musicName = null;
    // Stop the voice reading that file before deleting it.
    await _sync();

    if (oldPath != null) {
      try {
        final file = File(oldPath);
        if (await file.exists()) await file.delete();
      } catch (e) {
        _log.w('[AmbientMusic] Could not delete the chosen music file: $e');
      }
    }
    await _persist((prefs) async {
      await prefs.remove(_pathPreferenceKey);
      await prefs.remove(_namePreferenceKey);
    });
    notifyListeners();
  }

  /// Fades the ambience out until [resumeFor] is called with the same
  /// [owner] (side sessions, a file being replaced).
  Future<void> suspendFor(Object owner) async {
    await init();
    _suspensions.add(owner);
    await _sync();
  }

  Future<void> resumeFor(Object owner) async {
    if (!_suspensions.remove(owner)) return;
    await _sync();
  }

  /// An embedded session started outside the game launch dialog (Wii Menu,
  /// ARMSX2 BIOS): the ambience fades out before [launch] and comes back
  /// once [ended] completes, or at once when [started] says that [launch]
  /// opened no session.
  Future<T> holdForSideSession<T>({
    required Future<T> Function() launch,
    required bool Function(T result) started,
    required Future<void> Function() ended,
  }) async {
    final owner = Object();
    await suspendFor(owner);
    final T result;
    try {
      result = await launch();
    } catch (_) {
      await resumeFor(owner);
      rethrow;
    }
    if (!started(result)) {
      await resumeFor(owner);
      return result;
    }
    unawaited(
      ended()
          .catchError((Object error) {
            _log.w('[AmbientMusic] Side session end not observed: $error');
          })
          .whenComplete(() => resumeFor(owner)),
    );
    return result;
  }

  /// End of an embedded runtime's session, probed as [GameLaunchManager]
  /// probes embedded games. A failed probe counts as still active
  /// ([EmbeddedIOSSessionStatus]): frontend audio never comes back over a
  /// game on a guess.
  static Future<void> embeddedSessionEnded(String emulatorExe) async {
    while (await EmbeddedIOSSessionStatus.isActive(emulatorExe)) {
      await Future<void>.delayed(embeddedSessionProbe);
    }
  }

  /// End of an ARMSX2 session: its native session-end event, which also
  /// closes an ARMSX2 game in [GameLaunchManager].
  static Future<void> armsx2SessionEnded() =>
      Armsx2InternalBridge.sessionEvents.first;

  /// KartPad releases SDL's audio device; the shared engine is recreated.
  Future<void> beforeSharedEngineRestart() async {
    _sharedEngineRestarting = true;
    await _sync();
  }

  Future<void> afterSharedEngineRestart() async {
    _sharedEngineRestarting = false;
    await _sync();
  }

  /// Called by [MusicPlayerService] right before it releases the shared
  /// engine: the position is kept, the voice and source die with the engine.
  void handleEngineTearingDown() {
    final voice = _voice;
    if (voice != null && _backend.engineReady) {
      try {
        _resumePosition = _backend.position(voice);
        _resumeKey = _playingKey;
      } catch (_) {}
    }
    _engineEpoch++;
    _voice = null;
    _source = null;
    _playingKey = null;
  }

  Future<void> _fadeOutForLaunch() {
    // The gate is already blocked when this runs: the reconciliation below
    // fades the voice out and nothing restarts it until the game session
    // ends.
    return _sync();
  }

  void _onDependencyChanged() {
    if (_initialized) unawaited(_sync());
  }

  bool get _shouldPlay =>
      _initialized &&
      _enabled &&
      _frontendReady &&
      _appActive &&
      !_sharedEngineRestarting &&
      _suspensions.isEmpty &&
      !_gate.blocked &&
      !_sessionActive() &&
      !_userMusicPlaying();

  double get _targetGain => _userMusicDucked() ? 0.0 : gainFor(_volume);

  /// Reconciles the voice with the wanted state. Calls are serialized and
  /// coalesced: a request made while one is queued shares it.
  Future<void> _sync() {
    final pending = _pendingReconcile;
    if (pending != null) return pending;
    final next = _queue
        .then((_) {
          _pendingReconcile = null;
          return _reconcile();
        })
        .catchError((Object error) {
          _log.w('[AmbientMusic] Playback update failed: $error');
        });
    _pendingReconcile = next;
    _queue = next;
    return next;
  }

  Future<void> _reconcile() async {
    if (!_shouldPlay) {
      if (_voice != null) await _stopVoice();
      return;
    }
    final track = await _track();
    if (track == null) return;
    if (_voice != null && _playingKey != track.key) await _stopVoice();
    if (!_shouldPlay) return;
    if (_voice == null) {
      await _startVoice(track);
    } else {
      _applyGain();
    }
  }

  Future<_AmbientTrack?> _track() async {
    final custom = _musicPath;
    if (custom != null && custom.isNotEmpty && File(custom).existsSync()) {
      // Chosen files keep the decoding of earlier builds (in memory): the
      // streamed WAV/FLAC path of SoLoud 4.0.12 is not exact at loop seams.
      return _AmbientTrack(custom, custom, stream: false);
    }
    try {
      final bundled = _bundledPath ??= await _bundledTrackPath();
      return _AmbientTrack(bundled, bundled, stream: true);
    } catch (e) {
      _bundledPath = null;
      _log.w('[AmbientMusic] Bundled loop unavailable: $e');
      return null;
    }
  }

  Future<void> _startVoice(_AmbientTrack track) async {
    try {
      await _backend.prepareEngine();
      if (!_shouldPlay) return;
      final epoch = _engineEpoch;
      final source = await _backend.load(track.path, stream: track.stream);
      if (!_shouldPlay || epoch != _engineEpoch) {
        if (epoch == _engineEpoch) await _backend.dispose(source);
        return;
      }
      final resume = _resumeKey == track.key ? _resumePosition : Duration.zero;
      final gain = _targetGain;
      final voice = _backend.play(source, volume: 0, start: resume);
      _backend.fade(voice, gain, resume > Duration.zero ? resumeFadeIn : startFadeIn);
      _source = source;
      _voice = voice;
      _playingKey = track.key;
      _appliedGain = gain;
      _log.i('[AmbientMusic] Started (${resume.inMilliseconds} ms).');
    } catch (e) {
      _log.w('[AmbientMusic] Could not start: $e');
    }
  }

  Future<void> _stopVoice() async {
    final voice = _voice;
    final source = _source;
    if (voice == null) return;
    final epoch = _engineEpoch;
    final audible = _appActive && !_sharedEngineRestarting;
    if (audible && _backend.engineReady) {
      _backend.fade(voice, 0, fadeOut);
      _appliedGain = 0;
      await Future<void>.delayed(fadeOut + const Duration(milliseconds: 20));
      // The engine was released meanwhile: the teardown kept the position.
      if (epoch != _engineEpoch) return;
      if (_shouldPlay && _playingKey == _currentTrackKey) {
        // Wanted again during the fade (launch cancelled, switch flipped
        // back): fade back in instead of cutting.
        _applyGain(fade: startFadeIn);
        return;
      }
    }
    if (epoch == _engineEpoch && _backend.engineReady) {
      try {
        _resumePosition = _backend.position(voice);
        _resumeKey = _playingKey;
      } catch (_) {}
      try {
        await _backend.stop(voice);
      } catch (_) {}
      if (source != null) {
        try {
          await _backend.dispose(source);
        } catch (_) {}
      }
    }
    if (identical(_voice, voice)) {
      _voice = null;
      _source = null;
      _playingKey = null;
    }
  }

  String? get _currentTrackKey {
    final custom = _musicPath;
    if (custom != null && custom.isNotEmpty) return custom;
    return _bundledPath;
  }

  void _applyGain({Duration? fade}) {
    final voice = _voice;
    if (voice == null) return;
    final gain = _targetGain;
    if (gain == _appliedGain && fade == null) return;
    final ducking = (gain == 0) != (_appliedGain == 0);
    _appliedGain = gain;
    try {
      _backend.fade(voice, gain, fade ?? (ducking ? duckFade : volumeFade));
    } catch (_) {}
  }

  Future<void> _persist(
    Future<void> Function(SharedPreferences prefs) write,
  ) async {
    try {
      await write(await SharedPreferences.getInstance());
    } catch (e) {
      _log.w('[AmbientMusic] Could not save preference: $e');
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        _appActive = true;
        unawaited(_sync());
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        _appActive = false;
        unawaited(_sync());
      case AppLifecycleState.inactive:
        // Control Center, a system alert: the ambience keeps playing; iOS
        // interruptions are handled by SoLoud (device paused and resumed).
        break;
    }
  }

  /// Copies the bundled loop once into the caches (a file SoLoud can stream);
  /// the name carries the asset identity so a new asset gets a new copy.
  static Future<String> _prepareBundledTrack() async {
    final caches = await getApplicationCacheDirectory();
    final directory = Directory(p.join(caches.path, _bundledCacheDirectory));
    final file = File(
      p.join(
        directory.path,
        'once_upon_a_time_loop-$bundledTrackSha256Prefix.ogg',
      ),
    );
    if (await file.exists() && await file.length() == bundledTrackBytes) {
      return file.path;
    }
    await directory.create(recursive: true);
    final data = await rootBundle.load(bundledTrackAsset);
    final bytes = data.buffer.asUint8List(
      data.offsetInBytes,
      data.lengthInBytes,
    );
    if (bytes.length != bundledTrackBytes) {
      throw StateError('Unexpected bundled loop size ${bytes.length}');
    }
    final partial = File('${file.path}.part');
    await partial.writeAsBytes(bytes, flush: true);
    await partial.rename(file.path);
    // Copies of an earlier asset.
    await for (final entity in directory.list(followLinks: false)) {
      if (entity is File && !p.equals(entity.path, file.path)) {
        try {
          await entity.delete();
        } catch (_) {}
      }
    }
    return file.path;
  }

  static Future<Directory> _defaultCustomDirectory() async {
    final userDataPath = await ConfigService.getUserDataPath();
    return Directory(p.join(userDataPath, _directoryName));
  }

  Future<Directory> _musicDirectory() async {
    final directory = await _customDirectory();
    await directory.create(recursive: true);
    return directory;
  }

  bool _isSupportedPath(String value) {
    final extension = p.extension(value).toLowerCase().replaceFirst('.', '');
    return _allowedExtensions.contains(extension);
  }

  String _safeExtension(String value) {
    final extension = p.extension(value).toLowerCase();
    return _allowedExtensions.contains(extension.replaceFirst('.', ''))
        ? extension
        : '.mp3';
  }

  /// Migrates tracks selected by older builds from Application Support into
  /// the new user-data directory. If no preference exists, a supported file
  /// manually placed in `menu_music` is discovered automatically.
  Future<void> _migrateOrDiscoverMusic() async {
    final directory = await _musicDirectory();
    final existingPath = _musicPath;

    if (existingPath != null) {
      final source = File(existingPath);
      if (await source.exists() && _isSupportedPath(source.path)) {
        final normalizedDirectory = p.normalize(directory.absolute.path);
        final normalizedSource = p.normalize(source.absolute.path);
        final alreadyInDirectory = p.equals(
          normalizedDirectory,
          p.dirname(normalizedSource),
        );

        if (!alreadyInDirectory) {
          final oldPath = source.path;
          final oldParentName = p.basename(p.dirname(oldPath));
          await _storeFile(source, _musicName ?? p.basename(oldPath));

          // Older fork builds owned files inside an Application Support
          // `home_music` directory. Remove only that known legacy copy after a
          // successful migration; never delete arbitrary external source files.
          if (oldParentName == 'home_music') {
            try {
              final legacy = File(oldPath);
              if (await legacy.exists()) await legacy.delete();
            } catch (e) {
              _log.w('[AmbientMusic] Could not remove legacy music copy: $e');
            }
          }
        }
        return;
      }
    }

    File? discovered;
    await for (final entity in directory.list(followLinks: false)) {
      if (entity is! File || !_isSupportedPath(entity.path)) continue;
      if (discovered == null ||
          p.basename(entity.path).startsWith('main_menu_music.')) {
        discovered = entity;
      }
      if (p.basename(entity.path).startsWith('main_menu_music.')) break;
    }

    if (discovered != null) {
      _musicPath = discovered.path;
      _musicName = p.basename(discovered.path);
      _log.i('[AmbientMusic] Discovered menu music in user-data directory.');
    }
  }

  Future<bool> _pickAndStoreMusic() => StorageImportActivity.run(() async {
    try {
      final result = await FilePicker.pickFiles(
        type: FileType.custom,
        allowedExtensions: _allowedExtensions,
        allowMultiple: false,
      );
      final picked = result?.files.single;
      final sourcePath = picked?.path;
      if (picked == null || sourcePath == null || sourcePath.isEmpty) {
        return false;
      }

      final source = File(sourcePath);
      if (!await source.exists() || !_isSupportedPath(picked.name)) {
        return false;
      }

      await _storeFile(source, picked.name);
      _log.i('[AmbientMusic] Selected menu music: ${picked.name}');
      return true;
    } catch (e) {
      _log.w('[AmbientMusic] Could not import selected music: $e');
      return false;
    }
  });

  /// Copies [source] transactionally so a failed replacement never destroys
  /// the currently selected track.
  Future<void> _storeFile(File source, String displayName) async {
    final directory = await _musicDirectory();
    final extension = _safeExtension(
      displayName.isEmpty ? source.path : displayName,
    );
    final temporary = File(
      p.join(directory.path, 'main_menu_music.importing$extension'),
    );
    final destination = File(
      p.join(directory.path, 'main_menu_music$extension'),
    );

    if (await temporary.exists()) await temporary.delete();
    await source.copy(temporary.path);

    // The voice may be reading the file about to be replaced: it fades out
    // first and the next reconciliation starts the new file.
    final replacing = Object();
    _suspensions.add(replacing);
    try {
      await _sync();

      // Keep one app-owned track only. The completed temporary copy is
      // excluded until it is atomically renamed to the canonical destination.
      await for (final entity in directory.list(followLinks: false)) {
        if (entity is! File) continue;
        if (p.equals(entity.absolute.path, temporary.absolute.path)) continue;
        try {
          await entity.delete();
        } catch (_) {}
      }

      await temporary.rename(destination.path);
      _musicPath = destination.path;
      _musicName = displayName.isEmpty ? p.basename(source.path) : displayName;
    } finally {
      _suspensions.remove(replacing);
    }

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_pathPreferenceKey, destination.path);
    await prefs.setString(_namePreferenceKey, _musicName!);
  }
}
