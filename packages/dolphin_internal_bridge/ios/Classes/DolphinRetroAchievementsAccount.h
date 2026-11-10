#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
// Shared menu validation only. The former engine-specific account screen and
// Keychain accessors have been retired; the central RA tab owns the account.
FOUNDATION_EXPORT NSData* _Nullable DOLSerializeMenuRequest(id _Nullable request);
NS_ASSUME_NONNULL_END
