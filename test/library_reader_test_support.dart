// Shared helpers of the Library reader tests (no network, no device).
import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_content.dart';
import 'package:neostation/screens/library_screen/reader/library_page_source.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_system.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_local_fixtures.dart';

/// Wake lock calls made by the readers.
final List<bool> wakelockCalls = <bool>[];

/// Stubs the platform plugins the readers touch.
void setUpReaderEnvironment() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    wakelockCalls.clear();
    LibraryReaderSystemSession.wakelock = (enabled) async {
      wakelockCalls.add(enabled);
    };
    LibraryReaderOrientation.instance = LibraryReaderOrientation(isIOS: false);
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    // GamepadNavigation.initialize() finds no controller.
    messenger.setMockMethodCallHandler(
      const MethodChannel('xyz.luan/gamepads'),
      (call) async => <dynamic>[],
    );
    // Haptics, SystemChrome: accepted silently.
    messenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async => null,
    );
  });
}

/// Lets real asynchronous work (file I/O, worker isolates) progress while
/// the test runs in fake time.
Future<void> settle(WidgetTester tester, {int rounds = 12}) async {
  for (var i = 0; i < rounds; i++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 15)),
    );
    await tester.pump();
  }
}

/// Runs the frames of a page turn or scroll animation (it starts on the
/// frame after the input).
Future<void> frames(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
}

/// A store in a fresh temporary directory, loaded.
Future<(LibraryReadingStore, Directory)> createStore(
  WidgetTester tester, {
  Directory? directory,
}) async {
  final dir =
      directory ??
      (await tester.runAsync(() => createTempDir('ns_reader_store_')))!;
  final store = LibraryReadingStore(
    directory: dir,
    saveDelay: const Duration(milliseconds: 5),
  );
  await tester.runAsync(store.load);
  return (store, dir);
}

/// Writes every pending change of [store] (the write runs in fake time).
Future<void> flushStore(WidgetTester tester, LibraryReadingStore store) async {
  unawaited(store.flush());
  for (var i = 0; i < 20 && store.hasPendingChanges; i++) {
    await settle(tester, rounds: 1);
  }
  expect(store.hasPendingChanges, isFalse);
}

/// Sets a landscape phone-like test surface (logical pixels, ratio 1).
void useSurface(WidgetTester tester, {Size size = const Size(900, 600)}) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
}

/// Hosts [reader] above a home route so it can be closed.
Future<GlobalKey<NavigatorState>> pumpReader(
  WidgetTester tester,
  Widget reader, {
  Locale locale = const Locale('en'),
}) async {
  final navigator = GlobalKey<NavigatorState>();
  await tester.pumpWidget(
    MaterialApp(
      navigatorKey: navigator,
      locale: locale,
      supportedLocales: <Locale>[locale],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: const Scaffold(body: Text('home')),
    ),
  );
  unawaited(
    navigator.currentState!.push<void>(
      MaterialPageRoute<void>(builder: (_) => reader),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  // The store was loaded in the real zone: its continuations need real
  // event-loop turns as well as fake-time pumps.
  await settle(tester, rounds: 3);
  return navigator;
}

/// Pages decoded from tiny PNGs kept in memory.
class MemoryPageSource implements LibraryPageSource {
  MemoryPageSource(int count, {this.key = 'memory', this.failing = const {}})
    : pages = List<Uint8List>.generate(
        count,
        (i) => buildPng(4, 6, red: (40 * i) & 0xFF),
      );

  @override
  final String key;
  final List<Uint8List> pages;

  /// Pages whose first [FailingImage] load fails.
  final Set<int> failing;
  final List<int> prefetched = <int>[];
  final Map<int, FailingImage> _failing = <int, FailingImage>{};
  bool disposed = false;

  @override
  int get length => pages.length;

  @override
  ImageProvider imageFor(int index, {int? cacheWidth, int? cacheHeight}) {
    if (failing.contains(index)) {
      return _failing.putIfAbsent(index, () => FailingImage('$key#$index'));
    }
    return MemoryImage(pages[index]);
  }

  @override
  void prefetch(int index) => prefetched.add(index);

  @override
  Future<void> dispose() async => disposed = true;
}

/// An image that fails on its first load and stays pending afterwards.
class FailingImage extends ImageProvider<FailingImage> {
  FailingImage(this.id);

  final String id;
  int loads = 0;

  @override
  Future<FailingImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture<FailingImage>(this);

  @override
  ImageStreamCompleter loadImage(
    FailingImage key,
    ImageDecoderCallback decode,
  ) {
    loads++;
    if (loads == 1) {
      return OneFrameImageStreamCompleter(
        Future<ImageInfo>.error(
          const LibraryNetworkException(
            LibraryNetworkErrorKind.serverUnavailable,
            statusCode: 503,
          ),
        ),
      );
    }
    return OneFrameImageStreamCompleter(Completer<ImageInfo>().future);
  }

  @override
  bool operator ==(Object other) => other is FailingImage && other.id == id;

  @override
  int get hashCode => id.hashCode;
}

typedef FakeLoader =
    Future<LibraryPageSource> Function(int index, LibraryCancelToken cancel);

/// Page reader content with in-memory chapters.
class FakePageContent extends LibraryPageReaderContent {
  FakePageContent({
    this.title = 'Fake title',
    this.progressKey = 'online:fake:manga',
    this.chapterCount = 1,
    this.pagesPerChapter = 5,
    this.tracksChapters = false,
    this.initialChapterIndex = 0,
    this.startPage,
    this.layoutHint = LibraryPageLayoutHint.unknown,
    FakeLoader? loader,
  }) : _loader = loader;

  @override
  final String title;
  @override
  final String progressKey;
  final int chapterCount;
  final int pagesPerChapter;
  @override
  final bool tracksChapters;
  @override
  final int initialChapterIndex;
  @override
  final int? startPage;
  @override
  final LibraryPageLayoutHint layoutHint;
  final FakeLoader? _loader;
  final List<int> loads = <int>[];
  final List<MemoryPageSource> sources = <MemoryPageSource>[];

  @override
  List<LibraryPageReaderChapter> get chapters => <LibraryPageReaderChapter>[
    for (var i = 0; i < chapterCount; i++)
      LibraryPageReaderChapter(id: 'c$i', number: (i + 1).toDouble()),
  ];

  @override
  Future<LibraryPageSource> load(int index, LibraryCancelToken cancel) async {
    loads.add(index);
    final loader = _loader;
    if (loader != null) return loader(index, cancel);
    final source = MemoryPageSource(pagesPerChapter, key: 'chapter$index');
    sources.add(source);
    return source;
  }
}
