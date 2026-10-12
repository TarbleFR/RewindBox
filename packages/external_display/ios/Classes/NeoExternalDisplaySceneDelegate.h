// SPDX-License-Identifier: GPL-3.0-or-later
// UIWindowSceneDelegate of the external, non-interactive scene role
// (docs/external-display-universal.md § 3.4). Named by the host's
// Info.plist (build-utils/configure_external_display_ios.py:
// UISceneDelegateClassName = NeoExternalDisplaySceneDelegate) and resolved
// by UIKit in this dynamic framework, loaded before main.
#pragma once
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@interface NeoExternalDisplaySceneDelegate : UIResponder <UIWindowSceneDelegate>
/// The coordinator's window on the external screen (never made key).
@property(nonatomic, strong, nullable) UIWindow *window;
@end

NS_ASSUME_NONNULL_END
