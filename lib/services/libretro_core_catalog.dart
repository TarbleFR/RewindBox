/// Static description of the libretro cores embedded in NeoStation iOS and of
/// the NeoStation systems they run.
///
/// The cores are the official iOS builds from the libretro buildbot — the
/// same binaries RetroArch's iOS packaging script downloads — packaged as
/// `<id>_libretro.framework` by `build-utils/libretro/build_cores.py`.
library;

import 'libretro_resolution.dart';

export 'libretro_resolution.dart' show LibretroResolutionDeclaration;

/// RETRO_HW_CONTEXT_* values understood by the native host.
abstract final class LibretroHardwareContext {
  static const int none = 0;
  static const int openGLES3 = 4;
  static const int vulkan = 6;
}

/// A setting NeoStation exposes in the in-game menu. Its label and the
/// labels of word values come from `LibretroLocale`; numeric values such as
/// resolutions are shown as they are.
class LibretroCuratedSetting {
  const LibretroCuratedSetting(this.key, this.labelKey, this.values,
      {this.valueLabelKeys = const <String, String>{}, this.inGameMenu = true});

  final String key;
  final String labelKey;
  final List<String> values;
  final Map<String, String> valueLabelKeys;

  /// Offered by the in-game menu, whose footer says the settings apply
  /// after "Restart game". False for a setting that needs a new session
  /// (the 3DS model): it stays on its console page, with its own hint.
  final bool inGameMenu;
}

class LibretroCore {
  const LibretroCore({
    required this.id,
    required this.displayName,
    required this.extensions,
    this.biosAnyOf = const <String>[],
    this.biosAllOf = const <String>[],
    this.preferredHardwareContext = LibretroHardwareContext.none,
    this.optionDefaults = const <String, String>{},
    this.noJitOverrides = const <String, String>{},
    this.lockedOptions = const <String, String>{},
    this.settings = const <LibretroCuratedSetting>[],
    this.resolution,
  });

  /// Framework name without the `_libretro` suffix.
  final String id;

  /// Product name, never translated.
  final String displayName;

  /// Extensions the core opens; `.zip` archives are extracted by the host.
  final Set<String> extensions;

  /// At least one of these files must exist in the System folder.
  final List<String> biosAnyOf;

  /// Every one of these files must exist in the System folder (FreeIntv
  /// loads any game without them and only draws an error screen).
  final List<String> biosAllOf;
  final int preferredHardwareContext;
  final Map<String, String> optionDefaults;
  final Map<String, String> noJitOverrides;

  /// Core options NeoStation imposes for the whole session, before
  /// `retro_init`, and shows read-only: the screen crop, the touch screen and
  /// the controls of dual-screen consoles depend on them.
  final Map<String, String> lockedOptions;
  final List<LibretroCuratedSetting> settings;

  /// Internal resolution option of the pinned build (Build 455), null for a
  /// core that draws at the console's own resolution (2D cores). The
  /// in-game menu reads the option the running core declares instead.
  final LibretroResolutionDeclaration? resolution;
}

class LibretroSystemBinding {
  const LibretroSystemBinding({
    required this.coreId,
    required this.console,
    this.alternatives = const <String>[],
    this.achievementsConsoleId = 0,
  });

  final String coreId;

  /// NeoStation console of the system (key of [LibretroCoreCatalog.consoles]):
  /// skins, screen format, shaders and controls belong to the console, not
  /// to the core.
  final String console;
  final List<String> alternatives;

  /// RetroAchievements console id (rc_consoles.h), 0 when unsupported.
  final int achievementsConsoleId;
}

/// A console as NeoStation's embedded engine presents it: the key of its
/// frontend settings and skins, whatever core or system folder runs it.
class LibretroConsole {
  const LibretroConsole({
    required this.id,
    required this.name,
    required this.width,
    required this.height,
    required this.importSystem,
    this.catalogSystems = const <String>[],
    this.regions = const <String, List<double>>{},
  });

  final String id;

  /// Product name, never translated.
  final String name;

  /// Nominal picture size in console pixels; 0 x 0 when it varies (arcade
  /// boards), so no skin crop is ever trusted for it.
  final int width;
  final int height;

  /// System folder (an `assets/systems` id bound to this console) that games
  /// imported for the console go to.
  final String importSystem;

  /// Lowercase `systems` codes of the Provenance skin catalog for the console.
  final List<String> catalogSystems;

  /// Dual-screen consoles: normalized `[x, y, width, height]` of the "top"
  /// and "bottom" screens in the core picture (the core renders them
  /// stacked).
  final Map<String, List<double>> regions;

  bool get isDualScreen => regions.isNotEmpty;

  /// Entry of [LibretroCoreCatalog.consoleGeometry] for this console.
  Map<String, Object> get geometry => <String, Object>{
        'size': <int>[width, height],
        if (regions.isNotEmpty) 'regions': regions,
      };

  /// Folder the console's games are imported into, named as the library
  /// scanner knows the import system ([LibretroCoreCatalog.importFolderFor]).
  String get importFolder => LibretroCoreCatalog.importFolderFor(importSystem);
}

