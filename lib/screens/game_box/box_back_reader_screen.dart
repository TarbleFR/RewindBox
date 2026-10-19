import 'dart:io';

import 'package:flutter/material.dart';
import 'package:neo_box_reader/neo_box_reader.dart';

import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/game_box_locale.dart';
import 'package:neostation/services/game_box/box_text_layout.dart';
import 'package:neostation/services/game_box/box_text_service.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/services/game_service.dart' show GamepadNavigationManager;
import 'package:neostation/utils/gamepad_nav.dart';
import 'package:neostation/widgets/game_box/game_box_language_picker.dart';

/// Reading mode of a box back (docs/game-box-3d.md § 7).
///
/// The text comes only from the scan: recognised on the device, grouped into
/// its printed sections, then translated on the device into the reading
/// language when it is in another language. The original stays one tap away,
/// every automatic step is labelled as such, and the game's metadata summary
/// is shown apart, never in place of the text of the box.
class BoxBackReaderScreen extends StatefulWidget {
  const BoxBackReaderScreen({
    super.key,
    required this.title,
    required this.scanPath,
    required this.readingLanguage,
    this.scanRegion,
    this.publishedLanguage,
    this.summaryFor,
    this.onReadingLanguageChanged,
  });

  final String title;
  final String? scanPath;

  /// NeoStation code of the reading language.
  final String readingLanguage;

  /// ScreenScraper region of the scan (recognition hints, edition label).
  final String? scanRegion;

  /// Language the scan was chosen for (a localized edition), if any.
  final String? publishedLanguage;

  /// Metadata summary of the game in a language, or empty.
  final String Function(String language)? summaryFor;

  final ValueChanged<String>? onReadingLanguageChanged;

  @override
  State<BoxBackReaderScreen> createState() => _BoxBackReaderScreenState();
}

enum _Stage { recognizing, translating, ready, failed }

class _BoxBackReaderScreenState extends State<BoxBackReaderScreen> {
  late String _language = widget.readingLanguage;
  late final GamepadNavigation _gamepadNav;
  _Stage _stage = _Stage.recognizing;
  BoxTranscript? _transcript;
  BoxTranslation? _translation;
  String? _ocrError;
  String? _translationError;
  bool _showOriginal = false;
  double _scale = 1.0;
  int _request = 0;

