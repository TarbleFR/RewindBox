import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';

import 'package:neostation/l10n/game_box_locale.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/screens/game_box/box_back_reader_screen.dart';
import 'package:neostation/services/game_box/game_box_fetcher.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/services/game_box/game_box_regions.dart';
import 'package:neostation/services/game_launch_manager.dart';
import 'package:neostation/services/game_service.dart' show GamepadNavigationManager;
import 'package:neostation/utils/gamepad_nav.dart';
import 'package:neostation/widgets/game_box/game_box_art_loader.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:neostation/widgets/game_box/game_box_language_picker.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';
import 'package:neostation/widgets/library_reduce_motion.dart';

/// Single launch through a box: set while a box opens or hands its game to
/// the launcher, so that repeated presses never start a second game.
class GameBoxLaunchGate {
  GameBoxLaunchGate._();
  static bool _busy = false;
  static bool get busy => _busy;
  static bool tryEnter() {
    if (_busy) return false;
    _busy = true;
    return true;
  }

  static void leave() => _busy = false;
}

/// What the inspector needs to know about the game it shows.
class GameBoxSubject {
  const GameBoxSubject({
    required this.game,
    required this.systemFolder,
    required this.fileProvider,
    this.systemId,
    this.appSystemId,
    this.frontFallback,
  });

  final GameModel game;
  final String systemFolder;
  final FileProvider fileProvider;

  /// NeoStation system id (box family).
  final String? systemId;

  /// Id the scraper maps to ScreenScraper (faces fetch).
  final String? appSystemId;
  final Widget Function()? frontFallback;
}

/// Full-screen viewer of a game box (docs/game-box-3d.md § 3).
///
/// Gestures here only move the box: the library behind cannot change its
/// selection while the viewer is open. "Play" opens the box, then hands the
/// game to the library's normal launch, which keeps every check (file, BIOS,
/// engine, JIT) and its dialogs.
class GameBoxInspector extends StatefulWidget {
  const GameBoxInspector({
    super.key,
    required this.subject,
    required this.onPlay,
    this.autoPlay = false,
  });

  final GameBoxSubject subject;

  /// The library's launch of the selected game.
  final VoidCallback onPlay;

  /// Opened by "Play" in the library: no inspection, the box opens at once.
  final bool autoPlay;

  /// Opens the viewer above the library.
  static Future<void> open(
    BuildContext context, {
    required GameBoxSubject subject,
    required VoidCallback onPlay,
    bool autoPlay = false,
  }) {
    final reduce = libraryReduceMotion(context);
    return Navigator.of(context, rootNavigator: true).push(PageRouteBuilder<void>(
      opaque: true,
      barrierDismissible: false,
      transitionDuration: Duration(milliseconds: reduce ? 120 : 220),
      reverseTransitionDuration: const Duration(milliseconds: 160),
      pageBuilder: (_, _, _) => GameBoxInspector(subject: subject, onPlay: onPlay, autoPlay: autoPlay),
      transitionsBuilder: (_, animation, _, child) => FadeTransition(opacity: animation, child: child),
    ));
  }

  @override
  State<GameBoxInspector> createState() => GameBoxInspectorState();
}

enum GameBoxInspectorPhase { inspecting, opening, launching }

@visibleForTesting
class GameBoxInspectorState extends State<GameBoxInspector> with TickerProviderStateMixin {
  late final GamepadNavigation _gamepadNav;
  late final AnimationController _poseAnim;
  late final AnimationController _spin;
  late final AnimationController _open;

  GameBoxInspectorPhase _phase = GameBoxInspectorPhase.inspecting;
  GameBoxInspectorPhase get phase => _phase;

  BoxPose _pose = BoxPose.rest;
  BoxPose get pose => _pose;
  BoxPose _from = BoxPose.rest;
  BoxPose _to = BoxPose.rest;
  BoxOpening _opening = BoxOpening.closed;
  double _outline = 0;
  double _finalZoom = 1;
  double _fade = 0;

  late GameBoxLocalMedia _media;
  late GameBoxArtSet _artSet;
  GameBoxProfile? _profile;
  Color? _edge;
  bool _detailed = false;

  String? _readingPref;
  String _readingLanguage = 'en';
  String? _backPath;
  GameBoxBackEdition? _backEdition;
  String? _downloadingLanguage;
  bool _editionFailed = false;
  bool _fetching = false;

