"""A gen0/gen1 collection no longer waits for the background collector's concurrent work (every title).

Evidence (private journals, counts and durations only):
- IPA 816-820 (303 journaled ephemeral collections, Hogwarts Legacy and Super Smash Bros. Ultimate): 14 pauses of
  300 ms or more, 9 of them promoting under 16 MiB (318 to 1 736 ms; gen0 collections of 545, 872 and 1 176 ms promote
  0 to 1 MiB); 21 of the 73 pauses of 100 ms or more promote under 16 MiB. One Hogwarts session of 470 s is stopped by
  collections 6.5 % of the time. IPA 821, Hogwarts Legacy, 176 s: 3.3 % stopped, two gen1 pauses of 316 and 322 ms
  (9 and 14 MiB promoted), the summary's longest gen1 809.9 ms; 21 background records, 10 of them the keep-alive's.
- Cause, read in dotnet/runtime v10.0.0 gc.cpp and executed here: the background collector's thread does its whole
  concurrent mark (handle table, mark list, dirtied pages, mark overflow) and its sweep in cooperative mode, and leaves
  it for a foreground collection only in gc_heap::allow_fgc, which does nothing unless g_fSuspensionPending is above
  zero. CoreCLR raises that flag around its thread suspension (IGCHeap::SetSuspensionPending); the NativeAOT 10.0.0
  runtime never does (the flag reads 0 at every yield and every sample of the control run below). The thread that
  starts a gen0 or gen1 collection then stays in ThreadStore::SuspendAllThreads until the background thread reaches one
  of its few preemptive points, and the collection's pause counts that wait.
- Host, NativeAOT 10.0.0 linux-x64, official runtime pack, workstation concurrent, 400 MiB of live linked objects and
  128 MiB of large ones, two threads allocating small objects and 256 KiB arrays, a background gen2 requested every
  2 s for 16 s (test/melonx_bgc_suspension_pending, four gate runs on a shared host): control, 5 to 9 ephemeral pauses
  of 250 ms or more, each promoting under 16 MiB, the longest 1 383 to 1 626 ms (gen0, 0 MiB promoted), 8.7 to 10.2 s
  stopped in the 14 s after the first request; with this change (two runs per gate run) the longest ephemeral pause
  is 35 to 64 ms and 2.1 to 2.8 s are stopped, 57 to 71 foreground suspensions begin inside a background collection,
  the object graph is intact, and the collector's own heap verification (DOTNET_HeapVerify=1) passes through 25 or 26
  such suspensions. The allocating threads' iterations are not reliably different on that host (0.82 to 1.25 million
  against 0.59 to 1.03): no throughput gain is claimed.

Change (RewindBoxRuntimeYield.c, the Core's own sched_yield of adapt_runtime_yield; nothing else): each sched_yield of
the image sets g_fSuspensionPending to 1 while a background collection runs (WKS::gc_heap::gc_background_running, the
flag that function already reads) and back to 0 once none does. The background collector's thread makes that call
itself right after it restarts the engine at the start of its concurrent phase (background_mark_phase: restart_vm
then GCToOSInterface::YieldThread), so the flag is up before its concurrent mark begins, and any other yield made
during the collection puts it up again. With the flag up the collector's own code does the rest, unchanged and
unrebuilt: allow_fgc lets a pending suspension through (EnablePreemptiveGC then DisablePreemptiveGC, which waits for
the foreground collection) at each object marked or swept; the flag's only other reader, the allocation lock's slow
path (WaitLongerNoInstru), skips its yield or 5 ms sleep at every eighth attempt and waits for a collection in
progress. No runtime library is rebuilt, replaced or relinked: the
collector's object code is the runtime pack's (the Core 663 lesson: the rebuilt gcwks object of Core 659-661 was
withdrawn after IPA 662's silent deaths).

Why not from the suspension itself: NativeAOT 10.0.0's suspension loop waits in minipal_microdelay (a nanosleep of up
to 128 microseconds between its passes) and hardly ever reaches its sched_yield: the image made 46 to 112 depressing
yields in all during a control run and its 9 to 10 s of such waits. A first version that raised the flag only while
threads were being stopped left pauses of 160 to 290 ms on the host whenever no other thread happened to yield.

Not changed: which collections run, when, their budgets and settings; the keep-alive (its request still keeps the
background thread alive; its cost to play is the wait this removes); the yield's own two behaviours. The flag stays 1
after a background collection until the next sched_yield of the image (its only reader then is that slow path).
Cost: the two mode changes at each allow_fgc. On the host, six background gen2s of 10 million 40-byte objects with
nothing else running take 12.4 to 13.7 s of processor time against 11.7 to 12.1 s (7 to 15 % more, four runs each;
the smallest objects are the worst case), on the background collector's own thread. The background collection itself
lasts longer on the clock, since foreground collections now run inside it instead of waiting for it.

Limits: the host runs the regions build of gc.cpp, the iPhone the segments build of the same file (the same allow_fgc
calls and scan_background_roots); what a foreground collection costs inside a concurrent mark on the device, and that
none of it disturbs a session, only a device run shows. Stretches of the concurrent phase without allow_fgc keep their
wait. A foreground collection inside the mark also scans the background mark stack.

Expected on the iPhone (next build, Hogwarts Legacy, same route): gcPause ephemeral lines of 300 ms or more that
promote under 16 MiB: none (IPA 816-820: 9; 821: 2 in 176 s), and those of 100 ms or more that promote under 16 MiB
rare (816-820: 21); the gcPause summary's longest gen0 under 150 ms; gcEvent fellBackFromBackground 0 and "requests
run blocking 0" as before. Pauses that promote tens of MiB are the collection's own work and are not treated here.
Refuted, and the adapter removed, if such pauses remain, or if a session ends by itself with this build and not
without it. No frame rate gain is claimed.

Fail closed: the C file must be the one adapt_runtime_yield wrote; the link fails if the runtime has no
g_fSuspensionPending. Rollback: drop this adapter from prepare_embedded.py and ORDER.
"""
import hashlib
from adapt_session import once

