#!/usr/bin/env python3
"""Exercise authenticated recovery and reject tampered inputs, without builds.

Pass --archives DIR containing the two original and retained ZIPs and captured
api-metadata.json to exercise the real production path entirely offline.
"""
import argparse
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import recover_core_archive as recovery
import reuse_core_baseline as baseline
import verify_dma_core as dma

checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


def rejects(action, message):
    try:
        action()
    except (RuntimeError, ValueError, AssertionError, KeyError, zipfile.BadZipFile):
        check(True, message)
    else:
        raise AssertionError(message)


def synthetic():
    retained = recovery.retained_components
    content = b'exact original archive bytes'
    origin = dict(workflow='producer.yml', source='original', run=1, attempt=1,
                  job=2, artifact=3, name='original', bytes=len(content), sha256=retained.sha(content))
    publisher = dict(build=4, source='publisher', run=5, attempt=1, job=6, artifact=7, name='retained')
    record = dict(schema=1, kind='melonx-core', original=origin, content='original.zip',
                  contentSHA256=origin['sha256'], contentBytes=len(content),
                  republisher=dict(build=4, source='publisher', run=5, attempt=1, job='republish'))

    def exercise(mutation=None):
        proof = copy.deepcopy(record)
        payload = content
        members = None
        if mutation == 'original': proof['original']['artifact'] += 1
        if mutation == 'publisher': proof['republisher']['source'] = 'other'
        if mutation == 'content': payload += b'changed'
        if mutation == 'extra': members = {'unexpected': b'no'}
        if mutation == 'traversal': members = {'../escape': b'no'}
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('original.zip', payload)
            archive.writestr('republication.json', json.dumps(proof))
            for name, value in (members or {}).items(): archive.writestr(name, value)
            if mutation == 'duplicate': archive.writestr('original.zip', payload)
            if mutation == 'symlink':
                entry = zipfile.ZipInfo('link')
                entry.external_attr = 0o120777 << 16
                archive.writestr(entry, 'original.zip')
        bundle = data.getvalue()
        pin = dict(publisher, bytes=len(bundle), sha256=retained.sha(bundle))
        metadata = {
            'actions/runs/5': dict(id=5, head_sha='publisher', path=retained.STANDARD_WORKFLOW,
                                  head_branch='Claude', run_attempt=1),
            'actions/jobs/6': dict(run_id=5, head_sha='publisher', run_attempt=1, name='republish',
                                  steps=[dict(name=retained.republish_step('melonx-core'), conclusion='success')]),
            'actions/artifacts/7': dict(id=7, name='retained', size_in_bytes=len(bundle), digest='sha256:' + pin['sha256'],
                                      expired=False, workflow_run=dict(id=5, head_sha='publisher'))}
        if mutation == 'expired': metadata['actions/artifacts/7']['expired'] = True
        if mutation == 'job': metadata['actions/jobs/6']['steps'] = []
        if mutation == 'digest': pin['sha256'] = '0' * 64
        if mutation == 'size': pin['bytes'] += 1
        def download(artifact, path):
            check(artifact == 7, 'Requested an original artifact')
            path.write_bytes(bundle)
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'original.zip'
            with patch.object(recovery, 'configuration', return_value={'743': dict(origin=origin, republished=pin)}):
                recovery.recover(743, target, metadata.__getitem__, download)
            check(target.read_bytes() == content, 'Recovered bytes differ')
    exercise()
    for mutation in ('original', 'publisher', 'content', 'extra', 'traversal', 'duplicate', 'symlink',
                     'expired', 'job', 'digest', 'size'):
        rejects(lambda: exercise(mutation), 'Accepted tampered recovery: ' + mutation)


