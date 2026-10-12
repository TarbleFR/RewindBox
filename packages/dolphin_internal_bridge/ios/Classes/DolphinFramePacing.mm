// SPDX-License-Identifier: GPL-3.0-or-later
#import "DolphinFramePacing.h"
#import "DolphinExternalDisplay.h"
#include "DolphinPacingLabels.h"
// Build 447: the external-display row reads and writes the global
// preference of the external_display pod (shared with Settings › General).
#if __has_include(<external_display/NeoExternalDisplayPreferences.h>)
#import <external_display/NeoExternalDisplayPreferences.h>
#else
#import "NeoExternalDisplayPreferences.h"
#endif
#include <mach/mach.h>
#include <sys/utsname.h>
#include <cmath>

static NSString* const DOLProfileKey=@"NeoStation.Dolphin.DisplayTrial.Profile";
static NSString* const DOLRefreshKey=@"NeoStation.Dolphin.DisplayTrial.Refresh";
static NSString* const DOLTraceKey=@"NeoStation.Dolphin.DisplayTrial.Trace";
// Build 442: a sampled frame above these durations is counted as a stutter
// sample (1.5× and 3× a 60 FPS frame). Sampling at 10 Hz catches every stall
// longer than 100 ms and a fraction of the shorter ones: an indicator, not a
// per-frame trace.
static const double DOLSlowFrameMs=25.0;
static const double DOLVerySlowFrameMs=50.0;
NSInteger DOLFrameProfile(void) {
  id v=[NSUserDefaults.standardUserDefaults objectForKey:DOLProfileKey];
  return [v isKindOfClass:NSNumber.class] && [v integerValue]>=0 && [v integerValue]<=2?[v integerValue]:2;
}
static NSInteger DOLRefreshPreference(void) {
  // Build 442 default: 60 Hz. One emulated frame per refresh; at 120 Hz each
  // frame spans two refreshes and small presentation jitter shows as stutter.
  id v=[NSUserDefaults.standardUserDefaults objectForKey:DOLRefreshKey];
  return [v isKindOfClass:NSNumber.class] && [@[@0,@60,@120] containsObject:v]?[v integerValue]:60;
}
NSInteger DOLRequestedRefresh(NSInteger requested,NSInteger maximum,BOOL lowPower,NSInteger thermal) {
  if(requested==0 || maximum<=0)return 0;
  NSInteger result=MIN(requested,maximum);
  if(lowPower || thermal>=NSProcessInfoThermalStateSerious)result=MIN(result,60);
  return MAX(1,result);
}
static double DOLMemoryFootprintMB(void) {
  task_vm_info_data_t info;
  mach_msg_type_number_t count=TASK_VM_INFO_COUNT;
  if(task_info(mach_task_self(),TASK_VM_INFO,(task_info_t)&info,&count)!=KERN_SUCCESS)return 0;
  return (double)info.phys_footprint/(1024.0*1024.0);
}
@class DOLDisplaySettings;
@interface DOLDisplayLinkTarget:NSObject
@property(nonatomic,weak) DolphinFramePacing* owner;
- (void)tick:(CADisplayLink*)link;
@end
@interface DolphinFramePacing ()
@property(nonatomic,strong,nullable) CADisplayLink* displayLink;
@property(nonatomic,weak,nullable) UIView* view;
@property(nonatomic,strong) NSMutableArray* records;
@property(nonatomic,strong) NSLock* sampleLock;
@property(nonatomic,assign) BOOL running;
@property(nonatomic,assign) double lastTimestamp;
@property(nonatomic,assign) double windowStart;
@property(nonatomic,assign) double observedHz;
@property(nonatomic,assign) double intervalHz;
@property(nonatomic,assign) double maxGapMs;
@property(nonatomic,assign) NSUInteger ticks;
@property(nonatomic,assign) NSInteger requestedHz;
@property(nonatomic,assign) NSInteger maximumHz;
// 10 Hz frame-time samples since the last trace row (sampleLock).
@property(nonatomic,assign) double intervalMaxMs;
@property(nonatomic,assign) double intervalMinMs;
@property(nonatomic,assign) NSUInteger intervalSamples;
@property(nonatomic,assign) NSUInteger intervalSlow;
@property(nonatomic,assign) NSUInteger intervalVerySlow;
// Whole session (sampleLock).
@property(nonatomic,assign) double worstFrameMs;
@property(nonatomic,assign) NSUInteger totalSamples;
@property(nonatomic,assign) NSUInteger totalSlow;
@property(nonatomic,assign) NSUInteger totalVerySlow;
- (void)tick:(CADisplayLink*)link;
@end
@interface DOLDisplaySettings:UITableViewController
@property(nonatomic,strong) DolphinFramePacing* pacing;
@end
@implementation DOLDisplayLinkTarget
- (void)tick:(CADisplayLink*)link {[self.owner tick:link];}
@end
@implementation DolphinFramePacing
- (instancetype)init {
  if((self=[super init])){_records=[NSMutableArray array];_sampleLock=[NSLock new];_locale=@"en";_gameId=@"";_intervalMinMs=INFINITY;}
  return self;
}
- (BOOL)traceEnabled {
  id value=[NSUserDefaults.standardUserDefaults objectForKey:DOLTraceKey];
  return value==nil || [value boolValue];
}
- (void)startWithView:(UIView*)view {
  NSAssert(NSThread.isMainThread,@"Display link belongs to the main run loop");
  [self stop];self.view=view;self.running=YES;
  for(NSString* name in @[UIApplicationDidBecomeActiveNotification,UIApplicationWillResignActiveNotification,
      NSProcessInfoPowerStateDidChangeNotification,NSProcessInfoThermalStateDidChangeNotification])
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(environmentChanged:) name:name object:nil];
  [self refreshPreference];
}
- (void)environmentChanged:(NSNotification*)notification {
  if(!NSThread.isMainThread){dispatch_async(dispatch_get_main_queue(),^{[self environmentChanged:notification];});return;}
  if([notification.name isEqual:UIApplicationWillResignActiveNotification]) {
    [self.displayLink invalidate];self.displayLink=nil;self.observedHz=0;self.windowStart=0;self.lastTimestamp=0;return;
  }
  [self refreshPreference];
}
- (void)refreshPreference {
  NSAssert(NSThread.isMainThread,@"Display hints are configured on main");
  UIScreen* screen=self.view.window.screen;
  self.maximumHz=screen.maximumFramesPerSecond;
  self.requestedHz=DOLRequestedRefresh(DOLRefreshPreference(),self.maximumHz,NSProcessInfo.processInfo.lowPowerModeEnabled,NSProcessInfo.processInfo.thermalState);
  if(!self.running || !screen || !self.requestedHz || UIApplication.sharedApplication.applicationState!=UIApplicationStateActive) {
    [self.displayLink invalidate];self.displayLink=nil;self.observedHz=0;return;
  }
  if(!self.displayLink) {
    DOLDisplayLinkTarget* target=[DOLDisplayLinkTarget new];target.owner=self;
    self.displayLink=[screen displayLinkWithTarget:target selector:@selector(tick:)];
    self.lastTimestamp=0;self.windowStart=0;self.ticks=0;
    [self.displayLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
  }
  // A timing hint only. Never draw, acquire a drawable or advance emulation here.
  // A fixed range keeps the panel cadence steady during touch input.
  self.displayLink.preferredFrameRateRange=CAFrameRateRangeMake(self.requestedHz,self.requestedHz,self.requestedHz);
}
- (void)tick:(CADisplayLink*)link {
  const double now=link.timestamp;
  if(self.lastTimestamp>0)self.maxGapMs=MAX(self.maxGapMs,(now-self.lastTimestamp)*1000);
  self.lastTimestamp=now;
  const double interval=link.targetTimestamp-link.timestamp;
  if(interval>0 && std::isfinite(interval))self.intervalHz=1.0/interval;
  if(!self.windowStart){self.windowStart=now;self.ticks=0;return;}
  self.ticks++;
  if(now-self.windowStart>=1) {
    self.observedHz=self.ticks/(now-self.windowStart);self.windowStart=now;self.ticks=0;
  }
}
- (void)recordFrameTimeMs:(double)lastFrameMs {
  // Any thread (the bridge samples on its runtime queue). Zero = no frame yet.
  if(!std::isfinite(lastFrameMs) || lastFrameMs<=0)return;
  [self.sampleLock lock];
  self.intervalSamples++;self.totalSamples++;
  self.intervalMaxMs=MAX(self.intervalMaxMs,lastFrameMs);
  self.intervalMinMs=MIN(self.intervalMinMs,lastFrameMs);
  self.worstFrameMs=MAX(self.worstFrameMs,lastFrameMs);
  if(lastFrameMs>=DOLSlowFrameMs){self.intervalSlow++;self.totalSlow++;}
  if(lastFrameMs>=DOLVerySlowFrameMs){self.intervalVerySlow++;self.totalVerySlow++;}
  [self.sampleLock unlock];
}
- (NSDictionary*)frameTimeSummary {
  [self.sampleLock lock];
  NSDictionary* summary=@{@"worstFrameTimeMs":@(self.worstFrameMs),@"frameSampleTotal":@(self.totalSamples),
    @"slowSampleTotal":@(self.totalSlow),@"verySlowSampleTotal":@(self.totalVerySlow),
    @"slowFrameThresholdMs":@(DOLSlowFrameMs),@"verySlowFrameThresholdMs":@(DOLVerySlowFrameMs)};
  [self.sampleLock unlock];
  return summary;
}
- (NSDictionary*)summary {
  NSMutableDictionary* summary=[@{@"requestedHz":@(self.requestedHz),@"preferenceHz":@(DOLRefreshPreference()),
    @"maximumHz":@(self.maximumHz),@"displayLinkCallbackHz":@(self.observedHz),
    @"displayLinkIntervalHz":@(self.intervalHz),@"displayLinkMaxGapMs":@(self.maxGapMs),
    @"activeProfile":@(self.activeProfile),@"nextProfile":@(DOLFrameProfile()),
    @"lowPower":@(NSProcessInfo.processInfo.lowPowerModeEnabled),@"thermalState":@(NSProcessInfo.processInfo.thermalState),
    @"traceEnabled":@(self.traceEnabled),@"gameId":self.gameId?:@"",
    @"externalDisplayMode":@(DOLExternalDisplayPreference()),@"externalDisplayActive":@(self.externalDisplayActive),
    @"externalDisplayEnabled":@(NeoExternalDisplayPreferences.enabled),@"externalDisplayGlobalMode":@((NSInteger)NeoExternalDisplayPreferences.mode),
    @"memoryFootprintMB":@(DOLMemoryFootprintMB()),
    @"measurementNote":@"CADisplayLink timing is not panel scanout or emulator FPS. Performance samples are 2Hz aggregates with 10Hz frame-time sub-samples, not a per-frame trace."} mutableCopy];
  [summary addEntriesFromDictionary:[self frameTimeSummary]];
  return summary;
}
- (NSArray*)samples {return [self.records copy];}
- (void)appendPerformance:(NSDictionary*)sample inputMs:(double)inputMs refreshed:(BOOL)refreshed {
  if(!self.traceEnabled || !self.running)return;
  NSMutableDictionary* row=[sample mutableCopy];row[@"hostSampleTime"]=@(CACurrentMediaTime());
  row[@"displayLinkHz"]=@(self.observedHz);row[@"displayLinkIntervalHz"]=@(self.intervalHz);
  row[@"inputRefreshMs"]=@(std::isfinite(inputMs)?inputMs:0);row[@"inputRefreshed"]=@(refreshed);
  row[@"thermalState"]=@(NSProcessInfo.processInfo.thermalState);row[@"requestedHz"]=@(self.requestedHz);
  row[@"memoryFootprintMB"]=@(DOLMemoryFootprintMB());row[@"externalDisplayActive"]=@(self.externalDisplayActive);
  [self.sampleLock lock];
  row[@"frameSamples"]=@(self.intervalSamples);
  row[@"frameTimeMaxMs"]=@(self.intervalSamples?self.intervalMaxMs:0);
  row[@"frameTimeMinMs"]=@(self.intervalSamples?self.intervalMinMs:0);
  row[@"slowSamples"]=@(self.intervalSlow);row[@"verySlowSamples"]=@(self.intervalVerySlow);
  self.intervalSamples=0;self.intervalMaxMs=0;self.intervalMinMs=INFINITY;self.intervalSlow=0;self.intervalVerySlow=0;
  [self.sampleLock unlock];
  if(self.records.count>=240)[self.records removeObjectAtIndex:0];
  [self.records addObject:row];
}
- (UIViewController*)settingsController {
  DOLDisplaySettings* page=[[DOLDisplaySettings alloc] initWithStyle:UITableViewStyleInsetGrouped];page.pacing=self;return page;
}
- (void)stop {
  [self.displayLink invalidate];self.displayLink=nil;self.running=NO;
  [NSNotificationCenter.defaultCenter removeObserver:self];self.view=nil;
}
- (void)dealloc {[self.displayLink invalidate];[NSNotificationCenter.defaultCenter removeObserver:self];}
@end

@implementation DOLDisplaySettings
- (NSString*)text:(NSString*)key{return DOLPacingText(key,self.pacing.locale);}
- (NSString*)profileName:(NSInteger)value{return [self text:@[@"legacy",@"metal",@"hybrid"][MAX(0,MIN(2,value))]];}
// Build 447: the global setting as shown to the player. Off is the Enabled
// switch; Automatic is a global mode of its own (Fit for a game).
- (NSString*)externalModeName {
  if(!NeoExternalDisplayPreferences.enabled)return [self text:@"externalOff"];
  switch(NeoExternalDisplayPreferences.mode) {
    case NeoExternalDisplayModeFit:return [self text:@"externalFit"];
    case NeoExternalDisplayModeFill:return [self text:@"externalFill"];
    case NeoExternalDisplayModeOriginal:return [self text:@"externalOriginal"];
    case NeoExternalDisplayModeAutomatic:break;
  }
  return [self text:@"externalAutomatic"];
}
- (void)viewDidLoad {
  [super viewDidLoad];self.overrideUserInterfaceStyle=UIUserInterfaceStyleDark;
  self.view.backgroundColor=UIColor.systemGroupedBackgroundColor;self.title=[self text:@"title"];
  self.tableView.rowHeight=UITableViewAutomaticDimension;self.tableView.estimatedRowHeight=64;
  self.navigationItem.largeTitleDisplayMode=UINavigationItemLargeTitleDisplayModeNever;
}
// Rows: refresh, profile, status, external display (Build 442), trace, export.
- (NSInteger)tableView:(UITableView*)table numberOfRowsInSection:(NSInteger)section {return 6;}
- (UITableViewCell*)tableView:(UITableView*)table cellForRowAtIndexPath:(NSIndexPath*)path {
  UITableViewCell* cell=[[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
  cell.backgroundColor=UIColor.secondarySystemGroupedBackgroundColor;cell.textLabel.textColor=UIColor.labelColor;
  cell.detailTextLabel.textColor=UIColor.secondaryLabelColor;cell.textLabel.numberOfLines=0;cell.detailTextLabel.numberOfLines=0;
  cell.textLabel.adjustsFontForContentSizeCategory=YES;cell.detailTextLabel.adjustsFontForContentSizeCategory=YES;
  cell.accessoryType=UITableViewCellAccessoryDisclosureIndicator;
  switch(path.row) {
    case 0:cell.textLabel.text=[self text:@"refresh"];
      cell.detailTextLabel.text=DOLRefreshPreference()==0?[self text:@"automatic"]:[NSString stringWithFormat:@"%ld Hz",(long)DOLRefreshPreference()];break;
    case 1:cell.textLabel.text=[self text:@"profile"];
      cell.detailTextLabel.text=[NSString stringWithFormat:@"%@\n%@: %@",[self profileName:DOLFrameProfile()],[self text:@"active"],[self profileName:self.pacing.activeProfile]];break;
    case 2:cell.textLabel.text=[self text:@"status"];
      cell.detailTextLabel.text=[NSString stringWithFormat:@"%@: %ld Hz · %@: %.1f Hz\n%@",[self text:@"request"],(long)self.pacing.requestedHz,[self text:@"callbacks"],self.pacing.observedHz,[self text:@"statusHelp"]];
      cell.accessoryType=UITableViewCellAccessoryNone;break;
    case 3:cell.textLabel.text=[self text:@"external"];
      cell.detailTextLabel.text=[NSString stringWithFormat:@"%@\n%@",[self externalModeName],
        [self text:self.pacing.externalDisplayActive?@"externalActive":@"externalNone"]];
      cell.accessibilityIdentifier=@"dolphinExternalDisplay";break;
    case 4:cell.textLabel.text=[self text:@"trace"];
      cell.detailTextLabel.text=[self text:self.pacing.traceEnabled?@"on":@"off"];break;
    case 5:cell.textLabel.text=[self text:@"export"];cell.detailTextLabel.text=[self text:@"traceHelp"];break;
  }
  return cell;
}
- (NSString*)tableView:(UITableView*)table titleForFooterInSection:(NSInteger)section {
  return [NSString stringWithFormat:@"%@\n\n%@\n\n%@\n\n%@",[self text:@"hzHelp"],[self text:@"hzDefaultHelp"],[self text:@"profileHelp"],[self text:@"externalHelp"]];
}
- (void)tableView:(UITableView*)table willDisplayFooterView:(UIView*)view forSection:(NSInteger)section {
  if([view isKindOfClass:UITableViewHeaderFooterView.class]) {
    UITableViewHeaderFooterView* footer=(id)view;footer.textLabel.textColor=UIColor.labelColor;footer.textLabel.numberOfLines=0;
  }
}
- (void)choose:(NSArray<NSNumber*>*)values names:(NSArray<NSString*>*)names key:(NSString*)key cell:(UIView*)cell {
  NSString* titleKey=[key isEqual:DOLRefreshKey]?@"refresh":@"profile";
  NSString* messageKey=[key isEqual:DOLRefreshKey]?@"hzHelp":@"restartHelp";
  UIAlertController* alert=[UIAlertController alertControllerWithTitle:[self text:titleKey]
    message:[self text:messageKey] preferredStyle:UIAlertControllerStyleActionSheet];
  for(NSUInteger i=0;i<values.count;i++) {
    NSNumber* value=values[i];
    UIAlertAction* action=[UIAlertAction actionWithTitle:names[i] style:UIAlertActionStyleDefault handler:^(UIAlertAction* a){
      [NSUserDefaults.standardUserDefaults setObject:value forKey:key];
      [self.pacing refreshPreference];
      [self.tableView reloadData];
      if([key isEqual:DOLProfileKey])self.navigationItem.prompt=[self text:@"restartHelp"];
    }];
    // A 60-Hz screen cannot be made 120 Hz. Low-power throttling does not erase the user's selection.
    if([key isEqual:DOLRefreshKey] && value.integerValue==120 && self.pacing.maximumHz<120)action.enabled=NO;
    [alert addAction:action];
  }
  [alert addAction:[UIAlertAction actionWithTitle:[self text:@"cancel"] style:UIAlertActionStyleCancel handler:nil]];
  alert.popoverPresentationController.sourceView=cell;alert.popoverPresentationController.sourceRect=cell.bounds;
  [self presentViewController:alert animated:YES completion:nil];
}
// Build 447: Off, Automatic, Fit, Fill, Original written to the global keys
// through NeoExternalDisplayPreferences, which reads each write back and
// tells the live coordinator; the Build 442 Dolphin key is never written.
- (void)chooseExternalDisplay:(UIView*)cell {
  UIAlertController* alert=[UIAlertController alertControllerWithTitle:[self text:@"external"]
    message:[self text:@"externalHelp"] preferredStyle:UIAlertControllerStyleActionSheet];
  NSArray<NSString*>* keys=@[@"externalOff",@"externalAutomatic",@"externalFit",@"externalFill",@"externalOriginal"];
  NSArray<NSNumber*>* modes=@[@(-1),@(NeoExternalDisplayModeAutomatic),@(NeoExternalDisplayModeFit),@(NeoExternalDisplayModeFill),@(NeoExternalDisplayModeOriginal)];
  for(NSUInteger i=0;i<keys.count;i++) {
    const NSInteger mode=modes[i].integerValue;
    [alert addAction:[UIAlertAction actionWithTitle:[self text:keys[i]] style:UIAlertActionStyleDefault handler:^(UIAlertAction* a){
      BOOL saved;
      if(mode<0)saved=[NeoExternalDisplayPreferences storeEnabled:NO];
      else saved=[NeoExternalDisplayPreferences storeMode:(NeoExternalDisplayMode)mode]
        && (NeoExternalDisplayPreferences.enabled || [NeoExternalDisplayPreferences storeEnabled:YES]);
      // A write iOS did not keep is said; the row shows the value really stored.
      if(!saved)self.navigationItem.prompt=[self text:@"externalSaveFailed"];
      [self.pacing refreshPreference];
      [self.tableView reloadData];
    }]];
  }
  [alert addAction:[UIAlertAction actionWithTitle:[self text:@"cancel"] style:UIAlertActionStyleCancel handler:nil]];
  alert.popoverPresentationController.sourceView=cell;alert.popoverPresentationController.sourceRect=cell.bounds;
  [self presentViewController:alert animated:YES completion:nil];
}
- (void)tableView:(UITableView*)table didSelectRowAtIndexPath:(NSIndexPath*)path {
  [table deselectRowAtIndexPath:path animated:YES];UIView* cell=[table cellForRowAtIndexPath:path];
  if(self.presentedViewController)return;
  if(path.row==0)[self choose:@[@0,@60,@120] names:@[[self text:@"automatic"],@"60 Hz",@"120 Hz"] key:DOLRefreshKey cell:cell];
  else if(path.row==1)[self choose:@[@0,@1,@2] names:@[[self text:@"legacy"],[self text:@"metal"],[self text:@"hybrid"]] key:DOLProfileKey cell:cell];
  else if(path.row==2){[self.pacing refreshPreference];[table reloadData];}
  else if(path.row==3)[self chooseExternalDisplay:cell];
  else if(path.row==4){[NSUserDefaults.standardUserDefaults setBool:!self.pacing.traceEnabled forKey:DOLTraceKey];[table reloadData];}
  else if(path.row==5) {
    struct utsname machine;uname(&machine);
    NSDictionary* report=@{@"schema":@2,@"build":NSBundle.mainBundle.infoDictionary[@"CFBundleVersion"]?:@"",
      @"device":@(machine.machine),@"iOS":UIDevice.currentDevice.systemVersion,@"summary":self.pacing.summary,@"samples":self.pacing.samples};
    NSData* bytes=[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:nil];
    NSURL* url=[NSURL fileURLWithPath:[NSTemporaryDirectory() stringByAppendingPathComponent:@"NeoStation-Dolphin-FramePacing.json"]];
    if(!bytes || ![bytes writeToURL:url options:NSDataWritingAtomic error:nil])return;
    UIActivityViewController* share=[[UIActivityViewController alloc] initWithActivityItems:@[url] applicationActivities:nil];
    share.popoverPresentationController.sourceView=cell;share.popoverPresentationController.sourceRect=cell.bounds;
    [self presentViewController:share animated:YES completion:nil];
  }
}
@end
