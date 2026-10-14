// Simulator probe of the embedded libretro session.
//
// Runs NeoStation's real LibretroSession (presentation, emulation thread,
// Metal presenter, OpenGL ES and Vulkan renderers, teardown) in the iOS
// Simulator with real cores: PPSSPP and Azahar from the pinned buildbot
// artifact, and the NeoTest core of test/libretro_host. Each scenario of
// probe-config.json (in the app bundle) launches a game the way the plugin
// does, lets it run, closes it like "Quit game" and records the launch
// result, the timings, the session journal and the core log.
//
// Results: Documents/probe.json once every scenario ran. Progress:
// Documents/probe-progress.log, written line by line as it happens, so a
// process that dies leaves the step it died in (with the session journal
// in Documents/Libretro/Logs).
//
// Like the plugin, the probe reserves PPSSPP's memory window right after
// launch (looked up with dlsym: older bridge sources have no reservation).
// A scenario with "crowdWindow" first takes the scratchpad slot of every
// base PPSSPP probes (base + 0x10000, 16 KiB, every 8 MiB from 4 GiB) that
// is still free, so no base of the window is usable unless reserved
// beforehand: the state of the iPhone on 10 October 2026 ("Failed finding
// a memory base"), while the holes between the slots still take the
// allocations made meanwhile, as the iPhone's lower holes do.
#import <UIKit/UIKit.h>

#import "LibretroSession.h"

#ifdef NEOSTATION_SHADER_SESSION_PROBE
#import "LibretroFrontendMenu.h"
#import "LibretroMetalPresenter.h"
#import "LibretroSlangShaders.h"
#import <neo_shader_kit/NeoShaderCatalog.h>
#import <neo_shader_kit/NeoShaderStorage.h>
#import <neo_shader_kit/NeoSlangRenderer.h>
#import <objc/runtime.h>
#endif

#include <dlfcn.h>
#include <fcntl.h>
#include <mach/mach.h>
#include <unistd.h>

static NSString *DocumentsPath(NSString *component) {
  NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
  return component.length > 0 ? [documents stringByAppendingPathComponent:component] : documents;
}

