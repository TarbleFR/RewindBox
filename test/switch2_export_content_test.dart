import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' show Locale;

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/switch2_export_content.dart';
import 'package:path/path.dart' as path;

/// Synthetic NPDM: META magic, ACI0 at [aciOffset] with [programId] (u64 LE) at ACI0 + 0x10.
Uint8List npdm({int programId = 0x0100ABCD00001000, int aciOffset = 0x80, int length = 0x100}) {
  final bytes = Uint8List(length);
  final data = ByteData.sublistView(bytes);
  bytes.setRange(0, 4, 'META'.codeUnits);
  data.setUint32(0x70, aciOffset, Endian.little);
  data.setUint32(0x74, 0x40, Endian.little);
  bytes.setRange(aciOffset, aciOffset + 4, 'ACI0'.codeUnits);
  data.setUint64(aciOffset + 0x10, programId, Endian.little);
  return bytes;
}

/// Synthetic NACP: [titles] by language index (name, publisher), display version at 0x3060.
Uint8List nacp({Map<int, (String, String)> titles = const {}, String version = '1.2.3'}) {
  final bytes = Uint8List(Switch2ExportContent.nacpSize);
  titles.forEach((language, entry) {
    final start = language * 0x300;
    final name = utf8.encode(entry.$1);
    bytes.setRange(start, start + name.length, name);
    final publisher = utf8.encode(entry.$2);
    bytes.setRange(start + 0x200, start + 0x200 + publisher.length, publisher);
  });
  final v = version.codeUnits;
  bytes.setRange(0x3060, 0x3060 + v.length, v);
  return bytes;
}

