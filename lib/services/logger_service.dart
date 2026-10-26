import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:logger/logger.dart';
import 'package:neostation/services/config_service.dart';
import 'package:neostation/utils/log_redaction.dart';

/// Supported log severity levels.
enum LogLevel { info, warning, error, debug }

/// Service responsible for application-wide logging with support for console
/// and file-based output.
///
/// Handles log rotation to prevent excessive disk usage and ensures that logs
/// are persisted across sessions for debugging purposes.
class LoggerService {
  static final LoggerService _instance = LoggerService._internal();
  static LoggerService get instance => _instance;

  Logger _logger;
  bool _initialized = false;
  AppendFileOutput? _fileOutput;

  LoggerService._internal()
    : _logger = Logger(
        printer: RedactingPrinter(SimplePrinter(colors: true)),
        filter: ProductionFilter(),
        output: MultiOutput([ConsoleOutput()]),
      );

  /// Initializes the logger, sets up file output, and performs log rotation.
  ///
  /// Rotates the log file if it exceeds 5MB, keeping one historical copy (`.old`).
  Future<void> init() async {
    if (_initialized) return;

    try {
      final logFilePath = await ConfigService.getLogFilePath();
      final logFile = File(logFilePath);

      final logDir = logFile.parent;
      if (!await logDir.exists()) {
        await logDir.create(recursive: true);
      }

      if (await logFile.exists()) {
        final size = await logFile.length();
        if (size > 5 * 1024 * 1024) {
          final oldLogFile = File('$logFilePath.old');
          if (await oldLogFile.exists()) {
            await oldLogFile.delete();
          }
          await logFile.rename(oldLogFile.path);
        }
      }

      _attach(File(logFilePath));

      _initialized = true;
      i('Logger initialized with file output: $logFilePath');
    } catch (e) {
      // ignore: avoid_print
      print('Error initializing file logger: $e');
    }
  }

  void _attach(File file) {
    final output = AppendFileOutput(file: file);
    _logger = Logger(
      level: Level.info,
      printer: RedactingPrinter(SimplePrinter(colors: true)),
      filter: CustomProductionFilter(),
      output: MultiOutput([ConsoleOutput(), output]),
    );
    _fileOutput = output;
  }

  /// Writes to [file] as [init] would, without reading the configuration.
  @visibleForTesting
  void attachFileForTesting(File file) => _attach(file);

  /// The file the log is written to; null without file output.
  String? get logFilePath => _fileOutput?.file.path;

  /// Moves the log file to [destination] when the user-data folder moves
  /// (`UserDataLocationService.migrateData`): copies its bytes there,
  /// replacing a file of that name, writes there from now on, then deletes
  /// the old file. Synchronous, so no line logged in between is lost or left
  /// in the old folder. Throws, keeping the current file, when the copy
  /// cannot be written whole.
  void moveLogFile(String destination) {
    final output = _fileOutput;
    if (output == null || output.file.path == destination) return;
    final source = output.file;
    final bytes = source.existsSync() ? source.readAsBytesSync() : <int>[];
    final target = File(destination);
    target.parent.createSync(recursive: true);
    target.writeAsBytesSync(bytes, flush: true);
    if (target.lengthSync() != bytes.length) {
      throw FileSystemException('Log file copy is incomplete', destination);
    }
    output.file = target;
    try {
      if (source.existsSync()) source.deleteSync();
    } catch (e) {
      w('Could not delete the previous log file ${source.path}: $e');
    }
  }

  /// Logs a message at the specified [LogLevel].
  void log(
    String message, {
    LogLevel level = LogLevel.info,
    Object? error,
    StackTrace? stackTrace,
  }) {
    switch (level) {
      case LogLevel.info:
        _logger.i(message, error: error, stackTrace: stackTrace);
        break;
      case LogLevel.warning:
        _logger.w(message, error: error, stackTrace: stackTrace);
        break;
      case LogLevel.error:
        _logger.e(message, error: error, stackTrace: stackTrace);
        break;
      case LogLevel.debug:
        _logger.d(message, error: error, stackTrace: stackTrace);
        break;
    }
  }

  /// Logs a debug-level message.
  void d(String message) => log(message, level: LogLevel.debug);

  /// Logs an info-level message.
  void i(String message) => log(message, level: LogLevel.info);

  /// Logs a warning-level message.
  void w(String message) => log(message, level: LogLevel.warning);

  /// Logs an error-level message with optional error object and stack trace.
  void e(String message, {Object? error, StackTrace? stackTrace}) =>
      log(message, level: LogLevel.error, error: error, stackTrace: stackTrace);
}

/// Strips credentials from every formatted log line before it reaches an
/// output.
///
/// This wraps the printer rather than the log call sites on purpose: the worst
/// leaks come from error objects we never format ourselves — an HTTP client
/// exception carries the full request URI, query string included — so
/// redaction has to happen after the event is rendered and before it is
/// written to the console or the log file.
class RedactingPrinter extends LogPrinter {
  RedactingPrinter(this._inner);

  final LogPrinter _inner;

  @override
  List<String> log(LogEvent event) =>
      _inner.log(event).map(redactSecrets).toList();
}

