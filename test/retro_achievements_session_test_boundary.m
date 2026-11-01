// Gameplay/codec fixtures intentionally run without a central RA ticket.
// This is a test-only link boundary, never an authentication/session mock
// used by the application. Any attempt to enable RA aborts the fixture.
#import <retro_achievements_session/RBRASession.h>
#include <stdio.h>
#include <stdlib.h>

static void RequireDisabled(NSDictionary *configuration) {
  if ([configuration[@"enabled"] boolValue] || configuration[@"sessionId"] != nil) {
    fputs("Unexpected RetroAchievements session in a non-RA fixture\n", stderr);
    abort();
  }
}

NSDictionary *RBRATakeLaunchConfiguration(NSDictionary *arguments, NSString *engine) {
  (void)engine;
  if (arguments[@"raSessionId"] != nil) {
    fputs("Unexpected RA launch ticket in a non-RA fixture\n", stderr);
    abort();
  }
  return @{@"enabled": @NO, @"supported": @NO, @"hardcore": @NO, @"notifications": @NO};
}

void RBRAPublishSessionState(NSDictionary *configuration, NSDictionary *state) {
  (void)state;
  RequireDisabled(configuration);
}

void RBRAEndSession(NSDictionary *configuration) {
  RequireDisabled(configuration);
}

NSString *RBRALocalizedText(NSString *key, NSString *locale) {
  (void)key; (void)locale;
  fputs("Unexpected RA notice in a non-RA fixture\n", stderr);
  abort();
}