static void Progress(NSString *format, ...) NS_FORMAT_FUNCTION(1, 2);
static void Progress(NSString *format, ...) {
  va_list arguments;
  va_start(arguments, format);
  NSString *line = [[NSString alloc] initWithFormat:format arguments:arguments];
  va_end(arguments);
  NSString *stamped = [NSString stringWithFormat:@"%.3f %@\n", CFAbsoluteTimeGetCurrent(), line];
  NSData *data = [stamped dataUsingEncoding:NSUTF8StringEncoding];
  int descriptor = open(DocumentsPath(@"probe-progress.log").fileSystemRepresentation,
                        O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
  if (descriptor >= 0) {
    write(descriptor, data.bytes, data.length);
    close(descriptor);
  }
  NSLog(@"[probe] %@", line);
}

static NSArray<NSString *> *Tail(NSArray *lines, NSUInteger count) {
  if (![lines isKindOfClass:NSArray.class]) return @[];
  if (lines.count <= count) return lines;
  return [lines subarrayWithRange:NSMakeRange(lines.count - count, count)];
}

static NSString *ReadText(NSString *path) {
  return [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil] ?: @"";
}

/// A JSON file the session wrote, NSNull when absent or unreadable.
static id ReadJSON(NSString *path) {
  NSData *data = [NSData dataWithContentsOfFile:path];
  id object = data != nil ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
  return object ?: NSNull.null;
}

#ifdef NEOSTATION_SHADER_SESSION_PROBE
// Test-only observation of the actual game's CAMetalDrawable. It adds a
// readback to the presenter's already encoded frame, before that same
// command buffer is committed/presented. No substitute shader renderer or
// synthetic frame is used. Each captured PNG therefore contains the image
// the running session actually sent to its display layer.
typedef void (^ProbeFrameCapture)(NSDictionary *observation);
static ProbeFrameCapture sCaptureNextFrame;
static NSString *sCaptureName;
static NSUInteger sCaptureGeneration;
static NSString *sShortDownload;
static NSMutableArray<NSString *> *sFixtureDownloadPaths;
static BOOL sOfficialCatalog;
static __thread BOOL sEncodingDrawable;
typedef NSArray *(*ProbeEncodeFrame)(id, SEL, id<MTLCommandBuffer>, id<MTLTexture>, NSArray *, id<MTLTexture>,
                                    unsigned, unsigned, BOOL);
static ProbeEncodeFrame sOriginalEncodeFrame;
typedef void (*ProbeDrawTexture)(id, SEL, id<MTLTexture>, unsigned, unsigned, BOOL, NSInteger, dispatch_block_t);
static ProbeDrawTexture sOriginalDrawTexture;

static void ObserveDrawableDraw(id presenter, SEL selector, id<MTLTexture> texture, unsigned width,
                                unsigned height, BOOL flipped, NSInteger slot, dispatch_block_t completion) {
  BOOL before = sEncodingDrawable;
  sEncodingDrawable = YES;
  sOriginalDrawTexture(presenter, selector, texture, width, height, flipped, slot, completion);
  sEncodingDrawable = before;
}

static NSArray *CaptureEncodedFrame(id presenter, SEL selector, id<MTLCommandBuffer> buffer,
                                    id<MTLTexture> target, NSArray *screens, id<MTLTexture> texture,
                                    unsigned width, unsigned height, BOOL flipped) {
  NSArray *mappings = sOriginalEncodeFrame(presenter, selector, buffer, target, screens, texture, width, height, flipped);
  // The menu also calls this encoder for its offscreen timing measurement.
  // Only drawTexture acquires/presents a CAMetalDrawable; those measurements
  // must not consume a request for evidence from the actual game display.
  if (!sEncodingDrawable) return mappings;
  ProbeFrameCapture capture = nil;
  NSString *name = nil;
  @synchronized(LibretroMetalPresenter.class) {
    capture = sCaptureNextFrame;
    name = sCaptureName;
    sCaptureNextFrame = nil;
  }
  if (capture == nil) return mappings;
  NSUInteger rowBytes = ((target.width * 4 + 255) / 256) * 256;
  id<MTLBuffer> readback = [target.device newBufferWithLength:rowBytes * target.height
                                                    options:MTLResourceStorageModeShared];
  id<MTLBlitCommandEncoder> blit = readback != nil ? [buffer blitCommandEncoder] : nil;
  if (blit == nil) {
    dispatch_async(dispatch_get_main_queue(), ^{ capture(@{@"captureError": @"readback allocation"}); });
    return mappings;
  }
  [blit copyFromTexture:target sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0)
             sourceSize:MTLSizeMake(target.width, target.height, 1) toBuffer:readback destinationOffset:0
    destinationBytesPerRow:rowBytes destinationBytesPerImage:rowBytes * target.height];
  [blit endEncoding];
  [buffer addCompletedHandler:^(id<MTLCommandBuffer> completed) {
    NSMutableDictionary *observation = [@{@"drawable": @YES,
                                         @"gpuCompleted": completed.status == MTLCommandBufferStatusCompleted ? @YES : @NO,
                                         @"width": @(target.width), @"height": @(target.height),
                                         @"format": @(target.pixelFormat)} mutableCopy];
    if (completed.error != nil) observation[@"gpuError"] = completed.error.description;
    NSMutableArray *samples = [NSMutableArray array];
    const uint8_t *pixels = readback.contents;
    for (NSValue *value in mappings) {
      LibretroScreenMapping mapping;
      [value getValue:&mapping size:sizeof(mapping)];
      if (mapping.output.w <= 0 || mapping.output.h <= 0) continue;
      NSUInteger x = MIN(target.width - 1, (NSUInteger)((mapping.output.x + mapping.output.w * 0.5) * target.width));
      NSUInteger y = MIN(target.height - 1, (NSUInteger)((mapping.output.y + mapping.output.h * 0.5) * target.height));
      const uint8_t *pixel = pixels + y * rowBytes + x * 4;
      [samples addObject:@[@(pixel[2]), @(pixel[1]), @(pixel[0]), @(pixel[3])]];
    }
    observation[@"screenCentresRGBA"] = samples;
    // Sample each actual game rectangle, including off-centre pixels:
    // CRT curvature/scanlines are not established by its centre alone.
    NSMutableArray *grids = [NSMutableArray array];
    for (NSValue *value in mappings) {
      LibretroScreenMapping mapping;
      [value getValue:&mapping size:sizeof(mapping)];
      if (mapping.output.w <= 0 || mapping.output.h <= 0) continue;
      NSMutableArray *grid = [NSMutableArray array];
      for (NSUInteger gy = 0; gy < 16; gy++) for (NSUInteger gx = 0; gx < 16; gx++) {
        NSUInteger x = MIN(target.width - 1, (NSUInteger)((mapping.output.x + mapping.output.w * (gx + 0.5) / 16) * target.width));
        NSUInteger y = MIN(target.height - 1, (NSUInteger)((mapping.output.y + mapping.output.h * (gy + 0.5) / 16) * target.height));
        const uint8_t *pixel = pixels + y * rowBytes + x * 4;
        [grid addObject:@[@(pixel[2]), @(pixel[1]), @(pixel[0])]];
      }
      [grids addObject:grid];
    }
    observation[@"screenGridsRGB"] = grids;
    CGColorSpaceRef colour = CGColorSpaceCreateDeviceRGB();
    CGContextRef context = CGBitmapContextCreate(readback.contents, target.width, target.height, 8, rowBytes, colour,
                                                kCGBitmapByteOrder32Little | kCGImageAlphaPremultipliedFirst);
    CGImageRef cgImage = context != NULL ? CGBitmapContextCreateImage(context) : NULL;
    NSData *png = cgImage != NULL ? UIImagePNGRepresentation([UIImage imageWithCGImage:cgImage]) : nil;
    NSString *directory = DocumentsPath(@"ShaderFrames");
    [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *filename = [name stringByAppendingString:@".png"];
    if ([png writeToFile:[directory stringByAppendingPathComponent:filename] atomically:YES]) observation[@"png"] = filename;
    if (cgImage != NULL) CGImageRelease(cgImage);
    if (context != NULL) CGContextRelease(context);
    CGColorSpaceRelease(colour);
    dispatch_async(dispatch_get_main_queue(), ^{ capture(observation); });
  }];
  return mappings;
}

static void PrepareShaderObservation(void) {
  NSString *fixtures = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"ShaderFixtures"];
  [[NeoShaderCatalogManager sharedManager] setCatalogDirectory:fixtures];
  sOfficialCatalog = [NSFileManager.defaultManager fileExistsAtPath:[fixtures stringByAppendingPathComponent:@"official"]];
  sFixtureDownloadPaths = [NSMutableArray array];
  if (sOfficialCatalog) {
    // Observe the production loader, without substituting its transport,
    // response bytes, catalog, revision or dependency list.
    NeoShaderStorage *storage = LibretroSlangStorage();
    SEL selector = NSSelectorFromString(@"effectiveLoader");
    NeoShaderDataLoader loader = ((NeoShaderDataLoader (*)(id, SEL))[storage methodForSelector:selector])(storage, selector);
    NSString *base = [NSURL URLWithString:LibretroSlangCatalog().rawBaseURL].path;
    storage.dataLoader = ^(NSURL *url, void (^completion)(NSData *, NSInteger, NSError *)) {
      NSString *path = [[url.path substringFromIndex:base.length] stringByRemovingPercentEncoding];
      while ([path hasPrefix:@"/"]) path = [path substringFromIndex:1];
      @synchronized(LibretroMetalPresenter.class) { [sFixtureDownloadPaths addObject:path]; }
      loader(url, completion);
    };
  } else {
  LibretroSlangStorage().dataLoader = ^(NSURL *url, void (^completion)(NSData *, NSInteger, NSError *)) {
    NSString *path = [[url.path substringFromIndex:@"/session/".length] stringByRemovingPercentEncoding];
    NSData *data = [NSData dataWithContentsOfFile:[fixtures stringByAppendingPathComponent:path]];
    @synchronized(LibretroMetalPresenter.class) { [sFixtureDownloadPaths addObject:path]; }
    if ([path isEqualToString:sShortDownload] && data.length > 0) data = [data subdataWithRange:NSMakeRange(0, data.length - 1)];
    completion(data, data != nil ? 200 : 404, nil);
  };
  }
  SEL selector = NSSelectorFromString(@"encodeFrameOnBuffer:target:screens:texture:width:height:flipped:");
  Method method = class_getInstanceMethod(LibretroMetalPresenter.class, selector);
  sOriginalEncodeFrame = (ProbeEncodeFrame)method_getImplementation(method);
  method_setImplementation(method, (IMP)CaptureEncodedFrame);
  selector = NSSelectorFromString(@"drawTexture:width:height:flipped:uploadSlot:completion:");
  method = class_getInstanceMethod(LibretroMetalPresenter.class, selector);
  sOriginalDrawTexture = (ProbeDrawTexture)method_getImplementation(method);
  method_setImplementation(method, (IMP)ObserveDrawableDraw);
}

static LibretroMenuRow *MenuRowWithIdentifier(LibretroMenuPage *page, NSString *identifier) {
  for (LibretroMenuSection *section in page.builder != nil ? page.builder() : @[]) {
    for (LibretroMenuRow *row in section.rows) {
      if ([row.identifier isEqualToString:identifier]) return row;
    }
  }
  return nil;
}