abstract final class LibretroCoreCatalog {
  static const Map<String, LibretroCore> cores = <String, LibretroCore>{
    'nestopia': LibretroCore(
      id: 'nestopia',
      displayName: 'Nestopia',
      extensions: {'nes', 'fds', 'unf', 'unif', 'nsf'},
    ),
    'snes9x': LibretroCore(
      id: 'snes9x',
      displayName: 'Snes9x',
      extensions: {'smc', 'sfc', 'swc', 'fig', 'bs', 'st'},
    ),
    'gambatte': LibretroCore(
      id: 'gambatte',
      displayName: 'Gambatte',
      extensions: {'gb', 'gbc', 'dmg'},
    ),
    'mgba': LibretroCore(
      id: 'mgba',
      displayName: 'mGBA',
      extensions: {'gb', 'gbc', 'gba'},
    ),
    'genesis_plus_gx': LibretroCore(
      id: 'genesis_plus_gx',
      displayName: 'Genesis Plus GX',
      extensions: {
        'mdx', 'md', 'smd', 'gen', 'bin', 'cue', 'iso', 'sms', 'bms', 'gg',
        'sg', '68k', 'sgd', 'chd', 'm3u',
      },
    ),
    'genesis_plus_gx_wide': LibretroCore(
      id: 'genesis_plus_gx_wide',
      displayName: 'Genesis Plus GX Wide',
      extensions: {
        'mdx', 'md', 'smd', 'gen', 'bin', 'cue', 'iso', 'sms', 'bms', 'gg',
        'sg', '68k', 'sgd', 'chd', 'm3u',
      },
    ),
    'picodrive': LibretroCore(
      id: 'picodrive',
      displayName: 'PicoDrive',
      extensions: {
        'bin', 'gen', 'smd', 'md', '32x', 'cue', 'iso', 'chd', 'sms', 'gg',
        'sg', 'sc', 'm3u', '68k', 'sgd', 'pco',
      },
    ),
    'fbneo': LibretroCore(
      id: 'fbneo',
      displayName: 'FinalBurn Neo',
      extensions: {'zip', '7z', 'cue', 'ccd'},
    ),
    'desmume': LibretroCore(
      id: 'desmume',
      displayName: 'DeSmuME',
      extensions: {'nds', 'ids', 'bin'},
      noJitOverrides: {'desmume_cpu_mode': 'interpreter'},
      resolution: LibretroResolutionDeclaration(
        libraryName: 'DeSmuME',
        key: 'desmume_internal_resolution',
        values: [
          '256x192', '512x384', '768x576', '1024x768', '1280x960', '1536x1152',
          '1792x1344', '2048x1536', '2304x1728', '2560x1920',
        ],
        coreDefault: '256x192',
      ),
      // The core always renders both screens stacked with no gap and reads
      // RETRO_DEVICE_POINTER as a touch screen (its default "mouse" pointer
      // type ignores it); NeoStation crops and places the two screens
      // itself, so DeSmuME's own screen layout is no longer offered.
      lockedOptions: {
        'desmume_screens_layout': 'top/bottom',
        'desmume_screens_gap': '0',
        'desmume_pointer_type': 'touch',
        'desmume_pointer_mouse': 'enabled',
      },
    ),
    'mupen64plus_next': LibretroCore(
      id: 'mupen64plus_next',
      displayName: 'Mupen64Plus-Next',
      extensions: {'n64', 'v64', 'z64', 'ndd', 'bin', 'u1'},
      preferredHardwareContext: LibretroHardwareContext.openGLES3,
      noJitOverrides: {'mupen64plus-cpucore': 'cached_interpreter'},
      // GLideN64's 4:3 viewport, read when the game starts. Build 455: the
      // "Resolution and picture" page replaces the curated setting.
      resolution: LibretroResolutionDeclaration(
        libraryName: 'Mupen64Plus-Next',
        key: 'mupen64plus-43screensize',
        values: [
          '320x240', '640x480', '960x720', '1280x960', '1440x1080', '1600x1200',
          '1920x1440', '2240x1680', '2560x1920', '2880x2160', '3200x2400',
          '3520x2640', '3840x2880',
        ],
        coreDefault: '640x480',
      ),
    ),
    'mednafen_psx_hw': LibretroCore(
      id: 'mednafen_psx_hw',
      displayName: 'Beetle PSX HW',
      extensions: {'cue', 'toc', 'm3u', 'ccd', 'exe', 'pbp', 'chd', 'bin'},
      biosAnyOf: ['scph5500.bin', 'scph5501.bin', 'scph5502.bin'],
      // Vulkan (MoltenVK): Beetle's renderer choice (rhi_intf_open, "Hardware
      // (Auto)") opens OpenGL only for an OpenGL or OpenGL Core preference and
      // Vulkan for a Vulkan one, so the OpenGL ES 3 preference NeoStation gave
      // until the Build 488 always ended in its software renderer. Vulkan is
      // also the renderer its HD texture replacement is documented for. A
      // Vulkan context that cannot be created leaves the core on its software
      // renderer (the session reports it); a stored "software" choice wins.
      preferredHardwareContext: LibretroHardwareContext.vulkan,
      // HD texture packs (Track + Replace Textures, switched per game from the
      // HD textures page): read from <Saves>/Beetle PSX HW, never written
      // beside the user's games; no dump in normal use; decoded-texture
      // caches bounded for an iPhone (the core's 3 GB / 2 GB defaults are
      // desktop budgets) and filled on demand rather than every palette at once.
      lockedOptions: {
        'beetle_psx_hw_texture_directory': 'save',
        'beetle_psx_hw_dump_textures': 'disabled',
        'beetle_psx_hw_hd_caching_method': 'lazy',
        'beetle_psx_hw_hd_cache_vram_budget': '512',
        'beetle_psx_hw_hd_cache_ram_budget': '512',
      },
      // No no-JIT override: the pinned iOS builds of both Beetle PSX cores
      // have no Lightrec dynarec option, and test/libretro_core_options_test.py
      // flags one if a future core build adds it. Build 455: the "Resolution
      // and picture" page replaces the curated resolution setting.
      resolution: LibretroResolutionDeclaration(
        libraryName: 'Beetle PSX HW',
        key: 'beetle_psx_hw_internal_resolution',
        values: ['1x(native)', '2x', '4x', '8x', '16x'],
        coreDefault: '1x(native)',
      ),
    ),
    'mednafen_psx': LibretroCore(
      id: 'mednafen_psx',
      displayName: 'Beetle PSX',
      extensions: {'cue', 'toc', 'm3u', 'ccd', 'exe', 'pbp', 'chd', 'bin'},
      biosAnyOf: ['scph5500.bin', 'scph5501.bin', 'scph5502.bin'],
      // The software renderer scales the picture too.
      resolution: LibretroResolutionDeclaration(
        libraryName: 'Beetle PSX',
        key: 'beetle_psx_internal_resolution',
        values: ['1x(native)', '2x', '4x', '8x', '16x'],
        coreDefault: '1x(native)',
      ),
    ),
    'ppsspp': LibretroCore(
      id: 'ppsspp',
      displayName: 'PPSSPP',
      extensions: {'elf', 'iso', 'cso', 'prx', 'pbp', 'chd'},
      preferredHardwareContext: LibretroHardwareContext.openGLES3,
      noJitOverrides: {'ppsspp_cpu_core': 'IR JIT'},
      // Build 455: native by default (the 960x544 NeoStation default is
      // gone; a value the user chose stays), set on the "Resolution and
      // picture" page instead of a curated setting.
      resolution: LibretroResolutionDeclaration(
        libraryName: 'PPSSPP',
        key: 'ppsspp_internal_resolution',
        values: [
          '480x272', '960x544', '1440x816', '1920x1088', '2400x1360', '2880x1632',
          '3360x1904', '3840x2176', '4320x2448', '4800x2720',
        ],
        coreDefault: '480x272',
      ),
    ),
    'azahar': LibretroCore(
      id: 'azahar',
      displayName: 'Azahar',
      extensions: {
        '3ds', '3dsx', 'z3dsx', 'elf', 'axf', 'cci', 'zcci', 'cxi', 'zcxi',
        'app',
      },
      preferredHardwareContext: LibretroHardwareContext.vulkan,
      // Official 2127.0-alpha1 iOS builds compile CPU and shader JIT off;
      // they no longer declare either JIT option. FastInterp uses no JIT.
      // A stored disabled choice wins over this default on the next launch.
      optionDefaults: {'citra_use_fastinterp': 'enabled'},
      resolution: LibretroResolutionDeclaration(
        libraryName: 'Azahar',
        key: 'citra_resolution_factor',
        values: [
          '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14',
          '15', '16', '17', '18',
        ],
        coreDefault: '1',
      ),
      // Top screen above the centred bottom screen, never swapped by the
      // core; the C-stick stays a stick instead of also driving a touch
      // cursor; stereoscopic modes would change the picture NeoStation crops.
      // The core's user folder (keys, NAND titles, system save) stays under
      // the libretro save directory, Files › NeoStation › Libretro › Saves,
      // where the Nintendo 3DS page reads and installs it.
      lockedOptions: {
        'citra_layout_option': 'default',
        'citra_swap_screen': 'Top',
        'citra_analog_function': 'c_stick',
        'citra_render_3d': 'off',
        'citra_use_libretro_save_path': 'LibRetro Default',
      },
      // System region, language and model, also offered by the Nintendo 3DS
      // page. The core applies the language only while the region is Auto,
      // at the next launch or after "Restart game"; the model needs a new
      // session (the reset runs before the options are read again), so the
      // in-game menu, whose footer promises "after Restart game", leaves it
      // to the Nintendo 3DS page. Raw values are the core's own.
      settings: [
        LibretroCuratedSetting(
          'citra_region_value',
          'setting3dsRegion',
          ['Auto', 'Japan', 'USA', 'Europe', 'Australia', 'China', 'Korea', 'Taiwan'],
          valueLabelKeys: {
            'Auto': 'region3dsAuto',
            'Japan': 'region3dsJapan',
            'USA': 'region3dsUsa',
            'Europe': 'region3dsEurope',
            'Australia': 'region3dsAustralia',
            'China': 'region3dsChina',
            'Korea': 'region3dsKorea',
            'Taiwan': 'region3dsTaiwan',
          },
        ),
        LibretroCuratedSetting(
          'citra_language_value',
          'setting3dsLanguage',
          [
            'English', 'Japanese', 'French', 'Spanish', 'German', 'Italian',
            'Dutch', 'Portuguese', 'Russian', 'Korean', 'Traditional Chinese',
            'Simplified Chinese',
          ],
          valueLabelKeys: {
            'English': 'lang3dsEnglish',
            'Japanese': 'lang3dsJapanese',
            'French': 'lang3dsFrench',
            'Spanish': 'lang3dsSpanish',
            'German': 'lang3dsGerman',
            'Italian': 'lang3dsItalian',
            'Dutch': 'lang3dsDutch',
            'Portuguese': 'lang3dsPortuguese',
            'Russian': 'lang3dsRussian',
            'Korean': 'lang3dsKorean',
            'Traditional Chinese': 'lang3dsZhHant',
            'Simplified Chinese': 'lang3dsZhHans',
          },
        ),
        LibretroCuratedSetting(
          'citra_is_new_3ds',
          'setting3dsModel',
          ['New 3DS', 'Old 3DS'],
          valueLabelKeys: {'New 3DS': 'model3dsNew', 'Old 3DS': 'model3dsOld'},
          inGameMenu: false,
        ),
        // The label explicitly requires closing and relaunching the game:
        // retro_reset does not re-read a paused menu choice before CPU init.
        LibretroCuratedSetting(
          'citra_use_fastinterp',
          'settingFastInterpreter',
          ['enabled', 'disabled'],
          valueLabelKeys: {
            'enabled': 'fastInterpreterEnabled',
            'disabled': 'fastInterpreterDisabled',
          },
        ),
      ],
    ),
    // Lot 1 of the consoles of the Consoles tab that only the RetroArch app
    // ran (docs/libretro-consoles-lot1.md): software cores of RetroArch's
    // iOS App Store list, no JIT, no hardware context.
    'mednafen_pce_fast': LibretroCore(
      id: 'mednafen_pce_fast',
      displayName: 'Beetle PCE Fast',
      extensions: {'pce', 'cue', 'ccd', 'chd', 'toc', 'm3u'},
    ),
    'mednafen_wswan': LibretroCore(
      id: 'mednafen_wswan',
      displayName: 'Beetle WonderSwan',
      extensions: {'ws', 'wsc', 'pc2', 'pcv2'},
    ),
    'mednafen_ngp': LibretroCore(
      id: 'mednafen_ngp',
      displayName: 'Beetle NeoPop',
      extensions: {'ngp', 'ngc', 'ngpc', 'npc'},
    ),
    'handy': LibretroCore(
      id: 'handy',
      displayName: 'Handy',
      extensions: {'lnx', 'lyx', 'o'},
    ),
    'mednafen_vb': LibretroCore(
      id: 'mednafen_vb',
      displayName: 'Beetle VB',
      extensions: {'vb', 'vboy', 'bin'},
    ),
    'stella': LibretroCore(
      id: 'stella',
      displayName: 'Stella',
      extensions: {'a26', 'bin'},
    ),
    'prosystem': LibretroCore(
      id: 'prosystem',
      displayName: 'ProSystem',
      extensions: {'a78', 'bin', 'cdf'},
    ),
    'a5200': LibretroCore(
      id: 'a5200',
      displayName: 'a5200',
      extensions: {'a52', 'bin'},
    ),
    'gearcoleco': LibretroCore(
      id: 'gearcoleco',
      displayName: 'Gearcoleco',
      extensions: {'col', 'cv', 'bin', 'rom'},
      biosAnyOf: ['colecovision.rom'],
    ),
    'pokemini': LibretroCore(
      id: 'pokemini',
      displayName: 'PokeMini',
      extensions: {'min'},
    ),
    'gw': LibretroCore(
      id: 'gw',
      displayName: 'Game & Watch',
      extensions: {'mgw'},
    ),
    'sameduck': LibretroCore(
      id: 'sameduck',
      displayName: 'SameDuck',
      extensions: {'bin', 'duck'},
    ),
    'potator': LibretroCore(
      id: 'potator',
      displayName: 'Potator',
      extensions: {'bin', 'sv'},
    ),
    'ardens': LibretroCore(
      id: 'ardens',
      displayName: 'Ardens',
      extensions: {'hex', 'arduboy'},
    ),
    'wasm4': LibretroCore(
      id: 'wasm4',
      displayName: 'WASM-4',
      extensions: {'wasm'},
      // The core's default "callback" audio is only heard through
      // RETRO_ENVIRONMENT_SET_AUDIO_CALLBACK, which the host does not offer:
      // its "normal" audio goes through the batch callback like every core.
      lockedOptions: {'wasm4_audio_type': 'normal'},
    ),
    'uzem': LibretroCore(
      id: 'uzem',
      displayName: 'Uzem',
      extensions: {'uze'},
    ),
    // Lot 2 (docs/libretro-consoles-lot2.md).
    'freechaf': LibretroCore(
      id: 'freechaf',
      displayName: 'FreeChaF',
      extensions: {'chf', 'bin'},
    ),
    'freeintv': LibretroCore(
      id: 'freeintv',
      displayName: 'FreeIntv',
      extensions: {'int', 'bin', 'rom'},
      biosAllOf: ['exec.bin', 'grom.bin'],
    ),
    'o2em': LibretroCore(
      id: 'o2em',
      displayName: 'O2EM',
      extensions: {'bin'},
      // The core's default BIOS option; c52.bin, g7400.bin and jopac.bin are
      // chosen in its options.
      biosAnyOf: ['o2rom.bin'],
    ),
    'mednafen_pcfx': LibretroCore(
      id: 'mednafen_pcfx',
      displayName: 'Beetle PC-FX',
      extensions: {'cue', 'ccd', 'toc', 'chd', 'm3u'},
      biosAnyOf: ['pcfx.rom'],
    ),
  };

