// Live verification of the ten French Aidoku sources against the real sites.
// Skipped unless NS_LIBRARY_LIVE=1 (never part of CI). Writes a JSON report
// to $NS_LIBRARY_LIVE_OUT (a directory, default: the system temp directory).
//
//   NS_LIBRARY_LIVE=1 flutter test test/library_aidoku_live_check_test.dart
//
// Uses LibraryHttp when it is implemented; otherwise a minimal package:http
// fetcher below that follows the LibraryHttp status mapping contract.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';

import 'library_aidoku_test_support.dart';

const List<String> _sources = <String>[
  'fr.mangasorigines',
  'fr.lelscanfr',
  'fr.sushiscan',
  'fr.sushiscans',
  'fr.mangascantrad',
  'fr.astralmanga',
  'fr.phenixscans',
  'fr.mangascan',
  'fr.reaperscans',
  'fr.legacyscans',
];

/// Stable titles probed on 2026-10-10 by the source research.
const Map<String, (String, String)> _knownTitles = <String, (String, String)>{
  'fr.mangasorigines': (
    '826-solo-leveling',
    'https://mangas-origines.fr/oeuvre/826-solo-leveling/',
  ),
  'fr.lelscanfr': ('one-piece', 'https://www.lelscanfr.com/manga/one-piece'),
  'fr.sushiscan': ('one-piece', 'https://sushiscan.net/catalogue/one-piece/'),
  'fr.sushiscans': ('one-piece', 'https://sushiscan.fr/catalogue/one-piece/'),
  'fr.mangascantrad': (
    'unknown-code',
    'https://manga-scantrad.io/manga/unknown-code/',
  ),
};

const Map<String, String> _queries = <String, String>{
  'fr.mangasorigines': 'solo',
  'fr.lelscanfr': 'one piece',
  'fr.sushiscan': 'one piece',
  'fr.sushiscans': 'one piece',
  'fr.mangascantrad': 'one',
};

/// Minimal fetcher used while LibraryHttp is a stub: one keep-alive client,
/// default User-Agent, timeouts, size limit and the status mapping contract.
class _MinimalFetcher {
  final http.Client _client = http.Client();
  int requests = 0;

  Future<LibraryHttpResponse> call(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    cancel?.throwIfCancelled(request.uri);
    if (mode == LibraryFetchMode.cacheOnly) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.notFound,
        uri: request.uri,
        detail: 'cache-miss',
      );
    }
    requests++;
    final outgoing = http.Request(request.method, request.uri)
      ..followRedirects = request.followRedirects
      ..maxRedirects = 5
      ..headers.addAll(<String, String>{
        'User-Agent': LibraryHttp.defaultUserAgent,
        ...request.headers,
      });
    final form = request.form;
    if (form != null) outgoing.bodyFields = form;
    final watch = Stopwatch()..start();
    http.StreamedResponse streamed;
    List<int> bytes;
    try {
      streamed = await _client
          .send(outgoing)
          .timeout(request.timeout ?? LibraryHttp.defaultTimeout);
      bytes = await streamed.stream.toBytes().timeout(
        request.timeout ?? LibraryHttp.defaultTimeout,
      );
    } on TimeoutException catch (error) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.timeout,
        uri: request.uri,
        detail: '$error',
      );
    } on SocketException catch (error) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.offline,
        uri: request.uri,
        detail: '$error',
      );
    } on HandshakeException catch (error) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.offline,
        uri: request.uri,
        detail: '$error',
      );
    } on http.ClientException catch (error) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.offline,
        uri: request.uri,
        detail: '$error',
      );
    }
    watch.stop();
    final maxBytes = request.maxBytes ?? LibraryHttp.defaultMaxBytes;
    if (bytes.length > maxBytes) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.tooLarge,
        uri: request.uri,
        statusCode: streamed.statusCode,
      );
    }
    final headers = <String, String>{
      for (final entry in streamed.headers.entries)
        entry.key.toLowerCase(): entry.value,
    };
    final status = streamed.statusCode;
    final finalUri = streamed is http.BaseResponseWithUrl
        ? (streamed as http.BaseResponseWithUrl).url
        : request.uri;
    final ok = status >= 200 && status < 300;
    if (!ok && !request.acceptStatuses.contains(status)) {
      final body = utf8.decode(bytes, allowMalformed: true);
      final challenge =
          (status == 403 || status == 503) &&
          (headers['cf-mitigated'] == 'challenge' ||
              body.contains('<title>Just a moment...</title>') ||
              body.contains('Attention Required! | Cloudflare') ||
              body.contains('challenge-platform'));
      final kind = challenge
          ? LibraryNetworkErrorKind.challenge
          : status == 404 || status == 410
          ? LibraryNetworkErrorKind.notFound
          : (status >= 500 && status <= 504) || (status >= 520 && status <= 530)
          ? LibraryNetworkErrorKind.serverUnavailable
          : LibraryNetworkErrorKind.httpStatus;
      throw LibraryNetworkException(
        kind,
        uri: request.uri,
        statusCode: status,
        detail: '${bytes.length} B',
      );
    }
    return LibraryHttpResponse(
      request: request,
      statusCode: status,
      bodyBytes: Uint8List.fromList(bytes),
      headers: headers,
      finalUri: finalUri,
      fetchedAt: DateTime.now().toUtc(),
      networkTime: watch.elapsed,
    );
  }

  void close() => _client.close();
}

