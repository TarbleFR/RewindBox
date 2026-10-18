// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "NeoCheatStore.h"
#include "NeoCheatLabels.h"
#include "NeoUnifiedNativeProgram.h"

static BOOL NeoUnifiedNativeSnapshotValid(id value, BOOL ps2) {
  if (![value isKindOfClass:NSDictionary.class]) return NO;
  NSDictionary* snapshot=value;
  if (![snapshot[@"available"] isKindOfClass:NSNumber.class] ||
      (snapshot[@"hardcore"] && ![snapshot[@"hardcore"] isKindOfClass:NSNumber.class]) ||
      ![snapshot[ps2 ? @"crc" : @"gameId"] isKindOfClass:NSString.class] ||
      (ps2 ? ![snapshot[@"serial"] isKindOfClass:NSString.class] : ![snapshot[@"revision"] isKindOfClass:NSNumber.class])) return NO;
  for (NSString* key in ps2 ? @[@"items"] : @[@"gecko",@"actionReplay"]) {
    id items=snapshot[key]; if (items && ![items isKindOfClass:NSArray.class]) return NO;
    for (id item in items) {
      if (![item isKindOfClass:NSDictionary.class] || ![item[@"name"] isKindOfClass:NSString.class] ||
          (ps2 && item[@"cheat"] && ![item[@"cheat"] isKindOfClass:NSNumber.class])) return NO;
    }
  }
  return YES;
}

static NSDictionary* NeoUnifiedEngineIdentity(NSDictionary* snapshot, BOOL ps2) {
  if (!NeoUnifiedNativeSnapshotValid(snapshot,ps2)) return @{};
  NSString* value = NeoField(snapshot, ps2 ? @"crc" : @"gameId");
  NSMutableArray* identities = [NSMutableArray arrayWithObject:@{
    @"type": ps2 ? @"ps2_crc" : @"game_id", @"value": value,
    @"scheme": ps2 ? @"pcsx2-executable-crc" : @"dolphin-disc-game-id"}];
  if (ps2 && NeoField(snapshot, @"serial").length)
    [identities addObject:@{@"type":@"serial", @"value":snapshot[@"serial"], @"scheme":@"ps2-disc-serial"}];
  // GameCube and Wii GameIDs have the region/language encoded in the ID;
  // revision remains an independent constraint, never inferred from a title.
  return @{@"system":ps2 ? @"ps2" : ([snapshot[@"wii"] boolValue] ? @"wii" : @"gc"),
           @"title":@"", @"identities":identities, @"regions":@[], @"languages":@[],
           @"revision":ps2 ? @"" : [snapshot[@"revision"] description] ?: @""};
}

static BOOL NeoUnifiedNativeGameMatches(NSDictionary* game, NSDictionary* snapshot, BOOL ps2) {
  if (![game isKindOfClass:NSDictionary.class] || !NeoUnifiedNativeSnapshotValid(snapshot,ps2) ||
      ![game[@"identities"] isKindOfClass:NSArray.class] ||
      (game[@"revision"] && ![game[@"revision"] isKindOfClass:NSString.class]) ||
      (game[@"edition_confirmed"] && ![game[@"edition_confirmed"] isKindOfClass:NSNumber.class])) return NO;
  NSString* required = ps2 ? @"ps2_crc" : @"game_id";
  NSString* scheme = ps2 ? @"pcsx2-executable-crc" : @"dolphin-disc-game-id";
  NSString* expected = NeoField(snapshot, ps2 ? @"crc" : @"gameId").uppercaseString;
  BOOL found = NO;
  for (id raw in game[@"identities"]) {
    if (![raw isKindOfClass:NSDictionary.class] || ![raw[@"type"] isKindOfClass:NSString.class] ||
        ![raw[@"value"] isKindOfClass:NSString.class] || ![raw[@"scheme"] isKindOfClass:NSString.class]) return NO;
    NSDictionary* item = raw;
    if ([NeoField(item,@"type") isEqual:required] && [NeoField(item,@"scheme") isEqual:scheme]) {
      if (![NeoField(item,@"value").uppercaseString isEqual:expected]) return NO;
      found = YES;
    }
    if (ps2 && [NeoField(item,@"type") isEqual:@"serial"]) {
      NSString* a = [NeoField(item,@"value").uppercaseString stringByReplacingOccurrencesOfString:@"-" withString:@""];
      NSString* b = [NeoField(snapshot,@"serial").uppercaseString stringByReplacingOccurrencesOfString:@"-" withString:@""];
      if (a.length && b.length && ![a isEqual:b]) return NO;
    }
  }
  if (!ps2 && NeoField(game,@"revision").length &&
      ![NeoField(game,@"revision") isEqual:[snapshot[@"revision"] description]]) return NO;
  if (!ps2 && !NeoField(game,@"revision").length && ![game[@"edition_confirmed"] boolValue]) return NO;
  return found;
}

