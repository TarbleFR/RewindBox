"""Hogwarts Legacy's shaders compiled by Metal without fast math (Inf and NaN kept).

IPA 666 (MeloNX Core 663), Hogwarts Legacy, pid 15186 (private journals and three screenshots, not in the repository):
large black blocks with blue and cyan glowing edges remain in the sky of the "Professeur Fig" area. The 5 s pass lines
of the same session show the Core 661 barrier lever active (later readers ordered in a new stage: vertex 144, fragment
761, compute 4985 in one window; encoder switches ordered by the policy 424): the missing-barrier reading of these blocks
is refuted. Black cores that grow in blocks with a bright blue/cyan fringe are what NaN or Inf values look like once
temporal accumulation and bloom spread them.

Mechanism (sources: MeloNX src/Ryujinx.Graphics.Vulkan/MoltenVK/MVKInitialization.cs; MoltenVK v1.4.2
MVKDevice::getMTLCompileOptions; Apple MTLMathMode documentation):
- MeloNX sets MVKConfiguration.FastMathEnabled = true, MVK_CONFIG_FAST_MATH_ALWAYS: every shader gets all SPIR-V fast
  math flags, so on iOS 18+ MoltenVK selects MTLMathModeFast with fast floating-point functions. In that mode Metal may
  assume that no value is Inf or NaN, so a shader's own guards against them (isnan/isinf tests, max/min/clamp used to
  flush NaN) are not guaranteed to survive compilation.
- On MoltenVK, Ryujinx also omits the SPIR-V NoContraction decoration on float arithmetic (reduceShaderPrecision) and
  restores it only for 1 / (x + c) in fragment shaders (ForcePreciseEnable); compute shaders are not covered.
- FastMathEnabled = false (MVK_CONFIG_FAST_MATH_NEVER) clears every flag: MTLMathModeSafe with precise functions, which
  makes no transformation that could change a result, Inf and NaN included.

Change:
- MVKInitialization gains a static PreciseMath; Initialize(), which every Vulkan session runs in its VulkanRenderer
  constructor before the session's Vulkan instance exists, writes FastMathEnabled = !PreciseMath instead of true
  (every other member as before) and records one durable configuration line with the mode.
- The launch preflight sets PreciseMath for the title it opens (native/melonx/EmbeddedLaunchPreflight.cs and
  EmbeddedRuntime.cs, not this adapter): true for Hogwarts Legacy, false for every other title and at the start of every
  preflight, so a previous Hogwarts session in the same process never carries over.

Cost and limits: Hogwarts Legacy's shaders may run slower on the GPU (no reassociation, contraction or fast functions);
its GPU was busy 74 % of the frame time in IPA 666 (25.5 ms per frame at 29 fps), so headroom exists but is not
measured. The MSL MoltenVK caches is unchanged (only the Metal compile options differ), so no cache is invalidated;
Metal's own compiled-shader cache misses once per shader. Whether NaN/Inf caused the blocks is a hypothesis this lever
tests: on a device the proof is the "Professeur Fig" area without black blocks in a session whose core journal reads
"MoltenVK math mode precise", with GPU busy per frame compared with IPA 666.
Fail closed on drift: each file must be the Core 663 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/MoltenVK/MVKInitialization.cs': '86176c3c682d9d74eaf2e6e60e4ba5f07b1016591f520608974c6a223f88e950',
}

FIELD_OLD = '''        private const uint MaxActiveMetalCommandBuffersPerQueue = 32;
'''
FIELD_NEW = '''        private const uint MaxActiveMetalCommandBuffersPerQueue = 32;

        // RewindBox (adapt_hogwarts_precise_math): the Metal math mode of the shaders the next Vulkan instance compiles,
        // set by the launch preflight for the title it opens. False keeps MeloNX's fast math (MVK_CONFIG_FAST_MATH_ALWAYS,
        // MTLMathModeFast on iOS 18+, where Metal may assume no Inf or NaN); true selects MVK_CONFIG_FAST_MATH_NEVER
        // (MTLMathModeSafe: no floating-point transformation that could change a result).
        public static bool PreciseMath;
'''

MATH_OLD = '''            config.FastMathEnabled = true;
'''
MATH_NEW = '''            config.FastMathEnabled = !PreciseMath;
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("configuration", "mathMode",
                detail: PreciseMath ? "MoltenVK math mode precise (Inf and NaN kept)" : "MoltenVK math mode fast");
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    initialization = paths['src/Ryujinx.Graphics.Vulkan/MoltenVK/MVKInitialization.cs']
    once(initialization, FIELD_OLD, FIELD_NEW)
    once(initialization, MATH_OLD, MATH_NEW)
    return list(paths.values())
