"""Refuse a second arena attempt after an opaque native mapping failure.

The host map helper has no proven rollback once blessing/remapping begins.
Keep the existing 1 GiB Hogwarts/update and 512 MiB default selection, but
never infer a clean refusal from a generic exception. Progressive fallback is
deliberately unavailable until a transactional helper contract exists.
"""
import hashlib
import json
from pathlib import Path


def edits(source):
    path = source / 'src/Ryujinx.Cpu/LightningJit/Cache/DualMappedNoWxCache.cs'
    text = path.read_text(encoding='utf-8-sig')
    old = '''            ulong size = Math.Max(DefaultCacheSize, DualMappedMemory.RequestedArenaSize);

            try
            {
                _sharedCacheAlloc = new(size);
            }
            catch (Exception) when (size > DefaultCacheSize)
            {
                // The helper could not prepare the larger arena: map the default.
                _sharedCacheAlloc = new(DefaultCacheSize);
            }'''
    new = '''            lock (_arenaGate)
            {
                if (_sharedCacheAlloc != null) return;
                if (_arenaAttempted)
                    throw new InvalidOperationException("A failed JIT mapping requires a new process.");
                ulong size = Math.Max(DefaultCacheSize, DualMappedMemory.RequestedArenaSize);
                // Set before entering native code, including an allocation
                // failure: the helper cannot prove a rollback after blessing.
                _arenaAttempted = true;
                _sharedCacheAlloc = new(size);
            }'''
    if text.count(old) != 1: raise RuntimeError('JIT arena retry drift')
    text = text.replace(old, new)
    old = '        private static DualMappedJitAllocator _sharedCacheAlloc;'
    if text.count(old) != 1: raise RuntimeError('JIT arena field drift')
    text = text.replace(old, old + '\n        private static readonly object _arenaGate = new();\n        private static bool _arenaAttempted;')
    return {path: text}


def apply(source):
    contract = json.loads(Path(__file__).with_name('jit-single-attempt-adapter-contract.json').read_text())
    actual = {p: hashlib.sha256((source / p).read_bytes()).hexdigest() for p in contract['before']}
    if actual == contract['after']: return [source / p for p in actual]
    if actual != contract['before']: raise RuntimeError('JIT single-attempt source drift')
    output = edits(source)
    if {str(p.relative_to(source)): hashlib.sha256(s.encode()).hexdigest() for p,s in output.items()} != contract['after']:
        raise RuntimeError('JIT single-attempt postimage drift')
    for path,text in output.items(): path.write_text(text)
    return list(output)
