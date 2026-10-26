#!/usr/bin/env python3
"""Analyze RPCS3 exports, preserving process/session/window and timer scopes.

Only aggregate observations are exported; native container paths and full
configuration messages never enter the evidence JSON. No log is modified.
"""
import argparse
import collections
import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

PAIR = re.compile(r"(\w+)=([^\s]+)")

def fields(message):
    return dict(PAIR.findall(message))

def utc(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).isoformat()

def union_us(intervals):
    merged = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(b, merged[-1][1])
        else:
            merged.append([a, b])
    return sum(b-a for a,b in merged)

def redact_paths(value):
    if isinstance(value, str):
        return re.sub(r'/var/mobile/[^\s"\']+', '<ios-path-redacted>', value)
    if isinstance(value, list):
        return [redact_paths(v) for v in value]
    if isinstance(value, dict):
        return {k:redact_paths(v) for k,v in value.items()}
    return value

def analyze_restore(rows):
    """Split restore attempts at process/build changes or reset elapsed clocks.

    The export does not provide a session identifier. Do not infer one from
    another file's currently active session. Paired parent/child costs overlap.
    """
    attempts=[]
    current=None
    last_elapsed={}
    for d in rows:
        p=fields(d['message'])
        key=(d['build'],d['pid'])
        elapsed=int(p.get('elapsed_us',0))
        if current is None or current['key']!=key or elapsed<last_elapsed.get(key,0):
            current={'key':key,'events':[]}
            attempts.append(current)
        current['events'].append((d,p))
        last_elapsed[key]=elapsed
    result=[]
    for attempt in attempts:
        events=attempt['events']
        begins={}
        opens={}
        pairs=[]
        files=[]
        unmatched=[]
        errors=[]
        for d,p in events:
            line=d['_line']
            elapsed=int(p.get('elapsed_us',0))
            phase=p.get('phase')
            if phase=='fxo_type_begin':
                begins[p['type']]=(line,elapsed)
            elif phase=='fxo_type_end':
                begin=begins.pop(p['type'],None)
                if begin:
                    pairs.append({'type':p['type'],'begin_line':begin[0],
                                  'end_line':line,'elapsed_us':elapsed-begin[1]})
                else:
                    unmatched.append({'line':line,'kind':'fxo_end_without_begin'})
            if p.get('stage')=='file_open_begin':
                opens[p['id']]=(line,elapsed)
            elif p.get('stage')=='file_open_end':
                begin=opens.pop(p['id'],None)
                files.append({'id':p['id'],'begin_line':begin[0] if begin else None,
                              'end_line':line,'elapsed_us':elapsed-begin[1] if begin else None,
                              'value':p.get('value')})
            if re.search(r'file_open_error|file_unavailable|exception|cancel|abort',d['message'],re.I):
                errors.append({'line':line,'reason':p.get('stage',p.get('phase','error_marker')),
                               'id':p.get('id'),'value':p.get('value')})
        anchors=[d['timestamp']*1e6-(d['clockMonotonicBeginUs']+d['clockMonotonicEndUs'])/2 for d,p in events]
        result.append({'build':attempt['key'][0],'pid':attempt['key'][1],
                       'attempt_in_export':len(result)+1,'session':'not_exported',
                       'first_line':events[0][0]['_line'],'last_line':events[-1][0]['_line'],
                       'first_utc':utc(events[0][0]['timestamp']),'last_utc':utc(events[-1][0]['timestamp']),
                       'first_elapsed_us':int(events[0][1].get('elapsed_us',0)),
                       'last_elapsed_us':int(events[-1][1].get('elapsed_us',0)),
                       'anchor_epoch_minus_mono_us':{'median':statistics.median(anchors),'min':min(anchors),'max':max(anchors)},
                       'type_pairs_count':len(pairs),
                       'longest_pairs':sorted(pairs,key=lambda x:x['elapsed_us'],reverse=True)[:12],
                       'file_opens':files,'errors':errors,'unmatched_ends':unmatched,
                       'limits':['Partial trace: first/last elapsed values are not the entire restore duration.',
                                 'FXO parent durations include nested file events; do not add them.',
                                 'Different serialized states/module sets are not controlled before/after comparisons.']})
    return result

