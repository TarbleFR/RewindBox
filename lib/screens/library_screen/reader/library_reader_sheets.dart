import 'package:flutter/material.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/widgets/library_reduce_motion.dart';

import 'library_reader_chrome.dart';
import 'library_reader_gamepad.dart';
import 'library_reader_palette.dart';

/// How the readers' sheets and dialogs come and go: without animation when
/// the system asks for reduced motion ([libraryReduceMotion]), else the
/// Material default.
AnimationStyle? libraryReaderSheetAnimation(BuildContext context) =>
    libraryReduceMotion(context) ? AnimationStyle.noAnimation : null;

// ---------------------------------------------------------------------------
// Settings sheet
// ---------------------------------------------------------------------------

/// One row of the reader settings sheet.
sealed class LibraryReaderSettingItem {
  const LibraryReaderSettingItem(this.label);

  final String label;

  /// Whether the controller's focus stops on this row (headers and notes
  /// are skipped).
  bool get focusable => true;
}

/// Title of a group of rows (docs/library-books-3d-plan.md § 3.8:
/// Appearance, Text, Navigation).
class LibraryReaderSectionHeader extends LibraryReaderSettingItem {
  const LibraryReaderSectionHeader(super.title);

  String get title => label;

  @override
  bool get focusable => false;
}

/// A sentence about the rows around it (what a choice implies, where it is
/// kept), or the [confirmation] of an action just done (announced by
/// VoiceOver as it appears).
class LibraryReaderSettingNote extends LibraryReaderSettingItem {
  const LibraryReaderSettingNote(super.text, {this.confirmation = false});

  String get text => label;

  /// Shown by the sheet once a [LibraryReaderActionSetting] with a
  /// confirmation was pressed.
  final bool confirmation;

  @override
  bool get focusable => false;
}

/// A row that does something at once ("Revert to general settings").
class LibraryReaderActionSetting extends LibraryReaderSettingItem {
  const LibraryReaderActionSetting({
    required String label,
    required this.onPressed,
    this.icon,
    this.confirmation,
  }) : super(label);

  final VoidCallback onPressed;
  final IconData? icon;

  /// Said in the sheet once the action is done, at the end of the rows (the
  /// row itself may be gone), until the action is offered again or the
  /// sheet closes: a message at the bottom of the reader would be hidden by
  /// the sheet.
  final String? confirmation;
}

class LibraryReaderSliderSetting extends LibraryReaderSettingItem {
  const LibraryReaderSliderSetting({
    required String label,
    required this.value,
    required this.min,
    required this.max,
    required this.step,
    required this.format,
    required this.onChanged,
  }) : super(label);

  final double value;
  final double min;
  final double max;
  final double step;
  final String Function(double value) format;
  final ValueChanged<double> onChanged;

  int get divisions => ((max - min) / step).round();

  void adjust(int direction) {
    final next = (value + step * direction).clamp(min, max).toDouble();
    if (next != value) onChanged(next);
  }
}

class LibraryReaderChoice<T> {
  const LibraryReaderChoice(this.value, this.label);

  final T value;
  final String label;
}

class LibraryReaderChoiceSetting<T> extends LibraryReaderSettingItem {
  const LibraryReaderChoiceSetting({
    required String label,
    required this.options,
    required this.value,
    required this.onChanged,
  }) : super(label);

  final List<LibraryReaderChoice<T>> options;
  final T value;
  final ValueChanged<T> onChanged;

  // Index based so callers holding a `LibraryReaderChoiceSetting<Object?>`
  // never read [onChanged] through the wider type.
  bool isSelected(int index) => options[index].value == value;

  void select(int index) => onChanged(options[index].value);

  void adjust(int direction) {
    final index = options.indexWhere((option) => option.value == value);
    final next = ((index < 0 ? 0 : index) + direction) % options.length;
    onChanged(options[next < 0 ? next + options.length : next].value);
  }
}

class LibraryReaderToggleSetting extends LibraryReaderSettingItem {
  const LibraryReaderToggleSetting({
    required String label,
    required this.value,
    required this.onChanged,
  }) : super(label);

  final bool value;
  final ValueChanged<bool> onChanged;
}

/// Builds the rows for the current settings; global changes go through
/// [update] ([LibraryReadingStore.updateSettings]), the navigation choices
/// of the open title through a [LibraryReaderBookSettingsEditor]. The rows
/// are built again whenever the store changes.
typedef LibraryReaderSettingsBuilder =
    List<LibraryReaderSettingItem> Function(
      BuildContext context,
      LibraryReaderSettings settings,
      void Function(LibraryReaderSettings settings) update,
    );

