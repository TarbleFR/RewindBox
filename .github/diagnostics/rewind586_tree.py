"""Private586 delivery tree: the delivered 585 product tree with the MeloNX engine files of 6314127, d8cd5f6, ac16f1c, 6edcd57 and 75a13f7, the Cheats & Enhancements work of b451b10 to e017be1 and the RPCS3 Core 587 of a8a7ce1.

585 shipped the 583 product (the 582 product with the RPCS3 Core 583: the
581 product with the MeloNX engine of e55ca25 and the Switch discovery fix
of 32a0da6/63fdb7e) with the RPCS3 Core 585. 586 keeps all of it and adds:

- the files of five MeloNX engine commits of this session:
  adapt_gpu_allocations.py (new: a buffer kept by the copy engine for
  partial copies, GPFIFO command words from the runtime's shared pool, large
  MemoryOwner arrays kept as spares outside the upstream pool for 3 s, a
  32 MiB render-thread span ring), adapt_shader_waits.py (new: a blocking
  wait for a new program's compile; the warm-up key of depth-only passes),
  adapt_deferred_flush.py (new: a texture write-back the GPU thread queued
  to the render thread is skipped when its guest memory was unmapped since),
  adapt_bindless.py (new: bindless texture handles read through SHFL, the
  manual textureGrad sequence, bind instead of reading 0; the host shader
  cache version changes),
  prepare_embedded.py (which applies and records them), adapt_jit_decoder.py
  (misaligned-unit guards) and the decoder probe and its test. None is
  compiled into the application; the engine they describe is built and
  tested by its own engine run from 75a13f7.
- the Cheats & Enhancements work of session 01JA5QgPNMf2RK6ptCEMpk2z: the
  page, its service, engine adapters and 12-language strings (lib), the
  bundled index (assets), the catalogues (native/enhancements; native/cheats
  after the 28 October withdrawal of the unlicensed 60 FPS programs), the
  cheat catalogue's refusal of withheld programs from old caches
  (packages/neo_cheat_catalog), the builders, the tests, the notices
  (NOTICE.md) and the withdrawal receipt the shipped tests and the unified
  cheats validator read. The rest of these commits' documentation follows
  HEAD (AGENTS.md) or stays at its 585 version.
- the unified cheats validator binding that receipt from build 586.
- lifecycle transitions and memory figures in the MeloNX session journal
  (host Swift, this session).
- the RPCS3 Core 587 recipe of a8a7ce1 (session 01BcZDeV9dViZteLEWQGkbHE:
  MoltenVK asynchronous submits with an encode barrier before every swapchain
  acquisition, the MetalFX handoff ordered, a boot canary), built and tested
  by its own Core run, in place of the Core 585 (the five Core recipe files
  the 585 tree pins at 2b01363 change with it), and the profile commit
  147af30 (God of War III asynchronous submits Automatic, Black Ops II
  relaxed SPU reservations). The Core documentation and the Mac evidence of
  its run follow HEAD.

Each file comes from the newest commit of its change that touched it, and
only those commits touched it since the version the 585 tree carries.
Earlier receipts stay bound to the delivered 585 tree, which at_585() gives
back: the 586 files at their 585 versions (the added ones absent) and this
recipe removed. Runner checkout only: Git history is not changed.
"""
import argparse, fnmatch, json, os, shutil, subprocess, tempfile
from pathlib import Path
import rpcs3cell585_tree as previous

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
SOURCE582 = previous.SOURCE582
SOURCE_APP582 = previous.SOURCE_APP582
SOURCE583 = previous.SOURCE583
SOURCE585 = previous.SOURCE585
SESSION = previous.previous.previous.SESSION
# The engine run's commit, and the three engine commits, newest first.
SOURCE586 = '75a13f7eda665b99c0ac96556e3956655379e668'
ENGINE_COMMITS = [SOURCE586, '6edcd57ea107e3bd150e067346ea0d494963ade2', 'ac16f1c5b84e850902ff120bf8cd7950584f4642', 'd8cd5f68996ef57c2e479b2eefebbda08c1e4ce9',
                  '6314127faf7c3da242d1ffa327f278526f8408d4']
