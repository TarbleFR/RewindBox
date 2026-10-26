// Build 554: a PS3 disc image of the library folder (roms/ps3) is read where
// it is, before RPCS3 installs it: PS3_GAME/PARAM.SFO from its ISO 9660 tree
// (the title ID tells whether RPCS3 already holds the disc), the disc key
// beside it, and a same-image check when the title ID cannot be read.
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/rpcs3_disc_image.dart';
import 'package:path/path.dart' as path;

import 'ps3_disc_image_builder.dart';

void main() {
  late Directory temp;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('rpcs3-disc-image-test');
  });

  tearDown(() async {
    await temp.delete(recursive: true);
  });

  Future<String> write(String name, Uint8List bytes) async {
    final file = File(path.join(temp.path, name));
    await file.writeAsBytes(bytes, flush: true);
    return file.path;
  }

  group('readIdentity', () {
    test(
      'reads PS3_GAME/PARAM.SFO past the padding of a directory sector',
      () async {
        final iso = await write(
          'Call of Duty - Black Ops (USA) (En,Fr).iso',
          Ps3DiscImageBuilder.image(),
        );
        final identity = await Rpcs3DiscImage.readIdentity(iso);
        expect(identity, isNotNull);
        expect(identity!.titleId, 'BLUS30591');
        expect(identity.title, 'Call of Duty®: Black Ops');
        expect(identity.category, 'DG');
      },
    );

    test('names are matched without case, version or trailing dot', () async {
      final iso = await write(
        'lower.iso',
        Ps3DiscImageBuilder.image(
          gameDirectory: 'ps3_game',
          paramSfoName: 'param.sfo.;1',
          titleId: 'bles01658',
        ),
      );
      final identity = await Rpcs3DiscImage.readIdentity(iso);
      expect(identity?.titleId, 'BLES01658');
    });

    test('an image without PS3_GAME is not a PS3 game disc', () async {
      final iso = await write(
        'nogame.iso',
        Ps3DiscImageBuilder.image(gameDirectory: null),
      );
      expect(await Rpcs3DiscImage.readIdentity(iso), isNull);
    });

    test(
      'an unreadable descriptor (encrypted region) gives no identity',
      () async {
        final random = Random(7);
        final noise = Uint8List.fromList(
          List<int>.generate(1024, (_) => random.nextInt(256)),
        );
        final iso = await write(
          'encrypted.iso',
          Ps3DiscImageBuilder.image(paramSfoBytes: noise),
        );
        expect(await Rpcs3DiscImage.readIdentity(iso), isNull);
      },
    );

    test('a descriptor without a valid title ID gives no identity', () async {
      final iso = await write(
        'badid.iso',
        Ps3DiscImageBuilder.image(titleId: '../../x'),
      );
      expect(await Rpcs3DiscImage.readIdentity(iso), isNull);
    });

    test('not an ISO 9660 image, short files and missing files', () async {
      final random = await write(
        'random.iso',
        Uint8List.fromList(List<int>.filled(40 * 2048, 0x5a)),
      );
      final short = await write('short.iso', Uint8List(4096));
      expect(await Rpcs3DiscImage.readIdentity(random), isNull);
      expect(await Rpcs3DiscImage.readIdentity(short), isNull);
      expect(
        await Rpcs3DiscImage.readIdentity(path.join(temp.path, 'none.iso')),
        isNull,
      );
    });

    test('a directory extent pointing past the image is refused', () async {
      final bytes = Ps3DiscImageBuilder.image();
      // Root directory record of the primary descriptor: extent sector.
      ByteData.sublistView(
        bytes,
      ).setUint32(16 * 2048 + 156 + 2, 900000, Endian.little);
      final iso = await write('outside.iso', bytes);
      expect(await Rpcs3DiscImage.readIdentity(iso), isNull);
    });
  });

  group('findDiscKey', () {
    test('finds the .dkey or .key of the same name in any case', () async {
      final iso = await write('Game (USA).iso', Uint8List(16));
      expect(await Rpcs3DiscImage.findDiscKey(iso), isNull);
      final key = await write('game (usa).KEY', Uint8List(16));
      expect(await Rpcs3DiscImage.findDiscKey(iso), key);
      final dkey = await write('Game (USA).dkey', Uint8List(32));
      expect(
        await Rpcs3DiscImage.findDiscKey(iso),
        dkey,
        reason: '.dkey first',
      );
    });

    test('ignores the keys of other discs', () async {
      final iso = await write('Game (USA).iso', Uint8List(16));
      await write('Game (Europe).dkey', Uint8List(32));
      await write('Game (USA) (Disc 2).key', Uint8List(16));
      expect(await Rpcs3DiscImage.findDiscKey(iso), isNull);
    });
  });

  group('sameImage', () {
    test('equal size and first mebibyte', () async {
      final a = await write('a.iso', Ps3DiscImageBuilder.image());
      final b = await write('b.iso', Ps3DiscImageBuilder.image());
      final other = await write('c.iso', Ps3DiscImageBuilder.image(fill: 3));
      final longer = await write(
        'd.iso',
        Uint8List.fromList([...Ps3DiscImageBuilder.image(), 0]),
      );
      expect(await Rpcs3DiscImage.sameImage(a, b), isTrue);
      expect(await Rpcs3DiscImage.sameImage(a, other), isFalse);
      expect(await Rpcs3DiscImage.sameImage(a, longer), isFalse);
      expect(
        await Rpcs3DiscImage.sameImage(a, path.join(temp.path, 'none.iso')),
        isFalse,
      );
    });
  });

  test('only .iso rows are disc images of the PS3 system', () {
    expect(Rpcs3DiscImage.isDiscImagePath('/roms/ps3/Game.ISO'), isTrue);
    expect(Rpcs3DiscImage.isDiscImagePath('/roms/ps3/Game.iso'), isTrue);
    expect(Rpcs3DiscImage.isDiscImagePath('/roms/ps3/Game.pkg'), isFalse);
    expect(
      Rpcs3DiscImage.isDiscImagePath('rpcs3-library://game?title-id=BLUS30591'),
      isFalse,
    );
    expect(Rpcs3DiscImage.isDiscImagePath(null), isFalse);
  });
}
