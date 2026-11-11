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
  engine-check-app APP   the built application: identity, frameworks byte for byte, JIT helper
  engine-check-ipa IPA   the signed IPA: distribution validator, identity, frameworks (payload
                    fingerprints, signed), JIT helper, signer receipt
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


def engine_origin(spec, get, repo):
    """The producer through the API: a successful run of the engine workflow on this branch, whose commit is in
    the delivered history, and the one unexpired artifact named after that commit."""
    run = get(f'actions/runs/{spec["run"]}')
    require(run.get('id') == spec['run'] and run.get('path') == ENGINE_WORKFLOW and
            run.get('head_branch') == DELIVERY_BRANCH and run.get('status') == 'completed' and
            run.get('conclusion') == 'success' and type(run.get('run_attempt')) is int and
            HEX40.fullmatch(str(run.get('head_sha'))),
            f'Run {spec["run"]} is not a successful {ENGINE_WORKFLOW} run of {DELIVERY_BRANCH}: '
            f'{run.get("path")} {run.get("head_branch")} {run.get("status")}/{run.get("conclusion")}')
    source = run['head_sha']
    require(repo.is_ancestor(source, 'HEAD'), f'The engine producer commit {source} is not in the delivered history')
    name = ENGINE_ARTIFACT.format(source=source)
    listing = get(f'actions/runs/{spec["run"]}/artifacts?name={name}&per_page=100')
    found = [item for item in listing.get('artifacts', []) if item.get('name') == name]
    require(len(found) == 1, f'Run {spec["run"]} has {len(found)} artifacts named {name}, not one')
    artifact = found[0]
    digest = str(artifact.get('digest') or '')
    require(type(artifact.get('id')) is int and type(artifact.get('size_in_bytes')) is int and
            artifact.get('expired') is False and artifact.get('workflow_run', {}).get('id') == run['id'] and
            artifact['workflow_run'].get('head_sha') == source and digest.startswith('sha256:') and
            HEX64.fullmatch(digest[len('sha256:'):]), f'Wrong or expired engine artifact {name}')
    return dict(workflow=ENGINE_WORKFLOW, branch=DELIVERY_BRANCH, run=run['id'], attempt=run['run_attempt'],
                source=source, conclusion=run['conclusion'],
                artifact=dict(id=artifact['id'], name=name, bytes=artifact['size_in_bytes'],
                              sha256=digest[len('sha256:'):], expiresAt=artifact.get('expires_at')))


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


def packaged_identity(manifest, record, inventories, script):
    return dict(schema=1, engine='S2Arm', build=manifest['build'], producer=record['producer'],
                sourceIdentity=record['identity'], sourceIdentitySHA256=record['identitySHA256'], zips=record['zips'],
                frameworks=inventories, jitHelper=dict(helper_contract(), scriptSHA256=sha(script)),
                physicalDeviceTested=False)


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
    text = json.dumps(packaged_identity(manifest, record, inventories, script), indent=2, sort_keys=True) + '\n'
    (app / PACKAGED_IDENTITY).write_text(text)
    return sd.save('s2arm-engine-embed.json', dict(result='embedded', build=manifest['build'], app=str(app),
                                                   identity=PACKAGED_IDENTITY, identitySHA256=sha(text.encode()),
                                                   images=list(ENGINE_IMAGES)))


def engine_check_app(sd, app, root=None):
    """engine-check-app APP: identity as embedded, frameworks byte for byte, JIT helper, before packaging."""
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
    return sd.save('s2arm-engine-app.json', dict(result='passed', build=manifest['build'], app=str(app),
                                                 identitySHA256=record['identitySHA256'], helper=helper,
                                                 frameworks=frameworks, physicalDeviceTested=False))


def check_engine_ipa(ipa, spec, script, identity_sha=None, signed_images=None):
    """The engine in a signed IPA (engine-check-ipa in CI, and the offline verification of a download)."""
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
    for image in ENGINE_IMAGES:
        require(image in payloads, f'{image} is not in the signed inventory')
        require(signed_images is None or signed_images.get(image) == payloads[image],
                f'{image} differs from the signer receipt')
    return dict(result='passed', ipaSHA256=sha_file(ipa), distributionBundles=sorted(bundles),
                distributionHelper=bundles[HELPER], helper=helper, frameworks=frameworks, identitySHA256=sha(raw),
                producer=identity['producer'], images={image: payloads[image] for image in ENGINE_IMAGES},
                physicalDeviceTested=False)


def engine_check_ipa(sd, ipa, root=None):
    """engine-check-ipa IPA: the signed IPA, after the recipe's own validation."""
    root = Path(root or sd.ROOT)
    manifest = sd.ci_manifest()
    spec = engine_spec(manifest)
    require(set(ENGINE_IMAGES) <= set(manifest['images']['added']), 'The manifest does not declare the engine images')
    record = json.loads((sd.OUT / 's2arm-engine-embed.json').read_bytes())
    signed = json.loads((sd.OUT / 'signed-payload-identity.json').read_bytes())
    require(signed['ipaSha256'] == sha_file(ipa), 'The signer receipt is not this IPA\'s')
    result = check_engine_ipa(ipa, spec, (root / HELPER_SCRIPT).read_bytes(), record['identitySHA256'], signed['images'])
    return sd.save('s2arm-engine-ipa.json', dict(result, build=manifest['build'], ipa=str(ipa)))


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
                   'engine-check-app', 'engine-check-ipa', 'dolphin-package')
PATH_OPERATIONS = {'engine-embed': engine_embed, 'engine-check-app': engine_check_app,
                   'engine-check-ipa': engine_check_ipa}
PLAIN_OPERATIONS = {'request-guard': request_guard, 'recipient-guard': recipient_guard,
                    'engine-download': engine_download, 'dolphin-package': dolphin_package}
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
