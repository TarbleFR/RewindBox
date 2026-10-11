// Live end-to-end journey of the reading Library against the real sites.
// Skipped unless NS_LIBRARY_LIVE=1 (never part of CI). Writes a JSON report
// to $NS_LIBRARY_LIVE_OUT (a directory, default: the system temp directory).
//
//   NS_LIBRARY_LIVE=1 flutter test test/library_e2e_live_test.dart
//
// Real LibraryHttp (keep-alive client, disk cache in a temporary folder):
// preview the French Aidoku index, activate the three sources verified as
// working, open the catalogue feed, search, open a title, its chapters and
// pages, download the first page image through LibraryImageCache. Then a
// "relaunch": new instances on the same cache folder with a transport that
// fails as when the device is offline, and the listing, the title, its page
// list and the page image must come from the cache.
//
// A run from a PC says nothing about an iPhone (network stack, ATS, memory).
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_source_catalog_service.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

const String _index =
    'https://raw.githubusercontent.com/Moomooo95/aidoku-french-sources/'
    'gh-pages/index.min.json';

const List<String> _working = <String>[
  'fr.mangasorigines',
  'fr.lelscanfr',
  'fr.sushiscan',
];

/// Query per source and the title preferred among its results.
const Map<String, (String, String?)> _searches = <String, (String, String?)>{
  'fr.mangasorigines': ('solo', null),
  'fr.lelscanfr': ('one piece', 'one-piece'),
  'fr.sushiscan': ('one piece', 'one-piece'),
};

/// One request seen by [_Recorder].
class _Record {
  _Record(this.phase, this.request, this.mode);

  final String phase;
  final LibraryRequest request;
  final LibraryFetchMode mode;
  int? status;
  String? contentType;
  int? bytes;
  int? ms;
  bool fromCache = false;
  bool stale = false;
  bool revalidated = false;
  String? error;

  Map<String, Object?> toJson() => <String, Object?>{
    'phase': phase,
    'method': request.method,
    'url': request.uri.toString(),
    'mode': mode.name,
    'status': ?status,
    'contentType': ?contentType,
    'bytes': ?bytes,
    'ms': ?ms,
    if (fromCache) 'fromCache': true,
    if (stale) 'stale': true,
    if (revalidated) 'revalidated': true,
    'error': ?error,
  };
}

/// LibraryFetcher wrapper recording every request of the journey.
class _Recorder {
  _Recorder(this.inner);

  final LibraryFetcher inner;
  final List<_Record> records = <_Record>[];
  String phase = 'start';

  Future<LibraryHttpResponse> call(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    final record = _Record(phase, request, mode);
    records.add(record);
    final watch = Stopwatch()..start();
    try {
      final response = await inner(request, mode: mode, cancel: cancel);
      record
        ..status = response.statusCode
        ..contentType = response.headers['content-type']
        ..bytes = response.bodyBytes.length
        ..fromCache = response.fromCache
        ..stale = response.stale
        ..revalidated = response.revalidated;
      return response;
    } on LibraryNetworkException catch (error) {
      record
        ..status = error.statusCode
        ..error =
            '${error.kind.name}${error.detail == null ? '' : ': ${error.detail}'}';
      rethrow;
    } finally {
      record.ms = watch.elapsedMilliseconds;
    }
  }

  _Record? last(String url) {
    for (final record in records.reversed) {
      if (record.request.uri.toString() == url) return record;
    }
    return null;
  }
}

/// Transport of the "relaunch": every connection fails like an iPhone
/// without network (host lookup failure).
class _OfflineClient extends http.BaseClient {
  final List<String> attempts = <String>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    attempts.add('${request.method} ${request.url}');
    return Future<http.StreamedResponse>.error(
      SocketException(
        "Failed host lookup: '${request.url.host}'",
        osError: const OSError('No address associated with hostname', 7),
      ),
    );
  }
}

