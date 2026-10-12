import 'package:flutter/widgets.dart';

import 'package:neostation/services/gamepad/gamepad_navigation_manager.dart';
import 'package:neostation/utils/gamepad_nav.dart';

/// Controller actions of one reader surface (reader, sheet, dialog).
@immutable
class LibraryReaderGamepadBindings {
  const LibraryReaderGamepadBindings({
    this.up,
    this.down,
    this.left,
    this.right,
    this.select,
    this.back,
    this.leftBumper,
    this.rightBumper,
    this.x,
    this.y,
    this.start,
    this.rightStickClick,
  });

  final VoidCallback? up;
  final VoidCallback? down;
  final VoidCallback? left;
  final VoidCallback? right;

  /// A.
  final VoidCallback? select;

  /// B: always closes the surface.
  final VoidCallback? back;
  final VoidCallback? leftBumper;
  final VoidCallback? rightBumper;
  final VoidCallback? x;
  final VoidCallback? y;

  /// Start / Menu.
  final VoidCallback? start;

  /// Right stick click (R3): "Fit" of the PDF scroll mode
  /// (docs/library-books-3d-plan.md § 3.10).
  final VoidCallback? rightStickClick;
}

/// Owns a modal [GamepadNavigationManager] layer while mounted, so the
/// screens underneath never receive controller input, and B always reaches
/// [LibraryReaderGamepadBindings.back]. The latest [bindings] are used for
/// every event.
class LibraryReaderGamepadScope extends StatefulWidget {
  const LibraryReaderGamepadScope({
    super.key,
    required this.name,
    required this.bindings,
    required this.child,
  });

  /// Layer name prefix (diagnostics).
  final String name;
  final LibraryReaderGamepadBindings bindings;
  final Widget child;

  @override
  State<LibraryReaderGamepadScope> createState() =>
      _LibraryReaderGamepadScopeState();
}

class _LibraryReaderGamepadScopeState extends State<LibraryReaderGamepadScope> {
  late final GamepadNavigation _navigation;
  late final String _layerId;
  bool _pushed = false;

  @override
  void initState() {
    super.initState();
    _layerId = '${widget.name}_${identityHashCode(this)}';
    LibraryReaderGamepadBindings b() => widget.bindings;
    _navigation = GamepadNavigation(
      onNavigateUp: () => b().up?.call(),
      onNavigateDown: () => b().down?.call(),
      onNavigateLeft: () => b().left?.call(),
      onNavigateRight: () => b().right?.call(),
      onSelectItem: () => b().select?.call(),
      onBack: () => b().back?.call(),
      onLeftBumper: () => b().leftBumper?.call(),
      onRightBumper: () => b().rightBumper?.call(),
      onXButton: () => b().x?.call(),
      onFavorite: () => b().y?.call(),
      onSettings: () => b().start?.call(),
      onRightStickClick: () => b().rightStickClick?.call(),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _navigation.initialize();
      GamepadNavigationManager.pushLayer(
        _layerId,
        modal: true,
        onActivate: _navigation.activate,
        onDeactivate: _navigation.deactivate,
      );
      _pushed = true;
    });
  }

  @override
  void dispose() {
    if (_pushed) GamepadNavigationManager.popLayer(_layerId);
    _navigation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
