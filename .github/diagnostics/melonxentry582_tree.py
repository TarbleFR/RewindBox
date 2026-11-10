"""Private582 delivery tree: the delivered 581 product tree with the MeloNX engine files of 6d8929d, e72895b and e55ca25 (LightningJit units end where another translation starts) and the Switch discovery fix of 32a0da6 and 63fdb7e.

581 shipped the 579 product (the 577 product: the 576 product with the
MeloNX engine of cfa5116/afd0d4b and the controller relay of d1f7b8d) with
the RPCS3 Core 581. 582 keeps all of it and replaces only the files of three
MeloNX engine commits of this session: the JIT decoder adaptation (a
translation unit ends where another translation already starts, unless a
loop around it or a short forward skip would be split; guest code is read a
page at a time; a unit ends before an unmapped page) and its probe and test.
None of them is compiled into the application. The engine they describe is
built and tested by its own engine run from e55ca25. Each file's version
before 6d8929d is the one the 581 tree carries (8cc2348), and no other
commit touched them since.

582 also carries 32a0da6 and 63fdb7e (this session): Switch discovery no
longer hashes whole games on the root isolate (the iOS main thread) or
while a game starts or runs; on iOS the bridge hashes a file with CryptoKit
on its own queue and stops at the next read when a launch begins, and an
index entry follows its file into a new app container. The product trees
differ from the delivered 581 ones in lib and packages only.

Earlier receipts stay bound to the delivered 581 tree, which at_581() gives
back: the 582 files at their 581 versions (or absent for the added test)
and this recipe removed. Runner checkout only: Git history is not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import rpcs3cell581_tree as previous

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
SOURCE577 = previous.SOURCE577
SOURCE_APP577 = previous.SOURCE_APP577
SOURCE579 = previous.SOURCE579
SOURCE581 = previous.SOURCE581
# The commit that recorded the delivered 581; the five 582 commits follow it.
RECORD581 = 'cc191e48209a3bc03d893f390ddbad6027ab64ed'
# The engine run's commit, and the three engine commits, newest first.
SOURCE582 = 'e55ca256a9347c4df8381bafc4702f80211fb492'
ENGINE_COMMITS = [SOURCE582, 'e72895b66342ae25cefafd279239fc3ba8e6bfc1', '6d8929d02f2e6f777a7332be335f098d7e71af2e']
SESSION = previous.previous.previous.SESSION
FIX582 = ['build-utils/melonx/adapt_jit_decoder.py',
          'test/melonx_jit_decoder/Program.cs',
          'test/melonx_jit_decoder_test.py']
# The engine's own input (hashed by the engine identity as an adaptation).
ENGINE582 = ['build-utils/melonx/adapt_jit_decoder.py']
# The Switch discovery fix, compiled into the application; its commits, newest first.
SOURCE_APP582 = '63fdb7ed716dc7b7e63df0370997ba7098f64a91'
SOURCE_DISCOVERY582 = '32a0da609ce66b5f08d23f2ecd9f8708d45bb98f'
APP_COMMITS = [SOURCE_APP582, SOURCE_DISCOVERY582]
APP582 = {'lib/services/melonx_library_scanner.dart': SOURCE_APP582,
          'lib/widgets/melonx_internal_playlist_actions.dart': SOURCE_DISCOVERY582,
          'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift': SOURCE_DISCOVERY582,
          'test/melonx_library_discovery_test.dart': SOURCE_APP582}
# delivery_contract_memo.py, which the 565 recipe owns, follows HEAD here too.
RECIPE = ['.github/diagnostics/melonxentry582_tree.py', '.github/diagnostics/melonxentry582_delivery.py',
          '.github/workflows/melonx-entry582-delivery.yml', 'build-utils/validate_rpcs3_582_ipa.py',
          'build-utils/validate_liquid_glass582_ipa.py', 'build-utils/validate_melonx_perf582_ipa.py',
          'build-utils/validate_rpcs3_library_files582_ipa.py', 'build-utils/validate_melonx_input582_ipa.py',
          'build-utils/validate_melonx_texture582_ipa.py', 'build-utils/validate_melonx_jit582_ipa.py',
          'build-utils/validate_melonx_switch582_ipa.py', 'build-utils/validate_melonx_warm582_ipa.py',
          'build-utils/validate_melonx_sync582_ipa.py', 'build-utils/validate_melonx_entry582_ipa.py',
          'build-utils/delivery-582-recipient.pem']
OWNED = previous.OWNED + FIX582 + sorted(APP582) + RECIPE
TREES = previous.TREES
CHANGED = FIX582 + sorted(APP582)


def exists(commit, path):
    return previous.exists(commit, path)


def source581(path):
    """Commit whose version of a file the delivered 581 tree carries; None
    when the file is absent from it."""
    source = previous.source_of(path)
    assert source is not None, (path, 'follows HEAD in the 581 tree')
    return source if exists(source, path) else None


# Files the 581 tree carries that 582 replaces; the discovery test is new.
REPLACED = sorted(p for p in CHANGED if source581(p))
ADDED = sorted(p for p in CHANGED if not source581(p))
assert REPLACED == ['build-utils/melonx/adapt_jit_decoder.py', 'lib/services/melonx_library_scanner.dart',
                    'lib/widgets/melonx_internal_playlist_actions.dart',
                    'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
                    'test/melonx_jit_decoder/Program.cs', 'test/melonx_jit_decoder_test.py'], REPLACED
assert ADDED == ['test/melonx_library_discovery_test.dart'], ADDED
assert all(source581(p) == SOURCE572 for p in FIX582)
assert set(ENGINE582) <= set(FIX582) and not set(FIX582) & set(APP582)
# The engine files ship nothing; the discovery fix ships Dart (lib) and Swift (packages).
assert not [p for p in FIX582 if p.split('/')[0] in TREES or p in TREES]
assert {p.split('/')[0] for p in APP582 if p.split('/')[0] in TREES} == {'lib', 'packages'}
assert not set(CHANGED) & (set(previous.CELL581) | set(previous.RECIPE))
assert not set(CHANGED) & set(previous.previous.previous.APP577)
assert previous.owned('build-utils/delivery_contract_memo.py')


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in FIX582 or path in APP582 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in FIX582:
        return SOURCE582
    if path in APP582:
        return APP582[path]
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


blob = previous.blob
index_with = previous.index_with


def at_581():
    """{path: commit, or None when absent}: every 582 file at its version in
    the delivered 581 tree, and this recipe removed. Applied to this index it
    gives back the 581 index exactly (docs follow HEAD in both)."""
    versions = {p: None for p in RECIPE}
    for p in CHANGED:
        versions[p] = source581(p)
    return versions


def parent_contract():
    """The 582 change is exactly this session's commits 6d8929d, e72895b and
    e55ca25 (engine) and 32a0da6 and 63fdb7e (Switch discovery), five commits
    in a row on cc191e4 (the 581 record): each file's version before them is
    the one the delivered 581 tree carries (absent for the added test), no
    other commit touched a 582 file since that version, and each file changed
    or was added."""
    chain = [RECORD581, SOURCE_DISCOVERY582, SOURCE_APP582] + ENGINE_COMMITS[::-1]
    for child, parent in zip(chain[1:], chain):
        assert git('rev-parse', child + '^') == parent, (child, parent)
    for commit in chain[1:]:
        assert SESSION in git('log', '-1', '--format=%B', commit), commit
    for p in CHANGED:
        before = previous.source_of(p)
        source = APP582.get(p, SOURCE582)
        commits = APP_COMMITS if p in APP582 else ENGINE_COMMITS
        parent = git('rev-parse', commits[-1] + '^')
        if p in ADDED:
            assert not exists(before, p) and not exists(parent, p), (p, before)
        else:
            assert exists(before, p) and blob(parent, p) == blob(before, p), (p, before)
        assert exists(source, p) and blob(source, p) != blob(before, p), (p, 'unchanged')
        touched = git('log', '--format=%H', before + '..' + source, '--', p).split()
        expected = [c for c in commits if git('diff', '--name-only', c + '^', c, '--', p)]
        assert expected and touched == expected, (p, touched, expected)
        assert expected[0] == source, (p, source)


def verify():
    """The index is the 581 product tree with the 582 files, each from its source.

    The index, not the working tree, is compared: later build steps generate and
    patch files in place but never stage them, so the check stays valid.
    """
    staged = [p for p in git('diff', '--cached', '--name-only', HOST_TREE).splitlines() if p]
    foreign = sorted(p for p in staged if not owned(p))
    assert not foreign, foreign
    p577 = previous.previous.previous
    for p in staged:
        source = source_of(p)
        if source is None:
            continue
        if not exists(source, p):
            # Deleted at its source (the 576 trace, the 504f9c0 Dart files): absent from the index.
            assert p in p577.DELETED577 + p577.previous.DELETED576 and not git('ls-files', '--', p), p
            continue
        assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), (p, source)
    for p in CHANGED:
        assert git('rev-parse', ':' + p) == git('rev-parse', source_of(p) + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(17):
        # 581, 579, 577, 576, 575, 573, 572, 567, 566, 565, 564, 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        p558 = chain
        chain = chain.previous
    p581 = previous
    p579 = p581.previous
    p577 = p579.previous
    p576 = p577.previous
    p575 = p576.previous
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
                    | set(p572.FIX572) | set(p573.CELL573) | set(p575.CELL575) | set(p576.FIX576)
                    | set(p576.APP576) | set(p577.FIX577) | set(p577.APP577) | set(p579.CELL579)
                    | set(p581.CELL581) | set(FIX582) | set(APP582)):
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
    trees581 = product_trees_581()
    # The Switch discovery fix (lib, packages) is the only product change: the engine is built by its own run.
    assert {p for p in TREES if trees[p] != trees581[p]} == {'lib', 'packages'}, (trees, trees581)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, source565=SOURCE565, source565App=SOURCE565APP,
                   source566=SOURCE566, source567=SOURCE567, source569=SOURCE569, source571=SOURCE571,
                   source572=SOURCE572, source573=SOURCE573, source575=SOURCE575, source576=SOURCE576,
                   source577=SOURCE577, sourceApp577=SOURCE_APP577, source579=SOURCE579, source581=SOURCE581,
                   source582=SOURCE582, engineCommits582=ENGINE_COMMITS, sourceApp582=SOURCE_APP582,
                   appCommits582=APP_COMMITS, app582=APP582, replaced=REPLACED, added=ADDED,
                   restored=restored, removed=sorted(removed), keptFiles=kept,
                   productTrees=trees, productTrees581=trees581,
                   reason='The 581 product tree with the MeloNX engine files of 6d8929d, e72895b and e55ca25 and the Switch discovery fix of 32a0da6 and 63fdb7e; each file from the commit that validated it; Git history unchanged.')
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


def tree_581():
    """The delivered 581 tree: the 582 files at their 581 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_581(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_581():
    tree = tree_581()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree582.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
