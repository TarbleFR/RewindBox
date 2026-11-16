import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:neo_texture_catalog/neo_texture_catalog.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

import '../l10n/catalogue_update_locale.dart';
import 'enhancements/enhancement_catalog.dart';
import 'global_notification_service.dart';
import 'logger_service.dart';

/// The catalogues the app can bring up to date by itself, from a page the
/// user opens. The unified cheats and the shader presets are bundled with the
/// app: a newer version of those arrives with an app update, not here.
enum UpdatableCatalogue { enhancements, hdTextures }

/// One revision of a catalogue: as the app holds it, or as it is published.
@immutable
class CatalogueRevision {
  const CatalogueRevision({required this.revision, this.date = '', this.count = 0, this.url = ''});

  final String revision;

  /// Day of the publication (HD textures: `generated_at`).
  final String date;

  /// Entries (enhancements) or packs (HD textures).
  final int count;

  /// Where the published version is read (enhancements: the folder of the
  /// app's own revision, which serves the newest index of its record format).
  final String url;

  Map<String, Object?> toJson() => {
    'revision': revision,
    if (date.isNotEmpty) 'date': date,
    'count': count,
    if (url.isNotEmpty) 'url': url,
  };

  static CatalogueRevision? fromJson(Object? json) {
    if (json is! Map) return null;
    final revision = json['revision'];
    if (revision is! String || revision.isEmpty) return null;
    final count = json['count'];
    return CatalogueRevision(
      revision: revision,
      date: json['date'] is String ? json['date'] as String : '',
      count: count is int ? count : 0,
      url: json['url'] is String ? json['url'] as String : '',
    );
  }
}

/// Answer of a conditional request: [notModified], or the body and its ETag.
@immutable
class CatalogueResponse {
  const CatalogueResponse.notModified() : notModified = true, bytes = null, etag = null;
  const CatalogueResponse.body(Uint8List this.bytes, this.etag) : notModified = false;

  final bool notModified;
  final Uint8List? bytes;
  final String? etag;
}

typedef CatalogueFetch = Future<CatalogueResponse> Function(Uri uri, {String? etag, required int limit});

/// Announces in the notification bell that a newer catalogue is published.
///
/// Light by design: the first check waits [firstCheckDelay] after launch; the
/// network is read at most once every [checkEvery] (again after
/// [retryAfterFailure] when offline), with a conditional request (the ETag of
/// the last answer), so an unchanged catalogue costs a `304 Not Modified` and
/// no body. A changed one is read once and only its revision and size are
/// kept; nothing is installed or replaced. The user brings a catalogue up to
/// date from its own page, which this notification names.
///
/// A notification the user dismisses stays dismissed for the revisions it
/// announced; it comes back only for a later publication.
class CatalogueUpdateService with WidgetsBindingObserver {
  CatalogueUpdateService({
    Future<CatalogueRevision?> Function()? localEnhancements,
    Future<CatalogueRevision?> Function()? localTextures,
    CatalogueFetch? fetch,
    Future<File> Function()? stateFile,
    DateTime Function()? now,
    GlobalNotificationService? notifications,
  }) : _localEnhancements = localEnhancements ?? _readLocalEnhancements,
       _localTextures = localTextures ?? _readLocalTextures,
       _fetch = fetch ?? httpFetch,
       _stateFile = stateFile ?? _defaultStateFile,
       _now = now ?? DateTime.now,
       _notifications = notifications ?? GlobalNotificationService();

  static final CatalogueUpdateService instance = CatalogueUpdateService();

  /// Id of the bell notification.
  static const notificationId = 'catalogue-updates';
  static const firstCheckDelay = Duration(seconds: 90);
  static const checkEvery = Duration(hours: 24);
  static const retryAfterFailure = Duration(hours: 6);

  /// Same address as NeoTextureCatalog.m (`_manifestURL`).
  static final hdTexturesManifest = Uri.parse(
    'https://raw.githubusercontent.com/TarbleFR/RewindBox/Claude/native/textures/catalogue/manifest.json.gz',
  );

  static const _maxPacked = 4 << 20;
  static const _maxExpanded = 32 << 20;

  final Future<CatalogueRevision?> Function() _localEnhancements;
  final Future<CatalogueRevision?> Function() _localTextures;
  final CatalogueFetch _fetch;
  final Future<File> Function() _stateFile;
  final DateTime Function() _now;
  final GlobalNotificationService _notifications;
  final _log = LoggerService.instance;

  Timer? _timer;
  bool _started = false;
  bool _firstCheckDone = false;
  Future<void>? _running;

  /// The state file, read once; every change goes through it, and writes are
  /// chained so a dismissal and a check never overwrite each other.
  _State? _cache;
  Future<void> _writing = Future.value();

