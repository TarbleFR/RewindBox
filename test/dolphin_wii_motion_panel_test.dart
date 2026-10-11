import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/dolphin_shake_locale.dart';
import 'package:neostation/models/dolphin_phone_shake_settings.dart';
import 'package:neostation/widgets/dolphin_wii_motion_panel.dart';

/// Loads the default (English) Material or Cupertino texts for any locale, as
/// the app's fallback delegates do, so the panel can be pumped under every
/// NeoStation locale.
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

/// Build 442: the Wii settings panel mirrors the native phone-shake
/// preferences (on/off, sensitivity) through injected loader/saver seams.
void main() {
  Widget host(Widget child, {Locale locale = const Locale('fr')}) {
    return ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (_, _) => MaterialApp(
        locale: locale,
        supportedLocales: const [Locale('en'), Locale('fr'), Locale('ja')],
        localizationsDelegates: const [
          _materialTexts,
          _cupertinoTexts,
          DefaultWidgetsLocalizations.delegate,
        ],
        home: Scaffold(body: SingleChildScrollView(child: child)),
      ),
    );
  }

  testWidgets('shows the native values and writes a changed switch', (
    tester,
  ) async {
    final saved = <Map<String, Object?>>[];
    var stored = const DolphinPhoneShakeSettings(
      enabled: true,
      sensitivity: 'medium',
    );
    await tester.pumpWidget(
      host(
        DolphinWiiMotionPanel(
          load: () async => stored,
          save: ({bool? enabled, String? sensitivity}) async {
            saved.add({'enabled': enabled, 'sensitivity': sensitivity});
            stored = stored.copyWith(
              enabled: enabled,
              sensitivity: sensitivity,
            );
            return stored;
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    final french = DolphinShakeLocale.values['fr']!;
    expect(find.text(french['wiiMotionSection']!), findsOneWidget);
    expect(find.text(french['phoneShakeToggle']!), findsOneWidget);
    expect(find.text(french['shakeSensitivity']!), findsOneWidget);
    expect(find.text(french['shakeSensitivityHelp']!), findsOneWidget);
    final toggle = tester.widget<SwitchListTile>(
      find.byKey(DolphinWiiMotionPanel.switchKey),
    );
    expect(toggle.value, isTrue);

    await tester.tap(find.byKey(DolphinWiiMotionPanel.switchKey));
    await tester.pumpAndSettle();
    expect(saved, [
      {'enabled': false, 'sensitivity': null},
    ]);
    expect(
      tester
          .widget<SwitchListTile>(find.byKey(DolphinWiiMotionPanel.switchKey))
          .value,
      isFalse,
    );
  });

  testWidgets('selecting a level writes only the sensitivity', (tester) async {
    final saved = <Map<String, Object?>>[];
    var stored = const DolphinPhoneShakeSettings(
      enabled: true,
      sensitivity: 'medium',
    );
    await tester.pumpWidget(
      host(
        DolphinWiiMotionPanel(
          load: () async => stored,
          save: ({bool? enabled, String? sensitivity}) async {
            saved.add({'enabled': enabled, 'sensitivity': sensitivity});
            stored = stored.copyWith(
              enabled: enabled,
              sensitivity: sensitivity,
            );
            return stored;
          },
        ),
        locale: const Locale('ja'),
      ),
    );
    await tester.pumpAndSettle();
    final japanese = DolphinShakeLocale.values['ja']!;
    final segmented = find.byKey(DolphinWiiMotionPanel.sensitivityKey);
    expect(
      tester.widget<SegmentedButton<String>>(segmented).selected,
      {'medium'},
    );
    await tester.tap(
      find.descendant(
        of: segmented,
        matching: find.text(japanese['shakeSensitivityHigh']!),
      ),
    );
    await tester.pumpAndSettle();
    expect(saved, [
      {'enabled': null, 'sensitivity': 'high'},
    ]);
    expect(tester.widget<SegmentedButton<String>>(segmented).selected, {
      'high',
    });
  });

  testWidgets('a rejected write restores the stored values', (tester) async {
    await tester.pumpWidget(
      host(
        DolphinWiiMotionPanel(
          load: () async => const DolphinPhoneShakeSettings(
            enabled: true,
            sensitivity: 'low',
          ),
          save: ({bool? enabled, String? sensitivity}) async => null,
        ),
        locale: const Locale('en'),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(DolphinWiiMotionPanel.switchKey));
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<SwitchListTile>(find.byKey(DolphinWiiMotionPanel.switchKey))
          .value,
      isTrue,
    );
    expect(
      tester
          .widget<SegmentedButton<String>>(
            find.byKey(DolphinWiiMotionPanel.sensitivityKey),
          )
          .selected,
      {'low'},
    );
  });

  testWidgets('renders nothing when the bridge has no values', (tester) async {
    await tester.pumpWidget(
      host(
        DolphinWiiMotionPanel(
          load: () async => null,
          save: ({bool? enabled, String? sensitivity}) async => null,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(DolphinWiiMotionPanel.switchKey), findsNothing);
    expect(find.byType(SizedBox), findsWidgets);
  });

  test('native values map to the model with a safe default', () {
    expect(
      DolphinPhoneShakeSettings.fromMap({'enabled': true, 'sensitivity': 'HIGH'}),
      const DolphinPhoneShakeSettings(enabled: true, sensitivity: 'high'),
    );
    expect(
      DolphinPhoneShakeSettings.fromMap({'enabled': false, 'sensitivity': 7}),
      const DolphinPhoneShakeSettings(enabled: false, sensitivity: 'medium'),
    );
    expect(
      DolphinPhoneShakeSettings.fromMap(const {}),
      const DolphinPhoneShakeSettings(enabled: true, sensitivity: 'medium'),
    );
  });
}
