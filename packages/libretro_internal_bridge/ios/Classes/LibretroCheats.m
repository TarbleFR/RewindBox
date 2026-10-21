#import "LibretroCheats.h"
#import "LibretroPicoCheatDecoder.h"
#import <CommonCrypto/CommonDigest.h>
#import <zlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <stdlib.h>
// Catalogue identity uses published MD5 hashes; it is not a security signature.
#pragma clang diagnostic ignored "-Wdeprecated-declarations"

static NSError *CheatError(NSString *message) {
  return [NSError errorWithDomain:@"NeoStation.Cheats" code:1 userInfo:@{NSLocalizedDescriptionKey: message}];
}
static BOOL Matches(NSString *text, NSString *pattern) {
  return [text rangeOfString:pattern options:NSRegularExpressionSearch].location != NSNotFound;
}
static NSString *Hex(const unsigned char *bytes, NSUInteger count) {
  NSMutableString *result = [NSMutableString stringWithCapacity:count * 2];
  for (NSUInteger i = 0; i < count; i++) [result appendFormat:@"%02x", bytes[i]];
  return result;
}
static NSString *String(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }
static NSArray<NSString *> *NativeBatches(NSArray<NSString *> *lines, NSUInteger maximumBytes) {
  NSMutableArray *result = [NSMutableArray array]; NSMutableString *batch = [NSMutableString string];
  for (NSString *line in lines) {
    if (line.length > maximumBytes) return nil;
    if (batch.length && batch.length + 1 + line.length > maximumBytes) {
      [result addObject:[batch copy]]; [batch setString:@""];
    }
    if (batch.length) [batch appendString:@"+"]; [batch appendString:line];
  }
  if (batch.length) [result addObject:[batch copy]];
  return result.count && result.count <= 99 ? result : nil;
}
static BOOL SameFileAttributes(NSDictionary *before, NSDictionary *after) {
  return before && after && [before[NSFileType] isEqual:after[NSFileType]] &&
    [before fileSize] == [after fileSize] && [before[NSFileModificationDate] isEqual:after[NSFileModificationDate]] &&
    [before[NSFileSystemFileNumber] isEqual:after[NSFileSystemFileNumber]];
}
static uint16_t LE16(const uint8_t *p) { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }
static uint32_t LE32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static uint32_t BE32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }
static uint64_t LE64(const uint8_t *p) { return LE32(p) | ((uint64_t)LE32(p + 4) << 32); }
static void AddIdentity(NSMutableArray *identities, NSString *type, NSString *value, NSString *scheme) {
  if (value.length) [identities addObject:@{@"type":type, @"value":value, @"scheme":scheme}];
}
static NSString *HeaderText(const uint8_t *p, NSUInteger length) {
  NSUInteger count = 0; while (count < length && p[count] >= 0x20 && p[count] <= 0x7e) count++;
  if (!count) return @"";
  return [[[NSString alloc] initWithBytes:p length:count encoding:NSASCIIStringEncoding]
    stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet] ?: @"";
}
// NES 2.0 sizes can use an exponent/multiplier. Reject invalid/oversized sizes
// before hashing; legacy canonical aliases below remain backwards compatible.
static uint64_t NESSize(uint8_t low, uint8_t high, uint64_t unit, BOOL nes2) {
  if (!nes2) return (uint64_t)low * unit;
  if (high != 15) return ((uint64_t)high * 256 + low) * unit;
  unsigned exponent = low >> 2; if (exponent >= 40) return UINT64_MAX;
  return (UINT64_C(1) << exponent) * ((low & 3) * 2 + 1);
}
// All reads are bounded by both the requested range and the actual file. This
// helper reads ISO9660 only, never the compressed bytes of CHD/CSO/PBP containers.
static NSData *ISOFile(NSString *path, NSArray<NSString *> *components, NSUInteger maximum) {
  if (![@[@"iso", @"bin", @"img"] containsObject:path.pathExtension.lowercaseString]) return nil;
  unsigned long long fileSize = [[NSFileManager.defaultManager attributesOfItemAtPath:path error:nil] fileSize];
  NSFileHandle *file = [NSFileHandle fileHandleForReadingAtPath:path]; if (!file) return nil;
  NSData *result = nil;
  @try {
    for (NSArray<NSNumber *> *layout in @[@[@2048,@0], @[@2352,@24], @[@2352,@16]]) {
      unsigned long long stride = layout[0].unsignedLongLongValue, header = layout[1].unsignedLongLongValue;
      for (NSNumber *pregap in @[@0,@150]) {
        unsigned long long start = pregap.unsignedLongLongValue * stride;
        if (start + 17 * stride + header > fileSize) continue;
        [file seekToFileOffset:start + 16 * stride + header]; NSData *pvd = [file readDataOfLength:2048]; const uint8_t *p = pvd.bytes;
        if (pvd.length != 2048 || p[0] != 1 || memcmp(p+1,"CD001",5) || p[6] != 1 || p[156] < 34) continue;
        uint32_t sector = LE32(p+158), size = LE32(p+166); BOOL found = YES;
        for (NSUInteger depth = 0; depth < components.count; depth++) {
          if (!sector || !size || size > 65536) { found = NO; break; }
          NSMutableData *directory = [NSMutableData data];
          for (uint32_t offset = 0; offset < size; offset += 2048) {
            unsigned long long at = start + ((unsigned long long)sector + offset/2048)*stride + header;
            NSUInteger count = MIN((uint32_t)2048, size-offset);
            if (at > fileSize || count > fileSize-at) break;
            [file seekToFileOffset:at]; NSData *part = [file readDataOfLength:count]; if (part.length != count) break;
            [directory appendData:part];
          }
          if (directory.length != size) { found = NO; break; }
          const uint8_t *d = directory.bytes; BOOL entry = NO;
          for (NSUInteger offset = 0; offset < directory.length;) {
            NSUInteger count = d[offset]; if (!count) { offset = (offset/2048+1)*2048; continue; }
            if (count < 34 || count > directory.length-offset || d[offset+32] > count-33) break;
            NSString *name = [[NSString alloc] initWithBytes:d+offset+33 length:d[offset+32] encoding:NSASCIIStringEncoding];
            name = [name componentsSeparatedByString:@";"].firstObject;
            if ([name.uppercaseString isEqual:components[depth].uppercaseString]) {
              BOOL isDirectory = (d[offset+25] & 2) != 0;
              if ((depth+1 < components.count) != isDirectory) break;
              sector = LE32(d+offset+2); size = LE32(d+offset+10); entry = YES; break;
            }
            offset += count;
          }
          if (!entry) { found = NO; break; }
        }
        if (!found || !sector || !size || size > maximum) continue;
        NSMutableData *data = [NSMutableData data];
        for (uint32_t offset = 0; offset < size; offset += 2048) {
          unsigned long long at = start + ((unsigned long long)sector + offset/2048)*stride + header;
          NSUInteger count = MIN((uint32_t)2048, size-offset);
          if (at > fileSize || count > fileSize-at) break;
          [file seekToFileOffset:at]; NSData *part = [file readDataOfLength:count]; if (part.length != count) break;
          [data appendData:part];
        }
        if (data.length == size) { result = data; break; }
      }
      if (result) break;
    }
  } @catch (NSException *__unused exception) { result = nil; }
  @finally { [file closeFile]; }
  return result;
}
static NSDictionary *SFOStrings(NSData *data) {
  if (data.length < 20 || data.length > 1024*1024) return @{};
  const uint8_t *p = data.bytes;
  if (memcmp(p,"\0PSF",4)) return @{};
  uint32_t keys = LE32(p+8), values = LE32(p+12), count = LE32(p+16);
  if (count > 256 || 20 + (uint64_t)count*16 > keys || keys >= values || values >= data.length) return @{};
  NSMutableDictionary *result = [NSMutableDictionary dictionary];
  for (uint32_t i = 0; i < count; i++) {
    const uint8_t *entry = p + 20 + i*16; uint64_t key = keys + (uint64_t)LE16(entry), value = values + (uint64_t)LE32(entry+12);
    uint32_t size = LE32(entry+4);
    if (key >= values || value >= data.length || !size || size > LE32(entry+8) || size > 256 || size > data.length-value || LE16(entry+2) != 0x0204) continue;
    const uint8_t *end = memchr(p+key,0,MIN((NSUInteger)64,(NSUInteger)(values-key)));
    if (!end || !memchr(p+value,0,size)) continue;
    NSString *name = [[NSString alloc] initWithBytes:p+key length:(NSUInteger)(end-(p+key)) encoding:NSASCIIStringEncoding];
    if (name && [@[@"DISC_ID",@"DISC_VERSION",@"TITLE_ID",@"APP_VER"] containsObject:name]) {
      if (result[name]) return @{}; // Ambiguous duplicate identity fields.
      result[name] = HeaderText(p+value,size);
    }
  }
  return result;
}

