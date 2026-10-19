import 'dart:io';

import 'package:flutter/material.dart';

import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/widgets/game_box/game_box_art_loader.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';

/// The box of a game in the Jaquette view: the real front scan on a case of
/// the console's family, still, at the resting pose (front, a little of the
/// spine and top). It has no gestures of its own, so swiping keeps
/// navigating between games; the inspector owns the box gestures.
///
/// Only the front and the spine are decoded, at the carousel's usual size.
class GameBoxCard extends StatelessWidget {
  const GameBoxCard({
    super.key,
    required this.frontPath,
    required this.title,
    this.systemId,
    this.spinePath,
    this.fitPadding = 0.94,
  });

  final String frontPath;
  final String title;
  final String? systemId;
  final String? spinePath;
  final double fitPadding;

  @override
  Widget build(BuildContext context) {
    final size = GameBoxImageSize.of(frontPath);
    final aspect = size == null || size.height == 0 ? null : size.width / size.height;
    final profile = GameBoxProfiles.of(systemId).withFrontAspect(aspect);
    final media = GameBoxLocalMedia(front: frontPath, spine: spinePath);
    final art = GameBoxArtSet(media: media, title: title).art(detailed: false);
    return ExcludeSemantics(
      child: GameBoxScene(
        model: GameBoxModel(profile),
        art: art,
        pose: BoxPose.rest,
        rotationSafeFit: false,
        fitPadding: fitPadding,
      ),
    );
  }

  /// Whether a spine scan exists for [path] (cheap check cached by callers).
  static bool exists(String path) => path.isNotEmpty && File(path).existsSync();
}