  /// Revisions the notification on screen announces, by catalogue.
  Map<UpdatableCatalogue, String> _shown = const {};
  bool _withdrawing = false;

  /// Schedules the checks. Called once, after the first frame.
  void start() {
    if (_started) return;
    _started = true;
    WidgetsBinding.instance.addObserver(this);
    _notifications.notifier.addListener(_watchDismissal);
    _timer = Timer(firstCheckDelay, () {
      _firstCheckDone = true;
      unawaited(check());
      // Each tick costs nothing unless a check is due or a notification waits.
      _timer = Timer.periodic(const Duration(hours: 1), (_) => unawaited(check()));
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _firstCheckDone) unawaited(check());
  }

  /// Compares the published catalogues with the app's and updates the bell.
  /// The network is read only when a check is due (or [force]); [reread]
  /// reads the app's own catalogues again after a page changed them.
  Future<void> check({bool force = false, bool reread = false}) =>
      _running ??= _check(force, reread).whenComplete(() => _running = null);

  Future<void> _check(bool force, bool reread) async {
    final state = await _state();
    final now = _now();
    final due = force || _isDue(state, now);
    var changed = false;

    for (final catalogue in UpdatableCatalogue.values) {
      final remote = state.remote[catalogue];
      final known = state.local[catalogue];
      // The app's own revision is read when it matters: for a network check,
      // when none is known yet, or while a newer publication waits (the user
      // may have brought the catalogue up to date since).
      if (!due && !reread && known != null && (remote == null || !_isNewer(catalogue, remote, known))) continue;
      CatalogueRevision? local;
      try {
        local = await (catalogue == UpdatableCatalogue.enhancements ? _localEnhancements() : _localTextures());
      } catch (error) {
        _log.d('Catalogue updates: ${catalogue.name} not readable here: $error');
      }
      if (local == null) {
        changed |= state.local.remove(catalogue) != null;
      } else if (known?.revision != local.revision || known?.url != local.url || known?.count != local.count) {
        state.local[catalogue] = local;
        changed = true;
      }
    }

    if (due) {
      var failed = false;
      for (final catalogue in UpdatableCatalogue.values) {
        final local = state.local[catalogue];
        if (local == null) continue;
        final uri = catalogue == UpdatableCatalogue.enhancements
            ? Uri.parse(local.url).resolve('index.json.gz')
            : hdTexturesManifest;
        try {
          final previous = state.remote[catalogue];
          final sameUrl = state.etags[catalogue]?.url == uri.toString();
          final response = await _fetch(
            uri,
            etag: sameUrl && previous != null ? state.etags[catalogue]?.etag : null,
            limit: _maxPacked,
          );
          if (response.notModified && sameUrl && previous != null) continue;
          final bytes = response.bytes;
          if (bytes == null) throw const FormatException('empty answer');
          final summary = await compute(_summarize, _SummaryRequest(catalogue, bytes));
          state.remote[catalogue] = summary;
          state.etags[catalogue] = (url: uri.toString(), etag: response.etag ?? '');
        } catch (error) {
          failed = true;
          _log.w('Catalogue updates: ${catalogue.name} check failed: $error');
        }
      }
      if (failed) {
        state.failedAt = now;
      } else {
        state.checkedAt = now;
        state.failedAt = null;
      }
      changed = true;
    }

    if (changed) await _save();
    _publish(state);
  }

  bool _isDue(_State state, DateTime now) {
    final failed = state.failedAt;
    if (failed != null && now.difference(failed) < retryAfterFailure) return false;
    final checked = state.checkedAt;
    return checked == null || now.difference(checked) >= checkEvery || failed != null;
  }

  /// Whether [remote] is a later publication than the app's [local] copy,
  /// by the rule the catalogue itself applies when it refreshes.
  static bool _isNewer(UpdatableCatalogue catalogue, CatalogueRevision remote, CatalogueRevision local) =>
      switch (catalogue) {
        // EnhancementCatalog.refresh: revisions start with the UTC date and time.
        UpdatableCatalogue.enhancements => remote.revision.compareTo(local.revision) > 0,
        // NeoTextureCatalog: a revision is a content digest; the newer day wins.
        UpdatableCatalogue.hdTextures =>
          remote.revision != local.revision && remote.date.compareTo(local.date) >= 0,
      };

  void _publish(_State state) {
    final fresh = <UpdatableCatalogue, CatalogueRevision>{};
    for (final catalogue in UpdatableCatalogue.values) {
      final remote = state.remote[catalogue], local = state.local[catalogue];
      if (remote == null || local == null || !_isNewer(catalogue, remote, local)) continue;
      if (state.dismissed[catalogue] == remote.revision) continue;
      fresh[catalogue] = remote;
    }
    if (fresh.isEmpty) {
      if (_shown.isNotEmpty) {
        _shown = const {};
        _withdrawing = true;
        _notifications.dismiss(notificationId);
        _withdrawing = false;
      }
      return;
    }
    int? added(UpdatableCatalogue catalogue) {
      final remote = fresh[catalogue];
      if (remote == null) return null;
      return remote.count - (state.local[catalogue]?.count ?? 0);
    }

    final shown = {for (final entry in fresh.entries) entry.key: entry.value.revision};
    final onScreen = _notifications.notifier.value.any((notification) => notification.id == notificationId);
    // Already listed for the same revisions: left in place, not moved to the end.
    if (onScreen && mapEquals(shown, _shown)) return;
    _shown = shown;
    _notifications.show(
      id: notificationId,
      title: CatalogueUpdateLocale.title(),
      message: CatalogueUpdateLocale.message(
        enhancementsAdded: added(UpdatableCatalogue.enhancements),
        texturesAdded: added(UpdatableCatalogue.hdTextures),
      ),
      icon: Icons.system_update_alt,
      type: GlobalNotificationType.info,
    );
  }

  /// The user dismissed the notification (or cleared all): remember the
  /// revisions it announced so it does not come back for them.
  void _watchDismissal() {
    if (_withdrawing || _shown.isEmpty) return;
    if (_notifications.notifier.value.any((notification) => notification.id == notificationId)) return;
    final dismissed = _shown;
    _shown = const {};
    unawaited(() async {
      (await _state()).dismissed.addAll(dismissed);
      await _save();
    }());
  }

  // ------------------------------------------------------------ the app's catalogues

  static Future<CatalogueRevision?> _readLocalEnhancements() async {
    final index = await EnhancementCatalog.instance.index();
    return CatalogueRevision(revision: index.revision, count: _entryCount(index.totals), url: index.baseUrl);
  }

  static Future<CatalogueRevision?> _readLocalTextures() async {
    if (!Platform.isIOS) return null;
    final snapshot = await NeoTextureCatalog.snapshot();
    final revision = snapshot['revision'];
    if (revision is! String || revision.isEmpty) return null;
    final count = snapshot['pack_count'];
    return CatalogueRevision(
      revision: revision,
      date: snapshot['generated_at']?.toString() ?? '',
      count: count is int ? count : 0,
    );
  }

  static int _entryCount(Map<String, dynamic> totals) {
    var count = 0;
    for (final engine in totals.values) {
      final entries = engine is Map ? engine['entries'] : null;
      if (entries is! Map) continue;
      for (final value in entries.values) {
        if (value is int) count += value;
      }
    }
    return count;
  }

  // ------------------------------------------------------------ published catalogues

  /// Revision, day and size of a published catalogue (run in an isolate: the
  /// HD textures manifest expands to a few megabytes).
  static CatalogueRevision _summarize(_SummaryRequest request) {
    if (request.bytes.length > _maxPacked) throw const FormatException('too large');
    final expanded = GZipCodec().decode(request.bytes);
    if (expanded.length > _maxExpanded) throw const FormatException('too large');
    final json = jsonDecode(utf8.decode(expanded));
    if (json is! Map) throw const FormatException('not an object');
    final revision = json['revision'];
    if (revision is! String || revision.isEmpty) throw const FormatException('no revision');
    switch (request.catalogue) {
      case UpdatableCatalogue.enhancements:
        if (json['catalogue'] != 'rewindbox-enhancements') throw const FormatException('not the enhancements index');
        final totals = json['totals'];
        return CatalogueRevision(
          revision: revision,
          count: totals is Map ? _entryCount(Map<String, dynamic>.from(totals)) : 0,
        );
      case UpdatableCatalogue.hdTextures:
        if (json['catalogue_id'] != 'neostation-hd-textures') throw const FormatException('not the HD manifest');
        final packs = json['packs'];
        return CatalogueRevision(
          revision: revision,
          date: json['generated_at']?.toString() ?? '',
          count: packs is List ? packs.length : 0,
        );
    }
  }

  /// HTTPS GET with `If-None-Match`, a hard size limit and timeouts.
  static Future<CatalogueResponse> httpFetch(Uri uri, {String? etag, required int limit}) async {
    if (uri.scheme != 'https') throw const FormatException('insecure url');
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 20)
      ..idleTimeout = const Duration(seconds: 20);
    try {
      final request = await client.getUrl(uri);
      if (etag != null && etag.isNotEmpty) request.headers.set(HttpHeaders.ifNoneMatchHeader, etag);
      final response = await request.close().timeout(const Duration(seconds: 60));
      if (response.statusCode == HttpStatus.notModified) {
        await response.drain<void>();
        return const CatalogueResponse.notModified();
      }
      if (response.statusCode != HttpStatus.ok) throw HttpException('HTTP ${response.statusCode}', uri: uri);
      if (response.contentLength > limit) throw const FormatException('too large');
      final builder = BytesBuilder(copy: false);
      await for (final chunk in response.timeout(const Duration(seconds: 60))) {
        builder.add(chunk);
        if (builder.length > limit) throw const FormatException('too large');
      }
      return CatalogueResponse.body(builder.takeBytes(), response.headers.value(HttpHeaders.etagHeader));
    } finally {
      client.close(force: true);
    }
  }

