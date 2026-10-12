import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:neostation/models/secondary_display_state.dart';
import 'package:neostation/screens/secondary_screen/secondary_screen.dart';

/// Root of the TV menu shown by the external display's second Flutter
/// engine (Build 447): the [SecondaryScreen] of the Android bottom display,
/// fed by the states the main engine pushes through [stateSource] instead
/// of the `sub_screen` shared state.
///
/// Black behind everything: the external window is sized to the TV, so the
/// screen lays itself out to those bounds and no band is drawn by NeoStation.
class ExternalMenuApp extends StatelessWidget {
  const ExternalMenuApp({
    super.key,
    required this.stateSource,
    this.initialThemeName,
  });

  /// States decoded from the `neostation/external_display/menu` channel
  /// (`ExternalDisplayStateChannel.state`); tests inject their own.
  final ValueListenable<SecondaryDisplayStateData?> stateSource;

  /// Theme name read from the database by the entrypoint, used until the
  /// main engine pushes a background colour.
  final String? initialThemeName;

  static const Key backgroundKey = Key('externalMenu.background');

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      color: Colors.black,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: Colors.black,
      ),
      // The twelve NeoStation languages, initialised by the entrypoint like
      // `subDisplay` does for the Android bottom display.
      localizationsDelegates: FlutterLocalization.instance.localizationsDelegates,
      supportedLocales: FlutterLocalization.instance.supportedLocales,
      home: ColoredBox(
        key: backgroundKey,
        color: Colors.black,
        child: SecondaryScreen(
          initialThemeName: initialThemeName,
          stateSource: stateSource,
        ),
      ),
    );
  }
}
