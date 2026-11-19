// Host side of the embedded Switch 2 engine. Method channel neostation/s2arm_internal. See docs/s2arm-engine-bridge.md.
#import "S2ArmEngineBridgePlugin.h"
#import "S2ArmEngineLoaded.h"
#import "S2ArmGuestABI.h"
#import "S2ArmCodePages.h"
#import "S2ArmPackPlan.h"
#import "S2ArmJitSession.h"
#import "S2ArmGamePreparation.h"
#import "S2ArmGraphicsGeneration.h"
#import "S2ArmPrepareABI.h"
#import "S2ArmLaunchJournal.h"
#import "S2ArmSettings.h"
#import "S2ArmSessionMenu.h"
#import "S2ArmNupImport.h"

#import <UIKit/UIKit.h>
#import <dlfcn.h>
#import <errno.h>
#import <sys/clonefile.h>
#import <sys/mount.h>

static NSString *const kChannel = @"neostation/s2arm_internal";
static NSString *const kProgressMethod = @"prepareProgress";
// The engine's main sets these before it loads the runtime (host_main.c:450-452, study § 9.1).
static NSString *const kGcSegmentSize = @"2000000";
static NSString *const kShaderCacheSize = @"67108864";
static NSTimeInterval const kHelperConnectTimeout = 30.0;
static NSTimeInterval const kAttachTimeout = 600.0;   // first use may mount a DDI, as for the RPCS3 helper
static NSTimeInterval const kCompletionTimeout = 120.0;
static uint64_t const kBootQuiesceNs = 2000000000ull;   // 2 s with no hook activity after boot code served = detach

static void s2arm_session_ended(int code, const char *reason, void *context);
static void s2arm_session_parked(const char *reason, void *context);

// The free space the engine wants before it puts the guest memory in files (S2Arm vawin.c guest_file_map reads
// S2A_GUEST_FILE_MIN_FREE_MB, 12288 MB when unset). The engine measures it with statfs, which counts none of the space iOS
// purges for a task the user asked for (caches); the Settings app and NSURLVolumeAvailableCapacityForImportantUsageKey count
// it, as the import does (IPA 728). IPA 778 (17 Nov): statfs gave 7901 MB while Settings showed about 50 GB, so the engine
// kept the guest memory anonymous (Mario Kart World's pool is 9216 MB, with 6133 MB left under the process limit: iOS stops
// the game after a while) and its "Not enough free storage" page covered the game. In 25 earlier sessions the sparse files
// held at most 5094 MB on disk. The files are used when either measure shows 6144 MB (the engine is given 0). Below that on
// both, the engine keeps its own check at 6144 MB and its page: the phone is really full. A value already in the environment
// is left as it is (12288 gives the engine's own behaviour back).
static void S2ArmGuestFileSpace(void) {
  if (getenv("S2A_GUEST_FILE_MIN_FREE_MB")) {
    s2arm_journal("guestFileSpace", "kept", NULL);
    return;
  }
  const unsigned long long needMB = 6144;
  NSString *tmp = NSTemporaryDirectory();
  struct statfs fs;
  unsigned long long statfsMB = statfs(tmp.fileSystemRepresentation, &fs) == 0 ? ((unsigned long long)fs.f_bavail * fs.f_bsize) >> 20 : 0;
  NSNumber *important = nil;
  [[NSURL fileURLWithPath:tmp] getResourceValue:&important forKey:NSURLVolumeAvailableCapacityForImportantUsageKey error:nil];
  unsigned long long importantMB = important.longLongValue > 0 ? (unsigned long long)important.longLongValue >> 20 : 0;
  unsigned long long thresholdMB = statfsMB >= needMB || importantMB >= needMB ? 0 : needMB;
  setenv("S2A_GUEST_FILE_MIN_FREE_MB", [NSString stringWithFormat:@"%llu", thresholdMB].UTF8String, 1);
  s2arm_journal("guestFileSpace", thresholdMB ? "short" : "enough", "\"statfsMB\":%llu,\"importantMB\":%llu,\"thresholdMB\":%llu",
                statfsMB, importantMB, thresholdMB);
}
static UIViewController *S2ArmTopViewController(void);
static BOOL S2ArmPathInside(NSString *path, NSString *root);
static void S2ArmPrepareSaveFolder(NSString *folder, NSString *docs);
static void S2ArmLogSaveImport(NSString *folder);

// The engine writes its own log to <game>/docs/host.log (patch 0009) and keeps the previous ones in <game>/docs/logs/,
// inside Library, which Files does not show. A copy goes to Documents/Diagnostics/S2Arm/engine/<gid>/ at each app start
// and at each session end, so that the player can send it: Mario Kart World on IPA 731 stalled 10 minutes in the
// engine, and nothing of the engine's own account could be read.
static void S2ArmExportEngineLogs(void) {
  NSFileManager *files = NSFileManager.defaultManager;
  NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
  NSString *library = S2ArmLibraryRoot();
  if (!documents.length || !library.length) return;
  NSString *outRoot = [documents stringByAppendingPathComponent:@"Diagnostics/S2Arm/engine"];
  for (NSString *gid in [files contentsOfDirectoryAtPath:library error:nil]) {
    NSString *docs = [[library stringByAppendingPathComponent:gid] stringByAppendingPathComponent:@"docs"];
    NSMutableArray<NSString *> *sources = [NSMutableArray array];
    NSString *current = [docs stringByAppendingPathComponent:@"host.log"];
    if ([files fileExistsAtPath:current]) [sources addObject:current];
    NSString *archive = [docs stringByAppendingPathComponent:@"logs"];
    for (NSString *name in [files contentsOfDirectoryAtPath:archive error:nil]) {
      if ([name hasPrefix:@"host-"] && [name hasSuffix:@".log"]) [sources addObject:[archive stringByAppendingPathComponent:name]];
    }
    if (!sources.count) continue;
    NSString *out = [outRoot stringByAppendingPathComponent:gid];
    [files createDirectoryAtPath:out withIntermediateDirectories:YES attributes:nil error:nil];
    for (NSString *source in sources) {
      NSString *target = [out stringByAppendingPathComponent:source.lastPathComponent];
      [files removeItemAtPath:target error:nil];
      [files copyItemAtPath:source toPath:target error:nil];
    }
  }
}

// The running game's log alone, when RewindBox goes to the background during a session. The IPA 772/773 test: the
// sessions end when the player closes RewindBox from the app switcher, so the copy of the next app start had not happened
// yet when the logs were sent, and the folder held only the sessions before (the profiles of the test were there). One
// file of a few MB, on a utility queue: the app has seconds left in the background, and closing it later loses nothing.
static void S2ArmExportRunningEngineLog(NSString *gid) {
  NSFileManager *files = NSFileManager.defaultManager;
  NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
  NSString *library = S2ArmLibraryRoot();
  if (!gid.length || !documents.length || !library.length || [gid containsString:@"/"]) return;
  NSString *source = [[[library stringByAppendingPathComponent:gid] stringByAppendingPathComponent:@"docs"] stringByAppendingPathComponent:@"host.log"];
  if (![files fileExistsAtPath:source]) return;
  NSString *out = [[documents stringByAppendingPathComponent:@"Diagnostics/S2Arm/engine"] stringByAppendingPathComponent:gid];
  [files createDirectoryAtPath:out withIntermediateDirectories:YES attributes:nil error:nil];
  NSString *target = [out stringByAppendingPathComponent:@"host.log"];
  [files removeItemAtPath:target error:nil];
  [files copyItemAtPath:source toPath:target error:nil];
}

static BOOL S2ArmMeloNXCoreLoaded(void) {
  int (*loaded)(void) = (int (*)(void))dlsym(RTLD_DEFAULT, "rb_melonx_core_loaded");
  return loaded && loaded() != 0;
}

static NSString *S2ArmEnginePath(void) {
  NSString *frameworks = NSBundle.mainBundle.privateFrameworksPath;
  return frameworks.length ? [frameworks stringByAppendingPathComponent:@"S2ArmEngine.framework/S2ArmEngine"] : nil;
}

@interface S2ArmEngineBridgePlugin ()
@property(nonatomic, strong) FlutterMethodChannel *channel;
@property(nonatomic, strong) dispatch_queue_t workQueue;
@property(atomic, strong, nullable) S2ArmGamePreparation *activePreparation;
@property(nonatomic, strong) S2ArmGraphicsGeneration *graphicsGeneration; // serial workQueue
@property(nonatomic) BOOL graphicsReady;
@property(atomic) BOOL graphicsCancelled;
@property(nonatomic, strong) NSCondition *graphicsPause;
@property(nonatomic) BOOL graphicsBackground; // guarded by graphicsPause
@property(nonatomic) uint64_t graphicsLastProgress;
@property(nonatomic, copy) NSString *graphicsLabel;
@property(nonatomic, copy) NSString *graphicsIncomplete;
@property(nonatomic, strong) NSTimer *graphicsMonitor;
@property(nonatomic, strong) UILabel *graphicsOverlay;

