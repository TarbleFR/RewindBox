import 'dart:math' as math;

import 'package:path/path.dart' as path;

/// Conversion of a RetroArch touch overlay (`.cfg`, the format of
/// libretro/common-overlays and PocketArch) into a Delta skin description
/// (info.json) that NeoStation's native parser, compatibility filter and
/// touch engine then handle like any imported skin.
///
/// Only constructs with an exact NeoStation equivalent are converted; the
/// semantics come from RetroArch's own sources (tasks/task_overlay.c,
/// input/input_driver.c):
/// - one page per orientation: a page named "portrait" / "landscape" (pause,
///   menu and hidden pages left out), else the declared aspect ratio; the
///   page must be `full_screen` and `normalized`;
/// - a desc "names,x,y,shape,range_x,range_y" is centred on (x, y) with half
///   sizes range_x / range_y of the page; its touch area grows by
///   `reach_*` (> 1 only: a smaller reach keeps the drawn area); a reach of 0
///   makes it untouchable in RetroArch, so it is not a control here either;
/// - RetroPad names (`a|b`...) are translated to the console's logical
///   inputs through the RetroPad id they press (Genesis "a" is RetroPad A,
///   NeoStation's "c"), names without a meaning on the console are dropped;
/// - `dpad_area` becomes a D-pad; `abxy_area` becomes an eight-way item
///   whose up / down / left / right press RetroPad X / B / Y / A as in
///   RetroArch (diagonals press both); `*_up` redefinitions are honoured;
/// - `analog_left` / `analog_right` become thumbsticks (with an image) or
///   four-way items; `l_x_minus`... `r_y_plus` press stick directions;
/// - commands: menu_toggle, and overlay_next to a pause / menu page, open
///   NeoStation's menu (which holds save, load, reset and quit);
///   hold_fast_forward / toggle_fast_forward / save_state / load_state map to
///   NeoStation's actions; the other commands (rewind, OSK, shaders,
///   keyboard keys...) are dropped and listed;
/// - in portrait the game takes the room above the topmost control; in
///   landscape it fills the view behind the translucent controls, as
///   RetroArch draws it;
/// - Nintendo DS: the game area holds both screens, the bottom one touch.
class LibretroOverlayConverter {
  /// RetroPad names RetroArch uses in overlay descs, by RetroPad id.
  static const Map<String, int> retroPadIds = <String, int>{
    'b': 0, 'y': 1, 'select': 2, 'start': 3, 'up': 4, 'down': 5, 'left': 6, 'right': 7,
    'a': 8, 'x': 9, 'l': 10, 'r': 11, 'l2': 12, 'r2': 13, 'l3': 14, 'r3': 15,
  };

  /// Logical input (LibretroInputMap) of each RetroPad id per console:
  /// the inverse of the tables documented in LibretroInputMap.h.
  static Map<int, String> logicalInputs(String console) {
    const directions = <int, String>{4: 'up', 5: 'down', 6: 'left', 7: 'right'};
    const nes = <int, String>{8: 'a', 0: 'b', 3: 'start', 2: 'select'};
    const gba = <int, String>{...nes, 10: 'l', 11: 'r'};
    const snes = <int, String>{...gba, 9: 'x', 1: 'y'};
    const genesis = <int, String>{1: 'a', 0: 'b', 8: 'c', 10: 'x', 9: 'y', 11: 'z', 3: 'start', 2: 'mode'};
    const masterSystem = <int, String>{0: 'b', 8: 'a', 3: 'start'};
    const arcade = <int, String>{0: 'b', 8: 'a', 1: 'y', 9: 'x', 10: 'l', 11: 'r', 2: 'select', 3: 'start'};
    const n64 = <int, String>{0: 'a', 1: 'b', 12: 'z', 10: 'l', 11: 'r', 3: 'start'};
    const psx = <int, String>{...snes, 12: 'l2', 13: 'r2', 14: 'l3', 15: 'r3'};
    const threeDS = <int, String>{...snes, 12: 'l2', 13: 'r2'};
    final table = switch (console) {
      'nes' || 'gb' || 'gbc' => nes,
      'gba' => gba,
      'snes' || 'nds' || 'psp' => snes,
      'md' || 'mcd' || '32x' => genesis,
      'sms' || 'gg' || 'sg1000' => masterSystem,
      'arcade' => arcade,
      'n64' => n64,
      'psx' => psx,
      '3ds' => threeDS,
      _ => const <int, String>{},
    };
    return <int, String>{...directions, ...table};
  }

