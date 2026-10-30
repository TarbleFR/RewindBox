import 'package:flutter/material.dart';
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
  bool get _fr => Localizations.localeOf(context).languageCode == 'fr';
  String _text(String en, String fr) => _fr ? fr : en;

  @override
  void initState() { super.initState(); _load(); }
  Future<void> _load() async {
    try {
      final info = await MelonxInternalService.content('inspectUnreal', filePath: widget.gamePath);
      final service = MelonxUnrealProfiles(await MelonxInternalService.rootDirectory());
      final current = await service.current(info);
      if (mounted) setState(() { _inspection = info; _profiles = service; _selected = current?['experiment'] as String? ?? 'off'; });
    } catch (e) { if (mounted) setState(() => _error = e.toString()); }
  }

  Future<void> _apply() async {
    setState(() { _busy = true; _error = null; });
    try {
      await MelonxInternalService.editLibrary(() async {
        final fresh = await MelonxInternalService.content('inspectUnreal', filePath: widget.gamePath);
        await _profiles!.apply(fresh, _selected);
      });
      if (mounted) Navigator.pop(context);
    } catch (e) { if (mounted) setState(() { _busy = false; _error = e.toString(); }); }
  }

  @override
  Widget build(BuildContext context) {
    final info = _inspection;
    final choice = MelonxUnrealProfiles.experiments[_selected];
    return AlertDialog(
      title: Text(_text('Unreal Engine experiments', 'Expériences Unreal Engine')),
      content: SizedBox(width: 460, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text(_text('One setting at a time. These Switch CVars and their loading path are unverified; an installed profile may have no effect. Original game files, saves and other mods remain intact.',
          'Un réglage à la fois. Ces CVars Switch et leur chargement ne sont pas validés : le profil installé peut rester sans effet. Les fichiers du jeu, sauvegardes et autres mods sont conservés.')),
        if (info != null) ...[
          Text('${_text('Inspected RomFS project', 'Projet RomFS inspecté')} : ${info['project']}'),
          DropdownButtonFormField<String>(
            initialValue: _selected,
            isExpanded: true,
            items: [
              DropdownMenuItem(value: 'off', child: Text(_text('No experimental profile', 'Aucun profil expérimental'))),
              for (final entry in MelonxUnrealProfiles.experiments.entries)
                DropdownMenuItem(value: entry.key, child: Text('${entry.value.$1}=${entry.value.$2}', overflow: TextOverflow.ellipsis)),
            ],
            onChanged: _busy ? null : (value) => setState(() { _selected = value!; _accepted = false; }),
          ),
          if (choice?.$3 == true) Text(_text('This test changes visual quality.', 'Cet essai modifie la qualité graphique.')),
          if (_selected != 'off') CheckboxListTile(
            title: Text(_text('Install this unverified experiment for the next launch', 'Installer cet essai non validé pour le prochain lancement')),
            value: _accepted,
            onChanged: _busy ? null : (value) => setState(() => _accepted = value ?? false),
          ),
          Text(_text('Choosing no profile removes only RewindBox’s verified experiment. Edited files are preserved. Previous experiments are backed up.',
            'Le choix « Aucun profil » retire uniquement l’essai RewindBox vérifié. Les fichiers modifiés sont préservés. Les essais précédents sont sauvegardés.')),
        ] else if (_error == null) const CircularProgressIndicator(),
        if (_error != null) Text(_error!),
      ]))),
      actions: [
        TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: Text(_text('Close', 'Fermer'))),
        FilledButton(onPressed: info == null || _busy || (_selected != 'off' && !_accepted) ? null : _apply,
          child: Text(_busy ? _text('Applying…', 'Application…') : _text('Apply', 'Appliquer'))),
      ],
    );
  }
}