/// Shows the settings sheet over a reader. Every change is stored at once
/// (and applied live by the reader, which listens to the store).
///
/// The rows are built again whenever the store changes, and whenever
/// [sessionChanges] notifies (choices a reader keeps for its session only,
/// outside the store).
Future<void> showLibraryReaderSettingsSheet(
  BuildContext context, {
  required LibraryReadingStore store,
  required LibraryReaderPalette palette,
  required LibraryReaderSettingsBuilder builder,
  Listenable? sessionChanges,
}) {
  return showModalBottomSheet<void>(
    context: context,
    useSafeArea: true,
    isScrollControlled: true,
    sheetAnimationStyle: libraryReaderSheetAnimation(context),
    backgroundColor: Color.alphaBlend(
      palette.chromeBackground,
      palette.background,
    ),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (sheetContext) => Theme(
      data: palette.materialTheme(Theme.of(context)),
      child: _LibraryReaderSettingsSheet(
        store: store,
        palette: palette,
        builder: builder,
        sessionChanges: sessionChanges,
      ),
    ),
  );
}

class _LibraryReaderSettingsSheet extends StatefulWidget {
  const _LibraryReaderSettingsSheet({
    required this.store,
    required this.palette,
    required this.builder,
    this.sessionChanges,
  });

  final LibraryReadingStore store;
  final LibraryReaderPalette palette;
  final LibraryReaderSettingsBuilder builder;
  final Listenable? sessionChanges;

  @override
  State<_LibraryReaderSettingsSheet> createState() =>
      _LibraryReaderSettingsSheetState();
}

