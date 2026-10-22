import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../widgets/neoplay_dialog.dart';

/// A resting destination in the same cycle as the other main tabs. Connections
/// remain explicit, and leaving this page never disconnects a running stream.
class AirPlayScreen extends StatefulWidget {
  const AirPlayScreen({
    super.key,
    required this.onPreviousTab,
    required this.onNextTab,
  });
  final VoidCallback onPreviousTab;
  final VoidCallback onNextTab;

  // The existing AppScreen controller owns input. Avoid another subscription
  // (and another activation delay) on each quick swipe through this tab.
  static _AirPlayScreenState? _current;
  static bool get canSwitchTabs => _current?._isCurrent ?? false;
  static bool navigateDown() => _current?._moveFocus(false) ?? false;
  static bool navigateUp() => _current?._moveFocus(true) ?? false;
  static void selectCurrent() {
    final focused = FocusManager.instance.primaryFocus?.context;
    if (_current != null && focused != null) {
      Actions.maybeInvoke(focused, const ActivateIntent());
    }
  }

  static void backCurrent() => _current?._back();

  @override
  State<AirPlayScreen> createState() => _AirPlayScreenState();
}

class _AirPlayScreenState extends State<AirPlayScreen> {
  final _focus = FocusScopeNode(debugLabel: 'AirPlay controls');
  bool get _isCurrent =>
      mounted && (ModalRoute.of(context)?.isCurrent ?? false);

  bool _moveFocus(bool previous) {
    final focused = FocusManager.instance.primaryFocus?.context;
    final scope = !_isCurrent && focused != null
        ? FocusScope.of(focused)
        : _focus;
    return previous ? scope.previousFocus() : scope.nextFocus();
  }

  void _back() {
    if (_isCurrent) {
      widget.onPreviousTab();
    } else if (mounted) {
      unawaited(Navigator.of(context).maybePop());
    }
  }

  @override
  void initState() {
    super.initState();
    AirPlayScreen._current = this;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _focus.requestFocus();
      _focus.nextFocus();
    });
  }

  @override
  void dispose() {
    if (identical(AirPlayScreen._current, this)) AirPlayScreen._current = null;
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SafeArea(
    child: Padding(
      padding: EdgeInsets.fromLTRB(20.r, 54.r, 20.r, 12.r),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: FocusScope(
            node: _focus,
            child: const NeoPlayDialog(embedded: true),
          ),
        ),
      ),
    ),
  );
}
