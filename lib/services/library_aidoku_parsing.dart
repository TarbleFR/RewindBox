import 'dart:convert';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:html/dom.dart';

import 'library_manga_models.dart';

/// Bodies larger than this are decoded and parsed on a worker isolate so a
/// 400-800 KB page never blocks the UI isolate.
const int libraryAidokuIsolateThreshold = 48 * 1024;

/// Decodes [body] as UTF-8 and runs [parser] on it, on a worker isolate when
/// the body exceeds [libraryAidokuIsolateThreshold].
///
/// [parser] must be a top-level or static function and [input] plain data:
/// both are sent to the worker. The result must be plain data too
/// (package:html documents never leave the parsing isolate).
Future<R> libraryAidokuParse<I, R>(
  Uint8List body,
  I input,
  R Function(String body, I input) parser, {
  int threshold = libraryAidokuIsolateThreshold,
}) {
  if (body.length <= threshold) {
    return Future<R>.sync(() => parser(_decodeBody(body), input));
  }
  return Isolate.run<R>(
    () => parser(_decodeBody(body), input),
    debugName: 'library-aidoku-parse',
  );
}

String _decodeBody(Uint8List body) => utf8.decode(body, allowMalformed: true);

/// Text and URL helpers shared by the site parsers.
abstract final class LibraryAidokuText {
  static final RegExp _spaces = RegExp(r'\s+');

  /// Whitespace-collapsed, trimmed text of [element] ('' for null).
  static String of(Element? element) =>
      element == null ? '' : clean(element.text);

  static String clean(String value) =>
      value.replaceAll(' ', ' ').replaceAll(_spaces, ' ').trim();

  /// Text of [element] without the descendants matching [selector] (badges
  /// such as "HOT"/"NEW" inside a title link).
  static String without(Element element, String selector) {
    if (element.querySelector(selector) == null) return of(element);
    final copy = element.clone(true);
    for (final excluded in copy.querySelectorAll(selector)) {
      excluded.remove();
    }
    return of(copy);
  }

  /// Paragraph texts of [container] joined by a blank line, or its text when
  /// it has no paragraph.
  static String paragraphs(Element? container) {
    if (container == null) return '';
    final parts = container
        .querySelectorAll('p')
        .map(of)
        .where((text) => text.isNotEmpty)
        .toList();
    if (parts.isEmpty) return of(container);
    return parts.join('\n\n');
  }

  /// Absolute https URL for [raw] resolved against [base], or null for an
  /// empty, `data:`, non-http(s) or host-less value. `http:` is upgraded
  /// (iOS App Transport Security), escaped slashes and surrounding
  /// whitespace are removed, invalid characters are percent-encoded.
  static String? absoluteUrl(String? raw, Uri base) {
    var value = (raw ?? '').replaceAll(r'\/', '/').trim();
    if (value.isEmpty || value.startsWith('data:') || value.startsWith('#')) {
      return null;
    }
    if (value.startsWith('//')) value = 'https:$value';
    Uri? parsed;
    try {
      parsed = Uri.parse(value);
      if (!parsed.hasScheme) parsed = base.resolveUri(parsed);
    } on FormatException {
      return null;
    }
    if (parsed.scheme == 'http') parsed = parsed.replace(scheme: 'https');
    if (parsed.scheme != 'https' || parsed.host.isEmpty) return null;
    return parsed.toString();
  }

  static final RegExp _resize = RegExp(r'[?&]resize=\d+,\d+$');

