#import "DolphinRetroAchievementsAccount.h"

// Legacy filename retained for existing menu test/build manifests. Account
// login, storage and migration belong exclusively to retro_achievements_session.
// Shared by the menu and bridge so native callers cannot bypass validation.
NSData* DOLSerializeMenuRequest(id request) {
  @try {
    if (![request isKindOfClass:NSDictionary.class] ||
        ![request[@"kind"] isKindOfClass:NSString.class] ||
        ![request[@"kind"] length] || ![NSJSONSerialization isValidJSONObject:request]) return nil;
    NSError* error = nil;
    NSData* data = [NSJSONSerialization dataWithJSONObject:request options:0 error:&error];
    return error ? nil : data;
  } @catch (NSException* exception) {
    // Never log requests: callers might accidentally include credentials.
    return nil;
  }
}
