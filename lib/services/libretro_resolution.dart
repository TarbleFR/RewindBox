/// Internal resolution of the cores of the embedded libretro engine
/// (Build 455): which core option makes a core render the game at a higher
/// resolution, the scale of each of its values, and when a change applies.
///
/// Three things are kept apart, as the in-game "Resolution" page shows them:
/// - the internal resolution: the size at which the core itself draws the
///   game (3D cores mostly), set by a core option this file recognizes;
/// - the image enlargement: how NeoStation scales the core's picture to the
///   screen (screen format, upscaling shaders), whatever the core;
/// - the filtering: smoothing of that enlargement.
///
/// Recognition is extensible: [LibretroResolution.profiles] maps the option
/// names cores give the same setting (with when it applies and its limits),
/// and a core whose option is in no profile is still recognized by its name
/// or description ([LibretroResolution.genericKeyPattern],
/// [LibretroResolution.genericDescriptionPattern]) when its values name
/// scales. The native session applies the same rules to the options a core
/// really declares (`LibretroResolution.m`, configured by [nativeRules]);
/// `test/fixtures/libretro_resolution_cases.json` holds the cases both
/// readers of values must agree on.
library;

import 'dart:math' as math;

/// When a new internal resolution takes effect.
enum LibretroResolutionApply {
  /// The core reads the option again while the game runs and draws at the
  /// new resolution as soon as the game resumes.
  live,

  /// The core reads the option only when it starts the game: the game must
  /// be closed and launched again. Also the rule for an option recognized
  /// by its name only, whose behaviour is unknown.
  relaunch,
}

/// The renderer a core obtained from NeoStation once its content is loaded
/// (`rendererName` of the native session), as profiles name it.
abstract final class LibretroResolutionRenderer {
  /// An OpenGL ES context.
  static const String gles = 'gles';

  /// A Vulkan device (MoltenVK).
  static const String vulkan = 'vulkan';

  /// No hardware context: the core sends its frames to NeoStation.
  static const String software = 'software';
}

/// A resolution option known by name.
class LibretroResolutionProfile {
  const LibretroResolutionProfile({
    required this.keys,
    required this.apply,
    this.nativeSize,
    this.maxFactor = 0,
    this.requires = const <String, List<String>>{},
    this.renderers = const <String>[],
  });

  /// Names cores give this option (the same setting across cores or core
  /// versions), tried in this order.
  final List<String> keys;
  final LibretroResolutionApply apply;

  /// For options whose values are sizes ("640x480"): the size of the
  /// native resolution. Null: the smallest size the core declares.
  final List<int>? nativeSize;

  /// Highest factor offered, 0 for none beyond
  /// [LibretroResolution.maxDimension].
  final double maxFactor;

  /// Other options deciding whether this one is used, `{key: values}`: the
  /// option is used only while each of these keys has one of its values. A
  /// key the core does not declare is no condition.
  final Map<String, List<String>> requires;

  /// Renderers ([LibretroResolutionRenderer]) the core must have obtained
  /// for this profile to apply, checked once its content is loaded; empty:
  /// any. Before the content is loaded (the native resolution NeoStation
  /// sets by default) they are no condition.
  final List<String> renderers;

  Map<String, Object> toNative() => <String, Object>{
        'keys': keys,
        'apply': apply.name,
        'nativeSize': ?nativeSize,
        if (maxFactor > 0) 'maxFactor': maxFactor,
        if (requires.isNotEmpty) 'requires': requires,
        if (renderers.isNotEmpty) 'renderers': renderers,
      };
}

/// One value of a resolution option and the scale it names.
class LibretroResolutionChoice {
  const LibretroResolutionChoice({
    required this.value,
    required this.factor,
    this.width = 0,
    this.height = 0,
  });

  /// The core's own value, stored as is.
  final String value;

  /// 1 for the native resolution, 2 for twice it…
  final double factor;

  /// The size a value such as "960x544" names; 0 for a multiplier ("2x").
  final int width;
  final int height;

