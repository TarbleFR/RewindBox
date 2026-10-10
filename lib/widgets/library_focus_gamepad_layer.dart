import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/gamepad/gamepad_navigation_manager.dart';
import '../utils/gamepad_nav.dart';

/// Moves Flutter's focus with a controller inside one subtree.
///
/// Shared by [LibraryFocusGamepadLayer] (pushed routes and dialogs) and by
/// the Library sections embedded in `LibraryScreen`, which receive the
/// controller input through `LibraryGamepadViewController`.
abstract final class LibraryFocusNavigation {
  static FocusHighlightStrategy? _savedStrategy;

  /// Moves the focus one step in [direction] inside [root]'s subtree. When
  /// nothing inside [root] has the focus yet, focuses its first control.
  /// Returns whether the focus moved.
  static bool move(FocusNode root, TraversalDirection direction) {
    showFocus();
    final current = FocusManager.instance.primaryFocus;
    final inside =
        current != null &&
        current != root &&
        current.context != null &&
        _isDescendant(current, root) &&
        !(current is FocusScopeNode && current.focusedChild == null);
    if (!inside) return focusFirst(root);
    return current.focusInDirection(direction);
  }

  /// Focuses the first focusable control of [root]. Returns false when
  /// [root] has none.
  static bool focusFirst(FocusNode root) {
    for (final candidate in root.traversalDescendants) {
      if (candidate.context == null || !candidate.canRequestFocus) continue;
      FocusTraversalPolicy.defaultTraversalRequestFocusCallback(
        candidate,
        alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtStart,
      );
      return true;
    }
    return false;
  }

  /// Activates the focused control of [root] through its [ActivateIntent]
  /// (buttons, list rows, checkboxes, switches). Returns whether a control
  /// inside [root] had the focus.
  static bool activate(FocusNode root) {
    final current = FocusManager.instance.primaryFocus;
    final context = current?.context;
    if (current == null ||
        context == null ||
        current == root ||
        !_isDescendant(current, root)) {
      return false;
    }
    Actions.maybeInvoke<ActivateIntent>(context, const ActivateIntent());
    return true;
  }

  /// True when the primary focus is a text field inside [root].
  static bool editingText(FocusNode root) {
    final current = FocusManager.instance.primaryFocus;
    final context = current?.context;
    if (current == null || context == null || !_isDescendant(current, root)) {
      return false;
    }
    return context.findAncestorWidgetOfExactType<EditableText>() != null ||
        context.widget is EditableText;
  }

  /// Controller users must see where the focus is: Material controls only
  /// draw their focus highlight in the traditional highlight mode, which
  /// iOS touch input otherwise switches off.
  static void showFocus() {
    final manager = FocusManager.instance;
    if (manager.highlightStrategy == FocusHighlightStrategy.alwaysTraditional) {
      return;
    }
    _savedStrategy ??= manager.highlightStrategy;
    manager.highlightStrategy = FocusHighlightStrategy.alwaysTraditional;
  }

  /// Gives the highlight back to touch input (called on any touch).
  static void restoreTouchHighlight() {
    final saved = _savedStrategy;
    if (saved == null) return;
    _savedStrategy = null;
    FocusManager.instance.highlightStrategy = saved;
  }

  static bool _isDescendant(FocusNode node, FocusNode root) {
    FocusNode? cursor = node;
    while (cursor != null) {
      if (identical(cursor, root)) return true;
      cursor = cursor.parent;
    }
    return false;
  }
}

/// Wraps a pushed Library route (or a dialog) so a controller can use it:
/// pushes a modal [GamepadNavigationManager] layer after the first frame and
/// pops it on dispose; the d-pad moves Flutter's focus
/// ([FocusNode.focusInDirection]), A activates the focused control through
/// its [ActivateIntent], B goes back ([onBack], default
/// `Navigator.maybePop`) and X calls [onSecondary]. The focus is drawn while
/// the controller is used; a touch gives the highlight back to touch mode.
///
/// Flutter's own arrow-key traversal and Enter activation are switched off
/// inside the layer so a hardware key never acts twice (the navigation
/// layer already handles arrows and Enter); text fields keep their keys.
class LibraryFocusGamepadLayer extends StatefulWidget {
  const LibraryFocusGamepadLayer({
    super.key,
    required this.child,
    this.onBack,
    this.onSecondary,
    this.debugLabel = 'library',
    this.enableGamepad = true,
    this.autofocus = true,
  });

