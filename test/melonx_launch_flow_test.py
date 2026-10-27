#!/usr/bin/env python3
"""Run the production Dart launch service with controlled native channel replies.

Only iOS platform identity, pairing-file I/O and native responses are doubled.
This is channel/order/error proof, never an iPhone JIT or gameplay claim.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
from rpcs3_atomic_startup_test import extract_function

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'lib/services/melonx_internal_service.dart').read_text()
source = source.replace("import 'dart:io';", "import 'dart:io' show File, Directory;")
source = source.replace("import 'pairing_file_service.dart';", '')
source = re.sub(r"import '(\w+\.dart)';", r"import 'package:neostation/services/\1';", source)
boundary = source.index('/// Nintendo Switch')
source = source[:boundary] + '''
class Platform { static const isIOS = true; }
class PairingFileService {
 static Future<bool> hasStoredPairingFile() async => true;
 static Future<Object?> importFromPicker({String? dialogTitle}) async => null;
 static Future<File> storedFile() async => File('/tmp/fixture-pairing-not-personal');
}
''' + source[boundary:]
tests = r'''
import 'dart:async';
import 'dart:io' show Directory, File;
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:neostation/l10n/melonx_launch_failure_locale.dart';
import 'package:neostation/services/melonx_launch_diagnostics.dart';
import 'service.dart';
class Paths extends PathProviderPlatform {
 final String root;Paths(this.root);
 @override Future<String?> getApplicationDocumentsPath() async=>root;
}
void main() {
 TestWidgetsFlutterBinding.ensureInitialized();
 const jit=MethodChannel('neostation/melonx_jit');
 const route=MethodChannel('neostation/stikjit');
 final messenger=TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
 final calls=<String>[];
 late Directory root;late File game;
 Map<String,dynamic> access={},launch={},jitReply={};
 Map<Object?,Object?> launchArguments={};
 bool arena=false;
 Future<Object?> native(MethodCall call) async {
  calls.add(call.method);
  switch(call.method) {
   case 'memoryEntitlements':return access;
   case 'diagnostics':return {'available':true,'jitArenaReady':arena};
   case 'configureLaunchJournal':return {'success':true};
   case 'launch':launchArguments=Map.of(call.arguments as Map);return launch;
   case 'cancelJit':return true;
  }
  throw StateError('Unexpected native method '+call.method);
 }
 setUp(()async {
  calls.clear();launchArguments={};arena=false;MelonxInternalService.nativeQuarantined=false;
  SharedPreferences.setMockInitialValues({});
  root=await Directory.systemTemp.createTemp('melonx-launch-channel-');
  PathProviderPlatform.instance=Paths(root.path);
  game=await File('${root.path}/Été.nro').writeAsBytes([1,2,3,4]);
  access={'checked':true,'allowed':true,'increasedMemoryLimit':true,'extendedRequired':false,'extendedVirtualAddressing':false};
  launch={'success':true,'firstMetalFramePresented':true,'jitMappingConfirmed':true};
  jitReply={'success':true,'helperConnected':true,'pidAttached':true,'debugged':true};
  messenger.setMockMethodCallHandler(MelonxInternalService.channel,native);
  messenger.setMockMethodCallHandler(jit,(call)async {calls.add(call.method);return call.method=='status'?{'debugged':true}:jitReply;});
  messenger.setMockMethodCallHandler(route,(call)async {calls.add(call.method);return {'reachable':true,'host':'10.7.0.1','port':49152};});
 });
 tearDown(()async{await root.delete(recursive:true);});
 test('missing signed entitlement refuses before runtime, keys or JIT',()async{
  access={...access,'allowed':false,'increasedMemoryLimit':false};
  final result=await MelonxInternalService.launch(gamePath:game.path,locale:'fr');
  expect(result['error'],'memoryEntitlements');expect(calls,['memoryEntitlements']);
 });
 test('the sole native preflight preserves key failure details',()async{
  launch={'success':false,'error':'missingKey','errorCode':'missingKey','stage':'contentPreflight','diagnostic':'Key Name: key_area_key_application_16','nativeStatus':-17};
  final result=await MelonxInternalService.launch(gamePath:game.path,locale:'fr');
  expect(result['error'],'missingKey');expect(result['nativeStatus'],-17);
  expect(MelonxLaunchDiagnostics.details(result),contains('key_area_key_application_16'));
  expect(calls,['memoryEntitlements','diagnostics','configureLaunchJournal','probeLocalDevVpnRoute','prepareJit','launch','cancelJit']);
 });
 // Contract replaced: the StikDebug fallback is removed. Its external path ran
 // the pre-iOS 26 RX/RW probe, which iOS 26 kills. A value stored by an older
 // build must not route around the integrated helper.
 test('a stale StikDebug fallback value is ignored and launch needs both native proofs',()async{
  SharedPreferences.setMockInitialValues({'ios_stikdebug_fallback_v1':true});
  final first=await MelonxInternalService.launch(gamePath:game.path,locale:'fr');
  expect(first['success'],true);
  expect(calls,['memoryEntitlements','diagnostics','configureLaunchJournal','probeLocalDevVpnRoute','prepareJit','launch']);
  expect(launchArguments['jitBackend'],'builtin');
  launch={'success':true};
  expect((await MelonxInternalService.launch(gamePath:game.path,locale:'fr'))['success'],false);
  expect(launchArguments['jitBackend'],'builtin');
 });
 test('helper refusal is explicit, cancelled once and retryable',()async{
  jitReply={'success':false,'helperConnected':true,'pidAttached':false,'message':'PID attach rejected'};
  var result=await MelonxInternalService.launch(gamePath:game.path,locale:'fr');
  expect(result['error'],'jitUnavailable');expect(result['diagnostic'],'PID attach rejected');
  expect(calls.where((s)=>s=='cancelJit').length,1);expect(calls, isNot(contains('launch')));
  jitReply={'success':true,'helperConnected':true,'pidAttached':true,'debugged':true};
  result=await MelonxInternalService.launch(gamePath:game.path,locale:'fr');expect(result['success'],true);
 });
 test('native failure preserves status and permits a second attempt',()async{
  launch={'success':false,'error':'ncaDecryption','stage':'content','nativeStatus':3,'diagnostic':'Unable to decrypt NCA section.'};
  final result=await MelonxInternalService.launch(gamePath:game.path,locale:'fr');
  expect(result['nativeStatus'],3);expect(result['stage'],'content');
  launch={'success':true,'firstMetalFramePresented':true,'jitMappingConfirmed':true};
  expect((await MelonxInternalService.launch(gamePath:game.path,locale:'fr'))['success'],true);
 });
 test('launch gate rejects a second request during the native launch',()async{
  final pending=Completer<Object?>();
  messenger.setMockMethodCallHandler(MelonxInternalService.channel,(call)async=>call.method=='launch'?pending.future:native(call));
  final first=MelonxInternalService.launch(gamePath:game.path,locale:'fr');
  await Future<void>.delayed(Duration.zero);
  expect((await MelonxInternalService.launch(gamePath:game.path,locale:'fr'))['error'],'busy');
  pending.complete({'success':true,'firstMetalFramePresented':true,'jitMappingConfirmed':true});expect((await first)['success'],true);
 });
 test('native preflight refusal cancels the prepared helper once and allows retry',()async{
  launch={'success':false,'error':'firmwareMissing','stage':'firmware','nativeStatus':-3};
  expect((await MelonxInternalService.launch(gamePath:game.path,locale:'fr'))['error'],'firmwareMissing');
  expect(calls.where((s)=>s=='cancelJit').length,1);expect(calls,isNot(contains('launchPreflight')));
  launch={'success':true,'firstMetalFramePresented':true,'jitMappingConfirmed':true};
  expect((await MelonxInternalService.launch(gamePath:game.path,locale:'fr'))['success'],true);
 });
 test('journal configuration failure cannot block a launch',()async{
  messenger.setMockMethodCallHandler(MelonxInternalService.channel,(call)async {
   if(call.method=='configureLaunchJournal')throw PlatformException(code:'journalUnavailable');
   return native(call);
  });
  expect((await MelonxInternalService.launch(gamePath:game.path,locale:'fr'))['success'],true);
 });
 test('quarantined native state cannot be relaunched or edited',()async{
  launch={'success':false,'error':'nativeFailure','sessionActive':true,'requiresRestart':true};
  await MelonxInternalService.launch(gamePath:game.path,locale:'fr');calls.clear();
  expect((await MelonxInternalService.launch(gamePath:game.path,locale:'fr'))['requiresRestart'],true);expect(calls,isEmpty);
 });
 test('all eight errors have twelve translations and Traditional Chinese',(){
  expect(MelonxLaunchFailureLocale.values.length,12);
  final keys=MelonxLaunchFailureLocale.values['en']!.keys.toSet();expect(keys.length,8);
  for(final entry in MelonxLaunchFailureLocale.values.entries){expect(entry.value.keys.toSet(),keys);expect(entry.value.values.every((s)=>s.isNotEmpty),true);}
  expect(MelonxLaunchFailureLocale.text(const Locale('zh','TW'),'missingKey'),MelonxLaunchFailureLocale.values['zh_Hant']!['missingKey']);
  final secret=List.filled(64,'a').join();
  expect(MelonxLaunchDiagnostics.details({'stage':'content','diagnostic':'header_key = '+secret}),isNot(contains(secret)));
 });
 test('a Switch refusal before the native service is logged and finalized without a false session',()async{
  final result=await LaunchDispatch.launchGame(AliveContext(),SystemModel(),GameModel());
  expect(result.errorDetails,'engine disabled');expect(GameLaunchManager().refused,true);
  expect(FrontendMediaGate.instance.owners,0);expect(GameSessionManager.pending,false);
 });
}
'''
dispatch = extract_function((ROOT / 'lib/services/game/game_launch_service.dart').read_text(), 'static Future<GameLaunchResult> launchGame(')
declarations = r'''
class AliveContext extends Fake implements BuildContext {@override bool get mounted=>true;}
class SystemModel {String folderName='switch';}
class GameModel {String romPath='/local/game.nro';}
class GameLaunchResult {final bool success;final String? errorMessage,errorDetails;GameLaunchResult.failure(this.errorMessage,[this.errorDetails]):success=false;}
class GameLaunchManager {static final instance=GameLaunchManager._();factory GameLaunchManager()=>instance;GameLaunchManager._();bool refused=false;void markInitializationFailed({required bool nativeStillActive}){refused=true;}}
class FrontendMediaGate {static final instance=FrontendMediaGate();int owners=0;Future<void> hold(Object o)async{owners++;}Future<void> get quiet async{}void release(Object o){owners--;}}
class GameSessionManager {static bool pending=false;static void beginLaunchPending(){pending=true;}static void clearLaunchPending(){pending=false;}}
class LaunchDispatch {
 static Future<GameLaunchResult> _launchGameImpl(BuildContext c,SystemModel s,GameModel g)async=>GameLaunchResult.failure('disabled','engine disabled');
''' + dispatch + '\n}\n'
tests = tests.replace('void main() {', declarations + '\nvoid main() {', 1)
with tempfile.TemporaryDirectory(prefix='.melonx-launch-', dir=ROOT) as temporary:
    work = Path(temporary)
    (work / 'service.dart').write_text(source)
    (work / 'launch_test.dart').write_text(tests)
    subprocess.run(['flutter', 'test', '--no-pub', '--concurrency=1', '--reporter', 'expanded', str(work / 'launch_test.dart')], cwd=ROOT, check=True, timeout=240)
