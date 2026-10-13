// SPDX-License-Identifier: GPL-3.0-or-later
// Behaviour of the Dolphin post-processing choice (DOLShaderStore.h, Build
// 450) on real files: what NeoStation stores, what reaches GFX.ini and
// Dolphin.ini right before the core initializes, imports and removals, and
// the interplay with the reversible display trial that edits GFX.ini too.
//
//   dolphin-shader-store-tests
#import <Foundation/Foundation.h>

#include "DOLShaderStore.h"

static int gChecks = 0;
static int gFailures = 0;

#define CHECK(condition, ...)                                \
  do {                                                       \
    gChecks++;                                               \
    if (!(condition)) {                                      \
      gFailures++;                                           \
      fprintf(stderr, "FAILED %s:%d: ", __FILE__, __LINE__); \
      fprintf(stderr, __VA_ARGS__);                          \
      fprintf(stderr, "\n");                                 \
    }                                                        \
  } while (0)

static NSString* Read(NSString* path) {
  return [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil] ?: @"";
}

static void Write(NSString* path, NSString* text) {
  [NSFileManager.defaultManager createDirectoryAtPath:path.stringByDeletingLastPathComponent
                          withIntermediateDirectories:YES
                                           attributes:nil
                                                error:nil];
  [text writeToFile:path atomically:YES encoding:NSUTF8StringEncoding error:nil];
}

static NSString* Shader(NSString* user, NSString* system, NSString* game) {
  NSString* applied = nil;
  CHECK(DOLApplyShaderSelection(user, system, game, &applied), "staging succeeds");
  id value = DOLIniValue(Read([user stringByAppendingPathComponent:@"Config/GFX.ini"]), @"Enhancements",
                         @"PostProcessingShader");
  CHECK([value isKindOfClass:NSString.class] && [value isEqualToString:applied ?: @"?"],
        "GFX.ini holds the shader staged (%s vs %s)", [[value description] UTF8String], applied.UTF8String);
  return [value isKindOfClass:NSString.class] ? value : nil;
}

static void TestNames(void) {
  CHECK(DOLShaderValidName(@"crt-mattias-original"), "a plain name");
  CHECK(DOLShaderValidName(@"CRT (v2) + glow_1.5"), "spaces, parentheses, plus, dot");
  CHECK(!DOLShaderValidName(@"../Config/GFX"), "no path");
  CHECK(!DOLShaderValidName(@".hidden"), "no leading dot");
  CHECK(!DOLShaderValidName(@" padded"), "no leading space");
  CHECK(!DOLShaderValidName(DOLShaderDefaultName), "Dolphin's default pass is never offered");
  CHECK(!DOLShaderValidName([@"" stringByPaddingToLength:65 withString:@"a" startingAtIndex:0]), "64 characters at most");
  CHECK(!DOLShaderValidName(@"shader\\x"), "no backslash");
  CHECK(DOLShaderValidGame(@"GALE01") && DOLShaderValidGame(@"RMGE") && !DOLShaderValidGame(@"gale01") &&
            !DOLShaderValidGame(@"GALE01/../"),
        "game IDs");
}

