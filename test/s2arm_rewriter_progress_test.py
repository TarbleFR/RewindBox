#!/usr/bin/env python3
"""The progress report added to S2Arm's rewriter reports only (plain python3, no S2Arm source needed).

build-utils/s2arm/prepare/patches/0001-rewriter-progress-report.patch adds a per-thread progress callback to
runtime/rewriter at the pinned commit, so that the Switch 2 preparation bar moves while a big module is rewritten
(IPA 728: "code · 0%" for minutes on Mario Kart World). No output byte may depend on it: every added line must be a
report (rb_progress*, RB_PROGRESS*, rb_unit*), a comment or structure, and nothing outside rb_* may be assigned. The
outputs themselves are compared with the unpatched rewriter in .github/workflows/s2arm-prepare.yml.

    python3 -B test/s2arm_rewriter_progress_test.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / 'build-utils/s2arm/prepare/patches'
PREPARE = ROOT / 'native/s2arm/prepare'
failures, checks = [], 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


patches = sorted(PATCHES.glob('*.patch'))
check([p.name for p in patches] == ['0001-rewriter-progress-report.patch'], f'one prepare patch: {[p.name for p in patches]}')
patch = patches[0].read_text(encoding='utf-8') if patches else ''

files = re.findall(r'^diff --git a/(\S+) b/(\S+)$', patch, re.M)
check([a for a, _ in files] == ['runtime/rewriter/rewriter.c', 'runtime/rewriter/rewriter.h'] and all(a == b for a, b in files),
      f'the patch touches rewriter.c and rewriter.h only: {files}')

sections = re.split(r'^diff --git ', patch, flags=re.M)
added = {}
for section in sections[1:]:
    name = section.split()[0][2:]
    lines = section.splitlines()
    removed = [l for l in lines if l.startswith('-') and not l.startswith('---')]
    check(not removed, f'{name}: the patch removes no line ({removed[:3]})')
    added[name] = [l[1:] for l in lines if l.startswith('+') and not l.startswith('+++')]

REPORT = re.compile(r'\b(rb_progress\w*|RB_PROGRESS\w*|rb_unit\w*|s2a_rewrite_set_progress|s2a_progress_fn)\b')
STRUCTURE = {'', '{', '}', 'do { \\', '} while (0)', '} while (0);', '} \\'}


def code_of(line):
    """The line without its comments."""
    line = re.sub(r'/\*.*?\*/', '', line)
    return re.sub(r'//.*$', '', line).strip()


source_lines = added.get('runtime/rewriter/rewriter.c', [])
check(len(source_lines) > 20, f'the rewriter.c part adds the report ({len(source_lines)} lines)')
in_comment = False
for raw in source_lines:
    line = raw.strip()
    if in_comment:
        in_comment = '*/' not in line
        continue
    if line.startswith('/*') and '*/' not in line:
        in_comment = True
        continue
    code = code_of(line)
    if code in STRUCTURE or code.startswith('*'):
        continue
    check(REPORT.search(code), f'rewriter.c: an added line that is not a report: {raw!r}')
    # Nothing but rb_* is assigned or incremented.
    for target in re.findall(r'([A-Za-z_][\w.>\-\[\]]*)\s*(?:[+\-*/%|&^]?=)(?!=)', code):
        if target.split('->')[0].split('.')[0].split('[')[0].split()[-1].startswith('rb_') or target in ('fn', 'context'):
            continue
        check(False, f'rewriter.c: an added line assigns {target!r}: {raw!r}')
    for target in re.findall(r'(\w+)\s*(?:\+\+|--)|(?:\+\+|--)\s*(\w+)', code):
        name = target[0] or target[1]
        check(name.startswith('rb_'), f'rewriter.c: an added line increments {name!r}: {raw!r}')
check(sum('RewindBox' in l for l in source_lines) >= 6, 'the rewriter.c changes are marked RewindBox')
check(sum(l.strip().startswith('rb_progress(S2A_PROGRESS_') for l in source_lines) >= 9,
      'each pass of an attempt is reported (load .. outputs)')
check(any('rb_progress_attempt++' in l for l in source_lines) and any('rb_progress_attempt = 0' in l for l in source_lines),
      'the attempt number restarts for each module and grows with each new layout')
for loop in ('S2A_PROGRESS_BOUNDARIES, a', 'S2A_PROGRESS_SCAN, a', 'S2A_PROGRESS_SPINS, a', 'S2A_PROGRESS_ANALYZE, fi, funcs.n'):
    check(any(loop in l for l in source_lines), f'the long loop reports: {loop}')

header_lines = added.get('runtime/rewriter/rewriter.h', [])
header = '\n'.join(header_lines)
passes = re.findall(r'S2A_PROGRESS_(\w+)', header)
expected = ['LOAD', 'PREPASS', 'BOUNDARIES', 'SCAN', 'DATA', 'ANALYZE', 'GENERATE', 'LATE', 'SPINS', 'OUTPUTS']
check(passes[:10] == expected, f'the header names the ten passes in order: {passes}')
check('S2A_PROGRESS_LOAD = 1' in header and 'void s2a_rewrite_set_progress(s2a_progress_fn fn, void* context);' in header,
      'the header declares the callback and its setter')

# Our side: the same passes, shares that cover a module once, the callback cleared after each rewrite.
prepare = (PREPARE / 's2arm_prepare.c').read_text(encoding='utf-8')
names = re.search(r'k_pass_name\[\] = \{([^}]*)\}', prepare)
check(names and re.findall(r'"(\w*)"', names.group(1)) == [''] + [p.lower() for p in expected],
      'k_pass_name lists the rewriter passes in the header order')
starts = [float(x) for x in re.search(r'k_pass_start\[\] = \{([^}]*)\}', prepare).group(1).split(',')]
widths = [float(x) for x in re.search(r'k_pass_width\[\] = \{([^}]*)\}', prepare).group(1).split(',')]
check(len(starts) == len(widths) == 11 and abs(sum(widths) - 1) < 1e-9, f'the pass shares sum to 1 ({sum(widths)})')
check(all(abs(starts[i] - sum(widths[1:i])) < 1e-9 for i in range(1, 11)), 'each pass starts where the previous one ends')
call = prepare.index('s2a_rewrite_files_with_options(&rewrite, NULL, log)')
check(prepare.rindex('s2a_rewrite_set_progress(rewriter_progress, work)', 0, call) < call <
      prepare.index('s2a_rewrite_set_progress(NULL, NULL)', call), 'the callback is set around the rewrite only')
check('if (fraction < w->last) fraction = w->last;' in prepare, 'the bar never goes back')
check('rb_s2arm_nro_to_nso_ex(request->romfs_dir, nroexe, work ? walk_seen : NULL' in prepare and
      'rb_s2arm_nro_exports_ex(request->romfs_dir, table, work ? walk_seen : NULL' in prepare, 'the RomFS walks report their entries')
check('zbic_poll' in prepare and 'return watch->request->cancelled ? watch->request->cancelled(watch->request->context) : 0;' in prepare,
      'the ZBIC progress keeps the request\'s own cancel callback')
check('work_end(work);\n    return RB_S2ARM_PREPARE_OK;' in prepare, 'the bar reaches the end of the code stage')
nro = (PREPARE / 's2arm_nro.c').read_text(encoding='utf-8')
check(nro.count('if (x->seen) x->seen(x->seen_context, ++x->entries);   // progress display only') == 1, 'one walk counter')

# CI: the reference rewriter stays unpatched; the library is built on the patched copy; the iOS core applies the series.
prepare_yml = (ROOT / '.github/workflows/s2arm-prepare.yml').read_text(encoding='utf-8')
check('build-utils/s2arm/prepare/**' in prepare_yml, 's2arm-prepare.yml runs when the patch changes')
check('"$RUNNER_TEMP/s2arm-rb"' in prepare_yml and 'build-utils/s2arm/prepare/patches/*.patch' in prepare_yml,
      's2arm-prepare.yml applies the patch series to a copy of the checkout')
check('-B "$RUNNER_TEMP/rewriter-rb"' in prepare_yml and 'find "$RUNNER_TEMP/rewriter-rb" -name \'libs2a_rewriter.a\'' in prepare_yml,
      'our library links the patched rewriter')
check(prepare_yml.count('"$RUNNER_TEMP/rewriter/s2a-rewrite"') >= 3 and 'rewriter-rb/s2a-rewrite' not in prepare_yml,
      'every comparison runs against the unpatched s2a-rewrite')
core_yml = (ROOT / '.github/workflows/s2arm-core.yml').read_text(encoding='utf-8')
check('build-utils/s2arm/prepare/patches/*.patch' in core_yml and "'patches'" in core_yml,
      's2arm-core.yml applies the prepare patches and records them in the identity')
# The phone rewrites with the spin pass off (Mario Kart World, IPA 729: over 20 minutes in it); the CI references must
# run the same configuration, or their comparisons would not cover what the phone runs.
prepare_c = (ROOT / 'native/s2arm/prepare/s2arm_prepare.c').read_text(encoding='utf-8')
check('.module = module, .spin = 0};' in prepare_c and '.spin = 1' not in prepare_c, 'the on-device rewrite turns the spin pass off')
check("env['S2A_REWRITE_SPIN'] = '0'" in (ROOT / 'tools/s2arm_prototype/run_code_stage_test.py').read_text(encoding='utf-8')
      and 'S2A_REWRITE_SPIN=0 "$reference"' in (ROOT / 'tools/s2arm_prototype/run_prepare_test.sh').read_text(encoding='utf-8'),
      'both CI references rewrite with S2A_REWRITE_SPIN=0, as the phone does')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check('`build-utils/s2arm/prepare/patches/0001-rewriter-progress-report.patch`' in notices, 'the legal notices list the patch')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks}))
sys.exit(1 if failures else 0)