def selected_event(d):
    """Export only relevant scalar facts, never raw messages or full configs."""
    message=d['message']
    item={k:d[k] for k in ['build','pid','timestamp','clockMonotonicBeginUs']}
    item['performance_line']=d['_line']
    if 'CONFIG_LAYERS' in message:
        item['reason']='effective_configuration'
        keys=['title','database','legacy_custom','sparse_overrides','shader_mode','frame_limit',
              'wcb','wdb','rsx_res','async_tex','max_spurs','inherited','kept','mt_rsx','mlaa_bypass',
              'spu_block','spu_decoder','ppu_decoder','getllar_pct','accurate_res','spu_spin']
        item['fields']={k:d['kv'][k] for k in keys if k in d['kv']}
    elif 'JITPROF_BOOT' in message:
        item['reason']='jit_boot'
        keys=['session','boot_kind','part','modules_total','modules_compiled','modules_cached',
              'modules_existing','ppu_cache_hits','ppu_cache_misses','wall_ms','ppu_codegen',
              'ppu_cache_read','ppu_object_load','ppu_finalize','ppu_pipeline','ppu_ir_passes','spu_pipeline']
        item['fields']={k:d['kv'][k] for k in keys if k in d['kv']}
    elif 'FREEZE_DUMP snapshot' in message:
        item['reason']='no_frame_snapshot'
        header=next((l for l in message.splitlines() if 'FREEZE_DUMP begin ' in l),'')
        kv=fields(header)
        item['fields']={k:kv[k] for k in ['dump','reason','no_frames_s','state','busiest_cores','lines','truncated'] if k in kv}
        rsx=fields(next((l for l in message.splitlines() if 'FREEZE_DUMP rsx ' in l),''))
        item['rsx']={k:rsx[k] for k in ['fifo_state','get','put','in_begin_end','ext_lock'] if k in rsx}
        item['waiting_components']=[{k:fields(l).get(k) for k in ['id','name','state','func','wait_s']}
                                    for l in message.splitlines() if 'FREEZE_DUMP spu ' in l or '_main_thread ' in l]
        item['interpretation']='Thread-state sample only; no persistent deadlock or causality inferred.'
    elif 'LOG_BUDGET' in message:
        item['reason']='log_budget_loss'
        item['fields']={k:d['kv'][k] for k in ['dropped','limit_per_s'] if k in d['kv']}
    else:
        return None
    return item

def self_check():
    def row(hist,n):
        return {'kv':{'histogram_upper_us':hist,'intervals':str(n)}}
    # A bin crossing 500 ms is uncertainty, not a fabricated exact count.
    ambiguous=hist_metrics([row('495999:1,503999:3,511999:2',6)])
    assert ambiguous['over500ms_bounds']==[2,5]
    assert ambiguous['p50_ms_bounds']==[496.0,503.999]
    assert hist_metrics([row('495999:1,511999:2',3)])['over500ms_bounds']==[2,2]
    assert hist_metrics([row('4294967295:1',1)])['p99_ms_bounds']==[1144.0,4294967.295]
    assert hist_metrics([row('',0)])['p50_ms_bounds'] is None
    # Parent/child and concurrent timers never add their overlapping duration.
    assert union_us([(0,100),(20,80)])==100
    assert union_us([(0,100),(90,120),(150,180)])==150
    assert union_us([])==0
    assert redact_paths({'message':'path=/var/mobile/Containers/secret next=1'})=={'message':'path=<ios-path-redacted> next=1'}
    return {'passed':True,'cases':9,'scope':'histogram threshold/quantiles, overlapping intervals, path redaction'}