FIX586 = ['build-utils/melonx/adapt_gpu_allocations.py',
          'build-utils/melonx/adapt_shader_waits.py',
          'build-utils/melonx/adapt_deferred_flush.py',
          'build-utils/melonx/adapt_bindless.py',
          'build-utils/melonx/adapt_jit_decoder.py',
          'build-utils/melonx/prepare_embedded.py',
          'test/melonx_jit_decoder/Program.cs',
          'test/melonx_jit_decoder_test.py']
# The engine's own inputs (hashed by the engine identity as adaptations).
ENGINE586 = ['build-utils/melonx/adapt_gpu_allocations.py', 'build-utils/melonx/adapt_shader_waits.py',
             'build-utils/melonx/adapt_deferred_flush.py', 'build-utils/melonx/adapt_bindless.py',
             'build-utils/melonx/adapt_jit_decoder.py',
             'build-utils/melonx/prepare_embedded.py']
# The Cheats & Enhancements commits, oldest first (two commits of the same session in between
# change documentation only); 68e28dd bundles the origin publication (v2) of the cheat index, 4a19415
# and e017be1 adapt its macOS and UIKit tests.
ENHANCE_SESSION = 'Claude-Session: https://claude.ai/code/session_01JA5QgPNMf2RK6ptCEMpk2z'
APP_COMMITS = ['b451b10256acd6ab7cd3c356a06f28b99a858003', '23a847d68665d2a6b6eebbe9fc714f5730d13f1f',
               '1c1d1f7f4b3fcf088a623d3cbf1014ea35b58811', 'cb59a78472a9ce5c5fc6925db7119649e76b3220',
               '1345bd3e96baba179b4045bbac89791923765b92', '3192f0f957fc20bb05cea71bd38bfc3cabff6d08',
               'c9b42115eea9419a572f6db04104aacade3130db', '68e28ddc7d26dd68fc65e54ba522533a827b03a2',
               '4a19415c63c1f917f3a42259bd5cb560e9fb082a', 'e017be1c332221e0291d785e5d9611e313cfc42e']
DOC_COMMITS = ['208274efa8f96509a4ec63cfae8d203a3fd8af58', 'd6cccb3c321eb0b6d09a784151a6bf3041d4d2dc']
# Documentation the shipped tests and the unified cheats validator read; NOTICE.md ships in the legal bundle.
KEPT_DOCS = ['docs/evidence/source-rights-withdrawal-fps478.json']
# The unified cheats validator binds that receipt and the origin publication (v2) from build 586 (this session).
VALIDATOR586 = {'build-utils/validate_unified_cheats_ipa.py': '8b099a6bc387665fc3425fb3ddc18a45c544a440'}
# Lifecycle transitions and memory in the MeloNX session journal (this session).
DIAG_SOURCE = 'd1ea146f281394ba25ab731361458132b2f72924'
DIAG586 = {'packages/melonx_internal_bridge/ios/Classes/MeloNXMetalSessionViewController.swift': DIAG_SOURCE,
           'packages/melonx_internal_bridge/ios/Classes/MeloNXPerfJournal.swift': DIAG_SOURCE}
# The RPCS3 Core 587 (session 01BcZDeV9dViZteLEWQGkbHE), built and tested by its own Core run, in place of
# the Core 585: the files of its Core commit, and the profile commit that follows it in the application.
RPCS3_SESSION = 'Claude-Session: https://claude.ai/code/session_01BcZDeV9dViZteLEWQGkbHE'
SOURCE587 = 'a8a7ce1072c189806f4ddf70552280b3e95a1e17'
CORE_COMMITS = {SOURCE587[:8]: '[rpcs3-cell587-core]'}
CELL587 = ['.github/diagnostics/rpcs3cell587_core.py', '.github/workflows/rpcs3-cell587-core.yml',
           '.github/workflows/rpcs3-core.yml', 'AGENTS.md', 'build-utils/build_rpcs3_embedded_core.sh',
           'build-utils/rpcs3/canonical-source.json', 'build-utils/rpcs3/embedded-core.patch',
           'build-utils/rpcs3/patch_moltenvk_exec_queue.py', 'docs/evidence/rpcs3-cell587-host-linux.json',
           'docs/rpcs3-cell587.md', 'test/fixtures/rpcs3_cell587.diff', 'test/native/rpcs3_cell587_mvk_exec_test.cpp',
           'test/native/rpcs3_cell587_mvk_gcd_test.cpp', 'test/neo_swap_core_pin_test.py', 'test/rpcs3_cell587_test.py']
