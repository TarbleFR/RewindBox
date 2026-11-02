"""The standard private IPA delivery recipe (AGENTS.md "Same recipe for every build").

Every private IPA is produced by this script and .github/workflows/standard-delivery.yml from the
last verified delivered IPA, adding only what the build's manifest build-utils/delivery/<N>.json
declares:

- replaced components are authenticated from their own producer route (rpcs3_core_component.py,
  melonx_reads_core_component.py), retained components keep their authenticated identity
  (retained_components.py), with every pin in the manifest or in the component's pin file;
- a test group reruns only when the manifest says fresh; otherwise its pinned evidence is
  authenticated and labelled reused; the delivery contract always reruns;
- a failed delivery is retried by changing only the recipe and reusing its successful test jobs.

Effective tree. The branch may carry concurrent product work that is not part of the build. The
local freeze replays base..HEAD commit by commit from the base tree and keeps exactly the product
changes of the reviewed commits (a reviewed commit must start from the bytes already in the
effective tree, so nothing unreviewed is absorbed); source-only commits are deferred. CI restores
that tree first in every job (operation materialize) and recomputes its digest; nothing may
check out again afterwards. Recipe paths (RECIPE_* below) are not product: they may change after
the freeze, except the recipe-pattern files the application embeds, which the freeze binds.

Local operations (never in CI): freeze, contract, trigger-paths, record.
CI operations: materialize, source-contract, baseline, contract, tests, await-tests and the
application steps (donor, RPCS3, Dolphin/ARMSX2, libretro, MeloNX, embed, structure, seal,
validate, diff-check, republish).
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import fnmatch
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for _part in ('.github/diagnostics', 'build-utils', 'build-utils/melonx'):
    if str(ROOT / _part) not in sys.path:
        sys.path.insert(0, str(ROOT / _part))

REPOSITORY = 'TarbleFR/RewindBox'
BRANCH = 'Claude'
WORKFLOW = '.github/workflows/standard-delivery.yml'
MANIFESTS = 'build-utils/delivery'
OUT = ROOT / 'build/delivery'
COMPONENTS = ROOT / 'build/standard-components'
VALIDATION = ROOT / 'build/validation'
CONTRACT_DIR = ROOT / 'build/standard-delivery/contract'
CONTRACT_TEST = ('python3', '-B', 'test/standard_delivery_contract_test.py')
IDENTITY = 'RewindBox-build-identity.json'
APP_ROOT = 'Payload/NeoStation.app/'
TRIGGER = re.compile(r'\[ipa-delivery:(\d{3,4})\]')
TRIGGER_MARKER = '[ipa-delivery:'
SKIP_TOKENS = ('[skip ci]', '[ci skip]', '[no ci]', '[skip actions]', '[actions skip]', 'skip-checks:true',
               'skip-checks: true')
TEST_GROUPS = ('flutter', 'native')
JOB_NAMES = ('preflight', 'flutter', 'native', 'republish', 'application')
MATERIALIZE_STEP = 'Materialize the frozen effective product tree'
REQUIRED_STEPS = {
    'preflight': {MATERIALIZE_STEP, 'Run the delivery contract', 'Preserve the delivery contract log'},
    'flutter': {MATERIALIZE_STEP, 'Run source contracts and Flutter behavior', 'Preserve actual command results'},
    'native': {MATERIALIZE_STEP, 'Run actual Xcode16.4 tests and host compilation', 'Preserve actual command results'},
}
APP = 'Frameworks/App.framework/App'
RUNNER = 'Runner'
# Recipe paths: read by the recipe, never compiled into the IPA. Every other path is product.
RECIPE_PREFIXES = ('.github/', 'docs/', '.claude/', 'build-utils/delivery/')
RECIPE_FILES = ('build-utils/rpcs3/core-pin.json', 'build-utils/melonx/reads-core-pin.json',
                'test/standard_delivery_contract_test.py', 'build-utils/verify_downloaded_delivery.py')
RECIPE_GLOBS = ('build-utils/delivery-*-recipient.pem',)
RECIPE_DEFINITION = dict(prefixes=list(RECIPE_PREFIXES), files=list(RECIPE_FILES), globs=list(RECIPE_GLOBS),
                         rootMarkdown=True)
# Recipe-pattern files whose bytes reach the IPA or its delivery (legal bundle, source notices, delivery
# notes): bound by the freeze although they are recipe paths. The contract test checks that this list
# covers every file embed_legal_bundle.py and collect_build_source_evidence.py read there.
EMBEDDED_RECIPE_FILES = (
    'LICENSE.md', 'NOTICE.md', 'docs/LEGAL_AND_CREDITS.md', 'docs/CHEAT_CATALOG_SOURCES.md',
    'docs/OVERLAY_SOURCES_AND_CREDITS.md', 'docs/HD_TEXTURE_CATALOG_SOURCES.md',
    'docs/HD_TEXTURE_SOURCES_AND_CREDITS.md', 'docs/SOURCE_CODE_ACCESS.md', 'docs/PACKAGE_SOURCES_AND_LICENSES.md',
    'docs/ENGINE_CORRESPONDING_SOURCES.md', 'docs/PPSSPP_SOURCE_AND_LICENSE_AUDIT.md',
    'docs/evidence/package-sources-license-audit-2026-10-21.json',
    'docs/evidence/engine-source-license-audit-2026-10-21.json',
    'docs/evidence/ppsspp-source-license-audit-2026-10-21.json',
    'docs/evidence/modified-sources-since-0.0.8-2026-10-21.json',
    'docs/evidence/achievement-translation-declarations-2026-10-31.json',
    'docs/evidence/retro-achievements-session-declarations-2026-11-01.json',
    'docs/evidence/rpcs3-retroachievements-declarations-2026-11-02.json',
    'docs/retroarch-rollback-2026-10-08.md',
)
EMBEDDED_RECIPE_FOLDERS = ('docs/licenses/',)
# App extensions built from a package whose name differs from the image.
PLUGIN_IMAGES = {
    'melonx_jit_helper': 'PlugIns/MeloNXJITHelper.appex/MeloNXJITHelper',
    'rpcs3_jit_helper': 'PlugIns/RPCS3JITHelper.appex/RPCS3JITHelper',
    'dolphin_jit_helper': 'PlugIns/DolphinJITHelper.appex/DolphinJITHelper',
    'armsx2_jit_helper': 'PlugIns/ARMSX2JITHelper.appex/ARMSX2JITHelper',
}
COMPONENT_MODES = {'replace', 'retain', 'retain-archive', 'pinned-source', 'pinned-release'}
REPUBLISHED_KINDS = ('rpcs3-core', 'rpcs3-host-tests', 'melonx-core', 'dolphin', 'armsx2', 'libretro',
                     'melonx-dependencies')
HEX40 = re.compile(r'[0-9a-f]{40}')
HEX64 = re.compile(r'[0-9a-f]{64}')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def in_ci():
    return bool(os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS'))


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, default=str) + '\n')
    return value


def write_outputs(**values):
    target = os.environ.get('GITHUB_OUTPUT')
    if target:
        with open(target, 'a') as output:
            for key, value in values.items():
                print(f'{key}={value}', file=output)


def write_environment(**values):
    target = os.environ.get('GITHUB_ENV')
    if target:
        with open(target, 'a') as output:
            for key, value in values.items():
                print(f'{key}={value}', file=output)


def api(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPOSITORY}/' + endpoint], cwd=ROOT, timeout=120))


def api_text(endpoint):
    return subprocess.check_output(['gh', 'api', f'repos/{REPOSITORY}/' + endpoint], cwd=ROOT, timeout=300).decode(
        errors='replace')


def download_artifact(artifact, path):
    with open(path, 'wb') as output:
        subprocess.run(['gh', 'api', f'repos/{REPOSITORY}/actions/artifacts/{artifact}/zip'], stdout=output,
                       cwd=ROOT, check=True, timeout=600)


# --- Git -----------------------------------------------------------------------------------------------

class Repo:
    """Read-only git queries on one checkout (the repository or a synthetic test repository)."""

    def __init__(self, root=ROOT):
        self.root = Path(root)

    def run(self, *args, input=None, env=None, check=True):
        return subprocess.run(['git', *args], cwd=self.root, input=input, env=env, capture_output=True,
                              timeout=900, check=check)

    def text(self, *args, env=None):
        return self.run(*args, env=env).stdout.decode()

    def commit(self, ref):
        result = self.run('rev-parse', '--verify', '--quiet', ref + '^{commit}', check=False)
        require(result.returncode == 0, 'Unknown commit: ' + ref)
        return result.stdout.decode().strip()

    def tree_of(self, ref):
        return self.text('rev-parse', ref + '^{tree}').strip()

    def is_ancestor(self, ancestor, descendant):
        return self.run('merge-base', '--is-ancestor', ancestor, descendant, check=False).returncode == 0

    def merges(self, base, head):
        return self.text('rev-list', '--merges', f'{base}..{head}').split()

    def commits(self, base, head):
        return self.text('rev-list', '--reverse', '--topo-order', f'{base}..{head}').split()

    def subject(self, ref):
        return self.text('show', '-s', '--format=%s', ref).strip()

    def entries(self, ref):
        """{path: (mode, blob)} of a commit tree; submodules are refused."""
        result = {}
        for item in self.run('ls-tree', '-r', '-z', '--full-tree', ref).stdout.split(b'\0'):
            if not item:
                continue
            header, path = item.split(b'\t', 1)
            mode, kind, obj = header.decode().split()
            require(kind == 'blob', 'Unsupported tracked entry: ' + path.decode())
            result[path.decode()] = (mode, obj)
        return result

    def changes(self, commit):
        """[(path, old, new)] of a non-merge commit, old/new = (mode, blob) or None."""
        parents = self.text('rev-list', '--parents', '-n', '1', commit).split()[1:]
        require(len(parents) <= 1, 'Merge commit in the delivery history: ' + commit)
        arguments = ['diff-tree', '-r', '-z', '--no-renames', '--no-commit-id', '--no-abbrev']
        arguments += [parents[0], commit] if parents else ['--root', commit]
        tokens = self.run(*arguments).stdout.split(b'\0')
        result, index = [], 0
        while index < len(tokens) - 1:
            meta = tokens[index].decode()
            if not meta.startswith(':'):
                index += 1
                continue
            path = tokens[index + 1].decode()
            index += 2
            old_mode, new_mode, old_obj, new_obj, _ = meta[1:].split()
            old = None if set(old_obj) == {'0'} else (old_mode, old_obj)
            new = None if set(new_obj) == {'0'} else (new_mode, new_obj)
            result.append((path, old, new))
        return result

    def show(self, ref, path):
        return self.run('show', f'{ref}:{path}').stdout

    def blob(self, obj):
        return self.run('cat-file', 'blob', obj).stdout

    def export(self, entries, target):
        """Write {path: (mode, blob)} into the empty directory `target` (modes and symlinks kept)."""
        by_object = {}
        for path, (mode, obj) in entries.items():
            safe_relative(path)
            by_object.setdefault(obj, []).append((path, mode))

        def write(obj, data):
            for path, mode in by_object[obj]:
                destination = Path(target) / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                if mode == '120000':
                    os.symlink(os.fsdecode(data), destination)
                else:
                    destination.write_bytes(data)
                    destination.chmod(0o755 if mode == '100755' else 0o644)
        self.blob_digests(by_object, sink=write)
        return len(entries)

    def blob_digests(self, objects, sink=None):
        """sha256 of the content of every blob, streamed through one cat-file process."""
        objects = sorted(set(objects))
        if not objects:
            return {}
        process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=self.root, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE)

        def feed():
            process.stdin.write(''.join(obj + '\n' for obj in objects).encode())
            process.stdin.close()
        writer = threading.Thread(target=feed)
        writer.start()
        result = {}
        for obj in objects:
            header = process.stdout.readline().decode().split()
            require(len(header) == 3 and header[0] == obj and header[1] == 'blob', 'Missing git object ' + obj)
            remaining, digest, chunks = int(header[2]), hashlib.sha256(), []
            while remaining:
                chunk = process.stdout.read(min(remaining, 1 << 20))
                require(chunk, 'Truncated git object ' + obj)
                digest.update(chunk)
                if sink:
                    chunks.append(chunk)
                remaining -= len(chunk)
            process.stdout.read(1)
            result[obj] = digest.hexdigest()
            if sink:
                sink(obj, b''.join(chunks))
        writer.join()
        process.stdout.close()
        require(process.wait() == 0, 'git cat-file failed')
        return result


# --- Recipe and product paths --------------------------------------------------------------------------

def is_recipe(path):
    if '/' not in path and path.endswith('.md'):
        return True
    if path.startswith(RECIPE_PREFIXES) or path in RECIPE_FILES:
        return True
    return any(fnmatch.fnmatchcase(path, pattern) and path.count('/') == pattern.count('/') for pattern in RECIPE_GLOBS)


def is_product(path):
    return not is_recipe(path)


def recipe_definition_sha():
    return sha(canonical(RECIPE_DEFINITION))


def is_embedded_recipe_input(path):
    return path in EMBEDDED_RECIPE_FILES or path.startswith(EMBEDDED_RECIPE_FOLDERS)


def safe_relative(path):
    pure = PurePosixPath(path)
    require(bool(path) and not pure.is_absolute() and '..' not in pure.parts and '\\' not in path and
            pure.parts[0] != '.git', 'Unsafe repository path: ' + path)
    return pure


# --- Manifest ------------------------------------------------------------------------------------------

def manifest_path(build):
    return f'{MANIFESTS}/{int(build)}.json'


def load_manifest(build, ref=None, repo=None):
    path = manifest_path(build)
    raw = (repo or Repo()).show(ref, path) if ref else (ROOT / path).read_bytes()
    value = json.loads(raw)
    require(value.get('schema') == 1 and value.get('build') == int(build), 'Wrong delivery manifest: ' + path)
    return value


def manifest_sha(build, root=ROOT):
    return sha_file(Path(root) / manifest_path(build))


def manifest_errors(value):
    """Schema problems of a draft or frozen manifest (empty list = valid)."""
    errors = []

    def check(condition, message):
        if not condition:
            errors.append(message)
    check(value.get('schema') == 1 and isinstance(value.get('build'), int), 'schema/build')
    check(value.get('status') in ('draft', 'frozen'), 'status must be draft or frozen')
    for key in ('base', 'components', 'product', 'images', 'tests', 'recipient', 'republish'):
        check(key in value, 'missing section ' + key)
    if errors:
        return errors
    base = value['base']
    for key in ('build', 'source', 'tree', 'run', 'attempt', 'workflow', 'jobs', 'receipt', 'identity', 'ipa'):
        check(key in base, 'base.' + key)
    check(HEX40.fullmatch(str(base.get('source'))) and HEX40.fullmatch(str(base.get('tree'))), 'base source/tree')
    check(set(base.get('jobs', {})) == {'preflight', 'application'}, 'base.jobs must name the preflight and application')
    for key, spec in value['components'].items():
        check(spec.get('mode') in COMPONENT_MODES, f'components.{key}.mode')
    for key in ('rpcs3', 'melonx'):
        check(value['components'].get(key, {}).get('mode') == 'replace' and value['components'][key].get('pin'),
              f'components.{key} must be a replaced component with a pin file')
    for key in ('dolphin', 'armsx2'):
        check(value['components'].get(key, {}).get('mode') == 'retain', f'components.{key} must be retained')
    for key in ('libretro', 'melonx-dependencies'):
        check(value['components'].get(key, {}).get('mode') == 'retain-archive', f'components.{key} must be a retained archive')
    product = value['product']
    check(isinstance(product.get('reviewedCommits'), list) and isinstance(product.get('sourceOnly'), list),
          'product.reviewedCommits and product.sourceOnly lists')
    for item in product.get('sourceOnly', []):
        check(isinstance(item.get('targetBuild'), int) and item.get('note'), 'sourceOnly entries need targetBuild and note')
    images = value['images']
    for key in ('mustChange', 'added', 'removed', 'retained', 'replaced'):
        check(key in images, 'images.' + key)
    for group in TEST_GROUPS:
        spec = value['tests'].get(group, {})
        check(spec.get('mode') in ('fresh', 'reuse'), f'tests.{group}.mode')
        if spec.get('mode') == 'reuse':
            check(set(spec.get('reuse', {})) >= {'source', 'run', 'attempt', 'job', 'artifact', 'artifactName',
                                                  'sha256', 'bytes', 'manifest'}, f'tests.{group}.reuse pins')
    check(set(value['recipient']) >= {'path', 'sha256'}, 'recipient path and sha256')
    check(set(value['republish']) <= set(REPUBLISHED_KINDS), 'republish lists unknown archives')
    if value['status'] == 'frozen':
        for key in ('freezeCommit', 'freezeTree', 'effective', 'restore', 'effectiveDigest', 'productFiles',
                    'recipeDefinitionSHA256', 'embeddedRecipeInputs', 'commits'):
            check(key in product, 'frozen product.' + key)
        for key in ('baseImages', 'retainedFingerprints', 'replacedFingerprints', 'derivedMustChange'):
            check(key in images, 'frozen images.' + key)
        for group in TEST_GROUPS:
            check(isinstance(value['tests'][group].get('commands'), list), f'frozen tests.{group}.commands')
        check(isinstance(value.get('frozen'), dict) and value['frozen'].get('inCI') is False, 'frozen record')
        for key in ('rpcs3', 'melonx'):
            check(HEX64.fullmatch(str(value['components'][key].get('pinSha256'))), f'frozen components.{key}.pinSha256')
    return errors


def ci_build():
    value = os.environ.get('BUILD_NUMBER', '')
    require(value.isdecimal(), 'BUILD_NUMBER must come from the preflight outputs')
    return int(value)


def ci_manifest():
    value = load_manifest(ci_build())
    require(value['status'] == 'frozen' and not manifest_errors(value), 'The delivery manifest is not frozen: ' +
            '; '.join(manifest_errors(value)))
    return value


def artifact_prefix(build, source):
    return f'RewindBox-Build{int(build)}-{source}'


def artifact_name(build, source, attempt, suffix):
    return f'{artifact_prefix(build, source)}-attempt{attempt}-{suffix}'


def subject_build(subject):
    """The build requested by `[ipa-delivery:NNN]` at the start of the commit subject (None when absent).

    The workflow gate is startsWith(head_commit.message, '[ipa-delivery:'), so a tag quoted in a body or
    later in a subject never starts a delivery."""
    found = TRIGGER.findall(subject)
    require(len(found) <= 1, 'The commit subject requests several builds: ' + subject)
    if not found:
        return None
    require(subject.startswith('[ipa-delivery:%s]' % found[0]),
            'The delivery tag must start the commit subject: ' + subject)
    return int(found[0])


def execution():
    source = os.environ['GITHUB_SHA']
    repo = Repo()
    require(HEX40.fullmatch(source) and source == repo.commit('HEAD'), 'Checkout differs from the workflow SHA')
    return dict(source=source, tree=repo.tree_of('HEAD'), run=int(os.environ['GITHUB_RUN_ID']),
                attempt=int(os.environ['GITHUB_RUN_ATTEMPT']))


# --- Base (last verified delivered IPA) -----------------------------------------------------------------

def read_worktree(path):
    target = ROOT / path
    return target.read_bytes() if target.is_file() else None


def verify_base(value, read=None):
    """The committed receipts of the base delivery, bound by digest (offline). Returns the base images."""
    read = read or read_worktree
    base = value['base']
    receipt_raw = read(base['receipt']['path'])
    require(receipt_raw is not None and sha(receipt_raw) == base['receipt']['sha256'], 'The base delivery receipt changed')
    receipt = json.loads(receipt_raw)
    run = receipt['execution']
    jobs = {job['name']: job['id'] for job in base['jobs'].values()}
    require(receipt['result'] == 'delivered-and-verified' and receipt['build'] == base['build'] and
            run['source'] == base['source'] and run['tree'] == base['tree'] and run['run'] == base['run'] and
            run['attempt'] == base['attempt'] and run['branch'] == BRANCH and run['runConclusion'] == 'success' and
            set(run['jobs']) == set(jobs) and
            all(run['jobs'][name]['id'] == job and run['jobs'][name]['conclusion'] == 'success'
                for name, job in jobs.items()), 'The base receipt differs from the pinned delivery run')
    require(all(receipt['ipa'][key] == base['ipa'][key] for key in ('name', 'producerName', 'bytes', 'sha256')),
            'The base receipt names another IPA')
    folder = PurePosixPath(base['receipt']['path']).parent
    proofs = receipt['proofFiles']
    require(len(proofs) == base['receipt']['proofFiles'], 'The base receipt proof inventory changed')
    for name, digest in proofs.items():
        safe_relative(name)
        raw = read(str(folder / name))
        require(raw is not None and sha(raw) == digest, 'Base proof file differs: ' + name)
    identity_raw = read(base['identity']['path'])
    require(identity_raw is not None and sha(identity_raw) == base['identity']['sha256'] ==
            proofs[PurePosixPath(base['identity']['path']).name], 'The base signed payload identity changed')
    identity = json.loads(identity_raw)
    require(len(identity['images']) == base['identity']['images'] and identity['ipaSha256'] == base['ipa']['sha256'] and
            identity['ipaBytes'] == base['ipa']['bytes'], 'The base image inventory differs from the delivered IPA')
    return identity['images']


def authenticate_base(value, get=None):
    get = get or api
    base = value['base']
    run = get(f"actions/runs/{base['run']}/attempts/{base['attempt']}")
    require(run['id'] == base['run'] and run['head_sha'] == base['source'] and run['conclusion'] == 'success' and
            run['run_attempt'] == base['attempt'] and run['head_branch'] == BRANCH and run['path'] == base['workflow'],
            'Wrong delivered base run')
    jobs = {}
    for key, job in base['jobs'].items():
        actual = get('actions/jobs/' + str(job['id']))
        require(actual['id'] == job['id'] and actual['name'] == job['name'] and actual['run_id'] == base['run'] and
                actual['head_sha'] == base['source'] and actual['run_attempt'] == base['attempt'] and
                actual['conclusion'] == 'success', 'Wrong delivered base job: ' + key)
        jobs[key] = dict(id=job['id'], name=job['name'], conclusion=actual['conclusion'])
    return dict(result='authenticated', build=base['build'], source=base['source'], run=base['run'],
                attempt=base['attempt'], workflow=base['workflow'], jobs=jobs, ipa=base['ipa'])


# --- Effective tree ------------------------------------------------------------------------------------

def replay(repo, base, head, reviewed, source_only):
    """Replay base..head from the base tree, applying only the reviewed commits' product changes."""
    require(not repo.merges(base, head), 'The history between the base and HEAD must be linear (no merge commit)')
    reviewed = {repo.commit(c) for c in reviewed}
    source_only = {repo.commit(c) for c in source_only}
    require(not reviewed & source_only, 'A commit is both reviewed and source-only')
    base_entries = {p: e for p, e in repo.entries(base).items() if is_product(p)}
    effective = dict(base_entries)
    commits = repo.commits(base, head)
    records, deferred, conflicts, unclassified = [], {}, [], []
    for commit in commits:
        changes = [change for change in repo.changes(commit) if is_product(change[0])]
        role = ('reviewed' if commit in reviewed else 'sourceOnly' if commit in source_only else
                'recipe' if not changes else 'unclassified')
        records.append(dict(commit=commit, subject=repo.subject(commit), role=role, productPaths=len(changes)))
        if role == 'reviewed':
            for path, old, new in changes:
                if effective.get(path) != old:
                    conflicts.append(dict(commit=commit, path=path,
                                          parent=list(old) if old else None,
                                          effective=list(effective[path]) if path in effective else None))
                elif new is None:
                    effective.pop(path, None)
                else:
                    effective[path] = new
        elif role == 'sourceOnly':
            deferred[commit] = sorted(path for path, _, _ in changes)
        elif role == 'unclassified':
            unclassified.append(dict(records[-1], paths=sorted(path for path, _, _ in changes)))
    present = set(commits)
    missing = sorted((reviewed | source_only) - present)
    return dict(base=base, head=head, baseEntries=base_entries, effective=effective, commits=records,
                deferred=deferred, conflicts=conflicts, unclassified=unclassified, missing=missing)


