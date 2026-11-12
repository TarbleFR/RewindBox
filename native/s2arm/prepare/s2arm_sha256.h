// RewindBox: SHA-256 for the preparation library (FIPS 180-4), portable C, no global state.
// Internal: the names do not start with rb_s2arm_, so the xcframework keeps them local.
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t h[8];
    uint8_t buf[64];
    uint64_t total;
    size_t fill;
} s2arm_sha256_ctx;

void s2arm_sha256_init(s2arm_sha256_ctx *s);
void s2arm_sha256_update(s2arm_sha256_ctx *s, const void *data, size_t len);
void s2arm_sha256_final(s2arm_sha256_ctx *s, uint8_t out[32]);
void s2arm_sha256(const void *data, size_t len, uint8_t out[32]);
void s2arm_sha256_hex(const uint8_t digest[32], char out[65]);

#ifdef __cplusplus
}
#endif