  /// RetroArch commands and the NeoStation action they become.
  static const Map<String, String> commands = <String, String>{
    'menu_toggle': 'menu',
    'hold_fast_forward': 'fastForward',
    'toggle_fast_forward': 'toggleFastForward',
    'save_state': 'quickSave',
    'load_state': 'quickLoad',
  };

  /// Stick directions pressed by `l_x_minus`... (RetroArch analog buttons).
  static const Map<String, String> stickButtons = <String, String>{
    'l_x_minus': 'leftStickLeft', 'l_x_plus': 'leftStickRight', 'l_y_minus': 'leftStickUp', 'l_y_plus': 'leftStickDown',
    'r_x_minus': 'rightStickLeft', 'r_x_plus': 'rightStickRight', 'r_y_minus': 'rightStickUp', 'r_y_plus': 'rightStickDown',
  };

  /// Width of the converted layouts (mapping units); heights follow the
  /// page's aspect ratio, else an edge-to-edge iPhone's (19.5:9) or an
  /// iPad's (4:3).
  static const double mappingWidth = 1000;
  static const double phoneAspect = 19.5 / 9;
  static const double tabletAspect = 4 / 3;

  /// Delta gameTypeIdentifier of each console.
  static const Map<String, String> gameTypes = <String, String>{
    'nes': 'com.rileytestut.delta.game.nes',
    'snes': 'com.rileytestut.delta.game.snes',
    'gb': 'com.rileytestut.delta.game.gbc',
    'gbc': 'com.rileytestut.delta.game.gbc',
    'gba': 'com.rileytestut.delta.game.gba',
    'nds': 'com.rileytestut.delta.game.ds',
    'n64': 'com.rileytestut.delta.game.n64',
    'md': 'com.rileytestut.delta.game.genesis',
    'mcd': 'com.rileytestut.delta.game.genesis',
    '32x': 'com.rileytestut.delta.game.genesis',
    'sms': 'public.aoshuang.game.ms',
    'gg': 'public.aoshuang.game.gg',
    'sg1000': 'public.aoshuang.game.sg1000',
    'psx': 'public.aoshuang.game.ps1',
    'psp': 'public.aoshuang.game.psp',
    'arcade': 'public.aoshuang.game.arcade',
  };

  /// Converts [cfg] (the overlay text, located at [cfgPath] in its
  /// repository, used to resolve image paths) for [console]. An overlay
  /// drawn for iPads ([device] "ipad") becomes an iPad layout, which the
  /// native filter adapts to the iPhone only when its controls stay large
  /// enough.
  static LibretroOverlayConversion convert(
    String cfg, {
    required String cfgPath,
    required String console,
    required String name,
    required String identifier,
    String device = 'iphone',
  }) {
    final conf = _parse(cfg);
    final problems = <String>[];
    final dropped = <String>{};
    final files = <String, String>{};
    final gameType = gameTypes[console];
    if (gameType == null) problems.add('console $console has no converted layout');
    if (cfg.contains('#include')) problems.add('#include is not supported');
    final count = int.tryParse(conf['overlays'] ?? '') ?? 0;
    final pages = <int, _Page>{};
    for (var index = 0; index < count; index++) {
      pages[index] = _Page(index, conf);
    }
    final representations = <String, Object?>{};
    for (final orientation in const <String>['portrait', 'landscape']) {
      final page = _pickPage(pages.values, orientation);
      if (page == null) continue;
      if (!page.normalized || !page.fullScreen) {
        problems.add('page ${page.name.isEmpty ? page.index : page.name} is not full_screen and normalized');
        continue;
      }
      final layout = _convertPage(
        page,
        conf,
        pages,
        console: console,
        orientation: orientation,
        deviceAspect: device == 'ipad' ? tabletAspect : phoneAspect,
        cfgDirectory: path.posix.dirname(cfgPath),
        files: files,
        dropped: dropped,
        problems: problems,
      );
      if (layout != null) representations[orientation] = layout;
    }
    if (representations.isEmpty && problems.isEmpty) problems.add('no portrait or landscape page');
    final info = <String, Object?>{
      'name': name,
      'identifier': identifier,
      'gameTypeIdentifier': gameType ?? console,
      'debug': false,
      'representations': <String, Object?>{
        if (device == 'ipad')
          'ipad': <String, Object?>{'standard': representations}
        else
          'iphone': <String, Object?>{'edgeToEdge': representations},
      },
    };
    return LibretroOverlayConversion(
      info: info,
      files: files,
      problems: problems,
      droppedCommands: dropped.toList()..sort(),
      orientations: representations.keys.toList(),
    );
  }