  bool get isNative => (factor - 1).abs() < 0.005;

  @override
  bool operator ==(Object other) =>
      other is LibretroResolutionChoice &&
      other.value == value &&
      other.factor == factor &&
      other.width == width &&
      other.height == height;

  @override
  int get hashCode => Object.hash(value, factor, width, height);

  @override
  String toString() => 'LibretroResolutionChoice($value, x$factor, ${width}x$height)';
}

/// What a value of a resolution option names.
class LibretroResolutionToken {
  const LibretroResolutionToken.factor(double this.factor)
      : width = 0,
        height = 0;
  const LibretroResolutionToken.size(this.width, this.height) : factor = null;

  /// A multiplier ("2x", "x2", "Native"), null for a size.
  final double? factor;
  final int width;
  final int height;

  bool get isSize => factor == null;
}

/// The internal resolution option of a packaged core as its pinned build
/// declares it (`test/libretro_core_options_test.py --cores` finds every
/// key, value and library name in the binary). The console settings offer
/// these values until the core's own declaration, read at a launch, is
/// known (`Config/Resolution/<core>.json`).
class LibretroResolutionDeclaration {
  const LibretroResolutionDeclaration({
    required this.libraryName,
    required this.key,
    required this.values,
    required this.coreDefault,
  });

  /// `library_name` of the core: its options are `Config/<library>.json`.
  final String libraryName;
  final String key;

  /// Every value the core declares, in its order.
  final List<String> values;

  /// The core's own default value.
  final String coreDefault;
}

