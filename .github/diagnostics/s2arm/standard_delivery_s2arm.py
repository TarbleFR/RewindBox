#!/usr/bin/env python3
"""Launcher of the standard delivery recipe for the Switch 2 (S2Arm) test line (IPA B, builds from 801).

The recipe (.github/diagnostics/standard_delivery.py) is imported unchanged; this file never writes it.
Only what ties the recipe to the common line is redirected, in memory, before its entry point runs:

  delivery side (the run that builds this IPA: our branch, our workflow, our request tag)
    BRANCH, WORKFLOW, TRIGGER, TRIGGER_MARKER   module constants
    subject_build                               its request tag is a literal in the recipe
    jobs_that_run                               its default branch was bound when the recipe was imported
    trigger_paths                               its default commit message carries the common tag
  producer side (the delivered base this IPA starts from: produced on the common line, or by this line)
    verify_base, authenticate_base              run with BRANCH = the branch of the base's own line

Nothing else changes: manifests stay under build-utils/delivery/, every check keeps its condition.
The redirection is refused when the recipe's uses of those constants are not exactly the reviewed
inventory below (RECIPE_INVENTORY), so a change of the recipe cannot be silently mis-redirected.

The S2Arm engine and its JIT helper (every build of this line from the first one that declares
s2arm.engine in its manifest): the engine frameworks come from a successful run of
.github/workflows/s2arm-engine.yml on this branch, authenticated through the API like the recipe's
component producers (rpcs3_core_component.py, melonx_*_core_component.py), and the closed extension
sets of the two common validators that have no S2Arm conditional of their own (verify_ipa.validate,
validate_rpcs3_ipa.validate_helper_bundles) gain S2ArmJITHelper.appex in memory, only for an application
that carries S2Arm-native-identity.json, and only while they run (EXTENSION_SETS, reviewed inventory).

Operations: every operation of the recipe (same arguments), plus
  request-guard     preflight: the run is on the line's branch and requests a build of this line
  recipient-guard   the recipient public key of this build is committed, is the manifest's and is the
                    one DELIVERY_RECIPIENT names (build-utils/delivery_cipher.py would otherwise fall
                    back to an old key when the variable is unset)
  inventory         print the recipe inventory this launcher was reviewed against, and the current one
  engine-download   authenticate the engine producer run and its artifact, download it, check its
                    files against the manifest (s2arm.engine) and the producer commit
  engine-embed APP  place S2ArmEngine.framework and NS2Pro.framework in APP/Frameworks, write
                    APP/S2Arm-native-identity.json
  engine-check-app APP   the built application: identity, frameworks byte for byte, JIT helper, engine bridge
  engine-check-ipa IPA   the signed IPA: distribution validator, identity, frameworks (payload
                    fingerprints, signed), JIT helper, signer receipt, engine bridge
  prepare-download  authenticate the producer run of the engine bridge's preparation library (s2arm-core.yml)
                    and its artifact, download it, check it against the manifest (s2arm.prepare), the
                    producer commit's pin and its sha256.txt
  prepare-install   unzip S2ArmPrepare.xcframework into packages/s2arm_engine_bridge/ios/Frameworks (the
                    path its podspec vendors), before the first pod install
  sysdata-download  authenticate the producer run of the system data (s2arm-prepare.yml) and its macOS
                    artifact, download it, check every file against its SHA256SUMS (s2arm.sysdata)
  sysdata-embed APP place the system data tree as APP/S2ArmSystemData, right before engine-embed
The engine bridge (packages/s2arm_engine_bridge) is checked in the application by engine-check-app and
engine-check-ipa, and recorded by engine-embed in S2Arm-native-identity.json: S2ArmSystemData complete
(SHA256SUMS) with its licences, S2ArmEngine.framework/S2ArmDirectChain.txt, the plugin registered by the
generated registrant, the Runner executable defining the bridge and preparation entry points (nm -gU),
leaving no rb_s2arm_* undefined (nm -u) and exporting rb_s2arm_engine_loaded (dyld export trie).
  dolphin-package   packages/dolphin_internal_bridge/ci/build_support.py package, unchanged, with the
                    S2Arm-aware extension set of its verify_ipa.validate
The recipe operations structure and seal run with the same S2Arm-aware extension sets.
"""
from __future__ import annotations

import ast
import functools
import hashlib
import importlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
RECIPE = '.github/diagnostics/standard_delivery.py'
VERIFIER = 'build-utils/verify_downloaded_delivery.py'

# --- The line ------------------------------------------------------------------------------------------
DELIVERY_BRANCH = 'work/s2arm-switch2-prototype-20261110'
WORKFLOW = '.github/workflows/s2arm-delivery.yml'
TRIGGER_MARKER = '[s2arm-delivery:'
TRIGGER = re.compile(r'\[s2arm-delivery:(\d{3,4})\]')
FIRST_BUILD = 801
RECIPIENT = 'build-utils/delivery-{build}-recipient.pem'
# The common line, as the recipe names it. A base is authenticated on the branch of the line that delivered it.
COMMON_BRANCH = 'Claude'
COMMON_WORKFLOW = '.github/workflows/standard-delivery.yml'
COMMON_TRIGGER_MARKER = '[ipa-delivery:'
BASE_LINES = {COMMON_WORKFLOW: COMMON_BRANCH, WORKFLOW: DELIVERY_BRANCH}

# --- Reviewed inventory of the recipe --------------------------------------------------------------------
# For every top-level function of the recipe: which line constants it reads and which line literals it
# quotes. Reviewed at .github/diagnostics/standard_delivery.py of commit 687ea833 (blob sha256 in the test).
LINE_NAMES = ('BRANCH', 'WORKFLOW', 'TRIGGER', 'TRIGGER_MARKER', 'MANIFESTS')
LINE_LITERALS = ('ipa-delivery', 'Claude', 'standard-delivery')
RECIPE_INVENTORY = {
    '<module>': ['BRANCH', 'MANIFESTS', 'TRIGGER', 'TRIGGER_MARKER', 'WORKFLOW', 'literal:Claude',
                 'literal:ipa-delivery', 'literal:standard-delivery'],
    'manifest_path': ['MANIFESTS'],
    'subject_build': ['TRIGGER', 'literal:ipa-delivery'],
    'verify_base': ['BRANCH'],
    'authenticate_base': ['BRANCH'],
    'reuse_guard': ['BRANCH', 'WORKFLOW'],
    'source_contract': ['BRANCH'],
    'materialize': ['literal:ipa-delivery'],
    'republish': ['WORKFLOW'],
    'freeze': ['BRANCH'],
    'jobs_that_run': ['BRANCH'],
    'trigger_paths': ['BRANCH', 'WORKFLOW', 'literal:Claude', 'literal:ipa-delivery'],
    'contract': ['MANIFESTS'],
    'record': ['BRANCH', 'WORKFLOW'],
}
# How each entry is handled (printed by `inventory`, asserted complete by the test).
HANDLING = {
    '<module>': 'constants: BRANCH, WORKFLOW, TRIGGER, TRIGGER_MARKER are assigned; MANIFESTS is kept',
    'manifest_path': 'kept: manifests of this line live in build-utils/delivery/ on this branch only',
    'subject_build': 'delivery side, replaced: the recipe quotes the common tag as a literal',
    'verify_base': 'producer side, wrapped: BRANCH is the base line branch while it runs',
    'authenticate_base': 'producer side, wrapped: BRANCH is the base line branch while it runs',
    'reuse_guard': 'delivery side, constants: the reused test run is an earlier run of this same build',
    'source_contract': 'delivery side, constant: GITHUB_REF_NAME is the line branch',
    'materialize': 'delivery side: calls the replaced subject_build; its literal is only a printed sentence',
    'republish': 'delivery side, constant: the republication record names this workflow',
    'freeze': 'delivery side, constant: checkout branch and origin/<branch> of the freeze',
    'jobs_that_run': 'delivery side, default argument rebound to the line branch',
    'trigger_paths': 'delivery side, constants; wrapped to give the default message the line tag',
    'contract': 'kept: the local default is the latest manifest of build-utils/delivery/',
    'record': 'delivery side, constants: the recorded run is this line\'s run and the receipt names its branch',
}
# What the downloaded-delivery verifier reads from the recipe module (attribute uses of `sd`).
VERIFIER_INVENTORY = {
    'api_binding': ['BRANCH', 'WORKFLOW', 'subject_build'],   # delivery side: the saved run of this build
    'verify': ['verify_base'],                                # producer side: wrapped
}


class LineError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise LineError(message)


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(source, prefix=None):
    """{function: sorted line constants read and line literals quoted}; with `prefix`, attribute uses of it."""
    attributes = set(LINE_NAMES) | {'subject_build', 'verify_base', 'authenticate_base'}

    def uses(node):
        found = set()
        for child in ast.walk(node):
            if prefix is None and isinstance(child, ast.Name) and child.id in LINE_NAMES:
                found.add(child.id)
            elif prefix and isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and \
                    child.value.id == prefix and child.attr in attributes:
                found.add(child.attr)
            elif prefix is None and isinstance(child, ast.Constant) and isinstance(child.value, str):
                found.update('literal:' + literal for literal in LINE_LITERALS if literal in child.value)
        return found
    result, module = {}, set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found = uses(node)
            if found:
                result[node.name] = sorted(found)
        else:
            module |= uses(node)
    if module:
        result['<module>'] = sorted(module)
    return result


def inventory_drift(actual, expected):
    """Readable differences between the current and the reviewed inventory (empty = identical)."""
    return [f'{name}: reviewed {expected.get(name)}, now {actual.get(name)}'
            for name in sorted(set(actual) | set(expected)) if actual.get(name) != expected.get(name)]


def check_recipe_inventory(root=ROOT):
    drift = inventory_drift(inventory((Path(root) / RECIPE).read_text()), RECIPE_INVENTORY)
    require(not drift, 'The standard recipe no longer uses its line constants as this launcher was reviewed for; '
            'review the launcher before any delivery of this line:\n- ' + '\n- '.join(drift))


def check_verifier_inventory(root=ROOT):
    drift = inventory_drift(inventory((Path(root) / VERIFIER).read_text(), prefix='sd'), VERIFIER_INVENTORY)
    require(not drift, 'The downloaded-delivery verifier no longer reads the recipe as this launcher was reviewed '
            'for:\n- ' + '\n- '.join(drift))


# --- Delivery side -------------------------------------------------------------------------------------