  static _Page? _pickPage(Iterable<_Page> pages, String orientation) {
    final usable = pages.where((page) => !page.auxiliary).toList();
    for (final page in usable) {
      if (page.name.toLowerCase().contains(orientation)) return page;
    }
    // Unnamed pages: the declared aspect ratio decides.
    for (final page in usable) {
      final aspect = page.aspect;
      if (page.name.toLowerCase().contains(orientation == 'portrait' ? 'landscape' : 'portrait')) continue;
      if (aspect != null && (orientation == 'portrait' ? aspect < 1 : aspect >= 1)) return page;
    }
    // A single unnamed page without aspect ratio: landscape (RetroArch's default).
    if (orientation == 'landscape' && usable.length == 1 && usable.first.aspect == null && usable.first.name.isEmpty) {
      return usable.first;
    }
    return null;
  }

  static Map<String, Object?>? _convertPage(
    _Page page,
    Map<String, String> conf,
    Map<int, _Page> pages, {
    required String console,
    required String orientation,
    required double deviceAspect,
    required String cfgDirectory,
    required Map<String, String> files,
    required Set<String> dropped,
    required List<String> problems,
  }) {
    final portrait = orientation == 'portrait';
    final aspect = page.aspect ?? (portrait ? 1 / deviceAspect : deviceAspect);
    final width = mappingWidth;
    final height = width / aspect;
    final logical = logicalInputs(console);
    final items = <Map<String, Object?>>[];
    final controlFrames = <math.Rectangle<double>>[];
    var imageIndex = 0;

    String? image(String? source) {
      if (source == null || source.isEmpty) return null;
      final resolved = path.posix.normalize(path.posix.join(cfgDirectory, source));
      if (resolved.startsWith('../') || path.posix.isAbsolute(resolved)) return null;
      final extension = path.posix.extension(resolved).toLowerCase();
      if (extension != '.png' && extension != '.jpg' && extension != '.jpeg') return null;
      final existing = files.entries.where((entry) => entry.value == resolved).map((entry) => entry.key);
      if (existing.isNotEmpty) return existing.first;
      final name = 'images/${orientation[0]}${imageIndex++}$extension';
      files[name] = resolved;
      return name;
    }

    for (var index = 0; index < page.descCount; index++) {
      final key = 'overlay${page.index}_desc$index';
      final raw = conf[key];
      if (raw == null) continue;
      final parts = raw.split(',').map((part) => part.trim()).toList();
      if (parts.length < 6) continue;
      final names = parts[0].split('|').map((name) => name.trim().toLowerCase()).where((name) => name.isNotEmpty).toList();
      final x = double.tryParse(parts[1]);
      final y = double.tryParse(parts[2]);
      final rangeX = double.tryParse(parts[4]);
      final rangeY = double.tryParse(parts[5]);
      if (x == null || y == null || rangeX == null || rangeY == null || rangeX <= 0 || rangeY <= 0) continue;
      double reach(String side, String axis) =>
          double.tryParse(conf['${key}_reach_$side'] ?? '') ?? double.tryParse(conf['${key}_reach_$axis'] ?? '') ?? 1;
      final reaches = <String, double>{
        'left': reach('left', 'x'),
        'right': reach('right', 'x'),
        'up': reach('up', 'y'),
        'down': reach('down', 'y'),
      };
      final frame = <String, Object?>{
        'x': _round((x - rangeX) * width),
        'y': _round((y - rangeY) * height),
        'width': _round(2 * rangeX * width),
        'height': _round(2 * rangeY * height),
      };
      final edges = <String, Object?>{
        'top': _round(math.max(0, reaches['up']! - 1) * rangeY * height),
        'bottom': _round(math.max(0, reaches['down']! - 1) * rangeY * height),
        'left': _round(math.max(0, reaches['left']! - 1) * rangeX * width),
        'right': _round(math.max(0, reaches['right']! - 1) * rangeX * width),
      };
      final asset = image(conf['${key}_overlay']);
      Map<String, Object?>? item;
      // RetroArch: a zero reach is a zero-size hit box, never pressed (the
      // button images over an eight-way area): drawn as decoration only.
      final untouchable = reaches.values.any((value) => value <= 0);
      final decorationOnly = untouchable || (names.length == 1 && (names.first == 'nul' || names.first == 'null'));
      if (decorationOnly) {
        if (asset != null) {
          items.add(<String, Object?>{
            'inputs': <String>[],
            'frame': frame,
            'asset': <String, Object?>{'normal': asset},
          });
        }
        continue;
      }

      if (names.length == 1 && (names.first == 'dpad_area' || names.first == 'abxy_area')) {
        final dpad = names.first == 'dpad_area';
        final defaults = dpad
            ? const <String, String>{'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right'}
            : const <String, String>{'up': 'x', 'down': 'b', 'left': 'y', 'right': 'a'};
        final inputs = <String, Object?>{};
        for (final direction in const <String>['up', 'down', 'left', 'right']) {
          final redefined = conf['${key}_$direction']?.split('|').first.trim().toLowerCase();
          final retroPad = retroPadIds[redefined ?? defaults[direction]!];
          inputs[direction] = retroPad == null ? '' : (logical[retroPad] ?? '');
        }
        item = <String, Object?>{'inputs': inputs, 'frame': frame, 'extendedEdges': edges};
        if (asset != null) item['asset'] = <String, Object?>{'normal': asset};
      } else if (names.length == 1 && (names.first == 'analog_left' || names.first == 'analog_right')) {
        final prefix = names.first == 'analog_left' ? 'leftStick' : 'rightStick';
        final inputs = <String, Object?>{
          'up': '${prefix}Up',
          'down': '${prefix}Down',
          'left': '${prefix}Left',
          'right': '${prefix}Right',
        };
        item = <String, Object?>{'inputs': inputs, 'frame': frame, 'extendedEdges': edges};
        if (asset != null) {
          item['thumbstick'] = <String, Object?>{
            'name': asset,
            'width': frame['width'],
            'height': frame['height'],
          };
        }
      } else {
        final inputs = <String>[];
        var control = true;
        for (final name in names) {
          final retroPad = retroPadIds[name];
          if (retroPad != null) {
            final input = logical[retroPad];
            if (input != null) inputs.add(input);
            continue;
          }
          final stick = stickButtons[name];
          if (stick != null) {
            inputs.add(console == 'n64' && stick.startsWith('rightStick')
                ? 'c${stick.substring('rightStick'.length)}'
                : stick);
            continue;
          }
          final command = commands[name];
          if (command != null) {
            inputs.add(command);
            continue;
          }
          if (name == 'overlay_next') {
            final target = conf['${key}_next_target']?.toLowerCase() ?? '';
            final targetPage = pages.values.where((other) => other.name.toLowerCase() == target).firstOrNull;
            if (targetPage != null && targetPage.pause) {
              inputs.add('menu');
            } else {
              // Orientation switch or a page NeoStation does not draw: it
              // rotates by itself.
              control = false;
            }
            continue;
          }
          dropped.add(name);
        }
        if (!control || inputs.isEmpty) continue;
        item = <String, Object?>{'inputs': inputs.toSet().toList(), 'frame': frame, 'extendedEdges': edges};
        if (asset != null) item['asset'] = <String, Object?>{'normal': asset};
      }
      items.add(item);
      final itemFrame = math.Rectangle<double>(
        (frame['x']! as num).toDouble(),
        (frame['y']! as num).toDouble(),
        (frame['width']! as num).toDouble(),
        (frame['height']! as num).toDouble(),
      );
      controlFrames.add(itemFrame);
    }

    final representation = <String, Object?>{
      'mappingSize': <String, Object?>{'width': _round(width), 'height': _round(height)},
      'translucent': true,
      'items': items,
    };
    final background = image(page.background);
    if (background != null) representation['assets'] = <String, Object?>{'medium': background};

    if (portrait) {
      // The game takes the room above the topmost control (the frames of
      // the shoulder buttons included).
      final top = controlFrames.isEmpty ? height : controlFrames.map((frame) => frame.top).reduce(math.min);
      final room = top - height * 0.01;
      if (room < height * 0.2) {
        problems.add('no room for the game above the controls in portrait');
        return null;
      }
      representation['screens'] = _screens(console, 0, 0, width, room);
    } else if (console == 'nds') {
      representation['screens'] = _screens(console, 0, 0, width, height);
    }
    if (console == 'nds') {
      final screens = representation['screens']! as List<Map<String, Object?>>;
      final bottom = screens.last['outputFrame']! as Map<String, Object?>;
      items.add(<String, Object?>{
        'inputs': <String, Object?>{'x': 'touchScreenX', 'y': 'touchScreenY'},
        'frame': bottom,
      });
    }
    return representation;
  }

