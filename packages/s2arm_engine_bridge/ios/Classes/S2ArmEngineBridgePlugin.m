// Host side of the embedded Switch 2 engine. Method channel neostation/s2arm_internal. See docs/s2arm-engine-bridge.md.
#import "S2ArmEngineBridgePlugin.h"
#import "S2ArmEngineLoaded.h"
#import "S2ArmGuestABI.h"
#import "S2ArmCodePages.h"
#import "S2ArmPackPlan.h"
#import "S2ArmJitSession.h"
#import "S2ArmGamePreparation.h"
#import "S2ArmLaunchJournal.h"
#import "S2ArmSettings.h"
#import "S2ArmSessionMenu.h"

#import <UIKit/UIKit.h>
#import <dlfcn.h>
#import <errno.h>
#import <sys/clonefile.h>

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
static UIViewController *S2ArmTopViewController(void);
static BOOL S2ArmPathInside(NSString *path, NSString *root);
static void S2ArmPrepareSaveFolder(NSString *folder, NSString *docs);

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
@property(atomic, strong, nullable) S2ArmJitSession *jitSession;
@property(atomic, assign) BOOL engineLoaded;      // the engine was dlopen'd: one per process, no retry after this
@property(atomic, assign) BOOL launchInProgress;  // a launch attempt is running now
@property(nonatomic, copy, nullable) NSDictionary<NSString *, NSString *> *menuStrings;   // from Dart, for the in-game menu
@property(nonatomic, strong, nullable) UIViewController *engineViewController;   // presented while a game runs (main thread)
@property(nonatomic, strong, nullable) S2ArmSessionMenu *sessionMenu;             // RewindBox's in-game menu (main thread)
@property(nonatomic, copy, nullable) NSString *saveFolder;   // Documents/S2Arm/Saves/<game>, given to the engine
@property(atomic, copy, nullable) NSString *runningGameId;   // the title id of the game the engine was configured for
@property(atomic, copy, nullable) NSString *parkedGameId;    // patch 0010: Quit parked this game; it can resume in this process
@end

@implementation S2ArmEngineBridgePlugin

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar> *)registrar {
  FlutterMethodChannel *channel = [FlutterMethodChannel methodChannelWithName:kChannel binaryMessenger:registrar.messenger];
  S2ArmEngineBridgePlugin *instance = [S2ArmEngineBridgePlugin new];
  instance.channel = channel;
  instance.workQueue = dispatch_queue_create("com.neogamelab.neostation.s2arm.work", DISPATCH_QUEUE_SERIAL);
  [registrar addMethodCallDelegate:instance channel:channel];
  // The previous run's engine log (a crash ends the process before session_ended can copy it).
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ S2ArmExportEngineLogs(); });
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
  if (self.activePreparation) {
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
  self.activePreparation = preparation;
  dispatch_async(self.workQueue, ^{
    NSDictionary *report = [preparation run];
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
  dispatch_async(self.workQueue, ^{
    NSDictionary *report = resume ? [self resumeParkedGame:gid]
                                  : [self runLaunchWithGid:gid images:images moduleDir:moduleDir gameData:gameData docs:docs pairing:pairing];
    self.launchInProgress = NO;
    dispatch_async(dispatch_get_main_queue(), ^{ result(report); });
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
  S2ArmSettingsPrepareLaunch();   // settings changed while parked apply now (the rebuild reloads the graphics settings)
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
                           resumeRc = resume(error, sizeof error);
                           if (resumeRc != 0) {
                             resumeError = @(error);
                             [vc.presentingViewController dismissViewControllerAnimated:NO completion:nil];
                           } else [self attachSessionMenuTo:vc stop:stop];
                           dispatch_semaphore_signal(done);
                         }];
  });
  dispatch_semaphore_wait(done, DISPATCH_TIME_FOREVER);
  if (resumeRc != 0) return launchFail(@"engineStartFailed", @"resume", resumeError);
  self.parkedGameId = nil;
  s2arm_journal("resume", "passed", NULL);
  return @{@"success" : @YES, @"gid" : gid, @"stage" : @"running", @"resumed" : @YES};
}

static NSDictionary *launchFail(NSString *error, NSString *stage, NSString *detail) {
  s2arm_journal("launch", "failed", "\"stage\":\"%s\",\"error\":\"%s\"", stage.UTF8String, error.UTF8String);
  return @{@"success" : @NO, @"error" : error, @"stage" : stage, @"diagnostic" : detail ?: @""};
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
  S2ArmSettingsPrepareLaunch();   // the game language, and the engine's brief overlay that the in-game menu shows or hides
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
  self.runningGameId = gid;

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
                           if (startRc != 0) startError = @(error);
                           else [self attachSessionMenuTo:vc stop:stop];
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
  [self.sessionMenu attach];
  s2arm_journal("menu", "attached", NULL);
}

// Main thread: the session is over (Quit from either menu, or an engine stop): remove the menu and the game view.
- (void)closeSessionView {
  [self.sessionMenu detach];
  self.sessionMenu = nil;
  UIViewController *vc = self.engineViewController;
  self.engineViewController = nil;
  if (vc.presentingViewController) [vc.presentingViewController dismissViewControllerAnimated:NO completion:nil];
}

#pragma mark - engine callbacks

// Patch 0010: Quit parked the session. The game view closes as for an end; the same game can resume in this process.
static void s2arm_session_parked(const char *reason, void *context) {
  S2ArmEngineBridgePlugin *self = (__bridge S2ArmEngineBridgePlugin *)context;
  self.parkedGameId = self.runningGameId;
  s2arm_journal("sessionParked", "passed", NULL);
  NSString *why = reason ? @(reason) : @"";
  dispatch_async(dispatch_get_main_queue(), ^{
    [self closeSessionView];
    [self.channel invokeMethod:@"sessionEnded" arguments:@{@"code" : @(S2A_RB_ENDED_NORMAL), @"reason" : why, @"parked" : @YES}];
  });
}

static void s2arm_session_ended(int code, const char *reason, void *context) {
  S2ArmEngineBridgePlugin *self = (__bridge S2ArmEngineBridgePlugin *)context;
  self.parkedGameId = nil;   // an end (or a failed resume) leaves nothing to resume
  s2arm_journal("sessionEnded", code == S2A_RB_ENDED_NORMAL ? "normal" : "failed", "\"code\":%d", code);
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{ S2ArmExportEngineLogs(); });
  NSString *why = reason ? @(reason) : @"";
  dispatch_async(dispatch_get_main_queue(), ^{
    [self closeSessionView];
    [self.channel invokeMethod:@"sessionEnded" arguments:@{@"code" : @(code), @"reason" : why}];
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
  setenv("S2A_SAVE_FOLDER", folder.fileSystemRepresentation, 1);
  s2arm_journal("saveFolder", "documents", NULL);
}

static UIViewController *S2ArmTopViewController(void) {
  UIWindow *keyWindow = nil;
  for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
    if (scene.activationState == UISceneActivationStateForegroundActive && [scene isKindOfClass:UIWindowScene.class]) {
      for (UIWindow *window in ((UIWindowScene *)scene).windows) {
        if (window.isKeyWindow) keyWindow = window;
      }
    }
  }
  UIViewController *top = keyWindow.rootViewController;
  while (top.presentedViewController) top = top.presentedViewController;
  return top;
}

@end
