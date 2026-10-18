import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neo_touch_layout/neo_touch_layout.dart';
import 'package:neostation/l10n/dolphin_import_locale.dart';
import 'package:neostation/l10n/touch_layout_locale.dart';
import 'package:neostation/widgets/embedded_touch_controls_panel.dart';

class _AnyLocaleDelegate<T> extends LocalizationsDelegate<T> {
  const _AnyLocaleDelegate(this._load);

  final Future<T> Function(Locale locale) _load;

  @override
  bool isSupported(Locale locale) => true;

  @override
  Future<T> load(Locale locale) => _load(locale);

  @override
  bool shouldReload(covariant LocalizationsDelegate<T> old) => false;
}

const _materialTexts = _AnyLocaleDelegate<MaterialLocalizations>(
  DefaultMaterialLocalizations.load,
);
const _cupertinoTexts = _AnyLocaleDelegate<CupertinoLocalizations>(
  DefaultCupertinoLocalizations.load,
);

NeoTouchLayoutSettings _settings(
  String console, {
  bool hide = true,
  bool customized = false,
}) {
  final keys = switch (console) {
    'wii' => ['wii', 'wii-classic'],
    _ => [console],
  };
  return NeoTouchLayoutSettings(
    console: console,
    hideWithController: hide,
    controllerConnected: false,
    layouts: [
      for (final key in keys)
        NeoTouchLayoutEntry(key: key, customized: customized, editable: true),
    ],
  );
}