  @override
  void initState() {
    super.initState();
    GameBoxPreferences.readerTextScale().then((v) {
      if (mounted) setState(() => _scale = v);
    });
    _gamepadNav = GamepadNavigation(
      onBack: () => Navigator.of(context).maybePop(),
      onLeftBumper: () => _setScale(_scale - 0.1),
      onRightBumper: () => _setScale(_scale + 0.1),
      onXButton: () {
        if (_canToggle) setState(() => _showOriginal = !_showOriginal);
      },
      onFavorite: _openScan,
      onSettings: _chooseLanguage,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        'game_box_reader',
        modal: true,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
    });
    _start();
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer('game_box_reader');
    _gamepadNav.dispose();
    super.dispose();
  }

  bool get _needsTranslation {
    final t = _transcript;
    if (t == null || t.document.isEmpty) return false;
    return t.language != _language;
  }

  bool get _canToggle => _needsTranslation && _translation != null;

  Future<void> _start() async {
    final path = widget.scanPath;
    if (path == null || !File(path).existsSync()) {
      setState(() => _stage = _Stage.failed);
      return;
    }
    final request = ++_request;
    setState(() {
      _stage = _Stage.recognizing;
      _ocrError = null;
    });
    try {
      final transcript = await BoxTextService.transcript(path, scanRegion: widget.scanRegion);
      if (!mounted || request != _request) return;
      setState(() => _transcript = transcript);
      await _translate();
    } on BoxReaderException catch (e) {
      if (!mounted || request != _request) return;
      setState(() {
        _ocrError = e.code;
        _stage = _Stage.failed;
      });
    } catch (e) {
      if (!mounted || request != _request) return;
      setState(() {
        _ocrError = BoxReaderException.ocrFailed;
        _stage = _Stage.failed;
      });
    }
  }

  Future<void> _translate() async {
    final transcript = _transcript;
    if (transcript == null) return;
    final request = ++_request;
    setState(() {
      _translation = null;
      _translationError = null;
      _showOriginal = false;
    });
    if (!_needsTranslation) {
      setState(() => _stage = _Stage.ready);
      return;
    }
    setState(() => _stage = _Stage.translating);
    try {
      final translation = await BoxTextService.translate(transcript, _language);
      if (!mounted || request != _request) return;
      setState(() {
        _translation = translation;
        _stage = _Stage.ready;
      });
    } on BoxReaderException catch (e) {
      if (!mounted || request != _request) return;
      setState(() {
        _translationError = e.code;
        _stage = _Stage.ready;
      });
    } catch (_) {
      if (!mounted || request != _request) return;
      setState(() {
        _translationError = BoxReaderException.failed;
        _stage = _Stage.ready;
      });
    }
  }

  void _setScale(double v) {
    final c = v.clamp(0.8, 2.4).toDouble();
    setState(() => _scale = c);
    GameBoxPreferences.setReaderTextScale(c);
  }

  Future<void> _chooseLanguage() async {
    final chosen = await showGameBoxLanguagePicker(context, current: _language);
    if (chosen == null || chosen == gameBoxFollowApp || chosen == _language || !mounted) return;
    setState(() => _language = chosen);
    widget.onReadingLanguageChanged?.call(chosen);
    await _translate();
  }

  void _openScan() {
    final path = widget.scanPath;
    if (path == null) return;
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => _ScanViewer(path: path, title: GameBoxLocale.text(context, GameBoxLocale.readerTitle)),
    ));
  }

  String _lang(String? code) => code == null
      ? GameBoxLocale.text(context, GameBoxLocale.unknownLanguage)
      : GameBoxLocale.languageName(context, code);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(GameBoxLocale.text(context, GameBoxLocale.readerTitle)),
        actions: [
          IconButton(
            tooltip: GameBoxLocale.text(context, GameBoxLocale.viewScan),
            onPressed: widget.scanPath == null ? null : _openScan,
            icon: const Icon(Icons.image_search_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          children: [
            Text(widget.title, style: theme.textTheme.titleMedium),
            const SizedBox(height: 12),
            _controls(theme),
            const SizedBox(height: 12),
            ..._notices(theme),
            const SizedBox(height: 8),
            ..._content(theme),
            ..._summary(theme),
          ],
        ),
      ),
    );
  }

  Widget _controls(ThemeData theme) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Tooltip(
          message: GameBoxLocale.text(context, GameBoxLocale.readingLanguage),
          child: Semantics(
            label: GameBoxLocale.text(context, GameBoxLocale.readingLanguage),
            button: true,
            child: ActionChip(
              avatar: const Icon(Icons.translate, size: 18),
              label: Text(AppLocale.supportedLanguages[_language] ?? _language),
              onPressed: _chooseLanguage,
            ),
          ),
        ),
        if (_needsTranslation)
          SegmentedButton<bool>(
            segments: [
              ButtonSegment(value: false, label: Text(GameBoxLocale.text(context, GameBoxLocale.translation))),
              ButtonSegment(value: true, label: Text(GameBoxLocale.text(context, GameBoxLocale.original))),
            ],
            selected: {_showOriginal || _translation == null},
            onSelectionChanged: _translation == null ? null : (s) => setState(() => _showOriginal = s.first),
          ),
        Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(
            tooltip: GameBoxLocale.text(context, GameBoxLocale.textSize),
            onPressed: _scale <= 0.8 ? null : () => _setScale(_scale - 0.1),
            icon: const Icon(Icons.text_decrease),
          ),
          Text('${(_scale * 100).round()} %', style: theme.textTheme.labelMedium),
          IconButton(
            tooltip: GameBoxLocale.text(context, GameBoxLocale.textSize),
            onPressed: _scale >= 2.4 ? null : () => _setScale(_scale + 0.1),
            icon: const Icon(Icons.text_increase),
          ),
        ]),
      ],
    );
  }

  Widget _notice(ThemeData theme, IconData icon, String text, {bool warning = false}) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, size: 18, color: warning ? theme.colorScheme.error : theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: 8),
          Expanded(child: Text(text, style: theme.textTheme.bodySmall)),
        ]),
      );

  List<Widget> _notices(ThemeData theme) {
    final out = <Widget>[];
    final region = widget.scanRegion;
    if (widget.publishedLanguage != null) {
      out.add(_notice(theme, Icons.verified_outlined,
          GameBoxLocale.format(context, GameBoxLocale.scanInLanguage, {'language': _lang(widget.publishedLanguage)})));
    } else if (region != null && region.isNotEmpty) {
      out.add(_notice(theme, Icons.public,
          GameBoxLocale.format(context, GameBoxLocale.edition, {'region': GameBoxLocale.regionName(context, region)})));
    }
    final t = _transcript;
    if (t != null && !t.document.isEmpty) {
      out.add(_notice(theme, Icons.document_scanner_outlined, GameBoxLocale.text(context, GameBoxLocale.ocrNotice)));
      if (t.language != null || t.rawLanguage != null) {
        out.add(_notice(theme, Icons.language,
            GameBoxLocale.format(context, GameBoxLocale.detectedLanguage, {'language': t.language == null ? (t.rawLanguage ?? '') : _lang(t.language)})));
      }
      if (t.document.hasLowConfidence) {
        out.add(_notice(theme, Icons.warning_amber_rounded, GameBoxLocale.text(context, GameBoxLocale.lowConfidence), warning: true));
      }
      if (t.document.illegibleLines > 0) {
        out.add(_notice(theme, Icons.blur_on, GameBoxLocale.text(context, GameBoxLocale.illegible), warning: true));
      }
      if (!_needsTranslation) {
        out.add(_notice(theme, Icons.check_circle_outline,
            GameBoxLocale.format(context, GameBoxLocale.translationNotNeeded, {'language': _lang(_language)})));
      } else if (_translation != null && !_showOriginal) {
        out.add(_notice(theme, Icons.auto_awesome_outlined,
            GameBoxLocale.format(context, GameBoxLocale.translationNotice, {'language': _lang(NeoBoxReader.appCodeOf(_translation!.source) ?? t.language)})));
      }
      if (_translationError != null) {
        out.add(_notice(theme, Icons.error_outline, _translationMessage(_translationError!), warning: true));
      }
      if (t.fromCache || (_translation?.fromCache ?? false) || _stage == _Stage.ready) {
        out.add(_notice(theme, Icons.offline_pin_outlined, GameBoxLocale.text(context, GameBoxLocale.cached)));
      }
    }
    return out;
  }

  String _translationMessage(String code) {
    final source = _lang(_transcript?.language);
    final target = _lang(_language);
    switch (code) {
      case BoxReaderException.unsupported:
        return GameBoxLocale.format(context, GameBoxLocale.translationUnsupported, {'source': source, 'target': target});
      case BoxReaderException.notInstalled:
        return GameBoxLocale.format(context, GameBoxLocale.translationNotInstalled, {'language': target});
      case BoxReaderException.unavailable:
        return GameBoxLocale.text(context, GameBoxLocale.ocrUnavailable);
      default:
        return GameBoxLocale.text(context, GameBoxLocale.translationFailed);
    }
  }

  List<Widget> _content(ThemeData theme) {
    if (widget.scanPath == null) {
      return [_message(theme, GameBoxLocale.text(context, GameBoxLocale.noBack))];
    }
    switch (_stage) {
      case _Stage.recognizing:
        return [_progress(theme, GameBoxLocale.text(context, GameBoxLocale.recognizing))];
      case _Stage.translating:
        return [
          _progress(theme, GameBoxLocale.format(context, GameBoxLocale.translating, {'language': _lang(_language)})),
          ..._blocks(theme, original: true),
        ];
      case _Stage.failed:
        final unavailable = _ocrError == BoxReaderException.unavailable;
        return [
          _message(theme, GameBoxLocale.text(context, unavailable ? GameBoxLocale.ocrUnavailable : GameBoxLocale.ocrFailed)),
          if (!unavailable)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: _start,
                icon: const Icon(Icons.refresh),
                label: Text(GameBoxLocale.text(context, GameBoxLocale.retry)),
              ),
            ),
        ];
      case _Stage.ready:
        final t = _transcript;
        if (t == null || t.document.isEmpty) {
          return [_message(theme, GameBoxLocale.text(context, GameBoxLocale.noText))];
        }
        return [
          ..._blocks(theme, original: _showOriginal || _translation == null),
          if (_translationError != null && _needsTranslation)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: _translate,
                icon: const Icon(Icons.refresh),
                label: Text(GameBoxLocale.text(context, GameBoxLocale.retry)),
              ),
            ),
        ];
    }
  }

  Widget _progress(ThemeData theme, String text) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Row(children: [
          const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.4)),
          const SizedBox(width: 12),
          Expanded(child: Text(text, style: theme.textTheme.bodyMedium)),
        ]),
      );

  Widget _message(ThemeData theme, String text) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Text(text, style: theme.textTheme.bodyLarge),
      );

  List<Widget> _blocks(ThemeData theme, {required bool original}) {
    final t = _transcript;
    if (t == null) return const [];
    final translated = original ? null : _translation?.units;
    var index = 0;
    final base = 15.0 * _scale;
    final out = <Widget>[];
    for (final block in t.document.blocks) {
      final units = <String>[];
      for (final u in block.units) {
        units.add(translated != null && index < translated.length ? translated[index] : u);
        index++;
      }
      final style = switch (block.kind) {
        BoxTextBlockKind.heading => theme.textTheme.titleMedium?.copyWith(fontSize: base * 1.25, fontWeight: FontWeight.w700),
        BoxTextBlockKind.legal => theme.textTheme.bodySmall?.copyWith(fontSize: base * 0.8, color: theme.colorScheme.onSurfaceVariant),
        _ => theme.textTheme.bodyLarge?.copyWith(fontSize: base, height: 1.45),
      };
      Widget body;
      if (block.kind == BoxTextBlockKind.list) {
        body = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final u in units)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('•  ', style: style),
                  Expanded(child: SelectableText(u, style: style)),
                ]),
              ),
          ],
        );
      } else {
        body = SelectableText(units.join('\n'), style: style);
      }
      out.add(Container(
        margin: const EdgeInsets.only(bottom: 14),
        padding: block.lowConfidence ? const EdgeInsets.only(left: 10) : EdgeInsets.zero,
        decoration: block.lowConfidence
            ? BoxDecoration(border: Border(left: BorderSide(color: theme.colorScheme.error.withValues(alpha: 0.5), width: 3)))
            : null,
        child: body,
      ));
    }
    return out;
  }

  List<Widget> _summary(ThemeData theme) {
    final summary = widget.summaryFor?.call(_language).trim() ?? '';
    if (summary.isEmpty) return const [];
    return [
      const Divider(height: 32),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: Text(GameBoxLocale.text(context, GameBoxLocale.metadataSummary), style: theme.textTheme.titleSmall),
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: SelectableText(summary, style: theme.textTheme.bodyMedium?.copyWith(fontSize: 14 * _scale)),
          ),
        ],
      ),
    ];
  }
}

/// The scan itself, zoomable, at up to 4096 px.
class _ScanViewer extends StatelessWidget {
  const _ScanViewer({required this.path, required this.title});
  final String path;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(title: Text(title), backgroundColor: Colors.black, foregroundColor: Colors.white),
      body: InteractiveViewer(
        maxScale: 8,
        child: Center(
          child: Image(
            image: ResizeImage(FileImage(File(path)), width: 4096, allowUpscaling: false),
            filterQuality: FilterQuality.high,
            gaplessPlayback: true,
          ),
        ),
      ),
    );
  }
}
