"""Bounded observers of existing work, with no emulation policy changes.

Apply after all three performance optimizations. Validate all source anchors
in memory before publishing any transformed file.
"""
from pathlib import Path

NAMES = [
    'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs',
    'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs',
    'src/Ryujinx.Graphics.GAL/Multithreading/Model/CircularSpanPool.cs',
    'src/Ryujinx.Graphics.Gpu/Memory/CounterCache.cs',
    'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs',
    'src/Ryujinx.Graphics.Vulkan/PipelineState.cs',
    'src/Ryujinx.Graphics.Vulkan/BufferHolder.cs',
    'src/Ryujinx.Graphics.Vulkan/Queries/CounterQueueEvent.cs',
    'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs',
    'src/Ryujinx.Graphics.Gpu/Memory/Buffer.cs',
]


def apply(source):
    paths = [Path(source) / name for name in NAMES]
    texts = {path: path.read_text(encoding='utf-8-sig') for path in paths}
    for path, text in texts.items():
        if 'EmbeddedPerformanceDiagnostics' in text:
            raise RuntimeError('Performance observers already present: ' + str(path))
        texts[path] = 'using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n' + text

    def once(path, old, new, count=1):
        text = texts[path]
        if text.count(old) != count:
            raise RuntimeError('Performance observer source drift: ' + str(path) + ': ' + old[:100])
        texts[path] = text.replace(old, new)

    fifo, renderer, span, reports, pipeline, state, buffer, query, cache, virtual = paths
    once(fifo,
         '            return !_commandBufferQueue.IsEmpty || (_event.WaitOne(8) && !_commandBufferQueue.IsEmpty);',
         '''            if (!_commandBufferQueue.IsEmpty) return true;
            using var waitMeasurement = PD.Measure(PD.Phase.GpuFifoWait);
            return _event.WaitOne(8) && !_commandBufferQueue.IsEmpty;''')
    once(fifo, '        public void DispatchCalls()\n        {',
         '        public void DispatchCalls()\n        {\n            using var dispatchMeasurement = PD.Measure(PD.Phase.GpuDispatch);')
    once(renderer, '                _galWorkAvailable.Wait();',
         '                using (PD.Measure(PD.Phase.RenderIdle)) _galWorkAvailable.Wait();')
    once(renderer, '                while (Volatile.Read(ref _commandCount) > 0 && Volatile.Read(ref _interruptAction) == null)',
         '                using (PD.Measure(PD.Phase.RenderDrain))\n                while (Volatile.Read(ref _commandCount) > 0 && Volatile.Read(ref _interruptAction) == null)')
    once(renderer, '                Thread.Sleep(1);',
         '                using (PD.Measure(PD.Phase.QueueBackpressure)) Thread.Sleep(1);')
    once(renderer, '            _invokeRun.Wait();',
         '            using (PD.Measure(PD.Phase.SyncInvoke)) _invokeRun.Wait();')
    once(renderer, '            _frameComplete.WaitOne();',
         '            using (PD.Measure(PD.Phase.FrameWait)) _frameComplete.WaitOne();')
    once(span, '                return new SpanRef<T>(_renderer, data.ToArray());',
         '''                PD.Count(PD.Counter.SpanFallbacks);
                PD.Count(PD.Counter.SpanFallbackBytes, size);
                return new SpanRef<T>(_renderer, data.ToArray());''')
    once(reports, '        internal void FlushPendingReports()\n        {',
         '        internal void FlushPendingReports()\n        {\n            using var reportMeasurement = PD.Measure(PD.Phase.CounterReports);')
    once(reports, '            lock (_gate) reports = _pending.ToArray();',
         '            lock (_gate) reports = _pending.ToArray();\n            PD.ReportBatch(reports.Length);')
    once(reports, '            foreach (var report in reports) report.Flush();',
         '''            foreach (var report in reports)
            {
                report.Flush();
                PD.Count(PD.Counter.CounterReportsFlushed);
            }''')
    once(pipeline, 'DrawCount++;', 'DrawCount++; PD.Count(PD.Counter.Draws);', count=9)
    once(pipeline, '            Gd.Barriers.QueueMemoryBarrier();',
         '            PD.Count(PD.Counter.BarrierRequests);\n            Gd.Barriers.QueueMemoryBarrier();')
    once(pipeline, '        public void ComputeBarrier()\n        {',
         '        public void ComputeBarrier()\n        {\n            PD.Count(PD.Counter.BarrierRequests);')
    for call in ['            Gd.Api.CmdDispatch(CommandBuffer, (uint)groupsX, (uint)groupsY, (uint)groupsZ);',
                 '            Gd.Api.CmdDispatchIndirect(CommandBuffer, indirectBuffer.Get(Cbs, indirectBufferOffset, 12).Value, (ulong)indirectBufferOffset);']:
        once(pipeline, call, call + '\n            PD.Count(PD.Counter.Dispatches);')
    # Cache-hit and async-deferral fast paths return before these coarse scopes.
    once(state, '            ComputePipelineCreateInfo pipelineCreateInfo = new()',
         '            using var pipelineMeasurement = PD.Measure(PD.Phase.ComputePipelineBuild);\n            ComputePipelineCreateInfo pipelineCreateInfo = new()')
    once(state, '            bool isMoltenVk = gd.IsMoltenVk;',
         '            using var pipelineMeasurement = PD.Measure(PD.Phase.GraphicsPipelineBuild);\n            bool isMoltenVk = gd.IsMoltenVk;')
    once(query, '            _queue.FlushTo(this);',
         '            using (PD.Measure(PD.Phase.QueryReadback)) _queue.FlushTo(this);')
    once(buffer, '                fence.Wait();',
         '                using (PD.Measure(PD.Phase.BufferReadback)) fence.Wait();')
    for call in ['            _waitable.WaitForFences(_gd.Api, _device);',
                 '            _waitable.WaitForFences(_gd.Api, _device, offset, size);']:
        once(buffer, call, call.replace('            ', '            using (PD.Measure(PD.Phase.BufferReadback)) ', 1))
    once(cache, '        private unsafe long GetCacheDataSize(CacheState state)\n        {',
         '        private unsafe long GetCacheDataSize(CacheState state)\n        {\n            using var sizeMeasurement = PD.Measure(PD.Phase.CacheSizeProbe);')
    once(cache, '            string temporaryPath = state.Path + ".tmp";',
         '            using var saveMeasurement = PD.Measure(PD.Phase.CacheSave);\n            string temporaryPath = state.Path + ".tmp";')
    once(cache, '                state.SavedGeneration = generation;',
         '''                PD.Count(PD.Counter.CacheExports);
                PD.Count(PD.Counter.CacheExportBytes, written);
                state.SavedGeneration = generation;''')
    once(virtual, '            if (_virtualDependencies.Count == 1)\n            {',
         '            if (_virtualDependencies.Count == 1)\n            {\n                PD.Count(PD.Counter.VirtualDependencySingle);', count=2)
    once(virtual, '''            else
            {
                foreach (MultiRangeBuffer virtualBuffer in _virtualDependencies.OrderBy(x => x.ModificationSequenceNumber))''',
         '''            else
            {
                PD.Count(PD.Counter.VirtualDependencyMultiple);
                foreach (MultiRangeBuffer virtualBuffer in _virtualDependencies.OrderBy(x => x.ModificationSequenceNumber))''', count=2)
    for path, text in texts.items():
        path.write_text(text)
    return paths
