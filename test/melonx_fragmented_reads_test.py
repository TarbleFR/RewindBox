#!/usr/bin/env python3
"""Run the real fragmented-read paths in control and candidate builds and compare them.

The control is the prepared source before adapt_fragmented_reads (the delivered 609
Core); the candidate is that source with adapt_fragmented_reads and every later adapter
that edits a composed file applied in preparation order (array deltas, then the Hogwarts
DMA copies), and it must equal the final prepared source when one is given. A test-only
probe is compiled into a disposable copy of Ryujinx.Graphics.Gpu for each side and drives
MemoryManagerHostTracked, the software MemoryManager, PhysicalMemory, Buffer.LoadRegion, the GPU MemoryManager and the command prefetch. Same bytes, tracking
and zero contract are required; the candidate must stop allocating per fragmented read.
Host x64 Release execution: it proves bytes and allocations, not Apple timing or FPS.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_fragmented_reads import apply, NAMES  # noqa: E402
from adapt_gpu_work_diagnostics import apply as apply_work, NAMES as WORK_NAMES  # noqa: E402
from adapt_bindless_array_deltas import apply as apply_arrays, NAMES as ARRAY_NAMES  # noqa: E402
from adapt_hogwarts_dma_copies import apply as apply_dma, NAMES as DMA_NAMES, LIBRARY as DMA_LIBRARY  # noqa: E402
from adapt_queued_syncpoints import apply as apply_queued, NAMES as QUEUE_NAMES  # noqa: E402
from adapt_host_qos_pipeline_budget import apply as apply_host, NAMES as HOST_NAMES  # noqa: E402
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import ORDER, apply_present  # noqa: E402

DIAGNOSTICS = 'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'
from adapt_pipeline_warmup_parity import BASELINE as WARMUP_BASELINE  # noqa: E402
from adapt_device_short_trim import BASELINE as TRIM_BASELINE  # noqa: E402
from adapt_moltenvk_barrier_ordering import BASELINE as BARRIER_BASELINE  # noqa: E402
from adapt_descriptor_scratch_all_titles import BASELINE as SCRATCH_BASELINE  # noqa: E402
from adapt_readback_occupied_attribution import BASELINE as OCCUPIED_BASELINE  # noqa: E402
from adapt_pipeline_miss_context import BASELINE as MISS_BASELINE  # noqa: E402
from adapt_readback_receivers import BASELINE as RECEIVERS_BASELINE  # noqa: E402
from adapt_present_source_attribution import BASELINE as PRESENT_BASELINE  # noqa: E402
# Core 639, 642 and 644: the PR #153, #154 and #156 lots' files join the composition, so the final GPU and Vulkan build binds
# every changed file.
COMPOSED = sorted(set(NAMES) | set(WORK_NAMES) | set(ARRAY_NAMES) | set(DMA_NAMES) | set(QUEUE_NAMES) | set(HOST_NAMES) |
                  set(WARMUP_BASELINE) | set(TRIM_BASELINE) | set(BARRIER_BASELINE) | set(SCRATCH_BASELINE) |
                  set(OCCUPIED_BASELINE) | set(MISS_BASELINE) | set(RECEIVERS_BASELINE) |
                  set(PRESENT_BASELINE) | {DIAGNOSTICS})
# Production files the candidate build compiles and this receipt binds (the region type is unchanged). Library.cs
# (Ryujinx.Library) is outside the GPU assembly closure: it is composed and bound here, compiled by NativeAOT.
COMPILED = sorted((set(COMPOSED) - {DMA_LIBRARY}) | {'src/Ryujinx.Graphics.Gpu/Memory/ReadOnlyRegion.cs'})
INPUTS = ['test/melonx_fragmented_reads_test.py', 'test/melonx_fragmented_reads/FragmentedReadsProbe.cs',
          'build-utils/melonx/adapt_fragmented_reads.py', 'build-utils/melonx/adapt_gpu_work_diagnostics.py',
          'build-utils/melonx/adapt_bindless_array_deltas.py', 'build-utils/melonx/adapt_hogwarts_dma_copies.py',
          'build-utils/melonx/adapt_queued_syncpoints.py', 'build-utils/melonx/adapt_host_qos_pipeline_budget.py',
          'build-utils/melonx/adapt_pipeline_warmup_parity.py', 'build-utils/melonx/adapt_device_short_trim.py',
          'build-utils/melonx/adapt_moltenvk_barrier_ordering.py', 'build-utils/melonx/adapt_descriptor_scratch_all_titles.py',
          'build-utils/melonx/adapt_readback_occupied_attribution.py', 'build-utils/melonx/adapt_pipeline_miss_context.py',
          'build-utils/melonx/adapt_readback_receivers.py', 'build-utils/melonx/adapt_present_source_attribution.py',
          'test/melonx_adapter_control.py', 'native/melonx/EmbeddedPerformanceDiagnostics.cs']
# One fragment of a real anchor per adapted file; altering it must stop the whole adapter.
DRIFT = {
    'src/Ryujinx.Memory/IVirtualMemoryManager.cs': 'ReadOnlySpan<byte> GetSpan(ulong va, int size, bool tracked = false);',
    'src/Ryujinx.Cpu/Jit/MemoryManagerHostTracked.cs': 'public override bool TryReadUnsafe(ulong va, int length, out Span<byte> data)',
    'src/Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs': 'return _cpuMemory.GetSpan(address, size, tracked);',
    'src/Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs': 'physicalMemory.GetSpan(pa, size, tracked).CopyTo(data[..size]);',
    'src/Ryujinx.Graphics.Gpu/Memory/Buffer.cs': '_physicalMemory.GetSpan(mAddress, (int)mSize)',
    'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs': 'public void Prefetch(MemoryManager memoryManager)',
    'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs': 'memoryManager.GetSpan(dstGpuVa + (ulong)dstBaseOffset, dstSize).CopyTo(dstSpan);',
    'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs': 'memoryManager.Physical.GetSpan(srcAddress, (int)size)',
}

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path, help='delivered prepared source (control)')
parser.add_argument('--candidate-source', type=Path, help='actual final prepared source')
parser.add_argument('--report', type=Path, default=ROOT / 'dist/melonx/fragmented-reads-checks.json')
args = parser.parse_args()
SOURCE = args.source.resolve()
CANDIDATE = args.candidate_source.resolve() if args.candidate_source else None
PROBE = ROOT / 'test/melonx_fragmented_reads/FragmentedReadsProbe.cs'
dotnet = os.environ.get('DOTNET', 'dotnet')
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
checks = 0


def check(ok, message):
    global checks
    if not ok:
        raise AssertionError(message)
    checks += 1


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def project_closure(src, project):
    seen, pending = set(), [project]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        text = (src / name / (name + '.csproj')).read_text(encoding='utf-8-sig')
        pending += re.findall(r'ProjectReference Include="\.\.\\([^\\"]+)\\', text)
    return sorted(seen)


def compose(target):
    """The preparation order: current diagnostics source, fragmented reads, GPU work probes, array deltas, DMA copies,
    the syncpoint increments queued behind occlusion reports, then the host threads' QoS and the pipeline cache budget."""
    shutil.copyfile(ROOT / 'native/melonx/EmbeddedPerformanceDiagnostics.cs', target / DIAGNOSTICS)
    apply(target)
    apply_work(target)
    apply_arrays(target)
    apply_dma(target)
    apply_queued(target)
    apply_host(target)
    # Then, last in prepare_embedded order, the PR #153 lot (Core 639) and the PR #154 lot (Core 642) on the files
    # this composition holds.
    for name in ORDER:
        apply_present(target, name)


