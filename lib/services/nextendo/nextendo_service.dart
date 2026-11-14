import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import 'nextendo_config.dart';

/// The signed-in player, as `GET /api/oauth/userinfo` describes them.
@immutable
class NextendoAccount {
  const NextendoAccount({required this.pid, required this.username, required this.friendCode, this.displayName});
  final int pid;
  final String username;
  final String friendCode;
  final String? displayName;

  String get shownName => (displayName?.trim().isNotEmpty ?? false) ? displayName!.trim() : username;

  Map<String, dynamic> toJson() => {
    'pid': pid,
    'username': username,
    'friend_code': friendCode,
    if (displayName != null) 'display_name': displayName,
  };

  static NextendoAccount? fromJson(Object? value) {
    if (value is! Map) return null;
    final pid = value['pid'];
    final username = value['username'];
    if (pid is! int || pid <= 0 || username is! String || username.isEmpty) return null;
    final display = value['display_name'];
    return NextendoAccount(
      pid: pid,
      username: username,
      friendCode: value['friend_code'] is String ? value['friend_code'] as String : '',
      displayName: display is String ? display : null,
    );
  }
}

/// The game token (`nx2.…`) of one launch. It only works in games, for a day.
@immutable
class NextendoGameToken {
  const NextendoGameToken({required this.token, required this.pid, required this.username, required this.expiresAt});
  final String token;
  final int pid;
  final String username;
  final DateTime expiresAt;
}

/// Why Nextendo refuses online play for this account, in the server's words.
@immutable
class NextendoOnlineStatus {
  const NextendoOnlineStatus({required this.allowed, required this.reason});
  final bool allowed;

  /// Empty when allowed; otherwise `unknown`, `disabled`, `suspended`,
  /// `unverified`, `discord_unlinked` or `elsewhere`.
  final String reason;
}

/// A failure the Nextendo screen translates ([code] is a locale key).
class NextendoException implements Exception {
  const NextendoException(this.code, [this.detail = '']);
  final String code;
  final String detail;
  @override
  String toString() => detail.isEmpty ? code : '$code:$detail';
}

/// Opens the system sign-in sheet on [url] and returns the redirect it ends on.
typedef NextendoAuthorizer = Future<Uri> Function(Uri url, String callbackScheme);

/// Where the session is kept. The default is the platform keychain.
abstract interface class NextendoStore {
  Future<String?> read();
  Future<void> write(String value);
  Future<void> clear();
}

class _KeychainStore implements NextendoStore {
  const _KeychainStore();
  static const _key = 'rewindbox.nextendo.session';
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(resetOnError: false, migrateWithBackup: true),
    mOptions: MacOsOptions(usesDataProtectionKeychain: false),
  );
  @override
  Future<String?> read() => _storage.read(key: _key);
  @override
  Future<void> write(String value) => _storage.write(key: _key, value: value);
  @override
  Future<void> clear() => _storage.delete(key: _key);
}

/// RewindBox's side of "Sign in with Nextendo" (OAuth 2.0, public client with
/// PKCE), written from Nextendo's developer documentation
/// (https://wiki.nextendo.network/developers).
///
/// The player signs in on nextendo.network inside the system sign-in sheet:
/// RewindBox never sees a password. It keeps the access token (one hour) and
/// the rotating refresh token (thirty days) in the keychain, and exchanges the
/// access token for a game token when a Switch game starts.
class NextendoService {
  NextendoService({http.Client? client, NextendoStore? store, NextendoAuthorizer? authorizer, DateTime Function()? clock, Random? random})
    : _client = client ?? http.Client(),
      _store = store ?? const _KeychainStore(),
      _authorizer = authorizer ?? _systemAuthorizer,
      _clock = clock ?? DateTime.now,
      _random = random ?? Random.secure();

  static final NextendoService instance = NextendoService();
  static const _channel = MethodChannel('neostation/web_auth');
  static const _timeout = Duration(seconds: 20);

  final http.Client _client;
  final NextendoStore _store;
  final NextendoAuthorizer _authorizer;
  final DateTime Function() _clock;
  final Random _random;

  /// The signed-in player; null when signed out.
  final ValueNotifier<NextendoAccount?> account = ValueNotifier(null);

  Map<String, dynamic>? _session;
  bool _restored = false;
  Future<String>? _refreshing;

  static Future<Uri> _systemAuthorizer(Uri url, String callbackScheme) async {
    final String? redirect;
    try {
      redirect = await _channel.invokeMethod<String>('authenticate', {'url': url.toString(), 'callbackScheme': callbackScheme});
    } on PlatformException catch (error) {
      throw NextendoException(switch (error.code) {
        'cancelled' => 'signInCancelled',
        'failed' => 'signInFailed',
        _ => 'signInUnavailable',
      }, error.message ?? '');
    } on MissingPluginException {
      throw const NextendoException('signInUnavailable');
    }
    final parsed = redirect == null ? null : Uri.tryParse(redirect);
    if (parsed == null) throw const NextendoException('signInFailed', 'redirect');
    return parsed;
  }

