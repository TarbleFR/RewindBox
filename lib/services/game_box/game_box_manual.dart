import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:pdfrx/pdfrx.dart';

/// First page of a local PDF manual, drawn small for the booklet in the box.
class GameBoxManualPage {
  GameBoxManualPage({required this.image, required this.aspect, required this.pageCount});

  /// Owned by the caller, who disposes it.
  final ui.Image image;

  /// Width / height of the first page.
  final double aspect;
  final int pageCount;

  void dispose() => image.dispose();
}

/// Draws the cover of the game's manual (docs/game-box-3d.md § 11).
///
/// The PDF is opened only when the box is opened for inspection, never while
/// the library scrolls: one page, at a booklet size (720 px on its long side),
/// then the document is closed. The full manual is read by NeoStation's
/// manual reader on the same file.
class GameBoxManualCover {
  GameBoxManualCover._();

  static const int coverPixels = 720;

  /// Replaces the PDF engine in tests.
  @visibleForTesting
  static Future<GameBoxManualPage?> Function(String path)? debugRenderer;

  /// The first page, or null when the file cannot be read as a PDF.
  static Future<GameBoxManualPage?> render(String path) async {
    final debug = debugRenderer;
    if (debug != null) return debug(path);
    PdfDocument? document;
    try {
      await pdfrxFlutterInitialize();
      document = await PdfDocument.openFile(path);
      if (document.pages.isEmpty) return null;
      final page = document.pages.first;
      if (page.width <= 0 || page.height <= 0) return null;
      final aspect = page.width / page.height;
      final width = aspect >= 1 ? coverPixels : (coverPixels * aspect).round();
      final height = aspect >= 1 ? (coverPixels / aspect).round() : coverPixels;
      final pdfImage = await page.render(
        width: width,
        height: height,
        fullWidth: width.toDouble(),
        fullHeight: height.toDouble(),
        backgroundColor: 0xFFFFFFFF,
      );
      if (pdfImage == null) return null;
      try {
        final image = await pdfImage.createImage();
        return GameBoxManualPage(image: image, aspect: aspect, pageCount: document.pages.length);
      } finally {
        pdfImage.dispose();
      }
    } catch (_) {
      // A damaged or protected PDF: the booklet keeps its plain cover and the
      // reader shows its own error.
      return null;
    } finally {
      await document?.dispose();
    }
  }
}
