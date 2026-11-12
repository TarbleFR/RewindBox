"""Programs translated during play bind once their shader modules exist, in every title (not only Hogwarts Legacy).

adapt_setprogram_warmup (Core 658) gave a program translated during play, with synchronous compilation (async shaders
off: no draw is ever skipped), the path a cached program takes: its shader modules and its warm-up pipeline compile on
the bounded background workers, SetProgram waits for the modules only, and a draw with the warm-up's key promotes that
warm-up and waits for it instead of building the same pipeline on the render thread. Library.cs set it for Hogwarts
Legacy only, "until a second title is measured" (VulkanRenderer.DetachPlayTimeWarmUps). Off, the render thread waits
in SetProgram for the program's whole warm-up pipeline, and the warm-up can even run inline in CreateProgram or in the
ProgramQueue that SetProgram processes.

Second title measured: Super Smash Bros. Ultimate v13.0.4 on IPA 727 (Core 737, pid 56632, 12 Nov; private journals,
not in the repository; aggregates only), asyncShaders=False, thermal state nominal throughout:
- render-thread "LogRenderWork" windows of 5 s: SetProgram 1 394, 989, 813, 778, 763, 670 ms (the largest six);
  CreateProgram 16 calls 446.5 ms and 7 calls 576.3 ms (28 to 82 ms each: warm-ups compiled inline);
- the session's largest presentation gaps (1 800 ms at t=207, 1 350, 733, 700, 583, 533 ms) fall in the windows of the
  pipeline bursts: the window of the 1.8 s gap holds 30 graphics pipeline builds (8.2 s inclusive, overlapping) and
  SetProgram 8 745 calls 1 394 ms; the journal of compiled pipelines counts 177 render-thread compilations in 30.7 s
  over the session, none compiled again (new pipelines), and the variant replay of the 1 209 known variants worked
  (ready before their first draw 594, late new variants 99 for 1.4 s);
- the same build's Hogwarts Legacy sessions, with the policy on (pid 54035, 55836): SetProgram at most 17.5 ms per
  window, CreateProgram 2 065 calls 84 ms.
The setprogram-warmup gate executes the real members (VulkanRenderer.CreateProgram, ShaderCollection, Shader,
PipelineBase.SetProgram/CreatePipeline, the scheduler, the GAL ProgramQueue) with the policy off and on: a burst of
programs created ahead binds in 1.4 ms instead of 1 571 ms and reaches its first draw in 444 ms instead of 1 603 ms, every
draw drawn with its own exact pipeline, no warm-up on the render thread or the main cache.

Change (Library.cs only): the flag is set for every title. Every other per-title policy keeps the Hogwarts scope. Not
changed: pipeline keys and state, which pipeline a draw binds, async shader mode (off by default: no draw or dispatch is
skipped), cached programs, the queues and their priorities. What moves: these warm-ups now compile on the workers' own
pipeline caches (128 MiB budget each, merged into the main cache at close, as for cached programs) instead of the main
cache: the memory of those worker caches and the Metal compiler's concurrency on the iPhone are not measured by the
gate; they are read in the next session's pipeline build lines, render-stage SetProgram times, [MeloNX:memory] lines and
presentation gaps. Rollback: remove this adapter (the flag returns to `hogwarts`). Not measured on an iPhone; no FPS or
heat gain claimed. Fail closed on drift: Library.cs must be the Core 737 preparation's.
"""
import hashlib
from adapt_session import once

LIBRARY = 'src/Ryujinx.Library/Library.cs'
BASELINE = {
    LIBRARY: 'd601923afc7d31e844d6eb2ea6f28516475da259c9449b9a2001df9f65e4ea97',
}
MARKER = 'adapt_playtime_warmup_all_titles'

OLD = '''            // RewindBox (adapt_setprogram_warmup): binding a program translated during play waits for its shader modules,
            // not for its warm-up pipeline (Hogwarts Legacy until a second title is measured).
            if (renderer is VulkanRenderer warmUpVulkan) warmUpVulkan.DetachPlayTimeWarmUps = hogwarts;
'''
NEW = '''            // RewindBox (adapt_setprogram_warmup): binding a program translated during play waits for its shader modules,
            // not for its warm-up pipeline. Every title (adapt_playtime_warmup_all_titles: Super Smash Bros. Ultimate on
            // IPA 727 waited up to 1.4 s per 5 s in SetProgram with it off; draws are never skipped either way).
            if (renderer is VulkanRenderer warmUpVulkan) warmUpVulkan.DetachPlayTimeWarmUps = true;
'''
PAIRS = [(LIBRARY, OLD, NEW)]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
