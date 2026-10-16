#import <UIKit/UIKit.h>
@class LibretroMenuPage;
NS_ASSUME_NONNULL_BEGIN
@interface LibretroCheatMenu : NSObject
- (instancetype)initWithDirectory:(NSString *)directory console:(NSString *)console core:(NSString *)core
                     contentPath:(NSString *)contentPath gameTitle:(NSString *)gameTitle legacy:(NSArray<NSDictionary *> *)legacy
                            text:(NSString *(^)(NSString *key))text apply:(void (^)(NSArray<NSString *> *codes))apply;
- (instancetype)initWithDirectory:(NSString *)directory console:(NSString *)console core:(NSString *)core
                     contentPath:(NSString *)contentPath legacy:(NSArray<NSDictionary *> *)legacy
                            text:(NSString *(^)(NSString *key))text apply:(void (^)(NSArray<NSString *> *codes))apply;
@property(nonatomic, readonly) NSUInteger enabledCount;
@property(nonatomic, copy, nullable) void (^diagnostic)(NSString *message);
- (LibretroMenuPage *)rootPage;
@end
NS_ASSUME_NONNULL_END
