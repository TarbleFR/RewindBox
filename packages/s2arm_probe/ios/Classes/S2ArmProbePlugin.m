#import "S2ArmProbePlugin.h"
#import "S2ArmProbe.h"

@implementation S2ArmProbePlugin
+ (void)registerWithRegistrar:(id)registrar {
}
+ (void *)attachedFunction {
  return (void *)&rb_s2arm_probe_attached;
}
+ (void *)detachedFunction {
  return (void *)&rb_s2arm_probe_detached;
}
@end
