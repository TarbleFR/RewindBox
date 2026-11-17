import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:neostation/services/nextendo/nextendo_bcat.dart';
import 'package:neostation/services/nextendo/nextendo_catalog.dart';
import 'package:neostation/services/nextendo/nextendo_ed25519.dart';
import 'package:neostation/services/nextendo/nextendo_online_play.dart';
import 'package:neostation/services/nextendo/nextendo_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

// Nextendo's game data (integration guide): the Ed25519-signed game catalog with each game's exact versions, the BCAT
// delivery data served from a folder, and the launch request that carries them. test/fixtures/nextendo/game-catalog.json
// is the public catalog of 17 November 2026 (revision 23), unchanged.
List<int> _hex(String text) => [for (var i = 0; i < text.length; i += 2) int.parse(text.substring(i, i + 2), radix: 16)];

List<int> _zip(Map<String, List<int>> files) {
  final archive = Archive();
  files.forEach((name, content) => archive.addFile(ArchiveFile(name, content.length, content)));
  return ZipEncoder().encode(archive);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Ed25519 (RFC 8032, section 7.1)', () {
    final vectors = [
      ('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
          'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'),
      ('3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
          '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00'),
      ('fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025', 'af82',
          '6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a'),
    ];
    for (final (key, message, signature) in vectors) {
      test('vector of message "$message" verifies, and only unchanged', () {
        expect(NextendoEd25519.verify(_hex(key), _hex(message), _hex(signature)), isTrue);
        expect(NextendoEd25519.verify(_hex(key), [..._hex(message), 0], _hex(signature)), isFalse);
        final bad = _hex(signature)..[10] ^= 1;
        expect(NextendoEd25519.verify(_hex(key), _hex(message), bad), isFalse);
      });
    }
    test('wrong lengths and a scalar of L or more are refused', () {
      expect(NextendoEd25519.verify(List.filled(31, 0), const [], List.filled(64, 0)), isFalse);
      expect(NextendoEd25519.verify(_hex(vectors[0].$1), const [], List.filled(63, 0)), isFalse);
      final high = _hex(vectors[0].$3)..fillRange(32, 64, 0xff);
      expect(NextendoEd25519.verify(_hex(vectors[0].$1), const [], high), isFalse);
    });
  });

  group('signed game catalog', () {
    final body = File('test/fixtures/nextendo/game-catalog.json').readAsStringSync();

    test('the live catalog verifies and lists Smash Bros. Ultimate at 13.0.5', () {
      final catalog = NextendoCatalog.parse(body)!;
      expect(catalog.revision, 23);
      final smash = catalog.forTitle('01006A800016E000')!;
      expect(smash.name, 'Super Smash Bros. Ultimate');
      expect(smash.accepted, ['13.0.5']);
      expect(smash.needsNplnPatches, isFalse);
      expect(catalog.forTitle('0100c2500fc20000')!.needsNplnPatches, isTrue); // Splatoon 3
      expect(catalog.forTitle('0123456789abcdef'), isNull);
    });

    test('a changed payload, another key id or another document type is refused', () {
      final envelope = Map<String, dynamic>.from(jsonDecode(body) as Map);
      final payload = utf8.decode(base64.decode(envelope['payload'] as String));
      final changed = {...envelope, 'payload': base64.encode(utf8.encode(payload.replaceFirst('13.0.5', '13.0.6')))};
      expect(NextendoCatalog.parse(jsonEncode(changed)), isNull);
      expect(NextendoCatalog.parse(jsonEncode({...envelope, 'key_id': 'other'})), isNull);
      expect(NextendoCatalog.parse('not json'), isNull);
    });

    test('the store keeps the last good catalog when the server fails, and never takes a lower revision', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      var now = DateTime.utc(2026, 11, 17, 21, 30);
      var answer = http.Response(body, 200);
      var calls = 0;
      final client = MockClient((request) async {
        calls++;
        expect(request.url.toString(), 'https://nextendo.network/service-catalog/v1/game-catalog');
        return answer;
      });
      expect((await NextendoCatalogStore.current(preferences: prefs, client: client, now: () => now))!.revision, 23);
      expect(calls, 1);
      now = now.add(const Duration(hours: 1));
      await NextendoCatalogStore.current(preferences: prefs, client: client, now: () => now);
      expect(calls, 1); // fresh: no request
      now = now.add(const Duration(hours: 6));
      answer = http.Response('{"error":"down"}', 503);
      expect((await NextendoCatalogStore.current(preferences: prefs, client: client, now: () => now))!.revision, 23);
      expect(calls, 2);
      expect(NextendoCatalogStore.stored(prefs)!.forTitle('01006a800016e000'), isNotNull);
    });
  });

  group('BCAT delivery data', () {
    late Directory root;
    setUp(() async => root = await Directory.systemTemp.createTemp('nextendo-bcat-'));
    tearDown(() async => root.delete(recursive: true));

    MockClient serving(http.Response Function() answer, List<Uri> urls) => MockClient((request) async {
      urls.add(request.url);
      return answer();
    });

    test('an archive is extracted to <root>/nextendo/bcat/<titleId>/<directory>/<file>, kept until it changes', () async {
      final urls = <Uri>[];
      var archive = _zip({'line_news/nx_line_news_0001': [1, 2, 3], 'present2/nx_present_0001': [4]});
      final client = serving(() => http.Response.bytes(archive, 200), urls);
      final events = <String>[];
      final path = await NextendoBcat.prepare(root: root, titleId: '01006A800016E000', client: client, onEvent: events.add);
      expect(path, '${root.path}/nextendo/bcat/01006a800016e000');
      expect(urls.single.toString(), 'https://nextendo.network/api/bcat/01006a800016e000');
      expect(File('$path/line_news/nx_line_news_0001').readAsBytesSync(), [1, 2, 3]);
      expect(File('$path/present2/nx_present_0001').readAsBytesSync(), [4]);
      await NextendoBcat.prepare(root: root, titleId: '01006a800016e000', client: client, onEvent: events.add);
      archive = _zip({'line_news/nx_line_news_0002': [9]});
      await NextendoBcat.prepare(root: root, titleId: '01006a800016e000', client: client, onEvent: events.add);
      expect(events, ['updated', 'current', 'updated']);
      expect(File('$path/line_news/nx_line_news_0001').existsSync(), isFalse);
      expect(File('$path/line_news/nx_line_news_0002').readAsBytesSync(), [9]);
      expect(root.listSync(recursive: true).where((e) => e.path.contains('.new-') || e.path.contains('.old-')), isEmpty);
    });

    test('204 removes the folder; a failed request keeps the copy already there', () async {
      final urls = <Uri>[];
      var answer = http.Response.bytes(_zip({'a/b': [1]}), 200);
      final client = serving(() => answer, urls);
      final path = await NextendoBcat.prepare(root: root, titleId: '0100f8f0000a2000', client: client);
      answer = http.Response('', 503);
      expect(await NextendoBcat.prepare(root: root, titleId: '0100f8f0000a2000', client: client), path);
      final failing = MockClient((_) async => throw const SocketException('offline'));
      expect(await NextendoBcat.prepare(root: root, titleId: '0100f8f0000a2000', client: failing), path);
      answer = http.Response('', 204);
      expect(await NextendoBcat.prepare(root: root, titleId: '0100f8f0000a2000', client: client), isNull);
      expect(Directory(path!).existsSync(), isFalse);
    });

    test('a path outside two plain levels refuses the whole archive and keeps the previous folder', () async {
      final urls = <Uri>[];
      var answer = http.Response.bytes(_zip({'news/one': [1]}), 200);
      final client = serving(() => answer, urls);
      final path = await NextendoBcat.prepare(root: root, titleId: '0100d2f00d5c0000', client: client);
      for (final name in ['../escape', 'a/b/c', '/abs/file', 'a/..', 'bad name/x', 'flat']) {
        answer = http.Response.bytes(_zip({name: [7]}), 200);
        expect(await NextendoBcat.prepare(root: root, titleId: '0100d2f00d5c0000', client: client), path, reason: name);
        expect(File('$path/news/one').readAsBytesSync(), [1], reason: name);
      }
      expect(File('${root.path}/nextendo/escape').existsSync(), isFalse);
    });

    test('a malformed title id asks nothing', () async {
      final urls = <Uri>[];
      expect(await NextendoBcat.prepare(root: root, titleId: '../x', client: serving(() => http.Response('', 200), urls)), isNull);
      expect(urls, isEmpty);
    });
  });

  test('the engine request carries the game data only when present', () {
    final token = NextendoGameToken(token: 'nx2.test', pid: 42, username: 'p', expiresAt: DateTime.utc(2026, 11, 18));
    const server = '198.51.100.1';
    const nat = '203.0.113.1';
    expect(NextendoLaunchOnline(token: token, serverAddress: server, natAddress: nat).toEngine().keys,
        ['nexToken', 'pid', 'serverAddress', 'natAddress']);
    final full = NextendoLaunchOnline(
      token: token,
      serverAddress: server,
      natAddress: nat,
      bcatDirectory: '/data/MeloNX/nextendo/bcat/01006a800016e000',
      nsa: '0123456789abcdef',
      acceptedVersions: const ['13.0.5'],
    ).toEngine();
    expect(full['bcatDirectory'], '/data/MeloNX/nextendo/bcat/01006a800016e000');
    expect(full['nsa'], '0123456789abcdef');
    expect(full['acceptedVersions'], ['13.0.5']);
  });
}
