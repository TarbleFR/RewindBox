// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

// A single, anonymous public-file resolution. Cancellation completes once with
// key "cancelled"; it never authenticates, changes accounts or retries quotas.
@protocol NeoTexHostResolution <NSObject>
- (void)cancel;
@end

// Parts carry {provider: gdrive|yandex, url: original public sharing URL,
// size: positive exact archive bytes, sha256: exact 64-hex archive digest}.
FOUNDATION_EXPORT BOOL NeoTexValidHostPart(NSDictionary *part);

// The returned URL is short-lived and must not be persisted into the catalogue.
// Completion runs once on an internal serial queue; the caller marshals it to
// its state queue. The archive downloader still checks exact size and SHA-256.
FOUNDATION_EXPORT id<NeoTexHostResolution> NeoTexResolveHostPart(
    NSDictionary *part, void (^completion)(NSURL * _Nullable, NSError * _Nullable));

// Dependency injection for native URLProtocol fixtures; the production entry
// point creates an ephemeral configuration. Both paths disable cookies/cache.
FOUNDATION_EXPORT id<NeoTexHostResolution> NeoTexResolveHostPartWithConfiguration(
    NSDictionary *part, NSURLSessionConfiguration *configuration,
    void (^completion)(NSURL * _Nullable, NSError * _Nullable));

NS_ASSUME_NONNULL_END
