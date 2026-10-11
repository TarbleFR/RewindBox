import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_reader_palette.dart';

/// A displayed piece of a block: blocks longer than [libraryReflowMaxUnit]
/// characters are cut at a line or word boundary so one widget never lays
/// out an unbounded text (a TXT file without line breaks, a huge
/// preformatted block). Offsets are characters of the block.
@immutable
class LibraryReflowUnit {
  const LibraryReflowUnit({
    required this.chapter,
    required this.block,
    required this.start,
    required this.end,
    required this.source,
    required this.spans,
  });

  final int chapter;
  final int block;
  final int start;
  final int end;
  final LibraryTextBlock source;

  /// Spans of [source] restricted to [start]..[end].
  final List<LibraryTextSpan> spans;

  bool get isFirstPiece => start == 0;

  bool get isLastPiece => end >= source.characterCount;

  int get length => end - start;
}

/// Target size of a display unit.
const int libraryReflowMaxUnit = 2000;

/// Splits the [blocks] of [chapter] into display units.
List<LibraryReflowUnit> libraryReflowUnits(
  int chapter,
  List<LibraryTextBlock> blocks, {
  int maxUnit = libraryReflowMaxUnit,
}) {
  final units = <LibraryReflowUnit>[];
  for (var index = 0; index < blocks.length; index++) {
    final block = blocks[index];
    final length = block.characterCount;
    final splittable =
        block.kind != LibraryTextBlockKind.image &&
        block.kind != LibraryTextBlockKind.rule &&
        length > maxUnit + maxUnit ~/ 2;
    if (!splittable) {
      units.add(
        LibraryReflowUnit(
          chapter: chapter,
          block: index,
          start: 0,
          end: length,
          source: block,
          spans: block.spans,
        ),
      );
      continue;
    }
    final text = block.text;
    var start = 0;
    while (start < length) {
      var end = length;
      if (length - start > maxUnit + maxUnit ~/ 2) {
        end = _breakAfter(text, start + maxUnit, maxUnit ~/ 2);
      }
      units.add(
        LibraryReflowUnit(
          chapter: chapter,
          block: index,
          start: start,
          end: end,
          source: block,
          spans: librarySliceSpans(block.spans, start, end),
        ),
      );
      start = end;
    }
  }
  return units;
}

/// First line break (else space) at or after [from] within [window]
/// characters; the cut happens after it.
int _breakAfter(String text, int from, int window) {
  final limit = (from + window).clamp(0, text.length);
  final newline = text.indexOf('\n', from);
  if (newline >= 0 && newline < limit) return newline + 1;
  final space = text.indexOf(' ', from);
  if (space >= 0 && space < limit) return space + 1;
  return from.clamp(1, text.length);
}

/// The parts of [spans] between characters [start] and [end].
List<LibraryTextSpan> librarySliceSpans(
  List<LibraryTextSpan> spans,
  int start,
  int end,
) {
  final result = <LibraryTextSpan>[];
  var offset = 0;
  for (final span in spans) {
    final spanStart = offset;
    final spanEnd = offset + span.text.length;
    offset = spanEnd;
    if (spanEnd <= start) continue;
    if (spanStart >= end) break;
    final from = (start - spanStart).clamp(0, span.text.length);
    final to = (end - spanStart).clamp(0, span.text.length);
    if (to > from) {
      result.add(
        from == 0 && to == span.text.length
            ? span
            : span.withText(span.text.substring(from, to)),
      );
    }
  }
  return result;
}

/// Typography of the reflowable reader.
@immutable
class LibraryReflowStyle {
  const LibraryReflowStyle({
    required this.palette,
    required this.fontSize,
    required this.lineHeight,
    required this.fontFamily,
    required this.justify,
    required this.margin,
  });

  factory LibraryReflowStyle.of(
    LibraryReaderSettings settings,
    LibraryReaderPalette palette,
  ) => LibraryReflowStyle(
    palette: palette,
    fontSize: settings.fontSize,
    lineHeight: settings.lineHeight,
    fontFamily: settings.fontFamily,
    justify: settings.justify,
    margin: settings.margin,
  );

  final LibraryReaderPalette palette;
  final double fontSize;
  final double lineHeight;
  final LibraryReaderFontFamily fontFamily;
  final bool justify;

  /// Horizontal margin in logical pixels (added to the safe area).
  final double margin;

