"""Say, on a missed pipeline warm-up, how many pipelines the program already had.

IPA 640 (Core 639, Hogwarts Legacy; private logs): the PR #153 diagnostic named two misses in 154 s,
"Topology warm-up=TriangleList draw=TriangleStrip; PrimitiveRestartEnable warm-up=False draw=True" and the restart
field alone. ShaderCollection.TryGetGraphicsPipeline returns before that warning while the program's pipeline table is
still empty, without consuming _firstBackgroundUse; such a draw then builds its own pipeline. So the warning compares the
warm-up either with the program's first draw (a warm-up state that differs from the first draw: a parity defect to fix)
or with a later draw in another state after earlier draws built pipelines of their own (a program legitimately used in
two states: a list without restart, then an indexed strip with restart). The two cannot be told apart from the line, and
the GPU-side draw paths (DrawManager, StateUpdater) record the topology and restart state for the warm-up and the host in
the same calls, so source inspection found no deterministic mismatch.

Change, diagnostics only: the once-per-program warning adds "(pipelines already built for this program: N)", counted
only on that miss under the pipeline table lock. N = 1 is the warm-up alone: the first draw missed it. N > 1: other states
were drawn first. No lookup, key or compile changes. Fail closed on drift: ShaderCollection.cs must be the Core 639
preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs': 'ccbfd6a72a1117909fb4fcfcb75c815cd570ca7a34b09e01c440d5848abd101f',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    collection = paths['src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs']
    once(collection, '''                        Logger.Warning?.Print(LogClass.Gpu, "Background pipeline compile missed on draw - incorrect pipeline state?" +
                            DescribeInitialKeyDifference(ref key));
''', '''                        Logger.Warning?.Print(LogClass.Gpu, "Background pipeline compile missed on draw - incorrect pipeline state?" +
                            DescribeInitialKeyDifference(ref key) + DescribeMissContext());
''')
    once(collection, '''        private string DescribeInitialKeyDifference(ref PipelineUid drawKey)
''', '''        // RewindBox (adapt_pipeline_miss_context): 1 = only the warm-up, so the program's first draw missed it; more = other
        // states were drawn first. Called under _pipelineCacheLock, once per program, on that miss only.
        private string DescribeMissContext()
        {
            int pipelines = 0;

            foreach (Auto<DisposablePipeline> _ in _graphicsPipelineCache.Values)
            {
                pipelines++;
            }

            return $" (pipelines already built for this program: {pipelines})";
        }

        private string DescribeInitialKeyDifference(ref PipelineUid drawKey)
''')
    return list(paths.values())
