// SPDX-License-Identifier: GPL-3.0-or-later
// Blending accuracy levels of the pinned ARMSX2 2.6 engine (pcsx2/Config.h
// AccBlendLevel: 0 Minimum, 1 Basic, 2 Medium, 3 High, 4 Full, 5 Maximum;
// INI key EmuCore/GS accurate_blending_unit; DEFAULT_BLENDING_ACCURACY = Basic).
//
// Only the levels that change what the iPhone renders are offered. Under
// TARGET_OS_IPHONE the Metal device publishes neither a texture barrier nor a
// multidraw framebuffer copy (GSDeviceMTL.mm), so FeatureSupport::feedback_loops()
// is false and the Medium case of GSRendererHW::EmulateBlending adds nothing to
// Basic: its only addition is gated by that flag and its mask only narrows the
// bits set by High, Full and Maximum. Medium is therefore not offered; a value
// already stored in an INI by another frontend is still reported as it is.
#pragma once
#ifdef __cplusplus
#include <array>
inline constexpr int kNeoARMSX2BlendingDefault = 1;  // Basic
inline constexpr int kNeoARMSX2BlendingMaximum = 5;  // Maximum
inline constexpr int kNeoARMSX2BlendingMedium = 2;   // identical to Basic on iPhone
inline constexpr std::array<int, 5> kNeoARMSX2BlendingLevels = {0, 1, 3, 4, 5};
inline constexpr bool NeoARMSX2BlendingLevelOffered(int level) {
  for (int offered : kNeoARMSX2BlendingLevels)
    if (offered == level) return true;
  return false;
}
#endif
