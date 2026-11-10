import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:neostation/l10n/game_box_locale.dart';
import 'package:neostation/services/game_box/game_box_art_fit.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_media_service.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/services/game_box/game_box_sources.dart';
import 'package:neostation/services/storage/storage_import_activity.dart';

/// What the media sheet changed on disk.
class GameBoxMediaChanges {
  const GameBoxMediaChanges({this.paths = const {}, this.frontChanged = false});
  final Set<String> paths;
  final bool frontChanged;
  bool get isEmpty => paths.isEmpty;
}

/// "Box media": the faces of a game's box, where each comes from, and the
/// two ways to improve them (docs/game-box-3d.md § 14) — complete the missing
/// faces from the best matching edition, or look at every source's scans of
/// one face and choose. Pictures can also be imported by hand (The Cover
/// Project, an own scan). Opened from the ScreenScraper button of the box
/// viewer.
class GameBoxMediaSheet extends StatefulWidget {
  const GameBoxMediaSheet({super.key, required this.context});

  final GameBoxSearchContext context;

  /// Shows the sheet; returns the files it changed.
  static Future<GameBoxMediaChanges> show(BuildContext context, GameBoxSearchContext search) async {
    final result = await showModalBottomSheet<GameBoxMediaChanges>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => FractionallySizedBox(heightFactor: 0.9, child: GameBoxMediaSheet(context: search)),
    );
    return result ?? const GameBoxMediaChanges();
  }

  @override
  State<GameBoxMediaSheet> createState() => GameBoxMediaSheetState();
}

@visibleForTesting
class GameBoxMediaSheetState extends State<GameBoxMediaSheet> {
  late GameBoxLocalMedia _media;
  final Map<GameBoxMediaKind, GameBoxImageCheck> _checks = {};
  GameBoxSearch? _search;
  GameBoxCompletionReport? _report;
  GameBoxCancel? _cancel;
  String? _busy;
  final Set<String> _changed = {};
  bool _frontChanged = false;
  String? _message;

  GameBoxSearchContext get _ctx => widget.context;

  @override
  void initState() {
    super.initState();
    _read();
  }

  /// Reads the faces again; the verdicts of the previous files are dropped
  /// at once (a replaced face never shows its predecessor's verdict) and a
  /// late verdict of an older read is ignored.
  int _reads = 0;
  void _read() {
    final read = ++_reads;
    _media = GameBoxMediaStore(_ctx.fileProvider).read(_ctx.game, _ctx.systemFolder);
    _checks.clear();
    for (final kind in GameBoxMediaKind.values) {
      final path = _media.pathOf(kind);
      if (path == null) continue;
      GameBoxMediaChecker.checkFile(path).then((c) {
        if (mounted && read == _reads) setState(() => _checks[kind] = c);
      });
    }
  }

  void _done() => Navigator.of(context).pop(GameBoxMediaChanges(paths: _changed, frontChanged: _frontChanged));

  String _t(String key) => GameBoxLocale.text(context, key);
  String _f(String key, Map<String, Object?> args) => GameBoxLocale.format(context, key, args);

  static String faceKey(GameBoxMediaKind kind) => switch (kind) {
        GameBoxMediaKind.front => GameBoxLocale.front,
        GameBoxMediaKind.back => GameBoxLocale.back,
        GameBoxMediaKind.spine => GameBoxLocale.titleSpine,
        GameBoxMediaKind.support => GameBoxLocale.faceSupport,
        GameBoxMediaKind.full => GameBoxLocale.faceSheet,
      };

  static String verdictKey(GameBoxImageVerdict verdict) => switch (verdict) {
        GameBoxImageVerdict.uniform => GameBoxLocale.refusedUniform,
        GameBoxImageVerdict.transparent => GameBoxLocale.refusedTransparent,
        GameBoxImageVerdict.tiny => GameBoxLocale.refusedTiny,
        GameBoxImageVerdict.unreadable || GameBoxImageVerdict.ok => GameBoxLocale.refusedUnreadable,
      };

