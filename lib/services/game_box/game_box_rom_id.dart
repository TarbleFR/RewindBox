import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;

import 'package:neostation/models/game_model.dart';

/// The id a game's own file gives GameTDB (docs/game-box-3d.md § 25): read
/// in the first bytes of the ROM, never guessed from its title.
///
/// | Platform | Id | Where |
/// |---|---|---|
/// | Wii, GameCube | 6 characters (`RSBP01`) | disc header: ISO/GCM at 0, WBFS at 0x200, RVZ/WIA at 0x58, CISO at 0x8000, TGC at its header size |
/// | Wii U | 6 characters (`AMKP01`) | `meta/meta.xml` of an extracted title (product and company codes); the product code of a WUD/WUX disc (`WUP-P-AMKP`, 4 characters) |
/// | DS | 4 characters (`AMCP`) | cartridge header at 0x0C |
/// | 3DS | 4 characters (`AMKP`) | product code of the NCCH (`CTR-P-AMKP`): .cxi at 0x150, .3ds/.cci in partition 0, a decrypted .cia in its first content |
///
/// Compressed formats whose header is not plain (GCZ, NKit in GCZ, an
/// encrypted CIA) give no id: the file name and the title are tried then.
class GameBoxRomId {
  GameBoxRomId._();

  static final RegExp _six = RegExp(r'^[A-Z0-9]{6}$');
  static final RegExp _four = RegExp(r'^[A-Z0-9]{4}$');

  static final Map<String, (int, String?)> _cache = {};

  /// Bytes read at most from one place of a file.
  static const int _chunk = 0x400;

  @visibleForTesting
  static void clearCache() => _cache.clear();

  /// GameTDB id of [game] on [platform] (`wii`, `wiiu`, `ds`, `3ds`): the
  /// library's own title id when it has the right form, else the ROM's
  /// header, else an id written in the file name (`[RSBP01]`).
  static Future<String?> forGame(GameModel game, String platform) async {
    final own = game.titleId?.trim().toUpperCase();
    if (own != null && isId(platform, own)) return own;
    final path = game.romPath;
    if (path != null && path.isNotEmpty && !path.contains('://')) {
      final fromFile = await read(path, platform);
      if (fromFile != null) return fromFile;
    }
    return fromFileName(game.romname, platform);
  }

  /// Whether [id] has the form of a GameTDB id of [platform]. A Wii U id
  /// read from a disc has only its 4-character product code.
  static bool isId(String platform, String id) => switch (platform) {
        'wii' => _six.hasMatch(id),
        'wiiu' => _six.hasMatch(id) || _four.hasMatch(id),
        'ds' || '3ds' || 'gba' => _four.hasMatch(id),
        _ => false,
      };

  /// An id in brackets or parentheses in a file name (`Brawl [RSBP01].iso`):
  /// it starts with a letter and its fourth character is a region letter.
  static String? fromFileName(String name, String platform) {
    final length = platform == 'wii' || platform == 'wiiu' ? 6 : 4;
    for (final m in RegExp('[\\[(]([A-Z0-9]{$length})[\\])]').allMatches(name)) {
      final id = m.group(1)!;
      if (!RegExp(r'^[A-Z]').hasMatch(id) || regionsOf(id).isEmpty) continue;
      return id;
    }
    return null;
  }

