import 'dart:async';
import 'package:achievement_translation/achievement_translation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/achievement_translation_locale.dart';
import 'package:neostation/models/secondary_achievement_item.dart';
import 'package:neostation/widgets/translated_achievement_text.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('rewindbox/achievement_translation_test');
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const source = AchievementSource(id: 42, title: 'Éclair 勇者', description: 'إنجاز البداية 🎮');
  var nativeLanguage = 'en';

  setUp(() {
    nativeLanguage = 'en';
    messenger.setMockMethodCallHandler(channel, (call) async {
      final args = call.arguments as Map;
      if (call.method == 'setLanguage') { nativeLanguage = args['language'] as String; return null; }
      if (call.method == 'texts') {
        return (args['achievements'] as List).map((value) {
          final row = value as Map;
          return {'id': row['id'], 'sourceTitle': row['title'], 'sourceDescription': row['description'],
            'title': '[$nativeLanguage] ${row['title']}', 'description': '[$nativeLanguage] ${row['description']}',
            'provenance': 'machine'};
        }).toList();
      }
      return null;
    });
  });
  tearDown(() => messenger.setMockMethodCallHandler(channel, null));

  testWidgets('detect and display every one of the 12 real application languages', (tester) async {
    expect(AppLocale.supportedLanguages.length, 12);
    expect(AchievementTranslationLocale.messages.keys.toSet(), AppLocale.supportedLanguages.keys.toSet());
    final client = AchievementTranslationClient(channel: channel, enabled: true);
    addTearDown(client.dispose);
    for (final code in AppLocale.supportedLanguages.keys) {
      await client.setLanguage(code);
      await tester.pumpWidget(MaterialApp(home: Scaffold(body: TranslatedAchievementText(
        id: source.id, title: source.title, description: source.description, client: client))));
      await tester.pumpAndSettle();
      expect(find.text(code == 'en' ? source.title : '[$code] ${source.title}'), findsOneWidget, reason: code);
      if (code != 'en') expect(find.text(AchievementTranslationLocale.messages[code]![0]), findsOneWidget);
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('long accents CJK Arabic and RTL remain intact in original fallback', (tester) async {
    final client = AchievementTranslationClient(enabled: false);
    addTearDown(client.dispose);
    await client.setLanguage('fr');
    final long = List.filled(300, 'Épée — 勇者 إنجاز 🎮').join(' ');
    await tester.pumpWidget(MaterialApp(home: Directionality(textDirection: TextDirection.rtl,
      child: SingleChildScrollView(child: Column(children: [
        TranslatedAchievementText(id: 42, title: source.title, description: long, client: client),
        TranslatedAchievementText(id: 42, title: source.title, description: long, showDescription: true, client: client),
      ])))));
    await tester.pumpAndSettle();
    expect(find.text(source.title), findsOneWidget);
    expect(find.text(long), findsOneWidget);
    expect(find.text(AchievementTranslationLocale.messages['fr']![1]), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('presentation cannot mutate source IDs points or unlock/Hardcore state', () async {
    final client = AchievementTranslationClient(channel: channel, enabled: true);
    addTearDown(client.dispose);
    const item = SecondaryAchievementItem(id: 42, title: 'Original', description: 'Requirements',
      points: 25, badgeName: '123', displayOrder: 7, earned: true, earnedHardcore: true);
    final before = item.toJson();
    await client.setLanguage('fr');
    client.text(AchievementSource(id: item.id, title: item.title, description: item.description));
    await Future<void>.delayed(Duration.zero);
    expect(item.toJson(), before);
    expect(item.earnedHardcore, isTrue);
  });

  test('latest successful language recovers after an older request fails', () async {
    final first = Completer<void>();
    messenger.setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'setLanguage' && (call.arguments as Map)['language'] == 'fr') {
        await first.future;
        throw PlatformException(code: 'test');
      }
      if (call.method == 'texts') return [{'id': 42, 'sourceTitle': source.title,
        'sourceDescription': source.description, 'title': 'German result',
        'description': source.description, 'provenance': 'machine'}];
      return null;
    });
    final client = AchievementTranslationClient(channel: channel, enabled: true);
    addTearDown(client.dispose);
    final old = client.setLanguage('fr');
    final latest = client.setLanguage('de');
    first.complete();
    await Future.wait([old, latest]);
    client.text(source);
    await Future<void>.delayed(Duration.zero);
    expect(client.text(source).title, 'German result');
    expect(client.language, 'de');
  });

  test('out of order response never overwrites the newly selected language', () async {
    final oldResponse = Completer<Object?>();
    var called = false;
    messenger.setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'setLanguage') { nativeLanguage = (call.arguments as Map)['language'] as String; return null; }
      if (!called) { called = true; return oldResponse.future; }
      return [{'id': 42, 'sourceTitle': source.title, 'sourceDescription': source.description,
        'title': 'Japanese result', 'description': source.description, 'provenance': 'machine'}];
    });
    final client = AchievementTranslationClient(channel: channel, enabled: true);
    addTearDown(client.dispose);
    await client.setLanguage('fr'); client.text(source);
    await Future<void>.delayed(Duration.zero);
    await client.setLanguage('ja');
    oldResponse.complete([{'id': 42, 'sourceTitle': source.title, 'sourceDescription': source.description,
      'title': 'Stale French result', 'description': source.description, 'provenance': 'machine'}]);
    await Future<void>.delayed(Duration.zero);
    expect(client.text(source).title, 'Japanese result');
  });

  test('secondary engine follows app language without writing it back', () async {
    var writes = 0;
    messenger.setMockMethodCallHandler(channel, (call) async { if (call.method == 'setLanguage') writes++; return []; });
    final client = AchievementTranslationClient(channel: channel, enabled: true);
    addTearDown(client.dispose);
    client.followAppLanguage('zh_Hant');
    expect(client.language, 'zh_Hant');
    await Future<void>.delayed(Duration.zero);
    expect(writes, 0);
  });
}
