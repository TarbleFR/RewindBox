import 'package:flutter/widgets.dart';

import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_manga_models.dart';

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
/// Contract stub: the readers implement these in Build 437 wave 2.
abstract final class LibraryReaderLauncher {
  /// Opens an imported book with the reader matching its format (EPUB/TXT
  /// reflowable reader, PDF reader, CBZ page reader) at its saved position.
  static Future<void> openLocalBook(BuildContext context, LibraryLocalBook book) =>
      throw UnimplementedError('LibraryReaderLauncher.openLocalBook');

  /// Opens an online chapter in the page reader.
  static Future<void> openOnlineChapter(
    BuildContext context,
    LibraryOnlineChapterSession session,
  ) => throw UnimplementedError('LibraryReaderLauncher.openOnlineChapter');

  /// Opens a PDF that is not part of the local library index (e.g. a file
  /// just downloaded from a provider). [progressKey] enables resume.
  static Future<void> openPdf(
    BuildContext context, {
    required String path,
    required String title,
    String? progressKey,
  }) => throw UnimplementedError('LibraryReaderLauncher.openPdf');
}
