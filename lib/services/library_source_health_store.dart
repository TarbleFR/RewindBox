import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'library_aidoku_native_service.dart';

/// Latest on-device health check of each Library source
/// (`Application Support/Library/source-health.json`).
///
/// One report is kept per Aidoku source id (the add-on id is not used, so
/// deactivating and reactivating a source keeps its last result). The file
/// is written atomically (temporary file + rename). A file that cannot be
/// decoded is kept as `source-health.json.corrupt`; a file that cannot be
/// read (I/O error) is never overwritten: [record] then throws.
class LibrarySourceHealthStore extends ChangeNotifier {
  LibrarySourceHealthStore({Future<Directory> Function()? directory})
    : _directory = directory ?? _defaultDirectory;

  static const String fileName = 'source-health.json';
  static const String schema = 'neostation.library.source-health.v1';

  static LibrarySourceHealthStore? _instance;

  static LibrarySourceHealthStore get instance =>
      _instance ??= LibrarySourceHealthStore();
  static set instance(LibrarySourceHealthStore value) => _instance = value;

  static Future<Directory> _defaultDirectory() async {
    final support = await getApplicationSupportDirectory();
    return Directory(p.join(support.path, 'Library'));
  }

  final Future<Directory> Function() _directory;
  final Map<String, LibrarySourceHealthReport> _reports =
      <String, LibrarySourceHealthReport>{};
  Future<void>? _loading;
  bool _loaded = false;
  bool _readFailed = false;
  Future<void> _tail = Future<void>.value();

  bool get isLoaded => _loaded;

  /// Every stored report, by Aidoku source id.
  Map<String, LibrarySourceHealthReport> get reports =>
      Map<String, LibrarySourceHealthReport>.unmodifiable(_reports);

  /// Latest report of [sourceId], or null when it was never checked on this
  /// device.
  LibrarySourceHealthReport? latest(String sourceId) => _reports[sourceId];

  /// Reads the file once; later calls share the first read.
  Future<void> load() => _loading ??= _load();

  /// Stores [report] as the latest result of its source.
  Future<void> record(LibrarySourceHealthReport report) {
    return _serialized(() async {
      await load();
      if (_readFailed) {
        // Retry the read: an unreadable file must not be replaced.
        await _read();
        if (_readFailed) {
          throw const FileSystemException('source-health.json is unreadable');
        }
      }
      _reports[report.sourceId] = report;
      await _write();
      notifyListeners();
    });
  }

  /// Forgets the stored result of [sourceId].
  Future<void> remove(String sourceId) {
    return _serialized(() async {
      await load();
      if (_reports.remove(sourceId) == null || _readFailed) return;
      await _write();
      notifyListeners();
    });
  }

  Future<void> _load() async {
    await _read();
    _loaded = true;
    notifyListeners();
  }

  Future<void> _read() async {
    final File file;
    try {
      file = File(p.join((await _directory()).path, fileName));
      if (!await file.exists()) {
        _readFailed = false;
        return;
      }
    } on Object {
      _readFailed = true;
      return;
    }
    List<int> bytes;
    try {
      bytes = await file.readAsBytes();
    } on FileSystemException {
      _readFailed = true;
      return;
    }
    _readFailed = false;
    Object? decoded;
    try {
      decoded = jsonDecode(utf8.decode(bytes));
    } on FormatException {
      decoded = null;
    }
    final stored = decoded is Map ? decoded['reports'] : null;
    if (stored is! Map) {
      try {
        final corrupt = File('${file.path}.corrupt');
        if (!await corrupt.exists()) await file.copy(corrupt.path);
      } on FileSystemException {
        // Best effort: the next write replaces the unreadable content.
      }
      _reports.clear();
      return;
    }
    _reports.clear();
    for (final entry in stored.entries) {
      // One damaged report (e.g. a field of the wrong type) is dropped; it
      // must not make the whole store unreadable for the session.
      final LibrarySourceHealthReport? report;
      try {
        report = LibrarySourceHealthReport.fromJson(entry.value);
      } on TypeError {
        continue;
      }
      if (report != null) _reports[report.sourceId] = report;
    }
  }

  Future<void> _write() async {
    final directory = await _directory();
    await directory.create(recursive: true);
    final file = File(p.join(directory.path, fileName));
    final temporary = File('${file.path}.tmp');
    final body = jsonEncode(<String, Object?>{
      'schema': schema,
      'reports': <String, Object?>{
        for (final entry in _reports.entries) entry.key: entry.value.toJson(),
      },
    });
    await temporary.writeAsString(body, flush: true);
    await temporary.rename(file.path);
  }

  Future<T> _serialized<T>(Future<T> Function() action) {
    final result = _tail.then((_) => action());
    _tail = result.then<void>((_) {}, onError: (Object _) {});
    return result;
  }
}
