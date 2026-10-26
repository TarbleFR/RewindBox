import 'dart:convert';
import 'dart:typed_data';

/// Builds small ISO 9660 images laid out like PS3 game discs for the Build
/// 554 tests: system area, primary descriptor (sector 16), terminator, a
/// root directory holding PS3_DISC.SFB and PS3_GAME, and a two-sector
/// PS3_GAME directory whose PARAM.SFO record sits in the second sector, so
/// the zero padding of the first one has to be skipped.
abstract final class Ps3DiscImageBuilder {
  static const int sector = 2048;

  static Uint8List paramSfo(Map<String, String> values) {
    final keys = values.keys.toList();
    final keyTable = BytesBuilder();
    final keyOffsets = <int>[];
    for (final key in keys) {
      keyOffsets.add(keyTable.length);
      keyTable.add([...ascii.encode(key), 0]);
    }
    while (keyTable.length % 4 != 0) {
      keyTable.addByte(0);
    }
    final dataTable = BytesBuilder();
    final dataOffsets = <int>[];
    final lengths = <int>[];
    final maxLengths = <int>[];
    for (final key in keys) {
      final bytes = [...utf8.encode(values[key]!), 0];
      final maxLength = (bytes.length + 3) & ~3;
      dataOffsets.add(dataTable.length);
      lengths.add(bytes.length);
      maxLengths.add(maxLength);
      dataTable.add(bytes);
      for (var index = bytes.length; index < maxLength; index++) {
        dataTable.addByte(0);
      }
    }
    final keyStart = 20 + 16 * keys.length;
    final dataStart = keyStart + keyTable.length;
    final out = Uint8List(dataStart + dataTable.length);
    final view = ByteData.sublistView(out);
    view.setUint32(0, 0x46535000, Endian.little);
    view.setUint32(4, 0x00000101, Endian.little);
    view.setUint32(8, keyStart, Endian.little);
    view.setUint32(12, dataStart, Endian.little);
    view.setUint32(16, keys.length, Endian.little);
    for (var index = 0; index < keys.length; index++) {
      final at = 20 + 16 * index;
      view.setUint16(at, keyOffsets[index], Endian.little);
      view.setUint16(at + 2, 0x0204, Endian.little);
      view.setUint32(at + 4, lengths[index], Endian.little);
      view.setUint32(at + 8, maxLengths[index], Endian.little);
      view.setUint32(at + 12, dataOffsets[index], Endian.little);
    }
    out.setRange(keyStart, dataStart, keyTable.takeBytes());
    out.setRange(dataStart, out.length, dataTable.takeBytes());
    return out;
  }

  /// A PS3 disc image. [paramSfoBytes] replaces the descriptor (noise for
  /// an encrypted region); [gameDirectory] null leaves PS3_GAME out.
  static Uint8List image({
    String titleId = 'BLUS30591',
    String title = 'Call of Duty®: Black Ops',
    String category = 'DG',
    Uint8List? paramSfoBytes,
    String? gameDirectory = 'PS3_GAME',
    String paramSfoName = 'PARAM.SFO;1',
    int fill = 0,
  }) {
    final sfo =
        paramSfoBytes ??
        paramSfo({'CATEGORY': category, 'TITLE': title, 'TITLE_ID': titleId});
    final sfoSectors = (sfo.length + sector - 1) ~/ sector;
    const root = 18;
    const game = 19; // two sectors: 19 and 20
    const sfoSector = 21;
    final iconSector = sfoSector + sfoSectors;
    final out = Uint8List((iconSector + 2) * sector);
    // The system area of a disc dump is not zero: give it a recognisable fill.
    for (var index = 0; index < 16 * sector; index++) {
      out[index] = (index * 31 + fill) & 0xff;
    }

    void descriptor(int index, int type) {
      final at = index * sector;
      out[at] = type;
      out.setRange(at + 1, at + 6, ascii.encode('CD001'));
      out[at + 6] = 1;
    }

    int record(
      int offset, {
      required int lba,
      required int size,
      required bool directory,
      required List<int> name,
    }) {
      final length = 33 + name.length + (name.length.isEven ? 1 : 0);
      final view = ByteData.sublistView(out);
      out[offset] = length;
      view.setUint32(offset + 2, lba, Endian.little);
      view.setUint32(offset + 6, lba, Endian.big);
      view.setUint32(offset + 10, size, Endian.little);
      view.setUint32(offset + 14, size, Endian.big);
      out[offset + 25] = directory ? 0x02 : 0x00;
      out[offset + 32] = name.length;
      out.setRange(offset + 33, offset + 33 + name.length, name);
      return offset + length;
    }

    descriptor(16, 1);
    descriptor(17, 255);
    record(
      16 * sector + 156,
      lba: root,
      size: sector,
      directory: true,
      name: [0],
    );

    var at = root * sector;
    at = record(at, lba: root, size: sector, directory: true, name: [0]);
    at = record(at, lba: root, size: sector, directory: true, name: [1]);
    at = record(
      at,
      lba: iconSector + 1,
      size: 16,
      directory: false,
      name: ascii.encode('PS3_DISC.SFB;1'),
    );
    if (gameDirectory != null) {
      record(
        at,
        lba: game,
        size: 2 * sector,
        directory: true,
        name: ascii.encode(gameDirectory),
      );
    }

    at = game * sector;
    at = record(at, lba: game, size: 2 * sector, directory: true, name: [0]);
    at = record(at, lba: root, size: sector, directory: true, name: [1]);
    record(
      at,
      lba: iconSector,
      size: 8,
      directory: false,
      name: ascii.encode('ICON0.PNG;1'),
    );
    record(
      (game + 1) * sector,
      lba: sfoSector,
      size: sfo.length,
      directory: false,
      name: ascii.encode(paramSfoName),
    );
    out.setRange(sfoSector * sector, sfoSector * sector + sfo.length, sfo);
    return out;
  }
}
