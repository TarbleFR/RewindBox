// SPDX-License-Identifier: GPL-3.0-or-later
// The four embedded engines' replacement-texture conventions, as read in
// their pinned sources (see docs/hd-textures-catalogue.md for the lines):
//
//  Dolphin (OatmealDome/dolphin-ios 7cac5416, VideoCommon/HiresTextures.cpp):
//    <User>/Load/Textures/<GameID>, else the region-free <GameID[0..3]>, plus
//    any top folder holding <GameID|ID3|all>.txt; tex1_*.png|dds. Switch:
//    [Video_Settings] HiresTextures in GameSettings/<GameID>[r<rev>].ini.
//  ARMSX2 (ARMSX2/ARMSX2 9d989ca9, GS/Renderers/HW/GSTextureReplacements.cpp):
//    <data>/textures/<SERIAL>/replacements, png|dds|astc|ktx, through the
//    ARMSX2 bridge's own store (Build 485): its importer, its per-game choice
//    given to ARMSX2Core before the first frame, its live switch in a game.
//  PPSSPP libretro: <memory stick = core save directory>/PSP/TEXTURES/<DISC_ID>,
//    textures.ini (+ PNG/DDS/ZIM or textures.zip). Switch: core option, per game.
//  Azahar libretro: <user>/load/textures/<program ID %016X>, png|dds|ktx and
//    an optional pack.json. Switch: core option, per game.
#import "Public/NeoTextureEngine.h"
#import "NeoTextureSupport.h"
#import "Public/NeoTextureIdentityReader.h"
#include "NeoTextureINI.h"
#include "NeoTextureInstall.h"
#include <sys/stat.h>
#import <objc/message.h>

static NSString *const kPPSSPPOption = @"ppsspp_texture_replacement";
static NSString *const kAzaharOption = @"citra_custom_textures";

NSString *NeoTextureINIValue(NSString *text, NSString *section, NSString *key) {
  const auto value = NeoTextureINI::Value(text.UTF8String ?: "", section.UTF8String, key.UTF8String);
  return value ? [NSString stringWithUTF8String:value->c_str()] : nil;
}

NSString *NeoTextureINISet(NSString *text, NSString *section, NSString *key, NSString *value) {
  const std::string updated = NeoTextureINI::Set(text.UTF8String ?: "", section.UTF8String, key.UTF8String, value.UTF8String);
  return [NSString stringWithUTF8String:updated.c_str()] ?: text;
}

static NSError *EngineError(NSString *key) {
  return [NSError errorWithDomain:@"NeoTextureEngine" code:1 userInfo:@{NSLocalizedDescriptionKey: key, @"key": key}];
}

static NSString *FirstIdentity(NSDictionary *identity, NSString *scheme) {
  for (NSDictionary *entry in [identity[@"identities"] isKindOfClass:NSArray.class] ? identity[@"identities"] : @[])
    if ([entry isKindOfClass:NSDictionary.class] && [NeoTexString(entry[@"scheme"]) isEqualToString:scheme]) {
      NSString *value = NeoTexString(entry[@"value"]);
      if (value.length) return value;
    }
  return nil;
}

static BOOL Matches(NSString *value, NSString *pattern) {
  return value.length && [value rangeOfString:pattern options:NSRegularExpressionSearch].location != NSNotFound;
}

static NSString *ExtensionOf(NSString *path) { return path.pathExtension.lowercaseString; }

/// Reads (bounded) an INI file below root, refusing links.
static NSString *ReadINI(NSString *root, NSString *path) {
  if (!NeoTexNoLinksBelow(root, path)) return nil;
  NSData *data = NeoTexReadBounded(path, 1 << 20);
  return data ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] : @"";
}

static BOOL WriteINI(NSString *root, NSString *path, NSString *text) {
  if (!NeoTexEnsureDirectory(root, path.stringByDeletingLastPathComponent)) return NO;
  struct stat st;
  if (lstat(path.fileSystemRepresentation, &st) == 0 && (!S_ISREG(st.st_mode) || st.st_size > (1 << 20))) return NO;
  return [text writeToFile:path atomically:YES encoding:NSUTF8StringEncoding error:nil];
}

static BOOL ParseBool(NSString *value, BOOL *result) {
  NSString *v = value.lowercaseString;
  if ([@[@"true", @"1", @"yes", @"on", @"enabled"] containsObject:v]) { *result = YES; return YES; }
  if ([@[@"false", @"0", @"no", @"off", @"disabled"] containsObject:v]) { *result = NO; return YES; }
  return NO;
}

#pragma mark - Dolphin