@property(atomic, strong, nullable) S2ArmJitSession *jitSession;
@property(nonatomic, strong, nullable) S2ArmNupImport *nupImport;   // NUP containers for the import (main thread)
@property(atomic, assign) BOOL engineLoaded;      // the engine was dlopen'd: one per process, no retry after this
@property(atomic, assign) BOOL launchInProgress;  // a launch attempt is running now
@property(nonatomic, copy, nullable) NSDictionary<NSString *, NSString *> *menuStrings;   // from Dart, for the in-game menu
@property(nonatomic, strong, nullable) UIViewController *engineViewController;   // presented while a game runs (main thread)
@property(nonatomic, strong, nullable) S2ArmSessionMenu *sessionMenu;             // RewindBox's in-game menu (main thread)
@property(nonatomic, copy, nullable) NSString *saveFolder;   // Documents/S2Arm/Saves/<game>, given to the engine
@property(nonatomic, copy, nullable) NSString *runningGameId;   // main thread, from launch through view dismissal
@property(atomic, copy, nullable) NSString *parkedGameId;    // patch 0010: Quit parked this game; it can resume in this process
// The game view's watch (main thread). IPA 771 test: the game view left the screen while the engine kept running (no stop, no park, no crash in
// its log); RewindBox stayed on its launch dialog, which the player cannot close during a Switch 2 session, so the only way out was to kill the app.
@property(nonatomic, strong, nullable) NSTimer *viewWatch;
@property(nonatomic, assign) s2a_rb_guest_stop_fn viewStop;
@property(nonatomic, assign) NSUInteger viewLostTicks;   // consecutive checks with the view off screen and no way to present it again
@property(nonatomic, assign) NSUInteger viewRestores;    // times the view was put back in this session
@property(nonatomic, assign) BOOL viewStopAsked;
- (void)closeSessionViewWithCompletion:(dispatch_block_t)completion;
@end

@implementation S2ArmEngineBridgePlugin

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar> *)registrar {
  FlutterMethodChannel *channel = [FlutterMethodChannel methodChannelWithName:kChannel binaryMessenger:registrar.messenger];
  S2ArmEngineBridgePlugin *instance = [S2ArmEngineBridgePlugin new];
  instance.channel = channel;
  instance.graphicsPause = [NSCondition new];
  instance.workQueue = dispatch_queue_create("com.neogamelab.neostation.s2arm.work", DISPATCH_QUEUE_SERIAL);
  [registrar addMethodCallDelegate:instance channel:channel];
  // The previous run's engine log (a crash ends the process before session_ended can copy it).
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ S2ArmExportEngineLogs(); });
  S2ArmPreparationCleanupAtStart();   // what an earlier run left of moved-aside preparations, in the background
  // A session's log is copied when RewindBox goes to the background with a game running (S2ArmExportRunningEngineLog)
  __weak S2ArmEngineBridgePlugin *weak = instance;
  [NSNotificationCenter.defaultCenter addObserverForName:UIApplicationDidEnterBackgroundNotification object:nil queue:nil
      usingBlock:^(NSNotification *note) {
    S2ArmEngineBridgePlugin *plugin = weak;
    [plugin.graphicsPause lock]; plugin.graphicsBackground = YES; [plugin.graphicsPause unlock];
  }];
  [NSNotificationCenter.defaultCenter addObserverForName:UIApplicationWillEnterForegroundNotification object:nil queue:nil
      usingBlock:^(NSNotification *note) {
    S2ArmEngineBridgePlugin *plugin = weak;
    [plugin.graphicsPause lock]; plugin.graphicsBackground = NO; [plugin.graphicsPause broadcast]; [plugin.graphicsPause unlock];
  }];
  [NSNotificationCenter.defaultCenter addObserverForName:UIApplicationDidEnterBackgroundNotification object:nil
                                                   queue:NSOperationQueue.mainQueue
                                              usingBlock:^(NSNotification *note) {
                                                S2ArmEngineBridgePlugin *plugin = weak;
                                                NSString *gid = plugin.engineViewController ? plugin.runningGameId : nil;
                                                if (!gid.length) return;
                                                s2arm_journal("engineLog", "copy", NULL);   // the copy itself runs next, on the utility queue
                                                dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ S2ArmExportRunningEngineLog(gid); });
                                              }];
}

- (void)handleMethodCall:(FlutterMethodCall *)call result:(FlutterResult)result {
  if ([call.method isEqualToString:@"status"]) {
    result([self status]);
    return;
  }
  if ([call.method isEqualToString:@"configureLaunchJournal"]) {
    NSString *path = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments[@"path"] : nil;
    BOOL opened = path.isAbsolutePath && s2arm_journal_open(path.fileSystemRepresentation) == 0;
    result(@(opened));  // a BOOL, so Dart gets true / false (see status)
    return;
  }
  // NUP containers (.nup): picked in place, checked, expanded into an export folder the Dart import moves into Games
  if ([call.method hasSuffix:@"Nup"] || [call.method isEqualToString:@"pickNupFiles"] || [call.method isEqualToString:@"releaseNupFiles"]) {
    if (!self.nupImport) self.nupImport = [[S2ArmNupImport alloc] initWithChannel:self.channel];
    NSDictionary *args = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{};
    NSString *path = [args[@"path"] isKindOfClass:NSString.class] ? args[@"path"] : @"";
    if ([call.method isEqualToString:@"pickNupFiles"]) {
      [self.nupImport pickFrom:S2ArmTopViewController() result:result];
      return;
    }
    if ([call.method isEqualToString:@"releaseNupFiles"]) {
      [self.nupImport releaseFiles];
      result(@YES);
      return;
    }
    if ([call.method isEqualToString:@"inspectNup"]) {
      [self.nupImport inspect:path result:result];
      return;
    }
    if ([call.method isEqualToString:@"expandNup"]) {
      NSString *output = [args[@"output"] isKindOfClass:NSString.class] ? args[@"output"] : @"";
      NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject ?: @"";
      [self.nupImport expand:path into:output documents:documents result:result];
      return;
    }
    if ([call.method isEqualToString:@"cancelNup"]) {
      [self.nupImport cancel];
      result(@YES);
      return;
    }
  }
  if ([call.method isEqualToString:@"detectExport"]) {
    NSString *folder = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments[@"exportFolder"] : nil;
    result(S2ArmDetectExport(folder ?: @""));
    return;
  }
  if ([call.method isEqualToString:@"gameInfo"]) {
    NSDictionary *args = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{};
    NSString *folder = [args[@"exportFolder"] isKindOfClass:NSString.class] ? args[@"exportFolder"] : @"";
    NSString *locale = [args[@"locale"] isKindOfClass:NSString.class] ? args[@"locale"] : nil;
    result(S2ArmGameInfo(folder, locale));
    return;
  }
  if ([call.method isEqualToString:@"storageInfo"]) {
    // Free bytes and the file-system number of a path, so the Dart import can tell move (same volume) from copy and check
    // free space before copying. The destination may not exist yet: its parent is measured.
    NSString *path = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments[@"path"] : nil;
    NSFileManager *files = NSFileManager.defaultManager;
    NSString *probe = path;
    while (probe.length > 1 && ![files fileExistsAtPath:probe]) probe = probe.stringByDeletingLastPathComponent;
    NSDictionary *attributes = probe.length ? [files attributesOfFileSystemForPath:probe error:nil] : nil;
    if (!attributes) {
      result(@{@"success" : @NO});
      return;
    }
    // The capacity iOS gives a task the user asked for: it counts the space the system can purge (caches), as the
    // Settings app does. NSFileSystemFreeSize and statvfs count none of it: IPA 728 refused a Switch 2 import as "not
    // enough space" while Settings showed about 68 GB available.
    NSNumber *important = nil;
    [[NSURL fileURLWithPath:probe] getResourceValue:&important forKey:NSURLVolumeAvailableCapacityForImportantUsageKey error:nil];
    result(@{
      @"success" : @YES,
      @"freeBytes" : attributes[NSFileSystemFreeSize] ?: @0,
      @"importantFreeBytes" : important ?: @0,
      @"systemNumber" : attributes[NSFileSystemNumber] ?: @0,
    });
    return;
  }
  if ([call.method isEqualToString:@"cloneTree"]) {
    // An APFS copy-on-write clone of a whole folder (clonefile(2)): instant, and it takes no space until a file changes.
    // The import uses it for a game on the same volume, and falls back to its byte copy when this fails (another volume,
    // another file system). The destination must be inside Documents and must not exist yet.
    NSDictionary *args = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{};
    NSString *from = [args[@"from"] isKindOfClass:NSString.class] ? args[@"from"] : nil;
    NSString *to = [args[@"to"] isKindOfClass:NSString.class] ? args[@"to"] : nil;
    NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    if (!from.isAbsolutePath || !to.isAbsolutePath || !documents || !S2ArmPathInside(to, documents) ||
        [NSFileManager.defaultManager fileExistsAtPath:to]) {
      result(@{@"success" : @NO, @"errno" : @(EINVAL)});
      return;
    }
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
      int status = clonefile(from.fileSystemRepresentation, to.fileSystemRepresentation, CLONE_NOFOLLOW);
      int code = status == 0 ? 0 : errno;
      dispatch_async(dispatch_get_main_queue(), ^{
        result(@{@"success" : status == 0 ? @YES : @NO, @"errno" : @(code)});
      });
    });
    return;
  }
  if ([call.method isEqualToString:@"prepareGame"]) {
    [self prepareGame:call.arguments result:result];
    return;
  }
  if ([call.method isEqualToString:@"cancelPrepare"]) {
    [self.activePreparation cancel];
    [self.graphicsPause lock]; self.graphicsCancelled = YES;
    [self.graphicsPause broadcast]; [self.graphicsPause unlock];
    result(@YES);
    return;
  }
  if ([call.method isEqualToString:@"launchGame"]) {
    [self launchGame:call.arguments result:result];
    return;
  }
  // Switch 2 settings: the engine's own NSUserDefaults keys and the game language (S2ArmSettings.h).
  if ([call.method isEqualToString:@"getSettings"]) {
    result(S2ArmSettingsSnapshot());
    return;
  }
  if ([call.method isEqualToString:@"openFolder"]) {
    // Shows a folder of the app's Documents in the Files app (shareddocuments: is the Files app's own scheme).
    NSString *folder = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments[@"path"] : nil;
    NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    if (![folder isKindOfClass:NSString.class] || !S2ArmPathInside(folder, documents)) {
      result(@NO);
      return;
    }
    NSURLComponents *url = [NSURLComponents new];
    url.scheme = @"shareddocuments";
    url.path = folder.stringByStandardizingPath;
    if (!url.URL) {
      result(@NO);
      return;
    }
    [UIApplication.sharedApplication openURL:url.URL options:@{} completionHandler:^(BOOL success) { result(@(success)); }];
    return;
  }
  if ([call.method isEqualToString:@"setSettings"]) {
    result(S2ArmSettingsApply([call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{}));
    return;
  }
  result(FlutterMethodNotImplemented);
}

