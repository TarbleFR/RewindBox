// RetroAchievements game identification for disc images rcheevos cannot read
// by itself (NEOSTATION_RA_DISC_READER_V1).
//
// rcheevos' default CD reader understands .cue/.bin, .gdi and raw .iso only.
// A .chd (MAME compressed disc) or .cso (compressed PSP ISO) was hashed as if
// it were a raw image, so the game was never recognized. This reader decodes
// both with the pinned libchdr (ThirdParty/libchdr) and zlib, and hands every
// other path to rcheevos' own default reader unchanged.
//
// The same callbacks serve the in-game client and the library, so both
// compute exactly the same hash for the same file.

#ifndef RB_DISC_HASH_READER_H
#define RB_DISC_HASH_READER_H

#include <stdint.h>

#include "rc_hash.h"

#ifdef __cplusplus
extern "C" {
#endif

/// Fills [callbacks->cdreader] with the CHD/CSO-aware reader. Other fields are
/// left untouched. Thread-safe: the reader keeps no global state.
void rb_hash_install_disc_reader(rc_hash_callbacks_t *callbacks);

/// Computes the RetroAchievements hash of [path] for [console_id] with the
/// same algorithm and reader as the in-game client. A console id of 0 lets
/// rcheevos pick from the file extension. Returns non-zero on success.
int rb_hash_generate_for_file(char hash[33], uint32_t console_id, const char *path);

#ifdef __cplusplus
}
#endif

#endif
