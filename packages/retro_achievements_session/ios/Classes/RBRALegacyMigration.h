#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Read-only legacy inputs. Tokens returned here stay inside the native Hub.
@interface RBRALegacyMigration : NSObject
+ (nullable NSDictionary<NSString *, NSString *> *)achievementValuesAtPath:(NSString *)path
                                                                    error:(NSError * _Nullable * _Nullable)error;
+ (NSArray<NSDictionary *> *)candidatesWithLibretro:(nullable NSDictionary *)libretro
                                  libretroEnabled:(nullable id)libretroEnabled
                                          dolphin:(nullable NSDictionary *)dolphin
                                    dolphinValues:(NSDictionary *)dolphinValues
                                    armsx2Values:(NSDictionary *)armsx2Values
                                   armsx2Secrets:(NSDictionary *)armsx2Secrets;
@end

NS_ASSUME_NONNULL_END
