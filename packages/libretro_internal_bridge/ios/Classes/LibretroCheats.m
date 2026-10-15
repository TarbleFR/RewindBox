#import "LibretroCheats.h"
#import <CommonCrypto/CommonDigest.h>
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
    if (code.length > 8192 || name.length > 2048 || [_game[@"cheats"] count] >= 4096) { [parser abortParsing]; return; }
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
    if (value.length > 8192 || values.count > 150000) { if (error) *error = CheatError(@"CHT limits exceeded"); return nil; }
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
           @"genesis_plus_gx", @"genesis_plus_gx_wide"];
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
    return @[[lines componentsJoinedByString:@"+"]];
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
+ (NSDictionary *)identityAtPath:(NSString *)path console:(NSString *)console core:(NSString *)core {
  NSInputStream *stream = [NSInputStream inputStreamWithFileAtPath:path]; [stream open];
  CC_MD5_CTX md5; CC_SHA256_CTX sha; CC_MD5_Init(&md5); CC_SHA256_Init(&sha);
  uint8_t buffer[65536]; NSInteger length; unsigned long long total = 0;
  while ((length = [stream read:buffer maxLength:sizeof(buffer)]) > 0) {
    CC_MD5_Update(&md5, buffer, (CC_LONG)length); CC_SHA256_Update(&sha, buffer, (CC_LONG)length); total += length;
  }
  BOOL valid = length == 0 && stream.streamError == nil && total > 0; [stream close];
  if (!valid) return nil;
  unsigned char m[CC_MD5_DIGEST_LENGTH], s[CC_SHA256_DIGEST_LENGTH]; CC_MD5_Final(m, &md5); CC_SHA256_Final(s, &sha);
  return @{@"console": console, @"core": core, @"title": path.lastPathComponent.stringByDeletingPathExtension,
           @"md5": Hex(m, sizeof(m)), @"sha256": Hex(s, sizeof(s)), @"bytes": @(total)};
}
+ (NSString *)searchTitle:(NSString *)title {
  NSRegularExpression *tags = [NSRegularExpression regularExpressionWithPattern:@"\\([^)]*\\)|\\[[^]]*\\]" options:0 error:nil];
  NSString *base = [tags stringByReplacingMatchesInString:title options:0 range:NSMakeRange(0, title.length) withTemplate:@""];
  return [[base lowercaseString] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
}
+ (NSString *)matchGame:(NSDictionary *)game identity:(NSDictionary *)identity {
  if (![String(game[@"console"]) isEqual:String(identity[@"console"])]) return @"none";
  NSArray *hashes = [game[@"md5s"] isKindOfClass:NSArray.class] ? game[@"md5s"] : @[];
  if (hashes.count > 0) return [hashes containsObject:identity[@"md5"] ?: @""] ? @"hash" : @"mismatch";
  NSString *title = [self searchTitle:String(game[@"title"])];
  return title.length && [title isEqual:[self searchTitle:String(identity[@"title"])]] ? @"candidate" : @"none";
}
@end