#pragma mark - status

// Every flag is a BOOL before it is boxed. In this Objective-C file (not Objective-C++) a comparison or `&&` is a C
// int, so @(a != nil) is an ordinary NSNumber, and Flutter's codec sends it as 1, not true. Dart's `== true` then failed:
// on IPA 727 the Consoles switch stayed off with the engine, system data and helper all present.
- (NSDictionary *)status {
  NSOperatingSystemVersion os = NSProcessInfo.processInfo.operatingSystemVersion;
  BOOL enginePresent = S2ArmEnginePath().length && [NSFileManager.defaultManager fileExistsAtPath:S2ArmEnginePath()];
  BOOL ns2pro = NO;
  if (NSBundle.mainBundle.privateFrameworksPath.length) {
    ns2pro = [NSFileManager.defaultManager
        fileExistsAtPath:[NSBundle.mainBundle.privateFrameworksPath stringByAppendingPathComponent:@"NS2Pro.framework/NS2Pro"]];
  }
  BOOL floorMet = os.majorVersion >= 18;  // S2Arm.app deployment target
  BOOL available = enginePresent && floorMet;
  BOOL helperPresent = S2ArmFindHelperBundleIdentifier() != nil;
  BOOL systemDataPresent = S2ArmShippedSystemData() != nil;
  BOOL engineLoaded = rb_s2arm_engine_loaded() != 0;
  return @{
    @"available" : @(available),
    @"enginePresent" : @(enginePresent),
    @"ns2proPresent" : @(ns2pro),
    @"iosMajor" : @(os.majorVersion),
    @"engineFloorMet" : @(floorMet),
    @"universalHandshake" : @(S2ArmRequiresCoreHandshake()),  // iOS 26+: the host drives commands 3/1/0
    @"getTaskAllow" : @(S2ArmHostHasGetTaskAllow()),
    @"debugged" : @(S2ArmHostIsDebugged()),
    @"helperPresent" : @(helperPresent),
    @"systemDataPresent" : @(systemDataPresent),
    @"directChain" : S2ArmShippedDirectChain() ?: [NSNull null],
    @"melonxCoreLoaded" : @(S2ArmMeloNXCoreLoaded()),
    @"engineLoaded" : @(engineLoaded),
    @"parkedGameId" : self.parkedGameId ?: @"",
    @"journalLines" : @(s2arm_journal_lines()),
  };
}

#pragma mark - prepare

- (void)prepareGame:(id)arguments result:(FlutterResult)result {
  if (![arguments isKindOfClass:NSDictionary.class] || ![arguments[@"exportFolder"] isKindOfClass:NSString.class]) {
    result(@{@"success" : @NO, @"code" : S2ArmErrorInvalidArguments});
    return;
  }
  if (self.activePreparation || self.launchInProgress || self.runningGameId.length) {
    result(@{@"success" : @NO, @"code" : @"prepareBusy"});
    return;
  }
  S2ArmGamePreparation *preparation = [S2ArmGamePreparation new];
  preparation.exportFolder = arguments[@"exportFolder"];
  preparation.directChain = [arguments[@"directChain"] isKindOfClass:NSString.class] ? arguments[@"directChain"] : nil;
  preparation.systemDataFolder = [arguments[@"systemDataFolder"] isKindOfClass:NSString.class] ? arguments[@"systemDataFolder"] : nil;
  __weak S2ArmEngineBridgePlugin *weakSelf = self;
  preparation.progress = ^(NSString *step, NSInteger index, NSInteger count, double fraction, NSString *detail, NSDictionary *work) {
    S2ArmEngineBridgePlugin *strongSelf = weakSelf;
    NSMutableDictionary *arguments = [@{@"step" : step, @"index" : @(index), @"count" : @(count), @"fraction" : @(fraction),
                                        @"detail" : detail ?: @""} mutableCopy];
    if (work) [arguments addEntriesFromDictionary:work];   // phase, attempt, done, total (code stage)
    dispatch_async(dispatch_get_main_queue(), ^{
      [strongSelf.channel invokeMethod:kProgressMethod arguments:arguments];
    });
  };
  self.graphicsCancelled = NO;
  self.activePreparation = preparation;
  dispatch_async(self.workQueue, ^{
    NSDictionary *report = [preparation run];
    self.graphicsGeneration = [report[@"success"] boolValue] ? preparation.graphicsGeneration : nil;
    self.graphicsReady = preparation.graphicsReady;
    self.activePreparation = nil;
    dispatch_async(dispatch_get_main_queue(), ^{ result(report); });
  });
}

#pragma mark - launch

- (void)launchGame:(id)arguments result:(FlutterResult)result {
  if (![arguments isKindOfClass:NSDictionary.class]) {
    result(@{@"success" : @NO, @"error" : S2ArmErrorInvalidArguments});
    return;
  }
  NSDictionary *args = arguments;
  NSString *gid = args[@"gid"];
  NSString *images = args[@"imagesPath"];
  NSString *moduleDir = args[@"moduleDir"];
  NSString *gameData = args[@"gameData"];
  NSString *docs = args[@"docs"];
  NSString *pairing = args[@"pairingFilePath"];
  NSString *displayTitle = [args[@"displayTitle"] isKindOfClass:NSString.class] ? args[@"displayTitle"] : nil;
  NSDictionary *menuStrings = [args[@"menuStrings"] isKindOfClass:NSDictionary.class] ? args[@"menuStrings"] : @{};
  NSString *saveFolder = [args[@"saveFolder"] isKindOfClass:NSString.class] ? args[@"saveFolder"] : nil;
  if (![gid isKindOfClass:NSString.class] || ![images isKindOfClass:NSString.class] || ![moduleDir isKindOfClass:NSString.class] ||
      ![gameData isKindOfClass:NSString.class] || ![docs isKindOfClass:NSString.class]) {
    result(@{@"success" : @NO, @"error" : S2ArmErrorInvalidArguments});
    return;
  }
  BOOL resume = NO;
  @synchronized(self) {
    if (self.launchInProgress) {   // first: a second tap while a launch or a resume runs is "busy", not "restart"
      result(@{@"success" : @NO, @"error" : @"busy"});
      return;
    }
    if (self.runningGameId.length) {   // even after the engine stopped, UIKit can still be closing its view
      result(@{@"success" : @NO, @"error" : @"busy"});
      return;
    }
    if (self.engineLoaded || rb_s2arm_engine_loaded() != 0) {
      // Patch 0010: the game Quit parked resumes in this process; any other Switch 2 game still needs a new process.
      resume = self.parkedGameId && [self.parkedGameId caseInsensitiveCompare:gid] == NSOrderedSame;
      if (!resume) {
        result(@{@"success" : @NO, @"error" : @"engineRestartRequired", @"diagnostic" : @"A Switch 2 game already ran in this process."});
        return;
      }
    }
    self.launchInProgress = YES;
  }
  self.menuStrings = menuStrings;
  self.graphicsLabel = [args[@"graphicsLabel"] isKindOfClass:NSString.class] ? args[@"graphicsLabel"] : @"Graphics preparation";
  self.graphicsIncomplete = [args[@"graphicsIncomplete"] isKindOfClass:NSString.class] ? args[@"graphicsIncomplete"] : @"Graphics preparation incomplete";
  self.saveFolder = saveFolder;
  // The Switch 1 engine's Core (MeloNX) and this engine cannot share a process (two .NET runtimes). Its own code,
  // distinct from engineRestartRequired (a Switch 2 game already ran), so the message names the right console. The
  // code and the diagnostic reach the player's failure dialog: they name the console, never the engine.
  if (S2ArmMeloNXCoreLoaded()) {
    self.launchInProgress = NO;
    s2arm_journal("launch", "refused", "\"reason\":\"switch1EngineLoaded\"");
    result(@{@"success" : @NO, @"error" : @"switch1EngineLoaded", @"diagnostic" : @"The Switch 1 engine ran in this session of RewindBox."});
    return;
  }
  // The deletion of earlier preparations (.discarded-*) waits while the game runs: it took 0.34 core in the first race of
  // the IPA 765 test. A failed launch lets it go on; the session's end or park does too (s2arm_session_ended / _parked).
  self.runningGameId = gid;
  S2ArmPreparationGameRunning(YES);
  dispatch_async(self.workQueue, ^{
    const char *title = displayTitle.UTF8String;
    if (title && *title) setenv("S2A_RB_DISPLAY_TITLE", title, 1);
    else unsetenv("S2A_RB_DISPLAY_TITLE");
    if (resume) S2ArmPrepareSaveFolder(saveFolder, docs);
    NSDictionary *report = resume ? [self resumeParkedGame:gid]
                                  : [self runLaunchWithGid:gid images:images moduleDir:moduleDir gameData:gameData docs:docs pairing:pairing];
    dispatch_async(dispatch_get_main_queue(), ^{
      if (![report[@"success"] boolValue]) {
        self.runningGameId = nil;
        S2ArmPreparationGameRunning(NO);
      }
      self.launchInProgress = NO;
      result(report);
    });
  });
}

