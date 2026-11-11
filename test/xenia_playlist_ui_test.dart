import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/xenia_locale.dart';
import 'package:neostation/screens/xenia/xenia_settings_screen.dart';
import 'package:neostation/services/xenia_settings_service.dart';
import 'package:neostation/widgets/xenia_internal_playlist_actions.dart';
import 'package:path/path.dart' as path;

void main() {
  late Directory temp;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('xenia_ui_');
  });

  tearDown(() async {
    debugDefaultTargetPlatformOverride = null;
    await temp.delete(recursive: true);
  });

  Widget app(Widget child, {Locale locale = const Locale('en')}) => ScreenUtilInit(
    designSize: const Size(800, 400),
    builder: (_, _) => MaterialApp(
      locale: locale,
      supportedLocales: const [Locale('en'), Locale('fr')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: Scaffold(body: child),
    ),
  );

  testWidgets('the playlist import button offers game and folder import and the Xbox 360 settings', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    final interactions = <bool>[];
    await tester.pumpWidget(app(
      Align(
        alignment: Alignment.topRight,
        child: XeniaInternalPlaylistActions(
          onLibraryChanged: () async {},
          onInteractionChanged: interactions.add,
        ),
      ),
    ));
    await tester.tap(find.byKey(const ValueKey('xenia-internal-import-menu')));
    await tester.pumpAndSettle();
    expect(find.text(XeniaLocale.values['en']!['importGames']!), findsOneWidget);
    expect(find.text(XeniaLocale.values['en']!['importFolder']!), findsOneWidget);
    expect(find.text(XeniaLocale.values['en']!['globalSettings']!), findsOneWidget);
    expect(interactions, <bool>[true], reason: 'the playlist gamepad navigation pauses while the menu is open');
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('outside iOS the button is absent', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    await tester.pumpWidget(app(XeniaInternalPlaylistActions(onLibraryChanged: () async {})));
    expect(find.byKey(const ValueKey('xenia-internal-import-menu')), findsNothing);
    debugDefaultTargetPlatformOverride = null;
  });

  testWidgets('per-game settings show the inherited value, store an override and go back to it', (tester) async {
    final frontend = Directory(path.join(temp.path, 'Frontend'));
    final service = XeniaSettingsService(frontendDirectory: () async => frontend);
    await tester.runAsync(() => service.setGlobal('framerate_limit', '60'));
    await tester.pumpWidget(app(
      XeniaSettingsScreen(service: service, gameKey: 'title:4D5307E6', gameTitle: 'Test Title'),
      locale: const Locale('fr'),
    ));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
    await tester.pumpAndSettle();
    final fr = XeniaLocale.values['fr']!;
    expect(find.text('Test Title'), findsOneWidget);
    // The console language is its own row, separate from the interface language.
    expect(find.text(fr['user_language']!), findsOneWidget);
    expect(find.textContaining(fr['interfaceNote']!), findsOneWidget);
    await tester.scrollUntilVisible(find.text(fr['framerate_limit']!), 120);
    expect(find.text(fr['framerate_limit']!), findsOneWidget);
    expect(
      find.textContaining('60 FPS · ${fr['inheritedFrom']!.replaceAll('{source}', fr['sourceGlobal']!)}'),
      findsOneWidget,
    );

    await tester.tap(find.text(fr['framerate_limit']!));
    await tester.pumpAndSettle();
    await tester.tap(find.text('30 FPS'));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    expect(service.gameValue('title:4D5307E6', 'framerate_limit'), '30');
    expect(find.byKey(const ValueKey('xenia-setting-reset-framerate_limit')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('xenia-setting-reset-framerate_limit')));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpAndSettle();
    expect(service.gameValue('title:4D5307E6', 'framerate_limit'), isNull);
    expect(service.resolve('framerate_limit', gameKey: 'title:4D5307E6').value, '60');
  });
}
