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

// The real menu answers the session mask. The plugin wraps it in an ordinary
// UINavigationController (DolphinInternalBridgePlugin.mm, presentSessionMenu),
// which does NOT forward its child's mask: it answers its own default (30,
// observed in run 41746963325). What UIKit applies to that presentation is the
// container's mask intersected with the application mask (DOLOrientation), so
// the EFFECTIVE mask is what must equal the session's: checked for no skin,
// portrait only, landscape only and both.
- (void)testRealMenuMaskFollowsTheSession {
  DolphinSessionMenu* menu = [DolphinSessionMenu new];
  UINavigationController* navigation = [[UINavigationController alloc] initWithRootViewController:menu];
  navigation.modalPresentationStyle = UIModalPresentationOverFullScreen;
  navigation.modalInPresentation = YES;
  XCTAssertEqual(menu.supportedInterfaceOrientations, UIInterfaceOrientationMaskLandscape, @"no skin: unchanged landscape");
  XCTAssertEqual(navigation.supportedInterfaceOrientations & [self applicationMask], UIInterfaceOrientationMaskLandscape,
                 @"no skin: the menu stays landscape like the landscape-only app");
  for (NSNumber* value in @[ @(UIInterfaceOrientationMaskPortrait), @(UIInterfaceOrientationMaskLandscape),
                             @(UIInterfaceOrientationMaskAllButUpsideDown) ]) {
    const UIInterfaceOrientationMask session = value.unsignedIntegerValue;
    DOLOrientationSetGameMask(session);
    XCTAssertEqual(menu.supportedInterfaceOrientations, session, @"the real menu answers the session mask");
    XCTAssertEqual(navigation.supportedInterfaceOrientations & [self applicationMask], session,
                   @"effective mask of the presented container (container & application) is the session's");
  }
}

- (void)waitUntil:(BOOL (^)(void))condition description:(NSString*)description {
  XCTNSPredicateExpectation* expectation = [[XCTNSPredicateExpectation alloc]
      initWithPredicate:[NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary* bindings) { return condition(); }]
                 object:nil];
  expectation.expectationDescription = description;
  [self waitForExpectations:@[ expectation ] timeout:8];
}

// A session with `mask` presented from the landscape app, the real menu opened
// over it the way the plugin does (ordinary navigation, OverFullScreen,
// modalInPresentation), a page pushed and popped, the menu closed (resume),
// then the session dismissed and the lock released.
- (void)runSessionWithMask:(UIInterfaceOrientationMask)mask name:(NSString*)name {
  UIWindow* window = self.window;
  UIViewController* frontend = window.rootViewController;
  XCTAssertNil(frontend.presentedViewController, @"%@: clean start", name);
  DOLOrientationSetGameMask(mask);
  MenuOrientationSession* game = [MenuOrientationSession new];
  game.modalPresentationStyle = UIModalPresentationFullScreen;
  XCTestExpectation* presented = [self expectationWithDescription:@"session"];
  [frontend presentViewController:game animated:NO completion:^{ [presented fulfill]; }];
  [self waitForExpectations:@[ presented ] timeout:5];
  [self waitUntil:^BOOL { return ((1u << window.windowScene.interfaceOrientation) & mask) != 0; }
      description:[name stringByAppendingString:@": session in an allowed orientation"]];
  const UIInterfaceOrientation sessionOrientation = window.windowScene.interfaceOrientation;

  DolphinSessionMenu* menu = [DolphinSessionMenu new];
  UINavigationController* navigation = [[UINavigationController alloc] initWithRootViewController:menu];
  navigation.modalPresentationStyle = UIModalPresentationOverFullScreen;
  navigation.modalInPresentation = YES;
  XCTestExpectation* shown = [self expectationWithDescription:@"menu"];
  [game presentViewController:navigation animated:YES completion:^{ [shown fulfill]; }];
  [self waitForExpectations:@[ shown ] timeout:5];
  XCTAssertNotNil(navigation.view.window, @"%@: the real menu is on screen", name);
  XCTAssertEqual(window.windowScene.interfaceOrientation, sessionOrientation, @"%@: the menu did not turn the session", name);
  XCTAssertTrue(((1u << window.windowScene.interfaceOrientation) & mask) != 0, @"%@: menu in an allowed orientation", name);
  if (mask == UIInterfaceOrientationMaskPortrait) {
    XCTAssertEqual(window.windowScene.interfaceOrientation, UIInterfaceOrientationPortrait, @"%@: upright", name);
    XCTAssertGreaterThan(navigation.view.bounds.size.height, navigation.view.bounds.size.width, @"%@: menu laid out upright", name);
  } else if (mask == UIInterfaceOrientationMaskLandscape) {
    XCTAssertGreaterThan(navigation.view.bounds.size.width, navigation.view.bounds.size.height, @"%@: menu laid out sideways", name);
  }

  UIViewController* page = [UIViewController new];
  [navigation pushViewController:page animated:NO];
  XCTAssertEqual(navigation.topViewController, page);
  XCTAssertEqual(window.windowScene.interfaceOrientation, sessionOrientation, @"%@: push keeps the orientation", name);
  [navigation popViewControllerAnimated:NO];
  XCTAssertEqual(navigation.topViewController, menu);
  XCTAssertEqual(window.windowScene.interfaceOrientation, sessionOrientation, @"%@: pop keeps the orientation", name);

  XCTestExpectation* resumed = [self expectationWithDescription:@"resume"];
  [navigation dismissViewControllerAnimated:YES completion:^{ [resumed fulfill]; }];
  [self waitForExpectations:@[ resumed ] timeout:5];
  XCTAssertEqual(window.windowScene.interfaceOrientation, sessionOrientation, @"%@: resumed in the same orientation", name);
  XCTAssertNotNil(game.view.window, @"%@: the session is still on screen", name);

  XCTestExpectation* closed = [self expectationWithDescription:@"closed"];
  DOLDismissSessionController(game, ^{
    DOLOrientationSetGameMask(0);  // what cleanupSharedResourcesAndUI does
    [closed fulfill];
  });
  [self waitForExpectations:@[ closed ] timeout:5];
  [self waitUntil:^BOOL { return ((1u << window.windowScene.interfaceOrientation) & UIInterfaceOrientationMaskLandscape) != 0; }
      description:[name stringByAppendingString:@": back to landscape"]];
  XCTAssertEqual(DOLOrientationGameMask(), 0u, @"%@: no residual lock", name);
  XCTAssertEqual([self applicationMask], UIInterfaceOrientationMaskLandscape, @"%@: the app's own mask again", name);
}

- (void)testRealMenuOpensUprightOverAPortraitSessionAndResumes {
  [self runSessionWithMask:UIInterfaceOrientationMaskPortrait name:@"portrait only"];
}

- (void)testRealMenuOverALandscapeOnlySessionAndResumes {
  [self runSessionWithMask:UIInterfaceOrientationMaskLandscape name:@"landscape only"];
}

- (void)testRealMenuOverABothOrientationsSessionAndResumes {
  [self runSessionWithMask:UIInterfaceOrientationMaskAllButUpsideDown name:@"both"];
}

@end