// Patch 0010: the game the player quit was parked (its guests, services, GPU and memory retired, its code pages kept). It
// boots again in the same view controller: no dlopen, no configure, no JIT transaction (the same code pages are reused).
- (NSDictionary *)resumeParkedGame:(NSString *)gid {
  s2arm_journal("resume", "begin", "\"gid\":\"%s\"", gid.UTF8String);
  s2a_rb_guest_parked_fn parked = (s2a_rb_guest_parked_fn)dlsym(RTLD_DEFAULT, S2A_RB_GUEST_PARKED);
  s2a_rb_guest_view_controller_fn viewController = (s2a_rb_guest_view_controller_fn)dlsym(RTLD_DEFAULT, S2A_RB_GUEST_VIEW_CONTROLLER);
  s2a_rb_guest_resume_fn resume = (s2a_rb_guest_resume_fn)dlsym(RTLD_DEFAULT, S2A_RB_GUEST_RESUME);
  s2a_rb_guest_stop_fn stop = (s2a_rb_guest_stop_fn)dlsym(RTLD_DEFAULT, S2A_RB_GUEST_STOP);
  if (!parked || !viewController || !resume || !parked()) {
    self.parkedGameId = nil;
    return launchFail(@"engineRestartRequired", @"resume", @"The engine has no parked session to resume.");
  }
  if (self.graphicsGeneration && self.graphicsReady) unsetenv("S2A_RB_PREPARE_PROFILE");
  S2ArmSettingsPrepareLaunch();   // settings changed while parked apply now (the rebuild reloads the graphics settings)
  [self applyStoredFrameRateLimit];   // patch 0078: S2A_FPS was read once, at this process's first game start
  __block UIViewController *vc = nil;
  dispatch_sync(dispatch_get_main_queue(), ^{ vc = (__bridge UIViewController *)viewController(); });
  if (!vc) return launchFail(@"engineViewFailed", @"resume", @"The engine did not return the parked view controller.");
  dispatch_semaphore_t done = dispatch_semaphore_create(0);
  __block int resumeRc = 0;
  __block NSString *resumeError = nil;
  dispatch_async(dispatch_get_main_queue(), ^{
    UIViewController *presenter = S2ArmTopViewController();
    if (!presenter) {
      resumeError = @"no foreground view controller to present the game on";
      resumeRc = -1;
      dispatch_semaphore_signal(done);
      return;
    }
    [presenter presentViewController:vc
                           animated:NO
                         completion:^{
                           char error[600] = "";
                           self.parkedGameId = nil;
                           resumeRc = resume(error, sizeof error);
                           if (resumeRc != 0) {
                             self.parkedGameId = parked() ? gid : nil;
                             resumeError = @(error);
                             [vc dismissViewControllerAnimated:NO completion:^{ dispatch_semaphore_signal(done); }];
                             return;
                           } else {
                             [self attachSessionMenuTo:vc stop:stop];
                             if (self.graphicsGeneration && !self.graphicsReady) {
                               s2arm_graphics_status_fn status = (s2arm_graphics_status_fn)dlsym(RTLD_DEFAULT, S2ARM_GRAPHICS_STATUS);
                               if (status) [self monitorGraphics:self.graphicsGeneration inView:vc.view status:status];
                             }
                           }
                           dispatch_semaphore_signal(done);
                         }];
  });
  dispatch_semaphore_wait(done, DISPATCH_TIME_FOREVER);
  if (resumeRc != 0) return launchFail(@"engineStartFailed", @"resume", resumeError);
  s2arm_journal("resume", "passed", NULL);
  return @{@"success" : @YES, @"gid" : gid, @"stage" : @"running", @"resumed" : @YES};
}

static NSDictionary *launchFail(NSString *error, NSString *stage, NSString *detail) {
  s2arm_journal("launch", "failed", "\"stage\":\"%s\",\"error\":\"%s\"", stage.UTF8String, error.UTF8String);
  return @{@"success" : @NO, @"error" : error, @"stage" : stage, @"diagnostic" : detail ?: @""};
}

static int graphicsCancelled(void *ctx) {
  S2ArmEngineBridgePlugin *plugin = (__bridge S2ArmEngineBridgePlugin *)ctx;
  // iOS can suspend the process between checkpoints. Returning to the same
  // process must resume the pending launch without attempting a second dlopen.
  [plugin.graphicsPause lock];
  while (plugin.graphicsBackground && !plugin.graphicsCancelled) [plugin.graphicsPause wait];
  BOOL cancelled = plugin.graphicsCancelled;
  [plugin.graphicsPause unlock];
  return cancelled;
}
static void graphicsProgress(void *ctx, uint64_t done, uint64_t total) {
  S2ArmEngineBridgePlugin *plugin = (__bridge S2ArmEngineBridgePlugin *)ctx;
  uint64_t now = s2arm_code_now_ns();
  @synchronized(plugin) {
    if (done != total && plugin.graphicsLastProgress && now - plugin.graphicsLastProgress < 200000000) return;
    plugin.graphicsLastProgress = now;
  }
  double fraction = total ? (double)done / total : 0;
  NSDictionary *event = @{@"step":@"graphics", @"index":@6, @"count":@7, @"phase":@"inputs",
                          @"fraction":@(fraction), @"done":@(done), @"total":@(total)};
  dispatch_async(dispatch_get_main_queue(), ^{ [plugin.channel invokeMethod:kProgressMethod arguments:event]; });
}

// Runs after the session's own view is visible. The renderer alone can confirm
// that its actual entry points and exact PSOs succeeded on this Metal device.
- (void)monitorGraphics:(S2ArmGraphicsGeneration *)generation inView:(UIView *)view status:(s2arm_graphics_status_fn)status {
  [self.graphicsMonitor invalidate]; [self.graphicsOverlay removeFromSuperview];
  UILabel *label = [UILabel new];
  label.numberOfLines = 2; label.textAlignment = NSTextAlignmentCenter;
  label.textColor = UIColor.whiteColor; label.backgroundColor = [UIColor.blackColor colorWithAlphaComponent:0.85];
  label.font = [UIFont preferredFontForTextStyle:UIFontTextStyleSubheadline]; label.text = self.graphicsLabel;
  label.accessibilityTraits = UIAccessibilityTraitUpdatesFrequently;
  label.translatesAutoresizingMaskIntoConstraints = NO; [view addSubview:label];
  [NSLayoutConstraint activateConstraints:@[[label.centerXAnchor constraintEqualToAnchor:view.safeAreaLayoutGuide.centerXAnchor],
    [label.topAnchor constraintEqualToAnchor:view.safeAreaLayoutGuide.topAnchor constant:8],
    [label.widthAnchor constraintLessThanOrEqualToAnchor:view.safeAreaLayoutGuide.widthAnchor],
    [label.heightAnchor constraintGreaterThanOrEqualToConstant:44]]];
  self.graphicsOverlay = label;
  __weak S2ArmEngineBridgePlugin *weak = self;
  self.graphicsMonitor = [NSTimer scheduledTimerWithTimeInterval:0.2 repeats:YES block:^(NSTimer *timer) {
    S2ArmEngineBridgePlugin *plugin = weak; if (!plugin) { [timer invalidate]; return; }
    uint64_t s[6] = {0}; int rc = status(s);
    uint64_t total = s[0] + s[2], done = s[1] + s[4];
    if (total) label.text = [NSString stringWithFormat:@"%@\n%llu / %llu", plugin.graphicsLabel, (unsigned long long)done, (unsigned long long)total];
    if (!rc) return;
    [timer invalidate]; plugin.graphicsMonitor = nil;
    NSArray *snapshot = @[@(s[0]), @(s[1]), @(s[2]), @(s[3]), @(s[4]), @(s[5])];
    dispatch_async(plugin.workQueue, ^{
      uint64_t counts[6]; for (NSUInteger i = 0; i < 6; ++i) counts[i] = [snapshot[i] unsignedLongLongValue];
      NSError *failure = nil;
      BOOL ready = rc == 1 && [generation activateWithGPU:counts error:&failure];
      plugin.graphicsReady = ready;
      s2arm_journal("graphics", ready ? "activated" : "incomplete",
                    "\"stages\":%llu,\"requestedStages\":%llu,\"strictPSO\":%llu,\"requestedPSO\":%llu,\"missingRecipes\":%llu",
                    (unsigned long long)counts[1], (unsigned long long)counts[0], (unsigned long long)counts[4],
                    (unsigned long long)counts[2], (unsigned long long)counts[5]);
      dispatch_async(dispatch_get_main_queue(), ^{
        if (plugin.graphicsOverlay != label) return;
        if (ready) { [label removeFromSuperview]; plugin.graphicsOverlay = nil; return; }
        label.text = [NSString stringWithFormat:@"%@\n%llu / %llu", plugin.graphicsIncomplete,
                     (unsigned long long)done, (unsigned long long)total];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 5*NSEC_PER_SEC), dispatch_get_main_queue(), ^{
          if (plugin.graphicsOverlay == label) { [label removeFromSuperview]; plugin.graphicsOverlay = nil; }
        });
      });
    });
  }];
}

