import 'dart:async';
import 'dart:convert';
import 'dart:isolate';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_text_document.dart';

import 'reader/library_book_reader_screen.dart';
import 'reader/library_page_reader_content.dart';
import 'reader/library_page_reader_screen.dart';
import 'reader/library_reflow_source.dart';

/// Reader for content already in memory: provider page URLs ([pages]) or
/// plain text ([text]).
///
/// Pages open in the page reader (paged or vertical, zoom, page slider),
/// text in the reflowable reader (font, theme, margins). Progress is kept
/// in [LibraryReadingStore] under [progressKey] (default derived from
/// [bookmarkId]); a bookmark saved by the former reader is used once when
/// nothing newer is stored.
class LibraryReaderScreen extends StatefulWidget {
  const LibraryReaderScreen({
    super.key,
    required this.title,
    this.subtitle = '',
    this.coverUrl,
    this.text,
    this.pages = const [],
    this.imageHeaders,
    this.bookmarkId,
    this.progressKey,
    this.store,
  });

  final String title;
  final String subtitle;
  final String? coverUrl;
  final String? text;
  final List<String> pages;
  final Map<String, String>? imageHeaders;

  /// Stable identity used to persist the reading position.
  /// When omitted, the reader derives one from the visible title/subtitle and content type.
  final String? bookmarkId;

  /// Key in [LibraryReadingStore]; defaults to `reader:<sha1 of identity>`.
  final String? progressKey;
  final LibraryReadingStore? store;

  bool get hasPages => pages.isNotEmpty;

  /// Identity of the content, as the former reader derived it.
  String get identity => bookmarkId?.trim().isNotEmpty == true
      ? bookmarkId!.trim()
      : '${hasPages ? 'pages' : 'text'}|$title|$subtitle';

  /// SHA-1 of [identity].
  String get digest => sha1.convert(utf8.encode(identity)).toString();

  /// Key of the position in [LibraryReadingStore].
  String get effectiveProgressKey => progressKey ?? 'reader:$digest';

  /// SharedPreferences key of the former reader's bookmark.
  String get legacyBookmarkKey => 'library_reader_bookmark_$digest';

  @override
  State<LibraryReaderScreen> createState() => _LibraryReaderScreenState();
}

class _LibraryReaderScreenState extends State<LibraryReaderScreen> {
  /// Above this length the text is split into paragraphs off the UI
  /// isolate.
  static const int _isolateThreshold = 200000;

  bool _ready = false;
  int? _legacyPage;
  double? _legacyFraction;

  @override
  void initState() {
    super.initState();
    unawaited(_readLegacyBookmark());
  }

  Future<void> _readLegacyBookmark() async {
    final store = widget.store ?? LibraryReadingStore.instance;
    try {
      await store.load();
      if (store.progressFor(widget.effectiveProgressKey) == null) {
        final preferences = await SharedPreferences.getInstance();
        final raw = preferences.getString(widget.legacyBookmarkKey);
        if (raw != null && raw.trim().isNotEmpty) {
          final decoded = jsonDecode(raw);
          if (decoded is Map) {
            final page = decoded['pageIndex'];
            final progress = decoded['progress'];
            if (page is num) _legacyPage = page.toInt();
            if (progress is num) {
              _legacyFraction = progress.toDouble().clamp(0.0, 1.0);
            }
          }
        }
      }
    } catch (_) {
      // A malformed former bookmark never blocks the reader.
    }
    if (mounted) setState(() => _ready = true);
  }

  Future<LibraryReflowSource> _openText() async {
    final text = widget.text ?? '';
    final document = text.length > _isolateThreshold
        ? await Isolate.run(() => LibraryTextDocument.fromText(text))
        : LibraryTextDocument.fromText(text);
    return LibraryTextReflowSource(document);
  }

  @override
  Widget build(BuildContext context) {
    if (!_ready) {
      return const Scaffold(backgroundColor: Colors.black);
    }
    if (widget.hasPages) {
      final legacyPage = _legacyPage;
      return LibraryPageReaderScreen(
        store: widget.store,
        content: LibraryUrlReaderContent(
          urls: widget.pages,
          headers: widget.imageHeaders ?? const <String, String>{},
          title: widget.title,
          subtitle: widget.subtitle.isEmpty ? null : widget.subtitle,
          coverUrl: widget.coverUrl,
          progressKey: widget.effectiveProgressKey,
          startPage: legacyPage == null || legacyPage < 0
              ? null
              : legacyPage.clamp(0, widget.pages.length - 1),
        ),
      );
    }
    return LibraryBookReaderScreen(
      store: widget.store,
      open: _openText,
      progressKey: widget.effectiveProgressKey,
      title: widget.title,
      subtitle: widget.subtitle.isEmpty ? null : widget.subtitle,
      coverUrl: widget.coverUrl,
      initialFraction: _legacyFraction,
    );
  }
}