# The Core files pinned at the Core commit; its documentation and the Mac evidence of its run follow HEAD.
CORE587 = [p for p in CELL587 if p != 'AGENTS.md' and not p.startswith('docs/')]
CORE_DOCS587 = [p for p in CELL587 if p.startswith('docs/')] + ['docs/evidence/rpcs3-cell587-macos.json']
# God of War III follows the Core on asynchronous submits; Black Ops II relaxes SPU reservations.
PROFILE_SOURCE = '147af30e5e9aa9e26ef7ef988b0aba699e8aafd7'
PROFILE587 = {'lib/services/rpcs3_game_profile_service.dart': PROFILE_SOURCE,
              'test/rpcs3_game_profile_service_test.dart': PROFILE_SOURCE}
# delivery_contract_memo.py, which the 565 recipe owns, follows HEAD here too.
RECIPE = ['.github/diagnostics/rewind586_tree.py', '.github/diagnostics/rewind586_delivery.py',
          '.github/workflows/rewind586-delivery.yml', 'build-utils/validate_rpcs3_586_ipa.py',
          'build-utils/validate_liquid_glass586_ipa.py', 'build-utils/validate_melonx_perf586_ipa.py',
          'build-utils/validate_rpcs3_library_files586_ipa.py', 'build-utils/validate_melonx_input586_ipa.py',
          'build-utils/validate_melonx_texture586_ipa.py', 'build-utils/validate_melonx_jit586_ipa.py',
          'build-utils/validate_melonx_switch586_ipa.py', 'build-utils/validate_melonx_warm586_ipa.py',
          'build-utils/validate_melonx_sync586_ipa.py', 'build-utils/validate_melonx_entry586_ipa.py',
          'build-utils/validate_melonx_alloc586_ipa.py', 'build-utils/validate_enhancements586_ipa.py',
          'build-utils/delivery-586-recipient.pem', '.github/diagnostics/rpcs3cell587_delivery_core.py']
TREES = previous.TREES


def git(*args, env=None, input=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, env=env, input=input).strip()


def documentation(path):
    return (path in ('AGENTS.md', 'ARCHITECTURE.md', 'README.md', 'CLAUDE.md')
            or (path.startswith('docs/') and path not in KEPT_DOCS))


def touched(commit):
    return git('diff', '--no-renames', '--name-only', commit + '^', commit).split('\n')


def app_files():
    """{path: newest Cheats & Enhancements commit that touched it}, documentation left out."""
    files = {}
    for commit in APP_COMMITS:
        for p in touched(commit):
            if p and not documentation(p):
                files[p] = commit
    return files


APP586 = app_files()
APP586.update(VALIDATOR586)
APP586.update(PROFILE587)
APP586.update(DIAG586)
CHANGED = FIX586 + sorted(APP586) + CORE587
OWNED = previous.OWNED + CHANGED + CORE_DOCS587 + RECIPE


def exists(commit, path):
    return previous.exists(commit, path)


def source585(path):
    """Commit whose version of a file the delivered 585 tree carries; None
    when the file is absent from it."""
    source = previous.source_of(path)
    assert source is not None, (path, 'follows HEAD in the 585 tree')
    return source if exists(source, path) else None


# Files the 585 tree carries that 586 replaces or removes; the others are new.
REPLACED = sorted(p for p in CHANGED if source585(p))
ADDED = sorted(p for p in CHANGED if not source585(p))
# Files the Cheats & Enhancements change removes: the 14 cheat packs the 60 FPS withdrawal replaced
# (new packs, new names) and the snapshot of a withheld source.
DELETED586 = sorted(p for p, source in APP586.items() if not exists(source, p))
assert len(DELETED586) == 15 and DELETED586[-1] == 'tools/cheats/snapshots/nds-fps-478.json', DELETED586
assert all(p.startswith('native/cheats/catalogue/packs/pack-') for p in DELETED586[:-1]), DELETED586
assert set(DELETED586) <= set(REPLACED)
assert [p for p in FIX586 if p in ADDED] == ['build-utils/melonx/adapt_gpu_allocations.py',
                                             'build-utils/melonx/adapt_shader_waits.py',
                                             'build-utils/melonx/adapt_deferred_flush.py',
                                             'build-utils/melonx/adapt_bindless.py']
