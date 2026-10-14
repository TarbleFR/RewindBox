// Behavioural tests of persistent shader activation/session recovery. These
// exercise the actual file-backed class; no rendered frame/device claim.
#import <Foundation/Foundation.h>
#import "LibretroShaderRecovery.h"

#include <stdio.h>

static int failures = 0;
#define CHECK(condition, label) do { \
  BOOL pass = (condition) ? YES : NO; \
  printf("%s %s (%d)\n", pass ? "PASS" : "FAIL", label, __LINE__); \
  if (!pass) failures++; \
} while (0)

static NSDictionary *ReadState(NSString *directory) {
  NSData *data = [NSData dataWithContentsOfFile:[directory stringByAppendingPathComponent:@"shader-attempts.json"]];
  return data != nil ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
}

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    NSString *base = argc > 1 ? @(argv[1]) : NSTemporaryDirectory();
    NSString *directory = [base stringByAppendingPathComponent:@"Frontend"];
    NSString *preset = @"slang:crt/zfast-crt.slangp";
    NSString *other = @"slang:scanlines/scanlines.slangp";
    NSString *core = @"snes9x";
    NSString *game = @"snes/test.sfc";
    LibretroShaderRecovery *one = [[LibretroShaderRecovery alloc] initWithDirectory:directory];
    CHECK(one.canProtect, "new protection store is usable");
    CHECK(![one blocksAutomaticPreset:preset core:core game:game], "new preset allowed automatically");
    NSString *attempt = [one beginPreset:preset core:core game:game];
    CHECK(attempt != nil && [ReadState(directory)[@"pending"][@"token"] isEqualToString:attempt],
          "attempt is on disk before compilation or first GPU frame");
    // Process ends without calling finishToken/finishSession. Reopening the
    // same class reads disk only, as a fresh process would.
    one = nil;
    LibretroShaderRecovery *two = [[LibretroShaderRecovery alloc] initWithDirectory:directory];
    CHECK([two blocksAutomaticPreset:preset core:core game:game], "interrupted compilation/activation is skipped");
    CHECK(![two blocksAutomaticPreset:other core:core game:game], "other shaders are unaffected");
    CHECK(![two blocksAutomaticPreset:preset core:@"genesis_plus_gx" game:game], "other cores are unaffected");
    CHECK(![two blocksAutomaticPreset:preset core:core game:@"snes/other.sfc"], "other games are unaffected");
    CHECK(ReadState(directory)[@"pending"] == nil, "interrupted attempt is moved out of pending");
    two = [[LibretroShaderRecovery alloc] initWithDirectory:directory];
    CHECK([two blocksAutomaticPreset:preset core:core game:game], "skipped launch does not silently remove protection");

    // Manual selection is permitted. A handled error removes the in-flight
    // marker, but only confirmed rendering clears an earlier interruption.
    attempt = [two beginPreset:preset core:core game:game];
    CHECK(attempt != nil, "manual retry of interrupted shader allowed");
    [two finishToken:attempt confirmed:NO];
    CHECK(ReadState(directory)[@"pending"] == nil, "handled compiler/validation error removes pending marker");
    CHECK([two blocksAutomaticPreset:preset core:core game:game], "handled error keeps interrupted shader blocked");
    attempt = [two beginPreset:preset core:core game:game];
    [two finishToken:attempt confirmed:YES];
    CHECK(![two blocksAutomaticPreset:preset core:core game:game], "actual GPU success clears old interrupted choice");
    CHECK(ReadState(directory)[@"pending"] == nil &&
          [ReadState(directory)[@"active"][@"token"] isEqualToString:attempt],
          "GPU-confirmed shader stays protected for later frames and parameter changes");

    // Switching starts an independent attempt without dropping protection
    // for the prior picture. Validation failure brings that picture back.
    NSString *failed = [two beginPreset:other core:core game:game];
    [two finishToken:failed confirmed:NO];
    CHECK([ReadState(directory)[@"active"][@"preset"] isEqualToString:preset],
          "failed switch preserves previous active protection");
    two = nil; // A crash on frame 2 or later, or an unrelated iOS termination.
    LibretroShaderRecovery *three = [[LibretroShaderRecovery alloc] initWithDirectory:directory];
    CHECK([three blocksAutomaticPreset:preset core:core game:game], "interruption after first GPU frame is also skipped");
    CHECK(![three blocksAutomaticPreset:other core:core game:game], "handled failed candidate is not blamed on relaunch");

    NSString *older = [three beginPreset:preset core:core game:game];
    NSString *newer = [three beginPreset:other core:core game:game];
    [three finishToken:older confirmed:YES];
    CHECK([ReadState(directory)[@"pending"][@"token"] isEqualToString:newer],
          "late old GPU callback cannot clear or accept a newer attempt");
    [three finishToken:newer confirmed:YES];
    CHECK([ReadState(directory)[@"active"][@"preset"] isEqualToString:other], "newest GPU-confirmed preset is active");
    [three deactivatePreset];
    CHECK(ReadState(directory)[@"active"] == nil, "disabling removes active session marker");
    three = [[LibretroShaderRecovery alloc] initWithDirectory:directory];
    CHECK(![three blocksAutomaticPreset:other core:core game:game], "disabled preset is safe to relaunch automatically");

    attempt = [three beginPreset:preset core:core game:game];
    [three finishToken:attempt confirmed:YES];
    [three beginPreset:other core:core game:game];
    [three finishSession];
    CHECK(ReadState(directory)[@"pending"] == nil && ReadState(directory)[@"active"] == nil,
          "normal session stop clears both compilation and active markers");
    three = [[LibretroShaderRecovery alloc] initWithDirectory:directory];
    CHECK(![three blocksAutomaticPreset:preset core:core game:game] &&
          ![three blocksAutomaticPreset:other core:core game:game], "normal stop creates no interrupted shader");

    // A write failure must refuse the candidate before risky native work.
    NSString *blockedDirectory = [base stringByAppendingPathComponent:@"regular-file"];
    [@"file" writeToFile:blockedDirectory atomically:YES encoding:NSUTF8StringEncoding error:nil];
    LibretroShaderRecovery *blocked = [[LibretroShaderRecovery alloc] initWithDirectory:blockedDirectory];
    CHECK([blocked beginPreset:preset core:core game:game] == nil, "failed marker write refuses activation");
    NSString *badDirectory = [base stringByAppendingPathComponent:@"Corrupt"];
    [NSFileManager.defaultManager createDirectoryAtPath:badDirectory withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *badPath = [badDirectory stringByAppendingPathComponent:@"shader-attempts.json"];
    [@"invalid-json" writeToFile:badPath atomically:YES encoding:NSUTF8StringEncoding error:nil];
    blocked = [[LibretroShaderRecovery alloc] initWithDirectory:badDirectory];
    CHECK(!blocked.canProtect && [blocked blocksAutomaticPreset:preset core:core game:game],
          "corrupt recovery data refuses automatic shader activation");
    CHECK([blocked beginPreset:preset core:core game:game] == nil, "corrupt protection does not accept a new attempt");
    CHECK([[NSString stringWithContentsOfFile:badPath encoding:NSUTF8StringEncoding error:nil] isEqualToString:@"invalid-json"],
          "bad protection data is preserved for diagnosis");

    CHECK([LibretroShaderFailureTextKey(@"DOWNLOAD_HASH") isEqualToString:@"shaderErrorVerification"], "hash error explanation");
    CHECK([LibretroShaderFailureTextKey(@"PRESET_TEXTURE_MISSING") isEqualToString:@"shaderInvalid"], "missing dependency explanation");
    CHECK([LibretroShaderFailureTextKey(@"METAL_PIPELINE_FAILED") isEqualToString:@"shaderCompileFailed"], "compile error explanation");
    CHECK([LibretroShaderFailureTextKey(@"CHAIN_MEMORY") isEqualToString:@"shaderTooHeavy"], "GPU budget explanation");
    CHECK([LibretroShaderFailureTextKey(@"CHAIN_GPU") isEqualToString:@"shaderGpuFailed"], "GPU execution error explanation");
    CHECK([LibretroShaderFailureTextKey(@"SHADER_INTERRUPTED") isEqualToString:@"shaderInterrupted"], "interruption is never reported as proved shader crash");
  }
  printf("shader_recovery_test: %d failure(s)\n", failures);
  return failures == 0 ? 0 : 1;
}
