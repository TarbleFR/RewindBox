// Opt-in network integration: real pinned repositories, then a disconnected reload.
#import <Foundation/Foundation.h>
#import "LibretroCheatCatalog.h"
#import "LibretroCheats.h"
// Reuse the production bounded NSURLSession delegate. Only CI API requests get
// the runner's read-only token; raw data stays public and the app has no token.
@interface LibretroCheatTransfer : NSObject <NSURLSessionDataDelegate>
@property(nonatomic, strong) NSMutableData *data;
@property(nonatomic, strong) NSError *error;
@property(nonatomic) NSUInteger limit;
@property(nonatomic, strong) dispatch_semaphore_t done;
@end
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
  NSString *token = NSProcessInfo.processInfo.environment[@"GH_TOKEN"];
  if (token.length) catalog.fetch = ^NSData *(NSURL *url,NSUInteger limit,NSError **error) {
    LibretroCheatTransfer *transfer=[LibretroCheatTransfer new];
    transfer.data=[NSMutableData data];transfer.limit=limit;transfer.done=dispatch_semaphore_create(0);
    NSURLSessionConfiguration *configuration=NSURLSessionConfiguration.ephemeralSessionConfiguration;
    configuration.timeoutIntervalForRequest=20;configuration.timeoutIntervalForResource=30;
    NSMutableDictionary *headers=[@{@"User-Agent":@"NeoStation-CheatCatalog-CI",@"Accept":@"application/vnd.github+json"} mutableCopy];
    if ([url.host isEqual:@"api.github.com"]) headers[@"Authorization"]=[@"Bearer " stringByAppendingString:token];
    configuration.HTTPAdditionalHeaders=headers;
    NSURLSession *session=[NSURLSession sessionWithConfiguration:configuration delegate:transfer delegateQueue:nil];
    [[session dataTaskWithURL:url] resume];
    BOOL timedOut=dispatch_semaphore_wait(transfer.done,dispatch_time(DISPATCH_TIME_NOW,35*NSEC_PER_SEC))!=0;
    [session invalidateAndCancel];
    if(timedOut){if(error)*error=[NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorTimedOut userInfo:nil];return nil;}
    if(error)*error=transfer.error;return transfer.error ? nil : [transfer.data copy];
  };
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
  __block BOOL psxDone=NO;__block NSDictionary *ff7=nil;
  [catalog installSource:@"libretro" console:@"psx" update:NO completion:^(NSDictionary *index,NSError *error){
    CHECK(error==nil && [index[@"games"] count]>0,"real PS1 source installs and indexes");
    for(NSDictionary *game in index[@"games"])if([game[@"title"] isEqual:@"Final Fantasy VII (USA)"])ff7=game;
    psxDone=YES;
  }];Wait(&psxDone);CHECK(ff7!=nil,"live PS1 source lists actual FFVII USA");
  if(ff7){psxDone=NO;[catalog downloadGame:ff7 completion:^(NSArray *cheats,NSError *error){
    CHECK(error==nil && cheats.count==19,"real FFVII resource downloads, validates and parses all 19 codes");
    NSUInteger supported=0;for(NSDictionary *cheat in cheats)if([LibretroCheats codesForCheat:cheat core:@"mednafen_psx_hw" console:@"psx"])supported++;
    CHECK(supported==17,"downloaded FFVII contains 17 supported native programs");psxDone=YES;
  }];Wait(&psxDone);[downloaded addObject:ff7];}
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
