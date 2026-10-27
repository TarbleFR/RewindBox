"""Private565 delivery tree: the delivered 564 product tree with the RPCS3 Core 565 recipe of 07e416c and the God of War III frame limit of c5ba917.

564 shipped the 563 product (550 interface to 558 MeloNX files, the 562
MeloNX keyboard and L3/R3 host, the RPCS3 Core 563) with the MeloNX engine of
876a087. 565 keeps every shipped file of it but one and replaces the Core recipe:
the canonical delta, its manifest, the Core build script, the Core pin test
and workflow, and the 565 driver, test, harness and fixture. The Core they
describe (563 with the early submission kept on for DBZ, the no-op PUTLLC that
keeps reservations and the RSX idle park) is built and tested by its own Core
run from 07e416c. The 563 recipe, which the 564 tree keeps, pins five of these
files at dd65e86; the only commits that changed 565 files since are 36ff40f
(the Core) and 07e416c (its native harness). The one shipped
change is the God of War III profile of c5ba917 (frame limit Auto instead of
30) with its test; every other product file is the delivered 564 one, so only
the lib tree differs.

Earlier receipts stay bound to the delivered 564 tree, which at_564() gives
back: the 565 files at their 564 versions and this recipe removed
(documentation follows HEAD in both). Runner checkout only: Git history is
not changed.
"""
import argparse, fnmatch, json, os, subprocess, tempfile
from pathlib import Path
import melonxtexture564_tree as previous

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
# The Core commit built and tested by the 565 Core run. 36ff40f carries the
# Core sources; its own run stopped in the native preflight on a harness timing
# check, which 07e416c fixed without changing any production source.
SOURCE565 = '07e416c42bbdfaede2df1870ccd7fda91d97abce'
CORE_COMMITS = {'07e416c4': '[rpcs3-cell565-core]', '36ff40f6': '[rpcs3-cell565-core]'}
# The God of War III profile without the 30 fps limiter, and its test.
SOURCE565APP = 'c5ba9175040b5a464d401cf5a0ee9bfe274d6114'
FIX565 = ['lib/services/rpcs3_game_profile_service.dart', 'test/rpcs3_game_profile_service_test.dart']
CELL565 = ['.github/diagnostics/rpcs3cell565_core.py',
           '.github/workflows/rpcs3-cell565-core.yml',
           '.github/workflows/rpcs3-core.yml',
           'build-utils/build_rpcs3_embedded_core.sh',
           'build-utils/rpcs3/canonical-source.json',
           'build-utils/rpcs3/embedded-core.patch',
           'docs/evidence/rpcs3-cell565-host-linux.json',
           'docs/evidence/rpcs3-cell565-macos.json',
           'docs/rpcs3-cell565.md',
           'test/fixtures/rpcs3_cell565.diff',
           'test/native/rpcs3_spu_rsx565.inc',
           'test/neo_swap_core_pin_test.py',
           'test/rpcs3_cell565_test.py']
# The files the 564 tree pins at the 563 Core commit that 565 replaces.
REPLACED = sorted(p for p in CELL565 if previous.source_of(p) == SOURCE563)
# delivery_contract_memo.py follows HEAD: the delivery module computes its
# source contract once per job with it.
RECIPE = ['.github/diagnostics/rpcs3cell565_tree.py', '.github/diagnostics/rpcs3cell565_delivery.py',
          '.github/workflows/rpcs3-cell565-delivery.yml', 'build-utils/validate_rpcs3_565_ipa.py',
          'build-utils/validate_liquid_glass565_ipa.py', 'build-utils/validate_melonx_perf565_ipa.py',
          'build-utils/validate_rpcs3_library_files565_ipa.py', 'build-utils/validate_melonx_input565_ipa.py',
          'build-utils/validate_melonx_texture565_ipa.py', 'build-utils/delivery-565-recipient.pem',
          'build-utils/delivery_contract_memo.py']
OWNED = previous.OWNED + CELL565 + FIX565 + RECIPE
TREES = previous.TREES
assert REPLACED == sorted(['.github/workflows/rpcs3-core.yml', 'build-utils/build_rpcs3_embedded_core.sh',
                           'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
                           'test/neo_swap_core_pin_test.py']), REPLACED
