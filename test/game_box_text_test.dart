import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neo_box_reader/neo_box_reader.dart';
import 'package:neostation/services/game_box/box_text_layout.dart';
import 'package:neostation/services/game_box/box_text_service.dart';
import 'package:path/path.dart' as p;

BoxReaderLine _line(String text, double x, double y, {double w = 0.4, double h = 0.02, double c = 0.95}) =>
    BoxReaderLine(text: text, confidence: c, x: x, y: y, width: w, height: h);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('layout', () {
    test('two columns are read column by column, top to bottom', () {
      final doc = BoxTextLayout.group([
        _line('Left one', 0.05, 0.20),
        _line('Right one', 0.55, 0.20),
        _line('Left two', 0.05, 0.225),
        _line('Right two', 0.55, 0.225),
        _line('Footer text', 0.05, 0.60, w: 0.9),
      ]);
      expect(doc.blocks.map((b) => b.units.join('|')).toList(),
          ['Left one Left two', 'Right one Right two', 'Footer text']);
    });

    test('headings, bullet lists and legal print are told apart', () {
      final doc = BoxTextLayout.group([
        _line('ADVENTURE AWAITS', 0.1, 0.05, h: 0.045),
        _line('A long story of a hero who', 0.1, 0.15),
        _line('saves the kingdom.', 0.1, 0.175),
        _line('• 40 levels', 0.1, 0.30),
        _line('• 2 players', 0.1, 0.325),
        _line('© 1998 Company. All rights reserved.', 0.1, 0.9, h: 0.015),
      ]);
      expect(doc.blocks.map((b) => b.kind).toList(), [
        BoxTextBlockKind.heading,
        BoxTextBlockKind.paragraph,
        BoxTextBlockKind.list,
        BoxTextBlockKind.legal,
      ]);
      expect(doc.blocks[2].units, ['40 levels', '2 players']);
      expect(doc.units, hasLength(6 - 1));
    });

    test('hyphenated words and CJK lines are rejoined without inventing text', () {
      expect(BoxTextLayout.join('an extra-', 'ordinary game'), 'an extraordinary game');
      expect(BoxTextLayout.join('Rock-', 'Paper'), 'Rock- Paper');
      expect(BoxTextLayout.join('冒険の', '始まり'), '冒険の始まり');
    });

    test('unreadable lines are counted, weak ones flagged, symbols dropped', () {
      final doc = BoxTextLayout.group([
        _line('Readable line', 0.1, 0.1),
        _line('Weak line', 0.1, 0.125, c: 0.3),
        _line('xx#', 0.1, 0.5, c: 0.05),
        _line('***', 0.1, 0.7),
      ]);
      expect(doc.illegibleLines, 1);
      expect(doc.hasLowConfidence, isTrue);
      expect(doc.plainText, isNot(contains('***')));
    });
  });

  group('service', () {
    late Directory dir;
    late File scan;
    final calls = <String>[];
    var translateFails = '';

    setUp(() {
      dir = Directory.systemTemp.createTempSync('box_text');
      scan = File(p.join(dir.path, 'back.png'))..writeAsBytesSync(List.generate(64, (i) => i));
      BoxTextService.rootForTesting = p.join(dir.path, 'cache');
      NeoBoxReader.debugSupported = true;
      calls.clear();
      translateFails = '';
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
        const MethodChannel('neostation/neo_box_reader'),
        (call) async {
          calls.add(call.method);
          final args = (call.arguments as Map?) ?? {};
          switch (call.method) {
            case 'recognize':
              expect(args['languages'], ['ja-JP', 'en-US'], reason: 'hints come from the Japanese region');
              return {
                'lines': [
                  {'text': 'ゲームの説明です。', 'confidence': 0.9, 'x': 0.1, 'y': 0.1, 'w': 0.5, 'h': 0.03},
                  {'text': '冒険が始まる', 'confidence': 0.9, 'x': 0.1, 'y': 0.135, 'w': 0.5, 'h': 0.03},
                ],
                'languages': args['languages'],
              };
            case 'detectLanguage':
              return {'language': 'ja', 'confidence': 0.97};
            case 'translate':
              if (translateFails.isNotEmpty) throw PlatformException(code: translateFails, message: 'native detail');
              final texts = (args['texts'] as List).cast<String>();
              return {'texts': [for (final t in texts) '[${args['target']}] $t'], 'source': 'ja'};
          }
          return null;
        },
      );
    });

    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(const MethodChannel('neostation/neo_box_reader'), null);
      NeoBoxReader.debugSupported = null;
      BoxTextService.rootForTesting = null;
      dir.deleteSync(recursive: true);
    });

    test('recognition and each translation are cached for later and offline reading', () async {
      final t = await BoxTextService.transcript(scan.path, scanRegion: 'jp');
      expect(t.language, 'ja');
      expect(t.document.units, ['ゲームの説明です。冒険が始まる']);
      expect(t.fromCache, isFalse);
      final fr = await BoxTextService.translate(t, 'fr');
      expect(fr.units.single, startsWith('[fr] '));
      expect(calls, ['recognize', 'detectLanguage', 'translate']);

      calls.clear();
      final again = await BoxTextService.transcript(scan.path, scanRegion: 'jp');
      expect(again.fromCache, isTrue);
      final frAgain = await BoxTextService.translate(again, 'fr');
      expect(frAgain.fromCache, isTrue);
      expect(calls, isEmpty, reason: 'no new recognition nor translation');

      final zhHant = await BoxTextService.translate(again, 'zh_Hant');
      expect(zhHant.units.single, startsWith('[zh-Hant] '));
      expect(calls, ['translate']);
    });

    test('a different scan never reuses the text of another one', () async {
      await BoxTextService.transcript(scan.path, scanRegion: 'jp');
      scan.writeAsBytesSync(List.generate(64, (i) => 255 - i));
      calls.clear();
      final t = await BoxTextService.transcript(scan.path, scanRegion: 'jp');
      expect(t.fromCache, isFalse);
      expect(calls.first, 'recognize');
    });

    test('translation errors keep their code for a translated message', () async {
      final t = await BoxTextService.transcript(scan.path, scanRegion: 'jp');
      translateFails = BoxReaderException.notInstalled;
      expect(
        () => BoxTextService.translate(t, 'ko'),
        throwsA(isA<BoxReaderException>().having((e) => e.code, 'code', 'not-installed')),
      );
    });

    test('language identifiers map to NeoStation codes', () {
      expect(NeoBoxReader.appCodeOf('zh-Hans'), 'zh');
      expect(NeoBoxReader.appCodeOf('zh-Hant'), 'zh_Hant');
      expect(NeoBoxReader.appCodeOf('zh-TW'), 'zh_Hant');
      expect(NeoBoxReader.appCodeOf('pt-BR'), 'pt');
      expect(NeoBoxReader.appCodeOf('ja-JP'), 'ja');
      expect(NeoBoxReader.appCodeOf('nl'), isNull);
      expect(NeoBoxReader.appleLanguages.keys, hasLength(12));
    });
  });
}