def actual(directory):
    metadata = json.loads((directory / 'api-metadata.json').read_bytes())
    real_recover = recovery.recover
    requested = []
    def api(endpoint):
        requested.append(endpoint)
        # Only republication metadata may be requested, never expired originals.
        return copy.deepcopy(metadata[endpoint])
    def download(artifact, path):
        core = {13976632507: 743, 13150348411: 614}[artifact]
        shutil.copyfile(directory / f'retained-core{core}.zip', path)
    def offline(core, path):
        return real_recover(core, path, api, download)

    pin = baseline.configuration()
    with zipfile.ZipFile(directory / 'core743.zip') as archive:
        baseline.verify_recovered_inventory(archive, pin)
        baseline.libhac_members(archive, pin)
        class Changed:
            def __init__(self, name): self.name = name
            def __getattr__(self, name): return getattr(archive, name)
            def namelist(self): return archive.namelist()
            def infolist(self): return archive.infolist()
            def getinfo(self, name): return archive.getinfo(name)
            def read(self, name):
                value = archive.read(name)
                return value + b'changed' if name == self.name else value
        for name in ('baseline-engine82/authentication/result.json',
                     'baseline-engine82/runtime-validation/result.json',
                     'baseline-engine82/ios-arm64/identity.json'):
            rejects(lambda: baseline.verify_recovered_inventory(Changed(name), pin), 'Accepted changed history: ' + name)
        for name in ('libhac-feed/Ryujinx.LibHac.0.21.0-alpha.129.nupkg', 'libhac-upstream-source.tar',
                     'libhac-generated-source.zip', 'libhac-identity.json', 'baseline-engine82/libhac-reuse.json'):
            rejects(lambda: baseline.libhac_members(Changed(name), pin), 'Accepted changed LibHac: ' + name)

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / 'build-utils').symlink_to(ROOT / 'build-utils', target_is_directory=True)
        (root / 'docs').symlink_to(ROOT / 'docs', target_is_directory=True)
        out = root / 'dist/melonx'
        with patch.object(recovery, 'recover', offline), patch.object(baseline, 'ROOT', root):
            dma.prepare_dependencies()
            engine = root / 'engine'
            engine.mkdir()
            with patch.dict(os.environ, MELONX_AUTHENTICATED_BASELINE=str(root / baseline.ARCHIVE)):
                feed, package = baseline.reuse_libhac(engine, root / baseline.LIBHAC_SOURCE)
            check(feed.is_dir() and bool(package), 'LibHac reuse failed')
            native = directory / 'native.zip'
            if native.is_file():
                recovery.retained_components.safe_extract(native, root / 'dist/melonx-native')
                baseline.dependencies()
                check((out / 'native-dependencies-reused.json').is_file(), 'Native reuse proof missing')
            with zipfile.ZipFile(directory / 'core743.zip') as archive:
                for name in archive.namelist():
                    if name.startswith('baseline-engine82/') and not name.endswith('/'):
                        check((out / name).read_bytes() == archive.read(name), 'Historical bytes changed: ' + name)
            receipt = json.loads((out / 'baseline-recovery.json').read_bytes())
            check(receipt['originalEngine82ArchiveRecovered'] is False and
                  receipt['originalEngine82BinariesRecovered'] is False, 'Recovery overstates scope')
        with patch.object(recovery, 'recover', offline), patch.object(dma, 'ARCHIVE', root / '614.zip'), \
                patch.object(dma, 'EVIDENCE', out / 'core-validation'):
            path = dma.prior_archive()
            check(baseline.digest(path) == dma.BASELINE['sha256'], '614 original bytes changed')
    expected_requests = {f"actions/{kind}/{spec['republished'][key]}"
                         for spec in recovery.configuration().values() if isinstance(spec, dict)
                         for kind, key in [('runs', 'run'), ('jobs', 'job'), ('artifacts', 'artifact')]}
    check(set(requested) == expected_requests, 'Unexpected metadata requests')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path)
    args = parser.parse_args()
    synthetic()
    if args.archives:
        actual(args.archives)
    print(json.dumps(dict(result='passed', checks=checks, realArchivesChecked=bool(args.archives),
                         buildsRun=False, historicalTestsReexecuted=False)))
