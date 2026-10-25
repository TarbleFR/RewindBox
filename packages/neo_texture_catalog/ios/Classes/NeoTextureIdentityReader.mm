// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoTextureIdentityReader.h"
#import "NeoTextureSupport.h"
#include "NeoTextureIdentity.h"

static NSString *CacheOverride;

static NSString *CachePath(void) {
  @synchronized([NeoTextureIdentityReader class]) {
    if (CacheOverride) return CacheOverride;
  }
  NSString *caches = NSSearchPathForDirectoriesInDomains(NSCachesDirectory, NSUserDomainMask, YES).firstObject ?: NSTemporaryDirectory();
  return [caches stringByAppendingPathComponent:@"NeoStation/Textures/identities.json"];
}

static NSString *Str(const std::string &value) { return [NSString stringWithUTF8String:value.c_str()] ?: @""; }

// One identifier per engine convention, with the scheme the catalogue matches on.
static NSDictionary *Identity(NSString *system, NSString *type, NSString *scheme, NSString *value, NSString *revision,
                              NSString *crc, NSString *region, NSString *title, NSString *path, NSString *format) {
  NSMutableDictionary *identity = [@{@"system": system, @"identities": @[@{@"type": type, @"scheme": scheme, @"value": value}]} mutableCopy];
  if (revision.length) identity[@"revision"] = revision;
  if (crc.length) identity[@"crc"] = crc;
  if (region.length) identity[@"regions"] = @[region];
  if (title.length) identity[@"title"] = title;
  if (path.length) identity[@"path"] = path;
  if (format.length) identity[@"format"] = format;
  return identity;
}

@implementation NeoTextureIdentityReader

+ (void)setCachePath:(NSString *)path {
  @synchronized(self) { CacheOverride = [path copy]; }
}

+ (NSDictionary *)identityWithSystem:(NSString *)system value:(NSString *)value revision:(NSString *)revision
                                 crc:(NSString *)crc title:(NSString *)title {
  NSString *s = NeoTexCanonicalSystem(system);
  NSString *v = value.uppercaseString ?: @"";
  if ([s isEqualToString:@"ps2"]) {
    NSString *region = Str(NeoTextureIdentity::PS2Region(std::string([[v stringByReplacingOccurrencesOfString:@"-" withString:@""] UTF8String] ?: "")));
    return Identity(s, @"serial", @"ps2-disc-serial", v, nil, crc.uppercaseString, region, title, nil, nil);
  }
  if ([s isEqualToString:@"gc"] || [s isEqualToString:@"wii"]) {
    NSString *region = @"";
    if (v.length == 6) {
      const unichar c = [v characterAtIndex:3];
      region = c == 'E' ? @"USA" : c == 'J' ? @"Japan" : c == 'K' ? @"Korea" : [@"PDFSIXYU" rangeOfString:[NSString stringWithCharacters:&c length:1]].location != NSNotFound ? @"Europe" : @"";
    }
    return Identity(s, @"game_id", @"dolphin-disc-game-id", v, revision, nil, region, title, nil, nil);
  }
  if ([s isEqualToString:@"psp"]) return Identity(s, @"disc_id", @"psp-param-sfo-disc-id", [v stringByReplacingOccurrencesOfString:@"-" withString:@""], revision, nil, nil, title, nil, nil);
  if ([s isEqualToString:@"n64"]) return Identity(s, @"rom_name", @"n64-rom-name-hex", v, revision, nil, nil, title, nil, nil);
  if ([s isEqualToString:@"ps1"]) {
    NSString *compact = [[v stringByReplacingOccurrencesOfString:@"-" withString:@""] stringByReplacingOccurrencesOfString:@"_" withString:@""];
    NSString *region = Str(NeoTextureIdentity::PS2Region(std::string(compact.UTF8String ?: "")));
    return Identity(s, @"serial", @"ps1-disc-serial", v, nil, nil, region, title, nil, nil);
  }
  if ([s isEqualToString:@"nes"]) return Identity(s, @"sha1", @"nes-rom-sha1", v, nil, nil, nil, title, nil, nil);
  return Identity(s, @"title_id", @"3ds-title-id", v, nil, nil, nil, title, nil, nil);
}

+ (NSDictionary *)identityForPath:(NSString *)path system:(NSString *)system title:(NSString *)title problem:(NSString **)problem {
  return [self identityForPath:path system:system title:title problem:problem quick:NO];
}

