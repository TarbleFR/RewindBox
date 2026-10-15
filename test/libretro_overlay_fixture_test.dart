import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/libretro_overlay_converter.dart';

void main() {
  for (final fixture in <String, String>{'flat-psx': 'gamepads/flat/psx.cfg', 'rgpad-modern': 'gamepads/rgpad/rgpad_modern.cfg'}.entries) {
    test('original ${fixture.key} reconstructs every orientation and exports the gameplay layout', () async {
      final cfg = await File('test/fixtures/libretro_overlays/${fixture.value.split('/').last}').readAsString();
      final result = LibretroOverlayConverter.convert(cfg, cfgPath: fixture.value, console: 'psx',
          name: fixture.key, identifier: 'org.neostation.test.${fixture.key}');
      expect(result.problems, isEmpty);
      expect(result.orientations, containsAll(['portrait', 'landscape']));
      expect(result.files.length, greaterThan(8));
      final source = jsonDecode(await File('assets/data/libretro_skin_overlays.json').readAsString()) as Map;
      final entry = (source['entries'] as List).cast<Map>().singleWhere((e) => e['path'] == fixture.value);
      for (final file in result.files.values) {
        expect(entry['files'] as List, contains(file), reason: 'every drawn asset must be available');
      }
      final representations = (result.info['representations'] as Map)['iphone'] as Map;
      final layouts = representations['edgeToEdge'] as Map;
      for (final layout in layouts.values.cast<Map>()) {
        expect((layout['items'] as List).where((item) => (item as Map)['asset'] != null).length, greaterThan(8));
      }
      // Export the actual Dart conversion for the UIKit preview integration probe.
      final output = Platform.environment['NEOSTATION_OVERLAY_FIXTURES'];
      if (output != null) {
        final directory = await Directory('$output/${fixture.key}').create(recursive: true);
        await File('${directory.path}/info.json').writeAsString(jsonEncode(result.info));
        await File('${directory.path}/resources.json').writeAsString(jsonEncode(result.files));
      }
    });
  }
}