- (NSDictionary *)runLaunchWithGid:(NSString *)gid
                            images:(NSString *)images
                         moduleDir:(NSString *)moduleDir
                          gameData:(NSString *)gameData
                              docs:(NSString *)docs
                           pairing:(NSString *)pairing {
  s2arm_journal("launch", "begin", "\"gid\":\"%s\"", gid.UTF8String);
  NSString *enginePath = S2ArmEnginePath();
  if (enginePath.length == 0 || ![NSFileManager.defaultManager fileExistsAtPath:enginePath]) {
    return launchFail(@"enginePresent", @"engine", @"S2ArmEngine.framework is not in this build.");
  }
  // Read what the boot will ask the hook for, so the host knows when the boot code is served (and can size the spare pool).
  s2arm_pack_plan plan;
  char planError[512] = "";
  if (s2arm_pack_plan_read(images.fileSystemRepresentation, &plan, planError, sizeof planError) != 0) {
    return launchFail(S2ArmErrorExportInvalid, @"imagePack", @(planError));
  }
  s2arm_journal("imagePack", "read", "\"modules\":%u,\"bootBlocks\":%u,\"bootBytes\":%llu,\"laterBlocks\":%u", plan.modules,
                plan.boot_code_blocks, (unsigned long long)plan.boot_code_bytes, plan.later_code_blocks);

  BOOL universal = S2ArmRequiresCoreHandshake();
  if (universal) {
    NSDictionary *jit = [self attachHelperWithPairing:pairing];
    if (![jit[@"success"] boolValue]) return jit;
  } else {
    // Below iOS 26 the helper's classic attach/detach (not wired in v1) leaves CS_DEBUGGED; here the process must already be
    // JIT-enabled. The whole device path so far is iOS 26+ (study § 6.4), so this branch is a guard, not a tested route.
    if (!S2ArmHostHasGetTaskAllow() || !S2ArmHostIsDebugged()) {
      return launchFail(@"jitUnavailable", @"jit", @"Below iOS 26 the process must already be JIT-enabled.");
    }
  }
  s2arm_code_begin(universal);

  if (universal) {
    // Prove the debugger round-trip before the dlopen, as the RPCS3 loader does at the Core boundary.
    uint64_t nonce = self.jitSession.probeNonce;
    if (s2arm_code_probe(nonce) != nonce + 1) {
      [self.jitSession close];
      self.jitSession = nil;
      return launchFail(@"jitUnavailable", @"jitProbe", @"The debugger did not answer the nonce probe.");
    }
    s2arm_journal("jitProbe", "passed", NULL);
    // The spare pool covers code the game loads after the detach (later NROs): command 1 cannot run once detached.
    // It also covers the boot code: if the boot is not served before the deadline, the helper detaches anyway and the
    // engine's first request must still find pages. Mario Kart World on IPA 731 asked for main's 42 MB right after a
    // forced detach, and a 16 MB pool ended the session (pool exhausted, code 134).
    uint64_t pool = plan.boot_code_bytes + plan.later_code_bytes + (16ull << 20);
    if (s2arm_code_prepare_pool(pool) != 0) {
      s2arm_journal("pool", "skipped", "\"bytes\":%llu", (unsigned long long)pool);   // launch still proceeds; later NROs may fail
    }
  }

  // Environment the engine's main sets, then the flag before the dlopen, then the dlopen (RTLD_NOW | RTLD_GLOBAL).
  setenv("DOTNET_GCSegmentSize", kGcSegmentSize.UTF8String, 0);
  setenv("MTL_SHADER_CACHE_SIZE", kShaderCacheSize.UTF8String, 0);
  // IPA 783: the engine refused to park with the workgroup enabled (-2), then took 304 ms for terminal shutdown.
  // Use the park-compatible path (0097) by default. A/B can restore the old default or explicitly select the workgroup.
  setenv("S2A_RB_PARK_COMPAT", "1", 0);
  const char *parkCompat = getenv("S2A_RB_PARK_COMPAT");
  BOOL parkEnabled = parkCompat && strcmp(parkCompat, "1") == 0;
  setenv("S2A_WORKGROUP", parkEnabled ? "0" : "1", 0);
  const char *workgroup = getenv("S2A_WORKGROUP");
  s2arm_journal("parkMode", parkEnabled && workgroup && !strcmp(workgroup, "0") ? "compatible" : "legacy", NULL);
  // Select measured engine changes by title before loading the framework. A value supplied for an A/B run wins.
  BOOL fastFusion = [gid caseInsensitiveCompare:@"040041E0212AE000"] == NSOrderedSame;
  BOOL marioKartWorld = [gid caseInsensitiveCompare:@"0400C3F00006E000"] == NSOrderedSame;
  int vertexProfile = setenv("S2A_RB_NVN2_VATTR_PREFIX", fastFusion ? "1" : "0", 0);
  int stagingProfile = setenv("S2A_RB_UP_PRESSURE_TRIM", marioKartWorld ? "1" : "0", 0);
  int workgroupProfile = setenv("S2A_RB_WG_CADENCE_IDLE", marioKartWorld ? "1" : "0", 0);
  int archiveProfile = setenv("S2A_RB_PSO_ARCHIVE_COALESCE", marioKartWorld ? "1" : "0", 0);
  int workerProfile = setenv("S2A_RB_YIELD_WORKER_IDLE", marioKartWorld ? "1" : "0", 0);
  int readAheadProfile = setenv("S2A_RB_POOL_QUEUE_BUDGET", marioKartWorld ? "1" : "0", 0);
  const char *kartRender = marioKartWorld ? "1" : "0";
  // Preserve reconstructible stage bytes on a real bind for every hosted title.
  // The engine bounds outstanding copies and retries failed writes.
  int shaderBytesProfile = setenv("S2A_RB_DSH_KEEP_MAPPED", "1", 0);
  int shaderQueueProfile = setenv("S2A_RB_SHADER_URGENT_UNIQUE", kartRender, 0);
  int poolIndexProfile = setenv("S2A_RB_POOL_INDEX_UPDATE", kartRender, 0);
  int textureViewsProfile = setenv("S2A_RB_TEX_FIT_FAST", kartRender, 0);
  int demandProbeProfile = setenv("S2A_RB_DEMAND_PROBE_BATCH", kartRender, 0);
  int audioReprimeProfile = setenv("S2A_RB_AUDIO_REPRIME", kartRender, 0);
  int feedbackProfile = setenv("S2A_RB_FB_DIRECT_SNAPSHOT", kartRender, 0);
  int pipelinePriorityProfile = setenv("S2A_RB_PSO_HOT_FIRST", kartRender, 0);
  int shaderCompletionProfile = setenv("S2A_RB_SHADER_AHEAD_JOIN", kartRender, 0);
  int pipelineLookaheadProfile = setenv("S2A_RB_PSO_LOOK_META", kartRender, 0);
  // IPA 785: 967,104 bounds tables in 300 race frames; 208,326 unproductive word spins;
  // 2,628 draws per frame repeated their shader signature lookup. Keep A/B controls per title.
  int uniformBoundsProfile = setenv("S2A_RB_UNIFORM_BOUNDS_REUSE", kartRender, 0);
  int waitProbeProfile = setenv("S2A_RB_IDLE_WAIT_PROBE", kartRender, 0);
  int frameKeyProfile = setenv("S2A_RB_FRAME_SHADER_KEY", kartRender, 0);
  // IPA 786: 82 and 96 on-screen drops in successive 300-frame windows at guest 30 FPS.
  int displayTicksProfile = setenv("S2A_RB_LINK_GAME30", kartRender, 0);
  int residencyCensusProfile = setenv("S2A_RB_RES_TOP_PER_FRAME", kartRender, 0);
  int shaderVariantProfile = setenv("S2A_RB_BOUND_SHADER_VARIANT", kartRender, 0);
  // IPA 786's automatic sampler held individual threads for up to 32.5 ms.
  // Keep continuous frame statistics and let diagnostic launches request the heavy capture.
  int automaticProbeProfile = marioKartWorld ? setenv("S2A_RB_AUTO_PROBE", "0", 0) : 0;
  int saveRestoreProfile = setenv("S2A_RB_SAVE_PROFILE", "1", 0);
  int saveTitleSlots = setenv("S2A_RB_SAVE_TITLE_SLOTS", "1", 0);
  BOOL profileFailed = vertexProfile || stagingProfile || workgroupProfile || archiveProfile || workerProfile ||
                       readAheadProfile || shaderBytesProfile || shaderQueueProfile || poolIndexProfile ||
                       textureViewsProfile || demandProbeProfile || audioReprimeProfile || feedbackProfile ||
                       pipelinePriorityProfile || shaderCompletionProfile || pipelineLookaheadProfile ||
                       uniformBoundsProfile || waitProbeProfile || frameKeyProfile ||
                       displayTicksProfile || residencyCensusProfile || shaderVariantProfile || automaticProbeProfile ||
                       saveRestoreProfile || saveTitleSlots;
  s2arm_journal("gameProfile", profileFailed ? "failed" : "selected",
                "\"profile\":\"%s\"", fastFusion ? "fast-fusion" : marioKartWorld ? "mario-kart-world" : "default");
  S2ArmSettingsPrepareLaunch();   // the game language, and the engine's brief overlay that the in-game menu shows or hides
  S2ArmGuestFileSpace();          // the free space the engine wants for the guest memory files (S2A_GUEST_FILE_MIN_FREE_MB)
  S2ArmPrepareSaveFolder(self.saveFolder, docs);   // the save folder the player sees in Files (S2A_SAVE_FOLDER)
  rb_s2arm_engine_mark_loading();
  self.engineLoaded = YES;   // from here the engine lives in this process: no second launch, even if the dlopen fails
  s2arm_journal("dlopen", "begin", NULL);
  void *engine = dlopen(enginePath.fileSystemRepresentation, RTLD_NOW | RTLD_GLOBAL);
  if (!engine) {
    return launchFail(@"engineLoadFailed", @"dlopen", @(dlerror() ?: "dlopen failed"));
  }
  s2arm_journal("dlopen", "passed", NULL);

  s2a_rb_guest_configure_fn configure = (s2a_rb_guest_configure_fn)dlsym(engine, S2A_RB_GUEST_CONFIGURE);
  s2a_rb_guest_make_view_controller_fn makeVC = (s2a_rb_guest_make_view_controller_fn)dlsym(engine, S2A_RB_GUEST_MAKE_VIEW_CONTROLLER);
  s2a_rb_guest_start_fn start = (s2a_rb_guest_start_fn)dlsym(engine, S2A_RB_GUEST_START);
  s2a_rb_guest_stop_fn stop = (s2a_rb_guest_stop_fn)dlsym(engine, S2A_RB_GUEST_STOP);   // the in-game menu's Quit
  if (!configure || !makeVC || !start) {
    return launchFail(@"engineAbiMissing", @"dlsym", @"The engine does not export the guest entry points.");
  }

  S2ArmGraphicsGeneration *generation = self.graphicsGeneration;
  s2arm_graphics_status_fn graphicsStatus = NULL;
  BOOL pendingGPU = generation && !self.graphicsReady;
  if (generation) {
    if (![generation.gid isEqual:gid] || ![generation.gameDir isEqual:docs.stringByDeletingLastPathComponent])
      return launchFail(S2ArmErrorPrepareFailed, @"graphics", @"The planned graphics generation belongs to another game.");
    if (pendingGPU) {
      s2arm_graphics_prepare_fn prepare = (s2arm_graphics_prepare_fn)dlsym(engine, S2ARM_GRAPHICS_PREPARE);
      graphicsStatus = (s2arm_graphics_status_fn)dlsym(engine, S2ARM_GRAPHICS_STATUS);
      if (!prepare || !graphicsStatus) return launchFail(@"engineAbiMissing", @"graphics", @"The verified graphics preparation entry points are missing.");
      uint64_t stages[8] = {0}; self.graphicsLastProgress = 0;
      int rc = prepare(gid.UTF8String, generation.buildID.UTF8String, gameData.fileSystemRepresentation,
                       generation.wire.fileSystemRepresentation, graphicsCancelled, (__bridge void *)self, stages,
                       rb_s2arm_shader_inflate, graphicsProgress);
      s2arm_journal("graphics", "stageInputs", "\"result\":%d,\"wanted\":%llu,\"recovered\":%llu,\"missing\":%llu,\"translated\":%llu,\"refused\":%llu",
                    rc, (unsigned long long)stages[0], (unsigned long long)stages[3], (unsigned long long)stages[4],
                    (unsigned long long)stages[5], (unsigned long long)stages[6]);
      if (rc) return launchFail(rc == 1 ? S2ArmErrorCancelled : S2ArmErrorPrepareFailed, @"graphics",
                                @"Graphics preparation stopped before rendering. Its checkpoints were retained.");
    }
    NSString *profile = [generation.wire stringByAppendingPathComponent:@"pso_reference.tsv"];
    if (setenv("DM_MSL_FALLBACK", [generation.wire stringByAppendingPathComponent:@"shaders"].fileSystemRepresentation, 1) ||
        setenv("DM_PSO_USER", [generation.wire stringByAppendingPathComponent:@"pso_user.tsv"].fileSystemRepresentation, 1) ||
        (pendingGPU ? setenv("S2A_RB_PREPARE_PROFILE", profile.fileSystemRepresentation, 1) : unsetenv("S2A_RB_PREPARE_PROFILE")))
      return launchFail(S2ArmErrorPrepareFailed, @"graphics", @"Could not select the graphics cache.");
    s2arm_journal("graphics", pendingGPU ? "staged" : "verifiedGeneration", NULL);
  }

  s2a_rb_guest_config config = {0};
  config.size = sizeof config;
  config.game_id = gid.UTF8String;
  config.images = images.fileSystemRepresentation;
  config.module_dir = moduleDir.fileSystemRepresentation;
  config.caps_dir = NULL;   // = module_dir, where the module step copied s2a_caps.tsv with the shell's other tables
  config.game_data = gameData.fileSystemRepresentation;
  config.ryu_data = NULL;   // = <docs>/S2A/ryujinx
  config.docs = docs.fileSystemRepresentation;
  config.prepare_code = s2arm_code_prepare;
  config.prepare_context = (__bridge void *)self;
  config.session_ended = s2arm_session_ended;
  config.ended_context = (__bridge void *)self;
  config.session_parked = s2arm_session_parked;   // patch 0010: Quit parks the session; the same game can resume
  config.parked_context = (__bridge void *)self;
  char configError[600] = "";
  s2arm_journal("configure", "begin", NULL);
  if (configure(&config, configError, sizeof configError) != 0) {
    return launchFail(@"engineConfigureFailed", @"configure", @(configError));
  }
  s2arm_journal("configure", "passed", NULL);

  // The view controller and the start are on the main thread; the host presents it full screen (landscape only).
  __block UIViewController *vc = nil;
  dispatch_sync(dispatch_get_main_queue(), ^{ vc = (__bridge UIViewController *)makeVC(); });
  if (!vc) return launchFail(@"engineViewFailed", @"viewController", @"The engine did not return a view controller.");
  s2arm_journal("viewController", "passed", NULL);

  // Present on the main thread; the start runs in the presentation's completion (the view controller is then in a window),
  // and a semaphore carries its result back to this background thread.
  dispatch_semaphore_t done = dispatch_semaphore_create(0);
  __block int startRc = 0;
  __block NSString *startError = nil;
  dispatch_async(dispatch_get_main_queue(), ^{
    UIViewController *presenter = S2ArmTopViewController();
    if (!presenter) {
      startError = @"no foreground view controller to present the game on";
      startRc = -1;
      dispatch_semaphore_signal(done);
      return;
    }
    [presenter presentViewController:vc
                           animated:NO
                         completion:^{
                           char error[600] = "";
                           startRc = start(error, sizeof error);
                           if (startRc != 0) {
                             startError = @(error);
                             [vc dismissViewControllerAnimated:NO completion:^{ dispatch_semaphore_signal(done); }];
                             return;
                           } else {
                             [self attachSessionMenuTo:vc stop:stop];
                             if (pendingGPU) [self monitorGraphics:generation inView:vc.view status:graphicsStatus];
                           }
                           dispatch_semaphore_signal(done);
                         }];
  });
  dispatch_semaphore_wait(done, DISPATCH_TIME_FOREVER);
  if (startRc != 0) return launchFail(@"engineStartFailed", @"start", startError);
  s2arm_journal("start", "passed", NULL);

  if (universal) [self detachAfterBootServed:&plan];
  s2arm_code_stats finalStats;
  s2arm_code_stats_get(&finalStats);
  s2arm_journal("launch", "running", "\"servedBlocks\":%u,\"afterDetach\":%u", finalStats.served_blocks, finalStats.after_detach_blocks);
  return @{@"success" : @YES, @"gid" : gid, @"stage" : @"running"};
}

