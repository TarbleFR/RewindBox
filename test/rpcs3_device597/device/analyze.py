#!/usr/bin/env python3
"""Read the uploaded 597 logs, preserving window/session and evidence scope."""
import argparse
import collections
import hashlib
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

KV = re.compile(r'(?:^|\s)([A-Za-z0-9_]+)=([^\s]+)')

def scalar(s):
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s

def fields(s):
    return {k: scalar(v) for k, v in KV.findall(s)}

def stamp(t):
    return {'unix': t, 'utc': datetime.fromtimestamp(t, timezone.utc).isoformat(),
            'paris': datetime.fromtimestamp(t, ZoneInfo('Europe/Paris')).isoformat()}

def stats(v):
    v = [x for x in v if isinstance(x, (int, float))]
    return {'n': len(v), 'min': min(v), 'max': max(v), 'median': statistics.median(v)} if v else None

def tuple_value(row, name, idx):
    try:
        return scalar(str(row[name]).split(':')[idx])
    except (KeyError, IndexError):
        return None

def load_jsonl(path):
    return [dict(json.loads(line), _file=path.name, _line=i)
            for i, line in enumerate(path.read_text().splitlines(), 1) if line.strip()]

def source(row):
    return {'file': row['_file'], 'line': row['_line'], 'timestamp': row['timestamp']}

