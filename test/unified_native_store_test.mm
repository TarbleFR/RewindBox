#include "NeoUnifiedNativeImport.h"
#import "RPCS3UnifiedCheats.h"
#include <cassert>

static NSString* mockRoot;
static NSMutableArray* toggles;
static BOOL rejectInstall;
static rpcs3_ios_status Install(const char* version,const char* sha,const void* bytes,size_t size) {
  assert(std::string(version)=="1.2" && strlen(sha)==64);
  if (rejectInstall) return -1;
  NSData* data=[NSData dataWithBytes:bytes length:size];
  assert([NSJSONSerialization JSONObjectWithData:data options:0 error:nil]);
  NSString* patch=[mockRoot stringByAppendingPathComponent:@"patches/patch.yml"];
  NSData* old=[NSData dataWithContentsOfFile:patch];
  if (old) [old writeToFile:[patch stringByAppendingString:@".old"] atomically:YES];
  return [data writeToFile:patch atomically:YES] ? 0 : -1;
}
static rpcs3_ios_status Enumerate(const char*,const char*,rpcs3_ios_runtime_patch_callback,void*) { return 0; }
static rpcs3_ios_status Toggle(const char* serial,const char* hash,const char* title,const char* version,const char* name,uint32_t enabled) {
  [toggles addObject:@{@"serial":@(serial),@"hash":@(hash),@"title":@(title),@"version":@(version),@"name":@(name),@"enabled":@(enabled)}];
  return 0;
}
static rpcs3_ios_status Games(rpcs3_ios_catalogue_game_callback callback,void* context) {
  rpcs3_ios_catalogue_game_info game={};game.struct_size=sizeof(game);
  game.title_id="BLES00001";game.version="01.01";callback(context,&game);return 0;
}
static NSDictionary* PS3Program(NSString* identifier,NSString* serial) {
  NSString* ppu=@"PPU-0123456789012345678901234567890123456789";
  return @{@"id":identifier,@"name":@"Original program",@"dialect":@"rpcs3-yaml",@"status":@"available",@"parameters":@[],@"dependencies":@[],
      @"native_document":@{@"Version":@"1.2",ppu:@{@"Original program":@{@"Games":@{@"Original title":@{serial:@[@"01.01"]}},@"Author":@"Original author",@"Patch":@[@[@"be32",@"0x00000000",@"0x00000001"]]}}}};
}
static NSDictionary* PS3Game(NSString* serial) {
  return @{@"system":@"ps3",@"edition_confirmed":@YES,@"revision":@"01.01",@"identities":@[@{@"type":@"serial",@"scheme":@"ps3-title-id",@"value":serial},
    @{@"type":@"ppu_hash",@"scheme":@"rpcs3-ppu-hash",@"value":@"0123456789012345678901234567890123456789"}]};
}
int main() { @autoreleasepool {
  NSFileManager* fm=NSFileManager.defaultManager;
  NSString* root=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  NSDictionary* snapshot=@{@"available":@YES,@"serial":@"SLES-00000",@"crc":@"ABCDEF12",@"hardcore":@NO,@"items":@[]};
  NSDictionary* game=@{@"system":@"ps2",@"identities":@[@{@"type":@"ps2_crc",@"scheme":@"pcsx2-executable-crc",@"value":@"ABCDEF12"}]};
  NSDictionary* master=@{@"id":@"master",@"name":@"Master",@"status":@"available",@"dialect":@"pnach",@"parameters":@[],@"dependencies":@[],@"code":@"patch=1,EE,D0000000,extended,00000001"};
  NSDictionary* child=@{@"id":@"child",@"name":@"Full cheat",@"status":@"available",@"dialect":@"pnach",@"parameters":@[],@"dependencies":@[@"master"],@"code":@"patch=1,EE,20000004,extended,00000002",@"provenance":@[@{@"author":@"Author",@"url":@"https://example.org/source",@"license":@"Test"}]};
  NSMutableDictionary* badGame=[game mutableCopy];badGame[@"identities"]=@[@"bad row"];
  assert(![NeoUnifiedNativeRequest(badGame,@[master],snapshot,YES)[@"success"] boolValue]);
  badGame[@"identities"]=@{@"type":@"ps2_crc"};
  assert(!NeoUnifiedNativeGameMatches(badGame,snapshot,YES));
  NSMutableDictionary* badProgram=[master mutableCopy];badProgram[@"dependencies"]=@{@"not":@"a list"};
  assert(![NeoUnifiedNativeRequest(game,@[badProgram],snapshot,YES)[@"success"] boolValue]);
  assert(!NeoUnifiedNativeProgram((id)@"bad program",YES));
  assert(![NeoUnifiedNativeRequest(game,(id)@"bad list",snapshot,YES)[@"success"] boolValue]);
  NSMutableDictionary* badSnapshot=[snapshot mutableCopy];badSnapshot[@"items"]=@[@"bad snapshot row"];
  assert(!NeoUnifiedNativeSnapshotValid(badSnapshot,YES));
  assert(!NeoUnifiedNativeReceipt(root,@{@"unifiedProvenance":@{@"game":game,@"programs":@[@"bad row"]}}));
  assert(![NeoUnifiedNativeRequest(game,@[child],snapshot,YES)[@"success"] boolValue]);
  NSDictionary* request=NeoUnifiedNativeRequest(game,@[master,child],snapshot,YES);
  assert([request[@"success"] boolValue]);
  auto parsed=NeoCheat::parse(NeoUTF8(request[@"content"]),"pnach","Fallback");
  assert(parsed && parsed.entries.size()==1 && parsed.entries[0].lines.size()==2 && parsed.entries[0].name=="Full cheat");
  assert(NeoUnifiedNativeReceipt(root,request));
  NSDictionary* saved=NeoPnachImport(root,request,snapshot);assert([saved[@"success"] boolValue]);
  NSString* pnach=[NSString stringWithContentsOfFile:saved[@"file"] encoding:NSUTF8StringEncoding error:nil];
  assert([pnach containsString:@"D0000000"] && [pnach containsString:@"20000004"]);
  NSMutableDictionary* wrong=[game mutableCopy];wrong[@"identities"]=@[@{@"type":@"ps2_crc",@"scheme":@"pcsx2-executable-crc",@"value":@"12345678"}];
  assert(![NeoUnifiedNativeRequest(wrong,@[master],snapshot,YES)[@"success"] boolValue]);
  NSDictionary* dol=@{@"available":@YES,@"gameId":@"G4BP08",@"revision":@0,@"hardcore":@NO,@"gecko":@[],@"actionReplay":@[]};
  NSDictionary* dolGame=@{@"revision":@"0",@"identities":@[@{@"type":@"game_id",@"scheme":@"dolphin-disc-game-id",@"value":@"G4BP08"}]};
  NSDictionary* dolProgram=@{@"id":@"g",@"name":@"Gecko",@"code":@"04000000 00000001",@"status":@"available",@"dialect":@"gecko",@"parameters":@[],@"dependencies":@[]};
  badGame=[dolGame mutableCopy];badGame[@"identities"]=@[@{@"type":@"game_id",@"value":NSNull.null,@"scheme":@"dolphin-disc-game-id"}];
  assert(![NeoUnifiedNativeRequest(badGame,@[dolProgram],dol,NO)[@"success"] boolValue]);
  request=NeoUnifiedNativeRequest(dolGame,@[dolProgram],dol,NO);
  saved=NeoDolphinImport(root,request,dol,NO);assert([saved[@"success"] boolValue]);
  NSString* ini=[NSString stringWithContentsOfFile:saved[@"file"] encoding:NSUTF8StringEncoding error:nil];
  assert([ini containsString:@"[Gecko_Disabled]\n$Gecko"]);
  wrong=[dolGame mutableCopy];wrong[@"revision"]=@"1";assert(!NeoUnifiedNativeGameMatches(wrong,dol,NO));
  NSMutableDictionary* knownDol=[dol mutableCopy]; knownDol[@"gecko"]=@[@{@"name":@"Gecko"}];
  NSMutableDictionary* second=[dolProgram mutableCopy]; second[@"id"]=@"g2";second[@"code"]=@"04000000 00000002";
  request=NeoUnifiedResolveNativeName(root,NeoUnifiedNativeRequest(dolGame,@[second],knownDol,NO),knownDol,NO);
  assert([request[@"unifiedDisplayName"] isEqual:@"Gecko (2)"]);
  saved=NeoDolphinImport(root,request,knownDol,NO);assert([saved[@"added"] intValue]==1);
  knownDol[@"gecko"]=@[@{@"name":@"Gecko"},@{@"name":@"Gecko (2)"}];
  request=NeoUnifiedResolveNativeName(root,NeoUnifiedNativeRequest(dolGame,@[second],knownDol,NO),knownDol,NO);
  assert([request[@"unifiedDisplayName"] isEqual:@"Gecko (2)"]);
  saved=NeoDolphinImport(root,request,knownDol,NO);assert([saved[@"added"] intValue]==0);
  request=NeoUnifiedResolveNativeName(root,NeoUnifiedNativeRequest(dolGame,@[dolProgram],knownDol,NO),knownDol,NO);
  assert([request[@"unifiedDisplayName"] isEqual:@"Gecko"] && [NeoDolphinImport(root,request,knownDol,NO)[@"added"] intValue]==0);
  NSMutableDictionary* third=[dolProgram mutableCopy];third[@"id"]=@"g3";third[@"code"]=@"04000000 00000003";
  request=NeoUnifiedResolveNativeName(root,NeoUnifiedNativeRequest(dolGame,@[third],knownDol,NO),knownDol,NO);
  assert([request[@"unifiedDisplayName"] isEqual:@"Gecko (3)"]);
  saved=NeoDolphinImport(root,request,knownDol,NO);assert([saved[@"added"] intValue]==1);
  ini=[NSString stringWithContentsOfFile:saved[@"file"] encoding:NSUTF8StringEncoding error:nil];
  assert([ini containsString:@"[Gecko_Disabled]\n$Gecko (2)"] && [ini containsString:@"[Gecko_Disabled]\n$Gecko (3)"]);
  BOOL removed=NO;ini=NeoRemoveCheatBlock(ini,@"gecko",@"Gecko (2)",NO,&removed);assert(removed);
  [ini writeToFile:saved[@"file"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
  knownDol[@"gecko"]=@[@{@"name":@"Gecko"},@{@"name":@"Gecko (3)"}];
  request=NeoUnifiedResolveNativeName(root,NeoUnifiedNativeRequest(dolGame,@[third],knownDol,NO),knownDol,NO);
  assert([request[@"unifiedDisplayName"] isEqual:@"Gecko (3)"] && [NeoDolphinImport(root,request,knownDol,NO)[@"added"] intValue]==0);

  mockRoot=[root stringByAppendingPathComponent:@"RPCS3"];
  [fm createDirectoryAtPath:[mockRoot stringByAppendingPathComponent:@"patches"] withIntermediateDirectories:YES attributes:nil error:nil];
  NSString* official=[mockRoot stringByAppendingPathComponent:@"patches/patch.yml"];
  NSData* original=[@"# Existing exact YAML bytes\nVersion: 1.2\n" dataUsingEncoding:NSUTF8StringEncoding];
  NSData* old=[@"# Older repository backup\n" dataUsingEncoding:NSUTF8StringEncoding];
  [original writeToFile:official atomically:YES];[old writeToFile:[official stringByAppendingString:@".old"] atomically:YES];
  toggles=[NSMutableArray array]; rpcs3_ios_patch_api api={Install,Enumerate,Toggle,Games};
  RPCS3UnifiedCheats* store=[[RPCS3UnifiedCheats alloc] initWithRoot:mockRoot api:api];
  badGame=[PS3Game(@"BLES00001") mutableCopy];badGame[@"identities"]=@[@"bad row"];
  assert(![store stageGame:badGame programs:@[PS3Program(@"invalid",@"BLES00001")] serial:@"BLES00001" version:@"01.01"]);
  assert(![store stageGame:(id)@"bad game" programs:(id)@"bad programs" serial:@"BLES00001" version:@"01.01"]);
  badProgram=[PS3Program(@"invalid",@"BLES00001") mutableCopy];badProgram[@"dependencies"]=@[@{@"invalid":@"dependency"}];
  assert(![RPCS3UnifiedCheats acceptsProgram:badProgram]);
  assert([[store installedVersionForTitle:@"BLES00001"] isEqual:@"01.01"]);
  assert([store stageGame:PS3Game(@"BLES00001") programs:@[PS3Program(@"source-1",@"BLES00001")] serial:@"BLES00001" version:@"01.01"]);
  assert(toggles.count==0 && [[NSData dataWithContentsOfFile:official] isEqual:original]); // staging never calls the Core.
  assert([store applyPendingWhileStoppedForTitle:@"BLES00001"]);
  assert([[NSData dataWithContentsOfFile:official] isEqual:original]);
  assert([[NSData dataWithContentsOfFile:[official stringByAppendingString:@".old"]] isEqual:old]);
  assert(toggles.count==1 && ![toggles.lastObject[@"enabled"] boolValue]);
  assert([fm fileExistsAtPath:[mockRoot stringByAppendingPathComponent:@"patches/BLES00001_patch.yml"]]);
  NSDictionary* state=[store snapshotForTitle:@"BLES00001" version:@"01.01"];assert([state[@"items"] count]==1);
  NSString* identifier=state[@"items"][0][@"id"];
  assert([store stageGame:PS3Game(@"BLES00001") programs:@[PS3Program(@"same-code-other-source",@"BLES00001")] serial:@"BLES00001" version:@"01.01"]);
  assert([[[store snapshotForTitle:@"BLES00001" version:@"01.01"] objectForKey:@"items"] count]==1);
  NSMutableDictionary* secondPS3=[NSJSONSerialization JSONObjectWithData:
      [NSJSONSerialization dataWithJSONObject:PS3Program(@"source-variant",@"BLES00001") options:0 error:nil]
      options:NSJSONReadingMutableContainers error:nil];
  secondPS3[@"native_document"][@"PPU-0123456789012345678901234567890123456789"][@"Original program"][@"Patch"]=@[@[@"be32",@"0x00000000",@"0x00000002"]];
  assert([store stageGame:PS3Game(@"BLES00001") programs:@[secondPS3] serial:@"BLES00001" version:@"01.01"]);
  state=[store snapshotForTitle:@"BLES00001" version:@"01.01"];
  assert([state[@"items"] count]==2 && [state[@"items"][1][@"name"] isEqual:@"Original program (2)"] && ![state[@"items"][1][@"enabled"] boolValue]);
  assert([store stageGame:PS3Game(@"BLES00001") programs:@[secondPS3] serial:@"BLES00001" version:@"01.01"]);
  assert([[[store snapshotForTitle:@"BLES00001" version:@"01.01"] objectForKey:@"items"] count]==2);
  assert([store setIdentifier:identifier enabled:YES serial:@"BLES00001"]);
  assert(![toggles.lastObject[@"enabled"] boolValue]); // still only a request for next launch.
  assert([store applyPendingWhileStoppedForTitle:@"BLES00001"]);
  BOOL requestedEnabled=NO;
  for (NSDictionary* toggle in toggles)
    if ([toggle[@"name"] isEqual:state[@"items"][0][@"description"]]) requestedEnabled=[toggle[@"enabled"] boolValue];
  assert(requestedEnabled && ![toggles.lastObject[@"enabled"] boolValue]);
  assert(![store stageGame:PS3Game(@"BLES00001") programs:@[PS3Program(@"mismatch",@"BLES00001")] serial:@"BLES00001" version:@"01.02"]);
  NSString* personal=[mockRoot stringByAppendingPathComponent:@"patches/BLES00002_patch.yml"];
  [@"# Existing personal YAML\nVersion: 1.2\n" writeToFile:personal atomically:YES encoding:NSUTF8StringEncoding error:nil];
  assert(![store stageGame:PS3Game(@"BLES00002") programs:@[PS3Program(@"other",@"BLES00002")] serial:@"BLES00002" version:@"01.01"]);
  assert([store applyPendingWhileStoppedForTitle:@"BLES00003"]); // a conflict cannot block another title.
  assert([[NSString stringWithContentsOfFile:personal encoding:NSUTF8StringEncoding error:nil] hasPrefix:@"# Existing personal"]);
  assert([store stageGame:PS3Game(@"BLES00003") programs:@[PS3Program(@"source-3",@"BLES00003")] serial:@"BLES00003" version:@"01.01"]);
  rejectInstall=YES;assert(![store applyPendingWhileStoppedForTitle:@"BLES00003"]);
  assert(store.bootSafe && [[store snapshotForTitle:@"BLES00003" version:@"01.01"][@"preparationFailed"] boolValue]);
  assert([[NSData dataWithContentsOfFile:official] isEqual:original]);
  assert(![fm fileExistsAtPath:[mockRoot stringByAppendingPathComponent:@"patches/BLES00003_patch.yml"]]);
  rejectInstall=NO;assert([store applyPendingWhileStoppedForTitle:@"BLES00003"]);
  assert(store.bootSafe);
  NSMutableDictionary* allGame=[PS3Game(@"BLES00004") mutableCopy];
  allGame[@"version_scope"]=@"all";allGame[@"revision"]=@"";
  NSMutableDictionary* allProgram=[NSJSONSerialization JSONObjectWithData:
      [NSJSONSerialization dataWithJSONObject:PS3Program(@"source-all",@"BLES00004") options:0 error:nil]
      options:NSJSONReadingMutableContainers error:nil];
  NSString* ppu=@"PPU-0123456789012345678901234567890123456789";
  allProgram[@"native_document"][ppu][@"Original program"][@"Games"][@"Original title"][@"BLES00004"]=@[@"All"];
  assert([store stageGame:allGame programs:@[allProgram] serial:@"BLES00004" version:@"01.03"]);
  assert([store applyPendingWhileStoppedForTitle:@"BLES00004"]);
  assert([toggles.lastObject[@"version"] isEqual:@"01.03"]); // author All scope narrowed to the installed release.
  allGame[@"edition_confirmed"]=@NO;
  assert(![store stageGame:allGame programs:@[allProgram] serial:@"BLES00004" version:@"01.03"]);
  // A missing optional API or rejected pending source must not stop an
  // unaffected game. A failure to restore global files is materially distinct.
  RPCS3UnifiedCheats* oldCore=[[RPCS3UnifiedCheats alloc] initWithRoot:mockRoot api:(rpcs3_ios_patch_api){}];
  assert([oldCore applyPendingWhileStoppedForTitle:@"BLES99999"] && oldCore.bootSafe);
  NSString* staging=[mockRoot stringByAppendingPathComponent:@"NeoStationUnifiedCheats"];
  NSString* statePath=[staging stringByAppendingPathComponent:@"state.json"];
  NSMutableDictionary* corrupt=[NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:statePath] options:NSJSONReadingMutableContainers error:nil];
  [corrupt[@"programs"] addObject:@"broken sibling"];
  [corrupt[@"programs"] addObject:@{@"serial":NSNull.null,@"enabled":@"bad Boolean"}];
  [[NSJSONSerialization dataWithJSONObject:corrupt options:0 error:nil] writeToFile:statePath atomically:YES];
  assert([[[store snapshotForTitle:@"BLES00001" version:@"01.01"] objectForKey:@"items"] count]==2); // intact siblings survive.
  NSData* intactState=[NSData dataWithContentsOfFile:statePath];
  corrupt[@"schema_version"]=@"1";
  [[NSJSONSerialization dataWithJSONObject:corrupt options:0 error:nil] writeToFile:statePath atomically:YES];
  assert(![store stageGame:PS3Game(@"BLES00005") programs:@[PS3Program(@"schema-bad",@"BLES00005")] serial:@"BLES00005" version:@"01.01"]);
  assert(![store applyPendingWhileStoppedForTitle:@"BLES99999"] && store.bootSafe);
  [intactState writeToFile:statePath atomically:YES];
  [fm removeItemAtPath:[staging stringByAppendingPathComponent:@"patch.yml.before-unified"] error:nil];
  NSData* journal=[NSJSONSerialization dataWithJSONObject:@{@"patch.yml":@YES,@"patch.yml.old":@YES} options:0 error:nil];
  [journal writeToFile:[staging stringByAppendingPathComponent:@"transaction.json"] atomically:YES];
  assert(![store applyPendingWhileStoppedForTitle:@"BLES99999"] && !store.bootSafe);
  [original writeToFile:[staging stringByAppendingPathComponent:@"patch.yml.before-unified"] atomically:YES];
  assert([store applyPendingWhileStoppedForTitle:@"BLES99999"] && store.bootSafe);
  [fm removeItemAtPath:root error:nil];
  NSLog(@"PASS: native imports, single dependency toggle, disabled states, RPCS3 staging/transaction recovery, personal-file preservation and isolated conflicts (Core transport mocked)");
} return 0; }