// Waits until the boot code blocks have been served, then detaches the helper and completes the JIT transaction.
- (void)detachAfterBootServed:(const s2arm_pack_plan *)plan {
  uint64_t deadline = s2arm_code_now_ns() + (uint64_t)(kAttachTimeout * 1000000000.0);
  for (;;) {
    s2arm_code_stats stats;
    s2arm_code_stats_get(&stats);
    uint64_t now = s2arm_code_now_ns();
    BOOL served = s2arm_pack_plan_boot_served(plan, stats.served_blocks, stats.served_bytes);
    BOOL quiesced = stats.in_progress == 0 && stats.last_activity_ns && now - stats.last_activity_ns > kBootQuiesceNs;
    if ((served && quiesced) || now > deadline) {
      s2arm_journal("bootServed", served ? "passed" : "timeout", "\"servedBlocks\":%u,\"servedBytes\":%llu", stats.served_blocks,
                    (unsigned long long)stats.served_bytes);
      break;
    }
    usleep(50000);
  }
  s2arm_code_detach();
  S2ArmJitSession *session = self.jitSession;
  if (session) {
    BOOL completed = [session waitUntilFinished:kCompletionTimeout];
    s2arm_journal("jitDetach", completed && session.success ? "passed" : "incomplete", "\"debugged\":%d", S2ArmHostIsDebugged() ? 1 : 0);
    [session close];
    self.jitSession = nil;
  }
}