static NeoCheat::Result NeoUnifiedNativeProgram(NSDictionary* program, BOOL ps2) {
  NeoCheat::Result rejected; rejected.error = "format";
  if (![program isKindOfClass:NSDictionary.class] || ![program[@"id"] isKindOfClass:NSString.class] ||
      ![program[@"name"] isKindOfClass:NSString.class] || ![program[@"code"] isKindOfClass:NSString.class] ||
      ![program[@"dialect"] isKindOfClass:NSString.class]) return rejected;
  for (NSString* key in @[@"parameters",@"dependencies",@"provenance"])
    if (program[key] && ![program[key] isKindOfClass:NSArray.class]) return rejected;
  if (![NeoField(program,@"status") isEqual:@"available"] ||
      ([program[@"parameters"] isKindOfClass:NSArray.class] && [program[@"parameters"] count])) return rejected;
  NSString* author = @"";
  NSMutableArray* notes = [NSMutableArray array];
  if ([program[@"provenance"] isKindOfClass:NSArray.class])
    for (id raw in program[@"provenance"]) {
      if (![raw isKindOfClass:NSDictionary.class]) return rejected;
      for (NSString* key in @[@"source_id",@"url",@"author",@"revision",@"license"])
        if (raw[key] && ![raw[key] isKindOfClass:NSString.class]) return rejected;
      if (!author.length) author = NeoField(raw,@"author");
      NSString* url = NeoField(raw,@"url");
      if (url.length && url.length <= 2048 && [url rangeOfCharacterFromSet:NSCharacterSet.newlineCharacterSet].location == NSNotFound)
        [notes addObject:[@"Source: " stringByAppendingString:url]];
    }
  if (!NeoCheat::safeName(NeoUTF8(author))) author = @"";
  auto result = NeoUnifiedNative::parse(NeoUTF8(NeoField(program,@"code")),
      NeoUTF8(NeoField(program,@"dialect")), NeoUTF8(NeoField(program,@"name")), NeoUTF8(author), ps2);
  if (result) for (auto& entry : result.entries)
    for (NSString* note in notes) entry.notes.push_back(NeoUTF8(note));
  return result;
}

static NSDictionary* NeoUnifiedNativeRequest(NSDictionary* game, NSArray* programs,
                                            NSDictionary* snapshot, BOOL ps2) {
  if (![programs isKindOfClass:NSArray.class] || programs.count>512) return NeoCheatFailure(@"invalidCode");
  if (!NeoUnifiedNativeGameMatches(game,snapshot,ps2)) return NeoCheatFailure(@"wrongGame");
  std::vector<NeoCheat::Entry> entries;
  NSMutableSet* selected = [NSMutableSet set];
  for (id program in programs) {
    if (![program isKindOfClass:NSDictionary.class] || ![program[@"id"] isKindOfClass:NSString.class] ||
        !NeoField(program,@"id").length || [selected containsObject:program[@"id"]]) return NeoCheatFailure(@"invalidCode");
    [selected addObject:program[@"id"]];
  }
  for (NSDictionary* program in programs) {
    const auto parsed = NeoUnifiedNativeProgram(program,ps2);
    if (!parsed) return NeoParserFailure(parsed);
    if ([program[@"dependencies"] isKindOfClass:NSArray.class])
      for (id dependency in program[@"dependencies"])
        if (![dependency isKindOfClass:NSString.class] || ![selected containsObject:dependency]) return NeoCheatFailure(@"invalidCode");
    entries.insert(entries.end(),parsed.entries.begin(),parsed.entries.end());
  }
  if (entries.empty()) return NeoCheatFailure(@"emptyFile");
  if (entries.size() > 1) {
    // The browser supplies one selected program with its complete ordered
    // dependency closure. A single native toggle must own the whole program;
    // importing a mastercode as an unrelated disabled entry would be broken.
    NeoCheat::Entry combined;
    combined.name = NeoUTF8(NeoField(programs.lastObject,@"name"));
    if (!NeoCheat::safeName(combined.name)) combined.name = "NeoStation";
    combined.type = entries.front().type;
    combined.encrypted = entries.front().encrypted;
    for (const auto& entry : entries) {
      if (entry.type != combined.type || entry.encrypted != combined.encrypted) return NeoCheatFailure(@"mixedFormat");
      combined.lines.insert(combined.lines.end(),entry.lines.begin(),entry.lines.end());
      combined.notes.insert(combined.notes.end(),entry.notes.begin(),entry.notes.end());
      if (!entry.creator.empty()) combined.notes.push_back("Author: " + entry.creator);
    }
    entries = {combined};
  }
  NSMutableDictionary* request = [snapshot mutableCopy];
  request[@"kind"] = @"import"; request[@"batchImport"] = @YES;
  request[@"name"] = @"NeoStation"; request[@"type"] = ps2 ? @"pnach" : @"ini";
  request[@"content"] = ps2 ? NeoEntriesPNACH(entries) : NeoEntriesINI(entries);
  request[@"filename"] = @""; request[@"success"] = @YES;
  // The importer uses this metadata only to preserve a provenance receipt.
  // It is not a setting and can never enable a program.
  request[@"unifiedProvenance"] = @{@"game":game, @"programs":programs};
  return request;
}

