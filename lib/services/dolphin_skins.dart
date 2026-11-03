import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as p;

import 'libretro_core_catalog.dart';
import 'libretro_skin_compatibility.dart';

/// What [DolphinSkins.inspect] read in a GameCube or Wii skin.
class DolphinSkinReport {
  const DolphinSkinReport({
    required this.console,
    required this.identifier,
    required this.name,
    required this.gameTypeIdentifier,
    required this.orientations,
    required this.compatibility,
    this.author,
    this.warnings = const <String>[],
  });

  /// `gc` or `wii`.
  final String console;
  final String identifier;
  final String name;
  final String? author;
  final String gameTypeIdentifier;

  /// Orientations the skin lays out for the iPhone ("portrait",
  /// "landscape").
  final List<String> orientations;
  final LibretroSkinCompatibility compatibility;
  final List<String> warnings;

  /// The summary the import records, in the native parser's shape.
  Map<String, Object?> get summary => <String, Object?>{
        'identifier': identifier,
        'name': name,
        'author': author,
        'consoles': <String>[console],
        'gameTypeIdentifier': gameTypeIdentifier,
        // The native parser's shape ({device: orientations}, read by
        // LibretroInstalledSkin.supports); on an iPad the Dolphin overlay
        // takes the skin's iPad layout, else its iPhone one.
        'orientations': <String, List<String>>{'iphone': orientations, 'ipad': orientations},
        'warnings': warnings,
      };
}

/// GameCube and Wii controller skins of the embedded Dolphin
/// (docs/dolphin-skins.md): the same `.deltaskin` / `.manicskin` files,
/// catalogs, import, iPhone filter and portrait / landscape / per-game
/// choices as the embedded Libretro consoles, stored with them
/// (`Documents/Libretro/Skins`, `Documents/Libretro/Config/Frontend/<gc|wii>.json`).
///
/// The native Libretro parser does not know these consoles (its input map
/// is the RetroPad's): their skins are read here, and drawn in a game by the
/// Dolphin bridge (`DOLSkinOverlay`), which follows the same input table.
abstract final class DolphinSkins {
  /// GameCube, Wii and PlayStation 2 as skin consoles. Never Libretro
  /// consoles: they are not added to [LibretroCoreCatalog.consoles]. Their
  /// skins are drawn by their own native overlay: `DOLSkinOverlay` (Dolphin:
  /// GameCube, Wii) and `ARMSX2SkinOverlay` (ARMSX2: PS2).
  static const Map<String, LibretroConsole> consoles = <String, LibretroConsole>{
    'gc': LibretroConsole(
      id: 'gc',
      name: 'Nintendo GameCube',
      width: 640,
      height: 528,
      importSystem: 'gc',
      catalogSystems: <String>['gamecube', 'gc', 'ngc'],
    ),
    'wii': LibretroConsole(
      id: 'wii',
      name: 'Nintendo Wii',
      width: 640,
      height: 528,
      importSystem: 'wii',
      catalogSystems: <String>['wii'],
    ),
    'ps2': LibretroConsole(
      id: 'ps2',
      name: 'Sony PlayStation 2',
      width: 640,
      height: 480,
      importSystem: 'ps2',
      catalogSystems: <String>['ps2', 'playstation2', 'sonyplaystation2'],
    ),
  };

  static bool isDolphinConsole(String console) => consoles.containsKey(console);

  /// Libretro consoles and Dolphin's, for the skin screens and catalogs.
  static Map<String, LibretroConsole> get skinConsoles => <String, LibretroConsole>{
        ...LibretroCoreCatalog.consoles,
        ...consoles,
      };

  /// Geometry of every skin console, in [LibretroCoreCatalog.consoleGeometry]'s
  /// shape.
  static Map<String, Map<String, Object>> consoleGeometry() => <String, Map<String, Object>>{
        ...LibretroCoreCatalog.consoleGeometry(),
        for (final console in consoles.values) console.id: console.geometry,
      };

  static String _key(String value) =>
      value.trim().split('.').last.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');

  /// Console of a skin's `gameTypeIdentifier` (`public.aoshuang.game.ngc`
  /// for Manic's GameCube), or null when it is not a Dolphin console.
  static String? consoleOfGameType(String gameTypeIdentifier) => switch (_key(gameTypeIdentifier)) {
        'ngc' || 'gc' || 'gamecube' || 'dol' || 'dolphin' => 'gc',
        'wii' || 'rvl' || 'revolution' => 'wii',
        'ps2' || 'playstation2' || 'sonyplaystation2' || 'armsx2' || 'pcsx2' => 'ps2',
        _ => null,
      };

