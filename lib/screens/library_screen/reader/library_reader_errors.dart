import 'dart:io';

import 'package:flutter/material.dart';
import 'package:pdfrx/pdfrx.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_aidoku_engines.dart'
    show LibrarySourceErrorKind, LibrarySourceException;
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_local_models.dart';

import 'library_reader_chrome.dart';
import 'library_reader_palette.dart';

/// A reader failure as shown to the user: a translated explanation
/// ([messageKey] in [LibraryReaderLocale]) and the raw technical [detail]
/// (English, untranslated), shown separately.
@immutable
class LibraryReaderErrorInfo {
  const LibraryReaderErrorInfo(this.messageKey, {this.detail});

  final String messageKey;
  final String? detail;

  /// Translates a typed failure of the Library services.
  factory LibraryReaderErrorInfo.from(Object error) {
    if (error is LibraryNetworkException) {
      return LibraryReaderErrorInfo(
        networkKey(error.kind),
        detail: _networkDetail(error),
      );
    }
    if (error is LibrarySourceException) {
      final network = error.networkError;
      if (error.kind == LibrarySourceErrorKind.network && network != null) {
        return LibraryReaderErrorInfo(
          networkKey(network.kind),
          detail: _networkDetail(network),
        );
      }
      return LibraryReaderErrorInfo(
        sourceKey(error.kind),
        detail: <String>[
          error.kind.name,
          if (error.sourceId.isNotEmpty) error.sourceId,
          if (error.uri != null) error.uri.toString(),
          if (error.detail != null && error.detail!.isNotEmpty) error.detail!,
        ].join(' · '),
      );
    }
    if (error is LibraryBookException) {
      return LibraryReaderErrorInfo(
        bookIssueKey(error.issue),
        detail: error.toString(),
      );
    }
    if (error is PdfException) {
      return LibraryReaderErrorInfo(
        bookIssueKey(pdfIssue(error)),
        detail: <String>[
          error.runtimeType.toString(),
          if (error.errorCode != null) 'code ${error.errorCode}',
          error.message,
        ].join(' · '),
      );
    }
    if (error is FileSystemException) {
      return LibraryReaderErrorInfo(
        bookIssueKey(LibraryBookIssue.unreadable),
        detail: error.toString(),
      );
    }
    if (error is StateError) {
      // A worker isolate that crashed or was closed (EPUB, CBZ).
      return LibraryReaderErrorInfo('errorWorker', detail: error.toString());
    }
    return LibraryReaderErrorInfo('errorGeneric', detail: error.toString());
  }

  static String networkKey(LibraryNetworkErrorKind kind) => switch (kind) {
    LibraryNetworkErrorKind.offline => 'errorOffline',
    LibraryNetworkErrorKind.timeout => 'errorTimeout',
    LibraryNetworkErrorKind.cancelled => 'errorGeneric',
    LibraryNetworkErrorKind.challenge => 'errorChallenge',
    LibraryNetworkErrorKind.serverUnavailable => 'errorServerUnavailable',
    LibraryNetworkErrorKind.notFound => 'errorNotFound',
    LibraryNetworkErrorKind.httpStatus => 'errorHttpStatus',
    LibraryNetworkErrorKind.tooLarge => 'errorTooLarge',
    LibraryNetworkErrorKind.invalidResponse => 'errorInvalidResponse',
  };

  static String sourceKey(LibrarySourceErrorKind kind) => switch (kind) {
    LibrarySourceErrorKind.unsupported => 'errorSourceUnsupported',
    LibrarySourceErrorKind.noResults => 'errorSiteChanged',
    LibrarySourceErrorKind.noChapters => 'errorNoChapters',
    LibrarySourceErrorKind.noPages => 'errorNoPages',
    LibrarySourceErrorKind.protectedChapter => 'errorProtectedChapter',
    LibrarySourceErrorKind.parseFailed => 'errorSiteChanged',
    LibrarySourceErrorKind.invalidImage => 'errorInvalidImage',
    LibrarySourceErrorKind.network => 'errorOffline',
  };

  static String bookIssueKey(LibraryBookIssue issue) => switch (issue) {
    LibraryBookIssue.unsupportedFormat => 'issueUnsupportedFormat',
    LibraryBookIssue.rarArchive => 'issueRarArchive',
    LibraryBookIssue.sevenZipArchive => 'issueSevenZipArchive',
    LibraryBookIssue.kindleFormat => 'issueKindleFormat',
    LibraryBookIssue.folder => 'issueFolder',
    LibraryBookIssue.emptyFile => 'issueEmptyFile',
    LibraryBookIssue.drmProtected => 'issueDrmProtected',
    LibraryBookIssue.passwordProtected => 'issuePasswordProtected',
    LibraryBookIssue.encryptedArchive => 'issueEncryptedArchive',
    LibraryBookIssue.unsupportedCompression => 'issueUnsupportedCompression',
    LibraryBookIssue.corrupt => 'issueCorrupt',
    LibraryBookIssue.noContent => 'issueNoContent',
    LibraryBookIssue.tooLarge => 'issueTooLarge',
    LibraryBookIssue.unreadable => 'issueUnreadable',
    LibraryBookIssue.duplicate ||
    LibraryBookIssue.duplicateInSelection ||
    LibraryBookIssue.sameNameInSelection ||
    LibraryBookIssue.storageFailed => 'issueOther',
  };