static NSError* NeoUnifiedNativeError(NSDictionary* result, NSString* locale) {
  if (![result isKindOfClass:NSDictionary.class]) result=NeoCheatFailure(@"invalidCode");
  if (![result[@"success"] isKindOfClass:NSNumber.class]) result=NeoCheatFailure(@"invalidCode");
  if ([result[@"success"] boolValue]) return nil;
  NSString* key = NeoField(result,@"errorKey");
  return [NSError errorWithDomain:@"NeoStation.UnifiedCheats.Native" code:1
      userInfo:@{NSLocalizedDescriptionKey:NeoCheatText(key.length ? key : @"invalidCode",locale)}];
}

static NSString* NeoUnifiedVariantName(NSString* original,NSUInteger ordinal) {
  if (ordinal==1) return original;
  NSString* suffix=[NSString stringWithFormat:@" (%lu)",(unsigned long)ordinal];
  NSString* base=original;
  while (base.length && [base lengthOfBytesUsingEncoding:NSUTF8StringEncoding]+[suffix lengthOfBytesUsingEncoding:NSUTF8StringEncoding]>160) {
    NSRange last=[base rangeOfComposedCharacterSequenceAtIndex:base.length-1];
    base=[base substringToIndex:last.location];
  }
  return [base stringByAppendingString:suffix];
}

// Resolve native name collisions without changing any original catalogue
// identity. An identical previously imported variant is found even when an
// earlier ordinal was deleted. Every different body receives a free ordinal.
static NSDictionary* NeoUnifiedResolveNativeName(NSString* root,NSDictionary* request,
                                                NSDictionary* snapshot,BOOL ps2) {
  if (![request isKindOfClass:NSDictionary.class] || !NeoUnifiedNativeSnapshotValid(snapshot,ps2)) return NeoCheatFailure(@"invalidCode");
  if (request[@"unifiedProvenance"] && ![request[@"unifiedProvenance"] isKindOfClass:NSDictionary.class]) return NeoCheatFailure(@"invalidCode");
  if (![request[@"unifiedProvenance"] isKindOfClass:NSDictionary.class]) return request;
  const auto parsed=NeoCheat::parse(NeoUTF8(NeoField(request,@"content")),ps2?"pnach":"ini","NeoStation");
  if (!parsed || parsed.entries.size()!=1) return NeoCheatFailure(@"invalidCode");
  NeoCheat::Entry entry=parsed.entries.front(); NSString* original=NeoString(entry.name);
  NSMutableSet<NSNumber*>* candidates=[NSMutableSet setWithObject:@1];
  NSMutableArray* names=[NSMutableArray array];
  if (ps2) {
    for (NSDictionary* item in snapshot[@"items"]) if ([item[@"cheat"] boolValue])
      [names addObject:NeoCheatDisplayName(NeoField(item,@"name"))];
  } else for (NSDictionary* item in snapshot[NeoString(entry.type)]) [names addObject:NeoField(item,@"name")];
  NSString* creatorSuffix=entry.type=="actionReplay" && !entry.creator.empty()
      ? [NSString stringWithFormat:@" [%@]",NeoString(entry.creator)] : @"";
  NSRegularExpression* suffix=[NSRegularExpression regularExpressionWithPattern:@" \\(([0-9]+)\\)$" options:0 error:nil];
  for (NSString* rawName in names) {
    NSString* name=rawName;
    if (creatorSuffix.length && [name hasSuffix:creatorSuffix]) name=[name substringToIndex:name.length-creatorSuffix.length];
    if ([name isEqual:original]) continue;
    NSTextCheckingResult* match=[suffix firstMatchInString:name options:0 range:NSMakeRange(0,name.length)];
    if (!match) continue;
    NSUInteger number=[[name substringWithRange:[match rangeAtIndex:1]] integerValue];
    if (number>=2 && number<=10000 && [name isEqual:NeoUnifiedVariantName(original,number)]) [candidates addObject:@(number)];
  }
  NSMutableSet<NSNumber*>* occupied=[NSMutableSet set];
  NeoCheat::Entry chosen=entry; BOOL identical=NO;
  for (NSNumber* candidate in [[candidates allObjects] sortedArrayUsingSelector:@selector(compare:)]) {
    entry.name=NeoUTF8(NeoUnifiedVariantName(original,candidate.unsignedIntegerValue));
    const auto selection=NeoSelectBatch(root,snapshot,ps2,{entry});
    if (selection.skipped==1) { chosen=entry; identical=YES; break; }
    if (selection.conflict) [occupied addObject:candidate];
  }
  if (!identical) {
    NSUInteger ordinal=1;
    while ([occupied containsObject:@(ordinal)] && ordinal<=10000) ++ordinal;
    if (ordinal>10000) return NeoCheatFailure(@"fileTooLarge");
    chosen.name=NeoUTF8(NeoUnifiedVariantName(original,ordinal));
  }
  NSMutableDictionary* renamed=[request mutableCopy];
  renamed[@"content"]=ps2 ? NeoEntriesPNACH({chosen}) : NeoEntriesINI({chosen});
  renamed[@"unifiedDisplayName"]=NeoString(chosen.name);
  return renamed;
}

