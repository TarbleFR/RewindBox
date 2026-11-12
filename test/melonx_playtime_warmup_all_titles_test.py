#!/usr/bin/env python3
"""Play-time warm-ups detached for every title (adapt_playtime_warmup_all_titles) on the real prepared engine.

Usage: melonx_playtime_warmup_all_titles_test.py <Core 737 prepared MeloNX tree>
       melonx_playtime_warmup_all_titles_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the prepared Library.cs and checks that only the DetachPlayTimeWarmUps assignment
changed (from the Hogwarts flag to every title), that every other per-title policy keeps `hogwarts`, and that the
assignment is still made on the Vulkan renderer before it is wrapped by the threaded renderer. The policy-on behaviour
is the setprogram-warmup gate's proof, run on this very Library.cs (docs/evidence/melonx-739-gates/
setprogram-warmup-checks.json, its Library.cs postimage equal to this adapter's baseline): the real members with the
policy on draw every scenario with its own pipeline, put no warm-up on the render thread or the main cache, bind a burst
of programs without waiting for their warm-ups; with the policy off, the delivered path (SetProgram waits for the
warm-up). This test binds the scope change to that proof. No device; no FPS or heat claim.
Writes dist/melonx/playtime-warmup-all-titles-checks.json.
"""
from pathlib import Path
import difflib, hashlib, json, shutil, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_playtime_warmup_all_titles', _HOLD)
import adapt_playtime_warmup_all_titles as adapter  # noqa: E402

EVIDENCE = 'docs/evidence/melonx-739-gates/setprogram-warmup-checks.json'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


L = adapter.LIBRARY
check(list(adapter.BASELINE) == [L] and len(adapter.PAIRS) == 1, 'one replacement, in Library.cs, and no other file')
check(sha(SOURCE / L) == adapter.BASELINE[L], 'control is the Core 737 preparation: ' + L)
with tempfile.TemporaryDirectory(prefix='melonx-playtime-warmup-scope-') as temporary:
    work = Path(temporary)
    target = work / L
    target.parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / L, target)
    before = target.read_text(encoding='utf-8-sig').splitlines()
    changed = adapter.apply(work)
    after = target.read_text(encoding='utf-8-sig').splitlines()
    check([str(p.relative_to(work)) for p in changed] == [L], 'the adapter changed Library.cs only')
    candidate = target.read_text(encoding='utf-8-sig')
    drift = work / 'drift'
    (drift / L).parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / L, drift / L)
    (drift / L).write_bytes((drift / L).read_bytes() + b'\n// unreviewed drift\n')
    try:
        adapter.apply(drift)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'a drifted Library.cs is refused')
diff = list(difflib.ndiff(before, after))
removed = [line[2:].strip() for line in diff if line.startswith('- ')]
added = [line[2:].strip() for line in diff if line.startswith('+ ')]
code = lambda lines: [line for line in lines if not line.startswith('//')]
check(code(removed) == ['if (renderer is VulkanRenderer warmUpVulkan) warmUpVulkan.DetachPlayTimeWarmUps = hogwarts;'] and
      code(added) == ['if (renderer is VulkanRenderer warmUpVulkan) warmUpVulkan.DetachPlayTimeWarmUps = true;'],
      'only the play-time warm-up flag changes, to every title')
check(adapter.MARKER in adapter.NEW, 'the comment names the adapter')
for policy in ('GraphicsConfig.HogwartsFloatDmaGpuCopy = hogwarts;', 'GraphicsConfig.HogwartsDmaRegionUpload = hogwarts;',
               'GraphicsConfig.ProgressAwareForcedSyncpointWait = hogwarts;', 'MoltenVkPolicy.DeferInPassReadBarriers = hogwarts;',
               'MoltenVkPolicy.MeasureGpu = hogwarts;', 'MoltenVkPolicy.OrderEncoderTransitions = hogwarts;',
               'EncodingPolicy.IncrementalArrayDescriptors = hogwarts;', 'GpuContext.QueueSyncpointsBehindReports = hogwarts;',
               'EncodingPolicy.BindingSizedDescriptorScratch = true;'):
    check(candidate.count(policy) == 1, 'scope kept: ' + policy)
check(candidate.count('DetachPlayTimeWarmUps') == 1, 'one assignment only')
check(candidate.index('warmUpVulkan.DetachPlayTimeWarmUps = true;') < candidate.index('renderer = renderer.TryMakeThreaded(options.BackendThreading);'),
      'set on the Vulkan renderer before the threaded wrapper')
