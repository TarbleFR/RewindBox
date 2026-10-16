#import "LibretroCheats.h"
#import <CommonCrypto/CommonDigest.h>
#import <zlib.h>
#include <string.h>
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
           @"genesis_plus_gx", @"genesis_plus_gx_wide", @"desmume", @"mednafen_psx_hw", @"mednafen_psx"];
}
+ (NSArray<NSString *> *)codesForCheat:(NSDictionary *)cheat core:(NSString *)core console:(NSString *)console {
  if ([core hasSuffix:@"_libretro"]) core = [core substringToIndex:core.length - 9];
  id handler = cheat[@"handler"];
  if (handler != nil && ![handler isKindOfClass:NSNumber.class]) return nil;
  if (![[self supportedCoreIDs] containsObject:core] || [handler integerValue] != 0) return nil;
  NSString *code = [String(cheat[@"code"]) uppercaseString];
  if (code.length == 0 || code.length > 8192 || ![code canBeConvertedToEncoding:NSASCIIStringEncoding]) return nil;
  NSString *pattern = nil;
  BOOL gba = [core isEqual:@"mgba"] && [console isEqual:@"gba"];
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
    NSMutableArray *words = [NSMutableArray array], *lines = [NSMutableArray array];
    for (NSString *word in [code componentsSeparatedByCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"+ ;,\t\r\n"]])
      if (word.length) [words addObject:word];
    for (NSUInteger i = 0; i < words.count; i++) {
      NSString *word = words[i], *pair = nil;
      if (Matches(word, psx ? @"^[0-9A-F]{12}$" : @"^[0-9A-F]{16}$")) pair = word;
      else if (Matches(word, @"^[0-9A-F]{8}$") && i+1 < words.count &&
        Matches(words[i+1], psx ? @"^[0-9A-F]{4}$" : @"^[0-9A-F]{8}$")) pair = [word stringByAppendingString:words[++i]];
      if (!pair || (psx && !Matches(pair, @"^(?:30|80)[0-9A-F]{10}$"))) return nil;
      [lines addObject:[NSString stringWithFormat:@"%@ %@", [pair substringToIndex:8], [pair substringFromIndex:8]]];
    }
    NSString *program = [lines componentsJoinedByString:@"+"];
    // Preserve AR conditions as one program. The shared ABI boundary is 255
    // bytes; longer programs stay unavailable rather than being truncated.
    return lines.count && program.length <= 255 ? @[program] : nil;
  }
  if (gba) {
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
  CC_MD5_CTX md5, canonicalMD5; CC_SHA1_CTX sha1, canonicalSHA1; CC_SHA256_CTX sha;
  CC_MD5_Init(&md5); CC_SHA1_Init(&sha1); CC_SHA256_Init(&sha);
  CC_MD5_Init(&canonicalMD5); CC_SHA1_Init(&canonicalSHA1);
  uint8_t buffer[65536]; NSInteger length; unsigned long long total = 0, skip = 0;
  uLong crc = crc32(0L, Z_NULL, 0); NSUInteger swap = 0;
  while ((length = [stream read:buffer maxLength:sizeof(buffer)]) > 0) {
    CC_MD5_Update(&md5, buffer, (CC_LONG)length); CC_SHA1_Update(&sha1, buffer, (CC_LONG)length);
    CC_SHA256_Update(&sha, buffer, (CC_LONG)length); crc = crc32(crc, buffer, (uInt)length);
    if (total == 0) {
      if ([console isEqual:@"nes"] && length >= 16 && memcmp(buffer, "NES\x1a", 4) == 0)
        skip = 16 + ((buffer[6] & 4) ? 512 : 0);
      if ([console isEqual:@"snes"] && [before fileSize] % 1024 == 512) skip = 512;
      if ([console isEqual:@"n64"] && length >= 4) {
        if (memcmp(buffer, "\x37\x80\x40\x12", 4) == 0) swap = 2;
        if (memcmp(buffer, "\x40\x12\x37\x80", 4) == 0) swap = 4;
      }
    }
    NSUInteger offset = total < skip ? (NSUInteger)MIN(skip - total, (unsigned long long)length) : 0;
    if (swap) for (NSUInteger i = 0; i + swap <= (NSUInteger)length; i += swap)
      for (NSUInteger j = 0; j < swap / 2; j++) { uint8_t t = buffer[i+j]; buffer[i+j] = buffer[i+swap-1-j]; buffer[i+swap-1-j] = t; }
    CC_MD5_Update(&canonicalMD5, buffer + offset, (CC_LONG)(length - offset));
    CC_SHA1_Update(&canonicalSHA1, buffer + offset, (CC_LONG)(length - offset)); total += length;
  }
  BOOL valid = length == 0 && stream.streamError == nil && total > skip; [stream close];
  NSDictionary *after = [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
  if (!valid || ![before[NSFileModificationDate] isEqual:after[NSFileModificationDate]] || [before fileSize] != [after fileSize]) return nil;
  unsigned char m[16], s[32], h[20], cm[16], ch[20]; CC_MD5_Final(m, &md5); CC_SHA1_Final(h, &sha1); CC_SHA256_Final(s, &sha);
  CC_MD5_Final(cm, &canonicalMD5); CC_SHA1_Final(ch, &canonicalSHA1);
  return @{@"console": console, @"core": core, @"title": title,
    @"serial": [console isEqual:@"psx"] ? ([self playStationSerialAtPath:path] ?: @"") : @"",
    @"md5": Hex(m, sizeof(m)), @"sha1": Hex(h, sizeof(h)), @"sha256": Hex(s, sizeof(s)),
    @"crc32": [NSString stringWithFormat:@"%08lx", (unsigned long)crc], @"bytes": @(total),
    @"md5s": [NSOrderedSet orderedSetWithArray:@[Hex(m, sizeof(m)), Hex(cm, sizeof(cm))]].array,
    @"sha1s": [NSOrderedSet orderedSetWithArray:@[Hex(h, sizeof(h)), Hex(ch, sizeof(ch))]].array};
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
    @"germany":@"germany", @"france":@"france", @"spain":@"spain", @"italy":@"italy", @"korea":@"korea", @"australia":@"australia"};
  NSRegularExpression *tags = [NSRegularExpression regularExpressionWithPattern:@"\\(([^)]*)\\)" options:0 error:nil];
  for (NSTextCheckingResult *match in [tags matchesInString:title.lowercaseString options:0 range:NSMakeRange(0, title.length)])
    for (NSString *part in [[title.lowercaseString substringWithRange:[match rangeAtIndex:1]] componentsSeparatedByString:@","]) {
      NSString *region = aliases[[part stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet]];
      if (region) [regions addObject:region];
    }
  return regions;
}
+ (NSString *)matchGame:(NSDictionary *)game identity:(NSDictionary *)identity {
  if (![String(game[@"console"]) isEqual:String(identity[@"console"])]) return @"none";
  NSArray *hashes = [game[@"md5s"] isKindOfClass:NSArray.class] ? game[@"md5s"] : @[];
  NSArray *actual = [identity[@"md5s"] isKindOfClass:NSArray.class] ? identity[@"md5s"] : @[identity[@"md5"] ?: @""];
  if (hashes.count) {
    for (NSString *hash in actual) if ([hashes containsObject:hash]) return @"hash";
    return @"mismatch";
  }
  NSArray *titles = [identity[@"titles"] isKindOfClass:NSArray.class] ? identity[@"titles"] : @[];
  if (titles.count) {
    NSString *version = [self versionTitle:String(game[@"title"])];
    for (NSString *title in titles) if ([version isEqual:[self versionTitle:title]]) return @"hash";
  }
  NSArray *serialTitles = [identity[@"serialTitles"] isKindOfClass:NSArray.class] ? identity[@"serialTitles"] : @[];
  NSArray *hints = [identity[@"titleHints"] isKindOfClass:NSArray.class] ? identity[@"titleHints"] : @[String(identity[@"title"])];
  // A real identity always outranks a library label, including its region.
  NSArray *search = titles.count ? titles : serialTitles.count ? serialTitles : hints;
  for (NSString *title in search) {
    if (![[self searchTitle:title] isEqual:[self searchTitle:String(game[@"title"])]]) continue;
    NSSet *a = [self regions:title], *b = [self regions:String(game[@"title"])];
    if (a.count && b.count && ![a containsObject:@"world"] && ![b containsObject:@"world"] && ![a intersectsSet:b]) continue;
    // A different explicit revision is never a candidate for automatic loading.
    NSRegularExpression *rev = [NSRegularExpression regularExpressionWithPattern:@"\\((?:rev |v)[^)]*\\)" options:NSRegularExpressionCaseInsensitive error:nil];
    NSTextCheckingResult *ar = [rev firstMatchInString:title options:0 range:NSMakeRange(0,title.length)];
    NSString *other = String(game[@"title"]);
    NSTextCheckingResult *br = [rev firstMatchInString:other options:0 range:NSMakeRange(0,other.length)];
    if (ar && br && ![[title substringWithRange:ar.range].lowercaseString isEqual:[other substringWithRange:br.range].lowercaseString]) continue;
    return @"candidate";
  }
  return @"none";
}
@end
