// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#import <Foundation/Foundation.h>
#import "NeoTextureHostResolver.h"
#ifdef __cplusplus
#include <functional>
#endif

NS_ASSUME_NONNULL_BEGIN

/// One anonymous public MEGA resolution. Cancels whichever metadata request
/// is currently active, including the second request for a selected folder file.
@interface NeoTextureMegaRequest : NSObject <NeoTexHostResolution>
- (void)cancel;
@end

/// Explicit provider tag; malformed MEGA parts still go through the resolver
/// and fail closed instead of being fetched as ordinary web pages.
FOUNDATION_EXPORT BOOL NeoTexIsMegaPart(NSDictionary *part);
/// Validates a public file link, or one selected file in a public folder.
/// Does not access the network and never accepts a folder as a whole archive.
FOUNDATION_EXPORT BOOL NeoTexMegaPublicFileURL(NSString *url);

/// Calls MEGA's anonymous public API once (twice for a selected folder file).
/// Account, blocked, quota and rate-limit errors end the attempt; no retries.
/// The URL and crypto context are transient: do not write them to disk/logs.
/// Completion is asynchronous; the caller dispatches to its own state queue.
FOUNDATION_EXPORT NeoTextureMegaRequest *NeoTexResolveMegaPart(NSDictionary *part, NSURLSession *session,
    void (^completion)(NSURL *_Nullable url, NSDictionary *_Nullable crypto, NSError *_Nullable error));

#ifdef __cplusplus
/// Decrypts a complete ciphertext cache file in place, using a fixed 2 MiB
/// working buffer. Accepts only the exact verified plaintext size and SHA-256.
/// The caller must still retain its normal final integrity/install gates.
/// A cancel, I/O error, wrong key or changed digest deletes this cache candidate
/// (never an installed pack). Ciphertext resume data must not reuse this path.
NSError *_Nullable NeoTexDecryptMegaFile(NSString *path, NSDictionary *part, NSDictionary *crypto,
                                        std::function<bool()> cancelled);
#endif

NS_ASSUME_NONNULL_END