static void CaptureNextGameFrame(LibretroSession *session, NSString *name, ProbeFrameCapture completion) {
  // CAMetalDrawable textures are display-only by default. The observation
  // app enables readback; the NeoStation product keeps its normal setting.
  CAMetalLayer *layer = [session valueForKey:@"metalLayer"];
  layer.framebufferOnly = NO;
  __block BOOL answered = NO;
  ProbeFrameCapture once = ^(NSDictionary *frame) {
    if (answered) return;
    answered = YES;
    LibretroMetalPresenter *presenter = [session valueForKey:@"presenter"];
    id<LibretroFrontendMenuHost> host = (id<LibretroFrontendMenuHost>)session;
    NSMutableDictionary *observation = [frame mutableCopy];
    observation[@"active"] = presenter.activePresetIdentifier ?: @"";
    observation[@"failure"] = host.lastShaderFailureCode ?: @"";
    observation[@"textureBytes"] = @(host.slangTextureBytes);
    observation[@"passes"] = @(host.activeSlangProgram.passCount);
    observation[@"gameKey"] = host.gameKey;
    observation[@"frontend"] = [host.frontendStore snapshotForConsole:host.console];
    observation[@"recovery"] = ReadJSON(DocumentsPath(@"Libretro/Config/Frontend/shader-attempts.json"));
    completion(observation);
  };
  NSUInteger generation;
  @synchronized(LibretroMetalPresenter.class) {
    generation = ++sCaptureGeneration;
    sCaptureNextFrame = once;
    sCaptureName = name;
  }
  // In-game menus pause the core. Use the session's normal redraw request,
  // on its emulation thread, to observe the displayed paused-game image.
  SEL redraw = NSSelectorFromString(@"requestRedraw");
  ((void (*)(id, SEL))[session methodForSelector:redraw])(session, redraw);
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 5 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
    @synchronized(LibretroMetalPresenter.class) {
      if (sCaptureGeneration == generation) sCaptureNextFrame = nil;
    }
    once(@{@"captureError": @"no game drawable in 5 seconds"});
  });
}
#endif

/// PPSSPP's probe (Core/MemMap.cpp): bases from 4 GiB, below this limit, in
/// 8 MiB steps; the scratchpad view at base + 0x10000.
static const uint64_t kProbeBaseMinimum = 0x100000000ull;
static const uint64_t kProbeBaseLimit = 0x17FFF0000ull;
static const uint64_t kProbeBaseStride = 0x800000ull;
static const uint64_t kScratchpadOffset = 0x10000ull;
static const uint64_t kScratchpadSize = 0x4000ull;

/// Takes every free scratchpad slot of the window. Returns the slots taken.
static NSArray<NSNumber *> *CrowdWindow(void) {
  NSMutableArray<NSNumber *> *taken = [NSMutableArray array];
  for (uint64_t base = kProbeBaseMinimum; base < kProbeBaseLimit; base += kProbeBaseStride) {
    vm_address_t slot = (vm_address_t)(base + kScratchpadOffset);
    if (vm_allocate(mach_task_self(), &slot, (vm_size_t)kScratchpadSize, VM_FLAGS_FIXED) != KERN_SUCCESS) continue;
    vm_protect(mach_task_self(), slot, (vm_size_t)kScratchpadSize, FALSE, VM_PROT_NONE);
    [taken addObject:@((uint64_t)slot)];
  }
  return taken;
}

static void ReleaseCrowd(NSArray<NSNumber *> *taken) {
  for (NSNumber *slot in taken) {
    vm_deallocate(mach_task_self(), (vm_address_t)slot.unsignedLongLongValue, (vm_size_t)kScratchpadSize);
  }
}

/// Evidence only: the regions mapped where PPSSPP's scratchpad slots lie,
/// as [address, size, user tag (VM_MEMORY_*), protection]. Compared before
/// and after the boot, they name the mapping that left a base to PPSSPP.
static NSArray<NSArray<NSNumber *> *> *WindowRegions(void) {
  NSMutableArray<NSArray<NSNumber *> *> *regions = [NSMutableArray array];
  vm_address_t address = (vm_address_t)kProbeBaseMinimum;
  const uint64_t end = kProbeBaseLimit + kScratchpadOffset + kScratchpadSize;
  for (unsigned guard = 0; guard < 65536 && address < end; guard++) {
    vm_size_t size = 0;
    natural_t depth = 0;
    vm_region_submap_info_data_64_t info;
    mach_msg_type_number_t count = VM_REGION_SUBMAP_INFO_COUNT_64;
    if (vm_region_recurse_64(mach_task_self(), &address, &size, &depth, (vm_region_recurse_info_t)&info, &count) !=
            KERN_SUCCESS ||
        size == 0 || address >= end) {
      break;
    }
    [regions addObject:@[ @((uint64_t)address), @((uint64_t)size), @(info.user_tag), @(info.protection) ]];
    address += size;
  }
  return regions;
}

/// The bridge's reservation report, when these sources have one.
static NSString *ReservationReport(void) {
  NSString *(*report)(void) = (NSString * (*)(void)) dlsym(RTLD_DEFAULT, "LibretroPPSSPPReservationReport");
  return report != NULL ? report() : @"no reservation in these sources";
}

@interface ProbeAppDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end

@implementation ProbeAppDelegate {
  NSDictionary *_config;
  NSArray<NSDictionary *> *_scenarios;
  NSMutableArray<NSDictionary *> *_results;
  NSUInteger _index;
  LibretroSession *_session;
  NSUInteger _generation;
}

- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  UIViewController *root = [UIViewController new];
  root.view.backgroundColor = UIColor.blackColor;
  self.window.rootViewController = root;
  [self.window makeKeyAndVisible];
  [NSFileManager.defaultManager removeItemAtPath:DocumentsPath(@"probe-progress.log") error:nil];
  [NSFileManager.defaultManager removeItemAtPath:DocumentsPath(@"probe.json") error:nil];
  NSString *configPath = [NSBundle.mainBundle pathForResource:@"probe-config" ofType:@"json"];
  NSData *configData = configPath != nil ? [NSData dataWithContentsOfFile:configPath] : nil;
  id config = configData != nil ? [NSJSONSerialization JSONObjectWithData:configData options:0 error:nil] : nil;
  _config = [config isKindOfClass:NSDictionary.class] ? config : @{};
  _scenarios = [_config[@"scenarios"] isKindOfClass:NSArray.class] ? _config[@"scenarios"] : @[];
  _results = [NSMutableArray array];
  [self prepareDirectories];
#ifdef NEOSTATION_SHADER_SESSION_PROBE
  for (NSDictionary *scenario in _scenarios) {
    if (scenario[@"shaders"] != nil) {
      PrepareShaderObservation();
      break;
    }
  }
#endif
  Progress(@"probe started: %lu scenarios, source %@", (unsigned long)_scenarios.count, _config[@"source"] ?: @"?");
  // As LibretroInternalBridgePlugin does once the plugins are registered.
  dispatch_async(dispatch_get_main_queue(), ^{
    BOOL (*reserve)(void) = (BOOL (*)(void))dlsym(RTLD_DEFAULT, "LibretroPPSSPPReserveWindow");
    if (reserve != NULL) reserve();
    Progress(@"PPSSPP window at launch: %@", ReservationReport());
  });
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
    [self runNext];
  });
  return YES;
}

