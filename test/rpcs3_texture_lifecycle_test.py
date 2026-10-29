#!/usr/bin/env python3
"""Exercise production texture retirement and ordered index maintenance.

Storage, lifecycle and lookup bodies are extracted verbatim. GPU resources,
guest mappings and validation are host adapters. The address case compares
594 with this candidate and checks cross-block membership/index invariants.
The exact case compares each lifecycle's indexed lookup with its own existing
linear fallback, restoring the same storage between calls. Private range
retirement stays private in the compiled section adapter; only the actual
production owning-block friend declaration grants clear() access.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import tempfile

import rpcs3_texture_address_index_test as address
import rpcs3_texture_exact_index_test as exact
from rpcs3_cell559_test import without_ios_blocks

ROOT = Path(__file__).resolve().parents[1]
CACHE, UTILS, CPP, RANGE = address.CACHE, address.UTILS, address.CPP, address.RANGE
SOURCE = [UTILS, CACHE]
SUPPORT = [CPP, RANGE, exact.PITCH, exact.ARRAY]
ADAPTER = ROOT / 'test/native/rpcs3_texture_lifecycle.inc'
METHODS = [
    'void initialize(ranged_storage_block_type* block)',
    'void reset(const address_range32& memory_range)', 'void notify_range_valid()',
    'void invalidate_range()', 'void on_section_resources_created()',
    'void on_section_resources_destroyed()', 'void set_dirty(bool new_dirty)',
    'void update_unreleased()', 'bool is_unreleased() const', 'bool sync_protection()',
    'bool matches(u32 format, u32 width, u32 height, u32 depth, u32 mipmaps) const',
    'bool matches(u32 rsx_address, u32 format, u32 width, u32 height, u32 depth, u32 mipmaps) const',
]
STORAGE = [
    ('template <typename section_storage_type, usz array_size>', 'class ranged_storage_block_list\n'),
    ('template <typename _ranged_storage_type>', 'class ranged_storage_block\n'),
    ('template <typename traits>', 'class ranged_storage\n'),
]
sha, braced = address.sha, address.braced


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def source_guards(source, baseline):
    for path in [CACHE] + [p for p in SUPPORT if p != CPP]:
        assert sha(source / path) == sha(baseline / path), path
    # The global follow-up changes only sync(), which this lifecycle harness
    # never extracts. Its publication/concurrency has a separate native test.
    current_cpp, old_cpp = (source / CPP).read_text(), (baseline / CPP).read_text()
    sync = 'bool buffered_section::sync() const'
    assert current_cpp.replace(braced(current_cpp, sync), '@SYNC@', 1) == old_cpp.replace(braced(old_cpp, sync), '@SYNC@', 1)
    current, old = (source / UTILS).read_text(), (baseline / UTILS).read_text()
    assert without_ios_blocks(current) == without_ios_blocks(old)
    assert braced(current, 'class ranged_storage\n') == braced(old, 'class ranged_storage\n')
    assert braced(current, 'class ranged_storage_block_list\n') == braced(old, 'class ranged_storage_block_list\n')
    assert current.count('friend ranged_storage_block_type;') == 1
    assert 'friend ranged_storage_block_type;' not in old


def section_methods(util):
    methods = ''
    for signature in METHODS:
        text = util[util.index('class cached_texture_section :'):] if signature in (
            'void reset(const address_range32& memory_range)', 'void invalidate_range()') else util
        body = braced(text, signature)
        name = signature.split('(')[0].split()[-1]
        methods += body.replace(name + '(', 'Section::' + name + '(', 1) + '\n'
    return methods


def section_access(section, util):
    production = util[util.index('class cached_texture_section :'):]
    before_retirement = production[:production.index('void invalidate_range()')]
    assert re.findall(r'\b(public|protected|private)\s*:', before_retirement)[-1] == 'private'
    friend = 'friend ranged_storage_block_type;' if 'friend ranged_storage_block_type;' in production else ''
    old = 'void notify_range_valid();void invalidate_range();'
    assert section.count(old) == 1
    # The wrapper is an explicit stimulus for the old test's idempotence cases.
    # Production block.clear() still calls the private method directly.
    new = ('void notify_range_valid();\nprivate:\n' + friend + '\nvoid invalidate_range();\npublic:\n'
           'void invalidate_test_range(){invalidate_range();}\n')
    return section.replace(old, new)


def buffered(source):
    text = (source / CPP).read_text()
    return '\n'.join(braced(text, signature) for signature in (
        'void buffered_section::reset(', 'void buffered_section::invalidate_range(',
        'void buffered_section::discard(', 'const address_range32& buffered_section::get_bounds('))


def address_harness(source, baseline):
    code = address.ADAPTER.read_text().replace('.invalidate_range()', '.invalidate_test_range()')
    code = code.replace('// @RANGES@', exact.stripped(source / RANGE))
    code = code.replace('// @BUFFERED@', buffered(source))
    section_template = code.split('// @SECTION_BEGIN@')[1].split('// @SECTION_END@')[0]
    versions = ''
    for label, tree in [('before', baseline), ('after', source)]:
        util = (tree / UTILS).read_text()
        body = 'namespace ' + label + ' {\nusing namespace rsx;\n'
        for template, signature in STORAGE:
            # Expose storage solely for invariant inspection. Preserve private
            # cached-section access so the production clear call is compiled.
            body += template + '\n' + braced(util, signature).replace('private:', 'public:') + ';\n'
        section = section_access(section_template, util)
        lookup = braced((tree / CACHE).read_text(), 'section_storage_type *find_texture_from_dimensions(')
        section = section.replace('// @LOOKUP@', 'template <bool check_unlocked=false>\n' + lookup)
        versions += body + section + section_methods(util) + '}\n'
    start = code.index('// @SECTION_BEGIN@')
    end = code.index('// @SECTION_END@') + len('// @SECTION_END@')
    code = code[:start] + versions + code[end:]
    insertion = code.index('Counters correctness()')
    code = code[:insertion] + ADAPTER.read_text() + '\n' + code[insertion:]
    # Recheck full storage at each differential query, after all preceding edits.
    code = code.replace('void compare(before::Cache&', 'void audit_candidate(after::Cache&);\nvoid compare(before::Cache&', 1)
    anchor = ' assert(old==now&&old_validation==rsx::validations);'
    assert code.count(anchor) == 1
    code = code.replace(anchor, ' audit_candidate(b);\n' + anchor)
    anchor = 'int main(int argc,char**){const auto c=correctness();'
    assert code.count(anchor) == 1
    code = code.replace(anchor, 'int main(int argc,char**){lifecycle_cases();const auto c=correctness();')
    anchor = 'if(argc>1)benchmark();'
    assert code.count(anchor) == 1
    code = code.replace(anchor, 'std::cout<<",\\\"fullIndexChecks\\\":"<<lifecycle_index_checks'
                        '<<",\\\"boundaryRetags\\\":"<<lifecycle_retags'
                        '<<",\\\"baselineStaleMembershipChecks\\\":"<<lifecycle_negative_memberships'
                        '<<",\\\"clearReuseChecks\\\":"<<lifecycle_clear_reuses'
                        '<<",\\\"privateRetirementAccessChecked\\\":true";' + anchor)
    assert '// @' not in code
    return code


def exact_harness(tree):
    code = exact.ADAPTER.read_text().replace('.invalidate_range()', '.invalidate_test_range()')
    code = code.replace('// @RANGES@', exact.stripped(tree / RANGE))
    code = code.replace('// @ARRAY@', exact.stripped(tree / exact.ARRAY))
    code = code.replace('// @PITCH@', 'template <bool __is_surface=true, typename SurfaceType>\n' +
                        braced((tree / exact.PITCH).read_text(), 'inline bool pitch_compatible(const SurfaceType* surface, u32 pitch_required, u16 height_required)'))
    code = code.replace('// @BUFFERED@', buffered(tree))
    util = (tree / UTILS).read_text()
    storage = 'using namespace rsx;\n'
    for template, signature in STORAGE:
        storage += template + '\n' + braced(util, signature) + ';\n'
    code = code.replace('// @STORAGE@', storage)
    start = code.index('// @SECTION_BEGIN@')
    end = code.index('// @SECTION_END@') + len('// @SECTION_END@')
    code = code[:start] + section_access(code[start:end], util) + code[end:]
    code = code.replace('// @METHODS@', section_methods(util))
    indexed = exact.lookup_body(tree)
    selector = 'if (memory_range.valid() && memory_range.start == attr.address &&'
    assert indexed.count(selector) == 1
    # Force only the dispatch predicate. The existing iOS fallback, including
    # validation and swap-with-tail merge handling, remains byte-for-byte.
    linear = indexed.replace(selector, 'if (false && memory_range.valid() && memory_range.start == attr.address &&')
    assert indexed != linear
    lookups = ''
    for debug in [False, True]:
        if debug:
            lookups += '#define TEXTURE_CACHE_DEBUG\n'
        for label, lookup in [('before', linear), ('after', indexed)]:
            lookups += ('[[gnu::noinline]] Result query_' + label + ('_debug' if debug else '') +
                        '(const Attributes& attr,const address_range32& memory_range,const Options& options) {\n'
                        'const u32 scale=1,remap=0;rsx::simple_array<section_storage_type*> overlapping_locals;\n')
            lookups += lookup
            lookups += ('\nResult result;result.merge_count=overlapping_locals.size();'
                        'if(rsx::tracing)for(const auto* section:overlapping_locals)rsx::merges.push_back(section->id);return result;\n}\n')
        if debug:
            lookups += '#undef TEXTURE_CACHE_DEBUG\n'
    code = code.replace('// @LOOKUPS@', lookups)
    code = code.replace('// @SECTION_BEGIN@', '').replace('// @SECTION_END@', '')
    # The existing fallback stops at a matching unowned pointer. Its rank in
    # std::unordered_set depends on the allocator and standard library, even
    # when both lookups preserve exactly the same first match and trace.
    # Observe that rank without changing storage or traversal order. Keep the
    # native per-query counters exact instead of pinning one host's bucket order.
    anchor = 'struct Counts {'
    assert code.count(anchor) == 1
    code = code.replace(anchor, 'inline u64 lifecycle_unowned_rank=0,lifecycle_unowned_entries=0;\n' + anchor)
    anchor = 'const auto unowned=compare(r,q,counts);assert(unowned.selected&&unowned.view==1000);'
    assert code.count(anchor) == 1
    observation = '''static_assert(sizeof(Section*)==8);
  auto& prefix_block=r.cache->m_storage.block_for(q.range.start);
  for(auto it=prefix_block.unowned_begin();it!=prefix_block.unowned_end();++it){
   ++lifecycle_unowned_entries;
   if((*it)->id==1000)lifecycle_unowned_rank=lifecycle_unowned_entries;
  }
  assert(lifecycle_unowned_entries==24&&lifecycle_unowned_rank>=1&&lifecycle_unowned_rank<=24);
  const auto prefix_counts=counts;
  const auto unowned=compare(r,q,counts);assert(unowned.selected&&unowned.view==1000);
  assert(counts.range_before-prefix_counts.range_before==2*lifecycle_unowned_rank+1);
  assert(counts.range_after-prefix_counts.range_after==2*lifecycle_unowned_rank+1);
  assert(counts.predicates_before-prefix_counts.predicates_before==lifecycle_unowned_rank+1);
  assert(counts.predicates_after-prefix_counts.predicates_after==lifecycle_unowned_rank+1);
  const u64 prefix_allocations=lifecycle_unowned_rank>8?1:0;
  assert(counts.allocations_before-prefix_counts.allocations_before==prefix_allocations);
  assert(counts.allocations_after-prefix_counts.allocations_after==prefix_allocations);'''
    code = code.replace(anchor, observation)
    anchor = 'if(argc>1)benchmark();'
    assert code.count(anchor) == 1
    code = code.replace(anchor, 'std::cout<<",\\\"unownedPrefixRank\\\":"<<lifecycle_unowned_rank'
                        '<<",\\\"unownedPrefixEntries\\\":"<<lifecycle_unowned_entries;' + anchor)
    assert '// @' not in code
    return code


def harnesses(source, baseline, case):
    source_guards(source, baseline)
    if case == 'address':
        return {'combined': address_harness(source, baseline)}
    assert case == 'exact'
    return {'baseline': exact_harness(baseline), 'candidate': exact_harness(source)}


def expected(source, baseline, case='address'):
    source, baseline = Path(source), Path(baseline)
    codes = harnesses(source, baseline, case)
    return dict(sourceSHA256={path: sha(source / path) for path in SOURCE + SUPPORT},
                baselineSHA256={path: sha(baseline / path) for path in SOURCE + SUPPORT},
                harnessesSHA256={label: digest(code) for label, code in codes.items()},
                adapterSHA256=sha(ADAPTER),
                retainedAdaptersSHA256={str(p.relative_to(ROOT)): sha(p) for p in (address.ADAPTER, exact.ADAPTER)},
                case=case, nonIosSourceIdentical=True, privateRangeAccessPreserved=True)


def verify_counts(result, case):
    if case == 'address':
        fixed = dict(queries=22753, mutations=8618, baselineDirtyPredicateCalls=26629,
                     indexedDirtyPredicateCalls=26629, fullIndexChecks=26872, boundaryRetags=4105,
                     baselineStaleMembershipChecks=216, clearReuseChecks=3)
        for key, value in fixed.items():
            assert result[key] == value, (key, result[key], value)
        for key in ('sameFirstMatch', 'sameValidationOrder', 'sameOverlapMembership',
                    'clearAndResourceLessRetags', 'sectionLayoutUnchanged',
                    'presentationWalkUnchanged', 'privateRetirementAccessChecked'):
            assert result[key] is True, key
        if 'benchmarks' in result:
            assert [b['sections'] for b in result['benchmarks']] == [8, 16, 17, 64, 256, 1024]
            for b in result['benchmarks']:
                assert b['lookupAllocations'] == 0
                predicates = {8: 165000, 16: 285000}.get(b['sections'], 60000)
                assert b['baselineDirtyPredicateCalls'] == b['indexedDirtyPredicateCalls'] == predicates
                assert b['recycleBeforeNs'] > 0 and b['recycleAfterNs'] > 0
            assert result['indexHeadersBytes'] == 0
    else:
        assert set(result) == {'baseline', 'candidate'}
        for label, item in result.items():
            assert item['unownedPrefixEntries'] == 24, (label, item['unownedPrefixEntries'])
            rank = item['unownedPrefixRank']
            assert type(rank) is int and 1 <= rank <= 24, (label, rank)
            # All other cases are invariant. This prefix adds two range
            # visits and one dirty visit per rank, and spills the production
            # 64-byte pointer buffer only beyond its eight inline entries.
            for key, value in dict(queries=13492, debugQueries=3365, mutations=4036,
                                  rangePredicateCallsBefore=3279618 + 2 * rank,
                                  rangePredicateCallsAfter=3200628 + 2 * rank,
                                  dirtyPredicateCallsBefore=12710 + rank,
                                  dirtyPredicateCallsAfter=18053 + rank,
                                  arrayAllocationsBefore=34 + int(rank > 8),
                                  arrayAllocationsAfter=31 + int(rank > 8)).items():
                assert item[key] == value, (label, key, item[key], value)
            for key in ('sameFirstMatch', 'sameValidationOrder', 'sameMergeOrder',
                        'sameMutationState', 'sameInvalidViewSelection',
                        'confirmedRangeDebugCovered', 'realStorageAndPitch'):
                assert item[key] is True, (label, key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=['address,undefined'])
    parser.add_argument('--case', choices=['address', 'exact'], default='address')
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    identity = expected(source, baseline, args.case)
    codes = harnesses(source, baseline, args.case)
    cxx = shlex.split(args.compiler)
    flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-DRPCS3_IOS']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    flags += (['-O1', '-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
              if args.sanitizer else ['-O3'])
    if args.sanitizer and platform.system() == 'Linux':
        flags += ['-fno-pie', '-no-pie']
    flags += ['-UNDEBUG']
    results = {}
    with tempfile.TemporaryDirectory(prefix='rpcs3-texture-lifecycle-') as temp:
        for label, code in codes.items():
            cpp, exe = Path(temp) / (label + '.cpp'), Path(temp) / label
            cpp.write_text(code)
            subprocess.run(cxx + flags + [str(cpp), '-o', str(exe)], check=True)
            run = subprocess.run([str(exe)] + (['benchmark'] if args.benchmark and args.case == 'address' else []),
                                 text=True, capture_output=True, timeout=180,
                                 env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'))
            if run.returncode:
                raise RuntimeError(f'{label}: exit {run.returncode}\n{run.stdout}\n{run.stderr}')
            results[label] = json.loads(run.stdout)
    result = results['combined'] if args.case == 'address' else results
    verify_counts(result, args.case)
    assert identity == expected(source, baseline, args.case)
    report = dict(passed=True, assertionsActive=True,
                  compiler=subprocess.check_output(cxx + ['--version'], text=True).splitlines()[0],
                  compilerFlags=flags, sanitizer=args.sanitizer, host=platform.machine(),
                  system=platform.system(), results=result, physicalDeviceTested=False,
                  gameplayMeasured=False, scope=__doc__, **identity)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