+ (NSDictionary *)quickIdentityForPath:(NSString *)path system:(NSString *)system title:(NSString *)title problem:(NSString **)problem {
  return [self identityForPath:path system:system title:title problem:problem quick:YES];
}

+ (NSDictionary *)identityForPath:(NSString *)path system:(NSString *)system title:(NSString *)title problem:(NSString **)problem
                            quick:(BOOL)quick {
  if (problem) *problem = nil;
  NSString *s = NeoTexCanonicalSystem(system);
  NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
  if (![attributes[NSFileType] isEqual:NSFileTypeRegular]) { if (problem) *problem = @"unreadable"; return nil; }
  const BOOL serialOnly = quick && [s isEqualToString:@"ps2"];
  NSString *key = [NSString stringWithFormat:@"%@%@|%@|%llu|%.0f", serialOnly ? @"q:" : @"", s, path, attributes.fileSize,
                                             attributes.fileModificationDate.timeIntervalSince1970];
  @synchronized(self) {
    NSDictionary *cached = NeoTexJSONDictionary(NeoTexReadBounded(CachePath(), 8 << 20))[@"entries"][key];
    if ([cached isKindOfClass:NSDictionary.class]) {
      if ([cached[@"problem"] isKindOfClass:NSString.class]) { if (problem) *problem = cached[@"problem"]; return nil; }
      NSMutableDictionary *identity = [cached mutableCopy];
      if (title.length) identity[@"title"] = title;
      identity[@"path"] = path;
      return identity;
    }
  }
  const std::string file = path.fileSystemRepresentation ?: "";
  NeoTextureIdentity::Result r;
  if ([s isEqualToString:@"ps2"]) r = NeoTextureIdentity::PS2(file, !serialOnly);
  else if ([s isEqualToString:@"gc"] || [s isEqualToString:@"wii"]) r = NeoTextureIdentity::Dolphin(file, std::string(s.UTF8String));
  else if ([s isEqualToString:@"psp"]) r = NeoTextureIdentity::PSP(file);
  else if ([s isEqualToString:@"3ds"]) r = NeoTextureIdentity::N3DS(file);
  else if ([s isEqualToString:@"n64"]) r = NeoTextureIdentity::N64(file);
  else if ([s isEqualToString:@"ps1"]) r = NeoTextureIdentity::PS1(file);
  else if ([s isEqualToString:@"nes"]) r = NeoTextureIdentity::NES(file);
  else { if (problem) *problem = @"unsupportedFormat"; return nil; }
  NSDictionary *identity = nil;
  NSDictionary *record = nil;
  if (r.ok()) {
    // PS2 folders and the store use SLUS-21050; PS1 the same form; Dolphin, PSP and 3DS the raw value.
    NSString *value = [s isEqualToString:@"ps2"] ? Str(r.folder) : Str(r.value);
    identity = Identity(s, Str(r.type), Str(r.scheme), value, Str(r.revision), Str(r.crc), Str(r.region), title, path, Str(r.format));
    // NES: the name of the file Mesen loads (HdPacks/<name>), part of what the file says.
    if ([s isEqualToString:@"nes"]) {
      NSMutableDictionary *named = [identity mutableCopy];
      named[@"content"] = Str(r.folder);
      identity = named;
    }
    NSMutableDictionary *stored = [identity mutableCopy];
    [stored removeObjectForKey:@"title"];
    [stored removeObjectForKey:@"path"];
    record = stored;
  } else {
    if (problem) *problem = Str(r.problem.empty() ? std::string("unreadable") : r.problem);
    // Unreadable is not cached: the file may be still downloading from iCloud.
    if (r.problem != "unreadable") record = @{@"problem": Str(r.problem)};
  }
  if (record) {
    @synchronized(self) {
      NSString *cache = CachePath();
      NSMutableDictionary *document = [NeoTexJSONDictionary(NeoTexReadBounded(cache, 8 << 20)) mutableCopy] ?: [NSMutableDictionary dictionary];
      NSMutableDictionary *entries = [document[@"entries"] isKindOfClass:NSDictionary.class] ? [document[@"entries"] mutableCopy] : [NSMutableDictionary dictionary];
      entries[key] = record;
      while (entries.count > 6000) [entries removeObjectForKey:[entries.allKeys sortedArrayUsingSelector:@selector(compare:)].firstObject];
      document[@"entries"] = entries;
      NeoTexWriteAtomic(NeoTexJSONData(document), cache, nil);
    }
  }
  return identity;
}

@end
