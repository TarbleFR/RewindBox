import 'dart:convert';
import 'dart:typed_data';

/// Rebuilds the code fields of a catalogue program from its origin file.
///
/// Port of tools/cheats/origin/recipe.py, which is the reference: both run
/// against every published program (tools/cheats/origin/skeleton.py and
/// test/cheat_origin_recipe_test.dart). Python's string semantics are kept
/// exactly (str.strip, str.splitlines, re `\s`, cp1252), since the rebuilt
/// chunk must have the published SHA-256.
abstract final class OriginRecipe {
  /// Characters `str.isspace()` accepts (`\s` of Python's `re` on str).
  static const _space = {
    0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x85, 0xA0, 0x1680, //
    0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200A, //
    0x2028, 0x2029, 0x202F, 0x205F, 0x3000,
  };

  /// Line boundaries of `str.splitlines()` (besides "\r\n").
  static const _lineBreaks = {0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D, 0x1E, 0x85, 0x2028, 0x2029};

  static const _simple = {
    'nes-gamegenie', 'nes-raw', 'snes-gamegenie', 'snes-par', 'gb-gameshark', 'gb-gamegenie', //
    'md-gamegenie', 'md-raw', 'sega8-gamegenie', 'sega8-raw',
  };
  static const _paired = {
    'ds-actionreplay', 'ps1-gameshark', 'gba-gameshark-v1', 'gba-gameshark-v3', 'gba-codebreaker', //
    'gba-unknown', 'gba-auto', 'n64-gameshark', 'gateshark', 'ctrpf', 'gecko', 'actionReplay',
  };
  static const _normalised = {
    ..._simple, 'ds-actionreplay', 'ps1-gameshark', 'gba-gameshark-v1', 'gba-gameshark-v3', //
    'gba-codebreaker', 'gba-auto', 'gba-vba-raw', 'n64-gameshark', 'cwcheat', 'pce-raw', 'wswan-raw',
  };
  static const _literals = {'\n', ':', '?', '+'};

  // ------------------------------------------------------------ Python text

  static bool _isSpace(int rune) => _space.contains(rune);

  static String strip(String value) {
    final runes = value.runes.toList();
    var start = 0, end = runes.length;
    while (start < end && _isSpace(runes[start])) {
      start++;
    }
    while (end > start && _isSpace(runes[end - 1])) {
      end--;
    }
    return String.fromCharCodes(runes.sublist(start, end));
  }

  static List<String> splitLines(String value) {
    final lines = <String>[];
    final runes = value.runes.toList();
    var start = 0, i = 0;
    while (i < runes.length) {
      final rune = runes[i];
      if (_lineBreaks.contains(rune)) {
        lines.add(String.fromCharCodes(runes.sublist(start, i)));
        i += rune == 0x0D && i + 1 < runes.length && runes[i + 1] == 0x0A ? 2 : 1;
        start = i;
      } else {
        i++;
      }
    }
    if (start < runes.length) lines.add(String.fromCharCodes(runes.sublist(start)));
    return lines;
  }

  /// `re.split(r"[+;,\s]+", value)` without empty parts.
  static List<String> separatorParts(String value) {
    final parts = <String>[];
    final current = StringBuffer();
    for (final rune in value.runes) {
      if (rune == 0x2B || rune == 0x3B || rune == 0x2C || _isSpace(rune)) {
        if (current.isNotEmpty) parts.add(current.toString());
        current.clear();
      } else {
        current.writeCharCode(rune);
      }
    }
    if (current.isNotEmpty) parts.add(current.toString());
    return parts;
  }

