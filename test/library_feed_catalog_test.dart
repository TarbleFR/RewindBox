// Behaviour of LibraryCatalogFeed's catalogue: cache-first display,
// progressive per-source publication, bounded queue with first-paint
// timeout, blocked sources, manual refresh and round-robin pagination.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_http.dart';

import 'library_feed_test_fakes.dart';

void main() {
  late FakeFeedBackend backend;
  late TestClock clock;

  LibraryCatalogFeed newFeed({
    int maxConcurrentSources = 3,
    Duration firstPaintTimeout = const Duration(seconds: 8),
    Duration loadMoreThrottle = Duration.zero,
  }) {
    final feed = LibraryCatalogFeed(
      backend: backend,
      clock: clock.call,
      maxConcurrentSources: maxConcurrentSources,
      firstPaintTimeout: firstPaintTimeout,
      loadMoreThrottle: loadMoreThrottle,
    );
    addTearDown(feed.dispose);
    return feed;
  }

  List<String> titles(LibraryCatalogFeed feed) =>
      feed.entries.map((entry) => entry.item.title).toList();

  setUp(() {
    backend = FakeFeedBackend();
    clock = TestClock();
  });

  test('cached page 1 is published before the network answers', () async {
    final source = aidokuTestAddon('fr.alpha');
    backend.cachedPages['fr.alpha'] = testPage(
      [testItem('cached-1'), testItem('cached-2')],
      stale: true,
      fromCache: true,
      fetchedAt: clock.now.subtract(const Duration(hours: 2)),
    );
    final network = PendingPage();
    backend.pages['fr.alpha'] = (_) => network.completer.future;
    final feed = newFeed();
    final published = <List<String>>[];
    feed.addListener(() => published.add(titles(feed)));

    final opening = feed.open([source]);
    await settle();

    expect(titles(feed), ['cached-1', 'cached-2']);
    expect(published, isNotEmpty);
    expect(feed.source(source.id)!.loading, isTrue);
    // The stale cache is revalidated in refresh mode so a failure is typed.
    expect(backend.callsOf('page').single.mode, LibraryFetchMode.refresh);

    network.complete(testPage([testItem('fresh-1'), testItem('cached-1')]));
    await opening;
    await settle();
    expect(titles(feed), ['fresh-1', 'cached-1', 'cached-2']);
    expect(feed.source(source.id)!.loading, isFalse);
    expect(feed.source(source.id)!.failure, isNull);
  });

  test('a fresh cached page is not requested again', () async {
    final source = aidokuTestAddon('fr.alpha');
    backend.cachedPages['fr.alpha'] = testPage(
      [testItem('cached')],
      fromCache: true,
      fetchedAt: clock.now.subtract(const Duration(minutes: 3)),
    );
    final feed = newFeed();
    await feed.open([source]);
    await settle();
    expect(titles(feed), ['cached']);
    expect(backend.callsOf('page'), isEmpty);
  });

  test('a cache miss loads page 1 with cacheFirst', () async {
    final source = aidokuTestAddon('fr.alpha');
    backend.pages['fr.alpha'] = (_) async => testPage([testItem('one')]);
    final feed = newFeed();
    await feed.open([source]);
    await settle();
    expect(titles(feed), ['one']);
    expect(backend.callsOf('page').single.mode, LibraryFetchMode.cacheFirst);
  });

  test('each source is published as soon as it completes', () async {
    final a = aidokuTestAddon('fr.a');
    final b = aidokuTestAddon('fr.b');
    final c = aidokuTestAddon('fr.c');
    final pendingA = PendingPage();
    final pendingB = PendingPage();
    final pendingC = PendingPage();
    backend.pages['fr.a'] = (_) => pendingA.completer.future;
    backend.pages['fr.b'] = (_) => pendingB.completer.future;
    backend.pages['fr.c'] = (_) => pendingC.completer.future;
    final feed = newFeed();
    final opening = feed.open([a, b, c]);
    await settle();
    expect(feed.entries, isEmpty);

    pendingB.complete(testPage([testItem('b1')]));
    await settle();
    expect(titles(feed), ['b1'], reason: 'B is shown while A and C load');
    expect(feed.source(a.id)!.loading, isTrue);

    pendingC.complete(testPage([testItem('c1')]));
    await settle();
    expect(titles(feed).toSet(), {'b1', 'c1'});

    pendingA.complete(testPage([testItem('a1')]));
    await opening;
    expect(titles(feed), ['a1', 'b1', 'c1'], reason: 'source order kept');
  });

  test(
    'a slow source frees its queue slot after the first-paint timeout',
    () async {
      final slow = aidokuTestAddon('fr.slow');
      final quick = aidokuTestAddon('fr.quick');
      final slowPage = PendingPage();
      backend.pages['fr.slow'] = (_) => slowPage.completer.future;
      backend.pages['fr.quick'] = (_) async => testPage([testItem('quick')]);
      final feed = newFeed(
        maxConcurrentSources: 1,
        firstPaintTimeout: const Duration(milliseconds: 40),
      );
      final opening = feed.open([slow, quick]);
      await settle();
      expect(backend.callsOf('page').map((c) => c.sourceKey), [slow.id]);
      expect(feed.isLoading, isTrue);

      await Future<void>.delayed(const Duration(milliseconds: 80));
      await settle();
      expect(titles(feed), ['quick'], reason: 'not delayed by the slow source');
      expect(feed.source(slow.id)!.slow, isTrue);
      expect(feed.source(slow.id)!.loading, isTrue);
      expect(
        feed.isLoading,
        isFalse,
        reason: 'slow sources load in background',
      );

      slowPage.complete(testPage([testItem('late')]));
      await opening;
      expect(titles(feed), ['late', 'quick']);
      expect(feed.source(slow.id)!.slow, isFalse);
    },
  );

  test(
    'a source verified as blocked is not requested until a manual refresh',
    () async {
      final blocked = aidokuTestAddon('fr.blocked');
      backend.support['fr.blocked'] = blockedSupport(
        'fr.blocked',
        LibrarySourceKnownState.challenge,
      );
      backend.pages['fr.blocked'] = (_) async =>
          throw const LibraryNetworkException(
            LibraryNetworkErrorKind.challenge,
            statusCode: 403,
          );
      final feed = newFeed();
      await feed.open([blocked]);
      await settle();
      expect(backend.callsOf('page'), isEmpty);
      expect(feed.unavailableCount, 1);
      final failure = feed.source(blocked.id)!.failure!;
      expect(failure.issue, LibraryFeedIssue.challenge);
      expect(failure.known, isTrue);
      expect(failure.verifiedOn, DateTime.utc(2026, 10, 10));

      await feed.refresh();
      expect(backend.callsOf('page'), hasLength(1));
      expect(feed.source(blocked.id)!.failure!.known, isFalse);
      expect(feed.source(blocked.id)!.failure!.statusCode, 403);
    },
  );

  test(
    'a challenge failure is not retried automatically for 10 minutes',
    () async {
      final source = aidokuTestAddon('fr.alpha');
      var attempts = 0;
      backend.pages['fr.alpha'] = (_) async {
        attempts++;
        throw const LibraryNetworkException(LibraryNetworkErrorKind.challenge);
      };
      final feed = newFeed();
      await feed.open([source]);
      expect(attempts, 1);
      expect(
        feed.source(source.id)!.failure!.issue,
        LibraryFeedIssue.challenge,
      );

      clock.advance(const Duration(minutes: 5));
      await feed.open([source]);
      expect(attempts, 1, reason: 'tab switch within the pause');

      clock.advance(const Duration(minutes: 6));
      await feed.open([source]);
      expect(attempts, 2);
    },
  );

  test('reopening within the fresh window does not refetch', () async {
    final source = aidokuTestAddon('fr.alpha');
    backend.pages['fr.alpha'] = (_) async => testPage([testItem('one')]);
    final feed = newFeed();
    await feed.open([source]);
    await feed.open([source]);
    clock.advance(const Duration(minutes: 10));
    await feed.open([source]);
    expect(backend.callsOf('page'), hasLength(1));
    clock.advance(const Duration(minutes: 6));
    await feed.open([source]);
    expect(backend.callsOf('page'), hasLength(2));
  });

  test('refresh keeps the entries shown until page 1 replaces them', () async {
    final source = aidokuTestAddon('fr.alpha');
    final responses = <PendingPage>[];
    backend.pages['fr.alpha'] = (call) {
      final pending = PendingPage();
      responses.add(pending);
      return pending.completer.future;
    };
    final feed = newFeed();
    final opening = feed.open([source]);
    await settle();
    responses.single.complete(testPage([testItem('old-1'), testItem('old-2')]));
    await opening;

    final refreshing = feed.refresh();
    await settle();
    expect(backend.callsOf('page').last.mode, LibraryFetchMode.refresh);
    expect(feed.isRefreshing, isTrue);
    expect(titles(feed), ['old-1', 'old-2'], reason: 'kept while refreshing');

    responses.last.complete(testPage([testItem('new-1'), testItem('old-1')]));
    await refreshing;
    expect(titles(feed), ['new-1', 'old-1', 'old-2']);
  });

  test(
    'a failed refresh keeps the entries and records a typed failure',
    () async {
      final source = aidokuTestAddon('fr.alpha');
      var fail = false;
      backend.pages['fr.alpha'] = (_) async {
        if (fail) {
          throw const LibraryNetworkException(
            LibraryNetworkErrorKind.serverUnavailable,
            statusCode: 504,
          );
        }
        return testPage([testItem('kept')]);
      };
      final feed = newFeed();
      await feed.open([source]);
      fail = true;
      await feed.refresh();
      expect(titles(feed), ['kept']);
      final failure = feed.source(source.id)!.failure!;
      expect(failure.issue, LibraryFeedIssue.serverUnavailable);
      expect(failure.technical, contains('HTTP 504'));
      expect(feed.unavailableCount, 1);
      expect(feed.allSourcesFailed, isFalse, reason: 'it still shows titles');
    },
  );

  test('loadMore requests next pages in round robin, two at a time', () async {
    final sources = [
      aidokuTestAddon('fr.a'),
      aidokuTestAddon('fr.b'),
      aidokuTestAddon('fr.c'),
    ];
    for (final source in sources) {
      final id = source.aidokuSourceId!;
      backend.pages[id] = (call) async =>
          testPage([testItem('$id-p${call.page}')], page: call.page);
    }
    final feed = newFeed();
    await feed.open(sources);
    backend.calls.clear();

    await feed.loadMore();
    await feed.loadMore();
    await feed.loadMore();
    final requested = backend
        .callsOf('page')
        .map((c) => '${c.sourceKey}#${c.page}');
    expect(requested, [
      'aidoku.fr.a#2',
      'aidoku.fr.b#2',
      'aidoku.fr.c#2',
      'aidoku.fr.a#3',
      'aidoku.fr.b#3',
      'aidoku.fr.c#3',
    ]);
    expect(titles(feed), contains('fr.c-p3'));
  });

  test('loadMore never runs more than two pages at once', () async {
    final sources = [
      aidokuTestAddon('fr.a'),
      aidokuTestAddon('fr.b'),
      aidokuTestAddon('fr.c'),
    ];
    final pending = <PendingPage>[];
    for (final source in sources) {
      final id = source.aidokuSourceId!;
      backend.pages[id] = (call) {
        if (call.page == 1) return Future.value(testPage([testItem('$id-1')]));
        final page = PendingPage();
        pending.add(page);
        return page.completer.future;
      };
    }
    final feed = newFeed();
    await feed.open(sources);
    unawaited(feed.loadMore());
    unawaited(feed.loadMore());
    await settle();
    expect(pending, hasLength(2));
    expect(feed.isLoadingMore, isTrue);
    for (final page in pending) {
      page.complete(testPage(const [], hasMore: false));
    }
    await settle();
    expect(feed.isLoadingMore, isFalse);
  });

  test('loadMore with a source filter only requests that source', () async {
    final a = aidokuTestAddon('fr.a');
    final b = aidokuTestAddon('fr.b');
    for (final id in ['fr.a', 'fr.b']) {
      backend.pages[id] = (call) async =>
          testPage([testItem('$id-${call.page}')], page: call.page);
    }
    final feed = newFeed();
    await feed.open([a, b]);
    backend.calls.clear();
    await feed.loadMore(preferredSourceKey: b.id);
    await feed.loadMore(preferredSourceKey: b.id);
    expect(backend.callsOf('page').map((c) => c.sourceKey), [b.id, b.id]);
  });

  test('loadMore stops at an empty or final page', () async {
    final source = aidokuTestAddon('fr.a');
    backend.pages['fr.a'] = (call) async => call.page == 1
        ? testPage([testItem('one')])
        : testPage([testItem('one')], hasMore: true);
    final feed = newFeed();
    await feed.open([source]);
    await feed.loadMore();
    expect(
      feed.source(source.id)!.exhausted,
      isTrue,
      reason: 'page 2 added nothing new',
    );
    expect(feed.canLoadMore, isFalse);
  });

  test('safe mode neither shows nor requests primarily NSFW sources', () async {
    final safe = aidokuTestAddon('fr.safe');
    final adult = aidokuTestAddon('fr.adult', contentRating: 2);
    backend.pages['fr.safe'] = (_) async => testPage([testItem('safe')]);
    backend.pages['fr.adult'] = (_) async => testPage([testItem('adult')]);
    final feed = newFeed();
    await feed.open([safe, adult]);
    expect(backend.callsOf('page').map((c) => c.sourceKey), [safe.id]);
    expect(feed.isHiddenBySafeMode(feed.source(adult.id)!), isTrue);

    feed.safeMode = false;
    await settle(20);
    expect(backend.callsOf('page').map((c) => c.sourceKey), [
      safe.id,
      adult.id,
    ]);
    expect(titles(feed), ['safe', 'adult']);
  });

  test('a removed source is dropped and its late answer ignored', () async {
    final a = aidokuTestAddon('fr.a');
    final pending = PendingPage();
    backend.pages['fr.a'] = (_) => pending.completer.future;
    final feed = newFeed();
    unawaited(feed.open([a]));
    await settle();
    final cancel = backend.callsOf('page').single.cancel!;
    await feed.open(const []);
    expect(feed.sources, isEmpty);
    expect(cancel.isCancelled, isTrue);
    pending.complete(testPage([testItem('late')]));
    await settle();
    expect(feed.entries, isEmpty);
  });

  test(
    'catalogue sources show their cached copy, then the catalogue',
    () async {
      final gallica = catalogTestAddon('gallica', gallica: true);
      backend.cachedCatalogs[gallica.id] = [testItem('cached')];
      final completer = Completer<List<dynamic>>();
      backend.catalogs[gallica.id] = (_) async {
        await completer.future;
        return [testItem('fresh')];
      };
      final feed = newFeed();
      final opening = feed.open([gallica]);
      await settle();
      expect(titles(feed), ['cached']);
      expect(feed.entries.single.languages, {
        'fr',
      }, reason: 'Gallica entries default to French');
      completer.complete(const []);
      await opening;
      expect(titles(feed), ['fresh']);
      expect(feed.source(gallica.id)!.kind, LibraryFeedSourceKind.catalog);
    },
  );

  test('version and contentVersion grow monotonically', () async {
    final source = aidokuTestAddon('fr.a');
    backend.pages['fr.a'] = (_) async => testPage([testItem('one')]);
    final feed = newFeed();
    final versions = <int>[];
    final contents = <int>[];
    feed.addListener(() {
      versions.add(feed.version);
      contents.add(feed.contentVersion);
    });
    await feed.open([source]);
    await settle();
    expect(versions, isNotEmpty);
    for (var i = 1; i < versions.length; i++) {
      expect(versions[i], greaterThan(versions[i - 1]));
      expect(contents[i], greaterThanOrEqualTo(contents[i - 1]));
    }
  });
}