  /// Screens of the game area: one picture aspect-fitted by NeoStation, or
  /// for the DS both screens stacked (256 x 384, as DeSmuME renders them).
  static List<Map<String, Object?>> _screens(String console, double x, double y, double width, double height) {
    if (console != 'nds') {
      return <Map<String, Object?>>[
        <String, Object?>{
          'outputFrame': <String, Object?>{'x': _round(x), 'y': _round(y), 'width': _round(width), 'height': _round(height)},
        },
      ];
    }
    final scale = math.min(width / 256, height / 384);
    final screenWidth = 256 * scale, screenHeight = 192 * scale;
    final left = x + (width - screenWidth) / 2;
    final top = y + (height - 2 * screenHeight) / 2;
    Map<String, Object?> screen(double offset, double inputY) => <String, Object?>{
          'inputFrame': <String, Object?>{'x': 0, 'y': inputY, 'width': 256, 'height': 192},
          'outputFrame': <String, Object?>{
            'x': _round(left),
            'y': _round(top + offset),
            'width': _round(screenWidth),
            'height': _round(screenHeight),
          },
        };
    return <Map<String, Object?>>[screen(0, 0), screen(screenHeight, 192)];
  }

  static double _round(num value) => (value * 100).roundToDouble() / 100;

  /// `key = value` lines; quotes removed; `#` comments ignored.
  static Map<String, String> _parse(String text) {
    final values = <String, String>{};
    for (final rawLine in text.split(RegExp(r'\r?\n'))) {
      final line = rawLine.trim();
      if (line.isEmpty || line.startsWith('#')) continue;
      final equals = line.indexOf('=');
      if (equals <= 0) continue;
      final key = line.substring(0, equals).trim();
      var value = line.substring(equals + 1).trim();
      if (value.startsWith('"')) {
        final end = value.indexOf('"', 1);
        value = end > 0 ? value.substring(1, end) : value.substring(1);
      } else {
        final comment = value.indexOf('#');
        if (comment >= 0) value = value.substring(0, comment).trim();
      }
      values[key] = value;
    }
    return values;
  }
}

