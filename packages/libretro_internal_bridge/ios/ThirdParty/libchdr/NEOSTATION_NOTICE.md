# libchdr in the libretro bridge

Pinned copy used by `Classes/RBDiscHashReader.c` (NEOSTATION_RA_DISC_READER_V1)
so that RetroAchievements can identify games stored as `.chd` images, in game
and in the library.

- Upstream: https://github.com/rtissera/libchdr
- Commit: `47d794151b2b64f6aba60304e6480f4f5a2bc24b` (2026-10-11)
- Copied without modification: `LICENSE.txt`, `README.md`, `include/libchdr/*.h`,
  `include/dr_libs/dr_flac.h`, `src/*.{c,h}` (except the optional C++
  `libchdr_flac_microflac.cpp` backend), `deps/lzma-26.02` (`LICENSE`,
  `LzmaDec` only), `deps/zstd-1.5.7` (`zstd.h`, `zstd_errors.h`,
  `zstddeclib.c`).
- Not copied: the bundled miniz (the system zlib is used, `CHDR_SYSTEM_ZLIB`),
  build files, tests and tools.
- Build defines (podspec): `CHDR_SYSTEM_ZLIB=1`, `ZSTD_DISABLE_ASM=1`; libchdr's
  own defaults otherwise (raw data sectors, subcode and block CRC verification
  on).

Licenses (each file keeps its own notice):

| Component | License |
| --- | --- |
| libchdr | BSD-3-Clause (`LICENSE.txt`) |
| LZMA SDK (`deps/lzma-26.02`) | Public domain (`deps/lzma-26.02/LICENSE`) |
| Zstandard decoder (`deps/zstd-1.5.7`) | BSD or GPLv2, at the user's option (header of `zstddeclib.c`) |
| dr_flac (`include/dr_libs/dr_flac.h`) | Public domain or MIT-0 (end of the file) |
