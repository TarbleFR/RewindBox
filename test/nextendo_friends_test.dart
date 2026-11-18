import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:neostation/services/nextendo/nextendo_config.dart';
import 'package:neostation/services/nextendo/nextendo_service.dart';
import 'package:neostation/widgets/nextendo_friends_button.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _config = NextendoConfig(
  clientId: NextendoConfig.registeredClientId,
  serverAddress: '',
  natAddress: '',
);

class _Store implements NextendoStore {
  _Store({bool signedIn = true})
    : value = signedIn
          ? jsonEncode({
              'client_id': _config.clientId,
              'access_token': 'website-access',
              'access_expiry': 3600,
              'refresh_token': 'refresh',
              'account': {'pid': 1, 'username': 'player'},
            })
          : null;
  String? value;

  @override
  Future<String?> read() async => value;
  @override
  Future<void> write(String value) async => this.value = value;
  @override
  Future<void> clear() async => value = null;
}

NextendoService _service(http.Client client, {bool signedIn = true}) =>
    NextendoService(
      client: client,
      store: _Store(signedIn: signedIn),
      clock: () => DateTime.fromMillisecondsSinceEpoch(0),
    );

http.Response _answer(Map<String, Object?> body) =>
    http.Response(jsonEncode(body), 200);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('OAuth reads presence for accepted friends only', () async {
    final client = MockClient((request) async {
      expect(request.method, 'GET');
      expect(
        request.url,
        Uri.parse('https://nextendo.network/api/friends?images=0'),
      );
      expect(request.headers['authorization'], 'Bearer website-access');
      return _answer({
        'friends': [
          {
            'name': ' Lila ',
            'presence': {'status': 1},
          },
          {
            'username': 'Sam',
            'presence': {'status': 2},
          },
          {
            'name': 'Offline',
            'presence': {'status': 0},
          },
          {'name': 'Hidden', 'presence': null},
        ],
        'requests': [
          {
            'name': 'Pending',
            'presence': {'status': 1},
          },
        ],
      });
    });
    addTearDown(client.close);

    expect(await _service(client).onlineFriends(_config), ['Lila', 'Sam']);
  });

  test('a reply for an account signed out in flight is discarded', () async {
    final sent = Completer<void>();
    final response = Completer<http.Response>();
    final client = MockClient((request) async {
      if (request.url.path == '/api/oauth/revoke') return _answer({});
      sent.complete();
      return response.future;
    });
    addTearDown(client.close);
    final service = _service(client);
    final pending = expectLater(
      service.onlineFriends(_config),
      throwsA(
        isA<NextendoException>().having(
          (error) => error.code,
          'code',
          'signedOut',
        ),
      ),
    );
    await sent.future;
    await service.signOut(_config);
    response.complete(_answer({'friends': []}));
    await pending;
  });

  Future<void> mount(WidgetTester tester, NextendoService service) async {
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        builder: (context, _) => MaterialApp(
          home: Scaffold(
            body: Center(child: NextendoFriendsButton(service: service)),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('opens and refreshes the live list only on request', (
    tester,
  ) async {
    var calls = 0;
    final client = MockClient((_) async {
      calls++;
      if (calls == 1) return _answer({'friends': []});
      if (calls == 2) return http.Response('', 503);
      return _answer({
        'friends': [
          {
            'name': 'Lila',
            'presence': {'status': 2},
          },
          {
            'name': 'Hidden',
            'presence': {'status': 0},
          },
        ],
      });
    });
    addTearDown(client.close);
    await mount(tester, _service(client));
    expect(calls, 0);
    await tester.tap(find.byType(NextendoFriendsButton));
    await tester.pumpAndSettle();
    expect(find.text('No Nextendo friends are online.'), findsOneWidget);

    await tester.tap(find.text('Refresh'));
    await tester.pumpAndSettle();
    expect(find.text('Nextendo is temporarily unavailable.'), findsOneWidget);

    await tester.tap(find.text('Refresh'));
    await tester.pumpAndSettle();
    expect(find.text('Lila'), findsOneWidget);
    expect(find.text('Hidden'), findsNothing);
    expect(calls, 3);
  });

  testWidgets('offers sign-in when there is no account', (tester) async {
    final client = MockClient(
      (_) async => throw StateError('Unexpected request'),
    );
    addTearDown(client.close);
    await mount(tester, _service(client, signedIn: false));
    await tester.tap(find.byType(NextendoFriendsButton));
    await tester.pumpAndSettle();
    expect(find.text('Sign in with Nextendo'), findsOneWidget);
  });
}