if FINAL_PREPARATION:
    from melonx_adapter_control import files_edited_later, later_sharing  # noqa: E402
    # Core 745: adapt_nifm_network_watch (one more text in the sessionRetention journal line) and adapt_paced_strict_syncs
    # (two Hogwarts assignments) edit Library.cs after this adapter. Each of their replacements is undone, once, from
    # the final preparation before the exact comparison; no other later adapter edits the file.
    later = later_sharing('adapt_playtime_warmup_all_titles')
    check(later == ['adapt_nifm_network_watch', 'adapt_paced_strict_syncs'] and files_edited_later('adapt_playtime_warmup_all_titles') == {L},
          'the later adapters editing Library.cs are the two reviewed ones: %s' % later)
    final_text = (FINAL_SOURCE / L).read_text(encoding='utf-8-sig')
    for name in reversed(later):
        module = __import__(name)
        pairs = module.LIBRARY_PAIRS if hasattr(module, 'LIBRARY_PAIRS') else module.FILE_PAIRS[L]
        for old, new in reversed(pairs):
            check(final_text.count(new) == 1, name + ': replacement present once in the final Library.cs')
            final_text = final_text.replace(new, old)
    for policy in ('GpuContext.PaceStrictHostSyncs = hogwarts;', 'SubmitPacing.Paced = hogwarts;'):
        check((FINAL_SOURCE / L).read_text(encoding='utf-8-sig').count(policy) == 1, 'later Hogwarts policy keeps its scope: ' + policy)
    check(final_text == candidate, 'the final preparation is the control plus the adapter and the two later adapters\' replacements')

# The policy-on proof, on this very Library.cs.
gate = json.loads((ROOT / EVIDENCE).read_text())
check(gate['result'] == 'passed' and gate['finalPreparationBound'] is True and gate['productionVulkanAssemblyBuilt'] is True and
      gate['productionLibraryAssemblyBuilt'] is True, 'the setprogram-warmup gate passed on a final preparation, production assemblies built')
check(gate['postimages'].get(L) == adapter.BASELINE[L], 'its Library.cs is this adapter\'s baseline')
on, off = gate['reports']['candidate'], gate['reports']['control']
graphics = ('mismatch', 'match', 'burstMatch', 'burstMismatch', 'cachedMatch')
check(all(on[s]['drawn'] is True and on[s]['renderThreadWarmUps'] == 0 for s in graphics) and
      on['compute']['dispatched'] is True and on['compute']['renderThreadWarmUps'] == 0,
      'policy on: every draw and dispatch is made, no warm-up on the render thread')
check(all(on[s].get('canBindWhileIncomplete') in (False, None) for s in on if isinstance(on[s], dict)),
      'policy on: a program never binds before its shader modules (no draw skipped)')
check(on['burstMatch']['mainCacheWarmUps'] == 0 and on['burstMismatch']['mainCacheWarmUps'] == 0, 'policy on: no warm-up on the main cache')
check(on['mismatchPolicyOff']['compilesInBackground'] is False and on['computePolicyOff']['compilesInBackground'] is False and
      on['mismatchPolicyOff']['setProgramMs'] > 10 * on['mismatch']['setProgramMs'],
      'policy off is the delivered path (SetProgram waits for the warm-up)')
timings = gate['timings']
check(timings['candidate']['burstMatch']['setProgramMs'] * 100 < timings['control']['burstMatch']['setProgramMs'] and
      timings['candidate']['burstMatch']['toFirstDrawMs'] < timings['control']['burstMatch']['toFirstDrawMs'],
      'a burst binds without waiting and reaches its first draw sooner')

inputs = ['build-utils/melonx/adapt_playtime_warmup_all_titles.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_playtime_warmup_all_titles_test.py', EVIDENCE, 'test/melonx_adapter_control.py']
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core737Preparation',
               postimages={L: sha(FINAL_SOURCE / L)} if FINAL_PREPARATION else {}, physicalDeviceTested=False,
               sourceBaseline=adapter.BASELINE,
               hostBurst=dict(control=timings['control']['burstMatch'], candidate=timings['candidate']['burstMatch']),
               deviceEvidence='IPA 727 Super Smash Bros. Ultimate pid 56632 (private journals): SetProgram up to 1 394 ms per 5 s '
                              'window with the policy off; Hogwarts Legacy sessions of the same build with it on: at most 17.5 ms',
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Scope change bound to the setprogram-warmup proof (host, timed compile doubles); the Metal compiler\'s '
                          'concurrency, the worker caches\' memory and SSBU frame times are read in the next device session.')
out = ROOT / 'dist/melonx/playtime-warmup-all-titles-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks)))