  static String statusKey(GameBoxSourceStatus status) => switch (status) {
        GameBoxSourceStatus.ok => GameBoxLocale.srcOk,
        GameBoxSourceStatus.notConfigured => GameBoxLocale.srcNotConfigured,
        GameBoxSourceStatus.notSupported => GameBoxLocale.srcNotSupported,
        GameBoxSourceStatus.needsLogin => GameBoxLocale.srcNeedsLogin,
        GameBoxSourceStatus.systemNotMapped => GameBoxLocale.srcNotSupported,
        GameBoxSourceStatus.notFound => GameBoxLocale.srcNotFound,
        GameBoxSourceStatus.quota => GameBoxLocale.srcQuota,
        GameBoxSourceStatus.offline => GameBoxLocale.srcOffline,
        GameBoxSourceStatus.failed => GameBoxLocale.srcFailed,
        GameBoxSourceStatus.cancelled => GameBoxLocale.srcCancelled,
      };

  /// State of one face as the box draws it.
  String _faceStatus(GameBoxMediaKind kind) {
    final path = _media.pathOf(kind);
    final record = _media.recordOf(kind);
    if (path == null) {
      if (kind == GameBoxMediaKind.spine && _media.full != null) return _t(GameBoxLocale.frontFromSheet);
      return _t(GameBoxLocale.statusMissing);
    }
    final check = _checks[kind];
    if (check != null && !check.ok) return '${_t(GameBoxLocale.statusRefused)} — ${_t(verdictKey(check.verdict))}';
    if (record?.manual ?? false) return _t(GameBoxLocale.statusManual);
    if (kind == GameBoxMediaKind.front || kind == GameBoxMediaKind.back) {
      final nature = GameBoxArtClassifier.classify(
        profile: _ctx.profile,
        size: GameBoxImageSize.of(path),
        provenance: record?.type,
        opaqueShare: check?.opaqueShare,
        front: kind == GameBoxMediaKind.front,
      );
      if (nature == GameBoxArtNature.promo || nature == GameBoxArtNature.render3d) {
        return _t(GameBoxLocale.statusNotCover);
      }
    }
    return _t(GameBoxLocale.statusOk);
  }

  String _faceDetail(GameBoxMediaKind kind) {
    final path = _media.pathOf(kind);
    if (path == null) return '';
    final record = _media.recordOf(kind);
    final size = GameBoxImageSize.of(path);
    final parts = <String>[];
    if (record != null) {
      parts.add(record.provider == 'manual' ? _t(GameBoxLocale.statusManual) : _providerName(record.provider));
      final type = record.type.contains(':') ? record.type.split(':').last : record.type;
      if (record.provider != 'manual') parts.add(type);
      if (record.region != null) parts.add(GameBoxLocale.regionName(context, record.region!));
      if (record.edition != null) parts.add(record.edition!);
      if (record.note != null) parts.add(record.note!);
    }
    if (size != null) parts.add('${size.width.round()} × ${size.height.round()} px');
    return parts.join(' · ');
  }

  static String _providerName(String id) => switch (id) {
        'screenscraper' => 'ScreenScraper',
        'gametdb' => 'GameTDB',
        'mobygames' => 'MobyGames',
        'rpcs3' => 'RPCS3',
        'melonx' => 'MeloNX',
        final other => other,
      };

  // Actions -----------------------------------------------------------------

  Future<GameBoxSearch?> _ensureSearch() async {
    if (_search != null) return _search;
    final cancel = _cancel = GameBoxCancel();
    final search = await GameBoxMediaService.search(
      _ctx,
      cancel: cancel,
      onProvider: (p) {
        if (mounted) setState(() => _busy = _f(GameBoxLocale.mediaSearching, {'source': p.label}));
      },
    );
    if (!mounted || cancel.cancelled) return null;
    setState(() => _search = search);
    return search;
  }

