import 'dart:math' as math;

import 'package:neo_box_reader/neo_box_reader.dart';

enum BoxTextBlockKind { heading, paragraph, list, legal }

/// A section of the back as printed: a heading, a paragraph, a bullet list
/// or the small legal print.
class BoxTextBlock {
  BoxTextBlock({
    required this.kind,
    required this.units,
    required this.lowConfidence,
    required this.left,
    required this.top,
    required this.right,
    required this.bottom,
  });

  final BoxTextBlockKind kind;

  /// Texts translated one by one: the paragraph, or each list item.
  final List<String> units;
  final bool lowConfidence;
  final double left, top, right, bottom;

  Map<String, dynamic> toJson() => {
        'kind': kind.name,
        'units': units,
        'lowConfidence': lowConfidence,
        'box': [left, top, right, bottom],
      };

  static BoxTextBlock? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final kind = BoxTextBlockKind.values.where((k) => k.name == raw['kind']).firstOrNull;
    final units = raw['units'];
    final box = raw['box'];
    if (kind == null || units is! List || box is! List || box.length != 4) return null;
    double d(Object? v) => v is num ? v.toDouble() : 0;
    return BoxTextBlock(
      kind: kind,
      units: [for (final u in units) u.toString()],
      lowConfidence: raw['lowConfidence'] == true,
      left: d(box[0]),
      top: d(box[1]),
      right: d(box[2]),
      bottom: d(box[3]),
    );
  }
}

/// Result of [BoxTextLayout.group].
class BoxTextDocument {
  BoxTextDocument({required this.blocks, required this.illegibleLines});
  final List<BoxTextBlock> blocks;

  /// Lines Vision saw but could not read with any confidence; they are
  /// reported, never reconstructed.
  final int illegibleLines;

  bool get isEmpty => blocks.isEmpty;
  bool get hasLowConfidence => blocks.any((b) => b.lowConfidence);

  /// Every unit, in reading order (the translation request).
  List<String> get units => [for (final b in blocks) ...b.units];

  String get plainText => blocks.map((b) => b.units.join('\n')).join('\n\n');
}

/// Turns recognised lines into the sections of the back, in reading order.
///
/// Only the recognised text is used; columns are separated by their
/// horizontal extent, sections by line gaps and size changes. Lines with too
/// little confidence are counted as illegible and left out.
class BoxTextLayout {
  BoxTextLayout._();

  static const double minConfidence = 0.15;
  static const double weakConfidence = 0.5;

  static final RegExp _letterOrDigit = RegExp(r'[\p{L}\p{N}]', unicode: true);
  static final RegExp _cjk = RegExp(r'[぀-ヿ㐀-鿿가-힯豈-﫿]');
  static final RegExp _bullet = RegExp(r'^\s*([•・●■□◆◇▶►▸‣∙·○\-–—*]|\d{1,2}[.)])\s*');
  static final RegExp _legal = RegExp(
    r'(©|®|™|\(c\)|all rights reserved|tous droits réservés|licensed|alle rechte|todos los derechos|'
    r'tutti i diritti|무단|禁止|版权|版權|著作権|права защищены)',
    caseSensitive: false,
  );

  static BoxTextDocument group(List<BoxReaderLine> raw) {
    var illegible = 0;
    final lines = <BoxReaderLine>[];
    for (final l in raw) {
      if (!_letterOrDigit.hasMatch(l.text)) continue;
      if (l.confidence < minConfidence) {
        illegible++;
        continue;
      }
      lines.add(l);
    }
    if (lines.isEmpty) return BoxTextDocument(blocks: const [], illegibleLines: illegible);

    final heights = lines.map((l) => l.height).toList()..sort();
    final median = heights[heights.length ~/ 2];
    lines.sort((a, b) => a.y.compareTo(b.y));

    final groups = <List<BoxReaderLine>>[];
    for (final line in lines) {
      List<BoxReaderLine>? target;
      var bestGap = double.infinity;
      for (final g in groups) {
        final last = g.last;
        final gap = line.y - last.bottom;
        final h = math.max(line.height, last.height);
        if (gap < -h * 0.5 || gap > h * 0.95) continue;
        final ratio = line.height / last.height;
        if (ratio < 0.65 || ratio > 1.55) continue;
        if (!_sameColumn(line, last, median)) continue;
        if (gap < bestGap) {
          bestGap = gap;
          target = g;
        }
      }
      if (target == null) {
        groups.add([line]);
      } else {
        target.add(line);
      }
    }

    final blocks = groups.map((g) => _block(g, median)).toList();
    return BoxTextDocument(blocks: _readingOrder(blocks), illegibleLines: illegible);
  }

