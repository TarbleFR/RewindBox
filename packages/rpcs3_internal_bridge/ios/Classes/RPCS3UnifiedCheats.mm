// SPDX-License-Identifier: GPL-3.0-or-later
#import "RPCS3UnifiedCheats.h"
#import <CommonCrypto/CommonDigest.h>

static NSString* RPCheatString(id object) { return [object isKindOfClass:NSString.class] ? object : @""; }
static BOOL RPCheatMatch(NSString* value,NSString* expression) {
  return [value isKindOfClass:NSString.class] && [value rangeOfString:expression options:NSRegularExpressionSearch].location != NSNotFound;
}
static NSString* RPCheatDigest(NSData* bytes) {
  unsigned char hash[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(bytes.bytes,(CC_LONG)bytes.length,hash);
  NSMutableString* result=[NSMutableString string];
  for (unsigned char byte : hash) [result appendFormat:@"%02x",byte];
  return result;
}
static NSData* RPCheatJSON(id object) {
  return [NSJSONSerialization isValidJSONObject:object]
      ? [NSJSONSerialization dataWithJSONObject:object options:NSJSONWritingSortedKeys error:nil] : nil;
}
// The builder supplies a parsed, standalone YAML document as JSON. JSON is
// valid YAML 1.2. Never reconstruct YAML by replacing strings or renaming NCL.
static NSDictionary* RPCheatDocument(NSDictionary* program) {
  if (![program isKindOfClass:NSDictionary.class] || ![program[@"id"] isKindOfClass:NSString.class] ||
      ![program[@"name"] isKindOfClass:NSString.class]) return nil;
  for (NSString* key in @[@"parameters",@"dependencies",@"provenance"])
    if (program[key] && ![program[key] isKindOfClass:NSArray.class]) return nil;
  for (id dependency in program[@"dependencies"]) if (![dependency isKindOfClass:NSString.class]) return nil;
  for (id source in program[@"provenance"]) {
    if (![source isKindOfClass:NSDictionary.class]) return nil;
    for (NSString* key in @[@"source_id",@"url",@"author",@"revision",@"license"])
      if (source[key] && ![source[key] isKindOfClass:NSString.class]) return nil;
  }
  if (![RPCheatString(program[@"status"]) isEqual:@"available"] ||
      ![RPCheatString(program[@"dialect"]) isEqual:@"rpcs3-yaml"] ||
      ([program[@"parameters"] isKindOfClass:NSArray.class] && [program[@"parameters"] count])) return nil;
  NSDictionary* document=[program[@"native_document"] isKindOfClass:NSDictionary.class] ? program[@"native_document"] : nil;
  if (!document || ![[document[@"Version"] description] isEqual:@"1.2"] || document.count != 2) return nil;
  NSString* hash=nil;
  for (NSString* key in document) {
    if (![key isKindOfClass:NSString.class]) return nil;
    if (![key isEqual:@"Version"]) hash=key;
  }
  if (!RPCheatMatch(hash ?: @"",@"^PPU-[0-9A-Fa-f]{40}$")) return nil;
  NSDictionary* variants=[document[hash] isKindOfClass:NSDictionary.class] ? document[hash] : nil;
  if (!variants.count || variants.count > 64) return nil;
  for (NSString* name in variants) {
    if (![name isKindOfClass:NSString.class]) return nil;
    NSDictionary* patch=[variants[name] isKindOfClass:NSDictionary.class] ? variants[name] : nil;
    if (!name.length || name.length > 512 || !patch || patch[@"Configurable Values"] ||
        ![patch[@"Games"] isKindOfClass:NSDictionary.class] ||
        ![patch[@"Patch"] isKindOfClass:NSArray.class] || ![patch[@"Patch"] count] ||
        [patch[@"Patch"] count] > 8192) return nil;
    for (id line in patch[@"Patch"])
      if (![line isKindOfClass:NSArray.class] || [line count] != 3 ||
          ![line[0] isKindOfClass:NSString.class] ||
          !RPCheatMatch(line[0],@"^(byte|le16|le32|le64|lef32|lef64|be16|be32|be64|bd32|bd64|bef32|bef64|alloc|code_alloc|jump|jump_link|jump_func|utf8|cutf8|bpex)$") ||
          // patch_type_uses_hex_offset covers every opcode allowed above.
          // A typed YAML loader must preserve/re-emit hexadecimal addresses:
          // JSON decimal numbers are scalars but the real Core rejects them.
          !RPCheatMatch(line[1],@"^0x[0-9A-Fa-f]{1,8}$") ||
          !([line[2] isKindOfClass:NSString.class] || [line[2] isKindOfClass:NSNumber.class])) return nil;
  }
  return document;
}

// Reviewed NCL type-0 instruction writes only. No pointers, conditions,
// RAM freeze, repeats, arithmetic or string opcodes can enter this adapter.
static NSArray* RPCheatStaticRows(NSDictionary* program) {
  if(![program isKindOfClass:NSDictionary.class] || ![program[@"dialect"] isEqual:@"ps3-static-be32"] ||
      ![program[@"status"] isEqual:@"available"] || !RPCheatString(program[@"id"]).length || !RPCheatString(program[@"name"]).length) return nil;
  for(NSString* field in @[@"parameters",@"dependencies"])
    if(program[field] && (![program[field] isKindOfClass:NSArray.class] || [program[field] count]))return nil;
  NSString* code=RPCheatString(program[@"code"]);if(!code.length || code.length>4096)return nil;
  NSMutableArray* rows=[NSMutableArray array];
  for(NSString* line in [code componentsSeparatedByString:@"\n"]) {
    if(!RPCheatMatch(line,@"^[0-9A-Fa-f]{8} [0-9A-Fa-f]{8}$"))return nil;
    unsigned address=0;[[NSScanner scannerWithString:[line substringToIndex:8]] scanHexInt:&address];
    if(address<0x10000 || address>=0x02000000 || (address&3))return nil;
    [rows addObject:@[@"be32",[@"0x" stringByAppendingString:[line substringToIndex:8]],[@"0x" stringByAppendingString:[line substringFromIndex:9]]]];
    if(rows.count>64)return nil;
  }
  return rows.count ? rows : nil;
}
@interface RPCS3UnifiedCheats ()
@property(nonatomic,copy) NSString* root;
@property(nonatomic,assign) rpcs3_ios_patch_api api;
@property(nonatomic,readwrite) BOOL bootSafe;
@property(nonatomic,assign) BOOL preparationFailed;
@property(nonatomic,copy) NSString* preparationTitle;
- (BOOL)managedTitleFile:(NSString*)serial state:(NSDictionary*)state;
@end

@implementation RPCS3UnifiedCheats
- (instancetype)initWithRoot:(NSString*)root api:(rpcs3_ios_patch_api)api {
  if ((self=[super init])) { _root=[root copy]; _api=api; }
  return self;
}
+ (BOOL)acceptsProgram:(NSDictionary*)program { return RPCheatDocument(program) != nil || RPCheatStaticRows(program) != nil; }
- (NSString*)folder { return [self.root stringByAppendingPathComponent:@"NeoStationUnifiedCheats"]; }
- (NSString*)statePath { return [self.folder stringByAppendingPathComponent:@"state.json"]; }
- (NSMutableDictionary*)state {
  NSData* data=[NSData dataWithContentsOfFile:self.statePath options:0 error:nil];
  // A mutable root copy does not make its nested literal array mutable.
  // The first import must be able to append before any state file exists.
  if (!data) return [@{@"schema_version":@1,@"pending":@NO,@"programs":[NSMutableArray array]} mutableCopy];
  if (data.length > 32*1024*1024) return nil;
  id object=[NSJSONSerialization JSONObjectWithData:data options:NSJSONReadingMutableContainers error:nil];
  if (![object isKindOfClass:NSMutableDictionary.class] ||
      ![object[@"schema_version"] isKindOfClass:NSNumber.class] || [object[@"schema_version"] doubleValue]!=1 ||
      ![object[@"programs"] isKindOfClass:NSMutableArray.class]) return nil;
  // A corrupt sibling must not crash the menu or discard intact records.
  // Its native file remains protected by managedTitleFile's exact comparison.
  NSMutableArray* intact=[NSMutableArray array];
  for (id raw in object[@"programs"]) {
    if (![raw isKindOfClass:NSMutableDictionary.class]) continue;
    BOOL valid=YES;
    for (NSString* key in @[@"id",@"name",@"serial",@"version",@"hash",@"title",@"description"])
      if (![raw[key] isKindOfClass:NSString.class] || ![raw[key] length]) valid=NO;
    if (![raw[@"patch"] isKindOfClass:NSDictionary.class] || ![raw[@"enabled"] isKindOfClass:NSNumber.class] ||
        (raw[@"pending"] && ![raw[@"pending"] isKindOfClass:NSNumber.class]) ||
        (raw[@"sources"] && ![raw[@"sources"] isKindOfClass:NSArray.class]) ||
        (raw[@"game"] && ![raw[@"game"] isKindOfClass:NSDictionary.class])) valid=NO;
    if (valid) [intact addObject:raw];
  }
  object[@"programs"]=intact;
  object[@"pending"]=@NO;
  for (NSDictionary* record in intact) if ([record[@"pending"] boolValue]) object[@"pending"]=@YES;
  return object;
}
- (BOOL)save:(NSDictionary*)state {
  NSData* data=RPCheatJSON(state);
  return data.length && data.length<=32*1024*1024 &&
      [NSFileManager.defaultManager createDirectoryAtPath:self.folder withIntermediateDirectories:YES attributes:nil error:nil] &&
      [data writeToFile:self.statePath options:NSDataWritingAtomic error:nil];
}

static void RPCheatGame(void* context,const rpcs3_ios_catalogue_game_info* game) {
  NSMutableDictionary* result=(__bridge NSMutableDictionary*)context;
  if (game && game->struct_size>=sizeof(*game) && game->title_id && game->version)
    result[@(game->title_id)]=@(game->version);
}
- (NSString*)installedVersionForTitle:(NSString*)serial {
  if (![serial isKindOfClass:NSString.class]) return @"";
  if (!self.api.enumerate_games) return @"";
  NSMutableDictionary* versions=[NSMutableDictionary dictionary];
  return self.api.enumerate_games(RPCheatGame,(__bridge void*)versions)==0 ? RPCheatString(versions[serial]) : @"";
}
- (NSDictionary*)snapshotForTitle:(NSString*)serial version:(NSString*)version {
  serial=RPCheatString(serial); version=RPCheatString(version);
  NSMutableArray* rows=[NSMutableArray array];
  NSDictionary* state=[self state];
  for (NSDictionary* record in state[@"programs"])
    if ([RPCheatString(record[@"serial"]) isEqual:serial] && [RPCheatString(record[@"version"]) isEqual:version] &&
        (!self.runtimePPUHash.length || [record[@"hash"] isEqual:self.runtimePPUHash]))
      [rows addObject:record];
  return @{@"available":@(self.api.install_repository && self.api.set_enabled && self.api.enumerate_patches),
      @"serial":serial ?: @"", @"revision":version ?: @"", @"ppuHash":self.runtimePPUHash ?: @"", @"items":rows,
      @"conflict":@(state && ![self managedTitleFile:serial state:state]),
      @"preparationFailed":@(self.preparationFailed && [self.preparationTitle isEqual:serial])};
}
- (BOOL)managedTitleFile:(NSString*)serial state:(NSDictionary*)state {
  NSString* path=[[self.root stringByAppendingPathComponent:@"patches"] stringByAppendingPathComponent:[serial stringByAppendingString:@"_patch.yml"]];
  if (![NSFileManager.defaultManager fileExistsAtPath:path]) return YES;
  BOOL owned=NO;
  for (NSDictionary* record in state[@"programs"]) if ([record[@"serial"] isEqual:serial]) owned=YES;
  if (!owned) return NO;
  NSDictionary* attributes=[NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
  if (![attributes[NSFileType] isEqual:NSFileTypeRegular] || [attributes[NSFileSize] unsignedLongLongValue]>32*1024*1024) return NO;
  NSData* bytes=[NSData dataWithContentsOfFile:path];
  NSDictionary* old=bytes ? [NSJSONSerialization JSONObjectWithData:bytes options:0 error:nil] : nil;
  if (![old isKindOfClass:NSDictionary.class] || old.count<2 || ![[old[@"Version"] description] isEqual:@"1.2"]) return NO;
  for (NSString* hash in old) if (![hash isEqual:@"Version"]) {
    if (![old[hash] isKindOfClass:NSDictionary.class]) return NO;
    for (NSString* description in old[hash]) {
      BOOL found=NO;
      for (NSDictionary* record in state[@"programs"])
        if ([record[@"serial"] isEqual:serial] && [record[@"hash"] isEqual:hash] &&
            [record[@"description"] isEqual:description] && [record[@"patch"] isEqual:old[hash][description]]) found=YES;
      if (!found) return NO; // preserve every unknown or user-modified patch.
    }
  }
  return YES;
}
- (BOOL)stageGame:(NSDictionary*)game programs:(NSArray*)programs serial:(NSString*)serial version:(NSString*)version {
  if (![game isKindOfClass:NSDictionary.class] || ![programs isKindOfClass:NSArray.class] ||
      ![game[@"identities"] isKindOfClass:NSArray.class] ||
      (game[@"revision"] && ![game[@"revision"] isKindOfClass:NSString.class]) ||
      (game[@"version_scope"] && ![game[@"version_scope"] isKindOfClass:NSString.class]) ||
      ![game[@"edition_confirmed"] isKindOfClass:NSNumber.class]) return NO;
  for (id identity in game[@"identities"])
    if (![identity isKindOfClass:NSDictionary.class] || ![identity[@"type"] isKindOfClass:NSString.class] ||
        ![identity[@"value"] isKindOfClass:NSString.class] || ![identity[@"scheme"] isKindOfClass:NSString.class]) return NO;
  BOOL allVersions=[RPCheatString(game[@"version_scope"]) isEqual:@"all"];
  if (!self.api.install_repository || !self.api.set_enabled || !self.api.enumerate_patches ||
      !RPCheatMatch(serial,@"^[A-Z0-9]{9}$") || !RPCheatMatch(version,@"^[0-9]{2}\\.[0-9]{2}$") ||
      (!allVersions && ![RPCheatString(game[@"revision"]) isEqual:version]) || ![game[@"edition_confirmed"] boolValue] ||
      !programs.count || programs.count>512) return NO;
  BOOL matchedSerial=NO;
  for (NSDictionary* identity in game[@"identities"])
    if ([RPCheatString(identity[@"type"]) isEqual:@"serial"] && [RPCheatString(identity[@"scheme"]) isEqual:@"ps3-title-id"])
      matchedSerial|=[RPCheatString(identity[@"value"]) isEqual:serial];
  if (!matchedSerial) return NO;
  NSMutableDictionary* state=[self state]; if (!state || ![self managedTitleFile:serial state:state]) return NO;
  NSMutableArray* ids=[NSMutableArray array],*lines=[NSMutableArray array],*authors=[NSMutableArray array],*notes=[NSMutableArray array];
  NSMutableSet* groups=[NSMutableSet set];
  NSString* commonHash=nil; NSString* title=nil; BOOL runtimeBinding=NO;
  for (NSDictionary* program in programs) {
    NSDictionary* document=RPCheatDocument(program);
    if(!document && RPCheatStaticRows(program)) {
      if(!RPCheatMatch(self.runtimePPUHash,@"^PPU-[0-9a-f]{40}$") || allVersions || !RPCheatString(game[@"title"]).length)return NO;
      runtimeBinding=YES;
      NSString *author=RPCheatString(program[@"author"]);
      document=@{@"Version":@"1.2",self.runtimePPUHash:@{program[@"name"]:@{@"Games":@{game[@"title"]:@{serial:@[version]}},@"Patch":RPCheatStaticRows(program),
          @"Author":author.length ? author : @"CodeFreak/PS3UserCheat",@"Notes":RPCheatString(program[@"notes"])}}};
    }
    if (!document) return NO;
    [ids addObject:RPCheatString(program[@"id"])];
    for (NSString* hash in document) if (![hash isEqual:@"Version"]) {
      if (commonHash && ![commonHash isEqual:hash]) return NO; commonHash=hash;
      for (NSString* name in document[hash]) {
        NSDictionary* patch=document[hash][name]; NSString* thisTitle=nil;
        for (NSString* candidate in patch[@"Games"]) {
          if (![candidate isKindOfClass:NSString.class]) return NO;
          NSDictionary* serials=[patch[@"Games"][candidate] isKindOfClass:NSDictionary.class] ? patch[@"Games"][candidate] : nil;
          NSArray* versions=[serials[serial] isKindOfClass:NSArray.class] ? serials[serial] : nil;
          for (id sourceVersion in versions) if (![sourceVersion isKindOfClass:NSString.class]) return NO;
          if ([versions containsObject:version] || (allVersions && [versions containsObject:@"All"])) thisTitle=candidate;
        }
        if (!thisTitle || (title && ![title isEqual:thisTitle])) return NO; title=thisTitle;
        [lines addObjectsFromArray:patch[@"Patch"]];
        if (RPCheatString(patch[@"Author"]).length) [authors addObject:patch[@"Author"]];
        if (RPCheatString(patch[@"Notes"]).length) [notes addObject:patch[@"Notes"]];
        if (RPCheatString(patch[@"Group"]).length) [groups addObject:patch[@"Group"]];
      }
    }
  }
  NSSet* included=[NSSet setWithArray:ids];
  for (NSDictionary* program in programs)
    for (id dependency in program[@"dependencies"])
      if (![dependency isKindOfClass:NSString.class] || ![included containsObject:dependency]) return NO;
  if (!commonHash || !title || !lines.count || lines.count>8192 || groups.count>1) return NO;
  BOOL matchedHash=NO;
  for (NSDictionary* identity in game[@"identities"])
    if ([RPCheatString(identity[@"type"]) isEqual:@"ppu_hash"] && [RPCheatString(identity[@"scheme"]) isEqual:@"rpcs3-ppu-hash"])
      matchedHash|=[RPCheatString(identity[@"value"]).lowercaseString isEqual:[[commonHash substringFromIndex:4] lowercaseString]];
  if (!matchedHash && !runtimeBinding) return NO;
  if(self.runtimePPUHash.length && ![commonHash isEqual:self.runtimePPUHash])return NO;
  NSString* originalName=RPCheatString([programs lastObject][@"name"]);
  NSString* key=RPCheatDigest(RPCheatJSON(@{@"serial":serial,@"version":version,@"hash":commonHash,
      @"name":originalName,@"lines":lines,@"group":groups.anyObject ?: @""}));
  for (NSDictionary* old in state[@"programs"]) if ([old[@"id"] isEqual:key]) return YES;
  NSMutableSet* occupiedNames=[NSMutableSet set];
  for (NSDictionary* old in state[@"programs"])
    if ([old[@"serial"] isEqual:serial] && [old[@"version"] isEqual:version]) [occupiedNames addObject:RPCheatString(old[@"name"])];
  NSString* name=originalName; NSUInteger ordinal=2;
  while ([occupiedNames containsObject:name] && ordinal<=10000)
    name=[NSString stringWithFormat:@"%@ (%lu)",originalName,(unsigned long)ordinal++];
  if ([occupiedNames containsObject:name]) return NO;
  NSString* description=[NSString stringWithFormat:@"NeoStation/%@/%@",NSUUID.UUID.UUIDString,name];
  NSMutableDictionary* patch=[@{@"Games":@{title:@{serial:@[version]}}, @"Author":[authors componentsJoinedByString:@", "],
      @"Notes":[notes componentsJoinedByString:@"\n"], @"Patch":lines} mutableCopy];
  if (groups.count) patch[@"Group"]=groups.anyObject;
  [state[@"programs"] addObject:@{@"id":key,@"name":name,@"source_name":originalName,@"serial":serial,@"version":version,
      @"hash":commonHash,@"title":title,@"description":description,@"patch":patch,
      @"enabled":@NO,@"pending":@YES,@"game":game,@"sources":programs,
      @"runtimeBound":@(runtimeBinding),@"mappedPPUHash":self.runtimePPUHash ?: @""}];
  state[@"pending"]=@YES;
  return [self save:state];
}
- (BOOL)setIdentifier:(NSString*)identifier enabled:(BOOL)enabled serial:(NSString*)serial {
  if (![identifier isKindOfClass:NSString.class] || ![serial isKindOfClass:NSString.class]) return NO;
  NSMutableDictionary* state=[self state]; if (!state) return NO;
  for (NSMutableDictionary* record in state[@"programs"]) if ([record[@"id"] isEqual:identifier] && [record[@"serial"] isEqual:serial]) {
    NSString* group=RPCheatString(record[@"patch"][@"Group"]);
    if (enabled && group.length)
      for (NSMutableDictionary* other in state[@"programs"])
        if ([other[@"serial"] isEqual:serial] && [RPCheatString(other[@"patch"][@"Group"]) isEqual:group]) {
          other[@"enabled"]=@NO; other[@"pending"]=@YES;
        }
    record[@"enabled"]=@(enabled); record[@"pending"]=@YES; state[@"pending"]=@YES; return [self save:state];
  }
  return NO;
}

// install_patch_repository validates with the Core's real YAML parser. It
// writes patch.yml, so journal/restore those exact bytes before publishing our
// own *_patch.yml. Recovery runs before every boot, including after a crash.
- (BOOL)restoreRepositoryTransaction {
  NSString* journal=[self.folder stringByAppendingPathComponent:@"transaction.json"];
  NSData* data=[NSData dataWithContentsOfFile:journal]; if (!data) return YES;
  NSDictionary* transaction=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  if (![transaction isKindOfClass:NSDictionary.class]) return NO;
  for (NSString* name in @[@"patch.yml",@"patch.yml.old"])
    if (![transaction[name] isKindOfClass:NSNumber.class]) return NO;
  NSString* patches=[self.root stringByAppendingPathComponent:@"patches"];
  for (NSString* name in @[@"patch.yml",@"patch.yml.old"]) {
    NSString* target=[patches stringByAppendingPathComponent:name];
    NSString* backup=[self.folder stringByAppendingPathComponent:[name stringByAppendingString:@".before-unified"]];
    if ([transaction[name] boolValue]) {
      NSData* original=[NSData dataWithContentsOfFile:backup];
      if (!original || ![original writeToFile:target options:NSDataWritingAtomic error:nil]) return NO;
    } else if ([NSFileManager.defaultManager fileExistsAtPath:target] &&
               ![NSFileManager.defaultManager removeItemAtPath:target error:nil]) return NO;
  }
  return [NSFileManager.defaultManager removeItemAtPath:journal error:nil];
}
- (BOOL)applyPendingWhileStoppedForTitle:(NSString*)serial {
  self.bootSafe=NO; self.preparationFailed=YES; self.preparationTitle=serial;
  if (![self restoreRepositoryTransaction]) return NO;
  // A failed catalogue validation cannot prevent normal gameplay once these
  // original global files are known to be restored. Only failed restoration
  // itself is a reason to stop a launch.
  self.bootSafe=YES;
  if (!RPCheatMatch(serial,@"^[A-Z0-9]{9}$")) return NO;
  NSMutableDictionary* state=[self state]; if (!state) return NO;
  BOOL pending=NO;
  for (NSDictionary* record in state[@"programs"])
    if ([record[@"serial"] isEqual:serial] && [record[@"pending"] boolValue]) pending=YES;
  if (!pending) { self.preparationFailed=NO; return YES; }
  if (![self managedTitleFile:serial state:state]) return NO;
  if (!self.api.install_repository || !self.api.enumerate_patches || !self.api.set_enabled) return NO;
  NSMutableDictionary* document=[@{@"Version":@"1.2"} mutableCopy];
  for (NSDictionary* record in state[@"programs"]) {
    if (![record[@"serial"] isEqual:serial]) continue;
    NSString* hash=RPCheatString(record[@"hash"]),*description=RPCheatString(record[@"description"]);
    if (!RPCheatMatch(hash,@"^PPU-[0-9A-Fa-f]{40}$") || !description.length || ![record[@"patch"] isKindOfClass:NSDictionary.class]) return NO;
    if (!document[hash]) document[hash]=[NSMutableDictionary dictionary];
    document[hash][description]=record[@"patch"];
  }
  NSData* content=RPCheatJSON(document); if (!content.length || content.length>32*1024*1024) return NO;
  NSString* patches=[self.root stringByAppendingPathComponent:@"patches"];
  NSFileManager* fm=NSFileManager.defaultManager;
  if (![fm createDirectoryAtPath:patches withIntermediateDirectories:YES attributes:nil error:nil] ||
      ![fm createDirectoryAtPath:self.folder withIntermediateDirectories:YES attributes:nil error:nil]) return NO;
  NSMutableDictionary* transaction=[NSMutableDictionary dictionary];
  for (NSString* name in @[@"patch.yml",@"patch.yml.old"]) {
    NSString* path=[patches stringByAppendingPathComponent:name];
    BOOL exists=[fm fileExistsAtPath:path]; transaction[name]=@(exists);
    if (exists) {
      NSDictionary* attributes=[fm attributesOfItemAtPath:path error:nil];
      if (![attributes[NSFileType] isEqual:NSFileTypeRegular] || [attributes[NSFileSize] unsignedLongLongValue]>64*1024*1024) return NO;
      NSData* original=[NSData dataWithContentsOfFile:path];
      if (!original || ![original writeToFile:[self.folder stringByAppendingPathComponent:[name stringByAppendingString:@".before-unified"]] options:NSDataWritingAtomic error:nil]) return NO;
    }
  }
  if (![RPCheatJSON(transaction) writeToFile:[self.folder stringByAppendingPathComponent:@"transaction.json"] options:NSDataWritingAtomic error:nil]) return NO;
  self.bootSafe=NO;
  const BOOL valid=self.api.install_repository("1.2",RPCheatDigest(content).UTF8String,content.bytes,content.length)==0;
  BOOL installed=NO;
  if (valid) installed=[content writeToFile:[patches stringByAppendingPathComponent:[serial stringByAppendingString:@"_patch.yml"]] options:NSDataWritingAtomic error:nil];
  BOOL restored=[self restoreRepositoryTransaction]; self.bootSafe=restored;
  if (!restored || !installed) return NO;
  // Unique import names cannot inherit an old enabled state. Every Boolean
  // below is a persisted explicit user choice; newly imported entries are NO.
  for (NSDictionary* record in state[@"programs"]) {
    if (![record[@"serial"] isEqual:serial]) continue;
    if (self.api.set_enabled([record[@"serial"] UTF8String],[record[@"hash"] UTF8String],
        [record[@"title"] UTF8String],[record[@"version"] UTF8String],
        [record[@"description"] UTF8String],[record[@"enabled"] boolValue] ? 1u : 0u)!=0) return NO;
  }
  pending=NO;
  for (NSMutableDictionary* record in state[@"programs"]) {
    if ([record[@"serial"] isEqual:serial]) record[@"pending"]=@NO;
    pending|=[record[@"pending"] boolValue];
  }
  state[@"pending"]=@(pending);
  BOOL saved=[self save:state]; self.preparationFailed=!saved;
  return saved;
}
@end