def delta(before, after):
    """{path: after-entry or None} for every path whose entry differs."""
    return {path: after.get(path) for path in sorted(set(before) | set(after)) if before.get(path) != after.get(path)}


def entry_record(entry, digests):
    return None if entry is None else dict(mode=entry[0], gitBlob=entry[1], sha256=digests[entry[1]])


def digest_records(records):
    digest = hashlib.sha256()
    for path, mode, value in sorted(records):
        digest.update(f'{path}\0{mode}\0{value}\n'.encode())
    return digest.hexdigest()


def effective_tree(repo, base, head, reviewed, source_only):
    """The replay plus everything the manifest records about the effective tree."""
    result = replay(repo, base, head, reviewed, source_only)
    effective = result['effective']
    head_entries = {p: e for p, e in repo.entries(head).items() if is_product(p)}
    changed = delta(result['baseEntries'], effective)
    restore = delta(head_entries, effective)
    # Every changed or restored entry is an entry of the effective tree, so one pass hashes them all.
    digests = repo.blob_digests(obj for _, obj in effective.values())
    result.update(
        headEntries=head_entries,
        effectiveRecords={path: entry_record(entry, digests) for path, entry in changed.items()},
        restoreRecords={path: entry_record(entry, digests) for path, entry in restore.items()},
        effectiveDigest=digest_records((path, mode, digests[obj]) for path, (mode, obj) in effective.items()),
        productFiles=len(effective))
    return result


class EffectiveReader:
    """Read files of an effective tree from git objects (local checks, synthetic tests)."""

    def __init__(self, repo, effective):
        self.repo, self.effective = repo, effective

    def read(self, path):
        entry = self.effective.get(path)
        return None if entry is None else self.repo.blob(entry[1])

    def exists(self, path):
        prefix = path.rstrip('/') + '/'
        return path in self.effective or any(p.startswith(prefix) for p in self.effective)

    def listing(self, prefix):
        return sorted(p for p in self.effective if p.startswith(prefix))


def worktree_record(root, path):
    target = Path(root) / path
    info = os.lstat(target)
    if stat.S_ISLNK(info.st_mode):
        return '120000', sha(os.fsencode(os.readlink(target)))
    require(stat.S_ISREG(info.st_mode), 'Not a regular product file: ' + path)
    return ('100755' if info.st_mode & stat.S_IXUSR else '100644'), sha_file(target)


def restore_paths(manifest):
    return manifest['product']['restore']


def expected_product_paths(repo, manifest, head):
    """Product paths of the effective tree, computed two ways that must agree."""
    product = manifest['product']
    base_paths = {p for p in repo.entries(manifest['base']['source']) if is_product(p)}
    from_base = (base_paths | {p for p, e in product['effective'].items() if e}) - \
        {p for p, e in product['effective'].items() if e is None}
    head_paths = {p for p in repo.entries(head) if is_product(p)}
    from_head = (head_paths | {p for p, e in product['restore'].items() if e}) - \
        {p for p, e in product['restore'].items() if e is None}
    require(from_base == from_head, 'The manifest effective and restore records disagree: ' +
            repr(sorted(from_base ^ from_head)[:20]))
    return from_base


def recipe_only_since(repo, freeze, head):
    require(repo.is_ancestor(freeze, head), 'The freeze commit is not an ancestor of this checkout')
    require(not repo.merges(freeze, head), 'Merge commit after the freeze')
    later = []
    for commit in repo.commits(freeze, head):
        product = [path for path, _, _ in repo.changes(commit) if is_product(path)]
        require(not product, f'Commit {commit} after the freeze changes product paths: {product[:10]}')
        later.append(commit)
    return later


def effective_index(repo, manifest, head='HEAD'):
    """A temporary index holding HEAD with the manifest restore applied (the effective tree)."""
    handle, name = tempfile.mkstemp(prefix='effective-index-')
    os.close(handle)
    os.unlink(name)
    environment = dict(os.environ, GIT_INDEX_FILE=name)
    repo.run('read-tree', head, env=environment)
    lines = []
    for path, entry in sorted(restore_paths(manifest).items()):
        lines.append(f'0 {"0" * 40}\t{path}' if entry is None else f"{entry['mode']} {entry['gitBlob']}\t{path}")
    if lines:
        repo.run('update-index', '--index-info', input=('\n'.join(lines) + '\n').encode(), env=environment)
    repo.run('update-index', '-q', '--refresh', env=environment, check=False)
    return name, environment