  final Widget child;

  /// B button. Defaults to `Navigator.maybePop(context)`.
  final VoidCallback? onBack;

  /// X button.
  final VoidCallback? onSecondary;
  final String debugLabel;

  /// False in tests that must not start the gamepad plugin.
  final bool enableGamepad;

  /// Focuses the layer when it appears. Set false when a text field of the
  /// layer has its own autofocus (the first autofocus of a scope wins).
  final bool autofocus;

  @override
  State<LibraryFocusGamepadLayer> createState() =>
      LibraryFocusGamepadLayerState();
}

class LibraryFocusGamepadLayerState extends State<LibraryFocusGamepadLayer> {
  late final String _layerId =
      'library_focus_${widget.debugLabel}_${identityHashCode(this)}';
  final FocusNode _root = FocusNode(
    debugLabel: 'LibraryFocusGamepadLayer',
    skipTraversal: true,
  );
  GamepadNavigation? _navigation;
  bool _pushed = false;

  /// Focus node above every control of the layer (for tests and callers
  /// that need to move the focus programmatically).
  FocusNode get rootFocus => _root;

  @override
  void initState() {
    super.initState();
    if (!widget.enableGamepad) return;
    _navigation = GamepadNavigation(
      onNavigateUp: () => move(TraversalDirection.up),
      onNavigateDown: () => move(TraversalDirection.down),
      onNavigateLeft: () => move(TraversalDirection.left),
      onNavigateRight: () => move(TraversalDirection.right),
      onSelectItem: activateFocused,
      onBack: back,
      onXButton: () => widget.onSecondary?.call(),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final navigation = _navigation;
      if (!mounted || navigation == null) return;
      navigation.initialize();
      GamepadNavigationManager.pushLayer(
        _layerId,
        modal: true,
        onActivate: navigation.activate,
        onDeactivate: navigation.deactivate,
      );
      _pushed = true;
    });
  }

  @override
  void dispose() {
    if (_pushed) GamepadNavigationManager.popLayer(_layerId);
    _navigation?.dispose();
    _root.dispose();
    super.dispose();
  }

  bool move(TraversalDirection direction) =>
      LibraryFocusNavigation.move(_root, direction);

  void activateFocused() {
    if (!LibraryFocusNavigation.activate(_root)) {
      LibraryFocusNavigation.move(_root, TraversalDirection.down);
    }
  }

  void back() {
    if (!mounted) return;
    final onBack = widget.onBack;
    if (onBack != null) {
      onBack();
    } else {
      Navigator.of(context).maybePop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: (_) => LibraryFocusNavigation.restoreTouchHighlight(),
      child: FocusTraversalGroup(
        policy: ReadingOrderTraversalPolicy(),
        child: Shortcuts(
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
            child: Focus(
              focusNode: _root,
              autofocus: widget.autofocus,
              child: widget.child,
            ),
          ),
        ),
      ),
    );
  }
}

/// Outline drawn while a control inside [child] has the focus, so controller
/// users see where they are whatever the theme's focus colours are. A touch
/// on a button never gives it the focus, so touch users see nothing.
class LibraryFocusRing extends StatefulWidget {
  const LibraryFocusRing({
    super.key,
    required this.child,
    this.radius = 12,
    this.onFocusChange,
  });

  final Widget child;
  final double radius;
  final ValueChanged<bool>? onFocusChange;

  @override
  State<LibraryFocusRing> createState() => _LibraryFocusRingState();
}

class _LibraryFocusRingState extends State<LibraryFocusRing> {
  bool _focused = false;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return Focus(
      canRequestFocus: false,
      skipTraversal: true,
      onFocusChange: (focused) {
        widget.onFocusChange?.call(focused);
        if (mounted && focused != _focused) setState(() => _focused = focused);
      },
      child: DecoratedBox(
        position: DecorationPosition.foreground,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(widget.radius),
          border: Border.all(
            color: _focused ? color : Colors.transparent,
            width: 2,
          ),
        ),
        child: widget.child,
      ),
    );
  }
}
