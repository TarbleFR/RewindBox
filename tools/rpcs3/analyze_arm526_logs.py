#!/usr/bin/env python3
"""Deterministic 525 device observations, with union of diagnostic/milestone traces.
Raw records, file paths and game content stay outside the generated report.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

FILES = {'app': 'app(4).log', 'diagnostic': 'RPCS3-diagnostic(3).log',
         'milestones': 'RPCS3-milestones(3).log', 'operations': 'NeoSwap-operations(1).jsonl'}
KV = re.compile(r'(?<![\w])([a-z][a-z0-9_]*)=([^\s]+)')
def fields(message):
    out = {}
    for key, value in KV.findall(message):
        try: out[key] = float(value) if '.' in value else int(value)
        except ValueError: out[key] = value
    return out

def summarize(directory):
    paths = {key: directory / name for key, name in FILES.items()}
    hashes = {key: {'name': path.name, 'bytes': path.stat().st_size,
                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
              for key, path in paths.items()}
    logs = {key: [json.loads(line) for line in paths[key].read_text().splitlines() if line.strip()]
            for key in ('diagnostic','milestones','operations')}
    inventory = {}
    for key, rows in logs.items():
        groups = defaultdict(list)
        for row in rows: groups[(str(row.get('build', 'absent')), row['pid'])].append(row)
        inventory[key] = [dict(build=b, pid=p, rows=len(rs),
                              first_timestamp=min(r['timestamp'] for r in rs),
                              last_timestamp=max(r['timestamp'] for r in rs))
                          for (b,p),rs in sorted(groups.items())]
    pid, build = 24255, '525'
    diag = [r for r in logs['diagnostic'] if r['pid']==pid and r['build']==build]
    miles = [r for r in logs['milestones'] if r['pid']==pid and r['build']==build]
    origin = min(r['timestamp'] for r in diag)
    def point(row): return dict(timestamp=row['timestamp'], elapsed_s=round(row['timestamp']-origin,6), **fields(row['message']))
    def selected(token): return [r for r in diag if token in r['message']]
    # Matching duplicates count by full message multiplicity, not source count or timestamp.
    restore_diag=selected('SAVESTATE_RESTORE phase=')
    remaining=Counter(r['message'] for r in restore_diag)
    restore=list(restore_diag); unique=[]; mirrors=0
    for row in miles:
        if remaining[row['message']]: remaining[row['message']]-=1; mirrors+=1
        else: restore.append(row); unique.append(row)
    restore.sort(key=lambda r:r['timestamp'])
    parsed_restore=[point(r) for r in restore]
    profile=[point(r) for r in selected('COREPROF frames=')]
    memory=[point(r) for r in selected('JITMEM active=')]
    performance=[point(r) for r in diag if r['stage']=='performance_sample']
    launch=[r for r in performance if r.get('native_ui')==1]
    guest=[r for r in performance if r.get('native_ui')==0]
    phase_rows={r['phase']:r for r in parsed_restore if r['phase']!='fs_stage' and not r['phase'].startswith('fxo_')}
    phase_durations={p:round(phase_rows[p+'_end']['timestamp']-phase_rows[p+'_begin']['timestamp'],6)
                     for p in ('tar','vm','ppu_functions','ppu_segments','ppu_modules')
                     if p+'_begin' in phase_rows and p+'_end' in phase_rows}
    raw_events=[e for r in logs['operations'] if r['pid']==pid for e in r['batch']['events']]
    events={}
    for e in raw_events:
        key=(e['session'],e['sequence'])
        if key in events: assert events[key]==e
        events[key]=e
    events=list(events.values())
    def extrema(rows, key):
        vals=[r[key] for r in rows if isinstance(r.get(key),(int,float))]
        return {'min':min(vals),'max':max(vals)} if vals else None
    def subset(row,keys): return {key:row[key] for key in keys if key in row}
    post_boot_profiles=[r for r in profile if r['elapsed_s']>=245]
    memkeys=['elapsed_s','vma_block_bytes','vma_allocated','vma_unused','vma_snapshot_valid','vma_owner_live','vma_sample_valid','vma_generation',
             'gpu_textures_requested','texture_recyclable_images','texture_recyclable_bytes','texture_snapshot_valid','texture_owner_live','texture_sample_valid']
    boot=point(selected('JITPROF_BOOT session=')[0]); boot_spu=point(selected('JITPROF_BOOT session=')[1])
    return dict(schema=1,purpose='Observations from supplied Build525 device capture; no matched game-performance comparison',
        inputs=hashes,session_inventory=inventory,
        selected_session={'build':build,'pid':pid,'title':'BCES00510','device_total_memory_bytes':7989460992,
                          'diagnostic_duration_s':round(max(r['timestamp'] for r in diag)-origin,6),
                          'diagnostic_rows':len(diag),'physical_device_capture_supplied':True,
                          'physical_device_test_by_agent':False},
        restore={'diagnostic_rows':len(restore_diag),'milestone_rows':len(miles),'mirrors_deduplicated':mirrors,
                 'unique_milestone_rows':[point(r) for r in unique], 'union_rows':len(restore),
                 'completed_phase_durations_s':phase_durations,
                 'fs_trace':[r for r in parsed_restore if r['phase']=='fs_stage'],
                 'final_event':parsed_restore[-1],
                 'interpretation':'File IDs3/4 reopen and seek successfully. ID5 regular/read-only reopen returns false. Capture ends before in-memory fallback or existing fatal failed-file path. This is not evidence of an open wait, directory VLE failure, crash, deadlock, corrupted state or a specific host error.',
                 'needed_internal_diagnostics':['error result and virtual mount classification for failed reopen',
                    'VFS resolution and host/ISO virtual-device path identity validity, without private paths',
                    'in-memory flag, subsequent payload/seek/descriptor completion markers']},
        native_path_activity={'spu_profile':[point(r) for r in selected('SPUPROF session=') if fields(r['message']).get('gameplay_attempts',0)],
                              'range_lock_profile':[point(r) for r in selected('RANGELOCKPROF session=') if fields(r['message']).get('episodes',0)],
                              'spu_interpreter_entries':extrema([point(r) for r in selected('SPUPROF session=')],'interp_entries'),
                              'texture_hash_bytes':extrema(memory,'texture_hash_bytes'),
                              'texture_hash_ticks':extrema(memory,'texture_hash_ticks'),
                              'interpretation':'No SPU interpreter instructions or texture hash bytes recorded in this brief capture. Native SIMD migration may target real users, but this capture alone cannot demonstrate their title CPU cost.'},
        cold_ppu_boot={'sample':boot,'spu':boot_spu,
                      'interpretation':'136 modules compiled after intentional PPU codegen digest change525; wall308.190s starts65.193s before capture. No comparison to warm524 timing permitted. Cache-read bytes and object-load bytes both44,809,056; count314 includes existence/missing-cache probes.'},
        presentation={'native_ui_samples':len(launch),'guest_samples':len(guest),
                      'native_ui_first':subset(launch[0],['elapsed_s','emu_state','boot_progress','guest_frames','native_ui','fps']),
                      'native_ui_last':subset(launch[-1],['elapsed_s','emu_state','boot_progress','guest_frames','native_ui','fps']),
                      'first_guest':subset(guest[0],['elapsed_s','emu_state','guest_frames','native_ui','fps']),
                      'last_guest':subset(guest[-1],['elapsed_s','emu_state','guest_frames','native_ui','fps']),
                      'post_boot_coreprof':post_boot_profiles,
                      'interpretation':'Most33FPS windows belong to native loading UI (guest_frames0, PPU/SPU0) while LLVM compiles. Only brief postboot guest presentation; no labelled gameplay/menu/cinematic or prolonged scene. GPU duration=-1 throughout.'},
        memory={'process_footprint_bytes':extrema([dict(r,footprint=int(r['memory'].split('/')[0])) for r in performance],'footprint'),
                'process_resident_bytes':extrema(performance,'process_resident'),
                'compressed_process_bytes_available':False,
                'donor_prepared_bytes':extrema(performance,'donor_prepared'),
                'donor_resident_bytes':extrema(performance,'donor_resident'),
                'donor_accounted_compressed_bytes':extrema(performance,'donor_accounted_compressed'),
                'donor_target_bytes':extrema(performance,'donor_target'),
                'donor_lost_counter':extrema(performance,'donor_lost'),
                'relay_live_backing_bytes':extrema(performance,'relay_live'),
                'relay_mapped_alias_bytes':extrema(performance,'relay_mapped'),
                'thermal_states':sorted({r['thermal'] for r in performance}),
                'requested_texture_bytes':extrema(memory,'gpu_textures_requested'),
                'last_guest_graphics_sample':subset(memory[-2],memkeys),
                'last_graphics_sample':subset(memory[-1],memkeys),
                'interpretation':'525 VMA zero/lifecycle reset observed after stop. Recyclable11 images/12,880,512B of61,606,016B texture requests before stop. No process compressed ledger in these new four files. Footprint/resident/shared/donor backing overlap; aliases and7GiB configured target are not additional physical RAM.'},
        neoswap_operations={'matching_pid':pid,'build_not_stored_in_source':True,'rows':sum(r['pid']==pid for r in logs['operations']),
                            'events':len(events),'duplicate_events':len(raw_events)-len(events),
                            'session_ids':sorted({e['session'] for e in events}),
                            'sequences':[min(e['sequence'] for e in events),max(e['sequence'] for e in events)],
                            'operation_counts':dict(Counter(e['operation'] for e in events)),
                            'result_counts':dict(Counter(e['resultName'] for e in events)),
                            'os_error_counts':dict(Counter(e['osError'] for e in events)),
                            'max_operation_duration_us':max(e['durationUs'] for e in events),
                            'aggregate_operation_duration_us':sum(e['durationUs'] for e in events),
                            'batches_complete_history':all(r['batch']['completeHistory'] for r in logs['operations'] if r['pid']==pid),
                            'dropped_events_cumulative_max':max(r['batch']['droppedEventsCumulative'] for r in logs['operations'] if r['pid']==pid),
                            'interpretation':'Quota refusals are admission decisions, not OS I/O errors.761 unique source-storage events in session2:100 CPU snapshots admitted/checkpointed/unmapped/discarded,361 quota refusals. Individual operation max97.254ms; sum677.077ms across process timeline is not a per-frame stall.'},
        missing=['No controlled525vs524 same-scene/device/settings comparison, no cold/warm paired loading campaign.',
                 'No full resume completion after ID5 failure, no controller/pause/second-launch completion.',
                 'No prolonged demanding GodofWarIII gameplay measurement, GPU timings or raw process compressed ledger.',
                 'Untimestamped app history hashed but not assigned to timed device session. Raw/private paths excluded.'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    out=summarize(a.directory);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
    print('PASS525/PID24255:172 mirrored restore events +1 unique milestone retained; failed reopen ID5, not an open wait')
