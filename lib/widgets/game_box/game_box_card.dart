import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import 'package:neostation/services/game_box/game_box_enhance.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/widgets/game_box/game_box_art_loader.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';

/// The box of a game in the library (carousel, grid and list): the real
/// front scan on a case of the console's family, still, at the resting pose
/// (front, a little of the spine and top). It has no gestures of its own, so
/// swiping keeps navigating between games; the inspector owns the box
/// gestures.
///
/// Only the front and the spine are decoded. The carousel decodes them at its
/// usual size; the grid and the list pass [decodeWidth], the size their flat
/// cover already used, and get a [compact] box (three facets per rounded
/// corner instead of eight, lit as one curve; no sleeve reflection), so a
/// screen of small boxes costs about what the flat covers did.
class GameBoxCard extends StatefulWidget {
  const GameBoxCard({
    super.key,
    required this.frontPath,
    required this.title,
    this.systemId,
    this.spinePath,
    this.fitPadding = 0.94,
    this.decodeWidth,
    this.pose = BoxPose.rest,
  });

  final String frontPath;
  final String title;
  final String? systemId;
  final String? spinePath;
  final double fitPadding;

  /// Decode width of the small boxes of the grid and list (null: carousel).
  final int? decodeWidth;

  /// Resting pose; the list shows its thumbnails a little more turned.
  final BoxPose pose;

  bool get compact => decodeWidth != null;

  @override
  State<GameBoxCard> createState() => _GameBoxCardState();

  /// Whether a spine scan exists for [path] (cheap check cached by callers).
  static bool exists(String path) => path.isNotEmpty && File(path).existsSync();
}

/// Shows the corrected copy of a degraded scan once it exists
/// (docs/game-box-3d.md § 22 and § 28): one made earlier is looked up in the
/// cache, one made now (the selection rested on the game, or its box was
/// opened) replaces the scan as soon as it is ready.
class _GameBoxCardState extends State<GameBoxCard> {
  StreamSubscription<String>? _changes;

  @override
  void initState() {
    super.initState();
    _changes = GameBoxEnhance.changes.listen((path) {
      if (!mounted) return;
      if (path.isEmpty || path == widget.frontPath || path == widget.spinePath) setState(() {});
    });
    _lookUp();
  }

  @override
  void didUpdateWidget(GameBoxCard old) {
    super.didUpdateWidget(old);
    if (old.frontPath != widget.frontPath || old.spinePath != widget.spinePath) _lookUp();
  }

  @override
  void dispose() {
    _changes?.cancel();
    super.dispose();
  }

  /// A copy found in the cache arrives through [GameBoxEnhance.changes].
  void _lookUp() {
    for (final path in [widget.frontPath, widget.spinePath]) {
      if (path != null && path.isNotEmpty) unawaited(GameBoxEnhance.cached(path));
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = GameBoxImageSize.of(widget.frontPath);
    final aspect = size == null || size.height == 0 ? null : size.width / size.height;
    // Rigid cases keep their physical size; only cardboard boxes (and tall
    // jewel inserts) follow their art (docs/game-box-3d.md § 13).
    final profile = GameBoxProfiles.of(widget.systemId).withFrontAspect(aspect);
    final media = GameBoxLocalMedia(front: widget.frontPath, spine: widget.spinePath);
    final art = GameBoxArtSet(media: media, title: widget.title)
        .art(detailed: false, compactWidth: widget.decodeWidth, profile: profile);
    return ExcludeSemantics(
      child: GameBoxScene(
        model: GameBoxModel(profile, cornerSegments: widget.compact ? 3 : 8),
        art: art,
        pose: widget.pose,
        rotationSafeFit: false,
        fitPadding: widget.fitPadding,
      ),
    );
  }
}
