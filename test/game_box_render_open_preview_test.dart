// Render previews of the open boxes and their manuals, and of the list view's
// boxes, for manual inspection (not part of CI). Run with GAME_BOX_RENDER_DIR
// and ROBOTO (a Roboto TTF) set. Every image is generated here: no real cover.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:provider/provider.dart';
import 'package:neostation/screens/game_box/game_box_inspector.dart';
import 'package:neostation/screens/game_screen/game_list_view.dart';
import 'package:neostation/services/game_box/game_box_manual.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/sfx_service.dart';
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

Future<ui.Image> _image(int w, int h, void Function(Canvas c, Size s) draw) async {
  final r = ui.PictureRecorder();
  final c = Canvas(r);
  draw(c, Size(w.toDouble(), h.toDouble()));
  return r.endRecording().toImage(w, h);
}

Future<Uint8List> _png(ui.Image im) async => (await im.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List();

void _text(Canvas c, String t, Offset o, double size, Color color, {double maxW = 400}) {
  final tp = TextPainter(
    text: TextSpan(text: t, style: TextStyle(fontSize: size, color: color, fontFamily: 'Roboto')),
    textDirection: TextDirection.ltr,
  )..layout(maxWidth: maxW);
  tp.paint(c, o);
}

GameModel _game(String system, String name) => GameModel(
      romname: '$name (USA).bin', realname: name, name: name,
      year: '', developer: '', publisher: '', genre: '', players: '', rating: 0,
      systemId: system, systemFolderName: system,
    );

void main() {
  final out = Platform.environment['GAME_BOX_RENDER_DIR'];
  testWidgets('open box and list previews', (tester) async {
    if (out == null) return;
    SharedPreferences.setMockInitialValues({});
    SfxService().setEnabled(false);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('xyz.luan/gamepads'), (call) async => <Object>[]);
    final dir = Directory.systemTemp.createTempSync('gbopen');
    final fp = _FP(dir.path);
    final cases = {
      'ps2': (_game('ps2', 'Sky Harbor'), 0.70, Size(520, 740)),
      'ps1': (_game('ps1', 'Crystal Quest'), 1.0, Size(600, 594)),
      'nes': (_game('nes', 'Pixel Knight'), 0.72, Size(500, 700)),
      'ds': (_game('ds', 'Pocket Garden'), 0.9, Size(520, 470)),
      'snes': (_game('snes', 'Star Rally'), 1.4, Size(700, 500)),
    };
    final covers = <String, ui.Image>{};
    await tester.runAsync(() async {
      final font = FontLoader('Roboto')
        ..addFont(File('${Platform.environment['ROBOTO']}').readAsBytes().then((b) => ByteData.view(b.buffer)));
      await font.load();
      for (final MapEntry(key: system, value: (game, aspect, size)) in cases.entries) {
        final front = await _image(size.width.round(), size.height.round(), (c, s) {
          c.drawRect(Offset.zero & s, Paint()..shader = const LinearGradient(colors: [Color(0xFF0D3B66), Color(0xFF6A0572)]).createShader(Offset.zero & s));
          _text(c, game.name.toUpperCase(), Offset(s.width * 0.12, s.height * 0.35), s.width * 0.1, Colors.amberAccent, maxW: s.width * 0.8);
        });
        final store = GameBoxMediaStore(fp);
        File(store.canonicalPath(game, system, 'box2d', 'png'))
          ..createSync(recursive: true)
          ..writeAsBytesSync(await _png(front));
        // A local "PDF" (only its existence matters here; the page is drawn below).
        File(game.getManualPath(system, fp))
          ..createSync(recursive: true)
          ..writeAsStringSync('%PDF-1.4');
        final pageH = 720;
        final pageW = (pageH * aspect).round();
        covers[game.getManualPath(system, fp)] = await _image(pageW, pageH, (c, s) {
          c.drawRect(Offset.zero & s, Paint()..color = const Color(0xFFF7F3EA));
          c.drawRect(Rect.fromLTWH(0, s.height * 0.08, s.width, s.height * 0.22), Paint()..color = const Color(0xFFB71C1C));
          _text(c, 'INSTRUCTION BOOKLET', Offset(s.width * 0.08, s.height * 0.12), s.width * 0.07, Colors.white, maxW: s.width * 0.9);
          _text(c, game.name, Offset(s.width * 0.08, s.height * 0.45), s.width * 0.1, const Color(0xFF222222), maxW: s.width * 0.9);
        });
      }
    });
    GameBoxManualCover.debugRenderer = (path) async {
      final page = covers[path];
      if (page == null) return null;
      return GameBoxManualPage(image: page.clone(), aspect: page.width / page.height, pageCount: 24);
    };
    GameBoxInspector.manualReader = (path, title) => Scaffold(body: Center(child: Text('READER $title')));
    addTearDown(() {
      GameBoxManualCover.debugRenderer = null;
    });

    final key = GlobalKey();
    Future<void> capture(String name) async {
      await tester.runAsync(() async {
        final b = key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final im = await b.toImage(pixelRatio: 1);
        File('$out/$name.png').writeAsBytesSync(await _png(im));
      });
    }

    Future<void> settleImages() async {
      for (var i = 0; i < 4; i++) {
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 150)));
        await tester.pump();
      }
    }

    for (final MapEntry(key: system, value: (game, _, _)) in cases.entries) {
      tester.view.physicalSize = const Size(430, 900);
      tester.view.devicePixelRatio = 1;
      await tester.pumpWidget(RepaintBoundary(
        key: key,
        child: MaterialApp(
          key: ValueKey(system),
          debugShowCheckedModeBanner: false,
          theme: ThemeData(brightness: Brightness.dark, fontFamily: 'Roboto', colorSchemeSeed: Colors.indigo),
          home: Builder(builder: (context) => Scaffold(body: Center(child: ElevatedButton(
            onPressed: () => GameBoxInspector.open(context, onPlay: () {},
                subject: GameBoxSubject(game: game, systemFolder: system, fileProvider: fp, systemId: system)),
            child: const Text('open'))))),
        ),
      ));
      await tester.tap(find.text('open'));
      for (var i = 0; i < 12; i++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      await settleImages();
      await capture('closed_$system');
      await tester.tap(find.byKey(const ValueKey('game_box_open')));
      for (var i = 0; i < 30; i++) {
        await tester.pump(const Duration(milliseconds: 40));
      }
      await settleImages();
      await capture('open_$system');
      // Midway through taking the manual out.
      await tester.tap(find.byKey(const ValueKey('game_box_manual_chip')));
      for (var i = 0; i < 14; i++) {
        await tester.pump(const Duration(milliseconds: 30));
      }
      await capture('taking_$system');
      await tester.pumpAndSettle();
      Navigator.of(tester.element(find.textContaining('READER'))).pop();
      await tester.pumpAndSettle();
      await settleImages();
      await capture('returned_$system');
    }

    // The list view: 3D thumbnails, halo on the selected title only.
    tester.view.physicalSize = const Size(900, 420);
    final games = [for (final c in cases.values) c.$1];
    final system = SystemModel(id: 'all', folderName: 'all', realName: 'All', iconImage: '', color: '#3355ff');
    await tester.pumpWidget(RepaintBoundary(
      key: key,
      child: ChangeNotifierProvider<SqliteConfigProvider>(
        create: (_) => SqliteConfigProvider(),
        child: ScreenUtilInit(
        designSize: const Size(640, 360),
        builder: (context, child) => MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: ThemeData(brightness: Brightness.dark, fontFamily: 'Roboto', colorSchemeSeed: Colors.indigo),
          home: Scaffold(
            body: Row(children: [
              SizedBox(
                width: 300,
                child: GameListView(
                  system: system,
                  games: games,
                  selectedIndex: 1,
                  systemColor: Colors.indigo,
                  onGameSelected: (_) {},
                  onGameConfirmed: () {},
                  isAllMode: true,
                  fileProvider: fp,
                  onInspectBox: (_) {},
                ),
              ),
              const Expanded(child: SizedBox()),
            ]),
          ),
        ),
      ),
      ),
    ));
    await tester.pump(const Duration(milliseconds: 600));
    for (var i = 0; i < 4; i++) {
      await settleImages();
    }
    await tester.pump(const Duration(milliseconds: 600));
    await capture('list_view');
    tester.view.reset();
  });
}
