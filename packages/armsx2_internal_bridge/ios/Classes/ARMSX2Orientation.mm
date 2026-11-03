#import "ARMSX2Orientation.h"

#import <objc/runtime.h>

typedef UIInterfaceOrientationMask (*ARMSX2OrientationIMP)(id, SEL, UIApplication *, UIWindow *);

/// Mask requested by the ARMSX2 game on screen (0: the app's own). Main
/// thread only, like every UIKit orientation query.
static UIInterfaceOrientationMask gGameMask = 0;
/// Classes that already carry NeoStation's implementation (by name).
static NSMutableSet<NSString *> *gInstalledClasses;
/// Implementations installed by this file, to recognise them later.
static NSMutableSet<NSValue *> *gInstalledImplementations;
/// The application delegate kept alive while it is re-assigned.
static id gRetainedDelegate;
static BOOL gInstalled = NO;

static SEL ARMSX2OrientationSelector(void) {
  return @selector(application:supportedInterfaceOrientationsForWindow:);
}

static UIInterfaceOrientationMask ARMSX2MaskFromNames(id names) {
  if (![names isKindOfClass:[NSArray class]]) return 0;
  UIInterfaceOrientationMask mask = 0;
  for (id name in (NSArray *)names) {
    if (![name isKindOfClass:[NSString class]]) continue;
    if ([name isEqualToString:@"UIInterfaceOrientationPortrait"]) {
      mask |= UIInterfaceOrientationMaskPortrait;
    } else if ([name isEqualToString:@"UIInterfaceOrientationPortraitUpsideDown"]) {
      mask |= UIInterfaceOrientationMaskPortraitUpsideDown;
    } else if ([name isEqualToString:@"UIInterfaceOrientationLandscapeLeft"]) {
      mask |= UIInterfaceOrientationMaskLandscapeLeft;
    } else if ([name isEqualToString:@"UIInterfaceOrientationLandscapeRight"]) {
      mask |= UIInterfaceOrientationMaskLandscapeRight;
    }
  }
  return mask;
}

/// What the app supported before NeoStation's method existed: the
/// Info.plist orientations (the ~ipad key first on iPad), as UIKit reads
/// them when the delegate does not answer.
static UIInterfaceOrientationMask ARMSX2InfoPlistMask(void) {
  static UIInterfaceOrientationMask mask = 0;
  static BOOL resolved = NO;
  if (resolved) return mask;
  NSDictionary<NSString *, id> *info = NSBundle.mainBundle.infoDictionary;
  BOOL iPad = UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad;
  UIInterfaceOrientationMask value = 0;
  if (iPad) value = ARMSX2MaskFromNames(info[@"UISupportedInterfaceOrientations~ipad"]);
  if (value == 0) value = ARMSX2MaskFromNames(info[@"UISupportedInterfaceOrientations"]);
  if (value == 0) value = iPad ? UIInterfaceOrientationMaskAll : UIInterfaceOrientationMaskAllButUpsideDown;
  mask = value;
  resolved = YES;
  return mask;
}

static void ARMSX2RememberImplementation(IMP implementation) {
  if (implementation == NULL) return;
  if (gInstalledImplementations == nil) gInstalledImplementations = [NSMutableSet set];
  [gInstalledImplementations addObject:[NSValue valueWithPointer:(const void *)implementation]];
}

static BOOL ARMSX2IsOurImplementation(IMP implementation) {
  if (implementation == NULL || gInstalledImplementations == nil) return NO;
  return [gInstalledImplementations containsObject:[NSValue valueWithPointer:(const void *)implementation]];
}

