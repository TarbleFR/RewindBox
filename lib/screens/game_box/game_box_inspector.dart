import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';

import 'package:flutter_localization/flutter_localization.dart';

import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/game_box_locale.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/screens/game_box/box_back_reader_screen.dart';
import 'package:neostation/screens/game_box/game_box_scan_viewer.dart';
import 'package:neostation/screens/game_screen/game_manual_reader_screen.dart';
import 'package:neostation/services/game_box/game_box_fetcher.dart';
import 'package:neostation/services/game_box/game_box_manual.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/services/game_box/game_box_regions.dart';
import 'package:neostation/services/game_box/game_box_sharp_scan.dart';
import 'package:neostation/services/game_launch_manager.dart';
import 'package:neostation/services/game_manual_service.dart';
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
    this.system,
    this.isAllMode = false,
  });

  final GameModel game;

  /// Media folder of the game (box faces and manual).
  final String systemFolder;
  final FileProvider fileProvider;

  /// The library's system, to download a missing manual through the same
  /// path as Game Settings › Manual (null: no download offered).
  final SystemModel? system;

  /// The library gathers several consoles (All, Favorites).
  final bool isAllMode;

  /// NeoStation system id (box family).
  final String? systemId;

  /// Id the scraper maps to ScreenScraper (faces fetch).
  final String? appSystemId;
  final Widget Function()? frontFallback;
}

/// Full-screen viewer of a game box (docs/game-box-3d.md § 3 and § 11).
///
/// Gestures here only move the box: the library behind cannot change its
/// selection while the viewer is open. "Back" (top left, B) goes up one level:
/// manual → open box → closed box → library. "Open the box" shows the inside
/// without starting anything; the game's manual, when its PDF is on the
/// device, lies there and opens in NeoStation's manual reader. "Play" opens
/// the box, then hands the game to the library's normal launch, which keeps
/// every check (file, BIOS, engine, JIT) and its dialogs.
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

  /// The manual reader opened from the box: NeoStation's own PDF reader on
  /// the same file as Game Settings › Manual. Replaced in tests only.
  @visibleForTesting
  static Widget Function(String manualPath, String gameTitle) manualReader =
      (manualPath, gameTitle) => GameManualReaderScreen(manualPath: manualPath, gameTitle: gameTitle);

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

/// The inside of the box while it is inspected (not while it opens to play).
enum GameBoxInsideState {
  closed,

  /// Opening or closing for inspection.
  moving,
  open,

