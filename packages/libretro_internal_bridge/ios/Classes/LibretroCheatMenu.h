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
@property(nonatomic, copy) NSString *uiLocale;
@property(nonatomic, copy, nullable) void (^diagnostic)(NSString *message);
/// FBNeo uses its native INI/core-options engine, not retro_cheat_set.
/// The session executes these requests on the emulation queue and returns on
/// main. Imported programs stay disabled and newly installed INI needs reload.
@property(nonatomic, copy, nullable) void (^fbneoCommand)(NSDictionary *request,
    void (^completion)(NSDictionary * _Nullable result, NSError * _Nullable error));
- (LibretroMenuPage *)rootPage;
@end
NS_ASSUME_NONNULL_END
