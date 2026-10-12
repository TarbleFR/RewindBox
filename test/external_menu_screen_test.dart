import 'dart:convert';

import 'package:flutter/foundation.dart' show ValueListenable;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/external_display/external_display_state_channel.dart';
import 'package:neostation/external_display/external_menu_screen.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/secondary_achievement_item.dart';
import 'package:neostation/models/secondary_display_state.dart';
import 'package:neostation/screens/secondary_screen/secondary_screen.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  const tv = Size(1920, 1080);

  setUpAll(() async {
    // FlutterLocalization reads its stored language from SharedPreferences.
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [
        MapLocale('en', AppLocale.en),
        MapLocale('fr', AppLocale.fr),
      ],
      initLanguageCode: 'en',
    );
  });

  Future<void> pumpTv(
    WidgetTester tester, {
    required ValueListenable<SecondaryDisplayStateData?> source,
    String? theme,
  }) async {
    tester.view.physicalSize = tv;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ExternalMenuApp(stateSource: source, initialThemeName: theme),
    );
    await tester.pumpAndSettle();
  }

  Future<void> send(String message) => binding.defaultBinaryMessenger
      .handlePlatformMessage(
        ExternalDisplayStateChannel.channelName,
        const StringCodec().encodeMessage(message),
        (_) {},
      );

  Scaffold scaffold(WidgetTester tester) =>
      tester.widget<Scaffold>(find.byType(Scaffold));

  testWidgets('fills a 1920×1080 TV in black with no band and no exception', (
    tester,
  ) async {
    final source = ValueNotifier<SecondaryDisplayStateData?>(null);
    addTearDown(source.dispose);
    await pumpTv(tester, source: source, theme: 'dark');
    expect(tester.takeException(), isNull);

    final background = find.byKey(ExternalMenuApp.backgroundKey);
    expect(tester.widget<ColoredBox>(background).color, Colors.black);
    expect(tester.getSize(background), tv);
    expect(tester.getTopLeft(background), Offset.zero);

    // The menu view lays itself out to the TV bounds: no band of its own.
    expect(find.byType(SecondaryScreen), findsOneWidget);
    expect(tester.getSize(find.byType(Scaffold)), tv);
    expect(tester.getTopLeft(find.byType(Scaffold)), Offset.zero);
    // Before any state: the WELCOME placeholder, not an empty screen.
    expect(find.text('WELCOME'), findsOneWidget);
    expect(tester.binding.hasScheduledFrame, isFalse);
  });

  testWidgets('the initial theme and the language apply before any state', (
    tester,
  ) async {
    final source = ValueNotifier<SecondaryDisplayStateData?>(null);
    addTearDown(source.dispose);
    await pumpTv(tester, source: source, theme: 'light');
    expect(
      scaffold(tester).backgroundColor,
      AppThemes.lightTheme.scaffoldBackgroundColor,
    );
    expect(scaffold(tester).backgroundColor, isNot(Colors.black));

    // Both MaterialApps carry the languages the entrypoint initialised.
    for (final app in tester.widgetList<MaterialApp>(find.byType(MaterialApp))) {
      expect(app.supportedLocales, FlutterLocalization.instance.supportedLocales);
      expect(app.supportedLocales, contains(const Locale('fr')));
      expect(app.debugShowCheckedModeBanner, isFalse);
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('a state received through the message channel updates the screen', (
    tester,
  ) async {
    final channel = ExternalDisplayStateChannel.forTesting();
    await pumpTv(tester, source: channel.state, theme: 'dark');
    expect(find.text('WELCOME'), findsOneWidget);

    await send(
      jsonEncode(
        SecondaryDisplayStateData(
          systemName: 'snes',
          backgroundColor: 0xFF123456,
        ).toJson(),
      ),
    );
    await tester.pumpAndSettle();
    expect(channel.received, 1);
    expect(channel.rejected, 0);
    expect(channel.state.value?.systemName, 'snes');
    expect(find.text('SNES'), findsOneWidget);
    expect(find.text('WELCOME'), findsNothing);
    expect(scaffold(tester).backgroundColor, const Color(0xFF123456));
    expect(tester.takeException(), isNull);

    // A second push replaces the first; a malformed one changes nothing.
    await send(
      jsonEncode(SecondaryDisplayStateData(systemName: 'Mega Drive').toJson()),
    );
    await tester.pumpAndSettle();
    expect(find.text('MEGA DRIVE'), findsOneWidget);
    expect(find.text('SNES'), findsNothing);

    await send('not json');
    await send('[1, 2]');
    await send('');
    await tester.pumpAndSettle();
    expect(channel.received, 2);
    expect(channel.rejected, 3);
    expect(find.text('MEGA DRIVE'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a state pushed before the screen exists is shown', (
    tester,
  ) async {
    final source = ValueNotifier<SecondaryDisplayStateData?>(
      SecondaryDisplayStateData(systemName: 'ps1'),
    );
    addTearDown(source.dispose);
    await pumpTv(tester, source: source, theme: 'dark');
    expect(find.text('PS1'), findsOneWidget);
    expect(find.text('WELCOME'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  test('the JSON the main engine sends decodes into the same state', () {
    // The channel carries text: the bridge decodes what jsonEncode produced,
    // nested lists and bytes included.
    final sent = SecondaryDisplayStateData(
      systemName: 'snes',
      gameImageBytes: Uint8List.fromList([0, 1, 2, 253, 254, 255]),
      achievements: const [
        SecondaryAchievementItem(
          id: 1,
          title: 'A',
          description: 'first',
          points: 5,
          badgeName: '111',
          displayOrder: 0,
          earned: true,
          earnedHardcore: false,
        ),
      ],
      newlyEarnedIds: const [1, 2],
      nowPlayingActive: true,
      dockApps: const ['com.a', '', '', '', ''],
    );
    final received = SecondaryDisplayStateData.fromJson(
      jsonDecode(jsonEncode(sent.toJson())) as Map<String, dynamic>,
    );
    expect(received.toJson(), sent.toJson());
    expect(received.achievements!.single.id, 1);
    expect(received.gameImageBytes, sent.gameImageBytes);
  });
}
