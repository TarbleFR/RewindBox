"""Let the gen0 budget grow during scene transitions: fewer collections, less premature promotion, shorter total pause.

IPA 650 / 643 (Hogwarts Legacy, maintainer's iPhone, private logs, not in the repository): at every scene transition
the managed allocation rate reaches 600-1100 MiB per 5-second window and the GC pause 200-800 ms in that window (S1
797 MiB / 312 ms, S2 1137 MiB / 688 ms, IPA 643 750 MiB / 298 ms), against about 45 MiB and 0-50 ms in steady gameplay.

Mechanism (.NET 10 gc.cpp, read for this change): the engine runs workstation GC with background GC enabled (the
evaluated RuntimeHostConfigurationOption items of the iOS publish carry no System.GC.Concurrent, whose default is
true; the device journals a .NET_BGC thread). With background GC, init_static_data caps the gen0 budget at
max(gen0 minimum, 6 MiB), and the minimum comes from the largest cache the OS reports (hw.perflevel0.l2cachesize on an
iPhone: 12-16 MiB, times 4/5 times 5/8 = 6-8 MiB). So a transition of 1 GiB runs 130-170 gen0 collections per window;
each one stops every managed thread, scans the cards of a heap of several hundred MiB and promotes whatever the
transition keeps alive for a few frames into gen1 (whose budget is capped at 6 MiB too) and on into gen2, where it dies
later as fragmentation.

Change: System.GC.Gen0MaxBudget = 64 MiB (RuntimeHostConfigurationOption, embedded by ILC as a runtime knob; the GC
reads it as its public config, gcconfig.h GCGen0MaxBudget). The minimum is unchanged, so the budget only rises when
survival is high (desired_new_allocation: survivors times the gen0 growth factor, bounded by the maximum). Nothing else
changes: ConserveMemory 5 and HighMemoryPercent 99 stay, Library.cs and its teardown collections are untouched.

Measured effect (test/melonx_gc_latency_test.py, NativeAOT linux-x64 host with the production project's evaluated GC
knobs and the iPhone's gen0 minimum, median of 3 seeds): see dist/melonx/gc-latency-checks.json. In development, on the
transition workload, total pause -35 % (2731 -> 1777 ms), gen0 collections 416 -> 60, frame p99 87 -> 41 ms, peak
committed +40 MiB; on a scene unload leaving 85 % of gen2 fragmented, total pause -18 %.

Evaluated and not adopted (measured by the same test): GCLatencyMode.SustainedLowLatency for the session. In the .NET 10
GC it only skips the per-heap fragmentation elevation to a blocking gen2 (generation_to_condemn, gen_max_high_frag_p);
joined_generation_to_condemn's ConserveMemory rule (gen2+LOH fragmentation above 1 - 5/10 -> blocking, compacting)
ignores the latency mode, so under ConserveMemory 5 the blocking compacting gen2 after a fragmenting unload happens with
or without it (measured). Only with ConserveMemory 0 did it remove that collection, at the cost of a larger heap and a
longer total pause. Raising the gen0 minimum (GCgen0size) has no public knob on NativeAOT and would cost memory in
steady gameplay too.

Limits: the blocking compacting gen2 itself (ConserveMemory's fragmentation rule) is not removed; its pause is not
shortened. Up to 56 MiB more gen0 space during transitions. Not measured on an iPhone: the device check is the
performance window's collections array (MiB allocated per gen0 collection should rise from about 8 to tens of MiB in
transition windows). Fail closed on drift.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Library/Ryujinx.Library.csproj': '90efb63fec94331a7c78936a765d227967a08b870b58eb65c2d3743a6b954199',
}

GEN0_MAX_BUDGET = 64 * 1024 * 1024

ANCHOR = '    <RuntimeHostConfigurationOption Include="System.GC.HighMemoryPercent" Value="99" />\n'
ADDED = ('    <!-- RewindBox (adapt_gc_latency): let the gen0 budget grow while survival is high (scene transitions);\n'
         '         the background-GC default caps it at max(cache-derived minimum, 6 MiB). -->\n'
         '    <RuntimeHostConfigurationOption Include="System.GC.Gen0MaxBudget" Value="%d" />\n' % GEN0_MAX_BUDGET)


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    project = paths['src/Ryujinx.Library/Ryujinx.Library.csproj']
    once(project, ANCHOR, ANCHOR + ADDED)
    return [project]