class _LibraryReaderSettingsSheetState
    extends State<_LibraryReaderSettingsSheet> {
  late LibraryReaderSettings _settings;
  final ScrollController _scroll = ScrollController();
  final List<GlobalKey> _rowKeys = <GlobalKey>[];
  int _focus = 0;
  bool _gamepadUsed = false;

  /// Confirmation of the action last pressed ([LibraryReaderActionSetting.
  /// confirmation]), shown after the rows.
  String? _confirmation;

  @override
  void initState() {
    super.initState();
    _settings = widget.store.settings;
    widget.store.addListener(_onStore);
    widget.sessionChanges?.addListener(_onStore);
  }

  @override
  void dispose() {
    widget.store.removeListener(_onStore);
    widget.sessionChanges?.removeListener(_onStore);
    _scroll.dispose();
    super.dispose();
  }

  void _onStore() {
    // Also the title's navigation settings, which the rows show: built
    // again whatever changed.
    if (!mounted) return;
    setState(() => _settings = widget.store.settings);
  }

  void _update(LibraryReaderSettings settings) {
    widget.store.updateSettings(settings);
    // The store clamps; show what it kept.
    setState(() => _settings = widget.store.settings);
  }

  /// Runs [action] (a tap, or A on the controller), then says its
  /// confirmation, if it has one (an action without one ends the previous
  /// confirmation).
  void _press(LibraryReaderActionSetting action) {
    action.onPressed();
    if (mounted) setState(() => _confirmation = action.confirmation);
  }

  /// The rows of [widget.builder], then the confirmation of the action
  /// last pressed, until that action is offered again.
  List<LibraryReaderSettingItem> _items(BuildContext context) {
    final items = widget.builder(context, _settings, _update);
    final confirmation = _confirmation;
    if (confirmation == null) return items;
    final offered = items.any(
      (item) =>
          item is LibraryReaderActionSetting &&
          item.confirmation == confirmation,
    );
    if (offered) {
      // The action can be done again: its confirmation is past.
      _confirmation = null;
      return items;
    }
    return <LibraryReaderSettingItem>[
      ...items,
      LibraryReaderSettingNote(confirmation, confirmation: true),
    ];
  }

  /// Indices of the rows the focus stops on.
  static List<int> _stops(List<LibraryReaderSettingItem> items) => <int>[
    for (var index = 0; index < items.length; index++)
      if (items[index].focusable) index,
  ];

  /// The focused row: the one at [_focus] when the focus can stop there,
  /// else the next row it can stop on.
  int? _focused(List<LibraryReaderSettingItem> items) {
    final stops = _stops(items);
    if (stops.isEmpty) return null;
    for (final stop in stops) {
      if (stop >= _focus) return stop;
    }
    return stops.last;
  }

  void _moveFocus(int delta, List<LibraryReaderSettingItem> items) {
    final stops = _stops(items);
    if (stops.isEmpty) return;
    final at = stops.indexOf(_focused(items)!);
    final target = stops[(at + delta).clamp(0, stops.length - 1)];
    setState(() {
      _gamepadUsed = true;
      _focus = target;
    });
    final key = _focus < _rowKeys.length ? _rowKeys[_focus] : null;
    final rowContext = key?.currentContext;
    if (rowContext != null) {
      Scrollable.ensureVisible(
        rowContext,
        duration: libraryReduceMotion(context)
            ? Duration.zero
            : const Duration(milliseconds: 150),
        alignmentPolicy: delta > 0
            ? ScrollPositionAlignmentPolicy.keepVisibleAtEnd
            : ScrollPositionAlignmentPolicy.keepVisibleAtStart,
      );
    }
  }

  void _adjust(List<LibraryReaderSettingItem> items, int direction) {
    final focused = _focused(items);
    if (focused == null) return;
    setState(() {
      _gamepadUsed = true;
      _focus = focused;
    });
    switch (items[focused]) {
      case final LibraryReaderSliderSetting slider:
        slider.adjust(direction);
      case final LibraryReaderChoiceSetting<Object?> choice:
        choice.adjust(direction);
      case final LibraryReaderToggleSetting toggle:
        toggle.onChanged(direction > 0);
      case LibraryReaderActionSetting():
      case LibraryReaderSectionHeader():
      case LibraryReaderSettingNote():
        break;
    }
  }

  void _activate(List<LibraryReaderSettingItem> items) {
    final focused = _focused(items);
    if (focused == null) return;
    setState(() {
      _gamepadUsed = true;
      _focus = focused;
    });
    switch (items[focused]) {
      case final LibraryReaderSliderSetting slider:
        slider.adjust(1);
      case final LibraryReaderChoiceSetting<Object?> choice:
        choice.adjust(1);
      case final LibraryReaderToggleSetting toggle:
        toggle.onChanged(!toggle.value);
      case final LibraryReaderActionSetting action:
        _press(action);
      case LibraryReaderSectionHeader():
      case LibraryReaderSettingNote():
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    final palette = widget.palette;
    final items = _items(context);
    while (_rowKeys.length < items.length) {
      _rowKeys.add(GlobalKey());
    }
    final focused = _gamepadUsed ? _focused(items) : null;
    final maxHeight = MediaQuery.sizeOf(context).height * 0.8;
    return LibraryReaderGamepadScope(
      name: 'library_reader_settings',
      bindings: LibraryReaderGamepadBindings(
        up: () => _moveFocus(-1, items),
        down: () => _moveFocus(1, items),
        left: () => _adjust(items, -1),
        right: () => _adjust(items, 1),
        select: () => _activate(items),
        back: () => Navigator.of(context).maybePop(),
        start: () => Navigator.of(context).maybePop(),
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: maxHeight),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            LibraryReaderSheetHeader(
              palette: palette,
              title: LibraryReaderLocale.text(context, 'settingsTitle'),
            ),
            Flexible(
              child: ListView.builder(
                controller: _scroll,
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                itemCount: items.length,
                itemBuilder: (context, index) => Container(
                  key: _rowKeys[index],
                  margin: const EdgeInsets.symmetric(vertical: 2),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: index == focused
                          ? palette.accent
                          : Colors.transparent,
                      width: 2,
                    ),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  child: _SettingRow(
                    item: items[index],
                    palette: palette,
                    onAction: _press,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SettingRow extends StatelessWidget {
  const _SettingRow({
    required this.item,
    required this.palette,
    required this.onAction,
  });

  final LibraryReaderSettingItem item;
  final LibraryReaderPalette palette;

  /// Runs an action row (and shows its confirmation).
  final ValueChanged<LibraryReaderActionSetting> onAction;

  @override
  Widget build(BuildContext context) {
    final labelStyle = TextStyle(
      color: palette.chromeForeground,
      fontSize: 15,
      fontWeight: FontWeight.w600,
    );
    switch (item) {
      case final LibraryReaderSliderSetting slider:
        return Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  Expanded(child: Text(slider.label, style: labelStyle)),
                  Text(
                    slider.format(slider.value),
                    style: TextStyle(
                      color: palette.secondaryText,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
              SizedBox(
                height: kLibraryReaderTouchTarget,
                child: Slider(
                  value: slider.value.clamp(slider.min, slider.max).toDouble(),
                  min: slider.min,
                  max: slider.max,
                  divisions: slider.divisions > 0 ? slider.divisions : null,
                  label: slider.format(slider.value),
                  semanticFormatterCallback: slider.format,
                  onChanged: slider.onChanged,
                ),
              ),
            ],
          ),
        );
      case final LibraryReaderChoiceSetting<Object?> choice:
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(choice.label, style: labelStyle),
              const SizedBox(height: 6),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: <Widget>[
                  for (var index = 0; index < choice.options.length; index++)
                    ChoiceChip(
                      label: Text(choice.options[index].label),
                      selected: choice.isSelected(index),
                      materialTapTargetSize: MaterialTapTargetSize.padded,
                      onSelected: (_) => choice.select(index),
                    ),
                ],
              ),
            ],
          ),
        );
      case final LibraryReaderToggleSetting toggle:
        return SwitchListTile.adaptive(
          contentPadding: EdgeInsets.zero,
          title: Text(toggle.label, style: labelStyle),
          value: toggle.value,
          onChanged: toggle.onChanged,
        );
      case final LibraryReaderSectionHeader header:
        return Padding(
          padding: const EdgeInsets.only(top: 16, bottom: 2),
          child: Semantics(
            header: true,
            child: Text(
              header.title,
              style: TextStyle(
                color: palette.accent,
                fontSize: 14,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.3,
              ),
            ),
          ),
        );
      case final LibraryReaderSettingNote note when note.confirmation:
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          // Read by VoiceOver as it appears.
          child: Semantics(
            liveRegion: true,
            container: true,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(
                  Icons.check_circle_rounded,
                  size: 18,
                  color: palette.accent,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    note.text,
                    style: TextStyle(
                      color: palette.chromeForeground,
                      fontSize: 14,
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      case final LibraryReaderSettingNote note:
        return Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Text(
            note.text,
            style: TextStyle(color: palette.secondaryText, fontSize: 13),
          ),
        );
      case final LibraryReaderActionSetting action:
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child: LibraryReaderTextButton(
              label: action.label,
              icon: action.icon,
              palette: palette,
              onPressed: () => onAction(action),
            ),
          ),
        );
    }
  }
}

/// Title row of a reader sheet: a grabber, the title and Close.
class LibraryReaderSheetHeader extends StatelessWidget {
  const LibraryReaderSheetHeader({
    super.key,
    required this.palette,
    required this.title,
  });

  final LibraryReaderPalette palette;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 8, 4),
      child: Column(
        children: <Widget>[
          Container(
            width: 36,
            height: 5,
            decoration: BoxDecoration(
              color: palette.divider,
              borderRadius: BorderRadius.circular(3),
            ),
          ),
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    color: palette.chromeForeground,
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              LibraryReaderIconButton(
                icon: Icons.close_rounded,
                tooltip: LibraryReaderLocale.text(context, 'close'),
                onPressed: () => Navigator.of(context).maybePop(),
                color: palette.chromeForeground,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// List sheet (table of contents, PDF outline)
// ---------------------------------------------------------------------------

@immutable
class LibraryReaderListEntry {
  const LibraryReaderListEntry({
    required this.title,
    this.depth = 0,
    this.enabled = true,
    this.trailing,
  });

  final String title;
  final int depth;
  final bool enabled;

  /// Short untranslated trailing text (a page number).
  final String? trailing;
}

/// Shows a list (table of contents) and returns the chosen index.
Future<int?> showLibraryReaderListSheet(
  BuildContext context, {
  required LibraryReaderPalette palette,
  required String title,
  required List<LibraryReaderListEntry> entries,
  int? currentIndex,
  String? emptyMessage,
}) {
  return showModalBottomSheet<int>(
    context: context,
    useSafeArea: true,
    isScrollControlled: true,
    sheetAnimationStyle: libraryReaderSheetAnimation(context),
    backgroundColor: Color.alphaBlend(
      palette.chromeBackground,
      palette.background,
    ),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (_) => Theme(
      data: palette.materialTheme(Theme.of(context)),
      child: _LibraryReaderListSheet(
        palette: palette,
        title: title,
        entries: entries,
        currentIndex: currentIndex,
        emptyMessage: emptyMessage,
      ),
    ),
  );
}

class _LibraryReaderListSheet extends StatefulWidget {
  const _LibraryReaderListSheet({
    required this.palette,
    required this.title,
    required this.entries,
    this.currentIndex,
    this.emptyMessage,
  });

  final LibraryReaderPalette palette;
  final String title;
  final List<LibraryReaderListEntry> entries;
  final int? currentIndex;
  final String? emptyMessage;

  @override
  State<_LibraryReaderListSheet> createState() =>
      _LibraryReaderListSheetState();
}

class _LibraryReaderListSheetState extends State<_LibraryReaderListSheet> {
  static const double _rowHeight = 52;
  late final ScrollController _scroll;
  late int _focus;
  bool _gamepadUsed = false;

  @override
  void initState() {
    super.initState();
    _focus = (widget.currentIndex ?? 0).clamp(
      0,
      widget.entries.isEmpty ? 0 : widget.entries.length - 1,
    );
    _scroll = ScrollController(
      initialScrollOffset: _focus > 2 ? (_focus - 2) * _rowHeight : 0,
    );
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _move(int delta) {
    if (widget.entries.isEmpty) return;
    setState(() {
      _gamepadUsed = true;
      _focus = (_focus + delta).clamp(0, widget.entries.length - 1);
    });
    if (!_scroll.hasClients) return;
    final position = _scroll.position;
    final top = _focus * _rowHeight;
    final bottom = top + _rowHeight;
    if (top < position.pixels) {
      _scroll.jumpTo(top);
    } else if (bottom > position.pixels + position.viewportDimension) {
      _scroll.jumpTo(
        (bottom - position.viewportDimension).clamp(
          0.0,
          position.maxScrollExtent,
        ),
      );
    }
  }

  void _choose(int index) {
    if (index < 0 || index >= widget.entries.length) return;
    if (!widget.entries[index].enabled) return;
    Navigator.of(context).pop(index);
  }

  @override
  Widget build(BuildContext context) {
    final palette = widget.palette;
    final maxHeight = MediaQuery.sizeOf(context).height * 0.8;
    return LibraryReaderGamepadScope(
      name: 'library_reader_list',
      bindings: LibraryReaderGamepadBindings(
        up: () => _move(-1),
        down: () => _move(1),
        leftBumper: () => _move(-8),
        rightBumper: () => _move(8),
        select: () => _choose(_focus),
        back: () => Navigator.of(context).maybePop(),
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: maxHeight),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            LibraryReaderSheetHeader(palette: palette, title: widget.title),
            if (widget.entries.isEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
                child: Text(
                  widget.emptyMessage ?? '',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: palette.secondaryText, fontSize: 15),
                ),
              )
            else
              Flexible(
                child: ListView.builder(
                  controller: _scroll,
                  shrinkWrap: true,
                  itemExtent: _rowHeight,
                  padding: const EdgeInsets.only(bottom: 16),
                  itemCount: widget.entries.length,
                  itemBuilder: (context, index) {
                    final entry = widget.entries[index];
                    final current = index == widget.currentIndex;
                    final focused = _gamepadUsed && index == _focus;
                    return InkWell(
                      onTap: entry.enabled ? () => _choose(index) : null,
                      child: Container(
                        decoration: BoxDecoration(
                          color: current
                              ? palette.accent.withValues(alpha: 0.14)
                              : null,
                          border: Border.all(
                            color: focused
                                ? palette.accent
                                : Colors.transparent,
                            width: 2,
                          ),
                        ),
                        padding: EdgeInsets.only(
                          left: 20 + 16.0 * entry.depth.clamp(0, 6),
                          right: 20,
                        ),
                        alignment: AlignmentDirectional.centerStart,
                        child: Row(
                          children: <Widget>[
                            Expanded(
                              child: Text(
                                entry.title,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: current
                                      ? FontWeight.w700
                                      : FontWeight.w400,
                                  color: entry.enabled
                                      ? palette.chromeForeground
                                      : palette.secondaryText,
                                ),
                              ),
                            ),
                            if (entry.trailing != null)
                              Text(
                                entry.trailing!,
                                style: TextStyle(
                                  color: palette.secondaryText,
                                  fontSize: 14,
                                ),
                              ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// External link confirmation
// ---------------------------------------------------------------------------

/// Asks before an https link of a book is opened outside NeoStation. The
/// address is shown as is (untranslated) under the translated question.
Future<bool> showLibraryReaderLinkDialog(
  BuildContext context, {
  required LibraryReaderPalette palette,
  required Uri uri,
}) async {
  final result = await showDialog<bool>(
    context: context,
    animationStyle: libraryReaderSheetAnimation(context),
    builder: (dialogContext) => Theme(
      data: palette.materialTheme(Theme.of(context)),
      child: LibraryReaderGamepadScope(
        name: 'library_reader_link',
        bindings: LibraryReaderGamepadBindings(
          select: () => Navigator.of(dialogContext).pop(true),
          back: () => Navigator.of(dialogContext).pop(false),
        ),
        child: AlertDialog(
          title: Text(LibraryReaderLocale.text(dialogContext, 'openLinkTitle')),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(LibraryReaderLocale.text(dialogContext, 'openLinkBody')),
              const SizedBox(height: 12),
              SelectableText(
                uri.toString(),
                style: TextStyle(color: palette.secondaryText, fontSize: 13),
              ),
            ],
          ),
          actions: <Widget>[
            TextButton(
              style: TextButton.styleFrom(
                minimumSize: const Size(64, kLibraryReaderTouchTarget),
              ),
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: Text(LibraryReaderLocale.text(dialogContext, 'cancel')),
            ),
            TextButton(
              style: TextButton.styleFrom(
                minimumSize: const Size(64, kLibraryReaderTouchTarget),
              ),
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: Text(LibraryReaderLocale.text(dialogContext, 'openLink')),
            ),
          ],
        ),
      ),
    ),
  );
  return result ?? false;
}

// ---------------------------------------------------------------------------
// Messages
// ---------------------------------------------------------------------------

/// Shows the translated message [key] at the bottom of a reader for a few
/// seconds (a bookmark added, a jump that failed), with an untranslated
/// technical [detail] under it when there is one.
void showLibraryReaderMessage(
  BuildContext context,
  String key, {
  String? detail,
}) {
  final text = LibraryReaderLocale.text(context, key);
  ScaffoldMessenger.maybeOf(context)
    ?..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(text),
            if (detail != null)
              Text(
                detail,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 12),
              ),
          ],
        ),
        duration: const Duration(seconds: 3),
      ),
    );
}

// ---------------------------------------------------------------------------
// Settings rows shared by the readers
// ---------------------------------------------------------------------------

/// Where a reader's navigation choices are kept (docs/library-books-3d-plan.md
/// § 3.8): changed from a reader, the rows of the Navigation section whose
/// setting exists in [LibraryReaderBookSettings] (page turn, double page,
/// first page alone, direction, reading mode, PDF display, text layout) are
/// written for the open title only, under `bookSettings[key]`; the readers
/// apply them with `LibraryReaderEffectiveSettings` (session > title >
/// content hint > global). A reader without a title [key] writes them
/// globally.
@immutable
class LibraryReaderBookSettingsEditor {
  const LibraryReaderBookSettingsEditor({
    required this.store,
    required this.key,
    this.hintedDirection,
  });

  final LibraryReadingStore store;

  /// Reading key of the title; empty when the reader saves nothing.
  final String key;

  /// The direction the content gives this title when it has none of its
  /// own, where the content decides before the general settings: the
  /// layout hint of the page reader in automatic mode
  /// (`LibraryReaderEffectiveSettings.hintedDirection`), the book's own
  /// direction for EPUB and TXT, left to right for PDFs (the general
  /// direction never applies to them). Null when the general direction
  /// applies (the page reader without a hint).
  final LibraryPageDirection? hintedDirection;

  /// Whether the choices are kept for the title (it has a key).
  bool get perBook => key.isNotEmpty;

  /// The title's own choices (null: it follows the global settings).
  LibraryReaderBookSettings? get settings =>
      perBook ? store.bookSettingsFor(key) : null;

  /// Whether the title has choices of its own ("Revert to general
  /// settings" is offered).
  bool get hasOwnSettings => settings != null;

  /// Writes [change] of the title's choices.
  void update(
    LibraryReaderBookSettings Function(LibraryReaderBookSettings settings)
    change,
  ) {
    if (!perBook) return;
    store.updateBookSettings(
      key,
      change(settings ?? const LibraryReaderBookSettings()),
    );
  }

  /// The title follows the global settings again.
  void reset() {
    if (perBook) store.clearBookSettings(key);
  }

  /// The general settings with the title's choices [own] (each field it
  /// sets).
  static LibraryReaderSettings _applied(
    LibraryReaderSettings global,
    LibraryReaderBookSettings own,
  ) => global.copyWith(
    turnStyle: own.turnStyle,
    doublePage: own.doublePage,
    firstPageAlone: own.firstPageAlone,
    pageDirection: own.pageDirection,
    mangaMode: own.mangaMode,
    pdfMode: own.pdfMode,
    textLayout: own.textLayout,
  );

  /// What the title keeps of [own] once its choices are the general ones:
  /// the fields its content would otherwise decide differently (the hint
  /// comes before the general settings), that is a direction other than
  /// [hintedDirection]; nothing else. Every other field resolves to the
  /// general value just written, the same.
  LibraryReaderBookSettings _kept(LibraryReaderBookSettings own) {
    final direction = own.pageDirection;
    final hinted = hintedDirection;
    if (direction != null && hinted != null && direction != hinted) {
      return LibraryReaderBookSettings(pageDirection: direction);
    }
    return const LibraryReaderBookSettings();
  }

  /// Whether "Apply to all books" changes anything: the title has choices
  /// of its own that are not the general ones yet, or that it does not
  /// need to keep.
  bool get canApplyToAllBooks {
    final own = settings;
    if (own == null) return false;
    final global = store.settings;
    return _applied(global, own) != global || _kept(own) != own;
  }

  /// "Apply to all books": the title's navigation choices become the
  /// general ones (each field it sets is written into the global settings)
  /// and the title follows them again, except where its content would
  /// then decide otherwise (a direction against [hintedDirection], kept
  /// for the title): the title shows exactly what it showed. Titles with
  /// choices of their own keep them. Nothing happens without choices of
  /// its own.
  void applyToAllBooks() {
    final own = settings;
    if (own == null) return;
    store.updateSettings(_applied(store.settings, own));
    // Empty settings clear the entry.
    store.updateBookSettings(key, _kept(own));
  }
}

/// Rows common to the readers: the Appearance section, the navigation
/// choices kept per title, the global rows of the Navigation section
/// (toolbar, tap zones, screen and rotation) and "Revert to general
/// settings".
abstract final class LibraryReaderCommonSettings {
  static LibraryReaderChoiceSetting<LibraryReaderTheme> theme(
    BuildContext context,
    LibraryReaderSettings settings,
    void Function(LibraryReaderSettings) update, {
    String labelKey = 'theme',
  }) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    return LibraryReaderChoiceSetting<LibraryReaderTheme>(
      label: t(labelKey),
      value: settings.theme,
      options: <LibraryReaderChoice<LibraryReaderTheme>>[
        LibraryReaderChoice(LibraryReaderTheme.system, t('themeSystem')),
        LibraryReaderChoice(LibraryReaderTheme.light, t('themeLight')),
        LibraryReaderChoice(LibraryReaderTheme.sepia, t('themeSepia')),
        LibraryReaderChoice(LibraryReaderTheme.dark, t('themeDark')),
        LibraryReaderChoice(LibraryReaderTheme.black, t('themeBlack')),
      ],
      onChanged: (value) => update(settings.copyWith(theme: value)),
    );
  }

  /// The Appearance section (global): theme or background, bookmark
  /// ribbon.
  static List<LibraryReaderSettingItem> appearance(
    BuildContext context,
    LibraryReaderSettings settings,
    void Function(LibraryReaderSettings) update, {
    String themeLabelKey = 'theme',
  }) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    return <LibraryReaderSettingItem>[
      LibraryReaderSectionHeader(t('sectionAppearance')),
      theme(context, settings, update, labelKey: themeLabelKey),
      LibraryReaderToggleSetting(
        label: t('bookmarkRibbon'),
        value: settings.bookmarkRibbon,
        onChanged: (value) => update(settings.copyWith(bookmarkRibbon: value)),
      ),
    ];
  }

  /// Title of the Navigation section, and that its choices are kept for
  /// this title.
  static List<LibraryReaderSettingItem> navigationHeader(
    BuildContext context,
    LibraryReaderBookSettingsEditor editor,
  ) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    return <LibraryReaderSettingItem>[
      LibraryReaderSectionHeader(t('sectionNavigation')),
      if (editor.perBook) LibraryReaderSettingNote(t('navigationPerBookNote')),
    ];
  }

  /// Writes a navigation choice for the title ([book]), or globally
  /// ([global]) for a reader without a title key.
  static void write(
    LibraryReaderBookSettingsEditor editor,
    LibraryReaderSettings settings,
    void Function(LibraryReaderSettings) update, {
    required LibraryReaderBookSettings Function(LibraryReaderBookSettings) book,
    required LibraryReaderSettings Function(LibraryReaderSettings) global,
  }) {
    if (editor.perBook) {
      editor.update(book);
    } else {
      update(global(settings));
    }
  }

  /// Page turn of the paged layouts (kept per title).
  static LibraryReaderChoiceSetting<LibraryPageTurnStyle> turnStyle(
    BuildContext context,
    LibraryReaderSettings settings,
    void Function(LibraryReaderSettings) update,
    LibraryReaderBookSettingsEditor editor,
  ) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    return LibraryReaderChoiceSetting<LibraryPageTurnStyle>(
      label: t('turnStyle'),
      value: editor.settings?.turnStyle ?? settings.turnStyle,
      options: <LibraryReaderChoice<LibraryPageTurnStyle>>[
        LibraryReaderChoice(LibraryPageTurnStyle.curl, t('turnCurl')),
        LibraryReaderChoice(LibraryPageTurnStyle.slide, t('turnSlide')),
        LibraryReaderChoice(LibraryPageTurnStyle.none, t('turnNone')),
      ],
      onChanged: (value) => write(
        editor,
        settings,
        update,
        book: (book) => book.copyWith(turnStyle: value),
        global: (global) => global.copyWith(turnStyle: value),
      ),
    );
  }

  /// Two pages side by side (kept per title).
  static LibraryReaderChoiceSetting<LibraryDoublePageMode> doublePage(
    BuildContext context,
    LibraryReaderSettings settings,
    void Function(LibraryReaderSettings) update,
    LibraryReaderBookSettingsEditor editor,
  ) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    return LibraryReaderChoiceSetting<LibraryDoublePageMode>(
      label: t('doublePage'),
      value: editor.settings?.doublePage ?? settings.doublePage,
      options: <LibraryReaderChoice<LibraryDoublePageMode>>[
        LibraryReaderChoice(LibraryDoublePageMode.auto, t('doublePageAuto')),
        LibraryReaderChoice(
          LibraryDoublePageMode.always,
          t('doublePageAlways'),
        ),
        LibraryReaderChoice(LibraryDoublePageMode.never, t('doublePageNever')),
      ],
      onChanged: (value) => write(
        editor,
        settings,
        update,
        book: (book) => book.copyWith(doublePage: value),
        global: (global) => global.copyWith(doublePage: value),
      ),
    );
  }

  /// The cover alone in a two-page layout (kept per title).
  static LibraryReaderToggleSetting firstPageAlone(
    BuildContext context,
    LibraryReaderSettings settings,
    void Function(LibraryReaderSettings) update,
    LibraryReaderBookSettingsEditor editor,
  ) {
    return LibraryReaderToggleSetting(
      label: LibraryReaderLocale.text(context, 'firstPageAlone'),
      value: editor.settings?.firstPageAlone ?? settings.firstPageAlone,
      onChanged: (value) => write(
        editor,
        settings,
        update,
        book: (book) => book.copyWith(firstPageAlone: value),
        global: (global) => global.copyWith(firstPageAlone: value),
      ),
    );
  }

  /// Page direction (kept per title); [value] is the direction in use,
  /// which the content's hint may decide. A reader whose titles never
  /// follow the general direction (PDF) passes [withoutKey]: without a
  /// title key the choice then lasts for its session instead of being
  /// written globally.
  static LibraryReaderChoiceSetting<LibraryPageDirection> pageDirection(
    BuildContext context,
    LibraryReaderSettings settings,
    void Function(LibraryReaderSettings) update,
    LibraryReaderBookSettingsEditor editor, {
    required LibraryPageDirection value,
    ValueChanged<LibraryPageDirection>? withoutKey,
  }) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    return LibraryReaderChoiceSetting<LibraryPageDirection>(
      label: t('pageDirection'),
      value: value,
      options: <LibraryReaderChoice<LibraryPageDirection>>[
        LibraryReaderChoice(LibraryPageDirection.ltr, t('directionLtr')),
        LibraryReaderChoice(LibraryPageDirection.rtl, t('directionRtl')),
      ],
      onChanged: (direction) {
        if (!editor.perBook && withoutKey != null) {
          withoutKey(direction);
          return;
        }
        write(
          editor,
          settings,
          update,
          book: (book) => book.copyWith(pageDirection: direction),
          global: (global) => global.copyWith(pageDirection: direction),
        );
      },
    );
  }

  /// Toolbar hidden after 4 s or always shown (global).
  static LibraryReaderChoiceSetting<LibraryReaderToolbarMode> toolbarMode(
    BuildContext context,
    LibraryReaderSettings settings,
    void Function(LibraryReaderSettings) update,
  ) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    return LibraryReaderChoiceSetting<LibraryReaderToolbarMode>(
      label: t('toolbarMode'),
      value: settings.toolbarMode,
      options: <LibraryReaderChoice<LibraryReaderToolbarMode>>[
        LibraryReaderChoice(LibraryReaderToolbarMode.auto, t('toolbarAuto')),
        LibraryReaderChoice(
          LibraryReaderToolbarMode.always,
          t('toolbarAlways'),
        ),
      ],
      onChanged: (value) => update(settings.copyWith(toolbarMode: value)),
    );
  }

  /// The global rows ending the Navigation section: toolbar, tap zones
  /// (where the reader has them), screen kept on, rotation.
  static List<LibraryReaderSettingItem> navigationTail(
    BuildContext context,
    LibraryReaderSettings settings,
    void Function(LibraryReaderSettings) update, {
    bool tapZones = true,
  }) => <LibraryReaderSettingItem>[
    toolbarMode(context, settings, update),
    ...toggles(context, settings, update, tapZones: tapZones),
  ];

  /// "Settings specific to this book", "Apply to all books" (its
  /// navigation choices become the general ones, confirmed in the sheet;
  /// offered while it would change something) and "Revert to general
  /// settings", while the title has navigation choices of its own.
  static List<LibraryReaderSettingItem> bookReset(
    BuildContext context,
    LibraryReaderBookSettingsEditor editor,
  ) {
    if (!editor.hasOwnSettings) return const <LibraryReaderSettingItem>[];
    String t(String key) => LibraryReaderLocale.text(context, key);
    return <LibraryReaderSettingItem>[
      LibraryReaderSettingNote(t('bookSettingsActive')),
      if (editor.canApplyToAllBooks)
        LibraryReaderActionSetting(
          label: t('applyNavigationToAllBooks'),
          icon: Icons.library_books_rounded,
          onPressed: editor.applyToAllBooks,
          confirmation: t('navigationAppliedToAllBooks'),
        ),
      LibraryReaderActionSetting(
        label: t('resetBookSettings'),
        icon: Icons.settings_backup_restore_rounded,
        onPressed: editor.reset,
      ),
    ];
  }

  static List<LibraryReaderSettingItem> toggles(
    BuildContext context,
    LibraryReaderSettings settings,
    void Function(LibraryReaderSettings) update, {
    bool tapZones = true,
  }) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    return <LibraryReaderSettingItem>[
      if (tapZones)
        LibraryReaderToggleSetting(
          label: t('tapZones'),
          value: settings.tapZones,
          onChanged: (value) => update(settings.copyWith(tapZones: value)),
        ),
      LibraryReaderToggleSetting(
        label: t('keepScreenOn'),
        value: settings.keepScreenOn,
        onChanged: (value) => update(settings.copyWith(keepScreenOn: value)),
      ),
      LibraryReaderToggleSetting(
        label: t('allowRotation'),
        value: settings.allowRotation,
        onChanged: (value) => update(settings.copyWith(allowRotation: value)),
      ),
    ];
  }
}
