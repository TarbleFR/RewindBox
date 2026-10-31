#import "Public/RBAchievementTranslation.h"
#import <achievement_translation/achievement_translation-Swift.h>

void RBAchievementResolve(NSInteger achievementID, NSString *title, NSString *description,
                          void (^completion)(NSDictionary<NSString *, NSString *> *)) {
    dispatch_async(dispatch_get_main_queue(), ^{
        [RBAchievementText resolveID:achievementID title:title description:description completion:completion];
    });
}

void RBAchievementPrefetch(NSArray<NSDictionary *> *achievements) {
    dispatch_async(dispatch_get_main_queue(), ^{ [RBAchievementText prefetch:achievements]; });
}

void RBAchievementPresent(UIViewController *owner, NSInteger achievementID, NSString *title,
                          NSString *description, NSString *suffix, NSTimeInterval duration, NSInteger kind,
                          UIView *(^surface)(void), BOOL (^valid)(void)) {
    dispatch_async(dispatch_get_main_queue(), ^{
        [RBAchievementToast presentOn:owner achievementID:achievementID title:title description:description
                              suffix:suffix duration:duration kind:kind surface:surface valid:valid];
    });
}
