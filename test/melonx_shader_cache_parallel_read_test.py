#!/usr/bin/env python3
"""The disk shader cache is read by a few threads ahead of the GPU thread (adapt_shader_cache_parallel_read), before and after, production code.

Usage: melonx_shader_cache_parallel_read_test.py <final preparation containing the adapter>
       melonx_shader_cache_parallel_read_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control), candidate is the adapter applied to it,
which must be the final preparation byte for byte. The production Ryujinx.Graphics.Gpu project is built from the
candidate tree, then again in that tree with the adapter's two files put back as the control has them (every other
file of the engine is the control's, byte for byte: checked). test/melonx_shader_cache_parallel_read/Program.cs runs
the complete production load of each assembly (ParallelDiskCacheLoader.LoadShaders with the real host and guest
storage, serializer, specialization state, shader information and code tables; only the renderer is a double that
records every program it is asked to create) on cache directories it writes in the on-disk format, and on a real cache
when MELONX_SHADER_CACHE_DIR names one (guest.*, shared.*, vulkan_apple.*; read from there, altered only in copies,
never copied into the repository).

(a) Same result. For the control and for the candidate with its own thread count and with 0, 1, 2 and 3 read-ahead
threads: the programs created (stages, every byte of host code, shader information), in the same order; the programs
the two tables hold, in order (guest code and constant buffer bytes, which stages share one array, stage information,
the specialization state written back by the engine's serializer); the state callbacks; the engine's log; the error
count; the exception that leaves LoadShaders; every cache file afterwards. On a cache written here, on that cache
rebuilt by the engine, on a launch-shaped cache (1,000 programs with the host code sizes and compression of the real
cache measured), on caches of 0, 15 and 16 programs, and on 24 corrupt or truncated caches: shared, guest and host
tables and data cut or altered at program 70, an unknown compression, an invalid stage mask, guest indices past the
table and negative, a host table without header, wrong magic and version (the load stops at the same program with the
same error, rebuilds the same files or deletes the cache); a host table that ends early, no host files, older host
files, another code generation, a malformed host code, a program that fails to link (the same programs go to the
translator). (b) Cancellation: before the load, at program 50, at program 300 of the launch-shaped cache: the same
programs are created, LoadShaders returns within 250 ms and every read-ahead thread has ended when it returns (each
asks the scheduler class through Ryujinx.Common.HostThreadClass, whose fixture hooks record the threads).
(c) Memory: with the GPU thread held in the creation of program 24 of 64 programs of 1 MiB, the candidate reaches at
most the window (8 programs, the one at hand included) more than the control; with host codes above the 2 MiB limit,
nothing more. (d) Cost: the load of the launch-shaped cache rebuilt by the engine (and of the real cache), best of
alternated runs, control against candidate with its own thread count for this host, with 2 threads (the count on six
cores) and with none. (e) The journal line "shaderCache read" of each load and its counts.
Static checks: the adapter changes its two files only, each by its hunks only; the statements that read a program are
the control's, in their order; what creates and queues a program is the control's text. No device: the time a load
takes on an iPhone is known only from the "shaderCache read" line of a device run.
Writes dist/melonx/shader-cache-parallel-read-checks.json.
"""
from pathlib import Path
import filecmp, hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_shader_cache_parallel_read', _HOLD)
from adapt_shader_cache_parallel_read import apply, BASELINE, PAIRS, STORAGE, GUEST  # noqa: E402

GPU = 'src/Ryujinx.Graphics.Gpu/'
LOADER = GPU + 'Shader/DiskCache/ParallelDiskCacheLoader.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_shader_cache_parallel_read'
REAL_CACHE = os.environ.get('MELONX_SHADER_CACHE_DIR', '')
WINDOW, LIMIT, CLASS = 8, 2 * 1024 * 1024, 0x21
THREADS = {'1': 0, '2': 1, '3': 1, '4': 1, '6': 2, '8': 3, '12': 3, '16': 3, '64': 3}
# Measured on the host (see the adapter), launch-shaped cache, best of alternated runs: about 0.6 of the control's time
# with one read-ahead thread and about 0.45 with two. The bounds keep a margin for a loaded machine; a round that misses
# them is measured again (up to MORE_ROUNDS times) before the gate fails.
DEFAULT_FACTOR, TWO_FACTOR, SERIAL_FACTOR, SERIAL_MARGIN = 0.85, 0.80, 1.25, 40
ROUNDS, MORE_ROUNDS, LOADS = 3, 4, 4
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def between(text, start, end):
    left = text.index(start)
    return text[left:text.index(end, left) + len(end)]


def run(command, cwd, timeout, environment):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=environment, cwd=cwd)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    return result


READ_LINE = re.compile(
    r'read (\d+) of (\d+) programs read and queued in (\d+) ms \((all|cancelled|stopped by an error)\); GPU thread: waited (\d+) ms for a program '
    r'being read, read (\d+) programs itself in (\d+) ms \((\d+) ahead; (\d+) with a host code above (\d+) KiB\), created and queued the programs in '
    r'(\d+) ms \(link waits of a full queue included\), other link checks (\d+) ms; (\d+) read-ahead threads of (\d+) read (\d+) programs in (\d+) ms '
    r'of their own; host code (\d+) MiB; at most (\d+) programs read and not yet used \(most: (\d+)\); reading ahead (never failed|ended at a read '
    r'that failed) \(adapt_shader_cache_parallel_read\)')
