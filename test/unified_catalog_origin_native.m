// SPDX-License-Identifier: GPL-3.0-or-later
// Origin publication (v2) on the actual Foundation manager, macOS host:
// a pack whose programs carry no code is rebuilt by the resolver, and every
// chunk it returns is still verified against the manifest. No engine runs.
#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#import <zlib.h>
#import "NeoUnifiedCheatCatalog.h"

static NSUInteger checks=0;
#define CHECK(condition,message) do { checks++; if(!(condition)) { fprintf(stderr,"FAIL %s:%d %s\n",__FILE__,__LINE__,message); exit(1); } } while(0)
static void Spin(BOOL (^done)(void)) {
  NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:20];
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
static NSDictionary *Install(NeoUnifiedCheatCatalog *catalog,NSError **failure) {
  __block NSDictionary *result=nil;__block NSError *problem=nil;__block BOOL done=NO;
  [catalog installAllWithProgress:nil completion:^(NSDictionary *data,NSError *error){result=data;problem=error;done=YES;}];
  Spin(^BOOL{return done;});if(failure)*failure=problem;return result;
}

int main(void) { @autoreleasepool {
  NSString *root=[NSTemporaryDirectory() stringByAppendingPathComponent:[NSUUID UUID].UUIDString];
  NSDictionary *chunk=@{@"schema_version":@1,@"game":@{@"id":@"origin-game",@"system":@"gb"},
    @"cheats":@[@{@"id":@"program-1",@"name":@"Infinite Lives",@"code":@"01FF10C0",@"lines":@[@"01FF10C0"],
      @"dialect":@"gb-gameshark",@"status":@"available",@"handler":@0,@"enabled":@NO,@"dependencies":@[],@"parameters":@[]}]};
  NSData *published=Bytes(chunk);
  // The skeleton the publisher wrote: the program keeps everything but its code.
  NSDictionary *skeleton=@{@"schema_version":@1,@"game":chunk[@"game"],
    @"cheats":@[@{@"id":@"program-1",@"name":@"Infinite Lives",@"dialect":@"gb-gameshark",@"status":@"available",@"handler":@0,
      @"enabled":@NO,@"dependencies":@[],@"parameters":@[],@"origin":@{@"f":@0,@"r":@[@[@0,@8]]}}]};
  NSData *packJSON=Bytes(@{@"schema_version":@1,@"origin":@{@"version":@1,@"sources":@{},@"files":@[]},
    @"files":@[@{@"game_id":@"origin-game",@"skeleton":[Bytes(skeleton) base64EncodedStringWithOptions:0]}]});
  NSData *pack=Gzip(packJSON);
  NSDictionary *manifest=@{@"schema_version":@1,@"catalogue_id":@"origin-test",@"revision":@"v2-test",@"sources":@[],
    @"games":@[@{@"id":@"origin-game",@"system":@"gb",@"title":@"Origin Game",@"path":@"games/origin-game.json",
      @"sha256":Hash(published),@"size":@(published.length),@"pack_id":@"pack-origin",@"identities":@[]}],
    @"packs":@[@{@"id":@"pack-origin",@"path":@"packs/pack-origin.json.gz",@"sha256":Hash(pack),@"size":@(pack.length),
      @"uncompressed_size":@(packJSON.length),@"game_ids":@[@"origin-game"],@"origin":@YES}]};
  __block NSUInteger packFetches=0;
  NeoUnifiedCheatFetch fetch=^(NSURL *url,NSUInteger limit,void(^completion)(NSData*,NSError*)){
    if([url.lastPathComponent hasPrefix:@"manifest"]){completion(Bytes(manifest),nil);return;}
    packFetches++;completion([url.lastPathComponent isEqual:@"pack-origin.json.gz"] ? pack : nil,nil);
  };
  NeoUnifiedCheatCatalog *(^make)(NSString *)=^NeoUnifiedCheatCatalog *(NSString *folder){
    NeoUnifiedCheatCatalog *catalog=[NeoUnifiedCheatCatalog new];catalog.bundledDirectory=nil;
    catalog.storageDirectory=[root stringByAppendingPathComponent:folder];
    catalog.manifestURL=[NSURL URLWithString:@"https://catalogue.invalid/data/manifest.json"];catalog.fetch=fetch;
    return catalog;
  };
  NSString *(^chunkPath)(NeoUnifiedCheatCatalog *)=^NSString *(NeoUnifiedCheatCatalog *catalog){
    return [catalog.storageDirectory stringByAppendingPathComponent:[NSString stringWithFormat:@"files/%@.json",Hash(published)]];
  };

  // 1. The resolver rebuilds the pack; the chunk is verified and installed.
  NeoUnifiedCheatCatalog *catalog=make(@"resolved");__block NSUInteger calls=0;
  catalog.originResolver=^NSData *(NSData *json,NSError **error){
    CHECK(!NSThread.isMainThread,"resolver runs on a catalogue worker");
    CHECK([json isEqualToData:packJSON],"resolver receives the expanded origin pack");calls++;
    return Bytes(@{@"schema_version":@1,@"files":@[@{@"game_id":@"origin-game",@"data":[published base64EncodedStringWithOptions:0]}]});
  };
  NSError *error=nil;NSDictionary *result=Install(catalog,&error);
  CHECK(!error && [result[@"installed_games"] unsignedIntegerValue]==1 && calls==1,"origin pack installed");
  CHECK([[NSData dataWithContentsOfFile:chunkPath(catalog)] isEqualToData:published],"chunk stored byte for byte");

  // 2. A rebuilt chunk that differs from the manifest is refused.
  NeoUnifiedCheatCatalog *tampered=make(@"tampered");
  tampered.originResolver=^NSData *(NSData *json,NSError **error){
    NSData *wrong=Bytes(@{@"schema_version":@1,@"game":chunk[@"game"],@"cheats":@[]});
    return Bytes(@{@"schema_version":@1,@"files":@[@{@"game_id":@"origin-game",@"data":[wrong base64EncodedStringWithOptions:0]}]});
  };
  result=Install(tampered,&error);
  CHECK(error && [result[@"failed_packs"] count]==1,"mismatching rebuilt chunk fails its pack");
  CHECK(![NSFileManager.defaultManager fileExistsAtPath:chunkPath(tampered)],"nothing installed from a wrong rebuild");

  // 3. Without a resolver an origin pack reports an error, never a partial chunk.
  NeoUnifiedCheatCatalog *bare=make(@"bare");
  result=Install(bare,&error);
  CHECK(error && [result[@"failed_packs"] count]==1,"origin pack needs a resolver");

  // 4. A resolver failure is reported with its message.
  NeoUnifiedCheatCatalog *failing=make(@"failing");
  failing.originResolver=^NSData *(NSData *json,NSError **error){
    if(error)*error=[NSError errorWithDomain:@"origin" code:1 userInfo:@{NSLocalizedDescriptionKey:@"Origin file changed at its source"}];
    return nil;
  };
  result=Install(failing,&error);
  CHECK([[result[@"errors"] firstObject][@"message"] isEqual:@"Origin file changed at its source"],"resolver error surfaced");

  // 5. An installed chunk (same SHA-256 as the hosted publication) stays
  //    installed: no pack download and no resolver call.
  NeoUnifiedCheatCatalog *updated=make(@"resolved");packFetches=0;
  updated.originResolver=^NSData *(NSData *json,NSError **error){CHECK(NO,"installed chunk must not be rebuilt");return nil;};
  result=Install(updated,&error);
  CHECK(!error && [result[@"installed_games"] unsignedIntegerValue]==1 && packFetches==0,"existing installation kept offline");

  [NSFileManager.defaultManager removeItemAtPath:root error:NULL];
  printf("Origin publication: %lu native checks passed.\n",(unsigned long)checks);
}return 0;}