  static const Map<String, LibretroSystemBinding> systems =
      <String, LibretroSystemBinding>{
    'nes': LibretroSystemBinding(coreId: 'nestopia', console: 'nes', achievementsConsoleId: 7),
    'fc': LibretroSystemBinding(coreId: 'nestopia', console: 'nes', achievementsConsoleId: 7),
    'nes-hacks': LibretroSystemBinding(coreId: 'nestopia', console: 'nes', achievementsConsoleId: 7),
    'fds': LibretroSystemBinding(coreId: 'nestopia', console: 'nes', achievementsConsoleId: 7),
    'snes': LibretroSystemBinding(coreId: 'snes9x', console: 'snes', achievementsConsoleId: 3),
    'sfc': LibretroSystemBinding(coreId: 'snes9x', console: 'snes', achievementsConsoleId: 3),
    'snes-hacks': LibretroSystemBinding(coreId: 'snes9x', console: 'snes', achievementsConsoleId: 3),
    'sfc-hacks': LibretroSystemBinding(coreId: 'snes9x', console: 'snes', achievementsConsoleId: 3),
    'satellaview': LibretroSystemBinding(coreId: 'snes9x', console: 'snes', achievementsConsoleId: 3),
    'gb': LibretroSystemBinding(coreId: 'gambatte', console: 'gb', alternatives: ['mgba'], achievementsConsoleId: 4),
    'gb-hacks': LibretroSystemBinding(coreId: 'gambatte', console: 'gb', alternatives: ['mgba'], achievementsConsoleId: 4),
    'gbc': LibretroSystemBinding(coreId: 'gambatte', console: 'gbc', alternatives: ['mgba'], achievementsConsoleId: 6),
    'gbc-hacks': LibretroSystemBinding(coreId: 'gambatte', console: 'gbc', alternatives: ['mgba'], achievementsConsoleId: 6),
    'gba': LibretroSystemBinding(coreId: 'mgba', console: 'gba', achievementsConsoleId: 5),
    'gba-hacks': LibretroSystemBinding(coreId: 'mgba', console: 'gba', achievementsConsoleId: 5),
    'md': LibretroSystemBinding(coreId: 'genesis_plus_gx', console: 'md', alternatives: ['genesis_plus_gx_wide', 'picodrive'], achievementsConsoleId: 1),
    'genesis': LibretroSystemBinding(coreId: 'genesis_plus_gx', console: 'md', alternatives: ['genesis_plus_gx_wide', 'picodrive'], achievementsConsoleId: 1),
    'md-hacks': LibretroSystemBinding(coreId: 'genesis_plus_gx', console: 'md', alternatives: ['genesis_plus_gx_wide', 'picodrive'], achievementsConsoleId: 1),
    'gen-hacks': LibretroSystemBinding(coreId: 'genesis_plus_gx', console: 'md', alternatives: ['genesis_plus_gx_wide', 'picodrive'], achievementsConsoleId: 1),
    'mcd': LibretroSystemBinding(coreId: 'genesis_plus_gx', console: 'mcd', alternatives: ['picodrive'], achievementsConsoleId: 9),
    'scd': LibretroSystemBinding(coreId: 'genesis_plus_gx', console: 'mcd', alternatives: ['picodrive'], achievementsConsoleId: 9),
    'sms': LibretroSystemBinding(coreId: 'genesis_plus_gx', console: 'sms', alternatives: ['picodrive'], achievementsConsoleId: 11),
    'mark3': LibretroSystemBinding(coreId: 'genesis_plus_gx', console: 'sms', alternatives: ['picodrive'], achievementsConsoleId: 11),
    'gg': LibretroSystemBinding(coreId: 'genesis_plus_gx', console: 'gg', alternatives: ['picodrive'], achievementsConsoleId: 15),
    'gg-hacks': LibretroSystemBinding(coreId: 'genesis_plus_gx', console: 'gg', alternatives: ['picodrive'], achievementsConsoleId: 15),
    'sg1k': LibretroSystemBinding(coreId: 'genesis_plus_gx', console: 'sg1000', achievementsConsoleId: 33),
    '32x': LibretroSystemBinding(coreId: 'picodrive', console: '32x', achievementsConsoleId: 10),
    'pico': LibretroSystemBinding(coreId: 'picodrive', console: 'md'),
    'arc': LibretroSystemBinding(coreId: 'fbneo', console: 'arcade', achievementsConsoleId: 27),
    'fbneo': LibretroSystemBinding(coreId: 'fbneo', console: 'arcade', achievementsConsoleId: 27),
    'cps1': LibretroSystemBinding(coreId: 'fbneo', console: 'arcade', achievementsConsoleId: 27),
    'cps2': LibretroSystemBinding(coreId: 'fbneo', console: 'arcade', achievementsConsoleId: 27),
    'cps3': LibretroSystemBinding(coreId: 'fbneo', console: 'arcade', achievementsConsoleId: 27),
    'neogeo': LibretroSystemBinding(coreId: 'fbneo', console: 'arcade', achievementsConsoleId: 27),
    'ds': LibretroSystemBinding(coreId: 'desmume', console: 'nds', achievementsConsoleId: 18),
    'n64': LibretroSystemBinding(coreId: 'mupen64plus_next', console: 'n64', achievementsConsoleId: 2),
    'ps1': LibretroSystemBinding(coreId: 'mednafen_psx_hw', console: 'psx', alternatives: ['mednafen_psx'], achievementsConsoleId: 12),
    'psp': LibretroSystemBinding(coreId: 'ppsspp', console: 'psp', achievementsConsoleId: 41),
    'pspminis': LibretroSystemBinding(coreId: 'ppsspp', console: 'psp', achievementsConsoleId: 41),
    '3ds': LibretroSystemBinding(coreId: 'azahar', console: '3ds', achievementsConsoleId: 62),
    'pce': LibretroSystemBinding(coreId: 'mednafen_pce_fast', console: 'pce', achievementsConsoleId: 8),
    'tg16': LibretroSystemBinding(coreId: 'mednafen_pce_fast', console: 'tg16', achievementsConsoleId: 8),
    'pccd': LibretroSystemBinding(coreId: 'mednafen_pce_fast', console: 'pccd', achievementsConsoleId: 76),
    'tgcd': LibretroSystemBinding(coreId: 'mednafen_pce_fast', console: 'tgcd', achievementsConsoleId: 76),
    'ws': LibretroSystemBinding(coreId: 'mednafen_wswan', console: 'ws', achievementsConsoleId: 53),
    'wsc': LibretroSystemBinding(coreId: 'mednafen_wswan', console: 'wsc', achievementsConsoleId: 53),
    'ngp': LibretroSystemBinding(coreId: 'mednafen_ngp', console: 'ngp', achievementsConsoleId: 14),
    'ngpc': LibretroSystemBinding(coreId: 'mednafen_ngp', console: 'ngpc', achievementsConsoleId: 14),
    'lynx': LibretroSystemBinding(coreId: 'handy', console: 'lynx', achievementsConsoleId: 13),
    'vb': LibretroSystemBinding(coreId: 'mednafen_vb', console: 'vb', achievementsConsoleId: 28),
    '2600': LibretroSystemBinding(coreId: 'stella', console: '2600', achievementsConsoleId: 25),
    '7800': LibretroSystemBinding(coreId: 'prosystem', console: '7800', achievementsConsoleId: 51),
    '5200': LibretroSystemBinding(coreId: 'a5200', console: '5200', achievementsConsoleId: 50),
    'cv': LibretroSystemBinding(coreId: 'gearcoleco', console: 'cv', achievementsConsoleId: 44),
    'mini': LibretroSystemBinding(coreId: 'pokemini', console: 'mini', achievementsConsoleId: 24),
    'gw': LibretroSystemBinding(coreId: 'gw', console: 'gw', achievementsConsoleId: 60),
    'duck': LibretroSystemBinding(coreId: 'sameduck', console: 'duck', achievementsConsoleId: 69),
    'wsv': LibretroSystemBinding(coreId: 'potator', console: 'wsv', achievementsConsoleId: 63),
    'ard': LibretroSystemBinding(coreId: 'ardens', console: 'ard', achievementsConsoleId: 71),
    'wasm4': LibretroSystemBinding(coreId: 'wasm4', console: 'wasm4', achievementsConsoleId: 72),
    'uze': LibretroSystemBinding(coreId: 'uzem', console: 'uze', achievementsConsoleId: 80),
    'chf': LibretroSystemBinding(coreId: 'freechaf', console: 'chf', achievementsConsoleId: 57),
    'intv': LibretroSystemBinding(coreId: 'freeintv', console: 'intv', achievementsConsoleId: 45),
    'mo2': LibretroSystemBinding(coreId: 'o2em', console: 'mo2', achievementsConsoleId: 23),
    'pcfx': LibretroSystemBinding(coreId: 'mednafen_pcfx', console: 'pcfx', achievementsConsoleId: 49),
  };