  /// Id read from the file at [path] (a file or an extracted Wii U folder).
  static Future<String?> read(String path, String platform) async {
    try {
      final type = await FileSystemEntity.type(path);
      if (type == FileSystemEntityType.directory) {
        return platform == 'wiiu' ? await _wiiuFolder(Directory(path)) : null;
      }
      if (type != FileSystemEntityType.file) return null;
      final file = File(path);
      final stat = await file.stat();
      final key = '$platform|$path';
      final cached = _cache[key];
      if (cached != null && cached.$1 == stat.size) return cached.$2;
      String? id;
      final ext = p.extension(path).toLowerCase();
      if (platform == 'wiiu' && (ext == '.rpx' || ext == '.xml')) {
        // A file inside an extracted title: code/x.rpx or meta/meta.xml.
        id = await _wiiuFolder(file.parent.parent);
      } else {
        final raf = await file.open();
        try {
          Future<Uint8List> at(int offset, int length) async {
            if (offset < 0 || offset >= stat.size) return Uint8List(0);
            await raf.setPosition(offset);
            return raf.read(length);
          }

          id = switch (platform) {
            'wii' => await discId(at),
            'ds' => dsId(await at(0, 0x20)),
            'gba' => gbaId(await at(0, 0xC0)),
            '3ds' => await ctrId(at),
            'wiiu' => await wiiuDiscId(at),
            _ => null,
          };
        } finally {
          await raf.close();
        }
      }
      _cache[key] = (stat.size, id);
      return id;
    } catch (_) {
      return null;
    }
  }

  static String? _ascii(Uint8List b, int offset, int length) {
    if (b.length < offset + length) return null;
    final s = String.fromCharCodes(b.sublist(offset, offset + length));
    return s;
  }

