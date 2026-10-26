import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:logger/logger.dart';
import 'package:neostation/services/logger_service.dart';

OutputEvent _event(List<String> lines) =>
    OutputEvent(LogEvent(Level.info, lines.join('\n')), lines);

// Stands in for the iOS bridge: an independent append to the same app.log.
void _nativeAppend(File file, String line) =>
    file.writeAsStringSync('$line\n', mode: FileMode.append);

void main() {
  late Directory directory;
  late File file;

  setUp(() {
    directory = Directory.systemTemp.createTempSync('logger-append-');
    file = File('${directory.path}/app.log');
  });
  tearDown(() => directory.deleteSync(recursive: true));

  test(
    'control: a sink opened once overwrites lines appended by others',
    () async {
      final sink = file.openWrite(mode: FileMode.writeOnlyAppend);
      sink.writeln('dart 1');
      await sink.flush();
      _nativeAppend(file, '[MeloNX:native] launch passed');
      sink.writeln('dart 2');
      await sink.close();
      expect(file.readAsStringSync(), isNot(contains('[MeloNX:native]')));
    },
  );

  test('native lines appended between Dart lines are kept, in order', () async {
    _nativeAppend(file, 'previous session');
    final output = AppendFileOutput(file: file);
    output.output(_event(['dart 1']));
    await output.flushed;
    _nativeAppend(file, '[MeloNX:native] launch passed');
    _nativeAppend(file, '[MeloNX:perf] t=1 fps=59.5/16.8/40');
    output.output(_event(['dart 2', 'dart 2 continued']));
    await output.destroy();
    expect(
      file.readAsStringSync(),
      'previous session\ndart 1\n[MeloNX:native] launch passed\n'
      '[MeloNX:perf] t=1 fps=59.5/16.8/40\ndart 2\ndart 2 continued\n',
    );
  });

  test('a burst is written completely and in order', () async {
    final output = AppendFileOutput(file: file);
    for (var i = 0; i < 500; i++) {
      output.output(_event(['line $i']));
    }
    await output.flushed;
    expect(file.readAsLinesSync(), [for (var i = 0; i < 500; i++) 'line $i']);
  });

  test('writes go through C fopen(path, "a") on this platform', () {
    expect(AppendFileOutput.usesAppendMode, isTrue);
  });

  test('a concurrent O_APPEND writer loses no line and splits none', () async {
    // The shell's `>>` opens with O_APPEND, as the iOS bridge does.
    final native = await Process.start('sh', [
      '-c',
      'i=0; while [ \$i -lt 20000 ]; do echo "native \$i" >> "\$1"; i=\$((i+1)); done',
      'sh',
      file.path,
    ]);
    final output = AppendFileOutput(file: file);
    for (var i = 0; i < 5000; i++) {
      output.output(_event(['dart $i']));
    }
    expect(await native.exitCode, 0);
    final lines = file.readAsLinesSync();
    expect(
      lines.where((l) => !RegExp(r'^(dart|native) \d+$').hasMatch(l)),
      isEmpty,
    );
    expect(lines.where((l) => l.startsWith('dart ')).toList(), [
      for (var i = 0; i < 5000; i++) 'dart $i',
    ]);
    expect(lines.where((l) => l.startsWith('native ')).toList(), [
      for (var i = 0; i < 20000; i++) 'native $i',
    ]);
    // The writers really overlapped.
    final first = lines.indexOf('dart 0'), last = lines.indexOf('dart 4999');
    expect(
      lines.sublist(first, last).any((l) => l.startsWith('native ')),
      isTrue,
    );
  });

  test('an event without lines writes nothing', () {
    AppendFileOutput(file: file).output(_event([]));
    expect(file.existsSync(), isFalse);
  });

  test('an unwritable file never throws into the app', () async {
    final output = AppendFileOutput(
      file: File('${directory.path}/missing/app.log'),
    );
    output.output(_event(['lost']));
    await output.destroy();
    output.output(_event(['still lost']));
    await output.flushed;
    expect(File('${directory.path}/missing/app.log').existsSync(), isFalse);
  });
}