  TextStyle get base => TextStyle(
    color: palette.text,
    fontSize: fontSize,
    height: lineHeight,
    fontFamily: LibraryReaderFonts.familyFor(fontFamily),
    fontFamilyFallback: LibraryReaderFonts.fallbackFor(fontFamily),
  );

  @override
  bool operator ==(Object other) =>
      other is LibraryReflowStyle &&
      other.palette == palette &&
      other.fontSize == fontSize &&
      other.lineHeight == lineHeight &&
      other.fontFamily == fontFamily &&
      other.justify == justify &&
      other.margin == margin;

  @override
  int get hashCode =>
      Object.hash(palette, fontSize, lineHeight, fontFamily, justify, margin);
}

/// Units currently built by the scroll view, to find the reading position.
class LibraryReflowUnitRegistry {
  final Set<LibraryReflowUnitViewState> _views = <LibraryReflowUnitViewState>{};

  Iterable<LibraryReflowUnitViewState> get views => _views;

  LibraryReflowUnitViewState? find(int chapter, int unitIndex) {
    for (final view in _views) {
      if (view.widget.chapter == chapter &&
          view.widget.unitIndex == unitIndex) {
        return view;
      }
    }
    return null;
  }
}

/// Loads the bytes of a book image.
typedef LibraryReflowImageLoader = Future<Uint8List> Function(String href);

/// One display unit: a paragraph (or part of one), heading, quote, list
/// item, preformatted block, rule or image.
class LibraryReflowUnitView extends StatefulWidget {
  const LibraryReflowUnitView({
    super.key,
    required this.unit,
    required this.chapter,
    required this.unitIndex,
    required this.style,
    required this.horizontalPadding,
    required this.registry,
    required this.onLink,
    required this.loadImage,
    required this.maxImageHeight,
  });

  final LibraryReflowUnit unit;
  final int chapter;
  final int unitIndex;
  final LibraryReflowStyle style;
  final EdgeInsets horizontalPadding;
  final LibraryReflowUnitRegistry registry;
  final ValueChanged<String> onLink;
  final LibraryReflowImageLoader loadImage;
  final double maxImageHeight;

  @override
  State<LibraryReflowUnitView> createState() => LibraryReflowUnitViewState();
}

class LibraryReflowUnitViewState extends State<LibraryReflowUnitView> {
  final GlobalKey _textKey = GlobalKey();
  final List<TapGestureRecognizer> _recognizers = <TapGestureRecognizer>[];

  LibraryReflowUnit get unit => widget.unit;

  @override
  void initState() {
    super.initState();
    widget.registry._views.add(this);
  }

