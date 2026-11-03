#import <XCTest/XCTest.h>
#import "DOLOrientation.h"
#import "DolphinSessionLifecycle.h"

// The harness app is landscape only (Info.plist), like RewindBox. These tests
// run the production coordinator (DOLOrientation) and the production teardown
// (DOLDismissSessionController) in the iOS Simulator. The game controller is a stand-in that answers the session's mask
// like DOLDolphinViewController does: the real one needs the Dolphin core.
// A simulator is not an iPhone.

@interface OrientationStandInSession : UIViewController
@end
@implementation OrientationStandInSession
- (UIInterfaceOrientationMask)supportedInterfaceOrientations {
  const UIInterfaceOrientationMask session = DOLOrientationGameMask();
  return session != 0 ? session : UIInterfaceOrientationMaskLandscape;
}
@end

@interface DolphinOrientationTests : XCTestCase
@end

@implementation DolphinOrientationTests

- (UIWindow*)window { return [(id)UIApplication.sharedApplication.delegate window]; }

- (UIInterfaceOrientationMask)applicationMask {
  id<UIApplicationDelegate> delegate = UIApplication.sharedApplication.delegate;
  return [delegate application:UIApplication.sharedApplication supportedInterfaceOrientationsForWindow:self.window];
}

- (void)setUp {
  DOLOrientationInstall();
  DOLOrientationSetGameMask(0);
}

- (void)tearDown {
  DOLOrientationSetGameMask(0);
}

- (void)testApplicationMaskFollowsTheSessionAndComesBack {
  XCTAssertEqual([self applicationMask], UIInterfaceOrientationMaskLandscape, @"app default: the plist's landscape");
  DOLOrientationSetGameMask(UIInterfaceOrientationMaskPortrait);
  XCTAssertEqual([self applicationMask], UIInterfaceOrientationMaskPortrait);
  DOLOrientationSetGameMask(UIInterfaceOrientationMaskAllButUpsideDown);
  XCTAssertEqual([self applicationMask], UIInterfaceOrientationMaskAllButUpsideDown);
  DOLOrientationSetGameMask(0);
  XCTAssertEqual([self applicationMask], UIInterfaceOrientationMaskLandscape, @"released: the app's own again");
}

- (void)waitForOrientation:(UIInterfaceOrientationMask)mask description:(NSString*)description {
  UIWindow* window = self.window;
  XCTNSPredicateExpectation* expectation = [[XCTNSPredicateExpectation alloc]
      initWithPredicate:[NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary* bindings) {
        return (1 << window.windowScene.interfaceOrientation) & mask;
      }] object:nil];
  expectation.expectationDescription = description;
  [self waitForExpectations:@[expectation] timeout:8];
}

// Portrait-only session: the mask is set BEFORE the presentation, the session
// opens upright from a landscape app, its menu can be opened and closed,
// and the release in the dismissal completion brings the app back to landscape.
// Run twice: a relaunch finds no residual lock.
- (void)testPortraitSessionOpensUprightMenuWorksAndTheLockIsReleased {
  for (NSInteger launch = 0; launch < 2; ++launch) {
    UIViewController* frontend = self.window.rootViewController;
    XCTAssertNil(frontend.presentedViewController);
    DOLOrientationSetGameMask(UIInterfaceOrientationMaskPortrait);
    OrientationStandInSession* game = [OrientationStandInSession new];
    game.modalPresentationStyle = UIModalPresentationFullScreen;
    XCTestExpectation* presented = [self expectationWithDescription:@"presented"];
    [frontend presentViewController:game animated:NO completion:^{ [presented fulfill]; }];
    [self waitForExpectations:@[presented] timeout:5];
    [self waitForOrientation:UIInterfaceOrientationMaskPortrait description:@"the session turned upright"];
    XCTAssertGreaterThan(game.view.bounds.size.height, game.view.bounds.size.width, @"the surface is portrait-sized");

    // A stand-in for the session menu: an ordinary navigation controller whose root follows the session mask,
    // like DolphinSessionMenu (its mask is checked in the source contract; the real one needs the pods).
    OrientationStandInSession* menuRoot = [OrientationStandInSession new];
    UINavigationController* menu = [[UINavigationController alloc] initWithRootViewController:menuRoot];
    menu.modalPresentationStyle = UIModalPresentationOverFullScreen;
    XCTestExpectation* menuShown = [self expectationWithDescription:@"menu"];
    [game presentViewController:menu animated:NO completion:^{ [menuShown fulfill]; }];
    [self waitForExpectations:@[menuShown] timeout:5];
    XCTAssertNotNil(menu.view.window);
    XCTAssertGreaterThan(menu.view.bounds.size.height, menu.view.bounds.size.width, @"the menu stays upright");

    XCTestExpectation* dismissed = [self expectationWithDescription:@"dismissed"];
    DOLDismissSessionController(game, ^{
      DOLOrientationSetGameMask(0);  // what cleanupSharedResourcesAndUI does
      [dismissed fulfill];
    });
    [self waitForExpectations:@[dismissed] timeout:5];
    XCTAssertEqual(DOLOrientationGameMask(), 0u, @"no residual lock");
    [self waitForOrientation:UIInterfaceOrientationMaskLandscape description:@"the app is back in landscape"];
    XCTAssertEqual([self applicationMask], UIInterfaceOrientationMaskLandscape);
  }
}

// A launch that fails after the mask is set goes through the same release.
- (void)testFailedLaunchReleasesTheLockWithoutAnythingPresented {
  DOLOrientationSetGameMask(UIInterfaceOrientationMaskPortrait);
  XCTestExpectation* done = [self expectationWithDescription:@"released"];
  DOLDismissSessionController(nil, ^{
    DOLOrientationSetGameMask(0);
    [done fulfill];
  });
  [self waitForExpectations:@[done] timeout:5];
  XCTAssertEqual(DOLOrientationGameMask(), 0u);
  XCTAssertEqual([self applicationMask], UIInterfaceOrientationMaskLandscape);
}

@end
