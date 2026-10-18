// SPDX-License-Identifier: GPL-3.0-or-later
// Executes the actual Foundation manager on macOS. No engine/game is executed.
#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#import <zlib.h>
#import <mach/mach.h>
#include <string.h>
#import "NeoUnifiedCheatCatalog.h"
@interface NeoUnifiedCheatCatalog (RuntimeTesting)
- (NSDictionary *)validatedManifest:(NSData *)data error:(NSError **)error;
@end

static NSUInteger checks=0;
#define CHECK(condition,message) do { checks++; if(!(condition)) { fprintf(stderr,"FAIL %s:%d %s\n",__FILE__,__LINE__,message); exit(1); } } while(0)
static void Spin(BOOL (^done)(void)) {
  NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:15];
  while(!done() && deadline.timeIntervalSinceNow>0)
    [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.005]];
  CHECK(done(),"asynchronous operation timed out");
}
static NSData *Bytes(id object) {return [NSJSONSerialization dataWithJSONObject:object options:NSJSONWritingSortedKeys error:NULL];}
static NSString *Hash(NSData *data) {
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256(data.bytes,(CC_LONG)data.length,digest);
  NSMutableString *s=[NSMutableString string];for(NSUInteger i=0;i<sizeof(digest);i++)[s appendFormat:@"%02x",digest[i]];return s;
}
static NSData *Gzip(NSData *data) {
  z_stream stream={0};CHECK(deflateInit2(&stream,Z_BEST_SPEED,Z_DEFLATED,16+MAX_WBITS,8,Z_DEFAULT_STRATEGY)==Z_OK,"gzip init");
  NSMutableData *compressed=[NSMutableData dataWithLength:compressBound((uLong)data.length)+64];
  stream.next_in=(Bytef *)data.bytes;stream.avail_in=(uInt)data.length;
  stream.next_out=compressed.mutableBytes;stream.avail_out=(uInt)compressed.length;
  CHECK(deflate(&stream,Z_FINISH)==Z_STREAM_END,"gzip finish");[compressed setLength:stream.total_out];deflateEnd(&stream);return compressed;
}
static NSDictionary *ID(NSString *type,NSString *value,NSString *scheme) {return @{@"type":type,@"value":value,@"scheme":scheme};}
static NSDictionary *Game(NSString *system,NSArray *ids,NSString *revision,NSString *region) {
  return @{@"system":system,@"title":@"Pokémon Rouge",@"identities":ids,@"revision":revision,@"regions":@[region],@"languages":@[@"fr"]};
}
static void IdentityChecks(void) {
  NSDictionary *fb=@{@"system":@"arcade",@"identities":@[ID(@"romset",@"neotest",@"fbneo-driver-name")]};
  CHECK([[NeoUnifiedCheatCatalog matchGame:fb identity:fb] isEqual:@"exact"],"native running driver is an exact arcade identity");
  CHECK((![NeoUnifiedCheatCatalog matchGame:fb identity:@{@"system":@"arcade",@"identities":@[ID(@"romset",@"neotestj",@"fbneo-driver-name")]}]),"arcade clone never inherits parent codes");
  NSDictionary *md5=ID(@"md5",@"123456",@"rom-full");
  NSDictionary *game=Game(@"gb",@[md5],@"0",@"France");
  CHECK([[NeoUnifiedCheatCatalog matchGame:game identity:game] isEqual:@"exact"],"full hash exact");
  CHECK(![NeoUnifiedCheatCatalog matchGame:game identity:Game(@"gb",@[md5],@"1",@"France")],"revision conflict");
  CHECK(![NeoUnifiedCheatCatalog matchGame:game identity:Game(@"gb",@[md5],@"0",@"USA")],"region conflict even with hash");
  CHECK(![NeoUnifiedCheatCatalog matchGame:game identity:Game(@"gba",@[md5],@"0",@"France")],"system conflict");
  CHECK([NeoUnifiedCheatCatalog gameHasConflict:game identity:Game(@"gba",@[md5],@"0",@"France")],"explicit system contradiction");
  CHECK([NeoUnifiedCheatCatalog gameHasConflict:game identity:Game(@"gb",@[md5],@"1",@"France")],"explicit revision contradiction");
  NSDictionary *usa=Game(@"gb",@[ID(@"md5",@"usa-hash",@"rom-full")],@"0",@"USA");
  CHECK([NeoUnifiedCheatCatalog gameHasConflict:usa identity:game],"USA full MD5 cannot be confirmed for French ROM");
  CHECK([NeoUnifiedCheatCatalog gameHasConflict:game identity:Game(@"gb",@[ID(@"md5",@"different",@"rom-full")],@"0",@"France")],"same-region typed hash mismatch is a conflict");
  NSMutableDictionary *english=[game mutableCopy];english[@"languages"]=@[@"en"];
  CHECK(![NeoUnifiedCheatCatalog matchGame:game identity:english],"language conflict");
  CHECK([NeoUnifiedCheatCatalog gameHasConflict:game identity:english],"explicit language contradiction");
  NSMutableDictionary *name=[game mutableCopy];name[@"identities"]=@[];
  CHECK([[NeoUnifiedCheatCatalog matchGame:game identity:name] isEqual:@"candidate"],"name never exact");
  CHECK(![NeoUnifiedCheatCatalog gameHasConflict:game identity:name],"missing identity is not a known contradiction");
  NSDictionary *ps2=Game(@"ps2",@[ID(@"ps2_crc",@"0123ABCD",@"pcsx2-executable-crc")],@"",@"Europe");
  CHECK([[NeoUnifiedCheatCatalog matchGame:ps2 identity:ps2] isEqual:@"exact"],"PS2 executable CRC exact");
  NSMutableDictionary *iso=[ps2 mutableCopy];iso[@"identities"]=@[ID(@"ps2_crc",@"0123ABCD",@"rom-full")];
  CHECK([[NeoUnifiedCheatCatalog matchGame:ps2 identity:iso] isEqual:@"candidate"],"ISO CRC not executable CRC");
  CHECK(![NeoUnifiedCheatCatalog gameHasConflict:ps2 identity:iso],"uncomparable CRC schemes are not known conflicting values");
  NSMutableDictionary *serialLeft=[ps2 mutableCopy],*serialRight=[ps2 mutableCopy];
  serialLeft[@"identities"]=[ps2[@"identities"] arrayByAddingObject:ID(@"serial",@"SLES-12345",@"ps2-disc-serial")];
  serialRight[@"identities"]=[ps2[@"identities"] arrayByAddingObject:ID(@"serial",@"SLUS-54321",@"ps2-disc-serial")];
  CHECK(![NeoUnifiedCheatCatalog matchGame:serialLeft identity:serialRight],"conflicting serial defeats matching executable CRC");
  CHECK([[NeoUnifiedCheatCatalog matchGame:serialLeft identity:ps2] isEqual:@"candidate"],"missing expected serial cannot confirm CRC alone");
  serialLeft[@"identities"]=[ps2[@"identities"] arrayByAddingObject:ID(@"serial",@"SLUS20655",@"ps2-disc-serial")];
  for (NSString *spelling in @[@"SLUS-20655",@"SLUS_206.55",@"slus20655"]) {
    serialRight[@"identities"]=[ps2[@"identities"] arrayByAddingObject:ID(@"serial",spelling,@"ps2-disc-serial")];
    CHECK([[NeoUnifiedCheatCatalog matchGame:serialLeft identity:serialRight] isEqual:@"exact"],"PS2 native serial spelling must match the published catalogue");
  }
  serialRight[@"identities"]=[ps2[@"identities"] arrayByAddingObject:ID(@"serial",@"SLUS-20656",@"ps2-disc-serial")];
  CHECK(![NeoUnifiedCheatCatalog matchGame:serialLeft identity:serialRight],"normalization cannot accept a different PS2 disc");
  NSMutableDictionary *multipleHashes=[game mutableCopy];
  multipleHashes[@"identities"]=[game[@"identities"] arrayByAddingObject:ID(@"sha1",@"sha-nes",@"nes-prg")];
  CHECK([[NeoUnifiedCheatCatalog matchGame:multipleHashes identity:game] isEqual:@"candidate"],"all expected identity groups must be verified");
  NSDictionary *dolphin=Game(@"gc",@[ID(@"game_id",@"GC6P01",@"dolphin-disc-game-id")],@"",@"Europe");
  CHECK([[NeoUnifiedCheatCatalog matchGame:dolphin identity:dolphin] isEqual:@"candidate"],"Dolphin missing revision candidate");
  CHECK(![NeoUnifiedCheatCatalog gameHasConflict:dolphin identity:dolphin],"unknown-revision candidate is not a conflict");
  NSMutableDictionary *known=[dolphin mutableCopy];known[@"revision"]=@"0";
  CHECK([[NeoUnifiedCheatCatalog matchGame:known identity:known] isEqual:@"exact"],"Dolphin known revision exact");
  NSMutableDictionary *labeledRevision=[known mutableCopy];labeledRevision[@"revision"]=@"Revision 0";
  CHECK([[NeoUnifiedCheatCatalog matchGame:labeledRevision identity:known] isEqual:@"exact"],"numeric cartridge revision label normalized");
  labeledRevision[@"revision"]=@0;
  CHECK([[NeoUnifiedCheatCatalog matchGame:labeledRevision identity:known] isEqual:@"exact"],"numeric revision zero is known");
  CHECK([[NeoUnifiedCheatCatalog matchGame:dolphin identity:known] isEqual:@"candidate"],"source missing revision not exact");
  NSDictionary *ds=Game(@"nds",@[ID(@"ds_game_code",@"CPUF",@"nds-header-gamecode"),ID(@"ds_crc",@"D8380D9F",@"r4-header512-crc32-inverted")],@"",@"France");
  CHECK([[NeoUnifiedCheatCatalog matchGame:ds identity:ds] isEqual:@"exact"],"DS gamecode plus header CRC exact");
  NSMutableDictionary *wrongScheme=[ds mutableCopy];wrongScheme[@"identities"]=@[ID(@"ds_game_code",@"CPUF",@"nds-header-gamecode"),ID(@"ds_crc",@"D8380D9F",@"rom-full")];
  CHECK([[NeoUnifiedCheatCatalog matchGame:ds identity:wrongScheme] isEqual:@"candidate"],"DS source CRC not full ROM CRC");
  NSDictionary *ps3=Game(@"ps3",@[ID(@"ppu_hash",@"abcdef",@"rpcs3-ppu-hash"),ID(@"serial",@"BCES00510",@"ps3-title-id")],@"1.03",@"Europe");
  CHECK([[NeoUnifiedCheatCatalog matchGame:ps3 identity:ps3] isEqual:@"exact"],"PS3 ppu serial and version exact");
  NSMutableDictionary *noSerial=[ps3 mutableCopy];noSerial[@"identities"]=@[ps3[@"identities"][0]];
  CHECK([[NeoUnifiedCheatCatalog matchGame:ps3 identity:noSerial] isEqual:@"candidate"],"PS3 missing serial not exact");
}
static NSDictionary *Fixture(void) {
  NSMutableArray *games=[NSMutableArray array],*packs=[NSMutableArray array];
  NSMutableDictionary *responses=[NSMutableDictionary dictionary];
  for(NSUInteger i=0;i<3;i++){
    NSString *gid=[NSString stringWithFormat:@"game-%lu",(unsigned long)i],*pid=[NSString stringWithFormat:@"pack-%lu",(unsigned long)i];
    NSMutableDictionary *game=[Game(@"gb",@[ID(@"md5",[NSString stringWithFormat:@"hash%lu",(unsigned long)i],@"rom-full")],@"0",@"France") mutableCopy];
    game[@"id"]=gid;
    NSArray *cheats=@[@{@"id":@"c-1",@"name":@"Money",@"code":@"0199F3D5",@"lines":@[@"0199F3D5"],@"dialect":@"game-shark",@"handler":@0,@"enabled":@YES,@"status":@"available",@"dependencies":@[],@"parameters":@[],@"provenance":@[]},
      @{@"id":@"c-2",@"name":@"Unsupported handler",@"code":@"0199F3D5",@"lines":@[],@"handler":@1,@"status":@"available"}];
    NSData *chunk=Bytes(@{@"schema_version":@1,@"game":game,@"cheats":cheats,@"sources":@[]});
    NSData *expanded=Bytes(@{@"schema_version":@1,@"files":@[@{@"game_id":gid,@"data":[chunk base64EncodedStringWithOptions:0]}]});
    NSData *compressed=Gzip(expanded);
    NSString *path=[NSString stringWithFormat:@"packs/%@.json.gz",pid];
    game[@"path"]=[NSString stringWithFormat:@"games/%@.json",gid];game[@"sha256"]=Hash(chunk);game[@"size"]=@(chunk.length);game[@"pack_id"]=pid;
    game[@"cheat_count"]=@2;game[@"available_count"]=@1;
    [games addObject:game];[packs addObject:@{@"id":pid,@"path":path,@"sha256":Hash(compressed),@"size":@(compressed.length),@"uncompressed_size":@(expanded.length),@"game_ids":@[gid]}];
    responses[path]=compressed;
  }
  // A malformed sibling row must not hide the valid games or prevent install.
  NSMutableDictionary *bad=[games.firstObject mutableCopy];bad[@"id"]=@"bad-row";bad[@"path"]=@"../escape.json";[games addObject:bad];
  NSDictionary *manifest=@{@"schema_version":@1,@"catalogue_id":@"test-unified",@"revision":@"1",@"sources":@[@{@"id":@"conditional",@"status":@"conditional"}],@"games":games,@"packs":packs};
  responses[@"manifest.json"]=Bytes(manifest);
  return @{@"manifest":manifest,@"responses":responses};
}
static NSDictionary *Load(NeoUnifiedCheatCatalog *catalog) {
  __block BOOL done=NO;__block NSDictionary *value=nil;
  [catalog loadWithCompletion:^(NSDictionary *manifest,NSError *error){CHECK(NSThread.isMainThread,"load callback main");CHECK(!error,"load succeeds");value=manifest;done=YES;}];
  Spin(^BOOL{return done;});return value;
}
static NSDictionary *Install(NeoUnifiedCheatCatalog *catalog,BOOL expectFailure) {
  __block BOOL done=NO;__block NSDictionary *value=nil;__block NSUInteger updates=0;
  [catalog installAllWithProgress:^(NSDictionary *progress){CHECK(NSThread.isMainThread,"progress callback main");CHECK([progress[@"completed_bytes"] unsignedLongLongValue]<=[progress[@"total_bytes"] unsignedLongLongValue],"bounded progress");updates++;}
    completion:^(NSDictionary *result,NSError *error){CHECK(NSThread.isMainThread,"install callback main");CHECK((error!=nil)==expectFailure,"expected partial failure status");value=result;done=YES;}];
  Spin(^BOOL{return done;});CHECK(updates>0,"progress emitted");return value;
}
static NSArray *Codes(NeoUnifiedCheatCatalog *catalog,NSDictionary *game,BOOL success) {
  __block BOOL done=NO;__block NSArray *value=nil;
  [catalog cheatsForGame:game completion:^(NSArray *cheats,NSError *error){CHECK(NSThread.isMainThread,"cheats callback main");CHECK((error==nil)==success,"expected cheat read status");value=cheats;done=YES;}];Spin(^BOOL{return done;});return value;
}
static void RejectionChecks(NSString *root) {
  NSDictionary *fixture=Fixture();
  NeoUnifiedCheatCatalog *decoder=[NeoUnifiedCheatCatalog new];
  NSData *raw=Bytes(fixture[@"manifest"]),*compressed=Gzip(raw);
  NSError *gzipError=nil;
  CHECK([[decoder validatedManifest:compressed error:&gzipError][@"games"] count]==3 && !gzipError,"gzip manifest roundtrip");
  NSData *truncated=[compressed subdataWithRange:NSMakeRange(0,compressed.length-4)];
  CHECK(![decoder validatedManifest:truncated error:&gzipError] && gzipError,"truncated gzip index rejected");
  NSMutableData *wrongSize=[compressed mutableCopy];
  ((unsigned char *)wrongSize.mutableBytes)[wrongSize.length-4]^=1;gzipError=nil;
  CHECK(![decoder validatedManifest:wrongSize error:&gzipError] && gzipError,"wrong gzip ISIZE rejected");
  NSMutableData *tooExpanded=[compressed mutableCopy];unsigned char *footer=tooExpanded.mutableBytes;
  uint32_t over=64*1024*1024+1;
  for(NSUInteger byte=0;byte<4;byte++)footer[tooExpanded.length-4+byte]=(unsigned char)(over>>(byte*8));
  gzipError=nil;CHECK(![decoder validatedManifest:tooExpanded error:&gzipError] && gzipError,"manifest expansion limit rejected before allocation");
  NSMutableData *tooCompressed=[NSMutableData dataWithLength:12*1024*1024+1];
  ((unsigned char *)tooCompressed.mutableBytes)[0]=0x1f;((unsigned char *)tooCompressed.mutableBytes)[1]=0x8b;
  gzipError=nil;CHECK(![decoder validatedManifest:tooCompressed error:&gzipError] && gzipError,"manifest compressed limit enforced");
  for(NSUInteger variant=0;variant<2;variant++) {
    NSMutableDictionary *manifest=[fixture[@"manifest"] mutableCopy];
    NSMutableArray *packs=[manifest[@"packs"] mutableCopy];NSMutableDictionary *bad=[packs[0] mutableCopy];
    if(variant==0)bad[@"sha256"]=[@"0" stringByPaddingToLength:64 withString:@"0" startingAtIndex:0];
    else bad[@"uncompressed_size"]=@([bad[@"uncompressed_size"] unsignedIntegerValue]+1);
    packs[0]=bad;manifest[@"packs"]=packs;
    NSDictionary *responses=fixture[@"responses"];
    NeoUnifiedCheatCatalog *catalog=[NeoUnifiedCheatCatalog new];catalog.bundledDirectory=nil;
    catalog.storageDirectory=[root stringByAppendingPathComponent:[NSString stringWithFormat:@"reject-%lu",(unsigned long)variant]];
    catalog.fetch=^(NSURL *url,NSUInteger limit,void(^completion)(NSData*,NSError*)) {
      NSString *key=[url.path componentsSeparatedByString:@"/catalogue/"].lastObject;
      completion([url.lastPathComponent hasPrefix:@"manifest.json"] ? Bytes(manifest) : responses[key],nil);
    };
    NSDictionary *result=Install(catalog,YES);
    CHECK([result[@"installed_games"] unsignedIntegerValue]==2,"bad hash/expansion isolated to one pack");
    CHECK([result[@"failed_packs"] count]==1,"corrupt pack reported");
  }
  // Supporting Apple's /var root link must not permit a link inside the cache.
  NSString *outside=[root stringByAppendingPathComponent:@"outside-cache"];
  NSString *blocked=[root stringByAppendingPathComponent:@"linked-cache"];
  CHECK([NSFileManager.defaultManager createDirectoryAtPath:outside withIntermediateDirectories:YES attributes:nil error:NULL],"create symlink test destination");
  CHECK([NSFileManager.defaultManager createDirectoryAtPath:blocked withIntermediateDirectories:YES attributes:nil error:NULL],"create symlink test cache");
  CHECK([NSFileManager.defaultManager createSymbolicLinkAtPath:[blocked stringByAppendingPathComponent:@"files"] withDestinationPath:outside error:NULL],"create internal cache link");
  NeoUnifiedCheatCatalog *linked=[NeoUnifiedCheatCatalog new];linked.bundledDirectory=nil;linked.storageDirectory=blocked;
  linked.fetch=^(NSURL *url,NSUInteger limit,void(^completion)(NSData*,NSError*)){NSString *key=[url.path componentsSeparatedByString:@"/catalogue/"].lastObject;completion([url.lastPathComponent hasPrefix:@"manifest.json"] ? Bytes(fixture[@"manifest"]) : fixture[@"responses"][key],nil);};
  NSDictionary *blockedResult=Install(linked,YES);
  CHECK([blockedResult[@"installed_games"] unsignedIntegerValue]==0,"internal cache link cannot receive an installation");
  CHECK([NSFileManager.defaultManager contentsOfDirectoryAtPath:outside error:NULL].count==0,"internal link writes nothing outside cache");
  NeoUnifiedCheatCatalog *malformed=[NeoUnifiedCheatCatalog new];malformed.bundledDirectory=nil;
  malformed.storageDirectory=[root stringByAppendingPathComponent:@"malformed-schema"];
  malformed.fetch=^(NSURL *url,NSUInteger limit,void(^completion)(NSData*,NSError*)) {completion(Bytes(@{@"schema_version":@{}}),nil);};
  __block BOOL done=NO;
  [malformed loadWithCompletion:^(NSDictionary *manifest,NSError *error){CHECK(NSThread.isMainThread,"error callback main");CHECK(!manifest && error,"non-number schema safely rejected");done=YES;}];Spin(^BOOL{return done;});
  // An insecure configured endpoint must not invoke even an injected fetch.
  NeoUnifiedCheatCatalog *insecure=[NeoUnifiedCheatCatalog new];insecure.bundledDirectory=nil;
  insecure.storageDirectory=[root stringByAppendingPathComponent:@"insecure"];
  insecure.manifestURL=[NSURL URLWithString:@"http://catalogue.invalid/manifest.json"];
  insecure.fetch=^(NSURL *url,NSUInteger limit,void(^completion)(NSData*,NSError*)){CHECK(NO,"insecure URL reached transport");};
  done=NO;[insecure loadWithCompletion:^(NSDictionary *manifest,NSError *error){CHECK(!manifest && error,"HTTP downgrade rejected");done=YES;}];Spin(^BOOL{return done;});
}
static void RuntimeChecks(NSString *root) {
  NSDictionary *fixture=Fixture(),*responses=fixture[@"responses"];
  NSObject *lock=[NSObject new];__block BOOL failThird=YES,offline=NO;
  __block NSUInteger active=0,maximum=0;NSMutableDictionary *requests=[NSMutableDictionary dictionary];
  NeoUnifiedCheatCatalog *catalog=[NeoUnifiedCheatCatalog new];catalog.storageDirectory=[root stringByAppendingPathComponent:@"storage"];catalog.bundledDirectory=nil;
  catalog.manifestURL=[NSURL URLWithString:@"https://catalogue.invalid/data/manifest.json"];
  catalog.fetch=^(NSURL *url,NSUInteger maximumBytes,void(^completion)(NSData*,NSError*)){
    CHECK(!NSThread.isMainThread,"transport off main");NSString *path=[url.path substringFromIndex:@"/data/".length];
    @synchronized(lock){active++;maximum=MAX(maximum,active);requests[path]=@([requests[path] unsignedIntegerValue]+1);}
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,20*NSEC_PER_MSEC),dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{
      BOOL fail=offline || (failThird && [path containsString:@"pack-2"]);
      NSData *data=responses[path];CHECK(!data || data.length<=maximumBytes,"transport byte budget");
      @synchronized(lock){active--;}
      completion(fail ? nil : data,fail ? [NSError errorWithDomain:@"fixture" code:404 userInfo:nil] : nil);
      // A buggy adapter completing twice must not install or callback twice.
      completion(nil,[NSError errorWithDomain:@"duplicate" code:1 userInfo:nil]);
    });
  };
  NSDictionary *loaded=Load(catalog);CHECK([loaded[@"games"] count]==3,"invalid path row isolated");
  CHECK([loaded[@"rejected_entries"] unsignedIntegerValue]==1,"malformed entry reported");
  NSDictionary *partial=Install(catalog,YES);
  if([partial[@"installed_games"] unsignedIntegerValue]!=2){
    NSDictionary *details=@{@"installed_games":partial[@"installed_games"] ?: @0,@"failed_packs":partial[@"failed_packs"] ?: @[],@"errors":partial[@"errors"] ?: @[],@"storage_error":partial[@"storage_error"] ?: @""};
    fprintf(stderr,"Partial installation diagnostic: %s\n",[[[NSString alloc] initWithData:Bytes(details) encoding:NSUTF8StringEncoding] UTF8String]);
  }
  CHECK([partial[@"installed_games"] unsignedIntegerValue]==2,"partial success kept");
  CHECK([partial[@"failed_packs"] count]==1,"failed pack recorded");
  CHECK(maximum<=2 && maximum==2,"at most two simultaneous transports");
  NSArray *games=loaded[@"games"],*codes=Codes(catalog,games[0],YES);
  CHECK(codes.count==2,"cheats returned");CHECK(![codes[0][@"enabled"] boolValue],"imports never enabled");
  CHECK([codes[1][@"status"] isEqual:@"requires_engine"],"unsupported handler not offered available");
  NSUInteger firstRequests=[requests[@"packs/pack-0.json.gz"] unsignedIntegerValue];
  failThird=NO;NSDictionary *complete=Install(catalog,NO);
  CHECK([complete[@"installed_games"] unsignedIntegerValue]==3,"retry installs missing pack");
  __block NSArray *native=nil;__block BOOL nativeDone=NO;
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{native=[catalog installedProgramsForIdentity:games[0]];nativeDone=YES;});
  Spin(^BOOL{return nativeDone;});CHECK(native.count==1,"boot adapter reads exact installed chunk without network");
  CHECK(![native[0][@"programs"][0][@"enabled"] boolValue],"boot catalogue programs remain disabled");
  CHECK([catalog installedProgramsForIdentity:games[0]].count==0,"boot disk adapter refuses main thread blocking");

  CHECK([requests[@"packs/pack-0.json.gz"] unsignedIntegerValue]==firstRequests,"retry skips verified success");
  CHECK([requests[@"packs/pack-2.json.gz"] unsignedIntegerValue]==2,"retry fetches failed pack");
  // A same-size corrupted chunk must not be trusted, even with installed.json.
  NSString *chunkPath=[catalog.storageDirectory stringByAppendingPathComponent:[NSString stringWithFormat:@"files/%@.json",games[0][@"sha256"]]];
  NSMutableData *broken=[[NSData dataWithContentsOfFile:chunkPath] mutableCopy];((unsigned char *)broken.mutableBytes)[0]^=1;[broken writeToFile:chunkPath atomically:YES];
  offline=YES;CHECK(Codes(catalog,games[0],YES).count==2,"corrupt chunk rebuilt from verified local pack offline");
  CHECK([requests[@"packs/pack-0.json.gz"] unsignedIntegerValue]==firstRequests,"offline rebuild uses cached pack");
  NeoUnifiedCheatCatalog *reloaded=[NeoUnifiedCheatCatalog new];reloaded.storageDirectory=catalog.storageDirectory;reloaded.bundledDirectory=nil;
  reloaded.fetch=^(NSURL *url,NSUInteger limit,void(^completion)(NSData*,NSError*)){CHECK(NO,"offline load/read must not access transport");};
  NSDictionary *persisted=Load(reloaded);
  CHECK([persisted[@"installed_games"] unsignedIntegerValue]==3,"persistent install index reload");
  NSDictionary *installed=[reloaded valueForKey:@"installed"];
  CHECK(installed[@"game-0"][@"game"]==persisted[@"games"][0],"install index reuses immutable manifest metadata");
  CHECK(Codes(reloaded,games[1],YES).count==2,"persistent codes readable offline");
  __block BOOL done=NO;
  [catalog gamesForIdentity:games[0] completion:^(NSArray *matches,NSError *error){CHECK(NSThread.isMainThread,"lookup main");CHECK(!error && matches.count==1,"source IDs exclude other games with same title");CHECK([matches[0][@"match"] isEqual:@"exact"],"runtime match exact");done=YES;}];Spin(^BOOL{return done;});
  done=NO;[catalog searchGames:@"pokemon" system:@"gba" completion:^(NSArray *found,NSError *error){CHECK(!error && found.count==0,"search respects system");done=YES;}];Spin(^BOOL{return done;});
  done=NO;[catalog searchGames:@"pokemon" system:@"gb" completion:^(NSArray *found,NSError *error){CHECK(!error && found.count==3,"accent insensitive search");done=YES;}];Spin(^BOOL{return done;});
  done=NO;[catalog searchGames:@"rouge pokemon" system:@"gb" completion:^(NSArray *found,NSError *error){CHECK(!error && found.count==3,"search accepts words in either order");done=YES;}];Spin(^BOOL{return done;});
  // A separately configured bundled index still permits an offline first load.
  NSString *bundle=[root stringByAppendingPathComponent:@"bundle"];[NSFileManager.defaultManager createDirectoryAtPath:bundle withIntermediateDirectories:YES attributes:nil error:NULL];
  [responses[@"manifest.json"] writeToFile:[bundle stringByAppendingPathComponent:@"manifest.json"] atomically:YES];
  NeoUnifiedCheatCatalog *bundled=[NeoUnifiedCheatCatalog new];bundled.storageDirectory=[root stringByAppendingPathComponent:@"bundled-cache"];bundled.bundledDirectory=bundle;
  bundled.fetch=reloaded.fetch;CHECK([Load(bundled)[@"games"] count]==3,"bundled offline index used");
}
static uint64_t Footprint(void) {
  task_vm_info_data_t info={0};mach_msg_type_number_t count=TASK_VM_INFO_COUNT;
  return task_info(mach_task_self(),TASK_VM_INFO,(task_info_t)&info,&count)==KERN_SUCCESS ? info.phys_footprint : 0;
}
static void InGameDownloadChecks(NSString *root) {
  NSMutableArray *games=[NSMutableArray array],*packs=[NSMutableArray array];
  NSMutableDictionary *responses=[NSMutableDictionary dictionary];
  NSArray *identities=@[
    @{@"system":@"ps2",@"title":@"Hobbit, The",@"revision":@"",@"identities":@[ID(@"serial",@"SLUS20655",@"ps2-disc-serial"),ID(@"ps2_crc",@"2D29C32F",@"pcsx2-executable-crc")]},
    @{@"system":@"ps3",@"title":@"Bladestorm: The Hundred Years' War",@"revision":@"01.00",@"identities":@[ID(@"serial",@"BLES00113",@"ps3-title-id")]}
  ];
  for (NSUInteger index=0;index<identities.count;index++) {
    NSString *gid=[NSString stringWithFormat:@"target-%lu",(unsigned long)index];
    NSMutableDictionary *game=[identities[index] mutableCopy];game[@"id"]=gid;
    NSDictionary *program=@{@"id":@"money",@"name":@"Test money",@"code":@"20000000 00000001",@"handler":@0,@"dialect":index ? @"ps3-static-be32" : @"pnach",@"status":@"available",@"enabled":@NO,@"dependencies":@[],@"parameters":@[]};
    NSData *chunk=Bytes(@{@"schema_version":@1,@"game":game,@"cheats":@[program]});
    NSData *expanded=Bytes(@{@"schema_version":@1,@"files":@[@{@"game_id":gid,@"data":[chunk base64EncodedStringWithOptions:0]}]});
    NSData *compressed=Gzip(expanded);NSString *path=[NSString stringWithFormat:@"packs/%@.json.gz",gid];
    game[@"pack_id"]=gid;game[@"path"]=[NSString stringWithFormat:@"games/%@.json",gid];game[@"sha256"]=Hash(chunk);game[@"size"]=@(chunk.length);
    [games addObject:game];[packs addObject:@{@"id":gid,@"path":path,@"sha256":Hash(compressed),@"size":@(compressed.length),@"uncompressed_size":@(expanded.length),@"game_ids":@[gid]}];responses[path]=compressed;
  }
  NSString *bundle=[root stringByAppendingPathComponent:@"target-bundle"];
  [NSFileManager.defaultManager createDirectoryAtPath:bundle withIntermediateDirectories:YES attributes:nil error:NULL];
  [Bytes(@{@"schema_version":@1,@"catalogue_id":@"targets",@"revision":@"475",@"games":games,@"packs":packs}) writeToFile:[bundle stringByAppendingPathComponent:@"manifest.json"] atomically:YES];
  NeoUnifiedCheatCatalog *catalog=[NeoUnifiedCheatCatalog new];catalog.storageDirectory=[root stringByAppendingPathComponent:@"target-cache"];catalog.bundledDirectory=bundle;
  catalog.manifestURL=[NSURL URLWithString:@"https://catalogue.invalid/targets/manifest.json"];
  NSObject *lock=[NSObject new];__block NSUInteger fetched=0;
  catalog.fetch=^(NSURL *url,NSUInteger limit,void(^completion)(NSData*,NSError*)) {
    NSString *path=[url.path substringFromIndex:@"/targets/".length];
    CHECK(![path isEqual:@"manifest.json"],"in-game install must use the verified local index before network refresh");
    @synchronized(lock){fetched++;}NSData *data=responses[path];CHECK(data && data.length<=limit,"real service requests an indexed bounded pack");completion(data,nil);
  };
  Load(catalog);
  NSMutableDictionary *nativePS2=[identities[0] mutableCopy];nativePS2[@"title"]=@"";
  nativePS2[@"identities"]=@[ID(@"serial",@"SLUS-20655",@"ps2-disc-serial"),ID(@"ps2_crc",@"2D29C32F",@"pcsx2-executable-crc")];
  __block BOOL done=NO;
  [catalog gamesForIdentity:nativePS2 completion:^(NSArray *matches,NSError *error){CHECK(!error && matches.count==1,"actual discovery prefilter accepts formatted native PS2 serial");CHECK(![matches[0][@"installed"] boolValue],"matching index is not confused with downloaded codes");done=YES;}];Spin(^BOOL{return done;});
  done=NO;__block NSUInteger progressCount=0;
  [catalog installAllForIdentity:identities[1] progress:^(NSDictionary *progress){CHECK(NSThread.isMainThread,"in-game progress is on main");progressCount++;}
      completion:^(NSDictionary *result,NSError *error){CHECK(!error && [result[@"installed_games"] unsignedIntegerValue]==2,"in-game button installs PS2 and PS3 through the real service");done=YES;}];Spin(^BOOL{return done;});
  CHECK(fetched==2 && progressCount>=3,"one request per pack with immediate and completion progress");
  CHECK(Codes(catalog,games[1],YES).count==1,"downloaded PS3 program is readable");
  CHECK(![Codes(catalog,games[0],YES)[0][@"enabled"] boolValue],"download never activates PS2 programs");
  catalog.fetch=^(NSURL *url,NSUInteger limit,void(^completion)(NSData*,NSError*)){CHECK(NO,"installed in-game catalogues must work without network");};
  done=NO;[catalog installAllForIdentity:nativePS2 progress:nil completion:^(NSDictionary *result,NSError *error){CHECK(!error && [result[@"installed_games"] unsignedIntegerValue]==2,"already downloaded button completes offline");done=YES;}];Spin(^BOOL{return done;});
  NSString *chunk=[catalog.storageDirectory stringByAppendingPathComponent:[NSString stringWithFormat:@"files/%@.json",games[0][@"sha256"]]];
  [NSFileManager.defaultManager removeItemAtPath:chunk error:NULL];
  done=NO;[catalog gamesForIdentity:nativePS2 completion:^(NSArray *matches,NSError *error){CHECK(!error && matches.count==1 && ![matches[0][@"installed"] boolValue] && [matches[0][@"cached_pack"] boolValue],"cached pack remains discoverable after an extracted file is missing");done=YES;}];Spin(^BOOL{return done;});
  CHECK(Codes(catalog,games[0],YES).count==1,"missing extracted PS2 codes recover from the verified offline pack");
  done=NO;[catalog gamesForIdentity:identities[1] completion:^(NSArray *matches,NSError *error){CHECK(!error && matches.count==1 && [matches[0][@"installed"] boolValue],"installed PS3 serial/version returns its cheat edition");done=YES;}];Spin(^BOOL{return done;});
}
static void FullManifestMemoryProbe(NSString *path,NSUInteger expectedGames,NSUInteger expectedPacks) {
  NSString *root=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  uint64_t before=Footprint();
  NeoUnifiedCheatCatalog *catalog=[NeoUnifiedCheatCatalog new];
  catalog.storageDirectory=root;catalog.bundledDirectory=path.stringByDeletingLastPathComponent;
  catalog.fetch=^(NSURL *url,NSUInteger limit,void(^completion)(NSData*,NSError*)){CHECK(NO,"memory probe must stay offline");};
  __block NSDictionary *first=nil;
  @autoreleasepool{first=Load(catalog);}
  CHECK([first[@"games"] count]>0,"full manifest has games");
  CHECK([first[@"rejected_entries"] unsignedIntegerValue]==0,"published manifest has no rejected records");
  if(expectedGames)CHECK([first[@"games"] count]==expectedGames,"runtime keeps every published game");
  if(expectedPacks)CHECK([first[@"packs"] count]==expectedPacks,"runtime keeps every published pack");
  if([first[@"totals"] isKindOfClass:NSDictionary.class] && [first[@"totals"][@"games"] unsignedIntegerValue])
    CHECK([first[@"games"] count]==[first[@"totals"][@"games"] unsignedIntegerValue],"game count matches publication totals");
  [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.1]];
  uint64_t loaded=Footprint();
  for(NSUInteger iteration=0;iteration<10;iteration++){@autoreleasepool{
    NSDictionary *again=Load(catalog);
    CHECK(again==first,"repeated loads share one frozen snapshot");
    CHECK(again[@"games"]==first[@"games"],"repeated menus share the game index");
    __block BOOL done=NO;
    [catalog searchGames:@"___no_such_game_for_memory_probe___" system:@"gb" completion:^(NSArray *rows,NSError *error){CHECK(!error && !rows.count,"memory search");done=YES;}];
    Spin(^BOOL{return done;});
  }}
  [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.1]];
  uint64_t repeated=Footprint();
  printf("Full manifest memory: games=%lu, file_bytes=%llu, before=%llu, loaded=%llu, after_ten_menus=%llu, retained_growth=%lld bytes\n",
    (unsigned long)[first[@"games"] count],
    [NSFileManager.defaultManager attributesOfItemAtPath:path error:NULL].fileSize,
    (unsigned long long)before,(unsigned long long)loaded,(unsigned long long)repeated,(long long)repeated-(long long)loaded);
  // A separate complete Foundation tree for each menu would retain hundreds
  // of MiB here. Permit allocator warm-up without calling it a device result.
  CHECK(!loaded || repeated<=loaded+32*1024*1024,"ten menus must not retain ten full indexes");
  [NSFileManager.defaultManager removeItemAtPath:root error:NULL];
}
int main(int argc,const char *argv[]) {@autoreleasepool{
  if(argc>=3 && strcmp(argv[1],"--manifest")==0){
    NSUInteger games=argc==7 ? (NSUInteger)strtoull(argv[4],NULL,10) : 0;
    NSUInteger packs=argc==7 ? (NSUInteger)strtoull(argv[6],NULL,10) : 0;
    FullManifestMemoryProbe([NSString stringWithUTF8String:argv[2]],games,packs);return 0;
  }
  IdentityChecks();NSString *root=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  [NSFileManager.defaultManager createDirectoryAtPath:root withIntermediateDirectories:YES attributes:nil error:NULL];
  RuntimeChecks(root);RejectionChecks(root);InGameDownloadChecks(root);[NSFileManager.defaultManager removeItemAtPath:root error:NULL];
  printf("Foundation unified catalogue: %lu behavioral checks passed\n",(unsigned long)checks);return 0;
}}
