import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

import 'enhancement_models.dart';

/// Turns a catalogue record that points into its sources' original files
/// into the record the adapters read.
///
/// Sources without a licence are not hosted by RewindBox: their record lists
/// `origin` files (source, path, size, SHA-256 at a pinned revision) and,
/// for each code, a pointer into one of them: `{o: file, k: key}` for a
/// Switch title file, `[file, start, end]` (a byte range) for a PS2 pnach.
/// The catalogue downloads and verifies those files; this class reads the
/// codes out of them with the same rules as tools/enhancements.
abstract final class EnhancementOrigin {
  static final _switchLine = RegExp(r'^[0-9A-Fa-f]{8}( [0-9A-Fa-f]{8}){0,3}$');

  /// The origin files a record needs, or empty for a hosted record.
  static List<Map<String, dynamic>> files(Map<String, dynamic> record) => [
    for (final file in (record['origin'] as List? ?? const []))
      if (file is Map) Map<String, dynamic>.from(file),
  ];

  /// Opcode words of one Atmosphere section, or null when a line is not one
  /// (`switch_lines` of the builder).
  static List<String>? switchLines(Iterable<String> body) {
    final lines = <String>[];
    for (final raw in body) {
      final line = raw.trim();
      if (line.isEmpty) continue;
      if (!_switchLine.hasMatch(line)) return null;
      lines.add(line.toUpperCase());
    }
    if (lines.isEmpty || lines.length > 512) return null;
    return lines;
  }

  /// The record of [engine] with every pointer replaced by its code, read
  /// from the verified [contents] of its origin files (same order).
  static Map<String, dynamic> resolve(
    EnhancementEngine engine,
    Map<String, dynamic> record,
    List<Uint8List> contents,
  ) {
    switch (engine) {
      case EnhancementEngine.melonx:
        return _resolveSwitch(record, contents);
      case EnhancementEngine.armsx2:
        return _resolvePs2(record, contents);
      default:
        throw EnhancementException('origin_kind', engine.name);
    }
  }

  /// PS2 cheat files: `parts` alternates RewindBox's own text with pointers
  /// `[file, start, end]` to the lines of a group in a source's pnach file.
  /// The text is rebuilt as the builder wrote it (strict UTF-8, carriage
  /// returns removed) and must have the size and SHA-256 the catalogue
  /// lists; the adapter then reads `text` as for a hosted file.
  static Map<String, dynamic> _resolvePs2(Map<String, dynamic> record, List<Uint8List> contents) {
    final files = <String, dynamic>{};
    for (final item in (record['files'] as Map? ?? const {}).entries) {
      final payload = item.value;
      final parts = payload is Map ? payload['parts'] : null;
      if (payload is! Map || parts is! List) {
        files[item.key.toString()] = payload;
        continue;
      }
      final text = StringBuffer();
      for (final part in parts) {
        if (part is String) {
          text.write(part);
          continue;
        }
        if (part is! List || part.length != 3) throw const EnhancementException('origin_format');
        final index = part[0];
        final start = part[1];
        final end = part[2];
        if (index is! int ||
            start is! int ||
            end is! int ||
            index < 0 ||
            index >= contents.length ||
            start < 0 ||
            end < start ||
            end > contents[index].length) {
          throw const EnhancementException('origin_format');
        }
        try {
          text.write(utf8.decode(Uint8List.sublistView(contents[index], start, end)).replaceAll('\r', ''));
        } on FormatException {
          throw const EnhancementException('origin_format');
        }
      }
      final value = text.toString();
      final encoded = utf8.encode(value);
      if (encoded.length != payload['size'] || sha256.convert(encoded).toString() != payload['sha256']) {
        throw EnhancementException('origin_integrity', payload['name']?.toString() ?? '');
      }
      files[item.key.toString()] = {
        for (final field in payload.entries)
          if (field.key != 'parts') field.key.toString(): field.value,
        'text': value,
      };
    }
    return {...record, 'files': files};
  }

  /// switch-cheats-db title files: `{BUILDID: {"[Name]": "[Name]\nwords..."}}`.
  static Map<String, dynamic> _resolveSwitch(Map<String, dynamic> record, List<Uint8List> contents) {
    final files = [
      for (final bytes in contents)
        switch (jsonDecode(utf8.decode(bytes))) {
          final Map<String, dynamic> map => map,
          _ => throw const EnhancementException('origin_format'),
        },
    ];
    List<String>? read(String build, Object? pointer) {
      if (pointer is! Map) return null;
      final index = pointer['o'];
      final key = pointer['k'];
      if (index is! int || index < 0 || index >= files.length || key is! String) return null;
      final codes = files[index][build];
      final code = codes is Map ? codes[key] : null;
      if (code == null) return null;
      return switchLines(code.toString().split('\n').skip(1));
    }

    final master = <String, dynamic>{};
    for (final build in (record['master'] as Map? ?? const {}).entries) {
      final lines = read(build.key.toString(), build.value);
      if (lines != null) master[build.key.toString()] = lines;
    }
    final entries = <Map<String, dynamic>>[];
    for (final raw in (record['entries'] as List? ?? const [])) {
      if (raw is! Map) continue;
      final entry = Map<String, dynamic>.from(raw);
      final builds = <String, dynamic>{};
      for (final build in (entry['builds'] as Map? ?? const {}).entries) {
        final lines = read(build.key.toString(), build.value);
        if (lines != null) builds[build.key.toString()] = lines;
      }
      // An entry is kept only with every build it was published for.
      if (builds.isEmpty || builds.length != (entry['builds'] as Map).length) continue;
      entries.add({...entry, 'builds': builds});
    }
    return {...record, 'master': master, 'entries': entries};
  }
}
