/// Minimal adapter for the small YAML subset used by RPCS3's configuration DB.
///
/// Database documents are maps (at most three levels deep) with scalar or list
/// leaves.  Editing lines in place preserves upstream values and lists while
/// avoiding a second YAML serialization dependency in the launch path.
abstract final class Rpcs3ConfigAdapter {
  /// Keys of the live official GameDB that this RPCS3 fork does not define
  /// (rpcs3/Emu/system_config.h). The Core validates every entry strictly and
  /// refuses the whole publication when one entry is invalid
  /// (RPCS3IOSConfigDatabase.cpp), so a single installed title carrying one of
  /// them (39 of 2294 live entries on 1 November 2026) would block every
  /// RewindBox title profile. They are desktop recommendations this Core
  /// cannot honour; every key the fork knows is kept.
  static const unsupportedUpstreamKeys = <String, String>{
    'Emulate HDD Read Speed': 'VFS',
    'Emulate BD-ROM Read Speed': 'VFS',
    'SPU MMIO Delay Enabled': 'Core',
  };

  static String sanitiseForIOS(String source) {
    final output = <String>[];
    String? section;
    for (final line in source.split('\n')) {
      final separator = line.indexOf(':');
      if (separator < 0) {
        output.add(line);
        continue;
      }
      final key = line.substring(0, separator).trim().replaceFirst('- ', '');
      final value = line.substring(separator + 1).trim();
      final indent = line.length - line.trimLeft().length;
      if (indent == 0) section = key;
      if (key == 'Renderer' && value == 'OpenGL') continue;
      if (key == 'Frame limit' && (value == 'Off' || value == 'Infinite')) {
        continue;
      }
      // Asynchronous texture streaming is a desktop recommendation (179 of
      // 2187 entries): a second transfer queue, synchronized with the graphics
      // queue by semaphores. On MoltenVK it has only ever produced defects on
      // the iPhone: God of War III was unplayable with it on IPA 724 (first
      // run of its database entry as is, 10 November 2026: graphics errors on
      // a fresh boot and on a savestate, against none on IPA 723 with it off),
      // after the Build 552 and Build 610 withdrawals for the same title and
      // for Assassin's Creed. The database entry keeps every other value; the
      // engine default (off) applies, and the per-game setting
      // "Asynchronous texture streaming" still turns it on for a title.
      if (key == 'Asynchronous Texture Streaming' && value == 'true') {
        continue;
      }
      if (indent == 2 && unsupportedUpstreamKeys[key] == section) continue;
      output.add(line);
    }
    return '${_dropEmptySections(output).join('\n').trim()}\n';
  }

  /// A section left without children decodes as null and fails the Core's
  /// "node is not a map" check, which would still invalidate the entry.
  /// Only sections emptied by [sanitiseForIOS] can exist here: upstream
  /// entries never publish an empty mapping.
  static List<String> _dropEmptySections(List<String> lines) {
    var current = lines;
    while (true) {
      final kept = <String>[];
      var removed = false;
      for (var index = 0; index < current.length; index++) {
        final line = current[index];
        final trimmed = line.trim();
        if (trimmed.endsWith(':') &&
            !trimmed.startsWith('- ') &&
            !trimmed.startsWith('#')) {
          final indent = line.length - line.trimLeft().length;
          var next = index + 1;
          while (next < current.length && current[next].trim().isEmpty) {
            next++;
          }
          final child = next < current.length ? current[next] : null;
          final childIndent =
              child == null ? -1 : child.length - child.trimLeft().length;
          final listChild = child != null &&
              child.trimLeft().startsWith('- ') &&
              childIndent >= indent;
          if (childIndent <= indent && !listChild) {
            removed = true;
            continue;
          }
        }
        kept.add(line);
      }
      if (!removed) return kept;
      current = kept;
    }
  }

  static String mergeScalarOverrides(
    String source,
    Map<List<String>, String> overrides,
  ) {
    var result = sanitiseForIOS(source);
    for (final entry in overrides.entries) {
      if (entry.key.isEmpty) continue;
      result = _setScalar(result, entry.key, entry.value);
    }
    return result;
  }

  static bool hasUsefulSetting(String source) {
    for (final line in source.split('\n')) {
      final separator = line.indexOf(':');
      if (separator >= 0 && line.substring(separator + 1).trim().isNotEmpty) {
        return true;
      }
      if (line.trimLeft().startsWith('- ')) return true;
    }
    return false;
  }

  static String _setScalar(String source, List<String> path, String value) {
    final trimmed = source.trimRight();
    final lines = trimmed.isEmpty ? <String>[] : trimmed.split('\n');
    var rangeStart = 0;
    var rangeEnd = lines.length;

    for (var depth = 0; depth < path.length; depth++) {
      final indent = depth * 2;
      final prefix = '${' ' * indent}${path[depth]}:';
      var found = -1;
      for (var index = rangeStart; index < rangeEnd; index++) {
        if (lines[index].startsWith(prefix)) {
          final remainder = lines[index].substring(prefix.length);
          if (remainder.isNotEmpty && !remainder.startsWith(' ')) continue;
          found = index;
          break;
        }
      }

      final isLeaf = depth == path.length - 1;
      if (found >= 0) {
        if (isLeaf) {
          lines[found] = '$prefix $value';
          return '${lines.join('\n')}\n';
        }
        rangeStart = found + 1;
        rangeEnd = _subtreeEnd(lines, rangeStart, indent);
        continue;
      }

      final inserted = <String>[];
      for (var remaining = depth; remaining < path.length; remaining++) {
        final childIndent = remaining * 2;
        final childPrefix = '${' ' * childIndent}${path[remaining]}:';
        inserted.add(
          remaining == path.length - 1
              ? '$childPrefix $value'
              : childPrefix,
        );
      }
      lines.insertAll(rangeEnd, inserted);
      return '${lines.join('\n')}\n';
    }
    return '${lines.join('\n')}\n';
  }

  static int _subtreeEnd(List<String> lines, int start, int parentIndent) {
    for (var index = start; index < lines.length; index++) {
      final line = lines[index];
      if (line.trim().isEmpty) continue;
      final indent = line.length - line.trimLeft().length;
      if (indent <= parentIndent) return index;
    }
    return lines.length;
  }
}
