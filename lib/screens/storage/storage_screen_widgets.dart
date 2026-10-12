/// Shared pieces of the storage pages (docs/storage-audit-cleanup.md § 3.10):
/// section cards, focusable read-only blocks, warning badges and the
/// expandable rows of the folder tree. Every label is a [StorageLocale] text;
/// sizes, paths, root ids and codes are raw values shown apart, never
/// translated.
library;

import 'package:flutter/material.dart';

import '../../l10n/storage_locale.dart';
import '../../services/rpcs3_save_exchange_service.dart';
import '../libretro/libretro_skin_manager_screen.dart';

/// Decimal size, as the Files app shows it (never translated).
String storageSize(int bytes) =>
    Rpcs3SaveExchangeService.formatBytes(bytes < 0 ? 0 : bytes);

/// Monospace style of the raw values (paths, ids, codes).
TextStyle? storageRawStyle(BuildContext context) =>
    Theme.of(context).textTheme.bodySmall?.copyWith(fontFamily: 'monospace');

/// A titled card of the storage pages.
class StorageSectionCard extends StatelessWidget {
  const StorageSectionCard({
    super.key,
    required this.icon,
    required this.title,
    required this.children,
  });

  final IconData icon;
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(icon, color: theme.colorScheme.primary),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(title, style: theme.textTheme.titleMedium),
                ),
              ],
            ),
            const SizedBox(height: 8),
            ...children,
          ],
        ),
      ),
    );
  }
}

/// A read-only block the controller can reach: the D-pad stops on it, so
/// the page scrolls to it and its outline shows where the user is (texts
/// at the end of a page would otherwise stay out of reach).
class StorageFocusable extends StatelessWidget {
  const StorageFocusable({super.key, required this.child, this.radius = 12});

  final Widget child;
  final double radius;

  @override
  Widget build(BuildContext context) => LibretroFocusRing(
    radius: radius,
    child: Focus(child: child),
  );
}

/// A warning shown on a candidate and repeated in the confirmation.
class StorageWarningBadge extends StatelessWidget {
  const StorageWarningBadge({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = Colors.amber.shade800;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.warning_amber_rounded,
            size: 16,
            color: color,
            semanticLabel: StorageLocale.text(
              context,
              StorageLocale.warningTitle,
            ),
          ),
          const SizedBox(width: 6),
          Flexible(child: Text(text, style: theme.textTheme.labelSmall)),
        ],
      ),
    );
  }
}

/// A row of the folder tree or of a preview group that opens on demand. Its
/// children are built only while it is open; the header is one focusable
/// tile (A or a tap opens and closes it).
class StorageExpandableTile extends StatefulWidget {
  const StorageExpandableTile({
    super.key,
    required this.title,
    required this.childrenBuilder,
    this.subtitle,
    this.leading,
    this.trailing,
    this.initiallyExpanded = false,
    this.indent = 0,
    this.headerKey,
  });

  final Widget title;
  final Widget? subtitle;
  final Widget? leading;
  final Widget? trailing;
  final List<Widget> Function(BuildContext context) childrenBuilder;
  final bool initiallyExpanded;
  final double indent;

  /// Key of the header tile (tests tap it).
  final Key? headerKey;

  @override
  State<StorageExpandableTile> createState() => _StorageExpandableTileState();
}

class _StorageExpandableTileState extends State<StorageExpandableTile> {
  late bool _expanded = widget.initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    final label = StorageLocale.text(
      context,
      _expanded ? StorageLocale.detailsHide : StorageLocale.detailsShow,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        LibretroFocusRing(
          radius: 12,
          child: ListTile(
            key: widget.headerKey,
            contentPadding: EdgeInsetsDirectional.only(
              start: 8 + widget.indent,
              end: 8,
            ),
            leading: widget.leading,
            title: widget.title,
            subtitle: widget.subtitle,
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (widget.trailing != null) widget.trailing!,
                const SizedBox(width: 4),
                Icon(
                  _expanded
                      ? Icons.expand_less_rounded
                      : Icons.expand_more_rounded,
                  semanticLabel: label,
                ),
              ],
            ),
            onTap: () => setState(() => _expanded = !_expanded),
          ),
        ),
        if (_expanded) ...widget.childrenBuilder(context),
      ],
    );
  }
}

/// One leaf of the folder tree: icon, raw name, translated detail, raw size.
class StorageNodeLine extends StatelessWidget {
  const StorageNodeLine({
    super.key,
    required this.icon,
    required this.name,
    required this.size,
    this.detail,
    this.indent = 0,
  });

  final IconData icon;
  final String name;
  final String size;
  final String? detail;
  final double indent;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsetsDirectional.only(
        start: 8 + indent,
        end: 8,
        top: 6,
        bottom: 6,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: storageRawStyle(context)),
                if (detail != null)
                  Text(
                    detail!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(size, style: theme.textTheme.bodyMedium),
        ],
      ),
    );
  }
}
