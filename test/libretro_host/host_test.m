// Behavioural test of NeoStation's portable libretro host on macOS: core
// loading, environment calls, content (plain and zipped), save RAM written
// on unload and restored on the next load, save states in RetroArch's
// RASTATE and rzip layouts, options, cheats, disk control, and a fresh core
// after unloading. Runs against test/libretro_host/test_core.c.
#import <Foundation/Foundation.h>

#import "LibretroCoreHost.h"
#import "LibretroCoreOptions.h"
#import "LibretroResolution.h"
#import "LibretroStateCodec.h"

#include <math.h>
#include <zlib.h>

static int failures = 0;

#define CHECK(condition, message)                                   \
  do {                                                              \
    if (condition) {                                                \
      printf("PASS %s\n", message);                                 \
    } else {                                                        \
      printf("FAIL %s (%s:%d)\n", message, __FILE__, __LINE__);    \
      failures++;                                                   \
    }                                                               \
  } while (0)

@interface TestDelegate : NSObject <LibretroCoreHostDelegate>
@property(nonatomic) unsigned frames;
@property(nonatomic) uint32_t pixel0;
@property(nonatomic) uint32_t pixel1;
// Size of the last frame and the geometry of the last SET_SYSTEM_AV_INFO.
@property(nonatomic) unsigned lastWidth;
@property(nonatomic) unsigned lastHeight;
@property(nonatomic) unsigned timingChanges;
@property(nonatomic) unsigned announcedWidth;
@property(nonatomic) size_t audioFrames;
@property(nonatomic) uint16_t buttons;
@property(nonatomic) unsigned fills;
@property(nonatomic, strong) NSMutableArray<NSNumber *> *fillFrames;
@end

@implementation TestDelegate
- (void)coreHost:(LibretroCoreHost *)host
      videoFrame:(const void *)data
           width:(unsigned)width
          height:(unsigned)height
           pitch:(size_t)pitch {
  if (data == NULL || data == RETRO_HW_FRAME_BUFFER_VALID) return;
  self.frames++;
  self.pixel0 = ((const uint32_t *)data)[0];
  self.pixel1 = ((const uint32_t *)data)[1];
  self.lastWidth = width;
  self.lastHeight = height;
}
- (void)coreHost:(LibretroCoreHost *)host timingChanged:(struct retro_system_av_info)avInfo {
  self.timingChanges++;
  self.announcedWidth = avInfo.geometry.base_width;
}
- (void)coreHost:(LibretroCoreHost *)host audioFrames:(const int16_t *)frames count:(size_t)count {
  self.audioFrames += count;
}
- (void)coreHost:(LibretroCoreHost *)host fillInput:(LibretroInputSnapshot *)snapshot {
  memset(snapshot, 0, sizeof(*snapshot));
  snapshot->buttons[0] = self.buttons;
  self.fills++;
  if (self.fillFrames != nil) [self.fillFrames addObject:@(host.frameSerial)];
}
@end

/// A delegate with a hardware context: its render interface exists from
/// context creation until the frontend releases the context.
@interface HardwareDelegate : TestDelegate
@property(nonatomic) BOOL contextAlive;
@end

@implementation HardwareDelegate
- (BOOL)coreHost:(LibretroCoreHost *)host prepareHardwareRender:(struct retro_hw_render_callback *)callback {
  self.contextAlive = YES;
  return YES;
}
- (const struct retro_hw_render_interface *)hardwareRenderInterfaceForCoreHost:(LibretroCoreHost *)host {
  static const struct retro_hw_render_interface interface = {RETRO_HW_RENDER_INTERFACE_VULKAN, 5};
  return self.contextAlive ? &interface : NULL;
}
@end

static NSUInteger LogIndex(NSArray<NSString *> *log, NSString *line) {
  NSUInteger index = [log indexOfObject:line];
  return index == NSNotFound ? NSUIntegerMax : index;
}

static LibretroCoreHost *MakeHost(NSString *core, NSString *work) {
  return [[LibretroCoreHost alloc] initWithCorePath:core
                                    systemDirectory:[work stringByAppendingPathComponent:@"System"]
                                      saveDirectory:[work stringByAppendingPathComponent:@"Saves"]
                                     stateDirectory:[work stringByAppendingPathComponent:@"States"]
                                   optionsDirectory:[work stringByAppendingPathComponent:@"Config"]
                                     cacheDirectory:[work stringByAppendingPathComponent:@"Cache"]
                                           language:RETRO_LANGUAGE_FRENCH
                                         jitCapable:NO];
}

static id JSONAtPath(NSString *path) {
  NSData *data = [NSData dataWithContentsOfFile:path];
  return data != nil ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
}

static NSArray<NSNumber *> *NumberPair(id value) {
  return [value isKindOfClass:[NSArray class]] && [value count] == 2 ? value : nil;
}

