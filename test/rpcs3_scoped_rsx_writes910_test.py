#!/usr/bin/env python3
"""REWINDBOX_SCOPED_RSX_UPLOADS_909, executed: the revalidation of an RSX guest write over its own range, on the real
texture cache, against a conservative witness.

Core 909 let NV308A inline data and NV0039 copies revalidate only the texture sections over the bytes they wrote
instead of starting a new global texture epoch; its test read the source. This one executes it. The harness of
test/rpcs3_texture_lookup_memo660_test.py compiles the tree's real rsx::texture_cache (lookups, sections,
buffered_section::sync, the prehash result table, sampler bindings, the lookup memo) on host stand-ins for Vulkan. The
driver adds the real body of VKGSRender::ios_rsx_wrote_guest_memory (extracted from VKGSRender.cpp) and, as the witness,
the real default of rsx::thread (RSXThread.cpp): a new global epoch for every write, the behaviour before Core 909.

Each scenario runs twice, scoped and witness, with the lookup memo off (God of War III) and active (Assassin's Creed):
  disjoint         a write over one texture, draws without any register change in between;
  limits           adjacent textures: straddling write, first and last byte, the bytes just outside;
  repeated         several writes in one epoch, with and without a draw in between, and a rewrite of the same bytes;
  prehash_late     a prehash of the old bytes published after the write (same epoch), a valid prehash of an intact one;
  destroy_recreate sections committed as a framebuffer, purged and evicted around the writes;
  alias            two shapes (two sections) over one guest range;
  fallback         an empty range, a wrapping range and the scope off: a new epoch, as before.
Required: (1) after every draw, what each slot serves is the current guest bytes (never stale), in both runs; (2) both
runs serve the same contents draw for draw; (3) the scoped run never hashes more than the witness and hashes less
wherever a texture stayed intact, with the same number of uploads; (4) a write next to a texture hashes nothing;
(5) negative controls: the tree with the section reset, the prehash bypass or the binding invalidation removed serves
stale data in these scenarios (the test detects what it claims to).

    python3 test/rpcs3_scoped_rsx_writes910_test.py --source CORE [--cxx g++] [--no-sanitizers] [--skip-mutations] [--report OUT.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rpcs3_texture_lookup_memo660_harness as harness  # noqa: E402

VK_CPP = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
THREAD_CPP = 'rpcs3/Emu/RSX/RSXThread.cpp'
TEX = 'rpcs3/Emu/RSX/Common/texture_cache.h'
UTILS = 'rpcs3/Emu/RSX/Common/texture_cache_utils.h'
RANGE_OF = '\tutils::address_range32 range_of(const tex_desc& t) { return utils::address_range32::start_length(address_of(t), t.pitch * t.height); }\n\n'
INTACT = {'disjoint', 'limits', 'repeated'}  # scenarios in which a bound texture stays intact across a write

# Negative controls: (name, [(file, pattern, replacement)], scenarios that must serve stale data).
MUTATIONS = [
    ('no_section_reset', [(TEX, '\t\t\t\tIt->reset_validation();\n', '')], {'disjoint', 'repeated', 'limits'}),
    ('no_prehash_bypass', [(UTILS, 'void reset_validation() const { validated_epoch = 0; prehash_bypass = true; }',
                            'void reset_validation() const { validated_epoch = 0; }')], {'prehash_late'}),
    ('no_binding_invalidation', [(TEX, '\t\t\tm_sampler_validation.invalidate(range.start, range.valid() ? u64{range.end} - range.start + 1 : 0);\n', '')],
     {'disjoint'}),
]


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def driver(tree: Path) -> str:
    base = (harness.NATIVE / 'rpcs3_texture_lookup_memo660_driver.cpp.in').read_text(encoding='utf-8')
    scenarios = (harness.NATIVE / 'rpcs3_scoped_rsx_writes910_scenarios.cpp.in').read_text(encoding='utf-8')
    vk_body = harness.body(harness.text(tree, VK_CPP), 'void VKGSRender::ios_rsx_wrote_guest_memory(u32 address, u32 length, u8 epoch_source)\n')
    base_call = 'rsx::thread::ios_rsx_wrote_guest_memory(address, length, epoch_source);'
    require(vk_body.count(base_call) == 1 and 'm_texture_cache.ios_revalidate_rsx_write(' in vk_body, 'the Vulkan hook body')
    base_body = harness.body(harness.text(tree, THREAD_CPP), '\tvoid thread::ios_rsx_wrote_guest_memory(u32 /*address*/, u32 /*length*/, u8 epoch_source)\n')
    require('advance_epoch(' in base_body, 'the default hook body')
    for marker, code in (('//@@BASE_HOOK_BODY@@', base_body), ('//@@VK_HOOK_BODY@@', vk_body.replace(base_call, 'base(address, length, epoch_source);'))):
        require(scenarios.count(marker) == 1, 'scenario marker ' + marker)
        scenarios = scenarios.replace(marker, code)
    require(base.count('//@@SCENARIOS@@') == 1, 'driver marker')
    return base[:base.index('//@@SCENARIOS@@')] + RANGE_OF + scenarios


def run(binary: Path, mode: str, memo: str) -> dict:
    leaks = 'detect_leaks=1:' if sys.platform.startswith('linux') else ''
    env = {'ASAN_OPTIONS': leaks + 'abort_on_error=1', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
    result = subprocess.run([str(binary), mode, memo], capture_output=True, text=True, timeout=600, env=env)
    require(result.returncode == 0, f'{binary.name} {mode} {memo} failed ({result.returncode}):\n' + result.stderr[-4000:])
    return json.loads(result.stdout)


def served(records: list) -> list:
    return [(r['draw'], r['slot'], r['content']) for r in records if r['k'] == 'served']


def stale(run_result: dict) -> dict:
    return {name: [(r['draw'], r['slot']) for r in records if r['k'] == 'served' and not r['fresh']]
            for name, records in run_result['scenarios'].items() if any(r['k'] == 'served' and not r['fresh'] for r in records)}


def work(records: list, label: str) -> dict:
    return next(r for r in records if r['k'] == 'work' and r['label'] == label)


def hashes_around(records: list, what: str) -> tuple:
    """Cumulative hash counts at the last draw before an event and at the first draw after it."""
    index = next(i for i, r in enumerate(records) if r['k'] == 'event' and r['what'] == what)
    before = [r['hashes'] for r in records[:index] if r['k'] == 'sections'][-1]
    after = next(r['hashes'] for r in records[index + 1:] if r['k'] == 'sections')
    return before, after


def check(scoped: dict, witness: dict, memo: str) -> dict:
    require(set(scoped['scenarios']) == set(witness['scenarios']) and len(scoped['scenarios']) == 7, 'scenarios')
    require(not stale(scoped) and not stale(witness), f'{memo}: stale data served: scoped {stale(scoped)} witness {stale(witness)}')
    require(scoped['log_errors'] == 0 and witness['log_errors'] == 0, 'logged errors')
    require(scoped['scoped_rsx_writes'] > 20 and witness['scoped_rsx_writes'] == 0, 'the scoped run goes through the scoped path')
    report = {}
    for name, records in scoped['scenarios'].items():
        other = witness['scenarios'][name]
        require(served(records) == served(other) and len(served(records)) >= 8, f'{memo} {name}: the two runs serve different contents')
        mine, theirs = work(records, 'after'), work(other, 'after')
        require(mine['uploads'] == theirs['uploads'], f'{memo} {name}: uploads {mine["uploads"]} against {theirs["uploads"]}')
        require(mine['hashes'] <= theirs['hashes'], f'{memo} {name}: the scoped run hashes more ({mine["hashes"]} > {theirs["hashes"]})')
        if name in INTACT:
            require(mine['hashes'] < theirs['hashes'], f'{memo} {name}: no hash saved on the intact texture')
        report[name] = {'draws_compared': len(served(records)), 'hashes_scoped': mine['hashes'], 'hashes_witness': theirs['hashes'],
                        'uploads': mine['uploads']}
    limits = scoped['scenarios']['limits']
    for outside in ('byte_before_N1', 'bytes_after_N2'):
        before, after = hashes_around(limits, outside)
        require(after == before, f'{memo}: a write next to the textures ({outside}) hashed {after - before} times')
    for inside in ('first_byte_N2', 'last_byte_N2', 'last_byte_N1', 'straddle_N1_N2'):
        before, after = hashes_around(limits, inside)
        require(after > before, f'{memo}: {inside} revalidated nothing')
    before, after = hashes_around(scoped['scenarios']['repeated'], 'write_A_same_bytes')
    require(after == before + 1, f'{memo}: a rewrite of the same bytes costs one hash and no upload, got {after - before}')
    for result in (scoped, witness):
        late = result['scenarios']['prehash_late']
        require(work(late, 'first_draw')['prehash_hits'] - work(late, 'published')['prehash_hits'] == 1,
                f'{memo} {result["mode"]}: the valid prehash of the intact texture was not used exactly once')
    fallback = scoped['scenarios']['fallback']
    epochs = [work(fallback, label)['epoch'] for label in ('before', 'empty_range', 'wrapping_range', 'scope_off')]
    require(epochs[1] == epochs[0] + 1 and epochs[2] == epochs[1] + 1 and epochs[3] == epochs[2] + 1,
            f'{memo}: an empty range, a wrapping range and the scope off each start one epoch: {epochs}')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--skip-mutations', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    tree = args.source.resolve()
    sanitize = not args.no_sanitizers
    report: dict = {'cxx': args.cxx, 'sanitizers': sanitize}
    with tempfile.TemporaryDirectory(prefix='scoped910-') as temporary:
        work_dir = Path(temporary)
        code = harness.render(tree, True, driver=driver(tree))
        binary = harness.compile_harness(tree, work_dir, 'scoped910', code, {'CANDIDATE': 1}, cxx=args.cxx, sanitize=sanitize)
        for memo in ('off', 'memo'):
            report[memo] = check(run(binary, 'scoped', memo), run(binary, 'witness', memo), memo)
            print(f'{memo}: ' + ', '.join(f"{name} {v['hashes_scoped']}/{v['hashes_witness']} hashes" for name, v in report[memo].items()))
        if not args.skip_mutations:
            report['negative_controls'] = {}
            for name, mutations, expected in MUTATIONS:
                mutant = harness.compile_harness(tree, work_dir, 'mutant-' + name, code, {'CANDIDATE': 1}, cxx=args.cxx, sanitize=False,
                                                 mutations=mutations)
                found = set(stale(run(mutant, 'scoped', 'off')))
                require(expected <= found, f'negative control {name}: stale data expected in {sorted(expected)}, found in {sorted(found)}')
                report['negative_controls'][name] = sorted(found)
                print(f'negative control {name}: stale data in {sorted(found)}')
    report['result'] = 'passed'
    print('PASS: RSX writes revalidated over their range on the real texture cache serve the current guest bytes in every draw, '
          'the same contents as the global-epoch witness, with fewer hashes on intact textures; stale prehash never validates; '
          'negative controls serve stale data')
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except harness.Fail as failure:
        raise SystemExit(str(failure))
