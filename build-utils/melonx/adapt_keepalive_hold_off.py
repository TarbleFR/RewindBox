"""The background-GC keep-alive requests its windows again when the device is short of memory (every title): IPA 736's behaviour.

adapt_keepalive_memory_hold (IPA 738) held the keep-alive's background gen2 request while the device had 8 % of its
memory available or less, on the premise that the runtime's own gen2s were one to three minutes apart in play and that
each mark pulled the managed heap out of the compressor. IPA 739 and 740 (private journals; Hogwarts Legacy, pid 5159
and 5954) refute it by its own criterion:
- the workstation BGC thread leaves after its 20 s idle wait (gc.cpp bgc_thread_function; .NET 10.0.0 official GC); with
  the window held, nothing was requested before that exit, and the runtime's next gen2 met the thread start race and ran
  blocking: 334.5 ms at 03:18:34 (739) and 518.3 ms at 04:33:31 (740, fellBackFromBackground 1, device 4-6 %), the
  longest in-game GC pause of the session; 736 (no hold) had 17 requests and no fallback in 250 s;
- the runtime's own gen2s were 14 to 22 s apart in streaming, not minutes;
- decompression did not drop, and the managed heap grew while held.

Change (EmbeddedSession.cs, BackgroundGcKeepAlive.Loop): the keep-alive acts on its own decision again
(BackgroundGcKeepAlive.Decide), not on KeepAliveMemoryHold.Apply's; the hold's class stays, unused, and its summary
reports no window held. Every other rule of the keep-alive (fragmentation guard, dormancy, heap size) is unchanged.

Expected on the device: no fallen-back blocking gen2 in play (gcEvent fellBackFromBackground 0); background gen2s
requested 12 to 16 s after the previous one, as on IPA 736. Not measured on an iPhone. Applied after
adapt_keepalive_memory_hold (its post-image). Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail
closed on drift.
"""
import hashlib
from adapt_session import once

SESSION = 'src/Ryujinx.Library/EmbeddedSession.cs'
BASELINE = {SESSION: '80f67552d100c78398ceeaf8a22861e9672347a9b081f08a67c5a67d2430963f'}

LOOP_OLD = '''                // RewindBox (adapt_keepalive_memory_hold): no request while the device is short of memory.
                switch (KeepAliveMemoryHold.Apply(run.Generation, Decide(lastChange < 0 ? -1 : now - lastChange, ReadHeapBytes(), fragmentation)))
'''
LOOP_NEW = '''                // RewindBox (adapt_keepalive_hold_off): the keep-alive's own decision, short of memory too. Holding the
                // request (adapt_keepalive_memory_hold) let the BGC thread leave, and the runtime's next gen2 ran blocking.
                switch (Decide(lastChange < 0 ? -1 : now - lastChange, ReadHeapBytes(), fragmentation))
'''


def apply(source):
    path = source / SESSION
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, SESSION
    # Apply is called from the loop only.
    assert not digests or path.read_text(encoding='utf-8-sig').count('KeepAliveMemoryHold.Apply(') == 1, SESSION
    once(path, LOOP_OLD, LOOP_NEW)
    return [path]