/// The plugin's layout: Documents/Libretro/{System,Saves,States,Config,...},
/// with the bundled system files (PPSSPP's assets) copied into System.
- (void)prepareDirectories {
  NSFileManager *files = NSFileManager.defaultManager;
  for (NSString *name in @[ @"System", @"Saves", @"States", @"Config", @"Config/Frontend", @"Cheats", @"Skins", @"Logs" ]) {
    [files createDirectoryAtPath:[DocumentsPath(@"Libretro") stringByAppendingPathComponent:name]
        withIntermediateDirectories:YES
                         attributes:nil
                              error:nil];
  }
  NSString *bundled = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"LibretroSystem"];
  NSString *system = DocumentsPath(@"Libretro/System");
  for (NSString *entry in [files contentsOfDirectoryAtPath:bundled error:nil]) {
    NSString *target = [system stringByAppendingPathComponent:entry];
    if (![files fileExistsAtPath:target]) {
      [files copyItemAtPath:[bundled stringByAppendingPathComponent:entry] toPath:target error:nil];
    }
  }
}

- (LibretroSessionConfiguration *)configurationForScenario:(NSDictionary *)scenario {
  NSString *core = scenario[@"core"];
  NSString *frameworks = NSBundle.mainBundle.privateFrameworksPath;
  NSString *name = [core stringByAppendingString:@"_libretro"];
  LibretroSessionConfiguration *configuration = [LibretroSessionConfiguration new];
  configuration.corePath = [frameworks stringByAppendingPathComponent:
                                           [NSString stringWithFormat:@"%@.framework/%@", name, name]];
  configuration.contentPath = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:scenario[@"content"]];
  configuration.gameTitle = scenario[@"name"];
  configuration.console = scenario[@"console"];
  configuration.consoleName = scenario[@"consoleName"] ?: @"";
  configuration.gameKey = [@"probe/" stringByAppendingString:[scenario[@"content"] lastPathComponent]];
  configuration.systemDirectory = DocumentsPath(@"Libretro/System");
  configuration.saveDirectory = DocumentsPath(@"Libretro/Saves");
  configuration.stateDirectory = DocumentsPath(@"Libretro/States");
  configuration.optionsDirectory = DocumentsPath(@"Libretro/Config");
  configuration.cheatsDirectory = DocumentsPath(@"Libretro/Cheats");
  NSString *caches = NSSearchPathForDirectoriesInDomains(NSCachesDirectory, NSUserDomainMask, YES).firstObject;
  configuration.cacheDirectory = [caches stringByAppendingPathComponent:@"Libretro"];
  configuration.skinsDirectory = DocumentsPath(@"Libretro/Skins");
  configuration.frontendDirectory = DocumentsPath(@"Libretro/Config/Frontend");
  configuration.consoleGeometry = _config[@"consoleGeometry"] ?: @{};
  configuration.uiLocale = @"en";
  configuration.retroLanguage = 0;
  // Labels fall back to their keys: the probe checks behaviour, not text.
  configuration.uiText = @{};
  configuration.optionDefaults = scenario[@"optionDefaults"] ?: @{};
  configuration.noJitOverrides = scenario[@"noJitOverrides"] ?: @{};
  configuration.lockedOptions = scenario[@"lockedOptions"] ?: @{};
  configuration.coreSettings = @[];
  configuration.achievementsAllowed = NO;
  configuration.preferredHardwareContext = [scenario[@"preferredHardwareContext"] unsignedIntValue];
  // Present since the session journal; absent from older sources.
  SEL logs = NSSelectorFromString(@"setLogsDirectory:");
  if ([configuration respondsToSelector:logs]) {
    ((void (*)(id, SEL, NSString *))[configuration methodForSelector:logs])(configuration, logs,
                                                                            DocumentsPath(@"Libretro/Logs"));
  }
  // Internal resolution (Build 455): the rules Dart sends and the core id
  // naming Config/Resolution/<core>.json; absent from older sources.
  SEL coreId = NSSelectorFromString(@"setCoreId:");
  if ([configuration respondsToSelector:coreId]) {
    ((void (*)(id, SEL, NSString *))[configuration methodForSelector:coreId])(configuration, coreId, core ?: @"");
  }
  SEL rules = NSSelectorFromString(@"setResolutionRules:");
  if ([configuration respondsToSelector:rules] && [_config[@"resolution"] isKindOfClass:NSDictionary.class]) {
    ((void (*)(id, SEL, NSDictionary *))[configuration methodForSelector:rules])(configuration, rules,
                                                                                  _config[@"resolution"]);
  }
  return configuration;
}

/// Size of the frames the core produces now, [width, height]; [0, 0] for a
/// tree without the measure.
static NSArray<NSNumber *> *ProducedFrameSize(LibretroSession *session) {
  SEL selector = NSSelectorFromString(@"producedFrameSize");
  if (![session respondsToSelector:selector]) return @[ @0, @0 ];
  CGSize size = ((CGSize(*)(id, SEL))[session methodForSelector:selector])(session, selector);
  return @[ @((NSInteger)size.width), @((NSInteger)size.height) ];
}

/// The in-game menu's resolution choice, through the same session call.
static BOOL SelectResolution(LibretroSession *session, NSString *value, BOOL game) {
  SEL selector = NSSelectorFromString(@"selectInternalResolution:forGame:");
  if (![session respondsToSelector:selector]) return NO;
  return ((BOOL(*)(id, SEL, NSString *, BOOL))[session methodForSelector:selector])(session, selector, value, game);
}

static NSDictionary *ResolutionState(LibretroSession *session) {
  SEL selector = NSSelectorFromString(@"internalResolutionState");
  if (![session respondsToSelector:selector]) return nil;
  return ((NSDictionary * (*)(id, SEL))[session methodForSelector:selector])(session, selector);
}

- (void)stopScenario:(NSMutableDictionary *)result session:(LibretroSession *)session {
  UIViewController *root = self.window.rootViewController;
  result[@"activeBeforeStop"] = @(session.active);
  result[@"presentedBeforeStop"] = @(root.presentedViewController != nil);
  Progress(@"%@: stop requested", result[@"name"]);
  CFAbsoluteTime stopStart = CFAbsoluteTimeGetCurrent();
  __weak ProbeAppDelegate *weakSelf = self;
  [session stopWithCompletion:^{
    result[@"stopped"] = @YES;
    result[@"stopSeconds"] = @(CFAbsoluteTimeGetCurrent() - stopStart);
    result[@"presentedAfterStop"] = @(root.presentedViewController != nil);
    Progress(@"%@: stopped", result[@"name"]);
#ifdef NEOSTATION_SHADER_SESSION_PROBE
    if (result[@"shaderSteps"] != nil) {
      [weakSelf verifyShaderRequestsAfterStop:result session:session];
      return;
    }
#endif
    [weakSelf finishScenario:result session:session];
  }];
}

