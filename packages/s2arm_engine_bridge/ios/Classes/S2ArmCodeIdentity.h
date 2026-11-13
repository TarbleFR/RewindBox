#pragma once
// The identity of compiled code, for the preparation's fingerprint (S2ArmGamePreparation.m): the UUID the linker
// writes into a Mach-O image (LC_UUID), which changes whenever the image's content does and stays the same when the
// same code is built again. The app's build number changes with every delivery, whatever it contains, so a
// preparation keyed on it was redone after each one: 92 s for Mario Kart World on an iPhone17,2 (13 Nov, IPA 734:
// 25 s for the RomFS view, 20 s to walk the pack and 43 s to hash it), then the engine's RomFS index again.
// Plain C over bytes: nothing here needs an Apple header, so the same file is tested on a computer.
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

enum { S2ARM_UUID_TEXT = 37 };   // "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX" and its terminator

/// The LC_UUID of a 64-bit Mach-O image whose header and load commands are the `size` bytes at `image`.
/// Returns 1 and the UUID as text, or 0 (not a thin 64-bit Mach-O, truncated or malformed commands, no LC_UUID).
int s2arm_macho_uuid(const void *image, size_t size, char out[S2ARM_UUID_TEXT]);

/// The same for a loaded image, from its header in memory (dladdr's dli_fbase): the header gives the size of its commands.
int s2arm_macho_uuid_loaded(const void *header, char out[S2ARM_UUID_TEXT]);

/// The same for an image file (the engine framework's binary, which is opened only when a game starts).
int s2arm_macho_uuid_file(const char *path, char out[S2ARM_UUID_TEXT]);

#ifdef __cplusplus
}
#endif
