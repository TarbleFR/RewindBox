#import <Foundation/Foundation.h>

// Keeps the probe linked into the app and lets the MeloNX bridge find it
// without a link-time dependency: NSClassFromString(@"S2ArmProbePlugin").
@interface S2ArmProbePlugin : NSObject
+ (void)registerWithRegistrar:(id)registrar;
// rb_s2arm_probe_attached and rb_s2arm_probe_detached (S2ArmProbe.h) as pointers.
+ (void *)attachedFunction;
+ (void *)detachedFunction;
@end
