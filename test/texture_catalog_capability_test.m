// SPDX-License-Identifier: GPL-3.0-or-later
// Foundation-only boundary test. No network, texture payload or emulator run.
#import <Foundation/Foundation.h>
#import "Public/NeoTextureCatalog.h"
#import "NeoTextureSupport.h"
#include <stdio.h>

static NSUInteger Checks;
#define CHECK(value, label) do { Checks++; if (!(value)) { fprintf(stderr, "FAIL: %s\n", label); return 1; } } while (0)

static NSMutableDictionary *Clone(NSDictionary *value) {
  return [NSJSONSerialization JSONObjectWithData:NeoTexJSONData(value) options:NSJSONReadingMutableContainers error:nil];
}

static NSDictionary *Index(NSDictionary *pack) {
  return @{@"catalogue_id": @"neostation-hd-textures", @"schema_version": @1, @"revision": @"native-capability-test",
           @"generated_at": @"2026-10-20", @"packs": @[pack], @"sources": @[]};
}

static NSDictionary *Checked(NSDictionary *pack) {
  return [NeoTextureCatalog validatedIndex:NeoTexJSONData(Index(pack)) error:nil][@"packs"][0];
}

static NSMutableDictionary *Manual(NSString *format) {
  NSString *digest = [@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0];
  return Clone(@{@"id": @"capability-fixture", @"system": @"gc", @"engine": @"dolphin", @"title": @"Capability fixture",
                @"version": @"test", @"authors": @[@"Test author"], @"page_url": @"https://example.org/creator",
                @"games": @[@{@"title": @"Fixture game", @"identities": @[@{@"type": @"game_id", @"scheme": @"dolphin-disc-game-id", @"value": @"GALE01"}]}],
                @"licence": @{@"summary": @"Synthetic metadata only"}, @"availability": @"manual",
                @"download": @{@"automatable": @NO, @"verified": @{@"format": format, @"file_name": [@"pack" stringByAppendingPathExtension:format],
                    @"size": @1234, @"sha256": digest, @"host": @"gdrive"}},
                @"install": @{@"files": @2, @"bytes": @4096, @"folders": @[@{@"from": @"GALE01/", @"to": @"{id}", @"exclude": @[@"dumps/"]}], @"formats": @[@"png"]}});
}

static void AddCapability(NSMutableDictionary *pack, NSString *provider, NSString *url) {
  NSDictionary *file = pack[@"download"][@"verified"];
  NSMutableDictionary *part = [@{@"url": url, @"size": file[@"size"], @"sha256": file[@"sha256"]} mutableCopy];
  if (provider) part[@"provider"] = provider;
  pack[@"download"][@"in_app"] = Clone(@{@"automatable": @YES, @"format": file[@"format"],
      @"file_name": file[@"file_name"], @"parts": @[part]});
}