  /// pdfrx / PDFium failures as book issues (same mapping as the import
  /// inspector): password, DRM (unsupported security handler), unreadable
  /// file, anything else damaged.
  static LibraryBookIssue pdfIssue(Object error) {
    if (error is PdfPasswordException) {
      return LibraryBookIssue.passwordProtected;
    }
    if (error is PdfException) {
      return switch (error.errorCode) {
        2 => LibraryBookIssue.unreadable,
        4 => LibraryBookIssue.passwordProtected,
        5 => LibraryBookIssue.drmProtected,
        _ => LibraryBookIssue.corrupt,
      };
    }
    if (error is FileSystemException) return LibraryBookIssue.unreadable;
    return LibraryBookIssue.corrupt;
  }

  static String _networkDetail(LibraryNetworkException error) => <String>[
    error.kind.name,
    if (error.statusCode != null) 'HTTP ${error.statusCode}',
    if (error.uri != null) error.uri.toString(),
    if (error.detail != null && error.detail!.isNotEmpty) error.detail!,
  ].join(' · ');

  /// Whether [error] is a cancellation that must not be shown.
  static bool isCancellation(Object error) =>
      error is LibraryNetworkException &&
          error.kind == LibraryNetworkErrorKind.cancelled ||
      error is LibrarySourceException &&
          error.networkError?.kind == LibraryNetworkErrorKind.cancelled;
}

/// Translated explanation, optional retry/close actions and an expandable
/// line with the raw technical detail.
class LibraryReaderErrorView extends StatefulWidget {
  const LibraryReaderErrorView({
    super.key,
    required this.error,
    required this.palette,
    this.onRetry,
    this.onClose,
    this.compact = false,
  });

  final LibraryReaderErrorInfo error;
  final LibraryReaderPalette palette;
  final VoidCallback? onRetry;
  final VoidCallback? onClose;

  /// Smaller layout used inside a single page.
  final bool compact;

  @override
  State<LibraryReaderErrorView> createState() => _LibraryReaderErrorViewState();
}

class _LibraryReaderErrorViewState extends State<LibraryReaderErrorView> {
  bool _showDetail = false;

  @override
  Widget build(BuildContext context) {
    final palette = widget.palette;
    final message = LibraryReaderLocale.text(context, widget.error.messageKey);
    final detail = widget.error.detail;
    final textStyle = TextStyle(
      color: palette.text,
      fontSize: widget.compact ? 15 : 17,
      height: 1.35,
    );
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                Icons.error_outline_rounded,
                size: widget.compact ? 32 : 44,
                color: palette.secondaryText,
              ),
              const SizedBox(height: 12),
              Text(message, textAlign: TextAlign.center, style: textStyle),
              const SizedBox(height: 16),
              Wrap(
                alignment: WrapAlignment.center,
                spacing: 12,
                runSpacing: 8,
                children: <Widget>[
                  if (widget.onRetry != null)
                    LibraryReaderTextButton(
                      label: LibraryReaderLocale.text(context, 'retry'),
                      icon: Icons.refresh_rounded,
                      palette: palette,
                      filled: true,
                      onPressed: widget.onRetry!,
                    ),
                  if (widget.onClose != null)
                    LibraryReaderTextButton(
                      label: LibraryReaderLocale.text(context, 'close'),
                      icon: Icons.close_rounded,
                      palette: palette,
                      onPressed: widget.onClose!,
                    ),
                ],
              ),
              if (detail != null && detail.isNotEmpty) ...<Widget>[
                const SizedBox(height: 8),
                LibraryReaderTextButton(
                  label: LibraryReaderLocale.text(context, 'technicalDetails'),
                  icon: _showDetail
                      ? Icons.expand_less_rounded
                      : Icons.expand_more_rounded,
                  palette: palette,
                  onPressed: () => setState(() => _showDetail = !_showDetail),
                ),
                if (_showDetail)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: SelectableText(
                      detail,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: palette.secondaryText,
                        fontSize: 12,
                        fontFamily: 'Menlo',
                        fontFamilyFallback: const <String>[
                          'Courier New',
                          'monospace',
                        ],
                      ),
                    ),
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
