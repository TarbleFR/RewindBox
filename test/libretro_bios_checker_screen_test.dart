import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart' as crypto;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/models/config_model.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/screens/libretro/libretro_bios_checker_screen.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/tools_settings_content.dart';
import 'package:neostation/services/libretro_bios_catalog.dart';
import 'package:neostation/services/libretro_bios_check_service.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:path/path.dart' as p;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _gamepads = MethodChannel('xyz.luan/gamepads');
const _paths = MethodChannel('plugins.flutter.io/path_provider');
const _bridge = MethodChannel('neostation/libretro_internal');

Uint8List synthetic(int length, int seed) =>
    Uint8List.fromList(List<int>.generate(length, (index) => (index * 31 + seed * 17 + (index >> 8)) & 0xff));

/// The checker with its starts and ends counted, on temporary folders.
class _CountingService extends LibretroBiosCheckService {
  _CountingService({required super.catalog, required super.environment, required super.library, required super.hasher});

  int started = 0;
  int finished = 0;
  final roots = <List<String>>[];

  @override
  Future<LibretroBiosReport> check({Iterable<String> libraryRoots = const <String>[]}) async {
    started++;
    roots.add(libraryRoots.toList());
    try {
      return await super.check(libraryRoots: libraryRoots);
    } finally {
      finished++;
    }
  }
}

/// Library folders as the settings provider holds them.
class _Roots extends SqliteConfigProvider {
  ConfigModel _value = const ConfigModel();

  @override
  ConfigModel get config => _value;

