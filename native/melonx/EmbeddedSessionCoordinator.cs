using System;

namespace Ryujinx.Library;

// One owner executes a session to completion. UI requests only signal it.
// Generation IDs prevent a delayed stop/pause from touching a later game.
internal sealed class EmbeddedSessionCoordinator
{
    private readonly object _gate = new();
    private long _generation;
    private int _state; // 0 idle, 1 prepared, 2 running, 3 stopping, 4 quarantined
    private bool _executing;
    private bool _stopRequested;
    private bool _inputsOpen;
    private Action _stop;
    private Action<bool> _pause;
    internal string LastFailure { get; private set; }
    internal int State { get { lock (_gate) return _state; } }

    internal long Prepare()
    {
        lock (_gate)
        {
            if (_state != 0) return -1;
            _generation = checked(_generation + 1);
            _state = 1;
            _stopRequested = false;
            _inputsOpen = true;
            LastFailure = null;
            return _generation;
        }
    }

    internal bool CancelPrepared(long generation)
    {
        lock (_gate)
        {
            if (generation != _generation || _executing || _state == 0 || _state == 4) return false;
            _state = 0;
            _inputsOpen = false;
            return true;
        }
    }

    internal bool Stop(long generation)
    {
        lock (_gate)
        {
            if (generation != _generation || _state == 0 || _state == 4) return false;
            _stopRequested = true;
            _inputsOpen = false;
            _state = 3;
            _stop?.Invoke();
            return true;
        }
    }

    internal bool Pause(long generation, bool paused)
    {
        lock (_gate)
        {
            if (generation != _generation || _state != 2 || _pause == null) return false;
            _pause(paused);
            return true;
        }
    }

    internal bool IsStopping { get { lock (_gate) return _stopRequested; } }

    internal bool WithInputs(long generation, Action input)
    {
        lock (_gate)
        {
            if (generation != _generation || !_inputsOpen || (_state != 1 && _state != 2)) return false;
            input();
            return true;
        }
    }

    // These callbacks must only signal live objects; never join or dispose.
    internal void PublishControls(Action stop, Action<bool> pause)
    {
        lock (_gate)
        {
            if (!_executing) throw new InvalidOperationException("No session owner.");
            _stop = stop;
            _pause = pause;
            _inputsOpen = !_stopRequested;
            if (_stopRequested) _stop();
        }
    }

    internal void WithdrawControls()
    {
        lock (_gate) { _stop = null; _pause = null; _inputsOpen = false; }
    }

    internal int Run(long generation, Func<int> run)
    {
        lock (_gate)
        {
            if (generation != _generation || _executing || (_state != 1 && _state != 3)) return 2;
            _executing = true;
            if (!_stopRequested) _state = 2;
        }
        bool failed = false;
        try { return IsStopping ? 0 : run(); }
        catch (Exception error)
        {
            failed = true;
            LastFailure = error.ToString();
            return 3;
        }
        finally
        {
            lock (_gate)
            {
                _stop = null;
                _pause = null;
                _executing = false;
                _inputsOpen = false;
                // A native/managed failure may have left partial engine state.
                // Require a process restart instead of reusing unknown handles.
                _state = failed ? 4 : 0;
            }
        }
    }
}
