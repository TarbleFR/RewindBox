import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;

import 'package:neostation/services/game_box/game_box_enhance.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_media_service.dart';
import 'package:neostation/services/logger_service.dart';

/// What "Restore the automatic back" did.
enum GameBoxBackRestore {
  /// The automatic back kept aside is shown again.
  restored,

  /// No automatic back was kept: the player's back is removed and the box
  /// shows a reconstructed back until a search finds one.
  removed,

  /// The back was not the player's: nothing changed.
  nothingToRestore,
}

/// The player's own back of a game (docs/game-box-3d.md § 21): "Edit the
/// back" imports a picture from Photos or Files, framed on the back panel,
/// and saves it as a face chosen by hand; it stays first after a restart and
/// after any scrape. "Restore the automatic back" brings back the back that
/// was there before, kept aside untouched.
///
/// Only this game's back changes: its file and its manifest, under the
/// game's own name in the system's media folders. Other games, other faces
/// and the back editions of other languages stay as they are.
class GameBoxBackOverride {
  GameBoxBackOverride._();

  /// Folder of the automatic backs kept aside, beside the back folder.
  static const String autoFolder = 'box2dback-auto';

  static const String recordType = 'manual:back';

  static GameBoxMediaStore _store(GameBoxSearchContext ctx) => GameBoxMediaStore(ctx.fileProvider);

  static (String dir, String key) _aside(GameBoxSearchContext ctx) {
    final manifest = _store(ctx).manifestPath(ctx.game, ctx.systemFolder);
    return (p.join(p.dirname(p.dirname(manifest)), autoFolder), p.basenameWithoutExtension(manifest));
  }

  /// The automatic back kept aside, if any.
  static File? keptAside(GameBoxSearchContext ctx) {
    final (dir, key) = _aside(ctx);
    for (final ext in const ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp']) {
      final f = File(p.join(dir, '$key.$ext'));
      if (f.existsSync()) return f;
    }
    return null;
  }

  /// Whether the back shown is the player's own.
  static bool isPlayers(GameBoxLocalMedia media) => media.back != null && (media.recordOf(GameBoxMediaKind.back)?.manual ?? false);

  /// [bytes] framed on [window] (fractions of the picture), as PNG; the
  /// bytes themselves when the window is the whole picture.
  static Future<Uint8List?> crop(Uint8List bytes, ui.Rect window) async {
    const full = ui.Rect.fromLTWH(0, 0, 1, 1);
    final w = window.intersect(full);
    if (w.width <= 0 || w.height <= 0) return null;
    if ((w.left).abs() < 1e-4 && (w.top).abs() < 1e-4 && (w.right - 1).abs() < 1e-4 && (w.bottom - 1).abs() < 1e-4) {
      return bytes;
    }
    final codec = await ui.instantiateImageCodec(bytes);
    final frame = await codec.getNextFrame();
    codec.dispose();
    final image = frame.image;
    try {
      final src = ui.Rect.fromLTRB(
        (w.left * image.width).roundToDouble(),
        (w.top * image.height).roundToDouble(),
        (w.right * image.width).roundToDouble(),
        (w.bottom * image.height).roundToDouble(),
      );
      final ow = src.width.round(), oh = src.height.round();
      if (ow < 1 || oh < 1) return null;
      final recorder = ui.PictureRecorder();
      ui.Canvas(recorder).drawImageRect(
        image,
        src,
        ui.Rect.fromLTWH(0, 0, ow.toDouble(), oh.toDouble()),
        ui.Paint()..filterQuality = ui.FilterQuality.none,
      );
      final cropped = await recorder.endRecording().toImage(ow, oh);
      final png = await cropped.toByteData(format: ui.ImageByteFormat.png);
      cropped.dispose();
      return png?.buffer.asUint8List(png.offsetInBytes, png.lengthInBytes);
    } finally {
      image.dispose();
    }
  }