READ_FIELDS = ('taken', 'entries', 'ms', 'end', 'waitMs', 'gpuRead', 'gpuReadMs', 'gpuAhead', 'left', 'limitKiB', 'createMs', 'checkMs', 'threads',
               'planned', 'threadRead', 'threadMs', 'hostMiB', 'window', 'most', 'ahead')


def read_line(text):
    found = READ_LINE.fullmatch(text or '')
    if found is None:
        return None
    return {name: (value if name in ('end', 'ahead') else int(value)) for name, value in zip(READ_FIELDS, found.groups())}


check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in BASELINE.items():
    check(sha(SOURCE / name) == expected, 'not the adapter\'s preparation: ' + name)
check(sorted(BASELINE) == sorted({name for name, _, _ in PAIRS}) == sorted([STORAGE, GUEST]), 'the adapter declares its two files')
real_cache = Path(REAL_CACHE).resolve() if REAL_CACHE else None
if real_cache is not None:
    check(all((real_cache / name).is_file() for name in ('guest.toc', 'guest.data', 'shared.toc', 'shared.data', 'vulkan_apple.toc', 'vulkan_apple.data')),
          'MELONX_SHADER_CACHE_DIR holds a cache with its host files')

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredPGO='0')
reports, texts, perf = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-shader-cache-read-') as temporary:
    temporary = Path(temporary).resolve()
    work = temporary / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)
    changed = apply(work)
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
    later = files_edited_later('adapt_shader_cache_parallel_read')
    for name in BASELINE:
        if name not in later:
            check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

    # Every source file of the engine but the two is the control's, byte for byte.
    different, compared = [], 0
    for path in sorted((SOURCE / 'src').rglob('*')):
        relative = path.relative_to(SOURCE)
        if path.is_file() and not path.is_symlink() and not {'bin', 'obj'} & set(relative.parts):
            compared += 1
            if not (work / relative).is_file() or not filecmp.cmp(path, work / relative, shallow=False):
                different.append(relative.as_posix())
    check(compared > 3000 and sorted(different) == sorted(BASELINE), 'only the two files differ from the control: ' + str(different[:8]))
    check(sum(1 for path in (work / 'src').rglob('*.cs') if not {'bin', 'obj'} & set(path.relative_to(work).parts)) ==
          sum(1 for path in (SOURCE / 'src').rglob('*.cs') if not {'bin', 'obj'} & set(path.relative_to(SOURCE).parts)), 'no source file added')
    for variant, tree in (('control', SOURCE), ('candidate', work)):
        texts[variant] = {name: (tree / name).read_text(encoding='utf-8-sig') for name in BASELINE}

    # The production assembly of the candidate, then of the control: the same tree with the two files put back.
    build = [DOTNET, 'build', str(work / (GPU + 'Ryujinx.Graphics.Gpu.csproj')), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false']
    output = work / (GPU + 'bin/Release/net10.0')
    engines = {}
    for variant in ('candidate', 'control'):
        if variant == 'control':
            for name in BASELINE:
                (work / name).write_text(texts['control'][name], encoding='utf-8')
        result = run(build, work, 3000, environment)
        check(result.returncode == 0, variant + ' production assembly builds: Ryujinx.Graphics.Gpu')
        engines[variant] = temporary / ('engine-' + variant)
        shutil.copytree(output, engines[variant])
    check(sha(engines['control'] / 'Ryujinx.Graphics.Gpu.dll') != sha(engines['candidate'] / 'Ryujinx.Graphics.Gpu.dll'), 'two different assemblies')
    shutil.rmtree(work)

    programs = {}
    for variant in ('control', 'candidate'):
        fixture = temporary / ('fixture-' + variant)
        fixture.mkdir()
        shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
        (fixture / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<LangVersion>preview</LangVersion><Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0067;CS0649</NoWarn>'
            '<TieredPGO>false</TieredPGO><ServerGarbageCollection>false</ServerGarbageCollection><InvariantGlobalization>true</InvariantGlobalization>'
            '</PropertyGroup><ItemGroup><Reference Include="' + str(engines[variant]) + '/*.dll" /></ItemGroup></Project>\n')
        result = run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'], fixture, 900, environment)
        check(result.returncode == 0, variant + ': the driver builds against the production assemblies')
        programs[variant] = fixture / 'bin/Release/net10.0/Fixture.dll'
        check(sha(programs[variant].parent / 'Ryujinx.Graphics.Gpu.dll') == sha(engines[variant] / 'Ryujinx.Graphics.Gpu.dll'), variant + ': the driver loads that assembly')

    for variant in ('control', 'candidate'):
        command = [DOTNET, str(programs[variant]), 'run', str(temporary / ('data-' + variant))] + ([str(real_cache)] if real_cache is not None else [])
        result = run(command, temporary, 2400, environment)
        check(result.returncode == 0, variant + ': the driver runs')
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps({variant: [dict(name=s['name'], ms={k: v['milliseconds'] for k, v in s['settings'].items()}) for s in reports[variant]['scenarios']]}), flush=True)

    # (d) Cost: both assemblies load the same directories, in alternated processes; the best load of each setting counts.
    measured = [('launch-shaped cache rebuilt by the engine', Path(reports['control']['setDirectories']['launch-rebuilt']))]
    if real_cache is not None:
        measured.append(('real cache', real_cache))
    for label, directory in measured:
        best, journal, before = {}, {}, {p.name: sha(p) for p in sorted(directory.iterdir())}

        def measure():
            for variant, settings in (('control', 'control'), ('candidate', 'default,2,0'), ('candidate', '0,2,default'), ('control', 'control')):
                result = run([DOTNET, str(programs[variant]), 'perf', str(directory), str(LOADS), settings], temporary, 1200, environment)
                check(result.returncode == 0, label + ': the cost is measured: ' + variant)
                for setting, value in json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{'))).items():
                    if setting not in best or value['best'] < best[setting]['best']:
                        best[setting], journal[setting] = value, read_line(value['journalRead'])

        def bounded():
            return (best['default']['best'] <= DEFAULT_FACTOR * best['control']['best'] and best['2']['best'] <= TWO_FACTOR * best['control']['best'] and
                    best['0']['best'] <= SERIAL_FACTOR * best['control']['best'] + SERIAL_MARGIN)

        rounds = 0
        while rounds < ROUNDS or (rounds < ROUNDS + MORE_ROUNDS and not bounded()):
            measure()
            rounds += 1
        check({p.name: sha(p) for p in sorted(directory.iterdir())} == before, label + ': the loads left the cache files as they were')
        perf[label] = dict(rounds=rounds, loadsPerRun=LOADS, best=best, journal=journal)
        print(json.dumps({label: {k: v['best'] for k, v in best.items()}, 'rounds': rounds}), flush=True)

control, candidate = reports['control'], reports['candidate']
check(not control['hasReadAhead'] and candidate['hasReadAhead'], 'the control has no read-ahead, the candidate has')
check(candidate['threadsForProcessors'] == THREADS, 'threads for the cores: with the GPU thread at most half of them read, never more than three threads, '
      'none on one core: ' + str(candidate['threadsForProcessors']))
check(candidate['window'] == WINDOW and candidate['maximumHostCodeSize'] == LIMIT, 'window of 8 programs, host codes of at most 2 MiB read ahead')
default_threads = candidate['defaultThreads']
check(default_threads == max(min(candidate['processors'] // 2 - 1, 3), 1 if candidate['processors'] > 1 else 0), 'this host\'s thread count: ' + str(default_threads))
check(control['codeGenVersion'] == candidate['codeGenVersion'] and control['sets'] == candidate['sets'], 'both read the same generated caches, byte for byte')
sets = control['sets']
check(sets['launch']['programs'] == 1000 and 2.8 <= sets['launch']['hostBytes'] / sets['launch']['hostCompressedBytes'] <= 3.8 and
      110_000 <= sets['launch']['hostBytes'] / 1000 <= 150_000 and sets['launch']['largestHostCode'] > 600_000,
      'the launch-shaped set has the host code sizes and compression of the measured cache: ' + str({k: v for k, v in sets['launch'].items() if k != 'files'}))
check(sets['hand']['largestHostCode'] > LIMIT and sets['above-limit']['largestHostCode'] > LIMIT and sets['window']['largestHostCode'] < LIMIT, 'host codes on both sides of the limit')

EQUAL = ('exception', 'programsCreated', 'sourceBytes', 'createOrdered', 'createSorted', 'callbacks', 'callbackKinds', 'lastCallback', 'logSorted', 'logLines',
         'graphicsPrograms', 'computePrograms', 'tables', 'distinctCodeArrays', 'files', 'filesUnchanged', 'journalCodeTableLines')
ORDERED = ('callbacksOrdered', 'logOrdered', 'errorCount')
SETTINGS = ['default', '0', '1', '2', '3']
names = [s['name'] for s in control['scenarios']]
check(names == [s['name'] for s in candidate['scenarios']] and len(set(names)) == len(names) == 41 + 3 * (real_cache is not None), 'the scenarios: ' + str(len(names)))
check(all(list(s['settings']) == ['control'] for s in control['scenarios']) and all(list(s['settings']) == SETTINGS for s in candidate['scenarios']),
      'the control once; the candidate with its own thread count and with 0, 1, 2 and 3 threads')
summary, by_name = [], {}
for sc, sk in zip(control['scenarios'], candidate['scenarios']):
    name, c = sc['name'], sc['settings']['control']
    by_name[name] = (c, sk['settings'])
    programs_in_set = {'hand-rebuilt': 120, 'launch-rebuilt': 1000, 'real': 1 << 20, 'absent': 0}.get(sc['set']) or sets.get(sc['set'], {}).get('programs', 0)
    for setting in SETTINGS:
        k = sk['settings'][setting]
        # (a) The same result, whatever the number of threads.
        for key in EQUAL + (() if sc['unordered'] else ORDERED):
            check(c[key] == k[key], f'{name}: control and candidate ({setting}) differ in {key}: {str(c[key])[:160]} / {str(k[key])[:160]}')
        check(k['loads'] == c['loads'] == k['loadsWithTheSameResult'] == c['loadsWithTheSameResult'] and c['loads'] in (1, 3, 40),
              f'{name} ({setting}): each of the {k["loads"]} loads gives the same result: ' + str(k['loadsWithTheSameResult']))
        threads = default_threads if setting == 'default' else int(setting)
        line = read_line(k['journalRead'])
        # A load whose shared table is accepted reaches its programs (none, perhaps): it has a read-ahead and a journal line.
        reading = name not in ('no cache file', 'wrong magic in the shared table', 'another format version')
        # (b) The read-ahead threads: as many as set once a program is asked of a cache of 16 or more, each in the scheduler class, none left at the return.
        started = threads if reading and programs_in_set >= 16 and name != 'cancelled before the load' else 0
        check(c['raisedThreads'] == 0 and k['raisedThreads'] == started and k['raisedThreadsAliveAtReturn'] == 0,
              f'{name} ({setting}): {started} read-ahead threads, all ended when LoadShaders returns: ' + str((k['raisedThreads'], k['raisedThreadsAliveAtReturn'])))
        check(k['raisedThreadNames'] == ','.join(f'GPU.ShaderCacheReadThread.{i}' for i in range(started)) and
              k['raisedClasses'] == (str(CLASS) if started else ''), f'{name} ({setting}): each thread asks the user-interactive class once: ' + k['raisedThreadNames'])
        # (e) One journal line per load that reached its programs, with the load's counts.
        check(c['journalRead'] is None and c['journalReadLines'] == 0 and k['journalReadLines'] == (1 if reading else 0) and (line is not None) == reading,
              f'{name} ({setting}): the journal line: ' + str(k['journalRead']))
        if line is not None:
            check(line['window'] == WINDOW and line['limitKiB'] == LIMIT // 1024 and line['most'] <= WINDOW and line['threads'] == started and
                  line['planned'] == threads and line['taken'] <= line['entries'] and line['taken'] <= line['gpuRead'] + line['threadRead'] and
                  line['gpuAhead'] <= line['gpuRead'] and (started > 0 or line['threadRead'] == line['gpuAhead'] == line['most'] == 0),
                  f'{name} ({setting}): the journal counts hold together: ' + k['journalRead'])
            if not sc['unordered'] and c['exception'] is None and 'cancelled' not in name:
                check(line['taken'] == c['programsCreated'], f'{name} ({setting}): programs taken are the programs created: ' + k['journalRead'])
            check(sc['unordered'] or abs(line['hostMiB'] - c['sourceBytes'] / 1048576) <= 1.01,
                  f'{name} ({setting}): host code read: ' + str((line['hostMiB'], c['sourceBytes'])))
    summary.append(dict(name=name, set=sc['set'], programsCreated=c['programsCreated'], exception=c['exception'], errorCount=c['errorCount'],
                        callbacks=c['callbackKinds'], log=c['log'][1:3], controlMs=c['milliseconds'],
                        candidateMs={setting: sk['settings'][setting]['milliseconds'] for setting in SETTINGS}))


def facts(name):
    return by_name[name][0]


def journal(name, setting):
    return read_line(by_name[name][1][setting]['journalRead'])


def logged(name, text):
    return any(text in line for line in facts(name)['log'])


# What each scenario is, read on the control (the candidate equals it).
for name, programs_expected, codes in (('hand-written cache', 120, sets['hand']['guestCodes']), ('cache rebuilt by the engine', 120, sets['hand']['guestCodes']),
                                       ('launch-shaped cache', 1000, sets['launch']['guestCodes']), ('launch-shaped cache rebuilt by the engine', 1000, sets['launch']['guestCodes']),
                                       ('15 programs', 15, sets['few15']['guestCodes']), ('16 programs', 16, sets['few16']['guestCodes'])):
    f = facts(name)
    check(f['exception'] is None and f['programsCreated'] == f['graphicsPrograms'] + f['computePrograms'] == programs_expected and f['errorCount'] == 0 and
          f['lastCallback'] == f'Loaded {programs_expected} {programs_expected}' and f['filesUnchanged'] and f['distinctCodeArrays'] == codes and
          f['logLines'] == 2 and f['computePrograms'] > 0, name + ': every program loaded from its host code, each guest code in one array, files untouched')
    for setting in SETTINGS:
        check(journal(name, setting)['end'] == 'all' and journal(name, setting)['ahead'] == 'never failed', name + ': the journal says so')
for name in ('hand-written cache', 'launch-shaped cache'):
    rebuilt = facts(name.replace(' cache', ' cache rebuilt by the engine') if name.startswith('launch') else 'cache rebuilt by the engine')
    check(facts(name)['tables'] == rebuilt['tables'] and facts(name)['createOrdered'] == rebuilt['createOrdered'],
          name + ': the cache the engine rebuilds from it loads to the same programs (the files written here are what the engine writes)')
for name, expected in (('truncated table of contents, rebuilt', 120), ('launch-shaped cache, truncated table of contents, rebuilt', 1000)):
    f = facts(name)
    check(f['exception'] is None and f['programsCreated'] == expected, name + ': every program is loaded before the truncated entry')
    check(f'Packaging={expected + 1}' in f['callbackKinds'] and logged(name, 'Error loading the shader cache. The cache file is corrupted.') and
          logged(name, f'Host code read back for the rebuild: {expected} programs, 0 unavailable') and logged(name, f'Rebuilt {expected} shaders successfully.'),
          name + ': then the files are rebuilt with every program and its host code')
    for setting in SETTINGS:
        check(journal(name, setting)['end'] == 'stopped by an error' and journal(name, setting)['entries'] == expected + 1, name + ': the journal counts the truncated entry')
AT = ('shared entry past the data file at program 70', 'shared data truncated inside program 70', 'shared data altered inside program 70',
      'shared data altered at the start of program 70', 'unknown compression of program 70', 'invalid stage mask at program 70',
      'guest index past the guest table at program 70', 'negative guest index at program 70', 'guest table truncated before the code of program 70',
      'guest code past the guest data at program 70', 'guest data altered at the start of the code of program 70',
      'host entry past the host data at program 70', 'host data altered inside program 70', 'host data truncated inside program 70',
      'host information altered at program 70')
errors = set()
for name in AT:
    f = facts(name)
    check(f['programsCreated'] == 70 and f['graphicsPrograms'] + f['computePrograms'] in (70, 67), name + ': the 70 programs before it are created: ' + str(f['programsCreated']))
    if f['exception'] is None:
        check('Packaging=71' in f['callbackKinds'] and logged(name, 'Error loading the shader cache.') and logged(name, 'Rebuilt 70 shaders successfully.') and
              f['graphicsPrograms'] + f['computePrograms'] == 70, name + ': the load stops there and rebuilds the files with the 70 programs')
        errors.add(f['log'][1])
    else:
        check(f['lastCallback'].startswith('Loading ') and f['logLines'] == 1, name + ': the exception leaves LoadShaders as it did: ' + f['exception'])
        errors.add(f['exception'])
    for setting in SETTINGS:
        check(journal(name, setting)['end'] == 'stopped by an error' and journal(name, setting)['taken'] == 70, name + ': the journal says where')
check(len(errors) >= 4 and sum(1 for name in AT if facts(name)['exception'] is not None) >= 3 and
      any('IndexOutOfRangeException' in (facts(name)['exception'] or '') for name in AT), 'several kinds of errors, thrown and handled: ' + str(sorted(errors)))
f = facts('guest data altered in the code of program 70')
check(f['exception'] is None and f['programsCreated'] == 120 and f['tables'] != facts('hand-written cache')['tables'] and
      f['createOrdered'] == facts('hand-written cache')['createOrdered'], 'guest data altered without a decoding error: the altered code is what both load')
for name in ('host table header truncated', 'host data file empty', 'wrong magic in the shared table', 'another format version'):
    f = facts(name)
    check(f['exception'] is None and f['programsCreated'] == 0 and logged(name, 'Shader cache deleted due to corruption.') and
          all(digest.startswith('0:') for digest in f['files'].values()) and len(f['files']) == 6, name + ': no program, the cache files are emptied')
for name, created, translated in (('host table ends at program 25', 25, 15), ('no host file', 0, 40), ('host files older than the shared cache', 0, 40),
                                  ('another code generation', 0, 40), ('malformed host code at program 20', 39, 1), ('host program 20 fails to link', 40, 1)):
    f = facts(name)
    check(f['exception'] is None and f['programsCreated'] == created and 'Loading=40' in f['callbackKinds'] and
          translated - 2 <= f['errorCount'] <= translated and f['logLines'] == translated + 2, name + f': {created} programs from the host cache, {translated} sent to the translator')
    for setting in SETTINGS:
        k = by_name[name][1][setting]
        check(translated - 2 <= k['errorCount'] <= translated and journal(name, setting)['taken'] == 40, name + ': the same with the candidate (' + setting + ')')
for name in ('no cache file', 'no program', 'cancelled before the load'):
    f = facts(name)
    check(f['exception'] is None and f['programsCreated'] == 0 and f['callbackKinds'] == 'Loaded=1,Start=1' and f['filesUnchanged'], name + ': nothing is loaded')
# (b) Cancellation.
for name, at in (('cancelled at program 50', 50), ('launch-shaped cache cancelled at program 300', 300)) + ((('real cache cancelled at program 500', 500),) if real_cache else ()):
    f = facts(name)
    check(f['exception'] is None and f['programsCreated'] == at + 1 and f['filesUnchanged'] and f['lastCallback'].startswith('Loaded '),
          name + ': the program being created is the last one')
    for setting in SETTINGS:
        k = by_name[name][1][setting]
        check(0 <= k['returnAfterCancelMilliseconds'] <= 250 and journal(name, setting)['end'] == 'cancelled' and journal(name, setting)['taken'] == at + 1,
              f'{name} ({setting}): LoadShaders returns promptly: ' + str(k['returnAfterCancelMilliseconds']))
# (c) Memory.
f, MIB = facts('64 programs of 1 MiB, GPU thread held at program 24'), 1048576
for setting in SETTINGS:
    k = by_name['64 programs of 1 MiB, GPU thread held at program 24'][1][setting]
    more, threads = (k['memoryAtProbe'] - f['memoryAtProbe']) / MIB, default_threads if setting == 'default' else int(setting)
    check((WINDOW - 2.5 <= more <= WINDOW + 0.5) if threads else abs(more) <= 1, f'window ({setting}): reachable memory against the control: {more:.1f} MiB')
    check(journal('64 programs of 1 MiB, GPU thread held at program 24', setting)['most'] == (WINDOW if threads else 0), f'window ({setting}): programs outstanding')
f = facts('24 programs above the limit, GPU thread held at program 10')
for setting in SETTINGS:
    k, line = by_name['24 programs above the limit, GPU thread held at program 10'][1][setting], journal('24 programs above the limit, GPU thread held at program 10', setting)
    more, threads = (k['memoryAtProbe'] - f['memoryAtProbe']) / MIB, default_threads if setting == 'default' else int(setting)
    check(abs(more) <= 1 and line['threadRead'] == line['gpuAhead'] == 0 and line['gpuRead'] == 24 and (line['left'] >= 8 if threads else line['left'] == 0),
          f'above the limit ({setting}): no host code is read ahead, the GPU thread reads the 24 programs: {more:.1f} MiB, ' + by_name[
              '24 programs above the limit, GPU thread held at program 10'][1][setting]['journalRead'])
for name in ('hand-written cache', 'launch-shaped cache'):
    for setting in ('1', '2', '3'):
        line = journal(name, setting)
        check(line['threadRead'] > 0 and line['threadRead'] + line['gpuRead'] == line['entries'], f'{name} ({setting}): the threads read programs: ' + str(line['threadRead']))
if real_cache is not None:
    f = facts('real cache')
    check(f['exception'] is None and f['errorCount'] == 0 and f['programsCreated'] == f['graphicsPrograms'] + f['computePrograms'] > 1000 and f['filesUnchanged'],
          'real cache: every program loaded from its host code')
    f = facts('real cache, truncated table of contents, rebuilt')
    check(f['exception'] is None and logged('real cache, truncated table of contents, rebuilt', f'Rebuilt {f["programsCreated"]} shaders successfully.'), 'real cache: rebuilt')

# (d) Cost.
for label, data in perf.items():
    best, lines = data['best'], data['journal']
    check(all(best[setting]['programsCreated'] == best['control']['programsCreated'] and best[setting]['sourceBytes'] == best['control']['sourceBytes']
              for setting in ('default', '2', '0')), label + ': the measured loads create the same programs')
    check(best['default']['best'] <= DEFAULT_FACTOR * best['control']['best'], label + f': faster with this host\'s {default_threads} read-ahead thread(s): ' +
          str((best['control']['best'], best['default']['best'])))
    check(best['2']['best'] <= TWO_FACTOR * best['control']['best'], label + ': faster with two read-ahead threads: ' + str((best['control']['best'], best['2']['best'])))
    check(best['0']['best'] <= SERIAL_FACTOR * best['control']['best'] + SERIAL_MARGIN, label + ': without a thread the GPU thread reads as the control: ' +
          str((best['control']['best'], best['0']['best'])))
    check(lines['2']['threadRead'] >= 0.4 * lines['2']['entries'] and lines['default']['threadRead'] >= 0.25 * lines['default']['entries'] and
          lines['0']['threadRead'] == 0 and lines['0']['gpuRead'] == lines['0']['entries'], label + ': who reads: ' + str({k: (v['threadRead'], v['gpuRead']) for k, v in lines.items() if v}))

# Static: each file is the control's but for the adapter's hunks; the read and the creation are the control's statements.
ck, kk = texts['control'], texts['candidate']
for name in BASELINE:
    reversed_text = kk[name]
    for file, old, new in PAIRS:
        if file == name:
            check(ck[name].count(old) == 1 and kk[name].count(new) == 1, 'hunk applies once and is unique afterwards: ' + name + ': ' + new[:50].strip())
            reversed_text = reversed_text.replace(new, old)
    check(reversed_text == ck[name], name + ' is the control but for the adapter\'s hunks')
check(sha(FINAL_SOURCE / LOADER) == sha(SOURCE / LOADER), 'the loader is not changed')
storage, guest = kk[STORAGE], kk[GUEST]
for signature in ('public byte[][] ReadHostCodesForRebuild(', 'public DiskCacheOutputStreams GetOutputStreams(', 'public void AddShader(', 'public void ClearGuestCache()',
                  'public void ClearSharedCache()', 'public void ClearHostCache(', 'private void WriteHostCode(', 'private static void CreateToc(',
                  'private static ShaderProgramInfo ReadShaderProgramInfo(', 'private static void WriteShaderProgramInfo(', 'public int GetProgramCount()', 'public bool CacheExists()'):
    check(member(ck[STORAGE], signature) == member(storage, signature), 'DiskCacheHostStorage unchanged: ' + signature)
for signature in ('public int AddShader(', 'private void LoadOrCreateToc(', 'private bool LoadTocEntries(', 'private int WriteNewEntry(', 'public void ClearMemoryCache()',
                  'public void ClearCache()', 'private void AddTocMemoryEntry(', 'public Stream OpenTocFileStream()', 'public Stream OpenDataFileStream()'):
    check(member(ck[GUEST], signature) == member(guest, signature), 'DiskCacheGuestStorage unchanged: ' + signature)


def statements(text, replacements=(), dropped=()):
    lines = []
    for line in text.splitlines():
        for old, new in replacements:
            line = line.replace(old, new)
        if line.strip() and line.strip() not in dropped and not line.strip().startswith('//'):
            lines.append(line.strip())
    return lines


old_load, new_load = member(ck[STORAGE], 'public void LoadShaders(GpuContext context, ParallelDiskCacheLoader loader)'), member(
    storage, 'public void LoadShaders(GpuContext context, ParallelDiskCacheLoader loader)')
reader = member(storage, 'public ProgramRead Read(int programIndex, uint maximumHostCodeSize)')
check(statements(between(old_load, 'ulong dataOffset = 0;', 'dataReader.EndCompression();')) ==
      statements(between(reader, 'ulong dataOffset = 0;', 'dataReader.EndCompression();'),
                 (('_dataFileStream', 'dataFileStream'), ('_guestTocFileStream', 'guestTocFileStream'), ('_guestDataFileStream', 'guestDataFileStream'),
                  ('_storage._guestStorage', '_guestStorage')), ('DataEntry entry = new();',)),
      'a program is read by the statements of the control\'s loop, in their order')
check(reader.index('_tocFileStream.Seek(_load.FirstEntry + (long)programIndex * sizeof(ulong), SeekOrigin.Begin);') < reader.index('ulong dataOffset = 0;') and
      'BinarySerializer tocReader = new(_tocFileStream);' in reader and 'BinarySerializer dataReader = new(_dataFileStream);' in reader,
      'each read starts at its entry of the table, with its own serializers')
host = between(reader, 'if (_load.LoadHostCache && programIndex < _load.FirstProgramWithoutHostCode)', 'return new ProgramRead')
check(re.sub(r'\s+', ' ', between(old_load, '= ReadHostCode(', 'header.Timestamp);')).replace('ref hostTocFileStream', 'ref _hostTocFileStream').replace(
          'ref hostDataFileStream', 'ref _hostDataFileStream').replace('context,', '_load.Context,').replace('header.Timestamp);', '_load.Timestamp,').replace(
          '= ReadHostCode(', '= _storage.ReadHostCode(') in
      re.sub(r'\s+', ' ', host) and 'maximumHostCodeSize);' in host and host.index('finally') < host.index('CloseHostStreams();') and
      'if (opens && !hasCode)' in host and '_load.NoteProgramWithoutHostCode(programIndex);' in host and 'return ProgramRead.LeftToGpuThread;' in host,
      'the host code is asked as the loop asked it; a call that opened the host files without finding a code closes them again')
create_old = between(old_load, 'bool vulkan = context.Capabilities.Api == TargetApi.Vulkan;', 'programIndex++;')
check(create_old in new_load and create_old.count('loader.QueueHostProgram(program, hostCode, programIndex, isCompute);') == 1 and
      create_old.count('loader.QueueGuestProgram(guestShaders, specState, programIndex, isCompute);') == 2 and 'loadHostCache = false;' in create_old,
      'what creates and queues a program is the control\'s text')
check(new_load.count('readAhead.Take(programIndex)') == 1 and new_load.index('while (programIndex < entries && loader.Active)') <
      new_load.index('ProgramRead read = readAhead.Take(programIndex);') < new_load.index('(byte[] hostCode, CachedShaderStage[] shaders) = (read.HostCode, read.Shaders);') <
      new_load.index(create_old) and 'if ((programIndex & 7) == 0)' in new_load and 'loader.CheckCompilation();' in new_load,
      'the loop takes the programs one by one, in order, while the loader is active, and checks compilations every eight')
check(re.search(r'int entries = \(int\)\(\(tocFileStream\.Length - tocFileStream\.Position \+ sizeof\(ulong\) - 1\) / sizeof\(ulong\)\);', new_load) is not None and
      'while (tocFileStream.Position < tocFileStream.Length && loader.Active)' in old_load, 'one pass per table entry, a truncated last one included')
final = new_load[new_load.rindex('finally'):]
check(final.index('readAhead?.End(completed, !loader.Active, createTicks, checkTicks);') < final.index('_guestStorage.ClearMemoryCache();') and
      'hostTocFileStream' not in new_load, 'the read-ahead ends (threads joined, streams closed) before the guest codes are dropped')
ahead = between(storage, 'private sealed class ProgramReadAhead', '// RewindBox (adapt_shader_cache_parallel_read): end')
end = member(ahead, 'public void End(bool completed, bool cancelled, long createTicks, long checkTicks)')
check(end.index('_closed = true;') < end.index('Monitor.PulseAll(_sync);') < end.index('_threads[index].Join();') < end.index('_reader.Dispose();') <
      end.index('EmbeddedLaunchDiagnostics.Record("shaderCache", "read"') and storage.count('EmbeddedLaunchDiagnostics.Record(') == 1,
      'End closes the reading, joins every started thread, closes the GPU thread\'s host streams, then writes the one journal line')
take = member(ahead, 'public ProgramRead Take(int programIndex)')
check(take.index('read = _ring[programIndex % Window];') < take.index('else if (_next == programIndex)') <
      take.index('else if (!_closed && _next < _entries && _next < programIndex + Window)') < take.index('Monitor.Wait(_sync);') and
      take.index('read == null || read == ProgramRead.Failed || read == ProgramRead.LeftToGpuThread') < take.index('read = _reader.Read(programIndex, uint.MaxValue);'),
      'Take: a program read ahead, else its own read; a failed or declined read ahead is read again in order, without a size limit')
thread = member(ahead, 'private void ReadAheadThread()')
check(thread.index('Ryujinx.Common.HostThreadClass.RaiseCurrentThread();') < thread.index('new ProgramReader(') and
      'while (!_closed && _next < _entries && _next >= _consumed + Window)' in thread and thread.count('writable: false') == 2 and 'writable: true' not in ahead and
      'ownsStreams: true' in thread and 'reader?.Dispose();' in thread, 'a thread reads with its own read-only streams, inside the window, and closes them')
check('return reader.Read(programIndex, MaximumHostCodeSize);' in member(ahead, 'private static ProgramRead TryRead(') and
      'IsBackground = true' in member(ahead, 'private void StartThreads()') and 'if (_entries < MinimumPrograms)' in member(ahead, 'private void StartThreads()'),
      'a read ahead has the size limit; no thread below 16 programs')
code_old, code_new = member(ck[STORAGE], 'private (byte[], CachedShaderStage[]) ReadHostCode('), member(storage, 'private (byte[], CachedShaderStage[]) ReadHostCode(')
for file, old, new in PAIRS[5:7]:
    code_new = code_new.replace(new, old)
check(code_new == code_old and 'uint maximumSize = uint.MaxValue)' in storage and
      storage.index('if (offsetAndSize.UncompressedSize > maximumSize)') < storage.index('byte[] hostCode = new byte[offsetAndSize.UncompressedSize];\n\n            BinarySerializer'),
      'ReadHostCode only gains the size above which it reads nothing, checked before the code is allocated')
load_old, load_new = member(ck[GUEST], 'public GuestCodeAndCbData LoadShader('), member(guest, 'public GuestCodeAndCbData LoadShader(')
check(statements(between(load_old, 'BinarySerializer tocReader = new(tocFileStream);', 'BinarySerializer.ReadCompressed(dataFileStream, guestCode);')) ==
      statements(between(load_new, 'BinarySerializer tocReader = new(tocFileStream);', 'BinarySerializer.ReadCompressed(dataFileStream, guestCode);')) and
      load_new.index('lock (_cacheLock)') < load_new.index('Array.Resize(ref _cache, Math.Max(index + 1, GetShadersCountFromLength(tocFileStream.Length)));') <
      load_new.index('lock (_readLocks[index % _readLocks.Length])') < load_new.index('BinarySerializer tocReader') and load_new.count('lock (_cacheLock)') == 3 and
      '_cache = new (byte[], byte[])[' in load_old and '_cache = new' not in guest,
      'a guest code is read by the control\'s statements, once per index, under its index lock; the table keeps the codes read when it grows')

inputs = ['build-utils/melonx/adapt_shader_cache_parallel_read.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_adapter_control.py',
          'test/melonx_shader_cache_parallel_read_test.py', 'test/melonx_shader_cache_parallel_read/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
cost = {label: dict(rounds=data['rounds'], controlMs=data['best']['control']['best'], candidateMs={k: data['best'][k]['best'] for k in ('default', '2', '0')},
                    programs=data['best']['control']['programsCreated'], hostCodeBytes=data['best']['control']['sourceBytes'],
                    journal={k: data['best'][k]['journalRead'] for k in ('default', '2', '0')}) for label, data in perf.items()}
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               postimages={p: sha(FINAL_SOURCE / p) for p in BASELINE}, scenarios=summary, cost=cost, sets={k: {a: b for a, b in v.items() if a != 'files'} for k, v in sets.items()},
               hostProcessors=candidate['processors'], hostReadAheadThreads=default_threads, threadsForProcessors=candidate['threadsForProcessors'],
               window=WINDOW, maximumHostCodeSizeReadAhead=LIMIT, sdk=sdk, physicalDeviceTested=False, productionGpuProjectBuilt=True,
               realCacheUsed=real_cache is not None, requiredFactors=dict(default=DEFAULT_FACTOR, twoThreads=TWO_FACTOR, noThread=SERIAL_FACTOR),
               sourceBaseline=BASELINE, inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Host CoreCLR on Linux (x86-64, JIT), production Ryujinx.Graphics.Gpu with a renderer double: the time of the read and of what the GPU '
                          'thread does around it, not of the renderer or of a device. The generated caches only have the sizes of a real one. The time a load '
                          'takes on an iPhone, and how the scheduler shares its cores with the guest, are known only from the "shaderCache read" line of a device run.')
out = ROOT / 'dist/melonx/shader-cache-parallel-read-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, realCacheUsed=real_cache is not None, cost=cost)))
