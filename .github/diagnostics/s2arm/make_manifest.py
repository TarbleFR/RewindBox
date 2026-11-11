#!/usr/bin/env python3
"""Draft manifest of a Switch 2 (S2Arm) test IPA: a delivered common build plus the declared probe delta.

The standard recipe has no manifest generator: a draft is the previous manifest without what the freeze
writes, with the base rebuilt from the delivered receipts and the build's own declarations. This script
does exactly that for the test line, from a model build of the common line (724 today, 725 once it is
delivered), and then lets the recipe's own checker validate the result (manifest_errors, verify_base).

  successor  --model N   the base is the delivered build N (docs/evidence/rewind<N>/delivery.json and
                         signed-payload-identity.json); both Cores are declared unchangedFromBase.
  sibling    --model N   same base, components and classified commits as build N (its frozen manifest),
                         plus the delta: the test IPA is build N rebuilt with the probe.

    python3 -B .github/diagnostics/s2arm/make_manifest.py sibling --model 724 --build 801 \\
        --reviewed <commit>=<note> [--source-only <commit>=<note>] --output build-utils/delivery/801.json

A build that carries the S2Arm engine names its producer run and the SHA-256 of its two archives; the
draft then also declares the engine delta (ENGINE_DELTA: the JIT helper package, its configure script, the
validator diff, three added images) and runs the S2Arm tests in the flutter group:

    ... --engine-run <run id> --engine-zip S2ArmEngine.framework.zip=<sha256> \\
        --engine-zip NS2Pro.framework.zip=<sha256>

The output is a DRAFT (status "draft"); only `standard_delivery_s2arm.py freeze <N>` makes it deliverable.
Nothing is written under build-utils/delivery/ unless --output says so.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import standard_delivery_s2arm as line  # noqa: E402

# The declared delta of the test IPA over the common IPA (docs/s2arm-trial-ipa-handoff.md).
DELTA = dict(
    package='packages/s2arm_probe',
    pubspec=dict(workspace='packages/s2arm_probe', dependency=dict(s2arm_probe=dict(path='packages/s2arm_probe'))),
    hostInfoPlist=dict(set={'RewindBoxS2ArmProbe': True}, never=['RewindBoxS2ArmProbeMapped'],
                       by='build-utils/s2arm/set_probe_key.py'),
    reviewedProductPaths=['pubspec.yaml', 'packages/s2arm_probe/', 'build-utils/s2arm/set_probe_key.py'],
    images=dict(mustChange=['Runner'], added=[], removed=[]),
    runnerMustDefine=['_OBJC_CLASS_$_S2ArmProbePlugin', '_rb_s2arm_probe_attached', '_rb_s2arm_probe_detached'],
)
# The engine delta of a build that carries the S2Arm engine (docs/s2arm-jit-helper.md). The frameworks are not
# product paths: they come from their producer run, named by s2arm.engine and authenticated by the launcher.
ENGINE_DELTA = dict(
    package='packages/s2arm_jit_helper',
    configure='build-utils/s2arm/configure_s2arm_ios.py',
    validator='build-utils/validate_single_ipa_distribution.py',
    reviewedProductPaths=['packages/s2arm_jit_helper/', 'build-utils/s2arm/configure_s2arm_ios.py',
                          'build-utils/validate_single_ipa_distribution.py'],
    images=dict(added=list(line.ENGINE_IMAGES)),
    packagedIdentity=line.PACKAGED_IDENTITY,
    helper=line.HELPER,
    producer=dict(workflow=line.ENGINE_WORKFLOW, branch=line.DELIVERY_BRANCH, artifact=line.ENGINE_ARTIFACT,
                  members=list(line.ENGINE_ZIPS) + [line.ENGINE_IDENTITY]),
)
ENGINE_TESTS = (
    ['s2arm-jit-helper', ['python3', '-B', 'test/s2arm_jit_helper_test.py']],
    ['s2arm-validator', ['python3', '-B', 'test/s2arm_validator_test.py']],
    ['s2arm-configure', ['python3', '-B', 'test/s2arm_configure_test.py']],
)
# Sections and keys a draft carries; everything else of a frozen manifest is written by the freeze.
DRAFT_PRODUCT_KEYS = ('reviewedCommits', 'sourceOnly', 'promotedCommits')
DRAFT_IMAGE_KEYS = ('mustChange', 'added', 'removed', 'replaced', 'retained')
FROZEN_TEST_KEYS = ('commands', 'reuse')
PINNED_CORES = ('rpcs3', 'melonx')


def require(condition, message):
    if not condition:
        raise SystemExit('make_manifest: ' + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(root, path):
    target = Path(root) / path
    require(target.is_file(), 'missing ' + path)
    return target.read_bytes()


def base_from_receipt(root, build):
    """The base section of a manifest whose base is the delivered build, from its committed receipts.

    Every value comes from docs/evidence/rewind<build>/delivery.json (written by the recipe's `record`
    after the downloaded IPA was verified) and from the signed image inventory next to it."""
    folder = f'docs/evidence/rewind{build}'
    receipt_raw = read(root, folder + '/delivery.json')
    identity_raw = read(root, folder + '/signed-payload-identity.json')
    receipt, identity = json.loads(receipt_raw), json.loads(identity_raw)
    execution = receipt['execution']
    require(receipt.get('result') == 'delivered-and-verified' and receipt.get('build') == build,
            f'{folder}/delivery.json is not the verified delivery of build {build}')
    return dict(
        build=build, source=execution['source'], tree=execution['tree'], run=execution['run'],
        attempt=execution['attempt'], workflow=receipt['recipe']['workflow'],
        jobs={name: dict(name=name, id=execution['jobs'][name]['id']) for name in ('preflight', 'application')},
        receipt=dict(path=folder + '/delivery.json', sha256=sha(receipt_raw), proofFiles=len(receipt['proofFiles'])),
        identity=dict(path=folder + '/signed-payload-identity.json', sha256=sha(identity_raw),
                      images=len(identity['images'])),
        ipa={key: receipt['ipa'][key] for key in ('name', 'producerName', 'bytes', 'sha256')})


def delta_paths(root, items=None):
    """Tracked files of the reviewed delta (folders expanded), as the freeze will see them."""
    paths = []
    for item in items or DELTA['reviewedProductPaths']:
        listed = subprocess.run(['git', 'ls-files', '-z', '--', item], cwd=root, capture_output=True, check=True)
        found = [name for name in listed.stdout.decode().split('\0') if name]
        paths += found or [item.rstrip('/')]
    return sorted(set(paths))


def engine_pin(engine):
    """s2arm.engine of a draft from {run, zips}; the launcher refuses the same malformed values."""
    value = dict(workflow=line.ENGINE_WORKFLOW, run=engine.get('run'), zips=dict(engine.get('zips', {})))
    errors = line.engine_errors(value)
    require(not errors, '; '.join(errors))
    return value


def draft(sd, mode, model_build, build, reviewed=(), source_only=(), note=None, root=ROOT, engine=None):
    root = Path(root)
    require(build >= line.FIRST_BUILD, f'builds of this line start at {line.FIRST_BUILD}')
    engine = engine_pin(engine) if engine is not None else None
    model = json.loads(read(root, sd.manifest_path(model_build)))
    require(model.get('status') == 'frozen' and not sd.manifest_errors(model),
            f'the model manifest {model_build} is not a frozen manifest')
    value = dict(schema=1, build=build, status='draft')
    components = copy.deepcopy(model['components'])
    images = {key: copy.deepcopy(model['images'][key]) for key in DRAFT_IMAGE_KEYS}
    if mode == 'successor':
        value['base'] = base_from_receipt(root, model_build)
        for key in PINNED_CORES:
            # The Core of the base is installed again from the same pin: retained image, never replaced.
            components[key]['unchangedFromBase'] = True
            components[key].pop('replaces', None)
            images['replaced'].pop(key, None)
            images['retained'][key] = [components[key]['image']]
        images['mustChange'] = []
        product = dict(reviewedCommits=[], sourceOnly=[], promotedCommits=[])
        what = f'the delivered common IPA {model_build}'
    else:
        value['base'] = copy.deepcopy(model['base'])
        product = {key: copy.deepcopy(model['product'].get(key, [])) for key in DRAFT_PRODUCT_KEYS}
        what = f'the common IPA {model_build} rebuilt from its own base {model["base"]["build"]}'
    base_images = sd.verify_base(value, lambda path: (root / path).read_bytes() if (root / path).is_file() else None)
    paths = delta_paths(root, DELTA['reviewedProductPaths'] +
                        (ENGINE_DELTA['reviewedProductPaths'] if engine else []))
    derived, unmapped = sd.images_for_paths(paths, set(base_images))
    images['mustChange'] = sorted(set(images['mustChange']) | set(DELTA['images']['mustChange']) | set(derived))
    require(not (set(images['added']) | set(images['removed'])), 'the model adds or removes images')
    if engine:
        require(not set(ENGINE_DELTA['images']['added']) & set(base_images), 'the base already has an engine image')
        images['added'] = sorted(ENGINE_DELTA['images']['added'])
    product['reviewedCommits'] += [dict(commit=commit, note=text) for commit, text in reviewed]
    product['sourceOnly'] += [dict(commit=commit, targetBuild=build + 1, note=text) for commit, text in source_only]
    tests = copy.deepcopy(model['tests'])
    for group in sd.TEST_GROUPS:
        tests[group] = {key: item for key, item in tests[group].items() if key not in FROZEN_TEST_KEYS}
        tests[group]['mode'] = 'fresh'   # the effective tree changes: no test evidence can be reused
    if engine:
        additions = tests['flutter'].setdefault('additions', {})
        commands = additions.setdefault('commands', [])
        commands += [copy.deepcopy(command) for command in ENGINE_TESTS if command[0] not in {c[0] for c in commands}]
    recipient = line.recipient_path(build)
    key_file = root / recipient
    pending = []
    if not key_file.is_file():
        pending.append(f'recipient: {recipient} is not committed yet (its sha256 is null)')
    if not reviewed:
        pending.append('product.reviewedCommits: the reviewed commit(s) of the delta are not declared yet')
    carried = ('' if not engine else
               f' With the S2Arm engine: S2ArmEngine.framework and NS2Pro.framework of run {engine["run"]} of '
               f'{line.ENGINE_WORKFLOW}, their identity {line.PACKAGED_IDENTITY} and the {line.HELPER} extension '
               '(packages/s2arm_jit_helper, build-utils/s2arm/configure_s2arm_ios.py, the S2Arm conditional of '
               'build-utils/validate_single_ipa_distribution.py).')
    value.update(
        note=note or (f'Private Switch 2 (S2Arm) test IPA {build} = {what}, plus the S2Arm device probe'
                      f'{"" if engine else " only"}: '
                      'package packages/s2arm_probe (static pod linked into Runner), its workspace and dependency '
                      'lines in pubspec.yaml, and the host Info.plist boolean RewindBoxS2ArmProbe = true.' + carried +
                      ' Same application identifier as the common IPA. Not a common-line build.'),
        components=components, product=product, images=images, tests=tests,
        recipient=dict(path=recipient, sha256=sha(key_file.read_bytes()) if key_file.is_file() else None),
        republish=copy.deepcopy(model['republish']),
        s2arm=dict(line=dict(branch=line.DELIVERY_BRANCH, workflow=line.WORKFLOW, tag=line.TRIGGER_MARKER + 'N]'),
                   derivation=dict(tool='.github/diagnostics/s2arm/make_manifest.py', mode=mode, model=model_build,
                                   modelManifestSHA256=sha(read(root, sd.manifest_path(model_build)))),
                   delta=DELTA, deltaPaths=paths, derivedMustChange=derived, pathsWithoutImage=unmapped,
                   pending=pending))
    if engine:
        value['s2arm'].update(engine=engine, engineDelta=copy.deepcopy(ENGINE_DELTA))
    errors = sd.manifest_errors(value)
    require(not errors, 'the recipe refuses the draft: ' + '; '.join(errors))
    return value


def pair(text):
    commit, separator, note = text.partition('=')
    require(separator and len(commit) == 40 and note.strip(), 'expected <40-hex commit>=<note>: ' + text)
    return commit, note.strip()


def archive_digest(text):
    name, separator, digest = text.partition('=')
    require(separator and name in line.ENGINE_ZIPS, 'expected <' + ' or '.join(line.ENGINE_ZIPS) + '>=<sha256>: ' + text)
    return name, digest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=('successor', 'sibling'))
    parser.add_argument('--model', type=int, required=True, help='build of the common line the draft derives from')
    parser.add_argument('--build', type=int, default=line.FIRST_BUILD)
    parser.add_argument('--reviewed', action='append', default=[], type=pair, metavar='COMMIT=NOTE')
    parser.add_argument('--source-only', action='append', default=[], type=pair, metavar='COMMIT=NOTE')
    parser.add_argument('--note')
    parser.add_argument('--engine-run', type=int, help='run id of the S2Arm engine producer (s2arm-engine.yml)')
    parser.add_argument('--engine-zip', action='append', default=[], type=archive_digest, metavar='NAME=SHA256')
    parser.add_argument('--output', type=Path, help='file to write (default: print the draft)')
    args = parser.parse_args(argv)
    sd = line.configure()
    require((args.engine_run is None) == (not args.engine_zip), '--engine-run and --engine-zip go together')
    require(len(dict(args.engine_zip)) == len(args.engine_zip), 'an engine archive is named twice')
    engine = dict(run=args.engine_run, zips=dict(args.engine_zip)) if args.engine_run is not None else None
    value = draft(sd, args.mode, args.model, args.build, args.reviewed, args.source_only, args.note, engine=engine)
    text = json.dumps(value, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
        print(json.dumps(dict(written=str(args.output), status=value['status'], mode=args.mode, model=args.model,
                              base=value['base']['build'], mustChange=value['images']['mustChange'],
                              added=value['images']['added'], engine=value['s2arm'].get('engine'),
                              pending=value['s2arm']['pending']), indent=2))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
