import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

import 'package:archive/archive.dart' show Archive, ArchiveFile, ZipEncoder;
import 'package:flutter/services.dart' show rootBundle;
import 'package:http/http.dart' as http;
import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:path/path.dart' as path;

import '../utils/bounded_concurrency.dart';
import 'libretro_core_catalog.dart';
import 'libretro_overlay_converter.dart';
import 'libretro_skin_catalog_service.dart';
import 'libretro_skin_compatibility.dart';
import 'libretro_skin_remote_inspector.dart';
import 'libretro_skin_service.dart';
import 'logger_service.dart';

/// Where a catalog skin comes from. Product names, never translated.
abstract final class LibretroSkinSources {
  static const String provenance = 'provenance';
  static const String deltaStyles = 'deltastyles';
  static const String deltaSkins = 'deltaskins';
  static const String pocketArch = 'pocketarch';
  static const String libretroOverlays = 'libretro-overlays';

  static const List<String> all = <String>[provenance, deltaStyles, deltaSkins, pocketArch, libretroOverlays];

  static String label(String source) => switch (source) {
        provenance => 'Provenance',
        deltaStyles => 'DeltaStyles',
        deltaSkins => 'Delta Skins',
        pocketArch => 'PocketArch',
        libretroOverlays => 'Libretro overlays',
        _ => source,
      };
}

/// One skin of the unified catalogs: a Delta / Manic archive (Provenance's
/// catalog, which also lists DeltaStyles and Delta Skins, or the Delta
/// Skins site) or a RetroArch touch overlay (PocketArch, libretro
/// common-overlays) converted on the device.
class LibretroCatalogSkin {
  const LibretroCatalogSkin({
    required this.key,
    required this.source,
    required this.name,
    required this.consoles,
    this.author,
    this.origin,
    this.thumbnailURL,
    this.downloadCount,
    this.license,
    this.archive,
    this.overlay,
    this.excludedReason,
    this.supports,
    this.catalogSources = const <String>[],
  });

  /// Unique key: the normalized download link, or the overlay's path.
  final String key;

  /// [LibretroSkinSources] id.
  final String source;

  /// Indexes that list this file, independently of its author's host.
  final List<String> catalogSources;

  bool belongsToSource(String value) => source == value || catalogSources.contains(value);

  LibretroCatalogSkin withCatalogSources(Iterable<String> values) => LibretroCatalogSkin(
        key: key, source: source, name: name, consoles: consoles,
        author: author, origin: origin, thumbnailURL: thumbnailURL,
        downloadCount: downloadCount, license: license, archive: archive,
        overlay: overlay, excludedReason: excludedReason, supports: supports,
        catalogSources: values.toSet().toList(),
      );
  final String name;

  /// Consoles the catalog lists it for (verified by the native filter).
  final List<String> consoles;
  final String? author;

  /// Repository or site detail ("LitRitt/emuskins").
  final String? origin;
  final String? thumbnailURL;
  final int? downloadCount;
  final String? license;

  /// Delta archive entry (download and import).
  final LibretroSkinCatalogEntry? archive;

  /// RetroArch overlay (converted on the device).
  final LibretroOverlayEntry? overlay;

  /// Reason code decided from the catalog data alone
  /// (LibretroSkinCompatibility constants), null when it must be analysed.
  final String? excludedReason;

  /// Devices the creator lists ("All phones + landscape"...), shown only.
  final String? supports;

  bool isForConsole(String console) => consoles.contains(console);
}

/// One RetroArch overlay of the bundled index (assets/data/libretro_skin_overlays.json).
class LibretroOverlayEntry {
  const LibretroOverlayEntry({
    required this.id,
    required this.source,
    required this.path,
    required this.repository,
    required this.commit,
    required this.device,
    required this.files,
  });

  final String id;
  final String source;

  /// .cfg path in its repository.
  final String path;
  final String repository;
  final String commit;

  /// "iphone" or "ipad" (layouts made for a tablet).
  final String device;

  /// Repository paths of the images the overlay uses.
  final List<String> files;

  /// Immutable download link of a repository file at the pinned commit.
  Uri fileUri(String file) => Uri(
        scheme: 'https',
        host: 'raw.githubusercontent.com',
        pathSegments: <String>[...repository.split('/'), commit, ...file.split('/')],
      );

  String get webURL => 'https://github.com/$repository/blob/$commit/${path.split('/').map(Uri.encodeComponent).join('/')}';
}

