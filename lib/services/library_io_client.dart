import 'dart:async';
import 'dart:io';

import 'package:http/http.dart' as http;

/// dart:io transport of the reading Library.
///
/// It behaves like package:http's `IOClient`, except for aborting: when an
/// [http.Abortable] request is aborted, the connection is closed whatever
/// the moment. `IOClient` relies on `HttpClientRequest.abort`, which does
/// nothing once dart:io has received the response headers; if the abort
/// lands after that but before the response body is listened to (one
/// asynchronous step inside `IOClient`, or the caller's own steps), the
/// `HttpClientResponse` is never listened to nor cancelled and its socket
/// stays open, counted against `HttpClient.maxConnectionsPerHost`. Here the
/// response is drained-cancelled as soon as the abort is known, which makes
/// dart:io destroy the connection.
class LibraryIoClient extends http.BaseClient {
  LibraryIoClient(HttpClient inner) : _inner = inner;

  HttpClient? _inner;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final inner = _inner;
    if (inner == null) {
      throw http.ClientException(
        'HTTP request failed. Client is already closed.',
        request.url,
      );
    }
    final body = request.finalize();
    final trigger = request is http.Abortable ? request.abortTrigger : null;

    var aborted = false;
    HttpClientRequest? ioRequest;
    HttpClientResponse? ioResponse;
    StreamSubscription<List<int>>? subscription;
    StreamController<List<int>>? controller;
    var consumed = false;

    void destroy(HttpClientResponse response) {
      if (consumed) return;
      consumed = true;
      // Cancelling an unfinished response makes dart:io destroy the socket.
      response.listen(null, onError: (Object _) {}).cancel().ignore();
    }

    void failController() {
      final active = controller;
      if (active != null && !active.isClosed) {
        active
          ..addError(http.RequestAbortedException(request.url))
          ..close();
      }
    }

    if (trigger != null) {
      unawaited(
        trigger.whenComplete(() {
          aborted = true;
          final response = ioResponse;
          if (response == null) {
            // Effective until dart:io has the response headers; later the
            // response is destroyed below, once it is known.
            ioRequest?.abort(http.RequestAbortedException(request.url));
            return;
          }
          final active = subscription;
          if (active == null) {
            destroy(response);
          } else {
            active.cancel().ignore();
          }
          failController();
        }),
      );
    }

    try {
      final opened = await inner.openUrl(request.method, request.url);
      ioRequest = opened;
      opened
        ..followRedirects = request.followRedirects
        ..maxRedirects = request.maxRedirects
        ..contentLength = request.contentLength ?? -1
        ..persistentConnection = request.persistentConnection;
      request.headers.forEach(opened.headers.set);
      if (aborted) {
        opened.abort(http.RequestAbortedException(request.url));
      }
      final response = await body.pipe(opened) as HttpClientResponse;
      ioResponse = response;
      if (aborted) {
        // The abort came while dart:io completed the response.
        destroy(response);
        throw http.RequestAbortedException(request.url);
      }

      late final StreamController<List<int>> responseController;
      responseController = StreamController<List<int>>(
        sync: true,
        onListen: () {
          if (aborted || consumed) {
            failController();
            return;
          }
          consumed = true;
          subscription = response.listen(
            responseController.add,
            onDone: () {
              subscription = null;
              unawaited(responseController.close());
            },
            onError: (Object error, StackTrace stackTrace) {
              if (error is HttpException) {
                responseController.addError(
                  http.ClientException(error.message, error.uri),
                  stackTrace,
                );
              } else {
                responseController.addError(error, stackTrace);
              }
            },
          );
        },
        onPause: () => subscription?.pause(),
        onResume: () => subscription?.resume(),
        onCancel: () {
          final active = subscription;
          subscription = null;
          return active?.cancel();
        },
      );
      controller = responseController;

      final headers = <String, String>{};
      response.headers.forEach((key, values) {
        headers[key] = values.map((value) => value.trimRight()).join(',');
      });
      return LibraryIoStreamedResponse(
        responseController.stream,
        response.statusCode,
        url: response.redirects.isNotEmpty
            ? response.redirects.last.location
            : request.url,
        contentLength: response.contentLength == -1
            ? null
            : response.contentLength,
        request: request,
        headers: headers,
        isRedirect: response.isRedirect,
        persistentConnection: response.persistentConnection,
        reasonPhrase: response.reasonPhrase,
      );
    } on SocketException catch (error) {
      if (aborted) throw http.RequestAbortedException(request.url);
      throw http.ClientException(error.message, request.url);
    } on HttpException catch (error) {
      if (aborted) throw http.RequestAbortedException(request.url);
      throw http.ClientException(error.message, error.uri);
    }
  }

  @override
  void close() {
    _inner?.close(force: true);
    _inner = null;
  }
}

/// Streamed response that also reports the URL after redirects.
class LibraryIoStreamedResponse extends http.StreamedResponse
    implements http.BaseResponseWithUrl {
  LibraryIoStreamedResponse(
    super.stream,
    super.statusCode, {
    required this.url,
    super.contentLength,
    super.request,
    super.headers,
    super.isRedirect,
    super.persistentConnection,
    super.reasonPhrase,
  });

  @override
  final Uri url;
}
