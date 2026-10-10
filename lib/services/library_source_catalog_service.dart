import 'dart:async';
import 'dart:convert';
import 'dart:io' as io;
import 'dart:isolate';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart' show sha256;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'library_addon_service.dart';
import 'library_http.dart';

/// Source catalogues of the reading Library (Build 437).
///
/// A pasted catalogue address is first *previewed*: the document is fetched
/// and parsed, nothing is installed. The user then *activates* the sources
/// they select; only those become [LibraryAddon]s. Supported documents:
/// * Aidoku legacy index (top-level array, `file`/`icon`/`lang`/`nsfw`);
/// * Aidoku index (`{name, sources: [...]}` with `downloadURL`/`iconURL`/
///   `languages`/`contentRating`);
/// * a single Aidoku `source.json` (legacy `info.lang`, new `info.languages`);
/// * an Aidoku `.aix` package: only `Payload/source.json` and the icon are
///   read from the ZIP, `main.wasm` is never executed;
/// * a NeoStation `neostation.library.v1` manifest;
/// * Tachiyomi/Mihon repositories, listed as metadata only (their Android
///   extensions cannot run on iOS, so they are never activated).
///
/// Services never return user-facing text: failures are
/// [LibraryCatalogException]s with a [LibraryCatalogErrorKind] the UI
/// translates, the raw technical detail being kept separately.

/// Kind of document a catalogue address resolved to.
enum LibraryCatalogFormat {
  aidokuLegacyIndex,
  aidokuIndex,
  aidokuSourceJson,
  aidokuPackage,
  neoStationManifest,
  tachiyomiRepository;

  /// Sources of this format can be activated on iOS.
  bool get isActivatable => this != tachiyomiRepository;

  bool get isAidoku =>
      this == aidokuLegacyIndex ||
      this == aidokuIndex ||
      this == aidokuSourceJson ||
      this == aidokuPackage;
}

enum LibraryCatalogErrorKind {
  /// The input is not a usable URL (empty, unparsable, unsupported deep link).
  invalidUrl,

  /// The address does not use HTTPS.
  notHttps,

  /// No catalogue document exists at the address (every candidate 404/410).
  notFound,

  /// The document could not be decoded (not JSON, broken ZIP, missing
  /// `source.json`, invalid NeoStation manifest...).
  invalidDocument,

  /// Valid JSON that is not a supported catalogue format.
  unsupportedFormat,

  /// A supported catalogue that lists no usable source.
  emptyCatalog,

  /// The document or package exceeds the size limits.
  tooLarge,

  /// Network failure; see [LibraryCatalogException.network].
  network,

  /// The catalogue cannot be activated on iOS (Tachiyomi/Mihon).
  notActivatable,
}

class LibraryCatalogException implements Exception {
  const LibraryCatalogException(
    this.kind, {
    this.uri,
    this.network,
    this.detail,
  });

  final LibraryCatalogErrorKind kind;
  final Uri? uri;

  /// Typed network failure for [LibraryCatalogErrorKind.network] (and the
  /// last miss for [LibraryCatalogErrorKind.notFound]).
  final LibraryNetworkException? network;

  /// Raw technical detail (English, untranslated).
  final String? detail;

  @override
  String toString() {
    final parts = <String>[
      kind.name,
      if (uri != null) uri.toString(),
      if (network != null) network.toString(),
      if (detail != null && detail!.isNotEmpty) detail!,
    ];
    return 'LibraryCatalogException(${parts.join(', ')})';
  }
}

/// One source listed by a previewed catalogue.
class LibraryCatalogSourceEntry {
  const LibraryCatalogSourceEntry({
    required this.id,
    required this.addonId,
    required this.name,
    required this.version,
    required this.versionLabel,
    this.languages = const <String>[],
    this.contentRating = LibraryAddon.contentRatingSafe,
    this.iconUrl,
    this.iconBytes,
    this.downloadUrl,
    this.websiteUrl,
    this.altNames = const <String>[],
    this.minAppVersion,
    this.maxAppVersion,
    this.activatable = true,
    this.alreadyInstalled = false,
    this.installedVersion,
    this.installedVersionLabel,
    this.updateAvailable = false,
    this.legacyAidokuFormat,
    this.packageSha256,
    this.packageSize,
    this.packageName,
    this.manifest,
  });

  /// Identifier published by the catalogue (Aidoku `id`, NeoStation manifest
  /// id, Tachiyomi source id). This is what [LibrarySourceCatalogService.activate]
  /// selects.
  final String id;

  /// Id of the [LibraryAddon] that activation creates or replaces.
  final String addonId;
  final String name;

  /// Integer version (Aidoku). 0 when the catalogue has none.
  final int version;

  /// Version as published (`1.0.0` for NeoStation manifests).
  final String versionLabel;
  final List<String> languages;

  /// 0 safe, 1 contains NSFW, 2 primarily NSFW (`contentRating ?? nsfw ?? 0`).
  final int contentRating;
  final String? iconUrl;

  /// Icon read from an `.aix` package (no URL exists for it).
  final Uint8List? iconBytes;

  /// Package (`.aix`, Tachiyomi APK) URL, informational on iOS.
  final String? downloadUrl;

  /// The source's own website, when the catalogue publishes it.
  final String? websiteUrl;
  final List<String> altNames;

  /// Aidoku app versions; informational only, never compared with
  /// NeoStation's version.
  final String? minAppVersion;
  final String? maxAppVersion;

  /// False for Tachiyomi/Mihon sources (metadata only on iOS).
  final bool activatable;
  final bool alreadyInstalled;
  final int? installedVersion;
  final String? installedVersionLabel;

  /// The catalogue offers a newer version than the installed one.
  final bool updateAvailable;

  /// For `source.json` / `.aix`: true when the package uses the legacy Aidoku
  /// format (`info.lang`), false for the current one (`info.languages`).
  final bool? legacyAidokuFormat;

  /// SHA-256 and size of a previewed `.aix` package.
  final String? packageSha256;
  final int? packageSize;

  /// Tachiyomi/Mihon extension package.
  final String? packageName;

  /// NeoStation manifest installed by activation.
  final Map<String, dynamic>? manifest;

  bool get isAdultOnly =>
      contentRating >= LibraryAddon.contentRatingPrimarilyNsfw;

  LibraryCatalogSourceEntry withInstallState({
    required bool alreadyInstalled,
    int? installedVersion,
    String? installedVersionLabel,
    required bool updateAvailable,
  }) => LibraryCatalogSourceEntry(
    id: id,
    addonId: addonId,
    name: name,
    version: version,
    versionLabel: versionLabel,
    languages: languages,
    contentRating: contentRating,
    iconUrl: iconUrl,
    iconBytes: iconBytes,
    downloadUrl: downloadUrl,
    websiteUrl: websiteUrl,
    altNames: altNames,
    minAppVersion: minAppVersion,
    maxAppVersion: maxAppVersion,
    activatable: activatable,
    alreadyInstalled: alreadyInstalled,
    installedVersion: installedVersion,
    installedVersionLabel: installedVersionLabel,
    updateAvailable: updateAvailable,
    legacyAidokuFormat: legacyAidokuFormat,
    packageSha256: packageSha256,
    packageSize: packageSize,
    packageName: packageName,
    manifest: manifest,
  );
}

/// Result of [LibrarySourceCatalogService.preview]. Nothing is installed.
class LibraryCatalogPreview {
  const LibraryCatalogPreview({
    required this.inputUrl,
    required this.catalogUrl,
    required this.documentUrl,
    required this.resolvedUrl,
    required this.format,
    required this.name,
    required this.sources,
    required this.fetchedAt,
    this.notModified = false,
    this.fromCache = false,
    this.stale = false,
  });

  /// The input as typed (trimmed).
  final String inputUrl;

  /// Canonical catalogue address: deep links unwrapped, GitHub `blob` links
  /// rewritten to raw. Identity of a remembered catalogue and the
  /// `repositoryOrigin` of activated sources. `file:<name>` for a local file.
  final String catalogUrl;

  /// Address that served the document (for a directory URL, the
  /// `index.min.json` / `index.json` that was found).
  final String documentUrl;

  /// Final address after redirects; relative URLs were resolved against it.
  final String resolvedUrl;
  final LibraryCatalogFormat format;

