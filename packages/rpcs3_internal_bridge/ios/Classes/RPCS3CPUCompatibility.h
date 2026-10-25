#pragma once
#import <Foundation/Foundation.h>
#include <sys/sysctl.h>
#include "RPCS3CPUCompatibilityPolicy.h"

static inline NSString* RPCS3CPUCompatibilityError(void) {
#if defined(__arm64__)
  const bool arm64 = true;
#else
  const bool arm64 = false;
#endif
  const bool supported = rewindbox::rpcs3::supports_core(
      rewindbox::rpcs3::bundled_core_baseline, arm64, [](const char* name) {
        int value = 0;
        size_t size = sizeof(value);
        return sysctlbyname(name, &value, &size, nullptr, 0) == 0 &&
            size == sizeof(value) && value == 1;
      });
  if (supported) return nil;
  return @"RPCS3_CPU_INCOMPATIBLE: This embedded RPCS3 Core requires ARMv8.4-A. "
      @"The device does not report the required CPU features. JIT preparation and Core loading are blocked. "
      @"An ARMv8-A compatibility Core is not bundled in this RewindBox build. Your games and saves are preserved.";
}