def hist_metrics(rows):
    hist = collections.Counter()
    for r in rows:
        for entry in r['kv'].get('histogram_upper_us', '').split(','):
            if ':' in entry:
                upper, count = map(int, entry.split(':'))
                hist[upper] += count
    n = sum(hist.values())
    expected = sum(int(r['kv']['intervals']) for r in rows)
    assert n == expected, (n, expected)
    # Known source buckets: first 128 are 1 ms; following 127 are 8 ms;
    # final bucket catches all >= 1.144 s, with u32 upper saturation.
    def lower(upper):
        if upper < 128000:
            return upper - 999
        if upper < 4294967295:
            return upper - 7999
        return 1144000
    def quantile(p):
        target = max(1, math.ceil(n*p))
        count = 0
        for upper, k in sorted(hist.items()):
            count += k
            if count >= target:
                return [lower(upper)/1000, upper/1000]
        return None
    above_lo = sum(k for upper,k in hist.items() if lower(upper) > 500000)
    above_hi = sum(k for upper,k in hist.items() if upper > 500000)
    return {'intervals': n, 'p50_ms_bounds': quantile(.5),
            'p95_ms_bounds': quantile(.95), 'p99_ms_bounds': quantile(.99),
            'over500ms_bounds': [above_lo, above_hi],
            'histogram_upper_us_counts': dict(sorted(hist.items()))}

def tuple_totals(rows, key):
    vals = [r.get(key, '0:0:0').split(':') for r in rows]
    return {'count': sum(int(v[0]) for v in vals),
            'total': round(sum(float(v[1]) for v in vals), 6),
            'max': max((float(v[2]) for v in vals if len(v)>2), default=0)}