def compose_staged(target):
    """A staged GPU closure has no Ryujinx.Library project: the policy file is composed beside it, not compiled."""
    (target / DMA_LIBRARY).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE / DMA_LIBRARY, target / DMA_LIBRARY)
    compose(target)


def stage(tree, work, candidate, transform=None):
    """Copy the projects the GPU and Vulkan assemblies need, optionally compose, insert the probe."""
    target = work / ('candidate' if candidate else 'control')
    target.mkdir(parents=True)
    for name in ('Directory.Build.props', 'Directory.Packages.props', 'global.json', 'nuget.config'):
        if (tree / name).exists():
            shutil.copy2(tree / name, target / name)
    # The Vulkan backend is built too: the host adapter changes two of its files.
    projects = sorted(set(project_closure(tree / 'src', 'Ryujinx.Graphics.Gpu')) |
                      set(project_closure(tree / 'src', 'Ryujinx.Graphics.Vulkan')))
    for name in projects:
        shutil.copytree(tree / 'src' / name, target / 'src' / name,
                        ignore=shutil.ignore_patterns('bin', 'obj'))
    for name in ('Directory.Build.props',):
        if (tree / 'src' / name).exists():
            shutil.copy2(tree / 'src' / name, target / 'src' / name)
    if transform:
        transform(target)
    probe = PROBE.read_text()
    if candidate:
        probe = '#define FRAGMENTED_READS_CANDIDATE\n' + probe
    (target / 'src/Ryujinx.Graphics.Gpu/FragmentedReadsProbe.cs').write_text(probe)
    runner = target / 'runner'
    runner.mkdir()
    (runner / 'Runner.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
        '<TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>'
        '<TreatWarningsAsErrors>false</TreatWarningsAsErrors><NuGetAudit>false</NuGetAudit></PropertyGroup>'
        '<ItemGroup><ProjectReference Include="../src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj" />'
        '<ProjectReference Include="../src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj" /></ItemGroup></Project>')
    (runner / 'Program.cs').write_text(
        'System.Console.WriteLine(Ryujinx.Graphics.Gpu.Memory.FragmentedReadsProbe.Run(args[0]));\n')
    return target, projects


