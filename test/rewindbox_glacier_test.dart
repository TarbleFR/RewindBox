// RewindBox Glacier: System Art alias resolution, offline installation of the
// embedded pack, the one-step preset, the Glacier grid geometry and the
// twelve languages of its texts.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/providers/neo_assets_provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/themes_settings_content.dart';
import 'package:path/path.dart' as path;
import 'package:neostation/l10n/glacier_locale.dart';
import 'package:neostation/l10n/interface_style_locale.dart';
import 'package:neostation/models/config_model.dart';
import 'package:neostation/models/my_systems.dart';
import 'package:neostation/screens/systems_screen/my_systems_section/grid_geometry.dart';
import 'package:neostation/services/glacier_preset.dart';
import 'package:neostation/services/neo_assets_service.dart';
import 'package:neostation/services/system_art/bundled_system_art.dart';
import 'package:neostation/services/system_art/system_art_alias_table.dart';
import 'package:neostation/themes/interface_style.dart';

const _locales = [
  'en',
  'es',
  'ru',
  'zh',
  'zh_Hant',
  'pt',
  'fr',
  'de',
  'it',
  'id',
  'ja',
  'ko',
];

/// The application bundle, with one file and the index optionally altered:
/// a newer pack version whose file is corrupt.
class _AlteredBundle extends CachingAssetBundle {
  _AlteredBundle({this.digest, this.corrupt});
  final String? digest;
  final String? corrupt;

