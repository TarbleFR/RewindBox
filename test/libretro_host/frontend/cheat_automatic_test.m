#import <Foundation/Foundation.h>
#import "LibretroCheats.h"
#import "LibretroCheatCatalog.h"
static unsigned checks, failures;
#define CHECK(c,m) do { checks++; if (!(c)) { failures++; fprintf(stderr,"FAIL %s:%d %s\n",__FILE__,__LINE__,m); } } while(0)
static NSData *UTF8(NSString *s) { return [s dataUsingEncoding:NSUTF8StringEncoding]; }
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
  [NSFileManager.defaultManager removeItemAtPath:work error:nil];
 } printf("Automatic cheats: %u checks, %u failures\n",checks,failures);return failures?1:0;
}
