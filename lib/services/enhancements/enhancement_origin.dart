import 'dart:convert';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart';

import 'enhancement_models.dart';

/// Turns a catalogue record that points into its sources' original files
/// into the record the adapters read.
///
/// Sources without a licence are not hosted by RewindBox: their record lists
/// `origin` files (source, path, size, SHA-256 at a pinned revision) and,
/// for each code, a pointer into one of them: `{o: file, k: key}` for a
/// Switch title file, `{bid, o: file, size, sha256}` for a Switch exefs
/// patch file, `[file, start, end]` (a byte range) for a PS2 pnach.
/// The catalogue downloads and verifies those files; this class reads the
/// codes out of them with the same rules as tools/enhancements.
abstract final class EnhancementOrigin {
  static final _switchLine = RegExp(r'^[0-9A-Fa-f]{8}( [0-9A-Fa-f]{8}){0,3}$');

  /// The origin files a record needs, or empty for a hosted record.
  static List<Map<String, dynamic>> files(Map<String, dynamic> record) => [
    for (final file in (record['origin'] as List? ?? const []))
      if (file is Map) Map<String, dynamic>.from(file),
  ];

  static final _pchtxtHeader = RegExp(r'^@nsobid-([0-9A-Fa-f]{32,64})$');

  /// The text RewindBox writes for an IPSwitch patch file (`pchtxt_text` of the
  /// builder): strict UTF-8, carriage returns removed, the Build ID of the
  /// first line in upper case (Ryujinx compares it case-sensitively), one
  /// final newline. Null when the file is not such a patch.
  static String? pchtxtText(Uint8List bytes) {
    final String text;
    try {
      text = utf8.decode(bytes);
    } on FormatException {
      return null;
    }
    final lines = text.replaceAll('\r', '').split('\n');
    final header = _pchtxtHeader.firstMatch(lines.first);
    if (header == null) return null;
    var body = ['@nsobid-${header.group(1)!.toUpperCase()}', ...lines.skip(1)].join('\n');
    if (!body.endsWith('\n')) body += '\n';
    return body.length <= 64 * 1024 ? body : null;
  }

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

  /// The record without what it reads from its sources' files, for an engine
  /// whose record stays useful without them; null when the whole record
  /// depends on them (Switch).
  ///
  /// A PS2 record also lists the patches the engine itself ships, enabled by
  /// name. They must stay usable when a source cannot be reached or no longer
  /// serves the pinned bytes: the cheat files built from pointers are left
  /// out, with the entries that need them.
  static Map<String, dynamic>? withoutOrigin(EnhancementEngine engine, Map<String, dynamic> record) {
    if (engine != EnhancementEngine.armsx2) return null;
    final files = <String, dynamic>{
      for (final item in (record['files'] as Map? ?? const {}).entries)
        if (item.value is Map && (item.value as Map)['text'] is String) item.key.toString(): item.value,
    };
    final entries = [
      for (final entry in (record['entries'] as List? ?? const []))
        if (entry is Map && (entry['kind'] != 'cheat' || files.containsKey(entry['crc']))) entry,
    ];
    return {
      for (final field in record.entries)
        if (field.key != 'origin') field.key: field.value,
      'files': files,
      'entries': entries,
    };
  }

