// The size of a box scan is read on the UI thread as list rows appear: only
// the first 64 KB are read, unless the size is further in (a JPEG with a large
// EXIF or ICC block), then up to 1 MB as before.
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/game_box/game_box_media.dart';

/// A JPEG made of SOI, an APP1 block of [app1] bytes (split in segments of at
/// most 65533 bytes), a baseline frame header of [width] × [height], EOI.
Uint8List _jpeg({required int app1, required int width, required int height}) {
  final out = BytesBuilder()..add([0xFF, 0xD8]);
  var left = app1;
  while (left > 0) {
    final chunk = left > 65533 ? 65533 : left;
    final length = chunk + 2;
    out
      ..add([0xFF, 0xE1, length >> 8, length & 0xFF])
      ..add(Uint8List(chunk));
    left -= chunk;
  }
  out
    ..add([0xFF, 0xC0, 0x00, 0x11, 0x08])
    ..add([height >> 8, height & 0xFF, width >> 8, width & 0xFF])
    ..add([0x03, 0x01, 0x22, 0x00, 0x02, 0x11, 0x01, 0x03, 0x11, 0x01])
    ..add([0xFF, 0xD9]);
  return out.toBytes();
}

void main() {
  late Directory dir;
  setUp(() => dir = Directory.systemTemp.createTempSync('box_size_header'));
  tearDown(() => dir.deleteSync(recursive: true));

  String write(String name, List<int> bytes) {
    final file = File('${dir.path}/$name')..writeAsBytesSync(bytes);
    GameBoxImageSize.evict(file.path);
    return file.path;
  }

  test('a JPEG whose size is past the first 64 KB is still measured', () {
    final path = write('exif.jpg', _jpeg(app1: 200 * 1024, width: 928, height: 1080));
    expect(File(path).lengthSync(), greaterThan(GameBoxImageSize.headerStart));
    expect(GameBoxImageSize.of(path), const Size(928, 1080));
  });

  test('a JPEG with a small header and a large file', () {
    final bytes = BytesBuilder()
      ..add(_jpeg(app1: 1000, width: 1166, height: 1888))
      ..add(Uint8List(3 * 1024 * 1024));
    expect(GameBoxImageSize.of(write('big.jpg', bytes.toBytes())), const Size(1166, 1888));
  });

  test('a PNG is measured from its first bytes', () {
    final png = Uint8List(2 * 1024 * 1024)
      ..setAll(0, [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52])
      ..setAll(16, [0, 0, 0x04, 0x8E, 0, 0, 0x07, 0x60]);
    expect(GameBoxImageSize.of(write('front.png', png)), const Size(1166, 1888));
  });

  test('a JPEG with no frame header in its first megabyte has no size', () {
    final path = write('none.jpg', _jpeg(app1: 1100 * 1024, width: 10, height: 10));
    expect(GameBoxImageSize.of(path), isNull);
  });
}
