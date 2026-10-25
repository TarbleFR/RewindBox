// SPDX-License-Identifier: GPL-3.0-or-later
// Host application of the Build 484 touch-layout UIKit tests: one full-screen
// window whose root controller follows the device orientation, like a game
// session (status bar hidden).
#import <UIKit/UIKit.h>

@interface TLRootViewController : UIViewController
@end

@implementation TLRootViewController
- (UIInterfaceOrientationMask)supportedInterfaceOrientations {
  return UIInterfaceOrientationMaskAllButUpsideDown;
}
- (BOOL)prefersStatusBarHidden {
  return YES;
}
@end

@interface TLAppDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow* window;
@end

@implementation TLAppDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  TLRootViewController* root = [TLRootViewController new];
  root.view.backgroundColor = UIColor.blackColor;
  self.window.rootViewController = root;
  [self.window makeKeyAndVisible];
  return YES;
}
@end

int main(int argc, char** argv) {
  @autoreleasepool {
    return UIApplicationMain(argc, argv, nil, NSStringFromClass(TLAppDelegate.class));
  }
}