/// The unified skin catalogs of one device: every source, deduplicated, and
/// the iPhone verdict of each entry for a console (central filter:
/// metadata first, then the native LibretroSkinCompatibility on the real
/// info.json, read with range requests, or on the converted overlay).
/// Verdicts are cached in `Caches/Libretro/skin-verdicts.json`; favorites
/// are kept in `Documents/Libretro/SkinFavorites.json`.
class LibretroSkinCatalogs {
  LibretroSkinCatalogs({
    required this.skins,
    required this.provenance,
    http.Client? client,
    Future<String> Function()? overlayIndex,
    Future<Map<String, dynamic>> Function(String directory)? inspect,
    DateTime Function()? clock,
    Future<Uint8List?> Function(String directory, String console, String orientation, double width, double height)? renderPreview,
    this.concurrency = 4,
    bool ownsClient = false,
  })  : _client = client ?? http.Client(),
        _ownsClient = client == null || ownsClient,
        _overlayIndex = overlayIndex ?? (() => rootBundle.loadString(overlayIndexAsset)),
        _inspect = inspect,
        _renderPreview = renderPreview,
        _clock = clock ?? DateTime.now;

  /// The catalogs installing into [skins], with their own HTTP client
  /// (closed by [dispose]).
  factory LibretroSkinCatalogs.over(LibretroSkinService skins) {
    final client = http.Client();
    return LibretroSkinCatalogs(
      skins: skins,
      provenance: LibretroSkinCatalogService(cacheDirectory: skins.cacheDirectory, skins: skins, client: client),
      client: client,
      ownsClient: true,
    );
  }

  static Future<LibretroSkinCatalogs> create() async => LibretroSkinCatalogs.over(await LibretroSkinService.create());

  static final _log = LoggerService.instance;

  static const String overlayIndexAsset = 'assets/data/libretro_skin_overlays.json';
  static const String deltaSkinsRepository = 'delta-skins/delta-skins.github.io';
  static const List<String> deltaSkinsPages = <String>['gba', 'gbc', 'nds', 'n64', 'nes', 'snes', 'unofficial'];
  static const String verdictsFileName = 'skin-verdicts.json';
  static const String favoritesFileName = 'SkinFavorites.json';
  static const String inspectionFolderName = 'SkinInspection';

  /// Bump when the native or Dart rules change: cached verdicts are redone.
  static const int rulesVersion = 3;
  static const Duration verdictLifetime = Duration(days: 30);
  static const Duration unreachableLifetime = Duration(hours: 6);

  final LibretroSkinService skins;
  final LibretroSkinCatalogService provenance;
  final int concurrency;
  final http.Client _client;
  final bool _ownsClient;
  final Future<String> Function() _overlayIndex;
  final Future<Map<String, dynamic>> Function(String directory)? _inspect;
  final DateTime Function() _clock;
  final Future<Uint8List?> Function(String, String, String, double, double)? _renderPreview;
  final Map<String, Future<Map<String, Uint8List>>> _previews = {};
  final List<Future<void>> _previewWorkers = [Future<void>.value(), Future<void>.value()];
  int _nextPreviewWorker = 0;

  List<LibretroCatalogSkin>? _entries;
  final Set<String> _unavailable = <String>{};
  Map<String, Map<String, Object?>>? _verdicts;
  Set<String>? _favorites;
  bool _disposed = false;

  /// Sources that could not be read on the last [load] (labels shown).
  Set<String> get unavailableSources => Set<String>.unmodifiable(_unavailable);

  /// Every catalog skin, deduplicated (the first source wins: Provenance,
  /// then the Delta Skins site, then the overlays). Null when no source
  /// could be read.
  Future<List<LibretroCatalogSkin>?> load({bool refresh = false}) async {
    if (_entries != null && !refresh) return _entries;
    _unavailable.clear();
    final merged = <String, LibretroCatalogSkin>{};
    var any = false;

    final provenanceEntries = await provenance.load(refresh: refresh);
    if (provenanceEntries == null) {
      _unavailable.add(LibretroSkinSources.provenance);
    } else {
      any = true;
      for (final entry in provenanceEntries) {
        // One unusable entry is skipped; it never takes the other catalog
        // entries and sources down with it (Build 446).
        final LibretroCatalogSkin skin;
        try {
          skin = fromProvenance(entry);
        } catch (error) {
          _log.w('Provenance skin skipped (${entry.downloadURL}): $error');
          continue;
        }
        _mergeEntry(merged, skin);
      }
    }
    try {
      for (final skin in await _deltaSkinsSite()) {
        _mergeEntry(merged, skin);
      }
      any = true;
    } catch (error) {
      _log.w('Delta Skins site unavailable: $error');
      _unavailable.add(LibretroSkinSources.deltaSkins);
    }
    try {
      for (final skin in parseOverlayIndex(await _overlayIndex())) {
        _mergeEntry(merged, skin);
      }
      any = true;
    } catch (error) {
      _log.w('Overlay index unreadable: $error');
      _unavailable.addAll(const <String>[LibretroSkinSources.pocketArch, LibretroSkinSources.libretroOverlays]);
    }
    if (!any) return null;
    return _entries = _withoutDuplicateNames(merged.values.toList());
  }

  /// Entries listed for [console], most downloaded first.
  static List<LibretroCatalogSkin> forConsole(Iterable<LibretroCatalogSkin> entries, String console) =>
      entries.where((entry) => entry.isForConsole(console)).toList()
        ..sort((a, b) => (b.downloadCount ?? 0).compareTo(a.downloadCount ?? 0));