@interface NeoTextureDolphin : NSObject <NeoTextureEngine>
@property(nonatomic, copy) NSString *userDirectory;
@end
@implementation NeoTextureDolphin
- (NSString *)engineID { return @"dolphin"; }
- (NSString *)texturesRoot { return [self.userDirectory stringByAppendingPathComponent:@"Load/Textures"]; }
- (BOOL)supportsSystem:(NSString *)system {
  NSString *s = NeoTexCanonicalSystem(system);
  return [s isEqualToString:@"gc"] || [s isEqualToString:@"wii"];
}
- (NSString *)gameID:(NSDictionary *)identity {
  NSString *game = FirstIdentity(identity, @"dolphin-disc-game-id").uppercaseString;
  return Matches(game, @"^[A-Z0-9]{6}$") ? game : nil;
}
- (NSString *)folderForIdentity:(NSDictionary *)identity { return [self gameID:identity]; }
- (NSArray<NSString *> *)effectiveFoldersForIdentity:(NSDictionary *)identity {
  NSString *game = [self gameID:identity];
  if (!game) return @[];
  NSFileManager *fm = NSFileManager.defaultManager;
  NSMutableArray *folders = [NSMutableArray array];
  NSString *root = self.texturesRoot;
  NSString *family = [game substringToIndex:3];
  if ([fm fileExistsAtPath:[root stringByAppendingPathComponent:game]]) [folders addObject:game];
  else if ([fm fileExistsAtPath:[root stringByAppendingPathComponent:family]]) [folders addObject:family];
  // A <GameID|ID3|all>.txt anywhere in a top folder makes Dolphin read that
  // folder for the game. The usual places are checked in every folder; a
  // folder NeoStation installed for this game is searched in full.
  NSArray *children = [fm contentsOfDirectoryAtPath:root error:nil] ?: @[];
  NSSet *markers = [NSSet setWithObjects:[game stringByAppendingPathExtension:@"txt"], [family stringByAppendingPathExtension:@"txt"], @"all.txt", nil];
  for (NSString *child in [children sortedArrayUsingSelector:@selector(compare:)]) {
    if ([child hasPrefix:@"."] || [folders containsObject:child] || children.count > 4000) continue;
    NSString *folder = [root stringByAppendingPathComponent:child];
    BOOL found = NO;
    for (NSString *file in markers)
      if ([fm fileExistsAtPath:[folder stringByAppendingPathComponent:[@"gameids" stringByAppendingPathComponent:file]]] ||
          [fm fileExistsAtPath:[folder stringByAppendingPathComponent:file]]) { found = YES; break; }
    if (!found && [self installedFolder:folder lists:game family:family]) {
      NSUInteger visited = 0;
      for (NSString *path in [fm enumeratorAtPath:folder]) {
        if (++visited > 400000) break;
        if ([markers containsObject:path.lastPathComponent]) { found = YES; break; }
      }
    }
    if (found) [folders addObject:child];
  }
  return folders;
}
// The NeoStation manifest of a folder names the game (or its region-free ID).
- (BOOL)installedFolder:(NSString *)folder lists:(NSString *)game family:(NSString *)family {
  NSData *data = [NSData dataWithContentsOfFile:[folder stringByAppendingPathComponent:NeoTexManifestName]];
  NSDictionary *manifest = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
  if (![manifest isKindOfClass:NSDictionary.class]) return NO;
  for (NSString *key in @[@"sourceGameIds", @"games"]) {
    NSArray *ids = [manifest[key] isKindOfClass:NSArray.class] ? manifest[key] : @[];
    for (id value in ids)
      if ([value isKindOfClass:NSString.class] && ([[value uppercaseString] isEqualToString:game] || [[value uppercaseString] isEqualToString:family]))
        return YES;
  }
  return NO;
}
- (BOOL)acceptsFile:(NSString *)relativePath {
  return NeoTextureInstall::Accepts(NeoTextureInstall::Engine::dolphin, relativePath.UTF8String ?: "");
}
- (NSString *)problemWithStagedFolder:(NSString *)folder pack:(NSDictionary *)pack {
  // Game ID markers alone replace nothing: at least one tex1_ texture.
  return NeoTextureInstall::HasTextures(NeoTextureInstall::Engine::dolphin, folder.UTF8String ?: "") ? nil : @"noTextures";
}
- (NSString *)settingsFolder { return [self.userDirectory stringByAppendingPathComponent:@"GameSettings"]; }
- (NSDictionary *)activationForIdentity:(NSDictionary *)identity {
  NSString *game = [self gameID:identity];
  if (!game) return @{@"known": @NO, @"reason": @"noGameID", @"setting": @"HiresTextures"};
  NSString *revision = NeoTexString(identity[@"revision"]);
  // Dolphin layers GFX.ini, then <G>.ini, <GXX>.ini, <GXXXXX>.ini and <GXXXXX>r<rev>.ini.
  BOOL enabled = NO;
  NSString *gfx = ReadINI(self.userDirectory, [self.userDirectory stringByAppendingPathComponent:@"Config/GFX.ini"]);
  NSString *value = gfx ? NeoTextureINIValue(gfx, @"Settings", @"HiresTextures") : nil;
  if (value) ParseBool(value, &enabled);
  NSMutableArray *names = [NSMutableArray arrayWithObjects:[game substringToIndex:1], [game substringToIndex:3], game, nil];
  if (Matches(revision, @"^[0-9]{1,5}$")) [names addObject:[NSString stringWithFormat:@"%@r%@", game, revision]];
  NSString *file = nil;
  for (NSString *name in names) {
    NSString *path = [self.settingsFolder stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"ini"]];
    NSString *text = ReadINI(self.userDirectory, path);
    NSString *setting = text ? NeoTextureINIValue(text, @"Video_Settings", @"HiresTextures") : nil;
    if (setting && ParseBool(setting, &enabled)) file = name;
  }
  return @{@"known": @YES, @"enabled": @(enabled), @"scope": file ? @"game" : @"default", @"appliesAt": @"next-launch",
           @"setting": @"[Video_Settings] HiresTextures"};
}
- (BOOL)setActivation:(BOOL)enabled identity:(NSDictionary *)identity error:(NSError **)error {
  NSString *game = [self gameID:identity];
  if (!game) { if (error) *error = EngineError(@"noGameID"); return NO; }
  NSString *revision = NeoTexString(identity[@"revision"]);
  NSString *name = Matches(revision, @"^[0-9]{1,5}$") ? [NSString stringWithFormat:@"%@r%@", game, revision] : game;
  NSString *path = [self.settingsFolder stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"ini"]];
  NSString *text = ReadINI(self.userDirectory, path);
  if (!text) { if (error) *error = EngineError(@"writeFailed"); return NO; }
  text = NeoTextureINISet(text, @"Video_Settings", @"HiresTextures", enabled ? @"True" : @"False");
  // Loading a whole pack into RAM defeats the mobile memory budget.
  text = NeoTextureINISet(text, @"Video_Settings", @"CacheHiresTextures", @"False");
  if (!WriteINI(self.userDirectory, path, text)) { if (error) *error = EngineError(@"writeFailed"); return NO; }
  return YES;
}
@end

