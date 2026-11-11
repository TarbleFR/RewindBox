import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../l10n/armsx2_ui_locale.dart';
import '../l10n/console_manager_locale.dart';
import '../l10n/launch_prerequisite_locale.dart';
import '../l10n/libretro_locale.dart';
import '../l10n/texture_catalog_locale.dart';
import '../services/armsx2_internal_service.dart';
import '../services/embedded_engine_policy.dart';
import '../services/home_music_service.dart';
import '../services/texture_catalog_service.dart';
import '../screens/libretro/libretro_skin_manager_screen.dart';
import 'armsx2_bios_picker.dart';
import '../services/stikjit_armsx2_service.dart';

class Armsx2InternalPlaylistActions extends StatefulWidget {
  const Armsx2InternalPlaylistActions({
    super.key,
    required this.onLibraryChanged,
    this.onInteractionChanged,
    this.embedded = false,
  });

  final Future<void> Function() onLibraryChanged;
  final ValueChanged<bool>? onInteractionChanged;
  final bool embedded;

  @override
  State<Armsx2InternalPlaylistActions> createState() =>
      _Armsx2InternalPlaylistActionsState();
}

class _Armsx2InternalPlaylistActionsState
    extends State<Armsx2InternalPlaylistActions> {
  bool _busy = false;

  String _t(String key) => Armsx2UiLocale.text(context, key);
  String _tf(String key, Map<String, Object?> values) =>
      Armsx2UiLocale.format(context, key, values);

  void _interaction(bool active) => widget.onInteractionChanged?.call(active);

  void _notice(String message, {bool long = false}) {
    if (!mounted || message.isEmpty) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        duration: Duration(seconds: long ? 10 : 4),
      ),
    );
  }

  // Build 486: the console's HD textures page (PS2).
  Future<void> _openTextures() async {
    _interaction(true);
    try {
      final opened = await TextureCatalogService.openConsole('ps2');
      if (!opened && mounted) _notice(TextureCatalogLocale.text(Localizations.localeOf(context), 'openFailed'));
    } finally {
      if (mounted) _interaction(false);
    }
  }

  /// PS2 controller skins (docs/dolphin-skins.md): the same manager as the
  /// GameCube, Wii and libretro consoles. Its choices go to
  /// `Config/Frontend/ps2.json`, read by ARMSX2SkinOverlay at the next launch.
  Future<void> _openSkins() async {
    _interaction(true);
    try {
      await Navigator.of(context).push(
        MaterialPageRoute<void>(builder: (_) => const LibretroSkinManagerScreen(console: 'ps2')),
      );
    } finally {
      if (mounted) _interaction(false);
    }
  }

  Future<void> _selected(String action) async {
    if (_busy) return;
    if (action == 'textures') {
      await _openTextures();
      return;
    }
    if (action == 'skins') {
      await _openSkins();
      return;
    }
    setState(() => _busy = true);
    _interaction(true);
    try {
      if (action == 'games') {
        final result = await Armsx2InternalService.importGames();
        // A file already on disk but missing from the list is shown too.
        if (result.imported > 0 || result.alreadyPresent > 0) {
          await widget.onLibraryChanged();
        }
        if (!mounted) return;
        final problems = result.problemSummary(_t);
        _notice(
          [
            if (result.imported > 0)
              _tf('gamesImported', {'count': result.imported}),
            if (problems.isNotEmpty)
              problems
            else if (result.rejected > 0)
              _t('gamesRejected'),
          ].join('\n'),
          long: true,
        );
      } else if (action == 'choose_bios') {
        await showArmsx2BiosPicker(context);
      } else if (action == 'boot_bios') {
        // Build 448: ARMSX2 switched off (Consoles tab or Settings ›
        // General) boots nothing, the BIOS included.
        final policy = EmbeddedEnginePolicy.instance;
        await policy.load();
        if (!mounted) return;
        if (!policy.allows('ps2')) {
          _notice(
            ConsoleManagerLocale.format(
              Localizations.localeOf(context),
              ConsoleManagerLocale.launchEngineOff,
              <String, Object?>{'console': 'PlayStation 2'},
            ),
          );
          return;
        }
        final selected = await showArmsx2BiosPicker(context);
        if (selected == null || !mounted) return;
        final uiLocale = Localizations.localeOf(context).toLanguageTag();
        // Outside the game launch dialog: the ambient music fades out before
        // ARMSX2 boots and comes back at its session end (Build 448).
        final launched = await HomeMusicService().holdForSideSession(
          launch: () => StikJitArmsx2Service.launchBios(uiLocale: uiLocale),
          started: (launched) => launched,
          ended: HomeMusicService.armsx2SessionEnded,
        );
        if (!launched) {
          if (!mounted) return;
          // The reason in the user's language when it is a known one (no
          // pairing file, LocalDevVPN off, …), else the technical text.
          final sentence = StikJitArmsx2Service.lastErrorText(
            LaunchPrerequisiteLocale.languageOf(Localizations.localeOf(context)),
          );
          final cause = StikJitArmsx2Service.lastError?.trim();
          // The sentence first, the technical cause under it when it differs.
          _notice(
            sentence != null
                ? [
                    sentence,
                    if (cause != null && cause.isNotEmpty && cause != sentence) cause,
                  ].join('\n')
                : cause ?? _t('bootBiosFailed'),
            long: true,
          );
        }
      } else if (action == 'bios') {
        final result = await Armsx2InternalService.importBios();
        if (!mounted) return;
        final problems = result.problemSummary(_t);
        if (result.imported > 0) {
          _notice(
            [
              _tf('biosImported', {'count': result.imported}),
              if (problems.isNotEmpty) problems,
            ].join('\n'),
            long: true,
          );
          if (mounted) await showArmsx2BiosPicker(context);
        } else if (result.rejected > 0 || problems.isNotEmpty) {
          _notice(
            problems.isNotEmpty ? problems : _t('biosImportFailed'),
            long: true,
          );
        }
      }
    } catch (error) {
      if (!mounted) return;
      _notice(_tf('importFailed', {'error': error}));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        _interaction(false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    // iOS only, like the other embedded engines (defaultTargetPlatform: the
    // same answer on the device, testable in widget tests).
    if (defaultTargetPlatform != TargetPlatform.iOS) return const SizedBox.shrink();
    final scheme = Theme.of(context).colorScheme;
    final button = SizedBox(
      width: 36.r,
      height: 36.r,
      child: PopupMenuButton<String>(
        key: const ValueKey('armsx2-internal-import-menu'),
        tooltip: _t('importMenu'),
        enabled: !_busy,
        padding: EdgeInsets.zero,
        onOpened: () => _interaction(true),
        onCanceled: () => _interaction(false),
        onSelected: _selected,
        icon: _busy
            ? SizedBox(
                width: 18.r,
                height: 18.r,
                child: const CircularProgressIndicator(strokeWidth: 2),
              )
            : Icon(
                Icons.file_upload_outlined,
                size: 18.r,
                color: widget.embedded ? scheme.onSurface : scheme.onTertiaryFixed,
              ),
        itemBuilder: (context) => [
          PopupMenuItem(
            value: 'games',
            child: Text(_t('importGames')),
          ),
          PopupMenuItem(
            value: 'bios',
            child: Text(_t('importBios')),
          ),
          PopupMenuItem(
            value: 'choose_bios',
            child: Text(_t('chooseBios')),
          ),
          PopupMenuItem(
            value: 'boot_bios',
            child: Text(_t('bootBios')),
          ),
          PopupMenuItem(
            key: const ValueKey('armsx2-skins'),
            value: 'skins',
            child: Text(LibretroLocale.text(context, 'skins')),
          ),
          if (TextureCatalogService.supports('ps2'))
            PopupMenuItem(
              value: 'textures',
              child: Text(TextureCatalogLocale.text(Localizations.localeOf(context), 'menuTitle')),
            ),
        ],
      ),
    );
    if (widget.embedded) return button;
    return Material(
      color: scheme.tertiaryFixed,
      borderRadius: BorderRadius.circular(10.r),
      elevation: 2,
      child: button,
    );
  }
}
