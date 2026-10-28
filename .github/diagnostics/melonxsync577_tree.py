"""Private577 delivery tree: the delivered 576 product tree with the MeloNX engine files of cfa5116 (and the launch test fixture of afd0d4b) and the controller relay change of d1f7b8d.

576 shipped the 575 product (the 573 product with the RPCS3 Core 575; God of
War III without the 30 fps limiter, MeloNX keyboard and L3/R3) with the
MeloNX engine 301e0f8, the StikDebug fallback removal of 504f9c0 and the
interface fixes of 48b9865. 577 keeps all of it and replaces only the files of
the MeloNX engine commit cfa5116 (this session): four engine adaptations
(kernel wakeups of the condition variables and address arbiters, the GC's
memory-load threshold, a code arena the host can size per launch, a pipeline
cache kept per title), the temporary FFT boot trace removed, the adaptation
list, the engine workflow's push paths, and two native sources compiled into
the engine, never into the application (the launch preflight asks for a
1 GiB code arena for Hogwarts Legacy with its update); and the launch
preflight test's fixture of afd0d4b, without which the engine run stopped.
The engine they describe is built and tested by its own engine run from
afd0d4b. Every file's version before cfa5116 is the one the 576 tree carries
(absent for the three added adaptations), and no other commit touched them.

577 also carries d1f7b8d (this session): while a game owns a controller,
MeloNXInputRouter takes the pad's profile-wide handler, which relayed every
stick and trigger change to the menu on the main thread, and gives it back at
close. The product trees differ from the delivered 576 ones in native (the
engine sources) and packages only.

Earlier receipts stay bound to the delivered 576 tree, which at_576() gives
back: the 577 files at their 576 versions (or absent for the added ones, or
restored for the deleted trace) and this recipe removed.
Runner checkout only: Git history is not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import melonxwarm576_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE551 = previous.SOURCE551
SOURCE558 = previous.SOURCE558
SOURCE559 = previous.SOURCE559
SOURCE560 = previous.SOURCE560
SOURCE561 = previous.SOURCE561
SOURCE562 = previous.SOURCE562
SOURCE563 = previous.SOURCE563
SOURCE564 = previous.SOURCE564
SOURCE565 = previous.SOURCE565
SOURCE565APP = previous.SOURCE565APP
SOURCE566 = previous.SOURCE566
SOURCE567 = previous.SOURCE567
SOURCE569 = previous.SOURCE569
SOURCE571 = previous.SOURCE571
SOURCE572 = previous.SOURCE572
SOURCE573 = previous.SOURCE573
SOURCE575 = previous.SOURCE575
SOURCE576 = previous.SOURCE576
# The engine run's commit: the MeloNX engine of cfa5116 and the launch test
# fixture of afd0d4b, built and tested by its own engine run.
SOURCE577 = 'afd0d4b0a7d9dfc6a40a38cb4088a747b413b688'
ENGINE_COMMIT577 = 'cfa5116857de35fcc189874b8e3e5349419413df'
ENGINE_COMMITS = [SOURCE577, ENGINE_COMMIT577]
SESSION = previous.SESSION
FIX577 = ['.github/workflows/melonx-core.yml',
          'build-utils/melonx/adapt_fft_boot_trace.py',
          'build-utils/melonx/adapt_gc.py',
          'build-utils/melonx/adapt_jit_arena.py',
          'build-utils/melonx/adapt_kernel_sync.py',
          'build-utils/melonx/adapt_pipeline_cache.py',
          'build-utils/melonx/prepare_embedded.py',
          'native/melonx/EmbeddedLaunchPreflight.cs',
          'native/melonx/EmbeddedRuntime.cs',
          'test/melonx_launch_native_test.py']
# The temporary FFT boot trace of 576, deleted by cfa5116.
DELETED577 = ['build-utils/melonx/adapt_fft_boot_trace.py']
# The engine's own inputs (hashed by the engine identity as adaptations).
ENGINE577 = ['build-utils/melonx/adapt_gc.py', 'build-utils/melonx/adapt_jit_arena.py',
             'build-utils/melonx/adapt_kernel_sync.py', 'build-utils/melonx/adapt_pipeline_cache.py',
             'build-utils/melonx/prepare_embedded.py', 'native/melonx/EmbeddedLaunchPreflight.cs',
             'native/melonx/EmbeddedRuntime.cs']
# The shipped 577 engine files (lib, native, packages, assets, pubspec): native
# sources compiled into the engine, never into the application itself.
SHIPPED577 = sorted(p for p in FIX577 if p.startswith(('lib/', 'native/', 'packages/', 'assets/', 'pubspec.')))
# The controller relay change (d1f7b8d), compiled into the application.
SOURCE_APP577 = 'd1f7b8dd6384a860f0d257a89ac08eca4a482b81'
APP577 = {'packages/melonx_internal_bridge/ios/Classes/MeloNXInputRouter.swift': SOURCE_APP577}
# delivery_contract_memo.py, which the 565 recipe owns, follows HEAD here too.
RECIPE = ['.github/diagnostics/melonxsync577_tree.py', '.github/diagnostics/melonxsync577_delivery.py',
          '.github/workflows/melonx-sync577-delivery.yml', 'build-utils/validate_rpcs3_577_ipa.py',
          'build-utils/validate_liquid_glass577_ipa.py', 'build-utils/validate_melonx_perf577_ipa.py',
          'build-utils/validate_rpcs3_library_files577_ipa.py', 'build-utils/validate_melonx_input577_ipa.py',
          'build-utils/validate_melonx_texture577_ipa.py', 'build-utils/validate_melonx_jit577_ipa.py',
          'build-utils/validate_melonx_switch577_ipa.py', 'build-utils/validate_melonx_warm577_ipa.py',
          'build-utils/validate_melonx_sync577_ipa.py', 'build-utils/delivery-577-recipient.pem']
OWNED = previous.OWNED + FIX577 + sorted(APP577) + RECIPE
TREES = previous.TREES


def exists(commit, path):
    return previous.exists(commit, path)


def source576(path):
    """Commit whose version of a file the delivered 576 tree carries; None
    when the file is absent from it."""
    source = previous.source_of(path)
    assert source is not None, (path, 'follows HEAD in the 576 tree')
    return source if exists(source, path) else None


# Files the 576 tree carries that 577 replaces; the added adaptations are new.
REPLACED = sorted(p for p in FIX577 if p not in DELETED577 and source576(p))
ADDED = sorted(p for p in FIX577 if p not in DELETED577 and not source576(p))
assert REPLACED == ['.github/workflows/melonx-core.yml', 'build-utils/melonx/adapt_gc.py',
                    'build-utils/melonx/prepare_embedded.py', 'native/melonx/EmbeddedLaunchPreflight.cs',
                    'native/melonx/EmbeddedRuntime.cs', 'test/melonx_launch_native_test.py'], REPLACED
assert ADDED == ['build-utils/melonx/adapt_jit_arena.py', 'build-utils/melonx/adapt_kernel_sync.py',
                 'build-utils/melonx/adapt_pipeline_cache.py'], ADDED
assert all(source576(p) == SOURCE576 for p in DELETED577)
assert SHIPPED577 == ['native/melonx/EmbeddedLaunchPreflight.cs', 'native/melonx/EmbeddedRuntime.cs']
assert set(ENGINE577) <= set(FIX577) and not set(ENGINE577) & set(DELETED577)
assert not set(APP577) & set(FIX577)
assert not set(FIX577 + sorted(APP577)) & set(previous.APP576)
assert {p.split('/')[0] for p in SHIPPED577 + sorted(APP577) if p.split('/')[0] in TREES} == {'native', 'packages'}
assert previous.owned('build-utils/delivery_contract_memo.py')


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX577 or path in APP577 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe, which follows HEAD."""
    if path in FIX577:
        return SOURCE577
    if path in APP577:
        return APP577[path]
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