# The Core recipe ships nothing; the profile is the only shipped 565 file.
assert not [p for p in CELL565 if p.split('/')[0] in TREES or p in TREES]
assert [p for p in FIX565 if p.split('/')[0] in TREES] == ['lib/services/rpcs3_game_profile_service.dart']


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env).strip()


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return path in CELL565 or path in FIX565 or matches(path, RECIPE) or previous.owned(path)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in CELL565:
        return None if path.startswith('docs/') else SOURCE565
    if path in FIX565:
        return SOURCE565APP
    if matches(path, RECIPE):
        return None
    return previous.source_of(path)


exists = previous.exists
blob = previous.blob
index_with = previous.index_with


def at_564():
    """{path: commit, or None when absent}: every 565 file (the profile
    included) at its version in the delivered 564 tree, and this recipe removed. Applied to this index it
    gives back the 564 index exactly (docs follow HEAD in both)."""
    versions = {p: None for p in RECIPE}
    for p in CELL565:
        source = previous.source_of(p)
        if source is None:
            versions[p] = git('rev-parse', 'HEAD') if exists('HEAD', p) else None
        else:
            versions[p] = source if exists(source, p) else None
    for p in FIX565:
        source = previous.source_of(p)
        versions[p] = source if source and exists(source, p) else None
    return versions


def parent_contract():
    """The 565 change is exactly the Core commits since 563: each replaced
    file's 564 version is the 563 Core one, the only commits that touched a 565
    file since dd65e86 are the two 565 Core commits (the last one validated by
    its own Core run), and each non-documentation file did change."""
    for p in CELL565:
        if p.startswith('docs/'):
            continue
        before = previous.source_of(p)
        assert before == SOURCE563 if p in REPLACED else not exists(before, p), (p, before)
        assert blob(SOURCE565, p) != (blob(before, p) if before else None), (p, 'unchanged')
    commits = git('log', '--format=%H', SOURCE563 + '..' + SOURCE565, '--',
                  *[p for p in CELL565 if not p.startswith('docs/')]).split()
    assert commits[0] == SOURCE565 and len(commits) == len(CORE_COMMITS), commits
    tags = {c[:8]: git('log', '-1', '--format=%s', c) for c in commits}
    assert set(tags) == set(CORE_COMMITS), tags
    for short, tag in CORE_COMMITS.items():
        assert tags[short].endswith(tag), (short, tags[short])
    # The profile change is exactly c5ba917: each file's version before it is
    # the one the 564 tree pins, and no other commit touched them since.
    parent = git('rev-parse', SOURCE565APP + '^')
    for p in FIX565:
        before = previous.source_of(p)
        assert blob(parent, p) == blob(before, p), (p, before)
        assert blob(SOURCE565APP, p) != blob(parent, p), (p, 'unchanged')
    assert git('log', '--format=%H', parent + '..' + SOURCE565APP, '--', *FIX565).split() == [SOURCE565APP]


def verify():
    """The index is the 564 product tree with the 565 files, each from its source.

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
        assert exists(source, p), (p, 'absent from', source)
        assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), (p, source)
    for p in CELL565:
        if source_of(p):
            assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE565 + ':' + p), p
    for p in FIX565:
        assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE565APP + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(7):
        # 564, 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        p558 = chain
        chain = chain.previous
    p563 = previous.previous
    p562 = p563.previous
    p561 = p562.previous
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(p558.UI550) | set(p558.CELL551) | set(p558.FIX552)
                    | set(p558.PARITY) | set(p558.FIX554) | set(p558.FIX557)
                    | set(p558.FIX558) | set(p561.previous.previous.CELL559) | set(p561.previous.CELL560)
                    | set(p561.CELL561) | set(p562.FIX562) | set(p563.CELL563) | set(previous.FIX564)
                    | set(CELL565) | set(FIX565)):
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
    trees564 = product_trees_564()
    # Only the lib tree changes, and only by the God of War III profile.
    assert {p for p in TREES if trees[p] != trees564[p]} == {'lib'}, (trees, trees564)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, source565=SOURCE565, source565App=SOURCE565APP, fix565=FIX565, replaced=REPLACED,
                   restored=restored, removed=sorted(removed), keptFiles=kept, productTrees=trees,
                   productTrees564=trees564,
                   reason='The 564 product tree with the RPCS3 Core 565 recipe of 07e416c and the God of War III profile of c5ba917; each file from the commit that validated it; Git history unchanged.')
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


def tree_564():
    """The delivered 564 tree: the 565 files at their 564 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_564(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_564():
    tree = tree_564()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree565.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