#pragma mark - ARMSX2 (the Build 485 store of the ARMSX2 bridge, reached at run time)

// PS2 pack files, NeoStation's per-game choice (inis/NeoStation-textures.json,
// given to ARMSX2Core before the first frame) and the installer that applies
// the engine's own path rules (TexturePackPaths) belong to the ARMSX2 bridge
// (packages/armsx2_internal_bridge, ARMSX2TexturePackStore, Build 485). This
// adapter drives that one system, through the Objective-C runtime so neither
// pod links the other: no second PS2 store, folder or switch exists.

static Class ARMSX2Store(void) { return NSClassFromString(@"ARMSX2TexturePackStore"); }
static Class ARMSX2Import(void) { return NSClassFromString(@"ARMSX2TextureImport"); }

static BOOL Responds(id target, NSString *selector) { return target && [target respondsToSelector:NSSelectorFromString(selector)]; }

static NSDictionary *StoreIdentify(NSString *gamePath, NSString *data) {
  SEL sel = NSSelectorFromString(@"identifyGameAtPath:dataPath:");
  if (!gamePath.length || !Responds(ARMSX2Store(), @"identifyGameAtPath:dataPath:")) return nil;
  id value = ((id (*)(id, SEL, id, id))objc_msgSend)(ARMSX2Store(), sel, gamePath, data);
  return [value isKindOfClass:NSDictionary.class] ? value : nil;
}

static NSDictionary *StoreStatus(NSString *serial, NSString *crc, NSString *data) {
  SEL sel = NSSelectorFromString(@"statusForSerial:crc:dataPath:");
  if (!serial.length || !Responds(ARMSX2Store(), @"statusForSerial:crc:dataPath:")) return nil;
  id value = ((id (*)(id, SEL, id, id, id))objc_msgSend)(ARMSX2Store(), sel, serial, crc.length == 8 ? crc : nil, data);
  return [value isKindOfClass:NSDictionary.class] ? value : nil;
}

static BOOL StoreSetEnabled(BOOL enabled, NSString *serial, NSString *data) {
  SEL sel = NSSelectorFromString(@"setEnabled:serial:dataPath:");
  if (!Responds(ARMSX2Store(), @"setEnabled:serial:dataPath:")) return NO;
  return ((BOOL (*)(id, SEL, BOOL, id, id))objc_msgSend)(ARMSX2Store(), sel, enabled, serial, data);
}

static NSDictionary *StoreRemove(NSString *serial, NSString *data) {
  SEL sel = NSSelectorFromString(@"removeSerial:dataPath:");
  if (!Responds(ARMSX2Store(), @"removeSerial:dataPath:")) return nil;
  id value = ((id (*)(id, SEL, id, id))objc_msgSend)(ARMSX2Store(), sel, serial, data);
  return [value isKindOfClass:NSDictionary.class] ? value : nil;
}

static void StoreDiscard(id path) {
  SEL sel = NSSelectorFromString(@"discardPath:");
  if ([path isKindOfClass:NSString.class] && [path length] && Responds(ARMSX2Store(), @"discardPath:"))
    ((void (*)(id, SEL, id))objc_msgSend)(ARMSX2Store(), sel, path);
}

// Waits for a host completion (delivered on the main queue): never on main.
static NSDictionary *Await(NSTimeInterval timeout, BOOL (^cancelled)(void), dispatch_block_t onCancel,
                           void (^start)(void (^done)(NSDictionary *))) {
  if (NSThread.isMainThread) return nil;
  __block NSDictionary *answer = nil;
  dispatch_semaphore_t signal = dispatch_semaphore_create(0);
  start(^(NSDictionary *value) {
    answer = [value isKindOfClass:NSDictionary.class] ? value : nil;
    dispatch_semaphore_signal(signal);
  });
  const CFAbsoluteTime deadline = CFAbsoluteTimeGetCurrent() + timeout;
  BOOL told = NO;
  while (dispatch_semaphore_wait(signal, dispatch_time(DISPATCH_TIME_NOW, 200 * NSEC_PER_MSEC)) != 0) {
    if (!told && cancelled && cancelled()) { told = YES; if (onCancel) onCancel(); }
    if (CFAbsoluteTimeGetCurrent() > deadline) return nil;
  }
  return answer;
}

static NSString *TextOf(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }

@interface NeoTextureARMSX2 : NSObject <NeoTextureEngine>
@property(nonatomic, copy) NSString *dataDirectory;
@property(nonatomic, copy) NSString *gamePath;
@property(nonatomic, strong) id host;  // ARMSX2TextureHost of the running game, nil in the library
@end