  /// Case-insensitive search in names, authors and sources.
  static List<LibretroCatalogSkin> search(Iterable<LibretroCatalogSkin> entries, String query) {
    final needle = query.trim().toLowerCase();
    if (needle.isEmpty) return entries.toList();
    return entries
        .where((entry) =>
            entry.name.toLowerCase().contains(needle) ||
            (entry.author?.toLowerCase().contains(needle) ?? false) ||
            <String>[entry.source, ...entry.catalogSources]
                .any((source) => LibretroSkinSources.label(source).toLowerCase().contains(needle)))
        .toList();
  }

  // ---- Sources ----

  /// A Provenance catalog entry, attributed to the site or repository it
  /// lists (DeltaStyles, the Delta Skins site, creators' repositories).
  static LibretroCatalogSkin fromProvenance(LibretroSkinCatalogEntry entry) {
    final host = (entry.source ?? '').toLowerCase();
    final source = host.contains('deltastyles')
        ? LibretroSkinSources.deltaStyles
        : host.contains('delta-skins.github.io')
            ? LibretroSkinSources.deltaSkins
            : LibretroSkinSources.provenance;
    return LibretroCatalogSkin(
      key: normalizeDownloadURL(entry.downloadURL),
      source: source,
      catalogSources: const <String>[LibretroSkinSources.provenance],
      name: entry.name,
      consoles: entry.consoles,
      author: entry.author,
      origin: source == LibretroSkinSources.provenance ? entry.source : null,
      thumbnailURL: entry.thumbnailURL,
      downloadCount: entry.downloadCount,
      archive: entry,
      excludedReason: entry.isDirectDownload ? null : LibretroSkinCompatibility.notDirect,
    );
  }

  /// Same link whatever its spelling: `github.com/OWNER/REPO/raw/REF/PATH`
  /// and `raw.githubusercontent.com/OWNER/REPO/REF/PATH` agree, host case
  /// and percent-encoding are ignored.
  static String normalizeDownloadURL(String url) {
    final trimmed = url.trim();
    final uri = Uri.tryParse(trimmed.replaceAll(' ', '%20').replaceAll('#', '%23'));
    if (uri == null || uri.host.isEmpty) return trimmed.toLowerCase();
    // pathSegments are already percent-decoded. Decoding them a second time
    // threw on any non-ASCII character or literal '%': two published
    // DeltaStyles links ("pokÃ©mon pinball GBA", "DK control + real dpad Â")
    // made every catalog fail to load in Builds 444 and 445.
    List<String> segments;
    try {
      segments = uri.pathSegments.toList();
    } catch (_) {
      return trimmed.toLowerCase();
    }
    var host = uri.host.toLowerCase();
    if (host.startsWith('www.')) host = host.substring(4);
    if (host == 'github.com' && segments.length > 4 && (segments[2] == 'raw' || segments[2] == 'blob')) {
      host = 'raw.githubusercontent.com';
      segments = <String>[segments[0], segments[1], ...segments.sublist(3)];
    }
    final query = host == 'drive.google.com' ? '?${uri.query}' : '';
    return '$host/${segments.join('/')}$query';
  }

  Future<List<LibretroCatalogSkin>> _deltaSkinsSite() async {
    final entries = <LibretroCatalogSkin>[];
    for (final page in deltaSkinsPages) {
      final uri = Uri.https('raw.githubusercontent.com', '/$deltaSkinsRepository/master/$page.html');
      final response = await _client.get(uri).timeout(LibretroSkinCatalogService.requestTimeout);
      if (response.statusCode != 200) throw HttpException('HTTP ${response.statusCode} $uri');
      entries.addAll(parseDeltaSkinsPage(utf8.decode(response.bodyBytes, allowMalformed: true)));
    }
    return entries;
  }

  /// The skins of one Delta Skins site page: its `<img data-console
  /// data-maker data-supports data-download alt src>` cards.
  static List<LibretroCatalogSkin> parseDeltaSkinsPage(String html) {
    final entries = <LibretroCatalogSkin>[];
    for (final tag in RegExp(r'<img\b[^>]*\bdata-download\s*=[^>]*>', caseSensitive: false).allMatches(html)) {
      final card = _deltaSkinsCard(tag.group(0)!);
      if (card != null) entries.add(card);
    }
    return entries;
  }