#ifdef NEOSTATION_SHADER_SESSION_PROBE
- (void)pollMenuShaderApplication:(LibretroMenuPage *)page
                            step:(NSMutableDictionary *)step
                         session:(LibretroSession *)session
                     applyInvoked:(BOOL)applyInvoked
                        deadline:(CFAbsoluteTime)deadline
                      completion:(void (^)(BOOL, NSString *))completion {
  id<LibretroFrontendMenuHost> host = (id<LibretroFrontendMenuHost>)session;
  NSString *preset = step[@"preset"];
  NSString *identifier = LibretroSlangShaderIdentifier(preset);
  if (!applyInvoked) {
    LibretroMenuRow *apply = MenuRowWithIdentifier(page, @"libretro-shader-entry-apply");
    if (apply != nil && apply.enabled && apply.action != nil) {
      NeoShaderInstallation *installation = [LibretroSlangStorage() installationWithIdentifier:preset];
      step[@"installationRegistered"] = installation != nil ? @YES : @NO;
      step[@"installationSuccess"] = installation != nil && [LibretroSlangStorage() installationIsComplete:installation] ? @YES : @NO;
      step[@"menuApplyHandler"] = @YES;
      step[@"menuPresetCheckedBeforeApply"] = @(apply.checked);
      apply.action(page);
      applyInvoked = YES;
    }
  }
  if (applyInvoked) {
    LibretroMetalPresenter *presenter = [session valueForKey:@"presenter"];
    LibretroSettingScope scope = LibretroSettingScopeDefault;
    id stored = [host.frontendStore valueForKey:LibretroSettingShaderPreset console:host.console game:host.gameKey scope:&scope];
    id enabled = [host.frontendStore valueForKey:LibretroSettingShaderEnabled console:host.console game:host.gameKey scope:NULL];
    if ([presenter.activePresetIdentifier isEqualToString:identifier] && host.activeSlangProgram != nil &&
        [stored isEqual:identifier] && [enabled isKindOfClass:NSNumber.class] && [enabled boolValue]) {
      step[@"menuStoredScope"] = scope == LibretroSettingScopeGame ? @"game" : @"console";
      step[@"menuStoredPreset"] = stored;
      step[@"menuStoredEnabled"] = @YES;
      NSUInteger before = [step[@"menuDownloadStart"] unsignedIntegerValue];
      @synchronized(LibretroMetalPresenter.class) {
        if (sFixtureDownloadPaths.count >= before) {
          step[@"menuDownloadedPaths"] = [sFixtureDownloadPaths subarrayWithRange:NSMakeRange(before, sFixtureDownloadPaths.count - before)];
        }
      }
      // These preferences are solely the existing menu's completion writes.
      // The probe observes them before it records the drawable pixels.
      completion(YES, host.lastShaderFailureCode);
      return;
    }
  }
  if (CFAbsoluteTimeGetCurrent() >= deadline) {
    step[@"menuFlowTimeout"] = @YES;
    completion(NO, host.lastShaderFailureCode ?: @"MENU_FLOW_TIMEOUT");
    return;
  }
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.1 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
    [self pollMenuShaderApplication:page step:step session:session applyInvoked:applyInvoked deadline:deadline completion:completion];
  });
}

- (void)applyShaderThroughMenu:(NSMutableDictionary *)step
                      session:(LibretroSession *)session
                   completion:(void (^)(BOOL, NSString *))completion {
  NSString *preset = step[@"preset"];
  NeoShaderStorage *storage = LibretroSlangStorage();
  // A fresh installation is a fixture precondition, not a replacement for
  // the download action: the actual entry handler must fetch verified bytes.
  [storage removeInstallationWithIdentifier:preset error:nil];
  NeoShaderCatalog *catalog = LibretroSlangCatalog();
  BOOL filesAbsent = YES;
  for (NeoShaderCatalogFile *file in [catalog entryWithIdentifier:preset].files) {
    NSString *path = [[storage filesDirectoryForRevision:catalog.sourceRevision] stringByAppendingPathComponent:file.path];
    [NSFileManager.defaultManager removeItemAtPath:path error:nil];
    filesAbsent = filesAbsent && ![NSFileManager.defaultManager fileExistsAtPath:path];
  }
  step[@"menuFreshInstallation"] = [storage installationWithIdentifier:preset] == nil && filesAbsent ? @YES : @NO;
  step[@"manualPersistence"] = @NO;
  @synchronized(LibretroMetalPresenter.class) { step[@"menuDownloadStart"] = @(sFixtureDownloadPaths.count); }
  UINavigationController *navigation = [session valueForKey:@"menu"];
  if (sOfficialCatalog) {
    if (navigation == nil) {
      SEL open = NSSelectorFromString(@"openMenu");
      ((void (*)(id, SEL))[session methodForSelector:open])(session, open);
      navigation = [session valueForKey:@"menu"];
    }
    LibretroFrontendMenu *frontend = [session valueForKey:@"frontendMenu"];
    LibretroMenuPage *category = [frontend shaderCategoryPage:[catalog entryWithIdentifier:preset].category];
    [navigation pushViewController:category animated:NO];
  }
  LibretroMenuPage *category = [navigation.topViewController isKindOfClass:LibretroMenuPage.class]
                                 ? (LibretroMenuPage *)navigation.topViewController : nil;
  LibretroMenuRow *entry = category != nil ? MenuRowWithIdentifier(category, [@"libretro-shader-entry-" stringByAppendingString:preset]) : nil;
  if (entry == nil || !entry.enabled || entry.action == nil) {
    completion(NO, @"MENU_ENTRY_MISSING");
    return;
  }
  step[@"menuEntryHandler"] = @YES;
  entry.action(category);
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.4 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
    LibretroMenuPage *page = [navigation.topViewController isKindOfClass:LibretroMenuPage.class]
                               ? (LibretroMenuPage *)navigation.topViewController : nil;
    LibretroMenuRow *download = page != nil && page != category ? MenuRowWithIdentifier(page, @"libretro-shader-entry-download") : nil;
    if (download == nil || !download.enabled || download.action == nil) {
      completion(NO, @"MENU_DOWNLOAD_MISSING");
      return;
    }
    step[@"menuDownloadHandler"] = @YES;
    download.action(page);
    [self pollMenuShaderApplication:page step:step session:session applyInvoked:NO
                          deadline:CFAbsoluteTimeGetCurrent() + 30 completion:completion];
  });
}