@implementation NeoTextureARMSX2
- (NSString *)engineID { return @"armsx2"; }
- (NSString *)texturesRoot { return [self.dataDirectory stringByAppendingPathComponent:@"textures"]; }
- (BOOL)supportsSystem:(NSString *)system { return [NeoTexCanonicalSystem(system) isEqualToString:@"ps2"]; }
- (BOOL)installsPacks { return ARMSX2Store() != nil && ARMSX2Import() != nil; }
+ (NSString *)serial:(NSDictionary *)identity {
  NSString *raw = FirstIdentity(identity, @"ps2-disc-serial").uppercaseString;
  NSString *compact = [[[raw stringByReplacingOccurrencesOfString:@"-" withString:@""]
                        stringByReplacingOccurrencesOfString:@"_" withString:@""] stringByReplacingOccurrencesOfString:@"." withString:@""];
  if (!Matches(compact, @"^[A-Z0-9]{4}[0-9]{5}$")) return nil;
  // CDVD.cpp: "SCES_123.45" becomes "SCES-12345", the store's folder form.
  return [NSString stringWithFormat:@"%@-%@", [compact substringToIndex:4], [compact substringFromIndex:4]];
}
- (NSString *)folderForIdentity:(NSDictionary *)identity {
  NSString *serial = [NeoTextureARMSX2 serial:identity];
  return serial ? [serial stringByAppendingPathComponent:@"replacements"] : nil;
}
- (NSArray<NSString *> *)effectiveFoldersForIdentity:(NSDictionary *)identity {
  NSString *folder = [self folderForIdentity:identity];
  BOOL directory = NO;
  return folder && [NSFileManager.defaultManager fileExistsAtPath:[self.texturesRoot stringByAppendingPathComponent:folder] isDirectory:&directory] && directory
      ? @[folder] : @[];
}
- (BOOL)acceptsFile:(NSString *)relativePath {
  return NeoTextureInstall::Accepts(NeoTextureInstall::Engine::armsx2, relativePath.UTF8String ?: "");
}
- (NSString *)problemWithStagedFolder:(NSString *)folder pack:(NSDictionary *)pack {
  for (NSString *path in [NSFileManager.defaultManager enumeratorAtPath:folder])
    if ([self acceptsFile:path]) return nil;
  return @"noTextures";
}
// ".neostation-expanded-" is the ARMSX2 store's own prefix: its leftover
// sweep removes such a folder if the app stops during an installation.
- (NSString *)expansionPrefix { return @".neostation-expanded-nt"; }
- (BOOL)readsArchiveFormat:(NSString *)format { return [@[@"zip", @"tar"] containsObject:format.lowercaseString]; }
- (BOOL)live { return self.host && Responds(self.host, @"textureLive") && ((BOOL (*)(id, SEL))objc_msgSend)(self.host, NSSelectorFromString(@"textureLive")); }

// What the running engine reports ({game, pack, engine}), in a game only.
- (NSDictionary *)hostState {
  if (!self.live || !Responds(self.host, @"textureReadState:")) return nil;
  id host = self.host;
  return Await(30, nil, nil, ^(void (^done)(NSDictionary *)) {
    ((void (*)(id, SEL, id))objc_msgSend)(host, NSSelectorFromString(@"textureReadState:"), done);
  });
}

// The game as the store's importer expects it: the identity the engine
// recorded at a boot, else the disc read by NeoStation.
- (NSDictionary *)gameFor:(NSDictionary *)identity {
  NSString *serial = [NeoTextureARMSX2 serial:identity] ?: @"";
  NSDictionary *recorded = StoreIdentify(self.gamePath ?: NeoTexString(identity[@"path"]), self.dataDirectory);
  if ([TextOf(recorded[@"serial"]) isEqualToString:serial] && [TextOf(recorded[@"source"]) isEqualToString:@"session"]) return recorded;
  NSString *crc = NeoTexString(identity[@"crc"]).uppercaseString;
  return @{@"serial": serial, @"crc": Matches(crc, @"^[0-9A-F]{8}$") ? crc : @"", @"version": NeoTexString(identity[@"version"]),
           @"title": NeoTexString(identity[@"title"]), @"source": serial.length ? @"disc" : @"none",
           @"region": TextOf(recorded[@"region"])};
}

- (NSDictionary *)activationForIdentity:(NSDictionary *)identity {
  NSString *serial = [NeoTextureARMSX2 serial:identity];
  NSString *setting = @"[EmuCore/GS] LoadTextureReplacements";
  if (!serial || !ARMSX2Store()) return @{@"known": @NO, @"reason": serial ? @"engineUnavailable" : @"noGameID", @"setting": setting};
  NSDictionary *engine = [self hostState][@"engine"];
  if ([engine[@"available"] boolValue] && [TextOf(engine[@"serial"]) isEqualToString:serial])
    return @{@"known": @YES, @"enabled": @([engine[@"effective"] boolValue]), @"scope": @"game", @"appliesAt": @"live", @"setting": setting};
  NSDictionary *status = StoreStatus(serial, NeoTexString(identity[@"crc"]).uppercaseString, self.dataDirectory);
  id choice = status[@"enabled"];
  id ini = status[@"iniEnabled"];
  BOOL enabled = [status[@"globalEnabled"] boolValue];
  NSString *scope = @"default";
  if ([ini isKindOfClass:NSNumber.class]) { enabled = [ini boolValue]; scope = @"game"; }
  // NeoStation's choice is given to the engine before the first frame and wins.
  if ([choice isKindOfClass:NSNumber.class]) { enabled = [choice boolValue]; scope = @"game"; }
  return @{@"known": @YES, @"enabled": @(enabled), @"scope": scope, @"appliesAt": @"next-launch", @"setting": setting};
}

