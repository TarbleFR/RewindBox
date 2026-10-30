import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/services/melonx_internal_service.dart';
import 'package:neostation/widgets/melonx_hogwarts_graphics_options.dart';

void main() {
  Future<void> show(WidgetTester tester, Map<String, dynamic> settings) async {
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: StatefulBuilder(
      builder: (context, update) => MelonxHogwartsGraphicsOptions(
        settings: settings, onChanged: () => update(() {})),
    ))));
  }

  testWidgets('Hogwarts defaults preserve unrelated graphics choices', (tester) async {
    final settings = <String, dynamic>{'resolution': 0.75, 'asyncShaders': false};
    await show(tester, settings);
    expect(tester.widgetList<SwitchListTile>(find.byType(SwitchListTile)).every((s) => s.value), isTrue);
    expect(settings, {'resolution': 0.75, 'asyncShaders': false});
    await tester.tap(find.text('Group GPU query submissions'));
    await tester.pump();
    expect(settings, {'resolution': 0.75, 'asyncShaders': false, 'relaxQueryFlushing': false});
  });

  testWidgets('sync opt-out disables batching without silently reenabling it later', (tester) async {
    final settings = <String, dynamic>{};
    await show(tester, settings);
    await tester.tap(find.text('Synchronize occlusion results'));
    await tester.pump();
    expect(settings, {'occlusionQuerySync': false, 'relaxQueryFlushing': false});
    expect(tester.widgetList<SwitchListTile>(find.byType(SwitchListTile)).last.onChanged, isNull);
    await tester.tap(find.text('Synchronize occlusion results'));
    await tester.pump();
    expect(settings, {'occlusionQuerySync': true, 'relaxQueryFlushing': false});
  });

  testWidgets('saved opt-out remains visible when reopening the editor', (tester) async {
    await show(tester, {'occlusionQuerySync': false, 'relaxQueryFlushing': true});
    expect(tester.widgetList<SwitchListTile>(find.byType(SwitchListTile)).every((s) => !s.value), isTrue);
  });

  test('independent opt-outs survive empty preferences and container moves', () async {
    final dir = Directory.systemTemp.createTempSync('hogwarts-graphics-');
    final previous = MelonxInternalService.durableGraphicsFile;
    addTearDown(() { MelonxInternalService.durableGraphicsFile = previous; dir.deleteSync(recursive: true); });
    MelonxInternalService.durableGraphicsFile = () async => File('${dir.path}/graphics.json');
    SharedPreferences.setMockInitialValues({});
    const before = '/var/mobile/old/Documents/MeloNX/Hogwarts.xci';
    const after = '/var/mobile/new/Documents/MeloNX/Hogwarts.xci';
    final choices = <String, dynamic>{'occlusionQuerySync': true, 'relaxQueryFlushing': false, 'shaderCache': true};
    await MelonxInternalService.saveGraphics(before, choices);
    SharedPreferences.setMockInitialValues({});
    expect(await MelonxInternalService.graphicsForGame(after), choices);
  });
}
