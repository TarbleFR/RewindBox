import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../l10n/switch_online_locale.dart';
import '../services/logger_service.dart';
import '../services/melonx_internal_service.dart';
import '../services/melonx_profile_avatar.dart';
import '../services/melonx_profiles_service.dart';

/// The Switch user profiles of the embedded engine: create, rename, picture,
/// delete, and the profile games open. Changes apply at the next game launch.
class MelonxProfilesDialog extends StatefulWidget {
  const MelonxProfilesDialog({super.key});
  @override
  State<MelonxProfilesDialog> createState() => _MelonxProfilesDialogState();
}

class _MelonxProfilesDialogState extends State<MelonxProfilesDialog> {
  MelonxProfilesState? _state;
  Directory? _root;
  String? _error;
  bool _busy = false;

  String _text(String key, [Map<String, Object?> parameters = const {}]) => SwitchOnlineLocale.text(context, key, parameters);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final root = await MelonxInternalService.rootDirectory();
      final state = await MelonxProfilesService.load(root);
      if (mounted) {
        setState(() {
          _root = root;
          _state = state;
        });
      }
    } catch (error) {
      if (mounted) setState(() => _error = _failure(error));
    }
  }

  String _failure(Object error) {
    if (error is MelonxProfilesException) return _text(error.code, {'detail': error.detail});
    if (error.toString().contains('libraryBusy')) return _text('profileBusy');
    LoggerService.instance.w('Switch profile change failed: $error');
    return _text('profileFailed');
  }

  Future<Uint8List> _defaultPicture() => MelonxProfileAvatar.generated(MelonxProfileAvatar.presets[1]);

  /// Every write holds the native launch gate: no game starts meanwhile, and
  /// none is running.
  Future<void> _change(Future<MelonxProfilesState> Function(Directory root) action) async {
    final root = _root;
    if (root == null || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final next = await MelonxInternalService.editLibrary(() => action(root));
      // An engine already loaded lists the profiles it read earlier (the save
      // import asks it): it is told now; otherwise the next launch reads them.
      await MelonxInternalService.refreshProfiles();
      if (mounted) setState(() => _state = next);
    } catch (error) {
      if (mounted) setState(() => _error = _failure(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<String?> _askName(String title, [String initial = '']) {
    final controller = TextEditingController(text: initial);
    return showDialog<String>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLength: MelonxProfilesService.maxNameCharacters,
          maxLengthEnforcement: MaxLengthEnforcement.enforced,
          textInputAction: TextInputAction.done,
          decoration: InputDecoration(labelText: _text('profileNickname')),
          onSubmitted: (value) => Navigator.pop(dialog, value),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialog), child: Text(_text('cancel'))),
          FilledButton(onPressed: () => Navigator.pop(dialog, controller.text), child: Text(_text('save'))),
        ],
      ),
    );
  }

  /// A generated picture in one of the preset colours, or a chosen image.
  Future<Uint8List?> _askPicture() async {
    final choice = await showDialog<Object>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: Text(_text('profilePicture')),
        content: SizedBox(
          width: 320,
          child: Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final colour in MelonxProfileAvatar.presets)
                InkWell(
                  customBorder: const CircleBorder(),
                  onTap: () => Navigator.pop(dialog, colour),
                  child: CircleAvatar(radius: 26, backgroundColor: Color(colour), child: const Icon(Icons.person, color: Colors.white)),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialog), child: Text(_text('cancel'))),
          TextButton(onPressed: () => Navigator.pop(dialog, 'file'), child: Text(_text('profileChooseImage'))),
        ],
      ),
    );
    if (choice is int) return MelonxProfileAvatar.generated(choice);
    return choice == 'file' ? MelonxProfileAvatar.pickImage() : null;
  }

  Future<void> _create() async {
    final name = await _askName(_text('profileNew'));
    if (name == null || !mounted) return;
    try {
      MelonxProfilesService.validateName(name);
      final used = _state?.profiles.length ?? 0;
      final picture = await MelonxProfileAvatar.generated(MelonxProfileAvatar.presets[used % MelonxProfileAvatar.presets.length]);
      await _change((root) => MelonxProfilesService.create(root, name, image: picture, defaultImage: _defaultPicture));
    } catch (error) {
      if (mounted) setState(() => _error = _failure(error));
    }
  }

  Future<void> _rename(MelonxProfile profile) async {
    final name = await _askName(_text('profileRename'), profile.name);
    if (name == null || !mounted || name.trim() == profile.name) return;
    await _change((root) => MelonxProfilesService.rename(root, profile.id, name, defaultImage: _defaultPicture));
  }

  Future<void> _picture(MelonxProfile profile) async {
    try {
      final picture = await _askPicture();
      if (picture == null || !mounted) return;
      await _change((root) => MelonxProfilesService.setImage(root, profile.id, picture, defaultImage: _defaultPicture));
    } catch (error) {
      if (mounted) setState(() => _error = _failure(error));
    }
  }

  Future<void> _delete(MelonxProfile profile) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: Text(_text('profileDelete')),
        content: Text(_text('profileDeleteConfirm', {'name': profile.name})),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialog, false), child: Text(_text('cancel'))),
          FilledButton(onPressed: () => Navigator.pop(dialog, true), child: Text(_text('profileDelete'))),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    await _change((root) => MelonxProfilesService.delete(root, profile.id, defaultImage: _defaultPicture));
  }

  Widget _row(MelonxProfile profile, bool active) => ListTile(
    key: ValueKey('switch-profile-${profile.id}'),
    contentPadding: EdgeInsets.zero,
    leading: CircleAvatar(
      radius: 22,
      backgroundImage: profile.image == null ? null : MemoryImage(profile.image!),
      child: profile.image == null ? const Icon(Icons.person) : null,
    ),
    title: Text(profile.name, maxLines: 1, overflow: TextOverflow.ellipsis),
    subtitle: active ? Text(_text('profileActive')) : null,
    selected: active,
    onTap: _busy || active
        ? null
        : () => _change((root) => MelonxProfilesService.select(root, profile.id, defaultImage: _defaultPicture)),
    trailing: PopupMenuButton<String>(
      enabled: !_busy,
      onSelected: (action) => switch (action) {
        'use' => _change((root) => MelonxProfilesService.select(root, profile.id, defaultImage: _defaultPicture)),
        'rename' => _rename(profile),
        'picture' => _picture(profile),
        _ => _delete(profile),
      },
      itemBuilder: (_) => [
        if (!active) PopupMenuItem(value: 'use', child: Text(_text('profileUse'))),
        PopupMenuItem(value: 'rename', child: Text(_text('profileRename'))),
        PopupMenuItem(value: 'picture', child: Text(_text('profilePicture'))),
        if (!profile.isDefault) PopupMenuItem(value: 'delete', child: Text(_text('profileDelete'))),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final state = _state;
    return AlertDialog(
      title: Text(_text('profilesTitle')),
      content: SizedBox(
        width: 460,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(_text('profilesIntro')),
              const SizedBox(height: 8),
              if (state == null && _error == null) const Center(child: CircularProgressIndicator()),
              if (state != null)
                for (final profile in state.profiles) _row(profile, profile.id == state.activeId),
              if (_error != null) Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(_text('close'))),
        FilledButton(
          onPressed: state == null || _busy || state.profiles.length >= MelonxProfilesService.maxProfiles ? null : _create,
          child: Text(_text('profileNew')),
        ),
      ],
    );
  }
}
