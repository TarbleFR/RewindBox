// Before/after comparison renders of the 3D box viewer (not part of CI).
//
// Drives the real GameBoxInspector with the filmed cases (PS3 XMB icon used
// as a front, a real PS3 cover, the square Switch icon, a uniform green
// Switch back, a 3DS control box, a low resolution Game Boy Color back) and
// writes PNG frames to $GAME_BOX_COMPARE_OUT. Artwork comes from
// $GAME_BOX_COMPARE_ART (local files, never committed). Only APIs present
// before and after the correction are used, so the same file renders both.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/gestures.dart';
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

class _Case {
  const _Case(this.id, this.system, this.title, {this.front, this.back, this.rotate = false, this.pinchLeft = false});
  final String id;
  final String system;
  final String title;
  final String? front;
  final String? back;
  final bool rotate;
  final bool pinchLeft;
}

const _cases = [
  _Case('ps3_bladestorm', 'ps3', 'Bladestorm', front: 'ps3_bladestorm_icon0.png'),
  _Case('ps3_gow3', 'ps3', 'God of War III', front: 'ps3_gow3_front.jpg', back: 'ps3_gow3_back.jpg', rotate: true),
  _Case('switch_hogwarts', 'switch', 'Hogwarts Legacy', front: 'switch_hogwarts_icon.jpg', back: 'switch_hogwarts_back.jpg'),
  _Case('switch_mario', 'switch', 'Super Mario 3D World', front: 'switch_mario_front.jpg', back: 'switch_mario_back_green.png', rotate: true),
  _Case('3ds_mk7', '3ds', 'Mario Kart 7', front: '3ds_mk7_front.png', back: '3ds_mk7_back.png', rotate: true),
  _Case('gbc_back', 'gbc', 'Pocket Quest', front: 'gbc_front.png', back: 'gbc_back.png', pinchLeft: true),
];

void main() {
  final out = Platform.environment['GAME_BOX_COMPARE_OUT'];
  final art = Platform.environment['GAME_BOX_COMPARE_ART'];
  final only = Platform.environment['GAME_BOX_COMPARE_ONLY'];
  for (final c in _cases) {
    if (only != null && only.isNotEmpty && !only.split(',').contains(c.id)) continue;
    testWidgets('compare ${c.id}', (tester) async {
      if (out == null || art == null) return;
      SharedPreferences.setMockInitialValues({});
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(const MethodChannel('xyz.luan/gamepads'), (call) async => <Object>[]);
      final dir = Directory.systemTemp.createTempSync('gbcmp');
      final fp = _FP(dir.path);
      final game = GameModel(
        romname: '${c.title}.iso', realname: c.title, name: c.title,
        year: '', developer: '', publisher: '', genre: '', players: '', rating: 0,
        systemId: c.system, systemFolderName: c.system,
      );
      final store = GameBoxMediaStore(fp);
      final written = <String>[];
      await tester.runAsync(() async {
        final font = FontLoader('Roboto')
          ..addFont(File('${Platform.environment['ROBOTO']}').readAsBytes().then((b) => ByteData.view(b.buffer)));
        await font.load();
        void put(String? name, String folder) {
          if (name == null) return;
          final ext = p.extension(name).replaceFirst('.', '');
          final target = store.canonicalPath(game, c.system, folder, ext);
          File(target)
            ..createSync(recursive: true)
            ..writeAsBytesSync(File(p.join(art, name)).readAsBytesSync());
          written.add(target);
        }
        put(c.front, 'box2d');
        put(c.back, GameBoxMediaFolders.back);
      });
      final dirOut = Directory(p.join(out, c.id))..createSync(recursive: true);
      final key = GlobalKey();
      tester.view.physicalSize = const Size(852 * 2, 393 * 2);
      tester.view.devicePixelRatio = 2;
      await tester.pumpWidget(RepaintBoundary(
        key: key,
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: ThemeData(brightness: Brightness.dark, fontFamily: 'Roboto', colorSchemeSeed: Colors.indigo),
          home: Builder(builder: (context) => Scaffold(body: Center(child: ElevatedButton(
            onPressed: () => GameBoxInspector.open(context, onPlay: () {},
                subject: GameBoxSubject(game: game, systemFolder: c.system, fileProvider: fp, systemId: c.system, appSystemId: c.system)),
            child: const Text('open'))))),
        ),
      ));
      await tester.runAsync(() async {
        final ctx = key.currentContext!;
        // Both decode keys: by width (before) and by longest side (after).
        for (final f in written) {
          for (final w in [1024, 2400]) {
            await precacheImage(ResizeImage(FileImage(File(f)), width: w), ctx);
          }
          await precacheImage(
              ResizeImage(FileImage(File(f)), width: 2400, height: 2400, policy: ResizeImagePolicy.fit), ctx);
        }
      });
      Future<void> settle() async {
        for (var i = 0; i < 4; i++) {
          await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 150)));
          await tester.pump(const Duration(milliseconds: 50));
        }
      }
      var frame = 0;
      Future<void> shot(String name, {double ratio = 1}) async {
        await tester.runAsync(() async {
          final b = key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
          final im = await b.toImage(pixelRatio: ratio);
          File(p.join(dirOut.path, '$name.png'))
              .writeAsBytesSync((await im.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List());
          im.dispose();
        });
      }
      await tester.tap(find.text('open'));
      for (var i = 0; i < 20; i++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      await settle();
      await shot('a_rest');
      await tester.tap(find.text('Front cover'));
      await tester.pumpAndSettle();
      await settle();
      await shot('b_front');
      // The "Back cover" button: every frame of its animation.
      await tester.tap(find.text('Back cover'));
      for (var i = 0; i < 30; i++) {
        await tester.pump(const Duration(milliseconds: 16));
        await shot('c_button_${(frame++).toString().padLeft(3, '0')}', ratio: 0.5);
      }
      await tester.pumpAndSettle();
      await settle();
      await shot('d_back');
      if (c.rotate) {
        // Back to the front, then a full turn by dragging, frame by frame.
        await tester.tap(find.text('Front cover'));
        await tester.pumpAndSettle();
        await settle();
        final area = tester.getRect(find.byType(ClipRect).first);
        final gesture = await tester.startGesture(area.center, kind: PointerDeviceKind.touch);
        await tester.pump(const Duration(milliseconds: 16));
        var turn = 0;
        for (var i = 0; i < 120; i++) {
          await gesture.moveBy(const Offset(-8, 0));
          await tester.pump(const Duration(milliseconds: 16));
          await shot('e_turn_${(turn++).toString().padLeft(3, '0')}', ratio: 0.5);
        }
        await gesture.up();
        await tester.pumpAndSettle();
        await settle();
        await shot('f_after_turn');
      }
      if (c.pinchLeft) {
        await tester.tap(find.text('Back cover'));
        await tester.pumpAndSettle();
        await settle();
        final area = tester.getRect(find.byType(ClipRect).first);
        final focus = Offset(area.left + area.width * 0.30, area.center.dy);
        final a = await tester.startGesture(focus - const Offset(20, 0));
        final b = await tester.startGesture(focus + const Offset(20, 0));
        await tester.pump(const Duration(milliseconds: 16));
        for (var i = 0; i < 20; i++) {
          await a.moveBy(const Offset(-6, 0));
          await b.moveBy(const Offset(6, 0));
          await tester.pump(const Duration(milliseconds: 16));
        }
        await a.up();
        await b.up();
        await tester.pumpAndSettle();
        await settle();
        await shot('g_pinch_left');
      }
      tester.view.reset();
    });
  }
}