  /// Logical inputs of each console, as the Dolphin bridge sends them.
  ///
  /// GameCube: `a b x y z l r start`, the D-pad `up down left right`, the
  /// main stick `stickUp…` and the C-stick `cUp…`.
  /// Wii (Wii Remote held upright with a Nunchuk): `a b one two plus minus
  /// home`, the D-pad, the Nunchuk stick `stickUp…`, its `c` and `z`
  /// buttons, and the pointer `pointerUp…`.
  /// PlayStation 2 (ARMSX2): `cross circle square triangle l1 l2 r1 r2
  /// select start l3 r3`, the D-pad, the left stick `stickUp…` and the right
  /// stick `rstickUp…`. L3 and R3 are separate targets, never a stick click.
  /// GameCube and Wii: the actions `menu`, `quickSave`, `quickLoad`; PS2: `menu`.
  static const Map<String, List<String>> inputs = <String, List<String>>{
    'gc': <String>[
      'a', 'b', 'x', 'y', 'z', 'l', 'r', 'start', 'up', 'down', 'left', 'right',
      'stickUp', 'stickDown', 'stickLeft', 'stickRight', 'cUp', 'cDown', 'cLeft', 'cRight',
      'menu', 'quickSave', 'quickLoad',
    ],
    'wii': <String>[
      'a', 'b', 'one', 'two', 'plus', 'minus', 'home', 'c', 'z', 'up', 'down', 'left', 'right',
      'stickUp', 'stickDown', 'stickLeft', 'stickRight', 'pointerUp', 'pointerDown', 'pointerLeft',
      'pointerRight', 'menu', 'quickSave', 'quickLoad',
    ],
    'ps2': <String>[
      'cross', 'circle', 'square', 'triangle', 'l1', 'l2', 'r1', 'r2', 'select', 'start', 'l3', 'r3',
      'up', 'down', 'left', 'right', 'stickUp', 'stickDown', 'stickLeft', 'stickRight',
      'rstickUp', 'rstickDown', 'rstickLeft', 'rstickRight', 'menu',
    ],
  };

  static const List<String> _directions = <String>['Up', 'Down', 'Left', 'Right'];

  /// Logical input of a raw skin input on [console], or null when the
  /// console has nothing for it. Spellings of Delta, Manic and Provenance
  /// are accepted (case and separators ignored); [adapted] tells whether the
  /// name needed an adaptation (a Wii Remote `x` read as 1, a right stick
  /// read as the Wii pointer…). Manic's GameCube names (`r1` Z, `l2` / `r2`
  /// L / R, the right stick as C-stick) are that console's own.
  static String? canonicalInput(String console, String raw, {List<bool>? adapted}) {
    final key = raw.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');
    void mark() => adapted?.add(true);
    String? stick(String prefix) {
      for (final d in _directions) {
        if (key == '$prefix${d.toLowerCase()}') return d;
      }
      return null;
    }

    for (final prefix in const ['leftthumbstick', 'analogstick', 'leftstick', 'leftanalog', 'analog', 'thumbstick']) {
      final d = stick(prefix);
      if (d != null) return 'stick$d';
    }
    for (final prefix in const ['rightthumbstick', 'rightstick', 'rightanalog', 'cstick', 'c']) {
      final d = stick(prefix);
      if (d != null) {
        // The right stick is the GameCube's C-stick and the PS2's right
        // stick; on a Wii it moves the pointer (an adaptation).
        if (console == 'wii') mark();
        return switch (console) { 'gc' => 'c$d', 'ps2' => 'rstick$d', _ => 'pointer$d' };
      }
    }
    for (final d in _directions) {
      if (key == d.toLowerCase() || key == 'dpad${d.toLowerCase()}') return d.toLowerCase();
    }
    switch (key) {
      case 'menu' || 'pause' || 'options':
        return 'menu';
      // The quick save and load actions open the Dolphin session menu's
      // state page; the PS2 session has no such skin action.
      case 'quicksave' when console != 'ps2':
        return 'quickSave';
      case 'quickload' when console != 'ps2':
        return 'quickLoad';
    }
    if (console == 'ps2') {
      // Only the PlayStation names: nothing is guessed from Nintendo names.
      return switch (key) {
        'cross' || 'circle' || 'square' || 'triangle' || 'l1' || 'l2' || 'r1' || 'r2' || 'select' || 'start' ||
        'l3' || 'r3' => key,
        _ => null,
      };
    }
    if (console == 'gc') {
      switch (key) {
        case 'a' || 'b' || 'x' || 'y' || 'z' || 'start':
          return key;
        case 'run' || 'plus':
          mark();
          return 'start';
        case 'l' || 'lefttrigger' || 'ltrigger':
          return 'l';
        case 'r' || 'righttrigger' || 'rtrigger':
          return 'r';
        // Manic's GameCube convention, the one of every published GameCube
        // skin: l2 / r2 are the L / R triggers, r1 is Z.
        case 'l2' || 'r2':
          return key == 'l2' ? 'l' : 'r';
        case 'r1':
          return 'z';
        case 'l1' || 'zr' || 'zl':
          mark();
          return 'z';
      }
      return null;
    }
    if (console == 'wii') {
      switch (key) {
        case 'a' || 'b' || 'home' || 'plus' || 'minus':
          return key;
        case '1' || 'one':
          return 'one';
        case '2' || 'two':
          return 'two';
        case 'x':
          mark();
          return 'one';
        case 'y':
          mark();
          return 'two';
        case 'start':
          mark();
          return 'plus';
        case 'select':
          mark();
          return 'minus';
        case 'c' || 'nunchukc':
          return 'c';
        case 'z' || 'nunchukz':
          return 'z';
        case 'l' || 'l1' || 'l2' || 'zl':
          mark();
          return 'c';
        case 'r' || 'r1' || 'r2' || 'zr':
          mark();
          return 'z';
      }
    }
    return null;
  }

