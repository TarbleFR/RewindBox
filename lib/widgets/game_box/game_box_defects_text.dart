import 'package:flutter/widgets.dart';

import 'package:neostation/l10n/game_box_locale.dart';
import 'package:neostation/services/game_box/game_box_enhance.dart';

/// The defects a corrected picture had, named in the player's language
/// (docs/game-box-3d.md § 22).
String gameBoxDefectsText(BuildContext context, Set<GameBoxImageDefect> defects) => [
      for (final d in GameBoxImageDefect.values)
        if (defects.contains(d))
          GameBoxLocale.text(context, switch (d) {
            GameBoxImageDefect.lowResolution => GameBoxLocale.defectLowResolution,
            GameBoxImageDefect.jpegBlocks => GameBoxLocale.defectJpegBlocks,
            GameBoxImageDefect.noise => GameBoxLocale.defectNoise,
            GameBoxImageDefect.blur => GameBoxLocale.defectBlur,
            GameBoxImageDefect.faded => GameBoxLocale.defectFaded,
          }),
    ].join(', ');
