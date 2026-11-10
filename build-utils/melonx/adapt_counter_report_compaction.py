"""Compact completed report prefixes without changing concurrent drain semantics."""
from pathlib import Path

RELATIVE = 'src/Ryujinx.Graphics.Gpu/Memory/CounterCache.cs'
BEFORE = '            lock (_gate) foreach (var report in reports) _pending.Remove(report);'
AFTER = '''            lock (_gate)
            {
                // Appends preserve this snapshot's prefix. Compact it once
                // instead of shifting the tail for every completed report.
                // A concurrent/reentrant drain or cancellation may change the
                // prefix; retain the original exact removals in that case.
                bool prefixMatches = _pending.Count >= reports.Length;
                for (int i = 0; prefixMatches && i < reports.Length; i++)
                    prefixMatches = object.ReferenceEquals(_pending[i], reports[i]);
                if (prefixMatches)
                    _pending.RemoveRange(0, reports.Length);
                else
                    foreach (var report in reports) _pending.Remove(report);
            }'''


def apply(source):
    path = Path(source) / RELATIVE
    text = path.read_text(encoding='utf-8-sig')
    if text.count(AFTER) == 1 and BEFORE not in text:
        return [path]
    if text.count(BEFORE) != 1:
        raise RuntimeError('Counter report compaction adapter anchor drift: ' + RELATIVE)
    path.write_text(text.replace(BEFORE, AFTER))
    return [path]