  static bool _sameColumn(BoxReaderLine a, BoxReaderLine b, double median) {
    final overlap = math.min(a.right, b.right) - math.max(a.x, b.x);
    final narrow = math.min(a.width, b.width);
    if (narrow > 0 && overlap >= narrow * 0.3) return true;
    // Left-aligned short lines (last line of a paragraph, list items).
    return (a.x - b.x).abs() <= median * 1.5;
  }

  static BoxTextBlock _block(List<BoxReaderLine> g, double median) {
    final left = g.map((l) => l.x).reduce(math.min);
    final top = g.map((l) => l.y).reduce(math.min);
    final right = g.map((l) => l.right).reduce(math.max);
    final bottom = g.map((l) => l.bottom).reduce(math.max);
    final weak = g.any((l) => l.confidence < weakConfidence);
    final avgHeight = g.map((l) => l.height).reduce((a, b) => a + b) / g.length;
    final joined = g.map((l) => l.text).join(' ');

    BoxTextBlockKind kind;
    final bullets = g.where((l) => _bullet.hasMatch(l.text)).length;
    if (_legal.hasMatch(joined) && avgHeight <= median * 1.05) {
      kind = BoxTextBlockKind.legal;
    } else if (g.length >= 2 && bullets * 2 >= g.length) {
      kind = BoxTextBlockKind.list;
    } else if (g.length <= 2 && avgHeight >= median * 1.35) {
      kind = BoxTextBlockKind.heading;
    } else {
      kind = BoxTextBlockKind.paragraph;
    }

    final units = <String>[];
    if (kind == BoxTextBlockKind.list) {
      for (final l in g) {
        if (_bullet.hasMatch(l.text) || units.isEmpty) {
          units.add(l.text.replaceFirst(_bullet, '').trim());
        } else {
          units[units.length - 1] = join(units.last, l.text);
        }
      }
    } else {
      var text = '';
      for (final l in g) {
        text = text.isEmpty ? l.text : join(text, l.text);
      }
      units.add(text);
    }
    return BoxTextBlock(
      kind: kind,
      units: units.where((u) => u.isNotEmpty).toList(),
      lowConfidence: weak,
      left: left,
      top: top,
      right: right,
      bottom: bottom,
    );
  }

  /// Joins two printed lines: no space between CJK lines, hyphenated words
  /// rejoined, one space otherwise.
  static String join(String a, String b) {
    final aa = a.trimRight(), bb = b.trimLeft();
    if (aa.isEmpty) return bb;
    if (bb.isEmpty) return aa;
    final lastA = aa.substring(aa.length - 1);
    final firstB = bb.substring(0, 1);
    if (_cjk.hasMatch(lastA) || _cjk.hasMatch(firstB)) return '$aa$bb';
    if (lastA == '-' && aa.length > 1 && RegExp(r'\p{Ll}', unicode: true).hasMatch(firstB)) {
      return '${aa.substring(0, aa.length - 1)}$bb';
    }
    return '$aa $bb';
  }

  /// Top to bottom; sections side by side (columns) left to right.
  static List<BoxTextBlock> _readingOrder(List<BoxTextBlock> blocks) {
    final sorted = [...blocks]..sort((a, b) => a.top.compareTo(b.top));
    final bands = <List<BoxTextBlock>>[];
    for (final b in sorted) {
      final band = bands.isEmpty ? null : bands.last;
      if (band != null) {
        final bandTop = band.map((x) => x.top).reduce(math.min);
        final bandBottom = band.map((x) => x.bottom).reduce(math.max);
        final overlap = math.min(bandBottom, b.bottom) - math.max(bandTop, b.top);
        final smaller = math.min(bandBottom - bandTop, b.bottom - b.top);
        if (smaller > 0 && overlap > smaller * 0.4) {
          band.add(b);
          continue;
        }
      }
      bands.add([b]);
    }
    int columnFirst(BoxTextBlock a, BoxTextBlock b) {
      if ((a.left - b.left).abs() < 0.05) return a.top.compareTo(b.top);
      return a.left.compareTo(b.left);
    }
    return [
      for (final band in bands) ...(band..sort(columnFirst)),
    ];
  }
}
