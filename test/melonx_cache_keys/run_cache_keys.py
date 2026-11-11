#!/usr/bin/env python3
"""Lot 10: a MoltenVK pipeline cache under MeloNX's descriptor set layouts, with whole configurations (shipped: the
control) and with cache keys (fifth part of build-utils/melonx/moltenvk/rewindbox-moltenvk.patch: the candidate), on the
macOS runner's real Metal device.

IPA 724, Hogwarts Legacy (pid 49375): 792.03 MiB of pipeline cache data for 4 669 libraries, 177 876 bytes each. MeloNX
declares 261 bindings for a vertex + fragment program; with Metal argument buffers MoltenVK lists each once per Metal
stage in every shader's conversion configuration (1 305 entries of 134 bytes serialized, 136 in memory: 174 870 bytes)
and keeps the configuration with each cached library. So the data, and the heap of every cache holding the libraries,
is mostly those tables; the compressed MSL the Core 721 mapping references is the small rest (which is why that change
showed nothing on the device). Only the bindings a shader uses decide a lookup (matches, alignWith).

One MoltenVK build (pinned revision + the recipe patch), control and candidate in the same binary
(MVK_CONFIG_REWINDBOX_FULL_CACHE_KEYS keeps whole configurations):
1. cache_key_property_test: MoltenVK's own matches() and alignWith() give the same answers and the same used flags with
   a key as with the whole configuration, on MeloNX-shaped and adversarial configurations; a prune without the order
   rule is caught.
2. mvk_cache_keys_test, each in a new process, same shaders:
   control-save, candidate-save            the data of MVK_BENCH_ROUNDS rounds (13 libraries, 36 pipelines each);
   control-load-full                       shipped behaviour on shipped data (RewindBox's flow: mapped file, staging
                                           cache with the private pNext structure, merge into main, staging destroyed);
   candidate-load-full                     the candidate on shipped data: the migration of a player's cache;
   candidate-load-key                      the candidate on its own data;
   control-load-key                        the shipped behaviour on the candidate's data (a driver without this change).
   Required of every load: no pipeline missing with FAIL_ON_PIPELINE_COMPILE_REQUIRED, nothing converted from SPIR-V
   again, one more pipeline of each program of the last round found; of every run: the 24 draws give the colours of
   the bound resources, the same bytes in all six runs. Required of the candidate: the data it writes after loading
   shipped data has the size of its own; a load keeps no more bindings than a tenth of those shipped data hold; its
   footprint after the load is lower than the control's by at least half of the tables' bytes.
Recorded: data sizes, the footprint at each step, load, lookup, size query and write times.
Writes dist/melonx-cache-keys/report.json. macOS runner, not an iPhone: no device figure is claimed from it.
"""
import hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PIN = json.loads((ROOT / 'build-utils/melonx/moltenvk-rebuild.json').read_text())
PATCH = ROOT / 'build-utils/melonx/moltenvk/rewindbox-moltenvk.patch'
OUT = ROOT / 'dist/melonx-cache-keys'
WORK = ROOT / '.cache-keys'
SHADERS = HERE / 'shaders.spvz'
ROUNDS = os.environ.get('MVK_BENCH_ROUNDS', '60')
SPIRV_CROSS = 'https://github.com/KhronosGroup/SPIRV-Cross.git'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sh(args, cwd=None, log=None, env=None):
    start = time.time()
    result = subprocess.run([str(a) for a in args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', env=env)
    if log:
        (OUT / log).write_text(result.stdout)
    print(f"$ {' '.join(str(a) for a in args)[:300]}  [{result.returncode}, {time.time() - start:.0f} s]", flush=True)
    if result.returncode:
        print('\n'.join(result.stdout.splitlines()[-80:]), flush=True)
        raise SystemExit(f'{args[0]} failed')
    return result.stdout


def checkout(target, repository, revision):
    if not (target / '.git').exists():
        sh(['git', 'init', '-q', target])
        sh(['git', '-C', target, 'remote', 'add', 'origin', repository])
    sh(['git', '-C', target, 'fetch', '-q', '--depth', '1', 'origin', revision])
    sh(['git', '-C', target, 'checkout', '-q', '--force', '--detach', 'FETCH_HEAD'])


def property_test(moltenvk):
    """MoltenVK's converter source and the pinned SPIRV-Cross, compiled for the host with the property test."""
    cross = WORK / 'SPIRV-Cross'
    checkout(cross, SPIRV_CROSS, (moltenvk / 'ExternalRevisions/SPIRV-Cross_repo_revision').read_text().strip())
    build = WORK / 'property'
    build.mkdir(parents=True, exist_ok=True)
    converter = moltenvk / 'MoltenVKShaderConverter/MoltenVKShaderConverter'
    includes = ['-I', cross, '-I', moltenvk / 'Common', '-I', converter]
    probe = subprocess.run(['c++', '-x', 'c++', '-E', '-'], input='#include <TargetConditionals.h>\n', capture_output=True, text=True)
    if probe.returncode:
        includes = ['-I', HERE / 'host'] + includes   # a host without Apple's header
    sources = [HERE / 'cache_key_property_test.cpp', HERE / 'host/converter_stubs.cpp', converter / 'SPIRVToMSLConverter.cpp'] + \
              [cross / (name + '.cpp') for name in ('spirv_cross', 'spirv_parser', 'spirv_cross_parsed_ir', 'spirv_cfg', 'spirv_glsl', 'spirv_msl')]
    binary = build / 'cache_key_property_test'
    sh(['c++', '-std=c++17', '-O1', '-w', *includes, *sources, '-o', binary], log='build-property-test.log')
    seed = int(os.environ.get('GITHUB_RUN_ID', str(int(time.time())))) % 1_000_000_007
    result = json.loads(sh([binary, seed, 400]).strip().splitlines()[-1])
    assert result['result'] == 'passed' and result['naivePruneCaught'] > 0 and result['lookupsMatching'] > 0 and result['lookupsNotMatching'] > 0, result
    result['seed'] = seed
    print('property test', json.dumps(result), flush=True)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    moltenvk = WORK / 'MoltenVK'
    checkout(moltenvk, PIN['repository'], PIN['revision'])
    sh(['git', '-C', moltenvk, 'apply', PATCH])
    properties = property_test(moltenvk)
    if '--property-only' in sys.argv:
        (OUT / 'report.json').write_text(json.dumps({'propertyTest': properties}, indent=1) + '\n')
        return
    sh([moltenvk / 'fetchDependencies', '--macos'], cwd=moltenvk, log='fetchDependencies.log')
    sh(['make', 'macos'], cwd=moltenvk, log='make-macos.log')
    library = moltenvk / 'Package/Latest/MoltenVK/dynamic/dylib/macOS/libMoltenVK.dylib'
    binary = OUT / 'mvk_cache_keys_test'
    sh(['clang++', '-std=c++17', '-O1', '-Wall', '-Wno-unused-function', '-I', moltenvk / 'Package/Latest/MoltenVK/include',
        HERE / 'mvk_cache_keys_test.cpp', library, '-lz', '-o', binary, '-Wl,-rpath,' + str(library.parent)], log='build-test.log')
    salt = int(os.environ.get('GITHUB_RUN_ID', str(int(time.time())))) % 1_000_000_007
    base = dict(os.environ, MVK_CONFIG_PERFORMANCE_TRACKING='1', MVK_CONFIG_LOG_LEVEL='3', MVK_BENCH_ROUNDS=ROUNDS)
    base.pop('MVK_CONFIG_REWINDBOX_FULL_CACHE_KEYS', None)
    full, key = OUT / 'full.bin', OUT / 'key.bin'
    runs = [('control-save', True, 'save', full, None), ('candidate-save', False, 'save', key, None),
            ('control-load-full', True, 'load', full, OUT / 'control-load-full.bin'),
            ('candidate-load-full', False, 'load', full, OUT / 'candidate-load-full.bin'),
            ('candidate-load-key', False, 'load', key, OUT / 'candidate-load-key.bin'),
            ('control-load-key', True, 'load', key, OUT / 'control-load-key.bin'),
            # Again, for the spread of the footprints and times.
            ('control-load-full-2', True, 'load', full, OUT / 'control-load-full-2.bin'),
            ('candidate-load-full-2', False, 'load', full, OUT / 'candidate-load-full-2.bin'),
            ('candidate-load-key-2', False, 'load', key, OUT / 'candidate-load-key-2.bin')]
    results, argument_buffers = {}, None
    for name, control, mode, data, written in runs:
        environment = dict(base)
        if control:
            environment['MVK_CONFIG_REWINDBOX_FULL_CACHE_KEYS'] = '1'
        arguments = [str(binary), str(SHADERS), str(salt), str(OUT / (name + '.json')), mode, str(data)] + ([str(written)] if written else [])
        start = time.time()
        run = subprocess.run(arguments, capture_output=True, text=True, errors='replace', timeout=5400, env=environment)
        (OUT / (name + '.log')).write_text(run.stdout + run.stderr)
        if run.returncode:
            print(run.stdout[-3000:], run.stderr[-3000:], flush=True)
            raise SystemExit(f'{name}: exit {run.returncode}')
        result = json.loads((OUT / (name + '.json')).read_text())
        text = run.stdout + run.stderr
        if argument_buffers is None:
            found = [line for line in text.splitlines() if 'Descriptor sets binding resources using' in line]
            argument_buffers = found[0].split('Descriptor sets binding resources using ')[1].strip() if found else 'not stated'
        result['seconds'] = round(time.time() - start, 1)
        if mode == 'load':
            lines = [line for line in text.splitlines() if 'RewindBox pipeline cache load:' in line]
            assert len(lines) == 1, f'{name}: load lines {lines}'
            line = lines[0].split('RewindBox pipeline cache load: ')[1]
            match = re.match(r"(\d+) shader libraries from (\d+) bytes, resource bindings (\d+) read (\d+) kept; "
                             r"compressed MSL referenced in the caller's data; pNext types 0x52425831\.", line)
            assert match, f'{name}: load line {line}'
            result.update(loadLine=line, librariesRead=int(match.group(1)), bindingsRead=int(match.group(3)), bindingsKept=int(match.group(4)))
            assert result['missing'] == 0 and result['againMissing'] == 0, f'{name}: every pipeline is found in the loaded cache'
            assert result['mvkSpirvToMsl']['count'] == 0, f'{name}: nothing converted from SPIR-V again'
            assert result['again'] == 48
        assert result['writeResult'] == 0 and result['draws'] == 24, f'{name}: data written, 24 draws'
        assert result['wrongPixels'] == 0 and result['pixelsUnchangedByContents'] == 0, f'{name}: every bound resource reaches its shader: {result["pixels"]}'
        results[name] = result
        print(name, json.dumps({k: v for k, v in result.items() if k != 'pixels'}), flush=True)

    first = results['control-save']
    for name, result in results.items():
        assert result['pixels'] == first['pixels'], f'{name}: the same pixels as a pipeline compiled by the control'
        assert result['pipelines'] == first['pipelines'] and result['shaderModules'] == first['shaderModules']
    libraries = results['control-load-full']['librariesRead']
    assert libraries == first['shaderModules'], 'one library per shader module'
    # Sizes: the candidate's data is the same whether it built the cache or read shipped data; the control keeps what
    # it reads (whole from shipped data, keys from the candidate's).
    assert results['control-load-full']['bytes'] == first['bytes'] == full.stat().st_size
    assert results['candidate-load-full']['bytes'] == results['candidate-save']['bytes'] == key.stat().st_size, 'a migrated cache is written at the key size'
    assert results['candidate-load-key']['bytes'] == key.stat().st_size and results['control-load-key']['bytes'] == key.stat().st_size
    assert key.stat().st_size < full.stat().st_size
    for name in ('control-load-full', 'control-load-full-2'):
        assert results[name]['bindingsKept'] == results[name]['bindingsRead'], f'{name}: the control keeps every binding'
    for name in ('candidate-load-full', 'candidate-load-full-2'):
        assert results[name]['bindingsRead'] == results['control-load-full']['bindingsRead']
        assert results[name]['bindingsKept'] * 10 <= results[name]['bindingsRead'], f'{name}: at most a tenth of the bindings kept'
    for name in ('candidate-load-key', 'candidate-load-key-2', 'control-load-key'):
        assert results[name]['bindingsRead'] == results[name]['bindingsKept'] == results['candidate-load-full']['bindingsKept'], f'{name}: the data holds keys'
    table_mib = (results['control-load-full']['bindingsRead'] - results['candidate-load-full']['bindingsKept']) * 136 / 1048576

    def growth(name, step):
        return round(results[name][step] - results[name]['footprintStartMiB'], 1)

    steps = ('footprintAfterStagingMiB', 'footprintAfterMergeMiB', 'footprintAfterDestroyMiB', 'footprintAfterPipelinesMiB', 'footprintAfterWriteMiB')
    loads = [name for name in results if '-load-' in name]
    summary = {name: {'footprintGrowthMiB': {step[len('footprintAfter'):-3]: growth(name, step) for step in steps},
                      'loadMs': round(results[name]['loadMs']), 'pipelinesMs': round(results[name]['createMs']),
                      'oneMorePipelineMs': round(results[name]['againMs'] / results[name]['again'], 3),
                      'sizeQueryMs': round(results[name]['sizeQueryMs'], 2), 'writeMs': round(results[name]['writeMs'], 1),
                      'bytes': results[name]['bytes']} for name in loads}
    for control, candidate in (('control-load-full', 'candidate-load-full'), ('control-load-full-2', 'candidate-load-full-2')):
        saved = growth(control, 'footprintAfterDestroyMiB') - growth(candidate, 'footprintAfterDestroyMiB')
        assert saved >= table_mib / 2, f'{candidate}: {saved:.1f} MiB less than the control after the load, tables {table_mib:.1f} MiB'
        peak = growth(control, 'footprintAfterMergeMiB') - growth(candidate, 'footprintAfterMergeMiB')
        assert peak >= table_mib, f'{candidate}: {peak:.1f} MiB less at the merge (two copies of the tables, {table_mib:.1f} MiB each)'
        assert results[candidate]['againMs'] <= results[control]['againMs'] * 1.5, f'{candidate}: a lookup is not slower'
    report = {'identity': {'moltenvk': {k: PIN[k] for k in ('repository', 'tag', 'revision')},
                           'patch': {'path': PATCH.relative_to(ROOT).as_posix(), 'sha256': sha(PATCH)},
                           'library': {'sha256': sha(library), 'bytes': library.stat().st_size},
                           'test': sha(HERE / 'mvk_cache_keys_test.cpp'), 'propertyTest': sha(HERE / 'cache_key_property_test.cpp'),
                           'shaders': sha(SHADERS), 'rounds': int(ROUNDS), 'salt': salt, 'descriptorSets': argument_buffers,
                           'xcode': sh(['xcodebuild', '-version']).splitlines()[:2], 'os': sh(['sw_vers']).split()},
              'propertyTest': properties,
              'data': {'libraries': libraries, 'wholeBytes': full.stat().st_size, 'keyBytes': key.stat().st_size,
                       'wholeBytesPerLibrary': round(full.stat().st_size / libraries), 'keyBytesPerLibrary': round(key.stat().st_size / libraries),
                       'bindingsPerLibraryWhole': round(results['control-load-full']['bindingsRead'] / libraries, 1),
                       'bindingsPerLibraryKept': round(results['candidate-load-full']['bindingsKept'] / libraries, 1),
                       'tablesInMemoryMiB': round(table_mib, 1)},
              'loads': summary, 'results': results,
              'limits': 'macOS runner (its Metal device and driver), synthetic shaders: sizes, counts and the equality of behaviour hold '
                        'for any device; the footprints and times are this runner\'s. Nothing here is an iPhone measurement.'}
    (OUT / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print('data:', json.dumps(report['data']), flush=True)
    print('loads:', json.dumps(summary, indent=1), flush=True)


if __name__ == '__main__':
    main()
