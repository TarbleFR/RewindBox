// SPDX-License-Identifier: GPL-3.0-or-later
// The original manager cases execute unchanged; new cases exercise the shared
// installation across independent callers/relaunch and exact published chunks.
#define main Catalogue476RegressionMain
#import "unified_catalog_runtime_native.m"
#undef main

@interface NeoUnifiedCheatCatalog (InstallationProbe)
- (NSError *)installPack:(NSDictionary *)pack manifest:(NSDictionary *)manifest;
@end
@interface Catalogue477Probe : NeoUnifiedCheatCatalog
@property(atomic) NSUInteger packAttempts;
@end
@implementation Catalogue477Probe
- (NSError *)installPack:(NSDictionary *)pack manifest:(NSDictionary *)manifest {
  @synchronized(self){self.packAttempts++;}
  return [super installPack:pack manifest:manifest];
}
@end

static Catalogue477Probe *SharedProbe(NSString *root,NSDictionary *fixture,NSMutableArray *requests) {
  Catalogue477Probe *catalog=[Catalogue477Probe new];
  catalog.storageDirectory=[root stringByAppendingPathComponent:@"installed"];
  catalog.bundledDirectory=[root stringByAppendingPathComponent:@"bundle"];
  [NSFileManager.defaultManager createDirectoryAtPath:catalog.bundledDirectory withIntermediateDirectories:YES attributes:nil error:nil];
  [Bytes(fixture[@"manifest"]) writeToFile:[catalog.bundledDirectory stringByAppendingPathComponent:@"manifest.json"] atomically:YES];
  catalog.manifestURL=[NSURL URLWithString:@"https://catalogue.example/manifest.json"];
  catalog.fetch=^(NSURL *url,NSUInteger limit,void(^done)(NSData*,NSError*)) {
    NSString *path=[url.path substringFromIndex:1];
    @synchronized(requests){[requests addObject:path];}
    NSData *data=fixture[@"responses"][path];
    CHECK(data && data.length<=limit,"only a known bounded immutable source is fetched");done(data,nil);
  };
  return catalog;
}
static NSDictionary *DownloadInGame(NeoUnifiedCheatCatalog *catalog,NSDictionary *identity) {
  __block BOOL done=NO;__block NSDictionary *result=nil;
  [catalog installAllForIdentity:identity progress:nil completion:^(NSDictionary *value,NSError *error){
    CHECK(!error && value,"in-game installation succeeds");result=value;done=YES;
  }];Spin(^BOOL{return done;});return result;
}
static NSDictionary *FileIdentity(NSString *root) {
  NSMutableDictionary *files=[NSMutableDictionary dictionary];
  for(NSString *name in [NSFileManager.defaultManager subpathsAtPath:root]) {
    NSString *path=[root stringByAppendingPathComponent:name];
    NSDictionary *attrs=[NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
    if([attrs.fileType isEqual:NSFileTypeRegular])files[name]=@{@"sha256":Hash([NSData dataWithContentsOfFile:path]),@"modified":attrs.fileModificationDate};
  }
  return files;
}
static void GlobalInstallationChecks(NSString *root,BOOL baseline) {
  NSDictionary *fixture=Fixture();NSMutableArray *requests=[NSMutableArray array];
  Catalogue477Probe *catalog=SharedProbe(root,fixture,requests);
  NSDictionary *complete=DownloadInGame(catalog,fixture[@"manifest"][@"games"][0]);
  CHECK([complete[@"installed_games"] unsignedIntegerValue]==3,"first request installs the common catalogue");
  NSUInteger attempts=catalog.packAttempts,fetches=requests.count;
  NSDictionary *files=FileIdentity(catalog.storageDirectory);
  DownloadInGame(catalog,fixture[@"manifest"][@"games"][1]);
  CHECK(catalog.packAttempts==attempts,"completed catalogue must not run any pack work again");
  CHECK(requests.count==fetches,"a second console performs zero catalogue network requests");
  CHECK([FileIdentity(catalog.storageDirectory) isEqual:files],"second request writes no duplicate or replacement file");
  if(baseline)return;
  CHECK([Load(catalog)[@"installation_state"] isEqual:@"complete"],"common snapshot reports complete");

  // Installation may have been interrupted after chunks were committed but
  // before its old metadata checkpoint. A new process must recover the files.
  [NSFileManager.defaultManager removeItemAtPath:[catalog.storageDirectory stringByAppendingPathComponent:@"installed.json"] error:nil];
  requests=[NSMutableArray array];Catalogue477Probe *reopened=SharedProbe(root,fixture,requests);
  NSDictionary *recovered=Load(reopened);
  CHECK([recovered[@"installation_state"] isEqual:@"complete"],"relaunch recovers completed files without installed.json");
  CHECK([recovered[@"installed_packs"] unsignedIntegerValue]==3,"all consoles share recovered pack counts");
  CHECK([recovered[@"download_requested"] boolValue],"the original download choice survives relaunch");
  files=FileIdentity(reopened.storageDirectory);
  DownloadInGame(reopened,fixture[@"manifest"][@"games"][2]);
  CHECK(!reopened.packAttempts && !requests.count,"relaunch and a third console do not reinstall or fetch");
  CHECK([FileIdentity(reopened.storageDirectory) isEqual:files],"recovered completed action writes nothing");

  NSDictionary *game=fixture[@"manifest"][@"games"][1],*pack=fixture[@"manifest"][@"packs"][1];
  NSString *chunk=[reopened.storageDirectory stringByAppendingPathComponent:[NSString stringWithFormat:@"files/%@.json",game[@"sha256"]]];
  NSString *packed=[reopened.storageDirectory stringByAppendingPathComponent:[NSString stringWithFormat:@"packs/%@.gz",pack[@"sha256"]]];
  [NSFileManager.defaultManager removeItemAtPath:chunk error:nil];[NSFileManager.defaultManager removeItemAtPath:packed error:nil];
  requests=[NSMutableArray array];Catalogue477Probe *partial=SharedProbe(root,fixture,requests);
  CHECK([Load(partial)[@"installation_state"] isEqual:@"partial"],"missing files are a partial install, not a second catalogue");
  DownloadInGame(partial,game);
  CHECK(partial.packAttempts==1 && requests.count==1 && [requests[0] isEqual:pack[@"path"]],"resume schedules and fetches exactly one missing pack");
  CHECK([Load(partial)[@"installation_state"] isEqual:@"complete"],"resumed common catalogue is complete");
  CHECK([FileIdentity(partial.storageDirectory) count]==files.count,"resume does not multiply stored files");
}

static void SharedRequestsAndPriority(NSString *root) {
  NSDictionary *fixture=Fixture();NSMutableArray *requests=[NSMutableArray array];
  Catalogue477Probe *catalog=SharedProbe(root,fixture,requests);
  NSOperationQueue *workers=[catalog valueForKey:@"packQueue"];workers.suspended=YES;
  __block NSUInteger completions=0,reads=0,notifications=0;
  id observer=[NSNotificationCenter.defaultCenter addObserverForName:@"NeoUnifiedCheatCatalogProgressNotification" object:catalog queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note){
    CHECK(NSThread.isMainThread,"shared progress notification is on main");notifications++;
  }];
  for(NSUInteger index=0;index<2;index++)[catalog installAllForIdentity:fixture[@"manifest"][@"games"][index] progress:nil completion:^(NSDictionary *result,NSError *error){
    CHECK(!error && [result[@"installed_games"] unsignedIntegerValue]==3,"concurrent consoles finish the same installation");completions++;
  }];
  Spin(^BOOL{return workers.operationCount==3;});
  NSDictionary *running=Load(catalog);
  CHECK([running[@"installation_state"] isEqual:@"installing"] && running[@"progress"],"another menu sees the running global operation");
  NSDictionary *game=fixture[@"manifest"][@"games"][2];
  for(NSUInteger index=0;index<2;index++)[catalog cheatsForGame:game completion:^(NSArray *programs,NSError *error){CHECK(!error && programs.count==2,"joined game readers obtain the complete verified chunk");reads++;}];
  Spin(^BOOL{
    NSDictionary *jobs=[catalog valueForKey:@"packJobs"];
    return [jobs[fixture[@"manifest"][@"packs"][2][@"sha256"]][@"callbacks"] count]==3;
  });
  NSDictionary *job=[catalog valueForKey:@"packJobs"][fixture[@"manifest"][@"packs"][2][@"sha256"]];
  CHECK(((NSOperation *)job[@"operation"]).queuePriority==NSOperationQueuePriorityVeryHigh,"a newly opened game raises the existing pack priority");
  CHECK(workers.operationCount==3 && !catalog.packAttempts,"bulk and per-game callers queue one operation per immutable pack");
  workers.suspended=NO;Spin(^BOOL{return completions==2 && reads==2;});
  CHECK(catalog.packAttempts==3 && requests.count==3,"concurrent callers neither download nor expand a pack twice");
  CHECK(notifications>0,"all open console menus receive the shared progress");
  [NSNotificationCenter.defaultCenter removeObserver:observer];
}