  /// One card of a Delta Skins site page; null when it is unusable (a bad
  /// card is skipped, the rest of the page is kept).
  static LibretroCatalogSkin? _deltaSkinsCard(String text) {
    try {
      String? attribute(String name) {
        final match = RegExp('\\b$name\\s*=\\s*("([^"]*)"|\'([^\']*)\')', caseSensitive: false).firstMatch(text);
        final value = match?.group(2) ?? match?.group(3);
        return value == null || value.trim().isEmpty ? null : _unescape(value.trim());
      }

      final download = attribute('data-download');
      final name = attribute('alt');
      final console = attribute('data-console');
      if (download == null || name == null || console == null) return null;
      final consoles = _deltaSkinsConsoles(console, name);
      if (consoles.isEmpty) return null;
      final source = attribute('src');
      final thumbnail = source == null
          ? null
          : 'https://raw.githubusercontent.com/$deltaSkinsRepository/master/${source.split('/').map(Uri.encodeComponent).join('/')}';
      final archive = LibretroSkinCatalogEntry(
        id: 'ds-${normalizeDownloadURL(download).hashCode.toUnsigned(32).toRadixString(16)}',
        name: name,
        author: attribute('data-maker'),
        systems: consoles,
        downloadURL: download,
        thumbnailURL: thumbnail,
        source: 'delta-skins.github.io',
      );
      return LibretroCatalogSkin(
        key: normalizeDownloadURL(download),
        source: LibretroSkinSources.deltaSkins,
        name: name,
        consoles: consoles,
        author: archive.author,
        thumbnailURL: thumbnail,
        archive: archive,
        supports: attribute('data-supports'),
        excludedReason: archive.isDirectDownload ? null : LibretroSkinCompatibility.notDirect,
      );
    } catch (error) {
      _log.w('Delta Skins card skipped: $error');
      return null;
    }
  }

  static List<String> _deltaSkinsConsoles(String page, String name) {
    switch (page.toLowerCase()) {
      case 'gba':
        return const <String>['gba'];
      case 'gbc':
        return const <String>['gb', 'gbc'];
      case 'nds':
        return const <String>['nds'];
      case 'n64':
        return const <String>['n64'];
      case 'nes':
        return const <String>['nes'];
      case 'snes':
        return const <String>['snes'];
    }
    // "unofficial": systems Delta itself does not run, named in the title.
    final lower = name.toLowerCase();
    if (lower.contains('game gear')) return const <String>['gg'];
    if (lower.contains('sms') || lower.contains('master system')) return const <String>['sms'];
    if (lower.contains('sg-1000') || lower.contains('sg1000')) return const <String>['sg1000'];
    if (lower.contains('genesis') || lower.contains('mega drive')) return const <String>['md', 'mcd', '32x'];
    if (lower.contains('psp')) return const <String>['psp'];
    if (lower.contains('ps1') || lower.contains('psx') || lower.contains('playstation')) return const <String>['psx'];
    return const <String>[];
  }

  static String _unescape(String value) => value
      .replaceAll('&amp;', '&')
      .replaceAll('&quot;', '"')
      .replaceAll('&#39;', "'")
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>');

  /// Entries of the bundled overlay index.
  static List<LibretroCatalogSkin> parseOverlayIndex(String text) {
    final json = jsonDecode(text);
    if (json is! Map || json['entries'] is! List) throw const FormatException('overlay index without entries');
    final sources = json['sources'] is Map ? json['sources'] as Map : const <Object?, Object?>{};
    final entries = <LibretroCatalogSkin>[];
    for (final raw in json['entries'] as List) {
      if (raw is! Map) continue;
      final source = raw['source'];
      final cfgPath = raw['path'];
      final id = raw['id'];
      final description = sources[source];
      if (source is! String || cfgPath is! String || id is! String || description is! Map) continue;
      final repository = description['repository'];
      final commit = description['commit'];
      if (repository is! String || commit is! String) continue;
      final excluded = raw['excluded'];
      final files = raw['files'];
      entries.add(LibretroCatalogSkin(
        key: 'overlay:$source:$cfgPath',
        source: source,
        name: raw['name'] is String ? raw['name'] as String : path.basenameWithoutExtension(cfgPath),
        consoles: <String>[for (final console in (raw['consoles'] as List? ?? const <Object?>[])) if (console is String) console],
        author: description['author'] is String ? description['author'] as String : null,
        origin: repository,
        license: description['license'] is String ? description['license'] as String : null,
        overlay: LibretroOverlayEntry(
          id: id,
          source: source,
          path: cfgPath,
          repository: repository,
          commit: commit,
          device: raw['device'] == 'ipad' ? 'ipad' : 'iphone',
          files: <String>[for (final file in (files is List ? files : const <Object?>[])) if (file is String) file],
        ),
        excludedReason: excluded is String ? excluded : null,
      ));
    }
    return entries;
  }

  /// Hides a skin published twice under the same name by the same author
  /// for the same consoles (kept: the most downloaded).
  static List<LibretroCatalogSkin> _withoutDuplicateNames(List<LibretroCatalogSkin> entries) {
    final kept = <String, LibretroCatalogSkin>{};
    for (final entry in entries) {
      final consoles = <String>[...entry.consoles]..sort();
      final identity = '${entry.name.trim().toLowerCase()}|${(entry.author ?? '').trim().toLowerCase()}|${consoles.join(',')}';
      final previous = kept[identity];
      if (previous == null) {
        kept[identity] = entry;
      } else {
        final winner = (entry.downloadCount ?? 0) > (previous.downloadCount ?? 0) ? entry : previous;
        kept[identity] = winner.withCatalogSources(<String>[
          previous.source, ...previous.catalogSources, entry.source, ...entry.catalogSources,
        ]);
      }
    }
    return kept.values.toList();
  }