- (NSDictionary *)attachHelperWithPairing:(NSString *)pairing {
  if (![pairing isKindOfClass:NSString.class] || ![NSFileManager.defaultManager isReadableFileAtPath:pairing]) {
    return launchFail(@"jitPairingRequired", @"jit", @"A readable pairing file is required for the JIT helper.");
  }
  if (!S2ArmHostHasGetTaskAllow()) return launchFail(@"jitUnavailable", @"jit", @"This installation does not keep get-task-allow.");
  NSData *pairingData = [NSData dataWithContentsOfFile:pairing options:NSDataReadingMappedIfSafe error:nil];
  if (pairingData.length == 0) return launchFail(@"jitUnavailable", @"jit", @"The stored pairing file could not be read.");
  NSError *sessionError = nil;
  S2ArmJitSession *session = [[S2ArmJitSession alloc] initWithError:&sessionError];
  if (!session) return launchFail(@"jitUnavailable", @"jit", sessionError.localizedDescription);
  session.requiresCoreHandshake = YES;
  self.jitSession = session;
  [session startReader];
  NSError *launchError = nil;
  if (![session launchHelperWithPairingData:pairingData error:&launchError]) {
    [session close];
    self.jitSession = nil;
    return launchFail(@"jitUnavailable", @"jit", launchError.localizedDescription);
  }
  if (![session waitUntilConnected:kHelperConnectTimeout]) {
    [session close];
    self.jitSession = nil;
    return launchFail(@"jitUnavailable", @"jit", session.finalMessage.length ? session.finalMessage : @"The JIT helper did not connect.");
  }
  s2arm_journal("jitHelper", "connected", NULL);
  if (![session waitUntilAttached:kAttachTimeout]) {
    [session close];
    self.jitSession = nil;
    return launchFail(@"jitUnavailable", @"jit", session.finalMessage.length ? session.finalMessage : @"The JIT helper did not attach.");
  }
  s2arm_journal("jitHelper", "attached", NULL);
  return @{@"success" : @YES};
}

#pragma mark - in-game menu

// Main thread, once the engine started in its presented view controller.
- (void)attachSessionMenuTo:(UIViewController *)vc stop:(s2a_rb_guest_stop_fn)stop {
  self.engineViewController = vc;
  self.sessionMenu = [[S2ArmSessionMenu alloc] initWithViewController:vc
                                                              strings:self.menuStrings ?: @{}
                                                                 stop:^{
                                                                   s2arm_journal("menu", "quit", NULL);
                                                                   // The engine stops on its own queue; session_ended follows.
                                                                   if (stop) stop("rewindbox-menu");
                                                                 }];
  // Patch 0078: the frame-rate limit the player picks in the menu is in effect at once (the other settings still wait for the next start)
  __weak S2ArmEngineBridgePlugin *weakSelf = self;
  if (dlsym(RTLD_DEFAULT, S2A_RB_GUEST_SET_FPS_LIMIT)) {
    self.sessionMenu.applyNow = ^BOOL(NSString *setting, id value) { return [weakSelf applyLiveSetting:setting value:value]; };
  }
  [self.sessionMenu attach];
  s2arm_journal("menu", "attached", NULL);
  [self watchGameView:stop];
}

// Patch 0078 (engine): the limit changed during play. YES when the engine took it (from its next frame on).
- (BOOL)applyLiveSetting:(NSString *)setting value:(id)value {
  if (![setting isEqualToString:@"frameRateLimit"] || ![value isKindOfClass:NSString.class]) return NO;
  s2a_rb_guest_set_fps_limit_fn set = (s2a_rb_guest_set_fps_limit_fn)dlsym(RTLD_DEFAULT, S2A_RB_GUEST_SET_FPS_LIMIT);
  if (!set) return NO;
  int fps = [(NSString *)value intValue];
  int rc = set(fps);
  s2arm_journal("frameRate", rc == 0 ? "now" : "nextStart", "\"fps\":%d,\"rc\":%d", fps, rc);
  return rc == 0;
}

// The stored frame-rate choice, for a parked game that resumes: the engine read S2A_FPS once, when this process first started a game.
- (void)applyStoredFrameRateLimit {
  id value = S2ArmSettingsSnapshot()[@"frameRateLimit"];
  if (value) (void)[self applyLiveSetting:@"frameRateLimit" value:value];
}

#pragma mark - game view watch

// Main thread. Once a second while a game runs: the game view must stay presented. If it left the screen with no stop asked (IPA 771:
// the engine kept running behind RewindBox's launch dialog, which the player cannot close in a Switch 2 session), it is presented again at
// once on the visible window; if it cannot be for 5 checks running while RewindBox is in the foreground, the game is stopped properly
// (saves written, session_ended) and RewindBox goes back to its menu instead of staying stuck. Each case goes to the journal.
- (void)watchGameView:(s2a_rb_guest_stop_fn)stop {
  [self.viewWatch invalidate];
  self.viewStop = stop;
  self.viewLostTicks = 0;
  self.viewRestores = 0;
  self.viewStopAsked = NO;
  __weak S2ArmEngineBridgePlugin *weakSelf = self;
  self.viewWatch = [NSTimer timerWithTimeInterval:1.0 repeats:YES block:^(NSTimer *timer) { [weakSelf checkGameView]; }];
  [NSRunLoop.mainRunLoop addTimer:self.viewWatch forMode:NSRunLoopCommonModes];
}

- (void)unwatchGameView {
  [self.viewWatch invalidate];
  self.viewWatch = nil;
}

// Class names of a presentation chain, root first (journal only: no title, no path).
static NSString *S2ArmChainNames(UIViewController *root) {
  NSMutableArray<NSString *> *names = [NSMutableArray array];
  for (UIViewController *c = root; c && names.count < 6; c = c.presentedViewController) [names addObject:NSStringFromClass(c.class)];
  return [names componentsJoinedByString:@">"];
}

- (void)checkGameView {
  UIViewController *vc = self.engineViewController;
  if (!vc || self.viewStopAsked) return;
  // What is on screen of the game: the view controller itself, or the engine's own screen over it (saves, settings: a full-screen
  // presentation takes the presenter's view out of the window), so the window is read from the top of its chain
  UIViewController *shown = vc;
  while (shown.presentedViewController) shown = shown.presentedViewController;
  if (vc.isBeingPresented || vc.isBeingDismissed || shown.isBeingPresented || shown.isBeingDismissed) return;   // look again at the next check
  UIWindow *window = shown.view.window ?: vc.view.window;
  if (vc.presentingViewController && window && !window.isHidden) {
    self.viewLostTicks = 0;
    return;
  }
  // Only the foreground can show it again (in the background the view stays where it is until the app comes back)
  if (UIApplication.sharedApplication.applicationState != UIApplicationStateActive) return;
  UIViewController *presenter = vc.presentingViewController ? nil : S2ArmTopViewController();
  if (self.viewLostTicks == 0) {
    s2arm_journal("gameView", "lost", "\"presenting\":%d,\"window\":%d,\"windowHidden\":%d,\"top\":\"%s\",\"restores\":%lu",
                  vc.presentingViewController != nil, window != nil, window ? (int)window.isHidden : -1,
                  S2ArmChainNames(presenter.view.window.rootViewController).UTF8String, (unsigned long)self.viewRestores);
  }
  if (vc.presentingViewController) {
    // Still presented, but on a window that is hidden now (or in no window): take it back from there once, then present it again on the
    // visible window at a next check. Never more than that for a view that is still presented: the game is not stopped for it.
    if (window.isHidden && self.viewLostTicks == 0) [vc.presentingViewController dismissViewControllerAnimated:NO completion:nil];
    self.viewLostTicks = 1;
    return;
  }
  if (presenter.isBeingPresented || presenter.isBeingDismissed) return;   // its transition ends first: next check
  if (presenter && presenter != vc) {
    self.viewRestores++;
    self.viewLostTicks = 0;
    NSUInteger restores = self.viewRestores;
    NSString *on = NSStringFromClass(presenter.class);
    vc.modalPresentationStyle = UIModalPresentationFullScreen;
    [presenter presentViewController:vc animated:NO completion:^{
      s2arm_journal("gameView", "restored", "\"on\":\"%s\",\"restores\":%lu", on.UTF8String, (unsigned long)restores);
    }];
    return;
  }
  // Not presented and nowhere to present it for 5 checks running in the foreground: stop the game properly rather than leave the player stuck
  if (++self.viewLostTicks < 5) return;
  self.viewStopAsked = YES;
  s2arm_journal("gameView", "stopping", "\"restores\":%lu", (unsigned long)self.viewRestores);
  if (self.viewStop) self.viewStop("rewindbox-view-lost");   // session_ended follows: the dialog closes, the menu is back
}

