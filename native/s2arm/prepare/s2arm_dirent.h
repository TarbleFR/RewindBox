// RewindBox: the type of a directory entry as readdir gives it, for the preparation's walks.
// Internal (static inline: nothing leaves a unit, the xcframework keeps only rb_s2arm_*).
// A walk that knows from the listing that an entry is a real file or a real directory needs no
// stat for it. Mario Kart World's RomFS has about 205 000 entries, and each walk with an lstat and
// a stat per entry took 29 s on the phone (IPA 731 journal: NRO walk, NRO exports walk, caps).
#pragma once
#include <dirent.h>

// The same values on Linux and Darwin; _POSIX_C_SOURCE / _XOPEN_SOURCE hide the names, not the field.
#ifndef DT_UNKNOWN
#define DT_UNKNOWN 0
#define DT_FIFO 1
#define DT_CHR 2
#define DT_DIR 4
#define DT_BLK 6
#define DT_REG 8
#define DT_LNK 10
#define DT_SOCK 12
#endif

// DT_DIR, DT_REG, DT_LNK..., or DT_UNKNOWN when the file system (or the platform) does not say:
// the caller then falls back to lstat / stat, as before.
static inline unsigned char s2arm_dirent_type(const struct dirent *e) {
#if defined(__APPLE__) || defined(__linux__)
    return e->d_type;
#else
    (void)e;
    return DT_UNKNOWN;
#endif
}