  /// Image URL of [image] following the attribute priority used by the
  /// Madara and MangaThemesia templates; placeholders are skipped.
  static String? imageUrl(
    Element? image,
    Uri base, {
    List<String> attributes = const <String>[
      'data-src',
      'data-lazy-src',
      'src',
      'srcset',
      'data-cfsrc',
    ],
  }) {
    if (image == null) return null;
    for (final attribute in attributes) {
      var value = image.attributes[attribute]?.trim() ?? '';
      if (value.isEmpty) continue;
      if (attribute.endsWith('srcset')) {
        value = value.split(',').first.trim().split(RegExp(r'\s+')).first;
      }
      if (_isPlaceholder(value)) continue;
      final resolved = absoluteUrl(value.replaceFirst(_resize, ''), base);
      if (resolved != null) return resolved;
    }
    return null;
  }

  static bool _isPlaceholder(String value) {
    final lower = value.toLowerCase();
    return lower.startsWith('data:') ||
        lower.contains('dflazy') ||
        lower.endsWith('readerarea.svg') ||
        lower.contains('/lazy.') ||
        lower.endsWith('blank.gif');
  }

  /// Path segment following [segment] in [url] (e.g. the manga slug after
  /// `/oeuvre/`), or null.
  static String? segmentAfter(String url, String segment) {
    final uri = Uri.tryParse(url);
    if (uri == null) return null;
    final parts = uri.pathSegments.where((part) => part.isNotEmpty).toList();
    final index = parts.indexOf(segment);
    if (index < 0 || index + 1 >= parts.length) return null;
    return parts[index + 1];
  }

  /// Last non-empty path segment of [url], or null.
  static String? lastSegment(String url) {
    final uri = Uri.tryParse(url);
    if (uri == null) return null;
    final parts = uri.pathSegments.where((part) => part.isNotEmpty).toList();
    return parts.isEmpty ? null : parts.last;
  }

  /// Path of [url] after `/[segment]/`, keeping the trailing slash
  /// (`826-solo-leveling/chapitre-200/`).
  static String? pathAfter(String url, String segment) {
    final uri = Uri.tryParse(url);
    if (uri == null) return null;
    final marker = '/$segment/';
    final index = uri.path.indexOf(marker);
    if (index < 0) return null;
    final rest = uri.path.substring(index + marker.length);
    if (rest.isEmpty) return null;
    try {
      return Uri.decodeComponent(rest);
    } on ArgumentError {
      return rest;
    }
  }

  static final RegExp _number = RegExp(r'(\d+(?:[.,]\d+)?)');
  static final RegExp _chapterLabel = RegExp(
    r'(?:chap(?:itre|ter)?|ch|episode|[ée]pisode|ep)\.?\s*(\d+(?:[.,]\d+)?)',
    caseSensitive: false,
  );
  static final RegExp _volumeLabel = RegExp(
    r'^\s*(?:volume|tome|vol)\.?\s*(\d+(?:[.,]\d+)?)',
    caseSensitive: false,
  );

  static double? firstNumber(String value) {
    final match = _number.firstMatch(value);
    return match == null ? null : _toDouble(match.group(1)!);
  }

  /// Number following "Chapitre"/"Chapter"/"Ch." in [label].
  static double? chapterNumberInLabel(String label) {
    final match = _chapterLabel.firstMatch(label);
    return match == null ? null : _toDouble(match.group(1)!);
  }

  /// Number of a "Volume N"/"Tome N" label, or null for chapters.
  static double? volumeNumberInLabel(String label) {
    final match = _volumeLabel.firstMatch(label);
    return match == null ? null : _toDouble(match.group(1)!);
  }

  static double? _toDouble(String value) =>
      double.tryParse(value.replaceAll(',', '.'));

  /// Status from a site label (French or English).
  static LibraryMangaStatus status(String raw) {
    final value = LibraryContentRating.normalizeLabel(raw);
    if (value.isEmpty) return LibraryMangaStatus.unknown;
    if (value.contains('pause') ||
        value.contains('hiatus') ||
        value.contains('on hold')) {
      return LibraryMangaStatus.hiatus;
    }
    if (value.contains('annul') ||
        value.contains('abandon') ||
        value.contains('cancel') ||
        value.contains('dropped')) {
      return LibraryMangaStatus.cancelled;
    }
    if (value.contains('termin') ||
        value.contains('complet') ||
        value.contains('fini') ||
        value == 'end' ||
        value.contains('acheve')) {
      return LibraryMangaStatus.completed;
    }
    if (value.contains('cours') ||
        value.contains('ongoing') ||
        value.contains('releasing') ||
        value.contains('publishing')) {
      return LibraryMangaStatus.ongoing;
    }
    return LibraryMangaStatus.unknown;
  }