  /// Origin files a record can lose without losing the rest: the Switch patch
  /// files only exefs mods point to. A mod whose file is missing is left out;
  /// the title's cheats, read from other files, stay.
  static Set<int> expendable(EnhancementEngine engine, Map<String, dynamic> record) {
    if (engine != EnhancementEngine.melonx) return const {};
    final needed = <int>{};
    final optional = <int>{};
    void note(Object? pointer, Set<int> into) {
      if (pointer is Map && pointer['o'] is int) into.add(pointer['o'] as int);
    }

    for (final value in (record['master'] as Map? ?? const {}).values) {
      note(value, needed);
    }
    for (final raw in (record['entries'] as List? ?? const [])) {
      if (raw is! Map) continue;
      for (final value in (raw['builds'] as Map? ?? const {}).values) {
        note(value, value is Map && value.containsKey('member') ? optional : needed);
      }
      for (final patch in (raw['exefs'] as List? ?? const [])) {
        note(patch, optional);
      }
    }
    return optional.difference(needed);
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
    // A title file is JSON; an exefs patch file is not. Each is read only when a pointer names it.
    final parsed = <int, Map<String, dynamic>>{};
    Map<String, dynamic> titleFile(int index) => parsed[index] ??= switch (jsonDecode(utf8.decode(contents[index]))) {
      final Map<String, dynamic> map => map,
      _ => throw const EnhancementException('origin_format'),
    };
    final archives = <int, Archive>{};
    Uint8List? member(int index, Map pointer) {
      final name = pointer['member'];
      final size = pointer['rawSize'];
      if (name is! String || size is! int || size < 1 || size > 65536 ||
          contents[index].isEmpty || name.contains(r'\') ||
          name.split('/').any((part) => part.isEmpty || part == '..' || part == '.')) {
        return null;
      }
      // The catalogue verified the entire pinned ZIP. Read only the named patch in memory.
      final archive = archives[index] ??= ZipDecoder().decodeBytes(contents[index]);
      final file = archive.findFile(name);
      if (file == null || !file.isFile || file.size != size) return null;
      final bytes = file.readBytes();
      return bytes != null && bytes.length == size ? bytes : null;
    }
    List<String>? read(String build, Object? pointer) {
      if (pointer is! Map) return null;
      final index = pointer['o'];
      final key = pointer['k'];
      if (index is! int || index < 0 || index >= contents.length || key is! String) return null;
      if (pointer.containsKey('member')) {
        final bytes = member(index, pointer);
        if (bytes == null) return null;
        final lines = utf8.decode(bytes).replaceAll('\r', '').split('\n').map((line) => line.trim()).toList();
        final start = lines.indexOf(key);
        if (start < 0) return null;
        return switchLines(lines.skip(start + 1).takeWhile((line) => !line.startsWith('[') && !line.startsWith('{')));
      }
      final codes = titleFile(index)[build];
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
    // Entries this record cannot offer now (a source file that could not be fetched or verified).
    final unavailable = <Map<String, dynamic>>[];
    for (final raw in (record['entries'] as List? ?? const [])) {
      if (raw is! Map) continue;
      final entry = Map<String, dynamic>.from(raw);
      final kept = entries.length;
      _resolveSwitchEntry(entry, entries, contents, member, read);
      if (entries.length == kept && entry['id'] != null) {
        unavailable.add({
          'id': entry['id'].toString(),
          'cat': entry['cat'],
          if (entry['group'] != null) 'group': entry['group'],
          'exefs': entry['exefs'] is List,
          'cheat': entry.containsKey('builds'),
        });
      }
    }
    return {
      ...record,
      'master': master,
      'entries': entries,
      if (unavailable.isNotEmpty) 'unavailable': unavailable,
    };
  }

  static void _resolveSwitchEntry(
    Map<String, dynamic> entry,
    List<Map<String, dynamic>> entries,
    List<Uint8List> contents,
    Uint8List? Function(int index, Map patch) member,
    List<String>? Function(String build, Object? pointer) read,
  ) {
    final exefs = entry['exefs'];
    if (exefs is List) {
      // Exefs patches: each pointer names a .pchtxt file of the source. The text the adapter
      // writes is rebuilt as the builder did and must have the listed size and SHA-256.
      final patches = <Map<String, dynamic>>[];
      for (final patch in exefs) {
        if (patch is! Map) continue;
        if (patch['text'] is String) {
          patches.add(Map<String, dynamic>.from(patch));
          continue;
        }
        final index = patch['o'];
        if (index is! int || index < 0 || index >= contents.length) continue;
        final bytes = patch.containsKey('member') ? member(index, patch) : contents[index];
        final text = bytes == null ? null : pchtxtText(bytes);
        if (text == null || !text.startsWith('@nsobid-${patch['bid']}\n')) continue;
        final encoded = utf8.encode(text);
        if (encoded.length != patch['size'] || sha256.convert(encoded).toString() != patch['sha256']) continue;
        patches.add({'bid': patch['bid'], 'text': text});
      }
      // Like a cheat, a mod is kept only with every patch it was published with.
      if (patches.isEmpty || patches.length != exefs.length) return;
      entry['exefs'] = patches;
      if (!entry.containsKey('builds')) {
        entries.add(entry);
        return;
      }
    }
    final builds = <String, dynamic>{};
    for (final build in (entry['builds'] as Map? ?? const {}).entries) {
      final lines = read(build.key.toString(), build.value);
      if (lines != null) builds[build.key.toString()] = lines;
    }
    // An entry is kept only with every build it was published for.
    if (builds.isEmpty || builds.length != (entry['builds'] as Map).length) return;
    entries.add({...entry, 'builds': builds});
  }
}