blob = previous.blob
index_with = previous.index_with


def at_576():
    """{path: commit, or None when absent}: every 577 file at its version in
    the delivered 576 tree, and this recipe removed. Applied to this index it
    gives back the 576 index exactly."""
    versions = {p: None for p in RECIPE}
    for p in FIX577 + sorted(APP577):
        versions[p] = source576(p)
    return versions


def parent_contract():
    """The 577 change is exactly this session's commits cfa5116 (engine),
    afd0d4b (its launch test fixture) and d1f7b8d (controller relay): each
    file's version before them is the one the delivered 576 tree carries
    (absent for the added adaptations), no other commit touched a 577 file
    since that version, and each file changed, was added or was deleted."""
    parent = git('rev-parse', ENGINE_COMMIT577 + '^')
    assert git('rev-parse', SOURCE_APP577 + '^') == ENGINE_COMMIT577
    assert git('rev-parse', SOURCE577 + '^') == SOURCE_APP577
    for p in FIX577 + sorted(APP577):
        before = previous.source_of(p)
        source = APP577.get(p, SOURCE577)
        if p in ADDED:
            assert not exists(before, p) and not exists(parent, p), (p, before)
            assert exists(source, p), p
        else:
            assert exists(before, p) and blob(parent, p) == blob(before, p), (p, before)
            if p in DELETED577:
                assert not exists(source, p), p
            else:
                assert exists(source, p) and blob(source, p) != blob(before, p), (p, 'unchanged')
        touched = git('log', '--format=%H', before + '..' + source, '--', p).split()
        expected = [c for c in (SOURCE577, SOURCE_APP577, ENGINE_COMMIT577)
                    if git('diff', '--name-only', c + '^', c, '--', p)]
        assert touched == expected and len(expected) == 1, (p, touched, expected)
    for commit in ENGINE_COMMITS + [SOURCE_APP577]:
        assert SESSION in git('log', '-1', '--format=%B', commit), commit


