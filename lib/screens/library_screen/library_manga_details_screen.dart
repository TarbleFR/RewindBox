import 'package:flutter/material.dart';

import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_catalog_service.dart';

/// Online title page (contract stub, Build 437 wave 2): details, favourite,
/// ordered chapter list with read marks, resume, opens the page reader.
class LibraryMangaDetailsScreen extends StatefulWidget {
  const LibraryMangaDetailsScreen({
    super.key,
    required this.item,
    this.addon,
    this.aidokuSourceId,
  });

  /// Catalogue card or favourite snapshot (its `raw` carries
  /// `aidokuSourceId`, `mangaId` and `imageHeaders` for Aidoku titles).
  final LibraryCatalogItem item;

  /// Active source; null when the source was deactivated (e.g. opened from
  /// a favourite): the screen then shows cached data and explains how to
  /// re-enable the source.
  final LibraryAddon? addon;

  /// Aidoku source id when [addon] is null.
  final String? aidokuSourceId;

  static Future<void> open(
    BuildContext context, {
    required LibraryCatalogItem item,
    LibraryAddon? addon,
    String? aidokuSourceId,
  }) {
    return Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => LibraryMangaDetailsScreen(
          item: item,
          addon: addon,
          aidokuSourceId: aidokuSourceId,
        ),
      ),
    );
  }

  @override
  State<LibraryMangaDetailsScreen> createState() =>
      _LibraryMangaDetailsScreenState();
}

class _LibraryMangaDetailsScreenState extends State<LibraryMangaDetailsScreen> {
  @override
  Widget build(BuildContext context) => const Scaffold();
}
