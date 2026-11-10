"""Complete report visibility at 3D syncpoints and threaded conditionals.

Applied to the retained prepared source after adapt_occlusion_reports. The
backend owns host reservations; the threaded caller observes its real result.
"""
from pathlib import Path


def apply(source):
    changes = {
        'src/Ryujinx.Graphics.Gpu/Engine/Threed/ThreedClass.cs': (
            '''            _context.AdvanceSequence();
            _context.CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint);
            _context.Renderer.UpdateCounters(); // Poll the query counters, the game may want an updated result.''',
            '''            _context.AdvanceSequence();
            if (!_context.SynchronizeOcclusionReports || !_context.FlushCounterReports())
                _context.CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint);
            _context.Renderer.UpdateCounters(); // Poll the query counters, the game may want an updated result.'''),
        'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedPipeline.cs': (
            '''                    if (!evt.ReserveForHostAccess())
                    {
                        return false;
                    }

                    _renderer.New<TryHostConditionalRenderingCommand>()->Set(Ref(evt), compare, isEqual);
                    _renderer.QueueCommand();
                    return true;''',
            '''                    // Only the backend knows whether a GPU condition was encoded.
                    // Let it own the reservation, then observe its actual result so
                    // an unsupported or expired query takes the CPU comparison path.
                    ResultBox<bool> result = new();
                    _renderer.New<TryHostConditionalRenderingCommand>()->Set(Ref(evt), compare, isEqual, Ref(result));
                    _renderer.InvokeCommand();
                    return result.Result;'''),
        'src/Ryujinx.Graphics.GAL/Multithreading/Commands/TryHostConditionalRenderingCommand.cs': (
            '''        private bool _isEqual;

        public void Set(TableRef<ThreadedCounterEvent> value, ulong compare, bool isEqual)
        {
            _value = value;
            _compare = compare;
            _isEqual = isEqual;
        }

        public static void Run(ref TryHostConditionalRenderingCommand command, ThreadedRenderer threaded, IRenderer renderer)
        {
            renderer.Pipeline.TryHostConditionalRendering(command._value.Get(threaded)?.Base, command._compare, command._isEqual);
        }''',
            '''        private bool _isEqual;
        private TableRef<ResultBox<bool>> _result;

        public void Set(TableRef<ThreadedCounterEvent> value, ulong compare, bool isEqual, TableRef<ResultBox<bool>> result)
        {
            _value = value;
            _compare = compare;
            _isEqual = isEqual;
            _result = result;
        }

        public static void Run(ref TryHostConditionalRenderingCommand command, ThreadedRenderer threaded, IRenderer renderer)
        {
            bool result = renderer.Pipeline.TryHostConditionalRendering(command._value.Get(threaded)?.Base, command._compare, command._isEqual);
            command._result.Get(threaded).Result = result;
        }'''),
    }
    # Validate every anchor before writing any file; exact postimages are a no-op.
    output = {}
    for relative, (before, after) in changes.items():
        path = Path(source) / relative
        text = path.read_text(encoding='utf-8-sig')
        if text.count(after) == 1 and before not in text:
            continue
        if text.count(before) != 1:
            raise RuntimeError('Occlusion completion adapter anchor drift: ' + relative)
        output[path] = text.replace(before, after)
    for path, text in output.items():
        path.write_text(text)
    return [Path(source) / relative for relative in changes]