  static const _cp1252 = <int, int>{
    0x80: 0x20AC, 0x82: 0x201A, 0x83: 0x0192, 0x84: 0x201E, 0x85: 0x2026, 0x86: 0x2020, 0x87: 0x2021, //
    0x88: 0x02C6, 0x89: 0x2030, 0x8A: 0x0160, 0x8B: 0x2039, 0x8C: 0x0152, 0x8E: 0x017D, 0x91: 0x2018, //
    0x92: 0x2019, 0x93: 0x201C, 0x94: 0x201D, 0x95: 0x2022, 0x96: 0x2013, 0x97: 0x2014, 0x98: 0x02DC, //
    0x99: 0x2122, 0x9A: 0x0161, 0x9B: 0x203A, 0x9C: 0x0153, 0x9E: 0x017E, 0x9F: 0x0178,
  };

  static String decode(Uint8List bytes, String encoding) {
    if (encoding != 'cp1252') return utf8.decode(bytes);
    final out = StringBuffer();
    for (final byte in bytes) {
      if (byte >= 0x80 && byte <= 0x9F) {
        final mapped = _cp1252[byte];
        if (mapped == null) throw const FormatException('undefined cp1252 byte');
        out.writeCharCode(mapped);
      } else {
        out.writeCharCode(byte);
      }
    }
    return out.toString();
  }

  /// The encoding the publisher used for a member: UTF-8, else cp1252.
  static String encodingOf(Uint8List bytes) {
    try {
      utf8.decode(bytes);
      return 'utf-8';
    } on FormatException {
      return 'cp1252';
    }
  }

  // ------------------------------------------------------------ fields

  static String _hex(int value, int width) => value.toRadixString(16).toUpperCase().padLeft(width, '0');

  /// unified_catalogue.program_lines for the dialects of origin programs.
  static List<String> programLines(String code, String dialect) {
    if (const {'pnach', 'rpcs3-yaml', 'ps3-static-be32'}.contains(dialect)) return splitLines(code);
    if (_simple.contains(dialect) || dialect == 'gba-vba-raw') {
      return [for (final p in separatorParts(code)) p.toUpperCase()];
    }
    if (dialect == 'pce-raw' || dialect == 'wswan-raw') {
      var lines = [for (final p in separatorParts(code)) p.toUpperCase()];
      if (dialect == 'wswan-raw') {
        lines = [
          for (final p in lines)
            if (RegExp(r'^[0-9A-F]{1,8}:[0-9A-F]{2}$').hasMatch(p) && int.parse(p.split(':')[0], radix: 16) <= 0xFFFF)
              '${_hex(int.parse(p.split(':')[0], radix: 16), 4)}:${p.split(':')[1]}'
            else
              p,
        ];
      }
      return lines;
    }
    if (dialect == 'cwcheat') {
      return [
        for (final line in splitLines(code))
          if (strip(line).isNotEmpty) line.toUpperCase().replaceAll('0X', ''),
      ];
    }
    if (_paired.contains(dialect)) {
      var tokens = separatorParts(code.toUpperCase());
      if (dialect == 'n64-gameshark') tokens = [for (final s in tokens) s.startsWith('0X') ? s.substring(2) : s];
      final width = const {'ps1-gameshark', 'n64-gameshark', 'gba-codebreaker'}.contains(dialect) ? 4 : 8;
      final whole = dialect == 'gba-auto'
          ? RegExp(r'^(?:[A-F0-9]{12}|[A-F0-9]{16})$')
          : RegExp('^[A-F0-9]{${8 + width}}\$');
      final lines = <String>[];
      var n = 0;
      while (n < tokens.length) {
        final token = tokens[n];
        if (whole.hasMatch(token)) {
          lines.add('${token.substring(0, 8)} ${token.substring(8)}');
          n++;
        } else if (n + 1 < tokens.length) {
          lines.add('$token ${tokens[n + 1]}');
          n += 2;
        } else {
          lines.add(token);
          n++;
        }
      }
      return lines;
    }
    return splitLines(code);
  }