  /// Reading mode from the site type label, then from genres.
  static LibraryReadingMode readingMode(
    String typeLabel,
    Iterable<String> genres,
  ) {
    LibraryReadingMode? fromLabel(String raw) {
      final value = LibraryContentRating.normalizeLabel(raw);
      if (value.isEmpty) return null;
      if (value.contains('manhwa') ||
          value.contains('manhua') ||
          value.contains('webtoon') ||
          value.contains('vertical') ||
          value.contains('korean') ||
          value.contains('chinese')) {
        return LibraryReadingMode.vertical;
      }
      if (value.contains('comic') ||
          value == 'bd' ||
          value.contains('bande dessinee')) {
        return LibraryReadingMode.leftToRight;
      }
      if (value.contains('manga') || value.contains('japan')) {
        return LibraryReadingMode.rightToLeft;
      }
      return null;
    }

    final direct = fromLabel(typeLabel);
    if (direct != null) return direct;
    for (final genre in genres) {
      final mode = fromLabel(genre);
      if (mode == LibraryReadingMode.vertical) return mode!;
    }
    return LibraryReadingMode.unknown;
  }

  /// Extracts the JSON object passed to `ts_reader.run(...)` in a
  /// MangaThemesia chapter page, or null.
  static Map<String, dynamic>? tsReaderConfig(String html) {
    final call = html.indexOf('ts_reader.run(');
    if (call < 0) return null;
    final start = html.indexOf('{', call);
    if (start < 0) return null;
    var depth = 0;
    var inString = false;
    var escaped = false;
    for (var i = start; i < html.length; i++) {
      final char = html.codeUnitAt(i);
      if (inString) {
        if (escaped) {
          escaped = false;
        } else if (char == 0x5c) {
          escaped = true;
        } else if (char == 0x22) {
          inString = false;
        }
        continue;
      }
      if (char == 0x22) {
        inString = true;
      } else if (char == 0x7b) {
        depth++;
      } else if (char == 0x7d) {
        depth--;
        if (depth == 0) {
          try {
            final decoded = jsonDecode(html.substring(start, i + 1));
            return decoded is Map<String, dynamic> ? decoded : null;
          } on FormatException {
            return null;
          }
        }
      }
    }
    return null;
  }
}

/// Date parsing for the French sources (absolute French/English dates,
/// numeric dates and relative "il y a 2 jours" / "2 hours ago").
abstract final class LibraryAidokuDates {
  static const Map<String, int> _months = <String, int>{
    'janvier': 1,
    'janv': 1,
    'jan': 1,
    'january': 1,
    'fevrier': 2,
    'fevr': 2,
    'fev': 2,
    'february': 2,
    'feb': 2,
    'mars': 3,
    'march': 3,
    'mar': 3,
    'avril': 4,
    'avr': 4,
    'april': 4,
    'apr': 4,
    'mai': 5,
    'may': 5,
    'juin': 6,
    'june': 6,
    'jun': 6,
    'juillet': 7,
    'juil': 7,
    'july': 7,
    'jul': 7,
    'aout': 8,
    'august': 8,
    'aug': 8,
    'septembre': 9,
    'sept': 9,
    'september': 9,
    'sep': 9,
    'octobre': 10,
    'oct': 10,
    'october': 10,
    'novembre': 11,
    'nov': 11,
    'november': 11,
    'decembre': 12,
    'dec': 12,
    'december': 12,
  };

