"""Opt-in query batching; mandatory waits/fences/Present remain unchanged."""
import hashlib
import json
from pathlib import Path


def edits(source):
    result = {}
    path = source / 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs'
    text = path.read_text(encoding='utf-8-sig')
    anchor = '        public ICounterEvent ReportCounter('
    if text.count(anchor) != 1: raise RuntimeError('VulkanRenderer drift')
    result[path] = text.replace(anchor, '''        public bool RelaxQueryFlushing { get; set; }

''' + anchor)
    path = source / 'src/Ryujinx.Graphics.Vulkan/AutoFlushCounter.cs'
    text = path.read_text(encoding='utf-8-sig')
    for old, new in [
        ('        private int _queryCount;', '        private int _queryCount;\n        private int _queriesSinceFlush;'),
        ('            _hasPendingQuery = false;', '            _hasPendingQuery = false;\n            _queriesSinceFlush = 0;'),
        ('            if (++_queryCount == InitialQueryCountForFlush)', '''            _queryCount++;
            _queriesSinceFlush++;
            // Bounded grouping only replaces speculative query thresholds.
            // Explicit conditional reads still use ShouldFlushQuery().
            if (_gd.RelaxQueryFlushing ? _queriesSinceFlush >= 128 : _queryCount == InitialQueryCountForFlush)'''),
        ('            if (_consecutiveQueries > MinConsecutiveQueryForFlush)', '            if (!_gd.RelaxQueryFlushing && _consecutiveQueries > MinConsecutiveQueryForFlush)'),
    ]:
        if text.count(old) != 1: raise RuntimeError('AutoFlushCounter drift: ' + old)
        text = text.replace(old, new)
    result[path] = text
    return result


def apply(source):
    contract = json.loads(Path(__file__).with_name('query-batching-adapter-contract.json').read_text())
    actual = {p: hashlib.sha256((source / p).read_bytes()).hexdigest() for p in contract['before']}
    if actual == contract['after']: return [source / p for p in actual]
    if actual != contract['before']: raise RuntimeError('Query batching source drift')
    output = edits(source)
    if {str(p.relative_to(source)): hashlib.sha256(s.encode()).hexdigest() for p,s in output.items()} != contract['after']:
        raise RuntimeError('Query batching postimage drift')
    for path,text in output.items(): path.write_text(text)
    return list(output)