def analyze(inp, repo):
    inputs = {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
              for p in sorted(inp.iterdir()) if p.is_file()}
    diag = load_jsonl(inp / 'RPCS3-diagnostic(6).log')
    perf = load_jsonl(inp / 'RPCS3-performance(2).log')
    mile = load_jsonl(inp / 'RPCS3-milestones(6).log')
    neo = load_jsonl(inp / 'NeoSwap-v1(1).jsonl')
    def identity(r):
        return (r.get('build'), r.get('pid'), r.get('timestamp'), r.get('stage'), r.get('message'))
    merged = {}
    for r in diag + perf:
        k = identity(r)
        if k in merged:
            merged[k].setdefault('_duplicates', []).append(source(r))
        else:
            merged[k] = r
    ordered = sorted(merged.values(), key=lambda r: (r['timestamp'], r.get('clockMonotonicBeginUs', 0), r['_line']))
    windows = {}; active = {}
    recognized = re.compile(r'\b(COREPROF(?:_RESILIENCE)?|SPUPROF|RANGELOCKPROF|JITPROF|JITMEM)\b(?: ([A-Z][A-Z0-9_]+))?')
    # Tagged rows precede the untagged COREPROF summary in each production report.
    for r in ordered:
        m = r['message']; f = fields(m); pid = (r['build'], r['pid'])
        if 'session' in f and 'window' in f and 'COREPROF ' in m:
            active[pid] = (f['session'], f['window'])
        mt = recognized.search(m)
        if not mt or pid not in active:
            continue
        name = mt.group(2) if mt.group(1) == 'COREPROF' and mt.group(2) else mt.group(1)
        ses, win = active[pid]; key = (r['build'], r['pid'], ses, win)
        w = windows.setdefault(key, {'build': r['build'], 'pid': r['pid'], 'session': ses,
                                    'window': win, 'metrics': {}, 'sources': {}})
        if name == 'SHADERPIPE543_COSTLY' or name == 'SHADERSTALL538_EVENT':
            w['metrics'].setdefault(name, []).append(f)
            w['sources'].setdefault(name, []).append(source(r))
        else:
            assert name not in w['metrics'], (key, name)
            w['metrics'][name] = f; w['sources'][name] = source(r)
    sessions = {}; title = {}; configs = []
    for r in mile:
        key = (r['build'], r['pid']); f = fields(r['message'])
        if r['stage'] == 'game_boot_begin': title[key] = r['message'].split()[0]
        if r['stage'] == 'savestate_boot' and 'title' in f: title[key] = f['title']
        if r['stage'] == 'config_layers':
            title[key] = f['title']
            configs.append({'build': r['build'], 'pid': r['pid'], 'source': source(r),
                            'config': {k:v for k,v in f.items() if k not in ['name', 'legacy_path']}})
        if r['stage'] == 'jitprof_boot' and f.get('part') != 'spu':
            sid = (r['build'], r['pid'], f['session'])
            sessions[sid] = {'build': r['build'], 'pid': r['pid'], 'session': f['session'],
                             'title': title.get(key), 'boot': f, 'boot_source': source(r)}
    for key, w in windows.items():
        s = sessions.get(key[:3]); w['title'] = s['title'] if s else None
        f = w['metrics'].get('FRAMEPROF527', {})
        w['guest_window'] = f.get('state') == 3 and f.get('native_ui_visible') == 0 and f.get('intervals', 0) > 0
        sh = w['metrics'].get('SHADERCOST534', {})
        sp = w['metrics'].get('SPUPROF', {})
        w['shader_compile_calls'] = {k: tuple_value(sh, k, 0) for k in ['source', 'module', 'graphics', 'compute']}
        w['no_shader_or_spu_build_attempts'] = (len(sh) > 0 and all(x == 0 for x in w['shader_compile_calls'].values())
                                               and sp.get('loading_attempts') == 0 and sp.get('gameplay_attempts') == 0)
        w['fps_from_guest_intervals'] = (1000 * f['intervals'] / f['total_interval_ms']
                                        if f.get('total_interval_ms', 0) > 0 else None)
        w['completed_interval_time_to_window_ratio'] = (f['total_interval_ms'] / f['window_ms']
                                                         if f.get('window_ms', 0) > 0 else None)
        w['completed_frames_per_wall_second'] = (1000 * f['intervals'] / f['window_ms']
                                                 if f.get('window_ms', 0) > 0 else None)
    for sid, s in sessions.items():
        rows = [w for key, w in windows.items() if key[:3] == sid]
        s['retained_windows'] = [w['window'] for w in rows]
        s['guest_windows'] = [w['window'] for w in rows if w['guest_window']]
        s['steady_windows'] = [w['window'] for w in rows if w['guest_window'] and w['no_shader_or_spu_build_attempts']]
    acquisition = []
    for r in mile:
        if r['stage'] == 'rsx_acquire':
            acquisition.append({'build': r['build'], 'pid': r['pid'], 'time': stamp(r['timestamp']),
                                'fields': fields(r['message']), 'message': r['message'], 'source': source(r)})
    # NeoSwap sessionSequence is independent of RPCS3 JIT session numbering.
    neo_groups = collections.defaultdict(list)
    for r in neo:
        s = r.get('memoryProfile', {}).get('sessionSequence')
        neo_groups[s].append(r)
    memory = []
    top_fields = ['processFootprintBytes', 'processResidentBytes', 'processCompressedLedgerBytes',
                  'processAvailableBytes', 'ioErrors', 'iosMemoryWarningCount', 'donorLostCount',
                  'thermalState', 'allocatedDiskBytes', 'liveBytes']
    for seq, rows in neo_groups.items():
        memory.append({'memory_profile_sequence': seq, 'records': len(rows),
                       'first': stamp(rows[0]['timestamp']), 'last': stamp(rows[-1]['timestamp']),
                       'sources': {'first': source(rows[0]), 'last': source(rows[-1])},
                       'title_labels': sorted(set(r.get('shaderStorage', {}).get('title', '?') for r in rows)),
                       'os_versions': sorted(set(r['osVersion'] for r in rows)),
                       'metrics': {k: stats([r.get(k) for r in rows]) for k in top_fields},
                       'first_values': {k: rows[0].get(k) for k in top_fields},
                       'last_values': {k: rows[-1].get(k) for k in top_fields},
                       'shader_memory_age_s': stats([r['timestamp'] - r['shaderStorage']['sampleTimestamp'] for r in rows if r.get('shaderStorage', {}).get('sampleTimestamp')]),
                       'event_counts': dict(collections.Counter(r.get('event', '?') for r in rows)),
                       'jetsam_confirmed_values': sorted(set(str(r.get('jetsamConfirmed')) for r in rows)),
                       'termination_cause_values': sorted(set(str(r.get('terminationCause')) for r in rows))})
    memory_events = []
    for r in neo:
        if r.get('event') in ['ios_memory_warning', 'memory_pressure', 'application_background']:
            memory_events.append({'event':r['event'], 'time':stamp(r['timestamp']), 'source':source(r),
                                  'values':{k:r.get(k) for k in top_fields},
                                  'budget_state':r.get('budget', {}).get('reason'),
                                  'pressure_mask':r.get('memoryProfile', {}).get('pressureMask')})
    historic = json.loads((repo / 'docs/evidence/rpcs3-device595-20261029/observed-build595.json').read_text())
    videos = []
    for fn, data in inputs.items():
        if fn.endswith('.mov'):
            same = [name for name, sha in historic['input_sha256'].items() if sha == data['sha256']]
            videos.append({'file': fn, 'sha256': data['sha256'], 'identical_historical595_files': same,
                           'excluded_from_597_visual_validation': bool(same)})
    def summary(rows):
        fm = [w['metrics']['FRAMEPROF527'] for w in rows]
        iv = sum(f['intervals'] for f in fm); total = sum(f['total_interval_ms'] for f in fm)
        return {'windows': [w['window'] for w in rows], 'intervals': iv, 'total_interval_ms': total,
                'fps_from_guest_intervals': 1000 * iv / total if total else None,
                'window_fps_range': stats([w['fps_from_guest_intervals'] for w in rows]),
                'window_p95_ms_range': stats([f['p95_ms'] for f in fm]),
                'max_interval_ms': max([f['max_ms'] for f in fm], default=None),
                'over50ms': sum(f.get('over50ms', 0) for f in fm),
                'over100ms': sum(f.get('over100ms', 0) for f in fm),
                'sampled_texture_ms': stats([w['metrics'].get('RSXFRAME551', {}).get('texture_ms') for w in rows]),
                'sampled_vertex_ms': stats([w['metrics'].get('RSXFRAME551', {}).get('vertex_ms') for w in rows]),
                'spu_cores': stats([w['metrics'].get('COREPROF', {}).get('spu_cores') for w in rows]),
                'rsx_cores': stats([w['metrics'].get('COREPROF', {}).get('rsx_cores') for w in rows]),
                'gpu_time_ms_values': sorted(set(w['metrics'].get('COREPROF', {}).get('gpu_time_ms', -1) for w in rows)),
                'shader_calls_total': {k: sum(w['shader_compile_calls'].get(k) or 0 for w in rows) for k in ['source', 'module', 'graphics', 'compute']}}
    aggregates = []
    for sid, s in sessions.items():
        rows = [w for key, w in windows.items() if key[:3] == sid and w['guest_window']]
        if rows:
            aggregates.append({'build': sid[0], 'pid': sid[1], 'session': sid[2], 'title': s['title'],
                               'guest': summary(rows), 'steady': summary([w for w in rows if w['no_shader_or_spu_build_attempts']])})
    file_counts = {}
    for rows in [diag, perf, mile, neo]:
        c = collections.Counter((r['build'], r['pid']) for r in rows)
        file_counts[rows[0]['_file']] = [{'build': b, 'pid': p, 'records': n} for (b, p), n in c.items()]
    shader_stalls = [{'source':source(r), 'fields':fields(r['message'])} for r in ordered if 'SHADERSTALL538_EVENT ' in r['message']]
    cpu_selection = [{'source':source(r), 'fields':fields(r['message'])} for r in ordered if 'JITCPU context=' in r['message']]
    core_receipt_path = repo / 'docs/evidence/rpcs3-continuation-20261030/apple-core.json'
    core_receipt = json.loads(core_receipt_path.read_text())
    return {'schema': 1, 'input_files': inputs, 'file_build_pid_counts': file_counts,
            'deduplication': {'raw_diagnostic_performance_records': len(diag) + len(perf),
                              'unique_records': len(ordered), 'duplicates_removed': len(diag) + len(perf) - len(ordered),
                              'key': ['build', 'pid', 'timestamp', 'stage', 'message']},
            'sessions': list(sessions.values()), 'configs': configs, 'rsx_acquires': acquisition,
            'aggregates': aggregates, 'neoswap': memory, 'memory_events': memory_events,
            'shader_stall_events':shader_stalls, 'cpu_selections':cpu_selection,
            'core_identity': {'expected_from_delivered597_receipt':core_receipt['source_commit'],
                              'expected_ppu_spu_codegen':core_receipt['codegen'],
                              'device_log_full_core_sha_present':False,
                              'scope':'Log build597 correlated with verified delivery; no full Core SHA is logged in these attachments.'},
            'historical_video_equality': videos,
            'historical595': historic,
            'windows': list(windows.values()),
            'limits': ['No scene-matched before/after FPS comparison exists.',
                       'Retained 597 diagnostic/performance windows omit BO2 sessions1/2 and early AC.',
                       'FRAMEPROF guest_unclassified is not proof of active gameplay rather than cutscene/menu.',
                       'Per-window p95 values are never averaged into a session percentile.',
                       'Completed-interval FPS excludes an unfinished trailing freeze: GOW3 session4 window28 has13 completed intervals over215.742ms within5078.760ms wall time.',
                       'COREPROF CPU-ms across threads overlaps wall time; gpu_time_ms=-1 is unavailable.',
                       'shaderStorage nested memory can be stale; top-level NeoSwap memory is used.',
                       'No 597 visual fix inferred from historical identical videos.',
                       'The new candidate being edited after these logs has no device results.']}

def main():
    p = argparse.ArgumentParser(); p.add_argument('--input', type=Path, required=True)
    p.add_argument('--repo', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); result = analyze(a.input, a.repo)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ['deduplication', 'aggregates', 'neoswap', 'rsx_acquires']}, ensure_ascii=False, indent=2))

if __name__ == '__main__': main()
