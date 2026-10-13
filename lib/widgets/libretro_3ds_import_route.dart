import 'package:flutter/material.dart';

import '../l10n/app_locale.dart';
import '../screens/libretro/libretro_3ds_system_screen.dart';

/// Opens the Nintendo 3DS system data page with its import assistant
/// started: from the 3DS import menu of the library, or after a RetroArch
/// copy was given an Azahar, Citra or Lime3DS folder. The page names the
/// app's languages as the engine settings panel opens it.
Future<void> openLibretro3dsImport(BuildContext context) => Navigator.of(context).push(
  MaterialPageRoute<void>(
    builder: (_) => const Libretro3dsSystemScreen(languageNames: AppLocale.supportedLanguages, startImport: true),
  ),
);
