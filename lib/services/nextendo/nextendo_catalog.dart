import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'nextendo_config.dart';
import 'nextendo_ed25519.dart';

/// One game of Nextendo's signed catalog: the exact versions its servers accept.
class NextendoGameRequirement {
  const NextendoGameRequirement({
    required this.name,
    required this.titleIds,
    required this.enabled,
    required this.protocol,
    required this.accepted,
    required this.recommended,
  });

  final String name;
  final List<String> titleIds; // 16 lowercase hex digits each
  final bool enabled;
  final String protocol; // nex, npln, demonware, ubisoft... ('' when the catalog gives none)
  final List<String> accepted;
  final String recommended;

  /// NPLN titles also need Nextendo's signed online patches (not applied by RewindBox yet).
  bool get needsNplnPatches => protocol == 'npln';
}

/// Nextendo's signed game catalog (integration guide, "Per-game requirements"):
/// `GET /service-catalog/v1/game-catalog` answers `{key_id, payload, signature}`;
/// the signature is Ed25519 over the base64-decoded payload with the published
/// key `catalog-key-1`; the payload must say `document_type = "game_catalog"`,
/// `revision >= 1` and `expires_at` in the future. Each game lists its title
/// ids and the exact versions accepted ("Enforce the exact game version in every
/// build you distribute, and read it from the signed catalog").
class NextendoCatalog {
  const NextendoCatalog({required this.revision, required this.expiresAt, required this.games});

  static const keyId = 'catalog-key-1';
  static const publicKey = 'xI+atR6VesrCH89ZDZD4t3WQLcYOFEhk5F0HLMzgWk4=';
  static const path = '/service-catalog/v1/game-catalog';
  static const maxBytes = 1024 * 1024;

  final int revision;
  final DateTime expiresAt;
  final List<NextendoGameRequirement> games;

  bool expired(DateTime now) => !expiresAt.isAfter(now);

  NextendoGameRequirement? forTitle(String titleId) {
    final id = titleId.toLowerCase();
    for (final game in games) {
      if (game.titleIds.contains(id)) return game;
    }
    return null;
  }

  /// The verified catalog of [body], or null: wrong key, bad signature, wrong
  /// document type, revision under 1, or a malformed field. Expiry is checked by
  /// the caller ([expired]) so that a last good copy can still be shown.
  static NextendoCatalog? parse(String body) {
    try {
      if (body.length > maxBytes * 2) return null;
      final envelope = jsonDecode(body);
      if (envelope is! Map || envelope['key_id'] != keyId) return null;
      final payloadText = envelope['payload'];
      final signatureText = envelope['signature'];
      if (payloadText is! String || signatureText is! String) return null;
      final payload = base64.decode(payloadText);
      if (payload.length > maxBytes) return null;
      if (!NextendoEd25519.verify(base64.decode(publicKey), payload, base64.decode(signatureText))) return null;
      final document = jsonDecode(utf8.decode(payload));
      if (document is! Map || document['document_type'] != 'game_catalog') return null;
      final revision = document['revision'];
      final expires = DateTime.tryParse('${document['expires_at']}');
      final list = document['games'];
      if (revision is! int || revision < 1 || expires == null || list is! List) return null;
      final games = <NextendoGameRequirement>[];
      for (final entry in list) {
        if (entry is! Map) continue;
        final ids = entry['title_ids'];
        final versions = entry['versions'];
        if (ids is! List || versions is! Map || versions['policy'] != 'exact') continue;
        final titleIds = [
          for (final id in ids)
            if (id is String && RegExp(r'^[0-9a-fA-F]{16}$').hasMatch(id)) id.toLowerCase(),
        ];
        final accepted = [
          for (final version in (versions['accepted'] is List ? versions['accepted'] as List : const []))
            if (version is String && version.isNotEmpty && version.length <= 32) version,
        ];
        if (titleIds.isEmpty || accepted.isEmpty) continue;
        games.add(NextendoGameRequirement(
          name: entry['name'] is String ? entry['name'] as String : titleIds.first,
          titleIds: titleIds,
          enabled: entry['enabled'] == true,
          protocol: entry['protocol'] is String ? entry['protocol'] as String : '',
          accepted: accepted,
          recommended: versions['recommended'] is String ? versions['recommended'] as String : accepted.last,
        ));
      }
      games.sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));
      return NextendoCatalog(revision: revision, expiresAt: expires.toUtc(), games: List.unmodifiable(games));
    } on Object {
      return null;
    }
  }
}

/// Keeps the last good verified catalog in the app's preferences and fetches a
/// new one when it is six hours old or expired. A lower revision never replaces
/// a higher one. Never throws.
abstract final class NextendoCatalogStore {
  static const refreshAfter = Duration(hours: 6);
  static const _bodyKey = 'rewindbox.nextendo.catalog.body';
  static const _fetchedKey = 'rewindbox.nextendo.catalog.fetchedAt';

  static Future<NextendoCatalog?>? _running;

  /// The last good catalog, fetched again first when stale. Null when no valid
  /// catalog was ever received.
  static Future<NextendoCatalog?> current({
    SharedPreferences? preferences,
    http.Client? client,
    DateTime Function()? now,
    bool force = false,
  }) {
    final running = _running;
    if (running != null) return running;
    final started = _current(preferences, client, now ?? DateTime.now, force);
    _running = started;
    return started.whenComplete(() => _running = null);
  }

  /// The stored catalog without any request (null when none).
  static NextendoCatalog? stored(SharedPreferences prefs) {
    final body = prefs.getString(_bodyKey);
    return body == null ? null : NextendoCatalog.parse(body);
  }

  static Future<NextendoCatalog?> _current(SharedPreferences? preferences, http.Client? client, DateTime Function() now, bool force) async {
    SharedPreferences prefs;
    try {
      prefs = preferences ?? await SharedPreferences.getInstance();
    } on Object {
      return null;
    }
    final last = stored(prefs);
    final fetchedAt = prefs.getInt(_fetchedKey);
    final current = now();
    final fresh = last != null &&
        !last.expired(current) &&
        fetchedAt != null &&
        current.difference(DateTime.fromMillisecondsSinceEpoch(fetchedAt)) < refreshAfter;
    if (fresh && !force) return last;
    final owned = client == null;
    final http.Client http0 = client ?? http.Client();
    try {
      final response = await http0
          .get(Uri.parse('${NextendoConfig.apiBase}${NextendoCatalog.path}'), headers: {'Accept': 'application/json'})
          .timeout(const Duration(seconds: 8));
      if (response.statusCode == 200 && response.bodyBytes.length <= NextendoCatalog.maxBytes * 2) {
        final body = utf8.decode(response.bodyBytes);
        final received = NextendoCatalog.parse(body);
        if (received != null && (last == null || received.revision >= last.revision)) {
          await prefs.setString(_bodyKey, body);
          await prefs.setInt(_fetchedKey, current.millisecondsSinceEpoch);
          return received;
        }
      }
    } on Object {
      // Unreachable or refused: the last good catalog stays.
    } finally {
      if (owned) http0.close();
    }
    return last;
  }
}
