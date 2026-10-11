import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/services/global_notification_service.dart';
import 'package:neostation/widgets/notification_bell.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('en', AppLocale.en)],
      initLanguageCode: 'en',
    );
  });

  tearDown(() => GlobalNotificationService().dismiss());

  Future<void> pumpBell(WidgetTester tester) async {
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(size: Size(1920, 1080)),
        child: ScreenUtilInit(
          designSize: const Size(1920, 1080),
          builder: (context, child) => MaterialApp(
            localizationsDelegates:
                FlutterLocalization.instance.localizationsDelegates,
            supportedLocales: FlutterLocalization.instance.supportedLocales,
            home: const Scaffold(body: Center(child: NotificationBell())),
          ),
        ),
      ),
    );
  }

  double bellOpacity(WidgetTester tester) => tester
      .widget<Opacity>(
        find
            .ancestor(of: find.byType(Icon), matching: find.byType(Opacity))
            .first,
      )
      .opacity;

  testWidgets('without notifications the bell schedules no frame', (
    tester,
  ) async {
    GlobalNotificationService().dismiss();
    await pumpBell(tester);
    // Before Build 438 the pulse repeated forever and this timed out.
    await tester.pumpAndSettle();
    expect(tester.hasRunningAnimations, isFalse);
    expect(tester.binding.hasScheduledFrame, isFalse);
    expect(bellOpacity(tester), 1.0);
  });

  testWidgets('the pulse runs only while a notification exists', (
    tester,
  ) async {
    GlobalNotificationService().dismiss();
    await pumpBell(tester);
    await tester.pumpAndSettle();

    GlobalNotificationService().show(id: 'scan', message: 'Scanning…');
    await tester.pump();
    expect(tester.hasRunningAnimations, isTrue);
    await tester.pump(const Duration(milliseconds: 600));
    expect(bellOpacity(tester), lessThan(1.0));

    GlobalNotificationService().dismiss('scan');
    await tester.pump();
    expect(bellOpacity(tester), 1.0);
    await tester.pumpAndSettle();
    expect(tester.hasRunningAnimations, isFalse);
    expect(tester.binding.hasScheduledFrame, isFalse);

    // A new notification starts it again.
    GlobalNotificationService().show(id: 'sync', message: 'Syncing…');
    await tester.pump();
    expect(tester.hasRunningAnimations, isTrue);
    GlobalNotificationService().dismiss();
    await tester.pumpAndSettle();
    expect(tester.hasRunningAnimations, isFalse);
  });

  testWidgets('a bell mounted while a notification exists pulses at once', (
    tester,
  ) async {
    GlobalNotificationService().show(id: 'boot', message: 'Updating…');
    await pumpBell(tester);
    await tester.pump();
    expect(tester.hasRunningAnimations, isTrue);
    GlobalNotificationService().dismiss();
    await tester.pumpAndSettle();
    expect(tester.hasRunningAnimations, isFalse);

    // Disposing the bell detaches its listener: no error on later changes.
    await tester.pumpWidget(const SizedBox.shrink());
    GlobalNotificationService().show(id: 'late', message: 'Later');
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
