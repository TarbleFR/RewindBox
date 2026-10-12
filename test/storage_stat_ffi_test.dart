import 'dart:ffi';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/storage/storage_stat_ffi.dart';
import 'package:path/path.dart' as p;

/// § 3.3 of docs/storage-audit-cleanup.md and test E (ffi part): on Linux
/// x86_64 (CI) the real `lstat`/`statvfs` of glibc are called through
/// `dart:ffi`; sizes equal `FileStat`, the layout agrees with GNU `stat`,
/// links are detected without being followed, and a missing symbol, an
/// unsupported ABI or a failed self-test fall back to logical sizes.
final bool _linuxX64 = Abi.current() == Abi.linuxX64;

Pointer<Void>? _process(String symbol) {
  final library = DynamicLibrary.process();
  return library.providesSymbol(symbol) ? library.lookup<Void>(symbol) : null;
}

/// A fake `lstat`: a plausible directory whose size is wrong.
int _lyingLstat(Pointer<Uint8> path, Pointer<Uint8> buffer) {
  final view = ByteData.sublistView(buffer.asTypedList(144));
  view.setUint64(16, 1, Endian.host); // st_nlink
  view.setUint32(24, 0x41ED, Endian.host); // st_mode: directory 0755
  view.setInt64(48, 123456789, Endian.host); // st_size: wrong
  view.setInt64(64, 8, Endian.host); // st_blocks
  return 0;
}

