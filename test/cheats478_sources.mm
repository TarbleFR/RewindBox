// Exercise the real published delta through retained native host APIs.
#import "NeoUnifiedCheatCatalog.h"
#include "NeoUnifiedNativeImport.h"
#import "RPCS3UnifiedCheats.h"
#import "LibretroCheats.h"
#include <cassert>
static NSUInteger mutations=0;
static rpcs3_ios_status Install(const char*,const char*,const void*,size_t){mutations++;return 0;}
static rpcs3_ios_status Enumerate(const char*,const char*,rpcs3_ios_runtime_patch_callback,void*){return 0;}
static rpcs3_ios_status Toggle(const char*,const char*,const char*,const char*,const char*,uint32_t){mutations++;return 0;}
static void Wait(BOOL (^done)(void)) {
  NSDate *end=[NSDate dateWithTimeIntervalSinceNow:30];
  while(!done() && end.timeIntervalSinceNow>0)[NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.01]];
  assert(done());
}
static std::vector<std::string> Lines(const NeoCheat::Result& parsed) {
  std::vector<std::string> result;
  for(const auto& entry:parsed.entries)result.insert(result.end(),entry.lines.begin(),entry.lines.end());
  return result;
}
static void Difference(id expected,id actual,NSString *path,NSUInteger depth) {
  if([expected isEqual:actual] || depth>32)return;
  if([expected isKindOfClass:NSDictionary.class] && [actual isKindOfClass:NSDictionary.class]) {
    for(NSString *key in expected)Difference(expected[key],actual[key],[path stringByAppendingFormat:@"/%@",key],depth+1);
  } else if([expected isKindOfClass:NSArray.class] && [actual isKindOfClass:NSArray.class] && [expected count]==[actual count]) {
    for(NSUInteger i=0;i<[expected count];i++)Difference(expected[i],actual[i],[path stringByAppendingFormat:@"/%lu",(unsigned long)i],depth+1);
  } else fprintf(stderr,"Source difference %s: %s (%s) -> %s (%s)\n",path.UTF8String,
      [[expected description] UTF8String],NSStringFromClass([expected class]).UTF8String,
      [[actual description] UTF8String],NSStringFromClass([actual class]).UTF8String);
}
int main(int argc,const char *argv[]) {@autoreleasepool{
  assert(argc==4);NSString *repo=@(argv[1]);NSUInteger expected=[@(argv[3]) integerValue];
  NSArray *chunks=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:@(argv[2])] options:0 error:nil];assert(chunks.count);
  NSString *root=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  NeoUnifiedCheatCatalog *catalog=[NeoUnifiedCheatCatalog new];catalog.storageDirectory=[root stringByAppendingPathComponent:@"catalog"];
  catalog.bundledDirectory=[repo stringByAppendingPathComponent:@"packages/neo_cheat_catalog/ios/Resources"];
  NSMutableSet *sources=[NSMutableSet set];NSUInteger ps2=0,ps3=0,nds=0,discovered=0;
  rpcs3_ios_patch_api api={Install,Enumerate,Toggle,nullptr};
  NSString *staging=[root stringByAppendingPathComponent:@"staging"];
  for(NSDictionary *chunk in chunks) {@autoreleasepool{
    NSDictionary *game=chunk[@"game"];NSMutableDictionary *confirmed=[game mutableCopy];confirmed[@"edition_confirmed"]=@YES;
    NSString *serial=@"",*crc=@"",*ppu=@"PPU-0123456789012345678901234567890123456789";
    for(NSDictionary *identity in game[@"identities"]) {
      if([identity[@"type"] isEqual:@"serial"])serial=identity[@"value"];
      if([identity[@"type"] isEqual:@"ps2_crc"])crc=identity[@"value"];
      if([identity[@"type"] isEqual:@"ppu_hash"])ppu=[@"PPU-" stringByAppendingString:[identity[@"value"] lowercaseString]];
    }
    assert([NeoUnifiedCheatCatalog matchGame:game identity:game]);
    // Real index lookup once per contributing source: the remaining complete
    // programs are checked individually below, without 6,000 redundant scans.
    BOOL lookup=NO;
    for(NSString *sid in chunk[@"sources"])if(![sources containsObject:sid]){[sources addObject:sid];lookup=YES;}
    if(lookup) {
      __block BOOL done=NO;__block BOOL found=NO;
      [catalog gamesForIdentity:game completion:^(NSArray *rows,NSError *error){
        assert(!error);for(NSDictionary *row in rows)if([row[@"id"] isEqual:game[@"id"]])found=YES;done=YES;
      }];Wait(^BOOL{return done;});assert(found);discovered++;
    }
    BOOL isPS2=[game[@"system"] isEqual:@"ps2"];
    BOOL isDS=[game[@"system"] isEqual:@"nds"];
    NSString *version=[game[@"version_scope"] isEqual:@"all"] ? @"01.00" : game[@"revision"];
    NSDictionary *snapshot=@{@"available":@YES,@"serial":serial,@"crc":crc,@"hardcore":@NO,@"items":@[]};
    for(NSDictionary *program in chunk[@"cheats"]) {@autoreleasepool{
      assert(![program[@"enabled"] boolValue]);
      if(isDS) {
        NSArray *codes=[LibretroCheats codesForCheat:program core:@"desmume" console:@"nds"];
        assert(codes.count==1);
        assert([codes[0] isEqual:[program[@"code"] stringByReplacingOccurrencesOfString:@"\n" withString:@"+"]]);
        assert([game[@"edition_confirmation_required"] boolValue] && [game[@"regions"] isEqual:@[@"USA"]]);
        nds++;
      } else if(isPS2) {
        auto original=NeoUnifiedNativeProgram(program,YES);assert(original);
        NSDictionary *request=NeoUnifiedNativeRequest(confirmed,@[program],snapshot,YES);
        if(![request[@"success"] boolValue]){fprintf(stderr,"PS2 request rejected %s\n",[program[@"name"] UTF8String]);return 2;}
        auto parsed=NeoCheat::parse(NeoUTF8(request[@"content"]),"pnach","Fallback");
        assert(parsed && parsed.entries.size()==1 && Lines(parsed)==Lines(original));ps2++;
      } else {
        RPCS3UnifiedCheats *store=[[RPCS3UnifiedCheats alloc] initWithRoot:staging api:api];store.runtimePPUHash=ppu;
        BOOL ok=[store stageGame:confirmed programs:@[program] serial:serial version:version];
        if(!ok){fprintf(stderr,"PS3 stage rejected %s / %s / %s\n",serial.UTF8String,[game[@"revision"] UTF8String],[program[@"name"] UTF8String]);return 3;}
        NSDictionary *state=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:[staging stringByAppendingPathComponent:@"NeoStationUnifiedCheats/state.json"]] options:0 error:nil];
        NSArray *records=state[@"programs"];assert(records.count==1 && ![records[0][@"enabled"] boolValue]);
        if(![records[0][@"sources"] isEqual:@[program]]) {
          fprintf(stderr,"Roundtrip mismatch %s / %s\n",serial.UTF8String,[program[@"name"] UTF8String]);
          Difference(@[program],records[0][@"sources"],@"program",0);
        }
        assert([records[0][@"sources"] isEqual:@[program]]);
        if([program[@"dialect"] isEqual:@"ps3-static-be32"]) {
          assert([records[0][@"runtimeBound"] boolValue]);
          assert([records[0][@"patch"][@"Author"] isEqual:program[@"author"]]);
          assert([records[0][@"patch"][@"Patch"] count]==[program[@"code"] componentsSeparatedByString:@"\n"].count);
          assert(![store stageGame:confirmed programs:@[program] serial:serial version:@"99.99"]);
        }
        assert(![store stageGame:confirmed programs:@[program] serial:@"FAKE00000" version:version]);
        [NSFileManager.defaultManager removeItemAtPath:staging error:nil];ps3++;
      }
    }}
    if(isPS2) {
      NSMutableDictionary *wrong=[snapshot mutableCopy];wrong[@"crc"]=@"00000001";
      assert(![NeoUnifiedNativeRequest(confirmed,@[chunk[@"cheats"][0]],wrong,YES)[@"success"] boolValue]);
    }
  }}
  NSDictionary *receipt=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:[repo stringByAppendingPathComponent:@"docs/evidence/cheats478-sources.json"]] options:0 error:nil];
  assert(ps2+ps3+nds==expected && sources.count==[receipt[@"sourceContributions"] count] && mutations==0);
  // The already-published European Bladestorm source is still 01.00 only.
  NSDictionary *id00113=@{@"system":@"ps3",@"revision":@"01.01",@"identities":@[@{@"type":@"serial",@"scheme":@"ps3-title-id",@"value":@"BLES00113"}]};
  __block BOOL done=NO;__block NSUInteger count=999;
  [catalog gamesForIdentity:id00113 completion:^(NSArray *rows,NSError *error){assert(!error);count=rows.count;done=YES;}];Wait(^BOOL{return done;});assert(count==0);
  [NSFileManager.defaultManager removeItemAtPath:root error:nil];
  printf("PASS exact expansion native: ps2=%lu ps3=%lu nds=%lu total=%lu sources=%lu discovery=%lu; zero activation or Core mutation.\n",(unsigned long)ps2,(unsigned long)ps3,(unsigned long)nds,(unsigned long)(ps2+ps3+nds),(unsigned long)sources.count,(unsigned long)discovered);
  return 0;
}}
