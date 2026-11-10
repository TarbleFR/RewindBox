// Explicit boundary for tests that never start achievement processing.
// This is not a presenter/translation implementation or presentation evidence.
// An unexpected call aborts the test rather than silently dropping a toast.
#import <achievement_translation/RBAchievementTranslation.h>
#include <stdio.h>
#include <stdlib.h>

static void UnexpectedAchievementCall(const char *name) {
    fprintf(stderr, "TEST FAILURE: %s called in a fixture with achievements disabled\n", name);
    abort();
}

void RBAchievementResolve(NSInteger achievementID, NSString *title, NSString *description,
                          void (^completion)(NSDictionary<NSString *, NSString *> *)) {
    UnexpectedAchievementCall(__func__);
}

void RBAchievementPrefetch(NSArray<NSDictionary *> *achievements) {
    UnexpectedAchievementCall(__func__);
}

void RBAchievementPresent(UIViewController *owner, NSInteger achievementID, NSString *title,
                          NSString *description, NSString *suffix, NSTimeInterval duration, NSInteger kind,
                          UIView *(^surface)(void), BOOL (^valid)(void)) {
    UnexpectedAchievementCall(__func__);
}
