#import <UIKit/UIKit.h>

// The simulator exercises the actual UIKit/Swift controls without JIT or a ROM.
extern "C" void neostation_dolphin_touch_event(int32_t port, int32_t input, float value, int32_t axis) {
  [NSUserDefaults.standardUserDefaults setObject:@[@(port), @(input), @(value), @(axis)] forKey:@"lastTouch"];
}
// The shake routing of the touch controller asks the core for its menu state;
// no core runs here: no snapshot, nothing applied.
extern "C" char* neostation_dolphin_menu_snapshot(int32_t, int32_t) { return nullptr; }
extern "C" int32_t neostation_dolphin_menu_apply(const char*) { return 0; }

@interface SessionHarnessDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation SessionHarnessDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  self.window.rootViewController = [UIViewController new];
  [self.window makeKeyAndVisible];
  return YES;
}
@end
int main(int argc, char** argv) {
  @autoreleasepool { return UIApplicationMain(argc, argv, nil, @"SessionHarnessDelegate"); }
}
