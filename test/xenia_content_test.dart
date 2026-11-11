import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/xenia_content.dart';
import 'package:path/path.dart' as path;

import 'xenia_test_images.dart';

void main() {
  late Directory temp;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('xenia_content_');
  });

  tearDown(() async {
    await temp.delete(recursive: true);
  });

  test('file kinds: games, executables, profiles and touch layouts', () {
    expect(XeniaContent.kindForName('Halo.ISO'), XeniaContentKind.discImage);
    expect(XeniaContent.kindForName('a.zar'), XeniaContentKind.zarArchive);
    expect(XeniaContent.kindForName('default.xex'), XeniaContentKind.looseExecutable);
    expect(XeniaContent.kindForName('me.xeniosprofile'), XeniaContentKind.profile);
    expect(XeniaContent.kindForName('pad.toml'), XeniaContentKind.touchLayout);
    expect(XeniaContent.kindForName('game.cue'), XeniaContentKind.unsupported);
    // Only single-file games are imported; profiles and layouts never are.
    expect(XeniaContent.importExtensions, <String>{'iso', 'zar'});
    expect(XeniaContent.gameExtensions, containsAll(<String>['iso', 'zar', 'xex']));
    expect(XeniaContent.gameExtensions, isNot(contains('toml')));
    expect(XeniaContent.gameExtensions, isNot(contains('xeniosprofile')));
  });

  test('a disc image gives its title and media identity', () async {
    final image = await writeXboxImage(path.join(temp.path, 'game.iso'));
    final identity = await XeniaContent.inspectDiscImage(image);
    expect(identity.partitionOffset, 0);
    expect(identity.titleId, '4D5307E6');
    expect(identity.mediaId, '11223344');
    expect(identity.discNumber, 1);
    expect(identity.discCount, 1);
  });

  test('every partition offset the engine probes is found', () async {
    for (final offset in XeniaContent.partitionOffsets) {
      final image = await writeXboxImage(
        path.join(temp.path, 'p$offset.iso'),
        partitionOffset: offset,
        titleId: 0x41560000 + offset % 0xFFFF,
        extraRootFiles: const <String>['media', 'nxeart'],
      );
      final identity = await XeniaContent.inspectDiscImage(image);
      expect(identity.partitionOffset, offset, reason: '$offset');
      expect(identity.titleId, isNotNull, reason: '$offset');
    }
  });

  test('a file that is not an Xbox image is refused', () async {
    final other = File(path.join(temp.path, 'not.iso'));
    await other.writeAsBytes(List<int>.filled(200000, 7));
    expect(
      () => XeniaContent.inspectDiscImage(other),
      throwsA(isA<XeniaContentException>().having((e) => e.error, 'error', XeniaContentError.notXboxImage)),
    );
  });

  test('an image cut before its executable is reported incomplete', () async {
    final image = await writeXboxImage(path.join(temp.path, 'cut.iso'), truncateExecutable: true);
    expect(
      () => XeniaContent.inspectDiscImage(image),
      throwsA(isA<XeniaContentException>().having((e) => e.error, 'error', XeniaContentError.truncated)),
    );
  });

  test('title IDs are normalized and placeholders rejected', () {
    expect(XeniaContent.normalizeTitleId(' 4d5307e6 '), '4D5307E6');
    expect(XeniaContent.normalizeTitleId('00000000'), isNull);
    expect(XeniaContent.normalizeTitleId('FFFFFFFF'), isNull);
    expect(XeniaContent.normalizeTitleId('BLES01234'), isNull);
    expect(XeniaContent.normalizeTitleId(null), isNull);
  });
}
