/// Line-preserving INI editor for files an engine and RewindBox share.
///
/// Only the lines an operation names change: comments, ordering, unknown
/// sections and keys written by the engine stay byte-identical.
class IniDocument {
  IniDocument.parse(String text)
    : _lines = text.isEmpty ? <String>[] : text.split(RegExp(r'\r?\n')) {
    if (_lines.isNotEmpty && _lines.last.isEmpty) _lines.removeLast();
  }

  final List<String> _lines;

  static String? _sectionName(String line) {
    final trimmed = line.trim();
    if (trimmed.length < 2 || !trimmed.startsWith('[') || !trimmed.endsWith(']')) {
      return null;
    }
    return trimmed.substring(1, trimmed.length - 1).trim();
  }

  /// [start, end) line range of the body of [section], or null.
  (int, int)? _range(String section) {
    for (var i = 0; i < _lines.length; i++) {
      if (_sectionName(_lines[i]) == section) {
        var end = i + 1;
        while (end < _lines.length && _sectionName(_lines[end]) == null) {
          end++;
        }
        return (i + 1, end);
      }
    }
    return null;
  }

  bool hasSection(String section) => _range(section) != null;

  /// Body lines of [section], trimmed, without blanks.
  List<String> lines(String section) {
    final range = _range(section);
    if (range == null) return const [];
    return [
      for (var i = range.$1; i < range.$2; i++)
        if (_lines[i].trim().isNotEmpty) _lines[i].trim(),
    ];
  }

  /// Values of `key = value` lines of [section] (keys compared ignoring case).
  List<String> values(String section, String key) => [
    for (final line in lines(section))
      if (_keyOf(line) == key.toLowerCase()) _valueOf(line),
  ];

  static String? _keyOf(String line) {
    final index = line.indexOf('=');
    return index <= 0 ? null : line.substring(0, index).trim().toLowerCase();
  }

  static String _valueOf(String line) => line.substring(line.indexOf('=') + 1).trim();

  /// Adds [line] at the end of [section], creating the section when absent.
  /// Returns false when an identical line already exists.
  bool addLine(String section, String line) {
    if (lines(section).contains(line.trim())) return false;
    final range = _range(section);
    if (range == null) {
      if (_lines.isNotEmpty && _lines.last.trim().isNotEmpty) _lines.add('');
      _lines
        ..add('[$section]')
        ..add(line);
      return true;
    }
    var insert = range.$2;
    while (insert > range.$1 && _lines[insert - 1].trim().isEmpty) {
      insert--;
    }
    _lines.insert(insert, line);
    return true;
  }

  /// Removes body lines of [section] equal to [line] after trimming.
  int removeLine(String section, String line) =>
      removeWhere(section, (candidate) => candidate == line.trim());

  int removeWhere(String section, bool Function(String trimmed) test) {
    final range = _range(section);
    if (range == null) return 0;
    var removed = 0;
    for (var i = range.$2 - 1; i >= range.$1; i--) {
      final trimmed = _lines[i].trim();
      if (trimmed.isNotEmpty && test(trimmed)) {
        _lines.removeAt(i);
        removed++;
      }
    }
    return removed;
  }

  /// Sets a single `key = value` line, returning the previous value.
  String? setValue(String section, String key, String value) {
    final previous = values(section, key);
    removeWhere(section, (line) => _keyOf(line) == key.toLowerCase());
    addLine(section, '$key = $value');
    return previous.isEmpty ? null : previous.first;
  }

  /// Removes `key = …` lines of [section].
  void removeKey(String section, String key) =>
      removeWhere(section, (line) => _keyOf(line) == key.toLowerCase());

  /// Drops sections left without any body line.
  void dropEmptySections(Iterable<String> sections) {
    for (final section in sections) {
      final range = _range(section);
      if (range == null) continue;
      final empty = [
        for (var i = range.$1; i < range.$2; i++) _lines[i],
      ].every((line) => line.trim().isEmpty);
      if (empty) _lines.removeRange(range.$1 - 1, range.$2);
    }
  }

  bool get isBlank => _lines.every((line) => line.trim().isEmpty);

  @override
  String toString() => _lines.isEmpty ? '' : '${_lines.join('\n')}\n';
}
