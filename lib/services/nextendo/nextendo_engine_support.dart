import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

/// Whether the Switch engine shipped in this build takes Nextendo online play.
///
/// The engine's online request answers a protocol name (`EmbeddedOnline.Protocol`
/// in the MeloNX Core); NativeAOT keeps that literal as UTF-16 text in the
/// binary. The binary is read here, never loaded: loading the Core from a menu
/// would mark the process as a MeloNX one (the Switch 2 engine then refuses to
/// start). The launch itself confirms it: the engine answers the request or
/// refuses it, and the launch journal says which.
abstract final class NextendoEngineSupport {
  static const protocol = 'rewindbox-nextendo-online-1';

  static Future<bool>? _cached;

  /// The answer for the running application, computed once.
  static Future<bool> supported() => _cached ??= _check(_corePath());

  /// For tests: forget the cached answer.
  static void reset() => _cached = null;

  static String? _corePath() {
    if (!Platform.isIOS) return null;
    final bundle = File(Platform.resolvedExecutable).parent.path;
    return '$bundle/Frameworks/MeloNXCore.framework/MeloNXCore';
  }

  static Future<bool> _check(String? path) async {
    if (path == null) return false;
    try {
      return await Isolate.run(() => containsProtocol(path));
    } on Object {
      return false;
    }
  }

  /// Whether the file at [path] holds [protocol] as UTF-16LE text.
  static bool containsProtocol(String path) {
    final file = File(path);
    if (!file.existsSync()) return false;
    final needle = Uint8List.fromList(protocolBytes());
    final reader = file.openSync();
    try {
      const chunk = 4 << 20;
      final buffer = Uint8List(chunk + needle.length);
      var carried = 0;
      while (true) {
        final read = reader.readIntoSync(buffer, carried, carried + chunk);
        if (read == 0) return false;
        final end = carried + read;
        if (_indexOf(buffer, end, needle) >= 0) return true;
        // Keep the tail that could start a match across the chunk boundary.
        final keep = needle.length - 1 < end ? needle.length - 1 : end;
        buffer.setRange(0, keep, buffer, end - keep);
        carried = keep;
      }
    } finally {
      reader.closeSync();
    }
  }

  static int _indexOf(Uint8List haystack, int length, Uint8List needle) {
    final first = needle[0];
    final last = length - needle.length;
    outer:
    for (var i = 0; i <= last; i++) {
      if (haystack[i] != first) continue;
      for (var j = 1; j < needle.length; j++) {
        if (haystack[i + j] != needle[j]) continue outer;
      }
      return i;
    }
    return -1;
  }

  /// The UTF-16LE bytes searched for (tests build a stand-in binary with them).
  static List<int> protocolBytes() => [for (final unit in protocol.codeUnits) ...[unit & 0xFF, unit >> 8]];
}