abstract final class LibretroResolution {
  /// Options known by name, from the cores' own option headers (sources and
  /// lines in docs/libretro-resolution.md § 2). [LibretroResolutionApply.live]
  /// only where the core's source reads the option again during the game and
  /// redraws at the new size; every other profile, and every core NeoStation
  /// does not package, applies at the next launch. A key may have several
  /// profiles for different configurations of the core: the first describes
  /// the core's default configuration (the console settings use it), and a
  /// key named by a profile is never recognized generically (a profile whose
  /// conditions fail means no internal resolution, as with PPSSPP's
  /// software rendering, which forces 1x). [LibretroResolutionProfile.renderers]
  /// name the renderers a profile was established for: PPSSPP without an
  /// OpenGL ES context draws in software at 1x whatever the option says, and
  /// changing it during the game then resets a hardware context PPSSPP does
  /// not have (`check_variables`, `ContextReset` on its software context).
  static const List<LibretroResolutionProfile> profiles = <LibretroResolutionProfile>[
    // Azahar (3DS), "1" to "18": retro_run parses the options again on an
    // update, the rasterizer cache rebuilds its surfaces at the new scale and
    // the layout is resized (SET_GEOMETRY). Beyond 10x the picture (400N x
    // 480N) exceeds the 7200 x 4800 the core announces as its maximum. The
    // Software API ignores the factor.
    LibretroResolutionProfile(
      keys: <String>['citra_resolution_factor'],
      apply: LibretroResolutionApply.live,
      maxFactor: 10,
      requires: <String, List<String>>{
        'citra_graphics_api': <String>['Auto', 'auto', 'Vulkan', 'OpenGL'],
      },
      renderers: <String>[LibretroResolutionRenderer.vulkan, LibretroResolutionRenderer.gles],
    ),
    // DeSmuME, "256x192" to "2560x1920" per screen: check_variables(false)
    // in retro_run resizes the framebuffer (SET_SYSTEM_AV_INFO or
    // SET_GEOMETRY). The iOS build has the software rasterizer only, which
    // scales the 3D; 2D layers are only enlarged.
    LibretroResolutionProfile(
      keys: <String>['desmume_internal_resolution'],
      apply: LibretroResolutionApply.live,
      nativeSize: <int>[256, 192],
    ),
    // Beetle PSX HW (OpenGL renderer here) and Beetle PSX (software):
    // "1x(native)" to "16x", applied in retro_run with SET_SYSTEM_AV_INFO.
    // 16x needs about 600 MiB in software and a 16384-pixel VRAM texture:
    // NeoStation keeps the 8x limit of the earlier builds. The Vulkan
    // renderer rebuilds itself only on a context reset NeoStation does not
    // make: next launch there.
    LibretroResolutionProfile(
      keys: <String>['beetle_psx_hw_internal_resolution', 'beetle_psx_internal_resolution'],
      apply: LibretroResolutionApply.live,
      maxFactor: 8,
      requires: <String, List<String>>{
        'beetle_psx_hw_renderer': <String>['hardware', 'hardware_gl', 'software'],
      },
      renderers: <String>[LibretroResolutionRenderer.gles, LibretroResolutionRenderer.software],
    ),
    LibretroResolutionProfile(
      keys: <String>['beetle_psx_hw_internal_resolution'],
      apply: LibretroResolutionApply.relaunch,
      maxFactor: 8,
      requires: <String, List<String>>{
        'beetle_psx_hw_renderer': <String>['hardware', 'hardware_vk'],
      },
      renderers: <String>[LibretroResolutionRenderer.vulkan],
    ),
    // PPSSPP, "480x272" to "4800x2720": with OpenGL ("auto" takes the
    // frontend's OpenGL ES context here) check_variables in retro_run
    // resizes the render and announces it (SET_SYSTEM_AV_INFO); Vulkan
    // needs a restart (the option says so). Software rendering forces 1x,
    // and so does PPSSPP's own software context when it gets no hardware
    // context (its frames stay 480x272; a change during the game would call
    // ContextReset on that software context). NeoStation keeps the 5x limit
    // of the earlier builds.
    LibretroResolutionProfile(
      keys: <String>['ppsspp_internal_resolution'],
      apply: LibretroResolutionApply.live,
      nativeSize: <int>[480, 272],
      maxFactor: 5,
      requires: <String, List<String>>{
        'ppsspp_backend': <String>['auto', 'opengl'],
        'ppsspp_software_rendering': <String>['disabled'],
      },
      renderers: <String>[LibretroResolutionRenderer.gles],
    ),
    LibretroResolutionProfile(
      keys: <String>['ppsspp_internal_resolution'],
      apply: LibretroResolutionApply.relaunch,
      nativeSize: <int>[480, 272],
      maxFactor: 5,
      requires: <String, List<String>>{
        'ppsspp_backend': <String>['auto', 'vulkan'],
        'ppsspp_software_rendering': <String>['disabled'],
      },
      renderers: <String>[LibretroResolutionRenderer.vulkan],
    ),
    // Mupen64Plus-Next with GLideN64 (its default plugin): the 4:3 viewport,
    // "320x240" to "3840x2880", read only when the game is loaded
    // (update_variables(true) in retro_load_game). NeoStation keeps the
    // 1920x1440 limit of the earlier builds.
    LibretroResolutionProfile(
      keys: <String>['mupen64plus-43screensize'],
      apply: LibretroResolutionApply.relaunch,
      nativeSize: <int>[320, 240],
      maxFactor: 6,
      requires: <String, List<String>>{
        'mupen64plus-rdp-plugin': <String>['gliden64'],
        'mupen64plus-aspect': <String>['4:3'],
        'mupen64plus-EnableNativeResFactor': <String>['0'],
      },
      renderers: <String>[LibretroResolutionRenderer.gles],
    ),
    // ParaLLEl-RDP: "1x" to "8x", read when the RDP starts (Vulkan).
    LibretroResolutionProfile(
      keys: <String>['mupen64plus-parallel-rdp-upscaling', 'parallel-n64-upscaling'],
      apply: LibretroResolutionApply.relaunch,
      requires: <String, List<String>>{
        'mupen64plus-rdp-plugin': <String>['parallel'],
      },
      renderers: <String>[LibretroResolutionRenderer.vulkan],
    ),
    // Cores NeoStation does not package (keys from their option headers):
    // known names of the same setting, applied at the next launch.
    LibretroResolutionProfile(
      keys: <String>['reicast_internal_resolution'],
      apply: LibretroResolutionApply.relaunch,
      nativeSize: <int>[640, 480],
    ),
    LibretroResolutionProfile(
      keys: <String>['melonds_opengl_resolution'],
      apply: LibretroResolutionApply.relaunch,
      requires: <String, List<String>>{
        'melonds_render_mode': <String>['opengl'],
      },
      renderers: <String>[LibretroResolutionRenderer.gles],
    ),
    LibretroResolutionProfile(
      keys: <String>[
        'dolphin_efb_scale',
        'swanstation_GPU_ResolutionScale',
        'kronos_resolution_mode',
        'yabasanshiro_resolution_mode',
        'play_res_multi',
        'pcsx2_upscale_multiplier',
      ],
      apply: LibretroResolutionApply.relaunch,
    ),
  ];