  // ------------------------------------------------------------ state

  static Future<File> _defaultStateFile() async {
    final support = await getApplicationSupportDirectory();
    return File(path.join(support.path, 'RewindBox', 'Catalogues', 'updates.json'));
  }

  Future<_State> _state() async => _cache ??= await _readState();

  Future<void> _save() {
    final state = _cache;
    if (state == null) return Future.value();
    return _writing = _writing.then((_) => _writeState(state));
  }

  Future<_State> _readState() async {
    try {
      final file = await _stateFile();
      if (await file.exists() && await file.length() < 65536) {
        final json = jsonDecode(await file.readAsString());
        if (json is Map) return _State.fromJson(json);
      }
    } catch (error) {
      _log.w('Catalogue updates: state ignored: $error');
    }
    return _State();
  }

  Future<void> _writeState(_State state) async {
    try {
      final file = await _stateFile();
      await file.parent.create(recursive: true);
      final temporary = File('${file.path}.partial');
      await temporary.writeAsString(jsonEncode(state.toJson()), flush: true);
      await temporary.rename(file.path);
    } catch (error) {
      _log.w('Catalogue updates: state not saved: $error');
    }
  }

  /// Test hook: forgets the notification on screen and stops the timers.
  @visibleForTesting
  void debugReset() {
    _timer?.cancel();
    _timer = null;
    if (_started) {
      WidgetsBinding.instance.removeObserver(this);
      _notifications.notifier.removeListener(_watchDismissal);
    }
    _started = false;
    _firstCheckDone = false;
    _shown = const {};
    _cache = null;
  }