def main(root, dest, title='BCES00510', suffix='', reference_report=None, window_scopes=()):
    data = {}
    sources = {}
    for kind in ['performance', 'timeline', 'restore-trace']:
        p = root / f'RPCS3-{kind}{suffix}.log'
        raw = p.read_bytes()
        lines = raw.decode().splitlines()
        data[kind] = [{**json.loads(l), '_line': i+1} for i,l in enumerate(lines)]
        sources[p.name] = {'sha256':hashlib.sha256(raw).hexdigest(),
                           'bytes':len(raw), 'lines':len(lines)}
    timeline_keys=[(d['build'],d['pid'],d['session'],d['window']) for d in data['timeline']]
    if len(timeline_keys)!=len(set(timeline_keys)):
        raise ValueError('Duplicate timeline windows: refusing to double count intervals.')
    pg = collections.defaultdict(list)
    report_context = {}
    for d in data['performance']:
        d['kv'] = fields(d['message'])
        if ' FRAMEPROF527 ' in d['message']:
            report_context[(d['build'],d['pid'])] = (int(d['kv']['session']),int(d['kv']['window']))
        d['_report_context'] = report_context.get((d['build'],d['pid']))
        pg[(d['build'],d['pid'])].append(d)
    clock = []
    for (build,pid),ds in pg.items():
        offsets=[d['timestamp']*1e6-(d['clockMonotonicBeginUs']+d['clockMonotonicEndUs'])/2 for d in ds]
        clock.append({'build':build,'pid':pid,'lines':len(ds),'utc_begin':utc(ds[0]['timestamp']),
                      'utc_end':utc(ds[-1]['timestamp']), 'wall_minus_monotonic_us_min':min(offsets),
                      'wall_minus_monotonic_us_max':max(offsets),'offset_drift_us':max(offsets)-min(offsets),
                      'max_anchor_width_us':max(d['clockMonotonicEndUs']-d['clockMonotonicBeginUs'] for d in ds)})
    periods = []
    previous_key = None
    for d in data['timeline']:
        key = (d['build'],d['pid'],d['session'],d['frame_ms']['phase'])
        if key != previous_key or not periods or d['window'] != periods[-1]['windows'][-1]+1:
            periods.append({'build':d['build'],'pid':d['pid'],'session':d['session'],
                            'phase_snapshot':d['frame_ms']['phase'],'windows':[],
                            'first_utc':utc(d['timestamp']), 'duration_ms':0,
                            'intervals':0, 'max_frame_ms':0, 'timeline_lines':[]})
        p=periods[-1]
        p['windows'].append(d['window'])
        p['last_utc']=utc(d['timestamp'])
        p['duration_ms']+=d['frame_ms']['window_ms']
        p['intervals']+=d['frame_ms']['intervals']
        p['max_frame_ms']=max(p['max_frame_ms'],d['frame_ms']['max_ms'])
        p['timeline_lines'].append(d['_line'])
        previous_key=key
    groups = collections.defaultdict(list)
    for d in data['timeline']:
        groups[(d['build'],d['pid'],d['session'],d['frame_ms']['phase'])].append(d)
    output=[]
    for (build,pid,session,phase),ts in groups.items():
        windows={t['window'] for t in ts}
        ps=[d for d in pg[(build,pid)] if d['_report_context'] and d['_report_context'][0]==session and d['_report_context'][1] in windows]
        frames=[d for d in ps if ' FRAMEPROF527 ' in d['message']]
        covered_windows={int(d['kv']['window']) for d in frames}
        expected_by_window={t['window']:t['frame_ms']['intervals'] for t in ts}
        if len(covered_windows)!=len(frames):
            raise ValueError('Duplicate frame histogram windows.')
        for d in frames:
            if int(d['kv']['intervals'])!=expected_by_window[int(d['kv']['window'])]:
                raise ValueError('Timeline/performance interval-count disagreement.')
        events=[d for d in pg[(build,pid)] if ' SHADERSTALL538_EVENT ' in d['message'] and int(d['kv'].get('report_session',-1))==session and int(d['kv'].get('report_window',-1)) in windows]
        by_origin=collections.defaultdict(list)
        for d in events: by_origin[(d['kv']['stage'],d['kv'].get('origin','NA'))].append(d)
        shaders=[]
        for (stage,origin),es in by_origin.items():
            shaders.append({'stage':stage,'origin':origin,'count_retained':len(es),
                            'total_operation_us_not_wall_time':sum(int(d['kv']['duration_us']) for d in es),
                            'union_operation_us':union_us([(int(d['kv']['begin_us']),int(d['kv']['end_us'])) for d in es]),
                            'max_us':max(int(d['kv']['duration_us']) for d in es),
                            'max_concurrent_driver_calls':max(int(d['kv'].get('concurrent_driver_calls',0)) for d in es)})
        rsx=[d['rsx_frame'] for d in ts if 'rsx_frame' in d and d['rsx_frame'].get('sampled',0)]
        sample_count=sum(d['sampled'] for d in rsx)
        mem=[d for d in ps if ' MEMPROF527 ' in d['message']]
        hash_records=[d for d in ps if ' JITMEM ' in d['message']]
        hash_bytes=sum(int(d['kv'].get('texture_hash_bytes',0)) for d in hash_records)
        hash_ticks=sum(int(d['kv'].get('texture_hash_ticks',0)) for d in hash_records)
        frame_count=sum(t['frame_ms']['intervals'] for t in ts)
        window_seconds=sum(t['frame_ms']['window_ms'] for t in ts)/1000
        fingerprints=[d for d in ps if ' SHADERPIPE543 ' in d['message']]
        last_fingerprint=fingerprints[-1] if fingerprints else None
        item={'build':build,'pid':pid,'session':session,'phase_snapshot':phase,
              'title_values':sorted({t.get('title','unavailable') for t in ts}),
              'windows':sorted(windows),'timeline_lines':[t['_line'] for t in ts],
              'utc_first_report':utc(ts[0]['timestamp']),'utc_last_report':utc(ts[-1]['timestamp']),
              'window_duration_ms':round(sum(t['frame_ms']['window_ms'] for t in ts),3),
              'intervals':sum(t['frame_ms']['intervals'] for t in ts),
              'max_frame_ms':max(t['frame_ms']['max_ms'] for t in ts),
              'over50ms':sum(t['frame_ms']['over50ms'] for t in ts),
              'over100ms':sum(t['frame_ms']['over100ms'] for t in ts),
              'frames_histogram':hist_metrics(frames) if frames else None,
              'histogram_coverage':{'complete':covered_windows==windows,
                                    'covered_windows':sorted(covered_windows),
                                    'missing_windows':sorted(windows-covered_windows),
                                    'scope':'Percentiles cover only supplied detailed histograms; total frame counts cover timeline windows.'},
              'peak_footprint_bytes':max(t['memory_bytes'].get('peak_footprint',0) for t in ts),
              'peak_compressed_bytes':max((int(d['kv'].get('peak_compressed',0)) for d in mem),default=None),
              'host_thermal_max':max(t['host'].get('thermal_max',-1) for t in ts),
              'memory_pressure_peak':max(t['resilience'].get('memory_pressure_peak',-1) for t in ts),
              'shader_cost_us':{k:tuple_totals([t['shader_cost_us'] for t in ts],k) for k in ['source','module','graphics','compute']},
              'shader_events_by_stage_origin':shaders,
              'shader_event_dropped':sum(t['shader_stall'].get('dropped',0) for t in ts),
              'shader_fingerprint_snapshot_last':{
                  'performance_line':last_fingerprint['_line'],
                  **{k:last_fingerprint['kv'].get(k) for k in ['distinct','repeated_builds','fingerprint_dropped','live_pipelines']},
                  'scope':'Bounded cumulative fingerprint tracker; dropped entries are not canceled hashes or proven duplicate builds.'
              } if last_fingerprint else None,
              'log_budget_dropped_max':max(t['lost'].get('log_budget_dropped',0) for t in ts),
              'rotations_last':ts[-1]['lost']['rotations'],
              'vdec_lifetime_last':ts[-1]['vdec_io_process_lifetime'],
              'neoswap_lifetime_last':ts[-1]['host'].get('neoswap_process_lifetime'),
              'swap_lifetime_last':ts[-1]['host'].get('swap_process_lifetime'),
              'rsx_sample_count':sample_count,
              'texture_hash':{'bytes':hash_bytes,'counter_ticks':hash_ticks,
                              'ticks_frequency_unavailable':True,
                              'mib_per_interval':hash_bytes/2**20/frame_count if frame_count else None,
                              'gib_per_window_second':hash_bytes/2**30/window_seconds if window_seconds else None,
                              'performance_lines':[d['_line'] for d in hash_records]},
              'rsx_sample_weighted_ms':{k:round(sum(d[k]*d['sampled'] for d in rsx)/sample_count,4) if sample_count else None for k in ['setup_ms','vertex_ms','texture_ms','exec_ms','flip_ms']},
              'wait_ms':{k:tuple_totals([t['wait_ms'] for t in ts],k) for k in ['pipeline_queue','pipeline_build_callback','cpu_gpu_fence','vm_range_episode','guest_rsx_semaphore','llvm_budget_cv','llvm_admission_mutex']},
              'rsx_sync_ms':{k:tuple_totals([t.get('rsx_sync',{}) for t in ts],k) for k in ['frame_latency','submit','hard_sync','texture','cb_reuse']}}
        item['longest_frame_windows']=[{
            'timeline_line':t['_line'],'window':t['window'],'timestamp':t['timestamp'],
            'frame_ms':t['frame_ms'],'shader_cost_us':t['shader_cost_us'],
            'jit':t['jit'],'rsx_sync':t.get('rsx_sync'),
            'reason':'Largest reported frame intervals; nearby window costs are correlation, not isolated causes.'
        } for t in sorted((t for t in ts if t['frame_ms']['intervals']),key=lambda t:t['frame_ms']['max_ms'],reverse=True)[:5]]
        if item['frames_histogram']:
            assert item['frames_histogram']['intervals']==sum(expected_by_window[w] for w in covered_windows)
        output.append(item)
    findings=[event for d in data['performance'] if (event:=selected_event(d)) is not None]
    identified_guest=[d for d in data['timeline'] if d.get('title')==title and d['frame_ms']['phase']=='guest_unclassified']
    tail=None
    if identified_guest:
        latest=max(identified_guest,key=lambda d:d['timestamp'])
        latest_key=(latest['build'],latest['pid'],latest['session'])
        latest_guest=[d for d in identified_guest if (d['build'],d['pid'],d['session'])==latest_key]
        tail=analyze_tail(latest_guest,pg[latest_key[:2]])
    restores=analyze_restore(data['restore-trace'])
    scoped=[]
    for build,pid,session,first,last in window_scopes:
        ts=[d for d in data['timeline'] if (d['build'],d['pid'],d['session'])==(build,pid,session)
            and first<=d['window']<=last]
        if {d['window'] for d in ts}!=set(range(first,last+1)):
            raise ValueError('Requested window scope is incomplete or absent in timeline.')
        scoped.append(analyze_scope(ts,pg[(build,pid)]))
    correlations=[]
    for event in findings:
        if event['reason']!='no_frame_snapshot':
            continue
        later=[r for r in restores if r['build']==event['build'] and r['pid']==event['pid']
               and datetime.datetime.fromisoformat(r['first_utc']).timestamp()>event['timestamp']]
        if later:
            first=min(later,key=lambda r:r['first_utc'])
            correlations.append({'reason':'freeze_precedes_first_available_restore_trace',
                                 'build':event['build'],'pid':event['pid'],
                                 'performance_line':event['performance_line'],'restore_line':first['first_line'],
                                 'seconds_to_first_restore_trace':datetime.datetime.fromisoformat(first['first_utc']).timestamp()-event['timestamp'],
                                 'limit':'First available restore trace can begin mid-restore; no global start marker or causal link is inferred.'})
    out={'sources':sources,'clock_anchors':clock,'groups':output,'contiguous_periods':periods,
         'selected_events':findings,'target_final_ten_windows':tail,
         'requested_window_scopes':scoped,
         'restore_attempts':restores,'cross_file_correlations':correlations,
         'timer_semantics':{
             'rsx_sync.frame_latency':'Queue submission to observed cleanup age; not an additional host wait.',
             'rsx_sync.texture':'Fence wait at texture DMA cleanup; overlaps wait_ms.cpu_gpu_fence for the same call.',
             'spu_wait':'Aggregated concurrent SPU threads; not serial frame pause time.',
             'rsx_frame.texture_ms':'Sampled draw texture-upload scope, not all RSX texture/blit/readback operations.',
             'denominators':'Intervals, COREPROF frames and RSX frames have independently drained boundaries; named separately.'},
         'analysis_checks':self_check(),
         'limitations':['phase is a snapshot at report time, not an interval-by-interval gameplay label',
                        'guest_unclassified cannot separate cinematic, menu and gameplay without scene markers',
                        'all timing categories and cross-thread waits may overlap; sums are not frame pause attribution',
                        'timeline is not averaged for p95/p99; only actual frame histograms are merged',
                        'historical timeline windows can survive after detailed performance histograms rotate',
                        'NeoSwap operation JSONL not supplied; host counters do not identify RAM or restoration failures',
                        'no paired before/after run, no physical iPhone available to analyst']}
    if reference_report is not None:
        previous_raw=reference_report.read_bytes()
        previous=json.loads(previous_raw)
        comparison={}
        for kind in ['performance','timeline','restore-trace']:
            current_name=f'RPCS3-{kind}{suffix}.log'
            reference_name=f'RPCS3-{kind}.log'
            old=previous.get('sources',{}).get(reference_name)
            comparison[kind]={'current_file':current_name,'reference_file':reference_name,
                              'identical_bytes':sources[current_name]['sha256']==old['sha256'] if old else None}
        out['reference_export_comparison']={
            'report':reference_report.name,'sha256':hashlib.sha256(previous_raw).hexdigest(),
            'files':comparison,
            'restore_is_identical_historical_export':comparison['restore-trace']['identical_bytes'],
            'limit':'Identical restore bytes are historical evidence, not new restore attempts in the latest processes.'}
    out=redact_paths(out)
    encoded=json.dumps(out,ensure_ascii=False,indent=2)+'\n'
    if '/var/mobile/' in encoded:
        raise ValueError('Private iOS path escaped redaction.')
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(encoded)
    print(json.dumps({'report':dest.name,'bytes':len(encoded.encode()),'groups':len(output),
                      'restore_attempts':len(out['restore_attempts']),'analysis_checks':out['analysis_checks']}))

