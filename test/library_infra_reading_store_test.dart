import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:path/path.dart' as p;

class _RecordingPinner implements LibraryCoverPinner {
  final List<String> events = <String>[];
  final Set<String> pinned = <String>{};

  @override
  Future<void> pin(
    String url, {
    Map<String, String> headers = const <String, String>{},
    bool fetch = false,
  }) async {
    events.add('pin $url fetch=$fetch referer=${headers['Referer']}');
    pinned.add(url);
  }

  @override
  Future<void> unpin(String url) async {
    events.add('unpin $url');
    pinned.remove(url);
  }
}

void main() {
  late Directory tmp;
  late DateTime now;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('library_infra_reading_');
    now = DateTime.utc(2026, 10, 10, 12);
  });

  tearDown(() async {
    try {
      await tmp.delete(recursive: true);
    } catch (_) {}
  });

  File stateFile() => File(p.join(tmp.path, LibraryReadingStore.fileName));

  LibraryReadingStore create({
    Duration saveDelay = const Duration(milliseconds: 40),
    LibraryCoverPinner? pinner,
    int maxProgressEntries = 2000,
  }) {
    return LibraryReadingStore(
      directory: tmp,
      clock: () => now,
      saveDelay: saveDelay,
      coverPinner: pinner,
      maxProgressEntries: maxProgressEntries,
    );
  }

  LibraryFavorite favorite(String sourceId, String mangaId, {String? cover}) =>
      LibraryFavorite(
        key: LibraryReadingStore.onlineKey(sourceId, mangaId),
        sourceId: sourceId,
        addonId: 'aidoku.$sourceId',
        mangaId: mangaId,
        title: 'Title $mangaId',
        coverUrl: cover,
        coverHeaders: const <String, String>{'Referer': 'https://a.test/'},
        mangaUrl: 'https://a.test/manga/$mangaId',
        language: 'fr',
        snapshot: <String, Object?>{
          'id': mangaId,
          'tags': <String>['action', 'drama'],
          'nested': <String, Object?>{'rating': 2, 'date': DateTime.utc(2026)},
        },
      );

  test('keys separate local books and online titles', () {
    expect(LibraryReadingStore.localKey('abc'), 'local:abc');
    expect(
      LibraryReadingStore.onlineKey('fr.sushiscan', 'black-clover'),
      'online:fr.sushiscan:black-clover',
    );
    expect(
      LibraryReadingStore.kindOfKey('online:fr.lelscanfr:x'),
      LibraryReadingKind.online,
    );
    expect(
      LibraryReadingStore.kindOfKey('local:book'),
      LibraryReadingKind.local,
    );
  });

  test('state round-trips through the JSON file', () async {
    final store = create();
    await store.load();
    final bookKey = LibraryReadingStore.localKey('book-1');
    final mangaKey = LibraryReadingStore.onlineKey('fr.lelscanfr', 'maria');
    store.saveProgress(
      LibraryReadingProgress(
        key: bookKey,
        location: 'epubcfi(/6/4!/4/2/1:0)',
        fraction: 0.42,
        chapterTitle: 'Chapitre 3',
        title: 'Livre',
        subtitle: 'Auteur',
        coverUrl: 'file:///cover.jpg',
      ),
    );
    now = now.add(const Duration(minutes: 1));
    store.saveProgress(
      LibraryReadingProgress(
        key: mangaKey,
        location: LibraryReadingProgress.pageLocation(7),
        fraction: 1.7,
        pageIndex: 7,
        pageCount: 20,
        chapterId: 'ch-32',
        coverHeaders: const <String, String>{'Referer': 'https://l.test/'},
      ),
    );
    store.markChapter(mangaKey, 'ch-31', read: true);
    store.markChapter(mangaKey, 'ch-32', page: 7, pageCount: 20);
    await store.addFavorite(
      favorite('fr.lelscanfr', 'maria', cover: 'https://img.test/m.jpg'),
    );
    store.updateSettings(
      store.settings.copyWith(
        fontSize: 22,
        theme: LibraryReaderTheme.sepia,
        pageDirection: LibraryPageDirection.rtl,
        mangaMode: LibraryMangaMode.vertical,
        allowRotation: false,
      ),
    );
    await store.flush();
    expect(store.hasPendingChanges, isFalse);

    final reopened = create();
    await reopened.load();
    final book = reopened.progressFor(bookKey)!;
    expect(book.location, 'epubcfi(/6/4!/4/2/1:0)');
    expect(book.fraction, closeTo(0.42, 1e-9));
    expect(book.kind, LibraryReadingKind.local);
    expect(book.chapterTitle, 'Chapitre 3');
    expect(book.subtitle, 'Auteur');
    expect(book.updatedAt, DateTime.utc(2026, 10, 10, 12));

    final manga = reopened.progressFor(mangaKey)!;
    expect(manga.fraction, 1.0);
    expect(manga.locationPage, 7);
    expect(manga.pageCount, 20);
    expect(manga.kind, LibraryReadingKind.online);
    expect(manga.coverHeaders['Referer'], 'https://l.test/');

    expect(reopened.chapterMark(mangaKey, 'ch-31')!.read, isTrue);
    final ch32 = reopened.chapterMark(mangaKey, 'ch-32')!;
    expect(ch32.read, isFalse);
    expect(ch32.page, 7);
    expect(ch32.pageCount, 20);

    final saved = reopened.favorite(mangaKey)!;
    expect(saved.addonId, 'aidoku.fr.lelscanfr');
    expect(saved.coverUrl, 'https://img.test/m.jpg');
    expect(saved.snapshot['tags'], <String>['action', 'drama']);
    expect(
      (saved.snapshot['nested'] as Map)['date'],
      DateTime.utc(2026).toString(),
    );
    expect(saved.addedAt, now);

    expect(reopened.settings.fontSize, 22);
    expect(reopened.settings.theme, LibraryReaderTheme.sepia);
    expect(reopened.settings.pageDirection, LibraryPageDirection.rtl);
    expect(reopened.settings.mangaMode, LibraryMangaMode.vertical);
    expect(reopened.settings.allowRotation, isFalse);
    expect(reopened.settings, store.settings);
  });

  test('writes are debounced and flush writes immediately', () async {
    final store = create(saveDelay: const Duration(milliseconds: 150));
    await store.load();
    var notifications = 0;
    store.addListener(() => notifications++);
    for (var page = 0; page < 5; page++) {
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:b',
          location: LibraryReadingProgress.pageLocation(page),
          fraction: page / 10,
        ),
      );
    }
    expect(notifications, 5);
    await Future<void>.delayed(const Duration(milliseconds: 40));
    expect(await stateFile().exists(), isFalse);

    await Future<void>.delayed(const Duration(milliseconds: 400));
    expect(await stateFile().exists(), isTrue);
    final written = jsonDecode(await stateFile().readAsString()) as Map;
    expect((written['progress'] as Map)['local:b']['location'], 'page:4');

    store.saveProgress(
      LibraryReadingProgress(key: 'local:b', location: 'page:9', fraction: 1),
    );
    await store.flush();
    final flushed = jsonDecode(await stateFile().readAsString()) as Map;
    expect((flushed['progress'] as Map)['local:b']['location'], 'page:9');
    expect(
      await File('${stateFile().path}.tmp').exists(),
      isFalse,
      reason: 'atomic write leaves no temporary file',
    );
  });

  test('a missing file starts empty', () async {
    final store = create();
    await store.load();
    expect(store.isLoaded, isTrue);
    expect(store.recent(), isEmpty);
    expect(store.favorites, isEmpty);
    expect(store.settings, const LibraryReaderSettings());
  });

  test('a corrupt file is preserved and the store starts empty', () async {
    await stateFile().writeAsString('{"progress": {"local:a": ');
    final store = create();
    await store.load();
    expect(store.recent(), isEmpty);
    final corrupt = File(
      '${stateFile().path}${LibraryReadingStore.corruptSuffix}',
    );
    expect(await corrupt.readAsString(), '{"progress": {"local:a": ');

    store.saveProgress(
      LibraryReadingProgress(key: 'local:a', location: 'page:1', fraction: 0.1),
    );
    await store.flush();
    final reopened = create();
    await reopened.load();
    expect(reopened.progressFor('local:a')!.location, 'page:1');
  });

  test('invalid entries are skipped, valid ones kept', () async {
    await stateFile().writeAsString(
      jsonEncode(<String, Object?>{
        'version': 1,
        'progress': <String, Object?>{
          'local:ok': <String, Object?>{
            'key': 'local:ok',
            'location': 'txt:120',
            'fraction': 0.5,
            'updatedAt': 1,
          },
          'local:bad': <String, Object?>{'key': 'local:bad'},
        },
        'favorites': <String, Object?>{'x': 'not a favourite'},
        'settings': <String, Object?>{
          'fontSize': 99,
          'lineHeight': 'big',
          'theme': 'neon',
          'justify': false,
        },
      }),
    );
    final store = create();
    await store.load();
    expect(store.progressFor('local:ok')!.location, 'txt:120');
    expect(store.progressFor('local:bad'), isNull);
    expect(store.favorites, isEmpty);
    expect(store.settings.fontSize, LibraryReaderSettings.maxFontSize);
    expect(store.settings.lineHeight, 1.5);
    expect(store.settings.theme, LibraryReaderTheme.system);
    expect(store.settings.justify, isFalse);
    expect(
      await File(
        '${stateFile().path}${LibraryReadingStore.corruptSuffix}',
      ).exists(),
      isFalse,
    );
  });

  test(
    'changes made before load are merged, never overwrite the file',
    () async {
      final seed = create();
      await seed.load();
      await seed.addFavorite(favorite('fr.sushiscan', 'one-piece'));
      seed.saveProgress(
        LibraryReadingProgress(
          key: 'local:old',
          location: 'page:3',
          fraction: 0.3,
        ),
      );
      await seed.flush();

      final store = create(saveDelay: const Duration(milliseconds: 10));
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:new',
          location: 'page:1',
          fraction: 0.1,
        ),
      );
      await Future<void>.delayed(const Duration(milliseconds: 60));
      final untouched = jsonDecode(await stateFile().readAsString()) as Map;
      expect((untouched['progress'] as Map).containsKey('local:new'), isFalse);

      await store.load();
      expect(store.progressFor('local:new'), isNotNull);
      expect(store.progressFor('local:old'), isNotNull);
      expect(
        store.isFavorite(
          LibraryReadingStore.onlineKey('fr.sushiscan', 'one-piece'),
        ),
        isTrue,
      );
      await store.flush();
      final merged = jsonDecode(await stateFile().readAsString()) as Map;
      expect(
        (merged['progress'] as Map).keys,
        containsAll(<String>['local:new', 'local:old']),
      );
    },
  );

  test('removals requested before load apply to the loaded data', () async {
    final seed = create();
    await seed.load();
    final fav = favorite('fr.sushiscan', 'gone');
    await seed.addFavorite(fav);
    seed.saveProgress(
      LibraryReadingProgress(key: 'local:x', location: 'page:3', fraction: 0.3),
    );
    seed.markChapter(fav.key, 'c1', read: true);
    await seed.flush();

    final store = create();
    store.removeProgress('local:x');
    store.clearChapterMarks(fav.key);
    await store.removeFavorite(fav.key);
    await store.load();
    expect(store.progressFor('local:x'), isNull);
    expect(store.chapterMarks(fav.key), isEmpty);
    expect(store.isFavorite(fav.key), isFalse);
    await store.flush();
    final reopened = create();
    await reopened.load();
    expect(reopened.progressFor('local:x'), isNull);
    expect(reopened.isFavorite(fav.key), isFalse);
  });

  test('recent lists the most recently updated entries first', () async {
    final store = create();
    await store.load();
    for (final id in <String>['a', 'b', 'c']) {
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:$id',
          location: 'page:0',
          fraction: 0,
        ),
      );
      now = now.add(const Duration(minutes: 1));
    }
    store.saveProgress(
      LibraryReadingProgress(
        key: LibraryReadingStore.onlineKey('fr.sushiscan', 'x'),
        location: 'page:2',
        fraction: 0.2,
      ),
    );
    now = now.add(const Duration(minutes: 1));
    store.saveProgress(
      LibraryReadingProgress(key: 'local:a', location: 'page:5', fraction: 0.5),
    );

    expect(store.recent().map((entry) => entry.key), <String>[
      'local:a',
      'online:fr.sushiscan:x',
      'local:c',
      'local:b',
    ]);
    expect(store.recent(limit: 2).map((entry) => entry.key), <String>[
      'local:a',
      'online:fr.sushiscan:x',
    ]);
    expect(
      store.recent(kind: LibraryReadingKind.local).map((entry) => entry.key),
      <String>['local:a', 'local:c', 'local:b'],
    );
  });

  test('favourites survive removal of unrelated keys and data', () async {
    final pinner = _RecordingPinner();
    final store = create(pinner: pinner);
    await store.load();
    final kept = favorite('fr.lelscanfr', 'maria', cover: 'https://img.test/a');
    final other = favorite(
      'fr.sushiscan',
      'clover',
      cover: 'https://img.test/b',
    );
    await store.addFavorite(kept);
    now = now.add(const Duration(minutes: 1));
    await store.addFavorite(other);
    store.saveProgress(
      LibraryReadingProgress(key: kept.key, location: 'page:1', fraction: 0.1),
    );
    store.markChapter(kept.key, 'c1', read: true);

    store.removeProgress(kept.key);
    store.clearChapterMarks(kept.key);
    await store.removeFavorite(other.key);
    store.removeProgress('online:fr.unknown:gone');

    expect(store.isFavorite(kept.key), isTrue);
    expect(store.favorites.map((entry) => entry.key), <String>[kept.key]);
    await store.flush();
    final reopened = create();
    await reopened.load();
    expect(reopened.isFavorite(kept.key), isTrue);
    expect(reopened.isFavorite(other.key), isFalse);
    expect(reopened.favorite(kept.key)!.title, 'Title maria');
  });

  test('favourite covers are pinned and unpinned when unused', () async {
    final pinner = _RecordingPinner();
    final store = create(pinner: pinner);
    await store.load();
    const shared = 'https://img.test/shared.jpg';
    final first = favorite('fr.lelscanfr', 'a', cover: shared);
    final second = favorite('fr.sushiscan', 'b', cover: shared);
    await store.addFavorite(first);
    expect(
      pinner.events.single,
      'pin $shared fetch=true referer=https://a.test/',
    );
    await store.addFavorite(second);
    final firstAddedAt = store.favorite(first.key)!.addedAt;

    now = now.add(const Duration(hours: 1));
    await store.addFavorite(first.copyWith(title: 'Renamed'));
    expect(store.favorite(first.key)!.title, 'Renamed');
    expect(store.favorite(first.key)!.addedAt, firstAddedAt);

    await store.removeFavorite(first.key);
    expect(pinner.pinned, contains(shared));
    await store.removeFavorite(second.key);
    expect(pinner.pinned, isNot(contains(shared)));

    // Favourites re-pin their covers after a reload (the cache directory
    // may have been purged by iOS).
    await store.addFavorite(favorite('fr.lelscanfr', 'c', cover: shared));
    await store.flush();
    final restoredPinner = _RecordingPinner();
    final reopened = create(pinner: restoredPinner);
    await reopened.load();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(restoredPinner.pinned, <String>{shared});
    expect(restoredPinner.events.single, contains('fetch=false'));
  });

  test('toggleFavorite and setFavorite agree', () async {
    final store = create();
    await store.load();
    final entry = favorite('fr.lelscanfr', 'z');
    expect(await store.toggleFavorite(entry), isTrue);
    expect(store.isFavorite(entry.key), isTrue);
    await store.setFavorite(entry, false);
    expect(store.isFavorite(entry.key), isFalse);
  });

  test('chapter marks merge partial updates', () async {
    final store = create();
    await store.load();
    const key = 'online:fr.sushiscan:clover';
    store.markChapter(key, '391', page: 3, pageCount: 18);
    store.markChapter(key, '391', read: true);
    store.setChaptersRead(key, <String>['389', '390'], read: true);
    final marks = store.chapterMarks(key);
    expect(marks.keys, containsAll(<String>['389', '390', '391']));
    expect(marks['391']!.read, isTrue);
    expect(marks['391']!.page, 3);
    expect(marks['391']!.pageCount, 18);
    store.setChaptersRead(key, <String>['391'], read: false);
    expect(store.chapterMark(key, '391')!.read, isFalse);
    expect(store.chapterMark(key, '391')!.page, 3);
  });

  test('the progress limit drops the oldest non-favourite entries', () async {
    final store = create(maxProgressEntries: 3);
    await store.load();
    final fav = favorite('fr.lelscanfr', 'oldest');
    await store.addFavorite(fav);
    store.saveProgress(
      LibraryReadingProgress(key: fav.key, location: 'page:0', fraction: 0),
    );
    for (final id in <String>['a', 'b', 'c']) {
      now = now.add(const Duration(minutes: 1));
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:$id',
          location: 'page:0',
          fraction: 0,
        ),
      );
    }
    expect(store.progressFor(fav.key), isNotNull);
    expect(store.progressFor('local:a'), isNull);
    expect(store.recent().map((entry) => entry.key), <String>[
      'local:c',
      'local:b',
      fav.key,
    ]);
  });

  test('settings clamp their ranges', () {
    const settings = LibraryReaderSettings();
    expect(settings.fontSize, 18);
    expect(settings.allowRotation, isTrue);
    final clamped = settings.copyWith(fontSize: 4, lineHeight: 9, margin: -3);
    expect(clamped.fontSize, LibraryReaderSettings.minFontSize);
    expect(clamped.lineHeight, LibraryReaderSettings.maxLineHeight);
    expect(clamped.margin, LibraryReaderSettings.minMargin);
    expect(LibraryReaderSettings.fromJson(clamped.toJson()), clamped);
  });
}
