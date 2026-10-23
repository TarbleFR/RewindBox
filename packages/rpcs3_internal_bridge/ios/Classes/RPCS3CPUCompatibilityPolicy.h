#pragma once

// The embedded Core is built with -march=armv8.4-a. An arm64 Mach-O slice
// alone says nothing about that ISA minimum; check before any JIT work.
namespace rewindbox::rpcs3 {
enum class cpu_baseline { armv8_a, armv8_4_a };
inline constexpr cpu_baseline bundled_core_baseline = cpu_baseline::armv8_4_a;
inline constexpr const char* armv84_features[] = {
    "hw.optional.arm.FEAT_DotProd", "hw.optional.arm.FEAT_JSCVT",
    "hw.optional.arm.FEAT_LRCPC", "hw.optional.arm.FEAT_LRCPC2",
    "hw.optional.arm.FEAT_FlagM",
};

template<class Probe>
bool supports_core(cpu_baseline baseline, bool arm64, Probe probe) {
  if (!arm64) return false;
  if (baseline == cpu_baseline::armv8_a) return true;
  for (const char* feature : armv84_features) {
    if (!probe(feature)) return false;  // Unknown/failed queries fail closed.
  }
  return true;
}
}  // namespace rewindbox::rpcs3
