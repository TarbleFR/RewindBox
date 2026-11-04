#import <UIKit/UIKit.h>

// A landscape-only host (like RewindBox) for the Dolphin orientation tests in the iOS Simulator.
@interface DolphinOrientationHarnessDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation DolphinOrientationHarnessDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  self.window.rootViewController = [UIViewController new];
  [self.window makeKeyAndVisible];
  return YES;
}
@end
int main(int argc, char** argv) {
  @autoreleasepool { return UIApplicationMain(argc, argv, nil, @"DolphinOrientationHarnessDelegate"); }
}