def analyze_tail(guest, process_rows):
    latest_ten=guest[-10:]
    latest_ten_windows={d['window'] for d in latest_ten}
    last=latest_ten[-1]
    tail_ps=[d for d in process_rows if d['_report_context'] and d['_report_context'][0]==last['session'] and d['_report_context'][1] in latest_ten_windows]
    tail_hash=[d for d in tail_ps if ' JITMEM ' in d['message']]
    tail_frames=[d for d in tail_ps if ' FRAMEPROF527 ' in d['message']]
    tail_n=sum(d['frame_ms']['intervals'] for d in latest_ten)
    tail_s=sum(d['frame_ms']['window_ms'] for d in latest_ten)/1000
    tail_bytes=sum(int(d['kv'].get('texture_hash_bytes',0)) for d in tail_hash)
    tail_samples=sum(d.get('rsx_frame',{}).get('sampled',0) for d in latest_ten)
    tail={'build':last['build'],'pid':last['pid'],'session':last['session'],
          'title':last.get('title'),'windows':sorted(latest_ten_windows),
          'duration_s':tail_s,'frame_histogram':hist_metrics(tail_frames),
          'max_frame_ms':max(d['frame_ms']['max_ms'] for d in latest_ten),
          'over50ms':sum(d['frame_ms']['over50ms'] for d in latest_ten),
          'over100ms':sum(d['frame_ms']['over100ms'] for d in latest_ten),
          'shader_cost_us':{k:tuple_totals([d['shader_cost_us'] for d in latest_ten],k) for k in ['source','module','graphics','compute']},
          'texture_hash_bytes':tail_bytes if tail_hash else None,'hash_mib_per_interval':tail_bytes/2**20/tail_n if tail_n and tail_hash else None,
          'hash_gib_per_second':tail_bytes/2**30/tail_s if tail_s and tail_hash else None,
          'hash_ticks':sum(int(d['kv'].get('texture_hash_ticks',0)) for d in tail_hash),
          'texture_ms_sample_weighted':sum(d.get('rsx_frame',{}).get('texture_ms',0)*d.get('rsx_frame',{}).get('sampled',0) for d in latest_ten)/tail_samples if tail_samples else None,
          'notes':'Selected final ten guest-labelled report windows, not a controlled scene. No gameplay/cinematic distinction is inferred.'}
    if not tail_frames:
        tail['frame_histogram']=None
    return tail