def subject_build(subject):
    """The build requested by `[s2arm-delivery:NNN]` at the start of the commit subject (None when absent).

    Same rules as the recipe's subject_build for its own tag: one tag at most, and it opens the subject.
    A build below 801 belongs to the shared sequence and is refused."""
    found = TRIGGER.findall(subject)
    require(len(found) <= 1, 'The commit subject requests several builds: ' + subject)
    if not found:
        return None
    require(subject.startswith(TRIGGER_MARKER + found[0] + ']'),
            'The delivery tag must start the commit subject: ' + subject)
    require(int(found[0]) >= FIRST_BUILD, f'Builds of the Switch 2 test line start at {FIRST_BUILD}: ' + subject)
    return int(found[0])


def recipient_path(build):
    return RECIPIENT.format(build=int(build))


# --- Producer side -------------------------------------------------------------------------------------

def base_branch(manifest):
    """The branch of the line that delivered the manifest's base, named by the base's workflow."""
    workflow = manifest['base'].get('workflow')
    require(workflow in BASE_LINES, 'The base was delivered by an unknown workflow: ' + repr(workflow))
    return BASE_LINES[workflow]


def on_base_line(sd, function):
    """Run a base check of the recipe with BRANCH = the branch of the base's own line, then restore it."""
    @functools.wraps(function)
    def wrapper(manifest, *arguments, **keywords):
        previous = sd.BRANCH
        sd.BRANCH = base_branch(manifest)
        try:
            return function(manifest, *arguments, **keywords)
        finally:
            sd.BRANCH = previous
    return wrapper


def with_line_message(function):
    @functools.wraps(function)
    def wrapper(build, paths, message=None, root=None, loader=None):
        message = message or f'{TRIGGER_MARKER}{build}] build(s2arm): request the private test IPA {build}'
        return function(build, paths, message, root, loader)
    return wrapper


# --- Configuration -------------------------------------------------------------------------------------

def load_recipe():
    """The recipe module under its own name, so every module that imports it gets the configured one."""
    for part in ('.github/diagnostics',):
        if str(ROOT / part) not in sys.path:
            sys.path.insert(0, str(ROOT / part))
    return importlib.import_module('standard_delivery')


def configure(sd=None):
    """Redirect the imported recipe to this line. Idempotent; refuses a recipe it was not reviewed for."""
    sd = sd or load_recipe()
    if getattr(sd, 'S2ARM_LINE', None) is not None:
        return sd
    check_recipe_inventory()
    require((sd.BRANCH, sd.WORKFLOW, sd.TRIGGER_MARKER, sd.MANIFESTS) ==
            (COMMON_BRANCH, COMMON_WORKFLOW, COMMON_TRIGGER_MARKER, 'build-utils/delivery') and
            sd.jobs_that_run.__defaults__ == (COMMON_BRANCH,) and
            sd.is_recipe(recipient_path(FIRST_BUILD)) and sd.is_recipe(WORKFLOW),
            'The standard recipe is not the common-line recipe this launcher redirects')
    sd.BRANCH = DELIVERY_BRANCH
    sd.WORKFLOW = WORKFLOW
    sd.TRIGGER = TRIGGER
    sd.TRIGGER_MARKER = TRIGGER_MARKER
    sd.subject_build = subject_build
    sd.jobs_that_run.__defaults__ = (DELIVERY_BRANCH,)
    sd.trigger_paths = with_line_message(sd.trigger_paths)
    sd.verify_base = on_base_line(sd, sd.verify_base)
    sd.authenticate_base = on_base_line(sd, sd.authenticate_base)
    sd.S2ARM_LINE = dict(branch=DELIVERY_BRANCH, workflow=WORKFLOW, tag=TRIGGER_MARKER, firstBuild=FIRST_BUILD,
                         baseLines=dict(BASE_LINES))
    return sd


# --- Operations of this line ---------------------------------------------------------------------------

def request_guard(sd, environment=None, repo=None):
    """Preflight, right after the effective tree is restored: the run is on the line branch and its head commit
    requests one build of this line; a manual run must name that same build."""
    environment = os.environ if environment is None else environment
    require(environment.get('GITHUB_REF_NAME') == DELIVERY_BRANCH and
            environment.get('GITHUB_REF', 'refs/heads/' + DELIVERY_BRANCH) == 'refs/heads/' + DELIVERY_BRANCH,
            'A delivery of this line runs on ' + DELIVERY_BRANCH + ' only')
    event = environment.get('GITHUB_EVENT_NAME', '')
    require(event in ('push', 'workflow_dispatch'), 'Unexpected event: ' + repr(event))
    repo = repo or sd.Repo()
    head = repo.commit('HEAD')
    require(head == environment.get('GITHUB_SHA', head), 'Checkout differs from the triggering source')
    requested = subject_build(repo.subject(head))
    require(requested is not None, 'The head commit subject does not start with ' + TRIGGER_MARKER + 'N]')
    if event == 'workflow_dispatch':
        asked = environment.get('REQUESTED_BUILD', '')
        require(asked.isdecimal() and int(asked) == requested,
                f'The manual run asks for build {asked!r} but the head commit requests {requested}')
    return dict(result='accepted', event=event, branch=DELIVERY_BRANCH, build=requested, source=head)


def recipient_guard(sd, environment=None, manifest=None):
    """The recipient public key of this build, and no other, receives the delivery."""
    environment = os.environ if environment is None else environment
    manifest = manifest or sd.ci_manifest()
    root = sd.ROOT
    expected = recipient_path(manifest['build'])
    value = environment.get('DELIVERY_RECIPIENT', '')
    require(value, 'DELIVERY_RECIPIENT is not set: delivery_cipher.py would encrypt to an old key')
    require(value == expected == manifest['recipient']['path'],
            f'The recipient of build {manifest["build"]} must be {expected} (variable {value!r}, manifest '
            f'{manifest["recipient"]["path"]!r})')
    require((Path(root) / expected).is_file(), 'The recipient public key is not committed: ' + expected)
    result = sd.recipient_check(manifest, environment)
    reused = sorted(path.name for path in (Path(root) / 'build-utils').glob('delivery-*-recipient.pem')
                    if path.name != Path(expected).name and sha_file(path) == result['sha256'])
    require(not reused, 'The recipient key of this build is the key of an earlier delivery: ' + ', '.join(reused))
    return dict(result='accepted', build=manifest['build'], **result)


# --- The S2Arm engine and its JIT helper --------------------------------------------------------------
# The producer: a successful run of the engine workflow on this branch. Its artifact (the contract the
# producer step of s2arm-engine.yml follows) is named after the run's commit and holds the two framework
# archives and their identity:
#   S2ArmEngine.framework.zip, NS2Pro.framework.zip   members <Name>.framework/..., no symbolic link
#   s2arm-engine-identity.json   {run, attempt, head_sha, s2arm_commit, patches: [{name, sha256}],
#                                 files: {<zip name>: sha256} for exactly the two archives}
# The manifest of a build that carries the engine names the run and the archive digests:
#   s2arm.engine = {workflow: .github/workflows/s2arm-engine.yml, run: <id>, zips: {<zip name>: sha256}}
ENGINE_WORKFLOW = '.github/workflows/s2arm-engine.yml'
ENGINE_ARTIFACT = 's2arm-engine-framework-{source}'
ENGINE_IDENTITY = 's2arm-engine-identity.json'
ENGINE_FRAMEWORKS = ('S2ArmEngine', 'NS2Pro')
ENGINE_ZIPS = tuple(f'{name}.framework.zip' for name in ENGINE_FRAMEWORKS)
ENGINE_DOWNLOAD = 'dist/s2arm-engine'
ENGINE_PATCHES = 'build-utils/s2arm/engine/patches/'
ENGINE_PIN = 'tools/s2arm_prototype/pin.json'
PACKAGED_IDENTITY = 'S2Arm-native-identity.json'
HELPER = 'S2ArmJITHelper.appex'
HELPER_EXECUTABLE = 'S2ArmJITHelper'
HELPER_SCRIPT = 'packages/s2arm_jit_helper/ios/Resources/s2arm-universal.js'
HELPER_REQUEST_TYPE = 'com.neogamelab.neostation.s2arm-jit-request'
STIKJIT = '@rpath/StikJIT.framework/StikJIT'
ENGINE_IMAGES = tuple(f'Frameworks/{name}.framework/{name}' for name in ENGINE_FRAMEWORKS) + (
    f'PlugIns/{HELPER}/{HELPER_EXECUTABLE}',)
HEX40 = re.compile(r'[0-9a-f]{40}')
HEX64 = re.compile(r'[0-9a-f]{64}')
MACHO_MAGICS = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xce',
                b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf', b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca'}