- (BOOL)setActivation:(BOOL)enabled identity:(NSDictionary *)identity error:(NSError **)error {
  NSString *serial = [NeoTextureARMSX2 serial:identity];
  if (!serial) { if (error) *error = EngineError(@"noGameID"); return NO; }
  if (self.live && Responds(self.host, @"textureSetEnabled:completion:")) {
    id host = self.host;
    NSDictionary *answer = Await(30, nil, nil, ^(void (^done)(NSDictionary *)) {
      ((void (*)(id, SEL, BOOL, id))objc_msgSend)(host, NSSelectorFromString(@"textureSetEnabled:completion:"), enabled, done);
    });
    if ([answer[@"success"] boolValue]) return YES;
    if (error) *error = EngineError(TextOf(answer[@"error"]).length ? @"engineRefused" : @"writeFailed");
    return NO;
  }
  if (StoreSetEnabled(enabled, serial, self.dataDirectory)) return YES;
  if (error) *error = EngineError(@"writeFailed");
  return NO;
}

// The store's verdict, against what the catalogue already establishes.
static BOOL NeedsAsking(NSDictionary *inspection, NSDictionary *pack, BOOL confirmed) {
  if (confirmed || ![inspection[@"needsConfirmation"] boolValue]) return NO;
  // An exact catalogue match means the author lists this game: a pack folder
  // named after another serial of the same release is expected. Any other
  // doubt (region, executable CRC, serial taken from a file name) is asked.
  const BOOL exact = [pack[@"match"] isEqual:@"exact"];
  const BOOL otherDoubts = [inspection[@"regionConflict"] boolValue] || [inspection[@"crcConflict"] boolValue] ||
                           [inspection[@"uncertain"] boolValue];
  return !exact || otherDoubts;
}

static NSDictionary *Asking(NSDictionary *inspection) {
  NSMutableDictionary *answer = [@{@"success": @NO, @"needsConfirmation": @YES, @"error": @"confirmationRequired"} mutableCopy];
  for (NSString *key in @[@"match", @"packSerial", @"packRegion", @"gameSerial", @"gameRegion", @"regionConflict", @"crcConflict",
                          @"uncertain", @"replacing", @"files", @"bytes"])
    if (inspection[key]) answer[key] = inspection[key];
  return answer;
}

- (NSDictionary *)runImportFrom:(NSURL *)url expanded:(BOOL)expanded sourceName:(NSString *)sourceName pack:(NSDictionary *)pack
                       identity:(NSDictionary *)identity confirmed:(BOOL)confirmed
                       progress:(void (^)(double))progress cancelled:(BOOL (^)(void))cancelled {
  NSDictionary *game = [self gameFor:identity];
  if (!TextOf(game[@"serial"]).length) return @{@"success": @NO, @"error": @"noGameID"};
  void (^report)(double, NSString *) = ^(double fraction, NSString *phase) { if (progress && fraction >= 0) progress(fraction); };
  if (self.live) {
    // In a game the host also reloads the engine's texture index afterwards.
    id host = self.host;
    if (!Responds(host, @"textureInspectURL:progress:completion:") || !Responds(host, @"textureInstall:allowMismatch:progress:completion:"))
      return @{@"success": @NO, @"error": @"engineUnavailable"};
    NSDictionary *inspection = Await(6 * 3600, cancelled, ^{
      if (Responds(host, @"textureCancelInspection")) ((void (*)(id, SEL))objc_msgSend)(host, NSSelectorFromString(@"textureCancelInspection"));
    }, ^(void (^done)(NSDictionary *)) {
      ((void (*)(id, SEL, id, id, id))objc_msgSend)(host, NSSelectorFromString(@"textureInspectURL:progress:completion:"), url, report, done);
    });
    NSString *token = TextOf(inspection[@"token"]);
    void (^discard)(void) = ^{
      if (token.length && Responds(host, @"textureDiscard:")) ((void (*)(id, SEL, id))objc_msgSend)(host, NSSelectorFromString(@"textureDiscard:"), token);
    };
    if (![inspection[@"success"] boolValue]) { discard(); return inspection ?: @{@"success": @NO, @"error": @"failed"}; }
    if (NeedsAsking(inspection, pack, confirmed)) { discard(); return Asking(inspection); }
    NSDictionary *outcome = Await(6 * 3600, cancelled, ^{
      if (Responds(host, @"textureCancel:")) ((void (*)(id, SEL, id))objc_msgSend)(host, NSSelectorFromString(@"textureCancel:"), token);
    }, ^(void (^done)(NSDictionary *)) {
      ((void (*)(id, SEL, id, BOOL, id, id))objc_msgSend)(host, NSSelectorFromString(@"textureInstall:allowMismatch:progress:completion:"),
                                                       token, YES, report, done);
    });
    discard();
    return outcome ?: @{@"success": @NO, @"error": @"failed"};
  }
  Class importClass = ARMSX2Import();
  id import = nil;
  SEL moving = NSSelectorFromString(@"initWithExpandedFolder:sourceName:dataPath:game:");
  if (expanded && [importClass instancesRespondToSelector:moving])
    import = ((id (*)(id, SEL, id, id, id, id))objc_msgSend)([importClass alloc], moving, url.path, sourceName, self.dataDirectory, game);
  else
    import = ((id (*)(id, SEL, id, id, id, id))objc_msgSend)([importClass alloc], NSSelectorFromString(@"initWithURL:dataPath:game:expander:"),
                                                         url, self.dataDirectory, game, nil);
  if (!import) return @{@"success": @NO, @"error": @"engineUnavailable"};
  __block BOOL stop = NO;
  void (^watched)(double, NSString *) = ^(double fraction, NSString *phase) {
    report(fraction, phase);
    if (!stop && cancelled && cancelled()) { stop = YES; ((void (*)(id, SEL))objc_msgSend)(import, NSSelectorFromString(@"cancel")); }
  };
  NSDictionary *inspection = ((id (*)(id, SEL, id))objc_msgSend)(import, NSSelectorFromString(@"inspectWithProgress:"), watched);
  NSDictionary *outcome = nil;
  if (![inspection[@"success"] boolValue]) outcome = inspection ?: @{@"success": @NO, @"error": @"failed"};
  else if (NeedsAsking(inspection, pack, confirmed)) outcome = Asking(inspection);
  else {
    outcome = ((id (*)(id, SEL, BOOL, id))objc_msgSend)(import, NSSelectorFromString(@"installAllowingMismatch:progress:"), YES, watched);
    // No engine holds the previous files in the library: they go now.
    StoreDiscard(outcome[@"previousPath"]);
  }
  ((void (*)(id, SEL))objc_msgSend)(import, NSSelectorFromString(@"close"));
  return outcome ?: @{@"success": @NO, @"error": @"failed"};
}