String _describe(Object error) {
  if (error is LibraryNetworkException) {
    return 'network ${error.kind.name}'
        '${error.statusCode == null ? '' : ' HTTP ${error.statusCode}'}'
        '${error.detail == null ? '' : ' (${error.detail})'}';
  }
  if (error is LibrarySourceException) {
    return 'source ${error.kind.name}'
        '${error.networkError == null ? '' : ' / ${_describe(error.networkError!)}'}';
  }
  return error.toString();
}

void main() {
  final enabled = Platform.environment['NS_LIBRARY_LIVE'] == '1';

  test(
    'live journey: catalogue → three sources → read → offline relaunch',
    () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      final started = DateTime.now().toUtc();
      final root = await Directory.systemTemp.createTemp('ns_e2e_live_');
      final caches = Directory(p.join(root.path, 'Caches', 'Library'));
      final support = Directory(p.join(root.path, 'Support', 'Library'));
      final report = <String, Object?>{
        'startedAt': started.toIso8601String(),
        'environment':
            'flutter test on ${Platform.operatingSystem} '
            '${Platform.operatingSystemVersion} (a PC, not an iPhone)',
        'dart': Platform.version.split(' ').first,
        'commit': Platform.environment['NS_LIBRARY_LIVE_COMMIT'] ?? 'unknown',
        'cacheDirectory': caches.path,
      };
      final failures = <String>[];
      final online = LibraryHttp(cacheDirectory: caches);
      final recorder = _Recorder(online.send);
      final images = LibraryImageCache(
        fetcher: recorder.call,
        cacheDirectory: caches,
      );
      final native = LibraryAidokuNativeService(fetcher: recorder.call);
      final sources = <String, Map<String, Object?>>{
        for (final id in _working) id: <String, Object?>{},
      };
      final chosen = <String, (LibraryAddon, LibraryCatalogItem)>{};
      final read = <String, (LibraryMangaDetails, LibraryMangaChapter)>{};
      final pageLists = <String, List<String>>{};
      final imageDigests = <String, String>{};
      final listingCounts = <String, int>{};
      try {
        // 1. Preview of the catalogue: nothing installed.
        recorder.phase = 'preview';
        final addons = LibraryAddonService.forTesting();
        await addons.load();
        final catalogs = LibrarySourceCatalogService(
          fetcher: recorder.call,
          addons: addons,
          store: LibraryCatalogFileStore(directory: () async => support),
        );
        var watch = Stopwatch()..start();
        final preview = await catalogs.preview(_index);
        report['catalogue'] = <String, Object?>{
          'url': _index,
          'ms': watch.elapsedMilliseconds,
          'format': preview.format.name,
          'sources': preview.sources.length,
          'fromCache': preview.fromCache,
          'installedBeforeActivation': (await addons.load()).length,
          'support': <String, Object?>{
            for (final entry in preview.sources)
              entry.id: <String, Object?>{
                'name': entry.name,
                'version': entry.versionLabel,
                'contentRating': entry.contentRating,
                'adapter': native.supportFor(entry.id).hasAdapter,
                'verifiedState': native.supportFor(entry.id).knownState.name,
              },
          },
        };

        // 2. Activation of exactly the three working sources.
        recorder.phase = 'activate';
        final activation = await catalogs.activate(preview, _working.toSet());
        final installed = await addons.load();
        report['activation'] = <String, Object?>{
          'added': activation.added.map((addon) => addon.id).toList(),
          'skipped': activation.skipped.map((skip) => skip.id).toList(),
          'catalogRemembered': activation.catalogRemembered,
          'installed': installed.map((addon) => addon.id).toList(),
        };
        if (installed.length != 3) failures.add('activation: $installed');
        LibraryAddon addonOf(String id) =>
            installed.firstWhere((addon) => addon.aidokuSourceId == id);

        // 3. Catalogue feed: each source published as soon as it answers.
        recorder.phase = 'feed';
        final feed = LibraryCatalogFeed(
          backend: LibraryCatalogFeedBackend(aidoku: native),
        );
        final shownAt = <String, int>{};
        watch = Stopwatch()..start();
        feed.addListener(() {
          for (final source in feed.sources) {
            if (source.entryCount > 0) {
              shownAt.putIfAbsent(
                source.addon.aidokuSourceId!,
                () => watch.elapsedMilliseconds,
              );
            }
          }
        });
        await feed.open(installed);
        report['feed'] = <String, Object?>{
          'openMs': watch.elapsedMilliseconds,
          'firstTitlesShownMs': shownAt,
          'sources': <String, Object?>{
            for (final source in feed.sources)
              source.addon.aidokuSourceId!: <String, Object?>{
                'titles': source.entryCount,
                'first': source.entries.isEmpty
                    ? null
                    : source.entries.first.item.title,
                'hasMore': !source.exhausted,
                'failure': source.failure?.technical,
              },
          },
        };
        for (final source in feed.sources) {
          listingCounts[source.addon.aidokuSourceId!] = source.entryCount;
          if (source.entryCount == 0 || source.failure != null) {
            failures.add(
              'feed ${source.key}: ${source.failure?.technical ?? 'empty'}',
            );
          }
        }

        // 4. Search (each query once, every source answers progressively).
        recorder.phase = 'search';
        final searchReport = <String, Object?>{};
        for (final query in _searches.values.map((e) => e.$1).toSet()) {
          watch = Stopwatch()..start();
          await feed.search(query);
          final current = feed.currentSearch!;
          searchReport[query] = <String, Object?>{
            'ms': watch.elapsedMilliseconds,
            for (final source in current.sources)
              source.addon?.aidokuSourceId ?? source.key: <String, Object?>{
                'status': source.status.name,
                'results': source.entries.length,
                'first': source.entries.isEmpty
                    ? null
                    : source.entries.first.item.title,
                'failure': source.failure?.technical,
              },
          };
          for (final source in current.sources) {
            final id = source.addon?.aidokuSourceId;
            if (id == null || _searches[id]?.$1 != query) continue;
            final preferred = _searches[id]!.$2;
            LibraryCatalogItem? item;
            for (final entry in source.entries) {
              if (preferred == null || entry.item.id == preferred) {
                item = entry.item;
                break;
              }
            }
            item ??= source.entries.isEmpty ? null : source.entries.first.item;
            if (item != null) {
              chosen[id] = (addonOf(id), item);
            } else {
              failures.add('search $id "$query": ${source.status.name}');
            }
          }
        }
        feed.clearSearch();
        report['search'] = searchReport;
        // A source whose search failed is read from its listing instead.
        for (final id in _working) {
          if (chosen.containsKey(id)) continue;
          final source = feed.source(addonOf(id).id);
          if (source != null && source.entries.isNotEmpty) {
            chosen[id] = (addonOf(id), source.entries.first.item);
          }
        }

        // 5. Title page, chapters, pages, first page image.
        for (final id in _working) {
          final pair = chosen[id];
          final entry = sources[id]!;
          if (pair == null) {
            entry['skipped'] = 'no title to open';
            continue;
          }
          final (addon, item) = pair;
          entry['title'] = item.title;
          entry['mangaId'] = item.id;
          try {
            recorder.phase = 'details:$id';
            watch = Stopwatch()..start();
            final details = await native.loadManga(addon, item);
            final ascending = details.chaptersAscending;
            final numbers = ascending
                .map((chapter) => chapter.number)
                .whereType<double>()
                .toList();
            entry['details'] = <String, Object?>{
              'ms': watch.elapsedMilliseconds,
              'title': details.item.title,
              'author': details.author,
              'status': details.status.name,
              'readingMode': details.readingMode.name,
              'contentRating': details.contentRating,
              'chapters': details.chapters.length,
              'chaptersComplete': details.chaptersComplete,
              'newest': details.chapters.isEmpty
                  ? null
                  : details.chapters.first.displayTitle,
              'oldest': details.chapters.isEmpty
                  ? null
                  : details.chapters.last.displayTitle,
              'ascendingNumbersSorted': _isSorted(numbers),
            };
            if (details.chapters.isEmpty) {
              failures.add('details $id: no chapter');
              continue;
            }
            recorder.phase = 'pages:$id';
            List<String>? pages;
            LibraryMangaChapter? chapter;
            final attempts = <String>[];
            for (final candidate in details.chapters.take(3)) {
              watch = Stopwatch()..start();
              try {
                pages = await native.loadPages(addon, details.item, candidate);
                chapter = candidate;
                break;
              } on Object catch (error) {
                attempts.add('${candidate.displayTitle}: ${_describe(error)}');
              }
            }
            if (pages == null || chapter == null) {
              entry['pages'] = <String, Object?>{'failed': attempts};
              failures.add('pages $id: $attempts');
              continue;
            }
            entry['pages'] = <String, Object?>{
              'chapter': chapter.displayTitle,
              'chapterId': chapter.id,
              'ms': watch.elapsedMilliseconds,
              'count': pages.length,
              'firstHost': Uri.parse(pages.first).host,
              if (attempts.isNotEmpty) 'skippedChapters': attempts,
            };
            read[id] = (details, chapter);
            pageLists[id] = pages;

            recorder.phase = 'image:$id';
            watch = Stopwatch()..start();
            final bytes = await images.load(
              pages.first,
              headers: native.imageHeaders(addon),
            );
            final record = recorder.last(pages.first);
            imageDigests[id] = sha256.convert(bytes).toString();
            entry['image'] = <String, Object?>{
              'url': pages.first,
              'ms': watch.elapsedMilliseconds,
              'status': record?.status,
              'contentType': record?.contentType,
              'bytes': bytes.length,
              'sha256': imageDigests[id],
              'looksLikeImage': LibraryImageCache.looksLikeImage(
                bytes,
                contentType: record?.contentType,
              ),
              'referer': native.imageHeaders(addon)['Referer'],
            };
          } on Object catch (error) {
            entry['error'] = _describe(error);
            failures.add('$id: ${_describe(error)}');
          }
        }
        report['sources'] = sources;
        report['onlineHttpStats'] = online.stats.toJson();
        feed.dispose();
        await online.idle();
        await images.idle();
        online.close();

        // 6. "Relaunch" offline: new instances on the same cache folder, two
        // hours later (listings and details past their fresh window).
        recorder.phase = 'offline';
        final offlineClient = _OfflineClient();
        DateTime later() => DateTime.now().add(const Duration(hours: 2));
        final offline = LibraryHttp(
          client: offlineClient,
          cacheDirectory: caches,
          clock: later,
        );
        final offlineRecorder = _Recorder(offline.send)..phase = 'offline';
        final offlineNative = LibraryAidokuNativeService(
          fetcher: offlineRecorder.call,
          clock: later,
        );
        final offlineImages = LibraryImageCache(
          fetcher: offlineRecorder.call,
          cacheDirectory: caches,
          clock: later,
        );
        final relaunch = <String, Object?>{};
        for (final id in _working) {
          final result = <String, Object?>{};
          relaunch[id] = result;
          final addon = addonOf(id);
          try {
            final listing = await offlineNative.loadCatalogPage(addon);
            result['listing'] = <String, Object?>{
              'titles': listing.items.length,
              'fromCache': listing.fromCache,
              'stale': listing.stale,
            };
            if (listing.items.length != listingCounts[id]) {
              failures.add(
                'offline listing $id: ${listing.items.length} titles, '
                'online ${listingCounts[id]}',
              );
            }
          } on Object catch (error) {
            result['listing'] = _describe(error);
            failures.add('offline listing $id: ${_describe(error)}');
          }
          final pair = read[id];
          final pages = pageLists[id];
          if (pair == null || pages == null) {
            result['reading'] = 'not read online';
            continue;
          }
          final (details, chapter) = pair;
          try {
            final cached = await offlineNative.loadManga(addon, chosen[id]!.$2);
            result['details'] = <String, Object?>{
              'chapters': cached.chapters.length,
              'sameChapters':
                  cached.chapters.map((c) => c.id).join('\n') ==
                  details.chapters.map((c) => c.id).join('\n'),
              'fromCache': cached.fromCache,
              'stale': cached.stale,
            };
            if (cached.chapters.length != details.chapters.length) {
              failures.add('offline details $id');
            }
            final cachedPages = await offlineNative.loadPages(
              addon,
              cached.item,
              chapter,
            );
            result['pages'] = <String, Object?>{
              'count': cachedPages.length,
              'samePages': cachedPages.join('\n') == pages.join('\n'),
            };
            if (cachedPages.join('\n') != pages.join('\n')) {
              failures.add('offline pages $id');
            }
            final bytes = await offlineImages.load(
              pages.first,
              headers: offlineNative.imageHeaders(addon),
            );
            final digest = sha256.convert(bytes).toString();
            result['image'] = <String, Object?>{
              'bytes': bytes.length,
              'sameBytes': digest == imageDigests[id],
            };
            if (digest != imageDigests[id]) failures.add('offline image $id');
          } on Object catch (error) {
            result['error'] = _describe(error);
            failures.add('offline $id: ${_describe(error)}');
          }
        }
        // The hub after the relaunch: cached titles shown, marked stale.
        final offlineFeed = LibraryCatalogFeed(
          backend: LibraryCatalogFeedBackend(aidoku: offlineNative),
          clock: later,
        );
        await offlineFeed.open(installed);
        relaunch['feed'] = <String, Object?>{
          for (final source in offlineFeed.sources)
            source.addon.aidokuSourceId!: <String, Object?>{
              'titles': source.entryCount,
              'fromCache': source.fromCache,
              'stale': source.stale,
              'failure': source.failure?.issue.name,
            },
        };
        for (final source in offlineFeed.sources) {
          if (source.entryCount == 0) {
            failures.add('offline feed ${source.key}: nothing shown');
          }
        }
        offlineFeed.dispose();
        relaunch['connectionAttempts'] = offlineClient.attempts.length;
        relaunch['httpStats'] = offline.stats.toJson();
        relaunch['requests'] = offlineRecorder.records
            .map((record) => record.toJson())
            .toList();
        report['relaunchOffline'] = relaunch;
        await offline.idle();
        offline.close();
      } on Object catch (error, stack) {
        failures.add('journey stopped: ${_describe(error)}');
        report['exception'] = '$error\n$stack';
      } finally {
        report['requests'] = recorder.records
            .map((record) => record.toJson())
            .toList();
        report['failures'] = failures;
        report['finishedAt'] = DateTime.now().toUtc().toIso8601String();
        final outDir = Directory(
          Platform.environment['NS_LIBRARY_LIVE_OUT'] ??
              Directory.systemTemp.path,
        )..createSync(recursive: true);
        final stamp = started.toIso8601String().replaceAll(
          RegExp(r'[:.]'),
          '-',
        );
        final file = File(p.join(outDir.path, 'e2e-live-$stamp.json'));
        file.writeAsStringSync(
          const JsonEncoder.withIndent('  ').convert(report),
        );
        // ignore: avoid_print
        print('Live report: ${file.path}');
        try {
          await root.delete(recursive: true);
        } on FileSystemException {
          // Left to the system temp cleanup.
        }
      }
      expect(failures, isEmpty);
    },
    skip: enabled ? false : 'set NS_LIBRARY_LIVE=1 to query the live sites',
    timeout: const Timeout(Duration(minutes: 10)),
  );
}

bool _isSorted(List<double> values) {
  for (var i = 1; i < values.length; i++) {
    if (values[i] < values[i - 1]) return false;
  }
  return true;
}
