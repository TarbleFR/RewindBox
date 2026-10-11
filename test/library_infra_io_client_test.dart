import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'package:neostation/services/library_io_client.dart';

/// A request aborted after dart:io received the response headers, but before
/// the body is listened to, must still close its connection. package:http's
/// IOClient leaves that response unconsumed (its socket stays open and keeps
/// a slot of HttpClient.maxConnectionsPerHost); LibraryIoClient does not.
void main() {
  late HttpServer server;
  late Completer<void> streaming;

  Future<void> waitFor(bool Function() condition, Duration timeout) async {
    final deadline = DateTime.now().add(timeout);
    while (!condition()) {
      if (DateTime.now().isAfter(deadline)) {
        throw TimeoutException('condition not reached');
      }
      await Future<void>.delayed(const Duration(milliseconds: 5));
    }
  }

  setUp(() async {
    streaming = Completer<void>();
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((request) async {
      final response = request.response
        ..bufferOutput = false
        ..headers.contentType = ContentType.text;
      final deadline = DateTime.now().add(const Duration(seconds: 4));
      while (DateTime.now().isBefore(deadline)) {
        try {
          response.add(utf8.encode('chunk\n'));
          await response.flush();
        } catch (_) {
          return;
        }
        if (!streaming.isCompleted) streaming.complete();
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
      await response.close();
    });
  });

  tearDown(() => server.close(force: true));

  Uri url() => Uri.parse('http://127.0.0.1:${server.port}/stream');

  /// Aborts once the response is returned and only then listens to it, as a
  /// caller does when the cancel arrives between two of its own steps.
  Future<void> abortBeforeListening(http.Client client) async {
    final trigger = Completer<void>();
    final request = http.AbortableRequest(
      'GET',
      url(),
      abortTrigger: trigger.future,
    );
    final response = await client.send(request);
    await streaming.future.timeout(const Duration(seconds: 2));
    trigger.complete();
    await Future<void>.delayed(Duration.zero);
    await expectLater(
      response.stream.drain<void>(),
      throwsA(isA<http.RequestAbortedException>()),
    );
  }

  test(
    'LibraryIoClient closes a connection aborted before its body is read',
    () async {
      final client = LibraryIoClient(HttpClient());
      addTearDown(client.close);
      await abortBeforeListening(client);
      await waitFor(
        () => server.connectionsInfo().total == 0,
        const Duration(seconds: 2),
      );
    },
  );

  test('package:http IOClient leaves that connection open (reason for '
      'LibraryIoClient)', () async {
    final client = IOClient(HttpClient());
    addTearDown(client.close);
    await abortBeforeListening(client);
    await Future<void>.delayed(const Duration(milliseconds: 600));
    expect(server.connectionsInfo().total, 1);
  });

  test(
    'LibraryIoClient closes a connection aborted while the body streams',
    () async {
      final client = LibraryIoClient(HttpClient());
      addTearDown(client.close);
      final trigger = Completer<void>();
      final response = await client.send(
        http.AbortableRequest('GET', url(), abortTrigger: trigger.future),
      );
      final done = response.stream.drain<void>();
      await streaming.future.timeout(const Duration(seconds: 2));
      trigger.complete();
      await expectLater(done, throwsA(isA<http.RequestAbortedException>()));
      await waitFor(
        () => server.connectionsInfo().total == 0,
        const Duration(seconds: 2),
      );
    },
  );

  test(
    'LibraryIoClient reports the URL after redirects and plain bodies',
    () async {
      final redirecting = await HttpServer.bind(
        InternetAddress.loopbackIPv4,
        0,
      );
      addTearDown(() => redirecting.close(force: true));
      redirecting.listen((request) async {
        if (request.uri.path == '/old') {
          request.response
            ..statusCode = HttpStatus.movedPermanently
            ..headers.set(HttpHeaders.locationHeader, '/new');
        } else {
          request.response.write('new body');
        }
        await request.response.close();
      });
      final client = LibraryIoClient(HttpClient());
      addTearDown(client.close);
      final response = await client.send(
        http.Request(
          'GET',
          Uri.parse('http://127.0.0.1:${redirecting.port}/old'),
        ),
      );
      expect(response, isA<http.BaseResponseWithUrl>());
      expect((response as http.BaseResponseWithUrl).url.path, '/new');
      expect(await response.stream.bytesToString(), 'new body');
    },
  );
}