/// The shared value cases (test/fixtures/libretro_resolution/value_cases.json),
/// which Dart's LibretroResolution passes too: both readers agree.
static void CheckResolutionCases(NSString *fixtures) {
  NSDictionary *cases = JSONAtPath([fixtures stringByAppendingPathComponent:@"value_cases.json"]);
  CHECK([cases[@"tokens"] count] > 0 && [cases[@"choices"] count] > 0, "resolution value cases read");
  int mismatches = 0;
  for (NSDictionary *entry in cases[@"tokens"]) {
    NSString *value = entry[@"value"];
    id expected = entry[@"expected"];
    double factor = 0;
    NSUInteger width = 0, height = 0;
    BOOL parsed = LibretroResolutionParseValue(value, &factor, &width, &height);
    BOOL same;
    if (expected == NSNull.null) {
      same = !parsed;
    } else if (expected[@"factor"] != nil) {
      same = parsed && fabs(factor - [expected[@"factor"] doubleValue]) < 1e-9 && width == 0 && height == 0;
    } else {
      same = parsed && factor == 0 && width == [expected[@"width"] unsignedIntegerValue] &&
             height == [expected[@"height"] unsignedIntegerValue];
    }
    if (!same) {
      mismatches++;
      printf("  token \"%s\": parsed %d, factor %g, %lux%lu\n", value.UTF8String, parsed, factor,
             (unsigned long)width, (unsigned long)height);
    }
  }
  CHECK(mismatches == 0, "every value of the shared cases reads as in Dart");
  mismatches = 0;
  for (NSDictionary *entry in cases[@"choices"]) {
    NSArray<NSNumber *> *console = NumberPair(entry[@"consoleSize"]);
    id maxDimension = entry[@"maxDimension"];
    NSArray<LibretroResolutionChoice *> *choices = LibretroResolutionChoices(
        entry[@"values"], entry[@"labels"], NumberPair(entry[@"nativeSize"]), console ? console[0].doubleValue : 0,
        console ? console[1].doubleValue : 0, [entry[@"maxFactor"] doubleValue],
        maxDimension != nil ? [maxDimension integerValue] : 8192);
    NSMutableArray *got = [NSMutableArray array];
    for (LibretroResolutionChoice *choice in choices) {
      [got addObject:@[ choice.value, @(choice.factor), @(choice.width), @(choice.height) ]];
    }
    NSMutableArray *want = [NSMutableArray array];
    for (NSDictionary *choice in entry[@"expected"]) {
      [want addObject:@[ choice[@"value"], @([choice[@"factor"] doubleValue]), @([choice[@"width"] unsignedIntegerValue]),
                         @([choice[@"height"] unsignedIntegerValue]) ]];
    }
    if (![got isEqualToArray:want]) {
      mismatches++;
      printf("  choices \"%s\": %s\n", [entry[@"name"] UTF8String], got.description.UTF8String);
    }
  }
  CHECK(mismatches == 0, "every choice list of the shared cases is as in Dart");
}

