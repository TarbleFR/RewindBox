// Host side of the embedded Switch 2 engine. Method channel neostation/s2arm_internal. See docs/s2arm-engine-bridge.md.
#import "S2ArmEngineBridgePlugin.h"
#import "S2ArmEngineLoaded.h"
#import "S2ArmGuestABI.h"
#import "S2ArmCodePages.h"
#import "S2ArmPackPlan.h"
#import "S2ArmJitSession.h"
#import "S2ArmGamePreparation.h"
#import "S2ArmLaunchJournal.h"

#import <UIKit/UIKit.h>
#import <dlfcn.h>

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
static UIViewController *S2ArmTopViewController(void);

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
@property(atomic, assign) BOOL launchStarted;   // one launch per process
@end

@implementation S2ArmEngineBridgePlugin

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar> *)registrar {
  FlutterMethodChannel *channel = [FlutterMethodChannel methodChannelWithName:kChannel binaryMessenger:registrar.messenger];
  S2ArmEngineBridgePlugin *instance = [S2ArmEngineBridgePlugin new];
  instance.channel = channel;
  instance.workQueue = dispatch_queue_create("com.neogamelab.neostation.s2arm.work", DISPATCH_QUEUE_SERIAL);
  [registrar addMethodCallDelegate:instance channel:channel];
}