  static void _mergeEntry(Map<String, LibretroCatalogSkin> entries, LibretroCatalogSkin entry) {
    final previous = entries[entry.key];
    entries[entry.key] = previous == null ? entry : previous.withCatalogSources(<String>[
      ...previous.catalogSources, entry.source, ...entry.catalogSources,
    ]);
  }

  // ---- Central filter ----

  File get _verdictsFile => File(path.join(skins.cacheDirectory, verdictsFileName));

  Future<Map<String, Map<String, Object?>>> _loadVerdicts() async {
    final loaded = _verdicts;
    if (loaded != null) return loaded;
    final verdicts = <String, Map<String, Object?>>{};
    try {
      final file = _verdictsFile;
      if (await file.exists()) {
        final json = jsonDecode(await file.readAsString());
        if (json is Map && json['rules'] == rulesVersion && json['entries'] is Map) {
          (json['entries'] as Map).forEach((key, value) {
            if (key is String && value is Map) verdicts[key] = Map<String, Object?>.from(value);
          });
        }
      }
    } catch (error) {
      _log.w('Skin verdict cache unreadable: $error');
    }
    return _verdicts = verdicts;
  }

  Future<void> _saveVerdicts() async {
    final verdicts = _verdicts;
    if (verdicts == null) return;
    try {
      final file = _verdictsFile;
      await file.parent.create(recursive: true);
      final partial = File('${file.path}.part');
      await partial.writeAsString(jsonEncode(<String, Object?>{'rules': rulesVersion, 'entries': verdicts}), flush: true);
      await partial.rename(file.path);
    } catch (error) {
      _log.w('Skin verdict cache not written: $error');
    }
  }

  static String _verdictKey(LibretroCatalogSkin entry, String console) => '${entry.key}|$console';

  /// The verdict known without any network access: a reason from the
  /// catalog data, or a fresh cached analysis; null when [classify] must run.
  Future<LibretroSkinCompatibility?> knownVerdict(LibretroCatalogSkin entry, String console) async {
    final excluded = _staticExclusion(entry, console);
    if (excluded != null) return excluded;
    final cached = (await _loadVerdicts())[_verdictKey(entry, console)];
    if (cached == null) return null;
    final checked = DateTime.tryParse('${cached['checkedAt']}');
    final verdict = LibretroSkinCompatibility.fromJson(cached['verdict'], console: console);
    if (checked == null || verdict == null) return null;
    final unreachable = verdict.reasons.contains(LibretroSkinCompatibility.unreachable);
    final lifetime = unreachable ? unreachableLifetime : verdictLifetime;
    if (_clock().difference(checked) > lifetime) return null;
    return verdict;
  }

  static LibretroSkinCompatibility? _staticExclusion(LibretroCatalogSkin entry, String console) {
    final reason = entry.excludedReason;
    if (reason != null) return LibretroSkinCompatibility.excluded(console, reason);
    if (!LibretroCoreCatalog.consoles.containsKey(console)) {
      return LibretroSkinCompatibility.excluded(console, LibretroSkinCompatibility.system);
    }
    return null;
  }

  /// Verdicts of [entries] for [console]: known ones at once, the others
  /// analysed [concurrency] at a time, most downloaded first. [onVerdict]
  /// reports each one as it arrives.
  Future<Map<String, LibretroSkinCompatibility>> classifyAll(
    List<LibretroCatalogSkin> entries,
    String console, {
    void Function(LibretroCatalogSkin entry, LibretroSkinCompatibility verdict)? onVerdict,
    bool Function()? cancelled,
  }) async {
    final verdicts = <String, LibretroSkinCompatibility>{};
    final pending = <LibretroCatalogSkin>[];
    for (final entry in entries) {
      final known = await knownVerdict(entry, console);
      if (known == null) {
        pending.add(entry);
      } else {
        verdicts[entry.key] = known;
        onVerdict?.call(entry, known);
      }
    }
    pending.sort((a, b) => (b.downloadCount ?? 0).compareTo(a.downloadCount ?? 0));
    var unsaved = 0;
    await runBounded<LibretroCatalogSkin>(pending, concurrency, (entry) async {
      if (cancelled?.call() ?? false) return;
      final verdict = await classify(entry, console, save: false);
      verdicts[entry.key] = verdict;
      onVerdict?.call(entry, verdict);
      if (++unsaved >= 20) {
        unsaved = 0;
        await _saveVerdicts();
      }
    }, label: 'Skin compatibility');
    await _saveVerdicts();
    return verdicts;
  }

