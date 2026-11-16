"""The Core's own sched_yield: a yield that keeps the thread's priority (Ryujinx.Library.csproj, one C file).

IPA 759, Core 127b72b9, Hogwarts Legacy on the iPhone (private journals; [MeloNX:hot] profiles decoded with the Core's
symbol map, figures in docs/melonx-ryujinx-update-2026-11-16.md): in the two profiles taken under 26 FPS, 97 of 640 and
109 of 753 running samples of the six busiest threads are in libsystem_kernel's swtch_pri, all of them under
System.Threading.Thread.Yield (RhYield, PalSwitchToThread, sched_yield); the call sites name the contended paths of two
runtime locks for 94 and 109 of them: Lock.TryEnterSlow (Monitor.Enter of KCriticalSection,
MemoryTracking.VirtualMemoryEvent, RegionHandle.Reprotect, KTimeManager, KThread.HandlePostSyscall) and
LowLevelLock.WaitAndAcquire (the WaitSubsystem's process-wide lock, taken by every event Set and every Monitor.Wait).
The two profiles taken at 30 FPS have one such sample each.

On Apple platforms sched_yield is swtch_pri(0): when another thread is runnable, XNU depresses the caller to priority 0
until it runs again. docs/rpcs3-cell579.md measured it on macOS under five busy threads: up to 22.4 ms for one
sched_yield, 18 us for thread_switch(MACH_PORT_NULL, SWITCH_OPTION_NONE, 0), which yields to runnable threads of the
caller's priority and keeps that priority. adapt_darwin_spin_yield already made that substitution for the engine's own
spin (AdaptiveSpinEvent); the yields left in IPA 759 are the runtime's, inside the NativeAOT runtime and CoreLib.

.NET 10.0.0 (dotnet/runtime v10.0.0): Lock.TryEnterSlow spins up to 22 iterations and, from the tenth, yields at every
other one (LowLevelSpinWaiter.Wait, Thread.UninterruptibleSleep0); LowLevelLock.WaitAndAcquire spins 8 iterations and
yields at the fifth and seventh; both then block. Neither count nor yield is a setting of LowLevelLock, and the yield
itself is PalSwitchToThread's sched_yield in libRuntime.WorkstationGC.a.

Change: the Core defines sched_yield itself, in one C file compiled by the linker's own driver for the link's target
and added to the link's inputs. A symbol defined in an image's own objects is the one its references bind to, so every
sched_yield of the Core (the runtime's PalSwitchToThread, the collector's GCToOSInterface::YieldThread) is this one;
the symbol is hidden and no other image of the app is changed. It calls thread_switch with no thread, no option and no
time, except in two states of the runtime, where it calls swtch_pri(0), the system library's own sched_yield:
- while the runtime stops its threads or holds them stopped (RhpTrapThreads of threadstore.cpp, not zero from the
  start of ThreadStore::SuspendAllThreads to ResumeAllThreads);
- while a background collection runs (WKS::gc_heap::gc_background_running of gc.cpp, set by the background collector's
  thread from the start of its collection to its end).
The spin counts, the order of spin, yield and block, and every wait condition are the runtime's, unchanged.

Why the two exceptions: both have loops whose only way forward is a thread that may have a lower priority.
- SuspendAllThreads yields once per millisecond of waiting "to make sure such threads can run": a thread it must stop
  that needs the suspending thread's core (thread pool, background pipeline compilation), while guest threads in
  translated code keep running. Only a yield that depresses hands it the core.
- During a background collection's concurrent mark, exclusive_sync (bgc_mark_set, uoh_alloc_set and their
  spin_and_switch) loops on a yield alone, with no sleep and no block, until the other side leaves: an allocating
  thread of priority 47 waits there for the background collector's thread, which the runtime creates without a
  priority class. The large-object throttle (uoh_alloc_yield) is one yield meant for that same thread.
A first version without the first exception was withdrawn before any build; the second came from the independent
review of the next one. Everything inside those two states keeps today's yield.

What stays the same: a yield with no other runnable thread returns at once in both calls; every yield made in the two
states above. What differs, outside them: the yielding thread no longer lets threads of lower priority run before it.
The yields left there: the two locks above (bounded spin, then a block); the collector's spin locks
(enter_spin_lock, a 5 ms sleep at every thirty-second iteration); enter_gc_done_event_lock (a yield alone, contended
only around the collector's own lock); Lock.NativeAot.cs's wait for its static initialisation (start-up only).

Fail closed: the project must be the one the final preparation leaves; the build stops when the runtime identifier is
not one of the two iOS ones, when the link has no target triple, or when the object is not produced; the link itself
fails if the runtime no longer defines one of the two flags. build_core.sh then reads the linked library: no
sched_yield import left, thread_switch and swtch_pri imported, the marker string present.

Expected on the iPhone, to be read from the next IPA's [MeloNX:hot] lines: no running sample in swtch_pri under
Lock.TryEnterSlow or LowLevelSpinWaiter.Wait. Refuted, and the adapter removed, if those samples remain, or if the
slow profiles show more blocked samples in the two locks with fewer presented frames. No frame rate gain is claimed.
"""
import hashlib
from adapt_session import once

