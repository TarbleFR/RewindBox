// Opt-in network integration: real pinned repositories, then a disconnected reload.
#import <Foundation/Foundation.h>
#import "LibretroCheatCatalog.h"
static unsigned checks, failures;
#define CHECK(c,m) do { checks++; if (!(c)) { failures++; fprintf(stderr,"FAIL %s\n",m); } } while(0)
static void Wait(BOOL *done) {
  NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:120];
  while (!*done && deadline.timeIntervalSinceNow > 0) [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
  CHECK(*done,"network operation completed within the test deadline");
}
int main(void) { @autoreleasepool {
  NSString *root = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  LibretroCheatCatalog *catalog = [[LibretroCheatCatalog alloc] initWithDirectory:root];
  NSMutableArray *downloaded = [NSMutableArray array];
  for (NSString *source in @[@"libretro",@"openemu-community"]) {
    __block BOOL done = NO; __block NSDictionary *index = nil;
    [catalog installSource:source console:@"snes" update:NO completion:^(NSDictionary *value,NSError *error) {
      CHECK(error == nil && [value[@"games"] count] > 0,"real source installs with reviewed licence and nonempty SNES games");
      if (error) fprintf(stderr,"%s: %s\n",source.UTF8String,error.localizedDescription.UTF8String);
      index = value; done = YES;
    }]; Wait(&done);
    if (!index) continue;
    NSDictionary *game = [index[@"games"] firstObject]; done = NO;
    [catalog downloadGame:game completion:^(NSArray<NSDictionary *> *cheats,NSError *error) {
      CHECK(error == nil && cheats.count > 0,"real source game downloads and parses");
      BOOL off = YES; for (NSDictionary *cheat in cheats) off &= ![cheat[@"enabled"] boolValue];
      CHECK(off,"downloaded real catalogue never enables codes");
      if (error) fprintf(stderr,"%s\n",error.localizedDescription.UTF8String);
      done = YES;
    }]; Wait(&done);
    [downloaded addObject:game];
    printf("Downloaded %s revision %s (%lu games)\n",source.UTF8String,[index[@"revision"] UTF8String],(unsigned long)[index[@"games"] count]);
  }
  CHECK(downloaded.count == 2,"both independent online sources downloaded");
  LibretroCheatCatalog *offline = [[LibretroCheatCatalog alloc] initWithDirectory:root];
  offline.fetch = ^NSData *(NSURL *url,NSUInteger limit,NSError **error) {
    CHECK(NO,"offline reload must not request any network resource");
    if(error)*error=[NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorNotConnectedToInternet userInfo:nil]; return nil;
  };
  for (NSDictionary *game in downloaded) {
    __block BOOL done = NO;
    [offline downloadGame:game completion:^(NSArray<NSDictionary *> *cheats,NSError *error) {
      CHECK(error == nil && cheats.count > 0,"previously downloaded real codes available offline"); done=YES;
    }]; Wait(&done);
  }
  [NSFileManager.defaultManager removeItemAtPath:root error:nil];
 } printf("Live cheat catalogues: %u checks, %u failures\n",checks,failures); return failures ? 1 : 0; }