assert set(ENGINE586) <= set(FIX586) and not set(FIX586) & set(APP586)
# The engine files ship nothing; the Cheats & Enhancements work ships Dart, assets, catalogues and Objective-C.
assert not [p for p in FIX586 if p.split('/')[0] in TREES or p in TREES]
SHIPPED = sorted({p.split('/')[0] for p in APP586 if p.split('/')[0] in TREES or p in TREES})
assert SHIPPED == ['assets', 'lib', 'native', 'packages'], SHIPPED
assert 'NOTICE.md' in APP586 and set(KEPT_DOCS) <= set(APP586)
# The Core recipe files the 585 tree pins at the 585 Core commit change with the Core; the Core ships nothing.
REPLACED_CORE = sorted(set(CORE587) & set(previous.CELL585))
assert REPLACED_CORE == sorted(p for p in CORE587 if source585(p)) == sorted(
    ['.github/workflows/rpcs3-core.yml', 'build-utils/build_rpcs3_embedded_core.sh', 'build-utils/rpcs3/canonical-source.json',
     'build-utils/rpcs3/embedded-core.patch', 'test/neo_swap_core_pin_test.py']), REPLACED_CORE
assert not [p for p in CORE587 if p.split('/')[0] in TREES or p in TREES]
assert not (set(CHANGED) - set(CORE587)) & (set(previous.CELL585) | set(previous.RECIPE))
assert not set(CORE587) & set(previous.RECIPE) and not set(CORE587) & set(APP586)
assert previous.owned('build-utils/delivery_contract_memo.py')


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def owned(path):
    return (path in FIX586 or path in APP586 or path in CORE587 or path in CORE_DOCS587 or matches(path, RECIPE)
            or previous.owned(path))


def source_of(path):
    """Commit whose version of a file this build carries; None for this
    build's own recipe and for documentation, which follow HEAD."""
    if path in FIX586:
        return SOURCE586
    if path in APP586:
        return APP586[path]
    if path in CORE587:
        return SOURCE587
    if path in CORE_DOCS587 or matches(path, RECIPE):
        return None
    return previous.source_of(path)


blob = previous.blob


def index_with(versions, index):
    """Writes into the scratch index [index] (a copy of the current one) the
    files of {path: commit or None (absent)}, in one update."""
    shutil.copy2(git('rev-parse', '--path-format=absolute', '--git-path', 'index'), index)
    env = dict(os.environ, GIT_INDEX_FILE=index)
    groups = {}
    for p, source in versions.items():
        groups.setdefault(source, []).append(p)
    lines = []
    for source, paths in sorted(groups.items(), key=lambda item: item[0] or ''):
        found = {}
        if source is not None:
            for start in range(0, len(paths), 200):
                for line in git('ls-tree', source, '--', *paths[start:start + 200]).splitlines():
                    meta, p = line.split('\t', 1)
                    found[p] = meta
        for p in paths:
            if p in found:
                mode, kind, sha = found[p].split()
                lines.append(f'{mode} {sha}\t{p}')
            else:
                lines.append(f'0 {"0" * 40}\t{p}')
    git('update-index', '--index-info', env=env, input='\n'.join(lines) + '\n')
    return env


def at_585():
    """{path: commit, or None when absent}: every 586 file at its version in
    the delivered 585 tree, and this recipe removed. Applied to this index it
    gives back the 585 index exactly (docs follow HEAD in both)."""
    versions = {p: None for p in RECIPE}
    for p in CHANGED:
        versions[p] = source585(p)
    # The Core 587 documentation the 585 tree does not carry.
    for p in CORE_DOCS587:
        assert not previous.owned(p) and not exists(previous.source_of(p), p), p
        versions[p] = None
    return versions