def analyze_scope(ts, process_rows):
    """Detailed requested window range; retain each denominator and timer scope."""
    first,last=ts[0],ts[-1]
    windows={d['window'] for d in ts}
    ps=[d for d in process_rows if d['_report_context'] and
        d['_report_context'][0]==last['session'] and d['_report_context'][1] in windows]
    frame_rows=[d for d in ps if ' FRAMEPROF527 ' in d['message']]
    if {int(d['kv']['window']) for d in frame_rows}!=windows:
        raise ValueError('Requested detailed scope lacks frame histograms.')
    intervals=sum(d['frame_ms']['intervals'] for d in ts)
    core_frames=sum(d['summary']['frames'] for d in ts)
    rsx_frames=sum(d['rsx_frame']['frames'] for d in ts)
    sample_count=sum(d['rsx_frame']['sampled'] for d in ts)
    rsx_rows=[d for d in ps if ' RSXFRAME551 ' in d['message']]
    waits={k:tuple_totals([d['wait_ms'] for d in ts],k) for k in ts[0]['wait_ms']}
    sync={k:tuple_totals([d['rsx_sync'] for d in ts],k) for k,v in ts[0]['rsx_sync'].items() if isinstance(v,str)}
    jit={k:tuple_totals([d['jit'] for d in ts],k) for k in ts[0]['jit']}
    hash_rows=[d for d in ps if ' JITMEM ' in d['message']]
    return {
        'build':last['build'],'pid':last['pid'],'session':last['session'],
        'titles':sorted({d.get('title','unavailable') for d in ts}),
        'phase_snapshots':sorted({d['frame_ms']['phase'] for d in ts}),
        'windows':sorted(windows),'timeline_lines':[d['_line'] for d in ts],
        'performance_line_begin':min(d['_line'] for d in ps),
        'performance_line_end':max(d['_line'] for d in ps),
        'utc_first_report':utc(first['timestamp']),'utc_last_report':utc(last['timestamp']),
        'window_duration_ms':sum(d['frame_ms']['window_ms'] for d in ts),
        'denominators':{'frame_intervals':intervals,'coreprof_frames':core_frames,
                        'rsx_frames':rsx_frames,'sampled_rsx_frames':sample_count},
        'frames_histogram':hist_metrics(frame_rows),
        'max_frame_ms':max(d['frame_ms']['max_ms'] for d in ts),
        'over50ms':sum(d['frame_ms']['over50ms'] for d in ts),
        'over100ms':sum(d['frame_ms']['over100ms'] for d in ts),
        'wait_ms':waits,'rsx_sync_ms':sync,
        'texture_fence_ms_per_rsx_frame':sync['texture']['total']/rsx_frames if rsx_frames else None,
        'texture_fences_per_rsx_frame':sync['texture']['count']/rsx_frames if rsx_frames else None,
        'draws_per_rsx_frame':sum(int(d['kv']['draws']) for d in rsx_rows)/rsx_frames if rsx_frames else None,
        'summary_ms_weighted_per_coreprof_frame':{
            k:sum(d['summary'][k]*d['summary']['frames'] for d in ts)/core_frames if core_frames else None
            for k in ['ppu_ms','spu_ms','rsx_ms','gpu_fence_wait_ms']},
        'rsx_sample_weighted_ms':{
            k:sum(d['rsx_frame'][k]*d['rsx_frame']['sampled'] for d in ts)/sample_count if sample_count else None
            for k in ['setup_ms','vertex_ms','texture_ms','exec_ms','flip_ms']},
        'shader_cost_us':{k:tuple_totals([d['shader_cost_us'] for d in ts],k)
                          for k in ['source','module','graphics','compute']},
        'jit_ms':jit,
        'spu_wait_ms':{k:{field:value for field,value in tuple_totals([d['spu_wait'] for d in ts],k).items()
                         if field in ['count','total']}
                       for k in ['getllar_poll','getllar_sleep','event_wait']},
        'spu_putllc_counts':{k:sum(d['spu_wait'][k] for d in ts)
                            for k in ['putllc_ok','putllc_fail','putllc_heavy']},
        'hybrid_texture_hash':{'bytes':sum(int(d['kv'].get('texture_hash_bytes',0)) for d in hash_rows),
                               'ticks':sum(int(d['kv'].get('texture_hash_ticks',0)) for d in hash_rows),
                               'scope':'Only the hybrid >=4 KiB path, not every possible texture hash.'},
        'peak_footprint_bytes':max(d['memory_bytes']['peak_footprint'] for d in ts),
        'min_available_bytes':min(d['host']['available_min_bytes'] for d in ts),
        'host_thermal_max':max(d['host']['thermal_max'] for d in ts),
        'memory_pressure_peak':max(d['resilience']['memory_pressure_peak'] for d in ts),
        'vdec_process_lifetime_last':last['vdec_io_process_lifetime'],
        'shader_long_events_dropped':sum(d['shader_stall']['dropped'] for d in ts),
        'log_budget_dropped_max':max(d['lost']['log_budget_dropped'] for d in ts),
        'rotations_last':last['lost']['rotations'],
        'scope_note':'An explicitly selected report range, not an identified gameplay or cinematic scene. Timers overlap.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--logs','--root',dest='logs',type=Path,help='Directory containing the three RPCS3 export logs.')
    parser.add_argument('--output',type=Path,help='Sanitized evidence JSON destination.')
    parser.add_argument('--title',default='BCES00510',help='Explicit title identifier for final-window selection.')
    parser.add_argument('--suffix',default='',help='Filename suffix before .log, e.g. (1); keeps separate exports distinct.')
    parser.add_argument('--reference-report',type=Path,help='Previous evidence JSON; compare file digests without merging exports.')
    parser.add_argument('--window-scope',action='append',default=[],metavar='BUILD:PID:SESSION:FIRST:LAST',
                        help='Detailed contiguous range; repeat for independent ranges without merging their metrics.')
    parser.add_argument('--self-test',action='store_true',help='Run arithmetic and redaction boundary checks.')
    args=parser.parse_args()
    if args.self_test:
        print(json.dumps(self_check()))
    else:
        if args.logs is None or args.output is None:
            parser.error('--logs and --output are required unless --self-test is selected')
        if '/' in args.suffix or '\\' in args.suffix:
            parser.error('--suffix cannot contain path separators')
        scopes=[]
        for raw in args.window_scope:
            try:
                build,pid,session,first,last=raw.split(':')
                scope=(build,int(pid),int(session),int(first),int(last))
                if scope[3]<1 or scope[4]<scope[3]: raise ValueError()
            except ValueError:
                parser.error('--window-scope must be BUILD:PID:SESSION:FIRST:LAST with 1 <= FIRST <= LAST')
            scopes.append(scope)
        main(args.logs,args.output,args.title,args.suffix,args.reference_report,scopes)
