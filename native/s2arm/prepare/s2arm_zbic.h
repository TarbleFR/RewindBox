// RewindBox: port of S2Arm pack/nx_unpack/ZbicDecoder.cs and pack/nx_unpack/NsoZbic.cs
// (Apache-2.0, pinned commit in tools/s2arm_prototype/pin.json).
//
// ZBIC is the zstd variant Switch system 22.0.0 accepts for NSO segments (NSO flag 0x80):
// standard zstd frames (RFC 8878) with the magic "ZBIC" (0x4349425A little-endian) and the
// FSE normalised-count headers written with binary interpolative coding. NSO
// normalisation rewrites a ZBIC NSO into the same NSO with uncompressed segments, which
// every later stage (and the runtime) reads. CI compares both, byte for byte and error
// for error, with the C# originals on synthetic input (tools/s2arm_prototype/run_zbic_test.py).
//
// The input is untrusted: every read and write is bounds-checked, no recursion depends
// on the input beyond 7 levels (the BIC header tree), and sizes are capped (below).
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    RB_S2ARM_ZBIC_OK = 0,
    RB_S2ARM_ZBIC_INVALID = 1,  // not a ZBIC frame / corrupt / truncated / wrong length / unknown NSO flag
    RB_S2ARM_ZBIC_IO = 2,       // a file could not be read or written, or out of memory
};

// Largest decompressed NSO segment accepted. The C# original would try up to its array
// limit (about 2 GiB); real segments are far smaller and a phone cannot hold that much.
#define RB_S2ARM_ZBIC_SEGMENT_CAP ((size_t)1 << 30)
// Largest file and largest normalised NSO: the C# array limit (Array.MaxLength).
#define RB_S2ARM_ZBIC_FILE_CAP ((size_t)0x7FFFFFC7)

// Decompresses all frames of src (ZBIC frames, skippable frames allowed between them) into
// dst, which must be exactly `expected` bytes long: the total must equal `expected`, as
// ZbicDecoder.Decompress(data, expected) requires. A standard zstd frame, an unknown magic,
// truncation, corruption, a checksum mismatch or a wrong length fail with
// RB_S2ARM_ZBIC_INVALID. `error` (may be NULL) receives one line on failure.
int rb_s2arm_zbic_decompress(const uint8_t *src, size_t src_len, uint8_t *dst, size_t expected, char *error, size_t error_size);

// NsoZbic.Normalize. Not an NSO (shorter than 0x100 or no "NSO0") or no ZBIC flag:
// *out = NULL, *out_len = 0 and RB_S2ARM_ZBIC_OK (the input is the result, unchanged).
// Flag bits other than 0x00-0x3F, 0x40 and 0x80 fail. A ZBIC NSO: *out receives a new
// malloc'd NSO with uncompressed segments laid out one after the other right after the
// header and whatever lies between the header and the first segment (the module name),
// flags without 0x80 and bits 0-2 (hash bits 3-5 and 0x40 kept, the stored SHA-256 being
// those of the decompressed segments, checked when their bit is set). `name` (may be NULL)
// prefixes the error messages as in the original.
int rb_s2arm_nso_normalize(const uint8_t *nso, size_t len, const char *name, uint8_t **out, size_t *out_len, char *error,
                           size_t error_size);

// nx_unpack --nso-normalize <in> <out>: reads `in`, normalises it and writes `out` (a copy
// of the input when there is nothing to normalise). Nothing is left at `out` on failure.
int rb_s2arm_nso_normalize_file(const char *in, const char *out, char *error, size_t error_size);

// XXH64 with seed 0 (used for the frame checksum; exposed for the tests).
uint64_t rb_s2arm_xxh64(const uint8_t *data, size_t len);

#ifdef __cplusplus
}
#endif