  /// Controls without which a console cannot be played by touch, each as
  /// the inputs that satisfy it.
  static const Map<String, Map<String, List<String>>> essentials = <String, Map<String, List<String>>>{
    'gc': <String, List<String>>{
      'leftStick': <String>['stickUp', 'stickDown', 'stickLeft', 'stickRight'],
      'a': <String>['a'],
      'b': <String>['b'],
      'start': <String>['start'],
    },
    'wii': <String, List<String>>{
      'directions': <String>['up', 'down', 'left', 'right'],
      'a': <String>['a'],
      'b': <String>['b'],
    },
    'ps2': <String, List<String>>{
      'directions': <String>['up', 'down', 'left', 'right'],
      'cross': <String>['cross'],
      'circle': <String>['circle'],
      'start': <String>['start'],
    },
  };

  /// Controls a game may need, reported when missing.
  static const Map<String, List<String>> optionals = <String, List<String>>{
    'gc': <String>['x', 'y', 'z', 'l', 'r', 'rightStick'],
    'wii': <String>['one', 'two', 'plus', 'minus', 'leftStick'],
    'ps2': <String>['square', 'triangle', 'l1', 'l2', 'r1', 'r2', 'select', 'l3', 'r3', 'leftStick', 'rightStick'],
  };

  static Map<String, dynamic>? _map(Object? o) => o is Map ? Map<String, dynamic>.from(o) : null;

  /// The iPhone layout of [orientation]: edge-to-edge first, then the
  /// standard one; an iPad layout is used when the skin has no iPhone one.
  static (Map<String, dynamic>, bool tablet)? layoutFor(Map<String, dynamic> info, String orientation) {
    final representations = _map(info['representations']);
    if (representations == null) return null;
    for (final (device, tablet) in const [('iphone', false), ('ipad', true)]) {
      final byDisplay = _map(representations[device]);
      if (byDisplay == null) continue;
      for (final display in const ['edgeToEdge', 'standard', 'splitView']) {
        final layout = _map(_map(byDisplay[display])?[orientation]);
        if (layout != null) return (layout, tablet);
      }
    }
    return null;
  }

  static String? _text(Object? o) {
    final t = o is String ? o.trim() : '';
    return t.isEmpty ? null : t;
  }

  /// Raw input names of one item: a list of buttons, or a D-pad / stick
  /// as `{up, down, left, right}`.
  static List<String> _itemInputs(Map<String, dynamic> item) {
    final raw = item['inputs'];
    if (raw is List) return <String>[for (final v in raw) if (v is String) v];
    if (raw is Map) return <String>[for (final v in raw.values) if (v is String) v];
    return const <String>[];
  }