- (void)handleMethodCall:(FlutterMethodCall *)call result:(FlutterResult)result {
  if ([call.method isEqualToString:@"status"]) {
    result([self status]);
    return;
  }
  if ([call.method isEqualToString:@"configureLaunchJournal"]) {
    NSString *path = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments[@"path"] : nil;
    result(@(path.isAbsolutePath && s2arm_journal_open(path.fileSystemRepresentation) == 0));
    return;
  }
  if ([call.method isEqualToString:@"detectExport"]) {
    NSString *folder = [call.arguments isKindOfClass:NSDictionary.class] ? call.arguments[@"exportFolder"] : nil;
    result(S2ArmDetectExport(folder ?: @""));
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
  result(FlutterMethodNotImplemented);
}

#pragma mark - status

- (NSDictionary *)status {
  NSOperatingSystemVersion os = NSProcessInfo.processInfo.operatingSystemVersion;
  BOOL enginePresent = S2ArmEnginePath().length && [NSFileManager.defaultManager fileExistsAtPath:S2ArmEnginePath()];
  BOOL ns2pro = NO;
  if (NSBundle.mainBundle.privateFrameworksPath.length) {
    ns2pro = [NSFileManager.defaultManager
        fileExistsAtPath:[NSBundle.mainBundle.privateFrameworksPath stringByAppendingPathComponent:@"NS2Pro.framework/NS2Pro"]];
  }
  return @{
    @"available" : @(enginePresent && os.majorVersion >= 18),
    @"enginePresent" : @(enginePresent),
    @"ns2proPresent" : @(ns2pro),
    @"iosMajor" : @(os.majorVersion),
    @"engineFloorMet" : @(os.majorVersion >= 18),            // S2Arm.app deployment target
    @"universalHandshake" : @(S2ArmRequiresCoreHandshake()),  // iOS 26+: the host drives commands 3/1/0
    @"getTaskAllow" : @(S2ArmHostHasGetTaskAllow()),
    @"debugged" : @(S2ArmHostIsDebugged()),
    @"helperPresent" : @(S2ArmFindHelperBundleIdentifier() != nil),
    @"systemDataPresent" : @(S2ArmShippedSystemData() != nil),
    @"directChain" : S2ArmShippedDirectChain() ?: [NSNull null],
    @"melonxCoreLoaded" : @(S2ArmMeloNXCoreLoaded()),
    @"engineLoaded" : @(rb_s2arm_engine_loaded() != 0),
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
  preparation.progress = ^(NSString *step, NSInteger index, NSInteger count, double fraction) {
    S2ArmEngineBridgePlugin *strongSelf = weakSelf;
    dispatch_async(dispatch_get_main_queue(), ^{
      [strongSelf.channel invokeMethod:kProgressMethod
                             arguments:@{@"step" : step, @"index" : @(index), @"count" : @(count), @"fraction" : @(fraction)}];
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
  if (![gid isKindOfClass:NSString.class] || ![images isKindOfClass:NSString.class] || ![moduleDir isKindOfClass:NSString.class] ||
      ![gameData isKindOfClass:NSString.class] || ![docs isKindOfClass:NSString.class]) {
    result(@{@"success" : @NO, @"error" : S2ArmErrorInvalidArguments});
    return;
  }
  if (self.launchStarted) {
    result(@{@"success" : @NO, @"error" : @"engineRestartRequired", @"diagnostic" : @"A Switch 2 game already ran in this process."});
    return;
  }
  // MeloNX's Core and this engine cannot share a process (two .NET runtimes). If MeloNX loaded, ask for a restart.
  if (S2ArmMeloNXCoreLoaded()) {
    s2arm_journal("launch", "refused", "\"reason\":\"melonxCoreLoaded\"");
    result(@{@"success" : @NO, @"error" : @"engineRestartRequired", @"diagnostic" : @"MeloNX ran in this session of RewindBox."});
    return;
  }
  self.launchStarted = YES;
  dispatch_async(self.workQueue, ^{
    NSDictionary *report = [self runLaunchWithGid:gid images:images moduleDir:moduleDir gameData:gameData docs:docs pairing:pairing];
    dispatch_async(dispatch_get_main_queue(), ^{ result(report); });
  });
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
      self.launchStarted = NO;
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
    uint64_t pool = plan.later_code_bytes + (16ull << 20);
    if (s2arm_code_prepare_pool(pool) != 0) {
      s2arm_journal("pool", "skipped", "\"bytes\":%llu", (unsigned long long)pool);   // launch still proceeds; later NROs may fail
    }
  }

  // Environment the engine's main sets, then the flag before the dlopen, then the dlopen (RTLD_NOW | RTLD_GLOBAL).
  setenv("DOTNET_GCSegmentSize", kGcSegmentSize.UTF8String, 0);
  setenv("MTL_SHADER_CACHE_SIZE", kShaderCacheSize.UTF8String, 0);
  rb_s2arm_engine_mark_loading();
  s2arm_journal("dlopen", "begin", NULL);
  void *engine = dlopen(enginePath.fileSystemRepresentation, RTLD_NOW | RTLD_GLOBAL);
  if (!engine) {
    return launchFail(@"engineLoadFailed", @"dlopen", @(dlerror() ?: "dlopen failed"));
  }
  s2arm_journal("dlopen", "passed", NULL);

  s2a_rb_guest_configure_fn configure = (s2a_rb_guest_configure_fn)dlsym(engine, S2A_RB_GUEST_CONFIGURE);
  s2a_rb_guest_make_view_controller_fn makeVC = (s2a_rb_guest_make_view_controller_fn)dlsym(engine, S2A_RB_GUEST_MAKE_VIEW_CONTROLLER);
  s2a_rb_guest_start_fn start = (s2a_rb_guest_start_fn)dlsym(engine, S2A_RB_GUEST_START);
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
                           dispatch_semaphore_signal(done);
                         }];
  });
  dispatch_semaphore_wait(done, DISPATCH_TIME_FOREVER);
  if (startRc != 0) return launchFail(@"engineStartFailed", @"start", startError);
  s2arm_journal("start", "passed", NULL);

  if (universal) [self detachAfterBootServed:&plan];
  s2arm_journal("launch", "running", "\"servedBlocks\":%u", ({ s2arm_code_stats s; s2arm_code_stats_get(&s); s.served_blocks; }));
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

#pragma mark - engine callbacks

static void s2arm_session_ended(int code, const char *reason, void *context) {
  S2ArmEngineBridgePlugin *self = (__bridge S2ArmEngineBridgePlugin *)context;
  s2arm_journal("sessionEnded", code == S2A_RB_ENDED_NORMAL ? "normal" : "failed", "\"code\":%d", code);
  dispatch_async(dispatch_get_main_queue(), ^{
    [self.channel invokeMethod:@"sessionEnded" arguments:@{@"code" : @(code), @"reason" : reason ? @(reason) : @""}];
  });
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
