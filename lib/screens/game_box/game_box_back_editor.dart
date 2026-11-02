import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import 'package:neostation/l10n/game_box_locale.dart';
import 'package:neostation/services/game_box/game_box_art_fit.dart';
import 'package:neostation/services/game_box/game_box_back_override.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_media_service.dart';
import 'package:neostation/services/storage/storage_import_activity.dart';
import 'package:neostation/widgets/game_box/game_box_art_loader.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';

/// What the back editor changed.
class GameBoxBackEdit {
  const GameBoxBackEdit({this.paths = const {}, this.message});

  /// Files written or removed.
  final Set<String> paths;

  /// What to tell the player, already in their language.
  final String? message;

  bool get changed => paths.isNotEmpty;
}

/// "Edit the back" of any game (docs/game-box-3d.md § 21): a picture from
/// Photos or Files, framed on the back panel, previewed on the box, saved as
/// the player's own back. "Restore the automatic back" undoes it.
class GameBoxBackEditor extends StatefulWidget {
  const GameBoxBackEditor({super.key, required this.context, this.debugPick});

  final GameBoxSearchContext context;

  /// Tests: the picture "picked" ([photos] true for Photos).
  final Future<Uint8List?> Function(bool photos)? debugPick;

  /// Opens the editor; returns what it changed.
  static Future<GameBoxBackEdit> show(BuildContext context, GameBoxSearchContext search) async {
    final result = await Navigator.of(context).push<GameBoxBackEdit>(MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => GameBoxBackEditor(context: search),
    ));
    return result ?? const GameBoxBackEdit();
  }

  @override
  State<GameBoxBackEditor> createState() => GameBoxBackEditorState();
}

@visibleForTesting
class GameBoxBackEditorState extends State<GameBoxBackEditor> {
  Uint8List? _bytes;
  Size? _size;
  String _source = 'files';
  Rect _window = const Rect.fromLTWH(0, 0, 1, 1);
  bool _preview = false;
  bool _busy = false;
  String? _message;

  GameBoxSearchContext get _ctx => widget.context;
  String _t(String key) => GameBoxLocale.text(context, key);