  /// recipe.derive: the fields review_program gives a program read as [raw].
  static Map<String, dynamic> derive(
    String raw,
    String dialect, {
    bool plus = false,
    String? sourceCode,
    bool drop = false,
  }) {
    final lines = programLines(raw, dialect);
    var code = strip(raw);
    final fields = <String, dynamic>{'code': code, 'lines': lines};
    if (sourceCode != null) fields['source_code'] = sourceCode;
    if (dialect == 'cwcheat' && code != lines.join('\n')) {
      fields['source_code'] = code;
      fields['code'] = code = lines.join('\n');
    }
    if (_normalised.contains(dialect)) {
      final normalised = plus ? [for (final p in lines) p.replaceAll(' ', '')].join('+') : lines.join('\n');
      if (code != normalised) {
        fields.putIfAbsent('source_code', () => code);
        fields['code'] = normalised;
      }
    }
    if (drop) fields.remove('source_code');
    return fields;
  }

  /// recipe.raw_text over one member.
  static String rawText(List<dynamic> items, Uint8List data, String encoding) {
    final out = StringBuffer();
    for (final item in items) {
      if (item is String) {
        if (!_literals.contains(item)) throw const FormatException('recipe literal is not a separator');
        out.write(item);
        continue;
      }
      final range = item as List;
      final start = range[0] as int, end = range[1] as int;
      if (start < 0 || end < start || end > data.length) throw const FormatException('recipe range');
      var value = decode(Uint8List.sublistView(data, start, end), encoding);
      if (range.length > 2) {
        if (range[2] != 'x') throw const FormatException('recipe transform');
        value = strip(value.replaceAll('0x', '')).toUpperCase();
      }
      out.write(value);
    }
    return out.toString();
  }

  /// recipe.mister: a converted MiSTer tuple program, or null.
  static (String code, String dialect, String source)? mister(Uint8List raw, String system) {
    if (raw.isEmpty || raw.length % 16 != 0 || raw.length > 128 * 1024) return null;
    final view = ByteData.sublistView(raw);
    final rows = [
      for (var n = 0; n < raw.length; n += 16) [for (var w = 0; w < 4; w++) view.getUint32(n + 4 * w, Endian.little)],
    ];
    if ((system == 'nes' && rows.length > 100) || (system == 'gba' && rows.length > 128)) return null;
    final lines = <String>[];
    final addresses = <int>{};
    String dialect;
    if (system == 'nes') {
      for (final [flags, address, compare, value] in rows) {
        if ((flags != 0 && flags != 1) || address < 0x8000 || address > 0xFFFF || value > 0xFF || compare > 0xFF) {
          return null;
        }
        if (!addresses.add(address)) return null;
        lines.add(
          flags == 1
              ? '${_hex(address, 4)}?${_hex(compare, 2)}:${_hex(value, 2)}'
              : '${_hex(address, 4)}:${_hex(value, 2)}',
        );
      }
      dialect = 'nes-raw';
    } else if (system == 'psx') {
      for (var index = 0; index < rows.length; index++) {
        final [flags, address, _, value0] = rows[index];
        var value = value0;
        var offset = address & 0x1FFFFFFF;
        final operation = flags & 15, mask = flags & 0xF0;
        if (flags > 255 ||
            !const {0x10, 0x20, 0x30}.contains(mask) ||
            !const {0, 1, 2, 6}.contains(operation) ||
            !const {0x00, 0x80, 0xA0}.contains(address >> 24) ||
            offset >= 0x200000 ||
            offset % 2 != 0) {
          return null;
        }
        final width = mask == 0x30 ? 2 : 1;
        if (mask == 0x20) {
          if (value > 0xFFFF || value & 0xFF != 0) return null;
          offset += 1;
          value >>= 8;
        }
        if (value >= 1 << (8 * width) || offset % width != 0 || offset + width > 0x200000) return null;
        int opcode;
        if (operation != 0) {
          if (index + 1 >= rows.length || rows[index + 1][0] & 15 != 0) return null;
          opcode = (width == 1 ? 0xE0 : 0xD0) + const {1: 0, 2: 3, 6: 1}[operation]!;
        } else {
          for (var byte = 0; byte < width; byte++) {
            if (addresses.contains(offset + byte)) return null;
          }
          for (var byte = 0; byte < width; byte++) {
            addresses.add(offset + byte);
          }
          opcode = width == 1 ? 0x30 : 0x80;
        }
        lines.add('${_hex((opcode << 24) | offset, 8)} ${_hex(value, 4)}');
      }
      dialect = 'ps1-gameshark';
    } else if (system == 'gba') {
      for (final [flags, address, _, value] in rows) {
        if (flags == 0 ||
            flags & ~0xF0 != 0 ||
            address % 4 != 0 ||
            !((address >= 0x02000000 && address <= 0x0203FFFC) || (address >= 0x03000000 && address <= 0x03007FFC))) {
          return null;
        }
        for (var lane = 0; lane < 4; lane++) {
          if (flags & (0x10 << lane) != 0) {
            lines.add('${_hex(address + lane, 8)}:${_hex((value >> (8 * lane)) & 0xFF, 2)}');
          }
        }
      }
      dialect = 'gba-vba-raw';
    } else {
      return null;
    }
    final source = [
      for (var n = 0; n < raw.length; n += 16)
        [for (final byte in raw.sublist(n, n + 16)) byte.toRadixString(16).padLeft(2, '0')].join().toUpperCase(),
    ].join('\n');
    return (lines.join('\n'), dialect, source);
  }