static void TestChoices(NSString* root) {
  NSString* user = [root stringByAppendingPathComponent:@"User"];
  NSString* system = [root stringByAppendingPathComponent:@"Sys"];
  Write([system stringByAppendingPathComponent:@"Shaders/FXAA.glsl"], @"void main() { SetOutput(Sample()); }\n");
  Write([system stringByAppendingPathComponent:@"Shaders/sepia.glsl"], @"void main() { SetOutput(Sample()); }\n");
  Write([system stringByAppendingPathComponent:@"Shaders/Anaglyph/dubois.glsl"], @"void main() {}\n");
  Write([system stringByAppendingPathComponent:@"Shaders/default_pre_post_process.glsl"], @"void main() {}\n");
  NSArray* names = DOLShaderNames(DOLShaderFolder(system));
  CHECK([names isEqualToArray:(@[ @"FXAA", @"sepia" ])], "offered: top-level shaders without the default pass (%s)",
        [names description].UTF8String);

  // Nothing chosen: an explicit empty value (the pinned loader keeps a key
  // that is missing from the file).
  Write([user stringByAppendingPathComponent:@"Config/GFX.ini"], @"[Settings]\nMSAA = 1\n[Enhancements]\nPostProcessingShader = sepia\n");
  CHECK([Shader(user, system, @"GALE01") isEqualToString:@""], "no choice: no effect");
  CHECK([DOLIniValue(Read([user stringByAppendingPathComponent:@"Config/GFX.ini"]), @"Settings", @"MSAA") isEqual:@"1"],
        "other GFX.ini settings are kept");

  CHECK(DOLShaderSetChoice(user, nil, @"FXAA"), "choice for every game");
  CHECK([Shader(user, system, @"GALE01") isEqualToString:@"FXAA"], "every game: FXAA");
  CHECK(DOLShaderSetChoice(user, @"GALE01", @""), "this game: no effect");
  CHECK([Shader(user, system, @"GALE01") isEqualToString:@""], "the game's own choice wins");
  CHECK([Shader(user, system, @"RMGE01") isEqualToString:@"FXAA"], "another game follows every game");
  CHECK([Shader(user, system, @"") isEqualToString:@"FXAA"], "the Wii Menu follows every game");
  CHECK(DOLShaderSetChoice(user, @"GALE01", @"sepia"), "this game: sepia");
  CHECK([Shader(user, system, @"GALE01") isEqualToString:@"sepia"], "this game: sepia staged");
  CHECK(DOLShaderSetChoice(user, @"GALE01", nil), "this game follows every game again");
  CHECK([Shader(user, system, @"GALE01") isEqualToString:@"FXAA"], "followed: FXAA");
  CHECK(!DOLShaderSetChoice(user, @"../x", @"FXAA") && !DOLShaderSetChoice(user, nil, @"../FXAA"),
        "invalid game or name refused");

  // A shader that is no longer there is switched off, not sent to the core.
  CHECK(DOLShaderSetChoice(user, nil, @"Ghost"), "choice of a missing shader is stored");
  CHECK([Shader(user, system, @"RMGE01") isEqualToString:@""], "a missing shader is not staged");

  // A damaged selection file reads as no choice.
  Write([user stringByAppendingPathComponent:DOLShaderSelectionPath], @"{not json");
  NSDictionary* selection = DOLShaderReadSelection(user);
  CHECK([selection[@"global"] isEqualToString:@""] && [selection[@"games"] count] == 0, "damaged file: defaults");
  Write([user stringByAppendingPathComponent:DOLShaderSelectionPath],
        @"{\"schema\":1,\"global\":\"../evil\",\"games\":{\"GALE01\":\"sepia\",\"bad\":\"FXAA\"},"
        @"\"options\":{\"sepia\":{\"X\":{\"type\":\"float\",\"values\":[\"x\"]},\"Z\":{\"type\":\"vector\",\"values\":[1]},\"Y\":{\"type\":\"float\",\"values\":[0.5]}}},"
        @"\"checked\":{\"sepia\":\"nothex\"}}");
  selection = DOLShaderReadSelection(user);
  NSDictionary* expectedOptions = @{@"sepia" : @{@"Y" : @{@"type" : @"float", @"values" : @[ @0.5 ]}}};
  CHECK(([selection[@"global"] isEqualToString:@""] && [selection[@"games"] isEqual:@{@"GALE01" : @"sepia"}] &&
         [selection[@"options"] isEqual:expectedOptions] && [selection[@"checked"] count] == 0),
        "invalid entries are dropped, valid ones kept (%s)", [selection description].UTF8String);
}

