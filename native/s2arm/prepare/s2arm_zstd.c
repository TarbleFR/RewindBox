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

#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>

// The descriptor must be a new empty scratch file. No decoded buffer scales
// with the archive: zstd retains at most its bounded history and one output block.
int rb_s2arm_shader_inflate_fd(const void *src, size_t n, int fd, uint64_t limit,
                                int (*cancel)(void *), void *ctx, uint64_t *written) {
    if (!written) return -4;
    *written=0;
    if (!src || !n) return 0;
    struct stat st;
    if (fd<0 || fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_size || lseek(fd,0,SEEK_CUR)!=0) return -4;
    ZSTD_frameHeader frame;
    if (ZSTD_getFrameHeader(&frame,src,n)!=0 || frame.frameType!=ZSTD_frame) return 0;
    if (frame.dictID) return -3;
    if (frame.windowSize>(32ull<<20) || !limit ||
        (frame.frameContentSize!=ZSTD_CONTENTSIZE_UNKNOWN && frame.frameContentSize>limit)) return -2;
    ZSTD_DCtx *z=ZSTD_createDCtx();
    if (!z) return -2;
    int rc=0;
    uint64_t total=0;
    if (ZSTD_isError(ZSTD_DCtx_setParameter(z,ZSTD_d_windowLogMax,25))) goto done;
    const unsigned char *p=src;
    size_t at=0;
    unsigned char output[65536];
    for (;;) {
        if (cancel && cancel(ctx)) { rc=-1; break; }
        const size_t remaining=n-at;
        ZSTD_inBuffer in={p+at,remaining<sizeof output ? remaining : sizeof output,0};
        ZSTD_outBuffer out={output,sizeof output,0};
        size_t next=ZSTD_decompressStream(z,&out,&in);
        if (ZSTD_isError(next)) break;
        if (out.pos>limit-total) { rc=-2; break; }
        size_t off=0;
        while (off<out.pos) {
            ssize_t took=write(fd,output+off,out.pos-off);
            if (took<0 && errno==EINTR) continue;
            if (took<=0) { rc=errno==ENOSPC || errno==EDQUOT ? -2:-4; goto done; }
            off+=(size_t)took;
        }
        at+=in.pos; total+=out.pos;
        if (!next) { rc=at==n && total && (frame.frameContentSize==ZSTD_CONTENTSIZE_UNKNOWN || frame.frameContentSize==total); break; }
        if (!out.pos && !in.pos) break;
    }
done:
    ZSTD_freeDCtx(z);
    if (rc==1) *written=total;
    else if (ftruncate(fd,0) || lseek(fd,0,SEEK_SET)<0) rc=-4;
    return rc;
}