  Future<void> complete() async {
    if (_busy != null) return;
    setState(() {
      _busy = _t(GameBoxLocale.fetching);
      _message = null;
      _report = null;
    });
    try {
      final search = await _ensureSearch();
      if (search == null || !mounted) return;
      final report = await GameBoxMediaService.complete(
        _ctx,
        search: search,
        cancel: _cancel,
        onFace: (kind) {
          if (mounted) {
            setState(() => _busy = _f(GameBoxLocale.mediaDownloading, {'face': _t(faceKey(kind))}));
          }
        },
        // A face of another language gives way to the print in the
        // scraping language (docs/game-box-3d.md § 19).
        upgradeLanguage: true,
      );
      if (!mounted) return;
      _changed.addAll(report.changedPaths);
      _frontChanged |= report.frontChanged;
      setState(() {
        _report = report;
        _read();
      });
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  void cancel() {
    _cancel?.cancel();
    setState(() => _busy = null);
  }

  Future<void> choose(GameBoxMediaKind kind) async {
    if (_busy != null) return;
    setState(() {
      _busy = _t(GameBoxLocale.fetching);
      _message = null;
    });
    GameBoxSearch? search;
    try {
      search = await _ensureSearch();
    } finally {
      if (mounted) setState(() => _busy = null);
    }
    if (search == null || !mounted) return;
    final rejected = _media.manifest?.rejected ?? const <String>{};
    final candidates = [
      ...search.of(kind),
      if (kind == GameBoxMediaKind.spine) ...search.of(GameBoxMediaKind.full),
    ].where((c) => !rejected.contains(c.identity)).toList();
    final picked = await showModalBottomSheet<GameBoxCandidate>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) => FractionallySizedBox(
        heightFactor: 0.75,
        child: _CandidateList(
          title: GameBoxLocale.text(ctx, faceKey(kind)),
          candidates: candidates,
          hint: search!.hint,
        ),
      ),
    );
    if (picked == null || !mounted) return;
    setState(() => _busy = _f(GameBoxLocale.mediaDownloading, {'face': _t(faceKey(kind))}));
    try {
      final adoption = await GameBoxMediaService.adopt(_ctx, picked, manualChoice: true);
      if (!mounted) return;
      if (adoption.ok) {
        _changed.add(adoption.path!);
        if (kind == GameBoxMediaKind.front) _frontChanged = true;
        setState(() {
          _message = _t(GameBoxLocale.faceChosen);
          _read();
        });
      } else {
        setState(() => _message = adoption.verdict == GameBoxImageVerdict.ok
            ? _t(statusKey(adoption.status))
            : _f(GameBoxLocale.importRefused, {'reason': _t(verdictKey(adoption.verdict))}));
      }
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  Future<void> importPicture(GameBoxMediaKind kind) async {
    if (_busy != null) return;
    final note = await showDialog<String>(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: Text(GameBoxLocale.text(ctx, GameBoxLocale.importSourceTitle)),
        children: [
          for (final key in const [GameBoxLocale.importTcpRetail, GameBoxLocale.importTcpCustom, GameBoxLocale.importOwn])
            SimpleDialogOption(
              onPressed: () => Navigator.of(ctx).pop(GameBoxLocale.text(ctx, key)),
              child: Text(GameBoxLocale.text(ctx, key)),
            ),
        ],
      ),
    );
    if (note == null || !mounted) return;
    setState(() => _busy = _f(GameBoxLocale.mediaDownloading, {'face': _t(faceKey(kind))}));
    try {
      final adoption = await _importPicked(kind, note);
      if (adoption == null || !mounted) return;
      if (adoption.ok) {
        _changed.add(adoption.path!);
        if (kind == GameBoxMediaKind.front) _frontChanged = true;
        setState(() {
          _message = _t(GameBoxLocale.faceChosen);
          _read();
        });
      } else {
        setState(() => _message = _f(GameBoxLocale.importRefused, {'reason': _t(verdictKey(adoption.verdict))}));
      }
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  /// The picked picture is read and checked while the import is counted, so
  /// that the storage clean-up never removes the picker's copy under it.
  Future<GameBoxAdoption?> _importPicked(GameBoxMediaKind kind, String note) => StorageImportActivity.run(() async {
        final picked = await FilePicker.pickFiles(type: FileType.image);
        final path = picked?.files.single.path;
        if (path == null) return null;
        return GameBoxMediaService.importFile(_ctx, kind, path, note: note);
      });

  Future<void> _openCoverProject() async {
    final uri = Uri.https('www.thecoverproject.net', '/view.php', {'searchstring': _ctx.title});
    try {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {}
  }

  Future<void> _editMobyKey() async {
    final current = await GameBoxPreferences.mobyGamesKey() ?? '';
    if (!mounted) return;
    final controller = TextEditingController(text: current);
    final saved = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(GameBoxLocale.text(ctx, GameBoxLocale.mobyKeyTitle)),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(GameBoxLocale.text(ctx, GameBoxLocale.mobyKeyDesc)),
          const SizedBox(height: 12),
          TextField(controller: controller, autocorrect: false, enableSuggestions: false),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: Text(GameBoxLocale.text(ctx, GameBoxLocale.close))),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(controller.text),
            child: Text(GameBoxLocale.text(ctx, GameBoxLocale.save)),
          ),
        ],
      ),
    );
    controller.dispose();
    if (saved == null) return;
    await GameBoxPreferences.setMobyGamesKey(saved);
    if (mounted) setState(() => _search = null);
  }

  // Build -------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final busy = _busy != null;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) return;
        if (busy) cancel();
        _done();
      },
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 8, 4),
          child: Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(_t(GameBoxLocale.mediaTitle), style: theme.textTheme.titleLarge),
                Text(_ctx.title, style: theme.textTheme.bodySmall, maxLines: 1, overflow: TextOverflow.ellipsis),
              ]),
            ),
            TextButton(onPressed: _done, child: Text(_t(GameBoxLocale.close))),
          ]),
        ),
        if (busy)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
            child: Row(children: [
              const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
              const SizedBox(width: 10),
              Expanded(child: Text(_busy!, style: theme.textTheme.bodySmall)),
              TextButton(
                key: const ValueKey('game_box_media_cancel'),
                onPressed: cancel,
                child: Text(_t(GameBoxLocale.mediaCancel)),
              ),
            ]),
          ),
        Expanded(
          child: ListView(padding: const EdgeInsets.fromLTRB(12, 0, 12, 16), children: [
            for (final kind in const [
              GameBoxMediaKind.front,
              GameBoxMediaKind.back,
              GameBoxMediaKind.spine,
              GameBoxMediaKind.support,
            ])
              Card(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Expanded(child: Text(_t(faceKey(kind)), style: theme.textTheme.titleSmall)),
                      Flexible(
                        child: Text(_faceStatus(kind),
                            textAlign: TextAlign.end, style: theme.textTheme.bodySmall),
                      ),
                    ]),
                    if (_faceDetail(kind).isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(_faceDetail(kind), style: theme.textTheme.bodySmall),
                      ),
                    Wrap(spacing: 4, children: [
                      TextButton.icon(
                        key: ValueKey('game_box_media_choose_${kind.name}'),
                        onPressed: busy ? null : () => choose(kind),
                        icon: const Icon(Icons.collections_outlined, size: 18),
                        label: Text(_t(GameBoxLocale.mediaReplace)),
                      ),
                      TextButton.icon(
                        onPressed: busy ? null : () => importPicture(kind),
                        icon: const Icon(Icons.file_open_outlined, size: 18),
                        label: Text(_t(GameBoxLocale.mediaImport)),
                      ),
                    ]),
                  ]),
                ),
              ),
            const SizedBox(height: 8),
            FilledButton.icon(
              key: const ValueKey('game_box_media_complete'),
              onPressed: busy ? null : complete,
              icon: const Icon(Icons.auto_fix_high_outlined),
              label: Text(_t(GameBoxLocale.mediaComplete)),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 4, 4, 8),
              child: Text(_t(GameBoxLocale.mediaCompleteDesc), style: theme.textTheme.bodySmall),
            ),
            if (_message != null)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Text(_message!, style: theme.textTheme.bodyMedium),
              ),
            if (_report != null) ..._reportLines(theme),
            if (_search != null) ..._statusLines(theme),
            const Divider(height: 24),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.travel_explore_outlined),
              title: Text(_t(GameBoxLocale.openCoverProject)),
              subtitle: Text(_t(GameBoxLocale.openCoverProjectDesc)),
              onTap: _openCoverProject,
            ),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.key_outlined),
              title: Text(_t(GameBoxLocale.mobyKeyTitle)),
              subtitle: Text(_t(GameBoxLocale.mobyKeyDesc)),
              onTap: _editMobyKey,
            ),
          ]),
        ),
      ]),
    );
  }

  List<Widget> _reportLines(ThemeData theme) {
    final r = _report!;
    String names(Iterable<GameBoxMediaKind> kinds) => kinds.map((k) => _t(faceKey(k))).join(', ');
    final lines = <String>[];
    final added = r.withOutcome(GameBoxFaceOutcome.added).toList();
    final improved = r.withOutcome(GameBoxFaceOutcome.improved).toList();
    final missing = [...r.withOutcome(GameBoxFaceOutcome.missing), ...r.withOutcome(GameBoxFaceOutcome.refused)];
    if (added.isNotEmpty) lines.add(_f(GameBoxLocale.reportAdded, {'faces': names(added)}));
    if (improved.isNotEmpty) lines.add(_f(GameBoxLocale.reportImproved, {'faces': names(improved)}));
    if (missing.isNotEmpty) lines.add(_f(GameBoxLocale.reportMissing, {'faces': names(missing)}));
    for (final (kind, provider, verdict) in r.refusals) {
      lines.add(_f(GameBoxLocale.faceRefused, {
        'face': '${_t(faceKey(kind))} (${provider.label})',
        'reason': _t(verdictKey(verdict)),
      }));
    }
    if (added.isEmpty && improved.isEmpty) lines.add(_t(GameBoxLocale.reportNothing));
    return [
      for (final line in lines)
        Padding(padding: const EdgeInsets.only(bottom: 2), child: Text(line, style: theme.textTheme.bodyMedium)),
    ];
  }

  List<Widget> _statusLines(ThemeData theme) {
    final statuses = _search!.statuses;
    final text = [
      for (final e in statuses.entries) '${e.key.label}: ${_t(statusKey(e.value))}',
    ].join(' · ');
    return [Padding(padding: const EdgeInsets.only(top: 6), child: Text(text, style: theme.textTheme.bodySmall))];
  }
}