def parent_contract():
    """The 586 change is exactly this session's engine commits 6314127,
    d8cd5f6, ac16f1c, 6edcd57 and 75a13f7, the seven Cheats & Enhancements commits of session
    01JA5QgPNMf2RK6ptCEMpk2z, this session's validator commit 2a3f8d3, and the
    RPCS3 Core 587 commit a8a7ce1 and profile commit 147af30 of session
    01BcZDeV9dViZteLEWQGkbHE. Each engine commit touches engine files only;
    each Cheats & Enhancements commit leaves out documentation only; the Core
    commit is the only commit since the 585 Core (2b01363) that touched a Core
    587 file, replacing the five Core recipe files the 585 tree pins at
    2b01363 and adding the others. For every other 586 file, the version the
    585 tree carries is an ancestor of its source, no other commit touched
    it since that version, and it changed, was added or was removed."""
    for commit in ENGINE_COMMITS:
        assert SESSION in git('log', '-1', '--format=%B', commit), commit
        assert set(touched(commit)) <= set(FIX586), (commit, set(touched(commit)) - set(FIX586))
    for commit in APP_COMMITS + DOC_COMMITS:
        assert ENHANCE_SESSION in git('log', '-1', '--format=%B', commit), commit
    for commit in DOC_COMMITS:
        assert all(documentation(p) for p in touched(commit)), commit
    for commit in APP_COMMITS:
        assert [p for p in touched(commit) if p not in APP586] == [p for p in touched(commit) if documentation(p)], commit
    for p, commit in VALIDATOR586.items():
        assert SESSION in git('log', '-1', '--format=%B', commit) and touched(commit) == [p], commit
    assert SESSION in git('log', '-1', '--format=%B', DIAG_SOURCE) and set(touched(DIAG_SOURCE)) == set(DIAG586), DIAG_SOURCE
    first = git('rev-parse', ENGINE_COMMITS[-1] + '^')
    for p in FIX586:
        before = previous.source_of(p)
        if p in ADDED:
            assert not exists(before, p) and not exists(first, p), (p, before)
            since = git('log', '--format=%H', SOURCE586, '--', p).split()
        else:
            assert exists(before, p) and blob(first, p) == blob(before, p), (p, before)
            since = git('log', '--format=%H', before + '..' + SOURCE586, '--', p).split()
        assert exists(SOURCE586, p) and (p in ADDED or blob(SOURCE586, p) != blob(before, p)), (p, 'unchanged')
        expected = [c for c in ENGINE_COMMITS if git('diff', '--name-only', c + '^', c, '--', p)]
        assert expected and since == expected, (p, since, expected)
    assert RPCS3_SESSION in git('log', '-1', '--format=%B', SOURCE587), SOURCE587
    assert RPCS3_SESSION in git('log', '-1', '--format=%B', PROFILE_SOURCE), PROFILE_SOURCE
    assert set(touched(PROFILE_SOURCE)) == set(PROFILE587), touched(PROFILE_SOURCE)
    assert set(touched(SOURCE587)) == set(CELL587), set(touched(SOURCE587)) ^ set(CELL587)
    for p in CORE587:
        before = previous.source_of(p)
        assert before == SOURCE585 if p in REPLACED_CORE else not exists(before, p), (p, before)
        assert blob(SOURCE587, p) != (blob(before, p) if exists(before, p) else None), (p, 'unchanged')
    commits = git('log', '--format=%H', SOURCE585 + '..' + SOURCE587, '--', *CORE587).split()
    assert commits == [SOURCE587], commits
    for short, tag in CORE_COMMITS.items():
        assert git('log', '-1', '--format=%s', short).endswith(tag), short
    allowed = set(APP_COMMITS) | set(VALIDATOR586.values()) | {PROFILE_SOURCE, DIAG_SOURCE}
    for p, source in APP586.items():
        before = previous.source_of(p)
        assert before is not None, (p, 'follows HEAD in the 585 tree')
        subprocess.run(['git', 'merge-base', '--is-ancestor', before, source], cwd=ROOT, check=True)
        since = git('log', '--format=%H', before + '..' + source, '--', p).split()
        assert since and since[0] == source and set(since) <= allowed, (p, since)
        assert blob(source, p) != blob(before, p), (p, 'unchanged')