  /// The consoles of the embedded engine (17, the 21 of lot 1, then the 4 of
  /// lot 2), in the order of the native `+[LibretroInputMap consoles]`.
  static const Map<String, LibretroConsole> consoles = <String, LibretroConsole>{
    'nes': LibretroConsole(
      id: 'nes',
      name: 'NES',
      width: 256,
      height: 240,
      importSystem: 'nes',
      catalogSystems: ['nes'],
    ),
    'snes': LibretroConsole(
      id: 'snes',
      name: 'Super Nintendo',
      width: 256,
      height: 224,
      importSystem: 'snes',
      catalogSystems: ['snes'],
    ),
    'gb': LibretroConsole(
      id: 'gb',
      name: 'Game Boy',
      width: 160,
      height: 144,
      importSystem: 'gb',
      // The catalog files Game Boy skins under "gbc".
      catalogSystems: ['gbc', 'gb'],
    ),
    'gbc': LibretroConsole(
      id: 'gbc',
      name: 'Game Boy Color',
      width: 160,
      height: 144,
      importSystem: 'gbc',
      catalogSystems: ['gbc'],
    ),
    'gba': LibretroConsole(
      id: 'gba',
      name: 'Game Boy Advance',
      width: 240,
      height: 160,
      importSystem: 'gba',
      catalogSystems: ['gba'],
    ),
    'md': LibretroConsole(
      id: 'md',
      name: 'Mega Drive / Genesis',
      width: 320,
      height: 224,
      importSystem: 'md',
      catalogSystems: ['genesis'],
    ),
    'mcd': LibretroConsole(
      id: 'mcd',
      name: 'Mega-CD / Sega CD',
      width: 320,
      height: 224,
      importSystem: 'mcd',
      catalogSystems: ['genesis', 'segacd'],
    ),
    '32x': LibretroConsole(
      id: '32x',
      name: '32X',
      width: 320,
      height: 224,
      importSystem: '32x',
      catalogSystems: ['genesis', 'sega32x', '32x'],
    ),
    'sms': LibretroConsole(
      id: 'sms',
      name: 'Master System',
      width: 256,
      height: 192,
      importSystem: 'sms',
      catalogSystems: ['mastersystem'],
    ),
    'gg': LibretroConsole(
      id: 'gg',
      name: 'Game Gear',
      width: 160,
      height: 144,
      importSystem: 'gg',
      catalogSystems: ['gamegear'],
    ),
    'sg1000': LibretroConsole(
      id: 'sg1000',
      name: 'SG-1000',
      width: 256,
      height: 192,
      importSystem: 'sg1k',
      catalogSystems: ['sg1000'],
    ),
    'arcade': LibretroConsole(
      id: 'arcade',
      name: 'Arcade',
      width: 0,
      height: 0,
      importSystem: 'arc',
      catalogSystems: ['mame'],
    ),
    'nds': LibretroConsole(
      id: 'nds',
      name: 'Nintendo DS',
      width: 256,
      height: 384,
      importSystem: 'ds',
      catalogSystems: ['nds'],
      regions: {
        'top': [0, 0, 1, 0.5],
        'bottom': [0, 0.5, 1, 0.5],
      },
    ),
    'n64': LibretroConsole(
      id: 'n64',
      name: 'Nintendo 64',
      width: 320,
      height: 240,
      importSystem: 'n64',
      catalogSystems: ['n64'],
    ),
    'psx': LibretroConsole(
      id: 'psx',
      name: 'PlayStation',
      width: 320,
      height: 240,
      importSystem: 'ps1',
      catalogSystems: ['psx'],
    ),
    'psp': LibretroConsole(
      id: 'psp',
      name: 'PlayStation Portable',
      width: 480,
      height: 272,
      importSystem: 'psp',
      catalogSystems: ['psp'],
    ),
    '3ds': LibretroConsole(
      id: '3ds',
      name: 'Nintendo 3DS',
      width: 400,
      height: 480,
      importSystem: '3ds',
      catalogSystems: ['threeds', '3ds'],
      // 400x240 top screen above the 320x240 bottom screen, centred.
      regions: {
        'top': [0, 0, 1, 0.5],
        'bottom': [0.1, 0.5, 0.8, 0.5],
      },
    ),
    // Lot 1 (docs/libretro-consoles-lot1.md): the consoles of the Consoles
    // tab that only the RetroArch app ran, with their ids and product names
    // unchanged. 0 x 0 where the core's picture size varies by game or by
    // TV standard (no skin crop is trusted then).
    // Beetle PCE Fast: 256 to 512 pixels wide depending on the game.
    'pce': LibretroConsole(
      id: 'pce',
      name: 'PC Engine',
      width: 0,
      height: 0,
      importSystem: 'pce',
      catalogSystems: ['pce'],
    ),
    'tg16': LibretroConsole(
      id: 'tg16',
      name: 'TurboGrafx-16',
      width: 0,
      height: 0,
      importSystem: 'tg16',
      catalogSystems: ['pce'],
    ),
    'pccd': LibretroConsole(
      id: 'pccd',
      name: 'PC Engine-CD',
      width: 0,
      height: 0,
      importSystem: 'pccd',
      catalogSystems: ['pce'],
    ),
    'tgcd': LibretroConsole(
      id: 'tgcd',
      name: 'TurboGrafx-CD',
      width: 0,
      height: 0,
      importSystem: 'tgcd',
      catalogSystems: ['pce'],
    ),
    'ws': LibretroConsole(
      id: 'ws',
      name: 'WonderSwan',
      width: 224,
      height: 144,
      importSystem: 'ws',
    ),
    'wsc': LibretroConsole(
      id: 'wsc',
      name: 'WonderSwan Color',
      width: 224,
      height: 144,
      importSystem: 'wsc',
    ),
    'ngp': LibretroConsole(
      id: 'ngp',
      name: 'NeoGeo Pocket',
      width: 160,
      height: 152,
      importSystem: 'ngp',
    ),
    'ngpc': LibretroConsole(
      id: 'ngpc',
      name: 'NeoGeo Pocket Color',
      width: 160,
      height: 152,
      importSystem: 'ngpc',
    ),
    'lynx': LibretroConsole(
      id: 'lynx',
      name: 'Atari Lynx',
      width: 160,
      height: 102,
      importSystem: 'lynx',
      catalogSystems: ['lynx'],
    ),
    'vb': LibretroConsole(
      id: 'vb',
      name: 'Virtual Boy',
      width: 384,
      height: 224,
      importSystem: 'vb',
      catalogSystems: ['virtualboy'],
    ),
    // Stella: 228 lines in NTSC, 274 in PAL.
    '2600': LibretroConsole(
      id: '2600',
      name: 'Atari 2600',
      width: 0,
      height: 0,
      importSystem: '2600',
    ),
    // ProSystem: 223 lines in NTSC, 272 in PAL.
    '7800': LibretroConsole(
      id: '7800',
      name: 'Atari 7800',
      width: 0,
      height: 0,
      importSystem: '7800',
    ),
    '5200': LibretroConsole(
      id: '5200',
      name: 'Atari 5200',
      width: 320,
      height: 224,
      importSystem: '5200',
    ),
    'cv': LibretroConsole(
      id: 'cv',
      name: 'ColecoVision',
      width: 256,
      height: 192,
      importSystem: 'cv',
    ),
    // PokeMini draws 96 x 64 scaled four times.
    'mini': LibretroConsole(
      id: 'mini',
      name: 'Pokémon Mini',
      width: 96,
      height: 64,
      importSystem: 'mini',
    ),
    // Each Game & Watch game has its own background size.
    'gw': LibretroConsole(
      id: 'gw',
      name: 'Game & Watch',
      width: 0,
      height: 0,
      importSystem: 'gw',
    ),
    'duck': LibretroConsole(
      id: 'duck',
      name: 'Mega Duck',
      width: 160,
      height: 144,
      importSystem: 'duck',
    ),
    'wsv': LibretroConsole(
      id: 'wsv',
      name: 'Watara Supervision',
      width: 160,
      height: 160,
      importSystem: 'wsv',
    ),
    'ard': LibretroConsole(
      id: 'ard',
      name: 'Arduboy',
      width: 128,
      height: 64,
      importSystem: 'ard',
    ),
    'wasm4': LibretroConsole(
      id: 'wasm4',
      name: 'WASM-4',
      width: 160,
      height: 160,
      importSystem: 'wasm4',
    ),
    // Uzem draws 720 x 224 frames shown at 630:448.
    'uze': LibretroConsole(
      id: 'uze',
      name: 'Uzebox',
      width: 0,
      height: 0,
      importSystem: 'uze',
    ),
    // Lot 2. FreeChaF draws the 102 x 64 picture three times larger.
    'chf': LibretroConsole(
      id: 'chf',
      name: 'Fairchild Channel F',
      width: 306,
      height: 192,
      importSystem: 'chf',
    ),
    'intv': LibretroConsole(
      id: 'intv',
      name: 'Intellivision',
      width: 352,
      height: 224,
      importSystem: 'intv',
    ),
    // O2EM crops the overscan or not (option).
    'mo2': LibretroConsole(
      id: 'mo2',
      name: 'Magnavox Odyssey 2',
      width: 0,
      height: 0,
      importSystem: 'mo2',
    ),
    // The PC-FX changes its dot clock between games.
    'pcfx': LibretroConsole(
      id: 'pcfx',
      name: 'NEC PC-FX',
      width: 0,
      height: 0,
      importSystem: 'pcfx',
    ),
  };

