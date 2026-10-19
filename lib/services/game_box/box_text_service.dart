import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:crypto/crypto.dart';
import 'package:neo_box_reader/neo_box_reader.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'package:neostation/services/game_box/box_text_layout.dart';
import 'package:neostation/services/game_box/game_box_regions.dart';
import 'package:neostation/services/logger_service.dart';

/// Text of a back scan as recognised on the device.
class BoxTranscript {
  BoxTranscript({
    required this.imageSha256,
    required this.lines,
    required this.document,
    required this.language,
    required this.languageConfidence,
    required this.recognitionLanguages,
    required this.createdAt,
    this.fromCache = false,
  });

  static const int version = 1;

  /// SHA-256 of the scan: a different picture never reuses this text.
  final String imageSha256;
  final List<BoxReaderLine> lines;
  final BoxTextDocument document;

  /// NeoStation code of the dominant language (null: not one of the twelve,
  /// or not identified) and the raw identifier when known.
  final String? language;
  final double languageConfidence;
  final List<String> recognitionLanguages;
  final DateTime createdAt;
  final bool fromCache;

  String? rawLanguage;

  Map<String, dynamic> toJson() => {
        'version': version,
        'engine': 'apple-vision',
        'imageSha256': imageSha256,
        'language': language,
        'rawLanguage': rawLanguage,
        'languageConfidence': languageConfidence,
        'recognitionLanguages': recognitionLanguages,
        'createdAt': createdAt.toIso8601String(),
        'lines': [for (final l in lines) l.toJson()],
      };

  static BoxTranscript? fromJson(Map<String, dynamic> json) {
    if (json['version'] != version) return null;
    final lines = <BoxReaderLine>[];
    for (final raw in (json['lines'] as List? ?? const [])) {
      final l = BoxReaderLine.fromJson(raw);
      if (l != null) lines.add(l);
    }
    final t = BoxTranscript(
      imageSha256: json['imageSha256']?.toString() ?? '',
      lines: lines,
      document: BoxTextLayout.group(lines),
      language: json['language'] as String?,
      languageConfidence: (json['languageConfidence'] as num?)?.toDouble() ?? 0,
      recognitionLanguages: [for (final l in (json['recognitionLanguages'] as List? ?? const [])) l.toString()],
      createdAt: DateTime.tryParse(json['createdAt']?.toString() ?? '') ?? DateTime.now(),
      fromCache: true,
    );
    t.rawLanguage = json['rawLanguage'] as String?;
    return t;
  }
}

/// A translation of a transcript into one NeoStation language.
class BoxTranslation {
  BoxTranslation({required this.target, required this.units, this.source, this.fromCache = false});
  final String target;
  final List<String> units;
  final String? source;
  final bool fromCache;
}

/// Reads and translates the back of a box on the device, with a cache.
///
/// Cache: `Application Support/NeoStation/BoxText/<scan SHA-256>/` keeps the
/// recognised lines (`transcript.json`) and one file per target language
/// (`<code>.json`), so a later reading, or a reading offline, reuses them.
/// The scan itself stays the source; nothing is uploaded.
class BoxTextService {
  BoxTextService._();

  static final _log = LoggerService.instance;
  static String? _rootOverride;

  /// Tests point the cache at a temporary folder.
  static set rootForTesting(String? path) => _rootOverride = path;

  static Future<Directory> _root() async {
    if (_rootOverride != null) return Directory(_rootOverride!);
    final support = await getApplicationSupportDirectory();
    return Directory(p.join(support.path, 'NeoStation', 'BoxText'));
  }

  static Future<String> sha256Of(String path) => Isolate.run(() async {
        final digest = await sha256.bind(File(path).openRead()).first;
        return digest.toString();
      });

  static Future<Directory> _dirFor(String sha) async => Directory(p.join((await _root()).path, sha));

  /// Cached transcript of the scan at [path], or a new recognition.
  ///
  /// [scanRegion] (ScreenScraper code) gives Vision its language hints.
  static Future<BoxTranscript> transcript(String path, {String? scanRegion}) async {
    final sha = await sha256Of(path);
    final dir = await _dirFor(sha);
    final file = File(p.join(dir.path, 'transcript.json'));
    try {
      if (await file.exists()) {
        final cached = BoxTranscript.fromJson(jsonDecode(await file.readAsString()) as Map<String, dynamic>);
        if (cached != null && cached.imageSha256 == sha) return cached;
      }
    } catch (_) {
      // A damaged cache file is replaced by a new recognition.
    }
    final recognition = await NeoBoxReader.recognize(
      path,
      languages: GameBoxRegions.recognitionHints(scanRegion),
    );
    final document = BoxTextLayout.group(recognition.lines);
    String? raw;
    var confidence = 0.0;
    if (!document.isEmpty) {
      try {
        final (lang, p) = await NeoBoxReader.detectLanguage(document.plainText);
        raw = lang;
        confidence = p;
      } catch (_) {}
    }
    final transcript = BoxTranscript(
      imageSha256: sha,
      lines: recognition.lines,
      document: document,
      language: NeoBoxReader.appCodeOf(raw),
      languageConfidence: confidence,
      recognitionLanguages: recognition.languages,
      createdAt: DateTime.now().toUtc(),
    )..rawLanguage = raw;
    try {
      await dir.create(recursive: true);
      await _writeAtomic(file, jsonEncode(transcript.toJson()));
    } catch (e) {
      _log.w('[GameBox] transcript cache not written: $e');
    }
    return transcript;
  }

  /// Translation of [transcript] into [target] (NeoStation code), cached.
  static Future<BoxTranslation> translate(BoxTranscript transcript, String target) async {
    final dir = await _dirFor(transcript.imageSha256);
    final file = File(p.join(dir.path, '${_safe(target)}.json'));
    final units = transcript.document.units;
    try {
      if (await file.exists()) {
        final json = jsonDecode(await file.readAsString()) as Map<String, dynamic>;
        final cached = (json['units'] as List?)?.map((e) => e.toString()).toList();
        if (json['version'] == 1 && cached != null && cached.length == units.length &&
            json['sourceUnits'] is List && _same(json['sourceUnits'] as List, units)) {
          return BoxTranslation(target: target, units: cached, source: json['source'] as String?, fromCache: true);
        }
      }
    } catch (_) {}
    final appleTarget = NeoBoxReader.appleLanguages[target] ?? target;
    final source = transcript.languageConfidence >= 0.5 ? transcript.rawLanguage : null;
    final (translated, detected) = await NeoBoxReader.translate(units, source: source, target: appleTarget);
    final result = BoxTranslation(target: target, units: translated, source: detected ?? source);
    try {
      await dir.create(recursive: true);
      await _writeAtomic(file, jsonEncode({
        'version': 1,
        'engine': 'apple-translation',
        'target': target,
        'source': result.source,
        'sourceUnits': units,
        'units': translated,
      }));
    } catch (e) {
      _log.w('[GameBox] translation cache not written: $e');
    }
    return result;
  }

  static bool _same(List a, List<String> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i].toString() != b[i]) return false;
    }
    return true;
  }

  static String _safe(String s) => s.replaceAll(RegExp(r'[^A-Za-z0-9_]'), '_');

  static Future<void> _writeAtomic(File file, String content) async {
    final temp = File('${file.path}.part');
    await temp.writeAsString(content, flush: true);
    await temp.rename(file.path);
  }
}
