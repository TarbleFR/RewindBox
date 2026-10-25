import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/armsx2_texture_locale.dart';
import 'package:neostation/services/armsx2_texture_service.dart';
import 'package:neostation/widgets/armsx2_texture_panel.dart';

class _AnyLocaleDelegate<T> extends LocalizationsDelegate<T> {
  const _AnyLocaleDelegate(this._load);

  final Future<T> Function(Locale locale) _load;

  @override
  bool isSupported(Locale locale) => true;

  @override
  Future<T> load(Locale locale) => _load(locale);

  @override
  bool shouldReload(covariant LocalizationsDelegate<T> old) => false;
}

const _materialTexts = _AnyLocaleDelegate<MaterialLocalizations>(
  DefaultMaterialLocalizations.load,
);
const _cupertinoTexts = _AnyLocaleDelegate<CupertinoLocalizations>(
  DefaultCupertinoLocalizations.load,
);

const _game = '/var/mobile/Documents/ARMSX2/Games/God of War II.chd';

/// The native store as the panel sees it: every call recorded, answers set
/// by each test. The store itself is exercised by test/armsx2_texture_packs_test.py
/// (files) and the macOS/UIKit suites (Foundation, in-game page).
class _FakeClient implements Armsx2TextureClient {
  _FakeClient(this.state);

  Map<String, dynamic> state;
  final calls = <List<Object?>>[];
  Map<String, dynamic> pickAnswer = const {'success': false, 'cancelled': true};
  Completer<Map<String, dynamic>>? installAnswer;
  Map<String, dynamic> installResult = const {'success': true};
  final progressEvents = StreamController<Map<String, dynamic>>.broadcast();

  @override
  Future<Map<String, dynamic>> status(String gamePath) async {
    calls.add(['status', gamePath]);
    return state;
  }

  @override
  Future<Map<String, dynamic>> pick(
    String gamePath, {
    required bool folder,
  }) async {
    calls.add(['pick', gamePath, folder]);
    return pickAnswer;
  }

  @override
  Future<Map<String, dynamic>> install(
    String token, {
    required bool allowMismatch,
  }) {
    calls.add(['install', token, allowMismatch]);
    return installAnswer?.future ?? Future.value(installResult);
  }

  @override
  Future<void> cancel(String token) async => calls.add(['cancel', token]);

  @override
  Future<void> discard(String token) async => calls.add(['discard', token]);

  @override
  Future<Map<String, dynamic>> setEnabled(String gamePath, bool enabled) async {
    calls.add(['setEnabled', gamePath, enabled]);
    return {
      'success': true,
      'message': enabled ? 'enabledNext' : 'disabledNext',
    };
  }

  @override
  Future<Map<String, dynamic>> remove(String gamePath) async {
    calls.add(['remove', gamePath]);
    return {'success': true};
  }

  @override
  Stream<Map<String, dynamic>> get progress => progressEvents.stream;

  List<String> get names => [for (final call in calls) call.first as String];
}