  void set(List<String> roots) {
    _value = _value.copyWith(romFolders: roots);
    notifyListeners();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final english = LibretroLocale.values['en']!;
  late Directory root;
  late Directory system;
  late _CountingService service;

  String en(String key, [Map<String, Object?> values = const <String, Object?>{}]) =>
      LibretroLocale.format(const Locale('en'), key, values);

  setUpAll(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(mapLocales: [MapLocale('en', AppLocale.en)], initLanguageCode: 'en');
  });

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    root = Directory.systemTemp.createTempSync('libretro_bios_screen_');
    system = Directory(p.join(root.path, 'Documents', 'Libretro', 'System'))..createSync(recursive: true);
    final json = (jsonDecode(File(LibretroBiosCatalog.assetPath).readAsStringSync()) as Map).cast<String, dynamic>();
    final gb = (json['entries'] as List).cast<Map<String, dynamic>>().firstWhere((entry) => entry['id'] == 'gb-boot');
    final good = synthetic(256, 1);
    gb['knownDumps'] = <Map<String, Object?>>[
      <String, Object?>{
        'size': good.length,
        'md5': crypto.md5.convert(good).toString(),
        'sha1': crypto.sha1.convert(good).toString(),
        'label': 'synthetic',
        'source': 'test',
      },
    ];
    File(p.join(system.path, 'gb_bios.bin')).writeAsBytesSync(good);
    File(p.join(system.path, 'bios_CD_U.bin')).writeAsBytesSync(synthetic(1024, 2));
    final catalog = LibretroBiosCatalog.parse(jsonEncode(json));
    service = _CountingService(
      catalog: () async => catalog,
      environment: () async => LibretroBiosEnvironment(
        systemDirectory: system.path,
        configDirectory: p.join(root.path, 'Documents', 'Libretro', 'Config'),
        cacheFile: p.join(root.path, 'Caches', LibretroBiosCheckService.cacheFileName),
        documentsDirectory: p.join(root.path, 'Documents'),
      ),
      library: (_) async => const <LibretroBiosGame>[],
      hasher: (requests) async => LibretroBiosCheckService.hashFilesSync(requests),
    );
    messenger.setMockMethodCallHandler(_gamepads, (call) async => <dynamic>[]);
    messenger.setMockMethodCallHandler(_paths, (_) async => root.path);
    messenger.setMockMethodCallHandler(_bridge, (call) async => call.method == 'availableCores' ? <String>[] : null);
  });

  tearDown(() {
    messenger.setMockMethodCallHandler(_gamepads, null);
    messenger.setMockMethodCallHandler(_paths, null);
    messenger.setMockMethodCallHandler(_bridge, null);
    root.deleteSync(recursive: true);
  });

  /// The checker reads real folders: each step needs real time (runAsync),
  /// then a pump. Stops once [checks] checks are done and the page is idle.
  Future<void> settle(WidgetTester tester, int checks) async {
    for (var round = 0; round < 400; round++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      await tester.pump();
      if (service.finished >= checks && service.started == service.finished &&
          find.byKey(const ValueKey('bios-summary-verified')).evaluate().isNotEmpty) {
        await tester.pump();
        return;
      }
    }
    fail('Timed out after ${service.finished} checks');
  }

  Future<void> pumpChecker(
    WidgetTester tester, {
    String? console,
    Future<LibretroRetroArchCopy?> Function()? copy,
    Future<void> Function(BuildContext context)? open3ds,
    _Roots? roots,
  }) async {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    final app = MaterialApp(
      locale: const Locale('en'),
      home: LibretroBiosCheckerScreen(console: console, service: service, copyRetroArch: copy, open3dsImport: open3ds),
    );
    await tester.pumpWidget(
      roots == null ? app : ChangeNotifierProvider<SqliteConfigProvider>.value(value: roots, child: app),
    );
    await settle(tester, 1);
  }

  Finder inEntry(String id, Finder matching) => find.descendant(of: find.byKey(ValueKey('bios-entry-$id')), matching: matching);

  int summary(LibretroBiosStatus status) {
    final tile = find.byKey(ValueKey('bios-summary-${status.name}'));
    final texts = find.descendant(of: tile, matching: find.byType(Text)).evaluate().map((element) => (element.widget as Text).data);
    return int.parse(texts.last!);
  }

  testWidgets('summary, green verified badge, statuses and texts from LibretroLocale', (tester) async {
    await pumpChecker(tester);

    expect(find.text(english['biosCheckerTitle']!), findsOneWidget);
    expect(find.text(english['biosWhereToPut']!), findsOneWidget);
    expect(find.text(english['importRetroArch']!), findsOneWidget);
    expect(summary(LibretroBiosStatus.verified), 1);
    expect(summary(LibretroBiosStatus.presentUnverified), 1);
    expect(summary(LibretroBiosStatus.invalid), 0);
    // Without any PS1 BIOS, the three PlayStation files are required; the
    // ColecoVision BIOS (lot 1, docs/libretro-consoles-lot1.md) always is.
    expect(summary(LibretroBiosStatus.missingRequired), 4);
    expect(inEntry('cv-os7', find.text(english['biosStatusMissingRequired']!)), findsOneWidget);

    final badge = find.byKey(const ValueKey('bios-status-badge-gb-boot'));
    expect(find.descendant(of: badge, matching: find.text(english['biosStatusVerified']!)), findsOneWidget);
    expect(find.descendant(of: badge, matching: find.byIcon(Icons.verified_rounded)), findsOneWidget);
    final decoration = tester.widget<Container>(find.descendant(of: badge, matching: find.byType(Container)).first).decoration as BoxDecoration;
    expect(decoration.color, Colors.green.shade600);

    expect(inEntry('gb-boot', find.text(en('biosDetected', {'path': 'NeoStation/Libretro/System/gb_bios.bin'}))), findsOneWidget);
    expect(inEntry('gb-boot', find.text(english['biosLevelOptional']!)), findsOneWidget);
    expect(inEntry('mcd-na', find.text(english['biosStatusUnverified']!)), findsOneWidget);
    expect(inEntry('mcd-na', find.text(en('biosLevelConditional', {'condition': english['biosCondMegaCd']})) ), findsOneWidget);
    expect(inEntry('mcd-na', find.text(english['biosRegionNorthAmerica']!)), findsOneWidget);
    expect(inEntry('psx-na', find.text(english['biosStatusMissingRequired']!)), findsOneWidget);
    expect(inEntry('psx-na', find.text(english['biosNotFound']!)), findsOneWidget);
    expect(
      find.text(en('biosGateMissing', {'files': 'scph5500.bin, scph5501.bin, scph5502.bin'})),
      findsOneWidget,
    );
    // One PlayStation BIOS is enough: the card asks for one fix, not four.
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('bios-console-card-psx')),
        matching: find.text(en('biosConsoleProblems', {'count': 1})),
      ),
      findsOneWidget,
    );
    // 32X, SG-1000 and the twelve lot 1 consoles whose cores need no firmware.
    const noBios = <String>['32x', 'sg1000', 'ws', 'wsc', 'ngp', 'ngpc', 'vb', '2600', 'gw', 'duck', 'wsv', 'ard', 'wasm4', 'uze'];
    expect(find.text(english['biosNoBiosNeeded']!), findsNWidgets(noBios.length));
    for (final console in noBios) {
      expect(
        find.descendant(of: find.byKey(ValueKey('bios-console-card-$console')), matching: find.text(english['biosNoBiosNeeded']!)),
        findsOneWidget,
        reason: console,
      );
    }

    // Technical details open on demand.
    await tester.ensureVisible(find.byKey(const ValueKey('bios-details-gb-boot')));
    await tester.tap(find.byKey(const ValueKey('bios-details-gb-boot')));
    await tester.pumpAndSettle();
    expect(find.text('MD5 ${crypto.md5.convert(synthetic(256, 1))}'), findsWidgets);
  });

  testWidgets('filters by status and by console narrow the list', (tester) async {
    await pumpChecker(tester);
    expect(find.byKey(const ValueKey('bios-entry-mcd-na')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('bios-status-verified')));
    await tester.pump();
    expect(find.byKey(const ValueKey('bios-entry-gb-boot')), findsOneWidget);
    expect(find.byKey(const ValueKey('bios-entry-mcd-na')), findsNothing);
    expect(find.byKey(const ValueKey('bios-console-card-psx')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('bios-status-all')));
    await tester.pump();
    await tester.ensureVisible(find.byKey(const ValueKey('bios-console-psx')));
    await tester.tap(find.byKey(const ValueKey('bios-console-psx')));
    await tester.pump();
    expect(find.byKey(const ValueKey('bios-console-card-psx')), findsOneWidget);
    expect(find.byKey(const ValueKey('bios-console-card-gb')), findsNothing);
    expect(find.byKey(const ValueKey('bios-entry-psx-jp')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('bios-status-verified')));
    await tester.pump();
    expect(find.text(english['biosNoResults']!), findsOneWidget);
  });

  testWidgets('another page can open it on one console', (tester) async {
    await pumpChecker(tester, console: 'mcd');
    expect(find.byKey(const ValueKey('bios-console-card-mcd')), findsOneWidget);
    expect(find.byKey(const ValueKey('bios-console-card-gb')), findsNothing);
    final chip = tester.widget<ChoiceChip>(find.byKey(const ValueKey('bios-console-mcd')));
    expect(chip.selected, isTrue);
  });

  testWidgets('check again, app resume and library folder changes run a new check', (tester) async {
    final roots = _Roots();
    await pumpChecker(tester, roots: roots);
    expect(service.started, 1);

    await tester.tap(find.byKey(const ValueKey('libretro-bios-check-again')));
    await settle(tester, 2);
    expect(service.started, 2);

    // Files added in the Files app: the page checks again when it is back.
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await settle(tester, 3);
    expect(service.started, 3);

    final library = Directory(p.join(root.path, 'ROMs'))..createSync();
    roots.set(<String>[library.path]);
    await settle(tester, 4);
    expect(service.started, 4);
    expect(service.roots.last, <String>[library.path]);

    // Same folders again: nothing to do.
    roots.set(<String>[library.path]);
    for (var round = 0; round < 10; round++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      await tester.pump();
    }
    expect(service.started, 4);
  });

  testWidgets('the RetroArch copy is the existing import, followed by a new check', (tester) async {
    var copies = 0;
    await pumpChecker(tester, copy: () async {
      copies++;
      return const LibretroRetroArchCopy(saves: 1, states: 0, system: 2);
    });
    await tester.ensureVisible(find.byKey(const ValueKey('libretro-bios-copy-retroarch')));
    await tester.tap(find.byKey(const ValueKey('libretro-bios-copy-retroarch')));
    await settle(tester, 2);
    expect(copies, 1);
    expect(service.started, 2);
    expect(find.text(en('retroArchImported', {'saves': 1, 'states': 0, 'system': 2})), findsOneWidget);
  });

  // Build 452: an Azahar folder given to the RetroArch copy said only that
  // nothing was found (video of 13 October 2026).
  testWidgets('a 3DS emulator folder given to the RetroArch copy leads to the 3DS import', (tester) async {
    var opened = 0;
    await pumpChecker(
      tester,
      copy: () async => const LibretroRetroArchCopy(saves: 0, states: 0, system: 0, emulator3dsFolder: true),
      open3ds: (_) async => opened++,
    );
    await tester.ensureVisible(find.byKey(const ValueKey('libretro-bios-copy-retroarch')));
    await tester.tap(find.byKey(const ValueKey('libretro-bios-copy-retroarch')));
    for (var round = 0; round < 10; round++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      await tester.pump();
    }
    expect(find.text(english['retroArch3dsFolder']!), findsOneWidget);
    expect(find.text(english['retroArchNothing']!), findsNothing);
    expect(service.started, 1, reason: 'nothing was copied, nothing to check again yet');

    // The snack bar slides in before its action can be touched.
    await tester.pump(const Duration(seconds: 1));
    await tester.tap(find.text(english['system3dsImport']!));
    await settle(tester, 2);
    expect(opened, 1);
    expect(service.started, 2, reason: 'checked again once the 3DS import is closed');
  });

  testWidgets('a cancelled RetroArch copy changes nothing', (tester) async {
    await pumpChecker(tester, copy: () async => null);
    await tester.ensureVisible(find.byKey(const ValueKey('libretro-bios-copy-retroarch')));
    await tester.tap(find.byKey(const ValueKey('libretro-bios-copy-retroarch')));
    for (var round = 0; round < 10; round++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      await tester.pump();
    }
    expect(service.started, 1);
    expect(find.byType(SnackBar), findsNothing);
  });

  testWidgets('a failed check is reported and can be run again', (tester) async {
    var attempts = 0;
    final failing = _CountingService(
      catalog: () async {
        attempts++;
        throw StateError('catalog unreadable');
      },
      environment: () async => throw StateError('unused'),
      library: (_) async => const <LibretroBiosGame>[],
      hasher: (requests) async => LibretroBiosCheckService.hashFilesSync(requests),
    );
    await tester.pumpWidget(MaterialApp(locale: const Locale('en'), home: LibretroBiosCheckerScreen(service: failing)));
    final message = find.text(en('biosScanFailed', {'error': StateError('catalog unreadable')}));
    for (var round = 0; round < 50 && message.evaluate().isEmpty; round++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      await tester.pump();
    }
    expect(message, findsOneWidget);
    expect(find.text(english['biosCheckerTitle']!), findsWidgets);
    await tester.tap(find.byKey(const ValueKey('libretro-bios-check-again')));
    for (var round = 0; round < 20 && attempts < 2; round++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      await tester.pump();
    }
    expect(attempts, 2);
  });

  group('Settings › Tools', () {
    Future<GlobalKey<ToolsSettingsContentState>> pumpTools(WidgetTester tester) async {
      final key = GlobalKey<ToolsSettingsContentState>();
      tester.view.physicalSize = const Size(1600, 2400);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(800, 1200),
          builder: (context, child) => MaterialApp(
            locale: const Locale('en'),
            localizationsDelegates: FlutterLocalization.instance.localizationsDelegates,
            supportedLocales: FlutterLocalization.instance.supportedLocales,
            home: Scaffold(
              body: ToolsSettingsContent(key: key, isContentFocused: true, selectedContentIndex: 3),
            ),
          ),
        ),
      );
      await tester.pump();
      return key;
    }

    testWidgets('iOS shows the BIOS checker as the fourth tool and opens it', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      final key = await pumpTools(tester);
      // Contract replaced (docs/storage-audit-cleanup.md § 3.10, chantier 5):
      // iOS now lists five tools, the storage analysis fifth after this
      // checker (test/storage_tools_row_test.dart). The BIOS checker keeps
      // its place: fourth row, index 3, checked below.
      expect(key.currentState!.getItemCount(), 5);
      expect(find.text(english['biosCheckerTitle']!), findsOneWidget);
      expect(find.text(english['biosCheckerSubtitle']!), findsOneWidget);

      key.currentState!.selectItem(3);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(LibretroBiosCheckerScreen), findsOneWidget);
      debugDefaultTargetPlatformOverride = null;
    });

    testWidgets('other platforms keep three tools', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      final key = await pumpTools(tester);
      expect(key.currentState!.getItemCount(), 3);
      expect(find.text(english['biosCheckerTitle']!), findsNothing);
      key.currentState!.selectItem(3);
      await tester.pump();
      expect(find.byType(LibretroBiosCheckerScreen), findsNothing);
      debugDefaultTargetPlatformOverride = null;
    });
  });
}