  /// Test hook: the notification listener, without [start].
  @visibleForTesting
  void debugWatchDismissal() => _notifications.notifier.addListener(_watchDismissal);
}

class _SummaryRequest {
  const _SummaryRequest(this.catalogue, this.bytes);
  final UpdatableCatalogue catalogue;
  final Uint8List bytes;
}

class _State {
  _State();

  DateTime? checkedAt;
  DateTime? failedAt;
  final Map<UpdatableCatalogue, CatalogueRevision> local = {};
  final Map<UpdatableCatalogue, CatalogueRevision> remote = {};
  final Map<UpdatableCatalogue, ({String url, String etag})> etags = {};
  final Map<UpdatableCatalogue, String> dismissed = {};

  static DateTime? _time(Object? value) =>
      value is int ? DateTime.fromMillisecondsSinceEpoch(value * 1000, isUtc: true) : null;

  factory _State.fromJson(Map<dynamic, dynamic> json) {
    final state = _State()
      ..checkedAt = _time(json['checked_at'])
      ..failedAt = _time(json['failed_at']);
    final catalogues = json['catalogues'];
    if (catalogues is Map) {
      for (final catalogue in UpdatableCatalogue.values) {
        final entry = catalogues[catalogue.name];
        if (entry is! Map) continue;
        final local = CatalogueRevision.fromJson(entry['local']);
        final remote = CatalogueRevision.fromJson(entry['remote']);
        if (local != null) state.local[catalogue] = local;
        if (remote != null) state.remote[catalogue] = remote;
        if (entry['url'] is String && entry['etag'] is String) {
          state.etags[catalogue] = (url: entry['url'] as String, etag: entry['etag'] as String);
        }
        if (entry['dismissed'] is String) state.dismissed[catalogue] = entry['dismissed'] as String;
      }
    }
    return state;
  }

  Map<String, Object?> toJson() {
    int? seconds(DateTime? time) => time == null ? null : time.millisecondsSinceEpoch ~/ 1000;
    return {
      'schema': 1,
      if (checkedAt != null) 'checked_at': seconds(checkedAt),
      if (failedAt != null) 'failed_at': seconds(failedAt),
      'catalogues': {
        for (final catalogue in UpdatableCatalogue.values)
          catalogue.name: {
            if (local[catalogue] != null) 'local': local[catalogue]!.toJson(),
            if (remote[catalogue] != null) 'remote': remote[catalogue]!.toJson(),
            if (etags[catalogue] != null) 'url': etags[catalogue]!.url,
            if (etags[catalogue] != null) 'etag': etags[catalogue]!.etag,
            if (dismissed[catalogue] != null) 'dismissed': dismissed[catalogue],
          },
      },
    };
  }
}
