import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/widgets/library_folder_report_dialog.dart';

/// The result of an import that refused more files than a notice can name
/// is shown whole, until the user closes it: one button, every line.
void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues(const <String, Object>{});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('xyz.luan/gamepads'),
      (call) async => <dynamic>[],
    );
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('en', AppLocale.en)],
      initLanguageCode: 'en',
    );
  });

  /// A localized, ScreenUtil-initialized host (the same as the confirm
  /// dialog's test) that hands back a context under the navigator.
  Future<BuildContext> pumpHost(WidgetTester tester) async {
    late BuildContext ctx;
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(size: Size(1920, 1080)),
        child: ScreenUtilInit(
          designSize: const Size(1920, 1080),
          builder: (context, child) => MaterialApp(
            localizationsDelegates: FlutterLocalization.instance.localizationsDelegates,
            supportedLocales: FlutterLocalization.instance.supportedLocales,
            home: Builder(
              builder: (context) {
                ctx = context;
                return const Scaffold(body: SizedBox.shrink());
              },
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return ctx;
  }

  Future<void> open(WidgetTester tester, List<LibraryReportLine> lines) async {
    final context = await pumpHost(tester);
    unawaited(
      LibraryFolderReportDialog.showLines(context, title: 'Import games', lines: lines, closeLabel: 'OK'),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('every refused file is listed and one button closes', (tester) async {
    final lines = <LibraryReportLine>[
      const LibraryReportLine(LibraryReportLineKind.heading, '8 file(s) not imported:'),
      for (var i = 1; i <= 8; i++) LibraryReportLine(LibraryReportLineKind.warning, 'file$i.bin — wrong type'),
    ];
    await open(tester, lines);

    expect(find.text('Import games'), findsOneWidget);
    for (var i = 1; i <= 8; i++) {
      expect(find.text('file$i.bin — wrong type'), findsOneWidget);
    }
    expect(find.byKey(const ValueKey('library-folder-report-cancel')), findsNothing);
    expect(find.byKey(const ValueKey('library-folder-report-confirm')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('library-folder-report-confirm')));
    await tester.pumpAndSettle();
    expect(find.text('Import games'), findsNothing);
  });
}
