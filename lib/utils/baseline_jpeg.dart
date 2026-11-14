import 'dart:math' as math;
import 'dart:typed_data';

/// Baseline JPEG (JFIF, 8-bit, YCbCr 4:4:4) encoder for small images.
///
/// A Nintendo Switch user profile carries its picture as a JPEG, and Flutter
/// can decode an image but only encode PNG. RewindBox owns this encoder so a
/// profile picture needs neither a native round trip nor another package. It
/// uses the example quantization and Huffman tables of ITU-T T.81 Annex K.
abstract final class BaselineJpeg {
  /// Encodes [rgba] (`width * height * 4` bytes, row-major, alpha ignored).
  /// [quality] is 1 (smallest) to 100 (best), on the usual IJG scale.
  static Uint8List encode(Uint8List rgba, int width, int height, {int quality = 88}) {
    if (width < 1 || height < 1 || width > 4096 || height > 4096) {
      throw ArgumentError('Unsupported image size $width x $height');
    }
    if (rgba.length < width * height * 4) {
      throw ArgumentError('Pixel buffer shorter than $width x $height RGBA');
    }
    final q = quality.clamp(1, 100);
    final scale = q < 50 ? 5000 ~/ q : 200 - q * 2;
    final luma = _scaled(_lumaQuant, scale);
    final chroma = _scaled(_chromaQuant, scale);
    final out = _BitWriter();

    out.marker(0xD8); // SOI
    out.segment(0xE0, [0x4A, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00]);
    out.segment(0xDB, [0x00, for (final index in _zigzag) luma[index]]);
    out.segment(0xDB, [0x01, for (final index in _zigzag) chroma[index]]);
    out.segment(0xC0, [
      0x08, height >> 8, height & 0xFF, width >> 8, width & 0xFF, 0x03,
      0x01, 0x11, 0x00, 0x02, 0x11, 0x01, 0x03, 0x11, 0x01,
    ]);
    out.segment(0xC4, [0x00, ..._dcLumaBits, ..._dcValues]);
    out.segment(0xC4, [0x10, ..._acLumaBits, ..._acLumaValues]);
    out.segment(0xC4, [0x01, ..._dcChromaBits, ..._dcValues]);
    out.segment(0xC4, [0x11, ..._acChromaBits, ..._acChromaValues]);
    out.segment(0xDA, [0x03, 0x01, 0x00, 0x02, 0x11, 0x03, 0x11, 0x00, 0x3F, 0x00]);

    final dcLuma = _HuffmanTable(_dcLumaBits, _dcValues);
    final acLuma = _HuffmanTable(_acLumaBits, _acLumaValues);
    final dcChroma = _HuffmanTable(_dcChromaBits, _dcValues);
    final acChroma = _HuffmanTable(_acChromaBits, _acChromaValues);
    final blockY = Float64List(64), blockCb = Float64List(64), blockCr = Float64List(64);
    final previous = [0, 0, 0];
    for (var top = 0; top < height; top += 8) {
      for (var left = 0; left < width; left += 8) {
        for (var y = 0; y < 8; y++) {
          // Edge blocks repeat the last row and column.
          final sourceY = top + y < height ? top + y : height - 1;
          for (var x = 0; x < 8; x++) {
            final sourceX = left + x < width ? left + x : width - 1;
            final pixel = (sourceY * width + sourceX) * 4;
            final r = rgba[pixel], g = rgba[pixel + 1], b = rgba[pixel + 2];
            final at = y * 8 + x;
            blockY[at] = 0.299 * r + 0.587 * g + 0.114 * b - 128;
            blockCb[at] = -0.168736 * r - 0.331264 * g + 0.5 * b;
            blockCr[at] = 0.5 * r - 0.418688 * g - 0.081312 * b;
          }
        }
        previous[0] = _block(out, blockY, luma, previous[0], dcLuma, acLuma);
        previous[1] = _block(out, blockCb, chroma, previous[1], dcChroma, acChroma);
        previous[2] = _block(out, blockCr, chroma, previous[2], dcChroma, acChroma);
      }
    }
    out.flushBits();
    out.marker(0xD9); // EOI
    return out.takeBytes();
  }

  static List<int> _scaled(List<int> table, int scale) => [
    for (final value in table) ((value * scale + 50) ~/ 100).clamp(1, 255),
  ];

  static final List<double> _cosine = [
    for (var u = 0; u < 8; u++)
      for (var x = 0; x < 8; x++) math.cos((2 * x + 1) * u * math.pi / 16) * (u == 0 ? math.sqrt(0.125) : 0.5),
  ];
  static final Float64List _scratch = Float64List(64);

