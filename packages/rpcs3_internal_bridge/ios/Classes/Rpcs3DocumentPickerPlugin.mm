#import "Rpcs3DocumentPickerPlugin.h"

static NSString* const kRpcs3DocumentsChannel = @"neostation/rpcs3_documents";

@interface Rpcs3DocumentPickerPlugin () <UIAdaptivePresentationControllerDelegate>
@property(nonatomic, strong) FlutterMethodChannel* channel;
@property(nonatomic, copy) FlutterResult pendingResult;
@property(nonatomic, assign) BOOL pickingFolder;
@property(nonatomic, strong) NSMutableArray<NSURL*>* activeURLs;
@property(nonatomic, strong) NSMutableSet<NSString*>* scopedPaths;
@end

@implementation Rpcs3DocumentPickerPlugin

+ (void)registerWithRegistrar:(NSObject<FlutterPluginRegistrar>*)registrar {
  FlutterMethodChannel* channel = [FlutterMethodChannel
      methodChannelWithName:kRpcs3DocumentsChannel
            binaryMessenger:registrar.messenger];
  Rpcs3DocumentPickerPlugin* instance = [Rpcs3DocumentPickerPlugin new];
  instance.channel = channel;
  instance.activeURLs = [NSMutableArray new];
  instance.scopedPaths = [NSMutableSet new];
  [registrar addMethodCallDelegate:instance channel:channel];
}

// The window the picker is presented from: a visible window of a foreground
// scene (any scene when none is active yet), the key one first. Same rule as
// the folder picker of external_folder_access.
static UIWindow* RPCS3DocumentsPresentingWindow(void) {
  NSMutableArray<UIWindow*>* active = [NSMutableArray new];
  NSMutableArray<UIWindow*>* any = [NSMutableArray new];
  for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
    if (![scene isKindOfClass:UIWindowScene.class]) continue;
    for (UIWindow* window in ((UIWindowScene*)scene).windows) {
      if (window.hidden || window.rootViewController == nil) continue;
      [any addObject:window];
      if (scene.activationState == UISceneActivationStateForegroundActive) {
        [active addObject:window];
      }
    }
  }
  NSArray<UIWindow*>* usable = active.count > 0 ? active : any;
  for (UIWindow* window in usable) {
    if (window.isKeyWindow) return window;
  }
  for (UIWindow* window in usable) {
    if (window.windowLevel == UIWindowLevelNormal) return window;
  }
  return usable.firstObject;
}

// The controller to present from. A controller that is being dismissed
// cannot present: the walk stops below it.
static UIViewController* RPCS3DocumentsRootController(void) {
  UIViewController* controller = RPCS3DocumentsPresentingWindow().rootViewController;
  while (controller.presentedViewController != nil &&
         !controller.presentedViewController.isBeingDismissed) {
    controller = controller.presentedViewController;
  }
  return controller;
}

// Whether a document picker is shown right now, anywhere in the presented
// chain (something may be presented above it), and not on its way out.
static BOOL RPCS3DocumentPickerIsOnScreen(void) {
  UIViewController* controller = RPCS3DocumentsPresentingWindow().rootViewController;
  while (controller.presentedViewController != nil) {
    UIViewController* presented = controller.presentedViewController;
    if ([presented isKindOfClass:UIDocumentPickerViewController.class] &&
        !presented.isBeingDismissed) {
      return YES;
    }
    controller = presented;
  }
  return NO;
}

- (void)releaseScopedResources {
  for (NSURL* url in self.activeURLs) {
    if ([self.scopedPaths containsObject:url.path]) {
      [url stopAccessingSecurityScopedResource];
    }
  }
  [self.activeURLs removeAllObjects];
  [self.scopedPaths removeAllObjects];
}

- (void)presentPickerForFolder:(BOOL)folder result:(FlutterResult)result {
  if (self.pendingResult != nil && RPCS3DocumentPickerIsOnScreen()) {
    result([FlutterError errorWithCode:@"PICKER_BUSY"
                                 message:@"Another RPCS3 document picker is already open."
                                 details:nil]);
    return;
  }
  UIViewController* root = RPCS3DocumentsRootController();
  if (!root) {
    // Nothing to present from (no window yet): a pick that may still be
    // shown is left alone, only this request is refused.
    result([FlutterError errorWithCode:@"NO_ROOT_VC"
                               message:@"No view controller is available for the RPCS3 picker."
                               details:nil]);
    return;
  }
  if (self.pendingResult != nil) {
    // The previous picker sheet went away without a delegate call: its
    // caller is answered as cancelled (left pending, it waited forever and
    // its button stayed disabled), then this pick goes on.
    FlutterResult stale = self.pendingResult;
    self.pendingResult = nil;
    stale(nil);
  }

  [self releaseScopedResources];
  self.pendingResult = result;
  self.pickingFolder = folder;

  NSArray<NSString*>* types = folder ? @[@"public.folder"] : @[@"public.data"];
  UIDocumentPickerViewController* picker =
      [[UIDocumentPickerViewController alloc] initWithDocumentTypes:types
                                                             inMode:UIDocumentPickerModeOpen];
  picker.delegate = self;
  picker.presentationController.delegate = self;
  picker.allowsMultipleSelection = !folder;
  [root presentViewController:picker animated:YES completion:nil];
}

- (void)handleMethodCall:(FlutterMethodCall*)call result:(FlutterResult)result {
  if ([call.method isEqualToString:@"pickGameFiles"]) {
    [self presentPickerForFolder:NO result:result];
    return;
  }
  if ([call.method isEqualToString:@"pickGameFolder"]) {
    [self presentPickerForFolder:YES result:result];
    return;
  }
  if ([call.method isEqualToString:@"releaseScopedResources"]) {
    [self releaseScopedResources];
    result(@YES);
    return;
  }
  result(FlutterMethodNotImplemented);
}

- (void)documentPicker:(UIDocumentPickerViewController*)controller
 didPickDocumentsAtURLs:(NSArray<NSURL*>*)urls {
  FlutterResult callback = self.pendingResult;
  self.pendingResult = nil;
  if (!callback) return;
  if (urls.count == 0) {
    callback(nil);
    return;
  }

  NSMutableArray<NSString*>* paths = [NSMutableArray new];
  for (NSURL* url in urls) {
    BOOL scoped = [url startAccessingSecurityScopedResource];
    [self.activeURLs addObject:url];
    if (scoped) [self.scopedPaths addObject:url.path];
    if (url.path.length > 0) [paths addObject:url.path];
  }

  if (self.pickingFolder) {
    if (paths.firstObject == nil) {
      callback([FlutterError errorWithCode:@"EMPTY_PATH"
                                   message:@"The picker returned an empty path."
                                   details:nil]);
      return;
    }
    callback(paths.firstObject);
  } else {
    callback(paths);
  }
}

- (void)documentPickerWasCancelled:(UIDocumentPickerViewController*)controller {
  FlutterResult callback = self.pendingResult;
  self.pendingResult = nil;
  if (callback) callback(nil);
}

- (void)presentationControllerDidDismiss:(UIPresentationController*)presentationController {
  FlutterResult callback = self.pendingResult;
  self.pendingResult = nil;
  if (callback) callback(nil);
}

- (void)dealloc {
  [self releaseScopedResources];
}

@end
