import 'package:flutter/material.dart';

import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_epub.dart';
import 'package:neostation/services/library_local_library_service.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_manga_models.dart';
import 'package:neostation/services/library_text_document.dart';

import 'library_pdf_reader_screen.dart';
import 'reader/library_book_reader_screen.dart';
import 'reader/library_page_reader_content.dart';
import 'reader/library_page_reader_screen.dart';
import 'reader/library_reflow_source.dart';

/// One online chapter to read, with the title it belongs to so the reader
/// can move to the previous/next chapter and record progress under
/// [LibraryMangaDetails.onlineKey].
class LibraryOnlineChapterSession {
  const LibraryOnlineChapterSession({
    required this.addon,
    required this.details,
    required this.chapter,
    this.startPage,
  });

  final LibraryAddon addon;
  final LibraryMangaDetails details;
  final LibraryMangaChapter chapter;

  /// Zero-based page to open; null resumes the saved position or starts at
  /// the first page.
  final int? startPage;
}

/// Single entry point used by the Library screens to open a reader.
///
/// Readers are pushed on the root navigator, so they stay open while the
/// Library tab underneath is rebuilt or replaced, and they depend on
/// nothing of the screen that opened them.
abstract final class LibraryReaderLauncher {
  /// Opens an imported book with the reader matching its format (EPUB/TXT
  /// reflowable reader, PDF reader, CBZ page reader) at its saved position.
  static Future<void> openLocalBook(
    BuildContext context,
    LibraryLocalBook book, {
    LibraryLocalLibraryService? service,
  }) async {
    final navigator = Navigator.of(context, rootNavigator: true);
    final library = service ?? LibraryLocalLibraryService.instance;
    // The book's absolute path needs the library roots.
    if (library.roots == null) await library.load();
    final reader = readerForLocalBook(book, library.absolutePath(book));
    await navigator.push<void>(MaterialPageRoute<void>(builder: (_) => reader));
  }

  /// The reader matching [book]'s format for the file at [path].
  @visibleForTesting
  static Widget readerForLocalBook(LibraryLocalBook book, String path) {
    final subtitle = book.authors.isEmpty ? null : book.authors.join(', ');
    return switch (book.format) {
      LibraryBookFormat.epub => LibraryBookReaderScreen(
        open: () async =>
            LibraryEpubReflowSource(await LibraryEpubDocument.open(path)),
        progressKey: book.readingKey,
        title: book.title,
        subtitle: subtitle,
      ),
      LibraryBookFormat.txt => LibraryBookReaderScreen(
        open: () async =>
            LibraryTextReflowSource(await LibraryTextDocument.open(path)),
        progressKey: book.readingKey,
        title: book.title,
        subtitle: subtitle,
      ),
      LibraryBookFormat.pdf => LibraryPdfReaderScreen(
        filePath: path,
        title: book.title,
        subtitle: subtitle,
        progressKey: book.readingKey,
      ),
      LibraryBookFormat.cbz => LibraryPageReaderScreen(
        content: LibraryArchiveReaderContent(
          path: path,
          title: book.title,
          subtitle: subtitle,
          progressKey: book.readingKey,
          rightToLeft: book.rightToLeft,
        ),
      ),
    };
  }

  /// Opens an online chapter in the page reader.
  static Future<void> openOnlineChapter(
    BuildContext context,
    LibraryOnlineChapterSession session,
  ) {
    return _push(
      context,
      LibraryPageReaderScreen(
        content: LibraryOnlineReaderContent(
          addon: session.addon,
          details: session.details,
          chapter: session.chapter,
          startPage: session.startPage,
        ),
      ),
    );
  }

  /// Opens a PDF that is not part of the local library index (e.g. a file
  /// just downloaded from a provider). [progressKey] enables resume.
  static Future<void> openPdf(
    BuildContext context, {
    required String path,
    required String title,
    String? progressKey,
  }) {
    return _push(
      context,
      LibraryPdfReaderScreen(
        filePath: path,
        title: title,
        progressKey: progressKey,
      ),
    );
  }

  static Future<void> _push(BuildContext context, Widget reader) {
    return Navigator.of(
      context,
      rootNavigator: true,
    ).push<void>(MaterialPageRoute<void>(builder: (_) => reader));
  }
}