  /// Loads the stored session once. A session kept for another client
  /// identifier is discarded: its tokens belong to that application.
  Future<NextendoAccount?> restore(NextendoConfig config) async {
    if (!_restored) {
      _restored = true;
      try {
        final text = await _store.read();
        final decoded = text == null ? null : jsonDecode(text);
        if (decoded is Map && decoded['client_id'] == config.clientId && decoded['refresh_token'] is String) {
          _session = Map<String, dynamic>.from(decoded);
        }
      } on Object {
        _session = null;
      }
      account.value = NextendoAccount.fromJson(_session?['account']);
      if (account.value == null) _session = null;
    } else if (_session != null && _session!['client_id'] != config.clientId) {
      await _forget();
    }
    return account.value;
  }

  /// The whole sign-in: consent on nextendo.network, code exchange, identity.
  Future<NextendoAccount> signIn(NextendoConfig config) async {
    if (!config.canSignIn) throw const NextendoException('notConfigured');
    final verifier = _randomToken(32);
    final state = _randomToken(16);
    final challenge = base64Url.encode(sha256.convert(ascii.encode(verifier)).bytes).replaceAll('=', '');
    final authorize = Uri.parse('${NextendoConfig.apiBase}/api/oauth/authorize').replace(queryParameters: {
      'client_id': config.clientId,
      'response_type': 'code',
      'redirect_uri': NextendoConfig.redirectUri,
      'code_challenge': challenge,
      'code_challenge_method': 'S256',
      'scope': NextendoConfig.scopes,
      'state': state,
    });
    final redirect = await _authorizer(authorize, NextendoConfig.callbackScheme);
    if (redirect.scheme != NextendoConfig.callbackScheme) throw const NextendoException('signInFailed', 'redirect');
    final parameters = redirect.queryParameters;
    // The state comes back unchanged; anything else is not this sign-in's answer.
    if (parameters['state'] != state) throw const NextendoException('signInFailed', 'state');
    if (parameters['error'] != null) {
      throw NextendoException(parameters['error'] == 'access_denied' ? 'signInCancelled' : 'signInFailed', parameters['error']!);
    }
    final code = parameters['code'];
    if (code == null || code.isEmpty) throw const NextendoException('signInFailed', 'code');
    final tokens = await _token(config, {
      'grant_type': 'authorization_code',
      'client_id': config.clientId,
      'code': code,
      'code_verifier': verifier,
      'redirect_uri': NextendoConfig.redirectUri,
    });
    final identity = NextendoAccount.fromJson(await _get('/api/oauth/userinfo', tokens['access_token'] as String));
    if (identity == null) throw const NextendoException('signInFailed', 'identity');
    await _keep(config, tokens, identity);
    return identity;
  }

  /// Signs the player out of RewindBox on Nextendo's side too (every refresh
  /// token of this application for that player), then forgets the session.
  Future<void> signOut(NextendoConfig config) async {
    await restore(config);
    final refresh = _session?['refresh_token'];
    await _forget();
    if (refresh is String) {
      try {
        await _client
            .post(Uri.parse('${NextendoConfig.apiBase}/api/oauth/revoke'), headers: _clientHeaders(config), body: {'token': refresh})
            .timeout(_timeout);
      } on Object {
        // The local session is gone either way; the refresh token expires alone.
      }
    }
  }

  /// A valid access token, refreshed when under a minute remains.
  Future<String> accessToken(NextendoConfig config) async {
    await restore(config);
    final session = _session;
    if (session == null) throw const NextendoException('signedOut');
    final expiry = session['access_expiry'];
    final access = session['access_token'];
    if (access is String && expiry is int && _clock().millisecondsSinceEpoch ~/ 1000 < expiry - 60) return access;
    // A refresh token is single-use: two callers share one refresh.
    return _refreshing ??= _refresh(config).whenComplete(() => _refreshing = null);
  }

  /// The game token of this launch (`GET /api/nex-token`): asked again at every
  /// launch, as Nextendo's documentation says.
  Future<NextendoGameToken> gameToken(NextendoConfig config) async {
    Object? answer;
    try {
      try {
        answer = await _get('/api/nex-token', await accessToken(config));
      } on NextendoException catch (error) {
        if (error.code != 'sessionRefused') rethrow;
        // The access token was withdrawn before its hour ended: one refresh
        // tells whether the session itself still stands.
        final fresh = await (_refreshing ??= _refresh(config).whenComplete(() => _refreshing = null));
        answer = await _get('/api/nex-token', fresh);
      }
    } on NextendoException catch (error) {
      // 403 here means the consent lacks game.matchmaking: sign in again.
      if (error.code == 'forbidden') throw const NextendoException('gameScopeMissing');
      rethrow;
    }
    if (answer is! Map) throw const NextendoException('serverAnswer', 'nex-token');
    final token = answer['nex_token'];
    final pid = answer['pid'];
    if (token is! String || !token.startsWith('nx2.') || token.length > 1024 || pid is! int) {
      throw const NextendoException('serverAnswer', 'nex-token');
    }
    final lifetime = answer['expires_in'];
    return NextendoGameToken(
      token: token,
      pid: pid,
      username: answer['username'] is String ? answer['username'] as String : account.value?.username ?? '',
      expiresAt: _clock().add(Duration(seconds: lifetime is int && lifetime > 0 ? lifetime : 24 * 3600)),
    );
  }