  /// The manual is being taken out, read, or put back.
  taking,
}

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

  // The back made for the size it is shown at (docs/game-box-3d.md § 12).
  late final GameBoxSharpTexture _sharp = GameBoxSharpTexture(onChanged: () {
    if (mounted) setState(() {});
  });
  bool _sharpText = true;
  bool _sharpScheduled = false;
  bool _gesture = false;

  String? _readingPref;
  String _readingLanguage = 'en';
  String? _backPath;
  GameBoxBackEdition? _backEdition;
  String? _downloadingLanguage;
  bool _editionFailed = false;
  bool _fetching = false;

  // Inside of the box (docs/game-box-3d.md § 11).
  GameBoxInsideState _inside = GameBoxInsideState.closed;
  GameBoxInsideState get inside => _inside;
  BoxPose _poseBeforeOpen = BoxPose.rest;
  double _openYaw = 0;
  String? _manualPath;
  String? get manualPath => _manualPath;
  bool _manualChecked = false;
  GameBoxManualPage? _manualPage;
  bool _manualPageLoading = false;
  bool _downloadingManual = false;
  double _manualProgress = 0;
  bool _readingManual = false;
  final Set<AnimationController> _transient = {};

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
    GameBoxPreferences.sharpText().then((v) {
      if (mounted && v != _sharpText) setState(() => _sharpText = v);
    });
    _gamepadNav = GamepadNavigation(
      onNavigateLeft: () => _turn(_isOpen ? 0.2 : math.pi / 4),
      onNavigateRight: () => _turn(_isOpen ? -0.2 : -math.pi / 4),
      onNavigateUp: () => _tilt(_isOpen ? -0.15 : -0.3),
      onNavigateDown: () => _tilt(_isOpen ? 0.15 : 0.3),
      onLeftBumper: () => _zoomBy(-0.5),
      onRightBumper: () => _zoomBy(0.5),
      onSelectItem: play,
      onBack: back,
      // X reads: the back of the closed box, the manual of the open one.
      onXButton: () {
        if (_inside == GameBoxInsideState.closed) {
          _read();
        } else if (_isOpen && _manualPath != null) {
          takeManual();
        } else if (_isOpen && _canDownloadManual) {
          _downloadManual();
        }
      },
      onFavorite: () {
        if (_inside == GameBoxInsideState.closed) _goTo(_facingBack ? BoxPose.front : BoxPose.back);
      },
      onSettings: _chooseLanguage,
      onLeftStickClick: () => _isOpen ? _recenter() : _goTo(BoxPose.rest),
      onRightStickClick: () => _isOpen ? closeBox() : openBox(),
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
    _checkManual();
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
    for (final c in _transient) {
      c.dispose();
    }
    _transient.clear();
    _manualPage?.dispose();
    _artSet.evictDetailed();
    _sharp.dispose();
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
        _sharp.clear();
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

  /// Gestures and buttons move the box only while it is still: closed, or
  /// open and not taking its manual.
  bool get _interactive =>
      _phase == GameBoxInspectorPhase.inspecting &&
      (_inside == GameBoxInsideState.closed || _inside == GameBoxInsideState.open);

  bool get _isOpen => _phase == GameBoxInspectorPhase.inspecting && _inside == GameBoxInsideState.open;

  /// An open box is looked into from the front: it turns and tilts a little,
  /// never round to its back.
  BoxPose _clampOpen(BoxPose p) {
    if (_inside != GameBoxInsideState.open) return p;
    return p.copyWith(
      yaw: p.yaw.clamp(_openYaw - 0.5, _openYaw + 0.45).toDouble(),
      pitch: p.pitch.clamp(-0.12, 0.9).toDouble(),
      perspective: 1,
    );
  }

  void _goTo(BoxPose target) {
    if (!_interactive) return;
    _stopMotion();
    // Keep the yaw on the same turn so "Front" never spins several times.
    final aligned = _clampOpen(target.copyWith(yaw: _pose.yaw + BoxPose.shortestAngle(_pose.yaw, target.yaw)));
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

  void _recenter() => _goTo(_pose.copyWith(zoom: 1, panX: 0, panY: 0));

  bool get _zoomed => _pose.zoom > 1.05 || _pose.panX.abs() > 1 || _pose.panY.abs() > 1;

  void _onScaleStart(ScaleStartDetails d) {
    if (!_interactive) return;
    _stopMotion();
    _gesture = true;
    _gestureStart = _pose;
    _gestureFocal = d.focalPoint;
    _rotating = d.pointerCount < 2 && _pose.zoom <= 1.05;
  }

  void _onScaleUpdate(ScaleUpdateDetails d) {
    if (!_interactive) return;
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
    setState(() => _pose = _clampOpen(_pose.copyWith(
          yaw: _gestureStart.yaw - delta.dx * k,
          pitch: (_gestureStart.pitch + delta.dy * k).clamp(-BoxPose.maxPitch, BoxPose.maxPitch).toDouble(),
          perspective: 1,
        )));
  }

  void _onScaleEnd(ScaleEndDetails d) {
    // The box is still again: the back can be made for its new size.
    if (_gesture) setState(() => _gesture = false);
    if (!_interactive || _inside != GameBoxInsideState.closed || !_rotating || _reduceMotion) return;
    final width = math.max(200.0, _viewport.width);
    final v = -d.velocity.pixelsPerSecond.dx * 3.4 / width;
    if (v.abs() < 0.4) return;
    // Inertia that stops by itself: the box stays still afterwards.
    _spin.animateWith(FrictionSimulation(0.12, _pose.yaw, v));
  }

  void _onDoubleTap() {
    if (!_interactive) return;
    _goTo(_pose.zoom > 1.05 ? _pose.copyWith(zoom: 1, panX: 0, panY: 0) : _pose.copyWith(zoom: 2.2));
  }

  /// A tap on the manual lying in the open box takes it.
  void _onTapUp(TapUpDetails d) {
    if (!_isOpen || _manualPath == null) return;
    final projector = _projector(_viewport);
    if (projector != null && projector.hitsBooklet(d.localPosition)) takeManual();
  }

  // Actions -----------------------------------------------------------------

  /// One level up: an open box closes, a closed box returns to the library
  /// (its view, selection and scroll position are kept underneath).
  void back() {
    if (_phase != GameBoxInspectorPhase.inspecting) return;
    switch (_inside) {
      case GameBoxInsideState.open:
        closeBox();
      case GameBoxInsideState.closed:
        Navigator.of(context).maybePop();
      case GameBoxInsideState.moving:
      case GameBoxInsideState.taking:
        return;
    }
  }

  Future<void> _chooseLanguage() async {
    if (!_interactive || _inside != GameBoxInsideState.closed) return;
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
    if (!_interactive || _inside != GameBoxInsideState.closed) return;
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
      _sharp.clear();
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

  /// The back scan alone, flat and full size, without the box's perspective.
  void _openFlatBack() {
    final path = _backPath;
    if (!_interactive || path == null) return;
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => GameBoxScanViewer(
        path: path,
        title: GameBoxLocale.text(context, GameBoxLocale.readerTitle),
        preview: _sharp.providerFor(path, sharpen: _sharpText) ?? _artSet.art(detailed: _detailed, backPath: path).back,
      ),
    )).then((_) => _reloadSharpText());
  }

  Future<void> _showOptions() async {
    if (!_interactive) return;
    var animation = await GameBoxPreferences.openingAnimation();
    var sharp = _sharpText;
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      // Scrolls when the options are taller than the sheet (landscape).
      isScrollControlled: true,
      builder: (ctx) => StatefulBuilder(builder: (ctx, setSheet) {
        return SafeArea(
          child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
            SwitchListTile(
              value: animation,
              title: Text(GameBoxLocale.text(ctx, GameBoxLocale.openingAnimation)),
              subtitle: Text(GameBoxLocale.text(ctx, GameBoxLocale.openingAnimationDesc)),
              onChanged: (v) {
                setSheet(() => animation = v);
                GameBoxPreferences.setOpeningAnimation(v);
              },
            ),
            SwitchListTile(
              key: const ValueKey('game_box_sharp_text'),
              value: sharp,
              title: Text(GameBoxLocale.text(ctx, GameBoxLocale.sharpText)),
              subtitle: Text(GameBoxLocale.text(ctx, GameBoxLocale.sharpTextDesc)),
              onChanged: (v) {
                setSheet(() => sharp = v);
                GameBoxPreferences.setSharpText(v);
                if (!mounted) return;
                setState(() {
                  _sharpText = v;
                  _sharp.clear();
                });
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
            // The manual has its own download, the same as Game Settings ›
            // Manual; it is never fetched with the box faces.
            if (_canDownloadManual)
              ListTile(
                leading: const Icon(Icons.menu_book_outlined),
                title: Text(GameBoxLocale.text(ctx, GameBoxLocale.downloadManual)),
                subtitle: Text(GameBoxLocale.text(ctx, GameBoxLocale.downloadManualDesc)),
                onTap: () {
                  Navigator.of(ctx).pop();
                  _downloadManual();
                },
              ),
          ])),
        );
      }),
    );
  }

  // Inside of the box and its manual --------------------------------------

  /// The box model drawn now: the manual lies in it only when its PDF is on
  /// the device (never an invented booklet).
  GameBoxModel? get _model {
    final profile = _profile;
    if (profile == null) return null;
    final booklet = _manualPath == null ? null : GameBoxBooklet(pageAspect: _manualPage?.aspect);
    return GameBoxModel(profile, booklet: booklet);
  }

  BoxProjector? _projector(Size viewport) {
    final model = _model;
    if (model == null || viewport.isEmpty) return null;
    return BoxProjector(
      model: model,
      viewport: viewport,
      pose: _shownPose,
      opening: _opening,
      outlineBlend: _outline,
    );
  }

  /// The back is read straight on, with a lower perspective.
  BoxPose get _shownPose {
    final reading = _facingBack &&
        _pose.zoom <= 1.05 &&
        _phase == GameBoxInspectorPhase.inspecting &&
        _inside == GameBoxInsideState.closed;
    return reading ? _pose.copyWith(perspective: math.min(_pose.perspective, 0.35)) : _pose;
  }

  /// Same file as Game Settings › Manual (GameModel.getManualPath through
  /// the FileProvider); nothing is downloaded here.
  Future<void> _checkManual() async {
    final path = await GameManualService.existing(_game, widget.subject.systemFolder, widget.subject.fileProvider);
    if (!mounted) return;
    setState(() {
      _manualPath = path;
      _manualChecked = true;
    });
    if (path == null) {
      _manualPage?.dispose();
      _manualPage = null;
    }
  }

  /// Draws the manual's first page once the box is opened.
  Future<void> _ensureManualPage() async {
    final path = _manualPath;
    if (path == null || _manualPage != null || _manualPageLoading) return;
    _manualPageLoading = true;
    final page = await GameBoxManualCover.render(path);
    _manualPageLoading = false;
    if (!mounted || path != _manualPath) {
      page?.dispose();
      return;
    }
    setState(() => _manualPage = page);
  }

  bool get _canDownloadManual =>
      _manualChecked &&
      _manualPath == null &&
      widget.subject.system != null &&
      _game.romPath != null &&
      !_downloadingManual;

  /// How far the support and the manual stand out of an open box being
  /// inspected: a cartridge and its manual peek out of a cardboard box; in a
  /// plastic case the disc stays on its hub and the manual in the panel.
  double get _inspectSupport => _profile?.caseKind == GameBoxCaseKind.cardboard ? 1 : 0;
  double get _inspectBooklet => _profile?.caseKind == GameBoxCaseKind.cardboard ? 1 : 0;

  /// Runs a short animation; skipped (end state at once) with Reduce Motion.
  Future<void> _animate(Duration duration, void Function(double t) tick) async {
    if (_reduceMotion) {
      tick(1);
      return;
    }
    final c = AnimationController(vsync: this, duration: duration);
    _transient.add(c);
    c.addListener(() {
      if (mounted) tick(c.value);
    });
    try {
      await c.forward().orCancel;
    } on TickerCanceled {
      return;
    } finally {
      if (_transient.remove(c)) c.dispose();
    }
  }

  static double _seg(double t, double a, double b) => ((t - a) / (b - a)).clamp(0.0, 1.0).toDouble();

  /// "Open the box": the inside, without starting the game.
  Future<void> openBox() async {
    final profile = _profile;
    if (!_interactive || _inside != GameBoxInsideState.closed || profile == null || !profile.opens) return;
    _stopMotion();
    _poseBeforeOpen = _pose;
    final start = _pose;
    final target = _openingPose.copyWith(yaw: start.yaw + BoxPose.shortestAngle(start.yaw, _openingPose.yaw));
    _openYaw = target.yaw;
    final support = _inspectSupport, booklet = _inspectBooklet;
    setState(() => _inside = GameBoxInsideState.moving);
    _ensureManualPage();
    await _animate(const Duration(milliseconds: 950), (t) {
      setState(() {
        _pose = BoxPose.lerp(start, target, Curves.easeInOutCubic.transform(_seg(t, 0, 0.3)));
        _opening = BoxOpening(
          lid: _seg(t, 0.15, 0.75),
          support: support * Curves.easeOutCubic.transform(_seg(t, 0.6, 1)),
          booklet: booklet * Curves.easeOutCubic.transform(_seg(t, 0.62, 1)),
        );
        _outline = Curves.easeInOut.transform(_seg(t, 0.1, 0.7));
      });
    });
    if (!mounted || _phase != GameBoxInspectorPhase.inspecting) return;
    setState(() {
      _pose = target;
      _opening = BoxOpening(lid: 1, support: support, booklet: booklet);
      _outline = 1;
      _inside = GameBoxInsideState.open;
    });
  }

  /// Closes the inspected box and turns it back the way it was.
  Future<void> closeBox() async {
    if (!_isOpen) return;
    _stopMotion();
    final start = _pose;
    final from = _opening;
    final outline = _outline;
    final target = _poseBeforeOpen.copyWith(
      yaw: start.yaw + BoxPose.shortestAngle(start.yaw, _poseBeforeOpen.yaw),
    );
    setState(() => _inside = GameBoxInsideState.moving);
    await _animate(const Duration(milliseconds: 720), (t) {
      setState(() {
        _opening = BoxOpening(
          lid: from.lid * (1 - _seg(t, 0.2, 0.85)),
          support: from.support * (1 - _seg(t, 0, 0.35)),
          booklet: from.booklet * (1 - _seg(t, 0, 0.3)),
        );
        _outline = outline * (1 - _seg(t, 0.3, 1));
        _pose = BoxPose.lerp(start, target, Curves.easeInOutCubic.transform(_seg(t, 0.45, 1)));
      });
    });
    if (!mounted || _phase != GameBoxInspectorPhase.inspecting) return;
    setState(() {
      _pose = target;
      _opening = BoxOpening.closed;
      _outline = 0;
      _inside = GameBoxInsideState.closed;
    });
  }

  /// Takes the manual out of the open box toward the camera, opens it in the
  /// manual reader, and puts it back once the reader closes: the same box,
  /// still open, at the same angle.
  Future<void> takeManual() async {
    final path = _manualPath;
    if (path == null || !_isOpen) return;
    _stopMotion();
    final rest = _opening;
    setState(() => _inside = GameBoxInsideState.taking);
    // Raised off its clips, then brought to the camera.
    await _animate(const Duration(milliseconds: 160), (t) {
      setState(() => _opening = rest.copyWith(booklet: rest.booklet + (1 - rest.booklet) * t));
    });
    if (!mounted) return;
    final target = _reduceMotion ? null : _projector(_viewport)?.bookletTakeTarget();
    if (target != null) {
      await _animate(const Duration(milliseconds: 420), (t) {
        setState(() => _opening = _opening.copyWith(take: Curves.easeInOutCubic.transform(t), takeTarget: target));
      });
      if (!mounted) return;
    }
    // While the manual is read the box is not drawn and its large images
    // are released.
    _artSet.evictDetailed();
    _sharp.clear();
    setState(() {
      _readingManual = true;
      _detailed = false;
    });
    await Navigator.of(context).push(PageRouteBuilder<void>(
      opaque: true,
      transitionDuration: Duration(milliseconds: _reduceMotion ? 0 : 200),
      reverseTransitionDuration: Duration(milliseconds: _reduceMotion ? 0 : 160),
      pageBuilder: (_, _, _) => GameBoxInspector.manualReader(path, _game.name),
      transitionsBuilder: (_, animation, _, child) => FadeTransition(opacity: animation, child: child),
    ));
    if (!mounted) return;
    setState(() {
      _readingManual = false;
      _detailed = true;
    });
    final taken = _opening;
    if (taken.take > 0) {
      await _animate(const Duration(milliseconds: 380), (t) {
        setState(() => _opening = taken.copyWith(take: taken.take * (1 - Curves.easeInOutCubic.transform(t))));
      });
      if (!mounted) return;
    }
    final raised = _opening.booklet;
    await _animate(const Duration(milliseconds: 160), (t) {
      setState(() => _opening = BoxOpening(lid: rest.lid, support: rest.support, booklet: raised + (rest.booklet - raised) * t));
    });
    if (!mounted) return;
    setState(() {
      _opening = rest;
      _inside = GameBoxInsideState.open;
    });
  }

  /// Downloads a missing manual with the same ScreenScraper path as Game
  /// Settings › Manual (credentials, language, regions, quota). On success
  /// it appears in the open box at once.
  Future<void> _downloadManual() async {
    final system = widget.subject.system;
    if (!_canDownloadManual || system == null) return;
    setState(() {
      _downloadingManual = true;
      _manualProgress = 0;
    });
    final messenger = ScaffoldMessenger.maybeOf(context);
    GameManualDownload result;
    try {
      final target = await GameManualService.targetSystem(_game, system, isAllMode: widget.subject.isAllMode);
      result = await GameManualService.download(
        game: _game,
        targetSystem: target,
        onProgress: (progress) {
          if (mounted) setState(() => _manualProgress = progress);
        },
      );
    } catch (_) {
      result = const GameManualDownload(success: false, messageKey: AppLocale.manualDownloadFailed);
    }
    if (!mounted) return;
    setState(() => _downloadingManual = false);
    await _checkManual();
    if (!mounted) return;
    messenger?.showSnackBar(SnackBar(content: Text(result.messageKey.getString(context))));
    if (_manualPath == null || !_isOpen) return;
    _ensureManualPage();
    final rest = _opening;
    if (rest.booklet < _inspectBooklet) {
      await _animate(const Duration(milliseconds: 320), (t) {
        setState(() => _opening = rest.copyWith(booklet: rest.booklet + (_inspectBooklet - rest.booklet) * t));
      });
    }
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
    if (_inside == GameBoxInsideState.moving || _inside == GameBoxInsideState.taking) return;
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
    final booklet = _opening.booklet;
    setState(() {
      _pose = _clampOpen(_openingPose.copyWith(yaw: _inside == GameBoxInsideState.open ? _pose.yaw : _openingPose.yaw));
      _opening = BoxOpening(lid: 1, support: 1, booklet: booklet);
      _outline = 1;
    });
    await Future<void>.delayed(const Duration(milliseconds: 260));
    if (!mounted) return;
    await _fadeOut(const Duration(milliseconds: 200));
  }

  Future<void> _animatedOpening() async {
    final start = _pose;
    // A box already open for inspection keeps its angle and only lets its
    // support out.
    final target = _inside == GameBoxInsideState.open
        ? start
        : _openingPose.copyWith(yaw: start.yaw + BoxPose.shortestAngle(start.yaw, _openingPose.yaw));
    final opens = _profile?.opens ?? false;
    final lifts = _profile != null && GameBoxModel(_profile!).supportLifts;
    final from = _opening;
    final outline0 = _outline;
    double seg(double t, double a, double b) => ((t - a) / (b - a)).clamp(0.0, 1.0).toDouble();
    void tick() {
      final t = _open.value;
      final align = Curves.easeInOutCubic.transform(seg(t, 0.0, 0.2));
      final lid = opens ? from.lid + (1 - from.lid) * seg(t, 0.16, 0.56) : 0.0;
      final support = opens
          ? from.support + (1 - from.support) * Curves.easeOutCubic.transform(seg(t, 0.56, lifts ? 0.8 : 0.66))
          : 0.0;
      final last = Curves.easeInCubic.transform(seg(t, 0.8, 1.0));
      setState(() {
        _pose = BoxPose.lerp(start, target, align);
        _opening = BoxOpening(lid: lid, support: support, booklet: from.booklet);
        _outline = opens ? outline0 + (1 - outline0) * Curves.easeInOut.transform(seg(t, 0.12, 0.6)) : 0;
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
    _sharp.clear();
    _manualPage?.dispose();
    _manualPage = null;
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
        _inside = GameBoxInsideState.closed;
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
      // The system back gesture goes up one level, like the Back button.
      canPop: _phase == GameBoxInspectorPhase.inspecting && _inside == GameBoxInsideState.closed,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) back();
      },
      child: Scaffold(
        backgroundColor: background,
        body: Stack(children: [
          SafeArea(
            child: LayoutBuilder(builder: (context, c) {
              final landscape = c.maxWidth > c.maxHeight * 1.1;
              // Room for the Back button, so the box never sits under it.
              final box = Padding(padding: const EdgeInsets.only(top: 52), child: _boxArea());
              final panel = AnimatedOpacity(
                opacity: controlsVisible ? 1 : 0,
                duration: const Duration(milliseconds: 160),
                child: IgnorePointer(
                  ignoring: !controlsVisible,
                  child: _panel(theme, landscape, maxHeight: c.maxHeight * portraitPanelShare),
                ),
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
          if (controlsVisible)
            Positioned(
              left: 0,
              top: 0,
              child: SafeArea(
                child: Padding(
                  padding: const EdgeInsets.all(8),
                  child: _backButton(theme),
                ),
              ),
            ),
          if (_fade > 0)
            Positioned.fill(
              child: IgnorePointer(child: ColoredBox(color: Colors.black.withValues(alpha: _fade.clamp(0.0, 1.0)))),
            ),
        ]),
      ),
    );
  }

  /// Always at the top left: back to the library, or out of the open box.
  Widget _backButton(ThemeData theme) {
    final open = _inside != GameBoxInsideState.closed;
    return Semantics(
      button: true,
      label: GameBoxLocale.text(context, open ? GameBoxLocale.closeBox : GameBoxLocale.backToLibrary),
      excludeSemantics: true,
      child: FilledButton.tonalIcon(
        key: const ValueKey('game_box_back'),
        onPressed: _interactive ? back : null,
        style: FilledButton.styleFrom(
          backgroundColor: theme.colorScheme.surface.withValues(alpha: 0.82),
          foregroundColor: theme.colorScheme.onSurface,
        ),
        icon: const Icon(Icons.arrow_back_rounded),
        label: Text(GameBoxLocale.text(context, GameBoxLocale.goBack)),
      ),
    );
  }

  /// Asks, once the box is still, for the back made for its size on screen.
  void _scheduleSharpBack(Size viewport) {
    final path = _backPath;
    if (path == null || _sharpScheduled || _gesture || _poseAnim.isAnimating || _spin.isAnimating) return;
    _sharpScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _sharpScheduled = false;
      if (!mounted || path != _backPath || !_facingBack || _inside != GameBoxInsideState.closed) return;
      final width = backScreenWidth(viewport);
      if (width == null) return;
      _sharp.request(path, width * MediaQuery.devicePixelRatioOf(context), sharpen: _sharpText);
    });
  }

  /// Width on the screen, in logical pixels, of the whole back scan, or null
  /// when the back is not seen.
  @visibleForTesting
  double? backScreenWidth(Size viewport) {
    final path = _backPath;
    final projector = _projector(viewport);
    if (path == null || projector == null) return null;
    // The back panel itself: the widest face of the back surface (its
    // corner facets share the surface).
    double? width;
    for (final f in projector.project()) {
      if (f.face.surface != BoxSurface.back) continue;
      final q = projector.faceQuad(f.face.id);
      if (q == null) continue;
      final w = math.max((q[1] - q[0]).distance, (q[2] - q[3]).distance);
      if (width == null || w > width) width = w;
    }
    if (width == null) return null;
    // A jewel inlay scanned with its spines shows only its middle there.
    final size = GameBoxImageSize.of(path);
    final spines = _profile?.caseKind == GameBoxCaseKind.jewelCase &&
        size != null &&
        size.height > 0 &&
        size.width / size.height >= 1.22;
    return spines ? width / (1 - 2 * GameBoxArt.jewelSpineFraction) : width;
  }

  Future<void> _reloadSharpText() async {
    final v = await GameBoxPreferences.sharpText();
    if (mounted && v != _sharpText) {
      setState(() {
        _sharpText = v;
        _sharp.clear();
      });
    }
  }

  /// The render of the back kept now, if any, and the box area (tests).
  @visibleForTesting
  GameBoxRenderedScan? get sharpBack => _sharp.current;
  @visibleForTesting
  Size get viewport => _viewport;

  Widget _boxArea() {
    final profile = _profile;
    return LayoutBuilder(builder: (context, c) {
      _viewport = c.biggest;
      // Nothing is drawn while the manual is read (the reader covers it).
      if (_readingManual) return const SizedBox.expand();
      final model = _model;
      if (profile == null || model == null) return const Center(child: CircularProgressIndicator());
      final art = _artSet.art(
        detailed: _detailed,
        backPath: _backPath,
        edgeColor: _edge,
        frontFallback: widget.subject.frontFallback?.call(),
        backUnavailable: GameBoxLocale.text(context, GameBoxLocale.backUnavailable),
        gloss: !_facingBack && _pose.zoom <= 1.1 && _inside == GameBoxInsideState.closed,
        bookletCover: _manualPage?.image,
      );
      // Read straight on, the back is the render made for its size.
      final readingBack =
          _facingBack && _phase == GameBoxInspectorPhase.inspecting && _inside == GameBoxInsideState.closed;
      final sharpBack = readingBack ? _sharp.providerFor(_backPath, sharpen: _sharpText) : null;
      if (readingBack && _detailed) _scheduleSharpBack(c.biggest);
      final scene = GameBoxScene(
        model: model,
        art: sharpBack == null ? art : art.copyWith(back: sharpBack),
        pose: _shownPose,
        opening: _opening,
        outlineBlend: _outline,
        groundShadow: _inside == GameBoxInsideState.closed,
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
      final label = _inside == GameBoxInsideState.closed
          ? GameBoxLocale.format(context, GameBoxLocale.semanticsBox, {'title': _game.name, 'face': face})
          : GameBoxLocale.format(context, GameBoxLocale.semanticsOpenBox, {'title': _game.name});
      return Stack(fit: StackFit.expand, children: [
        Semantics(
          label: label,
          hint: GameBoxLocale.text(context, GameBoxLocale.dragHint),
          image: true,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onScaleStart: _onScaleStart,
            onScaleUpdate: _onScaleUpdate,
            onScaleEnd: _onScaleEnd,
            onDoubleTap: _onDoubleTap,
            onTapUp: _onTapUp,
            child: ClipRect(child: zoomed),
          ),
        ),
        if (_isOpen && _manualPath != null) ?_manualChip(c.biggest),
      ]);
    });
  }

  /// A label under the manual lying in the open box: touching it (or the
  /// manual itself, or X) takes it out to read it.
  Widget? _manualChip(Size viewport) {
    final quad = _projector(viewport)?.faceQuad('booklet.front');
    if (quad == null) return null;
    final cx = quad.map((q) => q.dx).reduce((a, b) => a + b) / quad.length;
    // Under the manual lying in a case; above the one standing out of a
    // cardboard box (its lower part is hidden by the box).
    final double top = _profile?.caseKind == GameBoxCaseKind.cardboard
        ? quad.map((q) => q.dy).reduce(math.min) - 44
        : quad.map((q) => q.dy).reduce(math.max) + 6;
    return Positioned(
      left: (cx - 90).clamp(4.0, math.max(4.0, viewport.width - 184)).toDouble(),
      top: top.clamp(4.0, math.max(4.0, viewport.height - 44)).toDouble(),
      width: 180,
      child: Center(
        child: ActionChip(
          key: const ValueKey('game_box_manual_chip'),
          avatar: const Icon(Icons.menu_book_rounded, size: 18),
          label: Text(GameBoxLocale.text(context, GameBoxLocale.readManual), overflow: TextOverflow.ellipsis),
          onPressed: takeManual,
        ),
      ),
    );
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

  /// Largest share of the height the panel takes in portrait: the rest is
  /// the box's, so that its back is drawn large enough to be read (the
  /// panel scrolls; Play stays at its bottom).
  static const double portraitPanelShare = 0.36;

  Widget _panel(ThemeData theme, bool landscape, {required double maxHeight}) {
    final info = _infoLines(context);
    final language = _readingLanguage;
    final closed = _inside == GameBoxInsideState.closed;
    final open = _inside != GameBoxInsideState.closed;
    final opens = _profile?.opens ?? false;
    final playButton = FilledButton.icon(
      onPressed: _inside == GameBoxInsideState.moving || _inside == GameBoxInsideState.taking ? null : play,
      icon: const Icon(Icons.play_arrow_rounded),
      label: Text(GameBoxLocale.text(context, GameBoxLocale.play)),
    );
    final title = Row(children: [
      // Leaves room for the Back button above the box in portrait.
      const SizedBox(width: 12),
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
    ]);
    final infoLines = <Widget>[
      for (final line in info)
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 2, 12, 2),
          child: Text(line, style: theme.textTheme.bodySmall),
        ),
    ];
    final progress = <Widget>[
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
      if (_downloadingManual)
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 6, 12, 2),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(GameBoxLocale.text(context, GameBoxLocale.downloadingManual), style: theme.textTheme.bodySmall),
            const SizedBox(height: 4),
            LinearProgressIndicator(value: _manualProgress > 0 ? _manualProgress : null),
          ]),
        ),
    ];
    final actions = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        alignment: WrapAlignment.center,
        children: [
          if (closed) ...[
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
            if (_facingBack && _backPath != null)
              OutlinedButton.icon(
                onPressed: _openFlatBack,
                icon: const Icon(Icons.crop_free),
                label: Text(GameBoxLocale.text(context, GameBoxLocale.flatView)),
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
              icon: const Icon(Icons.chrome_reader_mode_outlined),
              label: Text(GameBoxLocale.text(context, GameBoxLocale.read)),
            ),
            if (opens)
              FilledButton.tonalIcon(
                key: const ValueKey('game_box_open'),
                onPressed: openBox,
                icon: const Icon(Icons.inventory_2_outlined),
                label: Text(GameBoxLocale.text(context, GameBoxLocale.openBox)),
              ),
          ],
          if (open) ...[
            OutlinedButton.icon(
              key: const ValueKey('game_box_close'),
              onPressed: _isOpen ? closeBox : null,
              icon: const Icon(Icons.inventory_2),
              label: Text(GameBoxLocale.text(context, GameBoxLocale.closeBox)),
            ),
            if (_manualPath != null)
              FilledButton.tonalIcon(
                key: const ValueKey('game_box_read_manual'),
                onPressed: _isOpen ? takeManual : null,
                icon: const Icon(Icons.menu_book_rounded),
                label: Text(GameBoxLocale.text(context, GameBoxLocale.readManual)),
              )
            else if (_canDownloadManual)
              OutlinedButton.icon(
                key: const ValueKey('game_box_download_manual'),
                onPressed: _isOpen ? _downloadManual : null,
                icon: const Icon(Icons.download_outlined),
                label: Text(GameBoxLocale.text(context, GameBoxLocale.downloadManual)),
              ),
          ],
          if (_zoomed)
            OutlinedButton.icon(
              onPressed: _recenter,
              icon: const Icon(Icons.center_focus_strong_outlined),
              label: Text(GameBoxLocale.text(context, GameBoxLocale.recenter)),
            ),
          if (landscape) playButton,
        ],
      ),
    );
    if (landscape) {
      return SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          title,
          ...infoLines,
          ...progress,
          const SizedBox(height: 8),
          actions,
          const SizedBox(height: 12),
        ]),
      );
    }
    // Portrait: the title and any progress, then the buttons and the notes
    // scrolling under them, Play always shown at the bottom.
    return ConstrainedBox(
      constraints: BoxConstraints(maxHeight: maxHeight),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        title,
        ...progress,
        Flexible(
          child: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const SizedBox(height: 4),
              actions,
              const SizedBox(height: 6),
              ...infoLines,
            ]),
          ),
        ),
        Padding(padding: const EdgeInsets.fromLTRB(8, 6, 8, 10), child: Center(child: playButton)),
      ]),
    );
  }

  bool get _missingFaces =>
      _media.manifest == null || _media.back == null || _media.spine == null || _media.support == null;

  List<String> _infoLines(BuildContext context) {
    if (_inside != GameBoxInsideState.closed) return _insideLines(context);
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

  /// What the open box shows, said plainly: the manual is the local PDF in
  /// its own language (never presented as translated), the inside is neutral.
  List<String> _insideLines(BuildContext context) {
    final out = <String>[];
    if (_manualPath != null) {
      final pages = _manualPage?.pageCount;
      out.add(pages == null
          ? GameBoxLocale.text(context, GameBoxLocale.manualInBox)
          : GameBoxLocale.format(context, GameBoxLocale.manualInBoxPages, {'pages': '$pages'}));
    } else if (_manualChecked) {
      out.add(GameBoxLocale.text(context, GameBoxLocale.manualNone));
    }
    out.add(GameBoxLocale.text(context, GameBoxLocale.insideNeutral));
    return out;
  }
}
