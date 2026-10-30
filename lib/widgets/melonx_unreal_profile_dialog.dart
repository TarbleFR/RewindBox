import 'package:flutter/material.dart';
import '../l10n/melonx_unreal_profile_locale.dart';
import '../services/melonx_internal_service.dart';
import '../services/melonx_unreal_profiles.dart';

class MelonxUnrealProfileDialog extends StatefulWidget {
  const MelonxUnrealProfileDialog({super.key, required this.gamePath});
  final String gamePath;
  @override
  State<MelonxUnrealProfileDialog> createState() => _MelonxUnrealProfileDialogState();
}

class _MelonxUnrealProfileDialogState extends State<MelonxUnrealProfileDialog> {
  Map<String, dynamic>? _inspection;
  MelonxUnrealProfiles? _profiles;
  String _selected = 'off';
  bool _accepted = false, _busy = false;
  String? _error;
  String? _errorKey;
  String _text(String key, [Map<String, Object?> parameters = const {}]) =>
      MelonxUnrealProfileLocale.text(context, key, parameters);

  @override
  void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    try {
      final info = await MelonxInternalService.content('inspectUnreal', filePath: widget.gamePath);
      final service = MelonxUnrealProfiles(await MelonxInternalService.rootDirectory());
      final current = await service.current(info);
      if (mounted) setState(() { _inspection = info; _profiles = service; _selected = current?['experiment'] as String? ?? 'off'; });
    } catch (e) { if (mounted) setState(() { _error = e.toString(); _errorKey = 'inspectFailed'; }); }
  }

  Future<void> _apply() async {
    setState(() { _busy = true; _error = null; _errorKey = null; });
    try {
      await MelonxInternalService.editLibrary(() async {
        final fresh = await MelonxInternalService.content('inspectUnreal', filePath: widget.gamePath);
        await _profiles!.apply(fresh, _selected);
      });
      if (mounted) Navigator.pop(context);
    } catch (e) { if (mounted) setState(() { _busy = false; _error = e.toString(); _errorKey = 'applyFailed'; }); }
  }

  @override
  Widget build(BuildContext context) {
    final info = _inspection;
    final choice = MelonxUnrealProfiles.experiments[_selected];
    return AlertDialog(
      title: Text(_text('title')),
      content: SizedBox(width: 460, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text(_text('intro')),
        if (info != null) ...[
          Text(_text('project', {'project': info['project']})),
          DropdownButtonFormField<String>(
            initialValue: _selected,
            isExpanded: true,
            items: [
              DropdownMenuItem(value: 'off', child: Text(_text('off'))),
              for (final entry in MelonxUnrealProfiles.experiments.entries)
                DropdownMenuItem(value: entry.key, child: Text('${entry.value.$1}=${entry.value.$2}', overflow: TextOverflow.ellipsis)),
            ],
            onChanged: _busy ? null : (value) => setState(() { _selected = value!; _accepted = false; }),
          ),
          if (choice?.$3 == true) Text(_text('quality')),
          if (_selected != 'off') CheckboxListTile(
            title: Text(_text('consent')),
            value: _accepted,
            onChanged: _busy ? null : (value) => setState(() => _accepted = value ?? false),
          ),
          Text(_text('removal')),
        ] else if (_error == null) const CircularProgressIndicator(),
        if (_error != null) ...[
          Text(_text(_errorKey!)),
          ExpansionTile(
            title: Text(_text('technicalDetails')),
            children: [SelectableText(_error!)],
          ),
        ],
      ]))),
      actions: [
        TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: Text(_text('close'))),
        FilledButton(onPressed: info == null || _busy || (_selected != 'off' && !_accepted) ? null : _apply,
          child: Text(_text(_busy ? 'applying' : 'apply'))),
      ],
    );
  }
}