  /// Transforms, quantizes and entropy-codes one 8x8 block; returns its DC value.
  static int _block(_BitWriter out, Float64List block, List<int> quant, int previousDc, _HuffmanTable dc, _HuffmanTable ac) {
    for (var y = 0; y < 8; y++) {
      for (var u = 0; u < 8; u++) {
        var sum = 0.0;
        for (var x = 0; x < 8; x++) {
          sum += block[y * 8 + x] * _cosine[u * 8 + x];
        }
        _scratch[y * 8 + u] = sum;
      }
    }
    final coefficients = List<int>.filled(64, 0);
    for (var u = 0; u < 8; u++) {
      for (var v = 0; v < 8; v++) {
        var sum = 0.0;
        for (var y = 0; y < 8; y++) {
          sum += _scratch[y * 8 + u] * _cosine[v * 8 + y];
        }
        final index = v * 8 + u;
        coefficients[index] = (sum / quant[index]).round();
      }
    }
    final dcValue = coefficients[0];
    final difference = dcValue - previousDc;
    final dcSize = _magnitude(difference);
    out.bits(dc.codes[dcSize], dc.sizes[dcSize]);
    if (dcSize > 0) out.bits(_amplitude(difference, dcSize), dcSize);
    var run = 0;
    for (var position = 1; position < 64; position++) {
      final value = coefficients[_zigzag[position]];
      if (value == 0) {
        run++;
        continue;
      }
      while (run > 15) {
        out.bits(ac.codes[0xF0], ac.sizes[0xF0]);
        run -= 16;
      }
      final size = _magnitude(value);
      final symbol = (run << 4) | size;
      out.bits(ac.codes[symbol], ac.sizes[symbol]);
      out.bits(_amplitude(value, size), size);
      run = 0;
    }
    if (run > 0) out.bits(ac.codes[0x00], ac.sizes[0x00]);
    return dcValue;
  }

  static int _magnitude(int value) {
    var remaining = value.abs(), size = 0;
    while (remaining > 0) {
      size++;
      remaining >>= 1;
    }
    return size;
  }

  static int _amplitude(int value, int size) => value >= 0 ? value : value + (1 << size) - 1;

  static const List<int> _zigzag = [
    0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63,
  ];
  static const List<int> _lumaQuant = [
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99,
  ];
  static const List<int> _chromaQuant = [
    17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99, 47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99, 99,
  ];
  static const List<int> _dcLumaBits = [0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0];
  static const List<int> _dcChromaBits = [0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0];
  static const List<int> _dcValues = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
  static const List<int> _acLumaBits = [0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7D];
  static const List<int> _acLumaValues = [
    0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07,
    0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0,
    0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
    0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
    0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7,
    0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5,
    0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
    0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8,
    0xF9, 0xFA,
  ];
  static const List<int> _acChromaBits = [0, 2, 1, 2, 4, 4, 3, 4, 7, 5, 4, 4, 0, 1, 2, 0x77];
  static const List<int> _acChromaValues = [
    0x00, 0x01, 0x02, 0x03, 0x11, 0x04, 0x05, 0x21, 0x31, 0x06, 0x12, 0x41, 0x51, 0x07, 0x61, 0x71,
    0x13, 0x22, 0x32, 0x81, 0x08, 0x14, 0x42, 0x91, 0xA1, 0xB1, 0xC1, 0x09, 0x23, 0x33, 0x52, 0xF0,
    0x15, 0x62, 0x72, 0xD1, 0x0A, 0x16, 0x24, 0x34, 0xE1, 0x25, 0xF1, 0x17, 0x18, 0x19, 0x1A, 0x26,
    0x27, 0x28, 0x29, 0x2A, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48,
    0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68,
    0x69, 0x6A, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87,
    0x88, 0x89, 0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3, 0xA4, 0xA5,
    0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3,
    0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA,
    0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8,
    0xF9, 0xFA,
  ];
}

/// Canonical Huffman codes for one table (T.81 Annex C).
final class _HuffmanTable {
  _HuffmanTable(List<int> bits, List<int> values) {
    var code = 0, index = 0;
    for (var length = 1; length <= 16; length++) {
      for (var count = 0; count < bits[length - 1]; count++) {
        final symbol = values[index++];
        codes[symbol] = code++;
        sizes[symbol] = length;
      }
      code <<= 1;
    }
  }
  final List<int> codes = List<int>.filled(256, 0);
  final List<int> sizes = List<int>.filled(256, 0);
}

final class _BitWriter {
  final BytesBuilder _bytes = BytesBuilder(copy: false);
  int _accumulator = 0, _count = 0;

  void marker(int code) => _bytes.add([0xFF, code]);

  void segment(int code, List<int> payload) {
    final length = payload.length + 2;
    _bytes.add([0xFF, code, length >> 8, length & 0xFF, ...payload]);
  }

  void bits(int value, int size) {
    for (var bit = size - 1; bit >= 0; bit--) {
      _accumulator = (_accumulator << 1) | ((value >> bit) & 1);
      if (++_count == 8) _emit();
    }
  }

  /// Pads the last byte with ones, as the standard requires.
  void flushBits() {
    while (_count != 0) {
      bits(1, 1);
    }
  }

  void _emit() {
    _bytes.addByte(_accumulator);
    if (_accumulator == 0xFF) _bytes.addByte(0x00); // byte stuffing
    _accumulator = 0;
    _count = 0;
  }

  Uint8List takeBytes() => _bytes.takeBytes();
}
