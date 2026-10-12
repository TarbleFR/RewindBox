// Build 447 additions to LibraryReadingStore (docs/library-books-3d-plan.md
// § 3.7 and § 3.9): bookmarks and per-title navigation settings, kept in
// reading-state.json under version 1.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_bookmarks.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:path/path.dart' as p;

void main() {
  late Directory tmp;
  late DateTime now;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('library_bookmarks_');
    now = DateTime.utc(2026, 10, 12, 9);
  });

  tearDown(() async {
    try {
      await tmp.delete(recursive: true);
    } catch (_) {}
  });

  File stateFile() => File(p.join(tmp.path, LibraryReadingStore.fileName));
  File tmpFile() => File('${stateFile().path}.tmp');
  File corruptFile() =>
      File('${stateFile().path}${LibraryReadingStore.corruptSuffix}');

  LibraryReadingStore create({
    int maxProgressEntries = 2000,
    int maxChapterMarkTitles = 1000,
    int maxBookSettingsTitles = 1000,
  }) {
    return LibraryReadingStore(
      directory: tmp,
      clock: () => now,
      saveDelay: const Duration(milliseconds: 40),
      maxProgressEntries: maxProgressEntries,
      maxChapterMarkTitles: maxChapterMarkTitles,
      maxBookSettingsTitles: maxBookSettingsTitles,
    );
  }

  LibraryBookmark mark(
    String key,
    String id, {
    String? location,
    double fraction = 0.5,
    DateTime? createdAt,
    String? chapterId,
    String? chapterTitle,
    int? pageIndex,
    String? label,
  }) => LibraryBookmark(
    id: id,
    key: key,
    location: location ?? 'page:$id',
    fraction: fraction,
    chapterId: chapterId,
    chapterTitle: chapterTitle,
    pageIndex: pageIndex,
    label: label,
    createdAt: createdAt ?? now,
  );

  Future<Map<String, Object?>> written() async =>
      jsonDecode(await stateFile().readAsString()) as Map<String, Object?>;

  Future<void> writeState(Map<String, Object?> state) =>
      stateFile().writeAsString(jsonEncode(state));

  /// Lets a write scheduled by a change (saveDelay 40 ms) happen.
  Future<void> pastSaveDelay() =>
      Future<void>.delayed(const Duration(milliseconds: 150));

  group('bookmarks', () {
    test('are listed in reading order, removed by id and saved', () async {
      const key = 'local:book';
      final store = create();
      await store.load();
      var notifications = 0;
      store.addListener(() => notifications++);

      final late = mark(key, 'late', location: 'page:30', fraction: 0.6);
      final early = mark(key, 'early', location: 'page:10', fraction: 0.2);
      // Same fraction as [late], created before it.
      final sameSpot = mark(
        key,
        'same',
        location: 'epubcfi(/6/4!/4/2/1:0)',
        fraction: 0.6,
        createdAt: now.subtract(const Duration(minutes: 1)),
      );
      final other = mark('online:s:m', 'o', chapterId: 'c4', pageIndex: 3);
      expect(store.addBookmark(late), isTrue);
      expect(store.addBookmark(early), isTrue);
      expect(store.addBookmark(sameSpot), isTrue);
      expect(store.addBookmark(other), isTrue);
      expect(notifications, 4);

      expect(store.bookmarksFor(key), <LibraryBookmark>[early, sameSpot, late]);
      expect(store.bookmarkAt(key, 'page:30'), late);
      expect(store.bookmarkAt(key, 'epubcfi(/6/4!/4/2/1:0)'), sameSpot);
      expect(store.bookmarkAt(key, 'page:31'), isNull);
      expect(store.bookmarkAt('local:absent', 'page:30'), isNull);
      expect(store.bookmarksFor('local:absent'), isEmpty);
      expect(
        () => store.bookmarksFor(key).add(early),
        throwsUnsupportedError,
        reason: 'callers cannot change the stored list',
      );

      store.removeBookmark(key, 'same');
      expect(notifications, 5);
      expect(store.bookmarksFor(key), <LibraryBookmark>[early, late]);
      // Nothing to remove: no change, no notification.
      store.removeBookmark(key, 'unknown');
      store.removeBookmark('local:absent', 'late');
      expect(notifications, 5);

      await store.flush();
      expect(store.lastSaveError, isNull);
      final reopened = create();
      await reopened.load();
      expect(reopened.bookmarksFor(key), <LibraryBookmark>[early, late]);
      expect(reopened.bookmarksFor('online:s:m'), <LibraryBookmark>[other]);
      expect(reopened.bookmarkAt('online:s:m', 'page:o')!.chapterId, 'c4');

      // A title whose last bookmark is removed leaves the file.
      reopened.removeBookmark('online:s:m', 'o');
      expect(reopened.bookmarksFor('online:s:m'), isEmpty);
      await reopened.flush();
      final bookmarks = (await written())['bookmarks'] as Map;
      expect(bookmarks.keys, <String>[key]);
    });

    test(
      'a title at 500 bookmarks refuses the next one and writes nothing',
      () async {
        const key = 'local:full';
        expect(LibraryReadingStore.maxBookmarksPerTitle, 500);
        final store = create();
        await store.load();
        for (var index = 0; index < 500; index++) {
          expect(
            store.addBookmark(mark(key, 'b$index', fraction: index / 500)),
            isTrue,
          );
        }
        await store.flush();
        expect(store.hasPendingChanges, isFalse);
        final saved = await stateFile().readAsString();
        final savedAt = await stateFile().lastModified();
        var notifications = 0;
        store.addListener(() => notifications++);

        expect(store.addBookmark(mark(key, 'b500')), isFalse);
        expect(notifications, 0);
        expect(store.hasPendingChanges, isFalse);
        expect(store.bookmarksFor(key), hasLength(500));
        expect(store.bookmarkAt(key, 'page:b500'), isNull);
        await pastSaveDelay();
        expect(await stateFile().readAsString(), saved);
        expect(await stateFile().lastModified(), savedAt);
        expect(await tmpFile().exists(), isFalse);

        // The limit is per title.
        expect(store.addBookmark(mark('local:other', 'x')), isTrue);
        // A removal makes room again.
        store.removeBookmark(key, 'b0');
        expect(store.addBookmark(mark(key, 'b500')), isTrue);
        expect(store.bookmarksFor(key), hasLength(500));
        await store.flush();
        final reopened = create();
        await reopened.load();
        expect(reopened.bookmarksFor(key), hasLength(500));
        expect(reopened.bookmarkAt(key, 'page:b500'), isNotNull);
        expect(reopened.bookmarkAt(key, 'page:b0'), isNull);
      },
    );

    test('a marked location, a repeated id or an incomplete bookmark is '
        'refused without any write', () async {
      const key = 'local:book';
      final store = create();
      await store.load();
      expect(store.addBookmark(mark(key, 'a', location: 'page:3')), isTrue);
      await store.flush();
      final saved = await stateFile().readAsString();
      var notifications = 0;
      store.addListener(() => notifications++);

      expect(store.addBookmark(mark(key, 'b', location: 'page:3')), isFalse);
      expect(store.addBookmark(mark(key, 'a', location: 'page:4')), isFalse);
      expect(store.addBookmark(mark(key, '', location: 'page:5')), isFalse);
      expect(store.addBookmark(mark('', 'c', location: 'page:6')), isFalse);
      expect(store.addBookmark(mark(key, 'd', location: '')), isFalse);
      expect(notifications, 0);
      expect(store.hasPendingChanges, isFalse);
      expect(store.bookmarksFor(key).map((bookmark) => bookmark.id), <String>[
        'a',
      ]);
      await pastSaveDelay();
      expect(await stateFile().readAsString(), saved);

      // The same location on another title, or once freed, is accepted.
      expect(
        store.addBookmark(mark('local:other', 'b', location: 'page:3')),
        isTrue,
      );
      store.removeBookmark(key, 'a');
      expect(store.addBookmark(mark(key, 'b', location: 'page:3')), isTrue);
      expect(store.bookmarkAt(key, 'page:3')!.id, 'b');
      await store.flush();
    });

    test('a bookmark is stored as the file reads it back', () async {
      const key = 'online:s:m';
      final store = create();
      await store.load();
      final local = DateTime(2026, 10, 12, 11, 30, 5, 120, 999);
      expect(
        store.addBookmark(
          LibraryBookmark(
            id: 'nan',
            key: key,
            location: 'page:1',
            fraction: double.nan,
            label: '',
            chapterId: '',
            pageIndex: -2,
            createdAt: local,
          ),
        ),
        isTrue,
      );
      expect(
        store.addBookmark(mark(key, 'big', location: 'page:2', fraction: 1.7)),
        isTrue,
      );
      final nan = store.bookmarkAt(key, 'page:1')!;
      expect(nan.fraction, 0.0);
      expect(nan.label, isNull);
      expect(nan.chapterId, isNull);
      expect(nan.pageIndex, isNull);
      expect(nan.createdAt.isUtc, isTrue);
      expect(
        nan.createdAt.millisecondsSinceEpoch,
        local.millisecondsSinceEpoch,
      );
      expect(nan.createdAt.microsecond, 0);
      expect(store.bookmarkAt(key, 'page:2')!.fraction, 1.0);

      // A NaN would make the whole state impossible to encode.
      await store.flush();
      expect(store.lastSaveError, isNull);
      expect(store.hasPendingChanges, isFalse);
      final reopened = create();
      await reopened.load();
      expect(reopened.bookmarksFor(key), store.bookmarksFor(key));
    });

    test('bookmarks and title settings are written under version 1 with the '
        'documented keys, atomically', () async {
      final store = create();
      await store.load();
      final full = mark(
        'online:s:m',
        'id-1',
        location: 'page:7',
        fraction: 0.25,
        chapterId: 'c12',
        chapterTitle: 'Chapitre 12',
        pageIndex: 7,
        label: 'Combat',
      );
      final bare = mark(
        'local:epub',
        'id-2',
        location: 'epubcfi(/6/4!/4/2/1:0)',
      );
      expect(store.addBookmark(full), isTrue);
      expect(store.addBookmark(bare), isTrue);
      store.updateBookSettings(
        'local:epub',
        const LibraryReaderBookSettings(
          turnStyle: LibraryPageTurnStyle.slide,
          pageDirection: LibraryPageDirection.rtl,
        ),
      );
      await store.flush();
      expect(await tmpFile().exists(), isFalse);

      final json = await written();
      expect(json['version'], 1);
      expect(
        json.keys,
        containsAll(<String>[
          'progress',
          'chapterMarks',
          'favorites',
          'settings',
          'bookmarks',
          'bookSettings',
        ]),
      );
      final bookmarks = json['bookmarks'] as Map;
      final fullEntry = (bookmarks['online:s:m'] as List).single as Map;
      expect(fullEntry, <String, Object?>{
        'id': 'id-1',
        'key': 'online:s:m',
        'location': 'page:7',
        'fraction': 0.25,
        'chapterId': 'c12',
        'chapterTitle': 'Chapitre 12',
        'pageIndex': 7,
        'label': 'Combat',
        'createdAt': now.millisecondsSinceEpoch,
      });
      final bareEntry = (bookmarks['local:epub'] as List).single as Map;
      expect(bareEntry.keys, <String>[
        'id',
        'key',
        'location',
        'fraction',
        'createdAt',
      ]);
      expect(json['bookSettings'], <String, Object?>{
        'local:epub': <String, Object?>{
          'turnStyle': 'slide',
          'pageDirection': 'rtl',
          'updatedAt': now.millisecondsSinceEpoch,
        },
      });
    });

    test('a version 1 file with unknown keys loads, and its data survives '
        'the next write', () async {
      await writeState(<String, Object?>{
        'version': 1,
        'progress': <String, Object?>{
          'local:a': LibraryReadingProgress(
            key: 'local:a',
            location: 'page:4',
            fraction: 0.4,
            updatedAt: DateTime.utc(2026),
          ).toJson(),
        },
        'bookmarks': <String, Object?>{
          'local:a': <Object?>[mark('local:a', 'm1').toJson()],
        },
        'bookSettings': <String, Object?>{
          'local:a': <String, Object?>{'textLayout': 'scroll', 'updatedAt': 5},
        },
        'settings': <String, Object?>{'fontSize': 21, 'pdfMode': 'scroll'},
        // Keys of a later build: unknown here.
        'shelves': <Object?>[
          <String, Object?>{
            'name': 'x',
            'keys': <String>['local:a'],
          },
        ],
        'futureFeature': <String, Object?>{'enabled': true, 'level': 3},
        'evictions': <String, Object?>{'progress': 2, 'somethingElse': 4},
      });
      final store = create();
      await store.load();
      expect(store.loadFailed, isFalse);
      expect(await corruptFile().exists(), isFalse);
      expect(store.progressFor('local:a')!.location, 'page:4');
      expect(store.bookmarksFor('local:a'), <LibraryBookmark>[
        mark('local:a', 'm1'),
      ]);
      expect(
        store.bookSettingsFor('local:a'),
        const LibraryReaderBookSettings(textLayout: LibraryTextLayout.scroll),
      );
      expect(
        store.bookSettingsFor('local:a')!.updatedAt,
        DateTime.fromMillisecondsSinceEpoch(5, isUtc: true),
      );
      expect(store.settings.fontSize, 21);
      expect(store.settings.pdfMode, LibraryPdfMode.scroll);
      expect(store.evictedProgressEntries, 2);

      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:b',
          location: 'page:1',
          fraction: 0.1,
        ),
      );
      await store.flush();
      expect(store.lastSaveError, isNull);
      final json = await written();
      expect(json['version'], 1);
      final reopened = create();
      await reopened.load();
      expect(reopened.loadFailed, isFalse);
      expect(reopened.progressFor('local:a')!.location, 'page:4');
      expect(reopened.progressFor('local:b')!.location, 'page:1');
      expect(reopened.bookmarksFor('local:a'), hasLength(1));
      expect(
        reopened.bookSettingsFor('local:a')!.textLayout,
        LibraryTextLayout.scroll,
      );
      expect(reopened.settings.pdfMode, LibraryPdfMode.scroll);
    });

    test('invalid bookmark and title settings entries are skipped, the valid '
        'ones kept', () async {
      final valid = mark('local:a', 'ok', location: 'page:1', fraction: 0.1);
      await writeState(<String, Object?>{
        'version': 1,
        'progress': <String, Object?>{
          'local:a': LibraryReadingProgress(
            key: 'local:a',
            location: 'page:9',
            fraction: 0.9,
          ).toJson(),
        },
        'bookmarks': <String, Object?>{
          'local:a': <Object?>[
            valid.toJson(),
            'not a bookmark',
            42,
            null,
            <String, Object?>{'id': 'no-location', 'key': 'local:a'},
            <String, Object?>{
              'id': 'bad-fraction',
              'key': 'local:a',
              'location': 'page:2',
              'fraction': 'half',
              'createdAt': 1,
            },
            <String, Object?>{
              'id': 'empty-key',
              'key': '',
              'location': 'page:3',
              'fraction': 0.3,
            },
            // Same id as [valid], elsewhere; same location, other id.
            mark('local:a', 'ok', location: 'page:5').toJson(),
            mark('local:a', 'twin', location: 'page:1').toJson(),
            // Kept: an out-of-range date reads as the epoch, wrong optional
            // fields are dropped.
            <String, Object?>{
              'id': 'odd',
              'key': 'local:a',
              'location': 'page:6',
              'fraction': 0.6,
              'createdAt': 9000000000000000,
              'label': 42,
              'chapterId': '',
              'pageIndex': -1,
              'chapterTitle': true,
            },
          ],
          'local:b': 'not a list',
          'local:c': <String, Object?>{'id': 'map'},
        },
        'bookSettings': <String, Object?>{
          'local:a': <String, Object?>{
            'turnStyle': 'warp',
            'doublePage': 'always',
            'firstPageAlone': 'yes',
            'pageDirection': 7,
            'updatedAt': 'today',
          },
          'local:b': 'garbage',
          'local:c': <String, Object?>{'turnStyle': 'warp'},
          '': <String, Object?>{'turnStyle': 'none'},
          'online:s:m': <String, Object?>{
            'turnStyle': 'none',
            'doublePage': 'never',
            'firstPageAlone': false,
            'pageDirection': 'rtl',
            'mangaMode': 'vertical',
            'pdfMode': 'scroll',
            'textLayout': 'scroll',
            'updatedAt': 1234,
          },
        },
      });
      final store = create();
      await store.load();
      expect(store.loadFailed, isFalse);
      expect(await corruptFile().exists(), isFalse);
      expect(store.progressFor('local:a')!.location, 'page:9');

      expect(
        store.bookmarksFor('local:a').map((bookmark) => bookmark.id),
        <String>['ok', 'odd'],
      );
      final odd = store.bookmarkAt('local:a', 'page:6')!;
      expect(
        odd.createdAt,
        DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
      );
      expect(odd.label, isNull);
      expect(odd.chapterId, isNull);
      expect(odd.chapterTitle, isNull);
      expect(odd.pageIndex, isNull);
      expect(store.bookmarksFor('local:b'), isEmpty);
      expect(store.bookmarksFor('local:c'), isEmpty);
      expect(store.bookmarksFor(''), isEmpty);

      expect(
        store.bookSettingsFor('local:a'),
        const LibraryReaderBookSettings(
          doublePage: LibraryDoublePageMode.always,
        ),
      );
      expect(
        store.bookSettingsFor('local:a')!.updatedAt,
        DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
      );
      expect(store.bookSettingsFor('local:b'), isNull);
      expect(store.bookSettingsFor('local:c'), isNull);
      expect(store.bookSettingsFor(''), isNull);
      expect(
        store.bookSettingsFor('online:s:m'),
        const LibraryReaderBookSettings(
          turnStyle: LibraryPageTurnStyle.none,
          doublePage: LibraryDoublePageMode.never,
          firstPageAlone: false,
          pageDirection: LibraryPageDirection.rtl,
          mangaMode: LibraryMangaMode.vertical,
          pdfMode: LibraryPdfMode.scroll,
          textLayout: LibraryTextLayout.scroll,
        ),
      );

      // Containers of the wrong type are ignored as a whole.
      await writeState(<String, Object?>{
        'version': 1,
        'progress': <String, Object?>{
          'local:z': LibraryReadingProgress(
            key: 'local:z',
            location: 'page:2',
            fraction: 0.2,
          ).toJson(),
        },
        'bookmarks': <Object?>[valid.toJson()],
        'bookSettings': 'scroll',
      });
      final other = create();
      await other.load();
      expect(other.loadFailed, isFalse);
      expect(await corruptFile().exists(), isFalse);
      expect(other.progressFor('local:z'), isNotNull);
      expect(other.bookmarksFor('local:a'), isEmpty);
      expect(other.bookSettingsFor('local:a'), isNull);
    });

    test('bookmarks are never dropped by any limit', () async {
      final store = create(
        maxProgressEntries: 1,
        maxChapterMarkTitles: 1,
        maxBookSettingsTitles: 1,
      );
      await store.load();
      final keys = <String>[
        for (var index = 0; index < 15; index++) 'online:s:m$index',
        for (var index = 0; index < 15; index++) 'local:b$index',
      ];
      for (final key in keys) {
        now = now.add(const Duration(minutes: 1));
        expect(store.addBookmark(mark(key, 'k')), isTrue);
        store.saveProgress(
          LibraryReadingProgress(key: key, location: 'page:0', fraction: 0),
        );
        store.markChapter(key, 'c1', read: true);
        store.updateBookSettings(
          key,
          const LibraryReaderBookSettings(turnStyle: LibraryPageTurnStyle.none),
        );
      }
      // The other limits did apply.
      expect(store.evictedChapterMarkTitles, greaterThan(0));
      expect(store.evictedBookSettingsTitles, greaterThan(0));
      for (final key in keys) {
        expect(store.bookmarksFor(key), hasLength(1), reason: key);
        // A title with bookmarks keeps its reading position.
        expect(store.progressFor(key), isNotNull, reason: key);
      }
      expect(store.evictedProgressEntries, 0);
      await store.flush();
      final reopened = create(
        maxProgressEntries: 1,
        maxChapterMarkTitles: 1,
        maxBookSettingsTitles: 1,
      );
      await reopened.load();
      for (final key in keys) {
        expect(reopened.bookmarksFor(key), hasLength(1), reason: key);
      }
    });

    test('bookmarks added before load are merged with the saved ones and '
        'checked again', () async {
      const key = 'local:book';
      final seed = create();
      await seed.load();
      expect(
        seed.addBookmark(mark(key, 's1', location: 'page:1', fraction: 0.1)),
        isTrue,
      );
      expect(
        seed.addBookmark(mark(key, 's2', location: 'page:2', fraction: 0.2)),
        isTrue,
      );
      await seed.flush();

      final store = create();
      // Nothing is known yet: accepted, then checked against the file.
      expect(
        store.addBookmark(mark(key, 'new', location: 'page:3', fraction: 0.3)),
        isTrue,
      );
      expect(
        store.addBookmark(mark(key, 'dup', location: 'page:1', fraction: 0.05)),
        isTrue,
      );
      store.removeBookmark(key, 's2');
      await store.load();
      expect(store.bookmarksFor(key).map((bookmark) => bookmark.id), <String>[
        's1',
        'new',
      ]);
      await store.flush();
      final reopened = create();
      await reopened.load();
      expect(
        reopened.bookmarksFor(key).map((bookmark) => bookmark.id),
        <String>['s1', 'new'],
      );

      // A title already full in the file refuses a bookmark added before
      // load.
      await writeState(<String, Object?>{
        'version': 1,
        'bookmarks': <String, Object?>{
          'local:full': <Object?>[
            for (var index = 0; index < 500; index++)
              mark('local:full', 'f$index').toJson(),
          ],
        },
      });
      final early = create();
      expect(early.addBookmark(mark('local:full', 'late')), isTrue);
      await early.load();
      expect(early.bookmarksFor('local:full'), hasLength(500));
      expect(early.bookmarkAt('local:full', 'page:late'), isNull);
      await early.flush();
    });

    test('moveProgress moves bookmarks and title settings, never over '
        'existing ones', () async {
      final seed = create();
      await seed.load();
      seed.saveProgress(
        LibraryReadingProgress(
          key: 'local:old',
          location: 'page:12',
          fraction: 0.12,
        ),
      );
      final first = mark('local:old', 'b1', location: 'page:3', fraction: 0.1);
      final second = mark(
        'local:old',
        'b2',
        location: 'page:9',
        fraction: 0.3,
        label: 'Note',
      );
      seed.addBookmark(first);
      seed.addBookmark(second);
      seed.updateBookSettings(
        'local:old',
        const LibraryReaderBookSettings(turnStyle: LibraryPageTurnStyle.slide),
      );
      seed.addBookmark(mark('local:kept', 'k1'));
      seed.addBookmark(mark('local:taken', 't1'));
      seed.updateBookSettings(
        'local:taken',
        const LibraryReaderBookSettings(pdfMode: LibraryPdfMode.scroll),
      );
      // Bookmarks only, no reading position.
      seed.addBookmark(mark('local:marks-only', 'm1'));
      await seed.flush();
      final settingsDate = seed.bookSettingsFor('local:old')!.updatedAt;

      now = now.add(const Duration(hours: 1));
      final store = create();
      // Recorded before load, applied to the saved data.
      store.moveProgress('local:old', 'local:new');
      await store.load();
      expect(store.progressFor('local:new')!.location, 'page:12');
      expect(store.bookmarksFor('local:old'), isEmpty);
      final moved = store.bookmarksFor('local:new');
      expect(moved.map((bookmark) => bookmark.id), <String>['b1', 'b2']);
      expect(moved.map((bookmark) => bookmark.key).toSet(), <String>{
        'local:new',
      });
      expect(moved.last.label, 'Note');
      expect(moved.last.location, 'page:9');
      expect(moved.first.createdAt, first.createdAt);
      expect(store.bookSettingsFor('local:old'), isNull);
      expect(
        store.bookSettingsFor('local:new')!.turnStyle,
        LibraryPageTurnStyle.slide,
      );
      expect(store.bookSettingsFor('local:new')!.updatedAt, settingsDate);

      // The destination has its own: both stay as they are.
      store.moveProgress('local:kept', 'local:taken');
      expect(store.bookmarksFor('local:kept').single.id, 'k1');
      expect(store.bookmarksFor('local:taken').single.id, 't1');
      expect(store.bookSettingsFor('local:kept'), isNull);
      expect(
        store.bookSettingsFor('local:taken')!.pdfMode,
        LibraryPdfMode.scroll,
      );

      // A title with bookmarks but no position still moves.
      store.moveProgress('local:marks-only', 'local:renamed');
      expect(store.bookmarksFor('local:marks-only'), isEmpty);
      expect(store.bookmarksFor('local:renamed').single.key, 'local:renamed');

      await store.flush();
      final reopened = create();
      await reopened.load();
      expect(
        reopened.bookmarksFor('local:new').map((bookmark) => bookmark.id),
        <String>['b1', 'b2'],
      );
      expect(reopened.bookmarksFor('local:old'), isEmpty);
      expect(reopened.bookmarksFor('local:renamed'), hasLength(1));
      expect(reopened.bookSettingsFor('local:new'), isNotNull);
    });

    test('a large state with bookmarks is encoded off the UI isolate '
        'intact', () async {
      await writeState(<String, Object?>{
        'version': 1,
        'progress': <String, Object?>{
          for (var page = 0; page < 1500; page++)
            'online:s:m$page': LibraryReadingProgress(
              key: 'online:s:m$page',
              location: LibraryReadingProgress.pageLocation(page),
              fraction: 0.5,
              chapterId: 'chapter-$page',
              title: 'A fairly long manga title number $page',
              coverUrl: 'https://img.test/covers/$page/cover.jpg',
              updatedAt: DateTime.utc(2026).add(Duration(minutes: page)),
            ).toJson(),
        },
      });
      expect(await stateFile().length(), greaterThan(128 * 1024));
      final store = create(maxProgressEntries: 5000);
      await store.load();
      for (var index = 0; index < 40; index++) {
        store.addBookmark(
          mark('online:s:m$index', 'b$index', chapterId: 'chapter-$index'),
        );
      }
      store.updateBookSettings(
        'online:s:m1',
        const LibraryReaderBookSettings(mangaMode: LibraryMangaMode.vertical),
      );
      await store.flush();
      expect(store.lastSaveError, isNull);
      expect(store.lastWriteEncodedInBackground, isTrue);
      expect(await tmpFile().exists(), isFalse);

      final reopened = create(maxProgressEntries: 5000);
      await reopened.load();
      for (var index = 0; index < 40; index++) {
        expect(
          reopened.bookmarksFor('online:s:m$index'),
          store.bookmarksFor('online:s:m$index'),
        );
      }
      expect(
        reopened.bookSettingsFor('online:s:m1')!.mangaMode,
        LibraryMangaMode.vertical,
      );
    });
  });

  group('title settings', () {
    test(
      'are stamped, saved, cleared, and same values change nothing',
      () async {
        const key = 'online:s:m';
        final store = create();
        await store.load();
        var notifications = 0;
        store.addListener(() => notifications++);
        expect(store.bookSettingsFor(key), isNull);

        store.updateBookSettings(
          key,
          LibraryReaderBookSettings(
            turnStyle: LibraryPageTurnStyle.slide,
            pageDirection: LibraryPageDirection.rtl,
            updatedAt: DateTime.utc(2000),
          ),
        );
        expect(notifications, 1);
        final stored = store.bookSettingsFor(key)!;
        expect(stored.turnStyle, LibraryPageTurnStyle.slide);
        expect(stored.pageDirection, LibraryPageDirection.rtl);
        expect(stored.doublePage, isNull);
        expect(stored.updatedAt, now, reason: 'stamped by the store clock');

        // The same values: nothing changes.
        now = now.add(const Duration(minutes: 5));
        store.updateBookSettings(
          key,
          const LibraryReaderBookSettings(
            turnStyle: LibraryPageTurnStyle.slide,
            pageDirection: LibraryPageDirection.rtl,
          ),
        );
        expect(notifications, 1);
        expect(store.bookSettingsFor(key)!.updatedAt, isNot(now));

        store.updateBookSettings(
          key,
          stored.copyWith(doublePage: LibraryDoublePageMode.never),
        );
        expect(notifications, 2);
        expect(store.bookSettingsFor(key)!.updatedAt, now);
        // An empty key is never stored.
        store.updateBookSettings(
          '',
          const LibraryReaderBookSettings(pdfMode: LibraryPdfMode.scroll),
        );
        expect(store.bookSettingsFor(''), isNull);
        expect(notifications, 2);
        store.updateBookSettings(
          'local:b',
          const LibraryReaderBookSettings(textLayout: LibraryTextLayout.scroll),
        );
        expect(notifications, 3);

        await store.flush();
        final reopened = create();
        await reopened.load();
        final reloaded = reopened.bookSettingsFor(key)!;
        expect(reloaded, store.bookSettingsFor(key));
        expect(reloaded.doublePage, LibraryDoublePageMode.never);
        expect(reloaded.updatedAt, now);

        var reopenedNotifications = 0;
        reopened.addListener(() => reopenedNotifications++);
        reopened.clearBookSettings(key);
        expect(reopened.bookSettingsFor(key), isNull);
        expect(reopenedNotifications, 1);
        reopened.clearBookSettings(key);
        expect(reopenedNotifications, 1);
        // Settings that inherit everything remove the entry.
        reopened.updateBookSettings(
          'local:b',
          const LibraryReaderBookSettings(),
        );
        expect(reopened.bookSettingsFor('local:b'), isNull);
        expect(reopenedNotifications, 2);
        await reopened.flush();
        expect((await written())['bookSettings'], isEmpty);
        final third = create();
        await third.load();
        expect(third.bookSettingsFor(key), isNull);
        expect(third.bookSettingsFor('local:b'), isNull);
      },
    );

    test(
      'a removal requested before load applies to the saved settings',
      () async {
        final seed = create();
        await seed.load();
        seed.updateBookSettings(
          'local:a',
          const LibraryReaderBookSettings(pdfMode: LibraryPdfMode.scroll),
        );
        seed.updateBookSettings(
          'local:b',
          const LibraryReaderBookSettings(pdfMode: LibraryPdfMode.scroll),
        );
        await seed.flush();

        final store = create();
        store.clearBookSettings('local:a');
        store.updateBookSettings(
          'local:b',
          const LibraryReaderBookSettings(turnStyle: LibraryPageTurnStyle.none),
        );
        await store.load();
        expect(store.bookSettingsFor('local:a'), isNull);
        expect(
          store.bookSettingsFor('local:b'),
          const LibraryReaderBookSettings(turnStyle: LibraryPageTurnStyle.none),
        );
        await store.flush();
        final reopened = create();
        await reopened.load();
        expect(reopened.bookSettingsFor('local:a'), isNull);
        expect(
          reopened.bookSettingsFor('local:b')!.turnStyle,
          LibraryPageTurnStyle.none,
        );
      },
    );

    test('over 1000 titles, the online ones changed the longest ago are '
        'dropped, never local books', () async {
      final defaults = LibraryReadingStore(directory: tmp);
      expect(defaults.maxBookSettingsTitles, 1000);
      defaults.dispose();
      final store = create();
      expect(store.maxBookSettingsTitles, 1000);
      await store.load();
      const settings = LibraryReaderBookSettings(
        turnStyle: LibraryPageTurnStyle.slide,
      );
      void later() => now = now.add(const Duration(seconds: 1));
      // The oldest entries are local books.
      for (var index = 0; index < 5; index++) {
        later();
        store.updateBookSettings('local:b$index', settings);
      }
      for (var index = 0; index < 995; index++) {
        later();
        store.updateBookSettings('online:s:m$index', settings);
      }
      expect(store.evictedBookSettingsTitles, 0);
      // Changed again: no longer the oldest online entry.
      later();
      store.updateBookSettings(
        'online:s:m0',
        settings.copyWith(pdfMode: LibraryPdfMode.scroll),
      );
      later();
      store.updateBookSettings('online:s:new', settings);
      expect(store.evictedBookSettingsTitles, 1);
      expect(store.bookSettingsFor('online:s:m1'), isNull);
      expect(store.bookSettingsFor('online:s:m0'), isNotNull);
      expect(store.bookSettingsFor('online:s:m2'), isNotNull);
      expect(store.bookSettingsFor('online:s:new'), isNotNull);
      for (var index = 0; index < 5; index++) {
        expect(store.bookSettingsFor('local:b$index'), isNotNull);
      }
      await store.flush();
      final json = await written();
      expect((json['bookSettings'] as Map).length, 1000);
      expect((json['evictions'] as Map)['bookSettingsTitles'], 1);
      final reopened = create();
      await reopened.load();
      expect(reopened.evictedBookSettingsTitles, 1);
      expect(reopened.bookSettingsFor('local:b0'), isNotNull);

      // When only local books (and the title being changed) remain, the
      // store grows past the limit instead.
      final small = LibraryReadingStore(
        directory: await Directory(p.join(tmp.path, 'small')).create(),
        clock: () => now,
        maxBookSettingsTitles: 2,
      );
      await small.load();
      for (final key in <String>['local:a', 'local:b', 'local:c']) {
        later();
        small.updateBookSettings(key, settings);
      }
      later();
      small.updateBookSettings('online:s:x', settings);
      for (final key in <String>[
        'local:a',
        'local:b',
        'local:c',
        'online:s:x',
      ]) {
        expect(small.bookSettingsFor(key), isNotNull, reason: key);
      }
      expect(small.evictedBookSettingsTitles, 0);
      await small.flush();
      small.dispose();
    });
  });

  group('models', () {
    test('LibraryReaderBookSettings reads tolerantly, clears fields and '
        'compares values', () {
      expect(LibraryReaderBookSettings.fromJson(null), isNull);
      expect(LibraryReaderBookSettings.fromJson('slide'), isNull);
      expect(
        LibraryReaderBookSettings.fromJson(<String, Object?>{})!.isEmpty,
        isTrue,
      );
      expect(const LibraryReaderBookSettings().isEmpty, isTrue);
      expect(
        const LibraryReaderBookSettings(firstPageAlone: false).isEmpty,
        isFalse,
      );

      final settings = LibraryReaderBookSettings(
        turnStyle: LibraryPageTurnStyle.none,
        doublePage: LibraryDoublePageMode.always,
        firstPageAlone: false,
        pageDirection: LibraryPageDirection.rtl,
        mangaMode: LibraryMangaMode.paged,
        pdfMode: LibraryPdfMode.scroll,
        textLayout: LibraryTextLayout.scroll,
        updatedAt: DateTime.utc(2026, 10, 1),
      );
      final roundTrip = LibraryReaderBookSettings.fromJson(
        jsonDecode(jsonEncode(settings.toJson())),
      )!;
      expect(roundTrip, settings);
      expect(roundTrip.updatedAt, DateTime.utc(2026, 10, 1));
      expect(
        const LibraryReaderBookSettings(
          mangaMode: LibraryMangaMode.auto,
        ).toJson(),
        <String, Object?>{'mangaMode': 'auto', 'updatedAt': 0},
      );

      final cleared = settings.copyWith(
        clear: <LibraryReaderBookField>{
          LibraryReaderBookField.turnStyle,
          LibraryReaderBookField.pageDirection,
        },
      );
      expect(cleared.turnStyle, isNull);
      expect(cleared.pageDirection, isNull);
      expect(cleared.doublePage, LibraryDoublePageMode.always);
      expect(cleared.firstPageAlone, isFalse);
      expect(cleared.mangaMode, LibraryMangaMode.paged);
      expect(cleared.pdfMode, LibraryPdfMode.scroll);
      expect(cleared.textLayout, LibraryTextLayout.scroll);
      expect(cleared.updatedAt, settings.updatedAt);
      // Clearing wins over a value given at the same time.
      expect(
        settings
            .copyWith(
              textLayout: LibraryTextLayout.pages,
              clear: <LibraryReaderBookField>{
                LibraryReaderBookField.textLayout,
              },
            )
            .textLayout,
        isNull,
      );
      final everything = settings.copyWith(
        clear: LibraryReaderBookField.values.toSet(),
      );
      expect(everything.isEmpty, isTrue);
      expect(
        settings.copyWith(pdfMode: LibraryPdfMode.pages).pdfMode,
        LibraryPdfMode.pages,
      );

      // Values compare, the date does not.
      final later = settings.copyWith(updatedAt: DateTime.utc(2027));
      expect(later, settings);
      expect(later.hashCode, settings.hashCode);
      expect(later.updatedAt, isNot(settings.updatedAt));
      expect(settings.copyWith(firstPageAlone: true) == settings, isFalse);
      expect(
        const LibraryReaderBookSettings().updatedAt,
        DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
      );
    });

    test('LibraryBookmark round-trips through JSON and rejects invalid '
        'entries', () {
      final bookmark = LibraryBookmark(
        id: 'id',
        key: 'online:s:m',
        location: 'page:4',
        fraction: 0.4,
        chapterId: 'c1',
        chapterTitle: 'Un',
        pageIndex: 4,
        label: 'Ici',
        createdAt: DateTime.utc(2026, 10, 12, 8),
      );
      final roundTrip = LibraryBookmark.fromJson(
        jsonDecode(jsonEncode(bookmark.toJson())),
      );
      expect(roundTrip, bookmark);
      expect(roundTrip.hashCode, bookmark.hashCode);

      // The same moment in another time zone is the same bookmark.
      final local = LibraryBookmark(
        id: 'id',
        key: 'online:s:m',
        location: 'page:4',
        fraction: 0.4,
        chapterId: 'c1',
        chapterTitle: 'Un',
        pageIndex: 4,
        label: 'Ici',
        createdAt: DateTime.utc(2026, 10, 12, 8).toLocal(),
      );
      expect(local, bookmark);
      expect(local.hashCode, bookmark.hashCode);
      expect(
        LibraryBookmark.fromJson(<String, Object?>{
          ...bookmark.toJson(),
          'label': 'Là',
        }),
        isNot(bookmark),
      );

      final valid = bookmark.toJson();
      for (final field in <String>['id', 'key', 'location', 'fraction']) {
        expect(
          LibraryBookmark.fromJson(<String, Object?>{...valid}..remove(field)),
          isNull,
          reason: 'without $field',
        );
      }
      expect(
        LibraryBookmark.fromJson(<String, Object?>{...valid, 'id': ''}),
        isNull,
      );
      expect(
        LibraryBookmark.fromJson(<String, Object?>{...valid, 'fraction': '1'}),
        isNull,
      );
      expect(LibraryBookmark.fromJson('page:4'), isNull);
      expect(LibraryBookmark.fromJson(null), isNull);
      // A missing date reads as the epoch, the bookmark is kept.
      expect(
        LibraryBookmark.fromJson(
          <String, Object?>{...valid}..remove('createdAt'),
        )!.createdAt,
        DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
      );
      // Never a NaN or an out-of-range fraction in the file.
      LibraryBookmark at(double fraction) => LibraryBookmark(
        id: 'n',
        key: 'local:a',
        location: 'page:1',
        fraction: fraction,
        createdAt: DateTime.utc(2026),
      );
      expect(at(double.infinity).toJson()['fraction'], 1.0);
      expect(at(double.negativeInfinity).toJson()['fraction'], 0.0);
      expect(at(double.nan).toJson()['fraction'], 0.0);
      expect(at(-0.5).toJson()['fraction'], 0.0);
    });
  });
}
