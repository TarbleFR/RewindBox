import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/screenscraper/rom_hasher.dart';
import 'package:neostation/utils/optimized_md5_utils.dart';
import 'package:shared_preferences/shared_preferences.dart';

class GuardedFile implements File {
  GuardedFile(this.real);
  final File real;
  int chunks = 0;
  int largestChunk = 0;
  @override String get path => real.path;
  @override Future<bool> exists() => real.exists();
  @override Future<RandomAccessFile> open({FileMode mode = FileMode.read}) =>
      real.open(mode: mode);
  @override Stream<List<int>> openRead([int? start, int? end]) =>
      real.openRead(start, end).map((bytes) {
        chunks++;
        if (bytes.length > largestChunk) largestChunk = bytes.length;
        return bytes;
      });
  @override Future<Uint8List> readAsBytes() =>
      Future.error(StateError('WHOLE_FILE_READ_BLOCKED'));
  @override Uint8List readAsBytesSync() =>
      throw StateError('WHOLE_FILE_READ_BLOCKED');
  @override dynamic noSuchMethod(Invocation invocation) =>
      throw UnsupportedError(invocation.memberName.toString());
}

Future<void> waitForLog(File log, String marker) async {
  final deadline = DateTime.now().add(const Duration(seconds: 5));
  while (DateTime.now().isBefore(deadline)) {
    if (await log.exists() && (await log.readAsString()).contains(marker)) return;
    await Future<void>.delayed(const Duration(milliseconds: 20));
  }
  fail('app.log did not persist $marker');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory root;
  setUpAll(() async {
    root = await Directory.systemTemp.createTemp('neostation-md5-');
    SharedPreferences.setMockInitialValues({'custom_user_data_path': root.path});
    await LoggerService.instance.init();
  });
  tearDownAll(() async { await root.delete(recursive: true); });

  test('scraping MD5 never requests whole-file bytes', () async {
    final bytes = List<int>.generate(1024 * 1024 + 17, (i) => i % 251);
    final file = await File('${root.path}/guard.iso').writeAsBytes(bytes);
    final guard = GuardedFile(file);
    final result = await IOOverrides.runZoned(
      () => OptimizedMd5Utils.calculateFileMd5(file.path),
      createFile: (_) => guard,
    );
    expect(result, crypto.md5.convert(bytes).toString());
    expect(guard.chunks, greaterThan(1));
    expect(guard.largestChunk, lessThanOrEqualTo(1024 * 1024));
  });

  test('full digests match empty and chunk boundary reference inputs', () async {
    for (final size in [0, 1, 63, 64, 65, 65535, 65536, 65537, 1048579]) {
      final bytes = List<int>.generate(size, (i) => (i * 31 + 7) % 256);
      final file = await File('${root.path}/boundary-$size.iso').writeAsBytes(bytes);
      expect(await OptimizedMd5Utils.calculateFileMd5(file.path),
          crypto.md5.convert(bytes).toString(), reason: 'size=$size');
    }
  });

  test('isolate success and failure reach the persistent app log', () async {
    final file = await File('${root.path}/diagnostic.iso').writeAsString('abc');
    expect(await ScreenscraperRomHasher.calculateMd5InIsolate(file.path),
        '900150983cd24fb0d6963f7d28e17f72');
    final log = File('${root.path}/app.log');
    await waitForLog(log, '[ScrapingMD5] completed file=diagnostic.iso bytes=3');
    expect(await log.readAsString(),
        contains('[ScrapingMD5] start file=diagnostic.iso bytes=3 mode=stream'));
    await expectLater(
      ScreenscraperRomHasher.calculateMd5InIsolate('${root.path}/missing.iso'),
      throwsA(isA<FileSystemException>()),
    );
    await waitForLog(log, '[ScrapingMD5] failed file=missing.iso');
  });

  test('concurrent scraping workers keep exact independent digests', () async {
    final files = <File>[];
    final expected = <String>[];
    for (var i = 0; i < 6; i++) {
      final bytes = List<int>.generate(1024 * 1024 + i, (j) => (j + i) % 256);
      files.add(await File('${root.path}/worker-$i.iso').writeAsBytes(bytes));
      expected.add(crypto.md5.convert(bytes).toString());
    }
    expect(await Future.wait(files.map((f) =>
        ScreenscraperRomHasher.calculateMd5InIsolate(f.path))), expected);
  });

  test('reported 3.36 GB ISO size hashes completely with bounded memory', () async {
    const size = 3363110912;
    final file = File('${root.path}/reported-size.iso');
    final handle = await file.open(mode: FileMode.write);
    try {
      await handle.truncate(size);
      final markers = <int, String>{
        0: 'NeoStation streaming MD5 regression',
        65535: 'boundary-before',
        65536: 'boundary-after',
        2147483665: 'above-2GiB',
        size - 128: 'tail-marker',
        size - 1: '!',
      };
      for (final entry in markers.entries) {
        await handle.setPosition(entry.key);
        await handle.writeFrom(utf8.encode(entry.value));
      }
    } finally {
      await handle.close();
    }
    final baselineRss = ProcessInfo.currentRss;
    var peakRss = baselineRss;
    final sampler = Timer.periodic(const Duration(milliseconds: 25), (_) {
      final rss = ProcessInfo.currentRss;
      if (rss > peakRss) peakRss = rss;
    });
    final watch = Stopwatch()..start();
    late String digest;
    try {
      digest = await ScreenscraperRomHasher.calculateMd5InIsolate(file.path);
      final rss = ProcessInfo.currentRss;
      if (rss > peakRss) peakRss = rss;
    } finally {
      sampler.cancel();
      await file.delete();
    }
    // Independently calculated by Python hashlib, including nonzero markers
    // across 64 KiB, above 2 GiB and in the final byte of the full fixture.
    expect(digest, 'f70f295bdaa27ba3e3ebc9f6fce9ddb8');
    expect(peakRss - baselineRss, lessThan(192 * 1024 * 1024));
    stdout.writeln('SCRAPING_MD5_METRICS ${jsonEncode({
      'fixtureBytes': size, 'digest': digest, 'baselineRss': baselineRss,
      'peakRss': peakRss, 'extraRss': peakRss - baselineRss,
      'elapsedMs': watch.elapsedMilliseconds,
      'physicalIPhoneTest': false,
    })}');
  }, timeout: const Timeout(Duration(minutes: 4)));
}
