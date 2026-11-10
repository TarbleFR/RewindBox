import 'dart:convert';

/// The exact bytes of Python's
/// `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"`
/// (tools/cheats/unified_catalogue.canonical). Catalogue chunks are verified
/// by the SHA-256 of these bytes, so a chunk rebuilt in the app must encode
/// exactly as the publisher did.
List<int> canonicalJson(Object? value) {
  final buffer = StringBuffer();
  _write(buffer, value);
  buffer.write('\n');
  return utf8.encode(buffer.toString());
}

void _write(StringBuffer out, Object? value) {
  switch (value) {
    case null:
      out.write('null');
    case bool():
      out.write(value ? 'true' : 'false');
    case int():
      out.write(value);
    case double():
      out.write(pythonFloat(value));
    case String():
      _string(out, value);
    case List():
      out.write('[');
      for (var i = 0; i < value.length; i++) {
        if (i > 0) out.write(',');
        _write(out, value[i]);
      }
      out.write(']');
    case Map():
      final keys = [for (final key in value.keys) key.toString()]..sort(_codePointOrder);
      out.write('{');
      for (var i = 0; i < keys.length; i++) {
        if (i > 0) out.write(',');
        _string(out, keys[i]);
        out.write(':');
        _write(out, value[keys[i]]);
      }
      out.write('}');
    default:
      throw ArgumentError('not JSON: ${value.runtimeType}');
  }
}

/// Python sorts keys by code point; Dart's compareTo uses UTF-16 units.
int _codePointOrder(String a, String b) {
  final left = a.runes.iterator;
  final right = b.runes.iterator;
  while (true) {
    final hasLeft = left.moveNext();
    final hasRight = right.moveNext();
    if (!hasLeft || !hasRight) return hasLeft ? 1 : (hasRight ? -1 : 0);
    if (left.current != right.current) return left.current - right.current;
  }
}

void _string(StringBuffer out, String value) {
  out.write('"');
  for (final unit in value.codeUnits) {
    switch (unit) {
      case 0x22:
        out.write(r'\"');
      case 0x5C:
        out.write(r'\\');
      case 0x0A:
        out.write(r'\n');
      case 0x0D:
        out.write(r'\r');
      case 0x09:
        out.write(r'\t');
      case 0x08:
        out.write(r'\b');
      case 0x0C:
        out.write(r'\f');
      default:
        if (unit < 0x20) {
          out.write(r'\u');
          out.write(unit.toRadixString(16).padLeft(4, '0'));
        } else {
          out.writeCharCode(unit);
        }
    }
  }
  out.write('"');
}

/// Python's `repr(float)`: the shortest round-trip digits, fixed notation
/// for 1e-4 <= |x| < 1e16, otherwise `d[.ddd]e±XX`.
String pythonFloat(double value) {
  if (value.isNaN || value.isInfinite) throw ArgumentError('not JSON: $value');
  if (value == 0) return value.isNegative ? '-0.0' : '0.0';
  final exponential = value.abs().toStringAsExponential();
  final mark = exponential.indexOf('e');
  final digits = exponential.substring(0, mark).replaceAll('.', '');
  final exponent = int.parse(exponential.substring(mark + 1));
  final sign = value.isNegative ? '-' : '';
  if (exponent >= -4 && exponent < 16) {
    final point = exponent + 1;
    if (point <= 0) return '${sign}0.${'0' * -point}$digits';
    if (point >= digits.length) return '$sign$digits${'0' * (point - digits.length)}.0';
    return '$sign${digits.substring(0, point)}.${digits.substring(point)}';
  }
  final mantissa = digits.length == 1 ? digits : '${digits[0]}.${digits.substring(1)}';
  final power = exponent.abs().toString().padLeft(2, '0');
  return '$sign${mantissa}e${exponent < 0 ? '-' : '+'}$power';
}
