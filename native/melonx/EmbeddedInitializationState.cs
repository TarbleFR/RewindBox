using System;

namespace Ryujinx.Library;

internal sealed class EmbeddedInitializationState
{
    private readonly object _gate = new();
    private string _root;
    private bool _failed;
    internal string LastFailure { get; private set; }
    internal bool Ready { get { lock (_gate) return _root != null && !_failed; } }

    internal int Initialize(string documents, string requested,
                            Func<bool> engineAlreadyInitialized, Action<string> initialize)
    {
        lock (_gate)
        {
            if (_failed) return 3;
            string root;
            try { root = EmbeddedDataRoot.Resolve(documents, requested); }
            catch (Exception error)
            {
                LastFailure = error.ToString();
                return 1;
            }
            if (_root != null) return string.Equals(_root, root, StringComparison.Ordinal) ? 0 : 2;
            if (engineAlreadyInitialized()) return 2;
            try
            {
                initialize(root);
                _root = root;
                return 0;
            }
            catch (Exception error)
            {
                _failed = true;
                LastFailure = error.ToString();
                return 3;
            }
        }
    }
}
