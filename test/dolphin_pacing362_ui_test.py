from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
origin=ROOT/'test/dolphin_account_267_test.py'
source=origin.read_text().replace("'CLANG_ENABLE_OBJC_ARC': 'YES',", "'CLANG_ENABLE_OBJC_ARC': 'YES', 'CLANG_CXX_LANGUAGE_STANDARD': 'c++20',")
source=source.replace("{'sdk': 'UIKit.framework'}", "{'sdk': 'UniformTypeIdentifiers.framework'}, {'sdk': 'UIKit.framework'}")
ns={'__file__':str(origin),'__name__':'pacing_tests'}
exec(compile(source,str(origin),'exec'),ns)
ns['TESTS']=r'''
#import <XCTest/XCTest.h>
#import "DolphinFramePacing.h"
#import "DolphinSessionMenu.h"
#import "DolphinPhoneShakeLabels.h"
#import "DOLShaderLabels.h"
@interface DolphinSessionMenu (ShaderTestAccess)
- (DolphinSessionMenu*)child:(NSInteger)page title:(NSString*)title;
@end
@interface DolphinFramePacing (TestAccess)
- (void)tick:(CADisplayLink*)link;
@end
@interface FakeTick:NSObject
@property double timestamp;
@property double targetTimestamp;
@end
@implementation FakeTick @end
@interface FramePacing362Tests:XCTestCase @end
@implementation FramePacing362Tests
- (void)setUp {
 for(NSString* key in @[@"Profile",@"Refresh",@"Trace"])
  [NSUserDefaults.standardUserDefaults removeObjectForKey:[@"NeoStation.Dolphin.DisplayTrial." stringByAppendingString:key]];
 [NSUserDefaults.standardUserDefaults removeObjectForKey:@"NeoStation.Dolphin.ExternalDisplay.Mode"];
}
- (void)testRefreshRequestsRespectHardwarePowerAndHeat {
 XCTAssertEqual(DOLRequestedRefresh(120,120,NO,0),120);
 XCTAssertEqual(DOLRequestedRefresh(120,60,NO,0),60);
 XCTAssertEqual(DOLRequestedRefresh(120,120,YES,0),60);
 XCTAssertEqual(DOLRequestedRefresh(120,120,NO,2),60);
 XCTAssertEqual(DOLRequestedRefresh(120,120,NO,3),60);
 XCTAssertEqual(DOLRequestedRefresh(60,120,NO,0),60);
 XCTAssertEqual(DOLRequestedRefresh(0,120,NO,0),0);
 XCTAssertEqual(DOLRequestedRefresh(120,0,NO,0),0);
}
- (void)testTraceIsBoundedAndDisplayCallbackMeasurementIsNotGameFPS {
 DolphinFramePacing* tracker=[DolphinFramePacing new];UIView* view=[UIView new];[tracker startWithView:view];
 FakeTick* tick=[FakeTick new];
 for(int i=0;i<241;i++){tick.timestamp=10+i/120.0;tick.targetTimestamp=tick.timestamp+1/120.0;[tracker tick:(id)tick];}
 XCTAssertEqualWithAccuracy([tracker.summary[@"displayLinkCallbackHz"] doubleValue],120,0.5);
 for(int i=0;i<600;i++)[tracker appendPerformance:@{@"fps":@60,@"vps":@60,@"frameTimeMs":@16.67} inputMs:0 refreshed:NO];
 XCTAssertEqual(tracker.samples.count,240);XCTAssertEqualObjects(tracker.samples.lastObject[@"fps"],@60);
 XCTAssertTrue([tracker.summary[@"measurementNote"] containsString:@"not panel"]);
 [tracker stop];[tracker appendPerformance:@{@"fps":@60} inputMs:0 refreshed:NO];XCTAssertEqual(tracker.samples.count,240);
}
- (void)testStopInvalidatesActualDisplayLinkAndNoRetainCycle {
 UIWindow* window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
 UIViewController* root=[UIViewController new];window.rootViewController=root;[window makeKeyAndVisible];
 __weak DolphinFramePacing* weak=nil;
 @autoreleasepool {
  DolphinFramePacing* tracker=[DolphinFramePacing new];weak=tracker;[tracker startWithView:root.view];
  XCTAssertNotNil([tracker valueForKey:@"displayLink"]);
  [tracker stop];XCTAssertNil([tracker valueForKey:@"displayLink"]);
 }
 XCTAssertNil(weak);window.hidden=YES;
}
- (void)testNativeSettingsAndTwelveLanguages {
 DolphinFramePacing* tracker=[DolphinFramePacing new];tracker.locale=@"fr";
 UITableViewController* page=(id)[tracker settingsController];[page loadViewIfNeeded];
 XCTAssertEqual([page.tableView.dataSource tableView:page.tableView numberOfRowsInSection:0],6);
 XCTAssertEqualObjects(page.title,@"Affichage et fluidité");XCTAssertEqual(DOLFrameProfile(),2);
 for(NSString* lang in @[@"en",@"fr",@"de",@"es",@"it",@"pt",@"ru",@"id",@"ja",@"ko",@"zh",@"zh_Hant"])
  for(NSString* key in @[@"title",@"hzHelp",@"profileHelp",@"export"])
   XCTAssertNotEqualObjects(DOLPacingText(key,lang),key);
}
- (void)testRemovedRestoreActionCannotResetPreferencesInAnyLocale {
 NSUserDefaults* settings=NSUserDefaults.standardUserDefaults;
 [settings setInteger:1 forKey:@"NeoStation.Dolphin.DisplayTrial.Profile"];
 [settings setInteger:120 forKey:@"NeoStation.Dolphin.DisplayTrial.Refresh"];
 [settings setBool:YES forKey:@"NeoStation.Dolphin.DisplayTrial.Trace"];
 for(NSString* lang in @[@"en",@"fr",@"de",@"es",@"it",@"pt",@"ru",@"id",@"ja",@"ko",@"zh",@"zh_Hant"]) {
  DolphinFramePacing* tracker=[DolphinFramePacing new];tracker.locale=lang;
  UITableViewController* page=(id)[tracker settingsController];[page loadViewIfNeeded];
  XCTAssertEqual([page.tableView.dataSource tableView:page.tableView numberOfRowsInSection:0],6);
  for(NSInteger i=0;i<6;i++) {
   UITableViewCell* cell=[page.tableView.dataSource tableView:page.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:i inSection:0]];
   XCTAssertFalse([cell.textLabel.text containsString:@"361"]);
  }
  XCTAssertEqualObjects(DOLPacingText(@"restore",lang),@"restore");
  // Even a stale selection delivered to the old row must do nothing.
  [page.tableView.delegate tableView:page.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:6 inSection:0]];
  XCTAssertNil(page.presentedViewController);
  XCTAssertEqual(DOLFrameProfile(),1);
  XCTAssertEqual([settings integerForKey:@"NeoStation.Dolphin.DisplayTrial.Refresh"],120);
  XCTAssertTrue([settings boolForKey:@"NeoStation.Dolphin.DisplayTrial.Trace"]);
 }
}
- (void)testGraphicsMenuOpensDisplayPanelWithoutChangingTheEmulator {
 DolphinSessionMenu* menu=[DolphinSessionMenu new];menu.labels=@{@"__locale":@"fr"};
 [menu setValue:@1 forKey:@"page"];[menu setValue:@{} forKey:@"snapshot"];__block BOOL opened=NO;
 menu.openDisplaySettings=^{opened=YES;};[menu loadViewIfNeeded];
 NSIndexPath* row=[NSIndexPath indexPathForRow:4 inSection:0];
 XCTAssertEqual([menu tableView:menu.tableView numberOfRowsInSection:0],5);
 XCTAssertEqualObjects([menu tableView:menu.tableView cellForRowAtIndexPath:row].textLabel.text,@"Affichage et fluidité");
 [menu tableView:menu.tableView didSelectRowAtIndexPath:row];XCTAssertTrue(opened);
}

- (void)testDirectShaderAccessOnGameCubeAndWiiPreservesDisplayAndTextureNavigation {
 for(NSNumber* wii in @[@NO,@YES])
  for(NSString* locale in @[@"en",@"fr",@"de",@"es",@"it",@"pt",@"ru",@"id",@"ja",@"ko",@"zh",@"zh_Hant"]) {
   DolphinSessionMenu* root=[DolphinSessionMenu new];root.wii=wii.boolValue;
   root.labels=@{@"__locale":locale};[root setValue:@{} forKey:@"snapshot"];
   __block NSUInteger display=0,shader=0,textures=0,coreWrites=0;
   root.openDisplaySettings=^{++display;};root.openShaderSettings=^{++shader;};root.openTextureSettings=^{++textures;};
   root.applySettings=^(NSDictionary* request,void(^done)(BOOL)){++coreWrites;done(YES);};
   // The graphics child created by the real menu must retain every shortcut.
   DolphinSessionMenu* menu=[root child:1 title:@"Graphics"];[menu loadViewIfNeeded];
   XCTAssertEqual(menu.wii,wii.boolValue);
   XCTAssertEqual([menu tableView:menu.tableView numberOfRowsInSection:0],7);
   NSIndexPath* effect=[NSIndexPath indexPathForRow:5 inSection:0];
   UITableViewCell* cell=[menu tableView:menu.tableView cellForRowAtIndexPath:effect];
   XCTAssertEqualObjects(cell.textLabel.text,DOLShaderText(@"title",locale));
   XCTAssertEqualObjects(cell.detailTextLabel.text,DOLShaderText(@"nextLaunch",locale));
   XCTAssertEqualObjects(cell.accessibilityIdentifier,@"dolphinPostProcessingFromMenu");
   [menu tableView:menu.tableView didSelectRowAtIndexPath:effect];XCTAssertEqual(shader,1U);
   [menu tableView:menu.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:4 inSection:0]];
   XCTAssertEqual(display,1U);
   [menu tableView:menu.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:6 inSection:0]];
   XCTAssertEqual(textures,1U);XCTAssertEqual(coreWrites,0U);
   // No Display callback: the same shader row moves to index four.
   menu.openDisplaySettings=nil;
   XCTAssertEqual([menu tableView:menu.tableView numberOfRowsInSection:0],6);
   cell=[menu tableView:menu.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:4 inSection:0]];
   XCTAssertEqualObjects(cell.accessibilityIdentifier,@"dolphinPostProcessingFromMenu");
   [menu tableView:menu.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:4 inSection:0]];
   XCTAssertEqual(shader,2U);XCTAssertEqual(coreWrites,0U);
  }
}

- (void)testWiiPhoneShakeOptionIsLocalizedPersistentAndDoesNotApplyCoreSettings {
 NSString* key=@"NeoStation.Dolphin.PhoneShake.Enabled";
 [NSUserDefaults.standardUserDefaults removeObjectForKey:key];
 DolphinSessionMenu* menu=[DolphinSessionMenu new];menu.wii=YES;
 menu.labels=@{@"__locale":@"fr"};[menu setValue:@5 forKey:@"page"];
 [menu setValue:@{@"controls":@[]} forKey:@"snapshot"];
 __block NSUInteger writes=0;
 menu.applySettings=^(NSDictionary* request,void(^done)(BOOL)){++writes;done(YES);};
 [menu loadViewIfNeeded];
 XCTAssertEqual([menu tableView:menu.tableView numberOfRowsInSection:0],6);
 NSIndexPath* row=[NSIndexPath indexPathForRow:4 inSection:0];
 UITableViewCell* cell=[menu tableView:menu.tableView cellForRowAtIndexPath:row];
 XCTAssertEqualObjects(cell.textLabel.text,@"Secouer l’appareil — Wiimote");
 XCTAssertEqual(cell.accessoryType,UITableViewCellAccessoryCheckmark);
 [menu tableView:menu.tableView didSelectRowAtIndexPath:row];
 XCTAssertFalse([NSUserDefaults.standardUserDefaults boolForKey:key]);
 [menu tableView:menu.tableView didSelectRowAtIndexPath:row];
 XCTAssertTrue([NSUserDefaults.standardUserDefaults boolForKey:key]);XCTAssertEqual(writes,0U);
 menu.wii=NO;XCTAssertEqual([menu tableView:menu.tableView numberOfRowsInSection:0],3);
 for(NSString* lang in @[@"en",@"fr",@"de",@"es",@"it",@"pt",@"ru",@"id",@"ja",@"ko",@"zh",@"zh_Hant"])
  for(NSString* name in @[@"title",@"help",@"usage",@"routeFailed",@"sensorUnavailable"])
   XCTAssertNotEqualObjects(DOLPhoneShakeText(name,lang),name);
 [NSUserDefaults.standardUserDefaults removeObjectForKey:key];
}
- (void)testWiiPhoneShakeFailureIsVisibleAndNotMarkedActiveInAllLocales {
 NSUserDefaults* settings=NSUserDefaults.standardUserDefaults;
 [settings setBool:YES forKey:@"NeoStation.Dolphin.PhoneShake.Enabled"];
 for(NSString* locale in @[@"en",@"fr",@"de",@"es",@"it",@"pt",@"ru",@"id",@"ja",@"ko",@"zh",@"zh_Hant"]) {
  DolphinSessionMenu* menu=[DolphinSessionMenu new];menu.wii=YES;
  menu.labels=@{@"__locale":locale};[menu setValue:@5 forKey:@"page"];
  [menu setValue:@{@"controls":@[]} forKey:@"snapshot"];[menu loadViewIfNeeded];
  for(NSNumber* status in @[@2,@3]) {
   [settings setInteger:status.integerValue forKey:@"Test.PhoneShakeRouteStatus"];
   UITableViewCell* cell=[menu tableView:menu.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:4 inSection:0]];
   XCTAssertEqualObjects(cell.detailTextLabel.text,DOLPhoneShakeText(status.integerValue==2?@"routeFailed":@"sensorUnavailable",locale));
   XCTAssertEqual(cell.accessoryType,UITableViewCellAccessoryNone);
  }
 }
 [settings removeObjectForKey:@"Test.PhoneShakeRouteStatus"];
 [settings removeObjectForKey:@"NeoStation.Dolphin.PhoneShake.Enabled"];
}
@end
'''
ns['native']()