PROJECT = 'src/Ryujinx.Library/Ryujinx.Library.csproj'
C_FILE = 'src/Ryujinx.Library/RewindBoxRuntimeYield.c'
BASELINE = {
    PROJECT: '90efb63fec94331a7c78936a765d227967a08b870b58eb65c2d3743a6b954199',
}
MARKER = 'RewindBox runtime yield 1: sched_yield is thread_switch(0, 0, 0) outside thread suspension and background collection'
# WKS::gc_heap::gc_background_running, as the Mach-O symbol table names it (an assembler label is used verbatim).
BACKGROUND_FLAG = '__ZN3WKS7gc_heap21gc_background_runningE'
C_SOURCE = '''/* RewindBox (adapt_runtime_yield): the Core's own sched_yield.
 *
 * On Apple platforms sched_yield is swtch_pri(0): with another thread runnable, the caller is depressed to priority 0
 * until it runs again. thread_switch with no thread, SWITCH_OPTION_NONE and no time yields to the runnable threads of
 * the caller's priority and keeps that priority. Every sched_yield of this image (the NativeAOT runtime's
 * PalSwitchToThread, the collector's GCToOSInterface::YieldThread) binds to this definition; the symbol is hidden.
 *
 * In two states of the runtime the yield stays the system library's own, because a loop there moves on only when a
 * thread of possibly lower priority runs: while the runtime stops its threads or holds them stopped
 * (ThreadStore::SuspendAllThreads yields for a thread that needs its core), and while a background collection runs
 * (exclusive_sync loops on a yield alone until the background collector's thread leaves).
 *
 * Declared here instead of <mach/mach_traps.h>: kern_return_t thread_switch(mach_port_name_t, int,
 * mach_msg_timeout_t) and boolean_t swtch_pri(int), with kern_return_t and boolean_t int and the two other types
 * unsigned int on arm64.
 */
extern int thread_switch(unsigned int thread_name, int option, unsigned int option_time);
extern int swtch_pri(int pri);

/* threadstore.cpp of the NativeAOT runtime (EXTERN_C volatile uint32_t): not zero from the start of a thread
 * suspension to the resume. */
extern volatile unsigned int RhpTrapThreads;

/* gc.cpp of the workstation collector (VOLATILE(BOOL) WKS::gc_heap::gc_background_running, one int): not zero from
 * the start of a background collection to its end. The link fails if the runtime has no such symbol. */
extern volatile int rewindbox_gc_background_running __asm__("''' + BACKGROUND_FLAG + '''");

__attribute__((used, visibility("hidden")))
const char rewindbox_runtime_yield_marker[] = "''' + MARKER + '''";

__attribute__((visibility("hidden")))
int sched_yield(void)
{
    if (RhpTrapThreads != 0u || rewindbox_gc_background_running != 0) {
        /* What sched_yield of the system library does. */
        (void)swtch_pri(0);
    } else {
        /* MACH_PORT_NULL, SWITCH_OPTION_NONE, no time. */
        (void)thread_switch(0u, 0, 0u);
    }
    return 0;
}
'''
TARGET = '''
  <!-- RewindBox (adapt_runtime_yield): the Core's own sched_yield, a yield that keeps the thread's priority
       (thread_switch with no thread, SWITCH_OPTION_NONE and no time instead of swtch_pri(0)), except while the runtime
       stops its threads or collects in the background. The C file is compiled by the link's driver for the link's
       target and added to its inputs; fail closed otherwise. -->
  <Target Name="RewindBoxRuntimeYield" BeforeTargets="LinkNative" DependsOnTargets="SetupOSSpecificProps">
    <PropertyGroup>
      <_RewindBoxYieldSource>$(MSBuildThisFileDirectory)RewindBoxRuntimeYield.c</_RewindBoxYieldSource>
      <_RewindBoxYieldObject>$([MSBuild]::NormalizePath('$(MSBuildProjectDirectory)', '$(IntermediateOutputPath)', 'RewindBoxRuntimeYield.o'))</_RewindBoxYieldObject>
    </PropertyGroup>
    <Error Condition=" '$(RuntimeIdentifier)' != 'ios-arm64' and '$(RuntimeIdentifier)' != 'iossimulator-arm64' " Text="RewindBox runtime yield: no reviewed target for RuntimeIdentifier '$(RuntimeIdentifier)'." />
    <Error Condition=" '$(TargetTriple)' == '' " Text="RewindBox runtime yield: the link has no target triple." />
    <Error Condition=" '$(CppLinker)' == '' " Text="RewindBox runtime yield: the link has no compiler driver." />
    <Error Condition=" !Exists('$(_RewindBoxYieldSource)') " Text="RewindBox runtime yield: the source is missing: $(_RewindBoxYieldSource)" />
    <MakeDir Directories="$([System.IO.Path]::GetDirectoryName('$(_RewindBoxYieldObject)'))" />
    <Delete Files="$(_RewindBoxYieldObject)" />
    <Exec Command="&quot;$(CppLinker)&quot; --target=$(TargetTriple) -O2 -Wall -Werror -c &quot;$(_RewindBoxYieldSource)&quot; -o &quot;$(_RewindBoxYieldObject)&quot;" />
    <Error Condition=" !Exists('$(_RewindBoxYieldObject)') " Text="RewindBox runtime yield: the object was not produced: $(_RewindBoxYieldObject)" />
    <ItemGroup>
      <LinkerArg Include="&quot;$(_RewindBoxYieldObject)&quot;" />
    </ItemGroup>
    <Message Importance="high" Text="RewindBox runtime yield: linking $(_RewindBoxYieldObject) ($(TargetTriple)); sched_yield of this image is thread_switch without depression, swtch_pri during thread suspension and background collection." />
  </Target>
</Project>'''
TAIL = '''    <TrimMode>full</TrimMode>
  </PropertyGroup>
</Project>'''


def apply(source):
    for name, expected in BASELINE.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name
    project, c_file = source / PROJECT, source / C_FILE
    c_file.write_text(C_SOURCE, encoding='utf-8')
    # The project's last lines; adapt_gc wrote the two collector settings above them.
    once(project, TAIL, TAIL[:-len('</Project>')] + TARGET)
    return [project, c_file]
