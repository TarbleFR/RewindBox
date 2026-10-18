// Exercise exact published programs through retained native import/staging APIs.
#import "NeoUnifiedCheatCatalog.h"
#include "NeoUnifiedNativeImport.h"
#import "RPCS3UnifiedCheats.h"
#include <cassert>

static rpcs3_ios_status Install(const char*,const char*,const void*,size_t){return 0;}
static rpcs3_ios_status Enumerate(const char*,const char*,rpcs3_ios_runtime_patch_callback,void*){return 0;}
static rpcs3_ios_status Toggle(const char*,const char*,const char*,const char*,const char*,uint32_t){return 0;}
static void Wait(BOOL (^done)(void)) {
  NSDate *end=[NSDate dateWithTimeIntervalSinceNow:30];
  while(!done() && end.timeIntervalSinceNow>0)[NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.01]];
  assert(done());
}
int main(int argc,const char *argv[]) {@autoreleasepool{
  assert(argc==3);NSString *repo=@(argv[1]);
  NSArray *chunks=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:@(argv[2])] options:0 error:nil];
  assert(chunks.count==5);
  NSString *root=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  NeoUnifiedCheatCatalog *catalog=[NeoUnifiedCheatCatalog new];catalog.storageDirectory=[root stringByAppendingPathComponent:@"catalog"];
  catalog.bundledDirectory=[repo stringByAppendingPathComponent:@"packages/neo_cheat_catalog/ios/Resources"];
  catalog.manifestURL=[NSURL URLWithString:@"https://catalogue.example/manifest.json.gz"];
  __block NSUInteger fetches=0;
  catalog.fetch=^(NSURL *url,NSUInteger limit,void(^done)(NSData*,NSError*)){
    assert([url.lastPathComponent isEqual:@"pack-2e1b142f0a03297148b4160e.json.gz"]);
    NSData *data=[NSData dataWithContentsOfFile:[repo stringByAppendingPathComponent:[@"native/cheats/catalogue/packs/" stringByAppendingString:url.lastPathComponent]]];
    assert(data.length && data.length<=limit);fetches++;done(data,nil);
  };
  NSUInteger programs=0;
  for(NSDictionary *chunk in chunks){
    NSDictionary *game=chunk[@"game"];NSString *serial=game[@"identities"][0][@"value"];
    NSMutableDictionary *identity=[game mutableCopy];
    if([game[@"system"] isEqual:@"ps2"]){
      identity[@"identities"]=[game[@"identities"] arrayByAddingObject:@{@"type":@"ps2_crc",@"scheme":@"pcsx2-executable-crc",@"value":@"1234ABCD"}];
    }
    __block BOOL loaded=NO;__block NSArray *codes=nil;__block NSDictionary *found=nil;
    [catalog gamesForIdentity:identity completion:^(NSArray *rows,NSError *error){
      assert(!error);for(NSDictionary *row in rows)if([row[@"id"] isEqual:game[@"id"]])found=row;
      assert(found);
      [catalog cheatsForGame:found completion:^(NSArray *value,NSError *problem){assert(!problem);codes=value;loaded=YES;}];
    }];Wait(^BOOL{return loaded;});
    assert([codes isEqual:chunk[@"cheats"]]);programs+=codes.count;
    NSMutableDictionary *confirmed=[found mutableCopy];confirmed[@"edition_confirmed"]=@YES;
    if([game[@"system"] isEqual:@"ps2"]){
      NSDictionary *snapshot=@{@"available":@YES,@"serial":serial,@"crc":@"1234ABCD",@"hardcore":@NO,@"items":@[]};
      assert(![NeoUnifiedNativeRequest(found,codes,snapshot,YES)[@"success"] boolValue]);
      // Direct switches import one whole selected program at a time. The
      // multi-program helper intentionally combines a dependency closure.
      for(NSDictionary *program in codes){
        NSDictionary *request=NeoUnifiedNativeRequest(confirmed,@[program],snapshot,YES);
        assert([request[@"success"] boolValue]);
        auto parsed=NeoCheat::parse(NeoUTF8(request[@"content"]),"pnach","Fallback");
        assert(parsed && parsed.entries.size()==1 && parsed.entries[0].lines.size()==1);
        assert(parsed.entries[0].lines[0]==NeoUTF8(program[@"code"]));
      }
      NSDictionary *wrong=@{@"available":@YES,@"serial":@"SLES00000",@"crc":@"1234ABCD",@"hardcore":@NO,@"items":@[]};
      assert(![NeoUnifiedNativeRequest(confirmed,codes,wrong,YES)[@"success"] boolValue]);
    }else{
      rpcs3_ios_patch_api api={Install,Enumerate,Toggle,nullptr};
      RPCS3UnifiedCheats *store=[[RPCS3UnifiedCheats alloc] initWithRoot:[root stringByAppendingPathComponent:@"rpcs3"] api:api];
      assert(![store stageGame:confirmed programs:codes serial:serial version:@"01.00"]);
      store.runtimePPUHash=@"PPU-0123456789012345678901234567890123456789";
      assert(![store stageGame:confirmed programs:codes serial:serial version:@"01.02"]);
      assert(![store stageGame:confirmed programs:codes serial:@"BLES00113" version:@"01.00"]);
      for(NSDictionary *program in codes)
        assert([store stageGame:confirmed programs:@[program] serial:serial version:@"01.00"]);
      NSArray *items=[store snapshotForTitle:serial version:@"01.00"][@"items"];assert(items.count==5);
      for(NSDictionary *item in items)assert(![item[@"enabled"] boolValue] && [item[@"runtimeBound"] boolValue]);
    }
  }
  assert(programs==16 && fetches==1);
  [NSFileManager.defaultManager removeItemAtPath:root error:nil];
  printf("PASS exact supplement: five editions / 16 native programs, one common pack, no automatic activation, different editions rejected.\n");
  return 0;
}}
