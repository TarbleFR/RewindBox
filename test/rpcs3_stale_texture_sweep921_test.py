#!/usr/bin/env python3
"""REWINDBOX_STALE_TEXTURE_SWEEP_921, executed: the release of idle iOS textures whose guest bytes changed, on the real
texture cache, with the Core 920 tree as the witness.

On iOS every CPU texture is confirmed by a hash of its guest bytes (texture_cache_protection_policy.h), so a texture
whose memory the title filled with other data stays cached until a lookup asks for it again; upstream's purge of
stale hashed sections (ranged_storage::trim_sections) only visits blocks of more than 256 locked sections. Black Ops II
journals of builds 620-721: 200-450 new sections per 5 s window, none released, the texture pool 74 -> 568 MiB in 4.4
minutes. The harness of test/rpcs3_texture_lookup_memo660_harness.py compiles a tree's real rsx::texture_cache (lookups,
sections, buffered_section::sync and the new sync_unpredicted, trim_sections, the lookup memo) on host stand-ins for
Vulkan; the scenarios (test/native/rpcs3_stale_texture_sweep921_scenarios.cpp.in) end each frame as VKGSRender::flip does
(the pass and the descriptor invalidation of VKPresent.cpp with the candidate, then vk::texture_cache::on_frame_end).

  stream      Black Ops II shape: a working set sampled every frame, one texture per frame streamed into a 24 MiB pool at
              shifting offsets, the last four sampled, then never again (2400 frames, 3 laps of the pool);
  idle_valid  32 textures idle for 400 frames with unchanged bytes, then sampled again;
  restored    a texture overwritten while idle, then its bytes written back and sampled again;
  bound       a texture left bound in the registers, idle and changed, then sampled again;
  budget      600 idle 64 KiB sections whose bytes all changed;
  prehash     the same with Texture Pre-Validation on (God of War III's setting).
Required: (1) witness: Core 920 keeps every streamed section (live bytes over the pool, growing to the end), the
candidate with the pass off does exactly the same; (2) candidate: live bytes bounded after the first lap, stale idle
sections near zero; (3) in every scenario and run every bound slot serves the current guest bytes; (4) the pass never
releases a section whose bytes match, a bound one or one used in the last 64 frames, never touches the prehash tables,
hashes at most 4 MiB plus one section and looks at most 2048 sections per pass, and examines each stale section once;
(5) idle unchanged textures are kept (no upload, the same images when they come back); (6) the production glue
(VKPresent.cpp, VKTextureCache.cpp, the policy and the setting) is the one modelled; (7) negative controls: a tree that
releases on a match, ignores the bound set or the idle delay fails these checks (the test detects what it claims).

    python3 test/rpcs3_stale_texture_sweep921_test.py --source CORE921 [--control CORE920] [--cxx g++] [--no-sanitizers]
        [--skip-mutations] [--report OUT.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rpcs3_texture_lookup_memo660_harness as harness  # noqa: E402

TEX = 'rpcs3/Emu/RSX/Common/texture_cache.h'
VKPRESENT = 'rpcs3/Emu/RSX/VK/VKPresent.cpp'
VKCACHE = 'rpcs3/Emu/RSX/VK/VKTextureCache.cpp'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
HEADER = 'rpcs3/ios/IOSStaleTextureSweep.h'
BYTES_PER_PASS = 4 << 20
SECTIONS_PER_PASS = 2048
POOL = 24 << 20
INCREMENT = Path(__file__).resolve().parents[1] / 'build-utils/rpcs3/core921-from-920.patch'

# Negative controls: (name, include-root mutations, rendered-code mutations, what must then fail).
MUTATIONS = [
    ('release_on_match', [], [('const bool unchanged = (fast_hash_internal() == mem_hash);', 'const bool unchanged = false;')],
     'released_valid'),
    ('no_bound_set', [(TEX, ' ||\n\t\t\t\t\t\t\texclusion_list.contains(region.get_section_base()))', ')')], [], 'released_bound'),
    ('no_idle_delay', [(TEX, '!residency::idle(region.last_use_frame, now) || !sweep::revisit_due', '!sweep::revisit_due')], [],
     'released_recent'),
]


def require(condition, message):
    if not condition:
        raise harness.Fail('FAIL: ' + message)


def driver() -> str:
    base = (harness.NATIVE / 'rpcs3_texture_lookup_memo660_driver.cpp.in').read_text(encoding='utf-8')
    scenarios = (harness.NATIVE / 'rpcs3_stale_texture_sweep921_scenarios.cpp.in').read_text(encoding='utf-8')
    require(base.count('//@@SCENARIOS@@') == 1, 'driver marker')
    return base[:base.index('//@@SCENARIOS@@')] + scenarios


def reverted_control(tree: Path, work: Path) -> Path:
    """The Core 920 witness: the source's rpcs3/ with the Core 921 increment reverted (every other top-level entry shared)."""
    control = work / 'control920'
    shutil.copytree(tree / 'rpcs3', control / 'rpcs3', symlinks=True)
    for entry in tree.iterdir():
        if entry.name not in ('rpcs3', '.git'):
            (control / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
    reverted = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(INCREMENT)], cwd=control, capture_output=True, text=True)
    require(reverted.returncode == 0, 'the Core 921 increment does not revert on the source:\n' + reverted.stderr[-2000:])
    return control