/// One overlay page.
class _Page {
  _Page(this.index, Map<String, String> conf)
      : name = conf['overlay${index}_name'] ?? '',
        fullScreen = (conf['overlay${index}_full_screen'] ?? 'false').toLowerCase() == 'true',
        normalized = (conf['overlay${index}_normalized'] ?? 'false').toLowerCase() == 'true',
        aspect = double.tryParse(conf['overlay${index}_aspect_ratio'] ?? conf['aspect_ratio'] ?? ''),
        background = conf['overlay${index}_overlay'],
        descCount = int.tryParse(conf['overlay${index}_descs'] ?? '') ?? 0;

  final int index;
  final String name;
  final bool fullScreen;
  final bool normalized;
  final double? aspect;
  final String? background;
  final int descCount;

  /// A pause or menu page (reached by overlay_next): NeoStation's own menu
  /// replaces it.
  bool get pause {
    final lower = name.toLowerCase();
    return lower.contains('pause') || lower.contains('menu');
  }

  /// Not a playing layout.
  bool get auxiliary {
    final lower = name.toLowerCase();
    return pause || lower.contains('hide') || lower.contains('hidden') || lower.contains('collapsed');
  }
}

/// Result of [LibretroOverlayConverter.convert].
class LibretroOverlayConversion {
  const LibretroOverlayConversion({
    required this.info,
    required this.files,
    required this.problems,
    required this.droppedCommands,
    required this.orientations,
  });

  /// The Delta skin description (info.json).
  final Map<String, Object?> info;

  /// Skin-relative image path -> path in the overlay's repository.
  final Map<String, String> files;

  /// Why the overlay cannot be converted faithfully (empty when it can).
  final List<String> problems;

  /// RetroArch commands without a NeoStation equivalent, left out.
  final List<String> droppedCommands;

  /// "portrait", "landscape" layouts produced.
  final List<String> orientations;

  bool get converted => problems.isEmpty && orientations.isNotEmpty;
}
