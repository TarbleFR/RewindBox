// SPDX-License-Identifier: GPL-3.0-or-later
// Compiles the vendored LZMA SDK 24.09 (public domain, ThirdParty/lzma) into
// this pod with hidden visibility. The application already links another
// copy of the SDK (flutter_7zip); hidden symbols keep each framework bound to
// its own copy. Only the 7z database reader and the LZMA/LZMA2 decoders are
// needed; branch filters stay disabled (a texture pack has no executables).
#define Z7_NO_METHODS_FILTERS 1
#pragma GCC visibility push(hidden)
#include "../ThirdParty/lzma/7zArcIn.c"
#include "../ThirdParty/lzma/7zBuf.c"
#include "../ThirdParty/lzma/7zCrc.c"
#include "../ThirdParty/lzma/7zCrcOpt.c"
#include "../ThirdParty/lzma/7zDec.c"
#include "../ThirdParty/lzma/7zStream.c"
#include "../ThirdParty/lzma/Bcj2.c"
#include "../ThirdParty/lzma/CpuArch.c"
#include "../ThirdParty/lzma/LzmaDec.c"
#include "../ThirdParty/lzma/Lzma2Dec.c"
#pragma GCC visibility pop
