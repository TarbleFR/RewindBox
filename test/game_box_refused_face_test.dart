// The filmed Super Mario 3D World back: a uniform #00FF00 file on disk is
// never drawn as the back; the valid faces stay (docs/game-box-3d.md § 15).
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/screens/game_box/game_box_inspector.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';
import 'package:neostation/widgets/game_box/game_box_surfaces.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

class _FP extends FileProvider {
  _FP(this.root);
  final String root;
  @override
  bool get isInitialized => true;
  @override
  String getMediaPath(String s, String t, String r, String e) =>
      p.join(root, 'media', s, t, '${FileProvider.stripRomExtension(r)}.$e');
  @override
  String getMediaDirectoryPath() => p.join(root, 'media');
  @override
  List<String> getEsdeMediaCandidates(String s, String t, String r) => const [];
}

Future<Uint8List> _png(int w, int h, {Color? flat}) async {
  final recorder = ui.PictureRecorder();
  final c = Canvas(recorder);
  final s = Size(w.toDouble(), h.toDouble());
  c.drawRect(Offset.zero & s, Paint()..color = flat ?? const Color(0xFFE60012));
  if (flat == null) c.drawCircle(Offset(w / 2, h / 2), w / 3, Paint()..color = const Color(0xFF2040A0));
  final image = await recorder.endRecording().toImage(w, h);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  return data!.buffer.asUint8List();
}

void main() {
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(mapLocales: [MapLocale('en', AppLocale.en)], initLanguageCode: 'en');
  });

  testWidgets('a uniform green back is drawn as refused, the front stays, the search is offered', (tester) async {
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('xyz.luan/gamepads'), (call) async => <Object>[]);
    GameBoxMediaChecker.clearCache();
    final dir = Directory.systemTemp.createTempSync('gbgreen');
    addTearDown(() => dir.deleteSync(recursive: true));
    final fp = _FP(dir.path);
    const game = GameModel(
      romname: 'Super Mario 3D World.nsp', realname: 'Super Mario 3D World', name: 'Super Mario 3D World',
      year: '', developer: '', publisher: '', genre: '', players: '', rating: 0,
      systemId: 'switch', systemFolderName: 'switch',
    );
    final store = GameBoxMediaStore(fp);
    final frontPath = store.canonicalPath(game, 'switch', 'box2d', 'png');
    final backPath = store.canonicalPath(game, 'switch', GameBoxMediaFolders.back, 'png');
    await tester.runAsync(() async {
      File(frontPath)
        ..createSync(recursive: true)
        ..writeAsBytesSync(await _png(233, 377));
      File(backPath)
        ..createSync(recursive: true)
        ..writeAsBytesSync(await _png(233, 377, flat: const Color(0xFF00FF00)));
      // The checks the inspector starts are made here, outside fake time.
      expect((await GameBoxMediaChecker.checkFile(backPath)).verdict, GameBoxImageVerdict.uniform);
      expect((await GameBoxMediaChecker.checkFile(frontPath)).ok, isTrue);
    });
    tester.view.physicalSize = const Size(852, 393);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: ElevatedButton(
              onPressed: () => GameBoxInspector.open(
                context,
                onPlay: () {},
                subject: GameBoxSubject(
                    game: game, systemFolder: 'switch', fileProvider: fp, systemId: 'switch', appSystemId: 'switch'),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 32));
    }
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    final state = tester.state<GameBoxInspectorState>(find.byType(GameBoxInspector));
    expect(state.refusedFaces, {GameBoxMediaKind.back: GameBoxImageVerdict.uniform});
    await tester.tap(find.text('Back cover'));
    await tester.pumpAndSettle();
    final scene = tester.widget<GameBoxScene>(find.byType(GameBoxScene));
    expect(scene.art.back, isNull, reason: 'the green file is not the back');
    expect(scene.art.front, isNotNull, reason: 'the valid front stays');
    expect(find.byType(GameBoxNeutralFace), findsWidgets);
    expect(find.text('Back refused: not a scan'), findsOneWidget);
    expect(find.textContaining('Back cover: picture refused, one flat colour, not a scan.'), findsOneWidget);
    expect(find.text('Get the box faces'), findsOneWidget, reason: 'another source can be searched');
    expect(File(backPath).existsSync(), isTrue, reason: 'the player\'s file is never deleted by viewing');
  });
}
