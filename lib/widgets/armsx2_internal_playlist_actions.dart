import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../l10n/armsx2_ui_locale.dart';
import '../l10n/console_manager_locale.dart';
import '../l10n/texture_catalog_locale.dart';
import '../services/armsx2_internal_service.dart';
import '../services/embedded_engine_policy.dart';
import '../services/home_music_service.dart';
import '../services/texture_catalog_service.dart';
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

  void _notice(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
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

  Future<void> _selected(String action) async {
    if (_busy) return;
    if (action == 'textures') {
      await _openTextures();
      return;
    }
    setState(() => _busy = true);
    _interaction(true);
    try {
      if (action == 'games') {
        final result = await Armsx2InternalService.importGames();
        if (result.imported > 0) {
          await widget.onLibraryChanged();
          _notice(_tf('gamesImported', {'count': result.imported}));
        }
        if (result.rejected > 0) {
          _notice(
            result.errors.isNotEmpty
                ? result.errors.first
                : _t('gamesRejected'),
          );
        }
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
          _notice(
            StikJitArmsx2Service.lastError ??
                _t('bootBiosFailed'),
          );
        }
      } else if (action == 'bios') {
        final result = await Armsx2InternalService.importBios();
        if (result.imported > 0) {
          _notice(_tf('biosImported', {'count': result.imported}));
          if (mounted) await showArmsx2BiosPicker(context);
        } else if (result.rejected > 0) {
          _notice(result.errors.isNotEmpty ? result.errors.first : _t('biosImportFailed'));
        }
      }
    } catch (error) {
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
    if (!Platform.isIOS) return const SizedBox.shrink();
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
