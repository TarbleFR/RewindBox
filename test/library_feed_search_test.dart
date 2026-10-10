// Behaviour of LibraryCatalogFeed.search: minimum length, progressive
// per-source results, cancellation of superseded queries, per-source
// timeout, skipped blocked sources and metadata providers.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';

import 'library_feed_test_fakes.dart';

void main() {
  late FakeFeedBackend backend;

  LibraryCatalogFeed newFeed({
    Duration searchTimeout = const Duration(seconds: 10),
  }) {
    final feed = LibraryCatalogFeed(
      backend: backend,
      clock: TestClock().call,
      searchTimeout: searchTimeout,
    );
    addTearDown(feed.dispose);
    return feed;
  }

  setUp(() => backend = FakeFeedBackend());

  Future<LibraryCatalogFeed> openFeed(List<String> sourceIds) async {
    for (final id in sourceIds) {
      backend.cachedPages[id] = testPage([
        testItem('$id-listing'),
      ], fetchedAt: TestClock().now);
    }
    final feed = newFeed();
    await feed.open([for (final id in sourceIds) aidokuTestAddon(id)]);
    return feed;
  }

  test('queries shorter than two characters never reach a source', () async {
    backend.pages['fr.a'] = (_) async => testPage([testItem('x')]);
    final feed = await openFeed(['fr.a']);
    await feed.search('a');
    await feed.search('  b ');
    expect(backend.callsOf('page'), isEmpty);
    expect(feed.currentSearch, isNull);
  });

  test('results are published per source as they arrive', () async {
    final pendingA = PendingPage();
    final pendingB = PendingPage();
    backend.pages['fr.a'] = (_) => pendingA.completer.future;
    backend.pages['fr.b'] = (_) => pendingB.completer.future;
    final feed = await openFeed(['fr.a', 'fr.b']);

    final searching = feed.search('solo');
    await settle();
    final search = feed.currentSearch!;
    expect(search.query, 'solo');
    expect(search.searching, isTrue);
    expect(backend.callsOf('page').map((c) => '${c.sourceKey}:${c.query}'), [
      'aidoku.fr.a:solo',
      'aidoku.fr.b:solo',
    ]);

    pendingB.complete(testPage([testItem('Solo B')]));
    await settle();
    expect(feed.currentSearch!.entries.map((e) => e.item.title), ['Solo B']);
    final statuses = {
      for (final source in feed.currentSearch!.sources)
        source.key: source.status,
    };
    expect(statuses['aidoku.fr.a'], LibraryFeedSearchStatus.searching);
    expect(statuses['aidoku.fr.b'], LibraryFeedSearchStatus.done);

    pendingA.fail(
      const LibraryNetworkException(
        LibraryNetworkErrorKind.timeout,
        detail: 'socket timed out',
      ),
    );
    await searching;
    final a = feed.currentSearch!.sources.firstWhere(
      (source) => source.key == 'aidoku.fr.a',
    );
    expect(a.status, LibraryFeedSearchStatus.failed);
    expect(a.failure!.issue, LibraryFeedIssue.timeout);
    expect(feed.currentSearch!.searching, isFalse);
  });

  test(
    'a new query cancels the previous one and its late results are dropped',
    () async {
      final pending = <String, PendingPage>{};
      backend.pages['fr.a'] = (call) {
        final page = PendingPage();
        pending[call.query] = page;
        return page.completer.future;
      };
      final feed = await openFeed(['fr.a']);

      unawaited(feed.search('one piece'));
      await settle();
      final firstToken = backend.callsOf('page').single.cancel!;
      expect(firstToken.isCancelled, isFalse);

      final second = feed.search('naruto');
      await settle();
      expect(firstToken.isCancelled, isTrue);
      expect(feed.currentSearch!.query, 'naruto');

      pending['one piece']!.complete(testPage([testItem('One Piece')]));
      await settle();
      expect(
        feed.currentSearch!.entries,
        isEmpty,
        reason: 'results of the superseded query are never applied',
      );

      pending['naruto']!.complete(testPage([testItem('Naruto')]));
      await second;
      expect(feed.currentSearch!.entries.map((e) => e.item.title), ['Naruto']);
    },
  );

  test('clearSearch cancels the running search', () async {
    final pending = PendingPage();
    backend.pages['fr.a'] = (_) => pending.completer.future;
    final feed = await openFeed(['fr.a']);
    unawaited(feed.search('solo'));
    await settle();
    final token = backend.callsOf('page').single.cancel!;
    feed.clearSearch();
    expect(feed.currentSearch, isNull);
    await settle();
    expect(token.isCancelled, isTrue, reason: 'the request is aborted');
    pending.complete(testPage([testItem('Solo')]));
    await settle();
    expect(feed.currentSearch, isNull);
  });

  test(
    'a source that does not answer in time is marked as timed out',
    () async {
      backend.pages['fr.slow'] = (_) =>
          Completer<LibraryMangaCatalogPage>().future;
      backend.pages['fr.quick'] = (_) async => testPage([testItem('Solo')]);
      for (final id in ['fr.slow', 'fr.quick']) {
        backend.cachedPages[id] = testPage([], fetchedAt: TestClock().now);
      }
      final feed = newFeed(searchTimeout: const Duration(milliseconds: 40));
      await feed.open([
        aidokuTestAddon('fr.slow'),
        aidokuTestAddon('fr.quick'),
      ]);

      final searching = feed.search('solo');
      await settle();
      final quick = feed.currentSearch!.sources.firstWhere(
        (source) => source.key == 'aidoku.fr.quick',
      );
      expect(quick.status, LibraryFeedSearchStatus.done);

      await searching.timeout(const Duration(seconds: 2));
      final slow = feed.currentSearch!.sources.firstWhere(
        (source) => source.key == 'aidoku.fr.slow',
      );
      expect(slow.status, LibraryFeedSearchStatus.failed);
      expect(slow.failure!.issue, LibraryFeedIssue.timeout);
      expect(backend.callsOf('page').first.cancel!.isCancelled, isTrue);
    },
  );

  test('sources verified as blocked are skipped with their reason', () async {
    backend.support['fr.blocked'] = blockedSupport(
      'fr.blocked',
      LibrarySourceKnownState.parked,
    );
    backend.pages['fr.ok'] = (_) async => testPage([testItem('Solo')]);
    backend.cachedPages['fr.ok'] = testPage([], fetchedAt: TestClock().now);
    final feed = newFeed();
    await feed.open([aidokuTestAddon('fr.blocked'), aidokuTestAddon('fr.ok')]);

    await feed.search('solo');
    final blocked = feed.currentSearch!.sources.firstWhere(
      (source) => source.key == 'aidoku.fr.blocked',
    );
    expect(blocked.status, LibraryFeedSearchStatus.skipped);
    expect(blocked.failure!.issue, LibraryFeedIssue.parked);
    expect(backend.callsOf('page').map((c) => c.sourceKey), ['aidoku.fr.ok']);
  });

  test('metadata providers are searched and attributed', () async {
    backend.providers = {'anilist': 'AniList'};
    backend.metadataSearch['anilist'] = (query) async => [
      testItem('a1', title: 'Solo Leveling', raw: {'isAdult': false}),
    ];
    final feed = newFeed();
    await feed.open(const []);
    await feed.search('solo');
    final source = feed.currentSearch!.sources.single;
    expect(source.key, 'provider:anilist');
    expect(source.name, 'AniList');
    expect(source.kind, LibraryFeedSourceKind.metadata);
    final entry = feed.currentSearch!.entries.single;
    expect(entry.providerId, 'anilist');
    expect(entry.identity, 'provider:anilist|a1');
    expect(backend.callsOf('metadata').single.query, 'solo');
  });

  test(
    'a provider that cannot be cancelled releases the search at once',
    () async {
      backend.providers = {'slow': 'Slow provider'};
      final never = Completer<List<LibraryCatalogItem>>();
      backend.metadataSearch['slow'] = (_) => never.future;
      final feed = newFeed();
      await feed.open(const []);
      final first = feed.search('solo');
      await settle();
      feed.clearSearch();
      await first.timeout(const Duration(seconds: 1));
    },
  );
}