- (NSDictionary *)installSource:(NSString *)source expanded:(BOOL)expanded pack:(NSDictionary *)pack identity:(NSDictionary *)identity
                      confirmed:(BOOL)confirmed progress:(void (^)(double))progress cancelled:(BOOL (^)(void))cancelled {
  // The archive's own name stays the pack's source name (serial and region hints).
  NSString *name = NeoTexString(pack[@"download"][@"file_name"]);
  if (!name.length) name = NeoTexString(pack[@"id"]);
  NSMutableDictionary *outcome = [[self runImportFrom:[NSURL fileURLWithPath:source isDirectory:expanded] expanded:expanded sourceName:name
                                                 pack:pack identity:identity confirmed:confirmed progress:progress cancelled:cancelled] mutableCopy];
  if ([outcome[@"success"] boolValue]) {
    NSString *serial = TextOf(outcome[@"serial"]).length ? outcome[@"serial"] : [NeoTextureARMSX2 serial:identity];
    NSDictionary *status = StoreStatus(serial, nil, self.dataDirectory);
    outcome[@"folder"] = [serial stringByAppendingPathComponent:@"replacements"];
    outcome[@"engine_stamp"] = TextOf(status[@"installedAt"]);
    // A first pack turns HD textures on for the game; a replacement keeps the choice.
    if (!outcome[@"enabled"]) outcome[@"enabled"] = @([status[@"enabled"] isKindOfClass:NSNumber.class] && [status[@"enabled"] boolValue]);
  }
  return outcome;
}

- (NSDictionary *)importURL:(NSURL *)url identity:(NSDictionary *)identity confirmed:(BOOL)confirmed
                   progress:(void (^)(double))progress cancelled:(BOOL (^)(void))cancelled {
  return [self runImportFrom:url expanded:NO sourceName:url.lastPathComponent ?: @"" pack:nil identity:identity confirmed:confirmed
                    progress:progress cancelled:cancelled];
}

- (NSDictionary *)installedRow:(NSString *)serial crc:(NSString *)crc {
  NSDictionary *status = StoreStatus(serial, crc, self.dataDirectory);
  if (![status[@"installed"] boolValue]) return nil;
  NSString *folder = [serial stringByAppendingPathComponent:@"replacements"];
  NSMutableDictionary *row = [@{@"folder": folder, @"files": status[@"files"] ?: @0, @"bytes": status[@"bytes"] ?: @0,
                                @"manual": @([status[@"external"] boolValue]), @"serial": serial,
                                @"title": TextOf(status[@"source"]).length ? status[@"source"] : folder} mutableCopy];
  if (status[@"installedAt"]) row[@"installed_at"] = status[@"installedAt"];
  // A catalogue pack is recognised only while the store's own installation
  // stamp is the one recorded when NeoStation installed it.
  NSDictionary *entry = NeoTexRegistryEntry(@"armsx2", folder);
  if (entry && [TextOf(entry[@"engine_stamp"]) isEqualToString:TextOf(status[@"installedAt"])] && TextOf(entry[@"engine_stamp"]).length) {
    for (NSString *key in @[@"pack_id", @"version", @"title", @"sha256", @"source"]) if (entry[key]) row[key] = entry[key];
  }
  return row;
}

- (NSArray<NSDictionary *> *)installedPacksForIdentity:(NSDictionary *)identity {
  NSString *serial = [NeoTextureARMSX2 serial:identity];
  NSDictionary *row = serial ? [self installedRow:serial crc:NeoTexString(identity[@"crc"]).uppercaseString] : nil;
  return row ? @[row] : @[];
}

- (NSArray<NSDictionary *> *)installedPacks {
  NSMutableArray *rows = [NSMutableArray array];
  NSArray *children = [[NSFileManager.defaultManager contentsOfDirectoryAtPath:self.texturesRoot error:nil] sortedArrayUsingSelector:@selector(compare:)];
  for (NSString *child in children) {
    if (rows.count >= 4000 || !Matches(child, @"^[A-Z0-9]{4}-[A-Z0-9]{5}$")) continue;
    NSDictionary *row = [self installedRow:child crc:nil];
    if (row) [rows addObject:row];
  }
  return rows;
}