  /// The iPhone verdict of one entry for [console] (cached).
  Future<LibretroSkinCompatibility> classify(LibretroCatalogSkin entry, String console, {bool save = true}) async {
    final known = await knownVerdict(entry, console);
    if (known != null) return known;
    LibretroSkinCompatibility verdict;
    final inspection = Directory(path.join(skins.cacheDirectory, inspectionFolderName, _randomName()));
    try {
      if (entry.overlay != null) {
        verdict = await _classifyOverlay(entry.overlay!, console, inspection);
      } else {
        verdict = await _classifyArchive(entry, console, inspection);
      }
    } on LibretroRemoteSkinInspectionException catch (error) {
      _log.w('Skin ${entry.key} not analysed: $error');
      verdict = LibretroSkinCompatibility.excluded(
        console,
        error.network ? LibretroSkinCompatibility.unreachable : LibretroSkinCompatibility.invalid,
      );
    } catch (error) {
      _log.w('Skin ${entry.key} not analysed: $error');
      verdict = LibretroSkinCompatibility.excluded(console, LibretroSkinCompatibility.unreachable);
    } finally {
      try {
        if (await inspection.exists()) await inspection.delete(recursive: true);
      } catch (_) {}
    }
    // Requests cut by dispose() say nothing about the file: not recorded.
    if (_disposed) return verdict;
    (await _loadVerdicts())[_verdictKey(entry, console)] = <String, Object?>{
      'checkedAt': _clock().toUtc().toIso8601String(),
      'verdict': verdict.toJson(),
    };
    if (save) await _saveVerdicts();
    return verdict;
  }

  Future<LibretroSkinCompatibility> _classifyArchive(
    LibretroCatalogSkin entry,
    String console,
    Directory inspection,
  ) async {
    final uri = entry.archive?.downloadUri;
    if (uri == null) return LibretroSkinCompatibility.excluded(console, LibretroSkinCompatibility.notDirect);
    final archive = await LibretroRemoteSkinInspector(client: _client).read(uri);
    await LibretroRemoteSkinInspector.materialize(archive, inspection);
    return _nativeVerdict(inspection, console);
  }

  Future<LibretroSkinCompatibility> _classifyOverlay(
    LibretroOverlayEntry overlay,
    String console,
    Directory inspection,
  ) async {
    final conversion = await _convert(overlay, console);
    if (!conversion.converted) {
      return LibretroSkinCompatibility.excluded(console, LibretroSkinCompatibility.overlayUnsupported);
    }
    await inspection.create(recursive: true);
    await File(path.join(inspection.path, 'info.json')).writeAsString(jsonEncode(conversion.info));
    for (final file in conversion.files.keys) {
      final stub = LibretroRemoteSkinInspector.stubFor(file);
      if (stub == null) continue;
      final target = File(path.join(inspection.path, file));
      await target.parent.create(recursive: true);
      await target.writeAsBytes(stub);
    }
    return _nativeVerdict(inspection, console);
  }

  Future<LibretroOverlayConversion> _convert(LibretroOverlayEntry overlay, String console) async {
    final bytes = await _readOverlayFile(overlay, overlay.path, 1024 * 1024);
    final conversion = LibretroOverlayConverter.convert(
      utf8.decode(bytes),
      cfgPath: overlay.path,
      console: console,
      name: path.basenameWithoutExtension(overlay.path).replaceAll('_', ' '),
      identifier: 'org.neostation.overlay.${overlay.id}.$console',
      device: overlay.device,
    );
    // Do not silently remove an image while leaving its reference in info.json.
    for (final file in conversion.files.values) {
      if (!overlay.files.contains(file)) conversion.problems.add('missing indexed resource: $file');
    }
    return conversion;
  }

  Future<LibretroSkinCompatibility> _nativeVerdict(Directory inspection, String console) async {
    final inspect = _inspect ??
        (String directory) => LibretroInternalBridge.inspectSkin(directory: directory, consoleGeometry: skins.consoleGeometry);
    final inspected = await inspect(inspection.path);
    if (inspected['ok'] != true) {
      return LibretroSkinCompatibility.excluded(console, LibretroSkinCompatibility.invalid);
    }
    final rawSummary = inspected['summary'];
    final summary = rawSummary is Map ? rawSummary : const <Object?, Object?>{};
    final verdict = LibretroSkinCompatibility.fromSummary(summary['compatibility'])[console];
    if (verdict != null) return verdict;
    // The native filter reports every console the skin declares: a console
    // without a report is one the skin's info.json does not name.
    final consoles = summary['consoles'];
    final declared = consoles is List && consoles.contains(console);
    return LibretroSkinCompatibility.excluded(
      console,
      declared ? LibretroSkinCompatibility.invalid : LibretroSkinCompatibility.otherConsole,
    );
  }

  /// Hidden from the catalogs of [console]: refused by the central filter,
  /// except a check that could not reach the file (shown, the install
  /// re-checks it). On an iPad ([tablet]) only the refusals that do not
  /// depend on the iPhone's screen hide an entry.
  static bool hidden(LibretroSkinCompatibility? verdict, {bool tablet = false}) {
    if (verdict == null || verdict.offered) return false;
    if (verdict.reasons.contains(LibretroSkinCompatibility.unreachable)) return false;
    if (!tablet) return true;
    return verdict.reasons.any(LibretroSkinCompatibility.deviceIndependentReasons.contains);
  }