  static int _be32(Uint8List b, int o) => (b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3];
  static int _le32(Uint8List b, int o) => b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24);
  static int _le64(Uint8List b, int o) => _le32(b, o) + _le32(b, o + 4) * 0x100000000;

  /// GameCube disc magic at 0x1C, Wii disc magic at 0x18 of a disc header.
  static bool _discHeader(Uint8List h) =>
      h.length >= 0x20 && (_be32(h, 0x1C) == 0xC2339F3D || _be32(h, 0x18) == 0x5D1C9EA3);

  static String? _idOfHeader(Uint8List h) {
    if (!_discHeader(h)) return null;
    final id = _ascii(h, 0, 6);
    return id != null && _six.hasMatch(id) ? id : null;
  }

  /// Wii or GameCube disc id, whatever the container.
  static Future<String?> discId(Future<Uint8List> Function(int offset, int length) at) async {
    final head = await at(0, _chunk);
    if (head.length < 0x20) return null;
    final magic = _ascii(head, 0, 4);
    if (magic == 'WBFS') return _idOfHeader(await at(0x200, 0x20));
    if (magic == 'RVZ\x01' || magic == 'WIA\x01') return _idOfHeader(await at(0x58, 0x20));
    if (magic == 'CISO') return _idOfHeader(await at(0x8000, 0x20));
    if (_be32(head, 0) == 0xAE0F38A2) {
      // TGC: the embedded GameCube image starts at the header size.
      return _idOfHeader(await at(_be32(head, 8), 0x20));
    }
    return _idOfHeader(head);
  }

  /// DS cartridge game code (header 0x0C); its title (0x00, 12 characters)
  /// must be printable, so that another file is not misread.
  static String? dsId(Uint8List h) {
    if (h.length < 0x10) return null;
    for (var i = 0; i < 12; i++) {
      final c = h[i];
      if (c != 0 && (c < 0x20 || c > 0x7E)) return null;
    }
    final id = _ascii(h, 0x0C, 4);
    return id != null && _four.hasMatch(id) ? id : null;
  }

  /// Game Boy Advance game code (header 0xAC), checked by the header's
  /// fixed value 0x96 at 0xB2 (used to find a French manual, § 26).
  static String? gbaId(Uint8List h) {
    if (h.length < 0xB3 || h[0xB2] != 0x96) return null;
    final id = _ascii(h, 0xAC, 4);
    return id != null && _four.hasMatch(id) ? id : null;
  }

  /// 3DS product code core (`CTR-P-AMKP` → `AMKP`) of an NCCH.
  static String? _productOfNcch(Uint8List h) {
    if (h.length < 0x160 || _ascii(h, 0x100, 4) != 'NCCH') return null;
    final code = _ascii(h, 0x150, 16)?.replaceAll('\x00', '').trim() ?? '';
    final m = RegExp(r'^(?:CTR|KTR)-[A-Z]-([A-Z0-9]{4})$').firstMatch(code);
    return m?.group(1);
  }

  static int _align(int v, int a) => (v + a - 1) ~/ a * a;

  /// 3DS id of a .cxi/.app (NCCH), a .3ds/.cci (NCSD) or a decrypted .cia.
  static Future<String?> ctrId(Future<Uint8List> Function(int offset, int length) at) async {
    final head = await at(0, _chunk);
    if (head.length < 0x200) return null;
    final ncch = _productOfNcch(head);
    if (ncch != null) return ncch;
    if (_ascii(head, 0x100, 4) == 'NCSD') {
      final offset = _le32(head, 0x120) * 0x200;
      return _productOfNcch(await at(offset, 0x200));
    }
    // CIA: header, certificates, ticket and TMD, each aligned to 64 bytes,
    // then the first content (an NCCH when it is not encrypted).
    final headerSize = _le32(head, 0);
    if (headerSize == 0x2020) {
      final cert = _le32(head, 0x08), ticket = _le32(head, 0x0C), tmd = _le32(head, 0x10);
      final content = _le64(head, 0x18);
      if (content <= 0) return null;
      final offset = _align(headerSize, 64) + _align(cert, 64) + _align(ticket, 64) + _align(tmd, 64);
      return _productOfNcch(await at(offset, 0x200));
    }
    return null;
  }

  /// Product code core of a Wii U disc (`WUP-P-AMKP` → `AMKP`): a WUD
  /// image, or the first sector of a WUX (its compressed form).
  static Future<String?> wiiuDiscId(Future<Uint8List> Function(int offset, int length) at) async {
    String? product(Uint8List b) {
      final m = RegExp(r'^WUP-[A-Z]-([A-Z0-9]{4})').firstMatch(_ascii(b, 0, 10) ?? '');
      return m?.group(1);
    }

    final head = await at(0, 0x20);
    if (head.length < 0x20) return null;
    if (_ascii(head, 0, 4) == 'WUX0' && _le32(head, 4) == 0x1099D02E) {
      final sectorSize = _le32(head, 8);
      final size = _le64(head, 0x10);
      if (sectorSize <= 0 || size <= 0) return null;
      final sectors = (size + sectorSize - 1) ~/ sectorSize;
      final index = await at(0x20, 4);
      if (index.length < 4) return null;
      final dataStart = _align(0x20 + sectors * 4, sectorSize);
      return product(await at(dataStart + _le32(index, 0) * sectorSize, 0x20));
    }
    return product(head);
  }

  /// Id of an extracted Wii U title (code/, content/, meta/): product code
  /// and the last two digits of the company code of `meta/meta.xml`.
  static Future<String?> _wiiuFolder(Directory dir) async {
    final meta = File(p.join(dir.path, 'meta', 'meta.xml'));
    if (!await meta.exists()) return null;
    return wiiuMetaId(utf8.decode(await meta.readAsBytes(), allowMalformed: true));
  }

  /// Id from the text of a Wii U `meta.xml`.
  static String? wiiuMetaId(String xml) {
    final product = RegExp(r'<product_code[^>]*>\s*WUP-[A-Z]-([A-Z0-9]{4})\s*<').firstMatch(xml)?.group(1);
    if (product == null) return null;
    final company = RegExp(r'<company_code[^>]*>\s*([0-9A-Z]{2,4})\s*<').firstMatch(xml)?.group(1);
    if (company == null || company.length < 2) return product;
    return '$product${company.substring(company.length - 2)}';
  }

  /// Regions of an id's region letter (the fourth character): P Europe,
  /// E America, J Japan, F France, D Germany… (ScreenScraper's codes).
  static List<String> regionsOf(String id) {
    if (id.length < 4) return const [];
    return switch (id[3]) {
      'P' || 'X' || 'Y' || 'Z' || 'V' => const ['eu'],
      'E' => const ['us'],
      'J' => const ['jp'],
      'K' => const ['kr'],
      'F' => const ['fr'],
      'D' => const ['de'],
      'S' => const ['sp'],
      'I' => const ['it'],
      'H' => const ['nl'],
      'U' => const ['au'],
      'W' => const ['tw'],
      'C' => const ['cn'],
      'A' => const ['wor'],
      _ => const [],
    };
  }
}
