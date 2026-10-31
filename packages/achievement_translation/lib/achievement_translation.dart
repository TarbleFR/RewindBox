import 'dart:async';
import 'dart:collection';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

@immutable
class AchievementSource {
  const AchievementSource({required this.id, required this.title, required this.description});
  final int id;
  final String title;
  final String description;
  (int, String, String) get key => (id, title, description);
  Map<String, Object> toMap() => {'id': id, 'title': title, 'description': description};
}

@immutable
class AchievementDisplayText {
  const AchievementDisplayText({required this.title, required this.description,
    required this.provenance, this.fallback});
  final String title;
  final String description;
  final String provenance;
  final String? fallback;
  @override
  bool operator ==(Object other) => other is AchievementDisplayText &&
      title == other.title && description == other.description &&
      provenance == other.provenance && fallback == other.fallback;
  @override
  int get hashCode => Object.hash(title, description, provenance, fallback);
}

/// Mirrors the existing app setting; it has no preferences, login or RA client.
/// Source models stay untouched. All engines use the same native Swift cache.
class AchievementTranslationClient extends ChangeNotifier {
  AchievementTranslationClient({MethodChannel? channel, bool? enabled})
      : _channel = channel ?? const MethodChannel('rewindbox/achievement_translation'),
        _enabled = enabled ?? (!kIsWeb && defaultTargetPlatform == TargetPlatform.iOS) {
    if (_enabled) _channel.setMethodCallHandler(_onNativeEvent);
  }
  static final shared = AchievementTranslationClient();
  final MethodChannel _channel;
  final bool _enabled;
  String _language = 'en';
  String get language => _language;
  int _generation = 0;
  int _languageWrites = 0;
  bool _disposed = false;
  bool _scheduled = false;
  bool _fetching = false;
  bool _available = true;
  Future<void> _languageReady = Future<void>.value();
  final _known = LinkedHashMap<(int, String, String), AchievementSource>();
  final _cache = <(int, String, String), AchievementDisplayText>{};
  final _pending = <(int, String, String)>{};

  Future<void> setLanguage(String appCode) async {
    if (_disposed) return;
    _language = appCode;
    _generation++;
    final requestedGeneration = _generation;
    _cache.clear();
    _available = true;
    _pending.addAll(_known.keys);
    if (_enabled) {
      _languageWrites++;
      // Serialize rapid settings changes; the last app choice wins natively too.
      _languageReady = _languageReady.then((_) async {
        try {
          await _channel.invokeMethod<void>('setLanguage', {'language': appCode});
          if (requestedGeneration == _generation) _available = true;
        }
        on MissingPluginException { if (requestedGeneration == _generation) _available = false; }
        on PlatformException { if (requestedGeneration == _generation) _available = false; }
        finally { _languageWrites--; }
      });
    }
    notifyListeners();
    await _languageReady;
    if (!_disposed) { _schedule(); notifyListeners(); }
  }

  /// Read-only mirror for external-display engines; never writes native preferences.
  void followAppLanguage(String appCode) {
    if (_disposed || _language == appCode) return;
    _language = appCode;
    _generation++;
    _cache.clear();
    _pending.addAll(_known.keys);
    _available = true;
    notifyListeners();
    _schedule();
  }

  AchievementDisplayText text(AchievementSource source) {
    final key = source.key;
    if (_known.length >= 4000 && !_known.containsKey(key)) {
      final old = _known.keys.first;
      _known.remove(old); _cache.remove(old); _pending.remove(old);
    }
    _known[key] = source;
    if (_language == 'en') return _original(source, null);
    final cached = _cache[key];
    if (cached != null) return cached;
    if (_enabled && _available && source.id > 0) {
      _pending.add(key);
      _schedule();
      return _original(source, 'pending');
    }
    return _original(source, 'unavailable');
  }

  AchievementDisplayText _original(AchievementSource source, String? reason) =>
      AchievementDisplayText(title: source.title, description: source.description,
          provenance: 'original', fallback: reason);

  Future<void> _onNativeEvent(MethodCall call) async {
    if (_disposed || call.method != 'revision') return;
    final arguments = call.arguments;
    final appLanguage = arguments is Map ? arguments['appLanguage'] : null;
    if (_languageWrites == 0 && appLanguage is String && appLanguage != _language) {
      // A secondary Flutter engine observes the same authority without writing it back.
      _language = appLanguage;
      _generation++;
      _cache.clear();
      notifyListeners();
    }
    _pending.addAll(_known.keys.where((key) =>
      _cache[key] == null || _cache[key]!.provenance == 'original'));
    _schedule();
  }

  void _schedule() {
    if (_scheduled || _fetching || _disposed || !_enabled || !_available || _language == 'en' || _pending.isEmpty) return;
    _scheduled = true;
    scheduleMicrotask(() { _scheduled = false; if (!_disposed) unawaited(_fetch()); });
  }

  Future<void> _fetch() async {
    if (_fetching || _disposed) return;
    _fetching = true;
    try {
      await _languageReady;
      while (!_disposed && _pending.isNotEmpty && _available && _language != 'en') {
        await _languageReady;
        if (_disposed || !_available) return;
        final gen = _generation;
        final keys = _pending.take(100).toList();
        _pending.removeAll(keys);
        final sources = keys.map((key) => _known[key]).whereType<AchievementSource>().toList();
        final rows = await _channel.invokeListMethod<Object?>('texts', {
          'achievements': sources.map((a) => a.toMap()).toList(),
        });
        if (_disposed) return;
        if (gen != _generation) { await _languageReady; continue; }
        var changed = false;
        for (final row in rows ?? const []) {
          if (row is! Map) continue;
          final id = row['id'];
          final title = row['sourceTitle'];
          final description = row['sourceDescription'];
          if (id is! int || title is! String || description is! String) continue;
          final key = (id, title, description);
          if (!_known.containsKey(key)) continue;
          final provenance = row['provenance'];
          if (!const {'original', 'machine', 'official'}.contains(provenance)) continue;
          final text = AchievementDisplayText(title: row['title'] as String? ?? title,
            description: row['description'] as String? ?? description,
            provenance: provenance as String, fallback: row['fallback'] as String?);
          if (_cache[key] != text) { _cache[key] = text; changed = true; }
        }
        if (changed) notifyListeners();
      }
    } on MissingPluginException {
      _available = false;
      _cache.clear();
      if (!_disposed) notifyListeners();
    } on PlatformException {
      _available = false;
      _cache.clear();
      if (!_disposed) notifyListeners();
    } finally {
      _fetching = false;
      _schedule();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    if (_enabled) _channel.setMethodCallHandler(null);
    super.dispose();
  }
}
