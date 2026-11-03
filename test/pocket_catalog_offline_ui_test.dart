import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:neostation/screens/libretro/libretro_skin_catalog_screen.dart';
import 'package:neostation/services/bundled_controller_skins.dart';
import 'package:neostation/services/libretro_skin_catalog_service.dart';
import 'package:neostation/services/libretro_skin_catalogs.dart';
import 'package:neostation/services/libretro_skin_compatibility.dart';
import 'package:neostation/services/libretro_skin_service.dart';
import 'package:neostation/widgets/liquid_progress.dart';
import 'package:path/path.dart' as path;

final _png = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
);

BundledControllerSkin _bundle(String console) => BundledControllerSkin(
  id: 'pocket-test-$console', name: 'Pocket offline $console', console: console,
  archiveAsset: 'assets/skins/pocket/test-$console.manicskin',
  sha256: List.filled(64, '0').join(), size: 1,
  previewAssets: {
    'portrait': 'assets/skins/pocket/test-$console-portrait.png',
    'landscape': 'assets/skins/pocket/test-$console-landscape.png',
  },
  author: 'RewindBox', license: 'Original test artwork',
);

/// Uses the framework asset path and real PNG decoding, without changing the
/// global platform messenger used by unrelated tests.
class _PreviewAssets extends CachingAssetBundle {
  @override
  Future<ByteData> load(String key) async {
    if (key == 'AssetManifest.bin') return const StandardMessageCodec().encodeMessage(<String, Object?>{})!;
    if (key == 'AssetManifest.json') return ByteData.sublistView(Uint8List.fromList(utf8.encode('{}')));
    if (key.startsWith('assets/skins/pocket/test-') && key.endsWith('.png')) {
      return ByteData.sublistView(_png);
    }
    throw FlutterError('Unexpected test asset: $key');
  }
}

class _PendingCatalogs extends LibretroSkinCatalogs {
  _PendingCatalogs(LibretroSkinService skins, String console)
      : super(
          skins: skins,
          provenance: LibretroSkinCatalogService(
            cacheDirectory: skins.cacheDirectory, skins: skins,
            client: MockClient((_) async => throw StateError('Unexpected HTTP')),
          ),
          client: MockClient((_) async => throw StateError('Unexpected HTTP')),
          loadBundledSkins: () async => [_bundle(console)],
          overlayIndex: () async => '{"version":1,"sources":{},"entries":[]}',
        );

  final remote = Completer<List<LibretroCatalogSkin>?>();
  final savedFavorites = <String>{};
  bool offline = false;

  @override
  Set<String> get unavailableSources => offline
      ? {LibretroSkinSources.provenance, LibretroSkinSources.deltaSkins}
      : const {};

  @override
  Future<List<LibretroCatalogSkin>?> load({bool refresh = false}) => remote.future;

  @override
  Future<Set<String>> favorites() async => Set.of(savedFavorites);

  @override
  Future<void> setFavorite(LibretroCatalogSkin entry, bool favorite) async {
    favorite ? savedFavorites.add(entry.key) : savedFavorites.remove(entry.key);
  }

  @override
  Future<Map<String, LibretroSkinCompatibility>> classifyAll(
    List<LibretroCatalogSkin> entries, String console, {
    void Function(LibretroCatalogSkin, LibretroSkinCompatibility)? onVerdict,
    bool Function()? cancelled,
  }) async {
    final result = <String, LibretroSkinCompatibility>{};
    for (final entry in entries) {
      await Future<void>.value();
      if (cancelled?.call() ?? false) break;
      final verdict = LibretroSkinCompatibility(
        verdict: LibretroSkinVerdict.compatible, console: console,
        orientations: const {'portrait': 'compatible', 'landscape': 'compatible'},
      );
      result[entry.key] = verdict;
      onVerdict?.call(entry, verdict);
    }
    return result;
  }
}

Future<void> _until(WidgetTester tester, bool Function() ready) async {
  for (var round = 0; round < 200; round++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 10)));
    await tester.pump();
    if (ready()) return;
  }
  fail('Pocket catalog did not reach the expected state');
}

