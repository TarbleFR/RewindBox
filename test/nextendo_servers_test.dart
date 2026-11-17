import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/nextendo/nextendo_config.dart';
import 'package:neostation/services/nextendo/nextendo_servers.dart';
import 'package:shared_preferences/shared_preferences.dart';

// Nextendo's two game-server addresses are looked up by name (nex.nextendo.network, nat.nextendo.network), kept
// about ten minutes, and the last good address is kept when a lookup fails. Addresses below are documentation
// ranges (RFC 5737), not Nextendo's.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late SharedPreferences prefs;
  late DateTime clock;
  late Map<String, int> calls;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    prefs = await SharedPreferences.getInstance();
    clock = DateTime.utc(2026, 11, 17, 21);
    calls = {};
  });

  NextendoLookup answers(Map<String, List<String>> table, {Set<String> failing = const {}}) => (host) async {
    calls[host] = (calls[host] ?? 0) + 1;
    if (failing.contains(host)) throw const SocketException('lookup failed');
    return [for (final value in table[host] ?? const <String>[]) InternetAddress(value)];
  };

  Future<void> refresh(NextendoLookup lookup) =>
      NextendoServers.refresh(preferences: prefs, lookup: lookup, now: () => clock);

  Future<NextendoConfig> config({String server = '', String nat = ''}) =>
      NextendoConfig.resolve(buildClientId: '', buildServer: server, buildNat: nat, preferences: prefs);

  final good = {
    NextendoServers.serverHost: ['198.51.100.10'],
    NextendoServers.natHost: ['203.0.113.20'],
  };

  test('both names resolved: the configuration plays online without any build value or field', () async {
    await refresh(answers(good));
    final settings = await config();
    expect(settings.serverAddress, '198.51.100.10');
    expect(settings.natAddress, '203.0.113.20');
    expect(settings.serverResolved && settings.natResolved, isTrue);
    expect(settings.serversAutomatic, isTrue);
    expect(settings.serversConfigured, isTrue);
    expect(calls, {NextendoServers.serverHost: 1, NextendoServers.natHost: 1});
  });

  test('an answer under ten minutes old is used without a new lookup', () async {
    await refresh(answers(good));
    clock = clock.add(const Duration(minutes: 9, seconds: 59));
    await refresh(answers(good));
    expect(calls, {NextendoServers.serverHost: 1, NextendoServers.natHost: 1});
    clock = clock.add(const Duration(seconds: 2));
    await refresh(answers(good));
    expect(calls, {NextendoServers.serverHost: 2, NextendoServers.natHost: 2});
  });

  test('a failed lookup keeps the last good address and tries again at the next call', () async {
    await refresh(answers(good));
    clock = clock.add(const Duration(minutes: 11));
    await refresh(answers(good, failing: {NextendoServers.serverHost, NextendoServers.natHost}));
    var settings = await config();
    expect(settings.serverAddress, '198.51.100.10');
    expect(settings.natAddress, '203.0.113.20');
    expect(settings.serversConfigured, isTrue);
    clock = clock.add(const Duration(seconds: 1));
    await refresh(answers({
      NextendoServers.serverHost: ['198.51.100.11'],
      NextendoServers.natHost: ['203.0.113.21'],
    }));
    settings = await config();
    expect(settings.serverAddress, '198.51.100.11');
    expect(settings.natAddress, '203.0.113.21');
    expect(calls, {NextendoServers.serverHost: 3, NextendoServers.natHost: 3});
  });

  test('each name is kept apart: one failure leaves the other answer', () async {
    await refresh(answers(good));
    clock = clock.add(const Duration(minutes: 11));
    await refresh(answers({NextendoServers.natHost: ['203.0.113.22']}, failing: {NextendoServers.serverHost}));
    final settings = await config();
    expect(settings.serverAddress, '198.51.100.10');
    expect(settings.natAddress, '203.0.113.22');
  });

  test('an empty answer, IPv6, loopback or 0.0.0.0 is not an address', () async {
    await refresh(answers({
      NextendoServers.serverHost: ['2001:db8::1', '127.0.0.1', '0.0.0.0'],
      NextendoServers.natHost: [],
    }));
    final settings = await config();
    expect(settings.serverAddress, isEmpty);
    expect(settings.natAddress, isEmpty);
    expect(settings.serversAutomatic, isFalse);
    expect(settings.serversIssue, 'missing');
  });

  test('the first IPv4 answer after unusable ones is taken', () async {
    await refresh(answers({
      NextendoServers.serverHost: ['2001:db8::1', '198.51.100.30', '198.51.100.31'],
      NextendoServers.natHost: ['203.0.113.30'],
    }));
    expect((await config()).serverAddress, '198.51.100.30');
  });

  test('nothing ever resolved: no lookup leaves the maintainer field as the only source', () async {
    await NextendoConfig.saveLocal(clientId: '', serverAddress: '198.51.100.40', natAddress: '203.0.113.40', preferences: prefs);
    await refresh(answers(const {}, failing: {NextendoServers.serverHost, NextendoServers.natHost}));
    final settings = await config();
    expect(settings.serverAddress, '198.51.100.40');
    expect(settings.natAddress, '203.0.113.40');
    expect(settings.serversAutomatic, isFalse);
    await refresh(answers(good));
    final resolved = await config();
    expect(resolved.serverAddress, '198.51.100.10');
    expect(resolved.serversAutomatic, isTrue);
  });

  test('a build define still overrides its name', () async {
    await refresh(answers(good));
    final settings = await config(server: '198.51.100.50');
    expect(settings.serverAddress, '198.51.100.50');
    expect(settings.serverFromBuild, isTrue);
    expect(settings.serverResolved, isFalse);
    expect(settings.natAddress, '203.0.113.20');
    expect(settings.serversAutomatic, isTrue);
  });

  test('concurrent refreshes share one lookup', () async {
    final first = refresh(answers(good));
    final second = refresh(answers(good));
    await Future.wait([first, second]);
    expect(calls, {NextendoServers.serverHost: 1, NextendoServers.natHost: 1});
  });

  test('a forced refresh looks both names up again', () async {
    await refresh(answers(good));
    await NextendoServers.refresh(preferences: prefs, lookup: answers(good), now: () => clock, force: true);
    expect(calls, {NextendoServers.serverHost: 2, NextendoServers.natHost: 2});
  });
}