  /// Name published by the catalogue (new Aidoku index, `source.json`,
  /// NeoStation manifest); null for legacy lists, which have none.
  final String? name;
  final List<LibraryCatalogSourceEntry> sources;
  final DateTime fetchedAt;

  /// The server confirmed the cached copy (HTTP 304).
  final bool notModified;
  final bool fromCache;

  /// Served from an expired cache entry because the network failed.
  final bool stale;

  bool get isActivatable => format.isActivatable;
  bool get isLocalFile => !catalogUrl.startsWith('https://');

  LibraryCatalogSourceEntry? sourceById(String id) {
    for (final entry in sources) {
      if (entry.id == id) return entry;
    }
    return null;
  }
}

/// Catalogue remembered for later refreshes.
class LibraryStoredCatalog {
  const LibraryStoredCatalog({
    required this.url,
    required this.format,
    required this.lastFetchedAt,
    required this.sourceCount,
    this.name,
    this.documentUrl,
    this.addedAt,
  });

  /// [LibraryCatalogPreview.catalogUrl].
  final String url;
  final String? name;
  final LibraryCatalogFormat format;
  final DateTime lastFetchedAt;
  final int sourceCount;

  /// Address that served the document last time (tried first on refresh).
  final String? documentUrl;
  final DateTime? addedAt;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'url': url,
    'name': ?name,
    'format': format.name,
    'lastFetchedAt': lastFetchedAt.toUtc().toIso8601String(),
    'sourceCount': sourceCount,
    'documentUrl': ?documentUrl,
    'addedAt': ?addedAt?.toUtc().toIso8601String(),
  };

  /// Null when [json] is not a valid stored catalogue.
  static LibraryStoredCatalog? fromJson(Object? json) {
    if (json is! Map) return null;
    final url = json['url'];
    final format = LibraryCatalogFormat.values.asNameMap()[json['format']];
    final lastFetchedAt = DateTime.tryParse(
      json['lastFetchedAt']?.toString() ?? '',
    );
    if (url is! String || url.trim().isEmpty) return null;
    if (format == null || lastFetchedAt == null) return null;
    final count = json['sourceCount'];
    final name = json['name'];
    final documentUrl = json['documentUrl'];
    return LibraryStoredCatalog(
      url: url.trim(),
      name: name is String && name.trim().isNotEmpty ? name.trim() : null,
      format: format,
      lastFetchedAt: lastFetchedAt,
      sourceCount: count is int && count >= 0 ? count : 0,
      documentUrl: documentUrl is String && documentUrl.isNotEmpty
          ? documentUrl
          : null,
      addedAt: DateTime.tryParse(json['addedAt']?.toString() ?? ''),
    );
  }
}

enum LibraryActivationSkipReason {
  /// The id is not listed by the previewed catalogue.
  notInCatalog,

  /// The source cannot run on iOS (Tachiyomi/Mihon).
  notActivatable,

  /// A higher version is already installed (highest version wins).
  newerVersionInstalled,

  /// The entry cannot form a valid add-on (see [LibraryActivationSkip.detail]).
  invalidEntry,
}

class LibraryActivationSkip {
  const LibraryActivationSkip({
    required this.id,
    required this.reason,
    this.offeredVersion,
    this.installedVersion,
    this.minAppVersion,
    this.detail,
  });

  final String id;
  final LibraryActivationSkipReason reason;
  final String? offeredVersion;
  final String? installedVersion;

  /// Aidoku `minAppVersion`, informational only.
  final String? minAppVersion;

  /// Raw technical detail (English, untranslated).
  final String? detail;
}

/// Outcome of [LibrarySourceCatalogService.activate].
class LibraryActivationResult {
  const LibraryActivationResult({
    required this.added,
    required this.updated,
    required this.skipped,
    this.catalogRemembered = false,
  });

  final List<LibraryAddon> added;
  final List<LibraryAddon> updated;
  final List<LibraryActivationSkip> skipped;

  /// The catalogue was saved for later refreshes (false for local files, an
  /// empty selection, or when the catalogue list could not be written).
  final bool catalogRemembered;

  bool get changed => added.isNotEmpty || updated.isNotEmpty;
}

/// Canonical catalogue address and the document URLs tried, in order.
class LibraryCatalogLocation {
  const LibraryCatalogLocation({
    required this.catalogUri,
    required this.candidates,
  });

  final Uri catalogUri;
  final List<Uri> candidates;
}

/// Persistence of remembered catalogues.
abstract class LibraryCatalogStore {
  Future<List<LibraryStoredCatalog>> read();
  Future<void> write(List<LibraryStoredCatalog> catalogs);
}

/// `Application Support/Library/catalogs.json`, written atomically.
class LibraryCatalogFileStore implements LibraryCatalogStore {
  LibraryCatalogFileStore({Future<io.Directory> Function()? directory})
    : _directory = directory ?? _defaultDirectory;

  static const String fileName = 'catalogs.json';
  static const String schema = 'neostation.library.catalogs.v1';

  final Future<io.Directory> Function() _directory;

  static Future<io.Directory> _defaultDirectory() async {
    final support = await getApplicationSupportDirectory();
    return io.Directory(p.join(support.path, 'Library'));
  }

  @override
  Future<List<LibraryStoredCatalog>> read() async {
    final directory = await _directory();
    final file = io.File(p.join(directory.path, fileName));
    if (!await file.exists()) return <LibraryStoredCatalog>[];
    // An I/O failure propagates: the caller must not overwrite a file it
    // could not read.
    final raw = utf8.decode(await file.readAsBytes(), allowMalformed: true);
    Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      decoded = null;
    }
    final list = decoded is Map ? decoded['catalogs'] : decoded;
    if (list is! List) {
      // Keep the unreadable file for diagnosis instead of losing it on the
      // next write.
      try {
        await file.copy('${file.path}.corrupt');
      } on io.FileSystemException {
        // Best effort only.
      }
      return <LibraryStoredCatalog>[];
    }
    final result = <LibraryStoredCatalog>[];
    for (final item in list) {
      final catalog = LibraryStoredCatalog.fromJson(item);
      if (catalog != null && result.every((c) => c.url != catalog.url)) {
        result.add(catalog);
      }
    }
    return result;
  }

  @override
  Future<void> write(List<LibraryStoredCatalog> catalogs) async {
    final directory = await _directory();
    await directory.create(recursive: true);
    final file = io.File(p.join(directory.path, fileName));
    final temporary = io.File('${file.path}.tmp');
    await temporary.writeAsString(
      jsonEncode(<String, dynamic>{
        'schema': schema,
        'catalogs': catalogs.map((catalog) => catalog.toJson()).toList(),
      }),
      flush: true,
    );
    await temporary.rename(file.path);
  }
}

/// In-memory store (tests, or callers that do not want persistence).
class LibraryCatalogMemoryStore implements LibraryCatalogStore {
  LibraryCatalogMemoryStore([
    List<LibraryStoredCatalog> initial = const <LibraryStoredCatalog>[],
  ]) : _catalogs = List<LibraryStoredCatalog>.of(initial);

  List<LibraryStoredCatalog> _catalogs;
  int writeCount = 0;

  @override
  Future<List<LibraryStoredCatalog>> read() async =>
      List<LibraryStoredCatalog>.of(_catalogs);

  @override
  Future<void> write(List<LibraryStoredCatalog> catalogs) async {
    _catalogs = List<LibraryStoredCatalog>.of(catalogs);
    writeCount++;
  }
}

class LibrarySourceCatalogService {
  LibrarySourceCatalogService({
    LibraryFetcher? fetcher,
    LibraryAddonService? addons,
    LibraryCatalogStore? store,
    DateTime Function()? clock,
  }) : _fetcher = fetcher ?? _sharedFetch,
       _addons = addons ?? LibraryAddonService.instance,
       _store = store ?? LibraryCatalogFileStore(),
       _clock = clock ?? DateTime.now;

  static final LibrarySourceCatalogService instance =
      LibrarySourceCatalogService();

  /// JSON catalogue documents (Tachiyomi indexes can be several MB).
  static const int maxIndexBytes = 20 * 1024 * 1024;

  /// `.aix` packages.
  static const int maxPackageBytes = 8 * 1024 * 1024;

  /// Sources accepted from one catalogue.
  static const int maxSources = 10000;

  static const int _maxPackageEntryBytes = 1024 * 1024;
  static const int _backgroundParseBytes = 512 * 1024;
  static const Duration _timeout = Duration(seconds: 20);

