import 'libretro_core_catalog.dart';
import 'libretro_internal_service.dart';

/// Per-game engine choices of an embedded libretro system, in the order the
/// game settings list them: the system's bundled cores, default first.
///
/// Build 438: the RetroArch app is no longer offered as a choice. A game whose
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