static void PublishedPS2PS3Chunks(NSString *root,NSString *repository) {
  NSMutableArray *games=[NSMutableArray array],*packs=[NSMutableArray array];
  NSMutableDictionary *responses=[NSMutableDictionary dictionary];
  for(NSString *name in @[@"bladestorm-bles00113.json",@"gow2-scus97481.json"]) {
    NSData *data=[NSData dataWithContentsOfFile:[repository stringByAppendingPathComponent:[@"test/fixtures/cheats477/" stringByAppendingString:name]]];
    NSDictionary *chunk=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    CHECK(chunk && data.length,"exact delivered source chunk exists");
    NSString *expected=[name hasPrefix:@"blade"] ? @"f4d2d47f81eff1e2a81daad1084597b40127e69f0891f27104a170a245bb6913" : @"4ebbd023af89055f3c25b6a91d028e69641dc8a6962af46a85cf2a405d54cf86";
    CHECK([Hash(data) isEqual:expected],"test uses the exact published Bladestorm or PS2 program bytes");
    NSMutableDictionary *game=[chunk[@"game"] mutableCopy];NSString *gid=game[@"id"],*pid=[@"fixture-" stringByAppendingString:gid];
    NSData *expanded=Bytes(@{@"schema_version":@1,@"files":@[@{@"game_id":gid,@"data":[data base64EncodedStringWithOptions:0]}]});NSData *compressed=Gzip(expanded);
    NSString *path=[NSString stringWithFormat:@"packs/%@.json.gz",pid];
    game[@"path"]=[NSString stringWithFormat:@"games/%@.json",gid];game[@"sha256"]=Hash(data);game[@"size"]=@(data.length);game[@"pack_id"]=pid;
    [games addObject:game];[packs addObject:@{@"id":pid,@"path":path,@"sha256":Hash(compressed),@"size":@(compressed.length),@"uncompressed_size":@(expanded.length),@"game_ids":@[gid]}];responses[path]=compressed;
  }
  NSDictionary *fixture=@{@"manifest":@{@"schema_version":@1,@"games":games,@"packs":packs,@"sources":@[]},@"responses":responses};
  NSMutableArray *requests=[NSMutableArray array];Catalogue477Probe *catalog=SharedProbe(root,fixture,requests);
  DownloadInGame(catalog,games[0]);CHECK(requests.count==2,"one download installs both PS2 and PS3 published sources");
  Catalogue477Probe *reopened=SharedProbe(root,fixture,[NSMutableArray array]);Load(reopened);
  for(NSDictionary *game in games) {
    NSMutableDictionary *identity=[game mutableCopy];
    if([game[@"system"] isEqual:@"ps2"])identity[@"identities"]=@[ID(@"serial",@"SCUS-97481",@"ps2-disc-serial"),ID(@"ps2_crc",@"2F123FD8",@"pcsx2-executable-crc")];
    __block BOOL done=NO;
    [reopened gamesForIdentity:identity completion:^(NSArray *matches,NSError *error){
      CHECK(!error && matches.count==1 && [matches[0][@"installed"] boolValue],"reopened common catalogue detects the actual PS2 or Bladestorm edition");
      [reopened cheatsForGame:matches[0] completion:^(NSArray *programs,NSError *problem){CHECK(!problem && programs.count==([game[@"system"] isEqual:@"ps3"]?4:54),"all exact published source programs are visible offline");done=YES;}];
    }];Spin(^BOOL{return done;});
  }
  CHECK(!reopened.packAttempts,"offline PS2/PS3 discovery does not revisit installed packs");
}

int main(int argc,const char *argv[]) {@autoreleasepool{
  BOOL baseline=argc==2 && strcmp(argv[1],"--baseline")==0;
  NSString *repository=baseline ? @"" : (argc==2 ? [NSString stringWithUTF8String:argv[1]] : @"");
  NSString *root=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  GlobalInstallationChecks([root stringByAppendingPathComponent:@"shared"],baseline);
  if(!baseline){
    SharedRequestsAndPriority([root stringByAppendingPathComponent:@"concurrent"]);
    PublishedPS2PS3Chunks([root stringByAppendingPathComponent:@"published"],repository);
    Catalogue476RegressionMain(0,NULL);
  }
  [NSFileManager.defaultManager removeItemAtPath:root error:nil];
  printf("Foundation Build 477 shared installation: %lu behavioral checks passed\n",(unsigned long)checks);return 0;
}}