def run_probe(target, mode):
    build = subprocess.run([dotnet, 'build', str(target / 'runner'), '-c', 'Release', '-p:TreatWarningsAsErrors=false', '-nologo'],
                           cwd=target, env=environment, text=True, capture_output=True, timeout=1800)
    if build.returncode:
        print(build.stdout[-6000:], build.stderr[-3000:])
        build.check_returncode()
    dll = target / 'runner/bin/Release/net10.0/Runner.dll'
    result = subprocess.run([dotnet, str(dll), mode], cwd=target, env=environment, text=True, capture_output=True, timeout=600)
    if result.returncode:
        print(result.stdout[-4000:], result.stderr[-4000:])
        result.check_returncode()
    return json.loads(result.stdout)


preimages = {name: sha(SOURCE / name) for name in COMPOSED}
with tempfile.TemporaryDirectory(prefix='melonx-fragmented-reads-') as temporary:
    work = Path(temporary)
    # The adapter refuses a drifted anchor in every file and writes nothing.
    for changed in NAMES:
        drift = work / 'drift'
        for name in NAMES:
            (drift / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, drift / name)
        text = (drift / changed).read_text(encoding='utf-8-sig')
        check(text.count(DRIFT[changed]) >= 1, 'drift token missing: ' + changed)
        (drift / changed).write_text(text.replace(DRIFT[changed], DRIFT[changed].replace('(', '( ', 1), 1))
        before = {name: sha(drift / name) for name in NAMES}
        try:
            apply(drift)
        except RuntimeError:
            check({name: sha(drift / name) for name in NAMES} == before, 'drifted source was partly written: ' + changed)
        else:
            raise AssertionError('drifted anchor accepted: ' + changed)
        shutil.rmtree(drift)
    composed = work / 'composed'
    for name in COMPOSED:
        (composed / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, composed / name)
    compose(composed)
    try:
        apply(composed)
    except RuntimeError:
        checks += 1
    else:
        raise AssertionError('adapter applied twice')
    postimages = {name: sha(composed / name) for name in COMPOSED}
    if CANDIDATE:
        check(postimages == {name: sha(CANDIDATE / name) for name in COMPOSED}, 'composition differs from the final prepared source')
    control, projects = stage(SOURCE, work, candidate=False)
    candidate, _ = stage(CANDIDATE or SOURCE, work, candidate=True, transform=None if CANDIDATE else compose_staged)
    compiled = {'control': {name: sha(control / name) for name in COMPILED},
                'candidate': {name: sha(candidate / name) for name in COMPILED}}
    if CANDIDATE:
        check(compiled['candidate'] == {name: sha(CANDIDATE / name) for name in COMPILED}, 'candidate build is not the final source')
    check(compiled['control'] == {name: sha(SOURCE / name) for name in COMPILED}, 'control build is not the delivered source')
    before = run_probe(control, 'control')
    after = run_probe(candidate, 'candidate')

# Same bytes everywhere.
for name, row in before['bufferUploads'].items():
    check(row['hash'] == after['bufferUploads'][name]['hash'], 'buffer upload bytes changed: ' + name)
for key in ('singleHash', 'contiguousHash', 'multiHash'):
    check(before['textureSnapshots'][key] == after['textureSnapshots'][key], 'texture snapshot bytes changed: ' + key)
check(before['tracking'] == after['tracking'] and after['tracking']['trackedReadActions'] >= 1, 'tracking behaviour changed')
check(before['handledInvalidAccess'] == after['handledInvalidAccess'] and
      after['handledInvalidAccess']['firstNonZeroAfterHole'] == -1, 'handled invalid access no longer zero-filled')
for key in ('orderedHash', 'shuffledHash', 'prefetchHash'):
    check(before['gpuMemory'][key] == after['gpuMemory'][key], 'GPU memory bytes changed: ' + key)
check(before['softwarePageTable'] == after['softwarePageTable'] and after['softwarePageTable']['matchesGetSpan'], 'software page table changed')
# MemoryManagerHostMapped (4 KiB hosts only; never iOS): tracked reads skip its mapping assertion. Every case,
# including the throws, must be identical, and the armed tracked read across the hole must return its data.
host_mapped = before['hostMapped']
check(host_mapped == after['hostMapped'], 'HostMapped behaviour changed: ' + json.dumps(dict(control=host_mapped, candidate=after['hostMapped'])))
if host_mapped['supported']:
    check(host_mapped['trackedAcrossHole'].startswith('ok length=262144') and host_mapped['trackedAcrossHole'].endswith('fired=1') and
          host_mapped['trackedReadIntoMapped'].endswith('fired=1'), 'HostMapped tracked scenario not exercised')
