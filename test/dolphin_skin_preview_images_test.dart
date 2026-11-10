import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/dolphin_skins.dart';
import 'package:path/path.dart' as p;

// Distinct, valid 1x1 RGBA PNGs: white background and dark complete preview.
final _backgroundPng = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGP4DwQACfsD/fteaysAAAAASUVORK5CYII=',
);
final _completePng = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGMQkdP4DwAB/gFaQ7UOogAAAABJRU5ErkJggg==',
);

Future<void> _writeInfo(Directory skin, Object? portraitPreview, {
  Object? landscapePreview,
  String background = 'background.png',
}) async {
  await File(p.join(skin.path, 'info.json')).writeAsString(jsonEncode({
    'name': 'Preview test',
    'identifier': 'org.rewindbox.test.preview',
    'gameTypeIdentifier': 'public.aoshuang.game.wii',
    'previewImages': {
      'portrait': portraitPreview,
      'landscape': ?landscapePreview,
    },
    'representations': {
      'iphone': {
        'edgeToEdge': {
          'portrait': {
            'assets': {'large': background},
          },
        },
      },
    },
  }));
}

void main() {
  late Directory root;
  late Directory skin;

  setUp(() async {
    root = await Directory.systemTemp.createTemp('dolphin-preview-');
    skin = await Directory(p.join(root.path, 'skin')).create();
    await Directory(p.join(skin.path, 'previews')).create();
    await File(p.join(skin.path, 'background.png')).writeAsBytes(_backgroundPng);
    await File(p.join(skin.path, 'previews', 'portrait.png')).writeAsBytes(_completePng);
  });

  tearDown(() async => root.delete(recursive: true));

  test('prefers the complete PNG to the distinct layout background', () async {
    await _writeInfo(skin, 'previews/portrait.png');

    final bytes = await DolphinSkins.previewImage(skin.path, 'portrait');

    expect(bytes, orderedEquals(_completePng));
    expect(bytes, isNot(orderedEquals(_backgroundPng)));
  });

  test('parent, absolute and backslash preview paths fall back to the background', () async {
    final outside = File(p.join(root.path, 'outside.png'));
    await outside.writeAsBytes(_completePng);
    for (final unsafePath in ['../outside.png', outside.path, r'previews\portrait.png']) {
      await _writeInfo(skin, unsafePath);

      expect(await DolphinSkins.previewImage(skin.path, 'portrait'), orderedEquals(_backgroundPng),
          reason: unsafePath);
    }
  });

  test('an oversized optional preview falls back to the background', () async {
    final oversized = await File(p.join(skin.path, 'previews', 'oversized.png')).open(mode: FileMode.write);
    try {
      await oversized.writeFrom(_completePng);
      await oversized.truncate(16 * 1024 * 1024 + 1);
    } finally {
      await oversized.close();
    }
    await _writeInfo(skin, 'previews/oversized.png');

    expect(await DolphinSkins.previewImage(skin.path, 'portrait'), orderedEquals(_backgroundPng));
  });

  test('a PNG extension with a JPEG signature falls back to the background', () async {
    await File(p.join(skin.path, 'previews', 'mismatch.png')).writeAsBytes([0xff, 0xd8, 0xff, 0xe0, 0x00]);
    await _writeInfo(skin, 'previews/mismatch.png');

    expect(await DolphinSkins.previewImage(skin.path, 'portrait'), orderedEquals(_backgroundPng));
  });

  test('a missing optional preview falls back to the background', () async {
    await _writeInfo(skin, 'previews/missing.png');

    expect(await DolphinSkins.previewImage(skin.path, 'portrait'), orderedEquals(_backgroundPng));
  });

  test('does not return an optional preview for an absent orientation layout', () async {
    await _writeInfo(skin, 'previews/portrait.png', landscapePreview: 'previews/portrait.png');

    expect(await DolphinSkins.previewImage(skin.path, 'landscape'), isNull);
  });

  test('an optional symlink escaping the skin falls back to the background', () async {
    final outside = File(p.join(root.path, 'outside.png'));
    await outside.writeAsBytes(_completePng);
    await Link(p.join(skin.path, 'previews', 'escape.png')).create(outside.path);
    await _writeInfo(skin, 'previews/escape.png');

    expect(await DolphinSkins.previewImage(skin.path, 'portrait'), orderedEquals(_backgroundPng));
  }, skip: !Platform.isLinux);

  test('an invalid optional preview preserves a PDF background as no bitmap', () async {
    await File(p.join(skin.path, 'background.pdf')).writeAsString('%PDF-1.4\n%%EOF\n');
    await _writeInfo(skin, 'previews/missing.png', background: 'background.pdf');

    expect(await DolphinSkins.previewImage(skin.path, 'portrait'), isNull);
  });
}
