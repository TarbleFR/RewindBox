#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN
/// Display-only. Called after the engine commits an unlock. Completion is on main.
FOUNDATION_EXPORT void RBAchievementResolve(NSInteger achievementID, NSString *title,
    NSString *description, void (^completion)(NSDictionary<NSString *, NSString *> *text));
FOUNDATION_EXPORT void RBAchievementPrefetch(NSArray<NSDictionary *> *achievements);
FOUNDATION_EXPORT void RBAchievementPresent(UIViewController *owner, NSInteger achievementID,
    NSString *title, NSString *description, NSString *suffix, NSTimeInterval duration, BOOL (^valid)(void));
NS_ASSUME_NONNULL_END
