// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoExternalDisplaySceneDelegate.h"

#import "NeoExternalDisplayCoordinator.h"

@implementation NeoExternalDisplaySceneDelegate

- (void)scene:(UIScene *)scene
    willConnectToSession:(UISceneSession *)session
                 options:(UISceneConnectionOptions *)connectionOptions {
  if (![scene isKindOfClass:UIWindowScene.class]) return;
  if (![session.role isEqualToString:UIWindowSceneSessionRoleExternalDisplayNonInteractive]) {
    NSLog(@"display.external_scene_ignored role=%@", session.role);
    return;
  }
  // The coordinator builds the window (windowFactory seam or
  // -[UIWindow initWithWindowScene:]), gives it the black root controller
  // and shows it without making it key. A second external scene stands by
  // without a window of its own until the shown one disconnects.
  NeoExternalDisplayCoordinator *coordinator = NeoExternalDisplayCoordinator.shared;
  [coordinator sceneDidConnect:(UIWindowScene *)scene];
  self.window = coordinator.window.windowScene == scene ? coordinator.window : nil;
}

- (void)sceneDidDisconnect:(UIScene *)scene {
  if (![scene isKindOfClass:UIWindowScene.class]) return;
  // The render view returns to the iPhone, then the window is released.
  [NeoExternalDisplayCoordinator.shared sceneDidDisconnect:(UIWindowScene *)scene];
  self.window = nil;
}

@end
