import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

/// The import segment used inside the media pill and in standalone toolbars.
class PlaylistImportButton extends StatelessWidget {
  const PlaylistImportButton({
    super.key,
    required this.menuKey,
    required this.tooltip,
    required this.busy,
    required this.embedded,
    required this.items,
    required this.onSelected,
    this.onOpened,
    this.onCanceled,
  });
  final Key menuKey;
  final String tooltip;
  final bool busy, embedded;
  final List<PopupMenuEntry<String>> Function(BuildContext) items;
  final ValueChanged<String> onSelected;
  final VoidCallback? onOpened, onCanceled;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final background = embedded ? scheme.surface : scheme.tertiaryFixed;
    var foreground = embedded ? scheme.onSurface : scheme.onTertiaryFixed;
    final light = foreground.computeLuminance();
    final dark = background.computeLuminance();
    final contrast =
        ((light > dark ? light : dark) + .05) /
        ((light < dark ? light : dark) + .05);
    if (contrast < 3) {
      foreground = dark <= .179 ? Colors.white : Colors.black;
    }
    final button = SizedBox(
      width: 36.r,
      height: 36.r,
      child: PopupMenuButton<String>(
        key: menuKey,
        tooltip: tooltip,
        enabled: !busy,
        padding: EdgeInsets.zero,
        onOpened: onOpened,
        onCanceled: onCanceled,
        onSelected: onSelected,
        itemBuilder: items,
        icon: busy
            ? SizedBox(
                width: 18.r,
                height: 18.r,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: foreground,
                ),
              )
            : Icon(Icons.file_upload_outlined, size: 18.r, color: foreground),
      ),
    );
    if (embedded) return button;
    return Material(
      color: scheme.tertiaryFixed,
      borderRadius: BorderRadius.circular(10.r),
      elevation: 2,
      child: button,
    );
  }
}
