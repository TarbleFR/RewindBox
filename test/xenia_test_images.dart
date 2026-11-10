import 'dart:io';
import 'dart:typed_data';

/// Builds small synthetic Xbox 360 disc images for the XeniOS tests: a GDFX
/// volume descriptor at sector 32 of [partitionOffset], a root directory
/// holding `default.xex`, and an XEX2 header whose execution info carries
/// [titleId]/[mediaId]. Files are written sparsely, so a partition at
/// 0x0FD90000 costs a few KiB on disk. No game content of any kind.
Future<File> writeXboxImage(
  String filePath, {
  int partitionOffset = 0,
  int titleId = 0x4D5307E6,
  int mediaId = 0x11223344,
  int discNumber = 1,
  int discCount = 1,
  bool truncateExecutable = false,
  List<String> extraRootFiles = const <String>[],
  int padding = 0,
}) async {
  const sector = 2048;
  final rootSector = 33;
  final xexSector = 40;
  const xexHeaderSize = 0x100;

  final descriptor = Uint8List(28);
  descriptor.setRange(0, 20, 'MICROSOFT*XBOX*MEDIA'.codeUnits);
  final descriptorView = ByteData.sublistView(descriptor);

  // Root directory: entries chained through their right node, the last one
  // being default.xex. Ordinals are offsets / 4.
  final names = <String>[...extraRootFiles, 'default.xex'];
  final directory = BytesBuilder();
  var offset = 0;
  final entries = <Uint8List>[];
  for (var index = 0; index < names.length; index++) {
    final name = names[index];
    final size = (14 + name.length + 3) & ~3;
    final entry = Uint8List(size);
    final view = ByteData.sublistView(entry);
    final next = index == names.length - 1 ? 0 : (offset + size) ~/ 4;
    view.setUint16(0, 0, Endian.little);
    view.setUint16(2, next, Endian.little);
    final isXex = name == 'default.xex';
    view.setUint32(4, isXex ? xexSector : 60 + index, Endian.little);
    view.setUint32(8, isXex ? xexHeaderSize : 16, Endian.little);
    entry[12] = 0;
    entry[13] = name.length;
    entry.setRange(14, 14 + name.length, name.codeUnits);
    entries.add(entry);
    offset += size;
  }
  for (final entry in entries) {
    directory.add(entry);
  }
  final root = directory.toBytes();
  descriptorView.setUint32(20, rootSector, Endian.little);
  descriptorView.setUint32(24, root.length, Endian.little);

  final xex = Uint8List(xexHeaderSize);
  final xexView = ByteData.sublistView(xex);
  xexView.setUint32(0, 0x58455832); // 'XEX2'
  xexView.setUint32(8, xexHeaderSize);
  xexView.setUint32(0x14, 1);
  xexView.setUint32(0x18, 0x00040006);
  xexView.setUint32(0x1C, 0x30);
  xexView.setUint32(0x30, mediaId);
  xexView.setUint32(0x3C, titleId);
  xex[0x42] = discNumber;
  xex[0x43] = discCount;

  final file = File(filePath);
  final handle = await file.open(mode: FileMode.write);
  try {
    await handle.setPosition(partitionOffset + 32 * sector);
    await handle.writeFrom(descriptor);
    await handle.setPosition(partitionOffset + rootSector * sector);
    await handle.writeFrom(root);
    await handle.setPosition(partitionOffset + xexSector * sector);
    await handle.writeFrom(
      truncateExecutable ? xex.sublist(0, 0x20) : xex,
    );
    if (padding > 0) {
      await handle.setPosition(await handle.length() + padding - 1);
      await handle.writeByte(0);
    }
  } finally {
    await handle.close();
  }
  return file;
}
