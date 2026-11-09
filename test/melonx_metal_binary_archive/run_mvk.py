#!/usr/bin/env python3
"""Lot 7: build MoltenVK (the revision MeloNX embeds) for macOS with the binary archive prototype and exercise it.

On a Mac with Xcode (the GitHub macOS runner; its Metal device is an "Apple Paravirtual device", not an iPhone):
1. fetch Khronos MoltenVK at the revision of build-utils/melonx/moltenvk-rebuild.json, apply
   build-utils/melonx/metal-archive/moltenvk-v1.4.2-binary-archives.patch, build it for macOS (fetchDependencies, make);
2. check that the built library carries the prototype, build mvk_archive_test.cpp against it;
3. run every session below as its own process, in isolated directories under dist/, never a player's cache.

Metal's own caches (com.apple.metal* under the user's cache directory) are found by what the first session made grow;
"system cache removed" deletes exactly those, so the next process compiles as on a cold system while the prototype's
archive stays. Writes dist/melonx-metal-archive-mvk/report.json; exits non-zero when an expectation fails, after
recording every session.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PIN = json.loads((ROOT / 'build-utils/melonx/moltenvk-rebuild.json').read_text())
PATCH = ROOT / 'build-utils/melonx/metal-archive/moltenvk-v1.4.2-binary-archives.patch'
OUT = ROOT / 'dist/melonx-metal-archive-mvk'
WORK = ROOT / '.metal-archive'
PIPELINES = 68  # 62 graphics + 6 compute
failures = []
sessions = []


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sh(args, cwd=None, log=None, check=True):
    start = time.time()
    result = subprocess.run([str(a) for a in args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
    if log:
        (OUT / 'logs' / log).write_text(result.stdout)
    print(f"$ {' '.join(str(a) for a in args)}  [{result.returncode}, {time.time() - start:.0f} s]", flush=True)
    if check and result.returncode:
        lines = result.stdout.splitlines()
        errors = [line for line in lines if ' error: ' in line or line.startswith('error:') or 'fatal error' in line]
        print('\n'.join(errors[:80] + ['--- last lines ---'] + lines[-60:]), flush=True)
        raise SystemExit(f'{args[0]} failed')
    return result.stdout


def build_moltenvk():
    target = WORK / 'MoltenVK'
    if not (target / '.git').exists():
        sh(['git', 'init', '-q', target])
        sh(['git', '-C', target, 'remote', 'add', 'origin', PIN['repository']])
    sh(['git', '-C', target, 'fetch', '-q', '--depth', '1', 'origin', PIN['revision']])
    sh(['git', '-C', target, 'checkout', '-q', '--force', '--detach', 'FETCH_HEAD'])
    assert sh(['git', '-C', target, 'rev-parse', 'HEAD']).strip() == PIN['revision'], 'not the pinned MoltenVK revision'
    sh(['git', '-C', target, 'apply', '--check', PATCH])
    sh(['git', '-C', target, 'apply', PATCH])
    changed = sh(['git', '-C', target, 'diff', '--stat'])
    sh([target / 'fetchDependencies', '--macos'], cwd=target, log='fetchDependencies.log')
    sh(['make', 'macos'], cwd=target, log='make-macos.log')
    package = target / 'Package/Latest/MoltenVK'
    library = package / 'dynamic/dylib/macOS/libMoltenVK.dylib'
    assert library.exists(), sorted(str(p.relative_to(target)) for p in (target / 'Package').rglob('*.dylib'))
    return target, package, library, changed


def metal_caches():
    roots = []
    for name in ('DARWIN_USER_CACHE_DIR', 'DARWIN_USER_TEMP_DIR'):
        value = subprocess.run(['getconf', name], capture_output=True, text=True).stdout.strip()
        if value:
            roots.append(Path(value))
    roots.append(Path.home() / 'Library/Caches')
    found = {}
    for root in roots:
        if not root.is_dir():
            continue
        for directory, names, _ in os.walk(root):
            if len(Path(directory).relative_to(root).parts) >= 5:
                names[:] = []
                continue
            for name in list(names):
                if name.startswith('com.apple.metal'):
                    names.remove(name)
                    path = Path(directory) / name
                    files = [f for f in path.rglob('*') if f.is_file()]
                    try:
                        found[str(path)] = (sum(f.stat().st_size for f in files), len(files))
                    except OSError:
                        found[str(path)] = (-1, len(files))
    return found


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / 'logs').mkdir(parents=True)
    WORK.mkdir(exist_ok=True)
    target, package, library, changed = build_moltenvk()
    data = library.read_bytes()
    markers = {m: m.encode() in data for m in ('RBX_MVK_BINARY_ARCHIVE_DIR', 'RewindBox Metal binary archives', 'rbx-mtl-archive-1')}
    identity = {'pin': {k: PIN[k] for k in ('repository', 'tag', 'revision')}, 'patch': {'path': str(PATCH.relative_to(ROOT)), 'sha256': sha(PATCH)},
                'patchApplied': changed.splitlines(), 'library': {'path': str(library.relative_to(target)), 'sha256': sha(library), 'bytes': library.stat().st_size},
                'markers': markers, 'platform': 'macOS (the prototype is not built for iOS here)',
                'xcode': subprocess.run(['xcodebuild', '-version'], capture_output=True, text=True).stdout.split('\n')[:2],
                'macOS': subprocess.run(['sw_vers', '-productVersion'], capture_output=True, text=True).stdout.strip()}
    (OUT / 'identity.json').write_text(json.dumps(identity, indent=1) + '\n')
    print(json.dumps(identity), flush=True)
    if not all(markers.values()):
        raise SystemExit('the built library does not carry the prototype')
    binary = OUT / 'mvk_archive_test'
    sh(['clang++', '-std=c++17', '-O1', '-Wall', '-I', package / 'include', HERE / 'mvk_archive_test.cpp', library, '-lz',
        '-Wl,-rpath,' + str(library.parent), '-o', binary], log='test-build.log')
    shaders = HERE / 'shaders.spvz'
    salt = int(os.environ.get('GITHUB_RUN_ID', str(int(time.time())))) % 1_000_000_007
    work = OUT / 'work'
    work.mkdir()
    caches = {'before': metal_caches(), 'grown': [], 'removals': 0}

    def remove_system_cache():
        for path in caches['grown']:
            shutil.rmtree(path, ignore_errors=True)
        caches['removals'] += 1

    def session(label, archive=None, args=(), salt_value=None, **settings):
        """One process. archive: the prototype's directory (None: the prototype is off, as upstream)."""
        index = len(sessions)
        output = work / f'session-{index:02d}.json'
        report = work / f'session-{index:02d}-archive.json'
        environment = dict(os.environ, MVK_CONFIG_PERFORMANCE_TRACKING='1', MVK_CONFIG_LOG_LEVEL='3')
        for key in list(environment):
            if key.startswith('RBX_MVK_BINARY_ARCHIVE'):
                del environment[key]
        if archive is not None:
            environment['RBX_MVK_BINARY_ARCHIVE_DIR'] = str(archive)
            environment['RBX_MVK_BINARY_ARCHIVE_REPORT'] = str(report)
            environment.setdefault('RBX_MVK_BINARY_ARCHIVE_SYNC_LOAD', '1')
            for key, value in settings.items():
                environment['RBX_MVK_BINARY_ARCHIVE_' + key] = str(value)
        start = time.time()
        run = subprocess.run(['/usr/bin/time', '-l', str(binary), str(shaders), str(salt_value if salt_value is not None else salt), str(output), *args],
                             capture_output=True, text=True, errors='replace', env=environment, timeout=1800)
        entry = {'label': label, 'archive': str(archive.relative_to(work)) if archive is not None else None, 'args': list(args),
                 'settings': {k: str(v) for k, v in settings.items()}, 'returncode': run.returncode, 'seconds': round(time.time() - start, 2)}
        if output.exists():
            entry['test'] = json.loads(output.read_text())
        if report.exists():
            entry['archiveReport'] = json.loads(report.read_text())
        for line in run.stderr.splitlines():
            if 'maximum resident set size' in line:
                entry['maxResidentMiB'] = round(int(line.split()[0]) / 1048576, 1)
            if 'peak memory footprint' in line:
                entry['peakFootprintMiB'] = round(int(line.split()[0]) / 1048576, 1)
        entry['archiveLog'] = [line[-700:] for line in (run.stdout + run.stderr).splitlines() if 'RewindBox Metal binary archives' in line][-3:]
        if run.returncode:
            entry['stderr'] = run.stderr[-3000:]
        sessions.append(entry)
        test, rep = entry.get('test', {}), entry.get('archiveReport', {})
        print(f"\n## {label} | rc {run.returncode} | {entry['seconds']} s | peak {entry.get('peakFootprintMiB')} MiB", flush=True)
        print('   test', json.dumps({k: test.get(k) for k in ('graphics', 'compute', 'createWallMs', 'absent', 'drawHash', 'computeHash', 'draws', 'dispatches',
                                                             'mvkSpirvToMsl', 'mvkMslCompile', 'mvkPipelineCompile', 'destroyDeviceMs', 'cacheReads') if k in test}), flush=True)
        if rep:
            print('   archive', json.dumps(rep), flush=True)
        if run.returncode:
            print(run.stderr[-1500:], flush=True)
        return entry

    def expect(condition, message, entry=None):
        if not condition:
            failures.append(message)
            print('   EXPECTATION FAILED: ' + message, flush=True)
            if entry is not None:
                entry.setdefault('failedExpectations', []).append(message)

    def created_all(entry, graphics=62, compute=6):
        test = entry.get('test', {})
        return entry['returncode'] == 0 and test.get('graphics', {}).get('created') == graphics and test.get('compute', {}).get('created') == compute

    def same_result(entry, reference):
        a, b = entry.get('test', {}), reference.get('test', {})
        return bool(a.get('drawHash')) and a.get('drawHash') == b.get('drawHash') and a.get('computeHash') == b.get('computeHash') and a.get('draws') == b.get('draws')

    def segments(directory):
        return sorted(str(p.relative_to(directory)) for p in Path(directory).rglob('seg-*') if p.is_file())

    # --- Reference: the prototype off (the library behaves as upstream) -----------------------------------------------
    reference = session('reference, cold (first run of this salt)')
    after = metal_caches()
    caches['grown'] = sorted(path for path, value in after.items() if caches['before'].get(path) != value)
    print('system Metal cache directories that changed:', caches['grown'], flush=True)
    expect(created_all(reference) and reference['test']['draws'] == 38 and reference['test']['dispatches'] == 6 and reference['test']['nonBlackPixels'] > 0,
           'reference: every pipeline is created, draws and computes', reference)
    warm = session('reference, system cache warm')
    expect(created_all(warm) and same_result(warm, reference), 'reference warm: same result', warm)
    remove_system_cache()
    cold2 = session('reference, system cache removed')
    expect(created_all(cold2) and same_result(cold2, reference), 'reference cold again: same result', cold2)

    # --- Collection, then reuse in new processes ------------------------------------------------------------------------
    archive = work / 'archive'
    remove_system_cache()
    collect = session('collection (empty archive directory, system cache removed)', archive)
    rep = collect.get('archiveReport', {})
    expect(created_all(collect) and same_result(collect, reference), 'collection: every pipeline created by the normal compilation, same result', collect)
    expect(rep.get('lookupsWithoutArchive') == PIPELINES and rep.get('hits') == 0 and rep.get('collected') == PIPELINES and rep.get('collectQueued') == PIPELINES and
           rep.get('addErrors') == 0 and rep.get('saves', 0) >= 1 and rep.get('saveErrors') == 0 and rep.get('savedBytes', 0) > 0,
           'collection: 68 pipelines collected and saved', collect)
    expect(len(segments(archive)) == 1, 'collection: one segment file published: %s' % segments(archive), collect)
    before = work / 'archive-first-segment'
    shutil.copytree(archive, before)

    reuse_warm = session('reuse, system cache warm', archive)
    rep = reuse_warm.get('archiveReport', {})
    expect(created_all(reuse_warm) and same_result(reuse_warm, reference), 'reuse warm: same result', reuse_warm)
    expect(rep.get('loadedSegments') == 1 and rep.get('hits') == PIPELINES and rep.get('misses') == 0 and rep.get('collected') == 0 and
           reuse_warm['test'].get('mvkPipelineCompile', {}).get('count') == 0,
           'reuse warm: the 68 pipelines come from the archive, none compiled', reuse_warm)
    remove_system_cache()
    reuse_cold = session('reuse, system cache removed, strict', archive, STRICT=1)
    rep = reuse_cold.get('archiveReport', {})
    expect(created_all(reuse_cold) and same_result(reuse_cold, reference), 'reuse strict, cold system cache: every pipeline served by the archive, same result', reuse_cold)
    expect(rep.get('hits') == PIPELINES and rep.get('misses') == 0 and reuse_cold['test'].get('mvkPipelineCompile', {}).get('count') == 0,
           'reuse strict: 68 archive hits, no compilation of a pipeline', reuse_cold)
    remove_system_cache()
    reuse_cold2 = session('reuse, system cache removed again, not strict', archive)
    expect(created_all(reuse_cold2) and same_result(reuse_cold2, reference) and reuse_cold2.get('archiveReport', {}).get('hits') == PIPELINES, 'reuse cold 2: 68 hits, same result', reuse_cold2)

    # --- A variant no archive holds ---------------------------------------------------------------------------------------
    strict_absent = session('variant left out, strict', archive, ('--absent',), STRICT=1)
    absent = strict_absent.get('test', {}).get('absent', {})
    expect(created_all(strict_absent) and absent.get('created') is False and absent.get('result') != 0 and strict_absent.get('archiveReport', {}).get('misses') == 1,
           'strict: the variant left out misses (pipeline refused), the 68 others are served', strict_absent)
    remove_system_cache()
    normal_absent = session('variant left out, normal operation (system cache removed)', archive, ('--absent',))
    absent, rep = normal_absent.get('test', {}).get('absent', {}), normal_absent.get('archiveReport', {})
    expect(created_all(normal_absent) and absent.get('created') is True and absent.get('result') == 0 and rep.get('hits') == PIPELINES and rep.get('misses') == 1 and
           normal_absent['test'].get('mvkPipelineCompile', {}).get('count') == 1 and rep.get('collected') == 1 and rep.get('saves') == 1,
           'normal: the variant left out is compiled as before (one compilation), collected and saved', normal_absent)
    expect(len(segments(archive)) == 2, 'a second segment is published, the first untouched: %s' % segments(archive), normal_absent)
    expect(sha(next(archive.rglob('seg-000001-*'))) == sha(next(before.rglob('seg-000001-*'))), 'the first segment is byte-identical after the second session', normal_absent)
    strict_both = session('variant collected, strict (two segments)', archive, ('--absent',), STRICT=1)
    absent, rep = strict_both.get('test', {}).get('absent', {}), strict_both.get('archiveReport', {})
    expect(created_all(strict_both) and absent.get('created') is True and rep.get('loadedSegments') == 2 and rep.get('hits') == PIPELINES + 1 and rep.get('misses') == 0,
           'strict with two segments: 69 pipelines served, the collected variant among them', strict_both)
    identity_name = rep.get('identity') or 'id-unknown'

    # --- Memory floor: nothing is collected, lookups and draws continue ---------------------------------------------------
    held = session('memory floor (collection held)', work / 'archive-memory', MIN_FREE_MB=1048576)
    rep = held.get('archiveReport', {})
    expect(created_all(held) and same_result(held, reference) and rep.get('collectHeldForMemory') == PIPELINES and rep.get('collected') == 0 and rep.get('saves') == 0,
           'memory floor: 68 collections held, none done, every pipeline still created', held)
    held_reuse = session('memory floor with a loaded archive', archive, MIN_FREE_MB=1048576)
    expect(created_all(held_reuse) and held_reuse.get('archiveReport', {}).get('hits') == PIPELINES, 'memory floor: lookups still served by the archive', held_reuse)

    # --- A save that fails keeps the published segment --------------------------------------------------------------------
    read_only = work / 'archive-read-only'
    shutil.copytree(before, read_only)
    first = next(read_only.rglob('seg-000001-*'))
    digest = sha(first)
    os.chmod(first.parent, 0o555)
    try:
        failed_save = session('save failure (directory read-only)', read_only, ('--absent',))
    finally:
        os.chmod(first.parent, 0o755)
    rep = failed_save.get('archiveReport', {})
    expect(created_all(failed_save) and failed_save['test'].get('absent', {}).get('created') is True and rep.get('collected') == 1 and rep.get('saveErrors', 0) >= 1 and rep.get('saves') == 0,
           'failed save: the pipeline is still created, the save fails and is counted', failed_save)
    expect(segments(read_only) == segments(before) and sha(first) == digest, 'failed save: the published segment is untouched, nothing else left', failed_save)
    after_failure = session('after the failed save, strict', read_only, STRICT=1)
    expect(created_all(after_failure) and after_failure.get('archiveReport', {}).get('hits') == PIPELINES, 'after a failed save the earlier segment still serves every pipeline', after_failure)

    # --- Damaged, cut, refused, other identities ---------------------------------------------------------------------------
    def damaged_copy(name, change):
        directory = work / name
        shutil.copytree(before, directory)
        segment = next(directory.rglob('seg-000001-*'))
        content = bytearray(segment.read_bytes())
        segment.write_bytes(change(content))
        return directory

    def overwrite_middle(content):
        middle = len(content) // 2
        content[middle:middle + 4096] = b'\xA5' * 4096
        return content

    damaged = session('damaged segment (4 KiB overwritten, same size)', damaged_copy('archive-damaged', overwrite_middle))
    rep = damaged.get('archiveReport', {})
    expect(created_all(damaged) and same_result(damaged, reference) and rep.get('removedDamaged') == 1 and rep.get('loadedSegments') == 0 and rep.get('hits') == 0 and
           rep.get('collected') == PIPELINES and rep.get('saves', 0) >= 1,
           'damaged segment: removed by its checksum, every pipeline compiled as before, a new segment saved', damaged)
    unverified = session('damaged segment, checksum check off (Metal alone)', damaged_copy('archive-damaged-unverified', overwrite_middle), VERIFY=0)
    rep = unverified.get('archiveReport', {})
    expect(created_all(unverified) and same_result(unverified, reference) and rep.get('hits', 0) + rep.get('misses', 0) == PIPELINES,
           'damaged segment without our check: every pipeline is created and draws the same (Metal misses its damaged entries)', unverified)
    cut = session('cut segment (half the file)', damaged_copy('archive-cut', lambda content: content[:len(content) // 2]))
    rep = cut.get('archiveReport', {})
    expect(created_all(cut) and same_result(cut, reference) and rep.get('removedDamaged') == 1 and rep.get('loadedSegments') == 0, 'cut segment: removed, normal compilation', cut)

    refused_directory = work / 'archive-refused' / identity_name
    refused_directory.mkdir(parents=True)
    text = b'not a Metal binary archive\n' * 64
    refused_file = refused_directory / f'seg-000001-{len(text)}-{hashlib.sha256(text).hexdigest()[:16]}.mtlarchive'
    refused_file.write_bytes(text)
    refused1 = session('intact file Metal refuses, first launch', work / 'archive-refused', SESSION_MAX_ADDS=0)
    rep = refused1.get('archiveReport', {})
    expect(created_all(refused1) and rep.get('refusedSegments') == 1 and rep.get('removedRefused') == 0 and refused_file.exists() and Path(str(refused_file) + '.refused').exists(),
           'first refusal: the file is kept and marked', refused1)
    refused2 = session('intact file Metal refuses, second launch', work / 'archive-refused', SESSION_MAX_ADDS=0)
    rep = refused2.get('archiveReport', {})
    expect(created_all(refused2) and rep.get('refusedSegments') == 1 and rep.get('removedRefused') == 1 and not refused_file.exists() and not Path(str(refused_file) + '.refused').exists(),
           'second refusal: the file and its mark are removed', refused2)

    identities = work / 'archive-identities'
    for name, age in (('id-00000000000000aa', 7200), ('id-00000000000000bb', 3600)):
        (identities / name).mkdir(parents=True)
        (identities / name / 'seg-000001-3-0000000000000000.mtlarchive').write_bytes(b'old')
        stamp = time.time() - age
        os.utime(identities / name, (stamp, stamp))
    other = session('archives of two other identities', identities, SESSION_MAX_ADDS=0)
    rep = other.get('archiveReport', {})
    expect(created_all(other) and rep.get('prunedIdentities') == 1 and rep.get('loadedSegments') == 0 and not (identities / 'id-00000000000000aa').exists() and
           (identities / 'id-00000000000000bb').exists() and (identities / identity_name).is_dir(),
           'other identities: never loaded; the most recent one kept, the older removed', other)

    # --- Bounds --------------------------------------------------------------------------------------------------------------
    bounded = work / 'archive-bounded'
    shutil.copytree(archive, bounded)
    two = session('two segments, at most two kept with this session\'s', bounded, ('--absent',), MAX_SEGMENTS=2)
    rep = two.get('archiveReport', {})
    expect(created_all(two) and rep.get('prunedSegments') == 1 and rep.get('loadedSegments') == 1 and rep.get('hits') == 1 and rep.get('misses') == PIPELINES and
           not list(bounded.rglob('seg-000001-*')) and len(segments(bounded)) == 2,
           'segment bound: the oldest segment removed, its pipelines compiled again and collected in the new segment', two)
    capped = session('session bound (10 collections)', work / 'archive-capped', SESSION_MAX_ADDS=10)
    rep = capped.get('archiveReport', {})
    expect(created_all(capped) and rep.get('collected') == 10 and rep.get('collectCapped') == PIPELINES - 10, 'session bound: 10 collected, 58 not queued', capped)

    # --- Concurrency: four creating threads, pipeline cache reads, saves every 4 additions, device destroyed at once ---------
    for round_index in range(3):
        directory = work / f'archive-threads-{round_index}'
        threaded = session(f'threads round {round_index + 1}: creation from 4 threads, cache reads, close at once', directory,
                           ('--threads', '4', '--cache-reads', '50', '--no-draw'), salt_value=salt + 10 + round_index, SAVE_EVERY=4)
        rep = threaded.get('archiveReport', {})
        accounted = rep.get('collected', 0) + rep.get('collectDroppedAtClose', 0) + rep.get('addErrors', 0)
        expect(created_all(threaded) and rep.get('collectQueued') == PIPELINES and accounted == PIPELINES and rep.get('addErrors') == 0 and rep.get('saveErrors') == 0,
               f'threads round {round_index + 1}: every pipeline created; queued collections all accounted for (collected or dropped at close)', threaded)
        again = session(f'threads round {round_index + 1}: next launch, 4 threads', directory, ('--threads', '4'), salt_value=salt + 10 + round_index)
        rep2 = again.get('archiveReport', {})
        expect(created_all(again) and rep2.get('hits') == rep.get('collected') and rep2.get('hits', 0) + rep2.get('misses', 0) == PIPELINES and again['test']['draws'] == 38,
               f'threads round {round_index + 1}: what was collected before the close is served at the next launch, the rest compiled', again)

    def figures(entry):
        test, rep = entry.get('test', {}), entry.get('archiveReport', {})
        return {'spirvToMslMs': test.get('mvkSpirvToMsl', {}).get('totalMs'), 'mslLibraryMs': test.get('mvkMslCompile', {}).get('totalMs'),
                'mslLibraries': test.get('mvkMslCompile', {}).get('count'), 'pipelineCompileMs': test.get('mvkPipelineCompile', {}).get('totalMs'),
                'pipelinesCompiled': test.get('mvkPipelineCompile', {}).get('count'), 'archiveHits': rep.get('hits'), 'archiveHitMs': rep.get('hitMs'),
                'archiveMisses': rep.get('misses'), 'archiveMissMs': rep.get('missMs'), 'graphicsCreateMs': test.get('graphics', {}).get('time', {}).get('totalMs'),
                'graphicsCreateMaxMs': test.get('graphics', {}).get('time', {}).get('maxMs'), 'computeCreateMs': test.get('compute', {}).get('time', {}).get('totalMs'),
                'collectMs': rep.get('addMs'), 'saveMs': rep.get('saveMs'), 'savedBytes': rep.get('savedBytes'), 'verifyMs': rep.get('verifyMs'), 'loadMs': rep.get('loadMs'),
                'destroyDeviceMs': test.get('destroyDeviceMs'), 'peakFootprintMiB': entry.get('peakFootprintMiB')}

    comparison = {entry['label']: figures(entry) for entry in (reference, warm, cold2, collect, reuse_warm, reuse_cold, reuse_cold2, normal_absent, damaged)}
    summary = {'device': reference.get('test', {}).get('device'), 'identity': identity, 'salt': salt, 'systemMetalCaches': caches['grown'],
               'comparison': comparison, 'failures': failures, 'sessions': sessions}
    (OUT / 'report.json').write_text(json.dumps(summary, indent=1) + '\n')
    shutil.rmtree(work, ignore_errors=True)
    binary.unlink(missing_ok=True)
    print('\n' + json.dumps({'comparison': comparison, 'failures': failures}, indent=1), flush=True)
    if failures:
        raise SystemExit(f'{len(failures)} expectation(s) failed')


if __name__ == '__main__':
    main()
