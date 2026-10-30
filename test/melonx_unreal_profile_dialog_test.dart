import 'dart:io';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:neostation/services/melonx_internal_service.dart';
import 'package:neostation/services/melonx_unreal_profiles.dart';
import 'package:neostation/widgets/melonx_unreal_profile_dialog.dart';

class _Documents extends PathProviderPlatform {
  _Documents(this.path);
  final String path;
  @override
  Future<String?> getApplicationDocumentsPath() async => path;
}
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory documents;
  late PathProviderPlatform previous;
  var inspections = 0, leases = 0;
  late Completer<void> mutationComplete;
  setUp(() {
    documents = Directory.systemTemp.createTempSync('unreal-dialog-');
    previous = PathProviderPlatform.instance;PathProviderPlatform.instance = _Documents(documents.path);
    inspections=leases=0;
    mutationComplete=Completer<void>();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(MelonxInternalService.channel, (call) async {
      if (call.method == 'inspectUnreal') { inspections++;return {'success':true,'available':true,'titleId':MelonxUnrealProfiles.titleId,'project':'Phoenix','baseConfiguration':'','configurationPath':'Phoenix/Config/UserEngine.ini',
        'modRoots':['${documents.path}/MeloNX/mods/contents/${MelonxUnrealProfiles.titleId}']}; }
      if (call.method == 'beginLibraryMutation') { leases++;return true; }
      if (call.method == 'endLibraryMutation') { leases--;mutationComplete.complete();return null; }
      throw StateError(call.method);
    });
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(MelonxInternalService.channel,null);
    PathProviderPlatform.instance=previous;documents.deleteSync(recursive:true);
  });
  Future<void> waitFor(WidgetTester tester, bool Function() ready) async {
    for (var i=0; i<500; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds:10)));
      await tester.pump();
      if (ready()) return;
    }
    throw StateError('Real filesystem operation did not finish');
  }
  Future<void> show(WidgetTester tester) async {
    await tester.pumpWidget(MaterialApp(home:Scaffold(body:Builder(builder:(context) => TextButton(
      onPressed:() => showDialog<void>(context:context,builder:(_) => const MelonxUnrealProfileDialog(gamePath:'/local/Hogwarts.xci')),
      child:const Text('Open'),
    )))));
    await tester.tap(find.text('Open'));
    // Real filesystem futures need the real event loop; fake-clock animation
    // settling cannot complete them while an indeterminate spinner is active.
    await waitFor(tester, () => find.byType(DropdownButtonFormField<String>).evaluate().isNotEmpty);
    await tester.pumpAndSettle();
  }
  testWidgets('inspection starts with no profile and never writes a mod', (tester) async {
    await show(tester);
    expect(find.text('No experimental profile'),findsOneWidget);
    expect(find.byType(CheckboxListTile),findsNothing);
    expect(Directory('${documents.path}/MeloNX/mods').existsSync(),isFalse);
    expect(inspections,1);expect(leases,0);
  });
  testWidgets('quality experiment needs explicit consent and uses a fresh gated inspection', (tester) async {
    await show(tester);
    await tester.tap(find.byType(DropdownButtonFormField<String>));await tester.pumpAndSettle();
    await tester.tap(find.text('r.MotionBlurQuality=0').last);await tester.pumpAndSettle();
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,isNull);
    await tester.ensureVisible(find.byType(CheckboxListTile));
    await tester.tap(find.byType(CheckboxListTile));await tester.pump();
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,isNotNull);
    await tester.ensureVisible(find.text('Apply'));
    await tester.tap(find.text('Apply'));
    await waitFor(tester, () => mutationComplete.isCompleted);
    await tester.pumpAndSettle();
    final ini=File('${documents.path}/MeloNX/mods/contents/${MelonxUnrealProfiles.titleId}/${MelonxUnrealProfiles.folder}/romfs/Phoenix/Config/UserEngine.ini');
    expect(ini.readAsStringSync(),contains('r.MotionBlurQuality=0'));
    expect(inspections,2);expect(leases,0);
  });
}