// Keep the original structured source/author/licence information independently
// from PNACH/INI syntax. Re-importing the same selection is content-addressed.
static BOOL NeoUnifiedNativeReceipt(NSString* root, NSDictionary* request) {
  if (![request isKindOfClass:NSDictionary.class]) return NO;
  if (request[@"unifiedProvenance"] && ![request[@"unifiedProvenance"] isKindOfClass:NSDictionary.class]) return NO;
  NSDictionary* selection = [request[@"unifiedProvenance"] isKindOfClass:NSDictionary.class] ? request[@"unifiedProvenance"] : nil;
  if (!selection) return YES; // existing manual imports are unchanged.
  if (![selection[@"programs"] isKindOfClass:NSArray.class] || ![selection[@"game"] isKindOfClass:NSDictionary.class]) return NO;
  NSMutableArray* programs = [NSMutableArray array];
  for (NSDictionary* program in selection[@"programs"]) {
    if (![program isKindOfClass:NSDictionary.class] || ![program[@"id"] isKindOfClass:NSString.class] ||
        (program[@"provenance"] && ![program[@"provenance"] isKindOfClass:NSArray.class]) ||
        (program[@"dependencies"] && ![program[@"dependencies"] isKindOfClass:NSArray.class])) return NO;
    [programs addObject:@{@"id":NeoField(program,@"id"), @"name":NeoField(program,@"name"),
        @"dialect":NeoField(program,@"dialect"), @"provenance":program[@"provenance"] ?: @[],
        @"dependencies":program[@"dependencies"] ?: @[]}];
  }
  NSDictionary* receipt = @{@"schema_version":@1, @"kind":@"catalogue_selection",
      @"game":selection[@"game"] ?: @{}, @"programs":programs,
      @"native_name":NeoField(request,@"unifiedDisplayName")};
  if (![NSJSONSerialization isValidJSONObject:receipt]) return NO;
  NSData* data = [NSJSONSerialization dataWithJSONObject:receipt options:NSJSONWritingSortedKeys error:nil];
  if (!data.length || data.length > 4 * 1024 * 1024) return NO;
  unsigned char hash[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(data.bytes,(CC_LONG)data.length,hash);
  NSMutableString* name = [NSMutableString string];
  for (unsigned char byte : hash) [name appendFormat:@"%02x",byte];
  NSString* folder = [root stringByAppendingPathComponent:@"NeoStationCatalogueProvenance"];
  NSFileManager* fm = NSFileManager.defaultManager;
  if (![fm createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil]) return NO;
  return [data writeToFile:[folder stringByAppendingPathComponent:[name stringByAppendingString:@".json"]]
                  options:NSDataWritingAtomic error:nil];
}
