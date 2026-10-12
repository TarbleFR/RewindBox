import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/storage_locale.dart';

/// Test H of docs/storage-audit-cleanup.md § 6: the storage analysis and
/// cleanup texts in the twelve NeoStation languages.
void main() {
  final placeholders = RegExp(r'\{\w+\}');
  final english = StorageLocale.values['en']!;
  final french = StorageLocale.values['fr']!;

  Set<String> placeholdersOf(String text) =>
      placeholders.allMatches(text).map((m) => m[0]!).toSet();

  // Keys named by docs/storage-audit-cleanup.md § 3.11, in its order.
  const contractKeys = <String>{
    'toolTitle',
    'toolSubtitle',
    'title',
    'scanning',
    'scanAgain',
    'scanFailed',
    'cancel',
    'summary',
    'totalLogical',
    'totalAllocated',
    'freeSpace',
    'freeSpaceUnavailable',
    'gapExplanation',
    'byCategory',
    'catGames',
    'catSaves',
    'catSystem',
    'catCaches',
    'catMedia',
    'catTemporary',
    'catLogs',
    'catUserContent',
    'catNeoSwap',
    'catIndex',
    'catUnknown',
    'byRoot',
    'rootLibrary',
    'rootDocuments',
    'rootSupport',
    'rootCaches',
    'rootTemporary',
    'entries',
    'links',
    'inaccessible',
    'icloudPlaceholders',
    'orphans',
    'orphanMedia',
    'orphanMetadata',
    'orphanCovers',
    'orphanSavesInfo',
    'duplicates',
    'computeHashes',
    'duplicateReferenced',
    'cleanup',
    'levelSafe',
    'levelSafeHelp',
    'levelRegenerable',
    'levelRegenerableHelp',
    'levelConfirmed',
    'levelConfirmedHelp',
    'preview',
    'nothingToClean',
    'selectedTotal',
    'deleteAction',
    'confirmTitle',
    'confirmBody',
    'rpcs3CacheWarning',
    'mediaQuotaWarning',
    'diagnosticsWarning',
    'hdd1Warning',
    'kartpadGameDataWarning',
    'duplicateWarning',
    'sessionActive',
    'rpcs3Busy',
    'deleting',
    'resultTitle',
    'resultDeleted',
    'resultSkippedChanged',
    'resultMissing',
    'resultRefused',
    'resultMetadata',
    'journalSaved',
    'refuseLink',
    'refuseProtected',
    'refuseOutside',
    'refuseAccess',
    'refuseNotEmpty',
    'refuseChanged',
    'export',
    'exportDetailed',
    'exportDetailedHelp',
    'share',
    'shareFailed',
    'limitsTitle',
    'limitFfi',
    'limitNeoSwap',
    'limitExtensions',
    'limitUnverified',
    'technicalCode',
  };

  // Keys added for the screens with their French wording (lead, 12 October
  // 2026): see [requestedFrench].
  const screenKeys = <String>{
    'allocatedUnavailable',
    'lastScan',
    'hashing',
    'detailsShow',
    'detailsHide',
    'levelPreselectedNote',
    'levelNeverPreselectedNote',
    'warningTitle',
    'cancelled',
    'metadataBackupNote',
  };

  // One text for each StorageRefusalReason of § 3.8 and each limit that § 7
  // announces on the screen but § 3.11 does not name.
  const coverageKeys = <String>{
    'refuseNotInPlan',
    'refuseRoot',
    'refuseCacheApi',
    'refuseRedirected',
    'refuseUnknown',
    'limitFreeSpace',
    'limitLinkedFolders',
    'limitRpcs3Cache',
    'limitDolphinStates',
    'limitScannerOrphans',
    'limitNoAutoPurge',
  };

  // Placeholders of § 3.11 (plus `{date}` of lastScan); every other key has
  // none.
  const expectedPlaceholders = <String, Set<String>>{
    'scanFailed': {'{error}'},
    'lastScan': {'{date}'},
    'totalLogical': {'{size}'},
    'totalAllocated': {'{size}'},
    'freeSpace': {'{free}', '{total}'},
    'entries': {'{count}'},
    'links': {'{count}'},
    'inaccessible': {'{count}'},
    'icloudPlaceholders': {'{count}'},
    'orphanMedia': {'{count}', '{size}'},
    'orphanMetadata': {'{count}'},
    'orphanCovers': {'{count}'},
    'orphanSavesInfo': {'{count}'},
    'duplicates': {'{count}', '{size}'},
    'selectedTotal': {'{count}', '{size}'},
    'confirmBody': {'{count}', '{size}'},
    'deleting': {'{done}', '{total}'},
    'resultDeleted': {'{count}', '{size}'},
    'resultSkippedChanged': {'{count}'},
    'resultMissing': {'{count}'},
    'resultRefused': {'{count}'},
    'resultMetadata': {'{count}'},
    'journalSaved': {'{path}'},
    'technicalCode': {'{code}'},
  };

  // The maintainer's French of § 3.11. The design document types a straight
  // apostrophe; the catalogs use the typographic one, as the other catalogs
  // do with the maintainer's wording (ExternalDisplayLocale.modeFit).
  const maintainerFrench = <String, String>{
    'toolTitle': 'Analyse et nettoyage du stockage',
    'toolSubtitle':
        'Mesure l’espace utilisé par NeoStation et ses moteurs, puis propose '
        'un nettoyage prévisualisé.',
    'scanning': 'Analyse en cours…',
    'scanAgain': 'Analyser à nouveau',
    'gapExplanation':
        'L’écart avec les Réglages iOS vient des blocs APFS, du dossier '
        'temporaire purgé par iOS, de la mémoire NeoSwap délinkée et des '
        'fichiers iCloud non téléchargés.',
    'catUnknown': 'Autres données (non identifiées)',
    'rootLibrary': 'Bibliothèque',
    'orphanSavesInfo':
        'Sauvegardes et états sans jeu associé : {count} (jamais supprimés)',
    'computeHashes': 'Calculer les empreintes',
    'duplicateReferenced': 'Référencé par la bibliothèque',
    'levelSafe': 'Sûr',
    'levelRegenerable': 'Régénérable',
    'levelConfirmed': 'Avec confirmation détaillée',
    'deleteAction': 'Supprimer',
    'rpcs3CacheWarning':
        'RPCS3 recompilera ses caches LLVM au prochain lancement (démarrage '
        'plus long).',
    'mediaQuotaWarning':
        'Les médias retirés devront être rescrapés (quota ScreenScraper).',
    'sessionActive': 'Nettoyage refusé : un jeu ou un import est en cours.',
    'exportDetailed': 'Mode détaillé (chemins relatifs)',
    'exportDetailedHelp': 'Par défaut, l’export ne contient que des totaux.',
    'limitFfi':
        'Tailles allouées et espace libre non disponibles sur cet appareil : '
        'tailles logiques affichées.',
    'limitUnverified': 'Chiffres non vérifiés sur iPhone.',
  };

  // The French requested with [screenKeys].
  const requestedFrench = <String, String>{
    'allocatedUnavailable': 'Taille allouée indisponible',
    'lastScan': 'Dernière analyse : {date}',
    'hashing': 'Calcul des empreintes…',
    'detailsShow': 'Afficher le détail',
    'detailsHide': 'Masquer le détail',
    'levelPreselectedNote': 'Les éléments de ce niveau sont présélectionnés.',
    'levelNeverPreselectedNote':
        'Aucun élément n’est présélectionné : cochez chaque élément à '
        'supprimer.',
    'warningTitle': 'Avertissement',
    'cancelled':
        'Nettoyage interrompu : les fichiers déjà supprimés le restent.',
    'metadataBackupNote':
        'Une copie de la base est enregistrée avant de retirer des '
        'métadonnées.',
  };

  // Texts that are legitimately the English text in another language. None:
  // every label of this catalog has its own wording in the eleven other
  // languages (product names such as NeoSwap always come with a translated
  // word). An entry here must say why the copy is the correct translation.
  const identicalToEnglish = <String>{};

  // Written with the same characters in Simplified and Traditional Chinese
  // and used as is in Taiwan: 重新分析, 取消, 清理, 安全, 警告, 已不存在.
  const sameInBothScripts = <String>{
    'scanAgain',
    'cancel',
    'cleanup',
    'levelSafe',
    'warningTitle',
    'resultMissing',
  };

  test(
    'the storage catalog covers exactly the twelve NeoStation languages',
    () {
      expect(
        StorageLocale.values.keys.toSet(),
        AppLocale.supportedLanguages.keys.toSet(),
      );
      expect(StorageLocale.values.length, 12);
    },
  );

  test('English holds the § 3.11 keys, the screen and coverage keys', () {
    expect(contractKeys.length, 89);
    expect(contractKeys.intersection(screenKeys), isEmpty);
    expect(contractKeys.intersection(coverageKeys), isEmpty);
    expect(screenKeys.intersection(coverageKeys), isEmpty);
    expect(english.keys.toSet(), {
      ...contractKeys,
      ...screenKeys,
      ...coverageKeys,
    });
    expect(maintainerFrench.keys, everyElement(isIn(contractKeys)));
    expect(requestedFrench.keys.toSet(), screenKeys);
  });

  test('each key constant is its own name and has an English text', () {
    final source = File('lib/l10n/storage_locale.dart').readAsStringSync();
    final constants = RegExp(
      r"static const (\w+) = '(\w+)';",
    ).allMatches(source).toList();
    for (final constant in constants) {
      expect(constant[2], constant[1], reason: constant[0]);
    }
    expect(constants.map((m) => m[1]).toSet(), english.keys.toSet());
    expect(StorageLocale.toolTitle, 'toolTitle');
    expect(StorageLocale.export, 'export');
    expect(StorageLocale.technicalCode, 'technicalCode');
  });

  test('placeholders are exactly those of the contract', () {
    expect(english.keys, containsAll(expectedPlaceholders.keys));
    for (final message in english.entries) {
      expect(
        placeholdersOf(message.value),
        expectedPlaceholders[message.key] ?? const <String>{},
        reason: message.key,
      );
    }
  });

  for (final entry in StorageLocale.values.entries) {
    test('${entry.key}: same keys, same placeholders, translated text', () {
      expect(entry.value.keys.toSet(), english.keys.toSet());
      for (final message in english.entries) {
        final translated = entry.value[message.key]!;
        final reason = '${entry.key}:${message.key}';
        expect(translated.trim(), isNotEmpty, reason: reason);
        expect(translated, translated.trim(), reason: '$reason is padded');
        expect(translated, isNot(contains('\n')), reason: reason);
        expect(
          placeholdersOf(translated),
          placeholdersOf(message.value),
          reason: reason,
        );
        if (entry.key != 'en' &&
            !identicalToEnglish.contains('${entry.key}:${message.key}')) {
          expect(
            translated,
            isNot(message.value),
            reason: '$reason is English',
          );
        }
      }
    });
  }

  test('Traditional Chinese is written for Taiwan, not copied from zh', () {
    final simplified = StorageLocale.values['zh']!;
    final traditional = StorageLocale.values['zh_Hant']!;
    final copies = traditional.keys
        .where((key) => traditional[key] == simplified[key])
        .toSet();
    expect(copies, sameInBothScripts);
    // Simplified forms that Traditional Chinese never uses.
    const simplifiedOnly = <String>[
      '储',
      '设',
      '缓',
      '删',
      '备',
      '项',
      '级',
      '录',
      '据',
      '库',
      '载',
      '这',
    ];
    for (final message in traditional.entries) {
      for (final character in simplifiedOnly) {
        expect(
          message.value,
          isNot(contains(character)),
          reason: 'zh_Hant:${message.key} uses $character',
        );
      }
    }
    // Taiwan vocabulary rather than mainland terms.
    expect(traditional[StorageLocale.rootCaches], contains('快取'));
    expect(traditional[StorageLocale.catTemporary], contains('暫存'));
    expect(traditional[StorageLocale.catMedia], contains('中繼資料'));
    expect(traditional[StorageLocale.catSystem], contains('韌體'));
    expect(traditional[StorageLocale.byRoot], contains('資料夾'));
    expect(simplified[StorageLocale.rootCaches], contains('缓存'));
    expect(simplified[StorageLocale.byRoot], contains('文件夹'));
  });

  test('the maintainer wording is used in French', () {
    for (final wording in {...maintainerFrench, ...requestedFrench}.entries) {
      expect(french[wording.key], wording.value, reason: wording.key);
    }
    for (final message in french.entries) {
      expect(
        message.value,
        isNot(contains("'")),
        reason: 'fr:${message.key} uses a straight apostrophe',
      );
    }
  });

  test(
    'the design contract § 3.11 is the catalog: keys, placeholders, French',
    () {
      final document = File('docs/storage-audit-cleanup.md').readAsStringSync();
      final start = document.indexOf('### 3.11');
      expect(start, isNonNegative);
      final end = document.indexOf('\n## ', start);
      final section = document
          .substring(start, end < 0 ? document.length : end)
          .replaceAll(RegExp(r'\s*\n\s*'), ' ');
      final named = RegExp(
        r'`([a-z][A-Za-z0-9]*)`',
      ).allMatches(section).map((m) => m[1]!).toSet();
      expect(named, containsAll(contractKeys));
      expect(english.keys, containsAll(named));

      final expectedFromDocument = <String, Set<String>>{};
      final annotated = RegExp(
        r'`([a-z][A-Za-z0-9]*)`\s*\(((?:`\{\w+\}`(?:,\s*)?)+)\)',
      );
      for (final match in annotated.allMatches(section)) {
        expectedFromDocument
            .putIfAbsent(match[1]!, () => <String>{})
            .addAll(placeholdersOf(match[2]!));
      }
      final quoted = RegExp(r'`([a-z][A-Za-z0-9]*)`\s*«\s*([^»]+?)\s*»');
      final quotedKeys = <String>{};
      for (final match in quoted.allMatches(section)) {
        final key = match[1]!;
        final wording = match[2]!.replaceAll("'", '’');
        quotedKeys.add(key);
        expect(french[key], wording, reason: key);
        expect(maintainerFrench[key], wording, reason: key);
        expectedFromDocument
            .putIfAbsent(key, () => <String>{})
            .addAll(placeholdersOf(wording));
      }
      expect(quotedKeys, maintainerFrench.keys.toSet());
      for (final key in named) {
        expect(
          placeholdersOf(english[key]!),
          expectedFromDocument[key] ?? const <String>{},
          reason: key,
        );
      }
    },
  );

  test('no text names the Library sources folder, a path or a raw code', () {
    // § 1: the Library sources folder is only counted under « Bibliothèque »,
    // in no language.
    const sourcesWords = <String, List<String>>{
      'en': ['source'],
      'es': ['fuente'],
      'ru': ['источник'],
      'zh': ['来源'],
      'zh_Hant': ['來源'],
      'pt': ['fonte'],
      'fr': ['source'],
      'de': ['quelle'],
      'it': ['fonte', 'fonti'],
      'id': ['sumber'],
      'ja': ['ソース'],
      'ko': ['소스'],
    };
    // Paths, file names and codes are shown raw by the screens, never
    // written into a translated text.
    const rawTokens = <String>[
      'sources',
      'library/',
      'documents/',
      'application support',
      'caches/',
      'tmp/',
      'dev_hdd',
      'vfs.yml',
      '.sqlite',
      '.jsonl',
      'inv-',
      'enoent',
      'eacces',
    ];
    expect(sourcesWords.keys.toSet(), StorageLocale.values.keys.toSet());
    for (final language in StorageLocale.values.entries) {
      for (final message in language.value.entries) {
        final lower = message.value.toLowerCase();
        for (final word in [...rawTokens, ...sourcesWords[language.key]!]) {
          expect(
            lower,
            isNot(contains(word)),
            reason: '${language.key}:${message.key} contains $word',
          );
        }
      }
    }
  });

  test('script and regional Chinese settings select Traditional Chinese', () {
    const key = StorageLocale.title;
    final traditional = StorageLocale.values['zh_Hant']![key];
    final simplified = StorageLocale.values['zh']![key];
    expect(traditional, isNot(simplified));
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale.fromSubtags(
        languageCode: 'zh',
        scriptCode: 'Hant',
        countryCode: 'TW',
      ),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
      const Locale('zh_Hant'),
    ]) {
      expect(StorageLocale.codeFor(locale), 'zh_Hant', reason: '$locale');
      expect(
        StorageLocale.forLocale(locale, key),
        traditional,
        reason: locale.toString(),
      );
    }
    for (final locale in <Locale>[
      const Locale('zh'),
      const Locale('zh', 'CN'),
      const Locale('zh', 'SG'),
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hans'),
    ]) {
      expect(StorageLocale.codeFor(locale), 'zh', reason: '$locale');
      expect(StorageLocale.forLocale(locale, key), simplified);
    }
    for (final code in StorageLocale.values.keys.where((c) => c != 'zh_Hant')) {
      expect(StorageLocale.codeFor(Locale(code)), code);
    }
    expect(StorageLocale.codeFor(const Locale('pt', 'BR')), 'pt');
    expect(StorageLocale.forLocale(const Locale('nl'), key), english[key]);
    expect(
      StorageLocale.forLocale(const Locale('fr'), 'noSuchKey'),
      'noSuchKey',
    );
  });

  testWidgets('text() follows the app locale and fills the placeholders', (
    tester,
  ) async {
    late BuildContext captured;
    await tester.pumpWidget(
      Localizations(
        locale: const Locale('fr'),
        delegates: const <LocalizationsDelegate<dynamic>>[
          DefaultWidgetsLocalizations.delegate,
        ],
        child: Builder(
          builder: (context) {
            captured = context;
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    expect(
      StorageLocale.text(captured, StorageLocale.toolTitle),
      'Analyse et nettoyage du stockage',
    );
    expect(
      StorageLocale.text(captured, StorageLocale.freeSpace, {
        'free': '12,4 Go',
        'total': '128 Go',
      }),
      'Espace libre : 12,4 Go sur 128 Go',
    );
    expect(
      StorageLocale.format(captured, StorageLocale.deleting, {
        'done': 3,
        'total': 50,
      }),
      'Suppression en cours… 3 sur 50',
    );
    expect(
      StorageLocale.text(captured, StorageLocale.orphanSavesInfo, {'count': 4}),
      'Sauvegardes et états sans jeu associé : 4 (jamais supprimés)',
    );
  });

  test('fill() inserts each value once and keeps unknown placeholders', () {
    // A raw path or error that contains braces is never expanded again.
    expect(
      StorageLocale.forLocale(const Locale('en'), StorageLocale.journalSaved, {
        'path': 'Diagnostics/run-{count}.jsonl',
        'count': 7,
      }),
      'Log saved: Diagnostics/run-{count}.jsonl',
    );
    expect(StorageLocale.fill('{a} {b}', {'a': '{b}', 'b': 'x'}), '{b} x');
    expect(StorageLocale.fill('{count} ({size})', {'count': 2}), '2 ({size})');
    expect(StorageLocale.fill('Code: {code}', const {}), 'Code: {code}');
    expect(StorageLocale.fill('[{x}]', {'x': null}), '[]');
  });

  test('the enum names of §§ 3.1, 3.7 and 3.8 map to catalog keys', () {
    final document = File('docs/storage-audit-cleanup.md').readAsStringSync();
    // Value names of `enum <name> { … }`, comments, annotations and the
    // members of an enhanced enum left aside.
    List<String>? enumNames(String source, String name) {
      final match = RegExp('enum $name\\s*\\{([^}]*)\\}').firstMatch(source);
      if (match == null) return null;
      final body = match[1]!
          .replaceAll(RegExp(r'/\*.*?\*/', dotAll: true), ' ')
          .replaceAll(RegExp(r'//[^\n]*'), ' ')
          .split(';')
          .first;
      return body
          .split(',')
          .map((value) => value.replaceAll(RegExp(r'@\w+(\([^)]*\))?'), ''))
          .map((value) => RegExp(r'^\s*(\w+)').firstMatch(value)?[1])
          .whereType<String>()
          .toList();
    }

    final maps = <String, (Map<String, String>, String)>{
      'StorageCategory': (
        StorageLocale.categoryKeys,
        'lib/services/storage/storage_roots.dart',
      ),
      'StorageContainer': (
        StorageLocale.containerKeys,
        'lib/services/storage/storage_roots.dart',
      ),
      'StorageCleanupLevel': (
        StorageLocale.levelKeys,
        'lib/services/storage/storage_cleanup_planner.dart',
      ),
      'StorageRefusalReason': (
        StorageLocale.refusalKeys,
        'lib/services/storage/storage_deletion_manager.dart',
      ),
    };
    for (final entry in maps.entries) {
      final (keys, implementation) = entry.value;
      final contract = enumNames(document, entry.key);
      expect(contract, isNotNull, reason: entry.key);
      expect(keys.keys.toList(), contract, reason: entry.key);
      // Once the service exists, its enum must match the catalog too.
      final file = File(implementation);
      if (file.existsSync()) {
        final names = enumNames(file.readAsStringSync(), entry.key);
        if (names != null) {
          expect(keys.keys.toList(), names, reason: implementation);
        }
      }
      expect(keys.values.toSet().length, keys.length, reason: entry.key);
      expect(english.keys, containsAll(keys.values), reason: entry.key);
    }
    expect(StorageLocale.levelHelpKeys.keys, StorageLocale.levelKeys.keys);
    expect(english.keys, containsAll(StorageLocale.levelHelpKeys.values));
  });

  test('every StorageLocale key used in lib/ exists in the catalog', () {
    const api = <String>{
      'values',
      'codeFor',
      'forLocale',
      'text',
      'format',
      'fill',
      'categoryKeys',
      'containerKeys',
      'levelKeys',
      'levelHelpKeys',
      'refusalKeys',
    };
    final members = RegExp(r'\bStorageLocale\.(\w+)');
    final literals = RegExp(
      r"\bStorageLocale\.(?:text|format|forLocale)\(\s*[^,()]+,\s*'(\w+)'",
    );
    final used = <String, String>{};
    for (final entity in Directory(
      'lib',
    ).listSync(recursive: true, followLinks: false)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final path = entity.path.replaceAll(r'\', '/');
      if (path == 'lib/l10n/storage_locale.dart') continue;
      final source = entity.readAsStringSync();
      for (final match in members.allMatches(source)) {
        if (!api.contains(match[1])) used[match[1]!] = entity.path;
      }
      for (final match in literals.allMatches(source)) {
        used[match[1]!] = entity.path;
      }
    }
    for (final use in used.entries) {
      expect(english.containsKey(use.key), isTrue, reason: '$use');
    }
  });
}
