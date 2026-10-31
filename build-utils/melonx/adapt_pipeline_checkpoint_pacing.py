"""Keep urgent cache pressure measurements separate from paced disk checkpoints."""
from pathlib import Path

RELATIVE = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
BEFORE = '''            if (!force)
            {
                if (state.EstimatedBytes < state.Budget)
                {
                    if (string.IsNullOrEmpty(state.Path))
                    {
                        return;
                    }

                    if (state.PipelineCount - state.SavedPipelineCount < SaveInterval)
                    {
                        return;
                    }

                    long now = Environment.TickCount64;

                    if (state.LastSaveTimestamp != 0 && now - state.LastSaveTimestamp < MinimumSaveIntervalMs)
                    {
                        return;
                    }
                }
            }

            state.SavedPipelineCount = state.PipelineCount;
            state.LastSaveTimestamp = Environment.TickCount64;'''
AFTER = '''            long now = Environment.TickCount64;
            bool checkpointDue = force || (!string.IsNullOrEmpty(state.Path) &&
                state.PipelineCount - state.SavedPipelineCount >= SaveInterval &&
                (state.LastSaveTimestamp == 0 || now - state.LastSaveTimestamp >= MinimumSaveIntervalMs));

            // An estimate near the budget still needs immediate measurement and
            // recycling when necessary. It must not bypass disk-write pacing.
            if (!checkpointDue && state.EstimatedBytes < state.Budget)
            {
                return;
            }

            if (checkpointDue)
            {
                state.SavedPipelineCount = state.PipelineCount;
                state.LastSaveTimestamp = now;
            }'''
DIRTY_BEFORE = '            if (state.Generation == state.SavedGeneration)'
DIRTY_AFTER = '            if (!checkpointDue || state.Generation == state.SavedGeneration)'


def apply(source):
    path = Path(source) / RELATIVE
    text = path.read_text(encoding='utf-8-sig')
    if text.count(AFTER) == 1 and text.count(DIRTY_AFTER) == 1 and BEFORE not in text:
        return [path]
    if text.count(BEFORE) != 1 or text.count(DIRTY_BEFORE) != 1:
        raise RuntimeError('Pipeline checkpoint pacing anchor drift: ' + RELATIVE)
    path.write_text(text.replace(BEFORE, AFTER).replace(DIRTY_BEFORE, DIRTY_AFTER))
    return [path]