// Main thread: the session is over (Quit from either menu, or an engine stop): remove the menu and the game view.
- (void)closeSessionViewWithCompletion:(dispatch_block_t)completion {
  [self.graphicsMonitor invalidate]; self.graphicsMonitor = nil;
  [self.graphicsOverlay removeFromSuperview]; self.graphicsOverlay = nil;
  [self unwatchGameView];
  [self.sessionMenu detach];
  self.sessionMenu = nil;
  UIViewController *vc = self.engineViewController;
  self.engineViewController = nil;
  if (vc.presentingViewController) {
    [vc.presentingViewController dismissViewControllerAnimated:NO completion:completion];
  } else {
    completion();
  }
}

#pragma mark - engine callbacks

// Patch 0010: Quit parked the session. The game view closes as for an end; the same game can resume in this process.
static void s2arm_session_parked(const char *reason, void *context) {
  S2ArmEngineBridgePlugin *self = (__bridge S2ArmEngineBridgePlugin *)context;
  s2arm_journal("sessionParked", "passed", NULL);
  NSString *why = reason ? @(reason) : @"";
  dispatch_async(dispatch_get_main_queue(), ^{
    NSString *gid = self.runningGameId;
    [self closeSessionViewWithCompletion:^{
      self.parkedGameId = gid;
      self.runningGameId = nil;
      NSString *saveFolder = self.saveFolder;
      self.saveFolder = nil;
      self.menuStrings = nil;
      if (saveFolder) dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ S2ArmLogSaveImport(saveFolder); });
      S2ArmPreparationGameRunning(NO);
      s2arm_journal("gameView", "closed", "\"parked\":true");
      dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ S2ArmExportRunningEngineLog(gid); });
      [self.channel invokeMethod:@"sessionEnded" arguments:@{@"code" : @(S2A_RB_ENDED_NORMAL), @"reason" : why, @"parked" : @YES}];
    }];
  });
}

static void s2arm_session_ended(int code, const char *reason, void *context) {
  S2ArmEngineBridgePlugin *self = (__bridge S2ArmEngineBridgePlugin *)context;
  self.parkedGameId = nil;   // an end (or a failed resume) leaves nothing to resume
  s2arm_journal("sessionEnded", code == S2A_RB_ENDED_NORMAL ? "normal" : "failed", "\"code\":%d", code);
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ S2ArmExportEngineLogs(); });
  NSString *why = reason ? @(reason) : @"";
  dispatch_async(dispatch_get_main_queue(), ^{
    [self closeSessionViewWithCompletion:^{
      self.runningGameId = nil;
      NSString *saveFolder = self.saveFolder;
      self.saveFolder = nil;
      self.menuStrings = nil;
      if (saveFolder) dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ S2ArmLogSaveImport(saveFolder); });
      S2ArmPreparationGameRunning(NO);
      s2arm_journal("gameView", "closed", "\"parked\":false");
      [self.channel invokeMethod:@"sessionEnded" arguments:@{@"code" : @(code), @"reason" : why}];
    }];
  });
}

// Whether `path` is `root` or inside it, after resolving symbolic links.
static BOOL S2ArmPathInside(NSString *path, NSString *root) {
  if (!path.isAbsolutePath || !root.length) return NO;
  NSString *resolved = path.stringByResolvingSymlinksInPath.stringByStandardizingPath;
  NSString *base = root.stringByResolvingSymlinksInPath.stringByStandardizingPath;
  return [resolved isEqualToString:base] || [resolved hasPrefix:[base stringByAppendingString:@"/"]];
}

// The engine reads the game's save from S2A_SAVE_FOLDER when the game starts and writes it back there when the game ends
// (S2Arm services SaveFolder.cs; an explicit environment value wins over its default, <docs>/SaveData, which is private
// here). RewindBox gives it Documents/S2Arm/Saves/<game>, visible in the Files app. A save the engine already wrote to the
// old private folder is copied once into an empty new one (the old copy stays where it was). Without a valid folder, the engine keeps its default.
static void S2ArmPrepareSaveFolder(NSString *folder, NSString *docs) {
  NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
  if (!folder.length || !S2ArmPathInside(folder, documents)) {
    const char *saveFolderEnvironment = "S2A_SAVE_FOLDER";
    unsetenv(saveFolderEnvironment);
    s2arm_journal("saveFolder", "default", NULL);
    return;
  }
  NSFileManager *files = NSFileManager.defaultManager;
  [files createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
  NSString *old = [docs stringByAppendingPathComponent:@"SaveData"];
  NSArray<NSString *> *oldEntries = [files contentsOfDirectoryAtPath:old error:nil] ?: @[];
  NSArray<NSString *> *newEntries = [files contentsOfDirectoryAtPath:folder error:nil] ?: @[];
  NSPredicate *visible = [NSPredicate predicateWithFormat:@"NOT (SELF BEGINSWITH '.')"];
  if ([oldEntries filteredArrayUsingPredicate:visible].count && ![newEntries filteredArrayUsingPredicate:visible].count) {
    BOOL moved = YES;
    for (NSString *name in [oldEntries filteredArrayUsingPredicate:visible]) {
      moved = [files copyItemAtPath:[old stringByAppendingPathComponent:name] toPath:[folder stringByAppendingPathComponent:name]
                              error:nil] && moved;
    }
    s2arm_journal("saveFolder", moved ? "migrated" : "migrationIncomplete", NULL);
  }
  int environmentStatus = setenv("S2A_SAVE_FOLDER", folder.fileSystemRepresentation, 1);
  if (environmentStatus == 0) {
    BOOL pending = [files fileExistsAtPath:[folder stringByAppendingPathComponent:@".rewindbox-import-pending"]];
    s2arm_journal("saveFolder", "documents", "\"importPending\":%s", pending ? "true" : "false");
  } else {
    s2arm_journal("saveFolder", "failed", "\"errno\":%d", errno);
  }
}

// Log only the guest's result, without storage paths, profile identifiers or file names.
static void S2ArmLogSaveImport(NSString *folder) {
  if (!folder.length) return;
  NSString *path = [folder stringByAppendingPathComponent:@".rewindbox-import-result"];
  NSFileManager *files = NSFileManager.defaultManager;
  BOOL pending = [files fileExistsAtPath:[folder stringByAppendingPathComponent:@".rewindbox-import-pending"]];
  NSDictionary *attributes = [files attributesOfItemAtPath:path error:nil];
  NSString *reported = nil;
  if ([attributes.fileType isEqual:NSFileTypeRegular] && attributes.fileSize <= 64) {
    reported = [[NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil]
        stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
  }
  if ([reported isEqualToString:@"applied"] && !pending) {
    s2arm_journal("saveImport", "applied", NULL);
  } else if (pending) {
    NSArray *reasons = @[@"unrecognized", @"ambiguousProfile", @"profileUnavailable", @"mountFailed", @"writeFailed"];
    BOOL failed = reported && [reasons containsObject:reported];
    s2arm_journal("saveImport", failed ? "failed" : "pending", "\"reason\":\"%s\"", failed ? reported.UTF8String : "unconfirmed");
  }
}

// The view controller the game is presented on: the top of the visible, normal-level window of the foreground application scene (the key
// window first). A transparent window above it (RewindBox's achievement text host, NeoPlay's overlay) or a hidden one never hosts the game:
// the game would leave the screen with that window. With no such window, the key window as before.
static UIViewController *S2ArmTopViewController(void) {
  NSMutableArray<UIWindow *> *windows = [NSMutableArray array];
  for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
    if (scene.activationState != UISceneActivationStateForegroundActive || ![scene isKindOfClass:UIWindowScene.class]) continue;
    if (![scene.session.role isEqualToString:UIWindowSceneSessionRoleApplication]) continue;
    for (UIWindow *window in ((UIWindowScene *)scene).windows) {
      if (window.isHidden || window.alpha <= 0 || window.windowLevel != UIWindowLevelNormal || !window.rootViewController) continue;
      if (window.isKeyWindow) [windows insertObject:window atIndex:0];
      else [windows addObject:window];
    }
  }
  UIViewController *top = windows.firstObject.rootViewController;
  if (!top) {
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
      if (scene.activationState != UISceneActivationStateForegroundActive || ![scene isKindOfClass:UIWindowScene.class]) continue;
      for (UIWindow *window in ((UIWindowScene *)scene).windows) {
        if (window.isKeyWindow) top = window.rootViewController;
      }
    }
  }
  while (top.presentedViewController) top = top.presentedViewController;
  return top;
}

@end
