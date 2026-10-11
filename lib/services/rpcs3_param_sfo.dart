import 'dart:convert';
import 'dart:typed_data';

/// Minimal reader of a PlayStation 3 `PARAM.SFO` (PSF) descriptor.
///
/// Layout (all integers little-endian): magic `00 50 53 46` (`"\0PSF"`),
/// version u32, key table offset u32, data table offset u32, entry count
/// u32, then one 16-byte index per entry (key offset u16, data format u16,
/// data length u32, data maximum length u32, data offset u32). Keys are
/// NUL-terminated ASCII strings of the key table; values of format `0x0204`
/// are NUL-terminated UTF-8 strings, `0x0004` UTF-8 strings without
/// terminator and `0x0404` signed 32-bit integers.
///
/// Only what the game-save exchange needs is read: the string values used
/// for reports (`TITLE`, `SUB_TITLE`, `DETAIL`, `SAVEDATA_DIRECTORY`) and the
/// structural validity that decides whether a folder is a save at all.
class Rpcs3ParamSfo {
  const Rpcs3ParamSfo._(this.strings, this.integers);

  /// `"\0PSF"` read as a little-endian 32-bit word.
  static const int magic = 0x46535000;

  /// A save descriptor is a few kilobytes; anything larger is not read.
  static const int maxFileLength = 1 << 20;

  static const int _maxEntries = 4096;
  static const int formatUtf8Special = 0x0004;
  static const int formatUtf8 = 0x0204;
  static const int formatInt32 = 0x0404;

  /// String values by key (formats `0x0204` and `0x0004`).
  final Map<String, String> strings;

  /// Integer values by key (format `0x0404`).
  final Map<String, int> integers;

  String? get title => _nonEmpty(strings['TITLE']);
  String? get subTitle => _nonEmpty(strings['SUB_TITLE']);
  String? get detail => _nonEmpty(strings['DETAIL']);
  String? get saveDataDirectory => _nonEmpty(strings['SAVEDATA_DIRECTORY']);

  static String? _nonEmpty(String? value) {
    if (value == null) return null;
    final trimmed = value.trim();
    return trimmed.isEmpty ? null : trimmed;
  }

  /// Parses [bytes]; throws a [FormatException] when the file is not a
  /// structurally valid PSF descriptor.
  static Rpcs3ParamSfo parse(Uint8List bytes) {
    if (bytes.length < 20) {
      throw const FormatException('PARAM.SFO is shorter than its header');
    }
    final view = ByteData.sublistView(bytes);
    if (view.getUint32(0, Endian.little) != magic) {
      throw const FormatException('PARAM.SFO magic is not "\\0PSF"');
    }
    final keyTable = view.getUint32(8, Endian.little);
    final dataTable = view.getUint32(12, Endian.little);
    final count = view.getUint32(16, Endian.little);
    if (count > _maxEntries) {
      throw FormatException('PARAM.SFO declares $count entries');
    }
    final indexEnd = 20 + count * 16;
    if (indexEnd > bytes.length ||
        keyTable < indexEnd ||
        keyTable > bytes.length ||
        dataTable < keyTable ||
        dataTable > bytes.length) {
      throw const FormatException('PARAM.SFO tables are out of range');
    }

    final strings = <String, String>{};
    final integers = <String, int>{};
    for (var index = 0; index < count; index++) {
      final at = 20 + index * 16;
      final keyOffset = view.getUint16(at, Endian.little);
      final format = view.getUint16(at + 2, Endian.little);
      final length = view.getUint32(at + 4, Endian.little);
      final maxLength = view.getUint32(at + 8, Endian.little);
      final dataOffset = view.getUint32(at + 12, Endian.little);

      final keyStart = keyTable + keyOffset;
      if (keyStart >= dataTable) {
        throw FormatException('PARAM.SFO key $index is out of range');
      }
      var keyEnd = keyStart;
      while (keyEnd < dataTable && bytes[keyEnd] != 0) {
        keyEnd++;
      }
      if (keyEnd == keyStart) {
        throw FormatException('PARAM.SFO key $index is empty');
      }
      final key = ascii.decode(
        bytes.sublist(keyStart, keyEnd),
        allowInvalid: true,
      );

      final valueStart = dataTable + dataOffset;
      final valueLength = length > maxLength && maxLength > 0 ? maxLength : length;
      if (valueStart > bytes.length || valueStart + valueLength > bytes.length) {
        throw FormatException('PARAM.SFO value of $key is out of range');
      }
      final value = Uint8List.sublistView(
        bytes,
        valueStart,
        valueStart + valueLength,
      );
      switch (format) {
        case formatUtf8:
          var end = value.length;
          final terminator = value.indexOf(0);
          if (terminator >= 0) end = terminator;
          strings[key] = utf8.decode(
            value.sublist(0, end),
            allowMalformed: true,
          );
        case formatUtf8Special:
          strings[key] = utf8.decode(value, allowMalformed: true);
        case formatInt32:
          if (value.length < 4) {
            throw FormatException('PARAM.SFO integer $key is truncated');
          }
          integers[key] = ByteData.sublistView(value).getInt32(0, Endian.little);
        default:
          // Unknown formats are tolerated: the file is still a PSF descriptor.
          break;
      }
    }
    return Rpcs3ParamSfo._(
      Map.unmodifiable(strings),
      Map.unmodifiable(integers),
    );
  }

  /// [parse] without the exception: null when [bytes] are not a descriptor.
  static Rpcs3ParamSfo? tryParse(Uint8List bytes) {
    try {
      return parse(bytes);
    } on FormatException {
      return null;
    }
  }
}
