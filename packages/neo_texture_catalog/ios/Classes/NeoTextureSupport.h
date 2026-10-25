// SPDX-License-Identifier: GPL-3.0-or-later
// Small helpers shared by the HD texture catalogue sources (not public).
#pragma once
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
#ifdef __cplusplus
extern "C" {
#endif

/// The manifest NeoStation writes in each pack folder it installed.
extern NSString *const NeoTexManifestName;

NSString *NeoTexString(id _Nullable value);
/// [A-Za-z0-9._-], 1...limit characters, not "." or "..".
BOOL NeoTexSafeToken(id _Nullable value, NSUInteger limit);
/// '/'-separated relative path of safe components (spaces, parentheses,
/// apostrophes and non-ASCII letters allowed; no control characters, '\\',
/// ':' or '..').
BOOL NeoTexSafeRelativePath(id _Nullable value, NSUInteger limit, NSUInteger components);
BOOL NeoTexHTTPS(id _Nullable value);
BOOL NeoTexSHA256(id _Nullable value);
BOOL NeoTexPositive(id _Nullable value, unsigned long long limit);
NSCharacterSet *NeoTexIdentityCharacters(void);
/// A manual pack's download.verified (the author's file on a file host, verified
/// on CI: format zip|7z, size, sha256, file_name), when well formed; nil otherwise.
NSDictionary *_Nullable NeoTexVerifiedFile(NSDictionary *_Nullable pack);
/// ps2->armsx2, gc/wii->dolphin, psp->ppsspp, 3ds->azahar, n64->mupen64plus, ps1->beetle, nes->mesen, else nil.
NSString *_Nullable NeoTexEngineForSystem(NSString *_Nullable system);
/// pspminis->psp, n3ds->3ds, gamecube->gc, lower case.
NSString *NeoTexCanonicalSystem(id _Nullable system);
/// The N64 ROM header name a catalogue identity writes in hexadecimal
/// (n64-rom-name-hex), when it is a usable folder name; nil otherwise.
NSString *_Nullable NeoTexN64RomName(NSString *_Nullable hex);
/// type|scheme -> set of upper-case values (PS2 serials without separators).
NSDictionary<NSString *, NSSet<NSString *> *> *NeoTexTypedIdentities(id _Nullable identities);
NSSet<NSString *> *NeoTexRegions(id _Nullable regions);
/// Lower case, no diacritics, punctuation or bracketed region tags.
NSString *NeoTexFoldTitle(id _Nullable title);

NSData *_Nullable NeoTexReadBounded(NSString *path, NSUInteger limit);
BOOL NeoTexWriteAtomic(NSData *_Nullable data, NSString *path, NSError **_Nullable error);
NSData *NeoTexJSONData(id object);
NSDictionary *_Nullable NeoTexJSONDictionary(NSData *_Nullable data);
/// Bounded HTTPS GET: status 200, HTTPS redirects only, no HTML body.
void NeoTexFetchData(NSURL *url, NSUInteger maximum, void (^completion)(NSData *_Nullable data, NSError *_Nullable error));
/// True when every component between root (inclusive) and path is a real
/// directory or the final regular file: no symbolic link anywhere.
BOOL NeoTexNoLinksBelow(NSString *root, NSString *path);
BOOL NeoTexEnsureDirectory(NSString *root, NSString *path);
unsigned long long NeoTexFreeBytes(NSString *path);
NSString *NeoTexFormatBytes(unsigned long long bytes);

/// Catalogue packs installed through an engine's own installer (ARMSX2),
/// whose folder carries that installer's manifest instead of NeoStation-pack.json:
/// Application Support/NeoStation/Textures/installed.json, keyed engine + folder.
/// An entry is trusted only while its "engine_stamp" (the installer's own
/// installation time) still matches the folder.
NSString *NeoTexRegistryPath(void);
void NeoTexSetRegistryPath(NSString *_Nullable path);
NSDictionary *_Nullable NeoTexRegistryEntry(NSString *engine, NSString *folder);
void NeoTexRegistrySet(NSString *engine, NSString *folder, NSDictionary *_Nullable entry);

#ifdef __cplusplus
}
#endif
NS_ASSUME_NONNULL_END
