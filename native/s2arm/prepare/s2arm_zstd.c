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

// Single frame, no out-of-band dictionary. A forged header or unknown content
// size never controls an unbounded allocation. Keep the result private on error.
int rb_s2arm_shader_inflate(const void *src, size_t n, void **out, size_t *size, size_t limit) {
    if (!out || !size) return 0;
    *out = NULL;
    *size = 0;
    if (!src || !n || !limit || limit > (64u << 20)) return 0;
    unsigned long long frame = ZSTD_getFrameContentSize(src, n);
    if (frame == ZSTD_CONTENTSIZE_ERROR || ZSTD_findFrameCompressedSize(src,n) != n
        || ZSTD_getDictID_fromFrame(src,n)) return 0;
    size_t capacity;
    if (frame == ZSTD_CONTENTSIZE_UNKNOWN) {
        unsigned long long bound = ZSTD_decompressBound(src,n);
        capacity = bound > limit ? limit : (size_t)bound;
    } else {
        if (frame > limit) return 0;
        capacity = (size_t)frame;
    }
    if (!capacity) return 0;
    void *decoded = malloc(capacity);
    if (!decoded) return 0;
    size_t actual = ZSTD_decompress(decoded,capacity,src,n);
    if (!actual || ZSTD_isError(actual) || (frame != ZSTD_CONTENTSIZE_UNKNOWN && actual != frame)) {
        free(decoded);
        return 0;
    }
    *out = decoded;
    *size = actual;
    return 1;
}