  /// Bound systems whose id is not one of the folder names the library
  /// scanner recognizes for them (`assets/systems/<id>.json` `folders`):
  /// their games are imported into this folder instead, so they appear.
  /// Before, games imported for the two hack playlists went to
  /// `roms/gb-hacks` and `roms/sfc-hacks`, which the scanner never lists.
  static const Map<String, String> _importFolders = <String, String>{
    'duck': 'megaduck',
    'gb-hacks': 'gbh',
    'sfc-hacks': 'sfch',
  };

  /// Folder name (lowercase) games of a bound system are copied into.
  static String importFolderFor(String system) {
    final key = system.toLowerCase();
    return _importFolders[key] ?? key;
  }

  static LibretroSystemBinding? bindingFor(String folderName) =>
      systems[folderName.toLowerCase()];

  static bool handles(String folderName) =>
      systems.containsKey(folderName.toLowerCase());

  /// Console of a bound system folder, null when the engine does not run it.
  static LibretroConsole? consoleFor(String folderName) {
    final binding = bindingFor(folderName);
    return binding == null ? null : consoles[binding.console];
  }

  /// Geometry of every console for the native skin parser and session
  /// (`+[LibretroSkin skinWithDirectory:consoleGeometry:errorCode:]`):
  /// `{console: {"size": [w, h], "regions": {"top": [x, y, w, h], ...}}}`.
  static Map<String, Map<String, Object>> consoleGeometry() =>
      <String, Map<String, Object>>{
        for (final console in consoles.values) console.id: console.geometry,
      };