  @override
  void didUpdateWidget(covariant LibraryReflowUnitView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.registry, widget.registry)) {
      oldWidget.registry._views.remove(this);
      widget.registry._views.add(this);
    }
  }

  @override
  void dispose() {
    widget.registry._views.remove(this);
    _disposeRecognizers();
    super.dispose();
  }

  void _disposeRecognizers() {
    for (final recognizer in _recognizers) {
      recognizer.dispose();
    }
    _recognizers.clear();
  }

  RenderBox? get box {
    final object = context.findRenderObject();
    return object is RenderBox && object.attached && object.hasSize
        ? object
        : null;
  }

  RenderParagraph? get _paragraph {
    final object = _textKey.currentContext?.findRenderObject();
    return object is RenderParagraph && object.attached && object.hasSize
        ? object
        : null;
  }

  /// Character offset (in the unit) of the line at [localY] of this unit.
  int offsetAt(double localY) {
    final box = this.box;
    final paragraph = _paragraph;
    if (box == null || paragraph == null) return 0;
    final top = paragraph.localToGlobal(Offset.zero, ancestor: box).dy;
    final maxY = paragraph.size.height - 1;
    final y = localY - top;
    if (y <= 0 || maxY <= 0) return 0;
    if (y > maxY) return unit.length;
    final position = paragraph.getPositionForOffset(Offset(1, y));
    return position.offset.clamp(0, unit.length);
  }

  /// Top of the line holding character [offset] (in the unit), relative to
  /// the unit's box; null before layout.
  double? caretTop(int offset) {
    final box = this.box;
    final paragraph = _paragraph;
    if (box == null) return null;
    if (paragraph == null || offset <= 0) return 0;
    final top = paragraph.localToGlobal(Offset.zero, ancestor: box).dy;
    final caret = paragraph.getOffsetForCaret(
      TextPosition(offset: offset.clamp(0, unit.length)),
      Rect.zero,
    );
    return top + caret.dy;
  }

  InlineSpan _span(LibraryTextSpan span, TextStyle style) {
    var effective = style;
    if (span.bold) effective = effective.copyWith(fontWeight: FontWeight.w700);
    if (span.italic) {
      effective = effective.copyWith(fontStyle: FontStyle.italic);
    }
    if (span.monospace) {
      effective = effective.copyWith(
        fontFamily: LibraryReaderFonts.monospace,
        fontFamilyFallback: LibraryReaderFonts.monospaceFallback,
        fontSize: (effective.fontSize ?? 16) * 0.9,
      );
    }
    if (span.superscript || span.subscript) {
      effective = effective.copyWith(
        fontFeatures: <FontFeature>[
          span.superscript
              ? const FontFeature.superscripts()
              : const FontFeature.subscripts(),
        ],
      );
    }
    final href = span.href;
    TapGestureRecognizer? recognizer;
    if (href != null && href.isNotEmpty) {
      recognizer = TapGestureRecognizer()..onTap = () => widget.onLink(href);
      _recognizers.add(recognizer);
      effective = effective.copyWith(
        color: widget.style.palette.link,
        decoration: TextDecoration.underline,
        decorationColor: widget.style.palette.link,
      );
    } else if (span.underline) {
      effective = effective.copyWith(decoration: TextDecoration.underline);
    }
    return TextSpan(text: span.text, style: effective, recognizer: recognizer);
  }

  Widget _text(TextStyle style, TextAlign align) {
    _disposeRecognizers();
    return RichText(
      key: _textKey,
      textAlign: align,
      textScaler: TextScaler.noScaling,
      text: TextSpan(
        style: style,
        children: <InlineSpan>[
          for (final span in unit.spans) _span(span, style),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final style = widget.style;
    final palette = style.palette;
    final base = style.base;
    final block = unit.source;
    final em = style.fontSize;
    final padding = widget.horizontalPadding;
    final paragraphAlign = block.alignCenter
        ? TextAlign.center
        : (style.justify ? TextAlign.justify : TextAlign.start);
    final bottom = unit.isLastPiece ? em * 0.6 : 0.0;
    final indent = em * 1.2 * block.indent.clamp(0, 6);

    switch (block.kind) {
      case LibraryTextBlockKind.heading:
        final level = block.headingLevel.clamp(1, 6);
        const scales = <double>[1.6, 1.4, 1.25, 1.12, 1.05, 1.0];
        final heading = base.copyWith(
          fontSize: em * scales[level - 1],
          fontWeight: FontWeight.w700,
          height: 1.25,
        );
        return Padding(
          padding: padding.add(
            EdgeInsets.only(
              top: unit.isFirstPiece ? em * 1.1 : 0,
              bottom: unit.isLastPiece ? em * 0.5 : 0,
            ),
          ),
          child: Semantics(
            header: true,
            child: _text(
              heading,
              block.alignCenter ? TextAlign.center : TextAlign.start,
            ),
          ),
        );
      case LibraryTextBlockKind.quote:
        return Padding(
          padding: padding.add(EdgeInsets.only(left: indent, bottom: bottom)),
          child: Container(
            decoration: BoxDecoration(
              border: Border(
                left: BorderSide(color: palette.quoteBar, width: 3),
              ),
            ),
            padding: EdgeInsets.only(left: em * 0.8),
            child: _text(
              base.copyWith(color: palette.text.withValues(alpha: 0.9)),
              paragraphAlign,
            ),
          ),
        );
      case LibraryTextBlockKind.listItem:
        final marker = block.ordinal != null ? '${block.ordinal}.' : '•';
        return Padding(
          padding: padding.add(
            EdgeInsets.only(
              left: indent,
              bottom: unit.isLastPiece ? em * 0.3 : 0,
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              SizedBox(
                width: em * 1.6,
                child: unit.isFirstPiece
                    ? Text(
                        marker,
                        textScaler: TextScaler.noScaling,
                        style: base,
                      )
                    : null,
              ),
              Expanded(child: _text(base, TextAlign.start)),
            ],
          ),
        );
      case LibraryTextBlockKind.preformatted:
        return Padding(
          padding: padding.add(EdgeInsets.only(bottom: bottom)),
          child: Container(
            color: palette.codeBackground,
            padding: EdgeInsets.symmetric(horizontal: em * 0.5, vertical: 4),
            width: double.infinity,
            child: _text(
              base.copyWith(
                fontFamily: LibraryReaderFonts.monospace,
                fontFamilyFallback: LibraryReaderFonts.monospaceFallback,
                fontSize: em * 0.85,
                height: 1.35,
              ),
              TextAlign.start,
            ),
          ),
        );
      case LibraryTextBlockKind.rule:
        return Padding(
          padding: padding.add(EdgeInsets.symmetric(vertical: em * 0.8)),
          child: Center(
            child: SizedBox(
              width: 96,
              child: Divider(color: palette.divider, thickness: 1, height: 1),
            ),
          ),
        );
      case LibraryTextBlockKind.image:
        return Padding(
          padding: padding.add(EdgeInsets.symmetric(vertical: em * 0.5)),
          child: _ReflowImage(
            href: block.imageHref,
            alt: block.imageAlt,
            loadImage: widget.loadImage,
            maxHeight: widget.maxImageHeight,
            palette: palette,
          ),
        );
      case LibraryTextBlockKind.paragraph:
        return Padding(
          padding: padding.add(EdgeInsets.only(left: indent, bottom: bottom)),
          child: _text(base, paragraphAlign),
        );
    }
  }
}

class _ReflowImage extends StatefulWidget {
  const _ReflowImage({
    required this.href,
    required this.alt,
    required this.loadImage,
    required this.maxHeight,
    required this.palette,
  });

  final String? href;
  final String? alt;
  final LibraryReflowImageLoader loadImage;
  final double maxHeight;
  final LibraryReaderPalette palette;

  @override
  State<_ReflowImage> createState() => _ReflowImageState();
}

class _ReflowImageState extends State<_ReflowImage> {
  Future<Uint8List>? _bytes;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant _ReflowImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.href != widget.href) _load();
  }

  void _load() {
    final href = widget.href;
    _bytes = href == null || href.isEmpty ? null : widget.loadImage(href);
  }

  @override
  Widget build(BuildContext context) {
    final alt = widget.alt?.trim();
    final label = alt != null && alt.isNotEmpty
        ? alt
        : LibraryReaderLocale.text(context, 'image');
    final unavailable = Semantics(
      label: LibraryReaderLocale.text(context, 'imageUnavailable'),
      child: SizedBox(
        height: 48,
        child: Center(
          child: Icon(
            Icons.image_not_supported_outlined,
            color: widget.palette.secondaryText,
          ),
        ),
      ),
    );
    final bytes = _bytes;
    if (bytes == null) return unavailable;
    return LayoutBuilder(
      builder: (context, constraints) {
        final ratio = MediaQuery.devicePixelRatioOf(context);
        final decodeWidth = (constraints.maxWidth * ratio).ceil().clamp(
          64,
          2048,
        );
        return FutureBuilder<Uint8List>(
          future: bytes,
          builder: (context, snapshot) {
            if (snapshot.hasError) return unavailable;
            final data = snapshot.data;
            if (data == null) {
              return SizedBox(height: constraints.maxWidth * 0.5);
            }
            return Semantics(
              image: true,
              label: label,
              child: ConstrainedBox(
                constraints: BoxConstraints(maxHeight: widget.maxHeight),
                child: Image.memory(
                  data,
                  cacheWidth: decodeWidth,
                  fit: BoxFit.contain,
                  gaplessPlayback: true,
                  errorBuilder: (_, _, _) => unavailable,
                ),
              ),
            );
          },
        );
      },
    );
  }
}

/// Keeps the bytes of the last book images requested.
class LibraryReflowImageCache {
  LibraryReflowImageCache(this._load, {this.capacity = 24});

  final LibraryReflowImageLoader _load;
  final int capacity;
  final Map<String, Future<Uint8List>> _entries = <String, Future<Uint8List>>{};

  Future<Uint8List> load(String href) {
    final cached = _entries.remove(href);
    if (cached != null) {
      _entries[href] = cached;
      return cached;
    }
    final future = _load(href);
    _entries[href] = future;
    future.then<void>((_) {}, onError: (Object _) => _entries.remove(href));
    while (_entries.length > capacity) {
      _entries.remove(_entries.keys.first);
    }
    return future;
  }

  void clear() => _entries.clear();
}