# Allocation: the control copies each fragmented read; the candidate does not.
upload = 1 << 20
check(before['bufferUploads']['fragmentedWhole']['allocatedPerUpload'] >= upload, 'control did not reproduce the per-upload copy')
check(after['bufferUploads']['fragmentedWhole']['allocatedPerUpload'] < 1024, 'candidate still allocates per fragmented upload')
check(after['bufferUploads']['fragmentedPart']['allocatedPerUpload'] < 1024, 'candidate allocates per partial upload')
check(after['bufferUploads']['contiguousWhole']['allocatedPerUpload'] <= before['bufferUploads']['contiguousWhole']['allocatedPerUpload'] + 64,
      'contiguous upload got more expensive')
check(before['textureSnapshots']['singleAllocated'] >= upload and after['textureSnapshots']['singleAllocated'] < 1024, 'texture snapshot copy not removed')
check(after['textureSnapshots']['multiAllocated'] < before['textureSnapshots']['multiAllocated'], 'multi-range snapshot not improved')
check(after['gpuMemory']['prefetchAllocated'] < 1024 and before['gpuMemory']['prefetchAllocated'] >= 0x18000, 'prefetch copy not removed')
check(after['candidateEntryPoints']['readIntoAllocated'] < 1024, 'GPU ReadInto allocates')
check(after['candidateEntryPoints']['gpuRegionShuffledAllocated'] < 1024 and after['candidateEntryPoints']['gpuRegionOrderedAllocated'] < 1024,
      'GPU regions allocate')
private = before['privatePartitions']
check(private == {**private} and private['supported'] == after['privatePartitions']['supported'], 'private mapping support differs')
if private['supported']:
    for key in ('crossingUploadHash', 'crossingSnapshotHash'):
        check(private[key] == after['privatePartitions'][key], 'private-partition bytes changed: ' + key)
    check(private['matchesGuestBytes'] and after['privatePartitions']['matchesGuestBytes'], 'private snapshot differs from guest memory')
    # A 4 KiB host bridges adjacent partitions, so the copy may not occur here; when it does, it must go.
    if private['crossingUploadAllocated'] >= 0x30000:
        check(after['privatePartitions']['crossingUploadAllocated'] < 1024, 'partition-crossing upload copy not removed')
    check(after['privatePartitions']['crossingSnapshotAllocated'] <= private['crossingSnapshotAllocated'] + 64,
          'partition-crossing snapshot got more expensive')
page = os.sysconf('SC_PAGESIZE')
reproduced = before['privatePartitions'].get('crossingUploadAllocated', 0) >= 0x30000
limits = ['managed Release build of the GPU and Vulkan assembly closures, not the NativeAOT library; no Apple timing, device memory or FPS claim']
if not reproduced:
    limits.append('the partition-crossing range was borrowed by both builds on this host (no copy in the control)')
if not host_mapped['supported']:
    limits.append('MemoryManagerHostMapped not exercised: ' + host_mapped['reason'])
report = dict(result='passed', checks=checks + before['checks'] + after['checks'], probeChecks=dict(control=before['checks'], candidate=after['checks']),
              compiledProjects=projects, preimages=preimages, postimages=postimages, compiledSourceInputs=compiled,
              finalPreparedSourceBound=bool(CANDIDATE), sourceKind='deliveredPreparedWithFinalCandidate' if CANDIDATE else 'deliveredPreparedComposed',
              control=before, candidate=after, inputs={name: sha(ROOT / name) for name in INPUTS},
              host=platform.system() + ' ' + platform.machine() + ' Release managed build', pageSize=page,
              privatePartitionCopyReproducedOnHost=reproduced, hostMappedChecked=host_mapped['supported'],
              physicalDeviceTested=False, fpsGainProven=False, limits=limits)
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=report['checks'],
                      fragmentedUpload=dict(control=before['bufferUploads']['fragmentedWhole']['allocatedPerUpload'],
                                            candidate=after['bufferUploads']['fragmentedWhole']['allocatedPerUpload']),
                      textureSnapshot=dict(control=before['textureSnapshots']['singleAllocated'], candidate=after['textureSnapshots']['singleAllocated']),
                      prefetch=dict(control=before['gpuMemory']['prefetchAllocated'], candidate=after['gpuMemory']['prefetchAllocated']))))
