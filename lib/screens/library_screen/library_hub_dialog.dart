import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';

import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/library_feature_locale.dart';
import 'package:neostation/services/gamepad/gamepad_navigation_manager.dart';
import 'package:neostation/utils/gamepad_nav.dart';

/// Information dialog of the Library hub and its sections, usable with the
/// controller: B closes, A runs the primary action (or closes when there is
/// none), up/down scroll a long content. While it is open the Library
/// screen below ignores controller input, so a dialog without its own
/// layer would leave a controller user stuck.
class LibraryHubDialog extends StatefulWidget {
  const LibraryHubDialog({
    super.key,
    required this.title,
    required this.children,
    this.primaryLabel,
    this.onPrimary,
  });

  final String title;
  final List<Widget> children;
  final String? primaryLabel;
  final VoidCallback? onPrimary;

  @override
  State<LibraryHubDialog> createState() => _LibraryHubDialogState();
}

class _LibraryHubDialogState extends State<LibraryHubDialog> {
  late final GamepadNavigation _gamepadNav;
  late final String _layerId = 'library_hub_dialog_${identityHashCode(this)}';
  final ScrollController _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _gamepadNav = GamepadNavigation(
      onBack: _close,
      onSelectItem: () {
        final primary = widget.onPrimary;
        if (primary != null) {
          primary();
        } else {
          _close();
        }
      },
      onNavigateUp: () => _scrollBy(-120),
      onNavigateDown: () => _scrollBy(120),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        _layerId,
        modal: true,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
    });
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer(_layerId);
    _gamepadNav.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _close() {
    if (mounted) Navigator.of(context).maybePop();
  }

  void _scrollBy(double delta) {
    if (!_scroll.hasClients) return;
    final position = _scroll.position;
    _scroll.jumpTo(
      (position.pixels + delta).clamp(0.0, position.maxScrollExtent),
    );
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final primary = widget.primaryLabel;
    return LibraryLayerOwnedKeys(
      child: AlertDialog(
        title: Text(widget.title),
        content: SizedBox(
          width: math.min(560, size.width * 0.8),
          child: ConstrainedBox(
            constraints: BoxConstraints(maxHeight: size.height * 0.6),
            child: SingleChildScrollView(
              controller: _scroll,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: widget.children,
              ),
            ),
          ),
        ),
        actions: [
          TextButton(
            style: TextButton.styleFrom(minimumSize: const Size(44, 44)),
            onPressed: _close,
            child: Text(AppLocale.close.getString(context)),
          ),
          if (primary != null)
            FilledButton(
              style: FilledButton.styleFrom(minimumSize: const Size(44, 44)),
              onPressed: widget.onPrimary,
              child: Text(primary),
            ),
        ],
      ),
    );
  }
}

/// Inside a dialog driven by its own controller layer, Flutter's arrow-key
/// focus traversal and Enter activation are switched off: the layer also
/// receives hardware-keyboard keys, so one Enter would otherwise act twice
/// (e.g. pop the dialog, then the screen under it).
class LibraryLayerOwnedKeys extends StatelessWidget {
  const LibraryLayerOwnedKeys({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Shortcuts(
    shortcuts: const <ShortcutActivator, Intent>{
      SingleActivator(LogicalKeyboardKey.enter):
          DoNothingAndStopPropagationIntent(),
      SingleActivator(LogicalKeyboardKey.numpadEnter):
          DoNothingAndStopPropagationIntent(),
    },
    child: Actions(
      actions: <Type, Action<Intent>>{
        DirectionalFocusIntent: DoNothingAction(),
      },
      child: Focus(autofocus: true, child: child),
    ),
  );
}

/// Raw technical detail (URL, HTTP status, exception text), untranslated,
/// under a translated "Technical details" label.
class LibraryTechnicalDetails extends StatelessWidget {
  const LibraryTechnicalDetails(this.technical, {super.key});

  final String technical;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          LibraryFeatureLocale.text(context, 'technicalDetails'),
          style: theme.textTheme.labelSmall?.copyWith(
            color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
          ),
        ),
        const SizedBox(height: 2),
        SelectableText(
          technical,
          style: theme.textTheme.bodySmall?.copyWith(
            fontFamily: 'monospace',
            color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
          ),
        ),
      ],
    );
  }
}
