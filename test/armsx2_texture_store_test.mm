// Runs the production HD texture pack store (ARMSX2TexturePackStore.mm, Build 485)
// with Foundation on real files written by test/armsx2_texture_packs_test.py:
// game identification, inspection verdicts, confirmation, installation, atomic
// replacement, cancellation, removal, per-game choices, the game's INI value,
// the boot choices given to ARMSX2Core and the .tar.zst path through an
// expander. No engine runs: whether a game uses the textures is not shown here.
#import <Foundation/Foundation.h>
#import "ARMSX2TexturePackStore.h"
#include <cstdlib>

static int checks = 0;
#define CHECK(x) do { if (!(x)) { NSLog(@"FAILED %d: %s", __LINE__, #x); std::abort(); } ++checks; } while (0)

static NSString* fixtures;
static NSString* data;
static NSFileManager* fm;

static NSURL* Fixture(NSString* name) { return [NSURL fileURLWithPath:[fixtures stringByAppendingPathComponent:name]]; }
static NSString* Textures(NSString* relative) {
  return [[ARMSX2TexturePackStore texturesRootForDataPath:data] stringByAppendingPathComponent:relative];
}
static NSDictionary* Game(NSString* serial) {
  return @{@"serial": serial, @"crc": @"", @"version": @"1.01", @"source": @"disc", @"region": @"NTSC-U"};
}
static NSDictionary* Import(NSString* fixture, NSDictionary* game, BOOL allow, ARMSX2TextureExpander expander = nil,
                            NSDictionary* __autoreleasing* inspection = nullptr) {
  ARMSX2TextureImport* import = [[ARMSX2TextureImport alloc] initWithURL:Fixture(fixture) dataPath:data game:game expander:expander];
  NSDictionary* inspected = [import inspectWithProgress:nil];
  if (inspection) *inspection = inspected;
  NSDictionary* result = [inspected[@"success"] boolValue] ? [import installAllowingMismatch:allow progress:nil] : inspected;
  [import close];
  return result;
}