Future<Map<String, Object?>> _timed(
  Future<Map<String, Object?>> Function() run,
) async {
  final watch = Stopwatch()..start();
  try {
    final result = await run();
    return <String, Object?>{
      'ok': true,
      ...result,
      'ms': watch.elapsedMilliseconds,
    };
  } catch (error) {
    return <String, Object?>{
      'ok': false,
      if (error is LibraryNetworkException) ...<String, Object?>{
        'networkError': error.kind.name,
        'statusCode': error.statusCode,
      },
      if (error is LibrarySourceException) 'sourceError': error.kind.name,
      'error': '$error',
      'ms': watch.elapsedMilliseconds,
    };
  }
}

void main() {
  final enabled = Platform.environment['NS_LIBRARY_LIVE'] == '1';

  test(
    'live check of the ten French Aidoku sources',
    () async {
      LibraryFetcher fetcher;
      String fetcherName;
      _MinimalFetcher? minimal;
      try {
        final libraryHttp = LibraryHttp(
          cacheDirectory: Directory.systemTemp.createTempSync('aidoku-live-'),
        );
        fetcher = libraryHttp.send;
        fetcherName = 'LibraryHttp';
      } on UnimplementedError {
        minimal = _MinimalFetcher();
        fetcher = minimal.call;
        fetcherName = 'minimal package:http fetcher (LibraryHttp is a stub)';
      }
      final service = LibraryAidokuNativeService(fetcher: fetcher);
      const mode = LibraryFetchMode.refresh;
      final report = <String, Object?>{
        'startedAt': DateTime.now().toUtc().toIso8601String(),
        'fetcher': fetcherName,
        'userAgent': LibraryHttp.defaultUserAgent,
        'host': Platform.operatingSystem,
        'sources': <String, Object?>{},
      };
      final sources = report['sources']! as Map<String, Object?>;

      for (final sourceId in _sources) {
        final addon = aidokuAddon(sourceId);
        final support = service.supportFor(sourceId);
        final entry = <String, Object?>{
          'supports': service.supports(addon),
          'knownState': support.knownState.name,
          'unsupportedReason': service.unsupportedReasonKind(addon)?.name,
        };
        sources[sourceId] = entry;

        if (!service.supports(addon)) {
          entry['rootProbe'] = await _timed(() async {
            final response = await fetcher(
              LibraryRequest.get(
                Uri.parse(support.websiteUrl),
                timeout: const Duration(seconds: 25),
                acceptStatuses: <int>{
                  for (var status = 300; status < 600; status++) status,
                },
              ),
              mode: mode,
            );
            final body = response.text;
            final title = RegExp(
              r'<title>([^<]*)</title>',
              caseSensitive: false,
            ).firstMatch(body)?.group(1);
            return <String, Object?>{
              'status': response.statusCode,
              'bytes': response.bodyBytes.length,
              'contentType': response.headers['content-type'],
              'cfMitigated': response.headers['cf-mitigated'],
              'server': response.headers['server'],
              'title': title?.trim(),
              'finalUrl': response.finalUri.toString(),
            };
          });
          continue;
        }

        final pages = <LibraryMangaCatalogPage?>[null, null];
        for (final pageNumber in <int>[1, 2]) {
          entry['listingP$pageNumber'] = await _timed(() async {
            final page = await service.loadCatalogPage(
              addon,
              page: pageNumber,
              mode: mode,
            );
            pages[pageNumber - 1] = page;
            return <String, Object?>{
              'listing': page.listing.name,
              'items': page.items.length,
              'hasMore': page.hasMore,
              'first': page.items.isEmpty ? null : page.items.first.title,
              'explicitItems': page.items
                  .where((item) => item.raw['explicitContent'] == true)
                  .length,
            };
          });
        }
        final p1 = pages[0]?.items.map((item) => item.id).toSet() ?? <String>{};
        final p2 = pages[1]?.items.map((item) => item.id).toSet() ?? <String>{};
        entry['listingOverlap'] = p1.intersection(p2).length;

        entry['search'] = await _timed(() async {
          final page = await service.loadCatalogPage(
            addon,
            query: _queries[sourceId]!,
            mode: mode,
          );
          return <String, Object?>{
            'query': page.query,
            'items': page.items.length,
            'hasMore': page.hasMore,
          };
        });

        final known = _knownTitles[sourceId]!;
        final item = LibraryCatalogItem(
          id: known.$1,
          title: known.$1,
          mediaType: LibraryMediaType.manga,
          subtitle: '',
          description: '',
          coverUrl: null,
          content: null,
          contentUrl: null,
          pageUrls: const <String>[],
          raw: <String, dynamic>{'mangaUrl': known.$2},
        );
        LibraryMangaDetails? details;
        entry['details'] = await _timed(() async {
          details = await service.loadManga(addon, item, mode: mode);
          final chapters = details!.chapters;
          return <String, Object?>{
            'id': known.$1,
            'title': details!.item.title,
            'author': details!.author,
            'status': details!.status.name,
            'genres': details!.genres.length,
            'readingMode': details!.readingMode.name,
            'contentRating': details!.contentRating,
            'hasCover': details!.item.coverUrl != null,
            'descriptionChars': details!.item.description.length,
            'chapters': chapters.length,
            'chaptersComplete': details!.chaptersComplete,
            'firstChapter': chapters.isEmpty
                ? null
                : chapters.first.number ?? chapters.first.title,
            'lastChapter': chapters.isEmpty
                ? null
                : chapters.last.number ?? chapters.last.title,
            'volumes': chapters.where((chapter) => chapter.isVolume).length,
            'datedChapters': chapters
                .where((chapter) => chapter.date != null)
                .length,
          };
        });

        final chapter = details == null || details!.chapters.isEmpty
            ? null
            : details!.chapters.first;
        List<String>? pageUrls;
        if (chapter != null) {
          entry['pages'] = await _timed(() async {
            pageUrls = await service.loadPages(
              addon,
              details!.item,
              chapter,
              mode: mode,
            );
            return <String, Object?>{
              'chapter': chapter.id,
              'pages': pageUrls!.length,
              'firstHost': Uri.parse(pageUrls!.first).host,
            };
          });
        }
        if (pageUrls != null && pageUrls!.isNotEmpty) {
          entry['firstImage'] = await _timed(() async {
            final response = await fetcher(
              LibraryRequest.get(
                Uri.parse(pageUrls!.first),
                headers: service.imageHeaders(addon),
                maxBytes: 32 * 1024 * 1024,
                acceptStatuses: <int>{
                  for (var status = 300; status < 600; status++) status,
                },
              ),
              mode: mode,
            );
            return <String, Object?>{
              'status': response.statusCode,
              'contentType': response.headers['content-type'],
              'bytes': response.bodyBytes.length,
            };
          });
        }

        final healthWatch = Stopwatch()..start();
        final health = await service.checkHealth(addon);
        entry['health'] = <String, Object?>{
          ...health.toJson(),
          'navigationWorking': health.navigationWorking,
          'readingWorking': health.readingWorking,
          'state': health.state.name,
          'totalMs': healthWatch.elapsedMilliseconds,
        };
      }

      report['finishedAt'] = DateTime.now().toUtc().toIso8601String();
      if (minimal != null) report['httpRequests'] = minimal.requests;
      minimal?.close();

      final outDir = Directory(
        Platform.environment['NS_LIBRARY_LIVE_OUT'] ??
            Directory.systemTemp.path,
      )..createSync(recursive: true);
      final stamp = DateTime.now().toUtc().toIso8601String().replaceAll(
        RegExp(r'[:.]'),
        '-',
      );
      final file = File('${outDir.path}/aidoku-live-$stamp.json');
      file.writeAsStringSync(
        const JsonEncoder.withIndent('  ').convert(report),
      );
      // ignore: avoid_print
      print('Live report: ${file.path}');
      expect(sources, hasLength(10));
    },
    skip: enabled ? false : 'set NS_LIBRARY_LIVE=1 to query the live sites',
    timeout: const Timeout(Duration(minutes: 15)),
  );
}