  static const List<String> _githubBranches = <String>[
    'repo',
    'gh-pages',
    'main',
    'master',
  ];

  final LibraryFetcher _fetcher;
  final LibraryAddonService _addons;
  final LibraryCatalogStore _store;
  final DateTime Function() _clock;

  List<LibraryStoredCatalog>? _catalogs;
  Future<void> _tail = Future<void>.value();

  // Resolved at call time so that creating the service never touches
  // [LibraryHttp.instance].
  static Future<LibraryHttpResponse> _sharedFetch(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) => LibraryHttp.instance.send(request, mode: mode, cancel: cancel);

  // ---------------------------------------------------------------------------
  // Address normalisation
  // ---------------------------------------------------------------------------

  /// Normalises a pasted catalogue address and lists the document URLs to
  /// try, following Aidoku's rules:
  /// * `aidoku://addSourceList?url=…` and
  ///   `https://aidoku.app/add-source-list/?url=…` are unwrapped;
  /// * a missing scheme defaults to HTTPS; `http:` is refused;
  /// * `github.com/<o>/<r>/blob|raw/<ref>/<path>` becomes the raw file and
  ///   `…/tree/<ref>/<path>` the raw directory;
  /// * `github.com/<o>/<r>` tries the usual branches
  ///   (`repo`, `gh-pages`, `main`, `master`);
  /// * an address without path extension is a directory: `index.min.json`,
  ///   then `index.json`, then the address itself are tried.
  /// Known moved repositories are appended as fallbacks.
  static LibraryCatalogLocation resolveInput(String input) {
    var text = _stripWrapping(input);
    Uri? resolved;
    for (var depth = 0; depth < 4 && resolved == null; depth++) {
      if (text.isEmpty) {
        throw const LibraryCatalogException(LibraryCatalogErrorKind.invalidUrl);
      }
      final parsed = Uri.tryParse(text);
      if (parsed == null) {
        throw LibraryCatalogException(
          LibraryCatalogErrorKind.invalidUrl,
          detail: text,
        );
      }
      final scheme = parsed.scheme.toLowerCase();
      if (scheme == 'aidoku') {
        final inner = parsed.host.toLowerCase() == 'addsourcelist'
            ? _wrappedUrl(parsed)
            : null;
        if (inner == null) {
          throw LibraryCatalogException(
            LibraryCatalogErrorKind.invalidUrl,
            uri: parsed,
          );
        }
        text = inner;
        continue;
      }
      if (scheme.isEmpty) {
        if (!_hostLike.hasMatch(text)) {
          throw LibraryCatalogException(
            LibraryCatalogErrorKind.invalidUrl,
            detail: text,
          );
        }
        text = 'https://$text';
        continue;
      }
      if ((scheme == 'https' || scheme == 'http') &&
          _isAidokuAddListPage(parsed)) {
        final inner = _wrappedUrl(parsed);
        if (inner == null) {
          throw LibraryCatalogException(
            LibraryCatalogErrorKind.invalidUrl,
            uri: parsed,
          );
        }
        text = inner;
        continue;
      }
      if (scheme != 'https') {
        throw LibraryCatalogException(
          LibraryCatalogErrorKind.notHttps,
          uri: parsed,
        );
      }
      if (parsed.host.isEmpty) {
        throw LibraryCatalogException(
          LibraryCatalogErrorKind.invalidUrl,
          uri: parsed,
        );
      }
      resolved = parsed.removeFragment();
    }
    if (resolved == null) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.invalidUrl,
        detail: text,
      );
    }
    return _locate(resolved);
  }

  static final RegExp _hostLike = RegExp(
    r'^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+(:\d+)?(/|$)',
  );

  static String _stripWrapping(String input) {
    var text = input.trim();
    while (text.length >= 2) {
      final first = text[0];
      final last = text[text.length - 1];
      if ((first == '<' && last == '>') ||
          (first == '"' && last == '"') ||
          (first == "'" && last == "'")) {
        text = text.substring(1, text.length - 1).trim();
      } else {
        break;
      }
    }
    return text;
  }

  static bool _isAidokuAddListPage(Uri uri) {
    final host = uri.host.toLowerCase();
    return (host == 'aidoku.app' || host == 'www.aidoku.app') &&
        uri.path.toLowerCase().startsWith('/add-source-list');
  }

  /// Value of the `url` query parameter. The Aidoku README links do not
  /// percent-encode it, so an unencoded value keeps everything after `url=`.
  static String? _wrappedUrl(Uri uri) {
    final query = uri.query;
    var start = -1;
    if (query.startsWith('url=')) {
      start = 4;
    } else {
      final index = query.indexOf('&url=');
      if (index >= 0) start = index + 5;
    }
    if (start < 0) return null;
    final remainder = query.substring(start);
    String value;
    if (remainder.contains('://')) {
      value = remainder;
    } else {
      final end = remainder.indexOf('&');
      final encoded = end < 0 ? remainder : remainder.substring(0, end);
      try {
        value = Uri.decodeQueryComponent(encoded);
      } on ArgumentError {
        return null;
      } on FormatException {
        return null;
      }
    }
    value = value.trim();
    return value.isEmpty ? null : value;
  }

  static LibraryCatalogLocation _locate(Uri uri) {
    final host = uri.host.toLowerCase();
    final segments = uri.pathSegments.where((s) => s.isNotEmpty).toList();

    if (host == 'github.com' || host == 'www.github.com') {
      if (segments.length < 2) {
        throw LibraryCatalogException(
          LibraryCatalogErrorKind.invalidUrl,
          uri: uri,
        );
      }
      final owner = segments[0];
      final repo = segments[1].replaceFirst(RegExp(r'\.git$'), '');
      if (segments.length >= 4 &&
          (segments[2] == 'blob' || segments[2] == 'raw')) {
        final rest = segments.sublist(3);
        final trailingSlash = uri.path.endsWith('/');
        return _locate(
          Uri.parse(
            'https://raw.githubusercontent.com/'
            '${_joinSegments([owner, repo, ...rest])}'
            '${trailingSlash ? '/' : ''}',
          ),
        );
      }
      if (segments.length >= 4 && segments[2] == 'tree') {
        return _locate(
          Uri.parse(
            'https://raw.githubusercontent.com/'
            '${_joinSegments([owner, repo, ...segments.sublist(3)])}/',
          ),
        );
      }
      final catalogUri = Uri.parse(
        'https://github.com/${_joinSegments([owner, repo])}',
      );
      final candidates = <Uri>[];
      _addKnownMovedRepositories(candidates, catalogUri);
      for (final branch in _githubBranches) {
        for (final index in const ['index.min.json', 'index.json']) {
          _addCandidate(
            candidates,
            Uri.parse(
              'https://raw.githubusercontent.com/'
              '${_joinSegments([owner, repo, branch, index])}',
            ),
          );
        }
      }
      return LibraryCatalogLocation(
        catalogUri: catalogUri,
        candidates: List.unmodifiable(candidates),
      );
    }

    final candidates = <Uri>[];
    final lastSegment = segments.isEmpty ? '' : segments.last;
    final isDirectory =
        uri.path.isEmpty ||
        uri.path.endsWith('/') ||
        !lastSegment.contains('.');
    if (isDirectory) {
      final directory = uri.path.endsWith('/') ? uri.path : '${uri.path}/';
      _addCandidate(
        candidates,
        uri.replace(path: '${directory}index.min.json'),
      );
      _addCandidate(candidates, uri.replace(path: '${directory}index.json'));
      _addCandidate(candidates, uri);
    } else {
      _addCandidate(candidates, uri);
      if (lastSegment.toLowerCase() == 'index.min.json') {
        final path = uri.path;
        _addCandidate(
          candidates,
          uri.replace(
            path:
                '${path.substring(0, path.length - 'index.min.json'.length)}'
                'index.json',
          ),
        );
      }
    }
    _addKnownMovedRepositories(candidates, uri);
    return LibraryCatalogLocation(
      catalogUri: uri,
      candidates: List.unmodifiable(candidates),
    );
  }

  static String _joinSegments(List<String> segments) =>
      segments.map(Uri.encodeComponent).join('/');

  static void _addCandidate(List<Uri> candidates, Uri uri) {
    if (uri.scheme != 'https' || uri.host.isEmpty) return;
    final text = uri.toString();
    if (candidates.every((candidate) => candidate.toString() != text)) {
      candidates.add(uri);
    }
  }

  /// Repositories that moved or were archived: the addresses users already
  /// have keep resolving (kept from the previous importer).
  static void _addKnownMovedRepositories(List<Uri> candidates, Uri uri) {
    final host = uri.host.toLowerCase();
    if (host != 'raw.githubusercontent.com' && host != 'github.com') return;
    final lowerPath = uri.path.toLowerCase();
    void add(String value) => _addCandidate(candidates, Uri.parse(value));

    if (lowerPath.contains('/almightyhak/aniyomi-anime-repo')) {
      add(
        'https://raw.githubusercontent.com/aniyomi-addons/anime-extensions-repo/repo/index.min.json',
      );
      add(
        'https://raw.githubusercontent.com/aniyomi-addons/anime-extensions-repo/repo/index.json',
      );
    }
    if (lowerPath.contains('/komikku-app/extensions')) {
      add(
        'https://raw.githubusercontent.com/yuzono/manga-repo/repo/index.min.json',
      );
    }
    if (lowerPath.contains('/thepbone/tachiyomi-extensions-revived')) {
      add(
        'https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.min.json',
      );
      add(
        'https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.json',
      );
    }
    if (lowerPath.contains('/moomooo95/aidoku-french-sources')) {
      add(
        'https://raw.githubusercontent.com/Moomooo95/aidoku-french-sources/gh-pages/index.min.json',
      );
      add(
        'https://raw.githubusercontent.com/Moomooo95/aidoku-french-sources/gh-pages/index.json',
      );
    }
  }

  // ---------------------------------------------------------------------------
  // Preview
  // ---------------------------------------------------------------------------

  /// Fetches and parses the catalogue at [input] without installing
  /// anything. Documents use [LibraryCachePolicy.catalogIndex]; with
  /// [refresh] the request is revalidated (`If-None-Match` /
  /// `If-Modified-Since` when validators are cached) instead of being served
  /// from a fresh cache entry. A remembered catalogue gets its metadata
  /// (name, count, last fetch) updated.
  Future<LibraryCatalogPreview> preview(
    String input, {
    LibraryCancelToken? cancel,
    bool refresh = false,
  }) async {
    final location = resolveInput(input);
    final catalogUrl = location.catalogUri.toString();
    final remembered = _findCatalog(await _loadCatalogs(), catalogUrl);

    final candidates = <Uri>[];
    final rememberedDocument = Uri.tryParse(remembered?.documentUrl ?? '');
    if (rememberedDocument != null) {
      _addCandidate(candidates, rememberedDocument);
    }
    for (final candidate in location.candidates) {
      _addCandidate(candidates, candidate);
    }

    final mode = refresh
        ? LibraryFetchMode.refresh
        : LibraryFetchMode.cacheFirst;
    LibraryCatalogException? documentError;
    LibraryNetworkException? lastMiss;

    for (final candidate in candidates) {
      if (cancel?.isCancelled ?? false) {
        throw LibraryCatalogException(
          LibraryCatalogErrorKind.network,
          uri: candidate,
          network: LibraryNetworkException(
            LibraryNetworkErrorKind.cancelled,
            uri: candidate,
          ),
        );
      }
      final isPackage = candidate.path.toLowerCase().endsWith('.aix');
      final LibraryHttpResponse response;
      try {
        response = await _fetcher(
          LibraryRequest.get(
            candidate,
            headers: <String, String>{
              'Accept': isPackage
                  ? 'application/octet-stream, application/zip, */*'
                  : 'application/json, text/plain, */*',
            },
            cache: LibraryCachePolicy.catalogIndex,
            timeout: _timeout,
            maxBytes: isPackage ? maxPackageBytes : maxIndexBytes,
          ),
          mode: mode,
          cancel: cancel,
        );
      } on LibraryNetworkException catch (error) {
        if (_isMiss(error.kind)) {
          lastMiss = error;
          continue;
        }
        throw LibraryCatalogException(
          error.kind == LibraryNetworkErrorKind.tooLarge
              ? LibraryCatalogErrorKind.tooLarge
              : LibraryCatalogErrorKind.network,
          uri: candidate,
          network: error,
        );
      }
      if (!response.ok) {
        final status = response.statusCode;
        lastMiss = LibraryNetworkException(
          status == 404 || status == 410
              ? LibraryNetworkErrorKind.notFound
              : LibraryNetworkErrorKind.httpStatus,
          uri: response.finalUri,
          statusCode: status,
        );
        continue;
      }

      final _ParsedCatalog parsed;
      try {
        parsed = await _parseInBackground(
          response.bodyBytes,
          response.finalUri,
        );
      } on LibraryCatalogException catch (error) {
        documentError ??= error;
        continue;
      }
      final preview = LibraryCatalogPreview(
        inputUrl: input.trim(),
        catalogUrl: catalogUrl,
        documentUrl: candidate.toString(),
        resolvedUrl: response.finalUri.toString(),
        format: parsed.format,
        name: parsed.name,
        sources: await _withInstallState(parsed.entries),
        fetchedAt: response.fetchedAt,
        notModified: response.revalidated,
        fromCache: response.fromCache,
        stale: response.stale,
      );
      if (remembered != null) {
        try {
          await _locked(() => _touchRememberedUnlocked(preview));
        } on Exception {
          // Metadata of the remembered entry stays as it was; the preview
          // itself is valid.
        }
      }
      return preview;
    }

    if (documentError != null) throw documentError;
    if (lastMiss != null && lastMiss.kind != LibraryNetworkErrorKind.notFound) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.network,
        uri: location.catalogUri,
        network: lastMiss,
      );
    }
    throw LibraryCatalogException(
      LibraryCatalogErrorKind.notFound,
      uri: location.catalogUri,
      network: lastMiss,
    );
  }

  /// Previews a catalogue read from a local file (JSON document or `.aix`).
  /// Relative URLs cannot be resolved without a web address: entries keep
  /// only their absolute HTTPS URLs.
  Future<LibraryCatalogPreview> previewDocument(
    List<int> bytes, {
    required String fileName,
  }) async {
    final name = p.basename(fileName.trim().replaceAll('\\', '/'));
    final catalogUrl = 'file:${name.isEmpty ? 'catalog.json' : name}';
    if (bytes.length > maxIndexBytes) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.tooLarge,
        detail: '${bytes.length} bytes',
      );
    }
    final data = bytes is Uint8List ? bytes : Uint8List.fromList(bytes);
    final parsed = await _parseInBackground(data, null);
    return LibraryCatalogPreview(
      inputUrl: fileName,
      catalogUrl: catalogUrl,
      documentUrl: catalogUrl,
      resolvedUrl: catalogUrl,
      format: parsed.format,
      name: parsed.name,
      sources: await _withInstallState(parsed.entries),
      fetchedAt: _clock(),
    );
  }

  static bool _isMiss(LibraryNetworkErrorKind kind) =>
      kind == LibraryNetworkErrorKind.notFound ||
      kind == LibraryNetworkErrorKind.httpStatus ||
      kind == LibraryNetworkErrorKind.invalidResponse;

  Future<List<LibraryCatalogSourceEntry>> _withInstallState(
    List<LibraryCatalogSourceEntry> entries,
  ) async {
    final installed = <String, LibraryAddon>{
      for (final addon in await _addons.load()) addon.id: addon,
    };
    return List.unmodifiable(
      entries.map((entry) {
        final addon = installed[entry.addonId];
        if (addon == null) {
          return entry.withInstallState(
            alreadyInstalled: false,
            updateAvailable: false,
          );
        }
        return entry.withInstallState(
          alreadyInstalled: true,
          installedVersion: addon.versionNumber,
          installedVersionLabel: addon.version,
          updateAvailable:
              compareVersionLabels(entry.versionLabel, addon.version) > 0,
        );
      }),
    );
  }

  /// Compares dotted numeric versions (`12` > `5`, `1.10.0` > `1.9`).
  /// Non-numeric parts are ignored.
  static int compareVersionLabels(String a, String b) {
    List<int> parts(String value) => RegExp(r'\d+')
        .allMatches(value.split(RegExp(r'[-+]')).first)
        .map((match) => int.tryParse(match.group(0)!) ?? 0)
        .toList();
    final left = parts(a);
    final right = parts(b);
    final length = left.length > right.length ? left.length : right.length;
    for (var index = 0; index < length; index++) {
      final x = index < left.length ? left[index] : 0;
      final y = index < right.length ? right[index] : 0;
      if (x != y) return x.compareTo(y);
    }
    return 0;
  }

  // ---------------------------------------------------------------------------
  // Activation
  // ---------------------------------------------------------------------------

  /// Installs exactly the sources of [preview] whose ids are in [sourceIds].
  ///
  /// * Aidoku sources become `aidoku.<id>` add-ons compatible with existing
  ///   installs; the highest version wins when another catalogue already
  ///   installed the same id, and every catalogue offering it is recorded.
  /// * A NeoStation manifest installs that single manifest.
  /// * Aidoku `minAppVersion`/`maxAppVersion` are informational only.
  /// * Tachiyomi/Mihon repositories are refused
  ///   ([LibraryCatalogErrorKind.notActivatable]).
  /// An HTTPS catalogue is remembered when at least one source was selected.
  Future<LibraryActivationResult> activate(
    LibraryCatalogPreview preview,
    Set<String> sourceIds,
  ) {
    if (!preview.format.isActivatable) {
      return Future<LibraryActivationResult>.error(
        LibraryCatalogException(
          LibraryCatalogErrorKind.notActivatable,
          uri: Uri.tryParse(preview.catalogUrl),
          detail: preview.format.name,
        ),
      );
    }
    return _locked(() => _activateUnlocked(preview, sourceIds));
  }

  Future<LibraryActivationResult> _activateUnlocked(
    LibraryCatalogPreview preview,
    Set<String> sourceIds,
  ) async {
    final installed = <String, LibraryAddon>{
      for (final addon in await _addons.load()) addon.id: addon,
    };
    final offered = <String, LibraryCatalogSourceEntry>{
      for (final entry in preview.sources) entry.id: entry,
    };
    final selected = <LibraryCatalogSourceEntry>[];
    final skipped = <LibraryActivationSkip>[];
    for (final id in sourceIds) {
      final entry = offered[id];
      if (entry == null) {
        skipped.add(
          LibraryActivationSkip(
            id: id,
            reason: LibraryActivationSkipReason.notInCatalog,
          ),
        );
      } else if (!entry.activatable) {
        skipped.add(
          LibraryActivationSkip(
            id: id,
            reason: LibraryActivationSkipReason.notActivatable,
          ),
        );
      } else {
        selected.add(entry);
      }
    }

    final aidokuAddons = <LibraryAddon>[];
    final added = <LibraryAddon>[];
    final updated = <LibraryAddon>[];

    for (final entry in selected) {
      final existing = installed[entry.addonId];
      if (existing != null &&
          compareVersionLabels(existing.version, entry.versionLabel) > 0) {
        skipped.add(
          LibraryActivationSkip(
            id: entry.id,
            reason: LibraryActivationSkipReason.newerVersionInstalled,
            offeredVersion: entry.versionLabel,
            installedVersion: existing.version,
            minAppVersion: entry.minAppVersion,
          ),
        );
        if (preview.format.isAidoku &&
            existing.isAidokuRepositorySource &&
            !preview.isLocalFile &&
            !existing.repositoryOrigins.contains(preview.catalogUrl)) {
          aidokuAddons.add(
            _withOrigins(existing, <String>[
              ...existing.repositoryOrigins,
              preview.catalogUrl,
            ]),
          );
        }
        continue;
      }

      if (preview.format == LibraryCatalogFormat.neoStationManifest) {
        final manifest = entry.manifest;
        if (manifest == null) {
          skipped.add(
            LibraryActivationSkip(
              id: entry.id,
              reason: LibraryActivationSkipReason.invalidEntry,
            ),
          );
          continue;
        }
        try {
          // Same validation as a direct manifest import (schema, HTTPS,
          // NeoStation's own minAppVersion).
          final result = await _addons.installDocumentFromJson(
            jsonEncode(manifest),
            origin: preview.catalogUrl,
          );
          final addon = result.addons.single;
          (result.updatedCount > 0 ? updated : added).add(addon);
        } on LibraryAddonException catch (error) {
          skipped.add(
            LibraryActivationSkip(
              id: entry.id,
              reason: LibraryActivationSkipReason.invalidEntry,
              detail: error.message,
            ),
          );
        }
        continue;
      }

      try {
        final addon = _aidokuAddon(preview, entry, existing);
        aidokuAddons.add(addon);
        (existing == null ? added : updated).add(addon);
      } on LibraryAddonException catch (error) {
        skipped.add(
          LibraryActivationSkip(
            id: entry.id,
            reason: LibraryActivationSkipReason.invalidEntry,
            minAppVersion: entry.minAppVersion,
            detail: error.message,
          ),
        );
      }
    }

    if (aidokuAddons.isNotEmpty) await _addons.upsertAddons(aidokuAddons);
    var remembered = false;
    if (selected.isNotEmpty && !preview.isLocalFile) {
      try {
        await _rememberUnlocked(preview);
        remembered = true;
      } on Exception {
        // The sources are installed; only the catalogue list could not be
        // saved. Reported through [LibraryActivationResult.catalogRemembered].
      }
    }
    return LibraryActivationResult(
      added: List.unmodifiable(added),
      updated: List.unmodifiable(updated),
      skipped: List.unmodifiable(skipped),
      catalogRemembered: remembered,
    );
  }

  LibraryAddon _aidokuAddon(
    LibraryCatalogPreview preview,
    LibraryCatalogSourceEntry entry,
    LibraryAddon? existing,
  ) {
    final manifest = LibraryAddon.aidokuSourceManifest(
      sourceId: entry.id,
      name: entry.name,
      version: entry.versionLabel,
      languages: entry.languages,
      contentRating: entry.contentRating,
      repositoryOrigin: preview.catalogUrl,
      repositoryOrigins: existing?.isAidokuRepositorySource == true
          ? existing!.repositoryOrigins
          : const <String>[],
      websiteUrl: entry.websiteUrl ?? existing?.websiteUrl,
      fallbackBaseUrl:
          _folderOf(preview.resolvedUrl) ?? _folderOf(entry.downloadUrl),
      iconUrl: entry.iconUrl ?? existing?.iconUrl,
      downloadUrl: entry.downloadUrl,
      altNames: entry.altNames,
      minAppVersion: entry.minAppVersion,
      maxAppVersion: entry.maxAppVersion,
      catalogFormat: preview.format.name,
      catalogName: preview.name,
      packageSha256: entry.packageSha256,
      packageSize: entry.packageSize,
      legacyPackageFormat: entry.legacyAidokuFormat,
    );
    return LibraryAddon.fromManifest(
      manifest,
      origin: preview.catalogUrl,
      installedAt: existing?.installedAt ?? _clock(),
    );
  }

  static String? _folderOf(String? url) {
    final https = LibraryAddon.httpsUrlOrNull(url);
    return https == null ? null : Uri.parse(https).resolve('.').toString();
  }

  static LibraryAddon _withOrigins(LibraryAddon addon, List<String> origins) {
    final manifest = Map<String, dynamic>.from(addon.manifest);
    final provider = Map<String, dynamic>.from(
      manifest['provider'] as Map? ?? const <String, dynamic>{},
    );
    final unique = <String>[];
    for (final origin in origins) {
      if (origin.isNotEmpty && !unique.contains(origin)) unique.add(origin);
    }
    if (unique.length > 1) {
      provider['repositoryOrigins'] = unique;
    } else {
      provider.remove('repositoryOrigins');
    }
    manifest['provider'] = provider;
    return addon.copyWithManifest(manifest);
  }

  /// Removes one activated source. Favourites and reading progress are keyed
  /// by the Aidoku source id in the reading store and are not touched, so
  /// re-activating the source brings them back.
  Future<bool> deactivate(String addonId) => _addons.remove(addonId);

  // ---------------------------------------------------------------------------
  // Remembered catalogues
  // ---------------------------------------------------------------------------

  /// Remembered catalogues, in the order they were added.
  Future<List<LibraryStoredCatalog>> list() async =>
      List.unmodifiable(await _locked(_loadCatalogs));

  /// Remembers [preview]'s catalogue without activating anything (local
  /// files cannot be refreshed and are not remembered: returns null).
  Future<LibraryStoredCatalog?> remember(LibraryCatalogPreview preview) {
    if (preview.isLocalFile) return Future<LibraryStoredCatalog?>.value();
    return _locked(() => _rememberUnlocked(preview));
  }

  /// Forgets the catalogue [url] (its [LibraryCatalogPreview.catalogUrl], or
  /// any address resolving to it; an origin recorded by older imports such
  /// as `…/index.min.json` also works). With [deactivateSources], the sources
  /// activated from it are removed too (other catalogues' sources stay; a
  /// source also offered by another catalogue only loses this origin).
  /// Returns the number of removed sources.
  Future<int> forget(String url, {bool deactivateSources = false}) {
    return _locked(() async {
      final targets = <String>{url.trim()}..remove('');
      try {
        targets.add(resolveInput(url).catalogUri.toString());
      } on LibraryCatalogException {
        // A `file:` origin or an older stored value: matched as given.
      }
      if (targets.isEmpty) return 0;
      final catalogs = await _loadCatalogs(strict: true);
      final remaining = catalogs
          .where((catalog) => !targets.contains(catalog.url))
          .toList();
      if (remaining.length != catalogs.length) await _saveCatalogs(remaining);
      if (!deactivateSources) return 0;

      final removeIds = <String>[];
      final rewrites = <LibraryAddon>[];
      for (final addon in await _addons.load()) {
        if (!addon.isRepositorySource || addon.isBuiltIn) continue;
        if (targets.contains(addon.repositoryOrigin)) {
          removeIds.add(addon.id);
        } else if (addon.repositoryOrigins.any(targets.contains)) {
          rewrites.add(
            _withOrigins(
              addon,
              addon.repositoryOrigins
                  .where((origin) => !targets.contains(origin))
                  .toList(),
            ),
          );
        }
      }
      if (rewrites.isNotEmpty) await _addons.upsertAddons(rewrites);
      return _addons.removeMany(removeIds);
    });
  }

  /// Updates a remembered catalogue after a fetch; never adds one.
  Future<void> _touchRememberedUnlocked(LibraryCatalogPreview preview) async {
    final catalogs = await _loadCatalogs();
    if (_findCatalog(catalogs, preview.catalogUrl) == null) return;
    await _rememberUnlocked(preview);
  }

  Future<LibraryStoredCatalog> _rememberUnlocked(
    LibraryCatalogPreview preview,
  ) async {
    final catalogs = await _loadCatalogs(strict: true);
    final index = catalogs.indexWhere((c) => c.url == preview.catalogUrl);
    final previous = index >= 0 ? catalogs[index] : null;
    final stored = LibraryStoredCatalog(
      url: preview.catalogUrl,
      name: preview.name ?? previous?.name,
      format: preview.format,
      lastFetchedAt: preview.fetchedAt,
      sourceCount: preview.sources.length,
      documentUrl: preview.documentUrl,
      addedAt: previous?.addedAt ?? _clock(),
    );
    final next = List<LibraryStoredCatalog>.of(catalogs);
    if (index >= 0) {
      next[index] = stored;
    } else {
      next.add(stored);
    }
    await _saveCatalogs(next);
    return stored;
  }

  static LibraryStoredCatalog? _findCatalog(
    List<LibraryStoredCatalog> catalogs,
    String url,
  ) {
    for (final catalog in catalogs) {
      if (catalog.url == url) return catalog;
    }
    return null;
  }

  /// Remembered catalogues, read once. A failed read is not cached; [strict]
  /// callers (those about to write) get the error instead of an empty list,
  /// so an unreadable file is never overwritten.
  Future<List<LibraryStoredCatalog>> _loadCatalogs({
    bool strict = false,
  }) async {
    final cached = _catalogs;
    if (cached != null) return cached;
    try {
      return _catalogs = List.unmodifiable(await _store.read());
    } on Exception {
      if (strict) rethrow;
      return const <LibraryStoredCatalog>[];
    }
  }

  Future<void> _saveCatalogs(List<LibraryStoredCatalog> catalogs) async {
    final next = List<LibraryStoredCatalog>.unmodifiable(catalogs);
    await _store.write(next);
    _catalogs = next;
  }

  /// Serialises catalogue/add-on mutations.
  Future<T> _locked<T>(Future<T> Function() action) {
    final previous = _tail;
    final done = Completer<void>();
    _tail = done.future;
    return previous.then((_) => action()).whenComplete(done.complete);
  }

  // ---------------------------------------------------------------------------
  // Parsing (pure, may run on a background isolate)
  // ---------------------------------------------------------------------------

  static Future<_ParsedCatalog> _parseInBackground(Uint8List bytes, Uri? base) {
    if (bytes.length < _backgroundParseBytes) {
      return Future<_ParsedCatalog>.sync(() => _parseDocument(bytes, base));
    }
    return Isolate.run(() => _parseDocument(bytes, base));
  }

  static _ParsedCatalog _parseDocument(Uint8List bytes, Uri? base) {
    if (_isZip(bytes)) return _parsePackage(bytes, base);
    final String text;
    try {
      text = utf8.decode(bytes);
    } on FormatException catch (error) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.invalidDocument,
        uri: base,
        detail: 'Not UTF-8: ${error.message}',
      );
    }
    final Object? decoded;
    try {
      decoded = jsonDecode(_withoutByteOrderMark(text));
    } on FormatException catch (error) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.invalidDocument,
        uri: base,
        detail: 'Not JSON: ${error.message}',
      );
    }
    return _classify(decoded, base);
  }

  static _ParsedCatalog _classify(Object? decoded, Uri? base) {
    if (decoded is Map) {
      final document = Map<String, dynamic>.from(decoded);
      final schema = document['schema'];
      if (schema != null) {
        if (schema == LibraryAddon.schemaV1) {
          return _parseNeoStationManifest(document, base);
        }
        throw LibraryCatalogException(
          LibraryCatalogErrorKind.unsupportedFormat,
          uri: base,
          detail: 'schema $schema',
        );
      }
      final info = document['info'];
      if (info is Map && info['id'] != null) {
        return _parseSourceJson(
          document,
          base,
          format: LibraryCatalogFormat.aidokuSourceJson,
        );
      }
      final sources = document['sources'];
      if (sources is List) {
        if (sources.isEmpty) {
          throw LibraryCatalogException(
            LibraryCatalogErrorKind.emptyCatalog,
            uri: base,
          );
        }
        if (sources.whereType<Map>().any((s) => s.containsKey('pkg'))) {
          return _parseTachiyomi(
            sources,
            base,
            _optionalString(document['name']),
          );
        }
        return _ParsedCatalog(
          format: LibraryCatalogFormat.aidokuIndex,
          name: _optionalString(document['name']),
          entries: _parseAidokuEntries(sources, base),
        );
      }
      final extensionList = document['extensionList'];
      if (extensionList is Map && extensionList['extensions'] is List) {
        return _parseTachiyomi(
          _modernTachiyomiExtensions(extensionList['extensions'] as List),
          base,
          _optionalString(document['name']),
        );
      }
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.unsupportedFormat,
        uri: base,
      );
    }
    if (decoded is List) {
      if (decoded.isEmpty) {
        throw LibraryCatalogException(
          LibraryCatalogErrorKind.emptyCatalog,
          uri: base,
        );
      }
      final maps = decoded.whereType<Map>();
      if (maps.any((entry) => entry.containsKey('pkg'))) {
        return _parseTachiyomi(decoded, base, null);
      }
      if (maps.any(_looksLikeAidokuEntry)) {
        return _ParsedCatalog(
          format: LibraryCatalogFormat.aidokuLegacyIndex,
          name: null,
          entries: _parseAidokuEntries(decoded, base),
        );
      }
    }
    throw LibraryCatalogException(
      LibraryCatalogErrorKind.unsupportedFormat,
      uri: base,
    );
  }

  static bool _looksLikeAidokuEntry(Map entry) {
    if (entry.containsKey('pkg')) return false;
    if (_optionalString(entry['id']) == null) return false;
    if (_optionalString(entry['name']) == null) return false;
    return entry.containsKey('file') ||
        entry.containsKey('downloadURL') ||
        entry.containsKey('downloadUrl') ||
        entry.containsKey('languages') ||
        entry.containsKey('lang');
  }

  /// Aidoku index entries, resolved like Aidoku's `ExternalSourceInfo`:
  /// `downloadURL` relative to the list, else `sources/<file>`; `iconURL`,
  /// else `icons/<icon>`; languages `languages ?? [lang]`; rating
  /// `contentRating ?? nsfw ?? 0`. Duplicate ids keep the highest version.
  static List<LibraryCatalogSourceEntry> _parseAidokuEntries(
    List<dynamic> rawEntries,
    Uri? base,
  ) {
    final byId = <String, LibraryCatalogSourceEntry>{};
    var accepted = 0;
    for (final raw in rawEntries) {
      if (raw is! Map || raw.containsKey('pkg')) continue;
      final id = _optionalString(raw['id']);
      final name = _optionalString(raw['name']);
      if (id == null || name == null) continue;
      if (++accepted > maxSources) {
        throw LibraryCatalogException(
          LibraryCatalogErrorKind.tooLarge,
          uri: base,
          detail: 'more than $maxSources sources',
        );
      }
      final version = _int(raw['version']) ?? 0;
      var languages = LibraryAddon.stringList(raw['languages']);
      if (languages.isEmpty) {
        final lang = _optionalString(raw['lang']);
        if (lang != null) languages = <String>[lang];
      }
      final file = _optionalString(raw['file']);
      final icon = _optionalString(raw['icon']);
      final entry = LibraryCatalogSourceEntry(
        id: id,
        addonId: LibraryAddon.aidokuAddonId(id),
        name: name,
        version: version,
        versionLabel: '$version',
        languages: languages,
        contentRating: LibraryAddon.normalizeContentRating(
          raw['contentRating'],
          raw['nsfw'],
        ),
        downloadUrl:
            _resolveHttps(raw['downloadURL'] ?? raw['downloadUrl'], base) ??
            _resolveHttps(file, base, folder: 'sources'),
        iconUrl:
            _resolveHttps(raw['iconURL'] ?? raw['iconUrl'], base) ??
            _resolveHttps(icon, base, folder: 'icons'),
        websiteUrl: LibraryAddon.httpsUrlOrNull(
          raw['baseURL'] ?? raw['baseUrl'],
        ),
        altNames: LibraryAddon.stringList(raw['altNames']),
        minAppVersion: _optionalString(raw['minAppVersion']),
        maxAppVersion: _optionalString(raw['maxAppVersion']),
      );
      final previous = byId[id];
      if (previous == null || entry.version > previous.version) {
        byId[id] = entry;
      }
    }
    if (byId.isEmpty) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.emptyCatalog,
        uri: base,
      );
    }
    return List.unmodifiable(byId.values);
  }

  static _ParsedCatalog _parseSourceJson(
    Map<String, dynamic> document,
    Uri? base, {
    required LibraryCatalogFormat format,
    String? packageUrl,
    Uint8List? iconBytes,
    String? packageSha256,
    int? packageSize,
  }) {
    final info = document['info'];
    if (info is! Map) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.invalidDocument,
        uri: base,
        detail: 'source.json without info',
      );
    }
    final id = _optionalString(info['id']);
    final name = _optionalString(info['name']);
    if (id == null || name == null) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.invalidDocument,
        uri: base,
        detail: 'source.json without info.id/info.name',
      );
    }
    final declaredLanguages = info['languages'];
    final legacy = declaredLanguages is! List && info['lang'] is String;
    var languages = LibraryAddon.stringList(declaredLanguages);
    if (languages.isEmpty) {
      final lang = _optionalString(info['lang']);
      if (lang != null) languages = <String>[lang];
    }
    String? website;
    for (final candidate in <Object?>[
      info['url'],
      ...LibraryAddon.stringList(info['urls']),
    ]) {
      website = LibraryAddon.httpsUrlOrNull(candidate);
      if (website != null) break;
    }
    final version = _int(info['version']) ?? 0;
    final entry = LibraryCatalogSourceEntry(
      id: id,
      addonId: LibraryAddon.aidokuAddonId(id),
      name: name,
      version: version,
      versionLabel: '$version',
      languages: languages,
      contentRating: LibraryAddon.normalizeContentRating(
        info['contentRating'],
        info['nsfw'],
      ),
      // Next to a published source.json, the build tools keep `Icon.png`
      // (legacy) or `icon.png` (current).
      iconUrl: packageUrl == null && base != null
          ? _resolveHttps(legacy ? 'Icon.png' : 'icon.png', base)
          : null,
      iconBytes: iconBytes,
      downloadUrl: LibraryAddon.httpsUrlOrNull(packageUrl),
      websiteUrl: website,
      altNames: LibraryAddon.stringList(info['altNames']),
      minAppVersion:
          _optionalString(info['minAppVersion']) ??
          _optionalString(document['minAppVersion']),
      maxAppVersion:
          _optionalString(info['maxAppVersion']) ??
          _optionalString(document['maxAppVersion']),
      legacyAidokuFormat: legacy,
      packageSha256: packageSha256,
      packageSize: packageSize,
    );
    return _ParsedCatalog(
      format: format,
      name: name,
      entries: List.unmodifiable(<LibraryCatalogSourceEntry>[entry]),
    );
  }

  static _ParsedCatalog _parseNeoStationManifest(
    Map<String, dynamic> document,
    Uri? base,
  ) {
    final manifest = Map<String, dynamic>.from(document)..remove('builtIn');
    final LibraryAddon addon;
    try {
      addon = LibraryAddon.fromManifest(
        manifest,
        origin: base?.toString() ?? 'local',
      );
    } on LibraryAddonException catch (error) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.invalidDocument,
        uri: base,
        detail: error.message,
      );
    }
    final leading = RegExp(r'^\d+').firstMatch(addon.version.trim());
    final entry = LibraryCatalogSourceEntry(
      id: addon.id,
      addonId: addon.id,
      name: addon.name,
      version: leading == null ? 0 : int.parse(leading.group(0)!),
      versionLabel: addon.version,
      languages: addon.languages,
      contentRating: addon.contentRating,
      iconUrl: addon.iconUrl,
      websiteUrl: addon.websiteUrl,
      minAppVersion: addon.minimumAppVersion,
      manifest: Map<String, dynamic>.unmodifiable(manifest),
    );
    return _ParsedCatalog(
      format: LibraryCatalogFormat.neoStationManifest,
      name: addon.name,
      entries: List.unmodifiable(<LibraryCatalogSourceEntry>[entry]),
    );
  }

  static List<dynamic> _modernTachiyomiExtensions(List<dynamic> extensions) {
    final result = <Map<String, dynamic>>[];
    for (final raw in extensions) {
      if (raw is! Map) continue;
      final resources = raw['resources'] is Map
          ? raw['resources'] as Map
          : const <String, dynamic>{};
      result.add(<String, dynamic>{
        'name': raw['name'],
        'pkg': raw['packageName'],
        'apk': resources['apkUrl'],
        'iconUrl': resources['iconUrl'],
        'version': raw['versionName'] ?? raw['extensionLib'],
        'code': raw['versionCode'],
        'nsfw': raw['contentWarning']?.toString() == 'CONTENT_WARNING_NSFW'
            ? 1
            : 0,
        'sources': <Map<String, dynamic>>[
          for (final source
              in (raw['sources'] is List
                  ? raw['sources'] as List
                  : const <dynamic>[]))
            if (source is Map)
              <String, dynamic>{
                'id': source['id'],
                'name': source['name'],
                'lang': source['language'],
                'baseUrl': source['homeUrl'],
              },
        ],
      });
    }
    return result;
  }

  /// Tachiyomi/Mihon extensions, expanded to one metadata-only entry per
  /// source (APK and icon follow the repository layout `apk/<file>` and
  /// `icon/<package>.png`).
  static _ParsedCatalog _parseTachiyomi(
    List<dynamic> extensions,
    Uri? base,
    String? name,
  ) {
    final byAddonId = <String, LibraryCatalogSourceEntry>{};
    for (final raw in extensions) {
      if (raw is! Map) continue;
      final packageName = _optionalString(raw['pkg']);
      if (packageName == null ||
          LibraryAddonService.isRepositoryDeprecationPackage(packageName)) {
        continue;
      }
      final extensionName = _optionalString(raw['name']) ?? packageName;
      final versionLabel =
          _optionalString(raw['version']) ??
          _optionalString(raw['code']) ??
          '0';
      final apkUrl = _resolveHttps(
        _optionalString(raw['apk']),
        base,
        folder: 'apk',
      );
      final iconUrl =
          LibraryAddon.httpsUrlOrNull(raw['iconUrl']) ??
          _resolveHttps('$packageName.png', base, folder: 'icon');
      final extensionLang = _optionalString(raw['lang']) ?? 'all';
      final rating = LibraryAddon.normalizeContentRating(
        raw['contentRating'],
        raw['nsfw'],
      );
      final sources = raw['sources'];
      if (sources is! List) continue;
      for (var index = 0; index < sources.length; index++) {
        final source = sources[index];
        if (source is! Map) continue;
        if (byAddonId.length >= maxSources) {
          throw LibraryCatalogException(
            LibraryCatalogErrorKind.tooLarge,
            uri: base,
            detail: 'more than $maxSources sources',
          );
        }
        final declaredId = _optionalString(source['id']);
        final sourceId = declaredId ?? '$index';
        final addonId = LibraryAddonService.tachiyomiAddonId(
          packageName,
          sourceId,
        );
        if (byAddonId.containsKey(addonId)) continue;
        byAddonId[addonId] = LibraryCatalogSourceEntry(
          id: declaredId ?? '$packageName:$index',
          addonId: addonId,
          name: _optionalString(source['name']) ?? extensionName,
          version: _int(raw['code']) ?? 0,
          versionLabel: versionLabel,
          languages: <String>[_optionalString(source['lang']) ?? extensionLang],
          contentRating: rating,
          iconUrl: iconUrl,
          downloadUrl: apkUrl,
          websiteUrl: LibraryAddon.httpsUrlOrNull(source['baseUrl']),
          activatable: false,
          packageName: packageName,
        );
      }
    }
    if (byAddonId.isEmpty) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.emptyCatalog,
        uri: base,
      );
    }
    return _ParsedCatalog(
      format: LibraryCatalogFormat.tachiyomiRepository,
      name: name,
      entries: List.unmodifiable(byAddonId.values),
    );
  }

  static bool _isZip(Uint8List bytes) =>
      bytes.length >= 4 &&
      bytes[0] == 0x50 &&
      bytes[1] == 0x4b &&
      (bytes[2] == 0x03 || bytes[2] == 0x05) &&
      (bytes[3] == 0x04 || bytes[3] == 0x06);

  /// Reads `Payload/source.json` and `Payload/Icon.png`/`icon.png` from an
  /// `.aix`. `main.wasm` is never read, let alone executed. Entries are
  /// inflated with a hard output limit (a lying ZIP header cannot exhaust
  /// memory).
  static _ParsedCatalog _parsePackage(Uint8List bytes, Uri? packageUri) {
    if (bytes.length > maxPackageBytes) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.tooLarge,
        uri: packageUri,
        detail: '${bytes.length} bytes',
      );
    }
    final Archive archive;
    try {
      archive = ZipDecoder().decodeBytes(bytes);
    } on Object catch (error) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.invalidDocument,
        uri: packageUri,
        detail: 'Invalid ZIP: $error',
      );
    }
    ArchiveFile? sourceJson;
    ArchiveFile? icon;
    for (final file in archive) {
      if (!file.isFile) continue;
      final name = file.name.replaceAll('\\', '/').toLowerCase();
      if (name == 'payload/source.json') {
        sourceJson = file;
      } else if (sourceJson == null && name.endsWith('/source.json')) {
        sourceJson = file;
      } else if (name == 'payload/icon.png') {
        icon ??= file;
      }
    }
    if (sourceJson == null) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.invalidDocument,
        uri: packageUri,
        detail: 'Payload/source.json missing',
      );
    }
    final Object? decoded;
    try {
      final raw = _readZipEntry(sourceJson, _maxPackageEntryBytes);
      if (raw == null) throw const FormatException('unreadable entry');
      final text = utf8.decode(raw);
      decoded = jsonDecode(_withoutByteOrderMark(text));
    } on _ZipEntryTooLarge {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.tooLarge,
        uri: packageUri,
        detail: 'Payload/source.json',
      );
    } on Object catch (error) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.invalidDocument,
        uri: packageUri,
        detail: 'Invalid Payload/source.json: $error',
      );
    }
    if (decoded is! Map || decoded['info'] is! Map) {
      throw LibraryCatalogException(
        LibraryCatalogErrorKind.invalidDocument,
        uri: packageUri,
        detail: 'Payload/source.json has no info object',
      );
    }
    Uint8List? iconBytes;
    if (icon != null) {
      try {
        iconBytes = _readZipEntry(icon, _maxPackageEntryBytes);
      } on Object {
        iconBytes = null; // An unreadable icon does not invalidate the source.
      }
    }
    return _parseSourceJson(
      Map<String, dynamic>.from(decoded),
      packageUri,
      format: LibraryCatalogFormat.aidokuPackage,
      packageUrl: packageUri?.toString(),
      iconBytes: iconBytes,
      packageSha256: sha256.convert(bytes).toString(),
      packageSize: bytes.length,
    );
  }

  static Uint8List? _readZipEntry(ArchiveFile file, int maxBytes) {
    if (file.size > maxBytes) throw const _ZipEntryTooLarge();
    final content = file.rawContent;
    if (content is! ZipFile) {
      final bytes = file.readBytes();
      if (bytes != null && bytes.length > maxBytes) {
        throw const _ZipEntryTooLarge();
      }
      return bytes;
    }
    if ((content.flags & 0x1) != 0) return null; // Encrypted entry.
    final raw = content.getStream(decompress: false).toUint8List();
    switch (content.compressionMethod) {
      case CompressionType.none:
        if (raw.length > maxBytes) throw const _ZipEntryTooLarge();
        return Uint8List.fromList(raw);
      case CompressionType.deflate:
        final sink = _BoundedBytesSink(maxBytes);
        final inflater = io.ZLibDecoder(raw: true).startChunkedConversion(sink);
        const chunk = 64 * 1024;
        for (var offset = 0; offset < raw.length; offset += chunk) {
          final end = offset + chunk < raw.length ? offset + chunk : raw.length;
          inflater.add(Uint8List.sublistView(raw, offset, end));
        }
        inflater.close();
        return sink.takeBytes();
      case CompressionType.bzip2:
        return null;
    }
  }

  /// Absolute HTTPS URL of [raw]: kept as is when absolute, otherwise
  /// resolved against [base] (inside [folder] when given, Aidoku's
  /// `sources/<file>` and `icons/<icon>` rule). Anything else is null.
  static String? _resolveHttps(Object? raw, Uri? base, {String? folder}) {
    if (raw is! String) return null;
    final value = raw.trim();
    if (value.isEmpty) return null;
    final parsed = Uri.tryParse(value);
    if (parsed == null) return null;
    Uri resolved;
    if (parsed.hasScheme) {
      resolved = parsed;
    } else {
      if (base == null) return null;
      try {
        resolved = base.resolve(folder == null ? value : '$folder/$value');
      } on FormatException {
        return null;
      }
    }
    if (resolved.scheme != 'https' || resolved.host.isEmpty) return null;
    return resolved.toString();
  }

  /// Some editors save JSON with a UTF-8 byte order mark, which
  /// `jsonDecode` rejects.
  static String _withoutByteOrderMark(String text) =>
      text.isNotEmpty && text.codeUnitAt(0) == 0xFEFF
      ? text.substring(1)
      : text;

  static String? _optionalString(Object? value) {
    if (value == null || value is Map || value is List) return null;
    final text = value.toString().trim();
    return text.isEmpty ? null : text;
  }

  static int? _int(Object? value) {
    if (value is int) return value;
    if (value is num) {
      return value.isFinite && value == value.roundToDouble()
          ? value.toInt()
          : null;
    }
    if (value is String) return int.tryParse(value.trim());
    return null;
  }
}

class _ParsedCatalog {
  const _ParsedCatalog({
    required this.format,
    required this.name,
    required this.entries,
  });

  final LibraryCatalogFormat format;
  final String? name;
  final List<LibraryCatalogSourceEntry> entries;
}

class _ZipEntryTooLarge implements Exception {
  const _ZipEntryTooLarge();
}

/// Collects inflated bytes and aborts once [maxBytes] is exceeded.
class _BoundedBytesSink implements Sink<List<int>> {
  _BoundedBytesSink(this.maxBytes);

  final int maxBytes;
  final BytesBuilder _builder = BytesBuilder(copy: true);

  @override
  void add(List<int> data) {
    if (_builder.length + data.length > maxBytes) {
      throw const _ZipEntryTooLarge();
    }
    _builder.add(data);
  }

  @override
  void close() {}

  Uint8List takeBytes() => _builder.takeBytes();
}
