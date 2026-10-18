// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoCheatCatalogPlugin.h"
#import "Public/NeoUnifiedCheatCatalog.h"

/// The native index is shared, but sending it through Flutter's codec would
/// recreate tens of thousands of metadata objects in Dart. Query pages use
/// searchGames/gamesForIdentity; the maintenance channel only needs a summary.
static NSDictionary *CompactSummary(NSDictionary *data) {
  NSMutableDictionary *summary=[data mutableCopy];
  summary[@"game_count"]=@([data[@"games"] isKindOfClass:NSArray.class] ? [data[@"games"] count] : 0);
  [summary removeObjectForKey:@"games"];[summary removeObjectForKey:@"packs"];
  return [summary copy];
}

@interface NeoCheatCatalogPlugin () <FlutterStreamHandler>
@property(nonatomic, copy) FlutterEventSink events;
@end
@implementation NeoCheatCatalogPlugin
+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar> *)registrar {
  NeoCheatCatalogPlugin *plugin=[self new];
  FlutterMethodChannel *methods=[FlutterMethodChannel methodChannelWithName:@"neostation/cheat_catalog" binaryMessenger:registrar.messenger];
  [registrar addMethodCallDelegate:plugin channel:methods];
  FlutterEventChannel *events=[FlutterEventChannel eventChannelWithName:@"neostation/cheat_catalog/progress" binaryMessenger:registrar.messenger];
  [events setStreamHandler:plugin];
}
- (FlutterError *)onListenWithArguments:(id)arguments eventSink:(FlutterEventSink)events {self.events=events;return nil;}
- (FlutterError *)onCancelWithArguments:(id)arguments {self.events=nil;return nil;}
- (void)handleMethodCall:(FlutterMethodCall *)call result:(FlutterResult)result {
  NeoUnifiedCheatCatalog *catalog=NeoUnifiedCheatCatalog.sharedCatalog;
  NSDictionary *args=[call.arguments isKindOfClass:NSDictionary.class] ? call.arguments : @{};
  if([call.method isEqualToString:@"load"]){
    [catalog loadWithCompletion:^(NSDictionary *data,NSError *error){result(data ? CompactSummary(data) : [FlutterError errorWithCode:@"catalogue_unavailable" message:error.localizedDescription details:nil]);}];
  }else if([call.method isEqualToString:@"installAll"]){
    __weak typeof(self) weakSelf=self;
    [catalog installAllWithProgress:^(NSDictionary *progress){FlutterEventSink events=weakSelf.events;if(events)events(progress);}
      completion:^(NSDictionary *data,NSError *error){
        // Successful packs must be reviewable even when their siblings fail.
        if(data){NSMutableDictionary *response=[CompactSummary(data) mutableCopy];if(error)response[@"error"]=error.localizedDescription;result(response);}
        else result([FlutterError errorWithCode:@"catalogue_install" message:error.localizedDescription details:nil]);
      }];
  }else if([call.method isEqualToString:@"gamesForIdentity"]){
    NSDictionary *identity=[args[@"identity"] isKindOfClass:NSDictionary.class] ? args[@"identity"] : @{};
    [catalog gamesForIdentity:identity completion:^(NSArray *games,NSError *error){result(error ? [FlutterError errorWithCode:@"catalogue_lookup" message:error.localizedDescription details:nil] : games);}];
  }else if([call.method isEqualToString:@"searchGames"]){
    NSString *query=[args[@"query"] isKindOfClass:NSString.class] ? args[@"query"] : @"";
    NSString *system=[args[@"system"] isKindOfClass:NSString.class] ? args[@"system"] : @"";
    [catalog searchGames:query system:system completion:^(NSArray *games,NSError *error){result(error ? [FlutterError errorWithCode:@"catalogue_lookup" message:error.localizedDescription details:nil] : games);}];
  }else if([call.method isEqualToString:@"cheatsForGame"]){
    NSDictionary *game=[args[@"game"] isKindOfClass:NSDictionary.class] ? args[@"game"] : @{};
    [catalog cheatsForGame:game completion:^(NSArray *cheats,NSError *error){result(error ? [FlutterError errorWithCode:@"catalogue_game" message:error.localizedDescription details:nil] : cheats);}];
  }else result(FlutterMethodNotImplemented);
}
@end
