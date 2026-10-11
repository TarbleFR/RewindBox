import 'dart:io';

import 'libretro_core_catalog.dart';
import 'libretro_internal_service.dart';

/// Per-game engine choices of an embedded libretro system, in the order the
/// game settings list them: the system's bundled cores, default first.
///
/// Build 440: the RetroArch app is no longer offered as a choice. A game whose
/// stored choice is already [LibretroInternalService.retroArchChoice] keeps it
/// (no preference is migrated or rewritten, and such a game still opens the
/// RetroArch app): the choice is listed last, as an earlier setting, so the
/// list shows the real setting and a core can replace it.
List<String> libretroEngineChoices(String systemKey, String? stored) =>
    <String>[
      for (final core in LibretroCoreCatalog.coresFor(systemKey)) core.id,
      if (stored == LibretroInternalService.retroArchChoice)
        LibretroInternalService.retroArchChoice,
    ];

/// Whether the game's file can be read here, the file condition of
/// [LibretroInternalService.shouldLaunchEmbedded]. Games known only to the
/// RetroArch app's exported library point into RetroArch's own container and
/// are not readable: they open the RetroArch app whatever their core choice.
Future<bool> libretroRomReadable(String? romPath) async {
  if (romPath == null || romPath.isEmpty) return false;
  try {
    return await File(romPath).exists();
  } catch (_) {
    return false;
  }
}

/// Whether the game settings may show the game as running in the embedded
/// engine (the check of the engine identity): its file is readable here and
/// it is not set to the RetroArch app. Display only; routing stays with
/// [LibretroInternalService.shouldLaunchEmbedded] (core presence in the IPA is
/// checked at build time, as for the other embedded engines).
bool libretroRunsEmbedded({
  required bool romReadable,
  required String? stored,
}) =>
    romReadable && stored != LibretroInternalService.retroArchChoice;