static NSData *RzipWrap(NSData *payload) {
  // One deflate (zlib-framed) chunk, as RetroArch's rzip writer produces.
  uLongf bound = compressBound((uLong)payload.length);
  NSMutableData *compressed = [NSMutableData dataWithLength:bound];
  compress2(compressed.mutableBytes, &bound, payload.bytes, (uLong)payload.length, 6);
  compressed.length = bound;
  NSMutableData *file = [NSMutableData data];
  const uint8_t magic[8] = {'#', 'R', 'Z', 'I', 'P', 'v', 1, '#'};
  [file appendBytes:magic length:8];
  uint32_t chunk = 131072;
  [file appendBytes:&chunk length:4];
  uint64_t total = payload.length;
  [file appendBytes:&total length:8];
  uint32_t size = (uint32_t)compressed.length;
  [file appendBytes:&size length:4];
  [file appendData:compressed];
  return file;
}

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    if (argc < 5) {
      printf("usage: host_test CORE WORKDIR CONTENT_ZIP RESOLUTION_FIXTURES\n");
      return 2;
    }
    NSString *core = @(argv[1]);
    NSString *work = @(argv[2]);
    NSString *zipped = @(argv[3]);
    NSString *content = [work stringByAppendingPathComponent:@"Test Game.ntc"];
    NSMutableData *rom = [NSMutableData dataWithLength:100];
    for (int index = 0; index < 100; index++) ((uint8_t *)rom.mutableBytes)[index] = (uint8_t)(index + 1);
    [rom writeToFile:content atomically:YES];

    // Build 453: the real option store preserves the FastInterp user choice
    // across fresh sessions and refuses values the core does not declare.
    struct retro_core_option_v2_definition fastDefinitions[] = {
      {.key = "citra_use_fastinterp", .desc = "Fast Interpreter",
       .values = {{"enabled", "Enabled"}, {"disabled", "Disabled"}, {NULL, NULL}},
       .default_value = "enabled"},
      {0}
    };
    struct retro_core_options_v2 fastDeclarations = {NULL, fastDefinitions};
    NSString *fastPath = [work stringByAppendingPathComponent:@"Config/FastInterpTest.json"];
    LibretroCoreOptions *fast = [[LibretroCoreOptions alloc] initWithStorePath:fastPath];
    [fast declareV2:&fastDeclarations local:NULL];
    [fast applyDefaults:@{@"citra_use_fastinterp": @"enabled"}];
    CHECK(strcmp([fast valueForKey:"citra_use_fastinterp"], "enabled") == 0,
          "FastInterp enabled for a new user");
    CHECK([fast setValue:@"disabled" forKey:@"citra_use_fastinterp" persist:YES],
          "FastInterp can be disabled through the same store as the in-game menu");
    LibretroCoreOptions *nextFast = [[LibretroCoreOptions alloc] initWithStorePath:fastPath];
    [nextFast declareV2:&fastDeclarations local:NULL];
    [nextFast applyDefaults:@{@"citra_use_fastinterp": @"enabled"}];
    CHECK(strcmp([nextFast valueForKey:"citra_use_fastinterp"], "disabled") == 0,
          "disabled choice survives relaunch and beats the enabled default");
    CHECK(![nextFast setValue:@"invalid" forKey:@"citra_use_fastinterp" persist:YES],
          "invalid FastInterp choice refused");
    CHECK([nextFast setValue:@"enabled" forKey:@"citra_use_fastinterp" persist:YES],
          "FastInterp can be enabled again");
    LibretroCoreOptions *lastFast = [[LibretroCoreOptions alloc] initWithStorePath:fastPath];
    [lastFast declareV2:&fastDeclarations local:NULL];
    CHECK(strcmp([lastFast valueForKey:"citra_use_fastinterp"], "enabled") == 0,
          "enabled choice also survives relaunch");

    // Session 1: plain content.
    TestDelegate *delegate = [TestDelegate new];
    delegate.buttons = 0x0103;
    LibretroCoreHost *host = MakeHost(core, work);
    host.delegate = delegate;
    NSError *error = nil;
    CHECK([host loadCore:&error], "core loads and exposes libretro API 1");
    CHECK([host.libraryName isEqualToString:@"NeoTest"], "library name read");
    [host.options applyDefaults:@{@"neotest_mode" : @"beta"}];
    CHECK([host loadContentAtPath:content error:&error], "plain content loads");
    for (int frame = 0; frame < 10; frame++) [host runFrame];
    CHECK(delegate.frames == 10 && delegate.pixel0 == 10, "ten frames presented");
    CHECK(delegate.audioFrames == 8000, "audio batches forwarded");
    CHECK(delegate.pixel1 == 0, "no save RAM restored on first run");
    CHECK([host saveStateToSlot:1 error:&error], "state saved to slot 1");
    NSData *stateFile = [NSData dataWithContentsOfFile:[host statePathForSlot:1]];
    CHECK(stateFile.length > 8 && memcmp(stateFile.bytes, "RASTATE", 7) == 0, "state written as RASTATE container");
    for (int frame = 0; frame < 5; frame++) [host runFrame];
    CHECK([host loadStateFromSlot:1 error:&error], "state loaded from slot 1");
    [host runFrame];
    CHECK(delegate.pixel0 == 11, "restored state resumes at frame 11");
    [host applyCheats:@[ @"CODE-1", @"", @"CODE-2" ]];
    CHECK(host.supportsDiskControl && host.diskCount == 2, "disk control interface registered");
    CHECK([host selectDisk:1] && host.diskIndex == 1, "disk 2 selected");
    CHECK([[host labelForDisk:1] isEqualToString:@"Test disc 2"], "disk label read");
    [host runFrame];
    NSString *saveRAM = host.saveRAMPath;
    [host unloadWithContextDestroy:nil contextRelease:nil];
    NSData *sram = [NSData dataWithContentsOfFile:saveRAM];
    const uint8_t *bytes = sram.bytes;
    CHECK(sram.length == 2048, "save RAM written on unload");
    CHECK(sram.length == 2048 && bytes[1] == 0x5A, "save RAM content");
    CHECK(sram.length == 2048 && bytes[2] == 'b', "NeoStation default option reached the core");
    CHECK(sram.length == 2048 && bytes[3] == 0, "JIT reported unavailable");
    CHECK(sram.length == 2048 && bytes[4] == 2, "only non-empty cheats applied");
    CHECK(sram.length == 2048 && bytes[5] == 1, "disk index persisted in core state");
    CHECK(sram.length == 2048 && bytes[10] == 0x03, "input bitmask delivered");
    CHECK([saveRAM.stringByDeletingLastPathComponent.lastPathComponent isEqualToString:@"NeoTest"],
          "save RAM sorted by core name like RetroArch");

    // Session 2: zipped content, fresh core, save RAM restored.
    TestDelegate *second = [TestDelegate new];
    LibretroCoreHost *again = MakeHost(core, work);
    again.delegate = second;
    CHECK([again loadCore:&error], "core reloads after unload");
    CHECK([again loadContentAtPath:zipped error:&error], "zipped content extracted and loaded");
    [again runFrame];
    CHECK(second.pixel0 == 1, "core state is fresh after dlclose");
    CHECK(second.pixel1 == 0x5A, "save RAM restored before the first frame");
    [again.options setValue:@"beta" forKey:@"neotest_mode" persist:YES];
    CHECK([again.options consumeUpdate], "option change flagged for the core");
    CHECK(![again.options consumeUpdate], "option change flagged only once");
    // User values that session 3's NeoStation values must beat.
    [again.options setValue:@"three" forKey:@"neotest_init" persist:YES];
    [again.options setValue:@"user" forKey:@"neotest_locked" persist:YES];

    // RetroArch-style compressed state in slot 2 (frame counter 42).
    uint32_t serialized[2] = {42, 0};
    NSData *container = [LibretroStateCodec containerForCoreState:[NSData dataWithBytes:serialized length:8]];
    [RzipWrap(container) writeToFile:[again statePathForSlot:2] atomically:YES];
    CHECK([again loadStateFromSlot:2 error:&error], "rzip-compressed RASTATE state accepted");
    [again runFrame];
    CHECK(second.pixel0 == 43, "compressed state restored the frame counter");
    NSError *decodeError = nil;
    const uint8_t zstd[20] = {'#', 'R', 'Z', 'I', 'P', 'v', 2, '#', 0, 0, 2, 0, 8, 0, 0, 0, 0, 0, 0, 0};
    CHECK([LibretroStateCodec coreStateFromFileData:[NSData dataWithBytes:zstd length:20] error:&decodeError] == nil &&
              decodeError.code == LibretroStateCodecErrorUnsupportedCompression,
          "zstd states are reported, not guessed");
    [again unloadWithContextDestroy:nil contextRelease:nil];

    NSData *options = [NSData dataWithContentsOfFile:[work stringByAppendingPathComponent:@"Config/NeoTest.json"]];
    CHECK(options != nil && [[[NSString alloc] initWithData:options encoding:NSUTF8StringEncoding]
                                containsString:@"beta"],
          "user option persisted per core");

    // Session 3: NeoStation's option values must reach a core that reads
    // them only in retro_init (DeSmuME), locked values resist user changes,
    // and a value changed during the session is flagged for the core.
    TestDelegate *third = [TestDelegate new];
    LibretroCoreHost *configured = MakeHost(core, work);
    configured.delegate = third;
    configured.initialOptionDefaults = @{@"neotest_default" : @"neo", @"neotest_mode" : @"alpha"};
    configured.initialSessionOverrides = @{@"neotest_init" : @"two", @"neotest_locked" : @"free"};
    configured.lockedSessionOverrides = @{@"neotest_locked" : @"fixed"};
    CHECK([configured loadCore:&error], "core loads with initial option values");
    CHECK([configured loadContentAtPath:content error:&error], "content loads in the option session");
    size_t reportSize = 0;
    const char *report = [configured memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&reportSize];
    BOOL hasReport = report != NULL && reportSize >= 96;
    CHECK(hasReport && strcmp(report, "two") == 0, "session override read in retro_init, over the stored value");
    CHECK(hasReport && strcmp(report + 16, "fixed") == 0, "locked override read in retro_init, over everything");
    CHECK(hasReport && strcmp(report + 32, "neo") == 0, "NeoStation default read in retro_init");
    CHECK(hasReport && strcmp(report + 48, "beta") == 0, "NeoStation default does not replace a stored user value");
    CHECK(!configured.options.updatePending, "values given before retro_init are not flagged as updates");
    CHECK([configured.options isLockedKey:@"neotest_locked"] && ![configured.options isLockedKey:@"neotest_init"],
          "only locked overrides are locked");
    CHECK(![configured.options setValue:@"user" forKey:@"neotest_locked" persist:YES],
          "a locked option refuses a user change");
    const char *lockedValue = [configured.options valueForKey:"neotest_locked"];
    CHECK(lockedValue != NULL && strcmp(lockedValue, "fixed") == 0, "the locked value stays in effect");
    CHECK(!configured.options.updatePending, "a refused change is not flagged");
    [configured runFrame];
    [configured.options applySessionOverrides:@{@"neotest_init" : @"two"}];
    CHECK(!configured.options.updatePending, "an override that changes nothing is not flagged");
    [configured.options applySessionOverrides:@{@"neotest_init" : @"one"}];
    CHECK(configured.options.updatePending, "an override changing a declared option is flagged for the core");
    [configured runFrame];
    CHECK(!configured.options.updatePending, "the core consumed the update");
    report = [configured memoryDataForIdentifier:RETRO_MEMORY_SYSTEM_RAM size:&reportSize];
    hasReport = report != NULL && reportSize >= 96;
    CHECK(hasReport && strcmp(report + 64, "one") == 0 && report[80] == 1, "the core re-read the overridden value");
    [configured.options applyDefaults:@{@"neotest_mode" : @"beta"}];
    CHECK(!configured.options.updatePending, "a default under a stored user value is not flagged");
    [configured.options applyDefaults:@{@"neotest_default" : @"core"}];
    CHECK(configured.options.updatePending, "a default changing a declared option is flagged for the core");
    [configured unloadWithContextDestroy:nil contextRelease:nil];
    NSData *stored = [NSData dataWithContentsOfFile:[work stringByAppendingPathComponent:@"Config/NeoTest.json"]];
    id storedJSON = stored != nil ? [NSJSONSerialization JSONObjectWithData:stored options:0 error:nil] : nil;
    NSDictionary *storedValues = [storedJSON isKindOfClass:[NSDictionary class]] ? storedJSON[@"values"] : nil;
    CHECK([storedValues[@"neotest_locked"] isEqual:@"user"], "the refused change was not stored");
    CHECK([storedValues[@"neotest_init"] isEqual:@"three"], "session overrides are never stored");

    // Session 4: RetroArch's teardown order. context_destroy first, then
    // retro_unload_game and retro_deinit while the hardware context and its
    // interface still exist (Azahar destroys its Vulkan renderer through the
    // frontend's VkDevice in retro_unload_game), then the frontend releases
    // the context, and dlclose last. Releasing the context before
    // retro_unload_game crashed NeoStation when a 3DS game was closed.
    HardwareDelegate *hardware = [HardwareDelegate new];
    LibretroCoreHost *rendered = MakeHost(core, work);
    rendered.delegate = hardware;
    rendered.initialSessionOverrides = @{@"neotest_hw" : @"on"};
    CHECK([rendered loadCore:&error], "core loads for the hardware context session");
    CHECK([rendered loadContentAtPath:content error:&error], "content loads with a hardware context");
    CHECK(rendered.usesHardwareRendering, "the core registered its hardware context");
    [rendered hardwareContextReset];
    [rendered runFrame];
    NSMutableArray<NSString *> *steps = [NSMutableArray array];
    rendered.teardownObserver = ^(NSString *step, BOOL finished) {
      [steps addObject:[NSString stringWithFormat:@"%@ %@", step, finished ? @"returned" : @"called"]];
    };
    __block NSArray<NSString *> *logAtRelease = @[];
    [rendered unloadWithContextDestroy:^{
      [steps addObject:@"frontend destroys the context"];
      [rendered hardwareContextDestroy];
    }
        contextRelease:^{
          [steps addObject:@"frontend releases the context"];
          logAtRelease = rendered.recentLog;
          hardware.contextAlive = NO;
        }];
    NSArray<NSString *> *expectedSteps = @[
      @"frontend destroys the context", @"retro_unload_game called", @"retro_unload_game returned",
      @"retro_deinit called", @"retro_deinit returned", @"frontend releases the context", @"dlclose called",
      @"dlclose returned"
    ];
    CHECK([steps isEqualToArray:expectedSteps], "teardown runs context_destroy, unload, deinit, release, dlclose");
    if (![steps isEqualToArray:expectedSteps]) printf("  steps: %s\n", [steps description].UTF8String);
    NSArray<NSString *> *log = rendered.recentLog;
    NSUInteger destroyed = LogIndex(log, @"[INFO] neotest context_destroy interface=1");
    NSUInteger unloaded = LogIndex(log, @"[INFO] neotest unload_game interface=1");
    NSUInteger deinitialized = LogIndex(log, @"[INFO] neotest deinit interface=1");
    CHECK(destroyed != NSUIntegerMax, "context_destroy runs while the context exists");
    CHECK(unloaded != NSUIntegerMax, "retro_unload_game still reaches the hardware render interface");
    CHECK(deinitialized != NSUIntegerMax, "retro_deinit still reaches the hardware render interface");
    CHECK(destroyed < unloaded && unloaded < deinitialized, "context_destroy, then retro_unload_game, then retro_deinit");
    CHECK([logAtRelease containsObject:@"[INFO] neotest deinit interface=1"],
          "the frontend releases its context only after retro_deinit returned");
    if (destroyed == NSUIntegerMax || unloaded == NSUIntegerMax || deinitialized == NSUIntegerMax) {
      printf("  log: %s\n", [log description].UTF8String);
    }

    // Session 5: a core that stops by itself (PPSSPP when its boot fails)
    // raises shutdownRequested and leaves its error line, which the session
    // quotes in a LIBRETRO_CORE_STOPPED launch failure.
    TestDelegate *fifth = [TestDelegate new];
    LibretroCoreHost *stopping = MakeHost(core, work);
    stopping.delegate = fifth;
    stopping.initialSessionOverrides = @{@"neotest_shutdown_frame" : @"3"};
    CHECK([stopping loadCore:&error], "core loads for the shutdown session");
    CHECK([stopping loadContentAtPath:content error:&error], "content loads for the shutdown session");
    int frames = 0;
    while (frames < 10 && !stopping.shutdownRequested) {
      [stopping runFrame];
      frames++;
    }
    CHECK(stopping.shutdownRequested && frames == 3, "the core's shutdown request is seen at the frame it is made");
    NSArray<NSString *> *errors = [stopping recentErrors:4];
    CHECK(errors.count == 1 && [errors.firstObject isEqualToString:@"[ERROR] neotest boot failed: simulated"],
          "the core's error line is available for the failure message");
    [stopping appendLog:@"[HOST] note"];
    CHECK([[stopping recentLog].lastObject isEqualToString:@"[HOST] note"], "frontend notes join the log");
    [stopping unloadWithContextDestroy:nil contextRelease:nil];

    // Session 6: input polling. A core that reads the pad without calling
    // input_poll still gets the current state (late polling, as RetroArch),
    // refreshed once per frame; a core polling twice gets both refreshes in
    // the same frame number; frameSerial counts retro_run calls.
    TestDelegate *late = [TestDelegate new];
    late.fillFrames = [NSMutableArray array];
    LibretroCoreHost *lazy = MakeHost(core, work);
    lazy.delegate = late;
    lazy.initialSessionOverrides = @{@"neotest_poll" : @"late"};
    CHECK([lazy loadCore:&error] && [lazy loadContentAtPath:content error:&error], "core loads for the late-poll session");
    late.buttons = 0x0001;
    [lazy runFrame];
    size_t lazySize = 0;
    uint8_t *lazyRAM = [lazy memoryDataForIdentifier:RETRO_MEMORY_SAVE_RAM size:&lazySize];
    CHECK(lazyRAM != NULL && lazySize > 11 && lazyRAM[11] == 0x01, "a core that never polls reads the current pad");
    late.buttons = 0x0002;
    [lazy runFrame];
    CHECK(lazyRAM != NULL && lazyRAM[11] == 0x02, "the late poll is refreshed at the next frame");
    CHECK(late.fills == 2 && [late.fillFrames isEqualToArray:(@[ @1, @2 ])],
          "one late poll per frame, numbered by frameSerial");
    CHECK(lazy.frameSerial == 2, "frameSerial counts retro_run calls");
    [lazy unloadWithContextDestroy:nil contextRelease:nil];

    TestDelegate *twice = [TestDelegate new];
    twice.fillFrames = [NSMutableArray array];
    LibretroCoreHost *eager = MakeHost(core, work);
    eager.delegate = twice;
    eager.initialSessionOverrides = @{@"neotest_poll" : @"twice"};
    CHECK([eager loadCore:&error] && [eager loadContentAtPath:content error:&error], "core loads for the double-poll session");
    twice.buttons = 0x0004;
    [eager runFrame];
    [eager runFrame];
    size_t eagerSize = 0;
    uint8_t *eagerRAM = [eager memoryDataForIdentifier:RETRO_MEMORY_SAVE_RAM size:&eagerSize];
    CHECK([twice.fillFrames isEqualToArray:(@[ @1, @1, @2, @2 ])],
          "a core polling twice per frame refreshes twice with one frame number");
    CHECK(eagerRAM != NULL && eagerSize > 11 && eagerRAM[11] == 0x04, "a polling core still reads its pad");
    [eager unloadWithContextDestroy:nil contextRelease:nil];

    // Session 7 (Build 455): internal resolution. The rules are those the
    // Dart catalog sends (native_rules.json); `live` adds a profile for the
    // test core's option, as the catalog has for the cores it knows.
    NSString *fixtures = @(argv[4]);
    CheckResolutionCases(fixtures);
    NSDictionary *nativeRules = JSONAtPath([fixtures stringByAppendingPathComponent:@"native_rules.json"]);
    CHECK([nativeRules[@"keyPattern"] length] > 0 && [nativeRules[@"profiles"] count] > 0, "native rules read");
    NSMutableDictionary *liveRules = [nativeRules mutableCopy];
    liveRules[@"profiles"] = [@[ @{@"keys" : @[ @"neotest_internal_resolution" ], @"apply" : @"live"} ]
        arrayByAddingObjectsFromArray:nativeRules[@"profiles"]];
    LibretroResolutionRules *live = [[LibretroResolutionRules alloc] initWithDictionary:liveRules];
    LibretroResolutionRules *generic = [[LibretroResolutionRules alloc] initWithDictionary:nativeRules];
    NSString *resolutionWork = [work stringByAppendingPathComponent:@"Resolution"];
    NSString *gamesPath = [resolutionWork stringByAppendingPathComponent:@"Config/Games/NeoTest.json"];
    NSString *corePath = [resolutionWork stringByAppendingPathComponent:@"Config/NeoTest.json"];
    [[NSFileManager defaultManager] createDirectoryAtPath:gamesPath.stringByDeletingLastPathComponent
                              withIntermediateDirectories:YES
                                               attributes:nil
                                                    error:nil];
    // Another game's value and an unknown key the per-game file must keep.
    NSDictionary *seeded = @{
      @"version" : @1,
      @"games" : @{@"gb/Other.ntc" : @{@"neotest_internal_resolution" : @"4x"}},
      @"kept" : @"yes",
    };
    [[NSJSONSerialization dataWithJSONObject:seeded options:0 error:nil] writeToFile:gamesPath atomically:YES];
    NSString *key = @"neotest_internal_resolution";
    NSString *thisGame = @"gb/Test Game.ntc";

    // A core whose own default (2x) is not native starts at native.
    TestDelegate *firstRun = [TestDelegate new];
    LibretroCoreHost *sized = MakeHost(core, resolutionWork);
    sized.delegate = firstRun;
    sized.optionsGameKey = thisGame;
    __block LibretroResolutionCapability *declared = nil;
    __block NSString *nativeApplied = nil;
    sized.optionsDeclared = ^(LibretroCoreOptions *options) {
      declared = [live capabilityForCoreOptions:options consoleWidth:160 consoleHeight:144];
      nativeApplied = LibretroResolutionApplyNativeDefault(declared, options);
    };
    CHECK([sized loadCore:&error] && [sized loadContentAtPath:content error:&error], "core loads for the resolution session");
    CHECK([declared.key isEqualToString:key] && declared.apply == LibretroResolutionApplyLive &&
              [declared.source isEqualToString:@"profile"],
          "the profile names the core's option once declared, before retro_init");
    CHECK(declared.choices.count == 4 && [declared.nativeChoice.value isEqualToString:@"1x (native)"] &&
              [declared.coreDefault isEqualToString:@"2x"],
          "four factors offered, native first, core default 2x");
    CHECK([nativeApplied isEqualToString:@"1x (native)"], "native applied as NeoStation's default");
    CHECK(!sized.options.updatePending, "the native default given before retro_init is not an update");
    [sized runFrame];
    CHECK(firstRun.lastWidth == 320 && firstRun.lastHeight == 240,
          "the core read native in retro_init and draws 320x240 from its first frame");

    // Live change for every game of the core: the effective picture changes.
    LibretroResolutionCapability *capability = [live capabilityForCoreOptions:sized.options
                                                                  consoleWidth:160
                                                                 consoleHeight:144];
    CHECK(LibretroResolutionSelect(capability, sized.options, @"3x", NO), "3x chosen for every game of the core");
    CHECK(sized.options.updatePending, "a live option is flagged for the running core");
    [sized runFrame];
    CHECK(firstRun.lastWidth == 960 && firstRun.lastHeight == 720, "the running core draws at 3x once the game resumes");
    CHECK(firstRun.timingChanges == 1 && firstRun.announcedWidth == 960,
          "the core announced its new size (SET_SYSTEM_AV_INFO) to the host");
    NSDictionary *coreFile = JSONAtPath(corePath);
    CHECK([coreFile[@"values"][key] isEqual:@"3x"], "the choice for every game is saved in the core's file at once");

    // Live change for this game only.
    CHECK(LibretroResolutionSelect(capability, sized.options, @"2x", YES), "2x chosen for this game only");
    [sized runFrame];
    CHECK(firstRun.lastWidth == 640 && firstRun.lastHeight == 480, "the game's own value is in effect at once");
    NSDictionary *gamesFile = JSONAtPath(gamesPath);
    CHECK([gamesFile[@"games"][thisGame][key] isEqual:@"2x"], "the game's value is saved in the per-game file");
    CHECK([gamesFile[@"games"][@"gb/Other.ntc"][key] isEqual:@"4x"] && [gamesFile[@"kept"] isEqual:@"yes"],
          "other games and unknown keys of the per-game file are kept");
    CHECK([JSONAtPath(corePath)[@"values"][key] isEqual:@"3x"], "the core's value is untouched by a game's value");
    CHECK(!LibretroResolutionSelect(capability, sized.options, @"5x", YES) &&
              !LibretroResolutionSelect(capability, sized.options, @"8x", NO),
          "a value the core does not offer is refused");
    CHECK([[sized.options valueForEveryGameForKey:key] isEqualToString:@"3x"] &&
              [[sized.options gameValueForKey:key] isEqualToString:@"2x"],
          "the page reads every game's value and this game's apart");
    [sized unloadWithContextDestroy:nil contextRelease:nil];

    // Relaunch of the same game: its own value, never replaced by native.
    TestDelegate *secondRun = [TestDelegate new];
    LibretroCoreHost *again2 = MakeHost(core, resolutionWork);
    again2.delegate = secondRun;
    again2.optionsGameKey = thisGame;
    __block NSString *secondNative = @"unset";
    again2.optionsDeclared = ^(LibretroCoreOptions *options) {
      secondNative = LibretroResolutionApplyNativeDefault([live capabilityForCoreOptions:options
                                                                            consoleWidth:160
                                                                           consoleHeight:144],
                                                         options);
    };
    CHECK([again2 loadCore:&error] && [again2 loadContentAtPath:content error:&error], "core loads again for the game");
    [again2 runFrame];
    CHECK(secondNative == nil && secondRun.lastWidth == 640, "the game's saved 2x survives the relaunch");
    LibretroResolutionCapability *againCapability = [live capabilityForCoreOptions:again2.options
                                                                       consoleWidth:160
                                                                      consoleHeight:144];
    CHECK(LibretroResolutionClear(againCapability, again2.options, YES), "the game's own value removed");
    [again2 runFrame];
    CHECK(secondRun.lastWidth == 960, "the game follows the core's 3x again, live");
    gamesFile = JSONAtPath(gamesPath);
    CHECK(gamesFile[@"games"][thisGame] == nil && [gamesFile[@"games"][@"gb/Other.ntc"][key] isEqual:@"4x"],
          "the game's entry is gone, the other game's kept");
    [again2 unloadWithContextDestroy:nil contextRelease:nil];

    // Other games: one with its own 4x, one following the core's 3x.
    for (NSArray *expectation in @[ @[ @"gb/Other.ntc", @1280 ], @[ @"gb/Third.ntc", @960 ] ]) {
      TestDelegate *otherRun = [TestDelegate new];
      LibretroCoreHost *other = MakeHost(core, resolutionWork);
      other.delegate = otherRun;
      other.optionsGameKey = expectation[0];
      CHECK([other loadCore:&error] && [other loadContentAtPath:content error:&error], "core loads for another game");
      [other runFrame];
      CHECK(otherRun.lastWidth == [expectation[1] unsignedIntValue], "each game gets its own value, else the core's");
      [other unloadWithContextDestroy:nil contextRelease:nil];
    }

    // An option recognized by its name only applies at the next launch: the
    // running core keeps its resolution and sees no update.
    TestDelegate *namedRun = [TestDelegate new];
    LibretroCoreHost *named = MakeHost(core, resolutionWork);
    named.delegate = namedRun;
    named.optionsGameKey = @"gb/Third.ntc";
    CHECK([named loadCore:&error] && [named loadContentAtPath:content error:&error], "core loads for the generic rule");
    [named runFrame];
    LibretroResolutionCapability *recognized = [generic capabilityForCoreOptions:named.options
                                                                    consoleWidth:160
                                                                   consoleHeight:144];
    CHECK([recognized.key isEqualToString:key] && [recognized.source isEqualToString:@"generic"] &&
              recognized.apply == LibretroResolutionApplyRelaunch,
          "without a profile the option is recognized by its name, for the next launch");
    CHECK(LibretroResolutionSelect(recognized, named.options, @"1x (native)", NO), "native chosen for every game");
    CHECK(!named.options.updatePending, "a next-launch choice is not flagged for the running core");
    [named runFrame];
    CHECK(namedRun.lastWidth == 960, "the running core keeps 3x until the game is launched again");
    CHECK([[named.options currentValueForKey:key] isEqualToString:@"3x"] &&
              [[named.options nextLaunchValueForKey:key] isEqualToString:@"1x (native)"],
          "the page tells the value in effect from the next launch's");
    [named unloadWithContextDestroy:nil contextRelease:nil];
    TestDelegate *relaunchedRun = [TestDelegate new];
    LibretroCoreHost *relaunched = MakeHost(core, resolutionWork);
    relaunched.delegate = relaunchedRun;
    relaunched.optionsGameKey = @"gb/Third.ntc";
    CHECK([relaunched loadCore:&error] && [relaunched loadContentAtPath:content error:&error], "core loads relaunched");
    [relaunched runFrame];
    CHECK(relaunchedRun.lastWidth == 320, "the next launch draws at the chosen native resolution");
    [relaunched unloadWithContextDestroy:nil contextRelease:nil];

    // Cores NeoStation offers no internal resolution for.
    CHECK([live capabilityForCoreOptions:nextFast consoleWidth:400 consoleHeight:480] == nil,
          "a core without a resolution option has none");
    LibretroResolutionRules *conditional = [[LibretroResolutionRules alloc] initWithDictionary:@{
      @"profiles" : @[ @{@"keys" : @[ key ], @"apply" : @"live", @"requires" : @{@"neotest_mode" : @[ @"gamma" ]}} ]
    }];
    LibretroCoreOptions *standalone = [[LibretroCoreOptions alloc]
        initWithStorePath:[resolutionWork stringByAppendingPathComponent:@"Config/Standalone.json"]];
    struct retro_core_option_v2_definition sizedDefinitions[] = {
      {.key = "neotest_mode", .desc = "Mode", .values = {{"alpha", NULL}, {"gamma", NULL}, {NULL, NULL}},
       .default_value = "alpha"},
      {.key = "neotest_internal_resolution", .desc = "Internal resolution",
       .values = {{"1x (native)", NULL}, {"2x", NULL}, {NULL, NULL}}, .default_value = "1x (native)"},
      {.key = "neotest2_render_scale", .desc = "Render scale", .values = {{"2x", NULL}, {"4x", NULL}, {NULL, NULL}},
       .default_value = "2x"},
      {0}
    };
    struct retro_core_options_v2 sizedDeclarations = {NULL, sizedDefinitions};
    [standalone declareV2:&sizedDeclarations local:NULL];
    CHECK([conditional capabilityForCoreOptions:standalone consoleWidth:160 consoleHeight:144] == nil,
          "a profile whose other option has another value is not used");
    [standalone setValue:@"gamma" forKey:@"neotest_mode" persist:NO];
    CHECK([[conditional capabilityForCoreOptions:standalone consoleWidth:160 consoleHeight:144].key isEqualToString:key],
          "the same profile applies once its condition holds");

    // Renderers: a profile established for one renderer is not used once
    // the core runs with another, and its key is not recognized by name
    // either; before the content is loaded (renderer unknown) they are no
    // condition, so the native default still applies.
    LibretroResolutionRules *rendered = [[LibretroResolutionRules alloc] initWithDictionary:@{
      @"profiles" : @[ @{@"keys" : @[ key ], @"apply" : @"live", @"renderers" : @[ LibretroResolutionRendererGLES ]} ],
      @"keyPattern" : nativeRules[@"keyPattern"],
      @"descriptionPattern" : nativeRules[@"descriptionPattern"],
    }];
    CHECK([[rendered capabilityForCoreOptions:standalone renderer:nil consoleWidth:160 consoleHeight:144].key
              isEqualToString:key],
          "before the content is loaded the renderer is no condition");
    LibretroResolutionCapability *renderedGL = [rendered capabilityForCoreOptions:standalone
                                                                          renderer:LibretroResolutionRendererGLES
                                                                      consoleWidth:160
                                                                     consoleHeight:144];
    CHECK([renderedGL.key isEqualToString:key] && renderedGL.apply == LibretroResolutionApplyLive,
          "a profile applies with a renderer it names");
    CHECK([rendered capabilityForCoreOptions:standalone
                                    renderer:LibretroResolutionRendererSoftware
                                consoleWidth:160
                               consoleHeight:144] == nil,
          "with another renderer nothing is offered, not even by the option's name");
    CHECK([[rendered profileKeyForOptions:standalone.options] isEqualToString:key],
          "the option is reported as present but not applicable");
    CHECK([generic profileKeyForOptions:standalone.options] == nil,
          "an option no profile names is never reported as not applicable");

    // PPSSPP with the rules the app sends: live with an OpenGL ES context,
    // next launch with Vulkan, nothing in its software context (frames stay
    // 480x272 there, and a change during the game resets a hardware context
    // it does not have).
    LibretroCoreOptions *psp = [[LibretroCoreOptions alloc]
        initWithStorePath:[resolutionWork stringByAppendingPathComponent:@"Config/PPSSPP.json"]];
    struct retro_core_option_v2_definition pspDefinitions[] = {
      {.key = "ppsspp_backend", .desc = "Backend",
       .values = {{"auto", NULL}, {"opengl", NULL}, {"vulkan", NULL}, {"none", NULL}, {NULL, NULL}},
       .default_value = "auto"},
      {.key = "ppsspp_software_rendering", .desc = "Software Rendering",
       .values = {{"disabled", NULL}, {"enabled", NULL}, {NULL, NULL}}, .default_value = "disabled"},
      {.key = "ppsspp_internal_resolution", .desc = "Rendering Resolution",
       .values = {{"480x272", NULL}, {"960x544", NULL}, {"1440x816", NULL}, {"1920x1088", NULL}, {"2400x1360", NULL},
                  {"2880x1632", NULL}, {NULL, NULL}},
       .default_value = "480x272"},
      {0}
    };
    struct retro_core_options_v2 pspDeclarations = {NULL, pspDefinitions};
    [psp declareV2:&pspDeclarations local:NULL];
    LibretroResolutionCapability *pspGL = [generic capabilityForCoreOptions:psp
                                                                   renderer:LibretroResolutionRendererGLES
                                                               consoleWidth:480
                                                              consoleHeight:272];
    CHECK([pspGL.key isEqualToString:@"ppsspp_internal_resolution"] && pspGL.apply == LibretroResolutionApplyLive &&
              pspGL.choices.count == 5 && [pspGL.nativeChoice.value isEqualToString:@"480x272"],
          "PPSSPP with OpenGL ES: live, native to 5x");
    LibretroResolutionCapability *pspVulkan = [generic capabilityForCoreOptions:psp
                                                                       renderer:LibretroResolutionRendererVulkan
                                                                   consoleWidth:480
                                                                  consoleHeight:272];
    CHECK([pspVulkan.key isEqualToString:@"ppsspp_internal_resolution"] &&
              pspVulkan.apply == LibretroResolutionApplyRelaunch,
          "PPSSPP with Vulkan: next launch");
    CHECK([generic capabilityForCoreOptions:psp
                                   renderer:LibretroResolutionRendererSoftware
                               consoleWidth:480
                              consoleHeight:272] == nil &&
              [[generic profileKeyForOptions:psp.options] isEqualToString:@"ppsspp_internal_resolution"],
          "PPSSPP in its software context: nothing offered, the option reported as not applicable");
    [psp setValue:@"enabled" forKey:@"ppsspp_software_rendering" persist:NO];
    CHECK([generic capabilityForCoreOptions:psp
                                   renderer:LibretroResolutionRendererGLES
                               consoleWidth:480
                              consoleHeight:272] == nil,
          "PPSSPP's software rendering option: nothing offered");
    struct retro_core_option_display hidden = {"neotest_internal_resolution", false};
    [standalone setDisplay:&hidden];
    LibretroResolutionCapability *hiddenCapability = [generic capabilityForCoreOptions:standalone
                                                                           consoleWidth:160
                                                                          consoleHeight:144];
    CHECK(hiddenCapability == nil, "a hidden option, and a named option without native resolution, are not offered");
  }
  if (failures > 0) {
    printf("%d libretro host check(s) failed\n", failures);
    return 1;
  }
  printf("All libretro host checks passed\n");
  return 0;
}