int main(void) {
  @autoreleasepool {
    NSMutableDictionary *manual = Manual(@"zip");
    CHECK([Checked(manual)[@"availability"] isEqual:@"manual"], "plain verified pack remains manual");
    NSMutableDictionary *capable = Clone(manual);
    AddCapability(capable, @"gdrive", @"https://drive.google.com/file/d/1xhYvVMScGS1uVN18_V6qh_PKPuvts9Vy/view");
    NSData *original = NeoTexJSONData(capable);
    NSDictionary *expanded = Checked(capable);
    CHECK([expanded[@"availability"] isEqual:@"available"] && [expanded[@"download"][@"automatable"] boolValue], "valid provider capability expands");
    CHECK([expanded[@"games"] isEqual:manual[@"games"]] && [expanded[@"install"] isEqual:manual[@"install"]], "identity and folder/exclusion plan preserved");
    CHECK([expanded[@"download"][@"parts"][0][@"sha256"] isEqual:manual[@"download"][@"verified"][@"sha256"]], "verified digest preserved");
    CHECK([NeoTexJSONData(capable) isEqualToData:original], "input metadata unchanged");

    for (NSString *field in @[@"provider", @"url", @"sha256", @"size"]) {
      NSMutableDictionary *bad = Clone(capable), *part = bad[@"download"][@"in_app"][@"parts"][0];
      part[field] = [field isEqual:@"provider"] ? @"unimplemented" : [field isEqual:@"url"] ? @"https://drive.google.com.evil.invalid/file/d/1234567890/view" :
                    [field isEqual:@"sha256"] ? [@"b" stringByPaddingToLength:64 withString:@"b" startingAtIndex:0] : @1235;
      NSDictionary *fallback = Checked(bad);
      CHECK([fallback[@"availability"] isEqual:@"manual"] && !fallback[@"download"][@"in_app"] && fallback[@"download"][@"verified"], "invalid capability retains exact manual fallback");
    }
    for (NSString *field in @[@"format", @"file_name"]) {
      NSMutableDictionary *bad = Clone(capable);
      bad[@"download"][@"in_app"][field] = [field isEqual:@"format"] ? @"7z" : @"another.zip";
      CHECK([Checked(bad)[@"availability"] isEqual:@"manual"], "format/name mismatch never expands");
    }
    NSMutableDictionary *wrongTotal = Clone(capable);
    wrongTotal[@"download"][@"in_app"][@"size"] = @1;
    CHECK([Checked(wrongTotal)[@"availability"] isEqual:@"manual"], "conflicting total cannot weaken space accounting");
    NSMutableDictionary *badPlan = Clone(capable);
    badPlan[@"install"][@"folders"][0][@"to"] = @"../escape";
    NSDictionary *rejected = [NeoTextureCatalog validatedIndex:NeoTexJSONData(Index(badPlan)) error:nil];
    CHECK([rejected[@"packs"] count] == 0 && [rejected[@"rejected_packs"] isEqual:@1], "bad install plan cannot become available");

    NSMutableDictionary *rar = Manual(@"rar");
    AddCapability(rar, nil, @"https://archive.org/download/creator-pack/pack.rar");
    CHECK([Checked(rar)[@"availability"] isEqual:@"available"], "RAR capability expands only in native client");
    NSMutableDictionary *rawRar = Clone(Checked(rar));
    NSDictionary *rawRejected = [NeoTextureCatalog validatedIndex:NeoTexJSONData(Index(rawRar)) error:nil];
    CHECK([rawRejected[@"packs"] count] == 0, "RAR does not silently use legacy top-level availability");
    NSMutableDictionary *mega = Clone(manual);
    AddCapability(mega, @"mega", @"https://mega.nz/file/kBciRAxD#TXEQPhtoe0RAH3-nWCDy1DCuV3k2wNVLmL6omcAL5hw");
    CHECK([Checked(mega)[@"availability"] isEqual:@"available"], "strict original MEGA link expands");
    mega[@"download"][@"in_app"][@"parts"][0][@"url"] = @"https://mega.nz/folder/kBciRAxD#eTtBixQ40IaBYmP_s8kDEA";
    CHECK([Checked(mega)[@"availability"] isEqual:@"manual"], "unselected MEGA folder remains manual");

    // A remote refresh caches the original wrapper, so offline reload expands
    // it again and a downgraded older app still sees the manual fallback.
    NSString *work = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    NeoTextureCatalog *catalog = [NeoTextureCatalog new];
    catalog.storageDirectory = work;
    catalog.bundledDirectory = nil;
    NSData *source = NeoTexJSONData(Index(capable));
    catalog.fetch = ^(NSURL *url, NSUInteger limit, void (^completion)(NSData *, NSError *)) { completion(source, nil); };
    __block BOOL done = NO;
    __block NSError *failure = nil;
    [catalog refreshWithCompletion:^(NSDictionary *snapshot, NSError *error) { failure = error; done = YES; }];
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:10];
    while (!done && [deadline timeIntervalSinceNow] > 0) [NSRunLoop.mainRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
    CHECK(done && !failure && [[catalog packWithID:@"capability-fixture"][@"availability"] isEqual:@"available"], "remote capability loaded");
    CHECK([[NSData dataWithContentsOfFile:[work stringByAppendingPathComponent:@"manifest.json"]] isEqualToData:source], "cache retains source wrapper exactly");
    NeoTextureCatalog *offline = [NeoTextureCatalog new];
    offline.storageDirectory = work;
    offline.bundledDirectory = nil;
    CHECK([[offline packWithID:@"capability-fixture"][@"availability"] isEqual:@"available"], "offline reload re-expands provider capability");
    [NSFileManager.defaultManager removeItemAtPath:work error:nil];
    printf("PASS: %lu catalogue native-capability checks, exact metadata, legacy fallback and offline source-cache reload\n", (unsigned long)Checks);
  }
  return 0;
}
