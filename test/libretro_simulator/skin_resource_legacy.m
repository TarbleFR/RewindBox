// Runs the unchanged public validation entry point against an original skin.
// Compiled with either Build 463 or the candidate renderer in an iOS app.
#import <UIKit/UIKit.h>
#import "LibretroSkinRenderer.h"
static NSDictionary *ReadFixture(NSString *file);

@interface SkinResourceDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end
@implementation SkinResourceDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  self.window.rootViewController = [UIViewController new];
  [self.window makeKeyAndVisible];
  NSString *root = [NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:@"original-dualshocked"];
  NSString *code = nil;
  LibretroSkin *skin = [LibretroSkin skinWithDirectory:root consoleGeometry:nil errorCode:&code];
  BOOL expected = [ReadFixture(@"expect.json")[@"valid"] boolValue];
  void (^finish)(BOOL) = ^(BOOL valid) {
    NSArray *checks = @[
      @{@"name":@"original archive is parsed as PlayStation", @"passed":@([skin.consoles containsObject:@"psx"])},
      @{@"name":@"both authored orientations are present", @"passed":@(skin.representations.count == 2)},
      @{@"name":@"exact renderer validation matches the expected regression verdict", @"passed":@(valid == expected)}
    ];
    NSDictionary *result = @{@"finished":@YES, @"results":@[@{@"name":@"original-dualshocked-resource-validation",
      @"valid":@(valid), @"warnings":skin.warnings ?: @[], @"checks":checks, @"parseCode":code ?: @""}]};
    NSData *data = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
    NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    [data writeToFile:[documents stringByAppendingPathComponent:@"probe.json"] atomically:YES];
  };
  if (skin) [LibretroSkinRenderer validateResourcesForSkin:skin completion:finish];
  else finish(NO);
  return YES;
}
static NSDictionary *ReadFixture(NSString *file) {
  NSData *data = [NSData dataWithContentsOfFile:[NSBundle.mainBundle.bundlePath stringByAppendingPathComponent:file]];
  return data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : @{};
}
@end
int main(int argc, char *argv[]) {
  @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(SkinResourceDelegate.class)); }
}