  /// Reads a skin's `info.json` ([info]) with the files it holds
  /// ([files], relative paths): null when it is not a GameCube or Wii skin.
  static DolphinSkinReport? inspect(Map<String, dynamic> info, Set<String> files) {
    final type = _text(info['gameTypeIdentifier']);
    if (type == null) return null;
    final console = consoleOfGameType(type);
    if (console == null) return null;
    final identifier = _text(info['identifier']) ?? type;
    final orientations = <String>[];
    final states = <String, String>{};
    final reasons = <String>{};
    final missing = <String>{};
    final missingOptional = <String>{};
    final adaptedInputs = <String>{};
    final unsupported = <String>{};
    var assetMissing = false;
    var tablet = false;
    var smallest = 0.0;
    for (final orientation in const ['portrait', 'landscape']) {
      final found = layoutFor(info, orientation);
      if (found == null) continue;
      final (layout, isTablet) = found;
      tablet = tablet || isTablet;
      final provided = <String>{};
      var controls = 0;
      for (final raw in (layout['items'] as List? ?? const [])) {
        final item = _map(raw);
        if (item == null) continue;
        var any = false;
        for (final name in _itemInputs(item)) {
          final adapted = <bool>[];
          final input = canonicalInput(console, name, adapted: adapted);
          if (input == null) {
            unsupported.add(name);
            continue;
          }
          if (adapted.isNotEmpty) adaptedInputs.add(name);
          provided.add(input);
          any = true;
        }
        for (final asset in <Object?>[_map(item['asset'])?['normal'], _map(item['thumbstick'])?['name']]) {
          final name = _text(asset);
          if (name != null && !files.contains(name)) assetMissing = true;
        }
        if (any) {
          controls++;
          final frame = _map(item['frame']);
          final w = (frame?['width'] as num?)?.toDouble() ?? 0, h = (frame?['height'] as num?)?.toDouble() ?? 0;
          final side = w < h ? w : h;
          if (side > 0 && (smallest == 0 || side < smallest)) smallest = side;
        }
      }
      final assets = _map(layout['assets']);
      final art = assets == null
          ? null
          : _text(assets['resizable']) ?? _text(assets['large']) ?? _text(assets['medium']) ?? _text(assets['small']);
      final hasArt = art != null && files.contains(art);
      final lacking = <String>[
        for (final entry in essentials[console]!.entries)
          if (!entry.value.every(provided.contains)) entry.key,
      ];
      // A Wii Remote D-pad may be the Nunchuk stick of the skin.
      if (console == 'wii' && lacking.contains('directions') &&
          const ['stickUp', 'stickDown', 'stickLeft', 'stickRight'].every(provided.contains)) {
        lacking.remove('directions');
        adaptedInputs.add('leftStick');
      }
      for (final optional in optionals[console]!) {
        final have = switch (optional) {
          'rightStick' => provided.contains(console == 'ps2' ? 'rstickUp' : 'cUp'),
          'leftStick' => provided.contains('stickUp'),
          _ => provided.contains(optional),
        };
        if (!have) missingOptional.add(optional);
      }
      String state;
      if (!hasArt) {
        reasons.add('SKIN_COMPAT_NO_ARTWORK');
        state = 'incompatible';
      } else if (controls == 0) {
        reasons.add(LibretroSkinCompatibility.noTouchControls);
        state = 'incompatible';
      } else if (lacking.isNotEmpty) {
        missing.addAll(lacking);
        reasons.add('SKIN_COMPAT_MISSING_CONTROLS');
        state = 'incompatible';
      } else {
        state = isTablet || adaptedInputs.isNotEmpty ? 'adaptable' : 'compatible';
      }
      states[orientation] = state;
      if (state != 'incompatible') orientations.add(orientation);
    }
    if (states.isEmpty) reasons.add('SKIN_COMPAT_NO_PHONE_LAYOUT');
    if (tablet) reasons.add('SKIN_COMPAT_TABLET_ADAPTED');
    if (adaptedInputs.isNotEmpty) reasons.add('SKIN_COMPAT_ADAPTED_INPUTS');
    final verdict = states.values.contains('compatible')
        ? LibretroSkinVerdict.compatible
        : states.values.contains('adaptable')
            ? LibretroSkinVerdict.adaptable
            : LibretroSkinVerdict.incompatible;
    final warnings = <String>[
      if (unsupported.isNotEmpty) 'SKIN_WARN_UNKNOWN_INPUTS',
      if (assetMissing) 'SKIN_WARN_ASSET_MISSING',
      if (states.length == 1) 'SKIN_WARN_ORIENTATION_MISSING',
    ];
    return DolphinSkinReport(
      console: console,
      identifier: identifier,
      name: _text(info['name']) ?? identifier,
      author: _text(info['author']),
      gameTypeIdentifier: type,
      orientations: orientations,
      warnings: warnings,
      compatibility: LibretroSkinCompatibility(
        verdict: verdict,
        console: console,
        orientations: states,
        reasons: reasons.toList(),
        missingControls: missing.toList(),
        missingOptionalControls: missingOptional.toList(),
        adaptedInputs: adaptedInputs.toList(),
        unsupportedInputs: unsupported.toList(),
        tabletLayout: tablet,
        smallestControlPoints: smallest,
      ),
    );
  }