  /// Option names that mean an internal resolution (case-insensitive), for
  /// cores in no profile.
  static const String genericKeyPattern =
      r'(internal|render(ing)?)[_\-.]?(res(olution)?|scale)|resolution[_\-.]?(factor|scale|multiplier|mode)|'
      r'upscal|res(olution)?[_\-.]?multi|efb[_\-.]?scale';

  /// Option descriptions that mean an internal resolution
  /// (case-insensitive), for cores in no profile.
  static const String genericDescriptionPattern =
      r'internal (gpu )?resolution|render(ing)? resolution|resolution (factor|scale|multiplier)|upscal';

  /// Largest side of the whole core picture NeoStation offers, in pixels:
  /// the console's size times the factor. Beyond it the picture would not
  /// fit the textures of the presentation, whatever the core accepts.
  static const int maxDimension = 8192;

  static final RegExp _leadingSize = RegExp(r'^(\d{2,5})\s*[xX×*]\s*(\d{2,5})(?!\d)');
  static final RegExp _leadingMultiplier = RegExp(r'^(\d+(?:[.,]\d+)?)\s*[xX×](?!\s*\d)');
  static final RegExp _leadingTimes = RegExp(r'^[xX×]\s*(\d+(?:[.,]\d+)?)(?![\d.,]|\s*[xX×]\s*\d)');
  static final RegExp _bareNumber = RegExp(r'^(\d+(?:[.,]\d+)?)$');
  static final RegExp _innerMultiplier = RegExp(r'(?<![\d.,])(\d+(?:[.,]\d+)?)\s*[xX×](?!\s*\d)');
  static final RegExp _native = RegExp('native|original', caseSensitive: false);

  static double _number(String text) => double.parse(text.replaceAll(',', '.'));

  /// What one value names, or null:
  /// - "960x544", "640 x 480", "960x544 (2x)": a size;
  /// - "2x", "1x(native)", "1x (Native)", "2x (1280x960)": the number before x;
  /// - "x2", "x1 (640 x 528)": the number after a leading x;
  /// - "2", "1.5": a bare number;
  /// - "Native", "original", "Native (2x)": 1, or the multiplier it names.
  static LibretroResolutionToken? token(String raw) {
    final value = raw.trim();
    if (value.isEmpty) return null;
    final size = _leadingSize.firstMatch(value);
    if (size != null) {
      final width = int.parse(size.group(1)!);
      final height = int.parse(size.group(2)!);
      return width > 0 && height > 0 ? LibretroResolutionToken.size(width, height) : null;
    }
    final match = _leadingMultiplier.firstMatch(value) ??
        _leadingTimes.firstMatch(value) ??
        _bareNumber.firstMatch(value);
    if (match != null) {
      final factor = _number(match.group(1)!);
      return factor > 0 ? LibretroResolutionToken.factor(factor) : null;
    }
    if (_native.hasMatch(value)) {
      final inner = _innerMultiplier.firstMatch(value);
      final factor = inner == null ? 1.0 : _number(inner.group(1)!);
      return factor > 0 ? LibretroResolutionToken.factor(factor) : null;
    }
    return null;
  }

  static double _rounded(double factor) => (factor * 100).roundToDouble() / 100;

