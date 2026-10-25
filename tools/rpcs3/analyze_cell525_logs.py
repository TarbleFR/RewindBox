#!/usr/bin/env python3
"""Summarize supplied device captures without mixing builds or counting mirrored logs twice.

The source files remain local. Relative times use the selected diagnostic
session's first event, not boot submission or the first presented game frame.
This is an observational baseline, not an emulator or device benchmark.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

FILES = {
    'app': 'app(3).log',
    'diagnostic': 'RPCS3-diagnostic(2).log',
    'milestones': 'RPCS3-milestones(2).log',
    'neoswap': 'NeoSwap-v1.jsonl(1).previous',
}
KEY_VALUE = re.compile(r'(?<![\w])([a-z][a-z0-9_]*)=([^\s]+)')


def fields(message):
    result = {}
    for key, raw in KEY_VALUE.findall(message):
        try:
            result[key] = float(raw) if '.' in raw else int(raw)
        except ValueError:
            result[key] = raw
    return result


def at(row, origin, keys=None):
    values = fields(row['message'])
    if keys is not None:
        values = {key: values[key] for key in keys if key in values}
    return dict(timestamp=row['timestamp'], elapsed_s=round(row['timestamp'] - origin, 6), **values)


def nested(row, path):
    for key in path.split('.'):
        if not isinstance(row, dict):
            return None
        row = row.get(key)
    return row


def maximum(rows, path, origin):
    available = [row for row in rows if isinstance(nested(row, path), (int, float))]
    if not available:
        return None
    row = max(available, key=lambda item: nested(item, path))
    return dict(value=nested(row, path), timestamp=row['timestamp'],
                elapsed_s=round(row['timestamp'] - origin, 6))


def analyze(directory, build, pid):
    paths = {key: directory / name for key, name in FILES.items()}
    inputs = {key: dict(filename=path.name, bytes=path.stat().st_size,
                       sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for key, path in paths.items()}
    logs = {}
    inventory = {}
    for key in ('diagnostic', 'milestones', 'neoswap'):
        rows = [json.loads(line) for line in paths[key].read_text().splitlines() if line.strip()]
        grouped = defaultdict(list)
        for row in rows:
            grouped[(str(row['build']), row['pid'])].append(row)
        inventory[key] = [dict(build=b, pid=p, rows=len(items),
            first_timestamp=min(item['timestamp'] for item in items),
            last_timestamp=max(item['timestamp'] for item in items))
            for (b, p), items in sorted(grouped.items())]
        logs[key] = sorted(grouped[(build, pid)], key=lambda row: row['timestamp'])
        if not logs[key]:
            raise ValueError(f'Missing selected {key} session {build}/{pid}')
    diagnostic, milestones, neoswap = (logs[key] for key in ('diagnostic', 'milestones', 'neoswap'))
    origin = diagnostic[0]['timestamp']
    select = lambda token: [row for row in diagnostic if token in row.get('message', '')]
    prof = select('COREPROF frames=')
    memory = select('JITMEM active=')
    restore = select('SAVESTATE_RESTORE phase=')
    copies = [row for row in milestones if 'SAVESTATE_RESTORE phase=' in row.get('message', '')]
    primary_restore = Counter(row['message'] for row in restore)
    mirrored_restore = Counter(row['message'] for row in copies)
    mirrored_count = sum((primary_restore & mirrored_restore).values())
    keep = ('frames', 'avg_fps', 'low1_fps', 'frametime_ms', 'p95_ms', 'p99_ms', 'ppu_ms', 'spu_ms',
            'rsx_ms', 'jit_ms', 'gpu_time_ms', 'gpu_fence_wait_ms', 'range_wait_ms', 'pipeline_jobs',
            'memory_mib', 'headroom_mib', 'window_ms', 'ppu_cores', 'spu_cores', 'rsx_cores', 'jit_cores')
    plateau = [row for row in prof if 54 <= row['timestamp'] - origin <= 196]
    late = [row for row in prof if 205 <= row['timestamp'] - origin < 249]
    pools = [at(row, origin) for row in memory]
    late_pools = [row for row in pools if 190 <= row['elapsed_s'] < 249]
    initial_pool = next(row for row in pools if row['elapsed_s'] >= 54)
    first_prof = next(row for row in prof if row['timestamp'] - origin >= 54)
    boot = next(row for row in select('JITPROF_BOOT session=') if 'part=spu' not in row['message'])
    boot_fields = at(boot, origin)
    for key in ('ppu_cache_read', 'ppu_object_load', 'ppu_finalize', 'ppu_symbols'):
        count, total, peak, size = boot_fields[key].split(':')
        boot_fields[key] = dict(calls=int(count), aggregate_ms=float(total), max_ms=float(peak), bytes=int(size))
    phase_rows = {fields(row['message'])['phase']: row for row in restore}
    phase_durations = {phase: round(phase_rows[phase + '_end']['timestamp'] -
        phase_rows[phase + '_begin']['timestamp'], 6) for phase in ('tar', 'vm')
        if phase + '_begin' in phase_rows and phase + '_end' in phase_rows}
    peak_paths = ('processFootprintBytes', 'processResidentBytes', 'processCompressedLedgerBytes',
        'reservedVirtualBytes', 'donationPreparedBytes', 'donatedResidentBytes', 'donatedCompressedBytes',
        'guestRelay.mappedAliasBytes', 'guestRelay.guestPeakBackingBytes', 'iosMemoryWarningCount',
        'ioErrors', 'guestRelay.mapFailureCount')
    last_neoswap = neoswap[-1]
    identity_rows = select('JITCPU context=game_boot')
    identity = [at(row, origin) for row in identity_rows]
    return dict(schema=1, purpose='observational device baseline for CELL525; no before/after performance claim',
        inputs=inputs, session_inventory=inventory,
        selected_session=dict(build=build, pid=pid,
            first_timestamp=origin, first_utc=datetime.fromtimestamp(origin, timezone.utc).isoformat(),
            diagnostic_duration_s=round(diagnostic[-1]['timestamp'] - origin, 6),
            stage_counts=dict(sorted(Counter(row['stage'] for row in diagnostic).items())),
            game_cpu_identity=identity),
        restore=dict(primary_source='diagnostic', milestone_mirrors_ignored=mirrored_count,
            diagnostic_phase_rows=len(restore), milestones_phase_rows=len(copies),
            completed_phase_durations_s=phase_durations,
            phases=[at(row, origin) for row in restore if fields(row['message']).get('phase') in
                ('tar_begin', 'tar_end', 'vm_begin', 'vm_end', 'ppu_functions_begin',
                 'ppu_segments_end', 'ppu_modules_end', 'ppu_fxo_begin')],
            final_event=at(restore[-1], origin),
            capture_ends_at_final_event=restore[-1] == diagnostic[-1],
            interpretation='FD-map restore entered; no per-descriptor trace. Capture does not prove crash, deadlock, or a specific file failure.'),
        warm_ppu_boot=boot_fields,
        cache_window_observations=[at(row, origin, ('cache_index_hits', 'cache_buffer_hits'))
            for row in memory if fields(row['message'])['cache_index_hits'] or fields(row['message'])['cache_buffer_hits']],
        performance=dict(scene_classification='unknown; gameplay, menu, and cinematic are not separately labelled',
            plateau_window_s=[54, 196], plateau_sample_count=len(plateau),
            plateau_first=at(first_prof, origin, keep), plateau_last=at(plateau[-1], origin, keep),
            late_window_s=[205, 249], late_samples=[at(row, origin, keep) for row in late],
            gpu_time_measured=False,
            cpu_and_range_wait_scope='aggregated across threads per presented frame; not additive wall-clock stalls'),
        gpu_allocations=dict(scope='requested allocation bytes, not physical or resident GPU RAM',
            plateau_first=initial_pool, late_samples=late_pools, post_stop_snapshot=pools[-1],
            interpretation='Texture allocations grow while system and scratch pools stay stable. Active/stale/pending split missing; no reclaimable-byte proof. Post-stop VMA snapshot remains nonzero with zero pool counters.'),
        neoswap=dict(samples=len(neoswap), maxima={path: maximum(neoswap, path, origin) for path in peak_paths},
            thermal_states=sorted({row['thermalState'] for row in neoswap}),
            system_pressure_states=sorted({row['budget']['inputs']['systemPressure'] for row in neoswap}),
            last_fast_allocation=last_neoswap['fastAllocation'],
            last_source_archive={key: value for key, value in last_neoswap['shaderStorage']['sourceArchive'].items()
                if key in ('demandReadRequests', 'demandReadUsCumulative', 'demandReadMaxUs',
                    'demandUtilityQueueWaitUsCumulative', 'diskReadBytes', 'diskWriteBytes', 'ioErrors')},
            last_relay_live_bytes=last_neoswap['budget']['relayHostLoans']['kindLiveBytes'],
            configured_donation_goal_bytes=max(row['donationGoalBytes'] for row in neoswap),
            accounting='Footprint, resident, and compressed ledger overlap; do not sum. Virtual reservations, mapped aliases, configured capacities, donor backing and cumulative traffic are not additional physical RAM.'),
        limitations=['Unmatched scenes and settings; no controlled before/after or cold-cache comparison.',
            'No raw logs, personal file paths, UUIDs or save contents are copied into this report.',
            'The untimestamped app log is hashed for provenance; its multiple launch histories are not assigned to this timed session.',
            'No iPhone gameplay, JIT, controller, pause/resume, restore or second-launch result is inferred from source tests.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_directory', type=Path)
    parser.add_argument('--build', default='524')
    parser.add_argument('--pid', type=int, default=23669)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.input_directory, args.build, args.pid)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"PASS separated session {args.build}/{args.pid}; {len(result['restore']['phases'])} restore phase boundaries; no device-gain claim")
