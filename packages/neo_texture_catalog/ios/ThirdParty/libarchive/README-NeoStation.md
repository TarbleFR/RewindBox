# Private RAR reader subset

Original upstream: [libarchive v3.8.10](https://github.com/libarchive/libarchive/releases/tag/v3.8.10), released 14 October 2026.
`source.json` pins the original archive SHA-256 and each unchanged upstream file.
The 25 C translation units implement RAR4/RAR5 reading, entry/string handling,
PPMd and checksum primitives. ZIP/7z retain their existing NeoStation readers.
No command line program, archive format writer, filesystem extractor, external filter,
password implementation or iOS system/private libarchive is compiled or invoked.

`config.h` is a local POSIX LP64 configuration for iOS17.4+, macOS and the Linux
verification host. All 340 defined upstream symbols are renamed in
`NeoTextureLibarchivePrefix.h` so they cannot collide with other embedded cores.
That list is generated from `nm -g --defined-only` on these translation units;
only the symbol macros and configuration are local. Original upstream sources
and their notices are unchanged. The iOS pod links public zlib and iconv.

All upstream allocation calls (including `strdup`) use
`Classes/NeoTextureRARMemory.c` through this configuration. Each reader has a
separate capped allocation budget, at most 256 MiB; it is selected only during a
synchronous decoder call and all allocations must be freed before that reader
is destroyed. The wrapper retains the existing archive/entry/name/file limits,
checks the sum of all declared expanded sizes before decoding (including
unselected solid members), polls cancellation on every output chunk,
normalizes and checks paths before any extraction, rejects links and encrypted
or multivolume archives, streams output through 256 KiB and input through 64 KiB,
and uses the existing exclusive staging-file writer and installer transaction.
RAR4 solid archives are not implemented by this upstream reader and remain
unsupported; RAR5 solid archives are supported and require decoding earlier members when listing/skipping;
no solid archive or complete entry is buffered in memory.

`Classes/NeoTextureRAR.h` independently reads bounded headers and verifies every
declared CRC32 or BLAKE2sp over selected output. This also covers stored RAR5
members, whose upstream path can otherwise complete without checksum
finalization. Optional checksums absent from a RAR5 file cannot be invented:
the catalogue's exact full-archive size/SHA-256 verification is still mandatory.
No failed archive is repaired, converted or repackaged for publication.

The public app API is NeoStation's C++ `NeoTextureArchive::Rar`; raw libarchive
functions are implementation details. `tools/textures/build_rar_library.py`
builds the same sources for native verification and returns a static library.
The pod compiles them directly. `test/texture_rar_test.py` exercises real
upstream compressed/solid fixtures plus path, encryption, link, volume,
integrity, cancellation and memory/size/count boundaries under ASan/UBSan.
Upstream fixture notices and digests are in `test/fixtures/texture_rar`.

Licences: upstream `COPYING` plus individual unchanged file headers;
BLAKE2's CC0 option is selected. The iOS resource
`Resources/libarchive-LICENSE.txt` retains the combined binary distribution
notices. NeoStation's adapter, allocator, configuration and tests use GPL-3.0-or-later.
