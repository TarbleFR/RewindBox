import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:neostation/services/library_http.dart';

/// Canned answer of [FakeLibraryFetcher] for one URL.
class FakeRoute {
  FakeRoute.bytes(
    this.body, {
    this.finalUri,
    this.headers = const <String, String>{},
    this.notModifiedOnRefresh = false,
  }) : error = null,
       statusCode = 200;

  FakeRoute.json(
    Object? value, {
    Uri? finalUri,
    bool notModifiedOnRefresh = false,
  }) : this.bytes(
         Uint8List.fromList(utf8.encode(jsonEncode(value))),
         finalUri: finalUri,
         notModifiedOnRefresh: notModifiedOnRefresh,
       );

  FakeRoute.text(String value, {Uri? finalUri})
    : this.bytes(Uint8List.fromList(utf8.encode(value)), finalUri: finalUri);

  FakeRoute.fixture(
    String name, {
    Uri? finalUri,
    bool notModifiedOnRefresh = false,
  }) : this.bytes(
         File('test/fixtures/library_catalog/$name').readAsBytesSync(),
         finalUri: finalUri,
         notModifiedOnRefresh: notModifiedOnRefresh,
       );

  FakeRoute.failure(LibraryNetworkErrorKind kind, {this.statusCode = 0})
    : error = kind,
      body = Uint8List(0),
      finalUri = null,
      headers = const <String, String>{},
      notModifiedOnRefresh = false;

  final Uint8List body;
  final Uri? finalUri;
  final Map<String, String> headers;
  final LibraryNetworkErrorKind? error;
  final int statusCode;

  /// Simulates a server answering 304 to a conditional refresh.
  final bool notModifiedOnRefresh;
}

class FakeFetchCall {
  const FakeFetchCall(this.request, this.mode);

  final LibraryRequest request;
  final LibraryFetchMode mode;

  String get url => request.uri.toString();
}

/// Offline [LibraryFetcher]: unknown URLs answer 404 like `LibraryHttp`.
class FakeLibraryFetcher {
  FakeLibraryFetcher([Map<String, FakeRoute>? routes])
    : routes = routes ?? <String, FakeRoute>{};

  final Map<String, FakeRoute> routes;
  final List<FakeFetchCall> calls = <FakeFetchCall>[];
  int _sequence = 0;

  List<String> get urls => calls.map((call) => call.url).toList();

  Future<LibraryHttpResponse> call(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    calls.add(FakeFetchCall(request, mode));
    final sequence = ++_sequence;
    cancel?.throwIfCancelled(request.uri);
    final route = routes[request.uri.toString()];
    if (route == null) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.notFound,
        uri: request.uri,
        statusCode: 404,
      );
    }
    final error = route.error;
    if (error != null) {
      throw LibraryNetworkException(
        error,
        uri: request.uri,
        statusCode: route.statusCode == 0 ? null : route.statusCode,
      );
    }
    final maxBytes = request.maxBytes ?? LibraryHttp.defaultMaxBytes;
    if (route.body.length > maxBytes) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.tooLarge,
        uri: request.uri,
      );
    }
    final revalidated =
        mode == LibraryFetchMode.refresh && route.notModifiedOnRefresh;
    return LibraryHttpResponse(
      request: request,
      statusCode: 200,
      bodyBytes: route.body,
      headers: route.headers,
      finalUri: route.finalUri ?? request.uri,
      fetchedAt: DateTime.utc(2026, 10, 10, 12, sequence),
      fromCache: revalidated,
      revalidated: revalidated,
    );
  }
}

/// Minimal PNG signature + header bytes used as an icon.
final Uint8List fakePngBytes = Uint8List.fromList(<int>[
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, //
  0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
]);

/// Builds an Aidoku `.aix` (ZIP with a `Payload/` folder). `main.wasm` holds
/// bytes that are not a runnable module: the importer must never need them.
Uint8List buildAix({
  required Map<String, dynamic> sourceJson,
  String iconName = 'Icon.png',
  Uint8List? icon,
  bool storeSourceJson = false,
  String? rawSourceJson,
}) {
  final archive = Archive();
  archive.addFile(
    ArchiveFile.bytes(
      'Payload/main.wasm',
      Uint8List.fromList(<int>[0x00, 0x61, 0x73, 0x6d, 0xde, 0xad, 0xbe, 0xef]),
    ),
  );
  final sourceBytes = utf8.encode(rawSourceJson ?? jsonEncode(sourceJson));
  archive.addFile(
    storeSourceJson
        ? ArchiveFile.noCompress(
            'Payload/source.json',
            sourceBytes.length,
            sourceBytes,
          )
        : ArchiveFile.bytes('Payload/source.json', sourceBytes),
  );
  archive.addFile(ArchiveFile.bytes('Payload/$iconName', icon ?? fakePngBytes));
  archive.addFile(ArchiveFile.string('Payload/filters.json', '[]'));
  return ZipEncoder().encodeBytes(archive);
}

/// Rewrites the declared uncompressed size of [entryName] in both the local
/// and the central ZIP headers (simulates a lying archive).
Uint8List patchDeclaredSize(Uint8List zip, String entryName, int size) {
  final bytes = Uint8List.fromList(zip);
  final data = ByteData.sublistView(bytes);
  final name = utf8.encode(entryName);
  bool nameAt(int offset) {
    if (offset + name.length > bytes.length) return false;
    for (var i = 0; i < name.length; i++) {
      if (bytes[offset + i] != name[i]) return false;
    }
    return true;
  }

  for (var offset = 0; offset + 46 <= bytes.length; offset++) {
    final signature = data.getUint32(offset, Endian.little);
    if (signature == 0x04034b50) {
      final nameLength = data.getUint16(offset + 26, Endian.little);
      if (nameLength == name.length && nameAt(offset + 30)) {
        data.setUint32(offset + 22, size, Endian.little);
      }
    } else if (signature == 0x02014b50) {
      final nameLength = data.getUint16(offset + 28, Endian.little);
      if (nameLength == name.length && nameAt(offset + 46)) {
        data.setUint32(offset + 24, size, Endian.little);
      }
    }
  }
  return bytes;
}

const String frenchRawDirectory =
    'https://raw.githubusercontent.com/Moomooo95/aidoku-french-sources/gh-pages/';
const String frenchRawIndex = '${frenchRawDirectory}index.min.json';
const String communityIndex =
    'https://aidoku-community.github.io/sources/index.min.json';