/// Writes each log event at the end of [file] with O_APPEND.
///
/// dart:io never opens with O_APPEND: it seeks to the end once, then writes
/// at its own position. The package's `FileOutput` keeps one such sink open,
/// and even a reopen per write leaves a gap between that seek and the write.
/// On iOS the MeloNX bridge appends its launch journal, stderr capture and
/// performance lines to the same app.log with O_APPEND, and Dart lines
/// overwrote them. Here each event is one unbuffered `fwrite` on a stream
/// opened by C `fopen(path, "a")` (POSIX: O_APPEND), through `dart:ffi` and
/// `DynamicLibrary.process()` as in `storage_stat_ffi.dart`: the kernel puts
/// it at the end, after any native line. Without those symbols (Windows) it
/// falls back to `writeAsStringSync` in append mode. A failed write is
/// dropped rather than thrown into the app.
class AppendFileOutput extends LogOutput {
  AppendFileOutput({required this.file});

  /// Changes only through [LoggerService.moveLogFile].
  File file;
  static final _CAppend? _c = _CAppend.load();

  /// True when writes go through C `fopen(path, "a")`.
  static bool get usesAppendMode => _c != null;

  @override
  void output(OutputEvent event) {
    if (event.lines.isEmpty) return;
    final text = '${event.lines.join('\n')}\n';
    try {
      final c = _c;
      if (c != null) {
        c.append(file.path, utf8.encode(text));
      } else {
        file.writeAsStringSync(text, mode: FileMode.append);
      }
    } catch (_) {}
  }

  /// Writes are synchronous: complete once [output] returns.
  Future<void> get flushed => Future<void>.value();
}

typedef _FopenNative = Pointer<Void> Function(Pointer<Uint8>, Pointer<Uint8>);
typedef _SetvbufNative =
    Int32 Function(Pointer<Void>, Pointer<Void>, Int32, Size);
typedef _SetvbufDart = int Function(Pointer<Void>, Pointer<Void>, int, int);
typedef _FwriteNative =
    Size Function(Pointer<Uint8>, Size, Size, Pointer<Void>);
typedef _FwriteDart = int Function(Pointer<Uint8>, int, int, Pointer<Void>);
typedef _FcloseNative = Int32 Function(Pointer<Void>);
typedef _FcloseDart = int Function(Pointer<Void>);
typedef _CallocNative = Pointer<Uint8> Function(Size, Size);
typedef _CallocDart = Pointer<Uint8> Function(int, int);
typedef _FreeNative = Void Function(Pointer<Uint8>);
typedef _FreeDart = void Function(Pointer<Uint8>);

/// C stdio append: `fopen(path, "a")`, unbuffered, one `fwrite`, `fclose`.
class _CAppend {
  _CAppend._(
    this._fopen,
    this._setvbuf,
    this._fwrite,
    this._fclose,
    this._calloc,
    this._free,
  );

  final Pointer<Void> Function(Pointer<Uint8>, Pointer<Uint8>) _fopen;
  final _SetvbufDart _setvbuf;
  final _FwriteDart _fwrite;
  final _FcloseDart _fclose;
  final _CallocDart _calloc;
  final _FreeDart _free;

  /// `_IONBF` in both Darwin's and glibc's stdio.h.
  static const int _unbuffered = 2;

  static _CAppend? load() {
    if (Platform.isWindows) return null;
    try {
      final c = DynamicLibrary.process();
      for (final name in [
        'fopen',
        'setvbuf',
        'fwrite',
        'fclose',
        'calloc',
        'free',
      ]) {
        if (!c.providesSymbol(name)) return null;
      }
      return _CAppend._(
        c.lookupFunction<
          _FopenNative,
          Pointer<Void> Function(Pointer<Uint8>, Pointer<Uint8>)
        >('fopen'),
        c.lookupFunction<_SetvbufNative, _SetvbufDart>('setvbuf'),
        c.lookupFunction<_FwriteNative, _FwriteDart>('fwrite'),
        c.lookupFunction<_FcloseNative, _FcloseDart>('fclose'),
        c.lookupFunction<_CallocNative, _CallocDart>('calloc'),
        c.lookupFunction<_FreeNative, _FreeDart>('free'),
      );
    } catch (_) {
      return null;
    }
  }

  /// Appends [bytes] to [path]; false if it could not be opened or written.
  bool append(String path, List<int> bytes) {
    final name = utf8.encode(path);
    final buffer = _calloc(name.length + bytes.length + 3, 1);
    if (buffer.address == 0) return false;
    try {
      final view = buffer.asTypedList(name.length + bytes.length + 3);
      view.setRange(0, name.length, name); // NUL-terminated by calloc
      view[name.length + 1] = 0x61; // "a", NUL-terminated
      final data = buffer + name.length + 3;
      view.setRange(name.length + 3, name.length + 3 + bytes.length, bytes);
      final stream = _fopen(buffer, buffer + name.length + 1);
      if (stream.address == 0) return false;
      _setvbuf(stream, nullptr, _unbuffered, 0);
      final written = bytes.isEmpty
          ? 0
          : _fwrite(data, 1, bytes.length, stream);
      return _fclose(stream) == 0 && written == bytes.length;
    } finally {
      _free(buffer);
    }
  }
}

/// Custom log filter that permits INFO level logs even in production/release environments.
class CustomProductionFilter extends LogFilter {
  @override
  bool shouldLog(LogEvent event) {
    return event.level.index >= level!.index;
  }
}