  /// The picked picture, read while the import is counted, so that the
  /// storage clean-up never removes the picker's copy under it.
  Future<Uint8List?> _pickBack(bool photos) => StorageImportActivity.run(() async {
        final picked = photos
            ? await FilePicker.pickFiles(type: FileType.image)
            : await FilePicker.pickFiles(
                type: FileType.custom,
                allowedExtensions: const ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'heic'],
              );
        final path = picked?.files.single.path;
        if (path == null) return null;
        return File(path).readAsBytes();
      });

  Future<void> pick(bool photos) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final bytes = await (widget.debugPick ?? _pickBack)(photos);
      if (!mounted || bytes == null) return;
      final check = await GameBoxMediaChecker.checkBytes(bytes);
      final size = GameBoxImageSize.fromBytes(bytes);
      if (!mounted) return;
      if (!check.ok || size == null) {
        setState(() => _message = GameBoxLocale.format(
            context, GameBoxLocale.importRefused, {'reason': _t(GameBoxLocale.refusedUnreadable)}));
        return;
      }
      // A full cover sheet (back | spine | front) is framed on its back.
      final parts = GameBoxWrapLayout.forProfile(_ctx.profile)?.split(size);
      setState(() {
        _bytes = bytes;
        _size = size;
        _source = photos ? 'photos' : 'files';
        _window = parts?.back ?? const Rect.fromLTWH(0, 0, 1, 1);
        _preview = false;
        _message = null;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// The frame, in fractions of the picture (tests).
  Rect get window => _window;
  set window(Rect value) => setState(() => _window = _clampWindow(value));

  static Rect _clampWindow(Rect r) {
    const minSide = 0.08;
    var l = r.left.clamp(0.0, 1 - minSide), t = r.top.clamp(0.0, 1 - minSide);
    var rr = r.right.clamp(l + minSide, 1.0), b = r.bottom.clamp(t + minSide, 1.0);
    return Rect.fromLTRB(l.toDouble(), t.toDouble(), rr.toDouble(), b.toDouble());
  }

  Future<void> save() async {
    final bytes = _bytes;
    if (bytes == null || _busy) return;
    setState(() => _busy = true);
    try {
      final before = GameBoxMediaStore(_ctx.fileProvider).read(_ctx.game, _ctx.systemFolder).back;
      final adoption = await GameBoxBackOverride.save(_ctx, bytes, window: _window, source: _source);
      if (!mounted) return;
      if (!adoption.ok) {
        setState(() => _message = GameBoxLocale.format(
            context, GameBoxLocale.importRefused, {'reason': _t(GameBoxLocale.refusedUnreadable)}));
        return;
      }
      GameBoxArtSet.evictPath(adoption.path!);
      if (before != null) GameBoxArtSet.evictPath(before);
      Navigator.of(context).pop(GameBoxBackEdit(
        paths: {adoption.path!, ?before},
        message: _t(GameBoxLocale.backSaved),
      ));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> restore() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final before = GameBoxMediaStore(_ctx.fileProvider).read(_ctx.game, _ctx.systemFolder).back;
      var result = await GameBoxBackOverride.restoreAutomatic(_ctx);
      // Nothing kept aside: the sources are asked for this game's back.
      if (result == GameBoxBackRestore.removed && _ctx.appSystemId != null) {
        final report = await GameBoxMediaService.complete(_ctx, kinds: {GameBoxMediaKind.back});
        if (report.outcomes[GameBoxMediaKind.back] == GameBoxFaceOutcome.added) result = GameBoxBackRestore.restored;
      }
      if (!mounted) return;
      final after = GameBoxMediaStore(_ctx.fileProvider).read(_ctx.game, _ctx.systemFolder).back;
      for (final path in {?before, ?after}) {
        GameBoxArtSet.evictPath(path);
      }
      Navigator.of(context).pop(GameBoxBackEdit(
        paths: {?before, ?after},
        message: _t(result == GameBoxBackRestore.restored ? GameBoxLocale.backRestored : GameBoxLocale.backRestoreNone),
      ));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final media = GameBoxMediaStore(_ctx.fileProvider).read(_ctx.game, _ctx.systemFolder);
    final players = GameBoxBackOverride.isPlayers(media);
    return Scaffold(
      appBar: AppBar(
        title: Text(_t(GameBoxLocale.editBack)),
        actions: [
          if (_bytes != null)
            TextButton(
              key: const ValueKey('game_box_back_save'),
              onPressed: _busy ? null : save,
              child: Text(_t(GameBoxLocale.save)),
            ),
        ],
      ),
      body: SafeArea(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (_busy) const LinearProgressIndicator(),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Wrap(spacing: 8, runSpacing: 8, children: [
              FilledButton.tonalIcon(
                key: const ValueKey('game_box_back_photos'),
                onPressed: _busy ? null : () => pick(true),
                icon: const Icon(Icons.photo_library_outlined),
                label: Text(_t(GameBoxLocale.importFromPhotos)),
              ),
              FilledButton.tonalIcon(
                key: const ValueKey('game_box_back_files'),
                onPressed: _busy ? null : () => pick(false),
                icon: const Icon(Icons.folder_open_outlined),
                label: Text(_t(GameBoxLocale.importFromFiles)),
              ),
              if (players)
                OutlinedButton.icon(
                  key: const ValueKey('game_box_back_restore'),
                  onPressed: _busy ? null : restore,
                  icon: const Icon(Icons.settings_backup_restore),
                  label: Text(_t(GameBoxLocale.restoreAutoBack)),
                ),
            ]),
          ),
          if (_message != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
              child: Text(_message!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          if (_bytes != null) ...[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
              child: SegmentedButton<bool>(
                segments: [
                  ButtonSegment(value: false, icon: const Icon(Icons.crop), label: Text(_t(GameBoxLocale.cropBackTitle))),
                  ButtonSegment(
                    value: true,
                    icon: const Icon(Icons.view_in_ar_outlined),
                    label: Text(_t(GameBoxLocale.cropPreview)),
                  ),
                ],
                selected: {_preview},
                onSelectionChanged: (v) => setState(() => _preview = v.first),
              ),
            ),
            if (!_preview)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(_t(GameBoxLocale.cropBackHint), style: Theme.of(context).textTheme.bodySmall),
              ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: _preview ? _previewOnBox(media) : _cropper(),
              ),
            ),
          ] else
            const Spacer(),
        ]),
      ),
    );
  }

  /// The picked picture with its frame: drag inside to move it, drag a
  /// corner to resize it.
  Widget _cropper() {
    final size = _size!;
    return LayoutBuilder(builder: (context, c) {
      final scale = math.min(c.maxWidth / size.width, c.maxHeight / size.height);
      final shown = Size(size.width * scale, size.height * scale);
      final origin = Offset((c.maxWidth - shown.width) / 2, (c.maxHeight - shown.height) / 2);
      Rect frame() => Rect.fromLTRB(
            origin.dx + _window.left * shown.width,
            origin.dy + _window.top * shown.height,
            origin.dx + _window.right * shown.width,
            origin.dy + _window.bottom * shown.height,
          );
      Widget handle(Alignment corner) {
        final f = frame();
        final at = Offset(
          corner.x < 0 ? f.left : f.right,
          corner.y < 0 ? f.top : f.bottom,
        );
        return Positioned(
          left: at.dx - 18,
          top: at.dy - 18,
          width: 36,
          height: 36,
          child: GestureDetector(
            key: ValueKey('game_box_back_handle_${corner.x}_${corner.y}'),
            behavior: HitTestBehavior.opaque,
            onPanUpdate: (d) {
              final dx = d.delta.dx / shown.width, dy = d.delta.dy / shown.height;
              window = Rect.fromLTRB(
                _window.left + (corner.x < 0 ? dx : 0),
                _window.top + (corner.y < 0 ? dy : 0),
                _window.right + (corner.x > 0 ? dx : 0),
                _window.bottom + (corner.y > 0 ? dy : 0),
              );
            },
            child: Center(
              child: Container(
                width: 18,
                height: 18,
                decoration: BoxDecoration(
                  color: Colors.white,
                  shape: BoxShape.circle,
                  border: Border.all(color: Theme.of(context).colorScheme.primary, width: 3),
                ),
              ),
            ),
          ),
        );
      }

      final f = frame();
      return Stack(children: [
        Positioned(
          left: origin.dx,
          top: origin.dy,
          width: shown.width,
          height: shown.height,
          child: Image.memory(_bytes!, fit: BoxFit.fill, gaplessPlayback: true),
        ),
        // Outside the frame is dimmed.
        Positioned.fill(child: IgnorePointer(child: CustomPaint(painter: _FrameShade(f)))),
        Positioned.fromRect(
          rect: f,
          child: GestureDetector(
            key: const ValueKey('game_box_back_frame'),
            behavior: HitTestBehavior.opaque,
            onPanUpdate: (d) {
              final dx = d.delta.dx / shown.width, dy = d.delta.dy / shown.height;
              final w = _window.width, h = _window.height;
              final l = (_window.left + dx).clamp(0.0, 1 - w), t = (_window.top + dy).clamp(0.0, 1 - h);
              window = Rect.fromLTWH(l.toDouble(), t.toDouble(), w, h);
            },
          ),
        ),
        for (final corner in const [Alignment.topLeft, Alignment.topRight, Alignment.bottomLeft, Alignment.bottomRight])
          handle(corner),
      ]);
    });
  }

  /// The framed picture on the box, seen from the back, before saving.
  Widget _previewOnBox(GameBoxLocalMedia media) {
    final size = _size!;
    final art = GameBoxArtSet(media: media, title: _ctx.title).art(detailed: false, profile: _ctx.profile);
    return GameBoxScene(
      key: const ValueKey('game_box_back_preview'),
      model: GameBoxModel(_ctx.profile),
      art: GameBoxArt(
        title: art.title,
        front: art.front,
        back: MemoryImage(_bytes!),
        spine: art.spine,
        backAspect: size.width / size.height,
        backWindow: _window,
        frontWindow: art.frontWindow,
        frontAspect: art.frontAspect,
        frontNature: art.frontNature,
        gloss: false,
      ),
      pose: const BoxPose(yaw: math.pi - 0.35, pitch: 0.12),
      groundShadow: true,
    );
  }
}

class _FrameShade extends CustomPainter {
  _FrameShade(this.frame);
  final Rect frame;

  @override
  void paint(Canvas canvas, Size size) {
    final outside = Path()
      ..fillType = PathFillType.evenOdd
      ..addRect(Offset.zero & size)
      ..addRect(frame);
    canvas.drawPath(outside, Paint()..color = const Color(0x99000000));
    canvas.drawRect(
      frame,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..color = Colors.white,
    );
  }

  @override
  bool shouldRepaint(_FrameShade old) => old.frame != frame;
}
