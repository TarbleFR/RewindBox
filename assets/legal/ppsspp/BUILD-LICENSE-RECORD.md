# PPSSPP Build 497 dependency license record

Pinned PPSSPP source: `1bd28b0d634d4ec31acb7092563f3e1e247d1e9c`.
Vendored FFmpeg source marker: `6c64b8f98ad0ca38f5360484618e2af6e44fcb3d`.
NeoStation source-build inputs: `native/ppsspp/source.json`,
`native/ppsspp/managed-memory.patch` and
`.github/diagnostics/ppsspp497/build.py`.

The iOS recipe builds FFmpeg from the vendored source through
`ext/ffmpeg-build/CMakeLists.txt`. It creates static avcodec, avformat,
avutil, swresample and swscale libraries; it does not invoke FFmpeg's usual
configure script. The checked template contains these literal settings:

```c
#define FFMPEG_LICENSE "GPL version 2 or later"
#define CONFIG_GPL 0
#define CONFIG_NONFREE 0
#define CONFIG_VERSION3 0
#define CONFIG_GPLV3 0
#define CONFIG_LGPLV3 0
```

The disabled GPL/nonfree/version3 flags coexist with a GPL-v2-or-later license
string. The upstream `ffmpeg/LICENSE.md` instead describes LGPL-2.1-or-later
as the default and GPL options when enabled. Both license texts are retained;
this record does not resolve that inconsistent metadata or claim an LGPL-only
binary. The selected libavcodec input list also includes the IJG files; the
required acknowledgment and their unmodified notices are retained separately.
No runtime, build flag or existing binary is changed by this documentation.

Other notices in this folder are copied from the pinned PPSSPP source tree or
from exact submodule commits fetched by the build. Conditional code and
source-build dependencies retain their own notices. This is a source-based
notice inventory; it is not an assertion that every referenced file reaches
the final executable or that the complete binary's legal review is finished.
The FreeType checkout is initialized by the recipe but is not referenced by
the reviewed libretro makefiles; it is not presented as a new shipped library.

Reproducing and distributing a modified core still requires retaining its
matching source, exact submodule trees, local patch and build recipe. A license
snapshot alone does not satisfy all corresponding-source obligations.