  @override
  Future<ByteData> load(String key) async {
    final data = await rootBundle.load(key);
    if (corrupt != null && key.endsWith('/$corrupt')) {
      final bytes = Uint8List.fromList(
        data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes),
      );
      bytes[bytes.length ~/ 2] ^= 0xFF;
      return ByteData.sublistView(bytes);
    }
    return data;
  }

  @override
  Future<String> loadString(String key, {bool cache = true}) async {
    final text = await rootBundle.loadString(key, cache: false);
    if (digest != null && key == BundledSystemArt.indexAsset) {
      final index = jsonDecode(text) as Map<String, dynamic>;
      index['contentDigest'] = digest;
      index['version'] = '9.9.9';
      return jsonEncode(index);
    }
    return text;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory root;
  late Directory themes;

  setUp(() async {
    root = await Directory.systemTemp.createTemp('rewindbox-glacier-unit-');
    themes = Directory(path.join(root.path, 'themes'))..createSync();
    BundledSystemArt.themesDirectoryOverride = () async => themes.path;
    BundledSystemArt.bundleOverride = null;
    NeoAssetsService.debugSetThemesDirectory(themes.path);
    SystemArtAliasTable.invalidate();
  });

  tearDown(() async {
    BundledSystemArt.themesDirectoryOverride = null;
    BundledSystemArt.bundleOverride = null;
    NeoAssetsService.debugSetThemesDirectory(null);
    SystemArtAliasTable.invalidate();
    await root.delete(recursive: true);
  });

  String pack() => path.join(themes.path, BundledSystemArt.folder);

  group('alias table', () {
    late SystemArtAliasTable table;
    setUp(() async {
      table = SystemArtAliasTable.parse(
        await rootBundle.loadString(
          '${BundledSystemArt.assetRoot}/aliases.json',
        ),
      )!;
    });

    test('122 plain canonical ids, every key owned by one of them', () {
      expect(table.canonicalIds, hasLength(122));
      for (final id in table.canonicalIds) {
        expect(
          RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]*$').hasMatch(id),
          isTrue,
          reason: id,
        );
        expect(table.resolve(id), id);
      }
    });

    test('Switch 2 has its own tile, distinct from the Switch', () {
      expect(table.resolve('switch2'), 'switch2');
      expect(table.resolve('Nintendo Switch 2'), 'switch2');
      expect(table.resolve('switch'), 'switch');
      expect(table.resolve('Nintendo Switch'), 'switch');
    });

    test('exact canonical id first: PSP Minis is not PSP', () {
      expect(table.resolve('pspminis'), 'pspminis');
      expect(table.resolve('psp'), 'psp');
      expect(table.resolve('PSP'), 'psp');
    });

    test('names, case variants and accents resolve to their system', () {
      expect(table.resolve('Super Nintendo'), 'snes');
      expect(table.resolve('SUPER NINTENDO'), 'snes');
      expect(table.resolve('  super nintendo '), 'snes');
      expect(table.resolve('Sega Mega Drive'), 'md');
      expect(table.resolve('playstation'), 'ps1');
      expect(table.resolve('genesis'), 'genesis');
      expect(table.resolve('not a system'), isNull);
    });

    test('the three slash aliases are logical keys, never paths', () {
      expect(table.resolve('NEC PC-8000/8800'), 'pc88');
      expect(table.resolve('Commodore Plus/4'), 'plus4');
      expect(table.resolve('Commodore - PLUS/4'), 'plus4');
    });

    test('a malformed table is refused', () {
      expect(SystemArtAliasTable.parse('{"schema": 2}'), isNull);
      expect(
        SystemArtAliasTable.parse(
          '{"schema": 1, "canonicalIds": ["../x", "ok"], "lookup": '
          '{"evil": {"owner": "../x"}, "fine": {"owner": "ok"}}}',
        )!.resolve('evil'),
        isNull,
      );
    });
  });

  group('offline installation of the embedded pack', () {
    test('installs every file of the index, without network', () async {
      expect(await BundledSystemArt.ensureInstalled(), isTrue);
      final index =
          jsonDecode(await rootBundle.loadString(BundledSystemArt.indexAsset))
              as Map<String, dynamic>;
      final files = (index['files'] as List).cast<Map>();
      expect(files, hasLength(129));
      for (final file in files) {
        final installed = File(path.join(pack(), file['path'] as String));
        expect(
          installed.lengthSync(),
          file['size'],
          reason: file['path'] as String,
        );
      }
      final record = jsonDecode(
        File(
          path.join(pack(), BundledSystemArt.installRecordName),
        ).readAsStringSync(),
      );
      expect(record['complete'], isTrue);
      expect(record['contentDigest'], index['contentDigest']);
      expect(File(path.join(pack(), 'theme.json')).existsSync(), isTrue);
      expect(File(path.join(pack(), 'CREDITS.md')).existsSync(), isTrue);
    });

    test('the same version is only checked, never copied again', () async {
      expect(await BundledSystemArt.ensureInstalled(), isTrue);
      final record = File(
        path.join(pack(), BundledSystemArt.installRecordName),
      );
      final first = record.readAsStringSync();
      expect(await BundledSystemArt.ensureInstalled(), isTrue);
      expect(record.readAsStringSync(), first);
    });

    test('two requests share one installation', () async {
      final a = BundledSystemArt.ensureInstalled();
      final b = BundledSystemArt.ensureInstalled();
      expect(await a, isTrue);
      expect(await b, isTrue);
      expect(themes.listSync().map((e) => path.basename(e.path)), [
        BundledSystemArt.folder,
      ]);
    });

    test('an interrupted swap is resumed and stale staging removed', () async {
      expect(await BundledSystemArt.ensureInstalled(), isTrue);
      // Killed between the two renames: the pack is only in ".previous".
      Directory(pack()).renameSync(
        path.join(themes.path, '.${BundledSystemArt.folder}.previous'),
      );
      Directory(
        path.join(themes.path, '.${BundledSystemArt.folder}.installing-1'),
      ).createSync();
      expect(await BundledSystemArt.ensureInstalled(), isTrue);
      expect(themes.listSync().map((e) => path.basename(e.path)), [
        BundledSystemArt.folder,
      ]);
      expect(File(path.join(pack(), 'aliases.json')).existsSync(), isTrue);
    });

    test('a failed update keeps the previous pack', () async {
      expect(await BundledSystemArt.ensureInstalled(), isTrue);
      final before = File(
        path.join(pack(), BundledSystemArt.installRecordName),
      ).readAsStringSync();
      BundledSystemArt.bundleOverride = _AlteredBundle(
        digest: 'f' * 64,
        corrupt: 'backgrounds/snes.webp',
      );
      expect(await BundledSystemArt.ensureInstalled(), isFalse);
      expect(
        File(
          path.join(pack(), BundledSystemArt.installRecordName),
        ).readAsStringSync(),
        before,
      );
      expect(
        File(path.join(pack(), 'backgrounds', 'snes.webp')).existsSync(),
        isTrue,
      );
      expect(themes.listSync().map((e) => path.basename(e.path)), [
        BundledSystemArt.folder,
      ]);
    });

    test(
      'art paths come from the alias table and stay inside the pack',
      () async {
        expect(await BundledSystemArt.ensureInstalled(), isTrue);
        String? art(String name) => NeoAssetsService.resolveBackgroundPathSync(
          BundledSystemArt.folder,
          name,
        );
        expect(art('snes'), path.join(pack(), 'backgrounds', 'snes.webp'));
        expect(
          art('Super Nintendo'),
          path.join(pack(), 'backgrounds', 'snes.webp'),
        );
        expect(
          art('pspminis'),
          path.join(pack(), 'backgrounds', 'pspminis.webp'),
        );
        expect(
          art('NEC PC-8000/8800'),
          path.join(pack(), 'backgrounds', 'pc88.webp'),
        );
        expect(
          art('Commodore Plus/4'),
          path.join(pack(), 'backgrounds', 'plus4.webp'),
        );
        expect(art('../../secrets'), isNull);
        expect(art('a/b'), isNull);
        for (final name in ['snes', 'pspminis', 'NEC PC-8000/8800']) {
          expect(path.isWithin(pack(), art(name)!), isTrue);
        }
      },
    );

    test(
      'the picker lists the embedded pack first, offline, with a local preview',
      () async {
        final listed = await NeoAssetsService.fetchThemes();
        expect(listed.first.folder, BundledSystemArt.folder);
        expect(listed.first.name, 'RewindBox Glacier');
        expect(listed.first.isBundled, isTrue);
        expect(listed.first.previewAsset, BundledSystemArt.previewAsset);
        expect(
          listed.where((t) => t.folder == BundledSystemArt.folder),
          hasLength(1),
        );
      },
    );
  });

  group('preset', () {
    test(
      'a new installation starts on Glacier, an update keeps its choices',
      () {
        const fresh = ConfigModel();
        expect(
          GlacierPreset.isExistingInstall(
            config: fresh,
            hasInterfaceStyle: false,
            savedThemeName: 'system',
            savedSystemArt: '',
          ),
          isFalse,
        );
        for (final existing in [
          (const ConfigModel(setupCompleted: true), false, 'system', ''),
          (const ConfigModel(romFolders: ['/roms']), false, 'system', ''),
          (fresh, true, 'system', ''),
          (fresh, false, 'dark', ''),
          (fresh, false, 'system', 'neoassets-pack'),
        ]) {
          expect(
            GlacierPreset.isExistingInstall(
              config: existing.$1,
              hasInterfaceStyle: existing.$2,
              savedThemeName: existing.$3,
              savedSystemArt: existing.$4,
            ),
            isTrue,
          );
        }
      },
    );

    test(
      'Glacier sets the layout and keeps motion, bubbles, density and status',
      () {
        const mine = InterfaceStyleSettings(
          motion: MotionLevel.reduced,
          showSystemBubbles: false,
          density: InterfaceDensity.comfortable,
          tabIconSize: TabIconSize.large,
          showClock: false,
        );
        final glacier = GlacierPreset.interfaceSettings(mine);
        expect(glacier.style, InterfaceStyle.glacier);
        expect(glacier.tabIndicator, TabIndicatorStyle.glacier);
        expect(glacier.tabLabels, TabLabelMode.selectedOnly);
        expect(glacier.showTabBumpers, isTrue);
        expect(glacier.motion, MotionLevel.reduced);
        expect(glacier.showSystemBubbles, isFalse);
        expect(glacier.density, InterfaceDensity.comfortable);
        expect(glacier.tabIconSize, TabIconSize.large);
        expect(glacier.showClock, isFalse);
        expect(InterfaceStyleSettings.decode(glacier.encode()), glacier);
      },
    );

    test('the previous look round-trips without the personal background', () {
      const previous = GlacierPreviousLook(
        themeName: 'dark',
        interfaceStyle: '{"style":"liquidGlass"}',
        systemArt: 'neoassets-pack',
      );
      final restored = GlacierPreviousLook.fromJson(
        jsonEncode(previous.toJson()),
      )!;
      expect(restored.themeName, 'dark');
      expect(restored.systemArt, 'neoassets-pack');
      expect(restored.toJson().keys, isNot(contains('background')));
      expect(GlacierPreviousLook.fromJson('not json'), isNull);
    });
  });

  group('grid geometry', () {
    test('two full rows at the reference format', () {
      final d = calculateGlacierGridDimensions(
        width: 838.5 + 0,
        viewportHeight: 254,
        cols: 6,
        rows: 2,
      );
      expect(d['itemHeight']! * 2 + d['mainAxisSpacing']!, closeTo(254, .01));
      expect(d['itemHeight']! / d['itemWidth']!, closeTo(246 / 264, .03));
    });

    test('a taller screen shows more whole rows when the library has them', () {
      final few = calculateGlacierGridDimensions(
        width: 1090,
        viewportHeight: 600,
        cols: 6,
        rows: 2,
      );
      final many = calculateGlacierGridDimensions(
        width: 1090,
        viewportHeight: 600,
        cols: 6,
        rows: 4,
      );
      expect(few['itemHeight']! / few['itemWidth']!, closeTo(1.12, .001));
      expect(
        many['itemHeight']! * 4 + many['mainAxisSpacing']! * 3,
        closeTo(600, .01),
      );
    });

    test('a compact screen keeps card proportions and scrolls', () {
      final d = calculateGlacierGridDimensions(
        width: 600,
        viewportHeight: 150,
        cols: 6,
        rows: 2,
      );
      expect(d['itemHeight']! / d['itemWidth']!, closeTo(.78, .001));
    });

    test('one card template: the recent game takes one cell', () {
      final cards = [
        SystemInfo(title: 'Game', isGame: true),
        for (var i = 0; i < 7; i++) SystemInfo(title: 's$i', folderName: 's$i'),
      ];
      final grid = buildVirtualGrid(cards, 6, uniformSpans: true);
      expect(grid, [
        [0, 1, 2, 3, 4, 5],
        [6, 7, -1, -1, -1, -1],
      ]);
    });
  });

  testWidgets(
    'Settings › Themes applies the whole Glacier look, then restores the previous one',
    (tester) async {
      SharedPreferences.setMockInitialValues({});
      await FlutterLocalization.instance.ensureInitialized();
      FlutterLocalization.instance.init(
        mapLocales: [MapLocale('fr', AppLocale.fr)],
        initLanguageCode: 'fr',
      );
      final theme = ThemeProvider.testing(themeName: 'dark');
      final assets = NeoAssetsProvider()..debugSetActiveTheme('some-pack');
      final config = SqliteConfigProvider();
      addTearDown(theme.dispose);
      addTearDown(assets.dispose);
      addTearDown(config.dispose);
      await tester.binding.setSurfaceSize(const Size(1000, 1600));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (_, _) => MultiProvider(
            providers: [
              ChangeNotifierProvider.value(value: theme),
              ChangeNotifierProvider.value(value: assets),
              ChangeNotifierProvider.value(value: config),
            ],
            child: MaterialApp(
              localizationsDelegates:
                  FlutterLocalization.instance.localizationsDelegates,
              supportedLocales: FlutterLocalization.instance.supportedLocales,
              home: const Scaffold(
                body: ThemesSettingsContent(
                  isContentFocused: false,
                  selectedContentIndex: 0,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      final card = find.byKey(const ValueKey('glacier-preset-card'));
      expect(card, findsOneWidget);
      expect(find.text('RewindBox Glacier'), findsOneWidget);
      expect(
        find.text(GlacierLocale.values['fr']![GlacierLocale.presetSubtitle]!),
        findsOneWidget,
      );

      await tester.runAsync(() async {
        expect(await GlacierPreset.apply(theme: theme, assets: assets), isTrue);
      });
      await tester.pump();
      expect(GlacierPreset.isActive(theme, assets), isTrue);
      expect(theme.currentThemeName, 'glacier');
      expect(theme.interfaceStyle.style, InterfaceStyle.glacier);
      expect(assets.activeThemeFolder, BundledSystemArt.folder);
      expect(
        find.text(GlacierLocale.values['fr']![GlacierLocale.presetRestore]!),
        findsOneWidget,
      );

      await tester.runAsync(() async {
        expect(
          await GlacierPreset.restorePrevious(
            theme: theme,
            assets: assets,
            systemFolders: const [],
          ),
          isTrue,
        );
      });
      await tester.pump();
      expect(theme.currentThemeName, 'dark');
      expect(theme.interfaceStyle.style, InterfaceStyle.liquidGlass);
      expect(GlacierPreset.isActive(theme, assets), isFalse);
      expect(await GlacierPreset.previousLook(), isNull);
      expect(tester.takeException(), isNull);
    },
  );

  test('every Glacier text exists in the twelve languages', () {
    final keys = GlacierLocale.values['en']!.keys.toSet();
    for (final locale in _locales) {
      expect(GlacierLocale.values[locale]?.keys.toSet(), keys, reason: locale);
      for (final key in keys) {
        expect(
          GlacierLocale.values[locale]![key]!.trim(),
          isNotEmpty,
          reason: '$locale $key',
        );
      }
    }
    for (final locale in _locales) {
      for (final key in [
        InterfaceStyleLocale.styleGlacier,
        InterfaceStyleLocale.styleGlacierHint,
        InterfaceStyleLocale.indicatorGlacier,
      ]) {
        expect(
          InterfaceStyleLocale.values[locale]?[key],
          isNotNull,
          reason: '$locale $key',
        );
      }
    }
    expect(
      GlacierLocale.forLocale(const Locale('fr'), GlacierLocale.recent),
      'Récent',
    );
    expect(
      GlacierLocale.forLocale(
        const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
        GlacierLocale.presetApply,
      ),
      '套用 Glacier',
    );
  });
}