  /// Whether Nextendo lets this account go online now, asked with the game
  /// token as its documentation describes.
  Future<NextendoOnlineStatus> onlineStatus(NextendoGameToken token) async {
    final answer = await _get('/api/online-status', token.token);
    if (answer is! Map || answer['allow'] is! bool) throw const NextendoException('serverAnswer', 'online-status');
    return NextendoOnlineStatus(allowed: answer['allow'] as bool, reason: '${answer['reason'] ?? ''}');
  }

  Future<String> _refresh(NextendoConfig config) async {
    final refresh = _session?['refresh_token'];
    if (refresh is! String) throw const NextendoException('signedOut');
    final Map<String, dynamic> tokens;
    try {
      tokens = await _token(config, {'grant_type': 'refresh_token', 'client_id': config.clientId, 'refresh_token': refresh});
    } on NextendoException catch (error) {
      // The server no longer accepts this session: expired, revoked by the
      // player, or the application suspended. Network failures keep it.
      if (const {'sessionExpired', 'applicationRefused'}.contains(error.code)) await _forget();
      rethrow;
    }
    await _keep(config, tokens, account.value!);
    return tokens['access_token'] as String;
  }

  Future<void> _keep(NextendoConfig config, Map<String, dynamic> tokens, NextendoAccount identity) async {
    final lifetime = tokens['expires_in'];
    final session = <String, dynamic>{
      'client_id': config.clientId,
      'access_token': tokens['access_token'],
      'access_expiry': _clock().millisecondsSinceEpoch ~/ 1000 + (lifetime is int && lifetime > 0 ? lifetime : 3600),
      'refresh_token': tokens['refresh_token'],
      'scope': tokens['scope'],
      'account': identity.toJson(),
    };
    // The new refresh token replaces the old one a minute after this answer:
    // it is stored before anything else uses the session.
    await _store.write(jsonEncode(session));
    _session = session;
    _restored = true;
    account.value = identity;
  }

  Future<void> _forget() async {
    _session = null;
    account.value = null;
    try {
      await _store.clear();
    } on Object {
      // Nothing readable is left in memory; the stored copy is dropped at the next sign-in.
    }
  }

  Map<String, String> _clientHeaders(NextendoConfig config) => {'X-Nextendo-Client-Id': config.clientId, 'Accept': 'application/json'};

  Future<Map<String, dynamic>> _token(NextendoConfig config, Map<String, String> form) async {
    final http.Response response;
    try {
      response = await _client
          .post(Uri.parse('${NextendoConfig.apiBase}/api/oauth/token'), headers: _clientHeaders(config), body: form)
          .timeout(_timeout);
    } on Object catch (error) {
      throw NextendoException('network', error.runtimeType.toString());
    }
    final body = _json(response);
    if (response.statusCode == 200 && body is Map && body['access_token'] is String && body['refresh_token'] is String) {
      return Map<String, dynamic>.from(body);
    }
    final reason = body is Map ? '${body['error'] ?? ''}' : '';
    if (response.statusCode == 429) throw const NextendoException('rateLimited');
    if (response.statusCode >= 500) throw NextendoException('serverUnavailable', '${response.statusCode}');
    if (reason == 'invalid_grant') throw const NextendoException('sessionExpired');
    // invalid_client, an unregistered or suspended application, a blocked one.
    if (reason == 'invalid_client' || reason == 'access_denied' || response.statusCode == 401 || response.statusCode == 403) {
      throw NextendoException('applicationRefused', body is Map ? '${body['code'] ?? reason}' : '');
    }
    throw NextendoException('serverAnswer', reason.isEmpty ? '${response.statusCode}' : reason);
  }

  Future<Object?> _get(String path, String bearer) async {
    final http.Response response;
    try {
      response = await _client
          .get(Uri.parse('${NextendoConfig.apiBase}$path'), headers: {'Authorization': 'Bearer $bearer', 'Accept': 'application/json'})
          .timeout(_timeout);
    } on Object catch (error) {
      throw NextendoException('network', error.runtimeType.toString());
    }
    switch (response.statusCode) {
      case 200:
        return _json(response);
      case 401:
        throw const NextendoException('sessionRefused');
      case 403:
        throw const NextendoException('forbidden');
      case 429:
        throw const NextendoException('rateLimited');
      default:
        throw NextendoException(response.statusCode >= 500 ? 'serverUnavailable' : 'serverAnswer', '${response.statusCode}');
    }
  }

  static Object? _json(http.Response response) {
    try {
      return jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      return null;
    }
  }

  /// [bytes] random bytes as unpadded base64url (32 bytes: a 43-character PKCE verifier).
  String _randomToken(int bytes) =>
      base64Url.encode([for (var index = 0; index < bytes; index++) _random.nextInt(256)]).replaceAll('=', '');
}
