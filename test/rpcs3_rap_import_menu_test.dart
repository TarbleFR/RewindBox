// The PS3 library Import menu offers "Import RAP licenses" after the folder
// import. Picking .rap files installs them where RPCS3 reads them, asks once
// before replacing a different licence, then shows the per-file report. The
// library is never reloaded, no progress overlay covers the dialogs, and
// RPCS3's Core and JIT channels stay silent.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/rpcs3_rap_licence_service.dart';
import 'package:neostation/widgets/library_focus_gamepad_layer.dart';
import 'package:neostation/widgets/rpcs3_internal_playlist_actions.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

const _id = 'EP0001-BLES00000_00-0123456789ABCDEF';

Uint8List _rap(int seed) =>
    Uint8List.fromList(List<int>.generate(16, (i) => (seed * 7 + i) & 0xff));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const paths = MethodChannel('plugins.flutter.io/path_provider');
  const documents = MethodChannel('neostation/rpcs3_documents');
  const core = MethodChannel('neostation/rpcs3_internal');
  const jit = MethodChannel('neostation/rpcs3_jit');
  const gamepads = MethodChannel('xyz.luan/gamepads');

  late Directory support;
  late String dataRoot;
  late List<String> calls;
  late List<String> selection;
  var libraryReloads = 0;

  setUp(() async {
    support = await Directory.systemTemp.createTemp('rpcs3-rap-menu-');
    dataRoot = p.join(support.path, 'NeoStation', 'RPCS3', 'Data');
    final version = File(
      p.join(dataRoot, 'dev_flash', 'vsh', 'etc', 'version.txt'),
    );
    await version.parent.create(recursive: true);
    await version.writeAsString('release:04.9100:\n');
    calls = <String>[];
    selection = <String>[];
    libraryReloads = 0;
    SharedPreferences.setMockInitialValues({});
    messenger.setMockMethodCallHandler(paths, (_) async => support.path);
    messenger.setMockMethodCallHandler(gamepads, (_) async => <dynamic>[]);
    messenger.setMockMethodCallHandler(documents, (call) async {
      calls.add('documents/${call.method}');
      return call.method == 'pickGameFiles' ? selection : true;
    });
    for (final channel in [core, jit]) {
      messenger.setMockMethodCallHandler(channel, (call) async {
        calls.add('${channel.name}/${call.method}');
        throw PlatformException(code: 'runtimeMustRemainDormant');
      });
    }
  });

  tearDown(() async {
    for (final channel in [paths, documents, core, jit, gamepads]) {
      messenger.setMockMethodCallHandler(channel, null);
    }
    await support.delete(recursive: true);
  });

  Future<String> pick(String name, List<int> bytes) async {
    final folder = Directory(
      p.join(support.path, 'Picked', '${selection.length}'),
    );
    await folder.create(recursive: true);
    final file = File(p.join(folder.path, name));
    await file.writeAsBytes(bytes);
    return file.path;
  }

  String exdata() => Rpcs3RapLicenceService.exdataPath(dataRoot);

  /// Filesystem work completes on the real event loop and widget work on
  /// the test clock: alternate both until [done].
  Future<void> settle(WidgetTester tester, bool Function() done) async {
    for (var frame = 0; !done() && frame < 300; frame++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 5)),
      );
      await tester.pump(const Duration(milliseconds: 16));
    }
    expect(done(), isTrue, reason: 'The awaited state never appeared');
    await tester.pump(const Duration(milliseconds: 300));
  }

  bool shown(Finder finder) => finder.evaluate().isNotEmpty;

  Future<void> openLibrary(
    WidgetTester tester, {
    Locale locale = const Locale('en'),
    bool embedded = false,
  }) async {
    var firmwareChecked = false;
    await tester.pumpWidget(
      MaterialApp(
        locale: locale,
        supportedLocales: [locale],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: Builder(
          builder: (context) {
            ScreenUtil.init(context, designSize: const Size(800, 600));
            final actions = Rpcs3InternalPlaylistActions(
              embedded: embedded,
              onLibraryChanged: () async => libraryReloads++,
              onFirmwareChanged: (_) => firmwareChecked = true,
              onBack: () {},
            );
            return Scaffold(
              appBar: embedded ? AppBar(actions: [actions]) : null,
              body: embedded
                  ? const SizedBox.expand()
                  : Stack(children: [Positioned.fill(child: actions)]),
            );
          },
        ),
      ),
    );
    await settle(tester, () => firmwareChecked);
    await tester.pumpAndSettle();
  }

  Future<void> chooseRapImport(WidgetTester tester, String label) async {
    await tester.tap(find.byKey(const ValueKey('rpcs3-internal-import-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text(label));
    await tester.pump();
  }

  testWidgets('the licence item sits right after the folder import', (
    tester,
  ) async {
    await openLibrary(tester);
    await tester.tap(find.byKey(const ValueKey('rpcs3-internal-import-menu')));
    await tester.pumpAndSettle();
    final labels = [
      'Import games',
      'Import a decrypted game folder',
      'Import RAP licenses',
      'Install PS3 firmware',
      'Open RPCS3',
    ];
    final tops = [
      for (final label in labels) tester.getTopLeft(find.text(label)).dy,
    ];
    for (var i = 1; i < tops.length; i++) {
      expect(tops[i], greaterThan(tops[i - 1]), reason: labels[i]);
    }
    expect(calls, isEmpty);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('imports, reports each file and never reloads the library', (
    tester,
  ) async {
    await openLibrary(tester);
    selection = [
      await tester.runAsync(() => pick('$_id.RAP', _rap(1))) as String,
    ];
    selection.add(
      await tester.runAsync(() => pick('readme.txt', [1, 2])) as String,
    );
    await chooseRapImport(tester, 'Import RAP licenses');
    expect(
      find.byKey(const ValueKey('rpcs3-import-progress-overlay')),
      findsNothing,
    );
    await settle(
      tester,
      () => shown(find.byKey(const ValueKey('rpcs3-rap-report'))),
    );

    expect(find.text('RAP licenses'), findsOneWidget);
    expect(find.text('Imported: 1 • Rejected: 1'), findsOneWidget);
    expect(find.text('$_id.RAP'), findsOneWidget);
    expect(find.text('Installed as $_id.rap'), findsOneWidget);
    expect(find.text('Imported'), findsOneWidget);
    expect(find.text('readme.txt'), findsOneWidget);
    expect(find.text('Not a .rap file.'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('rpcs3-import-progress-overlay')),
      findsNothing,
    );
    final installed = await tester.runAsync(
      () => File(p.join(exdata(), '$_id.rap')).readAsBytes(),
    );
    expect(installed, _rap(1));

    await tester.tap(find.byKey(const ValueKey('rpcs3-rap-close')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('rpcs3-rap-report')), findsNothing);
    expect(libraryReloads, 0);
    expect(calls, [
      'documents/pickGameFiles',
      'documents/releaseScopedResources',
    ]);
    // The menu is usable again.
    expect(
      tester
          .widget<PopupMenuButton<String>>(
            find.byKey(const ValueKey('rpcs3-internal-import-menu')),
          )
          .enabled,
      isTrue,
    );
    await tester.pumpWidget(const SizedBox.shrink());
  });

  for (final replace in [true, false]) {
    testWidgets('a different installed licence asks once and is '
        '${replace ? 'replaced with a backup' : 'kept'}', (tester) async {
      await tester.runAsync(() async {
        final file = File(p.join(exdata(), '$_id.rap'));
        await file.parent.create(recursive: true);
        await file.writeAsBytes(_rap(1));
      });
      await openLibrary(tester);
      selection = [
        await tester.runAsync(() => pick('$_id.rap', _rap(2))) as String,
      ];
      await chooseRapImport(tester, 'Import RAP licenses');
      await settle(
        tester,
        () => shown(find.byKey(const ValueKey('rpcs3-rap-replace-dialog'))),
      );
      expect(find.text('Replace installed licenses?'), findsOneWidget);
      expect(find.text(_id), findsOneWidget);
      expect(
        find.byKey(const ValueKey('rpcs3-import-progress-overlay')),
        findsNothing,
      );

      await tester.tap(
        find.byKey(ValueKey(replace ? 'rpcs3-rap-replace' : 'rpcs3-rap-keep')),
      );
      await tester.pump();
      await settle(
        tester,
        () => shown(find.byKey(const ValueKey('rpcs3-rap-report'))),
      );

      final installed = await tester.runAsync(
        () => File(p.join(exdata(), '$_id.rap')).readAsBytes(),
      );
      final backups = Directory(
        p.join(support.path, 'NeoStation', 'RPCS3', 'RapBackups'),
      );
      if (replace) {
        expect(find.text('Replaced: 1'), findsOneWidget);
        expect(
          find.text('The previous license was kept as a backup.'),
          findsOneWidget,
        );
        expect(installed, _rap(2));
        expect(backups.listSync(), hasLength(1));
      } else {
        expect(find.text('Rejected: 1'), findsOneWidget);
        expect(
          find.text(
            'A different license is already installed for this content ID. '
            'It was kept.',
          ),
          findsOneWidget,
        );
        expect(installed, _rap(1));
        expect(backups.existsSync(), isFalse);
      }
      await tester.tap(find.byKey(const ValueKey('rpcs3-rap-close')));
      await tester.pumpAndSettle();
      expect(libraryReloads, 0);
      expect(calls.where((call) => !call.startsWith('documents/')), isEmpty);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }

  testWidgets('controller: A keeps the installed licence, then closes', (
    tester,
  ) async {
    await tester.runAsync(() async {
      final file = File(p.join(exdata(), '$_id.rap'));
      await file.parent.create(recursive: true);
      await file.writeAsBytes(_rap(1));
    });
    await openLibrary(tester);
    selection = [
      await tester.runAsync(() => pick('$_id.rap', _rap(2))) as String,
    ];
    await chooseRapImport(tester, 'Import RAP licenses');
    await settle(
      tester,
      () => shown(find.byKey(const ValueKey('rpcs3-rap-replace-dialog'))),
    );

    // The safe choice has the focus; A activates it.
    Key? focusedButton() {
      Key? key;
      FocusManager.instance.primaryFocus?.context?.visitAncestorElements((
        element,
      ) {
        if (element.widget is! ButtonStyleButton) return true;
        key = element.widget.key;
        return false;
      });
      return key;
    }

    LibraryFocusGamepadLayerState layer() =>
        tester.state<LibraryFocusGamepadLayerState>(
          find.byType(LibraryFocusGamepadLayer),
        );
    expect(focusedButton(), const ValueKey('rpcs3-rap-keep'));
    layer().activateFocused();
    await tester.pump();
    await settle(
      tester,
      () => shown(find.byKey(const ValueKey('rpcs3-rap-report'))),
    );
    expect(find.text('Rejected: 1'), findsOneWidget);
    final installed = await tester.runAsync(
      () => File(p.join(exdata(), '$_id.rap')).readAsBytes(),
    );
    expect(installed, _rap(1));

    expect(focusedButton(), const ValueKey('rpcs3-rap-close'));
    layer().activateFocused();
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('rpcs3-rap-report')), findsNothing);
    expect(libraryReloads, 0);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('embedded library in French: no root overlay over the report', (
    tester,
  ) async {
    await openLibrary(tester, locale: const Locale('fr'), embedded: true);
    selection = [
      await tester.runAsync(() => pick('$_id (1).rap', _rap(3))) as String,
    ];
    await chooseRapImport(tester, 'Importer des licences RAP');
    expect(
      find.byKey(const ValueKey('rpcs3-import-progress-overlay')),
      findsNothing,
    );
    await settle(
      tester,
      () => shown(find.byKey(const ValueKey('rpcs3-rap-report'))),
    );
    expect(find.text('Licences RAP'), findsOneWidget);
    expect(find.text('Importées : 1'), findsOneWidget);
    expect(find.text('Importée'), findsOneWidget);
    expect(find.text('Installée sous le nom $_id.rap'), findsOneWidget);
    expect(find.text('Fermer'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('rpcs3-import-progress-overlay')),
      findsNothing,
    );
    await tester.tap(find.text('Fermer'));
    await tester.pumpAndSettle();
    expect(libraryReloads, 0);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('a cancelled picker shows nothing and frees the menu', (
    tester,
  ) async {
    await openLibrary(tester);
    await chooseRapImport(tester, 'Import RAP licenses');
    await settle(
      tester,
      () => calls.contains('documents/releaseScopedResources'),
    );
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.byType(SnackBar), findsNothing);
    expect(
      tester
          .widget<PopupMenuButton<String>>(
            find.byKey(const ValueKey('rpcs3-internal-import-menu')),
          )
          .enabled,
      isTrue,
    );
    expect(libraryReloads, 0);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
