import 'dart:async';
import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';

/// Looks up a host name's IPv4 addresses (the system resolver by default).
typedef NextendoLookup = Future<List<InternetAddress>> Function(String host);

/// Nextendo Network's two game-server addresses, found by name.
///
/// Nextendo's developer (17 November 2026): instead of build-time addresses
/// (`NEXTENDO_SERVER_IP`, `NEXTENDO_NAT_IP`), resolve `nex.nextendo.network`
/// for the game server and `nat.nextendo.network` for the secondary NAT test
/// address when the app starts, keep the result for about ten minutes, and keep
/// the last good address when a lookup fails. Nothing is written into the build.
///
/// The engine still receives two literal IPv4 addresses at each launch: it
/// answers the game's own DNS queries with them, and the Switch resolver only
/// hands IPv4 addresses to a game. Each name is kept apart: a failed lookup of
/// one leaves the other's fresh answer in place.
abstract final class NextendoServers {
  static const serverHost = 'nex.nextendo.network';
  static const natHost = 'nat.nextendo.network';

  /// How long a resolved address is used before it is looked up again.
  static const freshFor = Duration(minutes: 10);

  /// A lookup that takes longer counts as failed (the last good address stays).
  static const lookupTimeout = Duration(seconds: 5);

  // The game server name's other answers: the engine keeps the one that takes a TLS handshake (any title).
  static const _addressesKey = 'rewindbox.nextendo.resolved.gameAddresses';
  static Future<List<String>> gameAddresses(String primary, String nat, SharedPreferences? preferences) async {
    final prefs = preferences ?? await SharedPreferences.getInstance();
    final answers = prefs.getStringList(_addressesKey) ?? const [];
    if (answers.isEmpty || answers.first != primary) return const [];
    return answers.where((address) => address != nat && usable(address)).take(4).toList();
  }

  static const _serverKey = 'rewindbox.nextendo.resolved.server';
  static const _natKey = 'rewindbox.nextendo.resolved.nat';
  static const _serverAtKey = 'rewindbox.nextendo.resolved.serverAt';
  static const _natAtKey = 'rewindbox.nextendo.resolved.natAt';

  static Future<void>? _running;

  /// The last good address of each name (empty when none was ever found).
  static ({String server, String nat}) cached(SharedPreferences preferences) =>
      (server: preferences.getString(_serverKey) ?? '', nat: preferences.getString(_natKey) ?? '');

  /// Looks up each name whose last good address is missing or older than
  /// [freshFor] (every name with [force]). A success replaces that name's
  /// address and time; a failure, an empty answer or an answer without a
  /// usable IPv4 address keeps the last good one, and its time, so the next
  /// call tries again. Concurrent calls share one lookup. Never throws.
  static Future<void> refresh({
    SharedPreferences? preferences,
    NextendoLookup? lookup,
    DateTime Function()? now,
    bool force = false,
  }) {
    final running = _running;
    if (running != null) return running;
    final started = _refresh(preferences, lookup ?? _systemLookup, now ?? DateTime.now, force);
    _running = started;
    return started.whenComplete(() => _running = null);
  }

  static Future<void> _refresh(SharedPreferences? preferences, NextendoLookup lookup, DateTime Function() now, bool force) async {
    try {
      final prefs = preferences ?? await SharedPreferences.getInstance();
      await Future.wait([
        _refreshOne(prefs, serverHost, _serverKey, _serverAtKey, lookup, now, force),
        _refreshOne(prefs, natHost, _natKey, _natAtKey, lookup, now, force),
      ]);
    } on Object {
      // The preferences could not be read: the launch uses what it has.
    }
  }

  static Future<void> _refreshOne(
    SharedPreferences prefs,
    String host,
    String key,
    String atKey,
    NextendoLookup lookup,
    DateTime Function() now,
    bool force,
  ) async {
    final last = prefs.getString(key) ?? '';
    final at = prefs.getInt(atKey);
    final current = now();
    if (!force && last.isNotEmpty && at != null) {
      final age = current.difference(DateTime.fromMillisecondsSinceEpoch(at));
      if (!age.isNegative && age < freshFor) return;
    }
    try {
      final answers = await lookup(host).timeout(lookupTimeout);
      final found = answers.map((address) => address.address).where(usable).toSet().toList();
      if (found.isEmpty) return;
      if (host == serverHost) await prefs.setStringList(_addressesKey, found.take(5).toList());
      await prefs.setString(key, found.first);
      await prefs.setInt(atKey, current.millisecondsSinceEpoch);
    } on Object {
      // Lookup failed or timed out: the last good address stays.
    }
  }

  /// A public-looking literal IPv4 address the engine can hand to a game.
  static bool usable(String value) {
    final parsed = InternetAddress.tryParse(value);
    return parsed != null &&
        parsed.type == InternetAddressType.IPv4 &&
        !parsed.isLoopback &&
        parsed.address != '0.0.0.0';
  }

  static Future<List<InternetAddress>> _systemLookup(String host) =>
      InternetAddress.lookup(host, type: InternetAddressType.IPv4);
}