/// Gives `cls` NeoStation's application:supportedInterfaceOrientationsForWindow:.
/// - `cls` implements it itself: its implementation is wrapped (the game
///   mask wins, else the original answers);
/// - a superclass implements it: a method added to `cls` asks the
///   superclass's implementation when no game asks for more;
/// - nobody implements it: the added method answers the Info.plist mask.
/// Each wrapper captures its own original, so implementations that call
/// super never loop.
static BOOL ARMSX2InstallOnClass(Class cls) {
  if (cls == Nil) return NO;
  NSString *name = NSStringFromClass(cls);
  if (gInstalledClasses == nil) gInstalledClasses = [NSMutableSet set];
  if ([gInstalledClasses containsObject:name]) return YES;
  SEL selector = ARMSX2OrientationSelector();
  // "-[UIApplicationDelegate application:supportedInterfaceOrientationsForWindow:]":
  // returns NSUInteger, takes id self, SEL, id application, id window.
  const char *types = "Q@:@@";
  Method own = NULL;
  unsigned int count = 0;
  Method *methods = class_copyMethodList(cls, &count);
  for (unsigned int index = 0; index < count; index++) {
    if (method_getName(methods[index]) == selector) {
      own = methods[index];
      break;
    }
  }
  free(methods);

  IMP replacement = NULL;
  if (own != NULL) {
    ARMSX2OrientationIMP original = (ARMSX2OrientationIMP)method_getImplementation(own);
    if (ARMSX2IsOurImplementation((IMP)original)) {
      [gInstalledClasses addObject:name];
      return YES;
    }
    replacement = imp_implementationWithBlock(^UIInterfaceOrientationMask(id receiver, UIApplication *application,
                                                                          UIWindow *window) {
      UIInterfaceOrientationMask game = gGameMask;
      if (game != 0) return game;
      return original(receiver, selector, application, window);
    });
    method_setImplementation(own, replacement);
  } else {
    Method inherited = class_getInstanceMethod(cls, selector);
    ARMSX2OrientationIMP superImplementation =
        inherited != NULL ? (ARMSX2OrientationIMP)method_getImplementation(inherited) : NULL;
    if (superImplementation != NULL && ARMSX2IsOurImplementation((IMP)superImplementation)) {
      // A superclass already carries NeoStation's method.
      [gInstalledClasses addObject:name];
      return YES;
    }
    if (inherited != NULL && method_getTypeEncoding(inherited) != NULL) types = method_getTypeEncoding(inherited);
    replacement = imp_implementationWithBlock(^UIInterfaceOrientationMask(id receiver, UIApplication *application,
                                                                          UIWindow *window) {
      UIInterfaceOrientationMask game = gGameMask;
      if (game != 0) return game;
      if (superImplementation != NULL) return superImplementation(receiver, selector, application, window);
      return ARMSX2InfoPlistMask();
    });
    if (!class_addMethod(cls, selector, replacement, types)) {
      imp_removeBlock(replacement);
      return NO;
    }
  }
  ARMSX2RememberImplementation(replacement);
  [gInstalledClasses addObject:name];
  return YES;
}

/// Installed while the bridge framework loads, before UIApplicationMain
/// creates and assigns the application delegate (UIKit caches what the
/// delegate responds to at that moment). Flutter.framework is a dependency
/// of the bridge, so it is already loaded here.
@interface ARMSX2OrientationLoader : NSObject
@end

@implementation ARMSX2OrientationLoader

+ (void)load {
  Class flutterDelegate = NSClassFromString(@"FlutterAppDelegate");
  if (flutterDelegate != Nil && ARMSX2InstallOnClass(flutterDelegate)) gInstalled = YES;
}

@end

void ARMSX2OrientationInstall(void) {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{
      ARMSX2OrientationInstall();
    });
    return;
  }
  UIApplication *application = UIApplication.sharedApplication;
  id<UIApplicationDelegate> delegate = application.delegate;
  if (delegate == nil) return;
  Class cls = [(NSObject *)delegate class];
  SEL selector = ARMSX2OrientationSelector();
  IMP current = class_getMethodImplementation(cls, selector);
  BOOL answers = [(NSObject *)delegate respondsToSelector:selector];
  if (answers && ARMSX2IsOurImplementation(current)) {
    // Installed at +load on FlutterAppDelegate (or earlier here).
    gInstalled = YES;
    return;
  }
  if (!ARMSX2InstallOnClass(cls)) return;
  gInstalled = YES;
  // UIKit read the delegate's capabilities when it was assigned: assign it
  // again so the new method is seen. The strong reference keeps it alive
  // while the property is briefly nil.
  gRetainedDelegate = delegate;
  application.delegate = nil;
  application.delegate = gRetainedDelegate;
}

static void ARMSX2RefreshSupportedOrientations(void) {
  if (@available(iOS 16.0, *)) {
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
      if (![scene isKindOfClass:[UIWindowScene class]]) continue;
      for (UIWindow *window in ((UIWindowScene *)scene).windows) {
        UIViewController *root = window.rootViewController;
        if (root == nil) continue;
        [root setNeedsUpdateOfSupportedInterfaceOrientations];
        UIViewController *presented = root.presentedViewController;
        while (presented != nil) {
          [presented setNeedsUpdateOfSupportedInterfaceOrientations];
          presented = presented.presentedViewController;
        }
      }
    }
  }
}

void ARMSX2OrientationSetGameMask(UIInterfaceOrientationMask mask) {
  if (!NSThread.isMainThread) {
    dispatch_async(dispatch_get_main_queue(), ^{
      ARMSX2OrientationSetGameMask(mask);
    });
    return;
  }
  if (gGameMask == mask) return;
  gGameMask = mask;
  ARMSX2RefreshSupportedOrientations();
}

UIInterfaceOrientationMask ARMSX2OrientationGameMask(void) {
  return gGameMask;
}

BOOL ARMSX2OrientationIsInstalled(void) {
  return gInstalled;
}