def verify_materialized(repo, manifest, head=None):
    """The working tree is exactly the effective tree: digest recomputed from the files themselves."""
    product = manifest['product']
    head = head or repo.commit('HEAD')
    later = recipe_only_since(repo, product['freezeCommit'], head)
    paths = expected_product_paths(repo, manifest, head)
    for path, entry in product['restore'].items():
        if entry is None:
            require(not os.path.lexists(repo.root / path), 'A path absent from the effective tree exists: ' + path)
    records = [(path, *worktree_record(repo.root, path)) for path in sorted(paths)]
    digest = digest_records(records)
    if digest != product['effectiveDigest']:
        index, environment = effective_index(repo, manifest, head)
        try:
            changed = repo.text('diff', '--name-only', env=environment).split()
        finally:
            Path(index).unlink(missing_ok=True)
        raise ValueError('The working tree is not the frozen effective tree; differing paths: ' + repr(changed[:30]))
    index, environment = effective_index(repo, manifest, head)
    try:
        changed = repo.text('diff', '--name-only', env=environment).split()
    finally:
        Path(index).unlink(missing_ok=True)
    require(not changed, 'Tracked files differ from the effective tree: ' + repr(changed[:30]))
    return dict(result='verified', effectiveDigest=digest, productFiles=len(records), restored=len(product['restore']),
                freezeCommit=product['freezeCommit'], laterRecipeOnlyCommits=later)


def materialize_tree(repo, manifest, head=None):
    """Restore the effective tree in the working tree from git objects, then verify it."""
    head = head or repo.commit('HEAD')
    product = manifest['product']
    recipe_only_since(repo, product['freezeCommit'], head)
    restore = product['restore']
    head_entries = repo.entries(head)
    for path, entry in sorted(restore.items()):
        safe_relative(path)
        require(is_product(path), 'A restore path is a recipe path: ' + path)
        if entry is None:
            require(path in head_entries, 'A restore deletion is not tracked at HEAD: ' + path)
    real_root = os.path.realpath(repo.root)

    def inside(path):
        # No parent folder of a restored path may be a symlink leading out of (or around) the tree.
        parent = os.path.realpath((repo.root / path).parent)
        require(parent == os.path.join(real_root, os.path.dirname(path)).rstrip(os.sep) and
                os.path.commonpath([real_root, parent]) == real_root, 'A restore path crosses a symlinked folder: ' + path)

    for path, entry in sorted(restore.items()):
        if os.path.lexists((repo.root / path).parent):
            inside(path)
        if entry is None and os.path.lexists(repo.root / path):
            (repo.root / path).unlink()
    for path, entry in sorted(restore.items()):
        if entry is None:
            continue
        data = repo.blob(entry['gitBlob'])
        require(sha(data) == entry['sha256'], 'Effective blob digest differs: ' + path)
        target = repo.root / path
        if os.path.lexists(target):
            require(not target.is_dir() or target.is_symlink(), 'A restore target is a directory: ' + path)
            target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        inside(path)
        if entry['mode'] == '120000':
            os.symlink(os.fsdecode(data), target)
        else:
            target.write_bytes(data)
            target.chmod(0o755 if entry['mode'] == '100755' else 0o644)
    return verify_materialized(repo, manifest, head)


# --- Test groups ---------------------------------------------------------------------------------------

def base_groups():
    """The delivered 610 groups (rewind610_checks.GROUPS) with the standard delivery contract."""
    import rewind610_checks as checks610
    groups = {}
    for group in TEST_GROUPS:
        commands = []
        for name, argv in checks610.GROUPS[group]:
            commands.append([name, list(CONTRACT_TEST) if name == 'delivery-contract-tests' else list(argv)])
        groups[group] = commands
    return groups


def expand_commands(group, spec, listing):
    """Frozen command list of one group: the base commands plus the manifest additions."""
    commands = [[name, list(argv)] for name, argv in base_groups()[group]]
    additions = spec.get('additions', {})
    tests = list(additions.get('flutterTests', []))
    for pattern in additions.get('flutterTestGlobs', []):
        tests += [p for p in listing(pattern.split('*')[0]) if fnmatch.fnmatchcase(p, pattern) and
                  p.count('/') == pattern.count('/') and p not in tests]
    for command in commands:
        if command[0] == 'flutter-analysis':
            command[1] += [path for path in additions.get('analyze', []) if path not in command[1]]
        elif command[0] == 'flutter-behavior':
            command[1] += [path for path in tests if path not in command[1]]
    names = {name for name, _ in commands}
    for name, argv in additions.get('commands', []):
        require(name not in names, 'Duplicated test command name: ' + name)
        names.add(name)
        commands.append([name, list(argv)])
    return commands


INPUT_ROOTS = ('lib/', 'test/', 'packages/', '.github/', 'build-utils/', 'tools/', 'native/', 'assets/')


def command_inputs(commands):
    """Repository paths named by group commands (inputs; outputs live under build/)."""
    paths = []
    for _, argv in commands:
        for token in argv[1:]:
            if token.startswith(INPUT_ROOTS) and token not in paths:
                paths.append(token)
    return paths


def missing_command_inputs(commands, exists):
    return [path for path in command_inputs(commands) if not exists(path)]


