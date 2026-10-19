# LZMA SDK 24.09 (C sources, subset)

Copied unmodified from `packages/flutter_7zip/src/7zip/C` (7-Zip / LZMA SDK
24.09, 2024-11-29, by Igor Pavlov). The LZMA SDK is placed in the public
domain by its author ("Igor Pavlov : Public domain", 7zVersion.h).

Only the 7z archive reader and its decoders are used (7z database parser,
LZMA, LZMA2, BCJ2, CRC). `Classes/NeoTextureLZMA.c` compiles them once with
hidden visibility so their symbols never clash with the copy linked by the
flutter_7zip plugin.
