"""Avoid sorting one virtual dependency while preserving the owning HashSet."""
import hashlib
from pathlib import Path

RELATIVE = 'src/Ryujinx.Graphics.Gpu/Memory/Buffer.cs'
BASELINE = '1ca3cd05e3617952838b2631e5ec5fee67a0069164ea7e0613baefd6b4b92769'
CONSUMERS = {
    'src/Ryujinx.Graphics.Gpu/Memory/MultiRangeBuffer.cs': 'ebb48b7a07c3b370590ab982e43024d1bd124972d5635cf39ce50033370370a8',
    'src/Ryujinx.Graphics.Gpu/Memory/BufferModifiedRangeList.cs': '94129cf9cdcb552e5e614f4aaf75914f1cbd7e222448e9474025ace69ea36580',
}


def replacements():
    for arguments in ('this', 'address, size'):
        before = '''            foreach (MultiRangeBuffer virtualBuffer in _virtualDependencies.OrderBy(x => x.ModificationSequenceNumber))
            {
                currentVirtualBuffer = virtualBuffer;
                virtualBuffer.ConsumeModifiedRegion(''' + arguments + ''', copyRange);
            }'''
        after = '''            if (_virtualDependencies.Count == 1)
            {
                // Capture before the callback can mutate dependencies or reenter.
                // One element has no ordering work; retain the existing HashSet.
                using var dependency = _virtualDependencies.GetEnumerator();
                if (dependency.MoveNext())
                {
                    currentVirtualBuffer = dependency.Current;
                    currentVirtualBuffer.ConsumeModifiedRegion(''' + arguments + ''', copyRange);
                }
            }
            else
            {
''' + ''.join('    ' + line + '\n' for line in before.splitlines()) + '''            }'''
        yield before, after


def apply(source):
    source = Path(source)
    path = source / RELATIVE
    for relative, expected in CONSUMERS.items():
        if hashlib.sha256((source / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Single virtual dependency consumer drift: ' + relative)
    text = path.read_text(encoding='utf-8-sig')
    changes = list(replacements())
    if all(text.count(after) == 1 and before not in text for before, after in changes):
        return [path]
    if hashlib.sha256(path.read_bytes()).hexdigest() != BASELINE:
        raise RuntimeError('Single virtual dependency baseline drift: ' + RELATIVE)
    for before, after in changes:
        if text.count(before) != 1:
            raise RuntimeError('Single virtual dependency anchor drift: ' + RELATIVE)
        text = text.replace(before, after)
    path.write_text(text)
    return [path]