/// Build 484: the Emulators-tab panel of the GameCube, Wii, PS2 and PS3
/// embedded engines, through injected seams (the native editor is exercised
/// by test/touch_layout_ui_test.py in the iOS Simulator).
void main() {
  Widget host(Widget child, {Locale locale = const Locale('fr')}) {
    return ScreenUtilInit(
      designSize: const Size(844, 390),
      builder: (_, _) => MaterialApp(
        locale: locale,
        supportedLocales: const [
          Locale('en'),
          Locale('fr'),
          Locale('zh', 'TW'),
        ],
        localizationsDelegates: const [
          _materialTexts,
          _cupertinoTexts,
          DefaultWidgetsLocalizations.delegate,
        ],
        home: Scaffold(body: SingleChildScrollView(child: child)),
      ),
    );
  }

  testWidgets('PS2: switch on by default, turning it off is stored', (
    tester,
  ) async {
    final writes = <List<Object>>[];
    var stored = _settings('ps2');
    await tester.pumpWidget(
      host(
        EmbeddedTouchControlsPanel(
          console: 'ps2',
          load: (console) async => stored,
          setHide: (console, hide) async {
            writes.add([console, hide]);
            stored = _settings(console, hide: hide);
            return stored;
          },
          openEditor: (layout, locale) async => (opened: true, saved: false),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final french = TouchLayoutLocale.values['fr']!;
    expect(find.text(french['touchControls']!), findsOneWidget);
    expect(find.text(french['hideWithController']!), findsOneWidget);
    expect(find.text(french['hideWithControllerHelp']!), findsOneWidget);
    expect(find.textContaining(french['dolphinPlayerOneNote']!), findsNothing);
    expect(find.text(french['editTouchControls']!), findsOneWidget);
    final toggle = tester.widget<SwitchListTile>(
      find.byKey(EmbeddedTouchControlsPanel.switchKey),
    );
    expect(toggle.value, isTrue);
    await tester.tap(find.byKey(EmbeddedTouchControlsPanel.switchKey));
    await tester.pumpAndSettle();
    expect(writes, [
      ['ps2', false],
    ]);
    expect(
      tester
          .widget<SwitchListTile>(
            find.byKey(EmbeddedTouchControlsPanel.switchKey),
          )
          .value,
      isFalse,
    );
  });

  testWidgets('Wii: both pads are editable and the editor gets the locale', (
    tester,
  ) async {
    final opened = <List<String>>[];
    var loads = 0;
    await tester.pumpWidget(
      host(
        EmbeddedTouchControlsPanel(
          console: 'wii',
          load: (console) async {
            loads++;
            return _settings(console, customized: loads > 1);
          },
          setHide: (console, hide) async => _settings(console, hide: hide),
          openEditor: (layout, locale) async {
            opened.add([layout, locale]);
            return (opened: true, saved: true);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    final french = TouchLayoutLocale.values['fr']!;
    expect(find.byKey(EmbeddedTouchControlsPanel.editKey('wii')), findsOneWidget);
    expect(
      find.byKey(EmbeddedTouchControlsPanel.editKey('wii-classic')),
      findsOneWidget,
    );
    expect(
      find.text('${french['editTouchControls']} · ${french['layoutWiiClassic']}'),
      findsOneWidget,
    );
    // Dolphin explains who player 1 follows.
    expect(find.textContaining(french['dolphinPlayerOneNote']!), findsOneWidget);
    await tester.tap(
      find.byKey(EmbeddedTouchControlsPanel.editKey('wii-classic')),
    );
    await tester.pumpAndSettle();
    expect(opened, [
      ['wii-classic', 'fr'],
    ]);
    // The state is read again after the editor closes.
    expect(loads, 2);
    expect(find.textContaining(french['customized']!), findsNWidgets(2));
  });

  testWidgets('an unavailable editor is reported', (tester) async {
    await tester.pumpWidget(
      host(
        EmbeddedTouchControlsPanel(
          console: 'gc',
          load: (console) async => _settings(console),
          setHide: (console, hide) async => null,
          openEditor: (layout, locale) async => (opened: false, saved: false),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(EmbeddedTouchControlsPanel.editKey('gc')));
    await tester.pumpAndSettle();
    expect(
      find.text(TouchLayoutLocale.values['fr']!['editorUnavailable']!),
      findsOneWidget,
    );
  });

  testWidgets('Traditional Chinese is selected for zh-TW', (tester) async {
    await tester.pumpWidget(
      host(
        EmbeddedTouchControlsPanel(
          console: 'ps3',
          load: (console) async => _settings(console),
          setHide: (console, hide) async => null,
          openEditor: (layout, locale) async => (opened: true, saved: false),
        ),
        locale: const Locale('zh', 'TW'),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text(TouchLayoutLocale.values['zh_Hant']!['hideWithController']!),
      findsOneWidget,
    );
  });

  test('only the four embedded consoles have the panel', () {
    for (final console in ['gc', 'wii', 'ps2', 'ps3']) {
      expect(EmbeddedTouchControlsPanel.supports(console), isTrue);
    }
    for (final console in ['ports', 'snes', 'psx', '']) {
      expect(EmbeddedTouchControlsPanel.supports(console), isFalse);
    }
  });

  test('catalogue: twelve locales, identical keys, prefixed Dolphin labels', () {
    expect(TouchLayoutLocale.locales.length, 12);
    final keys = TouchLayoutLocale.values['en']!.keys.toSet();
    for (final locale in TouchLayoutLocale.locales) {
      expect(TouchLayoutLocale.values[locale]!.keys.toSet(), keys, reason: locale);
      for (final value in TouchLayoutLocale.values[locale]!.values) {
        expect(value.trim(), isNotEmpty, reason: locale);
      }
    }
    expect(TouchLayoutLocale.localeKey(const Locale('zh', 'HK')), 'zh_Hant');
    expect(
      TouchLayoutLocale.localeKey(
        const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      ),
      'zh_Hant',
    );
    expect(TouchLayoutLocale.localeKey(const Locale('zh', 'CN')), 'zh');
    expect(TouchLayoutLocale.localeKey(const Locale('nl')), 'en');
    // The Dolphin in-game menu reads its Touch controls page from its labels.
    final labels = DolphinImportLocale.labelsFor(const Locale('de'));
    expect(
      labels['touch.editTouchControls'],
      TouchLayoutLocale.values['de']!['editTouchControls'],
    );
    expect(
      labels['touch.hideWithControllerHelp'],
      TouchLayoutLocale.values['de']!['hideWithControllerHelp'],
    );
  });

  group('channel', () {
    TestWidgetsFlutterBinding.ensureInitialized();
    final calls = <MethodCall>[];
    setUp(() {
      calls.clear();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(NeoTouchLayout.channel, (call) async {
            calls.add(call);
            return switch (call.method) {
              'settings' => {
                'console': 'ps3',
                'controllerConnected': true,
                'layouts': [
                  {'key': 'ps3', 'customized': true, 'editable': true},
                  {'key': 7},
                ],
              },
              'setHideWithController' => {
                'console': 'ps3',
                'hideWithController': false,
                'layouts': [],
              },
              'openEditor' => {'opened': true, 'saved': true},
              _ => null,
            };
          });
    });
    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(NeoTouchLayout.channel, null);
    });

    test('a missing preference reads as on; malformed rows are ignored', () async {
      final settings = await NeoTouchLayout.settings('ps3');
      expect(calls.single.arguments, {'console': 'ps3'});
      expect(settings!.hideWithController, isTrue);
      expect(settings.controllerConnected, isTrue);
      expect(settings.layouts.length, 1);
      expect(settings.layouts.single.customized, isTrue);
    });

    test('writes and editor requests carry their arguments', () async {
      final stored = await NeoTouchLayout.setHideWithController('ps3', false);
      expect(calls.single.arguments, {'console': 'ps3', 'hide': false});
      expect(stored!.hideWithController, isFalse);
      final result = await NeoTouchLayout.openEditor('ps3', 'ja');
      expect(calls.last.arguments, {'layout': 'ps3', 'locale': 'ja'});
      expect(result.opened, isTrue);
      expect(result.saved, isTrue);
    });
  });
}