int main(int argc, char** argv) { @autoreleasepool {
  if (argc != 3) return 2;
  fixtures = [NSString stringWithUTF8String:argv[1]];
  data = [NSString stringWithUTF8String:argv[2]];
  fm = NSFileManager.defaultManager;
  [fm createDirectoryAtPath:[data stringByAppendingPathComponent:@"gamesettings"] withIntermediateDirectories:YES attributes:nil error:nil];
  [fm createDirectoryAtPath:Textures(@"SLUS-21137/dumps") withIntermediateDirectories:YES attributes:nil error:nil];
  CHECK([@"dump" writeToFile:Textures(@"SLUS-21137/dumps/keep-00000001.png") atomically:YES encoding:NSUTF8StringEncoding error:nil]);
  NSString* save = [data stringByAppendingPathComponent:@"Saves/Memory Cards/Mcd001.ps2"];
  [fm createDirectoryAtPath:save.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
  CHECK([@"memory card" writeToFile:save atomically:YES encoding:NSUTF8StringEncoding error:nil]);

  // Identification: the disc's SYSTEM.CNF, a serial in the name, then what the engine read.
  NSDictionary* iso = [ARMSX2TexturePackStore identifyGameAtPath:Fixture(@"game.iso").path dataPath:data];
  CHECK([iso[@"serial"] isEqual:@"SLUS-21137"] && [iso[@"source"] isEqual:@"disc"] && [iso[@"version"] isEqual:@"1.01"] && [iso[@"region"] isEqual:@"NTSC-U"]);
  NSString* named = [fixtures stringByAppendingPathComponent:@"Ratchet (SCES-50916).chd"];
  CHECK([[NSData dataWithBytes:"chd" length:3] writeToFile:named atomically:YES]);
  NSDictionary* byName = [ARMSX2TexturePackStore identifyGameAtPath:named dataPath:data];
  CHECK([byName[@"serial"] isEqual:@"SCES-50916"] && [byName[@"source"] isEqual:@"name"] && [byName[@"region"] isEqual:@"PAL"]);
  NSString* chd = [fixtures stringByAppendingPathComponent:@"not-a-disc.chd"];
  CHECK([[ARMSX2TexturePackStore identifyGameAtPath:chd dataPath:data][@"source"] isEqual:@"none"]);
  [ARMSX2TexturePackStore recordIdentity:@{@"serial": @"SLES-54164", @"crc": @"0BC2B4C1", @"version": @"1.00", @"title": @"God of War II"}
                             forGamePath:chd dataPath:data];
  NSDictionary* session = [ARMSX2TexturePackStore identifyGameAtPath:chd dataPath:data];
  CHECK([session[@"serial"] isEqual:@"SLES-54164"] && [session[@"source"] isEqual:@"session"] && [session[@"crc"] isEqual:@"0BC2B4C1"]);
  [ARMSX2TexturePackStore recordIdentity:@{@"serial": @"../../x"} forGamePath:chd dataPath:data];  // never a path
  CHECK([[ARMSX2TexturePackStore identifyGameAtPath:chd dataPath:data][@"serial"] isEqual:@"SLES-54164"]);

  // First pack for the game: no question, installed, turned on, dumps kept.
  NSDictionary* inspection = nil;
  NSDictionary* first = Import(@"pack-deflate.zip", Game(@"SLUS-21137"), NO, nil, &inspection);
  CHECK([inspection[@"match"] isEqual:@"same"] && ![inspection[@"needsConfirmation"] boolValue] && ![inspection[@"replacing"] boolValue]);
  CHECK([inspection[@"files"] integerValue] == 5 && [inspection[@"skipped"] integerValue] == 1);
  CHECK([first[@"success"] boolValue] && ![first[@"replaced"] boolValue] && [first[@"named"] integerValue] == 3 && [first[@"unsupported"] integerValue] == 1);
  CHECK([fm fileExistsAtPath:Textures(@"SLUS-21137/replacements/ui/0123456789abcdef-00004a2d.png")]);
  CHECK([fm fileExistsAtPath:Textures(@"SLUS-21137/dumps/keep-00000001.png")]);
  NSDictionary* status = [ARMSX2TexturePackStore statusForSerial:@"SLUS-21137" crc:nil dataPath:data];
  CHECK([status[@"installed"] boolValue] && ![status[@"external"] boolValue] && [status[@"named"] integerValue] == 3);
  CHECK([status[@"source"] isEqual:@"pack-deflate.zip"] && [status[@"sourceKind"] isEqual:@"zip"] && [status[@"enabled"] isEqual:@YES]);
  CHECK([status[@"folder"] isEqual:@"ARMSX2/textures/SLUS-21137/replacements"] && [status[@"formats"][@"ddsBc1"] integerValue] == 1);
  NSString* boot = [ARMSX2TexturePackStore bootPreferencesJSONForDataPath:data];
  CHECK([boot containsString:@"\"SLUS-21137\":true"]);
  CHECK([fm fileExistsAtPath:[data stringByAppendingPathComponent:@"inis/NeoStation-textures.json"]]);

  // The game's own INI value is reported apart from NeoStation's choice.
  CHECK([status[@"globalEnabled"] isEqual:@NO]);
  NSString* ini = [data stringByAppendingPathComponent:@"gamesettings/SLUS-21137_ABCD1234.ini"];
  CHECK([@"[EmuCore/GS]\nLoadTextureReplacements = false\nupscale_multiplier = 2\n" writeToFile:ini atomically:YES encoding:NSUTF8StringEncoding error:nil]);
  CHECK([[ARMSX2TexturePackStore statusForSerial:@"SLUS-21137" crc:@"abcd1234" dataPath:data][@"iniEnabled"] isEqual:@NO]);
  CHECK([ARMSX2TexturePackStore statusForSerial:@"SLUS-21137" crc:nil dataPath:data][@"iniEnabled"] == nil);

  // A replacement asks (replacing), keeps the game's choice and the old files until it commits.
  CHECK([ARMSX2TexturePackStore setEnabled:NO serial:@"SLUS-21137" dataPath:data]);
  NSDictionary* replace = Import(@"pack.tar", Game(@"SLUS-21137"), NO, nil, &inspection);
  CHECK([inspection[@"replacing"] boolValue] && [replace[@"success"] boolValue] && [replace[@"replaced"] boolValue]);
  CHECK([[ARMSX2TexturePackStore statusForSerial:@"SLUS-21137" crc:nil dataPath:data][@"enabled"] isEqual:@NO]);
  CHECK([replace[@"previousPath"] length] && [fm fileExistsAtPath:replace[@"previousPath"]]);
  [ARMSX2TexturePackStore discardPath:replace[@"previousPath"]];

  // Another region: explained first, refused without the user's consent.
  NSDictionary* other = Import(@"pack-other-region.zip", Game(@"SLUS-21137"), NO, nil, &inspection);
  CHECK([inspection[@"match"] isEqual:@"otherSerial"] && [inspection[@"packSerial"] isEqual:@"SLES-54164"] && [inspection[@"packRegion"] isEqual:@"PAL"]);
  CHECK([inspection[@"regionConflict"] boolValue] && [inspection[@"needsConfirmation"] boolValue]);
  CHECK(![other[@"success"] boolValue] && [other[@"error"] isEqual:@"confirmationRequired"]);
  CHECK([fm fileExistsAtPath:Textures(@"SLUS-21137/replacements/ui/0123456789abcdef-00004a2d.png")]);
  CHECK([Import(@"pack-other-region.zip", Game(@"SLUS-21137"), YES)[@"success"] boolValue]);
  CHECK([[ARMSX2TexturePackStore statusForSerial:@"SLUS-21137" crc:nil dataPath:data][@"packSerial"] isEqual:@"SLES-54164"]);

  // A serial taken from a file name needs consent too; an unknown serial is refused.
  NSMutableDictionary* guessed = [Game(@"SLUS-21137") mutableCopy]; guessed[@"source"] = @"name";
  Import(@"pack-deflate.zip", guessed, NO, nil, &inspection);
  CHECK([inspection[@"uncertain"] boolValue] && [inspection[@"needsConfirmation"] boolValue]);
  CHECK([Import(@"pack-deflate.zip", Game(@""), NO)[@"error"] isEqual:@"gameUnknown"]);
  CHECK([Import(@"pack-encrypted.zip", Game(@"SLUS-21137"), NO)[@"error"] isEqual:@"encrypted"]);
  CHECK([Import(@"pack-deflate64.zip", Game(@"SLUS-21137"), NO)[@"error"] isEqual:@"method"]);
  CHECK([Import(@"pack-deflate64.zip", Game(@"SLUS-21137"), NO)[@"detail"] isEqual:@"9"]);
  CHECK([Import(@"pack-unnamed.zip", Game(@"SLUS-21137"), NO)[@"error"] isEqual:@"noNamedTextures"]);
  CHECK([Import(@"not-a-disc.chd", Game(@"SLUS-21137"), NO)[@"error"] isEqual:@"format"]);
  // The engine's decoder is needed for .tar.zst: refused without a running game.
  CHECK([Import(@"pack.tar.zst", Game(@"SLUS-21137"), NO)[@"error"] isEqual:@"zstdNeedsGame"]);

  // In a game: the expander writes the archive's texture entries; they are moved.
  __block int expansions = 0;
  ARMSX2TextureExpander expander = ^NSString*(NSString* archive, NSString* destination, uint64_t available,
                                               const volatile int* cancel, volatile uint64_t* consumed) {
    ++expansions;
    NSString* tree = [fixtures stringByAppendingPathComponent:@"folder/SLUS-21137"];
    return [fm copyItemAtPath:tree toPath:[destination stringByAppendingPathComponent:@"SLUS-21137"] error:nil] ? nil : @"write";
  };
  NSDictionary* zst = Import(@"pack.tar.zst", Game(@"SLUS-21137"), YES, expander, &inspection);
  CHECK(expansions == 1 && [inspection[@"kind"] isEqual:@"tarzst"] && [zst[@"success"] boolValue] && [zst[@"named"] integerValue] == 3);
  ARMSX2TextureExpander failing = ^NSString*(NSString*, NSString*, uint64_t, const volatile int*, volatile uint64_t*) { return @"unsafe"; };
  CHECK([Import(@"pack.tar.zst", Game(@"SLUS-21137"), YES, failing)[@"error"] isEqual:@"unsafe"]);

  // Cancelling keeps the working pack.
  ARMSX2TextureImport* cancelled = [[ARMSX2TextureImport alloc] initWithURL:Fixture(@"pack-deflate.zip") dataPath:data
                                                                       game:Game(@"SLUS-21137") expander:nil];
  CHECK([[cancelled inspectWithProgress:nil][@"success"] boolValue]);
  [cancelled cancel];
  CHECK([[cancelled installAllowingMismatch:YES progress:nil][@"error"] isEqual:@"cancelled"]);
  [cancelled close];
  CHECK([fm fileExistsAtPath:Textures(@"SLUS-21137/replacements/ui/0123456789abcdef-00004a2d.png")]);

  // A folder chosen in Files, named after the serial.
  CHECK([Import(@"folder/SLUS-21137", Game(@"SLUS-21137"), YES)[@"success"] boolValue]);

  // Removal: only the pack, the game's switch goes off, dumps and saves stay.
  NSDictionary* removal = [ARMSX2TexturePackStore removeSerial:@"SLUS-21137" dataPath:data];
  CHECK([removal[@"success"] boolValue] && [fm fileExistsAtPath:removal[@"removingPath"]]);
  CHECK(![fm fileExistsAtPath:Textures(@"SLUS-21137/replacements")] && [fm fileExistsAtPath:Textures(@"SLUS-21137/dumps/keep-00000001.png")]);
  CHECK([[NSString stringWithContentsOfFile:save encoding:NSUTF8StringEncoding error:nil] isEqual:@"memory card"]);
  CHECK([[ARMSX2TexturePackStore statusForSerial:@"SLUS-21137" crc:nil dataPath:data][@"enabled"] isEqual:@NO]);
  CHECK([[ARMSX2TexturePackStore bootPreferencesJSONForDataPath:data] containsString:@"\"SLUS-21137\":false"]);
  CHECK([[ARMSX2TexturePackStore removeSerial:@"SCUS-97399" dataPath:data][@"error"] isEqual:@"missing"]);
  CHECK(![[ARMSX2TexturePackStore removeSerial:@"../SLUS-21137" dataPath:data][@"success"] boolValue]);

  // A pack copied by hand into ARMSX2/textures is described, not trusted.
  [fm createDirectoryAtPath:Textures(@"SLPM-65000") withIntermediateDirectories:YES attributes:nil error:nil];
  CHECK([fm copyItemAtPath:[fixtures stringByAppendingPathComponent:@"payload"] toPath:Textures(@"SLPM-65000/replacements") error:nil]);
  NSDictionary* external = [ARMSX2TexturePackStore statusForSerial:@"SLPM-65000" crc:nil dataPath:data];
  CHECK([external[@"installed"] boolValue] && [external[@"external"] boolValue] && [external[@"named"] integerValue] == 3 &&
        [external[@"unsupported"] integerValue] == 1 && external[@"enabled"] == NSNull.null);

  // Leftovers of an interrupted import, never anything else.
  [fm createDirectoryAtPath:Textures(@".neostation-import-crashed") withIntermediateDirectories:YES attributes:nil error:nil];
  [ARMSX2TexturePackStore sweepLeftoversInDataPath:data];
  CHECK(![fm fileExistsAtPath:Textures(@".neostation-import-crashed")] && [fm fileExistsAtPath:Textures(@"SLPM-65000/replacements")]);
  // Before ARMSX2's first game there is no textures folder yet: the volume is measured anyway,
  // and the install result reports the choice stored under the import's own data folder.
  NSString* fresh = [data stringByAppendingString:@"-fresh"];
  CHECK([fm createDirectoryAtPath:fresh withIntermediateDirectories:YES attributes:nil error:nil]);
  ARMSX2TextureImport* early = [[ARMSX2TextureImport alloc] initWithURL:Fixture(@"pack-deflate.zip") dataPath:fresh
                                                                   game:Game(@"SLUS-21137") expander:nil];
  CHECK([early.dataPath isEqual:fresh]);
  NSDictionary* earlyInspection = [early inspectWithProgress:nil];
  CHECK([earlyInspection[@"success"] boolValue] && [earlyInspection[@"available"] unsignedLongLongValue] > 0);
  CHECK([[early installAllowingMismatch:NO progress:nil][@"success"] boolValue]);
  [early close];
  CHECK([[ARMSX2TexturePackStore statusForSerial:@"SLUS-21137" crc:nil dataPath:early.dataPath][@"enabled"] isEqual:@YES]);
  // A damaged identity record is ignored, never trusted.
  NSString* state = [fresh stringByAppendingPathComponent:@"inis/NeoStation-textures.json"];
  NSMutableDictionary* stored = [[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:state]
                                                                 options:NSJSONReadingMutableContainers error:nil] mutableCopy];
  stored[@"identities"] = [@{} mutableCopy];
  CHECK([[NSJSONSerialization dataWithJSONObject:stored options:0 error:nil] writeToFile:state atomically:YES]);
  [ARMSX2TexturePackStore recordIdentity:@{@"serial": @"SLES-54164"} forGamePath:chd dataPath:fresh];
  stored = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:state] options:NSJSONReadingMutableContainers error:nil];
  for (NSString* key in [stored[@"identities"] allKeys]) stored[@"identities"][key] = @"not a record";
  CHECK([[NSJSONSerialization dataWithJSONObject:stored options:0 error:nil] writeToFile:state atomically:YES]);
  CHECK([[ARMSX2TexturePackStore identifyGameAtPath:chd dataPath:fresh][@"source"] isEqual:@"none"]);

  NSDictionary* formats = [ARMSX2TexturePackStore deviceFormats];
  CHECK(formats[@"bcTextures"] && formats[@"astcTextures"]);
  printf("PASS store: %d checks (identification, verdicts, consent, install/replace/cancel/remove, INI, boot choices, .tar.zst)\n", checks);
  return 0;
} }