  /// Saves [bytes], framed on [window], as the player's back. [source] says
  /// where it came from (`photos`, `files`). The automatic back shown until
  /// now is kept aside first, once.
  static Future<GameBoxAdoption> save(
    GameBoxSearchContext ctx,
    Uint8List bytes, {
    ui.Rect window = const ui.Rect.fromLTWH(0, 0, 1, 1),
    required String source,
  }) async {
    final framed = await crop(bytes, window);
    if (framed == null) return const GameBoxAdoption(verdict: GameBoxImageVerdict.unreadable);
    final store = _store(ctx);
    final before = store.read(ctx.game, ctx.systemFolder);
    final previous = before.back;
    if (previous != null && !isPlayers(before)) await _keepAside(ctx, previous, before.recordOf(GameBoxMediaKind.back));
    final size = GameBoxImageSize.fromBytes(bytes);
    final full = window.left <= 0 && window.top <= 0 && window.right >= 1 && window.bottom >= 1;
    final adoption = await GameBoxMediaService.importBytes(
      ctx,
      GameBoxMediaKind.back,
      framed,
      type: recordType,
      note: source,
      transforms: [
        if (!full && size != null)
          'crop:back ${_f(window.left)},${_f(window.top)},${_f(window.width)},${_f(window.height)} '
              'of ${size.width.round()}x${size.height.round()}',
      ],
    );
    if (adoption.ok) {
      if (previous != null) _forget(previous);
      _forget(adoption.path!);
      LoggerService.instance.i('GameBox: player back saved for ${ctx.game.romname} ($source${full ? '' : ', framed'}).');
    }
    return adoption;
  }

  static String _f(double v) => v.toStringAsFixed(4);

  static Future<void> _keepAside(GameBoxSearchContext ctx, String path, GameBoxFaceRecord? record) async {
    final (dir, key) = _aside(ctx);
    await Directory(dir).create(recursive: true);
    for (final old in [keptAside(ctx), File(p.join(dir, '$key.json'))]) {
      if (old != null && old.existsSync()) await old.delete();
    }
    final ext = p.extension(path).replaceFirst('.', '').toLowerCase();
    await File(path).copy(p.join(dir, '$key.${ext.isEmpty ? 'png' : ext}'));
    if (record != null) await File(p.join(dir, '$key.json')).writeAsString(jsonEncode(record.toJson()));
  }

  /// Removes the player's back and shows the automatic one again: the one
  /// kept aside when there is one (no network needed), else none, and the
  /// box shows a reconstructed back until a search finds one.
  static Future<GameBoxBackRestore> restoreAutomatic(GameBoxSearchContext ctx) async {
    final store = _store(ctx);
    final media = store.read(ctx.game, ctx.systemFolder);
    if (!isPlayers(media)) return GameBoxBackRestore.nothingToRestore;
    final current = media.back!;
    final target = store.canonicalPath(ctx.game, ctx.systemFolder, GameBoxMediaFolders.back, 'png');
    for (final ext in const ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp']) {
      final f = File('${p.withoutExtension(target)}.$ext');
      if (f.existsSync()) await f.delete();
    }
    _forget(current);
    final manifest = media.manifest;
    final faces = Map.of(manifest?.faces ?? const <GameBoxMediaKind, GameBoxFaceRecord>{})
      ..remove(GameBoxMediaKind.back);
    final aside = keptAside(ctx);
    final (dir, key) = _aside(ctx);
    final recordFile = File(p.join(dir, '$key.json'));
    var result = GameBoxBackRestore.removed;
    if (aside != null) {
      final ext = p.extension(aside.path).replaceFirst('.', '');
      final restored = '${p.withoutExtension(target)}.$ext';
      await File(restored).parent.create(recursive: true);
      await aside.copy(restored);
      await aside.delete();
      _forget(restored);
      if (recordFile.existsSync()) {
        final record = GameBoxFaceRecord.fromJson(jsonDecode(await recordFile.readAsString()));
        if (record != null) faces[GameBoxMediaKind.back] = record;
      }
      result = GameBoxBackRestore.restored;
    }
    if (recordFile.existsSync()) await recordFile.delete();
    if (manifest != null) await store.writeManifest(ctx.game, ctx.systemFolder, manifest.copyWith(faces: faces));
    LoggerService.instance.i('GameBox: automatic back of ${ctx.game.romname}: ${result.name}.');
    return result;
  }

  /// Forgets every cached size, check, decode and correction of [path].
  static void _forget(String path) {
    GameBoxImageSize.evict(path);
    GameBoxMediaChecker.evict(path);
    GameBoxEnhance.evict(path);
  }
}