- (void)verifyShaderRequestsAfterStop:(NSMutableDictionary *)result session:(LibretroSession *)session {
  id<LibretroFrontendMenuHost> host = (id<LibretroFrontendMenuHost>)session;
  NSString *recoveryPath = DocumentsPath(@"Libretro/Config/Frontend/shader-attempts.json");
  NSMutableDictionary *observation = [@{@"recoveryBefore": ReadJSON(recoveryPath)} mutableCopy];
  result[@"shaderAfterStop"] = observation;
  for (NSString *kind in @[@"builtin", @"slang"]) {
    NSMutableDictionary *response = [@{@"callbackCount": @0} mutableCopy];
    observation[kind] = response;
    NSString *identifier = [kind isEqualToString:@"slang"] ? LibretroSlangShaderIdentifier(@"simple.slangp") : nil;
    [host applyShaderPreset:identifier parameters:nil completion:^(BOOL success) {
      response[@"callbackCount"] = @([response[@"callbackCount"] unsignedIntegerValue] + 1);
      response[@"success"] = @(success);
      response[@"code"] = host.lastShaderFailureCode ?: @"";
    }];
  }
  // Leave a turn for the immediate refusals and any stale shader callbacks
  // queued before teardown. A late call must not start compilation, create
  // a recovery attempt or consume a callback without answering it.
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
    observation[@"recoveryAfter"] = ReadJSON(recoveryPath);
    [self finishScenario:result session:session];
  });
}

- (void)runShaderActions:(NSArray<NSDictionary *> *)actions
                   index:(NSUInteger)index
                  result:(NSMutableDictionary *)result
                 session:(LibretroSession *)session {
  if (index >= actions.count) {
    SEL close = NSSelectorFromString(@"closeMenu");
    ((void (*)(id, SEL))[session methodForSelector:close])(session, close);
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
      CaptureNextGameFrame(session, [result[@"name"] stringByAppendingString:@"-resumed"], ^(NSDictionary *frame) {
        result[@"shaderAfterMenu"] = frame;
        [self stopScenario:result session:session];
      });
    });
    return;
  }
  NSDictionary *action = actions[index];
  NSString *kind = action[@"kind"];
  NSString *preset = action[@"preset"];
  NSString *identifier = preset.length > 0 ? LibretroSlangShaderIdentifier(preset) : nil;
  NSMutableDictionary *step = [action mutableCopy];
  id<LibretroFrontendMenuHost> host = (id<LibretroFrontendMenuHost>)session;
  NeoShaderStorage *storage = LibretroSlangStorage();
  NeoShaderCatalog *catalog = LibretroSlangCatalog();
  Progress(@"%@: shader step %lu %@ %@", result[@"name"], (unsigned long)index, kind, preset ?: @"-");
  __weak ProbeAppDelegate *weakSelf = self;
  void (^record)(BOOL, NSString *) = ^(BOOL success, NSString *code) {
    step[@"observedSuccess"] = @(success);
    step[@"observedCode"] = code ?: @"";
    // Save only after the application reports success, exactly as the
    // in-game shader menu does; parameters use its existing frontend store.
    if (success && ![kind isEqualToString:@"menu-apply"] && ([action[@"persist"] boolValue] || [kind isEqualToString:@"disable"])) {
      NSString *game = host.gameKey;
      BOOL disabled = [kind isEqualToString:@"disable"];
      [host.frontendStore setValue:disabled ? @NO : @YES forKey:LibretroSettingShaderEnabled console:host.console game:game];
      if (!disabled) {
        [host.frontendStore setValue:identifier forKey:LibretroSettingShaderPreset console:host.console game:game];
        [host.frontendStore setValue:@{} forKey:LibretroSettingShaderParameters console:host.console game:game];
      }
    }
    // Observe a subsequent live frame, after the selection's own GPU
    // completion, including failed selections that must preserve the image.
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.2 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
      NSString *name = [NSString stringWithFormat:@"%@-%02lu-%@", result[@"name"], (unsigned long)index, kind];
      CaptureNextGameFrame(session, name, ^(NSDictionary *frame) {
        step[@"frame"] = frame;
        [result[@"shaderSteps"] addObject:step];
        Progress(@"%@: shader step %lu completed %d %@ active %@ pixels %@", result[@"name"], (unsigned long)index,
                 success, code ?: @"-", frame[@"active"], frame[@"screenCentresRGBA"] ?: @[]);
        [weakSelf runShaderActions:actions index:index + 1 result:result session:session];
      });
    });
  };
  void (^apply)(void) = ^{
    [host applyShaderPreset:[kind isEqualToString:@"disable"] ? nil : identifier
                   parameters:nil
                   completion:^(BOOL success) {
                     record(success, host.lastShaderFailureCode);
                   }];
  };
  if ([kind isEqualToString:@"menu-apply"]) {
    [self applyShaderThroughMenu:step session:session completion:record];
  } else if ([kind isEqualToString:@"parameter"]) {
    [host previewShaderParameter:action[@"parameter"] value:[action[@"value"] floatValue]];
    record(YES, nil);
  } else if ([kind isEqualToString:@"disable"]) {
    apply();
  } else if ([kind isEqualToString:@"restore-console"]) {
    // Set up the real preference transition of restoring console defaults:
    // console PSP LUT, current game CRT -> remove the game shader keys.
    // Invoke the menu's real reapplication method, not applyShaderPreset.
    [host.frontendStore setValue:@YES forKey:LibretroSettingShaderEnabled console:host.console game:nil];
    [host.frontendStore setValue:identifier forKey:LibretroSettingShaderPreset console:host.console game:nil];
    [host.frontendStore setValue:@{} forKey:LibretroSettingShaderParameters console:host.console game:nil];
    for (NSString *key in @[LibretroSettingShaderEnabled, LibretroSettingShaderPreset, LibretroSettingShaderParameters])
      [host.frontendStore setValue:nil forKey:key console:host.console game:host.gameKey];
    LibretroFrontendMenu *frontend = [session valueForKey:@"frontendMenu"];
    id state = [NSClassFromString(@"LibretroFrontendPageState") new];
    SEL selector = NSSelectorFromString(@"applyResolvedShaderWithState:page:");
    ((void (*)(id, SEL, id, id))[frontend methodForSelector:selector])(frontend, selector, state, nil);
    CFAbsoluteTime deadline = CFAbsoluteTimeGetCurrent() + 30;
    __block void (^poll)(void);
    poll = ^{
      LibretroMetalPresenter *presenter = [session valueForKey:@"presenter"];
      if ([presenter.activePresetIdentifier isEqualToString:identifier] &&
          [host.activeSlangProgram.presetPath isEqualToString:preset]) {
        poll = nil;
        record(YES, nil);
      } else if (CFAbsoluteTimeGetCurrent() >= deadline) {
        poll = nil;
        record(NO, @"CONSOLE_SHADER_RESTORE_TIMEOUT");
      } else {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.1 * NSEC_PER_SEC)), dispatch_get_main_queue(), poll);
      }
    };
    poll();
  } else if ([kind isEqualToString:@"delete-dependency"]) {
    NeoShaderInstallation *installation = [storage installationWithIdentifier:preset];
    NSString *path = [[storage filesDirectoryForRevision:installation.revision] stringByAppendingPathComponent:action[@"path"]];
    step[@"dependencyRemoved"] = @([NSFileManager.defaultManager removeItemAtPath:path error:nil]);
    apply();
  } else {
    if ([kind isEqualToString:@"download-short"]) {
      [storage removeInstallationWithIdentifier:preset error:nil];
      sShortDownload = preset;
    }
    [storage installEntry:[catalog entryWithIdentifier:preset] catalog:catalog progress:nil completion:^(NeoShaderResult *installed) {
      step[@"installationSuccess"] = @(installed.success);
      step[@"installationCode"] = installed.code ?: @"";
      step[@"installationRegistered"] = [storage installationWithIdentifier:preset] != nil ? @YES : @NO;
      sShortDownload = nil;
      if ([kind isEqualToString:@"download-short"]) {
        // The failed download may not register the shader. Applying its ID
        // separately must also refuse safely while the previous effect runs.
        [host applyShaderPreset:identifier parameters:nil completion:^(BOOL success) {
          step[@"applyAfterFailedDownload"] = @(success);
          step[@"applyAfterFailedDownloadCode"] = host.lastShaderFailureCode ?: @"";
          record(installed.success, installed.code);
        }];
      } else if ([kind isEqualToString:@"repair"]) {
        // Installing repairs a missing dependency; the already active
        // program still works because it owns its compiled LUT texture.
        record(installed.success, installed.code);
      } else if (!installed.success) {
        record(NO, installed.code);
      } else if ([kind isEqualToString:@"supersede-builtin"]) {
        // Two choices in the same main-queue turn: the queued built-in
        // activation/callback may not change, cancel or restore over the
        // newer slang selection. Observe each callback separately.
        __block NSUInteger oldCount = 0;
        __block NSUInteger newCount = 0;
        [host applyShaderPreset:nil parameters:nil completion:^(BOOL success) {
          step[@"supersededCallbackCount"] = @(++oldCount);
          step[@"supersededSuccess"] = @(success);
          step[@"supersededCode"] = host.lastShaderFailureCode ?: @"";
        }];
        [host applyShaderPreset:identifier parameters:nil completion:^(BOOL success) {
          step[@"newestCallbackCount"] = @(++newCount);
          if (newCount == 1) record(success, host.lastShaderFailureCode);
        }];
      } else {
        apply();
      }
    }];
  }
}

