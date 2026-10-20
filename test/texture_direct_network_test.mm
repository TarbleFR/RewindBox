// SPDX-License-Identifier: GPL-3.0-or-later
// Real small-file public-network probes through production native components.
#import <Foundation/Foundation.h>
#import "NeoTextureCatalog.h"
#import "NeoTextureEngine.h"
#import "NeoTexturePackStore.h"
#import "NeoTextureSupport.h"
#include <cstdio>

static NSString *Provider(NSDictionary *pack) {
  NSDictionary *part = [pack[@"download"][@"parts"] firstObject];
  NSString *provider = NeoTexString(part[@"provider"]);
  if (provider.length) return provider;
  NSString *host = [NSURL URLWithString:NeoTexString(part[@"url"])].host.lowercaseString ?: @"unknown";
  if ([host hasSuffix:@"gamebanana.com"]) return @"gamebanana";
  if ([host hasSuffix:@"dropbox.com"] || [host hasSuffix:@"dropboxusercontent.com"]) return @"dropbox";
  return @"direct";
}

int main(int argc, char **argv) {
  @autoreleasepool {
    if (argc != 4) return 64;
    NSData *data = [NSData dataWithContentsOfFile:@(argv[1])];
    NSArray *rows = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    if (![rows isKindOfClass:NSArray.class] || rows.count > 20) return 65;
    NSString *work = @(argv[3]);
    [NSFileManager.defaultManager createDirectoryAtPath:work withIntermediateDirectories:YES attributes:nil error:nil];
    NeoTexSetRegistryPath([work stringByAppendingPathComponent:@"registry.json"]);
    NSMutableArray *results = [NSMutableArray array];
    NSMutableSet *blocked = [NSMutableSet set];
    NSUInteger number = 0;
    for (NSDictionary *row in rows) {
      @autoreleasepool {
        NSDictionary *raw = row[@"pack"];
        NSDictionary *root = @{@"catalogue_id": @"neostation-hd-textures", @"schema_version": @1,
                               @"revision": @"native-public-network-probe", @"packs": @[raw ?: @{}], @"sources": @[]};
        NSDictionary *validated = [NeoTextureCatalog validatedIndex:
            [NSJSONSerialization dataWithJSONObject:root options:0 error:nil] error:nil];
        NSDictionary *pack = [validated[@"packs"] firstObject];
        NSString *packID = NeoTexString(raw[@"id"]), *provider = Provider(pack ?: raw);
        NSMutableDictionary *record = [@{@"id": packID, @"provider": provider, @"physical_device_rendering": @NO} mutableCopy];
        if ([blocked containsObject:provider]) {
          record[@"status"] = @"not_attempted_after_provider_failure";
          [results addObject:record]; continue;
        }
        if (!pack || ![pack[@"availability"] isEqual:@"available"] || ![pack[@"download"][@"automatable"] boolValue]) {
          record[@"status"] = @"catalogue_not_available";
          [results addObject:record]; continue;
        }
        NSString *base = [work stringByAppendingPathComponent:[NSString stringWithFormat:@"%lu", (unsigned long)number++]];
        NSString *configuration = [base stringByAppendingPathComponent:@"config"];
        id<NeoTextureEngine> engine = nil;
        if ([pack[@"engine"] isEqual:@"dolphin"]) engine = [NeoTextureEngines dolphinWithUserDirectory:[base stringByAppendingPathComponent:@"dolphin"]];
        else if ([pack[@"engine"] isEqual:@"ppsspp"]) engine = [NeoTextureEngines ppssppWithSaveDirectory:[base stringByAppendingPathComponent:@"psp"] configDirectory:configuration];
        if (!engine) { record[@"status"] = @"probe_engine_not_supported"; [results addObject:record]; continue; }
        NeoTexturePackStore *store = [NeoTexturePackStore new];
        store.downloadDirectory = [base stringByAppendingPathComponent:@"downloads"];
        __block BOOL finished = NO;
        __block NSDictionary *outcome = nil;
        __block NSError *failure = nil;
        NSDate *start = [NSDate date];
        [store installPack:pack engine:engine identity:row[@"identity"] replace:NO confirmed:NO
            completion:^(NSDictionary *result, NSError *error) { outcome = result; failure = error; finished = YES; }];
        NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:360];
        while (!finished && [deadline timeIntervalSinceNow] > 0)
          [NSRunLoop.mainRunLoop runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
        if (!finished) {
          [store cancelPack:packID];
          failure = [NSError errorWithDomain:NeoTexturePackStoreErrorDomain code:NeoTexturePackErrorNetwork userInfo:@{@"key": @"probeTimeout"}];
        }
        record[@"seconds"] = @(-[start timeIntervalSinceNow]);
        if (!failure && [outcome[@"installed"] count]) {
          record[@"status"] = @"ok";
          record[@"size_sha_verified_by_store"] = @YES;
          record[@"installed"] = outcome[@"installed"];
          record[@"activated"] = outcome[@"activated"] ?: @NO;
          unsigned long long files = 0, bytes = 0;
          for (NSString *folder in outcome[@"installed"]) {
            NSString *path = [engine.texturesRoot stringByAppendingPathComponent:folder];
            for (NSString *name in [NSFileManager.defaultManager enumeratorAtPath:path]) {
              if ([name isEqual:@"NeoStation-pack.json"]) continue;
              NSDictionary *attributes = [NSFileManager.defaultManager attributesOfItemAtPath:[path stringByAppendingPathComponent:name] error:nil];
              if ([attributes.fileType isEqual:NSFileTypeRegular]) { files++; bytes += attributes.fileSize; }
            }
          }
          record[@"installed_files"] = @(files); record[@"installed_bytes"] = @(bytes);
          record[@"expected_archive_bytes"] = pack[@"download"][@"size"] ?: [pack[@"download"][@"parts"] firstObject][@"size"];
          record[@"expected_archive_sha256"] = pack[@"download"][@"sha256"] ?: [pack[@"download"][@"parts"] firstObject][@"sha256"];
        } else {
          record[@"status"] = @"failed";
          record[@"error"] = NeoTexString(failure.userInfo[@"key"]);
          record[@"error_code"] = @(failure.code);
          for (NSString *key in @[@"status", @"provider_code"])
            if ([failure.userInfo[key] isKindOfClass:NSNumber.class]) record[[@"http_" stringByAppendingString:key]] = failure.userInfo[key];
          // Conservatively stop this provider after any failure. In particular
          // a403/quota result never triggers another file, runner or profile.
          [blocked addObject:provider];
        }
        [results addObject:record];
        fprintf(stdout, "%s %s %s\n", packID.UTF8String, provider.UTF8String, [record[@"status"] UTF8String]); fflush(stdout);
      }
    }
    NSDictionary *summary = @{@"schema": @1, @"network": @YES, @"native_store": @YES,
                               @"automatic_retries": @0, @"results": results};
    NSData *output = [NSJSONSerialization dataWithJSONObject:summary options:NSJSONWritingPrettyPrinted error:nil];
    return [output writeToFile:@(argv[2]) atomically:YES] ? 0 : 74;
  }
}
