import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// One line of text recognised on a scan, normalised (0..1, top-left).
class BoxReaderLine {
  const BoxReaderLine({
    required this.text,
    required this.confidence,
    required this.x,
    required this.y,
    required this.width,
    required this.height,
  });

  final String text;
  final double confidence;
  final double x;
  final double y;
  final double width;
  final double height;

  double get bottom => y + height;
  double get right => x + width;

  Map<String, dynamic> toJson() =>
      {'text': text, 'confidence': confidence, 'x': x, 'y': y, 'w': width, 'h': height};

  static BoxReaderLine? fromJson(Object? raw) {
    if (raw is! Map) return null;
    double d(Object? v) => v is num ? v.toDouble() : 0;
    final text = raw['text'];
    if (text is! String || text.trim().isEmpty) return null;
    return BoxReaderLine(
      text: text,
      confidence: d(raw['confidence']).clamp(0, 1).toDouble(),
      x: d(raw['x']),
      y: d(raw['y']),
      width: d(raw['w']),
      height: d(raw['h']),
    );
  }
}

class BoxReaderRecognition {
  const BoxReaderRecognition({required this.lines, required this.languages});
  final List<BoxReaderLine> lines;

  /// Recognition languages used ("auto" when Vision detected them).
  final List<String> languages;
}

/// Why a native request failed: a stable code for translated messages, and
/// the raw detail for diagnostics.
class BoxReaderException implements Exception {
  const BoxReaderException(this.code, [this.detail]);
  final String code;
  final String? detail;

  static const unavailable = 'unavailable';
  static const unsupported = 'unsupported';
  static const notInstalled = 'not-installed';
  static const cancelled = 'cancelled';
  static const failed = 'failed';
  static const ocrFailed = 'ocr-failed';

  @override
  String toString() => 'BoxReaderException($code${detail == null ? '' : ': $detail'})';
}

/// On-device reading of a box back: Apple Vision text recognition,
/// NaturalLanguage detection and Apple Translation (iOS 18). Only iOS has
/// the native side; elsewhere every call reports [BoxReaderException.unavailable].
class NeoBoxReader {
  NeoBoxReader._();

  static const MethodChannel _channel = MethodChannel('neostation/neo_box_reader');

  /// Tests exercise the channel contract on the host.
  @visibleForTesting
  static bool? debugSupported;

  static bool get isSupported => debugSupported ?? Platform.isIOS;

  /// NeoStation language codes and the identifiers Apple's frameworks use.
  static const Map<String, String> appleLanguages = {
    'en': 'en',
    'es': 'es',
    'ru': 'ru',
    'zh': 'zh-Hans',
    'zh_Hant': 'zh-Hant',
    'pt': 'pt-BR',
    'fr': 'fr',
    'de': 'de',
    'it': 'it',
    'id': 'id',
    'ja': 'ja',
    'ko': 'ko',
  };

  /// NeoStation code of an Apple language identifier ("zh-Hans", "pt-BR",
  /// "ja-JP"), or null for a language NeoStation does not offer.
  static String? appCodeOf(String? identifier) {
    if (identifier == null || identifier.isEmpty) return null;
    final id = identifier.replaceAll('_', '-');
    final lower = id.toLowerCase();
    if (lower.startsWith('zh')) {
      if (lower.contains('hant') || lower.endsWith('-tw') || lower.endsWith('-hk') || lower.endsWith('-mo')) {
        return 'zh_Hant';
      }
      return 'zh';
    }
    final base = lower.split('-').first;
    return appleLanguages.containsKey(base) ? base : null;
  }

  static Future<T> _invoke<T>(String method, [Map<String, Object?>? args]) async {
    if (!isSupported) throw const BoxReaderException(BoxReaderException.unavailable);
    try {
      final value = await _channel.invokeMethod<Object?>(method, args);
      return value as T;
    } on PlatformException catch (e) {
      throw BoxReaderException(e.code, e.message);
    } on MissingPluginException {
      throw const BoxReaderException(BoxReaderException.unavailable);
    }
  }

  /// Recognition languages of this device's text recogniser.
  static Future<List<String>> recognitionLanguages() async {
    final caps = await _invoke<Map<Object?, Object?>?>('capabilities');
    final langs = caps?['ocrLanguages'];
    return langs is List ? [for (final l in langs) l.toString()] : const [];
  }

  static Future<BoxReaderRecognition> recognize(String path, {List<String> languages = const []}) async {
    final raw = await _invoke<Map<Object?, Object?>?>('recognize', {'path': path, 'languages': languages});
    final lines = <BoxReaderLine>[];
    final rawLines = raw?['lines'];
    if (rawLines is List) {
      for (final l in rawLines) {
        final line = BoxReaderLine.fromJson(l);
        if (line != null) lines.add(line);
      }
    }
    final used = raw?['languages'];
    return BoxReaderRecognition(
      lines: lines,
      languages: used is List ? [for (final l in used) l.toString()] : const [],
    );
  }

  /// Dominant language of [text] as an Apple identifier, with probability.
  static Future<(String?, double)> detectLanguage(String text) async {
    final raw = await _invoke<Map<Object?, Object?>?>('detectLanguage', {'text': text});
    final language = raw?['language'];
    final p = raw?['confidence'];
    return (language is String ? language : null, p is num ? p.toDouble() : 0.0);
  }

  /// "installed", "supported" (downloadable) or "unsupported".
  static Future<String> translationStatus({String? source, required String target, String? sample}) =>
      _invoke<String>('translationStatus', {'source': source, 'target': target, 'sample': sample});

  static Future<List<String>> supportedTranslationLanguages() async {
    final raw = await _invoke<List<Object?>?>('supportedTranslationLanguages');
    return raw == null ? const [] : [for (final l in raw) l.toString()];
  }

  /// Translates [texts] (one request each, order kept). iOS may first show
  /// its own prompt to download a language.
  static Future<(List<String>, String?)> translate(
    List<String> texts, {
    String? source,
    required String target,
  }) async {
    final raw = await _invoke<Map<Object?, Object?>?>(
      'translate',
      {'texts': texts, 'source': source, 'target': target},
    );
    final out = raw?['texts'];
    final detected = raw?['source'];
    final list = out is List ? [for (final t in out) t.toString()] : <String>[];
    if (list.length != texts.length) throw const BoxReaderException(BoxReaderException.failed, 'count mismatch');
    return (list, detected is String ? detected : null);
  }
}