  // Gesture bookkeeping.
  BoxPose _gestureStart = BoxPose.rest;
  Offset _gestureFocal = Offset.zero;
  bool _rotating = false;
  Size _viewport = Size.zero;

  GameModel get _game => widget.subject.game;

  @override
  void initState() {
    super.initState();
    _poseAnim = AnimationController(vsync: this, duration: const Duration(milliseconds: 420))
      ..addListener(() {
        setState(() => _pose = BoxPose.lerp(_from, _to, Curves.easeInOutCubic.transform(_poseAnim.value)));
      });
    _spin = AnimationController.unbounded(vsync: this)
      ..addListener(() => setState(() => _pose = _pose.copyWith(yaw: _spin.value)));
    _open = AnimationController(vsync: this, duration: const Duration(milliseconds: 1750));
    _loadMedia();
    _gamepadNav = GamepadNavigation(
      onNavigateLeft: () => _turn(math.pi / 4),
      onNavigateRight: () => _turn(-math.pi / 4),
      onNavigateUp: () => _tilt(-0.3),
      onNavigateDown: () => _tilt(0.3),
      onLeftBumper: () => _zoomBy(-0.5),
      onRightBumper: () => _zoomBy(0.5),
      onSelectItem: play,
      onBack: _close,
      onXButton: _read,
      onFavorite: () => _goTo(_facingBack ? BoxPose.front : BoxPose.back),
      onSettings: _chooseLanguage,
      onLeftStickClick: () => _goTo(BoxPose.rest),
      onSelectButton: _showOptions,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        'game_box_inspector',
        modal: true,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
      // Large decodes only once the viewer is shown.
      setState(() => _detailed = true);
      if (widget.autoPlay) play();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _resolveReadingLanguage();
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer('game_box_inspector');
    _gamepadNav.dispose();
    _poseAnim.dispose();
    _spin.dispose();
    _open.dispose();
    _artSet.evictDetailed();
    if (_phase != GameBoxInspectorPhase.inspecting) GameBoxLaunchGate.leave();
    super.dispose();
  }

  // Media -------------------------------------------------------------------

  void _loadMedia() {
    final store = GameBoxMediaStore(widget.subject.fileProvider);
    _media = store.read(_game, widget.subject.systemFolder);
    _artSet = GameBoxArtSet(media: _media, title: _game.name);
    GameBoxProfiles.load(widget.subject.systemId ?? _game.systemId).then((p) {
      if (mounted) setState(() => _profile = p.withFrontAspect(_artSet.frontAspect));
    });
    GameBoxArtSet.edgeColor(_media.front).then((c) {
      if (mounted) setState(() => _edge = c);
    });
    _selectBack();
  }

  String get _appLanguage {
    final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
    return GameBoxLocale.codeFor(locale);
  }

  Future<void> _resolveReadingLanguage() async {
    final pref = await GameBoxPreferences.readingLanguage();
    if (!mounted) return;
    setState(() {
      _readingPref = pref;
      _readingLanguage = pref ?? _appLanguage;
    });
    _selectBack();
  }

  /// The back shown: a scan published for the reading language when the
  /// manifest lists one (downloaded once, on demand), else the default back.
  Future<void> _selectBack() async {
    final manifest = _media.manifest;
    final edition = manifest == null
        ? null
        : GameBoxMediaSelection.backForLanguage(manifest, _readingLanguage, gameRegions: _gameRegions);
    setState(() {
      _editionFailed = false;
      _backEdition = edition;
      _backPath = edition == null ? _media.back : (_media.backEditionFile(edition.entry) ?? _media.back);
    });
    if (edition == null || _media.backEditionFile(edition.entry) != null) return;
    final language = _readingLanguage;
    setState(() => _downloadingLanguage = language);
    final path = await GameBoxMediaFetcher.ensureBackEdition(
      game: _game,
      systemFolder: widget.subject.systemFolder,
      fileProvider: widget.subject.fileProvider,
      edition: edition,
    );
    if (!mounted || language != _readingLanguage) return;
    setState(() {
      _downloadingLanguage = null;
      if (path != null) {
        _media = GameBoxMediaStore(widget.subject.fileProvider).read(_game, widget.subject.systemFolder);
        _artSet.evictDetailed();
        _artSet = GameBoxArtSet(media: _media, title: _game.name);
        _backPath = path;
      } else {
        _editionFailed = true;
        _backEdition = null;
        _backPath = _media.back;
      }
    });
  }

  List<String> get _gameRegions {
    final m = _media.manifest;
    if (m != null && m.gameRegions.isNotEmpty) return m.gameRegions;
    return GameBoxRegions.fromFileName(_game.romname);
  }

  String? get _gameRegionSource {
    final m = _media.manifest;
    if (m != null && m.gameRegions.isNotEmpty) return m.gameRegionSource;
    return GameBoxRegions.fromFileName(_game.romname).isEmpty ? null : 'filename';
  }

  /// Region of the back shown.
  String? get _backRegion {
    final e = _backEdition;
    if (e != null) return e.regions.first;
    return _media.manifest?.defaultEntry(GameBoxMediaKind.back)?.region;
  }

  // Motion ------------------------------------------------------------------

  bool get _reduceMotion => libraryReduceMotion(context);

  bool get _facingBack {
    final yaw = _pose.yaw % (2 * math.pi);
    return yaw > math.pi / 2 && yaw < 3 * math.pi / 2;
  }

  void _stopMotion() {
    _poseAnim.stop();
    _spin.stop();
  }

  void _goTo(BoxPose target) {
    if (_phase != GameBoxInspectorPhase.inspecting) return;
    _stopMotion();
    // Keep the yaw on the same turn so "Front" never spins several times.
    final aligned = target.copyWith(yaw: _pose.yaw + BoxPose.shortestAngle(_pose.yaw, target.yaw));
    if (_reduceMotion) {
      setState(() => _pose = aligned);
      return;
    }
    _from = _pose;
    _to = aligned;
    _poseAnim.forward(from: 0);
  }

  void _turn(double delta) => _goTo(_pose.copyWith(yaw: _pose.yaw + delta, perspective: 1));

  void _tilt(double delta) =>
      _goTo(_pose.copyWith(pitch: (_pose.pitch + delta).clamp(-BoxPose.maxPitch, BoxPose.maxPitch)));

  void _zoomBy(double delta) {
    final z = (_pose.zoom + delta).clamp(BoxPose.minZoom, BoxPose.maxZoom).toDouble();
    _goTo(_pose.copyWith(zoom: z, panX: z == 1 ? 0 : _pose.panX, panY: z == 1 ? 0 : _pose.panY));
  }

  void _onScaleStart(ScaleStartDetails d) {
    if (_phase != GameBoxInspectorPhase.inspecting) return;
    _stopMotion();
    _gestureStart = _pose;
    _gestureFocal = d.focalPoint;
    _rotating = d.pointerCount < 2 && _pose.zoom <= 1.05;
  }

  void _onScaleUpdate(ScaleUpdateDetails d) {
    if (_phase != GameBoxInspectorPhase.inspecting) return;
    final delta = d.focalPoint - _gestureFocal;
    final width = math.max(200.0, _viewport.width);
    if (d.pointerCount >= 2 || !_rotating) {
      _rotating = false;
      final zoom = (_gestureStart.zoom * d.scale).clamp(BoxPose.minZoom, BoxPose.maxZoom).toDouble();
      final limitX = _viewport.width * (zoom - 1) * 0.6;
      final limitY = _viewport.height * (zoom - 1) * 0.6;
      setState(() => _pose = _pose.copyWith(
            zoom: zoom,
            panX: zoom <= 1 ? 0 : (_gestureStart.panX + delta.dx).clamp(-limitX, limitX).toDouble(),
            panY: zoom <= 1 ? 0 : (_gestureStart.panY + delta.dy).clamp(-limitY, limitY).toDouble(),
          ));
      return;
    }
    // One finger at zoom 1: turn the box (free yaw, bounded pitch). Dragging
    // right turns the front to the right, as on a turntable.
    final k = 3.4 / width;
    setState(() => _pose = _pose.copyWith(
          yaw: _gestureStart.yaw - delta.dx * k,
          pitch: (_gestureStart.pitch + delta.dy * k).clamp(-BoxPose.maxPitch, BoxPose.maxPitch).toDouble(),
          perspective: 1,
        ));
  }

  void _onScaleEnd(ScaleEndDetails d) {
    if (_phase != GameBoxInspectorPhase.inspecting || !_rotating || _reduceMotion) return;
    final width = math.max(200.0, _viewport.width);
    final v = -d.velocity.pixelsPerSecond.dx * 3.4 / width;
    if (v.abs() < 0.4) return;
    // Inertia that stops by itself: the box stays still afterwards.
    _spin.animateWith(FrictionSimulation(0.12, _pose.yaw, v));
  }

  void _onDoubleTap() {
    if (_phase != GameBoxInspectorPhase.inspecting) return;
    _goTo(_pose.zoom > 1.05 ? _pose.copyWith(zoom: 1, panX: 0, panY: 0) : _pose.copyWith(zoom: 2.2));
  }

  // Actions -----------------------------------------------------------------

  void _close() {
    if (_phase != GameBoxInspectorPhase.inspecting) return;
    Navigator.of(context).maybePop();
  }

  Future<void> _chooseLanguage() async {
    if (_phase != GameBoxInspectorPhase.inspecting) return;
    final scanLanguages = <String>{
      for (final e in _media.manifest?.backEditions() ?? const <GameBoxBackEdition>[]) ...e.languages,
    };
    final chosen = await showGameBoxLanguagePicker(
      context,
      current: _readingLanguage,
      followingApp: _readingPref == null,
      appLanguage: _appLanguage,
      scanLanguages: scanLanguages,
    );
    if (chosen == null || !mounted) return;
    final pref = chosen == gameBoxFollowApp ? null : chosen;
    await GameBoxPreferences.setReadingLanguage(pref);
    if (!mounted) return;
    setState(() {
      _readingPref = pref;
      _readingLanguage = pref ?? _appLanguage;
    });
    await _selectBack();
    if (mounted && _media.back != null) _goTo(BoxPose.back);
  }

  void _read() {
    if (_phase != GameBoxInspectorPhase.inspecting) return;
    final edition = _backEdition;
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => BoxBackReaderScreen(
        title: _game.name,
        scanPath: _backPath,
        readingLanguage: _readingLanguage,
        scanRegion: _backRegion,
        publishedLanguage: edition == null ? null : _readingLanguage,
        summaryFor: (code) => _game.getDescriptionForLanguage(code == 'ja' ? 'jp' : code),
        onReadingLanguageChanged: (code) {
          GameBoxPreferences.setReadingLanguage(code);
          if (!mounted) return;
          setState(() {
            _readingPref = code;
            _readingLanguage = code;
          });
          _selectBack();
        },
      ),
    ));
  }

  Future<void> _fetchFaces() async {
    final appSystemId = widget.subject.appSystemId;
    if (_fetching || appSystemId == null) return;
    setState(() => _fetching = true);
    final messenger = ScaffoldMessenger.maybeOf(context);
    final result = await GameBoxMediaFetcher.fetch(
      game: _game,
      appSystemId: appSystemId,
      systemFolder: widget.subject.systemFolder,
      fileProvider: widget.subject.fileProvider,
    );
    if (!mounted) return;
    setState(() {
      _fetching = false;
      _artSet.evictDetailed();
      for (final path in [_media.back, _media.spine, _media.support]) {
        if (path != null) GameBoxImageSize.evict(path);
      }
      _media = GameBoxMediaStore(widget.subject.fileProvider).read(_game, widget.subject.systemFolder);
      _artSet = GameBoxArtSet(media: _media, title: _game.name);
    });
    // Replaced files keep their path: drop their decodes.
    imageCache.clear();
    imageCache.clearLiveImages();
    await _selectBack();
    if (!mounted) return;
    final key = switch (result.status) {
      GameBoxFetchStatus.updated => GameBoxLocale.fetchDone,
      GameBoxFetchStatus.nothingNew => GameBoxLocale.fetchNothing,
      GameBoxFetchStatus.needsLogin => GameBoxLocale.fetchNeedsLogin,
      GameBoxFetchStatus.systemNotMapped => GameBoxLocale.fetchSystemNotMapped,
      GameBoxFetchStatus.notFound => GameBoxLocale.fetchNotFound,
      GameBoxFetchStatus.quota => GameBoxLocale.fetchQuota,
      GameBoxFetchStatus.failed => GameBoxLocale.fetchFailed,
    };
    messenger?.showSnackBar(SnackBar(content: Text(GameBoxLocale.text(context, key))));
  }

  Future<void> _showOptions() async {
    if (_phase != GameBoxInspectorPhase.inspecting) return;
    var animation = await GameBoxPreferences.openingAnimation();
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setSheet) {
        return SafeArea(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            SwitchListTile(
              value: animation,
              title: Text(GameBoxLocale.text(ctx, GameBoxLocale.openingAnimation)),
              subtitle: Text(GameBoxLocale.text(ctx, GameBoxLocale.openingAnimationDesc)),
              onChanged: (v) {
                setSheet(() => animation = v);
                GameBoxPreferences.setOpeningAnimation(v);
              },
            ),
            if (widget.subject.appSystemId != null)
              ListTile(
                leading: const Icon(Icons.download_outlined),
                title: Text(GameBoxLocale.text(ctx, GameBoxLocale.fetchFaces)),
                subtitle: Text(GameBoxLocale.text(ctx, GameBoxLocale.fetchFacesDesc)),
                onTap: () {
                  Navigator.of(ctx).pop();
                  _fetchFaces();
                },
              ),
          ]),
        );
      }),
    );
  }

  // Opening and launch ------------------------------------------------------

  /// Canonical pose for opening: front toward the viewer, a little of the
  /// hinge side; looking from above into a cardboard box.
  BoxPose get _openingPose => _profile?.caseKind == GameBoxCaseKind.cardboard
      ? const BoxPose(yaw: -0.2, pitch: 0.34)
      : const BoxPose(yaw: -0.22, pitch: 0.1);

  /// Opens the box, then starts the game through the library. Never twice.
  Future<void> play() async {
    if (_phase != GameBoxInspectorPhase.inspecting) return;
    if (!GameBoxLaunchGate.tryEnter()) return;
    _stopMotion();
    setState(() => _phase = GameBoxInspectorPhase.opening);
    var animate = true;
    try {
      animate = await GameBoxPreferences.openingAnimation();
    } catch (_) {}
    if (!mounted) return;
    final reduce = _reduceMotion;
    try {
      if (!animate) {
        await _fadeOut(const Duration(milliseconds: 140));
      } else if (reduce) {
        await _reducedOpening();
      } else {
        await _animatedOpening().timeout(const Duration(seconds: 4));
      }
    } catch (_) {
      // A rendering problem or a stuck animation never blocks the game.
    }
    if (!mounted) {
      GameBoxLaunchGate.leave();
      return;
    }
    _launch();
  }

  Future<void> _fadeOut(Duration d) async {
    final c = AnimationController(vsync: this, duration: d);
    c.addListener(() => setState(() => _fade = c.value));
    try {
      await c.forward().orCancel;
    } finally {
      c.dispose();
    }
  }

  /// Reduce Motion: no rotation or movement; the opened box appears by a
  /// cross-fade, then the screen fades.
  Future<void> _reducedOpening() async {
    setState(() {
      _pose = _openingPose;
      _opening = const BoxOpening(lid: 1, support: 1);
      _outline = 1;
    });
    await Future<void>.delayed(const Duration(milliseconds: 260));
    if (!mounted) return;
    await _fadeOut(const Duration(milliseconds: 200));
  }

  Future<void> _animatedOpening() async {
    final start = _pose;
    final target = _openingPose.copyWith(
      yaw: start.yaw + BoxPose.shortestAngle(start.yaw, _openingPose.yaw),
    );
    final opens = _profile?.opens ?? false;
    final lifts = _profile != null && GameBoxModel(_profile!).supportLifts;
    double seg(double t, double a, double b) => ((t - a) / (b - a)).clamp(0.0, 1.0).toDouble();
    void tick() {
      final t = _open.value;
      final align = Curves.easeInOutCubic.transform(seg(t, 0.0, 0.2));
      final lid = opens ? seg(t, 0.16, 0.56) : 0.0;
      final support = opens ? Curves.easeOutCubic.transform(seg(t, 0.56, lifts ? 0.8 : 0.66)) : 0.0;
      final last = Curves.easeInCubic.transform(seg(t, 0.8, 1.0));
      setState(() {
        _pose = BoxPose.lerp(start, target, align);
        _opening = BoxOpening(lid: lid, support: support);
        _outline = opens ? Curves.easeInOut.transform(seg(t, 0.12, 0.6)) : 0;
        _finalZoom = 1 + 0.65 * last;
        _fade = last;
      });
    }
    _open.addListener(tick);
    try {
      await _open.forward(from: 0).orCancel;
    } finally {
      _open.removeListener(tick);
    }
  }

  /// Hands the game to the library and leaves once its launch session has
  /// begun (its dialog is then above this viewer). If the library refuses to
  /// start (no session within a few seconds), the box closes again.
  void _launch() {
    setState(() {
      _phase = GameBoxInspectorPhase.launching;
      _fade = 1;
    });
    // Large decodes are released before the emulator starts.
    _artSet.evictDetailed();
    final manager = GameLaunchManager();
    final started = Completer<bool>();
    void listener() {
      if (manager.phase == GameLaunchPhase.launching && !started.isCompleted) started.complete(true);
    }
    manager.addListener(listener);
    try {
      widget.onPlay();
    } catch (_) {
      if (!started.isCompleted) started.complete(false);
    }
    started.future.timeout(const Duration(seconds: 6), onTimeout: () => false).then((ok) async {
      manager.removeListener(listener);
      if (!mounted) {
        GameBoxLaunchGate.leave();
        return;
      }
      if (ok) {
        await WidgetsBinding.instance.endOfFrame;
        await WidgetsBinding.instance.endOfFrame;
        if (!mounted) return;
        GameBoxLaunchGate.leave();
        final route = ModalRoute.of(context);
        if (route != null && route.isActive) route.navigator?.removeRoute(route);
        return;
      }
      GameBoxLaunchGate.leave();
      if (widget.autoPlay) {
        final route = ModalRoute.of(context);
        if (route != null && route.isActive) route.navigator?.removeRoute(route);
        return;
      }
      setState(() {
        _phase = GameBoxInspectorPhase.inspecting;
        _opening = BoxOpening.closed;
        _outline = 0;
        _finalZoom = 1;
        _fade = 0;
        _pose = BoxPose.rest;
      });
    });
  }

  // Build -------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final background = Color.lerp(theme.colorScheme.surface, Colors.black, 0.55)!;
    final controlsVisible = !widget.autoPlay && _phase == GameBoxInspectorPhase.inspecting;
    return PopScope(
      canPop: _phase == GameBoxInspectorPhase.inspecting,
      child: Scaffold(
        backgroundColor: background,
        body: Stack(children: [
          SafeArea(
            child: LayoutBuilder(builder: (context, c) {
              final landscape = c.maxWidth > c.maxHeight * 1.1;
              final box = _boxArea();
              final panel = AnimatedOpacity(
                opacity: controlsVisible ? 1 : 0,
                duration: const Duration(milliseconds: 160),
                child: IgnorePointer(ignoring: !controlsVisible, child: _panel(theme, landscape)),
              );
              if (landscape) {
                return Row(children: [
                  Expanded(child: box),
                  SizedBox(width: math.min(360, c.maxWidth * 0.4), child: panel),
                ]);
              }
              return Column(children: [
                Expanded(child: box),
                panel,
              ]);
            }),
          ),
          if (_fade > 0)
            Positioned.fill(
              child: IgnorePointer(child: ColoredBox(color: Colors.black.withValues(alpha: _fade.clamp(0.0, 1.0)))),
            ),
        ]),
      ),
    );
  }

  Widget _boxArea() {
    final profile = _profile;
    return LayoutBuilder(builder: (context, c) {
      _viewport = c.biggest;
      if (profile == null) return const Center(child: CircularProgressIndicator());
      final model = GameBoxModel(profile);
      final readingPose = _facingBack && _pose.zoom <= 1.05 && _phase == GameBoxInspectorPhase.inspecting;
      final art = _artSet.art(
        detailed: _detailed,
        backPath: _backPath,
        edgeColor: _edge,
        frontFallback: widget.subject.frontFallback?.call(),
        backUnavailable: GameBoxLocale.text(context, GameBoxLocale.backUnavailable),
        gloss: !_facingBack && _pose.zoom <= 1.1,
      );
      final scene = GameBoxScene(
        model: model,
        art: art,
        pose: readingPose ? _pose.copyWith(perspective: math.min(_pose.perspective, 0.35)) : _pose,
        opening: _opening,
        outlineBlend: _outline,
        groundShadow: true,
      );
      Widget zoomed = scene;
      if (_finalZoom > 1.001) {
        final focus = BoxProjector(
              model: model, viewport: c.biggest, pose: _pose, opening: _opening, outlineBlend: _outline,
            ).supportCenter ??
            c.biggest.center(Offset.zero);
        zoomed = Transform(
          transform: Matrix4.identity()
            ..translateByDouble(focus.dx, focus.dy, 0, 1)
            ..scaleByDouble(_finalZoom, _finalZoom, 1, 1)
            ..translateByDouble(-focus.dx, -focus.dy, 0, 1),
          child: scene,
        );
      }
      final face = _faceName(context);
      return Semantics(
        label: GameBoxLocale.format(context, GameBoxLocale.semanticsBox, {'title': _game.name, 'face': face}),
        hint: GameBoxLocale.text(context, GameBoxLocale.dragHint),
        image: true,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onScaleStart: _onScaleStart,
          onScaleUpdate: _onScaleUpdate,
          onScaleEnd: _onScaleEnd,
          onDoubleTap: _onDoubleTap,
          child: ClipRect(child: zoomed),
        ),
      );
    });
  }

  String _faceName(BuildContext context) {
    final profile = _profile;
    if (profile == null) return GameBoxLocale.text(context, GameBoxLocale.faceFront);
    final surface = BoxProjector(model: GameBoxModel(profile), viewport: const Size(100, 100), pose: _pose).facingSurface;
    final key = switch (surface) {
      BoxSurface.back => GameBoxLocale.faceBack,
      BoxSurface.spine => GameBoxLocale.faceSpine,
      BoxSurface.top => GameBoxLocale.faceTop,
      BoxSurface.bottom => GameBoxLocale.faceBottom,
      BoxSurface.edge || BoxSurface.spineRight => GameBoxLocale.faceSide,
      _ => GameBoxLocale.faceFront,
    };
    return GameBoxLocale.text(context, key);
  }

  Widget _panel(ThemeData theme, bool landscape) {
    final info = _infoLines(context);
    final language = _readingLanguage;
    final children = <Widget>[
      Row(children: [
        IconButton(
          tooltip: GameBoxLocale.text(context, GameBoxLocale.close),
          onPressed: _close,
          icon: const Icon(Icons.close),
        ),
        Expanded(
          child: Text(
            _game.name,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.titleMedium,
          ),
        ),
        IconButton(
          tooltip: GameBoxLocale.text(context, GameBoxLocale.options),
          onPressed: _showOptions,
          icon: const Icon(Icons.tune),
        ),
      ]),
      for (final line in info)
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 2, 12, 2),
          child: Text(line, style: theme.textTheme.bodySmall),
        ),
      if (_downloadingLanguage != null)
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 6, 12, 2),
          child: Row(children: [
            const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                GameBoxLocale.format(context, GameBoxLocale.downloadingEdition,
                    {'language': GameBoxLocale.languageName(context, _downloadingLanguage!)}),
                style: theme.textTheme.bodySmall,
              ),
            ),
          ]),
        ),
      if (_fetching)
        const Padding(padding: EdgeInsets.fromLTRB(12, 6, 12, 2), child: LinearProgressIndicator()),
      const SizedBox(height: 8),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Wrap(
          spacing: 8,
          runSpacing: 8,
          alignment: WrapAlignment.center,
          children: [
            OutlinedButton.icon(
              onPressed: () => _goTo(BoxPose.front),
              icon: const Icon(Icons.flip_to_front),
              label: Text(GameBoxLocale.text(context, GameBoxLocale.front)),
            ),
            OutlinedButton.icon(
              onPressed: () => _goTo(BoxPose.back),
              icon: const Icon(Icons.flip_to_back),
              label: Text(GameBoxLocale.text(context, GameBoxLocale.back)),
            ),
            OutlinedButton.icon(
              onPressed: () => _goTo(BoxPose.rest),
              icon: const Icon(Icons.threed_rotation),
              label: Text(GameBoxLocale.text(context, GameBoxLocale.reset)),
            ),
            Tooltip(
              message: GameBoxLocale.text(context, GameBoxLocale.readingLanguage),
              child: OutlinedButton.icon(
                onPressed: _chooseLanguage,
                icon: const Icon(Icons.translate),
                label: Text(GameBoxLocale.languageName(context, language)),
              ),
            ),
            if (widget.subject.appSystemId != null && _missingFaces)
              OutlinedButton.icon(
                onPressed: _fetching ? null : _fetchFaces,
                icon: const Icon(Icons.download_outlined),
                label: Text(GameBoxLocale.text(context, GameBoxLocale.fetchFaces)),
              ),
            FilledButton.tonalIcon(
              onPressed: _read,
              icon: const Icon(Icons.menu_book_outlined),
              label: Text(GameBoxLocale.text(context, GameBoxLocale.read)),
            ),
            FilledButton.icon(
              onPressed: play,
              icon: const Icon(Icons.play_arrow_rounded),
              label: Text(GameBoxLocale.text(context, GameBoxLocale.play)),
            ),
          ],
        ),
      ),
      const SizedBox(height: 12),
    ];
    final column = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: children,
    );
    return landscape ? SingleChildScrollView(child: column) : column;
  }

  bool get _missingFaces =>
      _media.manifest == null || _media.back == null || _media.spine == null || _media.support == null;

  List<String> _infoLines(BuildContext context) {
    final out = <String>[];
    final region = _backRegion;
    final regions = _gameRegions;
    final edition = _backEdition;
    if (_backPath != null) {
      if (edition != null) {
        out.add(GameBoxLocale.format(context, GameBoxLocale.scanInLanguage,
            {'language': GameBoxLocale.languageName(context, _readingLanguage)}));
      }
      if (region != null) {
        final isOther = regions.isNotEmpty && !(edition?.regions ?? [region]).any(regions.contains);
        out.add(isOther
            ? GameBoxLocale.format(context, GameBoxLocale.otherEdition, {
                'region': GameBoxLocale.regionName(context, region),
                'game': regions.map((r) => GameBoxLocale.regionName(context, r)).join(', '),
              })
            : GameBoxLocale.format(context, GameBoxLocale.edition, {'region': GameBoxLocale.regionName(context, region)}));
      }
      // Only a known edition tells the language of its print.
      final presumed = region == null ? null : GameBoxRegions.languageOfRegion(region);
      if (edition == null && presumed != null && presumed != _readingLanguage) {
        out.add(GameBoxLocale.format(context, GameBoxLocale.noScanInLanguage,
            {'language': GameBoxLocale.languageName(context, _readingLanguage)}));
      }
    } else {
      out.add(GameBoxLocale.text(context, GameBoxLocale.backUnavailable));
    }
    if (_editionFailed) out.add(GameBoxLocale.text(context, GameBoxLocale.editionFailed));
    if (regions.isEmpty) {
      out.add(GameBoxLocale.text(context, GameBoxLocale.gameRegionUnknown));
    } else {
      final names = regions.map((r) => GameBoxLocale.regionName(context, r)).join(', ');
      out.add(_gameRegionSource == 'filename'
          ? GameBoxLocale.format(context, GameBoxLocale.gameRegionFromName, {'region': names})
          : GameBoxLocale.format(context, GameBoxLocale.gameRegion, {'region': names}));
    }
    if (_media.spine == null) out.add(GameBoxLocale.text(context, GameBoxLocale.spineUnavailable));
    final profile = _profile;
    if (profile != null && profile.opens && _media.support == null &&
        profile.support != GameBoxSupportKind.none &&
        profile.support != GameBoxSupportKind.floppy &&
        profile.support != GameBoxSupportKind.cassette) {
      final kind = switch (profile.support) {
        GameBoxSupportKind.disc || GameBoxSupportKind.miniDisc || GameBoxSupportKind.umd => GameBoxLocale.supportDisc,
        GameBoxSupportKind.card => GameBoxLocale.supportCard,
        _ => GameBoxLocale.supportCartridge,
      };
      out.add(GameBoxLocale.format(context, GameBoxLocale.supportUnavailable,
          {'support': GameBoxLocale.text(context, kind)}));
    }
    if (_media.manifest != null) out.add(GameBoxLocale.text(context, GameBoxLocale.source));
    return out;
  }
}
