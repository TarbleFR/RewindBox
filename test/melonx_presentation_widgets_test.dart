import 'dart:async';
import 'dart:io';
import 'package:file_picker/file_picker.dart';
// ignore: implementation_imports
import 'package:file_picker/src/platform/file_picker_platform_interface.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:logger/logger.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:provider/provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/services/melonx_internal_service.dart';
import 'package:neostation/widgets/melonx_internal_playlist_actions.dart';
import 'database_test_helper.dart';

class _Paths extends PathProviderPlatform {
  _Paths(this.root);
  final String root;
  @override Future<String?> getApplicationDocumentsPath() async => root;
}
class _Picker extends FilePickerPlatform {
  _Picker(this.file);
  final File file;
  @override
  Future<FilePickerResult?> pickFiles({String? dialogTitle, String? initialDirectory,
    FileType type=FileType.any, List<String>? allowedExtensions,
    Function(FilePickerStatus)? onFileLoading, int compressionQuality=0,
    bool allowMultiple=false, bool withData=false, bool withReadStream=false,
    bool lockParentWindow=false, bool readSequential=false,
    bool cancelUploadOnWindowBlur=true, AndroidSAFOptions? androidSafOptions}) async =>
      FilePickerResult([PlatformFile(name:'prod.keys',path:file.path,size:await file.length())]);
}
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('import completes when playlist refresh disposes its menu', (tester) async {
    debugDefaultTargetPlatformOverride=TargetPlatform.iOS;
    addTearDown(() => debugDefaultTargetPlatformOverride=null);
    final database=DatabaseTestHelper();
    await database.setUp();addTearDown(database.tearDown);
    final temp=Directory.systemTemp.createTempSync('melonx-presentation-widget-');
    addTearDown(() => temp.delete(recursive:true));
    final previousPaths=PathProviderPlatform.instance;
    PathProviderPlatform.instance=_Paths(temp.path);
    addTearDown(() => PathProviderPlatform.instance=previousPaths);
    final source=File('${temp.path}/prod.keys')..writeAsStringSync('header_key = ${'a'*64}');
    final previousPicker=FilePickerPlatform.instance;
    FilePickerPlatform.instance=_Picker(source);
    addTearDown(() => FilePickerPlatform.instance=previousPicker);
    final messenger=TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(MelonxInternalService.channel,(call) async {
      if(call.method=='beginLibraryMutation') return true;
      if(call.method=='endLibraryMutation') return null;
      return {'success':true,'recognizedKeys':1};
    });
    addTearDown(() => messenger.setMockMethodCallHandler(MelonxInternalService.channel,null));
    final warnings=<String>[];
    void listener(LogEvent event) { warnings.add(event.message.toString()); }
    Logger.addLogListener(listener);addTearDown(() => Logger.removeLogListener(listener));
    final config=SqliteConfigProvider();addTearDown(config.dispose);
    final visible=ValueNotifier(true);addTearDown(visible.dispose);
    final resumed=Completer<void>();var refreshed=false;
    await tester.pumpWidget(ChangeNotifierProvider.value(value:config,
      child:ScreenUtilInit(designSize:const Size(1000,900),builder:(context,child) =>
        MaterialApp(home:Scaffold(body:ValueListenableBuilder<bool>(valueListenable:visible,
          builder:(context,show,child) => show ? MelonxInternalPlaylistActions(onLibraryChanged:() async {
            refreshed=true;visible.value=false;await resumed.future;
          }) : const Text('Refreshed playlist')))))));
    Future<void> until(bool Function() condition) async {
      for(var i=0;i<100 && !condition();i++) {
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds:10)));
        await tester.pump(const Duration(milliseconds:20));
      }
      expect(condition(),true);
    }
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds:30)));
    await tester.pumpAndSettle();
    tester.widget<PopupMenuButton<String>>(find.byKey(const ValueKey('melonx-import-menu'))).onSelected!('keys');
    await until(() => find.byType(AlertDialog).evaluate().isNotEmpty);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Done'));
    await until(() => refreshed);
    await tester.pumpAndSettle();
    expect(find.byType(MelonxInternalPlaylistActions),findsNothing);
    resumed.complete();
    await tester.pumpAndSettle();
    final failures=warnings.where((s) => s.startsWith('MeloNX library action failed:')).toList();
    if(const bool.fromEnvironment('EXPECT_OLD')) {
      expect(failures,hasLength(1));
      expect(failures.single,contains('Null check operator used on a null value'));
    } else { expect(failures,isEmpty); }
    expect(tester.takeException(),isNull);
    expect(File('${temp.path}/MeloNX/system/prod.keys').readAsStringSync(),source.readAsStringSync());
  });
}
