import 'package:achievement_translation/achievement_translation.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:neostation/models/secondary_display_state.dart';
import 'package:neostation/screens/secondary_screen/secondary_screen.dart';

/// Applies a language the main engine sent to this engine's
/// `FlutterLocalization` without writing its preferences (the main engine
/// owns them). Returns whether the language changed; false for a language
/// that is not initialised here or is already current. Never throws.
bool applyExternalDisplayLanguage(String code) {
  final localization = FlutterLocalization.instance;
  if (!localization.supportedLanguageCodes.contains(code)) return false;
  if (localization.currentLocale?.languageCode == code) return false;
  try {
    localization.translate(code, save: false);
    AchievementTranslationClient.shared.followAppLanguage(code);
    return true;
  } catch (error) {
    debugPrint('External display menu: language $code not applied ($error)');
    return false;
  }
}

/// The menu states as [SecondaryScreen] listens to them, plus one more
/// notification (same state) when the language changed: its own
/// `MaterialApp` then rebuilds with the new delegates of
/// `FlutterLocalization`.
class _LanguageAwareStateSource extends ChangeNotifier
    implements ValueListenable<SecondaryDisplayStateData?> {
  _LanguageAwareStateSource(this._states) {
    _states.addListener(notifyListeners);
  }

  ValueListenable<SecondaryDisplayStateData?> _states;

  /// Follows another source (the screen keeps listening to this object).
  set states(ValueListenable<SecondaryDisplayStateData?> next) {
    if (identical(next, _states)) return;
    _states.removeListener(notifyListeners);
    _states = next;
    _states.addListener(notifyListeners);
    notifyListeners();
  }

  @override
  SecondaryDisplayStateData? get value => _states.value;

  void languageChanged() => notifyListeners();

  @override
  void dispose() {
    _states.removeListener(notifyListeners);
    super.dispose();
  }
}

/// Root of the TV menu shown by the external display's second Flutter
/// engine (Build 447): the [SecondaryScreen] of the Android bottom display,
/// fed by the states the main engine pushes through [stateSource] instead
/// of the `sub_screen` shared state.
///
/// Black behind everything: the external window is sized to the TV, so the
/// screen lays itself out to those bounds and no band is drawn by NeoStation.
/// When this engine's localization could not be initialised (no language at
/// all), the TV stays black rather than showing a menu that cannot resolve
/// its texts.
class ExternalMenuApp extends StatefulWidget {
  const ExternalMenuApp({
    super.key,
    required this.stateSource,
    this.initialThemeName,
    this.languageSource,
  });

  /// States decoded from the `neostation/external_display/menu` channel
  /// (`ExternalDisplayStateChannel.state`); tests inject their own.
  final ValueListenable<SecondaryDisplayStateData?> stateSource;

  /// Theme name given by the main engine (entrypoint argument), used until
  /// the main engine pushes a state with its own theme and background.
  final String? initialThemeName;

  /// The app language the main engine sends when it changes
  /// (`ExternalDisplayStateChannel.language`); the menu is rebuilt in it.
  final ValueListenable<String?>? languageSource;

  static const Key backgroundKey = Key('externalMenu.background');

  @override
  State<ExternalMenuApp> createState() => _ExternalMenuAppState();
}

class _ExternalMenuAppState extends State<ExternalMenuApp> {
  late final _LanguageAwareStateSource _states;

  @override
  void initState() {
    super.initState();
    _states = _LanguageAwareStateSource(widget.stateSource);
    widget.languageSource?.addListener(_languageChanged);
    final pending = widget.languageSource?.value;
    if (pending != null) applyExternalDisplayLanguage(pending);
  }

  @override
  void didUpdateWidget(covariant ExternalMenuApp oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.stateSource, widget.stateSource)) {
      _states.states = widget.stateSource;
    }
    if (!identical(oldWidget.languageSource, widget.languageSource)) {
      oldWidget.languageSource?.removeListener(_languageChanged);
      widget.languageSource?.addListener(_languageChanged);
    }
  }

  @override
  void dispose() {
    widget.languageSource?.removeListener(_languageChanged);
    _states.dispose();
    super.dispose();
  }

  void _languageChanged() {
    final code = widget.languageSource?.value;
    if (code == null || !applyExternalDisplayLanguage(code) || !mounted) return;
    // Both MaterialApps take the new delegate of FlutterLocalization: this
    // one at this rebuild, the menu's own through its state listener.
    setState(() {});
    _states.languageChanged();
  }

  @override
  Widget build(BuildContext context) {
    final localization = FlutterLocalization.instance;
    final locales = localization.supportedLocales.toList();
    if (locales.isEmpty) {
      return const ColoredBox(
        key: ExternalMenuApp.backgroundKey,
        color: Colors.black,
        child: SizedBox.expand(),
      );
    }
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      color: Colors.black,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: Colors.black,
      ),
      // The twelve NeoStation languages, initialised by the entrypoint like
      // `subDisplay` does for the Android bottom display.
      localizationsDelegates: localization.localizationsDelegates,
      supportedLocales: locales,
      home: ColoredBox(
        key: ExternalMenuApp.backgroundKey,
        color: Colors.black,
        child: SecondaryScreen(
          initialThemeName: widget.initialThemeName,
          stateSource: _states,
        ),
      ),
    );
  }
}
