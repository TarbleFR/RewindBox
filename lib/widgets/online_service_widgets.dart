import 'package:flutter/material.dart';

/// The account or console identity used by an online service.
class OnlineServiceIdentitySection extends StatelessWidget {
  const OnlineServiceIdentitySection({
    super.key,
    required this.actionLabel,
    required this.onAction,
    this.actionKey,
    this.actionIcon = Icons.login,
    this.identityTitle,
    this.identitySubtitle,
    this.identityIcon = Icons.person,
  });

  final String actionLabel;
  final VoidCallback? onAction;
  final Key? actionKey;
  final IconData actionIcon;
  final String? identityTitle;
  final String? identitySubtitle;
  final IconData identityIcon;

  @override
  Widget build(BuildContext context) {
    final title = identityTitle;
    if (title == null) {
      return Align(
        alignment: AlignmentDirectional.centerStart,
        child: FilledButton.icon(
          key: actionKey,
          onPressed: onAction,
          icon: Icon(actionIcon),
          label: Text(actionLabel),
        ),
      );
    }
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: CircleAvatar(child: Icon(identityIcon)),
      title: Text(title),
      subtitle: identitySubtitle == null ? null : Text(identitySubtitle!),
      trailing: TextButton(
        key: actionKey,
        onPressed: onAction,
        child: Text(actionLabel),
      ),
    );
  }
}

/// One switch and one status line; callers retain ownership of service checks.
class OnlineServicesSwitch extends StatelessWidget {
  const OnlineServicesSwitch({
    super.key,
    required this.title,
    required this.status,
    required this.value,
    required this.onChanged,
    this.problem = false,
    this.checking = false,
  });

  final String title;
  final String status;
  final bool value;
  final ValueChanged<bool>? onChanged;
  final bool problem;
  final bool checking;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      secondary: Icon(
        !value
            ? Icons.public_off
            : (problem ? Icons.error_outline : Icons.public),
        color: problem
            ? colors.error
            : (value && !checking ? colors.primary : null),
      ),
      title: Text(title),
      subtitle: Text(
        status,
        style: problem ? TextStyle(color: colors.error) : null,
      ),
      value: value,
      onChanged: onChanged,
    );
  }
}
