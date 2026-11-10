import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as path;

/// The alias table of a compact System Art pack (`aliases.json`, RewindBox
/// Glacier): one image per canonical system, and a table mapping every other
/// spelling a library may use ("Super Nintendo", "sfc-hacks", "ColecoVision",
/// "NEC PC-8000/8800"...) to its canonical system.
///
/// The table is data, never a list of paths or of playable systems:
/// - an exact canonical identifier always wins (`pspminis` is PSP Minis, not
///   PSP);
/// - other names are matched case-insensitively (trimmed, accents composed),
///   so case variants resolve on a case-sensitive file system too;
/// - aliases containing a separator stay logical keys: only the canonical
///   identifier they resolve to is ever used to build a path, and only when it
///   is a plain file name declared by the pack.
class SystemArtAliasTable {
  SystemArtAliasTable._(this.canonicalIds, this._owners);

  final Set<String> canonicalIds;
  final Map<String, String> _owners;

  static final RegExp _plainName = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]*$');
  static final Map<String, SystemArtAliasTable?> _cache = {};

  int get keyCount => _owners.length;

  /// The table of the pack installed in [packDirectory] (read once, cached;
  /// null when the pack has none).
  static SystemArtAliasTable? forPackSync(String packDirectory) {
    if (_cache.containsKey(packDirectory)) return _cache[packDirectory];
    SystemArtAliasTable? table;
    try {
      final file = File(path.join(packDirectory, 'aliases.json'));
      if (file.existsSync()) table = parse(file.readAsStringSync());
    } catch (_) {
      table = null;
    }
    _cache[packDirectory] = table;
    return table;
  }

  /// Forgets a cached table (after a pack was installed or replaced).
  static void invalidate([String? packDirectory]) {
    if (packDirectory == null) {
      _cache.clear();
    } else {
      _cache.remove(packDirectory);
    }
  }

  static SystemArtAliasTable? parse(String source) {
    final decoded = jsonDecode(source);
    if (decoded is! Map || decoded['schema'] != 1) return null;
    final canonical = <String>{
      for (final id in (decoded['canonicalIds'] as List? ?? const []))
        if (id is String && _plainName.hasMatch(id)) id,
    };
    if (canonical.isEmpty) return null;
    final owners = <String, String>{};
    final lookup = decoded['lookup'];
    if (lookup is Map) {
      lookup.forEach((key, value) {
        if (key is! String || value is! Map) return;
        final owner = value['owner'];
        if (owner is! String || !canonical.contains(owner)) return;
        owners.putIfAbsent(normalize(key), () => owner);
        for (final spelling in (value['spellings'] as List? ?? const [])) {
          if (spelling is String) {
            owners.putIfAbsent(normalize(spelling), () => owner);
          }
        }
      });
    }
    // Every canonical identifier is its own key, before any alias.
    for (final id in canonical) {
      owners[normalize(id)] = owners[normalize(id)] ?? id;
    }
    return SystemArtAliasTable._(canonical, owners);
  }

  /// The canonical identifier [name] refers to, or null.
  String? resolve(String name) {
    if (canonicalIds.contains(name)) return name;
    return _owners[normalize(name)];
  }

  /// Trim, compose the common decomposed accents (NFC for Latin letters) and
  /// fold case.
  static String normalize(String value) {
    var text = value.trim();
    if (text.contains(RegExp('[̀-̈]'))) {
      const marks = {
        '́': 'áéíóúý',
        '̀': 'àèìòùỳ',
        '̂': 'âêîôûŷ',
        '̈': 'äëïöüÿ',
      };
      const bases = 'aeiouy';
      final buffer = StringBuffer();
      for (var i = 0; i < text.length; i++) {
        final char = text[i];
        final next = i + 1 < text.length ? text[i + 1] : '';
        final composed = marks[next];
        final base = bases.indexOf(char.toLowerCase());
        if (composed != null && base >= 0) {
          final letter = composed[base];
          buffer.write(
            char == char.toUpperCase() ? letter.toUpperCase() : letter,
          );
          i++;
        } else {
          buffer.write(char);
        }
      }
      text = buffer.toString();
    }
    return text.toLowerCase();
  }
}