/// Every source's scans of one face, best first, with what distinguishes
/// them: source, edition region, quality and size, and whether the edition
/// is the player's (docs/game-box-3d.md § 14).
class _CandidateList extends StatelessWidget {
  const _CandidateList({required this.title, required this.candidates, required this.hint});
  final String title;
  final List<GameBoxCandidate> candidates;
  final GameBoxEditionHint hint;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (candidates.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(GameBoxLocale.text(context, GameBoxLocale.candNone), textAlign: TextAlign.center),
        ),
      );
    }
    return ListView(padding: const EdgeInsets.fromLTRB(12, 0, 12, 16), children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(4, 0, 4, 8),
        child: Text(title, style: theme.textTheme.titleMedium),
      ),
      for (final c in candidates)
        Card(
          child: ListTile(
            title: Text([
              c.provider.label,
              GameBoxLocale.regionName(context, c.region.isEmpty ? 'wor' : c.region),
              if (c.edition != null) c.edition!,
            ].join(' · ')),
            subtitle: Text([
              c.type.split(':').last,
              if (c.width != null && c.height != null) '${c.width} × ${c.height} px',
              if (c.nature == GameBoxArtNature.wrap) GameBoxLocale.text(context, GameBoxLocale.faceSheet),
              hint.gameRegions.isEmpty
                  ? ''
                  : GameBoxCandidateRanking.regionAffinity(c.region, hint.gameRegions) >= 5
                      ? GameBoxLocale.text(context, GameBoxLocale.candSameEdition)
                      : GameBoxLocale.text(context, GameBoxLocale.candOtherEdition),
            ].where((s) => s.isNotEmpty).join(' · ')),
            onTap: () => Navigator.of(context).pop(c),
          ),
        ),
    ]);
  }
}