Future<void> _mount(WidgetTester tester, LibretroSkinService skins, _PendingCatalogs catalogs, String console, {String? readyName}) async {
  await tester.pumpWidget(DefaultAssetBundle(
    bundle: _PreviewAssets(),
    child: MaterialApp(locale: const Locale('en'),
      home: LibretroSkinCatalogScreen(console: console, skins: skins, catalogs: catalogs)),
  ));
  await _until(tester, () => find.text(readyName ?? 'Pocket offline $console').evaluate().isNotEmpty);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory root;
  late LibretroSkinService skins;
  setUp(() async {
    root = await Directory.systemTemp.createTemp('pocket-catalog-ui-');
    skins = LibretroSkinService(
      skinsDirectory: path.join(root.path, 'Skins'),
      frontendDirectory: path.join(root.path, 'Frontend'),
      cacheDirectory: path.join(root.path, 'Cache'),
    );
  });
  tearDown(() async => root.delete(recursive: true));

  testWidgets('bundled art decodes before remote completion and a favorite survives offline completion', (tester) async {
    final catalogs = _PendingCatalogs(skins, 'wii');
    addTearDown(catalogs.dispose);
    await _mount(tester, skins, catalogs, 'wii');
    await _until(tester, () => tester.widgetList<RawImage>(find.byType(RawImage))
        .any((image) => image.image != null && image.image!.width > 0 && image.image!.height > 0));
    expect(catalogs.remote.isCompleted, isFalse);
    expect(tester.takeException(), isNull);
    // The Favorites filter has the same icon: scope the tap to its button.
    await tester.tap(find.widgetWithIcon(IconButton, Icons.star_border));
    await tester.pump();
    expect(find.widgetWithIcon(IconButton, Icons.star), findsOneWidget);
    catalogs.offline = true;
    catalogs.remote.complete(await catalogs.bundledEntries());
    await _until(tester, () => find.byType(LiquidProgressIndicator).evaluate().isEmpty);
    expect(find.text('Pocket offline wii'), findsOneWidget);
    expect(find.widgetWithIcon(IconButton, Icons.star), findsOneWidget);
    expect(catalogs.savedFavorites, contains('bundled:pocket-test-wii'));
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a remembered remote source falls back offline and returns when that source is available', (tester) async {
    const remoteEntry = LibretroCatalogSkin(
      key: 'remote:gc-test', source: LibretroSkinSources.provenance,
      name: 'Remote GameCube test', consoles: ['gc'], author: 'Test author',
    );
    final initial = _PendingCatalogs(skins, 'gc');
    addTearDown(initial.dispose);
    initial.remote.complete([...await initial.bundledEntries(), remoteEntry]);
    await _mount(tester, skins, initial, 'gc');
    await _until(tester, () => find.widgetWithText(FilterChip, 'Provenance').evaluate().isNotEmpty);
    await tester.tap(find.widgetWithText(FilterChip, 'Provenance'));
    await tester.pump();
    expect(find.text('Remote GameCube test'), findsOneWidget);
    expect(find.text('Pocket offline gc'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());

    final offline = _PendingCatalogs(skins, 'gc');
    addTearDown(offline.dispose);
    await _mount(tester, skins, offline, 'gc');
    expect(offline.remote.isCompleted, isFalse);
    offline.offline = true;
    offline.remote.complete(await offline.bundledEntries());
    await _until(tester, () => find.byType(LiquidProgressIndicator).evaluate().isEmpty);
    expect(find.text('Pocket offline gc'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());

    final returned = _PendingCatalogs(skins, 'gc');
    addTearDown(returned.dispose);
    returned.remote.complete([...await returned.bundledEntries(), remoteEntry]);
    await _mount(tester, skins, returned, 'gc', readyName: 'Remote GameCube test');
    await _until(tester, () => find.text('Remote GameCube test').evaluate().isNotEmpty);
    expect(find.text('Pocket offline gc'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