# Common validators with a closed extension set and no S2Arm conditional of their own: {path: (module,
# function that copies EXPECTED_HELPERS once, function that must call it by name or None)}. Reviewed at
# 37c650b (both files identical on Claude 4142792). A file that names S2Arm handles it itself: not extended.
EXTENSION_SETS = {
    'packages/dolphin_internal_bridge/ci/verify_ipa.py': ('verify_ipa', 'validate', None),
    'build-utils/validate_rpcs3_ipa.py': ('validate_rpcs3_ipa', 'validate_helper_bundles', 'validate_ipa'),
}
# The reviewed in-memory edit of the downloaded-delivery verifier (verify_downloaded_delivery_s2arm.py):
# the application has one more extension when it carries the S2Arm identity. (old, new, occurrences)
VERIFIER_EDITS = (
    ('        require(len(bundles) == 8 and all(',
     "        require(len(bundles) == 8 + (root + 'S2Arm-native-identity.json' in names) and all(", 1),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def on_path(*parts):
    for part in parts:
        if str(ROOT / part) not in sys.path:
            sys.path.insert(0, str(ROOT / part))


def distribution():
    on_path('build-utils')
    return importlib.import_module('validate_single_ipa_distribution')


def engine_errors(spec):
    """Problems of an s2arm.engine pin (empty list = well formed)."""
    if not isinstance(spec, dict) or set(spec) != {'workflow', 'run', 'zips'}:
        return ['s2arm.engine must hold exactly workflow, run and zips']
    errors = []
    if spec['workflow'] != ENGINE_WORKFLOW:
        errors.append('s2arm.engine.workflow must be ' + ENGINE_WORKFLOW)
    if not (type(spec['run']) is int and spec['run'] > 0):
        errors.append('s2arm.engine.run must be the id of the producer run')
    zips = spec['zips']
    if not (isinstance(zips, dict) and set(zips) == set(ENGINE_ZIPS) and
            all(isinstance(value, str) and HEX64.fullmatch(value) for value in zips.values())):
        errors.append('s2arm.engine.zips must give the SHA-256 of ' + ' and '.join(ENGINE_ZIPS))
    return errors


def engine_spec(manifest):
    """The engine pin of a build of this line; a build without one is refused (this workflow embeds it)."""
    spec = manifest.get('s2arm', {}).get('engine')
    require(spec is not None, f'Build {manifest.get("build")} declares no S2Arm engine (s2arm.engine): every build of '
            'this workflow carries the engine and its JIT helper')
    errors = engine_errors(spec)
    require(not errors, '; '.join(errors))
    return spec


def producer_origin(spec, get, repo, workflow, artifact_name, label):
    """A producer through the API: a successful run of `workflow` on this branch, whose commit is in the delivered
    history, and the one unexpired artifact `artifact_name` names after that commit."""
    run = get(f'actions/runs/{spec["run"]}')
    require(run.get('id') == spec['run'] and run.get('path') == workflow and
            run.get('head_branch') == DELIVERY_BRANCH and run.get('status') == 'completed' and
            run.get('conclusion') == 'success' and type(run.get('run_attempt')) is int and
            HEX40.fullmatch(str(run.get('head_sha'))),
            f'Run {spec["run"]} is not a successful {workflow} run of {DELIVERY_BRANCH}: '
            f'{run.get("path")} {run.get("head_branch")} {run.get("status")}/{run.get("conclusion")}')
    source = run['head_sha']
    require(repo.is_ancestor(source, 'HEAD'), f'The {label} producer commit {source} is not in the delivered history')
    name = artifact_name.format(source=source)
    listing = get(f'actions/runs/{spec["run"]}/artifacts?name={name}&per_page=100')
    found = [item for item in listing.get('artifacts', []) if item.get('name') == name]
    require(len(found) == 1, f'Run {spec["run"]} has {len(found)} artifacts named {name}, not one')
    artifact = found[0]
    digest = str(artifact.get('digest') or '')
    require(type(artifact.get('id')) is int and type(artifact.get('size_in_bytes')) is int and
            artifact.get('expired') is False and artifact.get('workflow_run', {}).get('id') == run['id'] and
            artifact['workflow_run'].get('head_sha') == source and digest.startswith('sha256:') and
            HEX64.fullmatch(digest[len('sha256:'):]), f'Wrong or expired {label} artifact {name}')
    return dict(workflow=workflow, branch=DELIVERY_BRANCH, run=run['id'], attempt=run['run_attempt'],
                source=source, conclusion=run['conclusion'],
                artifact=dict(id=artifact['id'], name=name, bytes=artifact['size_in_bytes'],
                              sha256=digest[len('sha256:'):], expiresAt=artifact.get('expires_at')))


def engine_origin(spec, get, repo):
    """The engine producer: a successful run of the engine workflow on this branch, whose commit is in the delivered
    history, and the one unexpired artifact named after that commit."""
    return producer_origin(spec, get, repo, ENGINE_WORKFLOW, ENGINE_ARTIFACT, 'engine')


def safe_archive(archive, label):
    names = archive.namelist()
    require(len(names) == len(set(names)) and archive.testzip() is None, f'{label}: duplicate or corrupt member')
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        require(entry.filename and not path.is_absolute() and '..' not in path.parts and '\\' not in entry.filename,
                f'{label}: unsafe member {entry.filename}')
        require(not stat.S_ISLNK(entry.external_attr >> 16), f'{label}: symbolic link {entry.filename}')
    return names


def producer_patches(repo, source):
    """[{name, sha256}] of the patch series the engine workflow applies at the producer commit (sorted)."""
    paths = sorted(path for path in repo.entries(source) if path.startswith(ENGINE_PATCHES) and
                   path.endswith('.patch') and '/' not in path[len(ENGINE_PATCHES):])
    return [dict(name=path[len(ENGINE_PATCHES):], sha256=sha(repo.show(source, path))) for path in paths]


def engine_artifact(spec, origin, raw, repo):
    """The producer archive's members, checked against the API, the manifest and the producer commit."""
    require(len(raw) == origin['artifact']['bytes'] and sha(raw) == origin['artifact']['sha256'],
            'The downloaded engine artifact differs from the API record')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [name for name in safe_archive(archive, origin['artifact']['name']) if not name.endswith('/')]
        require(sorted(names) == sorted(ENGINE_ZIPS + (ENGINE_IDENTITY,)),
                f'The engine artifact must hold exactly {", ".join(ENGINE_ZIPS)} and {ENGINE_IDENTITY}: {sorted(names)}')
        files = {name: archive.read(name) for name in names}
    digests = {name: sha(files[name]) for name in ENGINE_ZIPS}
    require(digests == spec['zips'], f'The engine archives differ from the manifest: {digests}')
    identity = json.loads(files[ENGINE_IDENTITY])
    require(isinstance(identity, dict) and set(identity) >= {'run', 'attempt', 'head_sha', 's2arm_commit', 'patches',
                                                               'files'}, 'Incomplete ' + ENGINE_IDENTITY)
    require(identity['run'] == origin['run'] and identity['head_sha'] == origin['source'] and
            type(identity['attempt']) is int and 1 <= identity['attempt'] <= origin['attempt'],
            f'{ENGINE_IDENTITY} names another run, attempt or commit than its producer')
    require(identity['files'] == digests, f'{ENGINE_IDENTITY} files differ from the archives')
    pin = json.loads(repo.show(origin['source'], ENGINE_PIN))['s2arm']['commit']
    require(identity['s2arm_commit'] == pin, f'{ENGINE_IDENTITY} names S2Arm {identity["s2arm_commit"]}, the producer '
            f'commit pins {pin}')
    patches = producer_patches(repo, origin['source'])
    require(identity['patches'] == patches, f'{ENGINE_IDENTITY} patches differ from {ENGINE_PATCHES} at the producer '
            f'commit: {identity["patches"]} != {patches}')
    return files, identity


def framework_inventory(name, raw):
    """One engine framework archive: its members under <name>.framework/, its Info.plist and its one Mach-O
    image (an arm64 iOS dylib with install name @rpath/<name>.framework/<name>, linking only the system and the
    other engine framework)."""
    on_path('packages/dolphin_internal_bridge/ci', '.github/diagnostics')
    from verify_ipa import macho
    from rewind607_delivery import payload_record
    prefix = f'{name}.framework/'
    files = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in safe_archive(archive, f'{name}.framework.zip'):
            require(member.startswith(prefix), f'{name}.framework.zip member outside {prefix}: {member}')
            if member.endswith('/'):
                continue
            relative = member[len(prefix):]
            parts = PurePosixPath(relative).parts
            require(not any(part.endswith(('.framework', '.appex', '.app')) for part in parts[:-1]) and
                    not relative.endswith('.dylib'), f'Nested bundle or library in {name}.framework: {relative}')
            files[relative] = archive.read(member)
    require(name in files and 'Info.plist' in files, f'{name}.framework lacks its executable or Info.plist')
    info = plistlib.loads(files['Info.plist'])
    require(isinstance(info, dict) and info.get('CFBundleExecutable') == name and
            info.get('CFBundlePackageType') == 'FMWK', f'{name}.framework/Info.plist is not this framework')
    images = sorted(path for path, data in files.items() if data[:4] in MACHO_MAGICS)
    require(images == [name], f'{name}.framework must hold one Mach-O image, its executable: {images}')
    record = payload_record(files[name])
    image = macho(files[name])
    require(image['fileType'] == 6 and image['id'] == f'@rpath/{name}.framework/{name}',
            f'{name} is not a dylib with install name @rpath/{name}.framework/{name}: {image["fileType"]} {image["id"]}')
    others = {f'@rpath/{other}.framework/{other}' for other in ENGINE_FRAMEWORKS if other != name}
    for dependency in image['dependencies']:
        require(dependency['path'].startswith(('/usr/lib/', '/System/Library/')) or dependency['path'] in others,
                f'{name} links {dependency["path"]}: an engine framework links only the system and the other one')
    return dict(image=f'Frameworks/{name}.framework/{name}', files={path: sha(data) for path, data in sorted(files.items())},
                payloadFingerprint=record['fingerprint'], container=record['container'], installName=image['id'],
                dependencies=sorted(item['path'] for item in image['dependencies']), minimumOS=image['minimumOS'],
                bytes=len(files[name]))


def helper_contract():
    contract = distribution().S2ARM_EXTENSIONS[HELPER]
    return dict(bundle=HELPER, executable=HELPER_EXECUTABLE, requestType=HELPER_REQUEST_TYPE, **contract)


def check_helper(read, names, host, source_script, signed):
    """The S2Arm JIT helper inside an application (read(relative path) -> bytes; names: relative paths)."""
    on_path('packages/dolphin_internal_bridge/ci')
    from verify_ipa import macho
    contract = helper_contract()
    root = f'PlugIns/{HELPER}/'
    info = plistlib.loads(read(root + 'Info.plist'))
    metadata = info.get('NSExtension', {})
    require(info.get('CFBundleExecutable') == HELPER_EXECUTABLE and info.get('CFBundlePackageType') == 'XPC!' and
            info.get('CFBundleIdentifier') == host['CFBundleIdentifier'] + contract['bundleSuffix'] and
            info.get(contract['marker']) == '1' and
            metadata.get('NSExtensionPrincipalClass') == contract['principalClass'] and
            metadata.get('NSExtensionPointIdentifier') == 'com.apple.share-services' and
            info.get('CFBundleVersion') == host['CFBundleVersion'] and
            info.get('CFBundleShortVersionString') == host['CFBundleShortVersionString'],
            f'{HELPER} does not carry the S2Arm helper contract or the host versions')
    script = read(root + 's2arm-universal.js')
    require(script == source_script, f'{HELPER}/s2arm-universal.js differs from {HELPER_SCRIPT}')
    images = sorted(name for name in names if name.startswith(root) and read(name)[:4] in MACHO_MAGICS)
    require(images == [root + HELPER_EXECUTABLE], f'{HELPER} must hold one Mach-O image, its executable: {images}')
    executable = read(root + HELPER_EXECUTABLE)
    distribution().require_arm64_executable(executable, HELPER)
    image = macho(executable)
    require(any(item['path'] == STIKJIT for item in image['dependencies']) and
            '@executable_path/../../Frameworks' in image['rpaths'],
            f'{HELPER} does not link the shared StikJIT of the host')
    require(image['codeSignature'] is True or not signed, f'{HELPER} is not signed')
    return dict(contract, scriptSHA256=sha(script), executableBytes=len(executable), signed=image['codeSignature'])


def check_frameworks(read, names, identity, signed):
    """The engine frameworks inside an application against the packaged identity: every file byte for byte
    (before signing), or every file but the signature byte for byte and the image payload fingerprint (after)."""
    on_path('packages/dolphin_internal_bridge/ci', '.github/diagnostics')
    from verify_ipa import macho
    from rewind607_delivery import payload_record

    def sealed(path):   # what signing writes or rewrites
        return signed and path.startswith('_CodeSignature/')
    result = {}
    for name in ENGINE_FRAMEWORKS:
        expected = identity['frameworks'][name]
        prefix = f'Frameworks/{name}.framework/'
        present = sorted(item[len(prefix):] for item in names if item.startswith(prefix) and not item.endswith('/'))
        require([path for path in present if not sealed(path)] == [path for path in expected['files'] if not sealed(path)],
                f'{name}.framework files differ from the packaged identity')
        for path, digest in expected['files'].items():
            if not sealed(path) and (path != name or not signed):
                require(sha(read(prefix + path)) == digest, f'{name}.framework/{path} differs from the producer archive')
        raw = read(prefix + name)
        require(payload_record(raw)['fingerprint'] == expected['payloadFingerprint'], f'{name} payload changed')
        signature = macho(raw)['codeSignature']
        require(signature is True or not signed, f'{name} is not signed')
        result[name] = dict(image=expected['image'], payloadFingerprint=expected['payloadFingerprint'],
                            files=len(present), signed=signature)
    return result


def engine_download(sd, get=None, download=None, repo=None, root=None):
    """engine-download: the producer through the API, its artifact downloaded and checked, its files extracted."""
    manifest = sd.ci_manifest()
    spec = engine_spec(manifest)
    repo = repo or sd.Repo()
    origin = engine_origin(spec, get or sd.api, repo)
    target = Path(root or sd.ROOT) / ENGINE_DOWNLOAD
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    archive = target / 'artifact.zip'
    (download or sd.download_artifact)(origin['artifact']['id'], archive)
    files, identity = engine_artifact(spec, origin, archive.read_bytes(), repo)
    for name, data in files.items():
        (target / name).write_bytes(data)
    for name in ENGINE_FRAMEWORKS:
        framework_inventory(name, files[f'{name}.framework.zip'])
    return sd.save('s2arm-engine-download.json', dict(result='authenticated', build=manifest['build'], producer=origin,
                                                      zips=spec['zips'], identity=identity,
                                                      identitySHA256=sha(files[ENGINE_IDENTITY]),
                                                      directory=ENGINE_DOWNLOAD))


def packaged_identity(manifest, record, inventories, script, bridge=None):
    """S2Arm-native-identity.json; `bridge` adds the engine bridge pieces (prepare, systemData, bridge)."""
    return dict(schema=1, engine='S2Arm', build=manifest['build'], producer=record['producer'],
                sourceIdentity=record['identity'], sourceIdentitySHA256=record['identitySHA256'], zips=record['zips'],
                frameworks=inventories, jitHelper=dict(helper_contract(), scriptSHA256=sha(script)),
                **(bridge or {}), physicalDeviceTested=False)


def engine_embed(sd, app, root=None):
    """engine-embed APP: both frameworks into APP/Frameworks (never over an existing one), and the identity."""
    root = Path(root or sd.ROOT)
    app = Path(app)
    manifest = sd.ci_manifest()
    spec = engine_spec(manifest)
    record = json.loads((sd.OUT / 's2arm-engine-download.json').read_bytes())
    require(record['result'] == 'authenticated' and record['build'] == manifest['build'] and record['zips'] == spec['zips'],
            'The engine download record is not this build\'s')
    require(app.is_dir() and (app / 'Info.plist').is_file(), f'Missing built application: {app}')
    require(not (app / PACKAGED_IDENTITY).exists(), f'{PACKAGED_IDENTITY} is already in the application')
    inventories = {}
    for name in ENGINE_FRAMEWORKS:
        raw = (root / ENGINE_DOWNLOAD / f'{name}.framework.zip').read_bytes()
        require(sha(raw) == spec['zips'][f'{name}.framework.zip'], f'{name}.framework.zip changed after its download')
        inventories[name] = framework_inventory(name, raw)
        require(not (app / 'Frameworks' / f'{name}.framework').exists(), f'{name}.framework is already in the application')
    with zipfile.ZipFile(root / ENGINE_DOWNLOAD / 'S2ArmEngine.framework.zip') as archive:
        member = f'S2ArmEngine.framework/{DIRECT_CHAIN}'
        require(member in archive.namelist(), f'S2ArmEngine.framework has no {DIRECT_CHAIN}: the bridge stamps each '
                'prepared game with that direct shader chain version')
        chain = direct_chain(archive.read(member), member)
    bridge = bridge_pieces(sd, manifest, app, root, chain)
    for name in ENGINE_FRAMEWORKS:
        with zipfile.ZipFile(root / ENGINE_DOWNLOAD / f'{name}.framework.zip') as archive:
            for member in archive.infolist():
                if member.filename.endswith('/'):
                    continue
                target = app / 'Frameworks' / member.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
                target.chmod(0o755 if member.filename == f'{name}.framework/{name}' else 0o644)
    script = (root / HELPER_SCRIPT).read_bytes()
    text = json.dumps(packaged_identity(manifest, record, inventories, script, bridge), indent=2, sort_keys=True) + '\n'
    (app / PACKAGED_IDENTITY).write_text(text)
    return sd.save('s2arm-engine-embed.json', dict(result='embedded', build=manifest['build'], app=str(app),
                                                   identity=PACKAGED_IDENTITY, identitySHA256=sha(text.encode()),
                                                   images=list(ENGINE_IMAGES)))


def engine_check_app(sd, app, root=None):
    """engine-check-app APP: identity as embedded, frameworks byte for byte, JIT helper and engine bridge (system data,
    direct chain, registrant, Runner executable), before packaging."""
    root = Path(root or sd.ROOT)
    app = Path(app)
    manifest = sd.ci_manifest()
    spec = engine_spec(manifest)
    record = json.loads((sd.OUT / 's2arm-engine-embed.json').read_bytes())
    raw = (app / PACKAGED_IDENTITY).read_bytes()
    require(record['build'] == manifest['build'] and sha(raw) == record['identitySHA256'],
            f'{PACKAGED_IDENTITY} differs from the one embedded')
    identity = json.loads(raw)
    require(identity['zips'] == spec['zips'] and identity['producer']['run'] == spec['run'],
            f'{PACKAGED_IDENTITY} is not the manifest\'s engine')
    names = [path.relative_to(app).as_posix() for path in app.rglob('*') if path.is_file()]

    def read(relative):
        return (app / relative).read_bytes()
    host = plistlib.loads(read('Info.plist'))
    helper = check_helper(read, names, host, (root / HELPER_SCRIPT).read_bytes(), signed=False)
    frameworks = check_frameworks(read, names, identity, signed=False)
    bridge = check_bridge(read, names, identity, prepare_spec(manifest), sysdata_spec(manifest), host, registrant=root)
    return sd.save('s2arm-engine-app.json', dict(result='passed', build=manifest['build'], app=str(app),
                                                 identitySHA256=record['identitySHA256'], helper=helper,
                                                 frameworks=frameworks, bridge=bridge, physicalDeviceTested=False))


def check_engine_ipa(ipa, spec, script, identity_sha=None, signed_images=None, *, prepare, sysdata):
    """The engine in a signed IPA (engine-check-ipa in CI, and the offline verification of a download); `prepare` and
    `sysdata` are the manifest's s2arm.prepare and s2arm.sysdata, checked against the engine bridge it carries."""
    report = distribution().validate(Path(ipa))
    bundles = {item['bundle']: item for item in report['embeddedExtensions']}
    require(HELPER in bundles, f'The distribution validator did not see {HELPER}')
    on_path('.github/diagnostics')
    from rewind607_delivery import zip_payloads
    payloads = {name: record['fingerprint'] for name, record in zip_payloads(Path(ipa)).items()}
    with zipfile.ZipFile(ipa) as archive:
        prefix = 'Payload/NeoStation.app/'
        names = [name[len(prefix):] for name in archive.namelist() if name.startswith(prefix)]

        def read(relative):
            return archive.read(prefix + relative)
        raw = read(PACKAGED_IDENTITY)
        require(identity_sha is None or sha(raw) == identity_sha, f'{PACKAGED_IDENTITY} differs from the one embedded')
        identity = json.loads(raw)
        require(identity['zips'] == spec['zips'] and identity['producer']['run'] == spec['run'] and
                identity['producer']['workflow'] == ENGINE_WORKFLOW and identity['physicalDeviceTested'] is False,
                f'{PACKAGED_IDENTITY} is not the manifest\'s engine')
        host = plistlib.loads(read('Info.plist'))
        require(str(host['CFBundleVersion']) == str(identity['build']), f'{PACKAGED_IDENTITY} is another build\'s')
        helper = check_helper(read, names, host, script, signed=True)
        require(helper['scriptSHA256'] == identity['jitHelper']['scriptSHA256'], 'The helper script is not the embedded one')
        frameworks = check_frameworks(read, names, identity, signed=True)
        bridge = check_bridge(read, names, identity, prepare, sysdata, host)
    for image in ENGINE_IMAGES:
        require(image in payloads, f'{image} is not in the signed inventory')
        require(signed_images is None or signed_images.get(image) == payloads[image],
                f'{image} differs from the signer receipt')
    return dict(result='passed', ipaSHA256=sha_file(ipa), distributionBundles=sorted(bundles),
                distributionHelper=bundles[HELPER], helper=helper, frameworks=frameworks, bridge=bridge,
                identitySHA256=sha(raw), producer=identity['producer'],
                images={image: payloads[image] for image in ENGINE_IMAGES}, physicalDeviceTested=False)


def engine_check_ipa(sd, ipa, root=None):
    """engine-check-ipa IPA: the signed IPA, after the recipe's own validation."""
    root = Path(root or sd.ROOT)
    manifest = sd.ci_manifest()
    spec = engine_spec(manifest)
    require(set(ENGINE_IMAGES) <= set(manifest['images']['added']), 'The manifest does not declare the engine images')
    record = json.loads((sd.OUT / 's2arm-engine-embed.json').read_bytes())
    signed = json.loads((sd.OUT / 'signed-payload-identity.json').read_bytes())
    require(signed['ipaSha256'] == sha_file(ipa), 'The signer receipt is not this IPA\'s')
    result = check_engine_ipa(ipa, spec, (root / HELPER_SCRIPT).read_bytes(), record['identitySHA256'], signed['images'],
                              prepare=prepare_spec(manifest), sysdata=sysdata_spec(manifest))
    return sd.save('s2arm-engine-ipa.json', dict(result, build=manifest['build'], ipa=str(ipa)))


# --- The engine bridge: its preparation library and the system data -------------------------------------------
# packages/s2arm_engine_bridge, a plugin of the root pubspec.yaml, is linked statically into Runner with
# S2ArmPrepare.xcframework (the rb_s2arm_* entry points) and reads the system data from Runner.app/S2ArmSystemData.
# Neither is committed: both come from successful runs of this branch's producers, authenticated like the engine.
#   s2arm-core.yml     artifact S2ArmPrepare-<commit>: S2ArmPrepare.xcframework.zip (S2ArmPrepare.xcframework/: one
#                      static iOS arm64 library and its headers), sha256.txt (that zip and libS2ArmPrepare.a),
#                      undefined.txt (nm -u of the library), S2ArmPrepare-identity.json
#                      {component, source, s2arm, dependencies, sha256 (= sha256.txt), xcode}
#                      (build-utils/s2arm/build_prepare_xcframework.sh)
#   s2arm-prepare.yml  artifact s2arm-sysdata-macOS-<commit>: systemdata/, licenses/, SOURCES.tsv and SHA256SUMS,
#                      which lists every other file (tools/s2arm_prototype/build_sysdata_bundle.sh)
# The manifest of a build of this line names the runs and digests:
#   s2arm.prepare = {workflow: .github/workflows/s2arm-core.yml, run: <id>, zip: <SHA-256 of S2ArmPrepare.xcframework.zip>}
#   s2arm.sysdata = {workflow: .github/workflows/s2arm-prepare.yml, run: <id>, tree: <SHA-256 of its SHA256SUMS>}
# The whole tree is shipped as Runner.app/S2ArmSystemData (its licences and provenance with the data); the bridge
# gives the engine its systemdata/ folder.
PREPARE_WORKFLOW = '.github/workflows/s2arm-core.yml'
PREPARE_ARTIFACT = 'S2ArmPrepare-{source}'
PREPARE_ZIP = 'S2ArmPrepare.xcframework.zip'
PREPARE_SUMS = 'sha256.txt'
PREPARE_UNDEFINED = 'undefined.txt'
PREPARE_IDENTITY = 'S2ArmPrepare-identity.json'
PREPARE_MEMBERS = (PREPARE_ZIP, PREPARE_SUMS, PREPARE_UNDEFINED, PREPARE_IDENTITY)
PREPARE_XCFRAMEWORK = 'S2ArmPrepare.xcframework'
PREPARE_LIBRARY = 'libS2ArmPrepare.a'
PREPARE_DOWNLOAD = 'dist/s2arm-prepare'
BRIDGE_PACKAGE = 'packages/s2arm_engine_bridge'
BRIDGE_PODSPEC = BRIDGE_PACKAGE + '/ios/s2arm_engine_bridge.podspec'
BRIDGE_FRAMEWORKS = BRIDGE_PACKAGE + '/ios/Frameworks'
BRIDGE_VENDORED = f"s.vendored_frameworks = 'Frameworks/{PREPARE_XCFRAMEWORK}'"
BRIDGE_PLUGIN = 'S2ArmEngineBridgePlugin'
BRIDGE_REGISTRANT = 'ios/Runner/GeneratedPluginRegistrant.m'
BRIDGE_REGISTRATION = f'[{BRIDGE_PLUGIN} registerWithRegistrar:[registry registrarForPlugin:@"{BRIDGE_PLUGIN}"]];'
# The same call in the registrant Flutter generates, whatever its spacing.
BRIDGE_REGISTERED = re.compile(r'\[\s*' + BRIDGE_PLUGIN + r'\s+registerWithRegistrar:\s*\[\s*registry\s+registrarForPlugin:'
                               r'\s*@"' + BRIDGE_PLUGIN + r'"\s*\]\s*\]\s*;')
ENGINE_LOADED = '_rb_s2arm_engine_loaded'
# Every rb_s2arm_* function of S2ArmPrepare the bridge calls (packages/s2arm_engine_bridge/ios/Classes/S2ArmPrepareABI.h).
PREPARE_ENTRY_POINTS = tuple('_rb_s2arm_' + name for name in (
    'caps', 'direct_skeleton', 'module_dir', 'ns2_detect', 'ns2_dump', 'prepare_code', 'resource_pack'))
# What the Runner executable must define once the bridge pod and S2ArmPrepare are linked into it (nm -gU).
RUNNER_DEFINES = ('_OBJC_CLASS_$_' + BRIDGE_PLUGIN, ENGINE_LOADED, '_rb_s2arm_engine_mark_loading') + PREPARE_ENTRY_POINTS
# Both are linked into Runner: neither may be packaged as an image or a library of its own.
SEPARATE_IMAGES = ('s2arm_engine_bridge.framework', PREPARE_XCFRAMEWORK, PREPARE_LIBRARY)
DIRECT_CHAIN = 'S2ArmDirectChain.txt'
SYSDATA_WORKFLOW = '.github/workflows/s2arm-prepare.yml'
SYSDATA_ARTIFACT = 's2arm-sysdata-macOS-{source}'
SYSDATA_SUMS = 'SHA256SUMS'
SYSDATA_SOURCES = 'SOURCES.tsv'
SYSDATA_TOPS = ('systemdata/', 'licenses/')
SYSDATA_TZ_LICENCE = 'licenses/tzdata/LICENSE'
SYSDATA_FONT_LICENCES = 'licenses/fonts/OFL'
SYSDATA_DOWNLOAD = 'dist/s2arm-sysdata'
SYSTEM_DATA = 'S2ArmSystemData'
# The folder of it the bridge links as each game's resource pack systemdata (S2ArmGamePreparation.m, S2ArmShippedSystemData).
SYSTEM_DATA_READ = SYSTEM_DATA + '/systemdata'
BUNDLE_SUFFIXES = ('.app', '.appex', '.framework', '.xcframework', '.bundle', '.dylib')


def pin_errors(spec, key, workflow, digest):
    """Problems of an s2arm.<key> producer pin {workflow, run, <digest>} (empty list = well formed)."""
    if not isinstance(spec, dict) or set(spec) != {'workflow', 'run', digest}:
        return [f's2arm.{key} must hold exactly workflow, run and {digest}']
    errors = []
    if spec['workflow'] != workflow:
        errors.append(f's2arm.{key}.workflow must be {workflow}')
    if not (type(spec['run']) is int and spec['run'] > 0):
        errors.append(f's2arm.{key}.run must be the id of the producer run')
    if not (isinstance(spec[digest], str) and HEX64.fullmatch(spec[digest])):
        errors.append(f's2arm.{key}.{digest} must be a SHA-256')
    return errors


def prepare_errors(spec):
    return pin_errors(spec, 'prepare', PREPARE_WORKFLOW, 'zip')


def sysdata_errors(spec):
    return pin_errors(spec, 'sysdata', SYSDATA_WORKFLOW, 'tree')


def bridge_spec(manifest, key, errors_of, what):
    spec = manifest.get('s2arm', {}).get(key)
    require(spec is not None, f'Build {manifest.get("build")} declares no {what} (s2arm.{key}): every build of this '
            'workflow carries the engine bridge (packages/s2arm_engine_bridge in pubspec.yaml)')
    errors = errors_of(spec)
    require(not errors, '; '.join(errors))
    return spec


def prepare_spec(manifest):
    return bridge_spec(manifest, 'prepare', prepare_errors, 'S2Arm preparation library')


def sysdata_spec(manifest):
    return bridge_spec(manifest, 'sysdata', sysdata_errors, 'S2Arm system data')


def record_of(sd, name):
    path = sd.OUT / name
    require(path.is_file(), f'{name} is missing: its step did not run')
    return json.loads(path.read_bytes())


def fetch(sd, origin, directory, download, root, label):
    """The producer artifact downloaded into a fresh directory, checked against the API record."""
    target = Path(root or sd.ROOT) / directory
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    archive = target / 'artifact.zip'
    (download or sd.download_artifact)(origin['artifact']['id'], archive)
    raw = archive.read_bytes()
    require(len(raw) == origin['artifact']['bytes'] and sha(raw) == origin['artifact']['sha256'],
            f'The downloaded {label} artifact differs from the API record')
    return target, raw


def sums_listing(raw, label):
    """{path: SHA-256} of a shasum listing: one '<64 hex>  <path>' line per file, each path once."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise LineError(f'{label} is not UTF-8 text') from None
    listing = {}
    for line in text.splitlines():
        digest, separator, path = line.partition('  ')
        require(separator and HEX64.fullmatch(digest) and path and path not in listing,
                f'{label}: malformed or repeated line {line!r}')
        listing[path] = digest
    require(listing and text.endswith('\n'), f'{label} is empty or not newline-terminated')
    return listing


def xcframework_inventory(raw, library_sha):
    """S2ArmPrepare.xcframework.zip: one static iOS arm64 library (the bytes sha256.txt measured) and its headers."""
    prefix = PREPARE_XCFRAMEWORK + '/'
    files = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in safe_archive(archive, PREPARE_ZIP):
            require(member.startswith(prefix), f'{PREPARE_ZIP} member outside {prefix}: {member}')
            if not member.endswith('/'):
                files[member[len(prefix):]] = archive.read(member)
    require('Info.plist' in files, f'{PREPARE_XCFRAMEWORK} has no Info.plist')
    info = plistlib.loads(files['Info.plist'])
    libraries = info.get('AvailableLibraries') if isinstance(info, dict) else None
    require(isinstance(libraries, list) and info.get('CFBundlePackageType') == 'XFWK' and len(libraries) == 1 and
            isinstance(libraries[0], dict), f'{PREPARE_XCFRAMEWORK} must describe exactly one library')
    entry = libraries[0]
    identifier = entry.get('LibraryIdentifier')
    require(isinstance(identifier, str) and re.fullmatch(r'[A-Za-z0-9_.-]+', identifier) and
            entry.get('LibraryPath') == PREPARE_LIBRARY and entry.get('BinaryPath', PREPARE_LIBRARY) == PREPARE_LIBRARY and
            entry.get('SupportedPlatform') == 'ios' and 'SupportedPlatformVariant' not in entry and
            entry.get('SupportedArchitectures') == ['arm64'] and entry.get('HeadersPath', 'Headers') == 'Headers',
            f'{PREPARE_XCFRAMEWORK} is not one {PREPARE_LIBRARY} for iOS arm64 devices: {entry}')
    library = f'{identifier}/{PREPARE_LIBRARY}'
    headers = sorted(path for path in files if path.startswith(identifier + '/Headers/'))
    require(set(files) == {'Info.plist', library, *headers} and
            all(path.count('/') == 2 and path.endswith('.h') for path in headers),
            f'{PREPARE_XCFRAMEWORK} holds other files than its Info.plist, {library} and its headers: '
            f'{sorted(set(files) - {"Info.plist", library, *headers})}')
    require(files[library][:8] == b'!<arch>\n', f'{library} is not a static library')
    require(not [path for path, data in files.items() if data[:4] in MACHO_MAGICS],
            f'{PREPARE_XCFRAMEWORK} holds a Mach-O image: it is the static library alone')
    require(sha(files[library]) == library_sha, f'{library} ({sha(files[library])}) is not the {PREPARE_LIBRARY} '
            f'{PREPARE_SUMS} measured ({library_sha})')
    return dict(libraryIdentifier=identifier, library=dict(path=library, sha256=library_sha, bytes=len(files[library])),
                headers=[path.rsplit('/', 1)[1] for path in headers],
                files={path: sha(data) for path, data in sorted(files.items())})


def prepare_artifact(spec, origin, raw, repo):
    """The preparation library artifact, checked against the API, the manifest, the producer commit's pin and its
    own sha256.txt."""
    require(len(raw) == origin['artifact']['bytes'] and sha(raw) == origin['artifact']['sha256'],
            'The downloaded preparation library artifact differs from the API record')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [name for name in safe_archive(archive, origin['artifact']['name']) if not name.endswith('/')]
        require(sorted(names) == sorted(PREPARE_MEMBERS),
                f'The preparation library artifact must hold exactly {", ".join(PREPARE_MEMBERS)}: {sorted(names)}')
        files = {name: archive.read(name) for name in names}
    digest = sha(files[PREPARE_ZIP])
    require(digest == spec['zip'], f'{PREPARE_ZIP} differs from the manifest (s2arm.prepare.zip): {digest}')
    sums = sums_listing(files[PREPARE_SUMS], PREPARE_SUMS)
    require(set(sums) == {PREPARE_ZIP, PREPARE_LIBRARY} and sums[PREPARE_ZIP] == digest,
            f'{PREPARE_SUMS} must give {PREPARE_ZIP} (this archive) and {PREPARE_LIBRARY}: {sums}')
    identity = json.loads(files[PREPARE_IDENTITY])
    require(isinstance(identity, dict) and set(identity) >= {'component', 'source', 's2arm', 'dependencies', 'sha256',
                                                              'xcode'}, 'Incomplete ' + PREPARE_IDENTITY)
    require(identity['component'] == PREPARE_XCFRAMEWORK and identity['source'] == origin['source'],
            f'{PREPARE_IDENTITY} names another component or commit than its producer')
    pin = json.loads(repo.show(origin['source'], ENGINE_PIN))
    dependencies = {name: entry['sha256'] for name, entry in pin['dependencies'].items()}
    require(identity['s2arm'] == pin['s2arm']['commit'] and identity['dependencies'] == dependencies,
            f'{PREPARE_IDENTITY} names S2Arm {identity["s2arm"]} and {identity["dependencies"]}, the producer commit '
            f'pins {pin["s2arm"]["commit"]} and {dependencies}')
    require(identity['sha256'] == sums, f'{PREPARE_IDENTITY} digests differ from {PREPARE_SUMS}')
    require(isinstance(identity['xcode'], str) and identity['xcode'].strip(), f'{PREPARE_IDENTITY} names no Xcode')
    undefined = files[PREPARE_UNDEFINED].decode('utf-8', errors='replace').split()
    own = sorted(name for name in undefined if name.startswith('_rb_s2arm_'))
    require(not own, f'{PREPARE_UNDEFINED} leaves rb_s2arm_* entry points undefined: {own}')
    inventory = xcframework_inventory(files[PREPARE_ZIP], sums[PREPARE_LIBRARY])
    return files, identity, inventory


def prepare_download(sd, get=None, download=None, repo=None, root=None):
    """prepare-download: the preparation library's producer through the API, its artifact downloaded and checked."""
    manifest = sd.ci_manifest()
    spec = prepare_spec(manifest)
    repo = repo or sd.Repo()
    origin = producer_origin(spec, get or sd.api, repo, PREPARE_WORKFLOW, PREPARE_ARTIFACT, 'preparation library')
    target, raw = fetch(sd, origin, PREPARE_DOWNLOAD, download, root, 'preparation library')
    files, identity, inventory = prepare_artifact(spec, origin, raw, repo)
    for name, data in files.items():
        (target / name).write_bytes(data)
    return sd.save('s2arm-prepare-download.json', dict(
        result='authenticated', build=manifest['build'], producer=origin, zip=spec['zip'], identity=identity,
        identitySHA256=sha(files[PREPARE_IDENTITY]), xcframework=inventory,
        undefinedSHA256=sha(files[PREPARE_UNDEFINED]), directory=PREPARE_DOWNLOAD))


def installed_xcframework(root):
    """{path: SHA-256} of the xcframework installed in the bridge package (a symbolic link is refused)."""
    base = Path(root) / BRIDGE_FRAMEWORKS / PREPARE_XCFRAMEWORK
    require(base.is_dir(), f'{BRIDGE_FRAMEWORKS}/{PREPARE_XCFRAMEWORK} is not installed')
    files = {}
    for path in sorted(base.rglob('*')):
        require(not path.is_symlink(), f'Symbolic link in {PREPARE_XCFRAMEWORK}: {path.relative_to(base)}')
        if path.is_file():
            files[path.relative_to(base).as_posix()] = sha(path.read_bytes())
    return files


def check_podspec(root):
    """The bridge podspec vendors Frameworks/S2ArmPrepare.xcframework, and nothing else."""
    text = (Path(root) / BRIDGE_PODSPEC).read_text()
    lines = [line.strip() for line in text.splitlines() if 'vendored_' in line and not line.strip().startswith('#')]
    require(lines == [BRIDGE_VENDORED], f'{BRIDGE_PODSPEC} must vendor Frameworks/{PREPARE_XCFRAMEWORK} alone: {lines}')
    return sha(text.encode())


def prepare_install(sd, root=None):
    """prepare-install: S2ArmPrepare.xcframework unzipped where the bridge podspec vendors it, before pod install."""
    root = Path(root or sd.ROOT)
    manifest = sd.ci_manifest()
    spec = prepare_spec(manifest)
    record = record_of(sd, 's2arm-prepare-download.json')
    require(record['result'] == 'authenticated' and record['build'] == manifest['build'] and
            record['zip'] == spec['zip'] and record['producer']['run'] == spec['run'],
            'The preparation library download record is not this build\'s')
    raw = (root / PREPARE_DOWNLOAD / PREPARE_ZIP).read_bytes()
    require(sha(raw) == spec['zip'], f'{PREPARE_ZIP} changed after its download')
    inventory = xcframework_inventory(raw, record['xcframework']['library']['sha256'])
    podspec = check_podspec(root)
    frameworks = root / BRIDGE_FRAMEWORKS
    require(not frameworks.exists() or not any(frameworks.iterdir()),
            f'{BRIDGE_FRAMEWORKS} is not empty: the delivery installs {PREPARE_XCFRAMEWORK} there alone, once')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in archive.infolist():
            if member.filename.endswith('/'):
                continue
            target = frameworks / member.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
            target.chmod(0o644)
    installed = installed_xcframework(root)
    require(installed == inventory['files'], f'The installed {PREPARE_XCFRAMEWORK} differs from its archive')
    return sd.save('s2arm-prepare-install.json', dict(
        result='installed', build=manifest['build'], zip=spec['zip'], path=f'{BRIDGE_FRAMEWORKS}/{PREPARE_XCFRAMEWORK}',
        files=installed, library=inventory['library'], podspec=BRIDGE_PODSPEC, podspecSHA256=podspec))


def tree_files(directory):
    """{relative path: bytes} of every file under a directory (a symbolic link is refused)."""
    base = Path(directory)
    require(base.is_dir(), f'Missing {base}')
    files = {}
    for path in sorted(base.rglob('*')):
        require(not path.is_symlink(), f'Symbolic link in {base}: {path.relative_to(base)}')
        if path.is_file():
            files[path.relative_to(base).as_posix()] = path.read_bytes()
    return files


def check_tree(files, tree, label):
    """A system data tree {relative path: bytes}: the SHA256SUMS the manifest names, exactly the files it lists with
    their digests, the open font and time zone licence texts beside the data, no executable or bundle."""
    require(SYSDATA_SUMS in files, f'{label} has no {SYSDATA_SUMS}')
    digest = sha(files[SYSDATA_SUMS])
    require(digest == tree, f'{label}/{SYSDATA_SUMS} is not the one the manifest names (s2arm.sysdata.tree): {digest}')
    listed = sums_listing(files[SYSDATA_SUMS], f'{label}/{SYSDATA_SUMS}')
    present = set(files) - {SYSDATA_SUMS}
    missing, extra = sorted(set(listed) - present), sorted(present - set(listed))
    require(not missing and not extra, f'{label} differs from its {SYSDATA_SUMS}: missing {missing[:5]}, extra {extra[:5]}')
    changed = sorted(path for path, value in listed.items() if sha(files[path]) != value)
    require(not changed, f'{label} files differ from {SYSDATA_SUMS}: {changed[:5]}')
    for path in listed:
        parts = PurePosixPath(path).parts
        require((path == SYSDATA_SOURCES or path.startswith(SYSDATA_TOPS)) and '..' not in parts and '\\' not in path and
                not any(part.startswith('.') or part.endswith(BUNDLE_SUFFIXES) for part in parts),
                f'{label}: unexpected path {path}')
        require(files[path][:4] not in MACHO_MAGICS, f'{label}: Mach-O image {path}')
    folded = {}
    for path in listed:
        folded.setdefault(path.casefold(), []).append(path)
    clashes = sorted(paths for paths in folded.values() if len(paths) > 1)
    require(not clashes, f'{label}: paths that differ only by case (the signing Mac is case-insensitive): {clashes[:3]}')
    fonts = [path for path in listed if path.startswith('systemdata/fonts/') and path.endswith('.bfttf')]
    licences = sorted(path for path in listed if path.startswith('licenses/'))
    require(fonts, f'{label} has no shared font (systemdata/fonts/*.bfttf)')
    require(SYSDATA_TZ_LICENCE in licences and any(path.startswith(SYSDATA_FONT_LICENCES) for path in licences),
            f'{label}/licenses lacks the time zone licence or the open font licence texts: {licences}')
    require(SYSDATA_SOURCES in listed, f'{label} has no {SYSDATA_SOURCES}')
    return dict(tree=digest, files=len(listed), bytes=sum(len(files[path]) for path in listed), fonts=len(fonts),
                licences=licences)


def sysdata_sources(raw):
    """{part: source} of SOURCES.tsv (header 'part<TAB>source', one row per part)."""
    lines = raw.decode('utf-8', errors='replace').splitlines()
    require(lines[:1] == ['part\tsource'], f'{SYSDATA_SOURCES} has no part/source header')
    rows = {}
    for line in lines[1:]:
        part, separator, value = line.partition('\t')
        require(separator and part and part not in rows, f'{SYSDATA_SOURCES}: malformed or repeated line {line!r}')
        rows[part] = value
    return rows


def sysdata_artifact(spec, origin, raw, repo):
    """The system data artifact: every file against its SHA256SUMS, the S2Arm commit of SOURCES.tsv against the pin."""
    require(len(raw) == origin['artifact']['bytes'] and sha(raw) == origin['artifact']['sha256'],
            'The downloaded system data artifact differs from the API record')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [name for name in safe_archive(archive, origin['artifact']['name']) if not name.endswith('/')]
        files = {name: archive.read(name) for name in names}
    tree = check_tree(files, spec['tree'], origin['artifact']['name'])
    sources = sysdata_sources(files[SYSDATA_SOURCES])
    pin = json.loads(repo.show(origin['source'], ENGINE_PIN))['s2arm']['commit']
    require(sources.get('s2arm') == pin, f'{SYSDATA_SOURCES} names S2Arm {sources.get("s2arm")}, the producer commit '
            f'pins {pin}')
    return files, dict(tree, sources=sources)


def sysdata_download(sd, get=None, download=None, repo=None, root=None):
    """sysdata-download: the system data's producer through the API, its macOS artifact downloaded and checked."""
    manifest = sd.ci_manifest()
    spec = sysdata_spec(manifest)
    repo = repo or sd.Repo()
    origin = producer_origin(spec, get or sd.api, repo, SYSDATA_WORKFLOW, SYSDATA_ARTIFACT, 'system data')
    target, raw = fetch(sd, origin, SYSDATA_DOWNLOAD, download, root, 'system data')
    files, tree = sysdata_artifact(spec, origin, raw, repo)
    for name, data in files.items():
        path = target / 'tree' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return sd.save('s2arm-sysdata-download.json', dict(result='authenticated', build=manifest['build'], producer=origin,
                                                       **tree, directory=SYSDATA_DOWNLOAD + '/tree'))


def sysdata_embed(sd, app, root=None):
    """sysdata-embed APP: the downloaded tree, unchanged, as APP/S2ArmSystemData (never over an existing one)."""
    root = Path(root or sd.ROOT)
    app = Path(app)
    manifest = sd.ci_manifest()
    spec = sysdata_spec(manifest)
    record = record_of(sd, 's2arm-sysdata-download.json')
    require(record['result'] == 'authenticated' and record['build'] == manifest['build'] and
            record['tree'] == spec['tree'] and record['producer']['run'] == spec['run'],
            'The system data download record is not this build\'s')
    require(app.is_dir() and (app / 'Info.plist').is_file(), f'Missing built application: {app}')
    target = app / SYSTEM_DATA
    require(not target.exists(), f'{SYSTEM_DATA} is already in the application')
    files = tree_files(root / record['directory'])
    check_tree(files, spec['tree'], record['directory'])
    for name, data in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o644)
    placed = check_tree(tree_files(target), spec['tree'], SYSTEM_DATA)
    return sd.save('s2arm-sysdata-embed.json', dict(result='embedded', build=manifest['build'], app=str(app),
                                                    path=SYSTEM_DATA, **placed))


