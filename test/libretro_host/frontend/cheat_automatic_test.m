#import <Foundation/Foundation.h>
#import "LibretroCheats.h"
#import "LibretroCheatCatalog.h"
static unsigned checks, failures;
#define CHECK(c,m) do { checks++; if (!(c)) { failures++; fprintf(stderr,"FAIL %s:%d %s\n",__FILE__,__LINE__,m); } } while(0)
static NSData *UTF8(NSString *s) { return [s dataUsingEncoding:NSUTF8StringEncoding]; }
static void Put32(uint8_t *p,uint32_t v) { for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i)); }
// Original minimal ISO9660 fixture, no executable, BIOS or commercial game bytes.
static NSData *Disc(NSUInteger stride,NSUInteger header,NSUInteger pregap,NSString *serial) {
  NSMutableData *data=[NSMutableData dataWithLength:(pregap+24)*stride];uint8_t *p=data.mutableBytes;
  uint8_t *pvd=p+(pregap+16)*stride+header;pvd[0]=1;memcpy(pvd+1,"CD001",5);pvd[6]=1;pvd[156]=34;
  Put32(pvd+158,20);Put32(pvd+166,2048);
  uint8_t *entry=p+(pregap+20)*stride+header;entry[0]=46;Put32(entry+2,21);Put32(entry+10,64);entry[32]=12;memcpy(entry+33,"SYSTEM.CNF;1",12);
  NSData *cnf=UTF8([NSString stringWithFormat:@"BOOT = cdrom:\\%@;1\r\n",serial]);memcpy(p+(pregap+21)*stride+header,cnf.bytes,cnf.length);return data;
}
static void Wait(BOOL *done) {
  NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
  while (!*done && deadline.timeIntervalSinceNow>0) [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.01]];
  CHECK(*done,"async operation completed");
}
int main(int argc,const char **argv) { @autoreleasepool {
  NSString *repo=argc>2 ? @(argv[2]) : NSFileManager.defaultManager.currentDirectoryPath;
  NSString *work=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  LibretroCheatCatalog *catalog=[[LibretroCheatCatalog alloc] initWithDirectory:work];
  catalog.bundledDirectory=[repo stringByAppendingPathComponent:@"packages/libretro_internal_bridge/ios/Resources/Cheats"];
  __block NSUInteger requests=0;
  catalog.fetch=^NSData *(NSURL *url,NSUInteger limit,NSError **error) { requests++; if(error)*error=[NSError errorWithDomain:NSURLErrorDomain code:-1009 userInfo:nil]; return nil; };
  __block NSDictionary *official=nil,*community=nil; __block BOOL done=NO;
  [catalog loadSource:@"libretro" console:@"nes" completion:^(NSDictionary *value) {official=value;done=YES;}];Wait(&done);
  CHECK([official[@"games"] count]>2000 && [official[@"bundled"] boolValue],"reference index available with no install or HTTP");
  done=NO;[catalog loadSource:@"openemu-community" console:@"snes" completion:^(NSDictionary *value) {community=value;done=YES;}];Wait(&done);
  CHECK([community[@"games"] count]>0,"complementary initial cheats available offline");
  NSDictionary *game=[community[@"games"] firstObject]; NSString *md5=[game[@"md5s"] firstObject];
  CHECK(md5.length==32,"initial XML carries exact content identity");
  NSDictionary *renamed=@{@"console":@"snes",@"core":@"snes9x",@"title":@"My renamed game",@"md5":md5 ?: @""};
  CHECK([[LibretroCheats matchGame:game identity:renamed] isEqual:@"hash"],"renaming does not prevent automatic XML detection");
  done=NO;[catalog downloadGame:game completion:^(NSArray *cheats,NSError *error) {
    CHECK(error==nil && cheats.count>0,"matching initial codes need no network");
    for(NSDictionary *cheat in cheats) CHECK(![cheat[@"enabled"] boolValue],"initial codes disabled");done=YES;
  }];Wait(&done);
  CHECK(requests==0,"bootstrap, matching and initial cheats perform zero requests");
  NSDictionary *record=[official[@"identities"] firstObject];
  NSDictionary *resolved=[catalog resolveIdentity:@{@"console":@"nes",@"core":@"nestopia",@"title":@"renamed",@"md5":record[@"md5"] ?: @"",@"sha1":record[@"sha1"] ?: @""}];
  CHECK([resolved[@"titles"] containsObject:record[@"title"]],"canonical reference title recovered by content hash");
  CHECK(([[LibretroCheats matchGame:@{@"console":@"nes",@"title":[record[@"title"] stringByAppendingString:@" (Game Genie)"]} identity:resolved] isEqual:@"hash"]),"code-device tag does not hide exact reference match");
  NSDictionary *usa=@{@"console":@"nes",@"title":@"Example (USA)",@"titles":@[@"Example (USA)"]};
  CHECK(([[LibretroCheats matchGame:@{@"console":@"nes",@"title":@"Example (Europe)"} identity:usa] isEqual:@"none"]),"different region excluded");
  CHECK(([[LibretroCheats matchGame:@{@"console":@"nes",@"title":@"Example (USA) (Rev 2)"} identity:@{@"console":@"nes",@"titles":@[@"Example (USA) (Rev 1)"]}] isEqual:@"none"]),"different explicit revisions excluded");
  CHECK(([[LibretroCheats matchGame:@{@"console":@"nes",@"title":@"Example (USA)"} identity:@{@"console":@"nes",@"title":@"Example (USA)"}] isEqual:@"candidate"]),"same filename alone never proves a version");
  NSString *folder=[work stringByAppendingPathComponent:@"libretro/nes"];
  [NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
  [UTF8(@"{broken") writeToFile:[folder stringByAppendingPathComponent:@"index.json"] atomically:YES];
  done=NO;[catalog loadSource:@"libretro" console:@"nes" completion:^(NSDictionary *value) {CHECK([value[@"games"] count]>2000,"previous download with corrupt index recovers bundled index offline");done=YES;}];Wait(&done);
  NSMutableDictionary *legacy=[official mutableCopy];[legacy removeObjectForKey:@"bundled"];[legacy removeObjectForKey:@"schema"];
  [[NSJSONSerialization dataWithJSONObject:legacy options:0 error:nil] writeToFile:[folder stringByAppendingPathComponent:@"index.json"] atomically:YES];
  done=NO;[catalog loadSource:@"libretro" console:@"nes" completion:^(NSDictionary *value) {CHECK(value!=nil && ![value[@"bundled"] boolValue],"already installed v463 index remains indexed without migration");done=YES;}];Wait(&done);
  legacy[@"games"]=@[];
  [[NSJSONSerialization dataWithJSONObject:legacy options:0 error:nil] writeToFile:[folder stringByAppendingPathComponent:@"index.json"] atomically:YES];
  done=NO;[catalog loadSource:@"libretro" console:@"nes" completion:^(NSDictionary *value) {CHECK([value[@"games"] count]>2000 && [value[@"bundled"] boolValue],"downloaded-but-empty valid legacy index cannot hide the verified reference catalogue");done=YES;}];Wait(&done);
  done=NO;[catalog loadSource:@"libretro" console:@"tg16" completion:^(NSDictionary *value) {CHECK([value[@"games"] count]>0 && [value[@"games"][0][@"console"] isEqual:@"tg16"],"hidden console aliases use the same central index");done=YES;}];Wait(&done);
  done=NO;[catalog removeSource:@"libretro" console:@"nes" completion:^{done=YES;}];Wait(&done);
  done=NO;[catalog loadSource:@"libretro" console:@"nes" completion:^(NSDictionary *value) {CHECK(value==nil,"explicitly removed bundled source stays disabled");done=YES;}];Wait(&done);
  // Headerless aliases come from bytes, independently of a user filename.
  NSString *rom=[work stringByAppendingPathComponent:@"renamed.nes"];
  NSMutableData *nes=[NSMutableData dataWithLength:16];memcpy(nes.mutableBytes,"NES\x1a",4);[nes appendData:UTF8(@"abc")];[nes writeToFile:rom atomically:YES];
  NSDictionary *identity=[LibretroCheats identityAtPath:rom console:@"nes" core:@"nestopia"];
  CHECK([identity[@"md5s"] containsObject:@"900150983cd24fb0d6963f7d28e17f72"],"iNES header removed for reference hash only");
  CHECK([identity[@"sha1s"] containsObject:@"a9993e364706816aba3e25717850c26c9cd0d89d"],"SHA-1 canonical alias correct");
  CHECK(![identity[@"sha256"] isEqual:[LibretroCheats digest:UTF8(@"abc")]],"preferences retain full original content identity");
  CHECK([identity[@"crc32"] length]==8,"CRC32 available for diagnosis");
  NSString *cue=[work stringByAppendingPathComponent:@"renamed.cue"];
  [UTF8(@"FILE \"renamed.nes\" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n") writeToFile:cue atomically:YES];
  CHECK([[LibretroCheats identityContentPath:cue] isEqual:rom],"CUE resolves actual local game track instead of hashing descriptor text");
  CHECK([[LibretroCheats identityAtPath:cue console:@"psx" core:@"mednafen_psx_hw"][@"md5"] isEqual:identity[@"md5"]],"renamed CUE hashes actual track content");
  [UTF8(@"FILE \"../outside.bin\" BINARY\n") writeToFile:cue atomically:YES];
  CHECK([[LibretroCheats identityContentPath:cue] isEqual:cue],"CUE traversal never reads another folder");
  CHECK(([LibretroCheats codesForCheat:@{@"code":@"80012345 007F+30010000 00FF",@"handler":@0} core:@"mednafen_psx_hw" console:@"psx"].count==1),"PSX program preserves bounded simple GameShark writes");
  CHECK(([LibretroCheats codesForCheat:@{@"code":@"D0012345 0001+80012345 0002",@"handler":@0} core:@"mednafen_psx_hw" console:@"psx"]==nil),"unreviewed PSX conditional opcode remains explicitly unavailable");
  CHECK(([LibretroCheats codesForCheat:@{@"code":@"22000024 0000007F",@"handler":@0} core:@"desmume" console:@"nds"].count==1),"DeSmuME Action Replay adapter retains a complete program");
  NSError *parseError=nil;
  NSArray *separators=[LibretroCheats parseCHT:UTF8(@"cheats=2\ncheat0_desc=Section\ncheat0_code=\"\"\ncheat1_desc=Counter\ncheat1_code=0024:7F") error:&parseError];
  CHECK(separators.count==1 && parseError==nil,"explicit CHT separator does not hide valid following codes");
  NSString *longCode=[@"A" stringByPaddingToLength:9000 withString:@"A" startingAtIndex:0];
  NSArray *longEntries=[LibretroCheats parseCHT:UTF8([NSString stringWithFormat:@"cheats=1\ncheat0_desc=Long\ncheat0_code=\"%@\"",longCode]) error:&parseError];
  CHECK(longEntries.count==1 && [LibretroCheats codesForCheat:longEntries[0] core:@"nestopia" console:@"nes"]==nil,"long source program is retained visibly but unavailable for unsafe activation");
  __block NSDictionary *psx=nil;done=NO;
  [catalog loadSource:@"libretro" console:@"psx" completion:^(NSDictionary *value){psx=value;done=YES;}];Wait(&done);
  NSDictionary *ff7=nil;for(NSDictionary *g in psx[@"games"])if([g[@"title"] isEqual:@"Final Fantasy VII (USA)"])ff7=g;
  CHECK(ff7!=nil,"actual reviewed PS1 index contains FFVII USA");
  for(NSArray *layout in @[@[@2048,@0,@0],@[@2352,@24,@0],@[@2352,@16,@0],@[@2352,@24,@150]]) {
    NSString *disc=[work stringByAppendingPathComponent:@"renamed.iso"];
    [Disc([layout[0] unsignedIntegerValue],[layout[1] unsignedIntegerValue],[layout[2] unsignedIntegerValue],@"SCUS_941.63") writeToFile:disc atomically:YES];
    CHECK([[LibretroCheats playStationSerialAtPath:disc] isEqual:@"SCUS-94163"],"ISO/raw mode1/mode2/pregap identifies SYSTEM.CNF without basename");
    NSDictionary *identified=[catalog resolveIdentity:[LibretroCheats identityAtPath:disc console:@"psx" core:@"mednafen_psx_hw"]];
    CHECK([identified[@"serialTitles"] containsObject:@"Final Fantasy VII (USA) (Disc 1)"],"reviewed RDB serial resolves renamed PS1 title");
    CHECK([[LibretroCheats matchGame:ff7 identity:identified] isEqual:@"candidate"],"serial matching discovers generic multidisc codes without asserting a revision hash");
  }
  NSDictionary *fr=[catalog resolveIdentity:@{@"console":@"psx",@"core":@"mednafen_psx_hw",@"md5":@"cb1dfccc75154da5cf08994130139216",@"titleHints":@[@"Final Fantasy VII (USA)"]}];
  CHECK([[LibretroCheats matchGame:ff7 identity:fr] isEqual:@"none"],"French content hash excludes USA codes even with misleading library title");
  CHECK(([[LibretroCheats matchGame:ff7 identity:@{@"console":@"psx",@"title":@"renamed",@"titleHints":@[@"Final Fantasy VII"]}] isEqual:@"candidate"]),"library metadata discovers renamed compressed discs as uncertain candidates");
  NSString *fake=[work stringByAppendingPathComponent:@"SCUS-94163.iso"];[UTF8(@"BOOT = cdrom:\\SCUS_941.63;1") writeToFile:fake atomically:YES];
  CHECK([LibretroCheats playStationSerialAtPath:fake]==nil,"serial text outside a valid ISO filesystem is not trusted");
  NSData *ff7data=[NSData dataWithContentsOfFile:[repo stringByAppendingPathComponent:@"test/fixtures/libretro_cheats/ff7-usa-original.cht"]];
  CHECK([[LibretroCheats gitBlobSHA:ff7data] isEqual:ff7[@"sha"]],"FFVII fixture is the unchanged reviewed upstream file");
  NSArray *ff7codes=[LibretroCheats parseCHT:ff7data error:&parseError];CHECK(ff7codes.count==19,"all actual FFVII CHT entries parse");
  for(NSString *core in @[@"mednafen_psx_hw",@"mednafen_psx"]) {
    NSUInteger supported=0;for(NSDictionary *r in ff7codes)if([LibretroCheats codesForCheat:r core:core console:@"psx"])supported++;
    CHECK(supported==17,"both Beetle variants accept 17 simple FFVII programs and explicitly reject two repeat programs");
    CHECK(([[LibretroCheats codesForCheat:ff7codes.lastObject core:core console:@"psx"] isEqual:@[@"8009D260 967F+8009D262 0098"]]),"actual Max Gil plus-separated words become complete libretro program");
  }
  [NSFileManager.defaultManager removeItemAtPath:work error:nil];
 } printf("Automatic cheats: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