  static final RegExp _dayMonthYear = RegExp(
    r'^(\d{1,2})(?:er)?\s+([a-z]+)\.?,?\s+(\d{4})$',
  );
  static final RegExp _monthDayYear = RegExp(
    r'^([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$',
  );
  static final RegExp _numeric = RegExp(
    r'^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})$',
  );
  static final RegExp _iso = RegExp(r'^(\d{4})-(\d{2})-(\d{2})');
  static final RegExp _relative = RegExp(
    r'^(?:il y a\s+)?(\d+|un|une|a|an)\s+([a-z]+)\.?(?:\s+ago)?$',
  );

  /// Parses [raw]; relative dates are computed from [now]. Returns a UTC
  /// date (midnight for day-precision dates) or null.
  static DateTime? parse(String? raw, {required DateTime now}) {
    final value = LibraryContentRating.foldAccents(
      LibraryAidokuText.clean(raw ?? '').toLowerCase(),
    );
    if (value.isEmpty || value.contains('{{')) return null;

    final iso = _iso.firstMatch(value);
    if (iso != null) {
      return _date(
        int.parse(iso.group(1)!),
        int.parse(iso.group(2)!),
        int.parse(iso.group(3)!),
      );
    }

    final numeric = _numeric.firstMatch(value);
    if (numeric != null) {
      var year = int.parse(numeric.group(3)!);
      if (year < 100) year += 2000;
      return _date(
        year,
        int.parse(numeric.group(2)!),
        int.parse(numeric.group(1)!),
      );
    }

    final dayFirst = _dayMonthYear.firstMatch(value);
    if (dayFirst != null) {
      final month = _months[dayFirst.group(2)!];
      if (month != null) {
        return _date(
          int.parse(dayFirst.group(3)!),
          month,
          int.parse(dayFirst.group(1)!),
        );
      }
    }

    final monthFirst = _monthDayYear.firstMatch(value);
    if (monthFirst != null) {
      final month = _months[monthFirst.group(1)!];
      if (month != null) {
        return _date(
          int.parse(monthFirst.group(3)!),
          month,
          int.parse(monthFirst.group(2)!),
        );
      }
    }

    final relative = _relative.firstMatch(value);
    if (relative != null) {
      final amountText = relative.group(1)!;
      final amount = int.tryParse(amountText) ?? 1;
      final unit = _relativeUnit(relative.group(2)!);
      if (unit != null) return now.toUtc().subtract(unit * amount);
    }
    return null;
  }

  static Duration? _relativeUnit(String unit) {
    switch (unit) {
      case 's':
      case 'sec':
      case 'seconde':
      case 'secondes':
      case 'second':
      case 'seconds':
        return const Duration(seconds: 1);
      case 'min':
      case 'mins':
      case 'minute':
      case 'minutes':
        return const Duration(minutes: 1);
      case 'h':
      case 'heure':
      case 'heures':
      case 'hour':
      case 'hours':
      case 'hr':
      case 'hrs':
        return const Duration(hours: 1);
      case 'j':
      case 'jour':
      case 'jours':
      case 'd':
      case 'day':
      case 'days':
        return const Duration(days: 1);
      case 'sem':
      case 'semaine':
      case 'semaines':
      case 'w':
      case 'week':
      case 'weeks':
        return const Duration(days: 7);
      case 'mois':
      case 'month':
      case 'months':
        return const Duration(days: 30);
      case 'an':
      case 'ans':
      case 'annee':
      case 'annees':
      case 'y':
      case 'year':
      case 'years':
        return const Duration(days: 365);
    }
    return null;
  }

  static DateTime? _date(int year, int month, int day) {
    if (year < 1970 || year > 2200 || month < 1 || month > 12) return null;
    if (day < 1 || day > 31) return null;
    final date = DateTime.utc(year, month, day);
    return date.month == month ? date : null;
  }
}
