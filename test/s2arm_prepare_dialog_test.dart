import 'dart:ui' show Locale;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/switch2_library_locale.dart';
import 'package:neostation/services/s2arm_internal_service.dart';
import 'package:neostation/widgets/s2arm_internal_playlist_actions.dart';

/// The Switch 2 launch preparation dialog: the step and its part, the phase with its own counts, one weighted bar and the
/// elapsed time, so that a long code stage (Mario Kart World, IPA 728: "code · 0%" for minutes) visibly moves.
void main() {
  const fr = Locale('fr');
  const en = Locale('en');

  S2ArmImportProgress code({String part = 'main', String? phase, int attempt = 1, int? done, int? total, double overall = 0.24}) =>
      S2ArmImportProgress(
        name: 'code · $part',
        index: 1,
        count: 6,
        done: 250,
        total: 1000,
        step: 'code',
        part: part,
        phase: phase,
        attempt: attempt,
        unitsDone: done,
        unitsTotal: total,
        overall: overall,
      );

  test('the code stage reads as the step, its module, the pass and the counts', () {
    expect(s2armPreparationLines(fr, code(phase: 'analyze', attempt: 2, done: 1234, total: 5678)), [
      'Compilation du code du jeu · module principal · passe 2',
      'Analyse des fonctions · 1234 / 5678 fonctions',
    ]);
    expect(s2armPreparationLines(fr, code(phase: 'generate', done: 40, total: 90)),
        ['Compilation du code du jeu · module principal', 'Génération du code adapté · 40 / 90']);
    expect(s2armPreparationLines(fr, code(phase: 'scan', done: 34000000, total: 120000000)),
        ['Compilation du code du jeu · module principal', 'Recherche du code à adapter · 34 / 120 Mo']);
    expect(s2armPreparationLines(fr, code(part: 'subsdk0', phase: 'outputs')),
        ['Compilation du code du jeu · module subsdk0', 'Écriture du module']);
    expect(s2armPreparationLines(fr, code(part: 'nro', phase: 'walk', done: 321, total: 0)),
        ['Compilation du code du jeu · recherche des modules annexes', '321 fichiers parcourus']);
    expect(s2armPreparationLines(fr, code(part: 'zbic', phase: 'zbic', done: 5000000, total: 60000000)),
        ['Compilation du code du jeu · décompression des modules', '5 / 60 Mo']);
    expect(s2armPreparationLines(en, code(phase: 'start')), ['Compiling the game code · main module']);
  });

  test('the other steps, a reused preparation and an older event without step', () {
    const pack = S2ArmImportProgress(name: 'pack', index: 5, count: 6, done: 500, total: 1000, step: 'pack', overall: 0.97);
    expect(s2armPreparationLines(fr, pack), ['Ressources du jeu']);
    const reused = S2ArmImportProgress(name: 'done · reused', index: 6, count: 6, done: 1000, total: 1000, step: 'done', part: 'reused');
    expect(s2armPreparationLines(fr, reused), ['Déjà préparé : réutilisé']);
    const older = S2ArmImportProgress(name: 'code · main', index: 1, count: 6, done: 500, total: 1000);
    expect(s2armPreparationLines(fr, older), ['code · main · 50%']);
    expect(s2armPreparationLines(fr, null), isEmpty);
  });

  test('the elapsed time in each locale', () {
    expect(s2armElapsedText(fr, const Duration(seconds: 42)), '42 s');
    expect(s2armElapsedText(fr, const Duration(seconds: 65)), '1 min 05 s');
    expect(s2armElapsedText(const Locale('ja'), const Duration(seconds: 65)), '1分05秒');
    expect(s2armElapsedText(en, const Duration(minutes: 12, seconds: 3)), '12 min 03 s');
  });

  test('every preparation label exists in the 12 locales with the English placeholders', () {
    final english = Switch2LibraryLocale.values['en']!;
    final keys = english.keys.where((key) => key.startsWith('prep')).toList();
    expect(keys.length, greaterThanOrEqualTo(26));
    final placeholder = RegExp(r'\{(\w+)\}');
    for (final entry in Switch2LibraryLocale.values.entries) {
      for (final key in keys) {
        final value = entry.value[key];
        expect(value, isNotNull, reason: '${entry.key} $key');
        List<String> names(String text) => placeholder.allMatches(text).map((m) => m.group(1)!).toList()..sort();
        expect(names(value!), names(english[key]!), reason: '${entry.key} $key');
      }
    }
  });

  testWidgets('the dialog shows the step, the counts, the weighted bar and the elapsed time', (tester) async {
    var now = DateTime(2026, 11, 12, 9);
    S2ArmPrepareDialog.clock = () => now;
    addTearDown(() => S2ArmPrepareDialog.clock = DateTime.now);
    final progress = ValueNotifier<S2ArmImportProgress?>(null);
    addTearDown(progress.dispose);
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: S2ArmPrepareDialog(progress: progress, title: 'Mario Kart World'))));
    expect(find.text('Preparing Mario Kart World…'), findsOneWidget);
    expect(find.text('Elapsed: 0 s'), findsOneWidget);

    progress.value = code(phase: 'analyze', done: 10, total: 40);
    now = now.add(const Duration(seconds: 65));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Compiling the game code · main module'), findsOneWidget);
    expect(find.text('Analysing the functions · 10 / 40 functions'), findsOneWidget);
    expect(find.text('24 % · Elapsed: 1 min 05 s'), findsOneWidget);
    expect(tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator)).value, closeTo(0.24, 1e-9));

    // Time moves on its own while a long pass reports nothing new.
    now = now.add(const Duration(seconds: 30));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('24 % · Elapsed: 1 min 35 s'), findsOneWidget);

    await tester.pumpWidget(const SizedBox());   // disposes the dialog and its ticker
  });
}