def verify():
    """The index is the 576 product tree with the 577 files, each from its source.

    The index, not the working tree, is compared: later build steps generate and
    patch files in place but never stage them, so the check stays valid.
    """
    staged = [p for p in git('diff', '--cached', '--name-only', HOST_TREE).splitlines() if p]
    foreign = sorted(p for p in staged if not owned(p))
    assert not foreign, foreign
    for p in staged:
        source = source_of(p)
        if source is None:
            continue
        if not exists(source, p):
            # Deleted at its source (the 576 trace, the 504f9c0 Dart files): absent from the index.
            assert p in DELETED577 + previous.DELETED576 and not git('ls-files', '--', p), p
            continue
        assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), (p, source)
    for p in FIX577:
        if p in DELETED577:
            assert not git('ls-files', '--', p), p
        else:
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE577 + ':' + p), p
    for p, source in APP577.items():
        assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(14):
        # 576, 575, 573, 572, 567, 566, 565, 564, 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        p558 = chain
        chain = chain.previous
    p575 = previous.previous
    p573 = p575.previous
    p572 = p573.previous
    p567 = p572.previous
    p566 = p567.previous
    p565 = p566.previous
    p564 = p565.previous
    p563 = p564.previous
    p562 = p563.previous
    p561 = p562.previous
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(p558.UI550) | set(p558.CELL551) | set(p558.FIX552)
                    | set(p558.PARITY) | set(p558.FIX554) | set(p558.FIX557)
                    | set(p558.FIX558) | set(p561.previous.previous.CELL559) | set(p561.previous.CELL560)
                    | set(p561.CELL561) | set(p562.FIX562) | set(p563.CELL563) | set(p564.FIX564)
                    | set(p565.CELL565) | set(p565.FIX565) | set(p566.FIX566) | set(p567.CELL567)
                    | set(p572.FIX572) | set(p573.CELL573) | set(p575.CELL575) | set(previous.FIX576)
                    | set(previous.APP576) | set(FIX577) | set(APP577)):
        source = source_of(p)
        if source is not None:
            plan.setdefault(source, []).append(p)
    restored, removed = {}, []
    for source, paths in plan.items():
        present = [p for p in paths if exists(source, p)]
        absent = [p for p in paths if not exists(source, p)]
        changed = [p for p in present if not exists(head, p) or git('rev-parse', head + ':' + p) != git('rev-parse', source + ':' + p)]
        if changed:
            subprocess.run(['git', 'restore', '--source=' + source, '--staged', '--worktree', '--', *changed], cwd=ROOT, check=True)
            restored[source] = changed
        for p in absent:
            if exists(head, p):
                subprocess.run(['git', 'rm', '-q', '--cached', '--', p], cwd=ROOT, check=True)
                (ROOT / p).unlink(missing_ok=True)
                removed.append(p)
    kept = verify()
    # Fresh checkout: the working tree must equal the pinned index exactly.
    assert not git('diff', '--name-only'), git('diff', '--name-only')
    assert not git('ls-files', '--others', '--exclude-standard', '--', 'lib', 'native', 'packages', 'assets', 'build-utils/rpcs3')
    trees = product_trees()
    trees576 = product_trees_576()
    # The engine sources (native) and the controller relay (packages) are the only product changes.
    assert {p for p in TREES if trees[p] != trees576[p]} == {'native', 'packages'}, (trees, trees576)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, source565=SOURCE565, source565App=SOURCE565APP,
                   source566=SOURCE566, source567=SOURCE567, source569=SOURCE569, source571=SOURCE571,
                   source572=SOURCE572, source573=SOURCE573, source575=SOURCE575, source576=SOURCE576,
                   source577=SOURCE577, engineCommits577=ENGINE_COMMITS, replaced=REPLACED, added=ADDED,
                   deleted577=DELETED577, shipped577=SHIPPED577, sourceApp577=SOURCE_APP577, app577=APP577,
                   restored=restored, removed=sorted(removed), keptFiles=kept,
                   productTrees=trees, productTrees576=trees576,
                   reason='The 576 product tree with the MeloNX engine files of cfa5116 and afd0d4b and the controller relay change of d1f7b8d; each file from the commit that validated it; Git history unchanged.')
    if report:
        out = ROOT / report
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return receipt


def product_trees():
    """Git object IDs of every shipped source tree in the pinned index."""
    tree = git('write-tree')
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


def tree_576():
    """The delivered 576 tree: the 577 files at their 576 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_576(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_576():
    tree = tree_576()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree577.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