- (void)captureInitialShaderForScenario:(NSDictionary *)scenario
                                result:(NSMutableDictionary *)result
                               session:(LibretroSession *)session
                              deadline:(CFAbsoluteTime)deadline {
  NSString *expected = scenario[@"shaders"][@"initial"];
  LibretroMetalPresenter *presenter = [session valueForKey:@"presenter"];
  id<LibretroFrontendMenuHost> host = (id<LibretroFrontendMenuHost>)session;
  if (expected.length > 0 && CFAbsoluteTimeGetCurrent() < deadline &&
      (![presenter.activePresetIdentifier isEqualToString:expected] || host.activeSlangProgram == nil || host.slangTextureBytes == 0)) {
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.25 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
      [self captureInitialShaderForScenario:scenario result:result session:session deadline:deadline];
    });
    return;
  }
  CaptureNextGameFrame(session, [result[@"name"] stringByAppendingString:@"-initial"], ^(NSDictionary *frame) {
    result[@"shaderInitial"] = frame;
    if ([scenario[@"shaders"][@"menu"] boolValue]) {
      SEL open = NSSelectorFromString(@"openMenu");
      ((void (*)(id, SEL))[session methodForSelector:open])(session, open);
      UINavigationController *navigation = [session valueForKey:@"menu"];
      result[@"shaderMenuOpened"] = navigation != nil ? @YES : @NO;
      result[@"shaderMenuPaused"] = [session valueForKey:@"menuPaused"];
      LibretroFrontendMenu *frontend = [session valueForKey:@"frontendMenu"];
      LibretroMenuPage *catalog = [frontend shaderCategoryPage:@"other"];
      result[@"shaderCatalogOpened"] = catalog != nil ? @YES : @NO;
      if (catalog != nil) [navigation pushViewController:catalog animated:NO];
    }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
      [self runShaderActions:scenario[@"shaders"][@"actions"] ?: @[] index:0 result:result session:session];
    });
  });
}

- (void)runShaderScenario:(NSDictionary *)scenario result:(NSMutableDictionary *)result session:(LibretroSession *)session {
  result[@"shaderSteps"] = [NSMutableArray array];
  CAMetalLayer *layer = [session valueForKey:@"metalLayer"];
  layer.framebufferOnly = NO;
  // Stored effects compile asynchronously at load; readiness is checked
  // rather than inferred from a timer. Previously acquired display-only
  // drawables also drain before the first readback.
  CFAbsoluteTime deadline = CFAbsoluteTimeGetCurrent() + 30;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
    if ([scenario[@"shaders"][@"official"] boolValue] && [scenario[@"shaders"][@"initial"] length] == 0) {
      // A prior core can have saved a console-scoped choice. Keep that
      // preference and make the program absent, also the state after an
      // interrupted/failed automatic load. Apply must really retry it and
      // may not claim the stored choice is already rendered. Relaunch
      // cases retain and observe the real restored program.
      id<LibretroFrontendMenuHost> host = (id<LibretroFrontendMenuHost>)session;
      [host applyShaderPreset:nil parameters:nil completion:^(BOOL success) {
        result[@"baselineDisableSuccess"] = @(success);
        [self captureInitialShaderForScenario:scenario result:result session:session deadline:deadline];
      }];
      return;
    }
    [self captureInitialShaderForScenario:scenario result:result session:session deadline:deadline];
  });
}
#endif