def check_registrant(root):
    """The generated plugin registrant registers the bridge plugin, once."""
    path = Path(root) / BRIDGE_REGISTRANT
    require(path.is_file(), f'Missing generated plugin registrant: {BRIDGE_REGISTRANT}')
    raw = path.read_bytes()
    require(len(BRIDGE_REGISTERED.findall(raw.decode('utf-8', errors='replace'))) == 1,
            f'{BRIDGE_REGISTRANT} does not register {BRIDGE_PLUGIN} once: the engine bridge is not a plugin of the '
            'application')
    return dict(path=BRIDGE_REGISTRANT, sha256=sha(raw), registers=BRIDGE_PLUGIN)


def direct_chain(raw, label):
    """The direct shader chain version S2ArmEngine.framework carries (what the bridge reads: 1 to 12 characters)."""
    text = raw.decode('utf-8', errors='replace').strip()
    require(re.fullmatch(r'[0-9a-f]{1,12}', text), f'{label} is not a direct shader chain version: {raw[:40]!r}')
    return text


def thin_arm64(raw, label):
    """The arm64 image of an executable (a fat container is opened)."""
    if raw[:4] in (b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
        wide = raw[:4] == b'\xca\xfe\xba\xbf'
        count = int.from_bytes(raw[4:8], 'big')
        stride = 32 if wide else 20
        require(0 < count <= 32 and len(raw) >= 8 + stride * count, f'{label}: invalid fat header')
        for index in range(count):
            position = 8 + index * stride
            if int.from_bytes(raw[position:position + 4], 'big') == 0x0100000C:
                size = 8 if wide else 4
                offset = int.from_bytes(raw[position + 8:position + 8 + size], 'big')
                length = int.from_bytes(raw[position + 8 + size:position + 8 + 2 * size], 'big')
                require(offset + length <= len(raw), f'{label}: truncated arm64 image')
                return raw[offset:offset + length]
        raise LineError(f'{label} has no arm64 image')
    return raw


def check_runner(raw, label):
    """The Runner executable links the bridge pod and S2ArmPrepare: their entry points and the plugin class are defined
    there (nm -gU), no rb_s2arm_* symbol is left undefined (nm -u), and rb_s2arm_engine_loaded is in dyld's export
    trie (MeloNX's bridge and the engine look it up with dlsym(RTLD_DEFAULT))."""
    on_path('packages/dolphin_internal_bridge/ci', 'build-utils')
    from verify_ipa import macho
    from validate_shader_compiler_ipa import exported_symbols
    image = macho(raw)
    defined = set(image['definedSymbols'])
    missing = [name for name in RUNNER_DEFINES if name not in defined]
    require(not missing, f'{label} does not define {missing}: the engine bridge or S2ArmPrepare is not linked into it')
    left = sorted({name for name in image['undefinedSymbols'] if name.startswith('_rb_s2arm_')})
    require(not left, f'{label} leaves {left} undefined')
    require(ENGINE_LOADED in exported_symbols(thin_arm64(raw, label)), f'{label} does not export {ENGINE_LOADED} '
            '(dyld export trie)')
    return dict(executable=label, defines=list(RUNNER_DEFINES), undefinedRbS2Arm=[], exports=[ENGINE_LOADED])


def bridge_pieces(sd, manifest, app, root, chain):
    """engine-embed: the engine bridge pieces of this build, checked, as S2Arm-native-identity.json records them."""
    prepare, sysdata = prepare_spec(manifest), sysdata_spec(manifest)
    download, install = record_of(sd, 's2arm-prepare-download.json'), record_of(sd, 's2arm-prepare-install.json')
    fetched, placed = record_of(sd, 's2arm-sysdata-download.json'), record_of(sd, 's2arm-sysdata-embed.json')
    require(download['result'] == 'authenticated' and download['build'] == manifest['build'] and
            download['zip'] == prepare['zip'] and download['producer']['run'] == prepare['run'] and
            install['result'] == 'installed' and install['build'] == manifest['build'] and install['zip'] == prepare['zip'],
            'The preparation library records are not this build\'s')
    require(installed_xcframework(root) == install['files'],
            f'{PREPARE_XCFRAMEWORK} changed in {BRIDGE_FRAMEWORKS} after its installation')
    require(fetched['result'] == 'authenticated' and fetched['build'] == manifest['build'] and
            fetched['tree'] == sysdata['tree'] and fetched['producer']['run'] == sysdata['run'] and
            placed['result'] == 'embedded' and placed['build'] == manifest['build'] and placed['tree'] == sysdata['tree'] and
            placed['app'] == str(app), 'The system data records are not this build\'s or this application\'s')
    tree = check_tree(tree_files(app / SYSTEM_DATA), sysdata['tree'], SYSTEM_DATA)
    return dict(
        prepare=dict(workflow=PREPARE_WORKFLOW, run=prepare['run'], zip=prepare['zip'], producer=download['producer'],
                     sourceIdentity=download['identity'], sourceIdentitySHA256=download['identitySHA256'],
                     library=download['xcframework']['library'], installedAt=install['path'], linkedInto='Runner'),
        systemData=dict(workflow=SYSDATA_WORKFLOW, run=sysdata['run'], tree=sysdata['tree'], path=SYSTEM_DATA,
                        engineReads=SYSTEM_DATA_READ, producer=fetched['producer'], sources=fetched['sources'], files=tree['files'],
                        bytes=tree['bytes'], fonts=tree['fonts'], licences=tree['licences']),
        bridge=dict(package=BRIDGE_PACKAGE, pluginClass=BRIDGE_PLUGIN, registrant=check_registrant(root),
                    runnerDefines=list(RUNNER_DEFINES), runnerExports=[ENGINE_LOADED], directChain=chain))


def check_bridge(read, names, identity, prepare, sysdata, host, registrant=None):
    """The engine bridge inside an application (read(relative path) -> bytes; names: relative paths) against the
    packaged identity and the manifest's s2arm.prepare and s2arm.sysdata; with `registrant` (the checkout root of the
    generated host), the generated plugin registrant as well."""
    recorded, system, bridge = (identity.get(key) for key in ('prepare', 'systemData', 'bridge'))
    require(all(isinstance(value, dict) for value in (recorded, system, bridge)),
            f'{PACKAGED_IDENTITY} does not record the engine bridge (prepare, systemData, bridge)')
    require(recorded['workflow'] == PREPARE_WORKFLOW and recorded['run'] == prepare['run'] and
            recorded['zip'] == prepare['zip'], f'{PACKAGED_IDENTITY} is not the manifest\'s preparation library')
    require(system['workflow'] == SYSDATA_WORKFLOW and system['run'] == sysdata['run'] and
            system['tree'] == sysdata['tree'] and system['path'] == SYSTEM_DATA,
            f'{PACKAGED_IDENTITY} is not the manifest\'s system data')
    prefix = SYSTEM_DATA + '/'
    tree = check_tree({name[len(prefix):]: read(name) for name in names if name.startswith(prefix) and
                       not name.endswith('/')}, sysdata['tree'], SYSTEM_DATA)   # an IPA made by zip -r lists folders
    require(tree['files'] == system['files'] and tree['licences'] == system['licences'],
            f'{SYSTEM_DATA} is not the tree embedded')
    member = f'Frameworks/S2ArmEngine.framework/{DIRECT_CHAIN}'
    require(member in names, f'{member} is missing: the bridge cannot stamp a prepared game with its direct chain')
    chain = direct_chain(read(member), member)
    require(chain == bridge['directChain'], f'{member} is not the one embedded')
    separate = sorted(name for name in names if any(marker in name for marker in SEPARATE_IMAGES))
    require(not separate, f'The bridge or S2ArmPrepare is packaged on its own ({separate[:3]}): both are linked into Runner')
    executable = str(host.get('CFBundleExecutable', ''))
    require(executable in names, f'The application has no executable {executable!r}')
    runner = check_runner(read(executable), executable)
    recorded_registrant = bridge.get('registrant') if isinstance(bridge.get('registrant'), dict) else {}
    if registrant is not None:
        current = check_registrant(registrant)
        require(current == recorded_registrant, f'{BRIDGE_REGISTRANT} changed after the embedding')
    else:
        require(recorded_registrant.get('registers') == BRIDGE_PLUGIN, f'{PACKAGED_IDENTITY} records no registration of '
                f'{BRIDGE_PLUGIN}')
    return dict(prepare=dict(run=prepare['run'], zip=prepare['zip']), systemData=tree, directChain=chain, runner=runner,
                registrant=recorded_registrant)


# --- Closed extension sets of the common validators -----------------------------------------------------

def extension_set_readers(source):
    """{function: (reads of EXPECTED_HELPERS, dict(EXPECTED_HELPERS) copies)} of a validator's top-level functions."""
    readers = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        reads = sum(isinstance(child, ast.Name) and child.id == 'EXPECTED_HELPERS' for child in ast.walk(node))
        copies = sum(isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == 'dict' and
                     len(child.args) == 1 and isinstance(child.args[0], ast.Name) and
                     child.args[0].id == 'EXPECTED_HELPERS' for child in ast.walk(node))
        if reads:
            readers[node.name] = (reads, copies)
    return readers


def calls_by_name(source, caller, callee):
    node = next(item for item in ast.parse(source).body if isinstance(item, ast.FunctionDef) and item.name == caller)
    return any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == callee
               for child in ast.walk(node))