  /// Catalog key of a system: its id when the engine runs it, else the first
  /// folder alias it runs, else the folder name. A system copy named after
  /// an alias folder ("n3ds", "PlayStation Portable") keeps its canonical id,
  /// so it still launches with the embedded core and keeps its preferences.
  static String canonicalSystem({
    String? id,
    Iterable<String> folders = const <String>[],
    required String folderName,
  }) {
    if (id != null && handles(id)) return id.toLowerCase();
    for (final folder in folders) {
      if (handles(folder)) return folder.toLowerCase();
    }
    return folderName.toLowerCase();
  }

  /// Default core first, then the alternatives a game may be switched to.
  static List<LibretroCore> coresFor(String folderName) {
    final binding = bindingFor(folderName);
    if (binding == null) return const <LibretroCore>[];
    return <String>[binding.coreId, ...binding.alternatives]
        .map((id) => cores[id])
        .whereType<LibretroCore>()
        .toList(growable: false);
  }

  /// Extensions accepted by the import picker for a system: what its cores
  /// open plus `.zip`. With [indexed] (the extensions the library scanner
  /// lists for the system, from its `assets/systems` definition), only those
  /// the scanner also indexes, so an imported game always appears.
  static Set<String> importExtensionsFor(String folderName, {Iterable<String>? indexed}) {
    final extensions = <String>{'zip'};
    for (final core in coresFor(folderName)) {
      extensions.addAll(core.extensions);
    }
    if (indexed == null) return extensions;
    final scanned = <String>{
      for (final extension in indexed) _bareExtension(extension),
    };
    return extensions.intersection(scanned);
  }

  static String _bareExtension(String extension) {
    final trimmed = extension.trim().toLowerCase();
    return trimmed.startsWith('.') ? trimmed.substring(1) : trimmed;
  }
}