  /// The values of an option NeoStation offers, smallest factor first: each
  /// value whose scale is known ([token], else its [labels] entry), one per
  /// factor (the first declared), from the native resolution up to
  /// [maxFactor] and to [maxDimension] (0: no limit) for a console picture
  /// of [consoleSize]. Sizes are divided by [nativeSize], else by the smallest
  /// size declared; a size whose two sides do not scale alike is left out.
  static List<LibretroResolutionChoice> choices(
    List<String> values, {
    List<String>? labels,
    List<int>? nativeSize,
    List<int>? consoleSize,
    double maxFactor = 0,
    int maxDimension = LibretroResolution.maxDimension,
  }) {
    final tokens = <String, LibretroResolutionToken>{};
    for (var index = 0; index < values.length; index++) {
      final value = values[index];
      var parsed = token(value);
      if (parsed == null && labels != null && index < labels.length) parsed = token(labels[index]);
      if (parsed != null && !tokens.containsKey(value)) tokens[value] = parsed;
    }
    List<int>? base = nativeSize;
    if (base == null) {
      for (final parsed in tokens.values) {
        if (!parsed.isSize) continue;
        if (base == null || parsed.width < base[0]) base = <int>[parsed.width, parsed.height];
      }
    }
    final result = <LibretroResolutionChoice>[];
    final seen = <double>{};
    for (final entry in tokens.entries) {
      final parsed = entry.value;
      double factor;
      if (parsed.isSize) {
        if (base == null || base[0] <= 0 || base[1] <= 0) continue;
        final horizontal = parsed.width / base[0];
        final vertical = parsed.height / base[1];
        if ((horizontal - vertical).abs() > 0.02 * math.max(horizontal, vertical)) continue;
        factor = _rounded(horizontal);
      } else {
        factor = _rounded(parsed.factor!);
      }
      if (factor < 0.995) continue;
      if (maxFactor > 0 && factor > maxFactor + 0.005) continue;
      if (consoleSize != null && consoleSize.length == 2 && consoleSize[0] > 0 && consoleSize[1] > 0) {
        final largest = math.max(consoleSize[0], consoleSize[1]) * factor;
        if (maxDimension > 0 && largest > maxDimension + 0.5) continue;
      }
      if (!seen.add(factor)) continue;
      result.add(LibretroResolutionChoice(
        value: entry.key,
        factor: factor,
        width: parsed.isSize ? parsed.width : 0,
        height: parsed.isSize ? parsed.height : 0,
      ));
    }
    result.sort((a, b) => a.factor.compareTo(b.factor));
    return result;
  }

  /// The first profile naming [key] (the core's default configuration),
  /// null when none does.
  static LibretroResolutionProfile? profileFor(String key) {
    for (final profile in profiles) {
      if (profile.keys.contains(key)) return profile;
    }
    return null;
  }

  /// Languages writing a decimal comma (others a point): the factor of the
  /// native menu (NSNumberFormatter for the same language) reads the same.
  static const Set<String> _decimalComma = <String>{'fr', 'de', 'es', 'it', 'pt', 'ru', 'id'};

  /// "2", "4.5" or "4,5" for [localeKey] (a key of `LibretroLocale.values`).
  static String factorText(double factor, String localeKey) {
    final rounded = _rounded(factor);
    if (rounded == rounded.roundToDouble()) return rounded.round().toString();
    var text = rounded.toStringAsFixed(2);
    while (text.endsWith('0')) {
      text = text.substring(0, text.length - 1);
    }
    return _decimalComma.contains(localeKey) ? text.replaceAll('.', ',') : text;
  }

  /// Rules for the native session (`LibretroResolutionRules`).
  static Map<String, Object> nativeRules() => <String, Object>{
        'profiles': <Map<String, Object>>[for (final profile in profiles) profile.toNative()],
        'keyPattern': genericKeyPattern,
        'descriptionPattern': genericDescriptionPattern,
        'maxDimension': maxDimension,
      };
}
