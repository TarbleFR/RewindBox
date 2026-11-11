// Stand-in for Apple's TargetConditionals.h on a host that has none (the cache key property test compiles MoltenVK's
// SPIRVToMSLConverter.cpp for its matches(), alignWith() and cacheKey(), which use no platform service). Only used when
// the real header is absent: test/melonx_cache_keys_test.py adds this directory to the include path on such hosts.
#pragma once
#define TARGET_OS_MAC 1
#define TARGET_OS_OSX 1
#define TARGET_OS_IPHONE 0
#define TARGET_OS_IOS 0
#define TARGET_OS_TV 0
#define TARGET_OS_WATCH 0
#define TARGET_OS_VISION 0
#define TARGET_OS_XR 0
#define TARGET_OS_SIMULATOR 0
#define TARGET_OS_MACCATALYST 0
#define TARGET_CPU_ARM64 0
#define TARGET_CPU_X86_64 1