def verify():
    """The index is the 585 product tree with the 586 files, each from its source.

    The index, not the working tree, is compared: later build steps generate and
    patch files in place but never stage them, so the check stays valid.
    """
    staged = [p for p in git('diff', '--cached', '--name-only', HOST_TREE).splitlines() if p]
    foreign = sorted(p for p in staged if not owned(p))
    assert not foreign, foreign
    p577 = previous.previous.previous.previous.previous.previous
    for p in staged:
        source = source_of(p)
        if source is None:
            continue
        if not exists(source, p):
            # Deleted at its source (the 576 trace, the 504f9c0 Dart files, the withheld 60 FPS snapshot).
            assert p in p577.DELETED577 + p577.previous.DELETED576 + DELETED586 and not git('ls-files', '--', p), p
            continue
        assert git('rev-parse', ':' + p) == git('rev-parse', source + ':' + p), (p, source)
    for p in CHANGED:
        if p not in DELETED586:
            assert git('rev-parse', ':' + p) == git('rev-parse', source_of(p) + ':' + p), p
    return sorted(staged)


def pin(report):
    head = git('rev-parse', 'HEAD')
    parent_contract()
    chain = previous
    for _ in range(20):
        # 585, 583, 582, 581, 579, 577, 576, 575, 573, 572, 567, 566, 565, 564, 563, 562, 561, 560, 559 and 558, each against its own parent.
        chain.parent_contract()
        p558 = chain
        chain = chain.previous
    p585 = previous
    p583 = p585.previous
    p582 = p583.previous
    p581 = p582.previous
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
                    | set(p581.CELL581) | set(p582.FIX582) | set(p582.APP582) | set(p583.CELL583)
                    | set(p585.CELL585) | set(CHANGED)):
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
    trees585 = product_trees_585()
    # The Cheats & Enhancements work is the only product change: the engine is built by its own run.
    assert sorted(p for p in TREES if trees[p] != trees585[p]) == SHIPPED, (trees, trees585)
    receipt = dict(schemaVersion=1, head=head, hostTree=HOST_TREE, source551=SOURCE551, source558=SOURCE558,
                   source559=SOURCE559, source560=SOURCE560, source561=SOURCE561, source562=SOURCE562,
                   source563=SOURCE563, source564=SOURCE564, source565=SOURCE565, source565App=SOURCE565APP,
                   source566=SOURCE566, source567=SOURCE567, source569=SOURCE569, source571=SOURCE571,
                   source572=SOURCE572, source573=SOURCE573, source575=SOURCE575, source576=SOURCE576,
                   source577=SOURCE577, sourceApp577=SOURCE_APP577, source579=SOURCE579, source581=SOURCE581,
                   source582=SOURCE582, sourceApp582=SOURCE_APP582, source583=SOURCE583, source585=SOURCE585,
                   source586=SOURCE586, engineCommits586=ENGINE_COMMITS, appCommits586=APP_COMMITS,
                   source587=SOURCE587, core587=CORE587, replacedCore=REPLACED_CORE, profileSource587=PROFILE_SOURCE,
                   validator586=VALIDATOR586, app586=APP586, replaced=REPLACED, added=ADDED, deleted=DELETED586,
                   restored=restored, removed=sorted(removed), keptFiles=kept,
                   productTrees=trees, productTrees585=trees585,
                   reason='The 585 product tree with the MeloNX engine files of 6314127, d8cd5f6, ac16f1c, 6edcd57 and 75a13f7, the Cheats & Enhancements work of b451b10 to e017be1 and the RPCS3 Core 587 of a8a7ce1 with the profile of 147af30; each file from the commit that validated it; Git history unchanged.')
    if report:
        out = ROOT / report
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k not in ('keptFiles', 'restored', 'app586')}, indent=2))
    return receipt


def product_trees():
    """Git object IDs of every shipped source tree in the pinned index."""
    tree = git('write-tree')
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


def tree_585():
    """The delivered 585 tree: the 586 files at their 585 versions, computed in
    a scratch copy of the index, so the pinned index is untouched."""
    with tempfile.TemporaryDirectory() as scratch:
        env = index_with(at_585(), os.path.join(scratch, 'index'))
        return git('write-tree', env=env)


def product_trees_585():
    tree = tree_585()
    return {p: git('rev-parse', tree + ':' + p) for p in TREES}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--pin', action='store_true')
    p.add_argument('--report', default='build/delivery/host-tree586.json')
    a = p.parse_args()
    if a.pin:
        pin(a.report)
    else:
        print(json.dumps(verify(), indent=2))