- (NSDictionary *)removeInstalledPack:(NSDictionary *)installed {
  NSString *serial = TextOf(installed[@"serial"]);
  if (!Matches(serial, @"^[A-Z0-9]{4}-[A-Z0-9]{5}$")) return @{@"success": @NO, @"error": @"removeFailed"};
  NSDictionary *removal = nil;
  NSDictionary *engine = [self hostState][@"engine"];
  if ([TextOf(engine[@"serial"]) isEqualToString:serial] && Responds(self.host, @"textureRemove:")) {
    // The running game's own pack: the host turns the engine off and reloads first.
    id host = self.host;
    removal = Await(600, nil, nil, ^(void (^done)(NSDictionary *)) {
      ((void (*)(id, SEL, id))objc_msgSend)(host, NSSelectorFromString(@"textureRemove:"), done);
    });
  } else {
    removal = StoreRemove(serial, self.dataDirectory);
    StoreDiscard(removal[@"removingPath"]);
  }
  if ([removal[@"success"] boolValue]) NeoTexRegistrySet(@"armsx2", [serial stringByAppendingPathComponent:@"replacements"], nil);
  return removal ?: @{@"success": @NO, @"error": @"removeFailed"};
}

- (NSDictionary *)recordedIdentityForGamePath:(NSString *)path {
  NSDictionary *game = StoreIdentify(path, self.dataDirectory);
  NSString *serial = TextOf(game[@"serial"]);
  if (!Matches(serial, @"^[A-Z0-9]{4}-[A-Z0-9]{5}$")) return nil;
  NSMutableDictionary *identity = [[NeoTextureIdentityReader identityWithSystem:@"ps2" value:serial revision:nil crc:TextOf(game[@"crc"])
                                                                         title:TextOf(game[@"title"])] mutableCopy];
  identity[@"identity_source"] = TextOf(game[@"source"]);
  identity[@"path"] = path;
  if (TextOf(game[@"version"]).length) identity[@"version"] = game[@"version"];
  return identity;
}

- (id)detailsViewControllerWithLocale:(NSString *)locale {
  // The bridge's own page: what the engine recognised and loaded, its cache
  // and budget, and .tar.zst packs read by the engine's decoder.
  Class page = NSClassFromString(@"ARMSX2TexturePage");
  if (!self.live || !page) return nil;
  id controller = [page new];
  [controller setValue:locale forKey:@"localeIdentifier"];
  [controller setValue:self.host forKey:@"host"];
  return controller;
}
@end

#pragma mark - Libretro (PPSSPP, Azahar)

@interface NeoTextureLibretro : NSObject <NeoTextureEngine>
@property(nonatomic, copy) NSString *identifier, *coreLibrary, *optionKey, *root, *configDirectory;
@property(nonatomic, copy) NSString *_Nullable (^sessionReader)(NSString *key, NSString *gameKey);
@property(nonatomic, copy) BOOL (^sessionWriter)(NSString *key, NSString *value, NSString *gameKey);
@end
@implementation NeoTextureLibretro
- (NSString *)engineID { return self.identifier; }
- (NSString *)texturesRoot { return self.root; }
- (BOOL)supportsSystem:(NSString *)system {
  NSString *s = NeoTexCanonicalSystem(system);
  return [self.identifier isEqualToString:@"ppsspp"] ? [s isEqualToString:@"psp"] : [s isEqualToString:@"3ds"];
}
- (NSString *)folderForIdentity:(NSDictionary *)identity {
  if ([self.identifier isEqualToString:@"ppsspp"]) {
    NSString *disc = [FirstIdentity(identity, @"psp-param-sfo-disc-id").uppercaseString stringByReplacingOccurrencesOfString:@"-" withString:@""];
    return Matches(disc, @"^[A-Z]{4}[0-9]{5}$") ? disc : nil;
  }
  NSString *title = FirstIdentity(identity, @"3ds-title-id").uppercaseString;
  return Matches(title, @"^[0-9A-F]{16}$") ? title : nil;
}
- (NSArray<NSString *> *)effectiveFoldersForIdentity:(NSDictionary *)identity {
  NSString *folder = [self folderForIdentity:identity];
  BOOL directory = NO;
  return folder && [NSFileManager.defaultManager fileExistsAtPath:[self.root stringByAppendingPathComponent:folder] isDirectory:&directory] && directory
      ? @[folder] : @[];
}
- (BOOL)acceptsFile:(NSString *)relativePath {
  return NeoTextureInstall::Accepts([self.identifier isEqualToString:@"ppsspp"] ? NeoTextureInstall::Engine::ppsspp
                                                                              : NeoTextureInstall::Engine::azahar,
                                    relativePath.UTF8String ?: "");
}
- (NSString *)problemWithStagedFolder:(NSString *)folder pack:(NSDictionary *)pack {
  NSFileManager *fm = NSFileManager.defaultManager;
  if ([self.identifier isEqualToString:@"ppsspp"]) {
    // TextureReplacer reads textures.ini (or textures.zip) at the game folder's root.
    if (![fm fileExistsAtPath:[folder stringByAppendingPathComponent:@"textures.ini"]] &&
        ![fm fileExistsAtPath:[folder stringByAppendingPathComponent:@"textures.zip"]]) return @"missingIni";
    return NeoTextureInstall::HasTextures(NeoTextureInstall::Engine::ppsspp, folder.UTF8String ?: "") ? nil : @"noTextures";
  }
  return NeoTextureInstall::HasTextures(NeoTextureInstall::Engine::azahar, folder.UTF8String ?: "") ? nil : @"noTextures";
}
- (NSString *)gameStorePath { return [self.configDirectory stringByAppendingPathComponent:[NSString stringWithFormat:@"Games/%@.json", self.coreLibrary]]; }
- (NSString *)coreStorePath { return [self.configDirectory stringByAppendingPathComponent:[NSString stringWithFormat:@"%@.json", self.coreLibrary]]; }
- (NSDictionary *)activationForIdentity:(NSDictionary *)identity {
  NSString *gameKey = NeoTexString(identity[@"gameKey"]);
  if (!gameKey.length) return @{@"known": @NO, @"reason": @"noGameKey", @"setting": self.optionKey};
  NSString *value = self.sessionReader ? self.sessionReader(self.optionKey, gameKey) : nil;
  NSString *scope = value ? @"game" : @"default";
  if (!value) {
    NSDictionary *games = NeoTexJSONDictionary(NeoTexReadBounded(self.gameStorePath, 4 << 20))[@"games"];
    id entry = [games isKindOfClass:NSDictionary.class] ? games[gameKey] : nil;
    if ([entry isKindOfClass:NSDictionary.class] && [entry[self.optionKey] isKindOfClass:NSString.class]) { value = entry[self.optionKey]; scope = @"game"; }
  }
  if (!value) {
    NSDictionary *core = NeoTexJSONDictionary(NeoTexReadBounded(self.coreStorePath, 4 << 20))[@"values"];
    if ([core isKindOfClass:NSDictionary.class] && [core[self.optionKey] isKindOfClass:NSString.class]) value = core[self.optionKey];
  }
  // Both cores ship the option disabled by default.
  BOOL enabled = [value isEqualToString:@"enabled"];
  return @{@"known": @YES, @"enabled": @(enabled), @"scope": scope, @"appliesAt": @"next-launch", @"setting": self.optionKey};
}
- (BOOL)setActivation:(BOOL)enabled identity:(NSDictionary *)identity error:(NSError **)error {
  NSString *gameKey = NeoTexString(identity[@"gameKey"]);
  if (!gameKey.length || gameKey.length > 600) { if (error) *error = EngineError(@"noGameKey"); return NO; }
  NSString *value = enabled ? @"enabled" : @"disabled";
  // While this game runs, the session's option store owns its entry (and
  // rewrites it when the game closes): go through it.
  if (self.sessionWriter && self.sessionWriter(self.optionKey, value, gameKey)) return YES;
  @synchronized(NeoTextureLibretro.class) {
    NSMutableDictionary *document = [NeoTexJSONDictionary(NeoTexReadBounded(self.gameStorePath, 4 << 20)) mutableCopy] ?: [NSMutableDictionary dictionary];
    NSMutableDictionary *games = [document[@"games"] isKindOfClass:NSDictionary.class] ? [document[@"games"] mutableCopy] : [NSMutableDictionary dictionary];
    NSMutableDictionary *entry = [games[gameKey] isKindOfClass:NSDictionary.class] ? [games[gameKey] mutableCopy] : [NSMutableDictionary dictionary];
    entry[self.optionKey] = value;
    games[gameKey] = entry;
    document[@"games"] = games;
    document[@"version"] = @1;
    if (!NeoTexWriteAtomic(NeoTexJSONData(document), self.gameStorePath, nil)) { if (error) *error = EngineError(@"writeFailed"); return NO; }
  }
  return YES;
}
@end

