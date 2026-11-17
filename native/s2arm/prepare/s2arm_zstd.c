// RewindBox: zstd 1.5.7's single-file decoder for the preparation library's NUP reader (s2arm_nup.c), the
// copy RewindBox already ships for libchdr (packages/libretro_internal_bridge/ios/ThirdParty/libchdr/deps/
// zstd-1.5.7/zstddeclib.c, BSD option of zstd's "BSD or GPLv2"; its licence text is in
// assets/legal/libretro/RA-disc-reader-NOTICES.txt). Built into the xcframework's single relocatable
// object, where every name but rb_s2arm_* is local (build_prepare_xcframework.sh), so it cannot collide
// with libchdr's copy. The amalgamation is third-party code: its warnings are not this library's.
#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Weverything"
#elif defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wimplicit-fallthrough"
#pragma GCC diagnostic ignored "-Wsign-compare"
#endif
#include "../../../packages/libretro_internal_bridge/ios/ThirdParty/libchdr/deps/zstd-1.5.7/zstddeclib.c"
#if defined(__clang__)
#pragma clang diagnostic pop
#elif defined(__GNUC__)
#pragma GCC diagnostic pop
#endif
