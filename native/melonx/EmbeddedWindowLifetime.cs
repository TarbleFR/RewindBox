using System;
using System.Threading;

namespace Ryujinx.Library;

// Shared by the actual WindowBase and the executable host checks. Input stops
// first; the guest terminates while the GPU can still service its commands;
// then the render worker ends before any host handle may be released.
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

    internal void Run(Action input, Action render, Action stopGuest, Action releaseGpu)
    {
        lock (_gate)
        {
            if (_used || _disposed) throw new InvalidOperationException("Window already used.");
            _used = true;
            if (_requested) return;
            _running = _rendering = true;
        }
        using ManualResetEventSlim guestStopped = new(false);
        Exception renderError = null;
        Thread worker = new(() =>
        {
            try { render(); }
            catch (Exception error) { renderError = error; }
            finally
            {
                RequestStop();
                guestStopped.Wait();
                try { if (!GuestStopFailed) releaseGpu(); }
                catch (Exception error) { renderError = renderError == null ? error : new AggregateException(renderError, error); }
            }
        }) { Name = "NeoStation.MeloNX.Render", IsBackground = true };
        bool started = false;
        try
        {
            worker.Start();
            started = true;
            input();
        }
        finally
        {
            RequestStop();
            try { stopGuest(); }
            catch
            {
                lock (_gate) _guestStopFailed = true;
                throw;
            }
            finally
            {
                lock (_gate) { _rendering = false; _resume.Set(); }
                guestStopped.Set();
                // No timeout followed by unsafe disposal. A stuck worker keeps
                // this session occupied and cannot overlap a second game.
                if (started) worker.Join();
                lock (_gate) _running = false;
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
        }
        release();
    }
}