def extension_set_review(path, root=ROOT):
    """'extend' when the validator is the reviewed shape, 'native' when it names S2Arm itself; refused otherwise."""
    module, function, caller = EXTENSION_SETS[path]
    source = (Path(root) / path).read_text()
    if 's2arm' in source.lower():
        return 'native'
    require(extension_set_readers(source) == {function: (1, 1)} and
            (caller is None or calls_by_name(source, caller, function)),
            f'{path} no longer reads its closed extension set as reviewed ({extension_set_readers(source)}): review '
            'EXTENSION_SETS before any delivery of this line')
    return 'extend'


def s2arm_aware(module, function, carries_identity):
    """Wrap module.function: while it runs on an application that carries the S2Arm identity, the module's
    EXPECTED_HELPERS also holds S2ArmJITHelper.appex and the engine frameworks are required."""
    original = getattr(module, function)
    if getattr(original, 's2armExtended', False):
        return original
    contracts = distribution().S2ARM_EXTENSIONS

    @functools.wraps(original)
    def wrapper(*arguments, **keywords):
        frameworks = carries_identity(*arguments, **keywords)
        if frameworks is None:
            return original(*arguments, **keywords)
        for name in ENGINE_FRAMEWORKS:
            module.demand(f'Frameworks/{name}.framework/{name}' in frameworks,
                          'S2Arm identity requires the engine frameworks: ' + name)
        saved = module.EXPECTED_HELPERS
        module.EXPECTED_HELPERS = {**saved, **contracts}
        try:
            return original(*arguments, **keywords)
        finally:
            module.EXPECTED_HELPERS = saved
    wrapper.s2armExtended = True
    setattr(module, function, wrapper)
    return wrapper


