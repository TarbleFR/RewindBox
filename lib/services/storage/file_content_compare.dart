import 'dart:io';
import 'dart:typed_data';

/// True when [a] and [b] hold exactly the same bytes. Different lengths
/// answer false at once; otherwise both files are read chunk by chunk and the
/// first difference ends the comparison (never both files in memory).
Future<bool> filesHaveSameContent(
  File a,
  File b, {
  int chunkBytes = 1 << 20,
}) async {
  if (await a.length() != await b.length()) return false;
  RandomAccessFile? first;
  RandomAccessFile? second;
  try {
    first = await a.open();
    second = await b.open();
    while (true) {
      final left = await first.read(chunkBytes);
      final right = await second.read(chunkBytes);
      if (left.length != right.length) return false;
      if (left.isEmpty) return true;
      if (!_sameBytes(left, right)) return false;
    }
  } finally {
    await first?.close();
    await second?.close();
  }
}

bool _sameBytes(Uint8List left, Uint8List right) {
  for (var i = 0; i < left.length; i++) {
    if (left[i] != right[i]) return false;
  }
  return true;
}
