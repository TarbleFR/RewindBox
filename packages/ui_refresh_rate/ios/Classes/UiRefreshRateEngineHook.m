#import "UiRefreshRateEngineHook.h"

#import <objc/message.h>
#import <objc/runtime.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

NSString *const NeoUiRefreshPreferenceKey = @"NeoStation.UI.HighRefreshRate.Enabled";
const BOOL NeoUiRefreshDefaultEnabled = YES;
const double NeoUiRefreshCappedHz = 60.0;
const char NeoUiRefreshExpectedTypeEncoding[] = "d16@0:8";

/// Objective-C name of the Swift class `DisplayLinkManager` in Flutter.framework
/// (`@objc(FlutterDisplayLinkManager)`, Flutter 3.47.2).
static const char *const kNeoUiRefreshEngineClass = "FlutterDisplayLinkManager";
static const char *const kNeoUiRefreshEngineSelector = "displayRefreshRate";

typedef double (*NeoUiRefreshRateIMP)(id, SEL);

/// The engine's own implementation, captured before the replacement.
static NeoUiRefreshRateIMP gNeoUiRefreshOriginal = NULL;
static NeoUiRefreshHookStatus gNeoUiRefreshStatus = NeoUiRefreshHookStatusNotInstalled;
static BOOL gNeoUiRefreshActive = YES;
static dispatch_once_t gNeoUiRefreshActiveOnce;

double NeoUiRefreshPolicy(double engineHz, BOOL enabled) {
  // NaN, zero and negative values are the engine's "unknown": keep them so
  // its own fallbacks (60 Hz) still apply.
  if (!(engineHz > 0)) return engineHz;
  if (enabled) return engineHz;
  return engineHz < NeoUiRefreshCappedHz ? engineHz : NeoUiRefreshCappedHz;
}

BOOL NeoUiRefreshStoredEnabled(void) {
  id value = [NSUserDefaults.standardUserDefaults objectForKey:NeoUiRefreshPreferenceKey];
  if ([value isKindOfClass:NSNumber.class] || [value isKindOfClass:NSString.class]) {
    return [value boolValue];
  }
  return NeoUiRefreshDefaultEnabled;
}

BOOL NeoUiRefreshStoreEnabled(BOOL enabled) {
  NSUserDefaults *defaults = NSUserDefaults.standardUserDefaults;
  [defaults setBool:enabled forKey:NeoUiRefreshPreferenceKey];
  id stored = [defaults objectForKey:NeoUiRefreshPreferenceKey];
  return [stored isKindOfClass:NSNumber.class] && [stored boolValue] == enabled;
}

BOOL NeoUiRefreshActiveEnabled(void) {
  dispatch_once(&gNeoUiRefreshActiveOnce, ^{
    gNeoUiRefreshActive = NeoUiRefreshStoredEnabled();
  });
  return gNeoUiRefreshActive;
}

/// Replacement of `+[FlutterDisplayLinkManager displayRefreshRate]`. The
/// engine calls it from the main thread (Metal layer, vsync waiter: merged
/// platform/UI thread) and possibly from the raster thread; it only reads
/// immutable state after +load.
static double NeoUiRefreshReplacement(id receiver, SEL selector) {
  NeoUiRefreshRateIMP original = gNeoUiRefreshOriginal;
  double engineHz = original != NULL ? original(receiver, selector) : 0;
  return NeoUiRefreshPolicy(engineHz, NeoUiRefreshActiveEnabled());
}

/// The method declared by the class itself (not inherited), or NULL.
static Method NeoUiRefreshOwnClassMethod(Class cls, SEL selector) {
  // class_getClassMethod realizes the Swift class and its metaclass first.
  if (class_getClassMethod(cls, selector) == NULL) return NULL;
  Class meta = object_getClass(cls);
  if (meta == Nil) return NULL;
  unsigned int count = 0;
  Method *methods = class_copyMethodList(meta, &count);
  Method found = NULL;
  for (unsigned int index = 0; index < count; index++) {
    if (method_getName(methods[index]) == selector) {
      found = methods[index];
      break;
    }
  }
  free(methods);
  return found;
}

void NeoUiRefreshInstallEngineHook(void) {
  if (gNeoUiRefreshStatus == NeoUiRefreshHookStatusInstalled) return;
  Class cls = objc_getClass(kNeoUiRefreshEngineClass);
  if (cls == Nil) {
    gNeoUiRefreshStatus = NeoUiRefreshHookStatusClassMissing;
    return;
  }
  SEL selector = sel_registerName(kNeoUiRefreshEngineSelector);
  Method method = NeoUiRefreshOwnClassMethod(cls, selector);
  if (method == NULL) {
    gNeoUiRefreshStatus = NeoUiRefreshHookStatusMethodMissing;
    return;
  }
  const char *types = method_getTypeEncoding(method);
  if (types == NULL || strcmp(types, NeoUiRefreshExpectedTypeEncoding) != 0) {
    gNeoUiRefreshStatus = NeoUiRefreshHookStatusSignatureMismatch;
    return;
  }
  IMP current = method_getImplementation(method);
  if (current != (IMP)NeoUiRefreshReplacement) {
    // Capture the original before publishing the replacement, so no call can
    // observe the replacement without an original.
    gNeoUiRefreshOriginal = (NeoUiRefreshRateIMP)current;
    IMP previous = method_setImplementation(method, (IMP)NeoUiRefreshReplacement);
    if (previous != current && previous != (IMP)NeoUiRefreshReplacement) {
      gNeoUiRefreshOriginal = (NeoUiRefreshRateIMP)previous;
    }
  }
  gNeoUiRefreshStatus = NeoUiRefreshHookStatusInstalled;
}

NeoUiRefreshHookStatus NeoUiRefreshCurrentHookStatus(void) {
  return gNeoUiRefreshStatus;
}

NSString *NeoUiRefreshHookStatusName(NeoUiRefreshHookStatus status) {
  switch (status) {
    case NeoUiRefreshHookStatusInstalled:
      return @"installed";
    case NeoUiRefreshHookStatusClassMissing:
      return @"classMissing";
    case NeoUiRefreshHookStatusMethodMissing:
      return @"methodMissing";
    case NeoUiRefreshHookStatusSignatureMismatch:
      return @"signatureMismatch";
    case NeoUiRefreshHookStatusNotInstalled:
      break;
  }
  return @"notInstalled";
}

double NeoUiRefreshEngineTargetHz(void) {
  Class cls = objc_getClass(kNeoUiRefreshEngineClass);
  SEL selector = sel_registerName(kNeoUiRefreshEngineSelector);
  if (cls == Nil || class_getClassMethod(cls, selector) == NULL) return 0;
  return ((double (*)(id, SEL))objc_msgSend)((id)cls, selector);
}

#ifdef NEO_UI_REFRESH_TESTING
NeoUiRefreshRateFunction NeoUiRefreshTestingSwapOriginal(NeoUiRefreshRateFunction original) {
  NeoUiRefreshRateIMP previous = gNeoUiRefreshOriginal;
  gNeoUiRefreshOriginal = original;
  return previous;
}

void NeoUiRefreshTestingSetActiveEnabled(BOOL enabled) {
  (void)NeoUiRefreshActiveEnabled();
  gNeoUiRefreshActive = enabled;
}
#endif