- (void)runNext {
  if (_index >= _scenarios.count) {
    [self writeResultsFinished:YES];
    Progress(@"probe finished");
    return;
  }
  NSDictionary *scenario = _scenarios[_index++];
  NSString *name = scenario[@"name"];
  NSUInteger generation = ++_generation;
  NSMutableDictionary *result = [@{@"name" : name, @"core" : scenario[@"core"] ?: @""} mutableCopy];
  if ([scenario[@"crowdWindow"] boolValue]) {
    result[@"regionsBeforeCrowd"] = WindowRegions();
    NSArray<NSNumber *> *crowd = CrowdWindow();
    result[@"crowd"] = crowd;
    result[@"crowdSlots"] = crowd;
    result[@"regionsAfterCrowd"] = WindowRegions();
    Progress(@"%@: %lu scratchpad slots of the PPSSPP window taken; %@", name, (unsigned long)crowd.count,
             ReservationReport());
  }
  UIViewController *root = self.window.rootViewController;
  LibretroSession *session = [[LibretroSession alloc] initWithConfiguration:[self configurationForScenario:scenario]];
  _session = session;
  CFAbsoluteTime start = CFAbsoluteTimeGetCurrent();
  double runSeconds = [scenario[@"runSeconds"] doubleValue] > 0 ? [scenario[@"runSeconds"] doubleValue] : 2.0;
  __weak ProbeAppDelegate *weakSelf = self;
  session.endedHandler = ^{
    result[@"ended"] = @YES;
    result[@"endedSeconds"] = @(CFAbsoluteTimeGetCurrent() - start);
    Progress(@"%@: session ended", name);
  };
  Progress(@"%@: launch (%@)", name, scenario[@"content"]);
  [session startFromViewController:root
                        completion:^(NSDictionary<NSString *, id> *launch) {
                          ProbeAppDelegate *probe = weakSelf;
                          if (probe == nil || generation != probe->_generation) return;
                          BOOL success = [launch[@"success"] boolValue];
                          result[@"launchSeconds"] = @(CFAbsoluteTimeGetCurrent() - start);
                          if (result[@"crowdSlots"] != nil) result[@"regionsAtLaunch"] = WindowRegions();
                          result[@"launch"] = @{
                            @"success" : @(success),
                            @"code" : launch[@"code"] ?: @"",
                            @"message" : launch[@"message"] ?: @"",
                            @"hardwareRendering" : launch[@"hardwareRendering"] ?: @"",
                            @"libraryName" : launch[@"libraryName"] ?: @"",
                            @"libraryVersion" : launch[@"libraryVersion"] ?: @"",
                            @"log" : Tail(launch[@"log"], 80),
                          };
                          Progress(@"%@: launch %@ %@ %@", name, success ? @"succeeded" : @"failed",
                                   launch[@"code"] ?: @"", launch[@"hardwareRendering"] ?: @"");
                          if (!success) {
                            // The session has dismissed its view already.
                            [probe finishScenario:result session:session];
                            return;
                          }
                          if (scenario[@"shaders"] != nil) {
#ifdef NEOSTATION_SHADER_SESSION_PROBE
                            [probe runShaderScenario:scenario result:result session:session];
#else
                            result[@"shaderProbeUnavailable"] = @YES;
                            [probe stopScenario:result session:session];
#endif
                            return;
                          }
                          // Resolution scenarios: the frame size, then the menu's
                          // choice, then the frame size once the game ran again.
                          NSDictionary *resolution = [scenario[@"resolution"] isKindOfClass:NSDictionary.class]
                                                         ? scenario[@"resolution"]
                                                         : nil;
                          if (resolution != nil) {
                            double before = [resolution[@"beforeSeconds"] doubleValue];
                            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(before * NSEC_PER_SEC)),
                                           dispatch_get_main_queue(), ^{
                                             result[@"resolutionBefore"] = ProducedFrameSize(session);
                                             result[@"resolutionStateBefore"] = ResolutionState(session) ?: @{};
                                             NSString *value = resolution[@"select"];
                                             id scope = resolution[@"gameScope"];
                                             BOOL game = [scope isKindOfClass:NSNumber.class] && [scope boolValue];
                                             BOOL selected = value.length > 0 && SelectResolution(session, value, game);
                                             result[@"resolutionSelected"] = @(selected);
                                             Progress(@"%@: frame %@ before, %@ selected: %d", name,
                                                      result[@"resolutionBefore"], value ?: @"-", selected);
                                           });
                          }
                          dispatch_after(
                              dispatch_time(DISPATCH_TIME_NOW, (int64_t)(runSeconds * NSEC_PER_SEC)),
                              dispatch_get_main_queue(), ^{
                                if (resolution != nil) {
                                  result[@"resolutionAfter"] = ProducedFrameSize(session);
                                  result[@"resolutionStateAfter"] = ResolutionState(session) ?: @{};
                                  // What the session saved: its record of the
                                  // core's option, the value for every game of
                                  // the core and the values of single games.
                                  NSString *library = launch[@"libraryName"] ?: @"";
                                  result[@"resolutionSnapshot"] = ReadJSON(DocumentsPath(
                                      [NSString stringWithFormat:@"Libretro/Config/Resolution/%@.json", scenario[@"core"]]));
                                  result[@"resolutionCoreFile"] = ReadJSON(
                                      DocumentsPath([NSString stringWithFormat:@"Libretro/Config/%@.json", library]));
                                  result[@"resolutionGameFile"] = ReadJSON(
                                      DocumentsPath([NSString stringWithFormat:@"Libretro/Config/Games/%@.json", library]));
                                  result[@"gameKey"] = [@"probe/" stringByAppendingString:[scenario[@"content"] lastPathComponent]];
                                  Progress(@"%@: frame %@ after", name, result[@"resolutionAfter"]);
                                }
                                [probe stopScenario:result session:session];
                              });
                        }];
  // A launch that never answers ends the probe: the session may still hold
  // the emulation thread.
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(150 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
    ProbeAppDelegate *probe = weakSelf;
    if (probe == nil || generation != probe->_generation || result[@"finished"] != nil) return;
    result[@"timeout"] = @YES;
    result[@"recentLog"] = Tail(session.recentLog, 80);
    result[@"journal"] = ReadText(DocumentsPath(@"Libretro/Logs/session.log"));
    Progress(@"%@: timed out", name);
    [probe->_results addObject:result];
    [probe writeResultsFinished:NO];
  });
}

- (void)finishScenario:(NSMutableDictionary *)result session:(LibretroSession *)session {
  result[@"finished"] = @YES;
  // The journal's END line is written in the dismissal completion, before
  // the stop completion; give the ended handler a turn as well.
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
    result[@"activeAfterStop"] = @(session.active);
    result[@"presentedAtEnd"] = @(self.window.rootViewController.presentedViewController != nil);
    result[@"recentLog"] = Tail(session.recentLog, 80);
    result[@"journal"] = ReadText(DocumentsPath(@"Libretro/Logs/session.log"));
    NSArray<NSNumber *> *crowd = result[@"crowd"];
    if (crowd != nil) {
      ReleaseCrowd(crowd);
      result[@"crowd"] = @(crowd.count);
      result[@"reservationAfter"] = ReservationReport();
    }
    [self->_results addObject:result];
    [self writeResultsFinished:NO];
    self->_session = nil;
    Progress(@"%@: recorded", result[@"name"]);
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
      [self runNext];
    });
  });
}

- (void)writeResultsFinished:(BOOL)finished {
  NSDictionary *report = @{@"finished" : @(finished), @"source" : _config[@"source"] ?: @"", @"results" : _results};
  NSData *data = [NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:nil];
  NSString *name = finished ? @"probe.json" : @"probe-partial.json";
  [data writeToFile:DocumentsPath(name) atomically:YES];
}

@end

int main(int argc, char *argv[]) {
  @autoreleasepool {
    return UIApplicationMain(argc, argv, nil, NSStringFromClass(ProbeAppDelegate.class));
  }
}