  static const _quoted = r'"((?:[^"\\]|\\.)*)"';

  static int _fbneoInteger(String value) {
    if (value.toLowerCase().startsWith('0x')) return int.parse(value.substring(2), radix: 16);
    if (value.length > 1 && value.startsWith('0')) return int.parse(value, radix: 8);
    return int.parse(value);
  }

  /// recipe.fbneo: the fields of an available FBNeo block.
  static Map<String, dynamic> fbneo(String raw) {
    final choices = <Map<String, dynamic>>[];
    int? fallback;
    for (final line in raw.split('\n').skip(1)) {
      final declared = RegExp(r'^default\s+(\d+)$').firstMatch(line);
      if (declared != null) {
        fallback = _fbneoInteger(declared[1]!);
        continue;
      }
      final choice = RegExp('^(\\d+)\\s+$_quoted(?:\\s*,\\s*(.*))?\$', dotAll: true).firstMatch(line);
      if (choice == null) throw const FormatException('not an available FBNeo block');
      final values = choice[3] != null && choice[3]!.isNotEmpty
          ? [for (final word in choice[3]!.split(',')) strip(word)]
          : <String>[];
      final writes = [
        for (var n = 0; n + 2 < values.length; n += 3)
          {'cpu': _fbneoInteger(values[n]), 'address': values[n + 1], 'value': values[n + 2]},
      ];
      final name = choice[2]!.replaceAll(r'\"', '"').replaceAll(r'\\', r'\');
      choices.add({'index': _fbneoInteger(choice[1]!), 'name': name, 'writes': writes});
    }
    return {
      'code': raw,
      'lines': splitLines(raw),
      'choices': choices,
      'native_document': {'source_default': fallback, 'import_default': 0, 'choices': choices},
    };
  }

  /// The code fields of one skeleton program from its origin member.
  static Map<String, dynamic> rebuild(Map<String, dynamic> origin, Uint8List member, String dialect) {
    final kind = origin['k'];
    if (kind == 'mister') {
      final converted = mister(member, origin['s'] as String);
      if (converted == null || converted.$2 != dialect) throw const FormatException('MiSTer program');
      return derive(converted.$1, dialect, plus: origin['n'] == 'plus', sourceCode: converted.$3);
    }
    final encoding = encodingOf(member);
    final raw = rawText(origin['r'] as List, member, encoding);
    if (kind == 'fbneo') return fbneo(raw);
    return derive(raw, dialect, plus: origin['n'] == 'plus', drop: origin['d'] == 1);
  }
}