def build(tree: Path, work: Path, name: str, have_sweep: bool, cxx: str, sanitize: bool, mutations=None, code_mutations=None) -> Path:
    code = harness.render(tree, True, driver=driver())
    for pattern, replacement in code_mutations or []:
        require(code.count(pattern) == 1, f'code mutation pattern {pattern[:70]!r}')
        code = code.replace(pattern, replacement)
    return harness.compile_harness(tree, work, name, code, {'CANDIDATE': 1, 'HAVE_SWEEP': 1 if have_sweep else 0}, cxx=cxx,
                                   sanitize=sanitize, mutations=mutations)


def run(binary: Path, mode: str, memo: str = 'verify_all') -> dict:
    leaks = 'detect_leaks=1:' if sys.platform.startswith('linux') else ''
    env = {'ASAN_OPTIONS': leaks + 'abort_on_error=1', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
    began = time.monotonic()
    result = subprocess.run([str(binary), mode, memo], capture_output=True, text=True, timeout=1800, env=env)
    require(result.returncode == 0, f'{binary.name} {mode} {memo} failed ({result.returncode}):\n' + result.stderr[-4000:])
    data = json.loads(result.stdout)
    data['seconds'] = round(time.monotonic() - began, 2)
    return data


def records(data: dict, scenario: str, kind: str) -> list:
    return [r for r in data['scenarios'][scenario] if r['k'] == kind]


def one(data: dict, scenario: str, kind: str) -> dict:
    found = records(data, scenario, kind)
    require(len(found) == 1, f'{scenario}: {len(found)} {kind} records')
    return found[0]


def end(data: dict, scenario: str) -> dict:
    return next(r for r in data['scenarios'][scenario] if r['k'] == 'end')


def totals(data: dict, scenario: str) -> dict:
    return one(data, scenario, 'totals')


def stream_curve(data: dict) -> list:
    return [(r['frame'], r['live'], r['live_bytes'], r['stale_idle']) for r in data['scenarios']['stream'] if r['k'] in ('sample', 'end')]


def check_common(data: dict, label: str) -> None:
    require(data['log_errors'] == 0, f'{label}: logged errors')
    for name in data['scenarios']:
        last = end(data, name)
        require(last['served'] > 0 and last['stale_served'] == 0, f'{label} {name}: {last["stale_served"]} of {last["served"]} served slots stale')


def check_glue(tree: Path) -> dict:
    present = harness.text(tree, VKPRESENT)
    block = present[present.index('REWINDBOX_STALE_TEXTURE_SWEEP_921'):]
    block = block[:block.index('#endif')]
    for needle in ('rpcs3::ios::stale_texture_sweep::enabled.load(', 'scan_array(rsx::method_registers.fragment_textures);',
                   'scan_array(rsx::method_registers.vertex_textures);', 'm_texture_cache.release_stale_textures(bound_textures)',
                   'rsx::invalidate_sampler_context(fs_sampler_state, m_textures_dirty, context);',
                   'rsx::invalidate_sampler_context(vs_sampler_state, m_vertex_textures_dirty, context);',
                   'rsx::texture_upload_context::shader_read, rsx::texture_upload_context::blit_engine_src'):
        require(block.count(needle) == 1, f'VKPresent.cpp sweep block: {needle}')
    require(present.index('REWINDBOX_STALE_TEXTURE_SWEEP_921') < present.index('m_texture_cache.on_frame_end();'),
            'the pass runs before the texture cache frame end')
    vk = harness.body(harness.text(tree, VKCACHE), '\tbool texture_cache::release_stale_textures(const std::set<u32>& exclusion_list)\n')
    require('release_stale_idle_sections(exclusion_list,' in vk and '.released != 0;' in vk, 'VKTextureCache.cpp release_stale_textures')
    policy = harness.text(tree, POLICY)
    require(policy.count('resolve_mode(g_cfg.ios_experimental.stale_texture_sweep, true)') == 1 and
            policy.count('rpcs3::ios::stale_texture_sweep::enabled.store(resolved.stale_texture_sweep') == 1 and
            'Resolved title policy 921:' in policy, 'policy: Automatic enables the pass for every title, logged')
    require(harness.text(tree, SETTINGS).count('"experimental.stale_texture_sweep"') == 1, 'setting in the catalog')
    header = harness.text(tree, HEADER)
    require(f'bytes_per_pass = 4ull << 20' in header and f'sections_per_pass = {SECTIONS_PER_PASS}' in header, 'pass limits')
    return {'vkpresent': 'pass, bound set and invalidation present', 'policy': 'automatic = every title'}


def check_witness(witness: dict, label: str) -> dict:
    curve = stream_curve(witness)
    last = end(witness, 'stream')
    half = next(c for c in curve if c[0] == 1200)
    require(last['live_bytes'] > POOL and last['live'] >= 2000, f'{label}: the witness keeps {last["live"]} sections, {last["live_bytes"]} B')
    require(last['live_bytes'] >= 1.8 * half[2], f'{label}: the witness kept growing ({half[2]} -> {last["live_bytes"]})')
    require(last['stale_idle'] >= 1000, f'{label}: stale idle sections in the witness: {last["stale_idle"]}')
    return {'frames': last['frame'], 'live_sections': last['live'], 'live_mib': round(last['live_bytes'] / 2**20, 1),
            'live_mib_at_1200': round(half[2] / 2**20, 1), 'stale_idle': last['stale_idle'], 'uploads': last['uploads'],
            'hashes': last['hashes'], 'seconds': witness['seconds']}


def check_candidate(sweep: dict, witness: dict, label: str) -> dict:
    curve = stream_curve(sweep)
    last = end(sweep, 'stream')
    after_lap = [c for c in curve if c[0] >= 1200]
    plateau = max(c[2] for c in after_lap)
    at_1200 = next(c for c in curve if c[0] == 1200)
    require(plateau <= 1.15 * at_1200[2], f'{label}: live bytes still grow after the first laps ({at_1200[2]} -> {plateau})')
    require(last['live_bytes'] <= POOL + (2 << 20) and last['live_bytes'] < end(witness, 'stream')['live_bytes'] / 3,
            f'{label}: live bytes {last["live_bytes"]}')
    require(last['stale_idle'] <= 200, f'{label}: {last["stale_idle"]} stale idle sections left')
    require(last['uploads'] == end(witness, 'stream')['uploads'], f'{label}: uploads {last["uploads"]} vs witness {end(witness, "stream")["uploads"]}')
    report = {'stream': {'live_sections': last['live'], 'live_mib': round(last['live_bytes'] / 2**20, 1),
                         'live_mib_at_1200': round(at_1200[2] / 2**20, 1), 'plateau_mib': round(plateau / 2**20, 1),
                         'stale_idle': last['stale_idle'], 'uploads': last['uploads'], 'hashes': last['hashes'],
                         'seconds': sweep['seconds']}}
    for name in sweep['scenarios']:
        t = totals(sweep, name)
        for key in ('released_valid', 'released_bound', 'released_recent', 'prehash_records'):
            require(t[key] == 0, f'{label} {name}: {key}={t[key]}')
        require(t['max_pass_bytes'] <= BYTES_PER_PASS + t['max_section_bytes'], f'{label} {name}: a pass hashed {t["max_pass_bytes"]} B')
        require(t['max_pass_seen'] <= SECTIONS_PER_PASS, f'{label} {name}: a pass looked at {t["max_pass_seen"]} sections')
        report.setdefault('passes', {})[name] = {k: t[k] for k in ('passes', 'examined', 'examined_bytes', 'released', 'released_bytes',
                                                                   'revolutions', 'max_pass_bytes', 'max_pass_seen')}
    s = totals(sweep, 'stream')
    report['stream'].update(examined_mib=round(s['examined_bytes'] / 2**20, 1), released=s['released'],
                            hashed_per_frame_kib=round(s['examined_bytes'] / 1024 / max(1, s['passes']), 1))
    # idle_valid: kept, no upload, the same images.
    back = one(sweep, 'idle_valid', 'return')
    require(totals(sweep, 'idle_valid')['released'] == 0 and back['uploads'] == 0 and back['same_images'] == 8,
            f'{label} idle_valid: released {totals(sweep, "idle_valid")["released"]}, uploads {back["uploads"]}, same images {back["same_images"]}')
    require(totals(sweep, 'idle_valid')['examined'] >= 32, f'{label} idle_valid: the idle textures were examined')
    # restored: released while different, one upload when it comes back; the witness keeps and reuses it.
    require(totals(sweep, 'restored')['released'] == 1 and one(sweep, 'restored', 'return')['uploads'] == 1,
            f'{label} restored: {totals(sweep, "restored")["released"]} released, {one(sweep, "restored", "return")["uploads"]} uploads')
    require(one(witness, 'restored', 'return')['uploads'] == 0, 'witness restored: the kept section is reused')
    # bound: never examined, the lookup uploads it again in both runs.
    require(totals(sweep, 'bound')['released'] == 0 and one(sweep, 'bound', 'return')['uploads'] == 1 and
            one(witness, 'bound', 'return')['uploads'] == 1, f'{label} bound')
    # budget: every stale section examined once and released; passes within their limits.
    b = totals(sweep, 'budget')
    require(b['released'] == 600 and b['examined'] == 600, f'{label} budget: examined {b["examined"]}, released {b["released"]}')
    passes = [r for r in sweep['scenarios']['budget'] if r['k'] == 'pass']
    require(len(passes) == 30, 'budget samples')
    # prehash: the four changed textures released, the four others kept, no prehash record.
    p = totals(sweep, 'prehash')
    require(p['released'] == 4 and end(sweep, 'prehash')['live'] == 5, f'{label} prehash: released {p["released"]}, live {end(sweep, "prehash")["live"]}')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True, help='the tree with REWINDBOX_STALE_TEXTURE_SWEEP_921')
    parser.add_argument('--control', type=Path, help='the Core 920 tree (the witness); default: the source with the Core 921 '
                        'increment (build-utils/rpcs3/core921-from-920.patch) reverted')
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--skip-mutations', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    tree = args.source.resolve()
    sanitize = not args.no_sanitizers
    report: dict = {'cxx': args.cxx, 'sanitizers': sanitize, 'glue': check_glue(tree)}
    with tempfile.TemporaryDirectory(prefix='sweep921-') as temporary:
        work = Path(temporary)
        control = args.control.resolve() if args.control else reverted_control(tree, work)
        report['control'] = 'given' if args.control else 'source with the Core 921 increment reverted'
        require('REWINDBOX_STALE_TEXTURE_SWEEP_921' not in harness.text(control, TEX), 'the control tree already has the pass')
        witness_binary = build(control, work, 'witness920', False, args.cxx, sanitize)
        candidate_binary = build(tree, work, 'candidate921', True, args.cxx, sanitize)
        for memo in ('verify_all', 'active'):
            witness = run(witness_binary, 'control', memo)
            disabled = run(candidate_binary, 'control', memo)
            sweep = run(candidate_binary, 'sweep', memo)
            for data, label in ((witness, 'witness'), (disabled, 'disabled'), (sweep, 'sweep')):
                check_common(data, f'{memo} {label}')
            require(stream_curve(disabled) == stream_curve(witness), f'{memo}: the pass off is not the Core 920 behaviour')
            report[memo] = {'witness_920': check_witness(witness, f'{memo} witness'), 'candidate_921': check_candidate(sweep, witness, f'{memo} sweep')}
            print(f"{memo}: stream live {report[memo]['witness_920']['live_mib']} MiB ({report[memo]['witness_920']['live_sections']} sections) "
                  f"with Core 920, {report[memo]['candidate_921']['stream']['live_mib']} MiB ({report[memo]['candidate_921']['stream']['live_sections']}) "
                  f"with the pass; {report[memo]['candidate_921']['stream']['released']} released, "
                  f"{report[memo]['candidate_921']['stream']['hashed_per_frame_kib']} KiB hashed per frame")
        no_invalidation = run(candidate_binary, 'sweep_no_invalidation')
        report['without_descriptor_invalidation'] = {name: end(no_invalidation, name)['stale_served'] for name in no_invalidation['scenarios']}
        if not args.skip_mutations:
            report['negative_controls'] = {}
            for name, mutations, code_mutations, key in MUTATIONS:
                mutant = build(tree, work, 'mutant-' + name, True, args.cxx, False, mutations=mutations, code_mutations=code_mutations)
                data = run(mutant, 'sweep')
                found = {scenario: totals(data, scenario)[key] for scenario in data['scenarios'] if totals(data, scenario)[key]}
                require(found, f'negative control {name}: no scenario shows {key}')
                report['negative_controls'][name] = found
                print(f'negative control {name}: {key} in {found}')
    report['result'] = 'passed'
    print('PASS: with the pass the real texture cache keeps a bounded set of sections over a streamed pool (Core 920 keeps every '
          'one), releases only idle unbound sections whose guest bytes changed, within its per-pass limits, without the prehash '
          'tables; every slot serves the current bytes; the pass off is Core 920; negative controls fail as expected')
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except harness.Fail as failure:
        raise SystemExit(str(failure))