void main() {
  late Directory temp;

  setUp(() => temp = Directory.systemTemp.createTempSync('switch2_content_'));
  tearDown(() => temp.deleteSync(recursive: true));

  String write(String relative, List<int> bytes) {
    final file = File(path.join(temp.path, relative))..createSync(recursive: true);
    file.writeAsBytesSync(bytes);
    return file.path;
  }

  group('NPDM', () {
    test('program id is 16 lowercase hex digits', () {
      expect(Switch2ExportContent.programIdFromNpdm(npdm()), '0100abcd00001000');
      expect(Switch2ExportContent.programIdFromNpdm(npdm(programId: 0x1, aciOffset: 0xC0, length: 0x120)), '0000000000000001');
    });

    test('rejects a missing META magic, a bad ACI0 and truncation', () {
      final noMeta = npdm()..[0] = 0x58;
      expect(Switch2ExportContent.programIdFromNpdm(noMeta), isNull);
      final noAci = npdm()..[0x80] = 0x58;
      expect(Switch2ExportContent.programIdFromNpdm(noAci), isNull);
      expect(Switch2ExportContent.programIdFromNpdm(Uint8List(0x20)), isNull);
      // A whole NPDM cut inside its ACI0 header (program id at 0x90..0x98): the helper cannot write past the end.
      expect(Switch2ExportContent.programIdFromNpdm(Uint8List.fromList(npdm().sublist(0, 0x90))), isNull);
    });

    test('titleId reads the file and refuses an oversized one', () {
      expect(Switch2ExportContent.titleId(write('a/base/exefs/main.npdm', npdm())), '0100abcd00001000');
      final big = npdm(length: Switch2ExportContent.npdmLimit + 1);
      expect(Switch2ExportContent.titleId(write('b/base/exefs/main.npdm', big)), isNull);
      expect(Switch2ExportContent.titleId(path.join(temp.path, 'missing.npdm')), isNull);
    });
  });

  group('library entry', () {
    test('only <export>/base/exefs/main.npdm counts', () {
      expect(Switch2ExportContent.isLibraryEntry('/g/Game/base/exefs/main.npdm'), isTrue);
      expect(Switch2ExportContent.isLibraryEntry('/g/Game/Base/ExeFS/Main.NPDM'), isTrue);
      expect(Switch2ExportContent.isLibraryEntry('/g/Game/updates/1/exefs/main.npdm'), isFalse);
      expect(Switch2ExportContent.isLibraryEntry('/g/Game/updates/1/base/exefs/main.npdm'), isFalse);
      expect(Switch2ExportContent.isLibraryEntry('/g/Game/dlc/2/base/exefs/main.npdm'), isFalse);
      expect(Switch2ExportContent.isLibraryEntry('/g/Game/base/romfs/main.npdm'), isFalse);
      expect(Switch2ExportContent.isLibraryEntry('/g/Game/exefs/main.npdm'), isFalse);
      expect(Switch2ExportContent.isLibraryEntry('base/exefs/main.npdm'), isFalse);
      expect(Switch2ExportContent.isLibraryEntry('/g/Game/base/exefs/other.npdm'), isFalse);
    });

    test('exportFolder is three levels above the NPDM', () {
      expect(Switch2ExportContent.exportFolder('/g/Game/base/exefs/main.npdm'), '/g/Game');
    });

    test('libraryFileName: <title id>.npdm, else folder name and a path digest, never main.npdm', () {
      expect(
        Switch2ExportContent.libraryFileName('/g/Game/base/exefs/main.npdm', '0100ABCDEF012000'),
        '0100abcdef012000.npdm',
      );
      final a = Switch2ExportContent.libraryFileName('/g/Game/base/exefs/main.npdm', null);
      final b = Switch2ExportContent.libraryFileName('/h/Game/base/exefs/main.npdm', null);
      expect(a, matches(RegExp(r'^Game-[0-9a-f]{8}\.npdm$')));
      expect(b, matches(RegExp(r'^Game-[0-9a-f]{8}\.npdm$')));
      expect(a, isNot(b));
      expect(Switch2ExportContent.libraryFileName('/g/Game/base/exefs/main.npdm', null), a);
      expect(Switch2ExportContent.libraryFileName('/g/Game/base/exefs/main.npdm', 'not-an-id'), a);
      expect(
        Switch2ExportContent.libraryFileName('/g/Jeu: été?/base/exefs/main.npdm', ''),
        matches(RegExp(r'^Jeu_ _t__-[0-9a-f]{8}\.npdm$')),
      );
    });
  });

  group('NACP', () {
    test('title entries, language order and display version', () {
      final bytes = nacp(titles: {0: ('English Name', 'Pub'), 3: ('Nom Français', 'Éditeur'), 14: ('简体名', '')});
      expect(Switch2ExportContent.titleEntry(bytes, 3), (name: 'Nom Français', publisher: 'Éditeur'));
      expect(Switch2ExportContent.titleEntry(bytes, 4), (name: '', publisher: ''));
      expect(Switch2ExportContent.displayVersion(bytes), '1.2.3');
      expect(Switch2ExportContent.bestTitle(bytes, const Locale('fr'))?.name, 'Nom Français');
      expect(Switch2ExportContent.bestTitle(bytes, const Locale('zh'))?.name, '简体名');
      // No German entry: American English.
      expect(Switch2ExportContent.bestTitle(bytes, const Locale('de'))?.name, 'English Name');
      expect(Switch2ExportContent.bestTitle(nacp(), const Locale('en')), isNull);
    });

    test('language order follows the Switch table', () {
      expect(Switch2ExportContent.languageOrder(const Locale('en', 'GB')).first, 1);
      expect(Switch2ExportContent.languageOrder(const Locale('en', 'US')).first, 0);
      expect(Switch2ExportContent.languageOrder(const Locale('ja')).first, 2);
      expect(Switch2ExportContent.languageOrder(const Locale('fr', 'CA')).first, 9);
      expect(Switch2ExportContent.languageOrder(const Locale('es', 'MX')).first, 5);
      expect(Switch2ExportContent.languageOrder(const Locale('es', 'ES')).first, 6);
      expect(Switch2ExportContent.languageOrder(const Locale('pt', 'BR')).first, 15);
      expect(Switch2ExportContent.languageOrder(const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')).first, 13);
      expect(Switch2ExportContent.languageOrder(const Locale('xx')).first, 0);
      expect(Switch2ExportContent.languageOrder(const Locale('de')), hasLength(16));
    });
  });

  group('control lookup', () {
    test('base control.nacp, one level below, never in romfs or exefs', () {
      write('G/base/exefs/main.npdm', npdm());
      write('G/base/romfs/control.nacp', nacp());
      write('G/base/exefs/control.nacp', nacp());
      expect(Switch2ExportContent.findControl(path.join(temp.path, 'G')), isNull);
      write('G/base/control/control.nacp', nacp(titles: {0: ('Below', '')}));
      final found = Switch2ExportContent.findControl(path.join(temp.path, 'G'));
      expect(found, isNotNull);
      expect(path.basename(found!.directory), 'control');
      expect(Switch2ExportContent.titleEntry(found.nacp, 0).name, 'Below');
    });

    test('a control.nacp that is not exactly 0x4000 bytes is skipped', () {
      write('G/base/control.nacp', Uint8List(0x3FFF));
      expect(Switch2ExportContent.findControl(path.join(temp.path, 'G')), isNull);
      write('G/base/control.nacp', Uint8List(0x4001));
      expect(Switch2ExportContent.findControl(path.join(temp.path, 'G')), isNull);
    });

    test('the newest update folder with one wins over base', () {
      write('G/base/control.nacp', nacp(titles: {0: ('Base', '')}));
      write('G/updates/2/control.nacp', nacp(titles: {0: ('Old update', '')}));
      write('G/updates/10/control.nacp', nacp(titles: {0: ('New update', '')}));
      write('G/updates/readme/control.nacp', nacp(titles: {0: ('Not numeric', '')}));
      final exportDir = path.join(temp.path, 'G');
      expect(Switch2ExportContent.titleEntry(Switch2ExportContent.findControl(exportDir)!.nacp, 0).name, 'New update');
      File(path.join(exportDir, 'updates', '10', 'control.nacp')).deleteSync();
      // The newest update has none: base is next (the C port reads the newest update only).
      expect(Switch2ExportContent.titleEntry(Switch2ExportContent.findControl(exportDir)!.nacp, 0).name, 'Base');
    });

    test('libraryTitle: NACP title, else the export folder name', () {
      final npdmPath = write('My Export/base/exefs/main.npdm', npdm());
      expect(Switch2ExportContent.libraryTitle(npdmPath, locale: const Locale('en')), 'My Export');
      write('My Export/base/control.nacp', nacp(titles: {0: ('Mario Kart World', 'Nintendo')}));
      expect(Switch2ExportContent.libraryTitle(npdmPath, locale: const Locale('en')), 'Mario Kart World');
    });
  });

  group('icon', () {
    test('the best language icon next to the NACP, else the first by name', () {
      write('G/base/control.nacp', nacp());
      write('G/base/icon_AmericanEnglish.dat', [1]);
      write('G/base/icon_French.dat', [2]);
      final exportDir = path.join(temp.path, 'G');
      expect(path.basename(Switch2ExportContent.iconFile(exportDir, locale: const Locale('fr'))!.path), 'icon_French.dat');
      expect(path.basename(Switch2ExportContent.iconFile(exportDir, locale: const Locale('de'))!.path), 'icon_AmericanEnglish.dat');
      File(path.join(exportDir, 'base', 'icon_AmericanEnglish.dat')).deleteSync();
      expect(path.basename(Switch2ExportContent.iconFile(exportDir, locale: const Locale('de'))!.path), 'icon_French.dat');
    });

    test('none without control, and an oversized icon is refused', () {
      expect(Switch2ExportContent.iconFile(path.join(temp.path, 'none')), isNull);
      write('H/base/control.nacp', nacp());
      write('H/base/icon_AmericanEnglish.dat', Uint8List(Switch2ExportContent.iconLimit + 1));
      expect(Switch2ExportContent.iconFile(path.join(temp.path, 'H'), locale: const Locale('en')), isNull);
    });
  });
}