static void TestOptionsImportsRemoval(NSString* root) {
  NSString* user = [root stringByAppendingPathComponent:@"User"];
  NSString* system = [root stringByAppendingPathComponent:@"Sys"];
  [NSFileManager.defaultManager createDirectoryAtPath:DOLShaderFolder(system) withIntermediateDirectories:YES attributes:nil error:nil];
  NSData* code = [@"/*\n[configuration]\n[OptionRangeFloat]\nGUIName = Curvature\nOptionName = M_CURVATURE\n"
                  @"MinValue = 0.0\nMaxValue = 1.0\nDefaultValue = 0.5\nStepAmount = 0.05\n[/configuration]\n*/\n"
                  @"void main() { SetOutput(Sample()); }\n" dataUsingEncoding:NSUTF8StringEncoding];
  BOOL replaced = YES;
  CHECK(DOLShaderStoreImport(user, @"crt-mattias-original", code, &replaced) && !replaced, "import written");
  CHECK([[NSData dataWithContentsOfFile:[DOLShaderFolder(user) stringByAppendingPathComponent:@"crt-mattias-original.glsl"]]
            isEqualToData:code],
        "the file is Dolphin's user shader");
  CHECK(DOLShaderStoreImport(user, @"crt-mattias-original", code, &replaced) && replaced, "a second import replaces it");
  CHECK(!DOLShaderStoreImport(user, @"../escape", code, NULL), "an import cannot leave Shaders/");
  NSMutableData* large = [NSMutableData dataWithLength:DOLShaderMaxBytes + 1];
  CHECK(!DOLShaderStoreImport(user, @"large", large, NULL), "512 KB at most");

  CHECK(DOLShaderSetChoice(user, nil, @"crt-mattias-original"), "imported shader chosen");
  Write([user stringByAppendingPathComponent:@"Config/Dolphin.ini"],
        @"[Core]\nCPUThread = True\n[crt-mattias-original-options]\nM_STALE = 3\n");
  CHECK(DOLShaderSetOptionValues(user, @"crt-mattias-original", @{
          @"M_CURVATURE" : @{@"type" : @"float", @"values" : @[ @0.25 ]},
          @"M_GLOW" : @{@"type" : @"bool", @"values" : @[ @1 ]},
          @"M_SIZE" : @{@"type" : @"integer", @"values" : @[ @3, @4.4 ]},
          @"bad name" : @{@"type" : @"float", @"values" : @[ @1 ]},
        }),
        "options stored");
  CHECK([Shader(user, system, @"GALE01") isEqualToString:@"crt-mattias-original"], "imported shader staged");
  NSString* ini = Read([user stringByAppendingPathComponent:@"Config/Dolphin.ini"]);
  NSString* section = @"crt-mattias-original-options";
  CHECK([DOLIniValue(ini, section, @"M_CURVATURE") isEqual:@"0.25"], "float in the C locale (%s)", ini.UTF8String);
  CHECK([DOLIniValue(ini, section, @"M_GLOW") isEqual:@"True"], "bool as Dolphin writes it");
  CHECK([DOLIniValue(ini, section, @"M_SIZE") isEqual:@"3, 4"], "integers separated by \", \"");
  CHECK(DOLIniValue(ini, section, @"M_STALE") == NSNull.null, "a value NeoStation did not set is removed");
  CHECK(DOLIniValue(ini, section, @"bad name") == NSNull.null, "an invalid option name is never written");
  CHECK([DOLIniValue(ini, @"Core", @"CPUThread") isEqual:@"True"], "other Dolphin.ini settings are kept");

  CHECK(DOLShaderSetOptionValues(user, @"crt-mattias-original", nil), "options reset");
  CHECK([Shader(user, system, @"GALE01") isEqualToString:@"crt-mattias-original"], "staged again");
  ini = Read([user stringByAppendingPathComponent:@"Config/Dolphin.ini"]);
  CHECK(DOLIniValue(ini, section, @"M_CURVATURE") == NSNull.null, "reset: the shader's own defaults apply");

  CHECK(DOLShaderSetChoice(user, @"GALE01", @"crt-mattias-original") && DOLShaderSetChecked(user, @"crt-mattias-original",
            @"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"),
        "game choice and compiled hash stored");
  CHECK(DOLShaderRemoveImport(user, @"crt-mattias-original"), "removal");
  NSDictionary* selection = DOLShaderReadSelection(user);
  CHECK([selection[@"global"] isEqualToString:@""] && [selection[@"games"][@"GALE01"] isEqualToString:@""] &&
            selection[@"options"][@"crt-mattias-original"] == nil && selection[@"checked"][@"crt-mattias-original"] == nil,
        "choices that named it switch the effect off; what was kept about it is forgotten");
  CHECK(![NSFileManager.defaultManager fileExistsAtPath:[DOLShaderFolder(user) stringByAppendingPathComponent:@"crt-mattias-original.glsl"]],
        "the file is deleted");
  CHECK([Shader(user, system, @"GALE01") isEqualToString:@""], "nothing staged after removal");
}

/// The reversible display trial also edits GFX.ini before the core starts and
/// restores its own keys afterwards: the effect must survive both.
static void TestDisplayTrial(NSString* root) {
  NSString* user = [root stringByAppendingPathComponent:@"User"];
  NSString* system = [root stringByAppendingPathComponent:@"Sys"];
  Write([system stringByAppendingPathComponent:@"Shaders/FXAA.glsl"], @"void main() { SetOutput(Sample()); }\n");
  Write([user stringByAppendingPathComponent:@"Config/GFX.ini"], @"[Settings]\nShaderCompilationMode = 0\n");
  CHECK(DOLShaderSetChoice(user, nil, @"FXAA"), "choice");
  CHECK(DOLBeginDisplayTrial(user, @"GALE01", 2), "display trial begins");
  CHECK([Shader(user, system, @"GALE01") isEqualToString:@"FXAA"], "effect staged after the trial");
  CHECK(DOLRestoreDisplayTrial(user), "display trial restored");
  NSString* gfx = Read([user stringByAppendingPathComponent:@"Config/GFX.ini"]);
  CHECK([DOLIniValue(gfx, @"Enhancements", @"PostProcessingShader") isEqual:@"FXAA"], "the effect survives the restore (%s)",
        gfx.UTF8String);
  CHECK([DOLIniValue(gfx, @"Settings", @"ShaderCompilationMode") isEqual:@"0"], "the trial's own key is restored");
  CHECK(DOLBeginDisplayTrial(user, @"GALE01", 2), "next launch: trial again");
  CHECK([Shader(user, system, @"GALE01") isEqualToString:@"FXAA"], "next launch: effect staged again");
}

int main(void) {
  @autoreleasepool {
    NSString* base = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    TestNames();
    TestChoices([base stringByAppendingPathComponent:@"a"]);
    TestOptionsImportsRemoval([base stringByAppendingPathComponent:@"b"]);
    TestDisplayTrial([base stringByAppendingPathComponent:@"c"]);
    [NSFileManager.defaultManager removeItemAtPath:base error:nil];
    printf("%d checks, %d failures\n", gChecks, gFailures);
    return gFailures == 0 ? 0 : 1;
  }
}
