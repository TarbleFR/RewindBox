"""Private550 delivery tree: the validated 549 product tree with the interface of e12f1d4.

549 shipped the 546 delivery tree plus the RPCS3 547 Core files (08f2f7fa),
the 548 Liquid Glass interface (5a9f1502) and the MeloNX threading/FPS files
(c605eafd). 550 keeps all of that and replaces only the interface files with
their e12f1d4 versions (one-line header, NeoStation style, live preview,
floating side menu, new options). Every file is taken from the commit that
validated it, so RPCS3 or MeloNX work committed later never enters this
build; every other path is the 546 delivery tree's. Runner checkout only:
Git history is not changed.
"""
import argparse, fnmatch, json, subprocess
from pathlib import Path
import melonxthreading549_tree as previous

ROOT = Path(__file__).resolve().parents[2]
HOST_TREE = previous.HOST_TREE
SOURCE547 = previous.SOURCE547
SOURCE548 = previous.SOURCE548
SOURCE549 = 'c605eafdea4064b13cc316524c851ef2c75257c2'
SOURCE_UI = 'e12f1d4feaccd3cfbe8ed4b6b27352d136184ceb'
LOCAL = 'docs/evidence/liquid-glass-ui550-local.json'
RECIPE = ['.github/diagnostics/liquidglass550_*.py', '.github/workflows/liquid-glass-ui550-*.yml',
          'build-utils/validate_liquid_glass550_ipa.py', 'build-utils/validate_melonx_threading550_ipa.py',
          'build-utils/delivery-550-recipient.pem', LOCAL, 'docs/liquid-glass-ui.md']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def interface():
    """The interface files this build ships at their e12f1d4 versions: the
    548 interface plus every file e12f1d4 changed, as hashed by the receipt."""
    inputs = set(json.loads((ROOT / LOCAL).read_text())['interface']['inputs'])
    assert set(previous.GLASS) - set(previous.glass.RECIPE) <= inputs, 'the 548 interface must stay covered'
    return inputs


UI = sorted(interface()) if (ROOT / LOCAL).exists() else []
OWNED = previous.OWNED + UI + RECIPE


def owned(path):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in OWNED)


# Recipe modules this build imports, taken from the delivery that validated
# them so later edits for other builds cannot change this one.
RECIPE549 = ['.github/diagnostics/melonxthreading549_*.py', '.github/workflows/melonx-threading549-*.yml',
             'build-utils/validate_melonx_threading549_ipa.py', 'build-utils/validate_liquid_glass549_ipa.py',
             'build-utils/delivery-549-recipient.pem', 'test/melonx_threading549_test.dart',
             'docs/evidence/melonx-threading549-*.json']
RECIPE548 = ['.github/diagnostics/liquidglass_ui_delivery.py', 'build-utils/validate_liquid_glass_ipa.py',
             'docs/evidence/liquid-glass-ui-local.json', '.github/workflows/liquid-glass-ui-delivery.yml',
             'build-utils/delivery-548-recipient.pem']


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in UI:
        return SOURCE_UI
    if matches(path, RECIPE):
        return None
    if path in previous.MELONX549 or matches(path, RECIPE549):
        return None if path == 'docs/melonx-persona-performance-2026-10-25.md' else SOURCE549
    if previous.previous.owned(path):
        return None if path.startswith(('AGENTS.md', 'docs/')) else SOURCE547
    if matches(path, RECIPE548):
        return SOURCE548
    if path in previous.GLASS:
        return None if path.startswith('docs/') or path.endswith('liquid-glass-ui-checks.yml') else SOURCE548
    if owned(path):
        return None
    return HOST_TREE


def exists(commit, path):
    return bool(git('ls-tree', commit, '--', path))


def verify():
    """The index is the 546 delivery tree plus owned paths, each from its source.

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
        if exists(source, p):
            assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), (p, source)
        else:
            assert False, (p, 'absent from', source)
    for p in UI:
        assert git('rev-parse', ':' + p) == git('rev-parse', SOURCE_UI + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    committed = {p for p in git('diff', '--name-only', HOST_TREE, head).splitlines() if p}
    plan = {}
    for p in sorted(committed | set(UI)):
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
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source547=SOURCE547, source548=SOURCE548,
                   source549=SOURCE549, sourceInterface=SOURCE_UI, restored=restored, removed=sorted(removed),
                   keptFiles=kept, productTrees=product_trees(),
                   reason='The 549 product tree with the e12f1d4 interface; each file from the commit that validated it; Git history unchanged.')
    if report:
        out = ROOT / report
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return receipt


def product_trees():
    """Git object IDs of every shipped source tree in the pinned index."""
    tree = git('write-tree')
    return {p: git('rev-parse', tree + ':' + p) for p in ['lib', 'native', 'packages', 'assets', 'pubspec.yaml', 'pubspec.lock']}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree550.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