  // ---- Favorites ----

  File get _favoritesFile => File(path.join(path.dirname(skins.skinsDirectory), favoritesFileName));

  Future<Set<String>> favorites() async {
    final loaded = _favorites;
    if (loaded != null) return loaded;
    final favorites = <String>{};
    try {
      final file = _favoritesFile;
      if (await file.exists()) {
        final json = jsonDecode(await file.readAsString());
        if (json is List) favorites.addAll(json.whereType<String>());
      }
    } catch (error) {
      _log.w('Skin favorites unreadable: $error');
    }
    return _favorites = favorites;
  }

  Future<void> setFavorite(LibretroCatalogSkin entry, bool favorite) async {
    final favorites = await this.favorites();
    if (favorite ? !favorites.add(entry.key) : !favorites.remove(entry.key)) return;
    try {
      final file = _favoritesFile;
      await file.parent.create(recursive: true);
      final partial = File('${file.path}.part');
      await partial.writeAsString(jsonEncode(favorites.toList()..sort()), flush: true);
      await partial.rename(file.path);
    } catch (error) {
      _log.w('Skin favorites not written: $error');
    }
  }

  // ---- Installation ----

  /// Downloads and installs an entry for [console] through the same import
  /// as Files (limits, native parser, iPhone filter, replacement).
  Future<LibretroSkinImportResult> install(LibretroCatalogSkin entry, String console) async {
    final archive = entry.archive;
    if (archive != null) return provenance.download(archive, targetConsole: console);
    final overlay = entry.overlay;
    if (overlay == null) return const LibretroSkinImportFailed(LibretroSkinMessages.importFailed);
    final folder = Directory(path.join(skins.cacheDirectory, LibretroSkinCatalogService.downloadsFolderName));
    final zip = File(path.join(folder.path, '${_randomName()}.zip'));
    try {
      final conversion = await _convert(overlay, console);
      if (!conversion.converted) {
        return LibretroSkinImportFailed(
          LibretroSkinMessages.notPlayable,
          technicalDetails: conversion.problems.join('; '),
          compatibility: <LibretroSkinCompatibility>[
            LibretroSkinCompatibility.excluded(console, LibretroSkinCompatibility.overlayUnsupported),
          ],
        );
      }
      final bundle = Archive();
      final info = utf8.encode(jsonEncode(conversion.info));
      bundle.addFile(ArchiveFile('info.json', info.length, info));
      var total = info.length;
      for (final file in conversion.files.entries) {
        final bytes = await _readOverlayFile(overlay, file.value,
            min(16 * 1024 * 1024, LibretroSkinService.maxArchiveBytes - total));
        total += bytes.length;
        bundle.addFile(ArchiveFile(file.key, bytes.length, bytes));
      }
      await folder.create(recursive: true);
      await zip.writeAsBytes(ZipEncoder().encode(bundle), flush: true);
      return await skins.importFromFile(
        zip.path,
        source: overlay.webURL,
        author: entry.author,
        license: entry.license,
        targetConsole: console,
      );
    } on LibretroRemoteSkinInspectionException catch (error) {
      return LibretroSkinImportFailed(LibretroSkinMessages.download, technicalDetails: '$error');
    } on FormatException catch (error) {
      return LibretroSkinImportFailed(LibretroSkinMessages.importFailed, technicalDetails: '$error');
    } on TimeoutException catch (error) {
      return LibretroSkinImportFailed(LibretroSkinMessages.download, technicalDetails: '$error');
    } on IOException catch (error) {
      return LibretroSkinImportFailed(LibretroSkinMessages.download, technicalDetails: '$error');
    } on http.ClientException catch (error) {
      return LibretroSkinImportFailed(LibretroSkinMessages.download, technicalDetails: '$error');
    } finally {
      try {
        if (await zip.exists()) await zip.delete();
      } catch (_) {}
    }
  }

  /// The same converted layout and native compositor used by gameplay. Never
  /// substitute an individual descriptor image for a complete controller.
  /// At most two compositions/downloads run together; pinned PNGs work offline.
  Future<Map<String, Uint8List>> overlayPreviews(LibretroOverlayEntry overlay, String console) {
    final key = sha256.convert(utf8.encode(jsonEncode([
      rulesVersion, overlay.repository, overlay.commit, overlay.path, overlay.device,
      console, skins.consoleGeometry,
    ]))).toString();
    final existing = _previews[key];
    if (existing != null) return existing;
    // The disk cache remains authoritative when scrolling back through a large catalog.
    if (_previews.length >= 32) _previews.remove(_previews.keys.first);
    final worker = _nextPreviewWorker++ % _previewWorkers.length;
    final future = _previewWorkers[worker].then((_) => _composeOverlay(overlay, console, key));
    _previewWorkers[worker] = future.then<void>((_) {});
    return _previews[key] = future;
  }

