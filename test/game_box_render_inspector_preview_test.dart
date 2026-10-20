// Render previews of the inspector for manual inspection (not part of CI).
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/screens/game_box/game_box_inspector.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
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

Future<Uint8List> _img(int w, int h, void Function(Canvas c, Size s) draw) async {
  final r = ui.PictureRecorder();
  final c = Canvas(r);
  draw(c, Size(w.toDouble(), h.toDouble()));
  final im = await r.endRecording().toImage(w, h);
  return (await im.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List();
}

void _text(Canvas c, String t, Offset o, double size, Color color, {double maxW = 400}) {
  final tp = TextPainter(
    text: TextSpan(text: t, style: TextStyle(fontSize: size, color: color, fontFamily: 'Roboto')),
    textDirection: TextDirection.ltr,
  )..layout(maxWidth: maxW);
  tp.paint(c, o);
}

void main() {
  final out = Platform.environment['GAME_BOX_RENDER_DIR'];
  testWidgets('inspector previews', (tester) async {
    if (out == null) return;
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('xyz.luan/gamepads'), (call) async => <Object>[]);
    final dir = Directory.systemTemp.createTempSync('gbprev');
    final fp = _FP(dir.path);
    const game = GameModel(
      romname: 'Crystal Quest (USA).cue', realname: 'Crystal Quest', name: 'Crystal Quest',
      year: '1998', developer: '', publisher: '', genre: '', players: '', rating: 0,
      systemId: 'ps1', systemFolderName: 'ps1',
    );
    await tester.runAsync(() async {
      final font = FontLoader('Roboto')..addFont(File('${Platform.environment['ROBOTO']}').readAsBytes().then((b) => ByteData.view(b.buffer)));
      await font.load();
      final front = await _img(600, 594, (c, s) {
        c.drawRect(Offset.zero & s, Paint()..shader = const LinearGradient(colors: [Color(0xFF0D3B66), Color(0xFF6A0572)]).createShader(Offset.zero & s));
        c.drawRect(Rect.fromLTWH(0, 0, 60, s.height), Paint()..color = Colors.black);
        _text(c, 'CRYSTAL\nQUEST', const Offset(110, 200), 72, Colors.amberAccent);
      });
      final back = await _img(768, 600, (c, s) {
        c.drawRect(Offset.zero & s, Paint()..color = const Color(0xFF1B1B2F));
        c.drawRect(const Rect.fromLTWH(0, 0, 33, 600), Paint()..color = const Color(0xFF6A0572));
        c.drawRect(const Rect.fromLTWH(735, 0, 33, 600), Paint()..color = const Color(0xFF0D3B66));
        _text(c, 'Enter a world of crystals and danger. Explore 40 caves, solve ancient puzzles and defeat the Shadow King.', const Offset(70, 60), 26, Colors.white, maxW: 620);
        _text(c, '• 40 levels\n• 2 players', const Offset(70, 300), 26, Colors.white);
        _text(c, '© 1998 Example Co. All rights reserved.', const Offset(70, 540), 16, Colors.white70, maxW: 620);
      });
      final store = GameBoxMediaStore(fp);
      File(store.canonicalPath(game, 'ps1', 'box2d', 'png'))..createSync(recursive: true)..writeAsBytesSync(front);
      File(store.canonicalPath(game, 'ps1', GameBoxMediaFolders.back, 'png'))..createSync(recursive: true)..writeAsBytesSync(back);
    });
    final key = GlobalKey();
    Future<void> shot(String name, Size size, {bool backPose = false}) async {
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1;
      await tester.pumpWidget(RepaintBoundary(
        key: key,
        child: MaterialApp(
          key: ValueKey(name),
          debugShowCheckedModeBanner: false,
          theme: ThemeData(brightness: Brightness.dark, fontFamily: 'Roboto', colorSchemeSeed: Colors.indigo),
          home: Builder(builder: (context) => Scaffold(body: Center(child: ElevatedButton(
            onPressed: () => GameBoxInspector.open(context, onPlay: () {},
                subject: GameBoxSubject(game: game, systemFolder: 'ps1', fileProvider: fp, systemId: 'ps1', appSystemId: 'ps1')),
            child: const Text('open'))))),
        ),
      ));
      await tester.runAsync(() async {
        final ctx = key.currentContext!;
        final store = GameBoxMediaStore(fp);
        for (final folder in ['box2d', GameBoxMediaFolders.back]) {
          final f = File(store.canonicalPath(game, 'ps1', folder, 'png'));
          for (final w in [1024, 2400]) {
            await precacheImage(ResizeImage(FileImage(f), width: w), ctx);
          }
        }
      });
      await tester.tap(find.text('open'));
      for (var i = 0; i < 20; i++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      await tester.runAsync(() async {
        await Future<void>.delayed(const Duration(milliseconds: 300));
      });
      if (backPose) {
        await tester.tap(find.text('Back cover'));
        await tester.pumpAndSettle();
      }
      for (var i = 0; i < 3; i++) {
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
        await tester.pump();
      }
      await tester.runAsync(() async {
        final b = key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final im = await b.toImage(pixelRatio: 1);
        File('$out/$name.png').writeAsBytesSync((await im.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List());
      });
    }
    await shot('inspector_portrait', const Size(430, 900));
    await shot('inspector_back', const Size(430, 900), backPose: true);
    await shot('inspector_landscape', const Size(932, 430));
    tester.view.reset();
  });
}