def ipa_identity(ipa, *arguments, **keywords):
    """verify_ipa.validate(ipa): the framework files of an IPA that carries the identity, else None."""
    try:
        with zipfile.ZipFile(ipa) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return None
    prefix = 'Payload/NeoStation.app/'
    if prefix + PACKAGED_IDENTITY not in names:
        return None
    return {name[len(prefix):] for name in names if name.startswith(prefix + 'Frameworks/')}


def app_identity(app, *arguments, **keywords):
    """validate_rpcs3_ipa.validate_helper_bundles(app, info, root): the same, for an extracted application."""
    app = Path(app)
    if not (app / PACKAGED_IDENTITY).is_file():
        return None
    return {path.relative_to(app).as_posix() for path in (app / 'Frameworks').rglob('*') if path.is_file()}


def extend_validators(modules=None, root=ROOT):
    """Make the closed extension sets of the reviewed common validators S2Arm-aware (in memory, this process)."""
    on_path('build-utils', 'packages/dolphin_internal_bridge/ci')
    result = {}
    for path, (name, function, _) in EXTENSION_SETS.items():
        result[path] = extension_set_review(path, root)
        if result[path] == 'extend':
            module = (modules or {}).get(name) or importlib.import_module(name)
            s2arm_aware(module, function, ipa_identity if name == 'verify_ipa' else app_identity)
    return result


