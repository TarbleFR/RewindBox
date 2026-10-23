import 'dart:convert';

/// File-provider aliases are normalized only in a private import copy. The
/// native reader remains authoritative for supported names and exact sizes.
abstract final class MelonxKeyFile {
  static String? canonicalName(String name) {
    final match = RegExp(
      r'^(prod|title)(?:\s*\([0-9]+\))?\.keys(?:\.txt)?$',
      caseSensitive: false,
    ).firstMatch(name.trim());
    return match == null ? null : '${match[1]!.toLowerCase()}.keys';
  }

  static String normalize(List<int> bytes, String name) {
    if (bytes.isEmpty || bytes.length > 4 * 1024 * 1024) {
      throw const FormatException('keySyntax');
    }
    String text;
    if (bytes.length >= 2 &&
        ((bytes[0] == 0xff && bytes[1] == 0xfe) ||
            (bytes[0] == 0xfe && bytes[1] == 0xff))) {
      if (bytes.length.isOdd) throw const FormatException('keySyntax');
      final little = bytes[0] == 0xff;
      text = String.fromCharCodes([
        for (var i = 2; i < bytes.length; i += 2)
          little ? bytes[i] | (bytes[i + 1] << 8) : (bytes[i] << 8) | bytes[i + 1],
      ]);
    } else {
      try {
        text = utf8.decode(bytes);
      } on FormatException {
        throw const FormatException('keySyntax');
      }
    }
    final entries = <String>[];
    final pattern = name == 'title.keys'
        ? RegExp(r'^([a-f0-9]{32})\s*[=,]\s*([a-f0-9]{32})$')
        : RegExp(r'^([a-z0-9_]+)\s*[=,]\s*([a-f0-9]+)$');
    for (final line in const LineSplitter().convert(text)) {
      final value = line.trim().toLowerCase();
      if (value.isEmpty || value.startsWith('#')) continue;
      final match = pattern.firstMatch(value);
      if (match == null || match[2]!.length.isOdd) {
        throw const FormatException('keySyntax');
      }
      final canonical = '${match[1]} = ${match[2]}';
      if (canonical.length >= 2048) throw const FormatException('keySyntax');
      entries.add(canonical);
    }
    if (entries.isEmpty) throw const FormatException('keyNoSupported');
    return entries.join('\n');
  }
}