// FBNeo's native parser uses eight CPU slots, 512 addresses per choice and
// a fixed 8192-byte line buffer. Its libretro option API exposes <128 choices.
// Validate the native block again at the device boundary, independently of the
// remote catalogue's status. Never reinterpret its triples as libretro CHT.
static BOOL FBNumber(NSString *text, uint64_t maximum, uint64_t *value) {
  if (!Matches(text,@"^(?:0[xX][0-9a-fA-F]+|[0-9]+)$")) return NO;
  const char *input = text.UTF8String; char *end = NULL; errno = 0;
  unsigned long long number = strtoull(input,&end,0);
  if (errno || !end || *end || number > maximum) return NO;
  if (value) *value = number; return YES;
}
static NSString *FBDriver(NSDictionary *game) {
  if (![game isKindOfClass:NSDictionary.class]) return nil;
  if (![@"arcade" isEqual:String(game[@"system"])] && ![@"arcade" isEqual:String(game[@"console"])]) return nil;
  NSString *result = nil;
  for (id identity in [game[@"identities"] isKindOfClass:NSArray.class] ? game[@"identities"] : @[]) {
    if (![identity isKindOfClass:NSDictionary.class]) continue;
    if ([identity[@"type"] isEqual:@"romset"] && [identity[@"scheme"] isEqual:@"fbneo-driver-name"]) {
      NSString *driver = String(identity[@"value"]);
      if (!Matches(driver,@"^[a-zA-Z0-9_+-]{1,64}$") ||
          (result && [result caseInsensitiveCompare:driver] != NSOrderedSame)) return nil;
      result = driver;
    }
  }
  return result;
}
static NSString *FBBlock(NSDictionary *program) {
  if (![program isKindOfClass:NSDictionary.class] || ![program[@"dialect"] isEqual:@"fbneo-ini"] ||
      ![program[@"status"] isEqual:@"available"]) return nil;
  for (NSString *field in @[@"parameters",@"dependencies"]) {
    id values = program[field];
    if (values && (![values isKindOfClass:NSArray.class] || [values count])) return nil;
  }
  NSString *code = String(program[@"code"]);
  NSData *bytes = [code dataUsingEncoding:NSUTF8StringEncoding];
  if (!code.length || bytes.length > 1024*1024 || memchr(bytes.bytes,0,bytes.length)) return nil;
  NSRegularExpression *declaration = [NSRegularExpression regularExpressionWithPattern:@"^cheat\\s+\"(.*)\"$" options:0 error:nil];
  NSRegularExpression *choice = [NSRegularExpression regularExpressionWithPattern:@"^([0-9]{1,3})\\s+\"(.*)\"(?:\\s*,\\s*(.*))?$" options:0 error:nil];
  NSRegularExpression *defaults = [NSRegularExpression regularExpressionWithPattern:@"^default\\s+([0-9]{1,3})$" options:0 error:nil];
  NSMutableArray *lines = [NSMutableArray array]; NSMutableSet *indices = [NSMutableSet set];
  BOOL declared = NO, hasDefault = NO, hasWrites = NO; NSUInteger sourceDefault = 0;
  for (NSString *raw in [code componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
    NSString *line = [raw stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
    if (!line.length || [line hasPrefix:@"//"] || [line hasPrefix:@";"] || [line hasPrefix:@"#"]) continue;
    if ([line lengthOfBytesUsingEncoding:NSUTF8StringEncoding] >= 8192) return nil;
    NSTextCheckingResult *match = [declaration firstMatchInString:line options:0 range:NSMakeRange(0,line.length)];
    if (match) {
      if (declared || [[line substringWithRange:[match rangeAtIndex:1]] lengthOfBytesUsingEncoding:NSUTF8StringEncoding] > 126) return nil;
      declared = YES; [lines addObject:line]; continue;
    }
    if (!declared) return nil;
    match = [defaults firstMatchInString:line options:0 range:NSMakeRange(0,line.length)];
    if (match) {
      if (hasDefault) return nil; hasDefault = YES;
      uint64_t numericDefault;
      if (!FBNumber([line substringWithRange:[match rangeAtIndex:1]],126,&numericDefault)) return nil;
      sourceDefault = (NSUInteger)numericDefault;
      [lines addObject:@"default 0"]; continue;
    }
    match = [choice firstMatchInString:line options:0 range:NSMakeRange(0,line.length)];
    if (!match) return nil;
    uint64_t numericIndex;
    if (!FBNumber([line substringWithRange:[match rangeAtIndex:1]],126,&numericIndex)) return nil;
    NSUInteger index = (NSUInteger)numericIndex;
    NSString *name = [line substringWithRange:[match rangeAtIndex:2]];
    if (index >= 127 || [indices containsObject:@(index)] || [name lengthOfBytesUsingEncoding:NSUTF8StringEncoding] > 126) return nil;
    [indices addObject:@(index)]; NSRange valuesRange = [match rangeAtIndex:3];
    NSString *values = valuesRange.location == NSNotFound ? @"" : [line substringWithRange:valuesRange];
    NSArray *words = values.length ? [values componentsSeparatedByString:@","] : @[];
    if ((index == 0 && words.count) || (index != 0 && !words.count) || words.count % 3 || words.count > 512*3) return nil;
    for (NSUInteger i = 0; i < words.count; i+=3) {
      uint64_t address;
      if (!FBNumber([words[i] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet],7,NULL) ||
          !FBNumber([words[i+1] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet],UINT32_MAX,&address) || !address ||
          !FBNumber([words[i+2] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet],255,NULL)) return nil;
    }
    if (index && words.count) hasWrites = YES;
    [lines addObject:line];
  }
  if (!declared || !hasDefault || !hasWrites || ![indices containsObject:@(sourceDefault)] || indices.count < 2) return nil;
  for (NSUInteger i = 0; i < indices.count; i++) if (![indices containsObject:@(i)]) return nil;
  return [[lines componentsJoinedByString:@"\n"] stringByAppendingString:@"\n"];
}

@interface LibretroCheatXML : NSObject <NSXMLParserDelegate>
@property(nonatomic, strong) NSMutableArray<NSDictionary *> *games;
@property(nonatomic, strong) NSMutableDictionary *game;
@property(nonatomic, copy) NSString *console;
@property(nonatomic) NSUInteger depth;
@end
@implementation LibretroCheatXML
- (void)parser:(NSXMLParser *)parser didStartElement:(NSString *)element namespaceURI:(NSString *)uri
 qualifiedName:(NSString *)qualified attributes:(NSDictionary<NSString *, NSString *> *)attributes {
  if (++_depth > 16 || _games.count > 10000) { [parser abortParsing]; return; }
  if ([element isEqual:@"system"]) _console = [attributes[@"id"] componentsSeparatedByString:@"."].lastObject;
  if ([element isEqual:@"game"]) {
    if (String(attributes[@"title"]).length == 0 || String(_console).length == 0) { [parser abortParsing]; return; }
    _game = [@{@"title": attributes[@"title"], @"console": _console,
               @"md5s": [NSMutableArray array], @"cheats": [NSMutableArray array]} mutableCopy];
  }
  if ([element isEqual:@"hash"] && _game != nil) {
    NSString *md5 = [String(attributes[@"md5"]) lowercaseString];
    if (Matches(md5, @"^[a-f0-9]{32}$")) [_game[@"md5s"] addObject:md5];
  }
  if ([element isEqual:@"cheat"] && _game != nil) {
    NSString *code = String(attributes[@"code"]), *name = String(attributes[@"description"]);
    if (code.length > 65536 || name.length > 2048 || [_game[@"cheats"] count] >= 4096) { [parser abortParsing]; return; }
    if (code.length > 0) [_game[@"cheats"] addObject:@{@"name": name.length ? name : code, @"code": code,
      @"format": String(attributes[@"type"]), @"handler": @0, @"enabled": @NO}];
  }
}
- (void)parser:(NSXMLParser *)parser didEndElement:(NSString *)element namespaceURI:(NSString *)uri qualifiedName:(NSString *)qualified {
  if ([element isEqual:@"game"] && _game != nil) { [_games addObject:_game]; _game = nil; }
  if (_depth > 0) --_depth;
}
@end

@implementation LibretroCheats
+ (NSString *)digest:(NSData *)data {
  unsigned char digest[CC_SHA256_DIGEST_LENGTH]; CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
  return Hex(digest, sizeof(digest));
}
+ (NSString *)gitBlobSHA:(NSData *)data {
  CC_SHA1_CTX state; CC_SHA1_Init(&state);
  NSData *header = [[NSString stringWithFormat:@"blob %lu", (unsigned long)data.length] dataUsingEncoding:NSUTF8StringEncoding];
  CC_SHA1_Update(&state, header.bytes, (CC_LONG)header.length); const char zero = 0; CC_SHA1_Update(&state, &zero, 1);
  CC_SHA1_Update(&state, data.bytes, (CC_LONG)data.length);
  unsigned char digest[CC_SHA1_DIGEST_LENGTH]; CC_SHA1_Final(digest, &state); return Hex(digest, sizeof(digest));
}
+ (NSArray<NSDictionary *> *)parseCHT:(NSData *)data error:(NSError **)error {
  if (error != NULL) *error = nil;
  NSString *text = data.length <= 4u * 1024u * 1024u ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] : nil;
  if (text == nil) { if (error) *error = CheatError(@"Invalid UTF-8 or oversized CHT"); return nil; }
  if ([text hasPrefix:@"\uFEFF"]) text = [text substringFromIndex:1];
  NSMutableDictionary<NSString *, NSString *> *values = [NSMutableDictionary dictionary];
  for (NSString *raw in [text componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
    NSString *line = [raw stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
    if (line.length == 0 || [line hasPrefix:@"#"]) continue;
    NSRange equals = [line rangeOfString:@"="];
    if (equals.location == NSNotFound) continue;
    NSString *key = [[line substringToIndex:equals.location] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
    NSString *value = [[line substringFromIndex:equals.location + 1] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
    if ([value hasPrefix:@"\""]) {
      NSMutableString *decoded = [NSMutableString string]; BOOL escaped = NO, closed = NO;
      for (NSUInteger i = 1; i < value.length; i++) {
        unichar c = [value characterAtIndex:i];
        if (!escaped && c == '"') { closed = YES; break; }
        if (!escaped && c == '\\') { escaped = YES; continue; }
        [decoded appendFormat:@"%C", c]; escaped = NO;
      }
      if (!closed) { if (error) *error = CheatError(@"Unterminated CHT value"); return nil; }
      value = decoded;
    } else {
      value = [[[value componentsSeparatedByString:@"#"] firstObject] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
    }
    if (value.length > 65536 || values.count > 150000) { if (error) *error = CheatError(@"CHT limits exceeded"); return nil; }
    if (values[key] != nil) { if (error) *error = CheatError(@"Duplicate CHT field"); return nil; }
    values[key] = value;
  }
  NSString *countText = values[@"cheats"] ?: @"";
  if (!Matches(countText, @"^[0-9]{1,4}$") || countText.integerValue > 4096) {
    if (error) *error = CheatError(@"Invalid CHT cheat count"); return nil;
  }
  NSMutableDictionary<NSString *, NSMutableDictionary *> *groups = [NSMutableDictionary dictionary];
  for (NSString *key in values) {
    if (![key hasPrefix:@"cheat"]) continue;
    NSRange split = [key rangeOfString:@"_"];
    if (split.location == NSNotFound) continue;
    NSString *prefix = [key substringToIndex:split.location + 1];
    if (groups[prefix] == nil) groups[prefix] = [NSMutableDictionary dictionary];
    groups[prefix][[key substringFromIndex:split.location + 1]] = values[key];
  }
  NSMutableArray *result = [NSMutableArray array];
  for (NSInteger i = 0; i < countText.integerValue; i++) {
    NSString *prefix = [NSString stringWithFormat:@"cheat%ld_", (long)i];
    NSString *code = values[[prefix stringByAppendingString:@"code"]] ?: @"";
    NSString *name = values[[prefix stringByAppendingString:@"desc"]] ?: code;
    NSString *handler = values[[prefix stringByAppendingString:@"handler"]] ?: @"0";
    // Explicit empty code + description is a source's visual separator, not
    // a native program. Missing fields still reject an incomplete document.
    if ([handler isEqual:@"0"] && !code.length && name.length && values[[prefix stringByAppendingString:@"code"]] != nil) continue;
    if (!Matches(handler, @"^[01]$") || name.length == 0 || (code.length == 0 && [handler isEqual:@"0"])) {
      if (error) *error = CheatError(@"Missing CHT code, description or unsupported handler"); return nil;
    }
    NSDictionary *rawFields = groups[prefix] ?: @{};
    [result addObject:@{@"name": name, @"code": code, @"handler": @(handler.integerValue), @"enabled": @NO,
                       @"raw": rawFields}]; // `enable` from the source is deliberately ignored.
  }
  return result;
}
+ (NSArray<NSDictionary *> *)parseOpenEmu:(NSData *)data error:(NSError **)error {
  if (error) *error = nil;
  NSString *text = data.length <= 4u * 1024u * 1024u ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] : nil;
  if (text == nil || [text rangeOfString:@"<!DOCTYPE" options:NSCaseInsensitiveSearch].location != NSNotFound ||
      [text rangeOfString:@"<!ENTITY" options:NSCaseInsensitiveSearch].location != NSNotFound) {
    if (error) *error = CheatError(@"Oversized XML or disallowed entities"); return nil;
  }
  LibretroCheatXML *delegate = [LibretroCheatXML new]; delegate.games = [NSMutableArray array];
  NSXMLParser *parser = [[NSXMLParser alloc] initWithData:data]; parser.delegate = delegate;
  parser.shouldResolveExternalEntities = NO;
  if (![parser parse]) { if (error) *error = parser.parserError; return nil; }
  return delegate.games;
}
+ (NSArray<NSString *> *)supportedCoreIDs {
  // Explicitly audited native handlers, not just the presence of mandatory ABI symbols.
  return @[@"nestopia", @"snes9x", @"gambatte", @"mgba",
           @"genesis_plus_gx", @"genesis_plus_gx_wide", @"desmume", @"mednafen_psx_hw", @"mednafen_psx",
           @"ppsspp", @"mupen64plus_next", @"mednafen_pce_fast", @"mednafen_wswan", @"picodrive"];
}
+ (NSUInteger)maximumCodeBytesForCore:(NSString *)core {
  if ([core hasSuffix:@"_libretro"]) core = [core substringToIndex:core.length - 9];
  // DeSmuME frontend/libretro/libretro.cpp copies to ds_code[1024].
  // mGBA's existing bounded program adapter accepts 128 lines / 4096 bytes.
  if ([core isEqual:@"desmume"]) return 1023;
  if ([core isEqual:@"mgba"]) return 4096;
  // Delivered PPSSPP 1bd28b0 queues complete std::string programs; CWCheat
  // lines are kept together. Mupen has 256 token slots: 128 address/value pairs.
  if ([core isEqual:@"ppsspp"]) return 4096;
  if ([core isEqual:@"mupen64plus_next"]) return 1791;
  if ([core isEqual:@"mednafen_wswan"]) return 1023;
  return 255;
}
+ (NSArray<NSString *> *)codesForCheat:(NSDictionary *)cheat core:(NSString *)core console:(NSString *)console {
  if ([core hasSuffix:@"_libretro"]) core = [core substringToIndex:core.length - 9];
  id handler = cheat[@"handler"];
  if (handler != nil && ![handler isKindOfClass:NSNumber.class]) return nil;
  if (![[self supportedCoreIDs] containsObject:core] || [handler integerValue] != 0) return nil;
  NSString *code = [String(cheat[@"code"]) uppercaseString];
  if (code.length == 0 || code.length > 8192 || ![code canBeConvertedToEncoding:NSASCIIStringEncoding]) return nil;
  NSData *codeBytes = [code dataUsingEncoding:NSASCIIStringEncoding];
  if (memchr(codeBytes.bytes,0,codeBytes.length)) return nil;
  NSString *pattern = nil;
  BOOL gba = [core isEqual:@"mgba"] && [console isEqual:@"gba"];
  BOOL psp = [core isEqual:@"ppsspp"] && [console isEqual:@"psp"];
  BOOL n64 = [core isEqual:@"mupen64plus_next"] && [console isEqual:@"n64"];
  BOOL pico = [core isEqual:@"picodrive"] && [@[@"32x",@"pico",@"md",@"mcd"] containsObject:console];
  if (pico) {
    NSMutableArray *lines = [NSMutableArray array];
    for (NSString *line in [code componentsSeparatedByCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"+ \t\r\n"]]) {
      if (!line.length) continue;
      if (!NeoPicoMDTokenAllowed(line.UTF8String,![console isEqual:@"mcd"])) return nil;
      [lines addObject:line];
    }
    // Native calls append patches and execute only on the following frame.
    // Prevalidate everything, then preserve order across bounded ABI calls.
    return NativeBatches(lines,255);
  }
  BOOL pce = [core isEqual:@"mednafen_pce_fast"] && [@[@"pce",@"tg16",@"pccd",@"tgcd"] containsObject:console];
  BOOL ws = [core isEqual:@"mednafen_wswan"] && [@[@"ws",@"wsc"] containsObject:console];
  if (pce || ws) {
    NSMutableArray *lines = [NSMutableArray array];
    for (NSString *line in [code componentsSeparatedByCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"+ \t\r\n"]]) {
      if (!line.length) continue;
      if (!Matches(line,pce ? @"^[0-9A-F]{6}:[0-9A-F]{2}$" : @"^[0-9A-F]{1,8}:[0-9A-F]{2}$")) return nil;
      NSArray *parts = [line componentsSeparatedByString:@":"];
      uint64_t address = strtoull([parts[0] UTF8String],NULL,16);
      if (pce) {
        BOOL main = (address >= 0x1F0000 && address <= 0x1F1FFF) || (address >= 0xF82000 && address <= 0xF83FFF);
        BOOL cd = [@[@"pccd",@"tgcd"] containsObject:console] && address >= 0x0D0000 && address <= 0x10FFFF;
        if (!main && !cd) return nil;
        [lines addObject:line];
      } else {
        if (address > 0xFFFF) return nil;
        [lines addObject:[NSString stringWithFormat:@"%04llX:%@",(unsigned long long)address,parts[1]]];
      }
    }
    if (pce) return NativeBatches(lines,255);
    NSString *program = [lines componentsJoinedByString:@"+"];
    return lines.count && lines.count <= 128 && program.length <= [self maximumCodeBytesForCore:core] ? @[program] : nil;
  }
  if (psp || n64) {
    NSMutableArray *words = [NSMutableArray array], *lines = [NSMutableArray array];
    for (NSString *raw in [code componentsSeparatedByCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"+ ;,\t\r\n"]]) {
      if (!raw.length) continue;
      if (psp && [raw isEqual:@"_L"]) continue;
      [words addObject:[raw hasPrefix:@"0X"] ? [raw substringFromIndex:2] : raw];
    }
    for (NSUInteger i = 0; i < words.count; i++) {
      NSString *address = nil, *value = nil, *word = words[i];
      if (Matches(word, psp ? @"^[0-9A-F]{16}$" : @"^[0-9A-F]{12}$")) {
        address = [word substringToIndex:8]; value = [word substringFromIndex:8];
      } else if (Matches(word,@"^[0-9A-F]{8}$") && i+1 < words.count && Matches(words[i+1],psp ? @"^[0-9A-F]{8}$" : @"^[0-9A-F]{4}$")) {
        address = word; value = words[++i];
      }
      if (!address || (n64 && !Matches(address,@"^(?:80|81|A0|A1|D0|D1|D2|D3|50)[0-9A-F]{6}$"))) return nil;
      [lines addObject:[NSString stringWithFormat:@"%@ %@",address,value]];
    }
    if (!lines.count || lines.count > 128) return nil;
    // N64 conditions and slide codes require their following instruction.
    if (n64 && Matches(lines.lastObject,@"^(?:D[0-3]|50)")) return nil;
    NSString *program = [lines componentsJoinedByString:@"+"];
    return program.length <= [self maximumCodeBytesForCore:core] ? @[program] : nil;
  }
  if ([core isEqual:@"nestopia"] && [console isEqual:@"nes"])
    pattern = @"^(?:[APZLGITYEOXUKSVN]{6}|[APZLGITYEOXUKSVN]{8}|[0-9A-F]{8}|[0-9A-F]{4}:[0-9A-F]{2}|[0-9A-F]{4}\\?[0-9A-F]{2}:[0-9A-F]{2})$";
  if ([core isEqual:@"snes9x"] && [console isEqual:@"snes"])
    pattern = @"^(?:[0-9A-F]{8}|[0-9A-F]{6}:[0-9A-F]{2}|[0-9A-F]{4}-[0-9A-F]{4})$";
  if (([core isEqual:@"gambatte"] || [core isEqual:@"mgba"]) &&
      ([@[@"gb", @"gbc"] containsObject:console]))
    pattern = @"^(?:[0-9A-F]{8}|[0-9A-F]{3}-[0-9A-F]{3}(?:-[0-9A-F]{3})?)$";
  if ([core hasPrefix:@"genesis_plus_gx"] && [@[@"md", @"sms", @"gg", @"mcd"] containsObject:console])
    pattern = [console isEqual:@"md"] || [console isEqual:@"mcd"]
        ? @"^(?:[0-9ABCDEFGHJKLMNPRSTVWXYZ]{4}-[0-9ABCDEFGHJKLMNPRSTVWXYZ]{4}|[0-9A-F]{6}:[0-9A-F]{4})$"
        : @"^(?:[0-9A-F]{3}-[0-9A-F]{3}-[0-9A-F]{3}|[0-9A-F]{6}:[0-9A-F]{2})$";
  BOOL psx = [@[@"mednafen_psx_hw", @"mednafen_psx"] containsObject:core] && [console isEqual:@"psx"];
  BOOL ds = [core isEqual:@"desmume"] && [console isEqual:@"nds"];
  if (psx || ds) {
    NSMutableArray *words = [NSMutableArray array], *lines = [NSMutableArray array], *pairs = [NSMutableArray array];
    BOOL psxControl = NO;
    for (NSString *word in [code componentsSeparatedByCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"+ ;,\t\r\n"]])
      if (word.length) [words addObject:word];
    for (NSUInteger i = 0; i < words.count; i++) {
      NSString *word = words[i], *pair = nil;
      if (Matches(word, psx ? @"^[0-9A-F]{12}$" : @"^[0-9A-F]{16}$")) pair = word;
      else if (Matches(word, @"^[0-9A-F]{8}$") && i+1 < words.count &&
        Matches(words[i+1], psx ? @"^[0-9A-F]{4}$" : @"^[0-9A-F]{8}$")) pair = [word stringByAppendingString:words[++i]];
      if (!pair || (psx && !Matches(pair, @"^(?:30|80|D[0-3]|E[0-3]|50)[0-9A-F]{10}$"))) return nil;
      if (psx) {
        uint64_t value = strtoull([[pair substringFromIndex:8] UTF8String],NULL,16);
        if (([pair hasPrefix:@"30"] || [pair hasPrefix:@"E"]) && value > 255) return nil;
        if (![pair hasPrefix:@"30"] && ![pair hasPrefix:@"80"]) psxControl = YES;
        [pairs addObject:pair];
      }
      [lines addObject:[NSString stringWithFormat:@"%@ %@", [pair substringToIndex:8], [pair substringFromIndex:8]]];
    }
    NSString *program = [lines componentsJoinedByString:@"+"];
    // AR conditions must remain in one program. Never split or truncate a DS
    // program: the upstream entry point uses strcpy into ds_code[1024].
    if (ds) return lines.count && program.length <= [self maximumCodeBytesForCore:core] ? @[program] : nil;
    if (!lines.count) return nil;
    if (psxControl) {
      // Delivered Beetle 10e4b0c accumulates a condition/repeater in one
      // MemoryPatch until its next write. Never split this programme. Keep
      // only [one condition][one repeater]write groups, with byte fields
      // bounded exactly as the native decoder consumes them.
      NSUInteger pending = 0;
      for (NSString *pair in pairs) {
        if ([pair hasPrefix:@"30"] || [pair hasPrefix:@"80"]) { pending = 0; continue; }
        if ([pair hasPrefix:@"D"] || [pair hasPrefix:@"E"]) {
          if (pending) return nil;
          pending = 1; continue;
        }
        if (pending == 2 || ![pair hasPrefix:@"5000"] ||
            strtoull([[pair substringWithRange:NSMakeRange(4,2)] UTF8String],NULL,16) == 0 ||
            strtoull([[pair substringFromIndex:8] UTF8String],NULL,16) > 255) return nil;
        pending = 2;
      }
      if (pending) return nil;
      NSString *atomic = [pairs componentsJoinedByString:@"+"];
      return atomic.length <= [self maximumCodeBytesForCore:core] ? @[atomic] : nil;
    }
    if (program.length <= [self maximumCodeBytesForCore:core]) return @[program];
    // Only PSX 30/80 independent writes reach this branch. Beetle creates one
    // MemoryPatch per pair, so bounded contiguous batches preserve all effects
    // and their order without dropping the end of a long program.
    NSMutableArray *batches = [NSMutableArray array]; NSMutableString *batch = [NSMutableString string];
    for (NSString *line in lines) {
      if (batch.length && batch.length + 1 + line.length > [self maximumCodeBytesForCore:core]) {
        [batches addObject:[batch copy]]; [batch setString:@""];
      }
      if (batch.length) [batch appendString:@"+"];
      [batch appendString:line];
    }
    if (batch.length) [batches addObject:[batch copy]];
    return batches;
  }
  if (gba) {
    if ([String(cheat[@"dialect"]) isEqual:@"gba-vba-raw"]) {
      // mGBA 7a12d6d dispatches ':' to GBACheatAddVBALine before encrypted
      // formats. ROM words retain their source byte order. Canonical physical
      // RAM writes have explicit width and must stay inside the RAM bank.
      NSMutableArray *lines = [NSMutableArray array];
      for (NSString *line in [code componentsSeparatedByCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"+ \t\r\n"]]) {
        if (!line.length) continue;
        if (!Matches(line,@"^[0-9A-F]{8}:(?:[0-9A-F]{2}|[0-9A-F]{4}|[0-9A-F]{8})$")) return nil;
        uint64_t address = strtoull([[line substringToIndex:8] UTF8String],NULL,16);
        NSUInteger width = (line.length - 9) / 2;
        BOOL rom = width == 4 && address >= 0x08000000 && address <= 0x0DFFFFFF;
        uint64_t ramEnd = address >= 0x02000000 && address < 0x02040000 ? 0x02040000 :
          address >= 0x03000000 && address < 0x03008000 ? 0x03008000 : 0;
        BOOL ram = ramEnd && address + width <= ramEnd && address % width == 0;
        if (!rom && !ram) return nil;
        // The real libretro wrapper dispatches only 13/17-character records.
        // A byte VBA write is 11 characters: its two padding spaces must be
        // present before '+' and at the end of the final record as well.
        [lines addObject:width == 1 ? [line stringByAppendingString:@"  "] : line];
      }
      NSString *program = [lines componentsJoinedByString:@"+"];
      return lines.count && lines.count <= 128 && program.length <= 4096 ? @[program] : nil;
    }
    // OpenEmu writes concatenated address/value pairs; RetroArch CHT uses '+' separators.
    NSMutableArray *lines = [NSMutableArray array];
    NSArray *tokens = [code componentsSeparatedByCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"+ \t\r\n"]];
    NSMutableArray *words = [NSMutableArray array];
    for (NSString *token in tokens) if (token.length) [words addObject:token];
    for (NSUInteger i = 0; i < words.count; i++) {
      NSString *word = words[i], *line = nil;
      if (Matches(word, @"^[0-9A-F]{12}(?:[0-9A-F]{4})?$"))
        line = [NSString stringWithFormat:@"%@ %@", [word substringToIndex:8], [word substringFromIndex:8]];
      else if (Matches(word, @"^[0-9A-F]{8}$") && i + 1 < words.count && Matches(words[i + 1], @"^(?:[0-9A-F]{4}|[0-9A-F]{8})$"))
        line = [NSString stringWithFormat:@"%@ %@", word, words[++i]];
      if (line == nil) return nil;
      [lines addObject:line];
    }
    if (lines.count == 0 || lines.count > 128) return nil;
    // Keep each multi-line program intact: encrypted/conditional lines depend on ordering.
    NSString *program = [lines componentsJoinedByString:@"+"];
    return program.length <= 4096 ? @[program] : nil;
  }
  if (pattern == nil) return nil;
  NSMutableArray *result = [NSMutableArray array];
  for (NSString *part in [code componentsSeparatedByCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"+;, \r\n\t"]]) {
    if (part.length == 0) continue;
    if (!Matches(part, pattern)) return nil;
    [result addObject:part];
  }
  // Nestopia and Snes9x use 256-byte stack buffers. Each call receives one bounded code.
  return result.count > 0 && result.count <= 100 ? result : nil;
}
// A CUE describes tracks, not game bytes. Resolve its first binary track without
// accepting absolute paths, traversal or a different directory. CHD/playlists
// are deliberately left uncertain; their compressed/wrapper hash is not a ROM hash.
+ (NSString *)identityContentPath:(NSString *)path {
  if (![path.pathExtension.lowercaseString isEqual:@"cue"]) return path;
  NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
  if (!attributes || [attributes fileSize] > 1024u * 1024u) return path;
  NSString *cue = [NSString stringWithContentsOfFile:path encoding:NSUTF8StringEncoding error:nil];
  if (!cue) return path;
  NSRegularExpression *file = [NSRegularExpression regularExpressionWithPattern:@"^\\s*FILE\\s+(?:\"([^\"]+)\"|([^\\s]+))\\s+BINARY\\s*$"
    options:NSRegularExpressionCaseInsensitive | NSRegularExpressionAnchorsMatchLines error:nil];
  NSTextCheckingResult *match = [file firstMatchInString:cue options:0 range:NSMakeRange(0,cue.length)];
  if (!match) return path;
  NSRange capture = [match rangeAtIndex:1]; if (capture.location == NSNotFound) capture = [match rangeAtIndex:2];
  NSString *relative = [cue substringWithRange:capture];
  if (relative.isAbsolutePath || [relative.pathComponents containsObject:@".."] || [relative containsString:@"\\"]) return path;
  NSString *track = [path.stringByDeletingLastPathComponent stringByAppendingPathComponent:relative];
  NSDictionary *trackAttributes = [NSFileManager.defaultManager attributesOfItemAtPath:track error:nil];
  return [trackAttributes[NSFileType] isEqual:NSFileTypeRegular] ? track : path;
}
static uint32_t ISO32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
+ (NSString *)playStationSerialAtPath:(NSString *)path {
  path = [self identityContentPath:path];
  // Compressed containers require the core's CD reader. They use the library
  // title/manual version picker below, never a fabricated raw-disc identity.
  if (![@[@"bin", @"iso", @"img"] containsObject:path.pathExtension.lowercaseString]) return nil;
  NSFileHandle *file = [NSFileHandle fileHandleForReadingAtPath:path]; if (!file) return nil;
  NSString *serial = nil;
  @try {
    for (NSArray<NSNumber *> *layout in @[@[@2048,@0], @[@2352,@24], @[@2352,@16]]) {
      NSUInteger stride = layout[0].unsignedIntegerValue, header = layout[1].unsignedIntegerValue;
      for (NSNumber *pregap in @[@0,@150]) {
        unsigned long long start = pregap.unsignedLongLongValue * stride;
        [file seekToFileOffset:start + 16 * stride + header];
        NSData *pvd = [file readDataOfLength:2048]; const uint8_t *p = pvd.bytes;
        if (pvd.length != 2048 || p[0] != 1 || memcmp(p+1,"CD001",5) || p[6] != 1 || p[156] < 34) continue;
        uint32_t root = ISO32(p+158), length = ISO32(p+166);
        if (!root || !length || length > 65536) continue;
        NSMutableData *directory = [NSMutableData data];
        for (uint32_t offset = 0; offset < length; offset += 2048) {
          [file seekToFileOffset:start + ((unsigned long long)root + offset/2048)*stride + header];
          NSData *sector = [file readDataOfLength:MIN((uint32_t)2048,length-offset)];
          if (!sector.length) break; [directory appendData:sector];
        }
        const uint8_t *d = directory.bytes;
        for (NSUInteger offset = 0; offset < directory.length;) {
          NSUInteger count = d[offset];
          if (!count) { offset = (offset/2048+1)*2048; continue; }
          if (count < 34 || offset + count > directory.length || d[offset+32] > count-33) break;
          NSString *name = [[NSString alloc] initWithBytes:d+offset+33 length:d[offset+32] encoding:NSASCIIStringEncoding];
          if ([name.uppercaseString isEqual:@"SYSTEM.CNF;1"] || [name.uppercaseString isEqual:@"SYSTEM.CNF"]) {
            uint32_t sector = ISO32(d+offset+2), bytes = ISO32(d+offset+10);
            if (sector && bytes && bytes <= 2048 && !(d[offset+25]&2)) {
              [file seekToFileOffset:start + (unsigned long long)sector*stride + header];
              NSData *data = [file readDataOfLength:bytes];
              NSString *cnf = [[NSString alloc] initWithData:data encoding:NSASCIIStringEncoding];
              NSRegularExpression *boot = [NSRegularExpression regularExpressionWithPattern:@"(?im)^\\s*BOOT\\s*=\\s*cdrom:\\\\?([A-Z]{4})[_-]([0-9]{3})\\.?([0-9]{2})(?:;1)?\\s*$" options:0 error:nil];
              NSTextCheckingResult *match = cnf ? [boot firstMatchInString:cnf options:0 range:NSMakeRange(0,cnf.length)] : nil;
              if (match) serial = [NSString stringWithFormat:@"%@-%@%@", [[cnf substringWithRange:[match rangeAtIndex:1]] uppercaseString], [cnf substringWithRange:[match rangeAtIndex:2]], [cnf substringWithRange:[match rangeAtIndex:3]]];
            }
            break;
          }
          offset += count;
        }
        if (serial) break;
      }
      if (serial) break;
    }
  } @catch (NSException *__unused exception) { serial = nil; }
  @finally { [file closeFile]; }
  return serial;
}
// Raw content identifies preferences. Headerless/canonical aliases identify catalogues.
// The caller runs this once off-main and caches by file identity, size and mtime.
+ (NSDictionary *)identityAtPath:(NSString *)path console:(NSString *)console core:(NSString *)core {
  NSString *title = path.lastPathComponent.stringByDeletingPathExtension;
  path = [self identityContentPath:path];
  NSDictionary *before = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
  if (![before[NSFileType] isEqual:NSFileTypeRegular]) return nil;
  NSInputStream *stream = [NSInputStream inputStreamWithFileAtPath:path]; [stream open];
  CC_MD5_CTX md5, canonicalMD5, nesMD5; CC_SHA1_CTX sha1, canonicalSHA1, nesSHA1, prgSHA1; CC_SHA256_CTX sha, canonicalSHA;
  CC_MD5_Init(&md5); CC_SHA1_Init(&sha1); CC_SHA256_Init(&sha);
  CC_MD5_Init(&canonicalMD5); CC_SHA1_Init(&canonicalSHA1); CC_SHA256_Init(&canonicalSHA);
  CC_MD5_Init(&nesMD5); CC_SHA1_Init(&nesSHA1); CC_SHA1_Init(&prgSHA1);
  uint8_t buffer[65536]; NSInteger length; unsigned long long total = 0, skip = 0, prgSize = 0, nesSize = 0;
  uLong crc = crc32(0L, Z_NULL, 0), canonicalCRC = crc32(0L, Z_NULL, 0); NSUInteger swap = 0;
  NSMutableData *header = [NSMutableData data]; BOOL nes = NO, n64 = NO;
  while ((length = [stream read:buffer maxLength:sizeof(buffer)]) > 0) {
    CC_MD5_Update(&md5, buffer, (CC_LONG)length); CC_SHA1_Update(&sha1, buffer, (CC_LONG)length);
    CC_SHA256_Update(&sha, buffer, (CC_LONG)length); crc = crc32(crc, buffer, (uInt)length);
    if (total == 0) {
      if ([console isEqual:@"nes"] && length >= 16 && memcmp(buffer, "NES\x1a", 4) == 0) {
        skip = 16 + ((buffer[6] & 4) ? 512 : 0); BOOL nes2 = (buffer[7] & 12) == 8;
        prgSize = NESSize(buffer[4], buffer[9]&15, 16384, nes2);
        uint64_t chr = NESSize(buffer[5], buffer[9]>>4, 8192, nes2);
        nes = prgSize && prgSize != UINT64_MAX && chr != UINT64_MAX && prgSize <= [before fileSize] && chr <= [before fileSize]-prgSize && skip <= [before fileSize]-prgSize-chr;
        if (nes) nesSize = prgSize + chr;
      }
      if ([console isEqual:@"snes"] && ([before fileSize] & 0x7fff) == 512) skip = 512;
      if ([console isEqual:@"n64"] && length >= 64) {
        n64 = memcmp(buffer,"\x80\x37\x12\x40",4) == 0;
        if (memcmp(buffer, "\x37\x80\x40\x12", 4) == 0) { swap = 2; n64 = YES; }
        if (memcmp(buffer, "\x40\x12\x37\x80", 4) == 0) { swap = 4; n64 = YES; }
      }
    }
    NSUInteger offset = total < skip ? (NSUInteger)MIN(skip - total, (unsigned long long)length) : 0;
    if (swap) for (NSUInteger i = 0; i + swap <= (NSUInteger)length; i += swap)
      for (NSUInteger j = 0; j < swap / 2; j++) { uint8_t t = buffer[i+j]; buffer[i+j] = buffer[i+swap-1-j]; buffer[i+swap-1-j] = t; }
    if (header.length < 0x1000) [header appendBytes:buffer length:MIN((NSUInteger)length,0x1000-header.length)];
    CC_MD5_Update(&canonicalMD5, buffer + offset, (CC_LONG)(length - offset));
    CC_SHA1_Update(&canonicalSHA1, buffer + offset, (CC_LONG)(length - offset));
    CC_SHA256_Update(&canonicalSHA, buffer + offset, (CC_LONG)(length - offset));
    canonicalCRC = crc32(canonicalCRC,buffer+offset,(uInt)(length-offset));
    if (nes && total + (unsigned long long)length > skip && total < skip+nesSize) {
      NSUInteger begin = total < skip ? (NSUInteger)(skip-total) : 0;
      NSUInteger end = (NSUInteger)MIN((uint64_t)length,skip+nesSize-total);
      CC_MD5_Update(&nesMD5,buffer+begin,(CC_LONG)(end-begin)); CC_SHA1_Update(&nesSHA1,buffer+begin,(CC_LONG)(end-begin));
      if (total < skip+prgSize) {
        NSUInteger prgEnd = (NSUInteger)MIN((uint64_t)length,skip+prgSize-total);
        if (prgEnd > begin) CC_SHA1_Update(&prgSHA1,buffer+begin,(CC_LONG)(prgEnd-begin));
      }
    }
    total += length;
  }
  BOOL valid = length == 0 && stream.streamError == nil && total > skip; [stream close];
  NSDictionary *after = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
  if (!valid || !SameFileAttributes(before,after)) return nil;
  unsigned char m[16], s[32], h[20], cm[16], ch[20], cs[32], nm[16], nh[20], ph[20];
  CC_MD5_Final(m, &md5); CC_SHA1_Final(h, &sha1); CC_SHA256_Final(s, &sha);
  CC_MD5_Final(cm, &canonicalMD5); CC_SHA1_Final(ch, &canonicalSHA1); CC_SHA256_Final(cs,&canonicalSHA);
  CC_MD5_Final(nm,&nesMD5); CC_SHA1_Final(nh,&nesSHA1); CC_SHA1_Final(ph,&prgSHA1);
  NSString *serial = [console isEqual:@"psx"] ? ([self playStationSerialAtPath:path] ?: @"") : @"";
  NSMutableDictionary *result = [@{@"identitySchema":@2, @"console":console, @"core":core, @"title":title, @"serial":serial,
    @"md5":Hex(m,sizeof(m)), @"sha1":Hex(h,sizeof(h)), @"sha256":Hex(s,sizeof(s)),
    @"crc32":[NSString stringWithFormat:@"%08lx",(unsigned long)crc], @"bytes":@(total),
    @"md5s":[NSOrderedSet orderedSetWithArray:@[Hex(m,sizeof(m)),Hex(cm,sizeof(cm))]].array,
    @"sha1s":[NSOrderedSet orderedSetWithArray:@[Hex(h,sizeof(h)),Hex(ch,sizeof(ch))]].array} mutableCopy];
  NSMutableArray *identities = [NSMutableArray array]; result[@"identities"] = identities;
  // Preference identity always hashes the original bytes. A compressed container
  // hash is not an executable/ROM identity and must never match a rom-full feed.
  BOOL container = [@[@"zip",@"7z",@"chd",@"cso",@"pbp",@"m3u",@"cue",@"nsp",@"xci",@"cia"] containsObject:path.pathExtension.lowercaseString];
  NSString *scope = container ? @"container-file" : @"rom-full";
  AddIdentity(identities,@"md5",Hex(m,sizeof(m)),scope); AddIdentity(identities,@"sha1",Hex(h,sizeof(h)),scope);
  AddIdentity(identities,@"sha256",Hex(s,sizeof(s)),scope); AddIdentity(identities,@"crc32",result[@"crc32"],scope);
  if (nes) {
    AddIdentity(identities,@"md5",Hex(nm,sizeof(nm)),@"ines-prg-chr"); AddIdentity(identities,@"sha1",Hex(nh,sizeof(nh)),@"ines-prg-chr");
    AddIdentity(identities,@"sha1",Hex(ph,sizeof(ph)),@"nes-prg");
  }
  if ([console isEqual:@"snes"] && !container) {
    AddIdentity(identities,@"md5",Hex(cm,sizeof(cm)),@"snes-headerless"); AddIdentity(identities,@"sha1",Hex(ch,sizeof(ch)),@"snes-headerless");
    AddIdentity(identities,@"sha256",Hex(cs,sizeof(cs)),@"bsnes-cartridge");
  }
  if (serial.length) AddIdentity(identities,@"serial",serial,@"ps1-disc-serial");
  const uint8_t *p = header.bytes;
  if ([console isEqual:@"nds"] && header.length >= 512 && Matches(HeaderText(p+12,4),@"^[A-Z0-9]{4}$")) {
    NSString *code = HeaderText(p+12,4), *r4 = [NSString stringWithFormat:@"%08X",(uint32_t)~crc32(0L,p,512)];
    result[@"ndsGameCode"] = code; result[@"ndsR4CRC32"] = r4; result[@"gameRevision"] = @(p[0x1e]);
    AddIdentity(identities,@"ds_game_code",code,@"nds-header-gamecode");
    AddIdentity(identities,@"ds_crc",r4,@"r4-header512-crc32-inverted");
  }
  if (n64 && header.length >= 64 && total % 4 == 0) {
    NSString *crc1 = [NSString stringWithFormat:@"%08X",BE32(p+0x10)], *crc2 = [NSString stringWithFormat:@"%08X",BE32(p+0x14)];
    result[@"n64CRC1"] = crc1; result[@"n64CRC2"] = crc2; result[@"n64Country"] = @(p[0x3e]); result[@"gameRevision"] = @(p[0x3f]);
    AddIdentity(identities,@"md5",Hex(cm,sizeof(cm)),@"n64-big-endian"); AddIdentity(identities,@"sha1",Hex(ch,sizeof(ch)),@"n64-big-endian");
    AddIdentity(identities,@"crc32",[NSString stringWithFormat:@"%08lx",(unsigned long)canonicalCRC],@"n64-big-endian");
    AddIdentity(identities,@"n64_header",[NSString stringWithFormat:@"%@-%@-C:%02X",crc1,crc2,p[0x3e]],@"n64-crc1-crc2-country");
  }
  if ([@[@"gb",@"gbc"] containsObject:console] && header.length >= 0x150) result[@"gameRevision"] = @(p[0x14c]);
  if ([console isEqual:@"gba"] && header.length >= 0xc0 && Matches(HeaderText(p+0xac,4),@"^[A-Z0-9]{4}$")) {
    result[@"gbaGameCode"] = HeaderText(p+0xac,4); result[@"gameRevision"] = @(p[0xbc]);
  }
  if ([console isEqual:@"psp"]) {
    NSData *sfo = ISOFile(path,@[@"PSP_GAME",@"PARAM.SFO"],1024*1024);
    if ([path.pathExtension.lowercaseString isEqual:@"pbp"] && header.length >= 40 && memcmp(p,"\0PBP",4) == 0) {
      uint32_t begin = LE32(p+8), end = LE32(p+12);
      if (begin >= 40 && end > begin && end <= total && end-begin <= 1024*1024) {
        NSFileHandle *file = [NSFileHandle fileHandleForReadingAtPath:path];
        @try { [file seekToFileOffset:begin]; sfo = [file readDataOfLength:end-begin]; }
        @catch (NSException *__unused exception) { sfo = nil; } @finally { [file closeFile]; }
      }
    }
    NSDictionary *fields = SFOStrings(sfo); NSString *gameID = [String(fields[@"DISC_ID"]) stringByReplacingOccurrencesOfString:@"-" withString:@""].uppercaseString;
    if (Matches(gameID,@"^[A-Z]{4}[0-9]{5}$")) {
      result[@"pspGameID"] = gameID; AddIdentity(identities,@"game_id",gameID,@"psp-param-sfo-disc-id");
      if (String(fields[@"DISC_VERSION"]).length) result[@"pspDiscVersion"] = fields[@"DISC_VERSION"];
    }
  }
  if ([console isEqual:@"3ds"] && header.length >= 0x200) {
    uint64_t ncch = memcmp(p+0x100,"NCCH",4) == 0 ? 0 : UINT64_MAX;
    if (memcmp(p+0x100,"NCSD",4) == 0) ncch = (uint64_t)LE32(p+0x120)*512;
    NSData *ncchHeader = nil;
    if (ncch != UINT64_MAX && ncch <= total && total-ncch >= 0x200) {
      if (!ncch) ncchHeader = header;
      else { NSFileHandle *file = [NSFileHandle fileHandleForReadingAtPath:path];
        @try { [file seekToFileOffset:ncch]; ncchHeader = [file readDataOfLength:0x200]; }
        @catch (NSException *__unused exception) {} @finally { [file closeFile]; } }
    }
    const uint8_t *n = ncchHeader.bytes;
    if (ncchHeader.length >= 0x200 && memcmp(n+0x100,"NCCH",4) == 0 && LE64(n+0x118)) {
      NSString *titleID = [NSString stringWithFormat:@"%016llX",(unsigned long long)LE64(n+0x118)];
      result[@"titleID"] = titleID; AddIdentity(identities,@"title_id",titleID,@"3ds-title-id");
    }
  }
  // Header/SFO reads must be from the same unchanged content as the hash pass.
  after = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
  if (!SameFileAttributes(before,after)) return nil;
  return result;
}
+ (BOOL)canInstallFBNeoPrograms:(NSArray<NSDictionary *> *)programs game:(NSDictionary *)game {
  // A source INI block already contains all writes/choices. Multi-block
  // master/child dependency closures cannot become independent native toggles.
  if (![programs isKindOfClass:NSArray.class] || !FBDriver(game) || programs.count != 1) return NO;
  for (id program in programs) if (!FBBlock(program)) return NO;
  return YES;
}
+ (NSDictionary *)installFBNeoPrograms:(NSArray<NSDictionary *> *)programs game:(NSDictionary *)game
                      systemDirectory:(NSString *)directory error:(NSError **)error {
  if (error) *error = nil;
  if (![self canInstallFBNeoPrograms:programs game:game] || !directory.isAbsolutePath) {
    if (error) *error = CheatError(@"Unsupported FBNeo native program or missing driver identity"); return nil;
  }
  NSString *driver = FBDriver(game), *folder = [directory stringByAppendingPathComponent:@"NeoStationFBNeo/fbneo/cheats"];
  NSString *file = [folder stringByAppendingPathComponent:[driver stringByAppendingPathExtension:@"ini"]];
  NSString *receipt = [[folder stringByAppendingPathComponent:@"NeoStationManaged"] stringByAppendingPathComponent:[driver stringByAppendingPathExtension:@"json"]];
  NSFileManager *files = NSFileManager.defaultManager;
  NSDictionary *attributes = [files attributesOfItemAtPath:file error:nil];
  NSData *existing = attributes && [attributes fileSize] <= 4*1024*1024 ? [NSData dataWithContentsOfFile:file] : nil;
  NSDictionary *receiptAttributes = [files attributesOfItemAtPath:receipt error:nil];
  NSData *receiptData = receiptAttributes && [receiptAttributes fileSize] <= 12*1024*1024 ? [NSData dataWithContentsOfFile:receipt] : nil;
  id previous = receiptData ? [NSJSONSerialization JSONObjectWithData:receiptData options:0 error:nil] : nil;
  BOOL owned = [previous isKindOfClass:NSDictionary.class] && [previous[@"schema"] isEqual:@1] &&
    [previous[@"driver"] isEqual:driver] && existing && [previous[@"sha256"] isEqual:[self digest:existing]];
  if (attributes && (!owned || ![attributes[NSFileType] isEqual:NSFileTypeRegular])) {
    if (error) *error = CheatError(@"An existing personal or modified FBNeo cheat file was preserved"); return nil;
  }
  NSMutableDictionary *merged = [NSMutableDictionary dictionary];
  if (owned && [previous[@"programs"] isKindOfClass:NSArray.class]) for (NSDictionary *program in previous[@"programs"]) {
    NSString *block = FBBlock(program); if (block) merged[[self digest:[block dataUsingEncoding:NSUTF8StringEncoding]]] = program;
  }
  for (NSDictionary *program in programs) {
    NSString *block = FBBlock(program); merged[[self digest:[block dataUsingEncoding:NSUTF8StringEncoding]]] = program;
  }
  if (merged.count > 4096) { if (error) *error = CheatError(@"FBNeo managed programme limit exceeded"); return nil; }
  NSMutableString *text = [NSMutableString stringWithString:@"// RewindBox managed native cheats; activation is session-only.\n"];
  NSMutableArray *records = [NSMutableArray array];
  for (NSString *key in [merged.allKeys sortedArrayUsingSelector:@selector(compare:)]) {
    NSDictionary *program = merged[key]; [text appendString:FBBlock(program)]; [text appendString:@"\n"]; [records addObject:program];
  }
  NSData *data = [text dataUsingEncoding:NSUTF8StringEncoding];
  if (data.length > 4*1024*1024) { if (error) *error = CheatError(@"FBNeo native file exceeds size limit"); return nil; }
  NSDictionary *next = @{@"schema":@1,@"driver":driver,@"sha256":[self digest:data],@"programs":records};
  NSData *nextReceipt = [NSJSONSerialization dataWithJSONObject:next options:NSJSONWritingSortedKeys error:error];
  if (!nextReceipt || nextReceipt.length > 12*1024*1024) { if (error && !*error) *error = CheatError(@"FBNeo provenance exceeds size limit"); return nil; }
  BOOL changed = ![data isEqual:existing];
  if (![files createDirectoryAtPath:receipt.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:error]) return nil;
  // The UI serialises imports on the emulation queue. Never overwrite a file
  // that appeared or changed since the ownership check above.
  NSDictionary *current = [files attributesOfItemAtPath:file error:nil];
  if ((attributes && !SameFileAttributes(attributes,current)) || (!attributes && current)) {
    if (error) *error = CheatError(@"FBNeo cheat file changed during installation"); return nil;
  }
  if (changed && ![data writeToFile:file options:NSDataWritingAtomic error:error]) return nil;
  if (![nextReceipt writeToFile:receipt options:NSDataWritingAtomic error:error]) {
    NSData *written = [NSData dataWithContentsOfFile:file];
    if (changed && [written isEqual:data]) {
      if (existing) [existing writeToFile:file options:NSDataWritingAtomic error:nil];
      else [files removeItemAtPath:file error:nil];
    }
    return nil;
  }
  return @{@"driver":driver,@"imported_path":file,@"changed":@(changed),@"restart_required":@(changed),@"imported":@(programs.count)};
}
+ (NSDictionary *)stageManagedFBNeoDriver:(NSString *)driver systemDirectory:(NSString *)directory
                             destination:(NSString *)destination error:(NSError **)error {
  if (error) *error = nil;
  if (!Matches(driver,@"^[a-zA-Z0-9_+-]{1,64}$") || !directory.isAbsolutePath || !destination.isAbsolutePath) return nil;
  NSString *folder = [directory stringByAppendingPathComponent:@"NeoStationFBNeo/fbneo/cheats"];
  NSString *file = [folder stringByAppendingPathComponent:[driver stringByAppendingPathExtension:@"ini"]];
  NSString *receipt = [[folder stringByAppendingPathComponent:@"NeoStationManaged"] stringByAppendingPathComponent:[driver stringByAppendingPathExtension:@"json"]];
  NSFileManager *files = NSFileManager.defaultManager;
  NSDictionary *attributes = [files attributesOfItemAtPath:file error:nil];
  NSDictionary *receiptAttributes = [files attributesOfItemAtPath:receipt error:nil];
  if (![attributes[NSFileType] isEqual:NSFileTypeRegular] || [attributes fileSize] > 4*1024*1024 ||
      ![receiptAttributes[NSFileType] isEqual:NSFileTypeRegular] || [receiptAttributes fileSize] > 12*1024*1024) return nil;
  NSData *data = [NSData dataWithContentsOfFile:file], *receiptData = [NSData dataWithContentsOfFile:receipt];
  id provenance = receiptData ? [NSJSONSerialization JSONObjectWithData:receiptData options:0 error:nil] : nil;
  if (![provenance isKindOfClass:NSDictionary.class] || ![provenance[@"schema"] isEqual:@1] ||
      ![provenance[@"driver"] isEqual:driver] || ![provenance[@"sha256"] isEqual:[self digest:data ?: NSData.data]] ||
      ![provenance[@"programs"] isKindOfClass:NSArray.class] || [provenance[@"programs"] count] > 4096) return nil;
  NSMutableDictionary *blocks = [NSMutableDictionary dictionary];
  for (id program in provenance[@"programs"]) {
    NSString *block = FBBlock(program); if (!block) return nil;
    blocks[[self digest:[block dataUsingEncoding:NSUTF8StringEncoding]]] = block;
  }
  if (!blocks.count) return nil;
  NSMutableString *native = [NSMutableString stringWithString:@"// RewindBox managed native cheats; activation is session-only.\n"];
  for (NSString *key in [blocks.allKeys sortedArrayUsingSelector:@selector(compare:)]) {
    [native appendString:blocks[key]]; [native appendString:@"\n"];
  }
  // A matching receipt hash alone does not make arbitrary personal text safe.
  // Regeneration independently excludes includes, DAT scripts and active Off.
  NSData *regenerated = [native dataUsingEncoding:NSUTF8StringEncoding];
  if (![data isEqual:regenerated] || !SameFileAttributes(attributes,[files attributesOfItemAtPath:file error:nil])) return nil;
  NSString *target = [destination stringByAppendingPathComponent:[driver stringByAppendingPathExtension:@"ini"]];
  if (![data writeToFile:target options:NSDataWritingAtomic error:error]) return nil;
  return @{@"driver":driver,@"programs":@(blocks.count),@"sha256":[self digest:data],@"path":target};
}
+ (NSString *)searchTitle:(NSString *)title {
  static NSRegularExpression *tags, *spaces; static dispatch_once_t once;
  dispatch_once(&once, ^{
    tags = [NSRegularExpression regularExpressionWithPattern:@"\\([^)]*\\)|\\[[^]]*\\]" options:0 error:nil];
    spaces = [NSRegularExpression regularExpressionWithPattern:@"\\s+" options:0 error:nil];
  });
  NSString *base = [tags stringByReplacingMatchesInString:title options:0 range:NSMakeRange(0, title.length) withTemplate:@""];
  base = [spaces stringByReplacingMatchesInString:base.lowercaseString options:0 range:NSMakeRange(0,base.length) withTemplate:@" "];
  return [base stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
}
// Device tags describe the code format, not a different ROM. Region/revision tags
// remain in the exact key. Never strip all parentheses for an automatic match.
+ (NSString *)versionTitle:(NSString *)title {
  static NSRegularExpression *tags, *spaces; static dispatch_once_t once;
  dispatch_once(&once, ^{
    tags = [NSRegularExpression regularExpressionWithPattern:
      @"\\((?:Game Genie|GameShark|Game Shark|Action Replay|Pro Action Replay|Game Buster|Xploder|CodeBreaker|Code Breaker)\\)" options:NSRegularExpressionCaseInsensitive error:nil];
    spaces = [NSRegularExpression regularExpressionWithPattern:@"\\s+" options:0 error:nil];
  });
  NSString *result = [tags stringByReplacingMatchesInString:title options:0 range:NSMakeRange(0, title.length) withTemplate:@""];
  result = [result lowercaseString];
  return [[spaces stringByReplacingMatchesInString:result options:0 range:NSMakeRange(0, result.length) withTemplate:@" "] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
}
+ (NSSet *)regions:(NSString *)title {
  NSMutableSet *regions = [NSMutableSet set];
  NSDictionary *aliases = @{@"usa":@"usa", @"europe":@"europe", @"japan":@"japan", @"world":@"world",
    @"germany":@"germany", @"france":@"france", @"spain":@"spain", @"italy":@"italy", @"korea":@"korea", @"australia":@"australia",
    @"u":@"usa", @"us":@"usa", @"e":@"europe", @"eu":@"europe", @"j":@"japan", @"jp":@"japan"};
  NSRegularExpression *tags = [NSRegularExpression regularExpressionWithPattern:@"\\(([^)]*)\\)" options:0 error:nil];
  for (NSTextCheckingResult *match in [tags matchesInString:title.lowercaseString options:0 range:NSMakeRange(0, title.length)])
    for (NSString *part in [[title.lowercaseString substringWithRange:[match rangeAtIndex:1]] componentsSeparatedByString:@","]) {
      NSString *region = aliases[[part stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet]];
      if (region) [regions addObject:region];
    }
  return regions;
}
+ (NSDictionary *)metadataForTitle:(NSString *)title {
  NSSet *regions = [self regions:title]; NSMutableSet *languages = [NSMutableSet set];
  NSDictionary *aliases = @{@"en":@"en",@"fr":@"fr",@"de":@"de",@"es":@"es",@"it":@"it",@"ja":@"ja",@"ko":@"ko",@"zh":@"zh",@"nl":@"nl",@"pt":@"pt",@"ru":@"ru"};
  NSRegularExpression *tags = [NSRegularExpression regularExpressionWithPattern:@"\\(([^)]*)\\)" options:0 error:nil];
  NSString *lower = title.lowercaseString;
  for (NSTextCheckingResult *match in [tags matchesInString:lower options:0 range:NSMakeRange(0,lower.length)]) {
    for (NSString *part in [[lower substringWithRange:[match rangeAtIndex:1]] componentsSeparatedByString:@","]) {
      NSString *language = aliases[[part stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet]];
      if (language) [languages addObject:language];
    }
  }
  // A French-language release is not every European release. Country tags may
  // provide a language hint, whereas USA/Europe/World do not prove language.
  NSDictionary *countries = @{@"france":@"fr",@"germany":@"de",@"spain":@"es",@"italy":@"it",@"japan":@"ja",@"korea":@"ko"};
  for (NSString *region in regions) if (countries[region]) [languages addObject:countries[region]];
  NSMutableDictionary *result = [@{@"regions":[regions.allObjects sortedArrayUsingSelector:@selector(compare:)],
    @"languages":[languages.allObjects sortedArrayUsingSelector:@selector(compare:)]} mutableCopy];
  NSRegularExpression *revision = [NSRegularExpression regularExpressionWithPattern:@"\\((?:rev\\.?\\s*|v)([0-9][a-z0-9._-]*)\\)" options:NSRegularExpressionCaseInsensitive error:nil];
  NSTextCheckingResult *match = [revision firstMatchInString:lower options:0 range:NSMakeRange(0,lower.length)];
  if (match) result[@"gameRevision"] = [lower substringWithRange:[match rangeAtIndex:1]];
  return result;
}
+ (NSString *)matchGame:(NSDictionary *)game identity:(NSDictionary *)identity {
  NSString *system = String(game[@"console"]).length ? game[@"console"] : String(game[@"system"]);
  if (![system isEqual:String(identity[@"console"])]) return @"none";
  // An executable hash, cartridge hash and container hash are different
  // namespaces even when their digest strings happen to be identical. Values
  // within one type/scheme group are alternatives; distinct groups constrain
  // the same release together (notably DS game code AND R4 header checksum).
  NSArray *expected = [game[@"identities"] isKindOfClass:NSArray.class] ? game[@"identities"] : @[];
  NSArray *observed = [identity[@"identities"] isKindOfClass:NSArray.class] ? identity[@"identities"] : @[];
  if (expected.count) {
    if (expected.count > 64) return @"none";
    NSMutableDictionary<NSString *,NSMutableSet *> *groups = [NSMutableDictionary dictionary];
    for (id entry in expected) {
      if (![entry isKindOfClass:NSDictionary.class]) return @"none";
      NSString *type = String(entry[@"type"]), *scheme = String(entry[@"scheme"]), *value = String(entry[@"value"]);
      if (!type.length || !scheme.length || !value.length || value.length > 256 ||
          [type containsString:@"|"] || [scheme containsString:@"|"]) return @"none";
      NSString *key = [NSString stringWithFormat:@"%@|%@",type.lowercaseString,scheme.lowercaseString];
      if (!groups[key]) groups[key] = [NSMutableSet set];
      [groups[key] addObject:value.lowercaseString];
    }
    NSUInteger complete = 0; BOOL strong = NO;
    for (NSString *key in groups) {
      BOOL comparable = NO, matched = NO;
      for (id entry in observed) {
        if (![entry isKindOfClass:NSDictionary.class]) continue;
        NSString *actualKey = [NSString stringWithFormat:@"%@|%@",String(entry[@"type"]).lowercaseString,String(entry[@"scheme"]).lowercaseString];
        if (![key isEqual:actualKey]) continue;
        comparable = YES;
        if ([groups[key] containsObject:String(entry[@"value"]).lowercaseString]) matched = YES;
      }
      if (comparable && !matched) return @"mismatch";
      if (matched) {
        complete++;
        NSString *type = [key componentsSeparatedByString:@"|"].firstObject;
        if ([@[@"md5",@"sha1",@"sha256",@"crc32",@"n64_header"] containsObject:type]) strong = YES;
      }
    }
    if (complete == groups.count) {
      if (groups[@"ds_game_code|nds-header-gamecode"] && groups[@"ds_crc|r4-header512-crc32-inverted"]) strong = YES;
      id version = game[@"gameRevision"], actualVersion = identity[@"gameRevision"];
      if (version && actualVersion && ![[version description] isEqual:[actualVersion description]]) return @"mismatch";
      if (version && !actualVersion) strong = NO;
      // Disc/title IDs identify a regional release, but do not prove its update
      // or executable revision. Keep these visible for explicit confirmation.
      return strong ? @"hash" : @"candidate";
    }
    // Missing a required typed identity is uncertainty, never a name-based hash
    // match. A comparable mismatch above cannot fall through to title matching.
  }
  NSArray *hashes = [game[@"md5s"] isKindOfClass:NSArray.class] ? game[@"md5s"] : @[];
  NSArray *actual = [identity[@"md5s"] isKindOfClass:NSArray.class] ? identity[@"md5s"] : @[identity[@"md5"] ?: @""];
  if (hashes.count) {
    for (NSString *hash in actual) if ([hashes containsObject:hash]) return expected.count ? @"candidate" : @"hash";
    return @"mismatch";
  }
  NSArray *titles = [identity[@"titles"] isKindOfClass:NSArray.class] ? identity[@"titles"] : @[];
  if (titles.count) {
    NSString *version = [self versionTitle:String(game[@"title"])];
    for (NSString *title in titles) if ([version isEqual:[self versionTitle:title]]) return expected.count ? @"candidate" : @"hash";
  }
  NSArray *serialTitles = [identity[@"serialTitles"] isKindOfClass:NSArray.class] ? identity[@"serialTitles"] : @[];
  NSArray *hints = [identity[@"titleHints"] isKindOfClass:NSArray.class] ? identity[@"titleHints"] : @[String(identity[@"title"])];
  // A real identity always outranks a library label, including its region.
  NSArray *search = titles.count ? titles : serialTitles.count ? serialTitles : hints;
  for (NSString *title in search) {
    if (![[self searchTitle:title] isEqual:[self searchTitle:String(game[@"title"])]]) continue;
    NSSet *a = [self regions:title], *b = [self regions:String(game[@"title"])];
    if (a.count && b.count && ![a containsObject:@"world"] && ![b containsObject:@"world"] && ![a intersectsSet:b]) continue;
    NSDictionary *firstMetadata = [self metadataForTitle:title], *otherMetadata = [self metadataForTitle:String(game[@"title"])];
    NSSet *firstLanguages = [NSSet setWithArray:firstMetadata[@"languages"]], *otherLanguages = [NSSet setWithArray:otherMetadata[@"languages"]];
    if (firstLanguages.count && otherLanguages.count && ![firstLanguages intersectsSet:otherLanguages]) continue;
    // A different explicit revision is never a candidate for automatic loading.
    if (firstMetadata[@"gameRevision"] && otherMetadata[@"gameRevision"] &&
        ![firstMetadata[@"gameRevision"] isEqual:otherMetadata[@"gameRevision"]]) continue;
    return @"candidate";
  }
  return @"none";
}
@end