Map<String, dynamic> _status({
  bool installed = true,
  Object? enabled = true,
  Object? ini = true,
  String serial = 'SLUS-21137',
  String source = 'session',
}) => {
  'success': true,
  'sessionActive': false,
  'formats': {'bcTextures': false, 'astcTextures': true},
  'game': {
    'serial': serial,
    'source': source,
    'region': serial.isEmpty ? '' : 'NTSC-U',
    'version': '1.01',
    'crc': 'ABCD1234',
  },
  'pack': {
    'serial': serial,
    'installed': installed,
    'external': false,
    if (installed) ...{
      'files': 4,
      'bytes': 3 * 1024 * 1024,
      'named': 3,
      'mips': 1,
      'formats': {'png': 2, 'ddsBc1': 1, 'astc': 1},
      'source': 'GoW2-HD.zip',
      'packSerial': serial,
      'folder': 'ARMSX2/textures/$serial/replacements',
    },
    'enabled': enabled,
    'iniEnabled': ini,
    'globalEnabled': false,
  },
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    // The confirmation and help dialogs register gamepad layers.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('xyz.luan/gamepads'),
          (call) async => <dynamic>[],
        );
  });

  final panelKey = GlobalKey<Armsx2TexturePanelState>();

  Future<void> pump(
    WidgetTester tester,
    _FakeClient client, {
    Locale locale = const Locale('fr'),
  }) async {
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(844, 390),
        builder: (_, _) => MaterialApp(
          locale: locale,
          supportedLocales: const [
            Locale('en'),
            Locale('fr'),
            Locale('zh', 'TW'),
          ],
          localizationsDelegates: const [
            _materialTexts,
            _cupertinoTexts,
            DefaultWidgetsLocalizations.delegate,
          ],
          home: Scaffold(
            body: SingleChildScrollView(
              child: Armsx2TexturePanel(
                key: panelKey,
                gamePath: _game,
                client: client,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('installed pack, its game and the switch are shown apart', (
    tester,
  ) async {
    final client = _FakeClient(_status());
    await pump(tester, client);
    expect(find.text('Textures HD'), findsOneWidget);
    expect(find.text('SLUS-21137'), findsOneWidget);
    expect(find.text('NTSC-U · Version 1.01'), findsOneWidget);
    expect(
      find.text('Numéro de série lu par ARMSX2 au lancement du jeu'),
      findsOneWidget,
    );
    expect(find.text('Pack installé'), findsOneWidget);
    expect(find.textContaining('3 textures de remplacement'), findsOneWidget);
    expect(find.text('Formats : PNG 2 · DDS BC1 1 · ASTC 1'), findsOneWidget);
    expect(find.text('Provenance : GoW2-HD.zip'), findsOneWidget);
    expect(
      find.text('Dossier : ARMSX2/textures/SLUS-21137/replacements'),
      findsOneWidget,
    );
    expect(find.text('Utiliser les textures HD pour ce jeu'), findsOneWidget);
    expect(
      tester.widget<Switch>(find.byKey(Armsx2TexturePanel.switchKey)).value,
      isTrue,
    );
    // The import only checks files: the engine's evidence lives in the game's menu.
    expect(
      find.textContaining('Un import vérifie seulement les fichiers.'),
      findsOneWidget,
    );
    expect(
      find.textContaining('DDS BC1–BC3/BC7 décodés par le processeur'),
      findsOneWidget,
    );
    expect(panelKey.currentState!.rows, [
      'switch',
      'importFolder',
      'importArchive',
      'remove',
      'help',
    ]);
    expect(client.names, ['status']);
  });

  testWidgets('turning HD textures off is stored for the next start', (
    tester,
  ) async {
    final client = _FakeClient(_status());
    await pump(tester, client);
    client.state = _status(enabled: false, ini: true);
    await tester.tap(find.byKey(Armsx2TexturePanel.switchKey));
    await tester.pumpAndSettle();
    expect(client.calls, contains(equals(['setEnabled', _game, false])));
    expect(
      find.text('Textures HD désactivées : s’applique au démarrage du jeu.'),
      findsOneWidget,
    );
    // NeoStation's choice differs from the game's settings until it starts.
    expect(
      find.text('Enregistré · s’applique au démarrage du jeu'),
      findsOneWidget,
    );
    expect(
      tester.widget<Switch>(find.byKey(Armsx2TexturePanel.switchKey)).value,
      isFalse,
    );
  });

  testWidgets(
    'a pack for another region is explained, then installed only once confirmed',
    (tester) async {
      final client = _FakeClient(
        _status(installed: false, enabled: null, ini: null),
      );
      client.pickAnswer = {
        'success': true,
        'token': 'T1',
        'match': 'otherSerial',
        'packSerial': 'SLES-54164',
        'packRegion': 'PAL',
        'gameSerial': 'SLUS-21137',
        'gameRegion': 'NTSC-U',
        'regionConflict': true,
        'regions': ['PAL'],
        'needsConfirmation': true,
        'replacing': false,
      };
      client.installResult = {
        'success': true,
        'serial': 'SLUS-21137',
        'named': 3,
        'bytes': 3 * 1024 * 1024,
        'unsupported': 1,
        'unsupportedSamples': ['bad-0000beef.dds'],
        'excluded': 0,
        'enabled': true,
      };
      await pump(tester, client);
      expect(panelKey.currentState!.rows, [
        'switch',
        'importFolder',
        'importArchive',
        'help',
      ]);
      await tester.tap(find.byKey(Armsx2TexturePanel.rowKey('importArchive')));
      await tester.pumpAndSettle();
      expect(find.text('Vérifiez ce pack'), findsOneWidget);
      expect(
        find.textContaining(
          'Ce pack est prévu pour SLES-54164 (PAL). Ce jeu est SLUS-21137 (NTSC-U).',
        ),
        findsOneWidget,
      );
      expect(
        find.textContaining(
          'Les noms du pack mentionnent PAL ; ce jeu est NTSC-U.',
        ),
        findsOneWidget,
      );
      expect(find.textContaining('reconnues par leur contenu'), findsOneWidget);
      expect(client.names, isNot(contains('install')));
      await tester.tap(find.text('Installer pour SLUS-21137'));
      await tester.pumpAndSettle();
      expect(
        client.calls,
        containsAllInOrder([
          ['pick', _game, false],
          ['install', 'T1', true],
          ['discard', 'T1'],
        ]),
      );
      expect(
        find.textContaining('Pack installé pour SLUS-21137 : 3 textures'),
        findsOneWidget,
      );
      expect(
        find.textContaining(
          '1 fichiers écartés : format inutilisable par ARMSX2 (bad-0000beef.dds).',
        ),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'declining the confirmation installs nothing and releases the pack',
    (tester) async {
      final client = _FakeClient(_status());
      client.pickAnswer = {
        'success': true,
        'token': 'T2',
        'match': 'same',
        'gameSerial': 'SLUS-21137',
        'needsConfirmation': false,
        'replacing': true,
      };
      await pump(tester, client);
      await tester.tap(find.byKey(Armsx2TexturePanel.rowKey('importFolder')));
      await tester.pumpAndSettle();
      expect(
        find.textContaining('Le pack actuel de ce jeu sera remplacé.'),
        findsOneWidget,
      );
      // The panel's own cancel row (import in progress) stays behind the dialog.
      await tester.tap(
        find.descendant(
          of: find.byType(AlertDialog),
          matching: find.text('Annuler'),
        ),
      );
      await tester.pumpAndSettle();
      expect(client.calls, contains(equals(['pick', _game, true])));
      expect(client.calls, contains(equals(['discard', 'T2'])));
      expect(client.names, isNot(contains('install')));
    },
  );

  testWidgets('an unusable pack is explained and never installed', (
    tester,
  ) async {
    final client = _FakeClient(_status());
    client.pickAnswer = {
      'success': false,
      'token': 'T3',
      'error': 'noNamedTextures',
    };
    await pump(tester, client);
    await tester.tap(find.byKey(Armsx2TexturePanel.rowKey('importArchive')));
    await tester.pumpAndSettle();
    expect(
      find.textContaining(
        'Aucun fichier ne porte un nom de texture de remplacement ARMSX2',
      ),
      findsOneWidget,
    );
    expect(client.calls, contains(equals(['discard', 'T3'])));
    expect(client.names, isNot(contains('install')));
    client.pickAnswer = {
      'success': false,
      'token': 'T4',
      'error': 'space',
      'needed': 2 * 1024 * 1024 * 1024,
      'available': 1024 * 1024 * 1024,
    };
    await tester.tap(find.byKey(Armsx2TexturePanel.rowKey('importArchive')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Espace libre insuffisant'), findsOneWidget);
  });

  testWidgets('progress is shown and the import can be cancelled', (
    tester,
  ) async {
    final client = _FakeClient(
      _status(installed: false, enabled: null, ini: null),
    );
    client.pickAnswer = {
      'success': true,
      'token': 'T5',
      'match': 'same',
      'gameSerial': 'SLUS-21137',
    };
    client.installAnswer = Completer<Map<String, dynamic>>();
    await pump(tester, client);
    await tester.tap(find.byKey(Armsx2TexturePanel.rowKey('importFolder')));
    await tester.pump();
    await tester.pump();
    client.progressEvents.add({
      'token': 'T5',
      'fraction': 0.42,
      'phase': 'installing',
    });
    await tester.pump();
    expect(find.text('Installation… 42 %'), findsOneWidget);
    expect(panelKey.currentState!.rows, ['cancel']);
    await panelKey.currentState!.activateRow(0);
    expect(client.calls, contains(equals(['cancel', 'T5'])));
    client.installAnswer!.complete({'success': false, 'error': 'cancelled'});
    await tester.pumpAndSettle();
    expect(
      find.text('Import annulé. Le pack précédent a été conservé.'),
      findsOneWidget,
    );
    expect(client.calls, contains(equals(['discard', 'T5'])));
  });

  testWidgets('removal is confirmed and touches only the pack', (tester) async {
    final client = _FakeClient(_status());
    await pump(tester, client);
    // The confirmation dialog needs frames: the row's future ends after it.
    final removal = panelKey.currentState!.activateRow(3); // remove
    await tester.pumpAndSettle();
    expect(
      find.text('Supprimer les textures HD de SLUS-21137 ?'),
      findsOneWidget,
    );
    expect(
      find.textContaining(
        'Seuls les fichiers de ARMSX2/textures/SLUS-21137/replacements',
      ),
      findsOneWidget,
    );
    client.state = _status(installed: false, enabled: false);
    await tester.tap(find.text('Supprimer'));
    await tester.pumpAndSettle();
    expect(client.calls, contains(equals(['remove', _game])));
    expect(
      find.text(
        'Pack supprimé. Les jeux et les sauvegardes n’ont pas été modifiés.',
      ),
      findsOneWidget,
    );
    expect(find.text('Aucun pack installé'), findsOneWidget);
    await removal;
  });

  testWidgets('without a serial nothing can be associated', (tester) async {
    final client = _FakeClient(
      _status(
        installed: false,
        serial: '',
        source: 'none',
        enabled: null,
        ini: null,
      ),
    );
    await pump(tester, client);
    expect(find.text('Numéro de série inconnu'), findsOneWidget);
    expect(find.textContaining('lancez le jeu une fois'), findsOneWidget);
    expect(
      tester.widget<Switch>(find.byKey(Armsx2TexturePanel.switchKey)).onChanged,
      isNull,
    );
    await panelKey.currentState!.activateRow(0);
    await tester.pumpAndSettle();
    expect(client.names, isNot(contains('setEnabled')));
    expect(
      find.textContaining('Le numéro de série de ce jeu est inconnu'),
      findsOneWidget,
    );
  });

  testWidgets(
    'the help separates HD textures from shaders, resolution and PNACH patches',
    (tester) async {
      final client = _FakeClient(_status());
      await pump(tester, client, locale: const Locale('en'));
      await tester.tap(find.byKey(Armsx2TexturePanel.rowKey('help')));
      await tester.pumpAndSettle();
      expect(find.text('How to prepare a pack'), findsWidgets);
      expect(
        find.textContaining('textures/<serial>/replacements'),
        findsOneWidget,
      );
      expect(find.textContaining('They are not shaders'), findsOneWidget);
      expect(find.textContaining('PNACH patches'), findsOneWidget);
    },
  );

  test(
    'twelve locales, identical keys and placeholders; Traditional Chinese selected',
    () {
      const locales = [
        'en',
        'fr',
        'de',
        'es',
        'it',
        'pt',
        'ru',
        'id',
        'ja',
        'ko',
        'zh',
        'zh_Hant',
      ];
      expect(Armsx2TextureLocale.locales, locales);
      final keys = Armsx2TextureLocale.values['en']!.keys.toList();
      final placeholder = RegExp(r'\{(\w+)\}');
      for (final locale in locales) {
        final values = Armsx2TextureLocale.values[locale]!;
        expect(values.keys.toList(), keys, reason: locale);
        for (final key in keys) {
          expect(values[key]!.trim(), isNotEmpty, reason: '$locale.$key');
          final expected =
              placeholder
                  .allMatches(Armsx2TextureLocale.values['en']![key]!)
                  .map((m) => m[1])
                  .toList()
                ..sort();
          final actual =
              placeholder.allMatches(values[key]!).map((m) => m[1]).toList()
                ..sort();
          expect(actual, expected, reason: '$locale.$key');
        }
      }
      for (final error in Armsx2TextureErrors.keys.values) {
        expect(keys, contains(error));
      }
      expect(keys, contains(Armsx2TextureErrors.keyFor('unknown')));
      expect(
        Armsx2TextureLocale.localeKey(const Locale('zh', 'TW')),
        'zh_Hant',
      );
      expect(
        Armsx2TextureLocale.localeKey(
          const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
        ),
        'zh_Hant',
      );
      expect(Armsx2TextureLocale.localeKey(const Locale('zh', 'CN')), 'zh');
      expect(
        Armsx2TextureLocale.textFor(const Locale('zh', 'HK'), 'title'),
        'HD紋理',
      );
      expect(
        Armsx2TextureLocale.textFor(const Locale('nl'), 'title'),
        'HD textures',
      );
    },
  );
}
