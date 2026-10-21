import 'dart:convert';

import 'package:http/http.dart' as http;

/// Published System Art from the official NeoAssets API, without bundling art.
class NeoAssetsPublicCatalog {
  static const apiOrigin = 'https://api.neoassets.dev';
  static const cdnOrigin = 'https://cdn.neoassets.dev';
  static final RegExp _safeId = RegExp(r'^[a-z0-9][a-z0-9_-]{0,79}$');

  static bool isSafeId(String value) => _safeId.hasMatch(value);

  /// Preserve existing on-disk IDs and saved selections.
  static String localFolderForSlug(String slug) => switch (slug) {
    'riisu' => 'RiiSU',
    'neostation' => 'NeoStation',
    _ => slug,
  };

  static String? slugForLocalFolder(String folder) {
    final slug = switch (folder) {
      'RiiSU' => 'riisu',
      'NeoStation' => 'neostation',
      _ => folder,
    };
    return isSafeId(slug) ? slug : null;
  }

  static Uri _listUri(int offset) => Uri.https(
        'api.neoassets.dev',
        '/api/v1/packs',
        {'sort': 'downloads', 'limit': '100', 'offset': '$offset'},
      );

  static Uri _detailUri(String slug, {bool countInstall = false}) {
    if (!isSafeId(slug)) throw ArgumentError.value(slug, 'slug');
    return Uri.https(
      'api.neoassets.dev',
      '/api/v1/packs/' + slug + (countInstall ? '/download' : ''),
    );
  }

  /// Iterate every published page; list/detail lookups do not count downloads.
  static Future<List<Map<String, dynamic>>> fetchPublishedPacks({
    http.Client? client,
  }) async {
    final httpClient = client ?? http.Client();
    try {
      final packs = <Map<String, dynamic>>[];
      final seen = <String>{};
      var offset = 0;
      for (var page = 0; page < 30; page++) {
        final response = await httpClient.get(_listUri(offset));
        if (response.statusCode != 200) {
          throw StateError('NeoAssets catalogue HTTP ' +
              response.statusCode.toString());
        }
        final json = jsonDecode(response.body);
        if (json is! Map || json['themes'] is! List) {
          throw const FormatException('Invalid NeoAssets catalogue');
        }
        final batch = json['themes'] as List;
        if (batch.isEmpty) break;
        final before = seen.length;
        for (final value in batch) {
          if (value is! Map) continue;
          final item = Map<String, dynamic>.from(value);
          final slug = item['folder']?.toString() ?? '';
          if (isSafeId(slug) && seen.add(slug)) packs.add(item);
        }
        if (seen.length == before && page > 0) {
          throw const FormatException('Repeated NeoAssets catalogue page');
        }
        offset += batch.length;
        final rawTotal = json['total'];
        final total = rawTotal is num ? rawTotal.toInt() : offset;
        if (offset >= total) break;
        if (page == 29) {
          throw const FormatException('NeoAssets catalogue exceeded page cap');
        }
      }
      return packs;
    } finally {
      if (client == null) httpClient.close();
    }
  }

  static bool _allowedCdnUrl(Uri uri, String slug) =>
      uri.scheme == 'https' &&
      uri.host == 'cdn.neoassets.dev' &&
      uri.userInfo.isEmpty &&
      uri.path.startsWith('/packs/$slug/backgrounds/') &&
      (uri.path.toLowerCase().endsWith('.webp') ||
          uri.path.toLowerCase().endsWith('.gif'));

  /// The preview paths are CDN object keys, not paths on the old GitHub repo.
  static String previewUrl(Map<String, dynamic> record) {
    final backgrounds = record['backgrounds'];
    final slug = record['folder']?.toString() ?? '';
    if (backgrounds is! List || !isSafeId(slug)) return '';
    for (final item in backgrounds) {
      final key = item?.toString() ?? '';
      if (!key.startsWith('packs/$slug/backgrounds/')) continue;
      final url = Uri.tryParse('$cdnOrigin/$key');
      if (url != null && _allowedCdnUrl(url, slug)) return url.toString();
    }
    return '';
  }

  static Map<String, dynamic> manifestEntry(Map<String, dynamic> record) {
    final slug = record['folder']?.toString() ?? '';
    if (!isSafeId(slug)) throw ArgumentError.value(slug, 'folder');
    return {
      'source': 'neoassets',
      'folder': localFolderForSlug(slug),
      'slug': slug,
      'name': record['name']?.toString() ?? slug,
      'author': record['author']?.toString() ?? '',
      'version': record['version']?.toString() ?? '',
      'preview': previewUrl(record),
      'ai': record['ai'] == true,
    };
  }

  static Future<Map<String, dynamic>?> fetchDetail(
    String slug, {
    http.Client? client,
  }) async {
    final httpClient = client ?? http.Client();
    try {
      final response = await httpClient.get(_detailUri(slug));
      if (response.statusCode != 200) return null;
      final json = jsonDecode(response.body);
      if (json is! Map) return null;
      return Map<String, dynamic>.from(json);
    } finally {
      if (client == null) httpClient.close();
    }
  }

  /// Use system_id and the actual URL, not file_name: upstream conversions
  /// sometimes retain their original filename or extension in file_name.
  static Map<String, String> backgroundUrls(
    String slug,
    Map<String, dynamic> detail,
  ) {
    if (!isSafeId(slug) || detail['folder']?.toString() != slug) {
      return {};
    }
    final files = detail['files'];
    if (files is! List) return {};
    final urls = <String, String>{};
    for (final value in files) {
      if (value is! Map || value['kind'] != 'background') continue;
      final system = value['system_id']?.toString() ?? '';
      if (!isSafeId(system)) continue;
      final url = Uri.tryParse(value['url']?.toString() ?? '');
      if (url == null || !_allowedCdnUrl(url, slug)) continue;
      urls[system] = url.toString();
    }
    return urls;
  }

  static Map<String, dynamic> cacheableMetadata(
    String slug,
    Map<String, dynamic> detail,
  ) {
    final backgrounds = backgroundUrls(slug, detail);
    return {
      'source': 'neoassets',
      'folder': localFolderForSlug(slug),
      'slug': slug,
      'name': detail['name']?.toString() ?? slug,
      'author': detail['author']?.toString() ?? '',
      'version': detail['version']?.toString() ?? '',
      'ai': detail['ai'] == true,
      'systems': backgrounds.keys.toList(),
      'background_urls': backgrounds,
    };
  }

  /// Records one *actual* install; never called while listing or previewing.
  static Future<bool> recordInstall(String slug, {http.Client? client}) async {
    final httpClient = client ?? http.Client();
    try {
      final response = await httpClient.get(
        _detailUri(slug, countInstall: true),
      );
      return response.statusCode == 200;
    } finally {
      if (client == null) httpClient.close();
    }
  }
}
