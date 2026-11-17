import 'dart:typed_data';

import 'package:crypto/crypto.dart';

/// Ed25519 signature verification (RFC 8032, section 5.1.7), for Nextendo's
/// signed documents: the game catalog (`catalog-key-1`) and the NPLN patch
/// index (`npln-patches-key-1`) are signed with Ed25519 over the base64-decoded
/// payload bytes. Verification only: no secret key is ever handled here.
///
/// Plain BigInt arithmetic in extended coordinates: a verification takes a few
/// milliseconds, and RewindBox verifies a document at most a few times a day.
/// Checked against RFC 8032's test vectors and a live catalog
/// (test/nextendo_catalog_test.dart).
abstract final class NextendoEd25519 {
  static final BigInt _p = (BigInt.one << 255) - BigInt.from(19);
  static final BigInt _l = (BigInt.one << 252) + BigInt.parse('27742317777372353535851937790883648493');
  static final BigInt _d = (BigInt.from(-121665) * BigInt.from(121666).modPow(_p - BigInt.two, _p)) % _p;
  static final BigInt _sqrtM1 = BigInt.two.modPow((_p - BigInt.one) ~/ BigInt.from(4), _p);
  static final BigInt _mask255 = (BigInt.one << 255) - BigInt.one;
  static final List<BigInt> _base = _basePoint();

  /// Whether [signature] (64 bytes) is a valid Ed25519 signature of [message]
  /// by [publicKey] (32 bytes). Never throws.
  static bool verify(List<int> publicKey, List<int> message, List<int> signature) {
    try {
      if (publicKey.length != 32 || signature.length != 64) return false;
      final a = _decode(publicKey);
      if (a == null) return false;
      final rBytes = signature.sublist(0, 32);
      if (_decode(rBytes) == null) return false;
      final s = _fromLittleEndian(signature.sublist(32, 64));
      if (s >= _l) return false;
      final digest = sha512.convert([...rBytes, ...publicKey, ...message]).bytes;
      final k = _fromLittleEndian(digest) % _l;
      // [S]B == R + [k]A, compared as encode([S]B + [L - k]A) == R.
      final check = _encode(_add(_multiply(s, _base), _multiply((_l - k) % _l, a)));
      for (var i = 0; i < 32; i++) {
        if (check[i] != rBytes[i]) return false;
      }
      return true;
    } on Object {
      return false;
    }
  }

  static List<BigInt> _basePoint() {
    final y = (BigInt.from(4) * BigInt.from(5).modPow(_p - BigInt.two, _p)) % _p;
    final x = _recoverX(y, 0)!;
    return [x, y, BigInt.one, (x * y) % _p];
  }

  static BigInt? _recoverX(BigInt y, int sign) {
    if (y >= _p) return null;
    final u = (y * y - BigInt.one) % _p;
    final v = (_d * y * y + BigInt.one) % _p;
    final v3 = v.modPow(BigInt.from(3), _p);
    final v7 = v.modPow(BigInt.from(7), _p);
    var x = (u * v3 * (u * v7 % _p).modPow((_p - BigInt.from(5)) ~/ BigInt.from(8), _p)) % _p;
    final vx2 = (v * x * x) % _p;
    if (vx2 == u) {
      // x is a square root.
    } else if (vx2 == (-u) % _p) {
      x = (x * _sqrtM1) % _p;
    } else {
      return null;
    }
    if (x == BigInt.zero && sign == 1) return null;
    if ((x & BigInt.one).toInt() != sign) x = _p - x;
    return x;
  }

  static List<BigInt>? _decode(List<int> bytes) {
    if (bytes.length != 32) return null;
    final n = _fromLittleEndian(bytes);
    final sign = (n >> 255).toInt();
    final y = n & _mask255;
    final x = _recoverX(y, sign);
    if (x == null) return null;
    return [x, y, BigInt.one, (x * y) % _p];
  }

  static List<BigInt> _add(List<BigInt> p, List<BigInt> q) {
    final a = ((p[1] - p[0]) * (q[1] - q[0])) % _p;
    final b = ((p[1] + p[0]) * (q[1] + q[0])) % _p;
    final c = (p[3] * BigInt.two * _d * q[3]) % _p;
    final dd = (p[2] * BigInt.two * q[2]) % _p;
    final e = b - a;
    final f = dd - c;
    final g = dd + c;
    final h = b + a;
    return [(e * f) % _p, (g * h) % _p, (f * g) % _p, (e * h) % _p];
  }

  static List<BigInt> _multiply(BigInt scalar, List<BigInt> point) {
    var result = [BigInt.zero, BigInt.one, BigInt.one, BigInt.zero];
    var addend = point;
    var s = scalar;
    while (s > BigInt.zero) {
      if ((s & BigInt.one) == BigInt.one) result = _add(result, addend);
      addend = _add(addend, addend);
      s = s >> 1;
    }
    return result;
  }

  static Uint8List _encode(List<BigInt> point) {
    final zInverse = point[2].modPow(_p - BigInt.two, _p);
    final x = (point[0] * zInverse) % _p;
    final y = (point[1] * zInverse) % _p;
    var n = y | ((x & BigInt.one) << 255);
    final out = Uint8List(32);
    for (var i = 0; i < 32; i++) {
      out[i] = (n & BigInt.from(0xff)).toInt();
      n = n >> 8;
    }
    return out;
  }

  static BigInt _fromLittleEndian(List<int> bytes) {
    var n = BigInt.zero;
    for (var i = bytes.length - 1; i >= 0; i--) {
      n = (n << 8) | BigInt.from(bytes[i] & 0xff);
    }
    return n;
  }
}