def dolphin_package(sd):
    """dolphin-package: build_support.py package, unchanged, after its verify_ipa.validate became S2Arm-aware."""
    extended = extend_validators()
    verify_ipa = importlib.import_module('verify_ipa')
    support = importlib.import_module('build_support')
    require(support.validate is verify_ipa.validate and getattr(support.validate, 's2armExtended', False) ==
            (extended['packages/dolphin_internal_bridge/ci/verify_ipa.py'] == 'extend'),
            'build_support did not bind the S2Arm-aware validator')
    saved = sys.argv
    sys.argv = [str(ROOT / 'packages/dolphin_internal_bridge/ci/build_support.py'), 'package']
    try:
        support.main()
    finally:
        sys.argv = saved
    return dict(result='packaged', extensionSets=extended)


def edited_verifier_source(root=ROOT):
    """The downloaded-delivery verifier with the reviewed VERIFIER_EDITS applied (each occurs exactly as declared)."""
    text = (Path(root) / VERIFIER).read_text()
    for old, new, count in VERIFIER_EDITS:
        require(text.count(old) == count, f'{VERIFIER} no longer holds the reviewed text {old.strip()!r}: review '
                'VERIFIER_EDITS')
        text = text.replace(old, new)
    return text


def describe():
    actual = inventory((ROOT / RECIPE).read_text())
    return dict(recipe=RECIPE, recipeSHA256=sha_file(ROOT / RECIPE), line=dict(
        branch=DELIVERY_BRANCH, workflow=WORKFLOW, tag=TRIGGER_MARKER + 'N]', firstBuild=FIRST_BUILD,
        recipient=RECIPIENT, baseLines=BASE_LINES), reviewed=RECIPE_INVENTORY, current=actual,
        drift=inventory_drift(actual, RECIPE_INVENTORY), handling=HANDLING,
        verifier=dict(path=VERIFIER, reviewed=VERIFIER_INVENTORY,
                      current=inventory((ROOT / VERIFIER).read_text(), prefix='sd')))


