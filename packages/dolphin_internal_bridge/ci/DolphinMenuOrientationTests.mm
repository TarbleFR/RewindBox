#import <XCTest/XCTest.h>
#import "DOLOrientation.h"
#import "DolphinSessionLifecycle.h"
#import "DolphinSessionMenu.h"

// The REAL DolphinSessionMenu, in the ordinary UINavigationController the plugin
// uses, under the application mask a portrait-only skin sets (DOLOrientation).
// Before the fix it answered Landscape only: no orientation in common with a
// portrait-only application. iOS Simulator; a simulator is not an iPhone.

@interface MenuOrientationSession : UIViewController
@end
@implementation MenuOrientationSession
- (UIInterfaceOrientationMask)supportedInterfaceOrientations {
  const UIInterfaceOrientationMask session = DOLOrientationGameMask();
  return session != 0 ? session : UIInterfaceOrientationMaskLandscape;
}
@end

@interface DolphinMenuOrientationTests : XCTestCase
@end

@implementation DolphinMenuOrientationTests

- (UIWindow*)window { return [(id)UIApplication.sharedApplication.delegate window]; }

- (UIInterfaceOrientationMask)applicationMask {
  id<UIApplicationDelegate> delegate = UIApplication.sharedApplication.delegate;
  return [delegate application:UIApplication.sharedApplication supportedInterfaceOrientationsForWindow:self.window];
}

- (void)setUp { DOLOrientationInstall(); DOLOrientationSetGameMask(0); }
- (void)tearDown { DOLOrientationSetGameMask(0); }

- (void)testRealMenuMaskFollowsTheSession {
  DolphinSessionMenu* menu = [DolphinSessionMenu new];
  UINavigationController* navigation = [[UINavigationController alloc] initWithRootViewController:menu];
  XCTAssertEqual(menu.supportedInterfaceOrientations, UIInterfaceOrientationMaskLandscape, @"no skin: unchanged landscape");
  for (NSNumber* value in @[ @(UIInterfaceOrientationMaskPortrait), @(UIInterfaceOrientationMaskLandscape),
                             @(UIInterfaceOrientationMaskAllButUpsideDown) ]) {
    DOLOrientationSetGameMask(value.unsignedIntegerValue);
    XCTAssertEqual(menu.supportedInterfaceOrientations, value.unsignedIntegerValue);
    XCTAssertEqual(navigation.supportedInterfaceOrientations, value.unsignedIntegerValue, @"the navigation forwards it");
    XCTAssertNotEqual(navigation.supportedInterfaceOrientations & [self applicationMask], 0u,
                      @"menu and application share an orientation");
  }
}

- (void)waitUntil:(BOOL (^)(void))condition description:(NSString*)description {
  XCTNSPredicateExpectation* expectation = [[XCTNSPredicateExpectation alloc]
      initWithPredicate:[NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary* bindings) { return condition(); }]
                 object:nil];
  expectation.expectationDescription = description;
  [self waitForExpectations:@[ expectation ] timeout:8];
}

// Portrait-only session from the landscape app, the real menu opened over it and
// closed (resume), then the session dismissed and the lock released.
- (void)testRealMenuOpensUprightOverAPortraitSessionAndResumes {
  UIWindow* window = self.window;
  UIViewController* frontend = window.rootViewController;
  DOLOrientationSetGameMask(UIInterfaceOrientationMaskPortrait);
  MenuOrientationSession* game = [MenuOrientationSession new];
  game.modalPresentationStyle = UIModalPresentationFullScreen;
  XCTestExpectation* presented = [self expectationWithDescription:@"session"];
  [frontend presentViewController:game animated:NO completion:^{ [presented fulfill]; }];
  [self waitForExpectations:@[ presented ] timeout:5];
  [self waitUntil:^BOOL { return window.windowScene.interfaceOrientation == UIInterfaceOrientationPortrait; }
      description:@"session upright"];

  DolphinSessionMenu* menu = [DolphinSessionMenu new];
  UINavigationController* navigation = [[UINavigationController alloc] initWithRootViewController:menu];
  XCTestExpectation* shown = [self expectationWithDescription:@"menu"];
  [game presentViewController:navigation animated:NO completion:^{ [shown fulfill]; }];
  [self waitForExpectations:@[ shown ] timeout:5];
  XCTAssertNotNil(navigation.view.window, @"the real menu is on screen");
  XCTAssertEqual(window.windowScene.interfaceOrientation, UIInterfaceOrientationPortrait, @"the menu did not turn the session");
  XCTAssertGreaterThan(navigation.view.bounds.size.height, navigation.view.bounds.size.width, @"the menu is laid out upright");

  XCTestExpectation* resumed = [self expectationWithDescription:@"resume"];
  [navigation dismissViewControllerAnimated:NO completion:^{ [resumed fulfill]; }];
  [self waitForExpectations:@[ resumed ] timeout:5];
  XCTAssertEqual(window.windowScene.interfaceOrientation, UIInterfaceOrientationPortrait, @"resumed in portrait");

  XCTestExpectation* closed = [self expectationWithDescription:@"closed"];
  DOLDismissSessionController(game, ^{
    DOLOrientationSetGameMask(0);  // what cleanupSharedResourcesAndUI does
    [closed fulfill];
  });
  [self waitForExpectations:@[ closed ] timeout:5];
  [self waitUntil:^BOOL { return (1u << window.windowScene.interfaceOrientation) & UIInterfaceOrientationMaskLandscape; }
      description:@"back to landscape"];
  XCTAssertEqual(DOLOrientationGameMask(), 0u);
}

@end
