"""Pass synchronous texture-group visitor state explicitly, without closures.

SynchronizeMemory and FlushModified capture their texture and mutable locals on
all calls. SignalModified and SynchronizeDependents allocate instance delegates.
The other hot visitors retain three separate instance delegates per group. A
static callback plus a state parameter by reference preserves the existing range
walk and callback order, while keeping each call's state on its own stack frame.
No callback is stored or queued, so recursive calls cannot overwrite an outer
texture/flush result. Copy-dependency setup uses the same explicit-state API.
"""
from adapt_session import once


def _method(text, signature):
    start = text.index('        ' + signature + '\n')
    end = text.index('\n        /// <summary>', start)
    return text[start:end]


def apply(source):
    path = source / 'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs'
    once(path, '''        private delegate bool HandlesCallbackDelegate(int baseHandle, int regionCount, bool split = false, bool specialData = false);

        private readonly HandlesCallbackDelegate _signalModifyingCallback;
        private readonly HandlesCallbackDelegate _discardDataCallback;
        private readonly HandlesCallbackDelegate _checkDirtyCallback;
''', '''        // This visitor is synchronous. Keep mutable per-call state in the caller,
        // never on the group, so nested texture operations remain independent.
        private delegate bool HandlesCallbackDelegate<TState>(TextureGroup owner, ref TState state, int baseHandle, int regionCount, bool split = false, bool specialData = false);
''')
    once(path, '''
            _signalModifyingCallback = SignalModifyingCallback;
            _discardDataCallback = DiscardDataCallback;
            _checkDirtyCallback = CheckDirtyCallback;
''', '')
    once(path, '''            EvaluateRelevantHandles(texture, _checkDirtyCallback, out bool dirty, consume);''', '''            EvaluateRelevantHandles(texture, ref consume,
                static (TextureGroup owner, ref bool state, int baseHandle, int regionCount, bool split, bool specialData) =>
                    owner.CheckDirtyCallback(baseHandle, regionCount, split, specialData),
                out bool dirty, consume);''')
    once(path, '''            EvaluateRelevantHandles(texture, _discardDataCallback, out _);''', '''            EvaluateRelevantHandles(texture, ref texture,
                static (TextureGroup owner, ref Texture state, int baseHandle, int regionCount, bool split, bool specialData) =>
                    owner.DiscardDataCallback(baseHandle, regionCount, split, specialData),
                out _);''')
    once(path, '''            EvaluateRelevantHandles(texture, _signalModifyingCallback, out _, bound);''', '''            EvaluateRelevantHandles(texture, ref bound,
                static (TextureGroup owner, ref bool state, int baseHandle, int regionCount, bool split, bool specialData) =>
                    owner.SignalModifyingCallback(baseHandle, regionCount, split, specialData),
                out _, bound);''')

    text = path.read_text(encoding='utf-8-sig')
    for name in ('SynchronizeMemory', 'SynchronizeDependents', 'SignalModified'):
        method = _method(text, 'public void ' + name + '(Texture texture)')
        changed = method.replace(
            '            EvaluateRelevantHandles(texture, (baseHandle, regionCount, split, bound) =>\n',
            '            EvaluateRelevantHandles(texture, ref texture, static (TextureGroup owner, ref Texture texture, int baseHandle, int regionCount, bool split, bool bound) =>\n')
        assert changed != method, name
        # Only the callback accesses owner-qualified fields. Keep its surrounding
        # pre-flush and sequence bookkeeping in precisely the original order.
        callback = changed.index('            EvaluateRelevantHandles(')
        prefix, body = changed[:callback], changed[callback:]
        for old, new in (
            ('_handles', 'owner._handles'), ('_loadNeeded', 'owner._loadNeeded'),
            ('_context', 'owner._context'), ('SynchronizePartial(', 'owner.SynchronizePartial('),
        ):
            body = body.replace(old, new)
        text = text.replace(method, prefix + body)

    method = _method(text, 'public bool FlushModified(Texture texture, bool tracked)')
    changed = method.replace('''            bool flushed = false;

            EvaluateRelevantHandles(texture, (baseHandle, regionCount, split, bound) =>
''', '''            (Texture Texture, bool Tracked, bool Flushed) state = (texture, tracked, false);

            EvaluateRelevantHandles(texture, ref state, static (TextureGroup owner, ref (Texture Texture, bool Tracked, bool Flushed) state, int baseHandle, int regionCount, bool split, bool bound) =>
''')
    assert changed != method
    callback = changed.index('            EvaluateRelevantHandles(')
    tail = changed.index('            Storage.SignalModifiedDirty();', callback)
    prefix, body, suffix = changed[:callback], changed[callback:tail], changed[tail:]
    body = body.replace('                int startSlice = 0;', '                bool tracked = state.Tracked;\n                int startSlice = 0;')
    body = body.replace('_handles', 'owner._handles').replace('FlushSliceRange(', 'owner.FlushSliceRange(')
    body = body.replace('flushed = true;', 'state.Flushed = true;').replace('texture.Flush(tracked);', 'state.Texture.Flush(tracked);')
    suffix = suffix.replace('return flushed;', 'return state.Flushed;')
    text = text.replace(method, prefix + body + suffix)

    # Reuse the original walkers, changing only visitor plumbing. No new region
    # enumeration, range arithmetic, snapshots or list ownership is introduced.
    for signature in (
        'private void EvaluateRelevantHandles(Texture texture, HandlesCallbackDelegate callback, out bool result, bool specialData = false)',
        'private void EvaluateRelevantHandles(int firstLayer, int firstLevel, int slices, int levels, HandlesCallbackDelegate callback, out bool result, bool specialData = false)',
    ):
        method = _method(text, signature)
        changed = method.replace('EvaluateRelevantHandles(', 'EvaluateRelevantHandles<TState>(', 1)
        changed = changed.replace('HandlesCallbackDelegate callback', 'ref TState state, HandlesCallbackDelegate<TState> callback')
        changed = changed.replace('result = callback(', 'result = callback(this, ref state, ')
        changed = changed.replace('texture.Info.Levels, callback, out result', 'texture.Info.Levels, ref state, callback, out result')
        text = text.replace(method, changed)

    old = '''            EvaluateRelevantHandles(firstLayer, firstLevel, other.Info.GetSlices(), other.Info.Levels, (baseHandle, regionCount, split, specialData) =>
            {
                targetRange.Add((baseHandle, regionCount));
                return true;
            }, out _);
            otherGroup.EvaluateRelevantHandles(other, (baseHandle, regionCount, split, specialData) =>
            {
                otherRange.Add((baseHandle, regionCount));
                return true;
            }, out _);'''
    new = '''            EvaluateRelevantHandles(firstLayer, firstLevel, other.Info.GetSlices(), other.Info.Levels, ref targetRange,
                static (TextureGroup owner, ref List<(int BaseHandle, int RegionCount)> state, int baseHandle, int regionCount, bool split, bool specialData) =>
                {
                    state.Add((baseHandle, regionCount));
                    return true;
                }, out _);
            otherGroup.EvaluateRelevantHandles(other, ref otherRange,
                static (TextureGroup owner, ref List<(int BaseHandle, int RegionCount)> state, int baseHandle, int regionCount, bool split, bool specialData) =>
                {
                    state.Add((baseHandle, regionCount));
                    return true;
                }, out _);'''
    assert text.count(old) == 1
    text = text.replace(old, new)
    path.write_text(text, encoding='utf-8')
    return [path]