  Future<Uint8List> _readOverlayFile(LibretroOverlayEntry overlay, String file, int limit) async {
    if (_disposed || limit <= 0) throw const LibretroRemoteSkinInspectionException('download cancelled or too large');
    final response = await _client.send(http.Request('GET', overlay.fileUri(file)))
        .timeout(LibretroSkinCatalogService.requestTimeout);
    if (response.statusCode != 200 || (response.contentLength ?? 0) > limit) {
      await response.stream.listen((_) {}).cancel();
      throw LibretroRemoteSkinInspectionException('HTTP ${response.statusCode} or oversized resource: $file', network: true);
    }
    final bytes = BytesBuilder(copy: false);
    await for (final chunk in response.stream.timeout(LibretroSkinCatalogService.requestTimeout)) {
      if (_disposed || bytes.length + chunk.length > limit) {
        throw const LibretroRemoteSkinInspectionException('resource exceeds download limit');
      }
      bytes.add(chunk);
    }
    return bytes.takeBytes();
  }

  Future<Map<String, Uint8List>> _composeOverlay(LibretroOverlayEntry overlay, String console, String key) async {
    final folder = Directory(path.join(skins.cacheDirectory, 'OverlayPreviews'));
    final manifest = File(path.join(folder.path, '$key.json'));
    Directory? staging;
    try {
      if (_disposed) return {};
      if (await manifest.exists()) {
        try {
          final orientations = (jsonDecode(await manifest.readAsString()) as List).whereType<String>();
          final cached = <String, Uint8List>{};
          for (final orientation in orientations) {
            if (orientation != 'portrait' && orientation != 'landscape') throw const FormatException('orientation');
            cached[orientation] = await File(path.join(folder.path, '$key-$orientation.png')).readAsBytes();
          }
          return cached;
        } catch (_) {
          await manifest.delete(); // Eviction/interruption: regenerate the entire preview.
        }
      }
      final conversion = await _convert(overlay, console);
      if (!conversion.converted) return {};
      await folder.create(recursive: true);
      // A parser-safe skin id. No installed skin or selection is changed.
      final stagingRoot = await Directory(path.join(folder.path, 'staging')).create(recursive: true);
      staging = await stagingRoot.createTemp();
      final skin = await Directory(path.join(staging.path, key)).create();
      final info = utf8.encode(jsonEncode(conversion.info));
      await File(path.join(skin.path, 'info.json')).writeAsBytes(info);
      var total = info.length;
      for (final file in conversion.files.entries) {
        final bytes = await _readOverlayFile(overlay, file.value,
            min(16 * 1024 * 1024, LibretroSkinService.maxArchiveBytes - total));
        total += bytes.length;
        final target = File(path.join(skin.path, file.key));
        await target.parent.create(recursive: true);
        await target.writeAsBytes(bytes);
      }
      final result = <String, Uint8List>{};
      for (final orientation in conversion.orientations) {
        final portrait = orientation == 'portrait';
        final width = overlay.device == 'ipad' ? (portrait ? 768.0 : 1024.0) : (portrait ? 390.0 : 844.0);
        final height = overlay.device == 'ipad' ? (portrait ? 1024.0 : 768.0) : (portrait ? 844.0 : 390.0);
        final renderer = _renderPreview;
        final png = renderer != null
            ? await renderer(skin.path, console, orientation, width, height)
            : await LibretroInternalBridge.skinPreview(
                skinDirectory: skin.path, console: console, orientation: orientation,
                width: width, height: height, scale: 1,
                consoleGeometry: skins.consoleGeometry, cacheDirectory: staging.path);
        if (png == null || png.isEmpty) return {}; // No partial preview presented as complete.
        result[orientation] = png;
      }
      // Commit the manifest last; interrupted writes are never used as complete.
      for (final entry in result.entries) {
        await File(path.join(folder.path, '$key-${entry.key}.png')).writeAsBytes(entry.value, flush: true);
      }
      await manifest.writeAsString(jsonEncode(result.keys.toList()), flush: true);
      await _trimOverlayPreviews(folder, key);
      return result;
    } catch (error) {
      _log.w('Overlay preview unavailable (${overlay.path}): $error');
      return {};
    } finally {
      if (staging != null) {
        try { await staging.delete(recursive: true); } catch (_) {}
      }
    }
  }

  static Future<void> _trimOverlayPreviews(Directory folder, String keep) async {
    final files = <File, FileStat>{};
    await for (final entity in folder.list()) {
      if (entity is File) files[entity] = await entity.stat();
    }
    var bytes = files.values.fold<int>(0, (sum, stat) => sum + stat.size);
    final oldest = files.keys.toList()..sort((a, b) => files[a]!.modified.compareTo(files[b]!.modified));
    for (final file in oldest) {
      if (bytes <= 32 * 1024 * 1024) break;
      if (path.basename(file.path).startsWith(keep)) continue;
      bytes -= files[file]!.size;
      try { await file.delete(); } catch (_) {}
    }
  }

  void dispose() {
    _disposed = true;
    provenance.dispose();
    if (_ownsClient) _client.close();
  }

  static String _randomName() {
    final random = Random.secure();
    return List<String>.generate(8, (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
  }
}
