#import <Foundation/Foundation.h>
#import "LibretroCheats.h"
#import "LibretroCheatCatalog.h"
static unsigned failures, checks;
#define CHECK(c, m) do { checks++; if (!(c)) { failures++; fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, m); } } while (0)
static NSData *UTF8(NSString *s) { return [s dataUsingEncoding:NSUTF8StringEncoding]; }
static NSDictionary *Cheat(NSString *code) { return @{@"name":@"Test", @"code":code, @"handler":@0}; }
int main(void) {
  @autoreleasepool {
    NSError *error = nil;
    NSString *cht = @"cheats = 2\ncheat0_desc = \"Infinite health\"\ncheat0_code = \"0024:00+ZEEXIPIE\"\ncheat0_enable = true\ncheat1_desc = \"Memory\"\ncheat1_handler = 1\ncheat1_address = 4\ncheat1_value = 10\n";
    NSArray *records = [LibretroCheats parseCHT:UTF8(cht) error:&error];
    CHECK(records.count == 2 && error == nil, "both native and memory CHT entries retained");
    CHECK(![records[0][@"enabled"] boolValue], "source enable=true cannot enable anything");
    CHECK([records[1][@"raw"][@"address"] isEqual:@"4"], "memory semantics retained without sending an invented native code");
    CHECK([LibretroCheats codesForCheat:records[1] core:@"nestopia" console:@"nes"] == nil, "frontend memory cheats refused by native core adapter");
    NSArray *codes = [LibretroCheats codesForCheat:records[0] core:@"nestopia" console:@"nes"];
    CHECK(codes.count == 2 && [codes[0] isEqual:@"0024:00"], "NES multiline split preserves order and bounds each ABI call");
    CHECK([LibretroCheats codesForCheat:records[0] core:@"future_core" console:@"nes"] == nil, "unknown future core is not falsely advertised as supported");
    for (NSString *bad in @[@"cheats=99999999", @"cheats=-1", @"cheats=1\ncheat0_desc=x\ncheat0_code=\"unterminated",
      @"cheats=1\ncheat0_desc=x\ncheat0_desc=y\ncheat0_code=A", @"cheats=1\ncheat0_code=\"\"", @"cheats=1\ncheat0_handler=banana"]) {
      CHECK([LibretroCheats parseCHT:UTF8(bad) error:&error] == nil && error != nil, "malformed CHT rejected as a whole");
    }
    for (NSString *invalid in @[@"", @"not a code", @"1234:1234", @"A💥", [@"A" stringByPaddingToLength:9000 withString:@"A" startingAtIndex:0]])
      CHECK([LibretroCheats codesForCheat:Cheat(invalid) core:@"nestopia" console:@"nes"] == nil, "invalid and oversized NES code refused");
    CHECK([LibretroCheats codesForCheat:Cheat(@"3C3C-7DD5+7E2C53:7F") core:@"snes9x" console:@"snes"].count == 2, "SNES Game Genie and raw codes");
    CHECK([LibretroCheats codesForCheat:Cheat(@"01234567+123-456-789") core:@"gambatte" console:@"gbc"].count == 2, "GB/GBC formats");
    NSArray *gba = [LibretroCheats codesForCheat:Cheat(@"12345678ABCDEF01+87654321+ABCD") core:@"mgba" console:@"gba"];
    CHECK(gba.count == 1 && [gba[0] isEqual:@"12345678 ABCDEF01+87654321 ABCD"], "OpenEmu GBA words adapted, program grouping preserved");
    CHECK([LibretroCheats codesForCheat:Cheat(@"02002BFC:0000007E") core:@"mgba" console:@"gba"] == nil, "unverified OpenEmu raw address format not guessed");
    CHECK([LibretroCheats codesForCheat:Cheat(@"AAAA-AAAA") core:@"genesis_plus_gx" console:@"md"].count == 1, "Genesis format");
    NSString *xml = @"<systems><system id='openemu.system.snes'><game title='Game (USA)'><hashes><hash md5='0123456789abcdef0123456789abcdef'/></hashes><cheats><cheat code='7E2C53:7F' type='Action Replay' description='Money &amp; items'/></cheats></game></system></systems>";
    NSArray *games = [LibretroCheats parseOpenEmu:UTF8(xml) error:&error];
    CHECK(games.count == 1 && [games[0][@"console"] isEqual:@"snes"], "community system and game parsed");
    CHECK([games[0][@"cheats"][0][@"name"] isEqual:@"Money & items"] && ![games[0][@"cheats"][0][@"enabled"] boolValue], "XML description entities and disabled import");
    CHECK([LibretroCheats parseOpenEmu:UTF8(@"<!DOCTYPE x [<!ENTITY secret SYSTEM 'file:///etc/passwd'>]><systems>&secret;</systems>") error:&error] == nil, "external/internal entity declarations refused");
    NSDictionary *identity = @{@"console":@"snes", @"title":@"Game (Europe)", @"md5":@"0123456789abcdef0123456789abcdef"};
    CHECK([[LibretroCheats matchGame:games[0] identity:identity] isEqual:@"hash"], "file hash outranks imprecise filename");
    NSDictionary *other = @{@"console":@"snes", @"title":@"Game (USA)", @"md5":@"11111111111111111111111111111111"};
    CHECK([[LibretroCheats matchGame:games[0] identity:other] isEqual:@"mismatch"], "same title cannot override a different hash");
    CHECK([[LibretroCheats matchGame:@{@"console":@"snes", @"title":@"Game (Japan)"} identity:identity] isEqual:@"candidate"], "regional title match is manual, never exact");
    CHECK([[LibretroCheats matchGame:@{@"console":@"nes", @"title":@"Game"} identity:identity] isEqual:@"none"], "console identity respected");
    CHECK([[LibretroCheats gitBlobSHA:UTF8(@"hello\n")] isEqual:@"ce013625030ba8dba906f756967f9e9ca394464a"], "Git blob integrity algorithm");
    NSString *folder = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    [[NSFileManager defaultManager] createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *rom = [folder stringByAppendingPathComponent:@"same-title.bin"]; [UTF8(@"abc") writeToFile:rom atomically:YES];
    NSDictionary *first = [LibretroCheats identityAtPath:rom console:@"nes" core:@"nestopia"];
    CHECK([first[@"md5"] isEqual:@"900150983cd24fb0d6963f7d28e17f72"], "actual content streamed and hashed");
    [UTF8(@"def") writeToFile:rom atomically:YES];
    CHECK(![first[@"sha256"] isEqual:[LibretroCheats identityAtPath:rom console:@"nes" core:@"nestopia"][@"sha256"]], "same filename different content cannot share preferences identity");
    CHECK(LibretroCheatCatalog.sources.count >= 2, "multiple independent source adapters");
    CHECK([LibretroCheatCatalog folderForConsole:@"7800"] != nil && [LibretroCheatCatalog folderForConsole:@"gba"] != nil, "catalogues cover enabled and hidden consoles");
    [[NSFileManager defaultManager] removeItemAtPath:folder error:nil];
  }
  printf("Cheats: %u checks, %u failures\n", checks, failures); return failures ? 1 : 0;
}