LINE_OPERATIONS = ('request-guard', 'recipient-guard', 'inventory', 'engine-download', 'engine-embed',
                   'engine-check-app', 'engine-check-ipa', 'dolphin-package', 'prepare-download', 'prepare-install',
                   'sysdata-download', 'sysdata-embed')
PATH_OPERATIONS = {'engine-embed': engine_embed, 'engine-check-app': engine_check_app,
                   'engine-check-ipa': engine_check_ipa, 'sysdata-embed': sysdata_embed}
PLAIN_OPERATIONS = {'request-guard': request_guard, 'recipient-guard': recipient_guard,
                    'engine-download': engine_download, 'dolphin-package': dolphin_package,
                    'prepare-download': prepare_download, 'prepare-install': prepare_install,
                    'sysdata-download': sysdata_download}
# Recipe operations that run a closed-set validator on the application: they run S2Arm-aware.
EXTENDED_OPERATIONS = ('structure', 'seal')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'inventory':
        value = describe()
        print(json.dumps(value, indent=2))
        return 1 if value['drift'] else 0
    sd = configure()
    if argv and argv[0] in LINE_OPERATIONS:
        operation, rest = argv[0], argv[1:]
        if operation in PATH_OPERATIONS:
            require(len(rest) == 1, operation + ' takes the application or IPA path')
            result = PATH_OPERATIONS[operation](sd, Path(rest[0]))
        else:
            require(not rest, operation + ' takes no argument')
            result = PLAIN_OPERATIONS[operation](sd)
        print(json.dumps(result, indent=2, default=str))
        return 0
    if argv and argv[0] in EXTENDED_OPERATIONS:
        extend_validators()
    return sd.main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
