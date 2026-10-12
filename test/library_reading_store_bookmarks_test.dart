// Build 447 additions to LibraryReadingStore (docs/library-books-3d-plan.md
// § 3.7 and § 3.9): bookmarks, per-title navigation settings and the reader
// settings added then. They are kept in reading-state-extra.json (version
// 1), next to reading-state.json, which keeps exactly the Build 446 layout:
// Build 446 rewrites reading-state.json with only the keys it knows and
// never opens the other file, so going back to it (SideStore keeps the
// data) and then to 447 loses none of them (downgrade safety, review of the
// books chantier; phase 1 kept them in reading-state.json).
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
  File extraFile() => File(p.join(tmp.path, LibraryReadingStore.extraFileName));
  File extraTmpFile() => File('${extraFile().path}.tmp');
  File extraCorruptFile() =>
      File('${extraFile().path}${LibraryReadingStore.corruptSuffix}');

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

  Future<Map<String, Object?>> writtenExtra() async =>
      jsonDecode(await extraFile().readAsString()) as Map<String, Object?>;

  Future<void> writeState(Map<String, Object?> state) =>
      stateFile().writeAsString(jsonEncode(state));

  Future<void> writeExtra(Map<String, Object?> state) =>
      extraFile().writeAsString(jsonEncode(state));

  /// What Build 446 (8ceeb055) does to reading-state.json when it saves:
  /// it reads the keys and entry fields it knows and writes only them back
  /// ([build446] may change its data first). It never opens
  /// reading-state-extra.json.
  Future<void> rewriteAsBuild446({
    void Function(Map<String, Object?> state)? build446,
  }) async {
    final json = await written();
    Map<String, Object?> only(Object? value, Set<String> keys) =>
        <String, Object?>{
          for (final entry in (value as Map).entries)
            if (keys.contains(entry.key)) entry.key as String: entry.value,
        };
    final state = <String, Object?>{
      'version': 1,
      'progress': <String, Object?>{
        for (final entry in (json['progress'] as Map).entries)
          entry.key as String: only(entry.value, _build446ProgressFields),
      },
      'chapterMarks': <String, Object?>{
        for (final title in (json['chapterMarks'] as Map).entries)
          title.key as String: <String, Object?>{
            for (final mark in (title.value as Map).entries)
              mark.key as String: only(mark.value, _build446MarkFields),
          },
      },
      'favorites': <String, Object?>{
        for (final entry in (json['favorites'] as Map).entries)
          entry.key as String: only(entry.value, _build446FavoriteFields),
      },
      'settings': only(json['settings'], _build446Settings),
      if (json['evictions'] case final Map evictions)
        'evictions': only(evictions, const <String>{
          'progress',
          'chapterMarkTitles',
        }),
    };
    build446?.call(state);
    await writeState(state);
  }

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

      // A title whose last bookmark is removed leaves the file. Bookmarks
      // are in reading-state-extra.json, never in reading-state.json
      // (downgrade safety, see the top of this file).
      reopened.removeBookmark('online:s:m', 'o');
      expect(reopened.bookmarksFor('online:s:m'), isEmpty);
      await reopened.flush();
      final bookmarks = (await writtenExtra())['bookmarks'] as Map;
      expect(bookmarks.keys, <String>[key]);
      expect((await written()).containsKey('bookmarks'), isFalse);
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
        final savedExtra = await extraFile().readAsString();
        final savedExtraAt = await extraFile().lastModified();
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
        expect(await extraFile().readAsString(), savedExtra);
        expect(await extraFile().lastModified(), savedExtraAt);
        expect(await extraTmpFile().exists(), isFalse);

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
      final savedExtra = await extraFile().readAsString();
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
      expect(await extraFile().readAsString(), savedExtra);

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

    // Replaces the phase-1 contract (bookmarks and title settings in
    // reading-state.json, next to the other keys): Build 446 rewrites that
    // file with only its keys, which erased them for good after going back
    // to 446 (downgrade safety). They now live in reading-state-extra.json
    // and reading-state.json keeps exactly the Build 446 layout.
    test('bookmarks, title settings and the Build 447 reader settings are '
        'written to the extra file under version 1 with the documented keys, '
        'the main file keeps the Build 446 layout, both atomically', () async {
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
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:epub',
          location: 'epubcfi(/6/4!/4/2/1:0)',
          fraction: 0.1,
        ),
      );
      store.updateSettings(
        store.settings.copyWith(
          fontSize: 22,
          pdfMode: LibraryPdfMode.scroll,
          bookmarkRibbon: false,
        ),
      );
      await store.flush();
      expect(await tmpFile().exists(), isFalse);
      expect(await extraTmpFile().exists(), isFalse);

      final main = await written();
      expect(main['version'], 1);
      expect(
        main.keys.toSet(),
        _build446Keys.difference(<String>{'evictions'}),
      );
      expect((main['settings'] as Map).keys.toSet(), _build446Settings);
      expect((main['settings'] as Map)['fontSize'], 22);
      expect((main['progress'] as Map).keys, <String>['local:epub']);

      final json = await writtenExtra();
      expect(json['version'], 1);
      expect(json.keys.toSet(), <String>{
        'version',
        'settings',
        'bookmarks',
        'bookSettings',
      });
      expect(json['settings'], <String, Object?>{
        'turnStyle': 'curl',
        'doublePage': 'auto',
        'firstPageAlone': true,
        'pdfMode': 'scroll',
        'textLayout': 'pages',
        'toolbarMode': 'auto',
        'bookmarkRibbon': false,
      });
      expect((json['settings'] as Map).keys.toSet(), _build447Settings);
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

    // The phase-1 version of this test only checked the known data: the
    // unknown keys themselves were dropped at the first write (review of
    // the books chantier, probe C). Both files now carry what a later build
    // added, unchanged and with the entry it belongs to, so that going back
    // to this build loses nothing of that build either.
    test('keys and entry fields of a later build survive the next writes in '
        'both files and leave or move with their entry', () async {
      LibraryReadingProgress at(String key, int page) => LibraryReadingProgress(
        key: key,
        location: 'page:$page',
        fraction: page / 10,
        updatedAt: DateTime.utc(2026),
      );
      final favorite = LibraryFavorite(
        key: 'online:s:m',
        sourceId: 's',
        mangaId: 'm',
        title: 'Manga',
      );
      final readMark = LibraryChapterMark(read: true).toJson();
      await writeState(<String, Object?>{
        'version': 1,
        'progress': <String, Object?>{
          'local:a': <String, Object?>{
            ...at('local:a', 4).toJson(),
            'readingSeconds': 120,
          },
          'local:gone': <String, Object?>{
            ...at('local:gone', 2).toJson(),
            'readingSeconds': 5,
          },
          'local:old': <String, Object?>{
            ...at('local:old', 6).toJson(),
            'readingSeconds': 9,
          },
        },
        'chapterMarks': <String, Object?>{
          'online:s:m': <String, Object?>{
            'c1': <String, Object?>{...readMark, 'readAt': 77},
          },
        },
        'favorites': <String, Object?>{
          'online:s:m': <String, Object?>{...favorite.toJson(), 'shelf': 'x'},
        },
        'settings': <String, Object?>{'fontSize': 21, 'brightness': 0.4},
        'evictions': <String, Object?>{'progress': 2, 'somethingElse': 4},
        // Keys of a later build: unknown here.
        'shelves': <Object?>[
          <String, Object?>{
            'name': 'x',
            'keys': <String>['local:a'],
          },
        ],
        'futureFeature': <String, Object?>{'enabled': true, 'level': 3},
      });
      await writeExtra(<String, Object?>{
        'version': 1,
        'settings': <String, Object?>{'pdfMode': 'scroll', 'curlShadow': 0.5},
        'bookmarks': <String, Object?>{
          'local:a': <Object?>[
            <String, Object?>{
              ...mark('local:a', 'm1').toJson(),
              'color': 'red',
            },
            <String, Object?>{
              ...mark(
                'local:a',
                'm2',
                location: 'page:8',
                fraction: 0.8,
              ).toJson(),
              'color': 'blue',
            },
          ],
          'local:old': <Object?>[
            <String, Object?>{
              ...mark('local:old', 'o1').toJson(),
              'color': 'green',
            },
          ],
        },
        'bookSettings': <String, Object?>{
          'local:a': <String, Object?>{
            'textLayout': 'scroll',
            'updatedAt': 5,
            'zoom': 2,
          },
          'local:old': <String, Object?>{
            'turnStyle': 'none',
            'updatedAt': 6,
            'zoom': 3,
          },
        },
        'evictions': <String, Object?>{'bookSettingsTitles': 1, 'other': 9},
        'annotations': <String, Object?>{
          'local:a': <String>['note'],
        },
      });
      final store = create();
      await store.load();
      expect(store.loadFailed, isFalse);
      expect(await corruptFile().exists(), isFalse);
      expect(await extraCorruptFile().exists(), isFalse);
      expect(store.progressFor('local:a')!.location, 'page:4');
      expect(
        store.bookmarksFor('local:a').map((bookmark) => bookmark.id),
        <String>['m1', 'm2'],
      );
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
      expect(store.evictedBookSettingsTitles, 1);

      // Changes of every kind: a changed entry keeps its fields, a removed
      // one takes them away, a moved one takes them along.
      store.saveProgress(at('local:b', 1));
      store.saveProgress(at('local:a', 5));
      store.removeProgress('local:gone');
      store.removeBookmark('local:a', 'm2');
      store.updateBookSettings(
        'local:a',
        const LibraryReaderBookSettings(
          textLayout: LibraryTextLayout.scroll,
          turnStyle: LibraryPageTurnStyle.slide,
        ),
      );
      store.moveProgress('local:old', 'local:new');
      store.updateSettings(
        store.settings.copyWith(
          fontSize: 22,
          textLayout: LibraryTextLayout.scroll,
        ),
      );
      await store.flush();
      expect(store.lastSaveError, isNull);

      final main = await written();
      expect(main['version'], 1);
      expect(main['shelves'], <Object?>[
        <String, Object?>{
          'name': 'x',
          'keys': <Object?>['local:a'],
        },
      ]);
      expect(main['futureFeature'], <String, Object?>{
        'enabled': true,
        'level': 3,
      });
      expect(main['evictions'], <String, Object?>{
        'progress': 2,
        'chapterMarkTitles': 0,
        'somethingElse': 4,
      });
      final mainSettings = main['settings'] as Map;
      expect(mainSettings['brightness'], 0.4);
      expect(mainSettings['fontSize'], 22);
      expect(mainSettings.keys.toSet(), <String>{
        ..._build446Settings,
        'brightness',
      });
      final progress = main['progress'] as Map;
      expect(progress.keys.toSet(), <String>{
        'local:a',
        'local:b',
        'local:new',
      });
      expect((progress['local:a'] as Map)['location'], 'page:5');
      expect((progress['local:a'] as Map)['readingSeconds'], 120);
      expect((progress['local:new'] as Map)['key'], 'local:new');
      expect((progress['local:new'] as Map)['readingSeconds'], 9);
      expect(
        (progress['local:b'] as Map).containsKey('readingSeconds'),
        isFalse,
      );
      expect(
        ((main['chapterMarks'] as Map)['online:s:m'] as Map)['c1'],
        <String, Object?>{...readMark, 'readAt': 77},
      );
      expect(((main['favorites'] as Map)['online:s:m'] as Map)['shelf'], 'x');

      final extra = await writtenExtra();
      expect(extra['version'], 1);
      expect(extra['annotations'], <String, Object?>{
        'local:a': <Object?>['note'],
      });
      expect(extra['evictions'], <String, Object?>{
        'bookSettingsTitles': 1,
        'other': 9,
      });
      final extraSettings = extra['settings'] as Map;
      expect(extraSettings['curlShadow'], 0.5);
      expect(extraSettings['textLayout'], 'scroll');
      expect(extraSettings.keys.toSet(), <String>{
        ..._build447Settings,
        'curlShadow',
      });
      final bookmarks = extra['bookmarks'] as Map;
      expect(bookmarks.keys.toSet(), <String>{'local:a', 'local:new'});
      expect(bookmarks['local:a'], <Object?>[
        <String, Object?>{...mark('local:a', 'm1').toJson(), 'color': 'red'},
      ]);
      expect(bookmarks['local:new'], <Object?>[
        <String, Object?>{
          ...mark('local:new', 'o1').toJson(),
          'color': 'green',
        },
      ]);
      final bookSettings = extra['bookSettings'] as Map;
      expect(bookSettings.keys.toSet(), <String>{'local:a', 'local:new'});
      expect(bookSettings['local:a'], <String, Object?>{
        'turnStyle': 'slide',
        'textLayout': 'scroll',
        'updatedAt': now.millisecondsSinceEpoch,
        'zoom': 2,
      });
      expect(bookSettings['local:new'], <String, Object?>{
        'turnStyle': 'none',
        'updatedAt': 6,
        'zoom': 3,
      });

      // Read back by this version, and written back unchanged again.
      final reopened = create();
      await reopened.load();
      expect(reopened.loadFailed, isFalse);
      expect(reopened.progressFor('local:a')!.location, 'page:5');
      expect(reopened.progressFor('local:gone'), isNull);
      expect(reopened.bookmarksFor('local:a'), <LibraryBookmark>[
        mark('local:a', 'm1'),
      ]);
      expect(
        reopened.bookSettingsFor('local:new')!.turnStyle,
        LibraryPageTurnStyle.none,
      );
      expect(reopened.settings.fontSize, 22);
      expect(reopened.settings.pdfMode, LibraryPdfMode.scroll);
      reopened.markChapter('online:s:m', 'c2', read: true);
      await reopened.flush();
      final again = await written();
      expect(again['shelves'], main['shelves']);
      expect(again['futureFeature'], main['futureFeature']);
      expect(again['settings'], main['settings']);
      expect(again['progress'], main['progress']);
      expect(
        ((again['chapterMarks'] as Map)['online:s:m'] as Map)['c1'],
        <String, Object?>{...readMark, 'readAt': 77},
      );
      expect(await writtenExtra(), extra);
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
      });
      // Bookmarks and title settings are read from the extra file only.
      await writeExtra(<String, Object?>{
        'version': 1,
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
      expect(await extraCorruptFile().exists(), isFalse);
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
      });
      await writeExtra(<String, Object?>{
        'version': 1,
        'bookmarks': <Object?>[valid.toJson()],
        'bookSettings': 'scroll',
        'settings': 'pages',
      });
      final other = create();
      await other.load();
      expect(other.loadFailed, isFalse);
      expect(await corruptFile().exists(), isFalse);
      expect(await extraCorruptFile().exists(), isFalse);
      expect(other.progressFor('local:z'), isNotNull);
      expect(other.bookmarksFor('local:a'), isEmpty);
      expect(other.bookSettingsFor('local:a'), isNull);
      expect(other.settings, const LibraryReaderSettings());
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
      await writeExtra(<String, Object?>{
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
      expect(await extraTmpFile().exists(), isFalse);

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
        expect((await writtenExtra())['bookSettings'], isEmpty);
        expect((await written()).containsKey('bookSettings'), isFalse);
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
        // Changed contract (review of the books chantier): an update made
        // before load replaces only the fields it set, so the saved
        // pdfMode stays; it used to replace the title's saved settings as a
        // whole ({turnStyle: none} only). The explicit removal above still
        // removes everything.
        expect(
          store.bookSettingsFor('local:b'),
          const LibraryReaderBookSettings(
            pdfMode: LibraryPdfMode.scroll,
            turnStyle: LibraryPageTurnStyle.none,
          ),
        );
        await store.flush();
        final reopened = create();
        await reopened.load();
        expect(reopened.bookSettingsFor('local:a'), isNull);
        expect(
          reopened.bookSettingsFor('local:b')!.turnStyle,
          LibraryPageTurnStyle.none,
        );
        expect(
          reopened.bookSettingsFor('local:b')!.pdfMode,
          LibraryPdfMode.scroll,
        );
      },
    );

    test('settings changed before load, or while the files cannot be read, '
        'replace only the values they changed', () async {
      final seed = create();
      await seed.load();
      seed.updateBookSettings(
        'local:a',
        const LibraryReaderBookSettings(
          pdfMode: LibraryPdfMode.scroll,
          pageDirection: LibraryPageDirection.rtl,
          turnStyle: LibraryPageTurnStyle.slide,
        ),
      );
      seed.updateBookSettings(
        'local:c',
        const LibraryReaderBookSettings(
          doublePage: LibraryDoublePageMode.never,
        ),
      );
      seed.updateSettings(
        seed.settings.copyWith(
          theme: LibraryReaderTheme.dark,
          fontSize: 20,
          turnStyle: LibraryPageTurnStyle.none,
          pdfMode: LibraryPdfMode.scroll,
        ),
      );
      await seed.flush();
      final savedMain = await stateFile().readAsString();
      final savedExtra = await extraFile().readAsString();

      now = now.add(const Duration(hours: 1));
      final store = create();
      // A reader opened before load knows nothing saved: what it changes
      // is recorded field by field.
      store.updateBookSettings(
        'local:a',
        const LibraryReaderBookSettings(turnStyle: LibraryPageTurnStyle.none),
      );
      store.updateBookSettings(
        'local:a',
        const LibraryReaderBookSettings(
          turnStyle: LibraryPageTurnStyle.none,
          doublePage: LibraryDoublePageMode.always,
        ),
      );
      // Back to the general turn style: the field is cleared, the saved
      // one too.
      store.updateBookSettings(
        'local:a',
        const LibraryReaderBookSettings(
          doublePage: LibraryDoublePageMode.always,
        ),
      );
      store.updateBookSettings(
        'local:c',
        const LibraryReaderBookSettings(firstPageAlone: false),
      );
      store.updateSettings(
        store.settings.copyWith(
          fontSize: 24,
          doublePage: LibraryDoublePageMode.never,
        ),
      );
      // Nothing is written before the files are read.
      await pastSaveDelay();
      expect(await stateFile().readAsString(), savedMain);
      expect(await extraFile().readAsString(), savedExtra);

      await store.load();
      expect(
        store.bookSettingsFor('local:a'),
        const LibraryReaderBookSettings(
          pdfMode: LibraryPdfMode.scroll,
          pageDirection: LibraryPageDirection.rtl,
          doublePage: LibraryDoublePageMode.always,
        ),
      );
      expect(store.bookSettingsFor('local:a')!.updatedAt, now);
      expect(
        store.bookSettingsFor('local:c'),
        const LibraryReaderBookSettings(
          doublePage: LibraryDoublePageMode.never,
          firstPageAlone: false,
        ),
      );
      final settings = store.settings;
      expect(settings.theme, LibraryReaderTheme.dark);
      expect(settings.turnStyle, LibraryPageTurnStyle.none);
      expect(settings.pdfMode, LibraryPdfMode.scroll);
      expect(settings.fontSize, 24);
      expect(settings.doublePage, LibraryDoublePageMode.never);
      await store.flush();
      final reopened = create();
      await reopened.load();
      expect(reopened.settings, settings);
      expect(
        reopened.bookSettingsFor('local:a'),
        store.bookSettingsFor('local:a'),
      );
      expect(
        reopened.bookSettingsFor('local:c'),
        store.bookSettingsFor('local:c'),
      );

      // The same while the extra file cannot be read: nothing is replaced,
      // and the change is merged once it can be.
      final saved = await extraFile().readAsString();
      final mainBefore = await stateFile().readAsString();
      await extraFile().delete();
      final blocked = await Directory(extraFile().path).create();
      final unreadable = create();
      await unreadable.load();
      expect(unreadable.loadFailed, isTrue);
      unreadable.updateBookSettings(
        'local:c',
        const LibraryReaderBookSettings(mangaMode: LibraryMangaMode.vertical),
      );
      unreadable.updateSettings(
        unreadable.settings.copyWith(bookmarkRibbon: false),
      );
      await unreadable.flush();
      expect(unreadable.lastSaveError, isNotNull);
      expect(unreadable.hasPendingChanges, isTrue);
      expect(await blocked.exists(), isTrue);
      expect(await stateFile().readAsString(), mainBefore);
      await blocked.delete();
      await extraFile().writeAsString(saved);
      await unreadable.flush();
      expect(unreadable.loadFailed, isFalse);
      expect(unreadable.lastSaveError, isNull);
      expect(
        unreadable.bookSettingsFor('local:c'),
        const LibraryReaderBookSettings(
          doublePage: LibraryDoublePageMode.never,
          firstPageAlone: false,
          mangaMode: LibraryMangaMode.vertical,
        ),
      );
      expect(unreadable.settings, settings.copyWith(bookmarkRibbon: false));
      unreadable.dispose();
    });

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
      // In the extra file (downgrade safety, see the top of this file);
      // reading-state.json keeps the Build 446 evictions only.
      final json = await writtenExtra();
      expect((json['bookSettings'] as Map).length, 1000);
      expect(json['evictions'], <String, Object?>{'bookSettingsTitles': 1});
      final main = await written();
      expect(main.containsKey('bookSettings'), isFalse);
      expect(main.containsKey('evictions'), isFalse);
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

  group('two files', () {
    LibraryReadingProgress at(String key, int page) => LibraryReadingProgress(
      key: key,
      location: 'page:$page',
      fraction: page / 10,
    );

    // Downgrade safety (review of the books chantier): the Build 446 IPA
    // installed over 447 (SideStore keeps the data) rewrites
    // reading-state.json with only its keys and never opens
    // reading-state-extra.json. Back on 447 nothing of 447 is lost, and
    // what 446 saved meanwhile is there too.
    test('a Build 446 rewrite of reading-state.json loses no bookmark, title '
        'setting or Build 447 reader setting', () async {
      final store = create();
      await store.load();
      store.saveProgress(at('local:a', 4));
      store.markChapter('online:s:m', 'c1', read: true);
      expect(
        store.addBookmark(
          mark(
            'local:a',
            'b1',
            location: 'page:4',
            fraction: 0.4,
            label: 'Ici',
          ),
        ),
        isTrue,
      );
      expect(
        store.addBookmark(
          mark('online:s:m', 'b2', chapterId: 'c1', pageIndex: 2),
        ),
        isTrue,
      );
      store.updateBookSettings(
        'local:a',
        const LibraryReaderBookSettings(
          pageDirection: LibraryPageDirection.rtl,
          turnStyle: LibraryPageTurnStyle.slide,
        ),
      );
      store.updateSettings(
        store.settings.copyWith(
          fontSize: 22,
          turnStyle: LibraryPageTurnStyle.none,
          doublePage: LibraryDoublePageMode.never,
          firstPageAlone: false,
          pdfMode: LibraryPdfMode.scroll,
          textLayout: LibraryTextLayout.scroll,
          toolbarMode: LibraryReaderToolbarMode.always,
          bookmarkRibbon: false,
        ),
      );
      await store.flush();
      final settings = store.settings;
      final bookmarks = store.bookmarksFor('local:a');
      final onlineBookmarks = store.bookmarksFor('online:s:m');
      final bookSettings = store.bookSettingsFor('local:a');
      final extraBefore = await extraFile().readAsString();

      // Build 446 reads further, changes a setting it knows and saves.
      await rewriteAsBuild446(
        build446: (state) {
          (state['progress'] as Map)['local:446'] = at('local:446', 9).toJson();
          (state['settings'] as Map)['fontSize'] = 24.0;
        },
      );
      expect(
        (await written()).keys.toSet(),
        _build446Keys.difference(<String>{'evictions'}),
      );
      expect(await extraFile().readAsString(), extraBefore);

      // Back on 447.
      final reopened = create();
      await reopened.load();
      expect(reopened.loadFailed, isFalse);
      expect(reopened.bookmarksFor('local:a'), bookmarks);
      expect(reopened.bookmarksFor('online:s:m'), onlineBookmarks);
      expect(reopened.bookSettingsFor('local:a'), bookSettings);
      expect(reopened.settings, settings.copyWith(fontSize: 24));
      expect(reopened.progressFor('local:446')!.location, 'page:9');
      expect(reopened.progressFor('local:a')!.location, 'page:4');
      expect(reopened.chapterMark('online:s:m', 'c1')!.read, isTrue);

      // Again after the next 447 write and another 446 rewrite.
      reopened.saveProgress(at('local:a', 5));
      await reopened.flush();
      await rewriteAsBuild446();
      final third = create();
      await third.load();
      expect(third.bookmarksFor('local:a'), bookmarks);
      expect(third.bookSettingsFor('local:a'), bookSettings);
      expect(third.settings, settings.copyWith(fontSize: 24));
      expect(third.progressFor('local:a')!.location, 'page:5');
      expect(third.progressFor('local:446'), isNotNull);
    });

    test('a corrupt file is kept aside on its own: the other file\'s part is '
        'loaded and both are written again', () async {
      final seed = create();
      await seed.load();
      seed.saveProgress(at('local:a', 4));
      expect(seed.addBookmark(mark('local:a', 'b1')), isTrue);
      await seed.flush();
      const garbage = '{"bookmarks": {"local:a": [';
      await extraFile().writeAsString(garbage);

      final store = create();
      await store.load();
      expect(store.loadFailed, isFalse);
      expect(store.progressFor('local:a')!.location, 'page:4');
      expect(store.bookmarksFor('local:a'), isEmpty);
      expect(await extraCorruptFile().readAsString(), garbage);
      expect(await extraFile().exists(), isFalse);
      expect(await corruptFile().exists(), isFalse);
      expect(
        store.addBookmark(mark('local:a', 'b2', location: 'page:7')),
        isTrue,
      );
      await store.flush();
      final reopened = create();
      await reopened.load();
      expect(reopened.progressFor('local:a')!.location, 'page:4');
      expect(reopened.bookmarksFor('local:a').single.id, 'b2');
      expect(await extraCorruptFile().readAsString(), garbage);

      // A corrupt main file: the extra file's part is still loaded.
      await stateFile().writeAsString('[1, 2');
      final third = create();
      await third.load();
      expect(third.loadFailed, isFalse);
      expect(third.progressFor('local:a'), isNull);
      expect(third.bookmarksFor('local:a').single.id, 'b2');
      expect(await corruptFile().readAsString(), '[1, 2');
    });

    test('while either file cannot be read, neither is replaced, and the '
        'changes are merged once it can be', () async {
      final seed = create();
      await seed.load();
      seed.saveProgress(at('local:a', 4));
      expect(seed.addBookmark(mark('local:a', 'b1')), isTrue);
      await seed.flush();
      final main = await stateFile().readAsString();
      final extra = await extraFile().readAsString();

      for (final file in <File>[stateFile(), extraFile()]) {
        final content = await file.readAsString();
        await file.delete();
        // A directory at the path cannot be read as a file: an I/O failure.
        final blocked = await Directory(file.path).create();
        final store = create();
        await store.load();
        expect(store.loadFailed, isTrue, reason: file.path);
        store.saveProgress(at('local:b', 1));
        expect(store.addBookmark(mark('local:b', 'x')), isTrue);
        await store.flush();
        expect(store.lastSaveError, isA<FileSystemException>());
        expect((store.lastSaveError! as FileSystemException).path, file.path);
        expect(store.hasPendingChanges, isTrue);
        if (file.path != stateFile().path) {
          expect(await stateFile().readAsString(), main);
        }
        if (file.path != extraFile().path) {
          expect(await extraFile().readAsString(), extra);
        }
        expect(await tmpFile().exists(), isFalse);
        expect(await extraTmpFile().exists(), isFalse);
        expect(
          await FileSystemEntity.type(
            '${file.path}${LibraryReadingStore.corruptSuffix}',
          ),
          FileSystemEntityType.notFound,
        );

        await blocked.delete();
        await file.writeAsString(content);
        await store.flush();
        expect(store.loadFailed, isFalse, reason: file.path);
        expect(store.lastSaveError, isNull);
        expect(store.progressFor('local:a'), isNotNull);
        expect(store.bookmarksFor('local:a'), hasLength(1));
        expect(store.bookmarksFor('local:b'), hasLength(1));
        final reopened = create();
        await reopened.load();
        expect(reopened.progressFor('local:b'), isNotNull);
        expect(reopened.bookmarksFor('local:a'), hasLength(1));
        expect(reopened.bookmarksFor('local:b'), hasLength(1));
        store.dispose();
        reopened.dispose();
        // The seed again for the other file.
        await stateFile().writeAsString(main);
        await extraFile().writeAsString(extra);
      }
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

/// What Build 446 (8ceeb055) reads and writes in reading-state.json.
const Set<String> _build446Keys = <String>{
  'version',
  'progress',
  'chapterMarks',
  'favorites',
  'settings',
  'evictions',
};
const Set<String> _build446Settings = <String>{
  'fontSize',
  'lineHeight',
  'fontFamily',
  'theme',
  'margin',
  'justify',
  'pageDirection',
  'mangaMode',
  'tapZones',
  'keepScreenOn',
  'allowRotation',
};
const Set<String> _build446ProgressFields = <String>{
  'key',
  'location',
  'fraction',
  'pageIndex',
  'pageCount',
  'chapterId',
  'chapterTitle',
  'title',
  'subtitle',
  'coverUrl',
  'coverHeaders',
  'kind',
  'updatedAt',
};
const Set<String> _build446MarkFields = <String>{
  'read',
  'page',
  'pageCount',
  'updatedAt',
};
const Set<String> _build446FavoriteFields = <String>{
  'key',
  'sourceId',
  'addonId',
  'mangaId',
  'title',
  'coverUrl',
  'coverHeaders',
  'mangaUrl',
  'language',
  'addedAt',
  'snapshot',
};

/// The reader settings added by Build 447 (in reading-state-extra.json).
const Set<String> _build447Settings = <String>{
  'turnStyle',
  'doublePage',
  'firstPageAlone',
  'pdfMode',
  'textLayout',
  'toolbarMode',
  'bookmarkRibbon',
};
