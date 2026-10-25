using System;
using System.Threading;

namespace Ryujinx.Library;

// Shared by the actual WindowBase and the executable host checks. Teardown order:
// input stops first; the guest terminates while the GPU can still service its
// commands; then the render loop drains and only after that is any host handle
// released. The GPU render loop reports it has drained through
// NotifyRenderDrained, and the renderer is disposed from this controlling
// thread, not from the render worker.
//
// That split matters for the threaded backend renderer. With BackendThreading
// enabled the render worker blocks inside ThreadedRenderer.RenderLoop until the
// renderer is disposed; disposing it here, after the guest GPU loop has drained,
// unblocks that worker (mirroring the standalone WindowBase.Execute/Exit split).
// With threading off the worker returns from render() on its own and the dispose
// here is equivalent to the standalone Exit path on the controlling thread.
internal sealed class EmbeddedWindowLifetime
{
    private readonly object _gate = new();
    private bool _requested;
    private bool _running;
    private bool _rendering;
    private bool _used;
    private bool _disposed;
    private bool _guestStopFailed;
    internal bool GuestStopFailed { get { lock (_gate) return _guestStopFailed; } }
    private readonly ManualResetEventSlim _resume = new(true);
    // Set by the GPU render loop when its body has drained and will issue no
    // more guest GPU work: on the render worker when unthreaded, on the backend
    // renderer's own GPU thread when threaded. Also set defensively if render()
    // throws before the loop could signal, so the controlling thread never waits
    // on a drain that will not come.
    private readonly ManualResetEventSlim _renderDrained = new(false);
    internal bool InputAllowed { get { lock (_gate) return _running && !_requested; } }
    internal bool RenderAllowed { get { lock (_gate) return _rendering; } }

    internal void RequestStop()
    {
        lock (_gate)
        {
            if (_disposed) return;
            _requested = true;
            _resume.Set();
        }
    }

    internal void SetPaused(bool paused)
    {
        lock (_gate)
        {
            if (_disposed || _requested) return;
            if (paused) _resume.Reset(); else _resume.Set();
        }
    }

    internal void WaitUntilResumed() => _resume.Wait();

    // Called by WindowBase.Render's GPU loop when its while-body has exited and
    // all threaded commands were flushed. Safe to call more than once.
    internal void NotifyRenderDrained() => _renderDrained.Set();

    internal void Run(Action input, Action render, Action stopGuest, Action releaseGpu)
    {
        lock (_gate)
        {
            if (_used || _disposed) throw new InvalidOperationException("Window already used.");
            _used = true;
            // The loader has already created a guest before Window.Execute.
            // Even an early stop must start its GPU service: guest teardown
            // can wait for renderer readiness. Returning here strands that
            // guest, then the outer context.Dispose waits forever.
            // Cancellation before guest creation is handled by the session
            // coordinator; here we own an already-created guest.
            _running = _rendering = true;
        }
        Exception renderError = null;
        Thread worker = new(() =>
        {
            try { render(); }
            catch (Exception error) { renderError = error; }
            finally
            {
                // Render has ended (returned or threw). Signal stop so a
                // controlling thread still in input() unblocks, and report the
                // loop drained even if render() threw before the GPU loop could.
                // With the threaded renderer this runs after the dispose that
                // returned RenderLoop, so both calls are no-ops then.
                RequestStop();
                _renderDrained.Set();
            }
        }) { Name = "NeoStation.MeloNX.Render", IsBackground = true };
        bool started = false;
        try
        {
            worker.Start();
            started = true;
            if (InputAllowed) input();
        }
        finally
        {
            RequestStop();
            Exception stopError = null;
            // Terminate the guest while the render loop is still servicing its
            // GPU commands, exactly as the unthreaded path always has.
            try { stopGuest(); }
            catch (Exception error) { lock (_gate) _guestStopFailed = true; stopError = error; }

            // Now stop the render loop and wait for it to drain. The guest is
            // already stopping, so Device.WaitFifo unblocks and the loop breaks.
            lock (_gate) { _rendering = false; _resume.Set(); }
            // No timeout: a stuck loop keeps this session occupied, but we never
            // dispose the renderer while the GPU loop could still be running.
            _renderDrained.Wait();

            if (!GuestStopFailed)
            {
                // Release the GPU from this controlling thread. Threaded: this
                // disposes the ThreadedRenderer and unblocks the render worker
                // parked in RenderLoop. Unthreaded: render() has already
                // returned, so this is the standalone Exit dispose path.
                try { releaseGpu(); }
                catch (Exception error) { renderError = renderError == null ? error : new AggregateException(renderError, error); }
                // The worker is joinable in both modes now (threaded: RenderLoop
                // returned on dispose; unthreaded: render() already returned).
                if (started) worker.Join();
            }
            // Guest stop failed: the session is quarantined. Keep the renderer,
            // and the parked render worker when threaded, rooted until process
            // exit; the worker is a background thread and never blocks the
            // process. Do not join it (threaded RenderLoop would never return).

            lock (_gate) _running = false;

            if (stopError != null)
            {
                // Surface the failure so the session quarantines and RewindBox
                // asks for a restart, as before. Keep the outer type stable.
                throw new InvalidOperationException("Guest termination failed.",
                    renderError == null ? stopError : new AggregateException(stopError, renderError));
            }
        }
        if (renderError != null) throw new InvalidOperationException("Render worker failed.", renderError);
    }

    internal void Dispose(Action release)
    {
        lock (_gate)
        {
            if (_disposed) return;
            if (_running) throw new InvalidOperationException("Render worker is still live.");
            if (_guestStopFailed) throw new InvalidOperationException("Guest termination is unproven; retain resources until process exit.");
            _disposed = true;
            _resume.Dispose();
            _renderDrained.Dispose();
        }
        release();
    }
}
