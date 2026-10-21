import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:neostation/services/system_art/neoassets_public_catalog.dart';

void main() {
  group('NeoAssets public System Art catalogue', () {
    test('iterates published pages and retains all approved packs', () async {
      final offsets = <String>[];
      final client = MockClient((request) async {
        expect(request.uri.host, 'api.neoassets.dev');
        expect(request.uri.path, '/api/v1/packs');
        expect(request.uri.queryParameters['limit'], '100');
        final offset = request.uri.queryParameters['offset']!;
        offsets.add(offset);
        final packs = offset == '0'
            ? [
                {'folder': 'riisu', 'name': 'RiiSU'},
                {'folder': 'canvas-es-de', 'name': 'Canvas'}
              ]
            : [
                {'folder': 'pixel-ui-smart-folders', 'name': 'Pixel UI'}
              ];
        return http.Response(jsonEncode({'themes': packs, 'total': 3}), 200);
      });
      addTearDown(client.close);

      final result =
          await NeoAssetsPublicCatalog.fetchPublishedPacks(client: client);
      expect(result.map((e) => e['folder']), [
        'riisu',
        'canvas-es-de',
        'pixel-ui-smart-folders',
      ]);
      expect(offsets, ['0', '2']);
    });

    test('maps stable local folder IDs and uses the official CDN preview', () {
      final preview = NeoAssetsPublicCatalog.manifestEntry({
        'folder': 'riisu',
        'name': 'RiiSU',
        'author': 'mult1v4c',
        'version': '1.1',
        'backgrounds': ['packs/riisu/backgrounds/snes.webp'],
        'ai': false,
      });
      expect(preview['folder'], 'RiiSU');
      expect(preview['source'], 'neoassets');
      expect(preview['author'], 'mult1v4c');
      expect(preview['preview'],
          'https://cdn.neoassets.dev/packs/riisu/backgrounds/snes.webp');
      expect(NeoAssetsPublicCatalog.localFolderForSlug('neostation'),
          'NeoStation');
      expect(NeoAssetsPublicCatalog.slugForLocalFolder('NeoStation'),
          'neostation');
      expect(NeoAssetsPublicCatalog.slugForLocalFolder('CanvasESDE'), isNull);
    });

    test('uses system_id and the published media format and URL', () {
      final detail = <String, dynamic>{
        'folder': 'pixel-ui-smart-folders',
        'name': 'Pixel UI',
        'author': 'w0rm',
        'version': '1.0',
        'files': [
          {
            'kind': 'background',
            'system_id': 'ps1',
            'file_name': 'ps1.gif',
            'url':
                'https://cdn.neoassets.dev/packs/pixel-ui-smart-folders/backgrounds/ps1.gif',
          },
          {
            'kind': 'background',
            'system_id': 'fds',
            'file_name': 'fds.png',
            'url':
                'https://cdn.neoassets.dev/packs/pixel-ui-smart-folders/backgrounds/fds.webp',
          },
          {
            'kind': 'background',
            'system_id': 'ps3',
            'url': 'https://example.org/packs/pixel-ui-smart-folders/backgrounds/ps3.webp',
          },
          {
            'kind': 'preview',
            'system_id': 'gba',
            'url':
                'https://cdn.neoassets.dev/packs/pixel-ui-smart-folders/backgrounds/gba.webp',
          },
        ],
      };
      final urls = NeoAssetsPublicCatalog.backgroundUrls(
        'pixel-ui-smart-folders',
        detail,
      );
      expect(urls, hasLength(2));
      expect(urls['ps1'], endsWith('/ps1.gif'));
      expect(urls['fds'], endsWith('/fds.webp'));
      expect(urls.containsKey('ps3'), isFalse);
      final metadata = NeoAssetsPublicCatalog.cacheableMetadata(
        'pixel-ui-smart-folders',
        detail,
      );
      expect(metadata['systems'], ['ps1', 'fds']);
      expect(metadata['background_urls'], urls);
    });

    test('catalogue/detail never increment installs; counting is opt-in', () async {
      final paths = <String>[];
      final client = MockClient((request) async {
        paths.add(request.uri.path);
        if (request.uri.path.endsWith('/download')) {
          return http.Response('{"folder":"wiird"}', 200);
        }
        return http.Response(
          '{"folder":"wiird","version":"1.0","files":[]}',
          200,
        );
      });
      addTearDown(client.close);

      final detail =
          await NeoAssetsPublicCatalog.fetchDetail('wiird', client: client);
      expect(detail?['folder'], 'wiird');
      expect(paths, ['/api/v1/packs/wiird']);
      expect(
          await NeoAssetsPublicCatalog.recordInstall('wiird', client: client),
          isTrue);
      expect(paths, [
        '/api/v1/packs/wiird',
        '/api/v1/packs/wiird/download',
      ]);
    });

    test('rejects unsafe slugs and untrusted artwork hosts', () {
      expect(NeoAssetsPublicCatalog.isSafeId('../path'), isFalse);
      expect(NeoAssetsPublicCatalog.isSafeId('..'), isFalse);
      expect(
        NeoAssetsPublicCatalog.backgroundUrls('riisu', {
          'folder': 'riisu',
          'files': [
            {
              'kind': 'background',
              'system_id': 'snes',
              'url': 'https://cdn.neoassets.dev.evil.net/packs/riisu/backgrounds/snes.webp'
            }
          ]
        }),
        isEmpty,
      );
    });
  });
}
