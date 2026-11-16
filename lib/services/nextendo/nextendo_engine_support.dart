import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

/// Whether the Switch engine shipped in this build takes Nextendo online play.
///
/// Nothing is loaded: loading the Core from a menu would mark the process as a
/// Switch 1 one (the Switch 2 engine then refuses to start). The build answers
/// first: the IPA carries the packaged Core's identity
/// (`MeloNX-native-identity.json`, written beside the Core when the IPA is
/// built and checked against it), which names every adapter compiled into it.
/// Without that file, the Core binary is searched for texts of the online lot
/// kept as UTF-16 by NativeAOT. The launch itself confirms it: the engine
/// answers the online request or refuses it, and the launch journal says which.
abstract final class NextendoEngineSupport {
  static const protocol = 'rewindbox-nextendo-online-1';

  /// The adapter that adds online play to the engine.
  static const adapter = 'adapt_nextendo_online.py';

  /// Texts of the online lot searched in the binary. NativeAOT inlines the
  /// protocol constant (absent from Core 127b72b9); the trust-store error of
  /// EmbeddedOnline is kept.
  static const binaryMarkers = [protocol, 'A Nextendo root differs from its published fingerprint'];

  static Future<bool>? _cached;

  /// The answer for the running application, computed once.
  static Future<bool> supported() => _cached ??= _check(_bundle());

  /// For tests: forget the cached answer.
  static void reset() => _cached = null;

  static String? _bundle() => Platform.isIOS ? File(Platform.resolvedExecutable).parent.path : null;

  static Future<bool> _check(String? bundle) async {
    if (bundle == null) return false;
    try {
      return await Isolate.run(() => supportedIn(bundle));
    } on Object {
      return false;
    }
  }

  /// The answer for the application bundle at [bundle].
  static bool supportedIn(String bundle) {
    final identity = File('$bundle/MeloNX-native-identity.json');
    if (identity.existsSync()) {
      try {
        final receipt = jsonDecode(identity.readAsStringSync());
        final core = receipt is Map ? receipt['sourceCoreIdentity'] : null;
        final adaptations = core is Map ? core['adaptations'] : null;
        if (adaptations is Map) {
          return adaptations.keys.any((name) => name is String && (name == adapter || name.endsWith('/$adapter')));
        }
      } on FormatException {
        // An unreadable receipt: the binary decides.
      }
    }
    return containsAny('$bundle/Frameworks/MeloNXCore.framework/MeloNXCore', binaryMarkers);
  }

  /// Whether the file at [path] holds one of [texts] as UTF-16LE text.
  static bool containsAny(String path, List<String> texts) {
    final file = File(path);
    if (!file.existsSync() || texts.isEmpty) return false;
    final needles = [for (final text in texts) Uint8List.fromList(utf16le(text))];
    final longest = needles.map((n) => n.length).reduce((a, b) => a > b ? a : b);
    final reader = file.openSync();
    try {
      const chunk = 4 << 20;
      final buffer = Uint8List(chunk + longest);
      var carried = 0;
      while (true) {
        final read = reader.readIntoSync(buffer, carried, carried + chunk);
        if (read == 0) return false;
        final end = carried + read;
        for (final needle in needles) {
          if (_indexOf(buffer, end, needle) >= 0) return true;
        }
        // Keep the tail that could start a match across the chunk boundary.
        final keep = longest - 1 < end ? longest - 1 : end;
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

  /// The UTF-16LE bytes of [text].
  static List<int> utf16le(String text) => [for (final unit in text.codeUnits) ...[unit & 0xFF, unit >> 8]];
}
