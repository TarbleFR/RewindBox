#import <Foundation/Foundation.h>
#import "LibretroCheats.h"
#import "LibretroCheatCatalog.h"
static unsigned checks, failures;
#define CHECK(c,m) do { checks++; if (!(c)) { failures++; fprintf(stderr,"FAIL %s:%d %s\n",__FILE__,__LINE__,m); } } while(0)
static NSData *JSON(id value) { return [NSJSONSerialization dataWithJSONObject:value options:0 error:nil]; }
static void Wait(BOOL *done) {
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:5];
  while (!*done && deadline.timeIntervalSinceNow > 0) [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.01]];
  CHECK(*done, "async catalogue operation completed");
}
int main(int argc, const char **argv) {
 @autoreleasepool {
  NSString *root = argc > 2 ? @(argv[2]) : NSFileManager.defaultManager.currentDirectoryPath;
  NSString *work = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  LibretroCheatCatalog *catalog = [[LibretroCheatCatalog alloc] initWithDirectory:work];
  NSData *cht = [@"cheats=1\ncheat0_desc=\"Synthetic test counter\"\ncheat0_code=\"0024:00\"\ncheat0_enable=true" dataUsingEncoding:NSUTF8StringEncoding];
  NSData *xml = [@"<systems><system id='openemu.system.snes'><game title='Synthetic (USA)'><hashes><hash md5='900150983cd24fb0d6963f7d28e17f72'/></hashes><cheats><cheat code='7E0024:00' description='Synthetic counter' type='Action Replay'/></cheats></game></system></systems>" dataUsingEncoding:NSUTF8StringEncoding];
  NSString *chtTree = @"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", *systemTree = @"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
  __block BOOL offline = NO, changeLicense = NO; __block NSUInteger requests = 0;
  catalog.fetch = ^NSData *(NSURL *url, NSUInteger limit, NSError **error) {
    requests++;
    if (offline) { if (error) *error = [NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorNotConnectedToInternet userInfo:nil]; return nil; }
    NSString *path = url.path;
    BOOL community = [path containsString:@"skyzyx"];
    NSDictionary *source = LibretroCheatCatalog.sources[community ? 1 : 0];
    if ([path hasSuffix:@"/LICENSE"]) return [NSData dataWithContentsOfFile:[root stringByAppendingPathComponent:community ? @"test/fixtures/libretro_cheats/openemu-LICENSE" : @"test/fixtures/libretro_cheats/libretro-LICENSE"]];
    if ([path hasSuffix:@"/commits/master"]) return JSON(@{@"sha":@"cccccccccccccccccccccccccccccccccccccccc"});
    if ([path hasSuffix:@"/cheats-database.xml"]) return xml;
    if ([path hasSuffix:@".cht"]) return cht;
    if ([path hasSuffix:chtTree]) return JSON(@{@"tree":@[@{@"path":@"Nintendo - Nintendo Entertainment System",@"sha":systemTree,@"type":@"tree"}],@"truncated":@NO});
    if ([path hasSuffix:systemTree]) return JSON(@{@"tree":@[@{@"path":@"Synthetic (USA).cht",@"sha":[LibretroCheats gitBlobSHA:cht],@"type":@"blob",@"size":@(cht.length)}],@"truncated":@NO});
    NSDictionary *license = @{@"path":@"LICENSE",@"sha":changeLicense ? chtTree : source[@"licenseSHA"],@"type":@"blob"};
    NSDictionary *data = community ? @{@"path":@"cheats-database.xml",@"sha":[LibretroCheats gitBlobSHA:xml],@"type":@"blob"}
                                    : @{@"path":@"cht",@"sha":chtTree,@"type":@"tree"};
    return JSON(@{@"tree":@[license,data],@"truncated":@NO});
  };
  __block BOOL done = NO; __block NSDictionary *nes = nil, *snes = nil;
  [catalog installSource:@"libretro" console:@"nes" update:NO completion:^(NSDictionary *value, NSError *error) { nes=value; CHECK(error == nil,"official source installs with verified licence"); done=YES; }]; Wait(&done);
  CHECK([nes[@"games"] count] == 1, "official index contains a complete game entry");
  done = NO;
  [catalog installSource:@"openemu-community" console:@"snes" update:NO completion:^(NSDictionary *value, NSError *error) { snes=value; CHECK(error == nil,"independent community XML source installs"); done=YES; }]; Wait(&done);
  CHECK([snes[@"games"] count] == 1, "community hashes and codes retained");
  done = NO;
  [catalog downloadGame:nes[@"games"][0] completion:^(NSArray *cheats, NSError *error) {
    CHECK(error == nil && cheats.count == 1 && ![cheats[0][@"enabled"] boolValue], "download stays disabled regardless of source enable flag");
    CHECK([cheats[0][@"source"] isEqual:@"libretro"] && [cheats[0][@"license"] isEqual:@"CC BY-SA 4.0"], "download carries provenance/licence"); done=YES;
  }]; Wait(&done);
  offline=YES; NSUInteger before=requests; done=NO;
  [catalog downloadGame:nes[@"games"][0] completion:^(NSArray *cheats, NSError *error) { CHECK(error == nil && cheats.count == 1,"downloaded game works offline"); done=YES; }]; Wait(&done);
  CHECK(requests==before,"offline hit performs no HTTP request");
  done=NO; [catalog loadSource:@"libretro" console:@"nes" completion:^(NSDictionary *value) { CHECK([value[@"revision"] isEqual:nes[@"revision"]],"installed index survives reload offline"); done=YES; }]; Wait(&done);
  offline=NO; changeLicense=YES; done=NO;
  [catalog installSource:@"libretro" console:@"nes" update:YES completion:^(NSDictionary *value, NSError *error) { CHECK(value==nil && error!=nil,"changed licence refuses update before replacing data"); done=YES; }]; Wait(&done);
  done=NO; [catalog loadSource:@"libretro" console:@"nes" completion:^(NSDictionary *value) { CHECK([value[@"revision"] isEqual:nes[@"revision"]],"failed update keeps working catalogue"); done=YES; }]; Wait(&done);
  done=NO; [catalog removeSource:@"libretro" console:@"nes" completion:^{done=YES;}]; Wait(&done);
  done=NO; [catalog loadSource:@"libretro" console:@"nes" completion:^(NSDictionary *value) { CHECK(value==nil,"catalogue removal deletes its local data"); done=YES; }]; Wait(&done);
  done=NO; [catalog loadSource:@"openemu-community" console:@"snes" completion:^(NSDictionary *value) { CHECK(value!=nil,"removing one source preserves another"); done=YES; }]; Wait(&done);
  [[NSFileManager defaultManager] removeItemAtPath:work error:nil];
 }
 printf("Cheat catalogues: %u checks, %u failures\n", checks, failures); return failures ? 1 : 0;
}