void main() {
  late Directory temp;

  setUp(() async {
    StorageStatFfi.resetSession();
    temp = await Directory.systemTemp.createTemp('storage_stat_ffi_');
  });

  tearDown(() async {
    StorageStatFfi.resetSession();
    if (await temp.exists()) await temp.delete(recursive: true);
  });

  Future<File> write(String name, int length) async {
    final file = File(p.join(temp.path, name));
    await file.parent.create(recursive: true);
    await file.writeAsBytes(List<int>.generate(length, (index) => index % 251));
    return file;
  }

  Future<List<String>> gnuStat(List<String> arguments) async {
    final result = await Process.run('stat', arguments);
    expect(result.exitCode, 0, reason: '${result.stderr}');
    return (result.stdout as String).trim().split(RegExp(r'\s+'));
  }

  group('real FFI (Linux x86_64 glibc)', () {
    test('loads, passes its self-test and reports the glibc layout', () async {
      await write('probe.bin', 10);
      final stat = StorageStatFfi.tryLoad(probePath: temp.path);
      expect(stat, isNotNull);
      expect(stat!.available, isTrue);
      expect(stat.layout.name, 'linux-x64');
      expect(stat.layout.statSize, 144);
      expect(stat.layout.sizeOffset, 48);
      expect(stat.layout.blocksOffset, 64);
      expect(stat.layout.statvfsSize, 112);
      // The verdict is kept for the session.
      expect(
        identical(StorageStatFfi.tryLoad(probePath: temp.path), stat),
        isTrue,
      );
    });

    test('sizes equal FileStat and every field agrees with GNU stat', () async {
      final stat = StorageStatFfi.tryLoad(probePath: temp.path)!;
      for (final length in [0, 1, 4095, 4096, 65537, 1 << 20]) {
        final file = await write('file-$length.bin', length);
        final info = stat.lstat(file.path)!;
        expect(info.size, length);
        expect(info.size, (await file.stat()).size);
        expect(info.isRegularFile, isTrue);
        expect(info.isLink, isFalse);
        final gnu = await gnuStat(['--format=%i %h %b %B %s %f %d', file.path]);
        expect(info.ino, int.parse(gnu[0]), reason: 'st_ino');
        expect(info.nlink, int.parse(gnu[1]), reason: 'st_nlink');
        expect(
          info.allocatedBytes,
          int.parse(gnu[2]) * int.parse(gnu[3]),
          reason: 'st_blocks',
        );
        expect(info.size, int.parse(gnu[4]), reason: 'st_size');
        expect(info.mode, int.parse(gnu[5], radix: 16), reason: 'st_mode');
        expect(info.dev, int.parse(gnu[6]), reason: 'st_dev');
      }
      final directory = stat.lstat(temp.path)!;
      expect(directory.isDirectory, isTrue);
      expect(directory.size, (await temp.stat()).size);
    });

    test(
      'a link is described, never followed; hard links share an inode',
      () async {
        final stat = StorageStatFfi.tryLoad(probePath: temp.path)!;
        final target = await write('target.bin', 300000);
        final link = await Link(p.join(temp.path, 'link')).create(target.path);
        final info = stat.lstat(link.path)!;
        expect(info.isLink, isTrue);
        expect(info.size, target.path.length);
        expect(info.allocatedBytes, lessThan(300000));
        // FileStat follows the link: the two disagree, as they must.
        expect((await File(link.path).stat()).size, 300000);
        final dangling = await Link(
          p.join(temp.path, 'dangling'),
        ).create(p.join(temp.path, 'missing'));
        expect(stat.lstat(dangling.path)!.isLink, isTrue);

        final hard = p.join(temp.path, 'hard.bin');
        final ln = await Process.run('ln', [target.path, hard]);
        expect(ln.exitCode, 0);
        final first = stat.lstat(target.path)!;
        final second = stat.lstat(hard)!;
        expect(first.nlink, 2);
        expect(second.ino, first.ino);
        expect(second.dev, first.dev);
      },
    );

    test(
      'statvfs agrees with GNU stat -f and passes the sanity bounds',
      () async {
        final stat = StorageStatFfi.tryLoad(probePath: temp.path)!;
        final volume = stat.statvfs(temp.path)!;
        final gnu = await gnuStat(['-f', '--format=%S %b %a', temp.path]);
        final fragment = int.parse(gnu[0]);
        expect(volume.fragmentSize, fragment);
        expect(volume.totalBytes, int.parse(gnu[1]) * fragment);
        // Free space moves with other processes: same order of magnitude.
        final free = int.parse(gnu[2]) * fragment;
        expect((volume.freeBytes - free).abs(), lessThan(256 * 1024 * 1024));
        expect(volume.freeBytes, lessThanOrEqualTo(volume.totalBytes));
        expect(volume.fragmentSize, inInclusiveRange(512, 1024 * 1024));
      },
    );

    test('errors are null, never exceptions', () {
      final stat = StorageStatFfi.tryLoad(probePath: temp.path)!;
      expect(stat.lstat(p.join(temp.path, 'missing')), isNull);
      expect(stat.statvfs(p.join(temp.path, 'missing', 'deeper')), isNull);
      expect(stat.lstat('bad\u0000path'), isNull);
    });

    test('a missing symbol falls back to logical sizes', () {
      for (final missing in ['lstat', 'statvfs', 'calloc', 'free']) {
        final stat = StorageStatFfi.tryLoad(
          probePath: temp.path,
          lookup: (symbol) => symbol == missing ? null : _process(symbol),
        );
        expect(stat, isNull, reason: missing);
      }
      // Injected failures never poison the session verdict.
      expect(StorageStatFfi.tryLoad(probePath: temp.path), isNotNull);
    });

    test('a failed self-test falls back to logical sizes', () async {
      await write('probe.bin', 1234);
      // Darwin offsets read on glibc structures: the self-test sees the
      // mismatch with FileStat.
      expect(
        StorageStatFfi.tryLoad(probePath: temp.path, abi: Abi.iosArm64),
        isNull,
      );
      // An lstat that lies about the size.
      final lying =
          Pointer.fromFunction<Int32 Function(Pointer<Uint8>, Pointer<Uint8>)>(
            _lyingLstat,
            -1,
          );
      expect(
        StorageStatFfi.tryLoad(
          probePath: temp.path,
          lookup: (symbol) =>
              symbol == 'lstat' ? lying.cast<Void>() : _process(symbol),
        ),
        isNull,
      );
      // The probe must be a readable directory.
      expect(
        StorageStatFfi.tryLoad(
          probePath: p.join(temp.path, 'probe.bin'),
          abi: Abi.linuxX64,
        ),
        isNull,
      );
      expect(
        StorageStatFfi.tryLoad(
          probePath: p.join(temp.path, 'missing'),
          abi: Abi.linuxX64,
        ),
        isNull,
      );
    });
  }, skip: _linuxX64 ? false : 'glibc x86_64 only (the CI lane)');

  test('an ABI without a verified layout falls back to logical sizes', () {
    for (final abi in [
      Abi.windowsX64,
      Abi.androidArm64,
      Abi.linuxArm64,
      Abi.iosX64,
    ]) {
      expect(
        StorageStatFfi.tryLoad(probePath: temp.path, abi: abi),
        isNull,
        reason: '$abi',
      );
      expect(StorageStatLayout.forAbi(abi), isNull, reason: '$abi');
    }
    expect(
      StorageStatLayout.forAbi(Abi.iosArm64),
      same(StorageStatLayout.darwinArm64),
    );
    expect(
      StorageStatLayout.forAbi(Abi.macosArm64),
      same(StorageStatLayout.darwinArm64),
    );
    expect(
      StorageStatLayout.forAbi(Abi.linuxX64),
      same(StorageStatLayout.linuxX64),
    );
  });

  test('the Darwin arm64 layout reads a struct stat of 144 bytes', () {
    final bytes = ByteData(144)
      ..setInt32(0, 16777220, Endian.host) // st_dev
      ..setUint16(4, 0x81A4, Endian.host) // st_mode: regular 0644
      ..setUint16(6, 1, Endian.host) // st_nlink
      ..setUint64(8, 987654321, Endian.host) // st_ino
      ..setInt64(96, 5000, Endian.host) // st_size
      ..setInt64(104, 16, Endian.host); // st_blocks
    final info = StorageStatLayout.darwinArm64.readStat(bytes);
    expect(info.dev, 16777220);
    expect(info.isRegularFile, isTrue);
    expect(info.nlink, 1);
    expect(info.ino, 987654321);
    expect(info.size, 5000);
    expect(info.allocatedBytes, 8192);
    final volume = ByteData(64)
      ..setUint64(0, 4096, Endian.host) // f_bsize
      ..setUint64(8, 4096, Endian.host) // f_frsize
      ..setUint32(16, 1000, Endian.host) // f_blocks
      ..setUint32(20, 600, Endian.host) // f_bfree
      ..setUint32(24, 500, Endian.host); // f_bavail
    final values = StorageStatLayout.darwinArm64.readStatvfs(volume);
    expect(values.frsize, 4096);
    expect(values.blocks, 1000);
    expect(values.available, 500);
  });

  test(
    'the logical fallback uses FileStat only and never follows links',
    () async {
      const stat = StorageStatLogical();
      expect(stat.available, isFalse);
      final file = await write('a.bin', 777);
      final info = stat.lstat(file.path)!;
      expect(info.size, 777);
      expect(info.isRegularFile, isTrue);
      expect(info.blocks, 0);
      expect(stat.lstat(temp.path)!.isDirectory, isTrue);
      final link = await Link(p.join(temp.path, 'l')).create(file.path);
      final linkInfo = stat.lstat(link.path)!;
      expect(linkInfo.isLink, isTrue);
      expect(linkInfo.size, 0);
      expect(stat.lstat(p.join(temp.path, 'missing')), isNull);
      expect(stat.statvfs(temp.path), isNull);
    },
  );
}