def recipe_reads(repo, ref, commands):
    """Recipe-path files the group commands actually read, besides the always-rerun contract test.

    Scripts named by the commands, the .github/diagnostics modules they import (transitively), and
    exact recipe paths quoted in the Python or Dart test sources the commands run.
    """
    entries = repo.entries(ref)
    contract = CONTRACT_TEST[-1]
    # Analysed folders are not executed; executed files are named one by one.
    queue = [path for path in command_inputs(commands) if path in entries and path != contract]
    seen, reads = set(), set()
    quoted = re.compile(r"""['"]([A-Za-z0-9_./-]+)['"]""")
    while queue:
        path = queue.pop()
        if path in seen or path not in entries or path == contract:
            continue
        seen.add(path)
        if is_recipe(path):
            reads.add(path)
        if path.endswith('.py'):
            try:
                tree = ast.parse(repo.show(ref, path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split('.')[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    names = [node.module.split('.')[0]]
                elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in entries and \
                        is_recipe(node.value):
                    queue.append(node.value)
                queue += [f'.github/diagnostics/{name}.py' for name in names]
        elif path.endswith('.dart'):
            for literal in quoted.findall(repo.show(ref, path).decode(errors='replace')):
                if literal in entries and is_recipe(literal):
                    queue.append(literal)
    return sorted(reads)


def recipe_read_digests(repo, ref, commands):
    entries = repo.entries(ref)
    return {path: entries[path][1] for path in recipe_reads(repo, ref, commands)}


def run_group(group):
    """Fresh test job: run every frozen command of the group on the materialized effective tree."""
    import rewind608_checks as checks608
    manifest = ci_manifest()
    require(group in TEST_GROUPS and manifest['tests'][group]['mode'] == 'fresh', 'This group is not fresh: ' + group)
    contract = verify_source()
    commands = manifest['tests'][group]['commands']
    directory = VALIDATION / group
    directory.mkdir(parents=True, exist_ok=True)
    repo = Repo()
    receipt = dict(schema=1, result='running', group=group, build=manifest['build'], execution=execution(),
                   effectiveDigest=manifest['product']['effectiveDigest'],
                   manifestSHA256=manifest_sha(manifest['build']),
                   recipeReads=recipe_read_digests(repo, 'HEAD', commands), sourceContract=contract['effective'],
                   commands=[], physicalDeviceTested=False, translationModelsDownloaded=False)
    if group == 'native':
        receipt['xcodeVersion'] = subprocess.check_output(['xcodebuild', '-version'], text=True).strip()
        receipt['swiftVersion'] = subprocess.check_output(['xcrun', 'swift', '--version'], text=True).strip()
        require(receipt['xcodeVersion'].startswith('Xcode 16.4\n'), 'Select Xcode16.4 before targeted tests')
    first_failure = 0
    for name, arguments in commands:
        start = time.monotonic()
        log = directory / (name + '.log')
        print('+ ' + ' '.join(arguments), flush=True)
        with log.open('wb') as output:
            try:
                code = subprocess.run(arguments, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                      timeout=1800).returncode
            except subprocess.TimeoutExpired:
                code = 124
        raw = log.read_bytes()
        print(raw.decode(errors='replace')[-18000:], flush=True)
        receipt['commands'].append(dict(name=name, argv=list(arguments), exitCode=code,
                                        seconds=round(time.monotonic() - start, 3), log=log.name, logSHA256=sha(raw)))
        if code:
            first_failure = first_failure or code
            receipt['result'] = 'failed'
        (directory / 'validation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if first_failure:
        raise SystemExit(first_failure)
    receipt['result'] = 'passed'
    if group == 'native':
        result = json.loads((ROOT / 'build/ra-session-validation/validation.json').read_bytes())
        receipt['centralSessionXCTest'] = checks608.validate_central_receipt(result)
    (directory / 'validation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def check_group_receipt(receipt, group, execution_value, manifest, directory, reads):
    import rewind608_checks as checks608
    require(receipt['result'] == 'passed' and receipt['group'] == group and receipt['build'] == manifest['build'] and
            receipt['execution'] == execution_value, 'Wrong test execution receipt: ' + group)
    require(receipt['effectiveDigest'] == manifest['product']['effectiveDigest'],
            'Tests ran on another effective product tree: ' + group)
    expected = manifest['tests'][group]['commands']
    require([[c['name'], c['argv']] for c in receipt['commands']] == expected,
            'A required test command was omitted, replaced or reordered: ' + group)
    require(all(c['exitCode'] == 0 for c in receipt['commands']), 'A required test command did not succeed: ' + group)
    for command in receipt['commands']:
        require(sha((directory / command['log']).read_bytes()) == command['logSHA256'], 'Test command log changed')
    require(receipt['recipeReads'] == reads, 'A recipe file the test group reads changed: ' + group)
    if group == 'native':
        require(receipt['xcodeVersion'].startswith('Xcode 16.4\n'), 'Wrong targeted native compiler')
        require('Apple Swift version 6.' in receipt['swiftVersion'], 'Translation was not compiled with Swift6')
        checks608.validate_central_receipt(receipt['centralSessionXCTest'])
    return receipt


def run_jobs(current, get=None):
    get = get or api
    value = get(f"actions/runs/{current['run']}/attempts/{current['attempt']}/jobs?per_page=100")
    require(value['total_count'] == len(value['jobs']) <= 100, 'Unexpected job pagination')
    jobs = {}
    for job in value['jobs']:
        require(job['name'] not in jobs, 'Duplicated job name in this run: ' + job['name'])
        jobs[job['name']] = job
    return jobs


def check_job(job, current, group):
    require(job['head_sha'] == current['source'] and job['run_id'] == current['run'] and
            job['run_attempt'] == current['attempt'] and job['status'] == 'completed' and
            job['conclusion'] == 'success', f'The {group} job of this run did not succeed')
    require(REQUIRED_STEPS[group] <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            f'The {group} job omitted a required step')


def upload_binding(log, name, artifact, digest, size):
    """The job log line upload-artifact prints for this exact artifact (job-level binding)."""
    require(f'SHA256 digest of uploaded artifact zip is {digest}' in log and
            f'Artifact {name} has been successfully uploaded! Final size is {size} bytes. Artifact ID is {artifact}' in log,
            'The job log does not show this artifact upload: ' + name)


def fetch_evidence(artifact, size, digest, folder):
    archive = COMPONENTS / f'{folder}.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.is_file() or sha_file(archive) != digest:
        temporary = archive.with_suffix('.part')
        download_artifact(artifact, temporary)
        require(temporary.stat().st_size == size and sha_file(temporary) == digest, 'Evidence archive bytes differ')
        temporary.replace(archive)
    from rewind606_engine import safe_members
    target = COMPONENTS / folder
    if target.exists():
        shutil.rmtree(target)
    with zipfile.ZipFile(archive) as z:
        safe_members(z)
        z.extractall(target)
    return target


def fresh_evidence(group, job, current, manifest, get=None, log=None):
    get = get or api
    check_job(job, current, group)
    name = artifact_name(manifest['build'], current['source'], current['attempt'], 'tests-' + group)
    found = get(f"actions/runs/{current['run']}/artifacts?name={name}&per_page=100")
    matching = [a for a in found['artifacts'] if a['name'] == name]
    require(len(matching) == 1, 'Missing or duplicated test evidence artifact: ' + name)
    artifact = matching[0]
    digest = (artifact.get('digest') or '').removeprefix('sha256:')
    require(HEX64.fullmatch(digest) and not artifact['expired'] and artifact['workflow_run']['id'] == current['run'] and
            artifact['workflow_run']['head_sha'] == current['source'], 'Wrong test evidence artifact binding: ' + name)
    text = log(job['id']) if log else job_log(job['id'])
    upload_binding(text, name, artifact['id'], digest, artifact['size_in_bytes'])
    directory = fetch_evidence(artifact['id'], artifact['size_in_bytes'], digest, 'tests-' + group)
    receipt = json.loads((directory / 'validation.json').read_bytes())
    reads = recipe_read_digests(Repo(), 'HEAD', manifest['tests'][group]['commands'])
    check_group_receipt(receipt, group, current, manifest, directory, reads)
    return dict(result='authenticated', evidenceMode='fresh', kind=group, execution=current, job=job['id'],
                artifact=artifact['id'], artifactName=name, archiveSHA256=digest,
                archiveBytes=artifact['size_in_bytes'], receipt=receipt, testsExecutedInThisRun=True)


def job_log(job_id, attempts=8):
    for attempt in range(attempts):
        try:
            text = api_text(f'actions/jobs/{job_id}/logs')
            if 'SHA256 digest of uploaded artifact zip is' in text:
                return text
        except subprocess.CalledProcessError:
            pass
        time.sleep(15 * (attempt + 1))
    raise ValueError(f'The log of job {job_id} is not available')


def reuse_guard(group, manifest, repo=None, get=None, head=None):
    """Reused test evidence: the 610 reuse guard, pinned by the manifest, both scopes read from commits."""
    get = get or api
    repo = repo or Repo()
    head = head or repo.commit('HEAD')
    pin = manifest['tests'][group]['reuse']
    require(HEX40.fullmatch(pin['source']) and repo.is_ancestor(pin['source'], head),
            'The reused test source is not an ancestor of this checkout: ' + group)
    tested_raw = repo.show(pin['source'], pin['manifest'])
    current_raw = repo.show(head, manifest_path(manifest['build']))
    tested, current = json.loads(tested_raw), json.loads(current_raw)
    require(tested['product']['effectiveDigest'] == current['product']['effectiveDigest'] ==
            manifest['product']['effectiveDigest'], 'The effective product tree differs from the tested one: ' + group)
    require(tested['tests'][group]['commands'] == current['tests'][group]['commands'] ==
            manifest['tests'][group]['commands'], 'The tested commands differ: ' + group)
    reads_tested = recipe_read_digests(repo, pin['source'], current['tests'][group]['commands'])
    reads_now = recipe_read_digests(repo, head, current['tests'][group]['commands'])
    require(reads_tested == reads_now, 'A recipe file the tests read changed since the tested run: ' +
            repr(sorted(k for k in set(reads_tested) | set(reads_now) if reads_tested.get(k) != reads_now.get(k))))
    run = get(f"actions/runs/{pin['run']}/attempts/{pin['attempt']}")
    require(run['id'] == pin['run'] and run['head_sha'] == pin['source'] and run['head_branch'] == BRANCH and
            run['path'] == WORKFLOW and run['run_attempt'] == pin['attempt'] and run['event'] == 'push',
            'Wrong reused test run: ' + group)
    job = get('actions/jobs/' + str(pin['job']))
    require(job['id'] == pin['job'] and job['name'] == group and job['head_sha'] == pin['source'] and
            job['run_id'] == pin['run'] and job['run_attempt'] == pin['attempt'] and job['status'] == 'completed' and
            job['conclusion'] == 'success', 'The reused test job did not succeed: ' + group)
    require(REQUIRED_STEPS[group] <= {s['name'] for s in job['steps'] if s['conclusion'] == 'success'},
            'The reused test job omitted a required step: ' + group)
    artifact = get('actions/artifacts/' + str(pin['artifact']))
    expected_name = artifact_name(manifest['build'], pin['source'], pin['attempt'], 'tests-' + group)
    require(pin['artifactName'] == expected_name and artifact['id'] == pin['artifact'] and
            artifact['name'] == expected_name and artifact['digest'] == 'sha256:' + pin['sha256'] and
            artifact['size_in_bytes'] == pin['bytes'] and not artifact['expired'] and
            artifact['workflow_run']['id'] == pin['run'] and artifact['workflow_run']['head_sha'] == pin['source'],
            'Wrong reused test artifact binding: ' + group)
    execution_value = dict(source=pin['source'], tree=repo.tree_of(pin['source']), run=pin['run'],
                           attempt=pin['attempt'])
    return dict(result='authenticated', evidenceMode='reused-identical-effective-tree', kind=group,
                execution=execution_value, job=pin['job'], artifact=pin['artifact'], artifactName=expected_name,
                archiveSHA256=pin['sha256'], archiveBytes=pin['bytes'], recipeReads=reads_now,
                equivalence=dict(testedManifestSHA256=sha(tested_raw), currentManifestSHA256=sha(current_raw),
                                 effectiveDigest=manifest['product']['effectiveDigest'], commandsIdentical=True))


def reused_evidence(group, manifest):
    value = reuse_guard(group, manifest)
    directory = fetch_evidence(value['artifact'], value['archiveBytes'], value['archiveSHA256'], 'tests-' + group)
    receipt = json.loads((directory / 'validation.json').read_bytes())
    check_group_receipt(receipt, group, value['execution'], manifest, directory, value['recipeReads'])
    return dict(value, receipt=receipt, testsExecutedInThisRun=False)


def contract_evidence(current, manifest, jobs, get=None):
    """The delivery contract of this run's preflight, authenticated by its uploaded log digest."""
    get = get or api
    job = jobs['preflight']
    check_job(job, current, 'preflight')
    artifact_id = int(os.environ['CONTRACT_ARTIFACT_ID'])
    digest = os.environ['CONTRACT_ARTIFACT_DIGEST'].removeprefix('sha256:')
    require(HEX64.fullmatch(digest), 'Missing contract upload digest')
    name = artifact_name(manifest['build'], current['source'], current['attempt'], 'contract')
    artifact = get('actions/artifacts/' + str(artifact_id))
    require(artifact['id'] == artifact_id and artifact['name'] == name and artifact['digest'] == 'sha256:' + digest and
            not artifact['expired'] and artifact['workflow_run']['id'] == current['run'] and
            artifact['workflow_run']['head_sha'] == current['source'], 'Wrong delivery contract artifact')
    directory = fetch_evidence(artifact_id, artifact['size_in_bytes'], digest, 'contract')
    record = json.loads((directory / 'contract.json').read_bytes())
    require(record['result'] == 'passed' and record['exitCode'] == 0 and record['argv'] == list(CONTRACT_TEST) and
            record['execution'] == current and record['build'] == manifest['build'] and
            record['effectiveDigest'] == manifest['product']['effectiveDigest'] and
            sha((directory / 'contract.log').read_bytes()) == record['logSHA256'], 'The delivery contract record differs')
    return dict(result='authenticated', evidenceMode='fresh', command=' '.join(CONTRACT_TEST), rerunInThisRun=True,
                job=job['id'], artifact=artifact_id, archiveSHA256=digest, logSHA256=record['logSHA256'],
                execution=current)


def tests_summary(result, manifest):
    executed = [group for group in TEST_GROUPS if manifest['tests'][group]['mode'] == 'fresh'] + ['delivery-contract']
    run = {group: dict(mode=result[group]['evidenceMode'], run=result[group]['execution']['run'],
                       attempt=result[group]['execution']['attempt'], job=result[group]['job'],
                       source=result[group]['execution']['source']) for group in TEST_GROUPS}
    run['delivery-contract'] = dict(mode='fresh', run=result['deliveryContract']['execution']['run'],
                                    attempt=result['deliveryContract']['execution']['attempt'],
                                    job=result['deliveryContract']['job'])
    return executed, run


def reauthenticate_tests(tests, manifest, get=None):
    """The saved test evidence still names successful jobs and unexpired artifacts with the same digests."""
    get = get or api
    current = execution()
    jobs = run_jobs(current, get)
    for group in TEST_GROUPS:
        value = tests[group]
        if value['evidenceMode'] == 'fresh':
            check_job(jobs[group], current, group)
            require(jobs[group]['id'] == value['job'], 'Fresh test evidence names another job: ' + group)
        else:
            guard = reuse_guard(group, manifest, get=get)
            require(all(value[key] == guard[key] for key in ('execution', 'job', 'artifact', 'archiveSHA256')),
                    'Reused test evidence changed: ' + group)
        artifact = get('actions/artifacts/' + str(value['artifact']))
        require(artifact['digest'] == 'sha256:' + value['archiveSHA256'] and not artifact['expired'],
                'Test evidence artifact changed or expired: ' + group)
    contract = tests['deliveryContract']
    check_job(jobs['preflight'], current, 'preflight')
    require(jobs['preflight']['id'] == contract['job'] and
            int(os.environ['CONTRACT_ARTIFACT_ID']) == contract['artifact'] and
            os.environ['CONTRACT_ARTIFACT_DIGEST'].removeprefix('sha256:') == contract['archiveSHA256'],
            'The delivery contract evidence changed')
    return True


def await_tests(poll=True):
    """Application job, right before embedding the test identity: wait for and authenticate the tests."""
    manifest = ci_manifest()
    current = execution()
    deadline = time.monotonic() + 60 * int(manifest['tests'].get('awaitMinutes', 75))
    modes = {group: manifest['tests'][group]['mode'] for group in TEST_GROUPS}
    while True:
        jobs = run_jobs(current)
        pending = []
        for group, mode in modes.items():
            job = jobs.get(group)
            if job is None or job['status'] != 'completed':
                pending.append(group)
                continue
            if mode == 'fresh':
                require(job['conclusion'] == 'success', f"The {group} test job ended with {job['conclusion']}")
            else:
                require(job['conclusion'] == 'skipped', f'Reused {group} evidence needs a skipped {group} job')
        if not pending:
            break
        require(poll and time.monotonic() < deadline, 'Timed out waiting for the test jobs: ' + ', '.join(pending))
        print('Waiting for test jobs: ' + ', '.join(pending), flush=True)
        time.sleep(30)
    result = {group: fresh_evidence(group, jobs[group], current, manifest) if mode == 'fresh' else
              reused_evidence(group, manifest) for group, mode in modes.items()}
    result['deliveryContract'] = contract_evidence(current, manifest, jobs)
    executed, run = tests_summary(result, manifest)
    return save('standard-tests.json', dict(result, testsExecutedInThisRun=executed, testsRun=run))


# --- Source contract (every CI job) --------------------------------------------------------------------

def recipient_check(manifest, environment=None):
    environment = os.environ if environment is None else environment
    value = environment.get('DELIVERY_RECIPIENT', '')
    require(value, 'DELIVERY_RECIPIENT must be set: delivery_cipher.py would silently encrypt to the 422 key')
    require(value == manifest['recipient']['path'], 'DELIVERY_RECIPIENT is not the manifest recipient: ' + value)
    raw = (ROOT / value).read_bytes()
    require(sha(raw) == manifest['recipient']['sha256'] and raw.startswith(b'-----BEGIN PUBLIC KEY-----'),
            'The delivery recipient public key differs from the manifest')
    return dict(path=value, sha256=sha(raw))


def retained_inputs(manifest, listing, read):
    """Inputs of every retained/pinned-source component, read from one tree."""
    import retained_components as retained
    result = {}
    for kind, spec in manifest['components'].items():
        if spec['mode'] in ('retain', 'retain-archive', 'pinned-source') and spec.get('inputs'):
            for path in retained.input_paths(kind, spec, listing):
                result[path] = read(path)
    return result


def retained_inputs_unchanged(manifest, repo, listing, read):
    """Retained components' inputs in the effective tree equal the base tree (no rebuild was needed)."""
    base = repo.entries(manifest['base']['source'])
    base_reader = EffectiveReader(repo, base)
    current = retained_inputs(manifest, listing, read)
    before = retained_inputs(manifest, base_reader.listing, base_reader.read)
    changed = sorted(path for path in set(current) | set(before)
                     if is_product(path) and current.get(path) != before.get(path))
    require(not changed, 'A retained component input changed since the base: ' + repr(changed[:20]))
    return len(current)


def worktree_listing(prefix):
    folder = ROOT / prefix
    if not folder.is_dir():
        return []
    return sorted(str(p.relative_to(ROOT)) for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)


def pins_check(manifest):
    import rpcs3_core_component as rpcs3
    import melonx_reads_core_component as melonx
    components = manifest['components']
    rpcs3_pin = rpcs3.load_pin(ROOT / components['rpcs3']['pin'])
    rpcs3.pinned(rpcs3_pin)
    require(sha_file(ROOT / components['rpcs3']['pin']) == components['rpcs3']['pinSha256'],
            'The RPCS3 Core pin changed after the freeze')
    melonx_pin = melonx.pin()
    require(components['melonx']['pin'] == melonx.PIN and
            sha_file(ROOT / components['melonx']['pin']) == components['melonx']['pinSha256'],
            'The MeloNX Core pin changed after the freeze')
    return dict(rpcs3=rpcs3_pin['producer']['core']['source'], melonx=melonx_pin['source'])


def source_contract():
    manifest = ci_manifest()
    repo = Repo()
    require(os.environ.get('GITHUB_REF_NAME', BRANCH) == BRANCH, 'Wrong delivery branch')
    head = repo.commit('HEAD')
    require(head == os.environ.get('GITHUB_SHA', head), 'Checkout differs from the triggering source')
    require(repo.text('write-tree').strip() == repo.tree_of('HEAD'), 'The index changed after checkout')
    base = manifest['base']
    require(repo.tree_of(base['source']) == base['tree'] and repo.is_ancestor(base['source'], head) and
            not repo.merges(base['source'], head), 'The base delivery source is not the linear ancestor of this run')
    require(manifest['product']['recipeDefinitionSHA256'] == recipe_definition_sha(),
            'The recipe path definition changed after the freeze')
    effective = verify_materialized(repo, manifest, head)
    images = verify_base(manifest)
    for path, digest in manifest['product']['embeddedRecipeInputs'].items():
        require(read_worktree(path) is not None and sha(read_worktree(path)) == digest,
                'An embedded recipe-pattern input changed after the freeze: ' + path)
    pins = pins_check(manifest)
    inputs = retained_inputs_unchanged(manifest, repo, worktree_listing, read_worktree)
    recipient = recipient_check(manifest)
    require(json.loads((ROOT / 'build-utils/armsx2/source.json').read_bytes())['abi_version'] == 9,
            'The retained ARMSX2 Core needs the launch-policy ABI9')
    from helper_initialization import verify as verify_helper
    from collect_build_source_evidence import repository_inputs
    verify_helper()
    repository_inputs(ROOT)
    product = manifest['product']
    executed = [g for g in TEST_GROUPS if manifest['tests'][g]['mode'] == 'fresh'] + ['delivery-contract']
    return dict(result='passed', build=manifest['build'], source=head, tree=repo.tree_of('HEAD'),
                manifest=dict(path=manifest_path(manifest['build']), sha256=manifest_sha(manifest['build'])),
                base=dict(build=base['build'], source=base['source'], ipaSHA256=base['ipa']['sha256'],
                          images=len(images)),
                effective=effective, reviewedCommits=[c['commit'] for c in product['reviewedCommits']],
                sourceOnly=[dict(commit=c['commit'], targetBuild=c['targetBuild']) for c in product['sourceOnly']],
                componentPins=pins, retainedInputs=inputs, recipient=recipient,
                replacedComponents=sorted(k for k, v in manifest['components'].items() if v['mode'] == 'replace'),
                retainedComponents=sorted(k for k, v in manifest['components'].items() if v['mode'] != 'replace'),
                rebuiltForDelivery=['Flutter application and host plugins'],
                testsRun={g: manifest['tests'][g]['mode'] for g in TEST_GROUPS} | {'delivery-contract': 'fresh'},
                testsExecutedInThisRun=executed, physicalDeviceTested=False)


def verify_source():
    from delivery_contract_memo import reuse
    return reuse('standard-source', source_contract)


# --- CI operations ---------------------------------------------------------------------------------------

def materialize():
    """First step after checkout in every job: restore and verify the frozen effective tree."""
    repo = Repo()
    head = repo.commit('HEAD')
    require(head == os.environ.get('GITHUB_SHA', head), 'Checkout differs from the triggering source')
    subject = repo.subject(head)
    requested = subject_build(subject)
    if os.environ.get('BUILD_NUMBER'):
        require(requested == ci_build(), 'The commit subject does not request build ' + os.environ['BUILD_NUMBER'])
    if requested is None:
        write_outputs(build='')
        print('No delivery requested: the commit subject has no [ipa-delivery:NNN] tag; later jobs are skipped.')
        return dict(result='no-delivery-requested', subject=subject)
    manifest = load_manifest(requested)
    require(manifest['status'] == 'frozen' and not manifest_errors(manifest),
            'The requested build has no frozen manifest: ' + '; '.join(manifest_errors(manifest)))
    value = materialize_tree(repo, manifest, head)
    write_outputs(build=str(requested), recipient=manifest['recipient']['path'],
                  **{'artifact-prefix': artifact_prefix(requested, head),
                     'flutter-mode': manifest['tests']['flutter']['mode'],
                     'native-mode': manifest['tests']['native']['mode']})
    return save('standard-materialized.json', dict(value, build=requested, source=head))


def baseline():
    contract = save('standard-host-contract.json', verify_source())
    manifest = ci_manifest()
    base = authenticate_base(manifest)
    write_environment(DOLPHIN_SHA=manifest['components']['dolphin']['upstreamRevision'])
    return save('standard-baseline.json', dict(result='authenticated-run-and-effective-source', application=contract,
        delivered=base, previousPrivateIPADownloadedByThisRun=False,
        previousIPAMetadataOrigin='Verified delivery receipt committed by the integrator; the private IPA is not a runtime donor.',
        historicalTestsReexecuted=False))


def donor():
    manifest = ci_manifest()
    spec = manifest['components']['donor']
    folder = ROOT / 'build/native-baseline'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / spec['asset']
    subprocess.run(['curl', '--fail', '--location', '--retry', '3', spec['url'], '--output', str(target)], check=True,
                   timeout=900)
    require(target.stat().st_size == spec['bytes'] and sha_file(target) == spec['sha256'],
            'The pinned donor release asset differs')
    subprocess.run([sys.executable, 'build-utils/game_content_gate.py', str(target)], cwd=ROOT, check=True, timeout=1800)
    subprocess.run([sys.executable, spec['preparer'], str(target), '--build-number', str(manifest['build'])], cwd=ROOT,
                   check=True, timeout=1800)
    return save('standard-donor.json', dict(result='authenticated-and-extracted', release=spec['release'],
                                            asset=spec['asset'], bytes=spec['bytes'], sha256=spec['sha256']))


def rpcs3_pin(manifest=None):
    import rpcs3_core_component as rpcs3
    manifest = manifest or ci_manifest()
    pin = rpcs3.load_pin(ROOT / manifest['components']['rpcs3']['pin'])
    require(sha_file(ROOT / manifest['components']['rpcs3']['pin']) == manifest['components']['rpcs3']['pinSha256'],
            'The RPCS3 Core pin changed after the freeze')
    return rpcs3.pinned(pin)


def rpcs3_operation(operation, path=None):
    import rpcs3_core_component as rpcs3
    pin = rpcs3_pin()
    if operation == 'download-rpcs3':
        return save('standard-rpcs3-download.json', rpcs3.download_core(pin))
    if operation == 'install-rpcs3':
        return save('standard-rpcs3-install.json', rpcs3.install(pin))
    if operation == 'rpcs3-exports':
        return save('standard-rpcs3-exports.json', rpcs3.check_exports(pin, path))
    if operation == 'embed-rpcs3-source':
        return save('standard-rpcs3-source.json', rpcs3.embed_compiled_source(pin, path))
    raise ValueError(operation)


def component_runs():
    import rpcs3_core_component as rpcs3
    import melonx_reads_core_component as melonx
    return save('standard-component-runs.json', dict(rpcs3=rpcs3.core_run(rpcs3_pin()), melonx=melonx.producer('core')))


def melonx_operation(operation):
    import melonx_reads_core_component as melonx
    if operation == 'download-melonx':
        return save('standard-melonx-download.json', melonx.download('core'))
    return save('standard-melonx-evidence.json', melonx.engine_evidence())


def native_operation(kind, install=True):
    import retained_components as retained
    manifest = ci_manifest()
    suffix = '' if install else '-authenticated'
    return save(f'standard-{kind}{suffix}.json', retained.install_native(kind, manifest['components'][kind], install))


def archive_operation(kind):
    import retained_components as retained
    manifest = ci_manifest()
    return save(f'standard-retained-{kind}.json', retained.download_archive(kind, manifest['components'][kind]))


def libretro():
    import retained_components as retained
    manifest = ci_manifest()
    return save('standard-libretro.json', retained.verify_libretro(manifest['components']['libretro']))


def neoswap_host():
    pin = rpcs3_pin()
    store = pin['hostStore']
    source = (ROOT / store['path']).read_bytes()
    copied_path = Path('packages/neo_swap/ios/Classes/Storage/Store.cpp')
    copied = (ROOT / copied_path).read_bytes()
    require(source == copied, 'CocoaPods NeoSwap Store.cpp differs from the reviewed source')
    require(sha(copied) == store['sha256'], 'The reviewed NeoSwap host source was not copied')
    require('Store.cpp in Sources' in (ROOT / 'ios/Pods/Pods.xcodeproj/project.pbxproj').read_text(),
            'NeoSwap Store.cpp is absent from CocoaPods sources')
    return save('neoswap-host-source.json', dict(result='passed', source=store['path'], compiledSource=str(copied_path),
        sha256=store['sha256'], bytes=len(copied), cocoaPodsSourcesEntryPresent=True, nativeSuitesReplayed=False))


def diff_check():
    """`git diff --check` of the working tree against the effective tree (not against HEAD)."""
    manifest = ci_manifest()
    repo = Repo()
    index, environment = effective_index(repo, manifest)
    try:
        result = repo.run('diff', '--check', env=environment, check=False)
    finally:
        Path(index).unlink(missing_ok=True)
    require(result.returncode == 0, 'Whitespace errors in build changes:\n' + result.stdout.decode(errors='replace')[-4000:])
    return dict(result='passed')


# --- Images ----------------------------------------------------------------------------------------------

def expand_image_patterns(patterns, names):
    result = []
    for pattern in patterns:
        hits = sorted(n for n in names if fnmatch.fnmatchcase(n, pattern) and n.count('/') == pattern.count('/'))
        require(hits, 'An image pattern matches no base image: ' + pattern)
        result += [hit for hit in hits if hit not in result]
    return result


def images_for_paths(paths, base_images):
    """Images whose sources a product path feeds (Dart -> App, package ios -> its framework)."""
    images, unmapped = set(), []
    for path in paths:
        parts = path.split('/')
        if parts[0] == 'lib' or path in ('pubspec.yaml', 'pubspec.lock'):
            images.add(APP)
        elif parts[0] == 'packages' and len(parts) > 2:
            plugin = parts[1]
            if parts[2] in ('lib', 'pubspec.yaml'):
                images.add(APP)
            elif parts[2] == 'ios' and not (len(parts) > 3 and parts[3] in ('Frameworks', 'Tests')):
                name = PLUGIN_IMAGES.get(plugin, f'Frameworks/{plugin}.framework/{plugin}')
                if name in base_images:
                    images.add(name)
                else:
                    unmapped.append(path)
        elif parts[0] in ('native', 'ios'):
            unmapped.append(path)
    return sorted(images), unmapped


def image_expectations(manifest):
    images = manifest['images']
    return dict(retained=images['retainedFingerprints'], replaced=images['replacedFingerprints'],
                mustChange=images['mustChange'], added=images['added'], removed=images['removed'])


def check_images(actual, base, manifest):
    """Replaced images equal their new fingerprints, retained ones the base, must-change ones differ;
    the image set equals the base set unless the manifest declares additions or removals."""
    rules = image_expectations(manifest)
    expected_names = (set(base) - set(rules['removed'])) | set(rules['added'])
    require(set(actual) == expected_names, 'Native image inventory differs: missing=' +
            repr(sorted(expected_names - set(actual))) + ' extra=' + repr(sorted(set(actual) - expected_names)))
    for name, digest in rules['replaced'].items():
        require(actual[name] == digest != base[name], 'Replaced image is not its new payload: ' + name)
    for name, digest in rules['retained'].items():
        require(actual[name] == digest == base[name], 'Retained image payload changed: ' + name)
    for name in rules['mustChange']:
        require(actual[name] != base.get(name), 'An image that must change kept its base payload: ' + name)
    changed = sorted(name for name in actual if name in base and actual[name] != base[name])
    declared = set(rules['replaced']) | set(rules['mustChange'])
    return dict(imageCount=len(actual), changedFromBase=changed, undeclaredChanges=sorted(set(changed) - declared),
                added=sorted(rules['added']), removed=sorted(rules['removed']), retainedVerified=len(rules['retained']),
                replacedVerified=len(rules['replaced']), mustChangeVerified=len(rules['mustChange']))


def base_images(manifest):
    return verify_base(manifest)


def validate_inventory(names, manifest):
    rules = image_expectations(manifest)
    base = set(manifest['images']['baseImages'])
    expected_names = (base - set(rules['removed'])) | set(rules['added'])
    actual = set(names)
    require(actual == expected_names and len(names) == len(expected_names),
            'Native image inventory differs: missing=' + repr(sorted(expected_names - actual)) +
            ' extra=' + repr(sorted(actual - expected_names)))
    return len(actual)


# --- Identity, embedding, structure, seal and validation -----------------------------------------------

def expected():
    import retained_components as retained
    import rpcs3_core_component as rpcs3
    import melonx_reads_core_component as melonx
    manifest = ci_manifest()
    repo = Repo()
    application = json.loads((OUT / 'standard-host-contract.json').read_bytes())
    require(application['source'] == repo.commit('HEAD') and application['build'] == manifest['build'],
            'Application checkout changed after the contract')
    tests = json.loads((OUT / 'standard-tests.json').read_bytes())
    require(set(tests) == set(TEST_GROUPS) | {'deliveryContract', 'testsExecutedInThisRun', 'testsRun'},
            'The authenticated test evidence is absent')
    reauthenticate_tests(tests, manifest)
    natives = {}
    for kind in retained.NATIVES:
        value = json.loads((OUT / f'standard-{kind}.json').read_bytes())
        origin = retained.native_origin(kind, manifest['components'][kind])
        require(all(value.get(key) == origin[key] for key in origin if key != 'expiresAt'),
                'Retained Core differs from its authenticated original producer: ' + kind)
        natives[kind] = value
    archives = {kind: json.loads((OUT / f'standard-retained-{kind}.json').read_bytes()) for kind in retained.ARCHIVES}
    pin = rpcs3_pin(manifest)
    base = base_images(manifest)
    rpcs3_receipt = rpcs3.core_receipt(pin)
    require(rpcs3_receipt['corePayloadFingerprint'] == pin['core']['payloadFingerprint'] != base[rpcs3.CORE_IMAGE],
            'The RPCS3 Core payload must replace the delivered one')
    melonx_receipt = melonx.engine_evidence()
    melonx_image = manifest['components']['melonx']['image']
    require(melonx_receipt['payloadFingerprint'] == melonx.pin()['packagedFingerprint'] != base[melonx_image],
            'The MeloNX Core payload must replace the delivered one')
    packaging = json.loads((ROOT / 'dist/melonx/packaging-identity.json').read_bytes())
    return dict(schema=1, build=manifest['build'], recipe='standard',
                manifest=dict(path=manifest_path(manifest['build']), sha256=manifest_sha(manifest['build'])),
                base=dict(build=manifest['base']['build'], source=manifest['base']['source'],
                          ipaSHA256=manifest['base']['ipa']['sha256']),
                application=application, testEvidence=tests, evidenceModes={g: tests[g]['evidenceMode']
                                                                            for g in TEST_GROUPS},
                components=dict(rpcs3=rpcs3_receipt, melonx=dict(melonx_receipt, packagedCoreSHA256=packaging['packagedCoreSha256']),
                                **natives, **archives),
                physicalDeviceTested=False, gameTested=False, fpsGainProven=False)


def embed(app):
    import retained_components as retained
    manifest = ci_manifest()
    info = plistlib.loads((Path(app) / 'Info.plist').read_bytes())
    require(str(info['CFBundleVersion']) == str(manifest['build']), 'Wrong embedding build')
    value = expected()
    (Path(app) / IDENTITY).write_text(json.dumps(value, indent=2) + '\n')
    notices = {kind: retained.embed_native_notices(kind, manifest['components'][kind], app) for kind in retained.NATIVES}
    return save('standard-embedded.json', dict(result='embedded', identity=value, legalNotices=notices))


def structure(ipa):
    import rpcs3_core_component as rpcs3
    import validate_rpcs3_ipa as structural
    manifest = ci_manifest()
    pin = rpcs3_pin(manifest)
    with rpcs3.structural_verifier(pin) as verifier:
        value = structural.validate_ipa(Path(ipa), str(manifest['build']), Repo().commit('HEAD'),
                                        ROOT / rpcs3.DOWNLOAD / 'identity.json', pin['producer']['core']['source'],
                                        str(pin['producer']['core']['run']))
    return save('standard-rpcs3-structure.json', dict(value, coreIdentityVerifier=verifier))


def seal():
    import delivery_benchmark as benchmark
    from rewind607_delivery import app_payloads, zip_payloads
    manifest = ci_manifest()
    app = ROOT / 'build/ios/dolphin-unsigned/Payload/NeoStation.app'
    before = app_payloads(app)
    count = validate_inventory(before, manifest)
    benchmark.seal()
    after = app_payloads(app)
    ipa = ROOT / 'dist/NeoStation.ipa'
    packaged = zip_payloads(ipa)
    require(before == after == packaged, 'Signing/export changed compiled code, data, ABI or an architecture container')
    receipt = json.loads((OUT / 'signed-payload-identity.json').read_bytes())
    complete = {name: record['fingerprint'] for name, record in before.items()}
    require(set(receipt['images']) <= set(complete) and
            all(complete[name] == digest for name, digest in receipt['images'].items()),
            'Signer receipt disagrees with the full native inventory')
    require(receipt['ipaSha256'] == sha_file(ipa) and receipt['ipaBytes'] == ipa.stat().st_size and
            receipt['allCompiledCodeAndDataSectionsUnchangedBySigning'] is True and
            receipt['abiMetadataUnchangedBySigning'] is True, 'Wrong signed export identity')
    signature = json.loads((OUT / 'signature.json').read_bytes())
    signed_targets = {'.' if name == 'Runner' else name if name.endswith('.dylib') else Path(name).parent.as_posix()
                      for name in before}
    require(len(signed_targets) == count and len(signature['signatures']) == count and
            all(item['signatureVerified'] is True for item in signature['signatures']) and
            {item['bundle'] for item in signature['signatures']} == signed_targets,
            'Missing, duplicated or failed actual macOS signature verification')
    base = set(manifest['images']['baseImages'])
    receipt.update(build=manifest['build'], images=complete, imageCount=count, retainedImageNames=len(base & set(complete)),
                   addedImageNames=len(set(complete) - base),
                   architectureContainers={name: record['container'] for name, record in before.items()},
                   singleArm64FatImages=sum(record['container'].startswith('single-arm64-fat') for record in before.values()),
                   completeNativeInventoryCheckedBeforeAndAfterSigning=True, completeNativeInventoryCheckedInFinalZIP=True)
    return save('signed-payload-identity.json', receipt)


def validate(ipa):
    import retained_components as retained
    import rpcs3_core_component as rpcs3
    import melonx_reads_core_component as melonx
    import rewind608_producers as producers608
    from rewind606_engine import safe_members
    from rewind607_delivery import zip_payloads
    from delivery_benchmark import payload_fingerprint
    from validate_neoplay_ipa import validate as neoplay
    from validate_shader_compiler_ipa import validate as shaders
    from verify_ipa import macho
    manifest = ci_manifest()
    pin = rpcs3_pin(manifest)
    receipt = expected()
    complete = zip_payloads(ipa)
    validate_inventory(complete, manifest)
    signature = json.loads((OUT / 'signed-payload-identity.json').read_bytes())
    actual = {name: record['fingerprint'] for name, record in complete.items()}
    require(actual == signature['images'] and signature['ipaSha256'] == sha_file(ipa), 'Final ZIP differs from sealed payloads')
    images = check_images(actual, base_images(manifest), manifest)
    with zipfile.ZipFile(ipa) as archive:
        safe_members(archive)
        root = APP_ROOT
        require(json.loads(archive.read(root + IDENTITY)) == receipt, 'Packaged build identity differs')
        info = plistlib.loads(archive.read(root + 'Info.plist'))
        require(str(info['CFBundleVersion']) == str(manifest['build']) and info['MinimumOSVersion'] == '18.0',
                'Wrong application version/deployment target')
        rpc_result = rpcs3.compare_core_pinned(pin, archive.read(root + rpcs3.CORE_IMAGE), rpcs3.raw_core(pin), signed=True)
        source_record = json.loads(archive.read(root + 'Legal/RPCS3-current-core/actual-compiled-source.json'))
        source_zip = archive.read(root + 'Legal/RPCS3-current-core/compiled-host-inputs.zip')
        require(source_record['compiledInputsZipSHA256'] == sha(source_zip) and
                source_record['coreSHA256'] == pin['core']['dylibSha256'] and
                source_record['coreSource'] == pin['producer']['core']['source'], 'RPCS3 Core source notice identity differs')
        with zipfile.ZipFile(io.BytesIO(source_zip)) as sources:
            require({n: sha(sources.read(n)) for n in sources.namelist()} == source_record['inputs'] ==
                    rpcs3.compiled_inputs(pin), 'RPCS3 actual compiled source notice changed')
        core_image = macho(archive.read(root + rpcs3.CORE_IMAGE))
        require(set(rpcs3.added_symbols(pin)) <= set(core_image['definedSymbols']),
                'Packaged RPCS3 Core lacks the declared added exports')
        melonx_result = melonx.engine_ipa(archive, root)
        for kind in retained.NATIVES:
            spec = manifest['components'][kind]
            name = retained.CORE_NAMES[kind]
            raw = archive.read(root + f'Frameworks/{name}.framework/{name}')
            image = macho(raw)
            require(payload_fingerprint(raw) == receipt['components'][kind]['payloadFingerprint'] ==
                    spec['payloadFingerprint'] and image['codeSignature'] is True,
                    'Signed native Core differs from its retained payload: ' + kind)
            exports = set(image['definedSymbols'])
            require(producers608.DOLPHIN_EXPORTS <= exports if kind == 'dolphin' else exports == {'_NeoARMSX2_GetAPI'},
                    'Packaged native exports differ: ' + kind)
            folder = f"Legal/{spec['legalFolder']}/"
            require(json.loads(archive.read(root + folder + 'identity.json')) == receipt['components'][kind]['identity'],
                    'Retained Core source identity notice differs: ' + kind)
            for path, digest in receipt['components'][kind]['compiledSourcePostimages'].items():
                require(sha(archive.read(root + folder + 'patched-source/' + path)) == digest,
                        'Retained patched native source notice differs: ' + path)
        plugin = archive.read(root + 'Frameworks/achievement_translation.framework/achievement_translation')
        translation = macho(plugin)
        require(translation['platform'] == 2 and translation['fileType'] == 6 and translation['minimumOS'].startswith('18.'),
                'Wrong compiled Translation plugin')
        for marker in (b'AchievementTranslationPlugin', b'RBAchievementText', b'RBAchievementToast',
                       b'rewindbox/achievement_translation', b'RBAchievementPresent'):
            require(marker in plugin, 'Missing actual Translation implementation')
        plugin = archive.read(root + 'Frameworks/retro_achievements_session.framework/retro_achievements_session')
        central = macho(plugin)
        require(central['platform'] == 2 and central['fileType'] == 6 and central['minimumOS'].startswith('18.') and
                central['codeSignature'] is True, 'Wrong actual central session framework')
        require({'_RBRATakeLaunchConfiguration', '_RBRAPublishSessionState', '_RBRAEndSession', '_RBRALocalizedText'} <=
                set(central['definedSymbols']), 'Central RA facade is not exported')
        for marker in (b'RetroAchievementsSessionPlugin', b'rewindbox/retro_achievements_session'):
            require(marker in plugin, 'Missing compiled central account implementation')
        session = '@rpath/retro_achievements_session.framework/retro_achievements_session'
        for consumer in ('armsx2_internal_bridge', 'dolphin_internal_bridge', 'libretro_internal_bridge'):
            image = macho(archive.read(root + f'Frameworks/{consumer}.framework/{consumer}'))
            require(image['minimumOS'].startswith('18.') and any(d['path'] == session for d in image['dependencies']),
                    'Native consumer does not link the central session pod: ' + consumer)
        bridge = macho(archive.read(root + 'Frameworks/rpcs3_internal_bridge.framework/rpcs3_internal_bridge'))
        rpcs3_bridge_links_session = any(d['path'] == session for d in bridge['dependencies'])
        helper = 'PlugIns/MeloNXJITHelper.appex/melonx-universal.js'
        require(archive.read(root + helper) == (ROOT / 'packages/melonx_jit_helper/ios/Resources/melonx-universal.js').read_bytes(),
                'The MeloNX JIT helper differs from its source')
        host = archive.read(root + 'Frameworks/melonx_internal_bridge.framework/melonx_internal_bridge')
        for marker in (b'Hogwarts GPU policy:', b'occlusionQuerySync', b'relaxQueryFlushing',
                       b'original core SHA256 prefix', b'inspectUnreal'):
            require(marker in host, 'Delivered Hogwarts host behavior missing')
    head = Repo().commit('HEAD')
    return save('standard-ipa-validation.json', dict(result='passed', build=manifest['build'], ipaSHA256=sha_file(ipa),
        ipaBytes=Path(ipa).stat().st_size, identity=receipt, nativeImages=images['imageCount'], images=images,
        newRPCS3Payload=rpc_result, newMeloNXPayload=melonx_result, retainedNativePayloadsVerified=True,
        rpcs3BridgeLinksCentralSession=rpcs3_bridge_links_session, actualTranslationAndSessionPluginsPresent=True,
        retainedNeoPlay=neoplay(Path(ipa), str(manifest['build']), head),
        shaderCompilerIsolation=shaders(Path(ipa), str(manifest['build'])),
        physicalDeviceTested=False, gameTested=False, fpsGainProven=False))


def republication_sources(manifest):
    """{kind: (archive path, original pin)} of every authenticated archive this delivery downloaded."""
    import retained_components as retained
    import rpcs3_core_component as rpcs3
    import melonx_reads_core_component as melonx
    pin = rpcs3_pin(manifest)
    sources = {}
    for kind, (path, value) in rpcs3.archives(pin).items():
        sources[kind] = (path, dict(workflow=pin['producer']['workflow'], **value))
    melonx_pin = melonx.pin()
    sources['melonx-core'] = (melonx.CACHE / 'core.zip', dict(workflow=melonx_pin['workflow'], source=melonx_pin['source'],
        run=melonx_pin['run'], attempt=melonx_pin['attempt'], job=melonx_pin['job'], artifact=melonx_pin['artifact'],
        name=melonx_pin['name'], bytes=melonx_pin['bytes'], sha256=melonx_pin['sha256']))
    for kind in retained.NATIVES:
        sources[kind] = (retained.native_archive(kind), manifest['components'][kind]['origin'])
    for kind in retained.ARCHIVES:
        origin = dict(manifest['components'][kind]['origin'], job=None)
        sources[kind] = (retained.retained_archive(kind), origin)
    return sources


def republish():
    import retained_components as retained
    manifest = ci_manifest()
    current = execution()
    republisher = dict(build=manifest['build'], source=current['source'], run=current['run'], attempt=current['attempt'],
                       workflow=WORKFLOW, job=os.environ.get('GITHUB_JOB', 'republish'))
    sources = republication_sources(manifest)
    records = {}
    for kind in manifest['republish']:
        path, origin = sources[kind]
        records[kind] = retained.stage_republication(kind, origin, path, republisher)
    return save('standard-republication.json', dict(result='staged', retentionDays=90, records=records))


# --- Freeze (local) ----------------------------------------------------------------------------------------

def validate_effective_legal(repo, effective, head, dolphin_revision):
    """Run the application's own pre-compilation legal check (embed_legal_bundle.py --validate-only, which
    includes the source/license declarations of collect_build_source_evidence) on an exported copy of
    the effective tree, so a product defect that would stop the delivery late is reported by the freeze."""
    entries = dict(effective)
    entries.update({path: entry for path, entry in repo.entries(head).items() if is_recipe(path)})
    with tempfile.TemporaryDirectory(prefix='effective-tree-') as directory:
        repo.export(entries, directory)
        environment = {key: value for key, value in os.environ.items() if not key.startswith('GITHUB_')}
        process = subprocess.run([sys.executable, '-B', 'build-utils/embed_legal_bundle.py', '--validate-only',
                                  '--dolphin-sha', dolphin_revision], cwd=directory, capture_output=True,
                                 env=environment, timeout=600)
    output = (process.stdout + process.stderr).decode(errors='replace').strip()
    return process.returncode == 0, output.splitlines()[-1] if output else ''


def freeze(build, dry_run=False, repo=None, root=None):
    """Local integration only: bind the build's effective product tree and write its frozen manifest."""
    import retained_components as retained
    import rpcs3_core_component as rpcs3
    require(not in_ci(), 'The delivery manifest is frozen locally, never in CI')
    repo = repo or Repo()
    root = Path(root or repo.root)
    path = root / manifest_path(build)
    draft = json.loads(path.read_bytes())
    require(draft.get('schema') == 1 and draft.get('build') == build, 'Wrong draft manifest')
    blockers, notes = [], []
    head = repo.commit('HEAD')
    branch = repo.text('branch', '--show-current').strip()
    if branch != BRANCH:
        blockers.append(f'checkout: the branch is {branch!r}; the freeze runs on the {BRANCH} checkout')
    dirty = repo.text('status', '--porcelain', '--untracked-files=normal').strip()
    if dirty:
        blockers.append('checkout: the working tree is not clean: ' + repr(dirty.splitlines()[:10]))
    remote = repo.run('rev-parse', '--verify', '--quiet', 'refs/remotes/origin/' + BRANCH + '^{commit}', check=False)
    if remote.returncode:
        blockers.append(f'checkout: origin/{BRANCH} is unknown; fetch it before freezing')
    elif not repo.is_ancestor(remote.stdout.decode().strip(), head):
        blockers.append(f'checkout: HEAD lacks commits of origin/{BRANCH} (stale); rebase onto it first')
    base = draft['base']

    def read_head(name):
        target = root / name
        return target.read_bytes() if target.is_file() else None
    base_images_value = verify_base(draft, read_head)
    require(repo.tree_of(base['source']) == base['tree'] and repo.is_ancestor(base['source'], head),
            'The base delivery source is not an ancestor of HEAD')
    pin_path = root / draft['components']['rpcs3']['pin']
    pin = json.loads(pin_path.read_bytes())
    pin_report = rpcs3.pin_errors(pin, read_head)
    if pin['status'] != 'verified' or pin_report['missing']:
        blockers.append('components.rpcs3: the RPCS3 Core pin is pending; unknown values: ' +
                        ', '.join(pin_report['missing']))
    if pin_report['errors']:
        blockers.append('components.rpcs3: ' + '; '.join(pin_report['errors']))
    melonx_raw = (root / draft['components']['melonx']['pin']).read_bytes()
    melonx_pin = json.loads(melonx_raw)
    contract = read_head('build-utils/melonx/reads-core-contract.json')
    if not (melonx_pin.get('status') == 'verified' and contract is not None and
            melonx_pin['contractSha256'] == sha(contract) and melonx_pin['name'] == 'MeloNX-engine-' + melonx_pin['source']):
        blockers.append('components.melonx: the MeloNX Core pin is not verified against its contract')
    product = draft['product']
    reviewed = [item['commit'] for item in product['reviewedCommits']]
    source_only = [item['commit'] for item in product['sourceOnly']]
    tree = effective_tree(repo, base['source'], head, reviewed, source_only)
    for conflict in tree['conflicts']:
        blockers.append(f"product: reviewed commit {conflict['commit'][:12]} touches {conflict['path']} from bytes "
                        'that are not in the effective tree (an earlier source-only or unclassified change)')
    for item in tree['unclassified']:
        blockers.append(f"product: unclassified commit {item['commit'][:12]} ({item['subject']}) changes "
                        f"{item['productPaths']} product paths; declare it reviewed or source-only")
    for commit in tree['missing']:
        blockers.append(f'product: declared commit {commit[:12]} is not between the base and HEAD')
    reader = EffectiveReader(repo, tree['effective'])
    try:
        retained_count = retained_inputs_unchanged(draft, repo, reader.listing, reader.read)
    except ValueError as error:
        blockers.append('components: ' + str(error))
        retained_count = None
    legal_ok, legal_message = validate_effective_legal(repo, tree['effective'], head,
                                                       draft['components']['dolphin']['upstreamRevision'])
    if not legal_ok:
        blockers.append('product: the legal and source-notice check of the application (embed_legal_bundle.py '
                        '--validate-only) refuses the effective tree: ' + legal_message)
    tests = {}
    for group in TEST_GROUPS:
        spec = dict(draft['tests'][group])
        spec['commands'] = expand_commands(group, spec, reader.listing)
        missing = [p for p in command_inputs(spec['commands'])
                   if not (reader.exists(p) or (is_recipe(p) and (root / p).exists()))]
        if missing:
            blockers.append(f'tests.{group}: command inputs absent from the effective tree: {missing}')
        tests[group] = spec
    tests['awaitMinutes'] = draft['tests'].get('awaitMinutes', 75)
    names = sorted(base_images_value)
    images = dict(draft['images'])
    reviewed_paths = sorted({path for path, entry in tree['effectiveRecords'].items()})
    derived, unmapped = images_for_paths(reviewed_paths, set(names))
    replaced = {}
    for component, image in images['replaced'].items():
        replaced[image] = (pin['core'].get('payloadFingerprint') if component == 'rpcs3' else
                           melonx_pin['packagedFingerprint'] if component == 'melonx' else None)
    retained_images = {}
    for component, patterns in images['retained'].items():
        for name in expand_image_patterns(patterns, names):
            retained_images[name] = base_images_value[name]
    must_change = sorted(set(images['mustChange']) | set(derived) | set(replaced) | {RUNNER})
    overlap = set(retained_images) & (set(must_change) | set(replaced))
    if overlap:
        blockers.append('images: an image is both retained and changed: ' + repr(sorted(overlap)))
    if unmapped:
        notes.append(f'images: {len(unmapped)} reviewed product paths map to no image (reported, not fatal): ' +
                     repr(unmapped[:10]))
    images.update(baseImages=names, retainedFingerprints=dict(sorted(retained_images.items())),
                  replacedFingerprints=replaced, derivedMustChange=derived, mustChange=must_change)
    head_paths = repo.entries(head)
    embedded = {name: sha(read_head(name)) for name in sorted(head_paths)
                if is_embedded_recipe_input(name) and read_head(name) is not None}
    absent = [name for name in EMBEDDED_RECIPE_FILES if name not in embedded]
    if absent:
        blockers.append('product: embedded recipe-pattern inputs are absent: ' + repr(absent))
    for kind in ('rpcs3', 'melonx'):
        draft['components'][kind]['pinSha256'] = sha((root / draft['components'][kind]['pin']).read_bytes())
    for kind in retained.ARCHIVES + retained.NATIVES:
        expires = draft['components'][kind]['origin'].get('expiresAt')
        if expires and not draft['components'][kind].get('republished'):
            notes.append(f'components.{kind}: the retained producer artifact expires at {expires}')
    restore = tree['restoreRecords']
    frozen_product = dict(product, freezeCommit=head, freezeTree=repo.tree_of(head),
        recipeDefinitionSHA256=recipe_definition_sha(), recipeDefinition=RECIPE_DEFINITION,
        commits=tree['commits'], deferred=tree['deferred'], effective=tree['effectiveRecords'], restore=restore,
        effectiveDigest=tree['effectiveDigest'], productFiles=tree['productFiles'], embeddedRecipeInputs=embedded)
    frozen = dict(draft, status='frozen', product=frozen_product, images=images, tests=tests,
                  frozen=dict(at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), commit=head,
                              tool='standard_delivery.py freeze', inCI=False))
    errors = manifest_errors(frozen)
    if errors:
        blockers.append('manifest: ' + '; '.join(errors))
    report = dict(build=build, head=head, dryRun=dry_run, frozenWouldSucceed=not blockers, blockers=blockers,
                  notes=notes, unclassifiedCommits=tree['unclassified'], conflicts=tree['conflicts'],
                  commits=[dict(commit=c['commit'][:12], role=c['role'], productPaths=c['productPaths'],
                                subject=c['subject']) for c in tree['commits']],
                  deferred={c[:12]: len(p) for c, p in tree['deferred'].items()},
                  effectiveDifferencesFromBase=len(tree['effectiveRecords']),
                  restore=dict(count=len(restore), deleted=sorted(p for p, e in restore.items() if e is None),
                               restoredBytes=sorted(p for p, e in restore.items() if e is not None)),
                  effectiveDigest=tree['effectiveDigest'], productFiles=tree['productFiles'],
                  retainedInputsChecked=retained_count, legalCheck=dict(passed=legal_ok, message=legal_message),
                  images=dict(mustChange=must_change, derived=derived,
                                                                     retained=len(retained_images)),
                  tests={g: len(tests[g]['commands']) for g in TEST_GROUPS})
    if dry_run:
        return report
    require(not blockers, 'Freeze refused:\n- ' + '\n- '.join(blockers))
    path.write_text(json.dumps(frozen, indent=2) + '\n')
    return dict(report, written=str(path.relative_to(root)))


# --- Trigger commit (local) --------------------------------------------------------------------------------

def github_glob(pattern):
    """GitHub Actions filter pattern -> regex (* no slash, ** anything, ? and + quantify the previous char)."""
    out, index = '', 0
    while index < len(pattern):
        if pattern.startswith('**', index):
            out += '.*'
            index += 2
            continue
        char = pattern[index]
        if char == '*':
            out += '[^/]*'
        elif char in '?+':
            out += char
        elif char == '[':
            end = pattern.index(']', index)
            out += pattern[index:end + 1]
            index = end + 1
            continue
        else:
            out += re.escape(char)
        index += 1
    return re.compile(out + r'\Z')


def filter_match(patterns, value):
    if isinstance(patterns, str):
        patterns = [patterns]
    matched = False
    for pattern in patterns:
        negate = pattern.startswith('!')
        if github_glob(pattern[1:] if negate else pattern).match(value):
            matched = not negate
    return matched


def push_filter(spec):
    """The push trigger of a parsed workflow (None when push does not trigger it)."""
    on = spec.get('on', spec.get(True))
    if isinstance(on, str):
        return {} if on == 'push' else None
    if isinstance(on, list):
        return {} if 'push' in on else None
    if isinstance(on, dict) and 'push' in on:
        return on['push'] or {}
    return None


def push_triggers(push, branch, paths):
    if push is None:
        return False
    if 'branches' in push or 'branches-ignore' in push:
        if 'branches' in push and not filter_match(push['branches'], branch):
            return False
        if 'branches-ignore' in push and filter_match(push['branches-ignore'], branch):
            return False
    elif 'tags' in push or 'tags-ignore' in push:
        return False
    if 'paths' in push:
        return any(filter_match(push['paths'], path) for path in paths)
    if 'paths-ignore' in push:
        return any(not filter_match(push['paths-ignore'], path) for path in paths)
    return True


class Unevaluated(Exception):
    pass


TOKEN = re.compile(r"\s*(?:(\|\||&&|==|!=|<=|>=|[!()<>,\[\]])|'((?:[^']|'')*)'|(-?\d+(?:\.\d+)?)|([A-Za-z_][\w\-]*(?:\.[\w\-*]+)*))")


def tokenize(expression):
    tokens, index = [], 0
    while index < len(expression):
        if expression[index:].strip() == '':
            break
        match = TOKEN.match(expression, index)
        if not match:
            raise Unevaluated('Unsupported expression: ' + expression)
        operator, string, number, name = match.groups()
        if operator:
            tokens.append(('op', operator))
        elif string is not None:
            tokens.append(('value', string.replace("''", "'")))
        elif number is not None:
            tokens.append(('value', float(number)))
        else:
            tokens.append(('name', name))
        index = match.end()
    return tokens


def truthy(value):
    return not (value is None or value is False or value == 0 or value == '')


def loose_equal(left, right):
    if isinstance(left, str) and isinstance(right, str):
        return left.casefold() == right.casefold()
    return left == right


def evaluate(expression, context, status):
    """A GitHub Actions expression subset: literals, contexts, ! && || == != ( ), contains/startsWith/endsWith,
    and the status functions. Anything else raises Unevaluated (treated as 'may run')."""
    tokens = tokenize(expression)
    position = [0]

    def peek():
        return tokens[position[0]] if position[0] < len(tokens) else (None, None)

    def take(kind=None, value=None):
        token = peek()
        if token[0] is None or (kind and token[0] != kind) or (value is not None and token[1] != value):
            raise Unevaluated('Unexpected token in ' + expression)
        position[0] += 1
        return token

    def lookup(name):
        current = context
        for part in name.split('.'):
            current = current.get(part) if isinstance(current, dict) else None
        return current

    def primary():
        kind, value = peek()
        if kind == 'op' and value == '(':
            take()
            result = disjunction()
            take('op', ')')
            return result
        if kind == 'op' and value == '!':
            take()
            return not truthy(primary())
        if kind == 'value':
            take()
            return value
        if kind == 'name':
            take()
            if value in ('true', 'false'):
                return value == 'true'
            if value == 'null':
                return None
            if peek() == ('op', '('):
                take()
                arguments = []
                while peek() != ('op', ')'):
                    arguments.append(disjunction())
                    if peek() == ('op', ','):
                        take()
                take('op', ')')
                return call(value, arguments)
            return lookup(value)
        raise Unevaluated('Unexpected token in ' + expression)

    def call(name, arguments):
        lowered = name.lower()
        if lowered in status:
            return status[lowered]
        if lowered == 'contains' and len(arguments) == 2:
            haystack, needle = arguments
            if isinstance(haystack, list):
                return any(loose_equal(item, needle) for item in haystack)
            return str(needle).casefold() in str(haystack or '').casefold()
        if lowered in ('startswith', 'endswith') and len(arguments) == 2:
            text, affix = str(arguments[0] or '').casefold(), str(arguments[1] or '').casefold()
            return text.startswith(affix) if lowered == 'startswith' else text.endswith(affix)
        raise Unevaluated('Unsupported function ' + name)

    def comparison():
        left = primary()
        while peek()[0] == 'op' and peek()[1] in ('==', '!='):
            operator = take()[1]
            right = primary()
            left = loose_equal(left, right) if operator == '==' else not loose_equal(left, right)
        return left

    def conjunction():
        left = comparison()
        while peek() == ('op', '&&'):
            take()
            right = comparison()
            left = right if truthy(left) else left
        return left

    def disjunction():
        left = conjunction()
        while peek() == ('op', '||'):
            take()
            right = conjunction()
            left = left if truthy(left) else right
        return left
    result = disjunction()
    if position[0] != len(tokens):
        raise Unevaluated('Trailing tokens in ' + expression)
    return result


def strip_expression(value):
    text = value.strip()
    if text.startswith('${{') and text.endswith('}}'):
        text = text[3:-2]
    return text


def jobs_that_run(spec, message, branch=BRANCH):
    """Jobs of a push-triggered workflow that would execute for this head commit message."""
    jobs = spec.get('jobs') or {}
    context = dict(github=dict(event_name='push', ref='refs/heads/' + branch, ref_name=branch,
                               event=dict(head_commit=dict(message=message)), sha='0' * 40),
                   inputs={}, env={}, vars={}, secrets={})
    results, unevaluated, order = {}, [], []

    def needs(job):
        value = (jobs[job] or {}).get('needs') or []
        return [value] if isinstance(value, str) else list(value)
    pending = list(jobs)
    while pending:
        ready = [job for job in pending if all(n in results for n in needs(job))]
        require(ready, 'Cyclic job needs')
        for job in ready:
            pending.remove(job)
            upstream = needs(job)
            context['needs'] = {n: dict(result=results[n], outputs={}) for n in upstream}
            succeeded = all(results[n] == 'success' for n in upstream)
            status = dict(success=succeeded, failure=False, cancelled=False, always=True)
            condition = (jobs[job] or {}).get('if')
            if condition is None:
                runs = succeeded
            elif isinstance(condition, bool):
                runs = condition and succeeded
            else:
                text = strip_expression(str(condition))
                uses_status = re.search(r'\b(always|failure|cancelled|success)\s*\(', text) is not None
                try:
                    runs = truthy(evaluate(text, context, status)) and (uses_status or succeeded)
                except Unevaluated:
                    runs = True
                    unevaluated.append(job)
            results[job] = 'success' if runs else 'skipped'
            order.append(job)
    return [job for job in order if results[job] == 'success'], unevaluated


def trigger_paths(build, paths, message=None, root=None, loader=None):
    """Refuse a trigger commit whose paths or message would start any other push workflow on Claude."""
    root = Path(root or ROOT)
    if loader is None:
        import yaml
        loader = yaml.safe_load
    message = message or f'[ipa-delivery:{build}] build(delivery): request the private IPA{build} delivery'
    subject = message.splitlines()[0]
    require(subject_build(subject) == build, 'The trigger subject must carry [ipa-delivery:%d]' % build)
    require(not any(token in message.lower() for token in SKIP_TOKENS), 'A trigger commit cannot skip workflows')
    require(paths, 'A trigger commit changes at least its manifest')
    product = [path for path in paths if is_product(path)]
    require(not product, 'A trigger commit may change only recipe paths: ' + repr(product))
    started, skipped, unevaluated = {}, [], {}
    standard = None
    for workflow in sorted((root / '.github/workflows').glob('*.y*ml')):
        name = workflow.relative_to(root).as_posix()
        spec = loader(workflow.read_text())
        if not isinstance(spec, dict):
            continue
        push = push_filter(spec)
        if not push_triggers(push, BRANCH, paths):
            continue
        running, guessed = jobs_that_run(spec, message)
        if name == WORKFLOW:
            standard = running
            continue
        if guessed:
            unevaluated[name] = guessed
        if running:
            started[name] = running
        else:
            skipped.append(name)
    require(standard is not None and 'preflight' in standard, 'The trigger commit would not start the standard delivery')
    report = dict(build=build, subject=subject, paths=list(paths), standardDeliveryJobs=standard,
                  otherWorkflowsStarted=started, otherWorkflowsTriggeredAllJobsSkipped=skipped,
                  unevaluatedConditions=unevaluated, result='refused' if started else 'accepted')
    require(not started, 'The trigger commit would also start: ' + json.dumps(started))
    return report


# --- Workflow subset parser (no PyYAML in CI) ----------------------------------------------------------------

def load_yaml_subset(text):
    """Parse the YAML subset of the standard workflow: block mappings and sequences, plain/quoted scalars,
    literal blocks (| and |-), empty or one-line flow collections, full-line comments."""
    lines = text.split('\n')

    def indent(line):
        return len(line) - len(line.lstrip(' '))

    def skip(index):
        while index < len(lines) and (not lines[index].strip() or lines[index].lstrip().startswith('#')):
            index += 1
        return index

    def scalar(raw):
        raw = raw.strip()
        if raw.startswith("'"):
            require(raw.endswith("'") and len(raw) >= 2, 'Unterminated quoted scalar: ' + raw)
            return raw[1:-1].replace("''", "'")
        if raw.startswith('"'):
            return json.loads(raw)
        if raw in ('{}', '[]'):
            return {} if raw == '{}' else []
        if raw.startswith('[') and raw.endswith(']'):
            return [scalar(item) for item in raw[1:-1].split(',') if item.strip()]
        if raw in ('true', 'false'):
            return raw == 'true'
        if raw in ('null', '~', ''):
            return None
        if re.fullmatch(r'-?\d+', raw):
            return int(raw)
        require(not raw.startswith(('{', '&', '*', '!', '>', '|')), 'Unsupported YAML scalar: ' + raw)
        return raw

    key_pattern = re.compile(r"""^('(?:[^']|'')*'|"[^"]*"|[A-Za-z0-9_.\-/]+):(?:\s+(.*))?$""")

    def block_scalar(index, parent, style):
        collected, block_indent = [], None
        while index < len(lines):
            line = lines[index]
            if line.strip():
                if indent(line) <= parent:
                    break
                block_indent = indent(line) if block_indent is None else block_indent
                collected.append(line[block_indent:])
            else:
                collected.append('')
            index += 1
        while collected and not collected[-1]:
            collected.pop()
        value = '\n'.join(collected)
        return (value if style == '|-' else value + '\n'), index

    def block(index, level):
        index = skip(index)
        if lines[index][level:].startswith('- ') or lines[index][level:] == '-':
            return sequence(index, level)
        return mapping(index, level)

    def value_after(index, level, rest):
        if rest is None or rest == '':
            following = skip(index + 1)
            if following < len(lines) and indent(lines[following]) > level:
                return block(following, indent(lines[following]))
            if following < len(lines) and indent(lines[following]) == level and lines[following][level:].startswith('- '):
                return sequence(following, level)
            return None, index + 1
        if rest in ('|', '|-'):
            return block_scalar(index + 1, level, rest)
        index += 1
        # A plain or single-quoted scalar may continue on deeper-indented lines (folded with one space).
        while (rest[:1] not in '"[{' and index < len(lines) and lines[index].strip() and
               indent(lines[index]) > level and (rest[:1] != "'" or not rest.endswith("'") or len(rest) == 1)):
            rest += ' ' + lines[index].strip()
            index += 1
        return scalar(rest), index

    def mapping(index, level):
        result = {}
        while True:
            index = skip(index)
            if index >= len(lines) or indent(lines[index]) < level:
                return result, index
            require(indent(lines[index]) == level, f'Bad indentation at line {index + 1}')
            content = lines[index][level:]
            if content.startswith('- '):
                return result, index
            match = key_pattern.match(content)
            require(match, f'Unsupported YAML line {index + 1}: {content}')
            key = scalar(match.group(1)) if match.group(1)[0] in '\'"' else match.group(1)
            require(key not in result, 'Duplicated key: ' + str(key))
            result[key], index = value_after(index, level, match.group(2))

    def sequence(index, level):
        items = []
        while True:
            index = skip(index)
            if index >= len(lines) or indent(lines[index]) != level or not lines[index][level:].startswith('-'):
                return items, index
            content = lines[index][level + 1:]
            stripped = content.lstrip(' ')
            if not stripped:
                following = skip(index + 1)
                value, index = block(following, indent(lines[following]))
            elif key_pattern.match(stripped):
                # A mapping item: re-indent its first key to the column of the item content.
                offset = level + 1 + len(content) - len(stripped)
                lines[index] = ' ' * offset + stripped
                value, index = mapping(index, offset)
            else:
                value, index = scalar(stripped), index + 1
            items.append(value)
    value, end = block(0, 0)
    require(skip(end) >= len(lines), f'Unparsed YAML from line {end + 1}')
    return value


# --- Delivery contract (local and preflight) -----------------------------------------------------------------

def api_checks(manifest, strict):
    """API-backed authentication of every pinned producer; locally a failure is reported, not raised."""
    import retained_components as retained
    import rpcs3_core_component as rpcs3
    import melonx_reads_core_component as melonx
    checks = {
        'base': lambda: authenticate_base(manifest),
        'rpcs3': lambda: rpcs3.core_run(rpcs3.pinned(rpcs3.load_pin(ROOT / manifest['components']['rpcs3']['pin']))),
        'melonx': lambda: melonx.producer('core'),
        'donor': lambda: donor_release(manifest['components']['donor']),
    }
    for kind in retained.NATIVES:
        checks[kind] = lambda kind=kind: retained.native_origin(kind, manifest['components'][kind])
    for kind in retained.ARCHIVES:
        checks[kind] = lambda kind=kind: retained.archive_origin(kind, manifest['components'][kind])
    for group in TEST_GROUPS:
        if manifest['tests'][group]['mode'] == 'reuse':
            checks['tests-' + group] = lambda group=group: reuse_guard(group, manifest)
    report = {}
    for name, check in checks.items():
        try:
            report[name] = dict(result='authenticated', value=check())
        except Exception as error:  # noqa: BLE001 - every failure is reported with its reason
            if strict:
                raise
            report[name] = dict(result='pending' if 'pending' in str(error) else 'failed', reason=str(error))
    return report


def donor_release(spec, get=None):
    get = get or api
    release = get('releases/tags/' + spec['release'])
    assets = [a for a in release['assets'] if a['name'] == spec['asset']]
    require(len(assets) == 1 and assets[0]['size'] == spec['bytes'] and assets[0]['digest'] == 'sha256:' + spec['sha256'] and
            assets[0]['browser_download_url'] == spec['url'], 'The pinned donor release asset changed')
    return dict(release=spec['release'], asset=spec['asset'], bytes=spec['bytes'], sha256=spec['sha256'])


def contract(build=None, offline=False):
    """The delivery contract: the offline contract test, then the API-backed producer checks."""
    strict = in_ci()
    if strict:
        manifest = ci_manifest()
    else:
        builds = [build] if build else sorted(int(p.stem) for p in (ROOT / MANIFESTS).glob('*.json') if p.stem.isdecimal())
        require(builds, 'No delivery manifest')
        manifest = load_manifest(builds[-1])
    if CONTRACT_DIR.exists():
        shutil.rmtree(CONTRACT_DIR)
    CONTRACT_DIR.mkdir(parents=True)
    # As the delivered 610 preflight did: the source contract fails within a minute, before any macOS job.
    source = save('standard-host-contract.json', verify_source()) if strict else None
    process = subprocess.run(CONTRACT_TEST, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
    log = process.stdout
    (CONTRACT_DIR / 'contract.log').write_bytes(log)
    report = None if offline else api_checks(manifest, strict)
    record = dict(schema=1, build=manifest['build'], result='passed' if process.returncode == 0 else 'failed',
                  command=' '.join(CONTRACT_TEST), argv=list(CONTRACT_TEST), exitCode=process.returncode,
                  logSHA256=sha(log), execution=execution() if strict else None,
                  effectiveDigest=manifest['product'].get('effectiveDigest'),
                  manifestSHA256=manifest_sha(manifest['build']), manifestStatus=manifest['status'], api=report,
                  sourceContract=None if source is None else dict(result=source['result'],
                                                                   effectiveDigest=source['effective']['effectiveDigest']))
    (CONTRACT_DIR / 'contract.json').write_text(json.dumps(record, indent=2, default=str) + '\n')
    print(log.decode(errors='replace')[-6000:], flush=True)
    require(process.returncode == 0, 'The delivery contract failed')
    return record


# --- Receipt of a verified delivery (local) --------------------------------------------------------------------

def record(build, run, verification, api_directory, key_deleted=False, root=None):
    """docs/evidence/rewind<N>/delivery.json in the delivered 610 schema, from saved API metadata and the
    offline verification of the downloaded file (build-utils/verify_downloaded_delivery.py)."""
    require(not in_ci(), 'Delivery receipts are written locally after the downloaded file was verified')
    root = Path(root or ROOT)
    manifest = json.loads((root / manifest_path(build)).read_bytes())
    require(manifest['status'] == 'frozen', 'Only a frozen manifest is delivered')
    report = json.loads(Path(verification).read_bytes())
    require(report['result'] == 'passed-offline-checks' and report['build'] == build and
            report['execution']['run'] == run, 'The verification report is not a passed check of this run')
    api_directory = Path(api_directory)
    run_meta = json.loads((api_directory / 'run-attempt.json').read_bytes())
    jobs = json.loads((api_directory / 'jobs.json').read_bytes())
    jobs = jobs.get('jobs', jobs)
    require(run_meta['id'] == run and run_meta['path'] == WORKFLOW and run_meta['conclusion'] == 'success' and
            run_meta['head_sha'] == report['execution']['source'] and run_meta['head_branch'] == BRANCH,
            'The saved run metadata is not a successful standard delivery of this source')
    folder = root / f'docs/evidence/rewind{build}'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'api').mkdir(exist_ok=True)
    for name in ('run-attempt.json', 'jobs.json', 'artifacts.json'):
        shutil.copy2(api_directory / name, folder / 'api' / name)
    shutil.copy2(verification, folder / f'download{build}-verification.json')
    by_name = {job['name']: job for job in jobs}
    require(set(by_name) == set(JOB_NAMES), 'The saved jobs are not the four standard jobs')
    product = manifest['product']
    receipt = dict(schema=1, build=build, version=report.get('version'), result='delivered-and-verified',
        deliveryType='private', recipe=dict(workflow=WORKFLOW, manifest=manifest_path(build),
                                            manifestSHA256=sha((root / manifest_path(build)).read_bytes())),
        execution=dict(source=report['execution']['source'], tree=report['execution']['tree'], run=run,
                       attempt=run_meta['run_attempt'], branch=BRANCH,
                       jobs={name: dict(id=job['id'], conclusion=job['conclusion'], started=job.get('started_at'),
                                        completed=job.get('completed_at')) for name, job in sorted(by_name.items())},
                       runConclusion=run_meta['conclusion'], startedUTC=run_meta.get('run_started_at'),
                       completedUTC=run_meta.get('updated_at')),
        baseline=dict(build=manifest['base']['build'], source=manifest['base']['source'],
                      ipaSHA256=manifest['base']['ipa']['sha256']),
        ipa=dict(name=f'RewindBox-{build}.ipa', producerName=report['ipa']['name'], bytes=report['ipa']['bytes'],
                 sha256=report['ipa']['sha256']),
        delta=dict(freezeCommit=product['freezeCommit'], effectiveDigest=product['effectiveDigest'],
                   reviewedCommits=[c['commit'] for c in product['reviewedCommits']],
                   sourceOnly=[dict(commit=c['commit'], targetBuild=c['targetBuild']) for c in product['sourceOnly']],
                   restoredPaths=len(product['restore'])),
        components={kind: dict(mode=spec['mode']) for kind, spec in manifest['components'].items()},
        verification=dict(result=report['result'], nativeImageCount=report['binaryValidation']['nativeImageCount'],
                          bundles=report['binaryValidation']['bundleCount'],
                          imagesChangedFromBase=report['binaryValidation']['imagesChangedFromBase'],
                          offlineValidators={v['name']: v['exitCode'] for v in report['validators']},
                          signerReceiptIPASHA256Matched=True, cryptographicSignatureVerificationPerformedOffline=False),
        testEvidence=dict(testsRun={g: manifest['tests'][g]['mode'] for g in TEST_GROUPS} | {'delivery-contract': 'fresh'},
                          testsExecutedInThisRun=[g for g in TEST_GROUPS if manifest['tests'][g]['mode'] == 'fresh'] +
                          ['delivery-contract'], deliveryContractJob=by_name['preflight']['id']),
        limits=dict(physicalDeviceTested=False, gameplayTested=False, fpsGainProven=False,
                    appleProvisioningVerified=False, directAppleInstallationReady=False),
        privateRecipientKeyDeletedAfterVerifiedDelivery=bool(key_deleted))
    receipt['proofFiles'] = {p.relative_to(folder).as_posix(): sha_file(p) for p in sorted(folder.rglob('*'))
                             if p.is_file() and p.name != 'delivery.json'}
    (folder / 'delivery.json').write_text(json.dumps(receipt, indent=1) + '\n')
    return dict(result='written', path=str((folder / 'delivery.json').relative_to(root)),
                proofFiles=len(receipt['proofFiles']))


# --- Command line ------------------------------------------------------------------------------------------------

CI_OPERATIONS = ('materialize', 'source-contract', 'baseline', 'tests', 'await-tests', 'donor', 'download-rpcs3',
                 'install-rpcs3', 'rpcs3-exports', 'embed-rpcs3-source', 'component-runs', 'dolphin', 'armsx2',
                 'authenticate-dolphin', 'authenticate-armsx2',
                 'download-libretro', 'libretro', 'download-melonx-dependencies', 'download-melonx', 'melonx-evidence',
                 'neoswap-host', 'embed', 'structure', 'seal', 'validate', 'diff-check', 'republish')
LOCAL_OPERATIONS = ('freeze', 'trigger-paths', 'record')
OPERATIONS = CI_OPERATIONS + LOCAL_OPERATIONS + ('contract',)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('operation', choices=OPERATIONS)
    parser.add_argument('arguments', nargs='*')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--message')
    parser.add_argument('--run', type=int)
    parser.add_argument('--verification', type=Path)
    parser.add_argument('--api', type=Path)
    parser.add_argument('--key-deleted', action='store_true')
    args = parser.parse_args(argv)
    operation, rest = args.operation, args.arguments
    if operation in LOCAL_OPERATIONS:
        require(not in_ci(), operation + ' is a local operation')
    if operation == 'freeze':
        result = freeze(int(rest[0]), dry_run=args.dry_run)
    elif operation == 'trigger-paths':
        result = trigger_paths(int(rest[0]), rest[1:], args.message)
    elif operation == 'record':
        result = record(int(rest[0]), args.run, args.verification, args.api, args.key_deleted)
    elif operation == 'contract':
        result = contract(int(rest[0]) if rest else None, offline=args.offline)
    elif operation == 'materialize':
        result = materialize()
    elif operation == 'source-contract':
        result = save('standard-host-contract.json', verify_source())
    elif operation == 'baseline':
        result = baseline()
    elif operation == 'tests':
        result = run_group(rest[0])
    elif operation == 'await-tests':
        result = await_tests()
    elif operation == 'donor':
        result = donor()
    elif operation in ('download-rpcs3', 'install-rpcs3', 'rpcs3-exports', 'embed-rpcs3-source'):
        result = rpcs3_operation(operation, Path(rest[0]) if rest else None)
    elif operation == 'component-runs':
        result = component_runs()
    elif operation in ('dolphin', 'armsx2'):
        result = native_operation(operation)
    elif operation in ('authenticate-dolphin', 'authenticate-armsx2'):
        result = native_operation(operation.removeprefix('authenticate-'), install=False)
    elif operation in ('download-libretro', 'download-melonx-dependencies'):
        result = archive_operation(operation.removeprefix('download-'))
    elif operation == 'libretro':
        result = libretro()
    elif operation in ('download-melonx', 'melonx-evidence'):
        result = melonx_operation(operation)
    elif operation == 'neoswap-host':
        result = neoswap_host()
    elif operation in ('embed', 'structure', 'validate'):
        require(rest, 'Missing application or IPA path')
        result = globals()[operation](Path(rest[0]))
    elif operation == 'seal':
        result = seal()
    elif operation == 'diff-check':
        result = diff_check()
    else:
        result = republish()
    print(json.dumps(result, indent=2, default=str))
    if operation == 'freeze' and args.dry_run and not result['frozenWouldSucceed']:
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