@implementation NeoTextureEngines
+ (id<NeoTextureEngine>)dolphinWithUserDirectory:(NSString *)userDirectory {
  NeoTextureDolphin *engine = [NeoTextureDolphin new];
  engine.userDirectory = userDirectory.stringByStandardizingPath;
  return engine;
}
+ (id<NeoTextureEngine>)armsx2WithDataDirectory:(NSString *)dataDirectory gamePath:(NSString *)gamePath host:(id)host {
  NeoTextureARMSX2 *engine = [NeoTextureARMSX2 new];
  engine.dataDirectory = dataDirectory.stringByStandardizingPath;
  engine.gamePath = gamePath;
  engine.host = host;
  return engine;
}
+ (id<NeoTextureEngine>)ppssppWithSaveDirectory:(NSString *)saveDirectory configDirectory:(NSString *)configDirectory {
  NeoTextureLibretro *engine = [NeoTextureLibretro new];
  engine.identifier = @"ppsspp";
  engine.coreLibrary = @"PPSSPP";
  engine.optionKey = kPPSSPPOption;
  engine.root = [saveDirectory.stringByStandardizingPath stringByAppendingPathComponent:@"PSP/TEXTURES"];
  engine.configDirectory = configDirectory.stringByStandardizingPath;
  return engine;
}
+ (id<NeoTextureEngine>)azaharWithUserDirectory:(NSString *)userDirectory configDirectory:(NSString *)configDirectory {
  NeoTextureLibretro *engine = [NeoTextureLibretro new];
  engine.identifier = @"azahar";
  engine.coreLibrary = @"Azahar";
  engine.optionKey = kAzaharOption;
  engine.root = [userDirectory.stringByStandardizingPath stringByAppendingPathComponent:@"load/textures"];
  engine.configDirectory = configDirectory.stringByStandardizingPath;
  return engine;
}
+ (void)setLibretroSessionReader:(NSString * (^)(NSString *, NSString *))reader
                          writer:(BOOL (^)(NSString *, NSString *, NSString *))writer
                       forEngine:(id<NeoTextureEngine>)engine {
  if (![engine isKindOfClass:NeoTextureLibretro.class]) return;
  ((NeoTextureLibretro *)engine).sessionReader = reader;
  ((NeoTextureLibretro *)engine).sessionWriter = writer;
}
+ (NSString *)ppssppOptionKey { return kPPSSPPOption; }
+ (NSString *)azaharOptionKey { return kAzaharOption; }
@end