C_FILE = 'src/Ryujinx.Library/RewindBoxRuntimeYield.c'
BASELINE = {
    C_FILE: 'cba1ff349729371b9b215823b141081f5250144645c5c881cc3f48cdd3ede061',
}
MARKER = 'RewindBox suspension pending 1: g_fSuspensionPending is 1 while a background collection runs'

DECLARATION_OLD = '''__attribute__((used, visibility("hidden")))
const char rewindbox_runtime_yield_marker[] = '''
DECLARATION_NEW = '''/* RewindBox (adapt_bgc_suspension_pending): gccommon.cpp of the collector (VOLATILE(int32_t) g_fSuspensionPending,
 * one int). While it is above zero the background collector's thread lets a pending thread suspension through at each
 * gc_heap::allow_fgc() of its concurrent mark and sweep (it leaves cooperative mode and comes back, which waits for
 * the foreground collection), and the allocation lock's slow path (WaitLongerNoInstru) waits for a collection in
 * progress instead of yielding. CoreCLR raises it around its thread suspension; the NativeAOT 10.0.0 runtime never
 * does, so a gen0 or gen1 collection waited for the whole concurrent mark. The link fails if the runtime has no such
 * symbol. */
extern volatile int g_fSuspensionPending;

__attribute__((used, visibility("hidden")))
const char rewindbox_suspension_pending_marker[] = "''' + MARKER + '''";

__attribute__((used, visibility("hidden")))
const char rewindbox_runtime_yield_marker[] = '''

BODY_OLD = '''int sched_yield(void)
{
    if (RhpTrapThreads != 0u || rewindbox_gc_background_running != 0) {
'''
BODY_NEW = '''int sched_yield(void)
{
    /* RewindBox (adapt_bgc_suspension_pending): the flag is 1 while a background collection runs. The background
     * collector's thread makes this call itself when its concurrent phase starts (restart_vm, then YieldThread), and
     * the first yield of the image after the collection puts the flag back to 0. A yield that read "no background
     * collection" just before one started reads the flag again after its write. */
    if (rewindbox_gc_background_running != 0) {
        if (g_fSuspensionPending == 0) {
            g_fSuspensionPending = 1;
        }
    } else if (g_fSuspensionPending != 0) {
        g_fSuspensionPending = 0;
        if (rewindbox_gc_background_running != 0) {
            g_fSuspensionPending = 1;
        }
    }

    if (RhpTrapThreads != 0u || rewindbox_gc_background_running != 0) {
'''

PAIRS = (
    (DECLARATION_OLD, DECLARATION_NEW),
    (BODY_OLD, BODY_NEW),
)


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[C_FILE], old, new)
    return list(paths.values())
