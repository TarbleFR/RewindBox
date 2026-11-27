import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/gamepad/gamepad_navigation_manager.dart';
import '../utils/gamepad_nav.dart';

Future<void> showWiimmfiMessage(
  BuildContext context, {
  required String title,
  required String message,
  required String closeLabel,
}) => showDialog<void>(
  context: context,
  barrierDismissible: false,
  builder: (_) =>
      _WiimmfiDialog(title: title, message: message, confirmLabel: closeLabel),
);

Future<String?> editWiimmfiErrorCode(
  BuildContext context, {
  required String initialCode,
  required String title,
  required String confirmLabel,
  required String cancelLabel,
}) => showDialog<String>(
  context: context,
  barrierDismissible: false,
  builder: (_) => _WiimmfiDialog(
    title: title,
    initialCode: initialCode,
    confirmLabel: confirmLabel,
    cancelLabel: cancelLabel,
  ),
);

int _nextWiimmfiDialogId = 0;

class _WiimmfiDialog extends StatefulWidget {
  const _WiimmfiDialog({
    required this.title,
    required this.confirmLabel,
    this.message,
    this.initialCode,
    this.cancelLabel,
  });

  final String title;
  final String confirmLabel;
  final String? message;
  final String? initialCode;
  final String? cancelLabel;

  @override
  State<_WiimmfiDialog> createState() => _WiimmfiDialogState();
}

class _WiimmfiDialogState extends State<_WiimmfiDialog> {
  late final GamepadNavigation _navigation;
  final _focus = FocusNode();
  final _scroll = ScrollController();
  final _layer = 'wiimmfi_dialog_${_nextWiimmfiDialogId++}';
  late final List<int> _digits;
  int _position = 0;
  bool _closing = false;
  bool _registered = false;

  bool get _editing => widget.initialCode != null;
  bool get _current =>
      mounted && !_closing && ModalRoute.of(context)?.isCurrent == true;

  @override
  void initState() {
    super.initState();
    final initial = (widget.initialCode ?? '')
        .replaceAll(RegExp(r'[^0-9]'), '')
        .padRight(5, '0')
        .substring(0, 5);
    _digits = initial.codeUnits.map((value) => value - 48).toList();
    _navigation = GamepadNavigation(
      allowRepeat: false,
      isTextFieldFocused: () => false,
      onNavigateLeft: () => _move(-1),
      onNavigateRight: () => _move(1),
      onNavigateUp: () => _changeOrScroll(1),
      onNavigateDown: () => _changeOrScroll(-1),
      onSelectItem: _confirm,
      onBack: _cancel,
      onSettings: _cancel,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _navigation.initialize();
      _registered = true;
      GamepadNavigationManager.pushLayer(
        _layer,
        modal: true,
        onActivate: () {
          if (_current) {
            _navigation.activate();
            _focus.requestFocus();
          }
        },
        onDeactivate: _navigation.deactivate,
      );
    });
  }

  void _close([String? value]) {
    if (!_current) return;
    _closing = true;
    _navigation.deactivate();
    Navigator.of(context).pop(value);
  }

  void _confirm() => _close(_editing ? _digits.join() : null);
  void _cancel() => _close();

  void _move(int delta) {
    if (!_current || !_editing) return;
    setState(() => _position = (_position + delta) % 5);
  }

  void _changeDigit(int index, int delta) {
    if (!_current) return;
    setState(() {
      _position = index;
      _digits[index] = (_digits[index] + delta) % 10;
    });
  }

  void _changeOrScroll(int delta) {
    if (!_current) return;
    if (_editing) {
      _changeDigit(_position, delta);
    } else if (_scroll.hasClients) {
      _scroll.jumpTo(
        (_scroll.offset - delta * 80)
            .clamp(0.0, _scroll.position.maxScrollExtent)
            .toDouble(),
      );
    }
  }

  KeyEventResult _keyEvent(FocusNode node, KeyEvent event) {
    if (!_current) return KeyEventResult.ignored;
    // The global GamepadNavigation keyboard handler owns these keys. Stop
    // route shortcuts/focus traversal from performing a second action.
    if (const [
      LogicalKeyboardKey.arrowLeft,
      LogicalKeyboardKey.arrowRight,
      LogicalKeyboardKey.arrowUp,
      LogicalKeyboardKey.arrowDown,
      LogicalKeyboardKey.enter,
      LogicalKeyboardKey.backspace,
      LogicalKeyboardKey.escape,
      LogicalKeyboardKey.tab,
    ].contains(event.logicalKey)) {
      return KeyEventResult.handled;
    }
    if (!_editing ||
        event is! KeyDownEvent ||
        HardwareKeyboard.instance.isControlPressed ||
        HardwareKeyboard.instance.isAltPressed ||
        HardwareKeyboard.instance.isMetaPressed) {
      return KeyEventResult.ignored;
    }
    final number = int.tryParse(event.character ?? event.logicalKey.keyLabel);
    if (number == null || number < 0 || number > 9) {
      return KeyEventResult.ignored;
    }
    setState(() {
      _digits[_position] = number;
      _position = (_position + 1).clamp(0, 4);
    });
    return KeyEventResult.handled;
  }

  @override
  void dispose() {
    _navigation.deactivate();
    if (_registered) GamepadNavigationManager.popLayer(_layer);
    _navigation.dispose();
    _focus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Widget _digit(int index) {
    final colors = Theme.of(context).colorScheme;
    final selected = index == _position;
    return Expanded(
      child: Semantics(
        value: '${_digits[index]}',
        selected: selected,
        increasedValue: '${(_digits[index] + 1) % 10}',
        decreasedValue: '${(_digits[index] - 1) % 10}',
        onIncrease: () => _changeDigit(index, 1),
        onDecrease: () => _changeDigit(index, -1),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              onPressed: () => _changeDigit(index, 1),
              icon: const Icon(Icons.keyboard_arrow_up),
            ),
            Material(
              color: selected ? colors.primaryContainer : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
              child: InkWell(
                borderRadius: BorderRadius.circular(8),
                onTap: () {
                  if (_current) setState(() => _position = index);
                },
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 6,
                  ),
                  child: Text(
                    '${_digits[index]}',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                ),
              ),
            ),
            IconButton(
              onPressed: () => _changeDigit(index, -1),
              icon: const Icon(Icons.keyboard_arrow_down),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Focus(
    focusNode: _focus,
    autofocus: true,
    onKeyEvent: _keyEvent,
    // Navigation owns arrows/Enter/Back once. Touch controls cannot take
    // keyboard focus and dispatch a second activation for the same key.
    child: ExcludeFocus(
      child: AlertDialog(
        title: Text(widget.title),
        content: _editing
            ? SizedBox(
                width: 300,
                child: Row(children: List.generate(5, _digit)),
              )
            : SingleChildScrollView(
                controller: _scroll,
                child: Text(widget.message ?? ''),
              ),
        actions: [
          if (_editing)
            TextButton(onPressed: _cancel, child: Text(widget.cancelLabel!)),
          FilledButton(onPressed: _confirm, child: Text(widget.confirmLabel)),
        ],
      ),
    ),
  );
}
