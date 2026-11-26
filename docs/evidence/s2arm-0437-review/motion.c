// Compare the 0430 and 0432 search costs on the same finite R16Float inputs.
// Uses the same zero-motion preference in both variants to isolate the SAD.
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint32_t seed = 845;
static float luma(void) {
    seed ^= seed << 13;
    seed ^= seed >> 17;
    seed ^= seed << 5;
    return (float)(_Float16)((seed & 1023u) / 1023.f);
}

static uint32_t key(float sad, uint32_t lane) {
    uint32_t bits;
    memcpy(&bits, &sad, sizeof bits);
    return (bits & ~1023u) | lane;
}

static uint32_t motion(uint32_t best, float zero_sad) {
    uint32_t bits = best & ~1023u;
    float value;
    memcpy(&value, &bits, sizeof value);
    return zero_sad <= value * 1.02f + 0.05f ? 16u * 32u + 16u : best & 1023u;
}

int main(void) {
    unsigned changed = 0, changed_exact = 0;
    for (unsigned sample = 0; sample < 256; ++sample) {
        float window[40 * 40], block[64];
        for (unsigned i = 0; i < 1600; ++i) window[i] = luma();
        const unsigned known = sample * 17u % 1024;
        for (unsigned i = 0; i < 64; ++i)
            block[i] = sample < 128 ? window[(known / 32 + i / 8) * 40 + known % 32 + i % 8] : luma();
        uint32_t ref = UINT32_MAX, half = UINT32_MAX;
        float zero_sad = 0;
        for (unsigned lane = 0; lane < 1024; ++lane) {
            float sum = 0;
            _Float16 sum16 = 0;
            for (unsigned i = 0; i < 64; ++i) {
                float delta = fabsf(block[i] - window[(lane / 32 + i / 8) * 40 + lane % 32 + i % 8]);
                sum += delta;
                sum16 = (_Float16)((float)sum16 + (float)(_Float16)delta);
            }
            if (lane == 16u * 32u + 16u) zero_sad = sum;
            uint32_t k = key(sum, lane), h = key((float)sum16, lane);
            if (k < ref) ref = k;
            if (h < half) half = h;
        }
        if (motion(ref, zero_sad) != motion(half, zero_sad)) {
            if (sample < 128) ++changed_exact;
            else ++changed;
        }
    }
    printf("different vectors, exact translations %u/128, independent blocks %u/128\n", changed_exact, changed);
    return 0;
}