  /// [inspect] on an unpacked skin directory; null when it is not a
  /// GameCube or Wii skin, or has no readable `info.json`.
  static Future<DolphinSkinReport?> inspectDirectory(String directory) async {
    try {
      final info = jsonDecode(await File(p.join(directory, 'info.json')).readAsString());
      if (info is! Map) return null;
      final root = Directory(directory);
      final files = <String>{
        await for (final f in root.list(recursive: true, followLinks: false))
          if (f is File) p.relative(f.path, from: directory).replaceAll(r'\', '/'),
      };
      return inspect(Map<String, dynamic>.from(info), files);
    } catch (_) {
      return null;
    }
  }

  /// The skin's own picture of [orientation] when it is a PNG or JPEG.
  /// A complete `previewImages` picture is preferred to the background;
  /// an absent or invalid optional preview keeps older skins' fallback.
  /// PDF backgrounds are drawn in the game only.
  static Future<Uint8List?> previewImage(String directory, String orientation) async {
    try {
      final info = jsonDecode(await File(p.join(directory, 'info.json')).readAsString());
      if (info is! Map) return null;
      final found = layoutFor(Map<String, dynamic>.from(info), orientation);
      if (found == null) return null;
      final preview = await _previewBitmap(directory, _map(info['previewImages'])?[orientation]);
      if (preview != null) return preview;
      final assets = _map(found.$1['assets']);
      final art = assets == null
          ? null
          : _text(assets['resizable']) ?? _text(assets['large']) ?? _text(assets['medium']) ?? _text(assets['small']);
      return await _previewBitmap(directory, art);
    } catch (_) {
      return null;
    }
  }

  static const int _maximumPreviewBytes = 16 * 1024 * 1024;

  /// Reads only confined PNG/JPEG files. Both the lexical path and the
  /// resolved target must stay inside the skin, including through symlinks.
  static Future<Uint8List?> _previewBitmap(String directory, Object? rawPath) async {
    try {
      final name = _text(rawPath);
      if (name == null || name.contains(r'\') || p.isAbsolute(name) || p.windows.isAbsolute(name) ||
          name.split('/').contains('..')) {
        return null;
      }
      final extension = p.extension(name).toLowerCase();
      if (extension != '.png' && extension != '.jpg' && extension != '.jpeg') return null;
      final root = p.normalize(p.absolute(directory));
      final path = p.normalize(p.join(root, name));
      if (!p.isWithin(root, path)) return null;
      final resolvedRoot = await Directory(root).resolveSymbolicLinks();
      final resolvedPath = await File(path).resolveSymbolicLinks();
      if (!p.isWithin(resolvedRoot, resolvedPath)) return null;
      final file = File(resolvedPath);
      final stat = await file.stat();
      if (stat.type != FileSystemEntityType.file || stat.size <= 0 || stat.size > _maximumPreviewBytes) return null;
      final builder = BytesBuilder(copy: false);
      await for (final chunk in file.openRead()) {
        if (builder.length + chunk.length > _maximumPreviewBytes) return null;
        builder.add(chunk);
      }
      final bytes = builder.takeBytes();
      final png = bytes.length >= 8 && bytes[0] == 0x89 && bytes[1] == 0x50 && bytes[2] == 0x4e &&
          bytes[3] == 0x47 && bytes[4] == 0x0d && bytes[5] == 0x0a && bytes[6] == 0x1a && bytes[7] == 0x0a;
      final jpeg = bytes.length >= 3 && bytes[0] == 0xff && bytes[1] == 0xd8 && bytes[2] == 0xff;
      if (extension == '.png' ? !png : !jpeg) return null;
      return bytes;
    } catch (_) {
      return null;
    }
  }
}
