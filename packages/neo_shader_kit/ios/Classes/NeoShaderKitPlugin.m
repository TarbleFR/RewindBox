// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoShaderKitPlugin.h"

#import "NeoShaderStorage.h"

/// Engines whose shader storage the tools may report on.
static NSArray<NSString *> *KnownEngines(void) { return @[ @"libretro", @"dolphin" ]; }

/// {engine: root} from the call, limited to known engines and to folders
/// inside the application's container.
static NSDictionary<NSString *, NSString *> *Roots(id arguments) {
  NSDictionary *roots = [arguments isKindOfClass:NSDictionary.class] ? arguments[@"roots"] : nil;
  if (![roots isKindOfClass:NSDictionary.class]) return @{};
  NSString *home = NSHomeDirectory().stringByStandardizingPath;
  NSMutableDictionary<NSString *, NSString *> *result = [NSMutableDictionary dictionary];
  for (NSString *engine in KnownEngines()) {
    NSString *root = roots[engine];
    if (![root isKindOfClass:NSString.class]) continue;
    NSString *standard = root.stringByStandardizingPath;
    if ([standard hasPrefix:[home stringByAppendingString:@"/"]]) result[engine] = standard;
  }
  return result;
}

@implementation NeoShaderKitPlugin

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar> *)registrar {
  FlutterMethodChannel *channel = [FlutterMethodChannel methodChannelWithName:@"neostation/shader_kit"
                                                              binaryMessenger:[registrar messenger]];
  NeoShaderKitPlugin *instance = [NeoShaderKitPlugin new];
  [registrar addMethodCallDelegate:instance channel:channel];
}

- (void)handleMethodCall:(FlutterMethodCall *)call result:(FlutterResult)result {
  NSDictionary<NSString *, NSString *> *roots = Roots(call.arguments);
  if ([call.method isEqualToString:@"storageReport"]) {
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
      NSMutableArray *engines = [NSMutableArray array];
      unsigned long long previews = 0;
      for (NSString *engine in roots) {
        if (![NSFileManager.defaultManager fileExistsAtPath:roots[engine]]) continue;
        NSDictionary *report = [[NeoShaderStorage sharedStorageWithRoot:roots[engine] engine:engine] storageReport];
        previews += [report[@"previewBytes"] unsignedLongLongValue];
        [engines addObject:report];
      }
      dispatch_async(dispatch_get_main_queue(), ^{
        result(@{@"engines" : engines, @"previewCacheBytes" : @(previews)});
      });
    });
  } else if ([call.method isEqualToString:@"cleanCaches"]) {
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
      unsigned long long freed = 0;
      for (NSString *engine in roots) {
        if (![NSFileManager.defaultManager fileExistsAtPath:roots[engine]]) continue;
        freed += [[NeoShaderStorage sharedStorageWithRoot:roots[engine] engine:engine] cleanCaches];
      }
      dispatch_async(dispatch_get_main_queue(), ^{
        result(@(freed));
      });
    });
  } else {
    result(FlutterMethodNotImplemented);
  }
}

@end
