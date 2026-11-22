#!/usr/bin/env python3
"""Guest codes of the disk shader cache registered once the load has them all (adapt_shader_code_table_load), before and after, real engine code.

Usage: melonx_shader_code_table_load_test.py <final preparation containing the adapter>
       melonx_shader_code_table_load_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control), candidate is the adapter applied to it,
which must be the final preparation byte for byte. For each, the real HashTable/*.cs, ShaderCacheHashTable.cs,
ComputeShaderCacheHashTable.cs and ShaderCodeAccessor.cs are compiled whole, with the loader's real registration lines
(the successful branch of ParallelDiskCacheLoader.ProcessCompiledProgram and, in the candidate, the real
RegisterLoadedProgram, RegisterLoadedPrograms and their fields) and small doubles (test/melonx_shader_code_table_load).

Each data set is a disk cache load replayed in cache order: six adversarial sets (codes that are truncations or
extensions of others, equal sizes, the same content in two arrays, sizes not multiple of eight, every stage kind;
programs in increasing, decreasing and random size order; with heavy sharing and with none), a synthetic set with the
shape of the real cache measured on the host, a synthetic set of 12,600 programs and, when MELONX_SHADER_CACHE_DIR
names one, a real cache (guest.toc, guest.data, shared.toc, shared.data; read only, never copied).

(a) Equivalence. After the load the complete state of the tables is the same in both (every size table and entry:
stored hash, partial or full, item, content; identifier counters; identifier tables and their program lists in order;
GetPrograms order), and the real TryFind over a guest memory double gives the same answer for every registered code
(followed by other bytes, ending the mapped memory, cut short, one bit changed, its first bytes up to another
registered size, in another stage's table), for codes longer than any registered, for random content of registered
and unregistered sizes, and for every program. Identifiers are the same numbers, so nothing has to be argued about
their values. Programs then added as play adds them (lookup first, then Add with the cached arrays) give the same
answers and the same final state. The reservation alone (PartitionedHashTable.ReserveSizes on a table that already
holds data, sizes never added, a batch stopped half way) leaves the state the same adds give without it.
(b) Cost, counted by lines inserted into a second copy of the real files (the plain copy gives times, allocations and
states): the candidate hashes each registered code once, to the byte, and creates the same entries; on the
launch-shaped sets it must hash at least 20 times fewer bytes, compare at least 10 times fewer (a real cache: not
more), make no more table lookups, take at most a third of the control's time and allocate at most two thirds.
(c) Orders: on every adversarial set the candidate never hashes more than the control, makes at most a fifth more
lookups (arrays repeating another's content, or shadowed by a longer code, which a real cache does not hold) and takes
no more than the control's time plus a margin. (d) The production Ryujinx.Graphics.Gpu project builds from the candidate tree.
Static checks: the adapter changes its five files only, each by its hunks only; Add, TryFind and the play path are
the control's text (an add rebuilds a size table on "more buckets needed" instead of "another bucket count", the same
thing outside a batch). No device: the share of LoadShaders this removes on an iPhone is known only from the
"shaderCache codeTable" line of a device run. Writes dist/melonx/shader-code-table-load-checks.json.
"""
from pathlib import Path
import difflib, filecmp, hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_shader_code_table_load', _HOLD)
from adapt_shader_code_table_load import apply, BASELINE, FILE_PAIRS  # noqa: E402

GPU = 'src/Ryujinx.Graphics.Gpu/'
SHADER = GPU + 'Shader/'
PARTITION = SHADER + 'HashTable/PartitionHashTable.cs'
PARTITIONED = SHADER + 'HashTable/PartitionedHashTable.cs'
GRAPHICS = SHADER + 'ShaderCacheHashTable.cs'
COMPUTE = SHADER + 'ComputeShaderCacheHashTable.cs'
LOADER = SHADER + 'DiskCache/ParallelDiskCacheLoader.cs'
WHOLE = ['HashTable/HashState.cs', 'HashTable/IDataAccessor.cs', 'HashTable/PartitionHashTable.cs', 'HashTable/PartitionedHashTable.cs',
         'HashTable/SmartDataAccessor.cs', 'ShaderCacheHashTable.cs', 'ComputeShaderCacheHashTable.cs', 'ShaderCodeAccessor.cs']
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_shader_code_table_load'
REAL_CACHE = os.environ.get('MELONX_SHADER_CACHE_DIR', '')
REPETITIONS = 3
LAUNCH_SHAPED = ('synthetic, shape of the measured cache', 'synthetic, 12,600 programs', 'real cache')
# Measured on the host (see the adapter), real cache, synthetic of its shape, synthetic 12,600 programs: bytes hashed 58x,
# 69x and 148x fewer; bytes compared 4.3x, 47x and 130x fewer; time 9x, 11x and 9.5x shorter. The bounds keep a margin
# for another machine and a loaded one. Another real cache shares its codes otherwise: for a real cache the bytes
# compared must only not grow, and the factors apply from 1,000 programs.
HASHED_FACTOR, COMPARED_FACTOR, TIME_FACTOR = 20, 10, 3
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


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
    return text[left:text.index(end, left)]


def counted(directory):
    """Counters in a copy of the real files: one statement at each place, the same in the control and the candidate."""
    def insert(name, anchor, addition, count=1, replace=None):
        path = directory / name
        text = path.read_text(encoding='utf-8-sig')
        check(text.count(anchor) == count, 'counter anchor in ' + name + ': ' + anchor[:60])
        path.write_text(text.replace(anchor, replace if replace is not None else anchor + addition), encoding='utf-8')

    insert('HashState.cs', '            ReadOnlySpan<ulong> dataAsUlong = MemoryMarshal.Cast<byte, ulong>(data[_start..]);\n',
           '            global::TableCounters.HashedBytes += dataAsUlong.Length * 8L;\n')
    insert('PartitionHashTable.cs', '        private bool TryFindItem(uint dataHash, ReadOnlySpan<byte> data, out T item)\n        {\n',
           '            global::TableCounters.Lookups++;\n')
    insert('PartitionHashTable.cs', '.GetData().SequenceEqual(data)', '', 2, '.GetData().SequenceEqual(global::TableCounters.Compared(data))')
    insert('PartitionHashTable.cs', '        private void AddToBucket(uint dataHash, ref Entry entry)\n        {\n',
           '            global::TableCounters.Entries++;\n')
    insert('PartitionHashTable.cs', '        private void Rebuild(int newPow2Count)\n        {\n',
           '            global::TableCounters.Rebuilds++;\n            global::TableCounters.MovedEntries += _count - 1;\n')


check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the adapter\'s preparation: ' + name)
check(sorted(BASELINE) == sorted(FILE_PAIRS) == sorted([PARTITION, PARTITIONED, GRAPHICS, COMPUTE, LOADER]), 'the adapter declares its five files')
real_cache = Path(REAL_CACHE).resolve() if REAL_CACHE else None
if real_cache is not None:
    check(all((real_cache / name).is_file() for name in ('guest.toc', 'guest.data', 'shared.toc', 'shared.data')), 'MELONX_SHADER_CACHE_DIR holds a cache')

reports, texts = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredPGO='0')
with tempfile.TemporaryDirectory(prefix='melonx-shader-code-table-') as temporary:
    work = Path(temporary).resolve() / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)
    changed = apply(work)
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
    later = files_edited_later('adapt_shader_code_table_load')
    for name in BASELINE:
        if name not in later:
            check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

    # Every source file of the engine but the five is the control's, byte for byte.
    different, compared = [], 0
    for path in sorted((SOURCE / 'src').rglob('*')):
        relative = path.relative_to(SOURCE)
        if path.is_file() and not path.is_symlink() and not {'bin', 'obj'} & set(relative.parts):
            compared += 1
            if not (work / relative).is_file() or not filecmp.cmp(path, work / relative, shallow=False):
                different.append(relative.as_posix())
    check(compared > 3000 and sorted(different) == sorted(BASELINE), 'only the five files differ from the control: ' + str(different[:8]))
    check(sum(1 for path in (work / 'src').rglob('*.cs') if not {'bin', 'obj'} & set(path.relative_to(work).parts)) ==
          sum(1 for path in (SOURCE / 'src').rglob('*.cs') if not {'bin', 'obj'} & set(path.relative_to(SOURCE).parts)), 'no source file added')

    result = subprocess.run([DOTNET, 'build', str(work / (GPU + 'Ryujinx.Graphics.Gpu.csproj')), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                            capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'candidate production assembly builds: Ryujinx.Graphics.Gpu')

    for variant, tree in (('control', SOURCE), ('candidate', work)):
        loader = (tree / LOADER).read_text(encoding='utf-8-sig')
        texts[variant] = {name: (tree / name).read_text(encoding='utf-8-sig') for name in BASELINE}
        process = member(loader, 'private void ProcessCompiledProgram(')
        block = between(process, '                // Compilation successful, add to memory cache.\n', '\n                if (!entry.IsBinary)')
        fields, methods, end = '', '', ''
        if variant == 'candidate':
            fields = '\n'.join(line for line in loader.splitlines() if line.strip() in (
                'private readonly List<CachedShaderProgram> _loadedGraphics = new();', 'private readonly List<CachedShaderProgram> _loadedCompute = new();',
                'private bool _loadedRegistered;'))
            check(fields.count('\n') == 2, 'the loader\'s three fields')
            methods = member(loader, 'private void RegisterLoadedProgram(') + '\n\n' + member(loader, 'private void RegisterLoadedPrograms()')
            end = '            RegisterLoadedPrograms();'
            check(end + ' // RewindBox (adapt_shader_code_table_load)' in member(loader, 'private void LoadShadersThenRegister()'), 'the load ends with the registration')
        check(('RegisterLoadedPrograms' in loader) == (variant == 'candidate'), variant + ': grouped registration only in the candidate')
        template = (FIXTURE / 'Double.cs').read_text()
        for mark, code in (('/* LOADER_FIELDS */', fields), ('/* REGISTER_BLOCK */', block), ('/* END_LOAD */', end), ('/* LOADER_METHODS */', methods)):
            check(template.count(mark) == 1, 'fixture mark ' + mark)
            template = template.replace(mark, code)

        for build in ('plain', 'counted'):
            fixture = Path(temporary).resolve() / ('fixture-' + variant + '-' + build)
            fixture.mkdir()
            (fixture / 'Double.cs').write_text(template)
            shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
            for name in WHOLE:
                shutil.copyfile(tree / (SHADER + name), fixture / Path(name).name)
            if build == 'counted':
                counted(fixture)
            (fixture / 'Fixture.csproj').write_text(
                '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
                '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0649;CS0414;CS0169;CS8321;CS1998</NoWarn>'
                '<TieredCompilation>false</TieredCompilation><ConcurrentGarbageCollection>false</ConcurrentGarbageCollection>'
                '<InvariantGlobalization>true</InvariantGlobalization></PropertyGroup></Project>\n')
            command = [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant, str(REPETITIONS if build == 'plain' else 1)]
            if real_cache is not None:
                command.append(str(real_cache))
            for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'], command):
                result = subprocess.run(command, capture_output=True, text=True, timeout=1800, env=environment, cwd=fixture)
                if result.returncode:
                    print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                    result.check_returncode()
            reports[variant + '-' + build] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
            print(json.dumps({variant + '-' + build: [dict(name=s['name'], loadMs=s['loadMs'], lookups=s['lookups'], hashedBytes=s['hashedBytes'],
                                                         comparedBytes=s['comparedBytes']) for s in reports[variant + '-' + build]['sets']]}), flush=True)

c, k = reports['control-plain'], reports['candidate-plain']
cc, kc = reports['control-counted'], reports['candidate-counted']
names = [s['name'] for s in c['sets']]
check(len(names) == 8 + (real_cache is not None) and len(set(names)) == len(names), 'the data sets: ' + str(names))
check(all([s['name'] for s in r['sets']] == names for r in (k, cc, kc)), 'the same data sets in every run')
check(sum(1 for name in names if name.startswith('adversarial, ')) == 6 and
      all(sum(1 for name in names if word in name) == count for word, count in (
          ('increasing', 2), ('decreasing', 2), ('random', 2), ('heavy sharing', 3), ('no sharing', 3))), 'three orders, with and without sharing')
EQUAL = ('state', 'answers', 'playAnswers', 'playState', 'programs', 'computePrograms', 'stageCodes', 'codes', 'codeBytes', 'hashedOnce',
         'distinctSizes', 'sizeTables', 'fullEntries', 'partialEntries', 'identifiers', 'idTables', 'probes', 'hits', 'codesReturned',
         'playPrograms', 'playAdded', 'playProbes', 'playHits', 'playFullEntries', 'playSizeTables')
summary = []
for index, name in enumerate(names):
    sc, sk, scc, skc = (r['sets'][index] for r in (c, k, cc, kc))
    # (a) Equivalence: the same table state and the same answers, after the load and after play.
    for key in EQUAL:
        check(sc[key] == sk[key], name + ': control and candidate differ in ' + key + ': ' + str((sc[key], sk[key])))
        check(sc[key] == scc[key] and sk[key] == skc[key], name + ': the counted copy behaves as the plain one: ' + key)
    check(sc['probes'] >= 600 and 0 < sc['hits'] < sc['probes'] and sc['codesReturned'] > sc['hits'], name + ': lookups that find and lookups that miss')
    check(sc['playAdded'] >= 40 and sc['playHits'] > sc['hits'] and sc['playFullEntries'] > sc['fullEntries'] and
          sc['playSizeTables'] > sc['sizeTables'], name + ': play adds programs, codes and sizes after the load')
    check(sc['partialEntries'] > sc['fullEntries'] > 0 and sc['identifiers'] > 0 and sc['idTables'] > 0, name + ': tables hold full and partial entries')
    check(sc['kind'] == sk['kind'] == ('real' if name == 'real cache' else 'synthetic'), name + ': kind of data')
    if name.startswith('adversarial, '):
        check(sc['identifiers'] < sc['fullEntries'] + sc['codes'] and sc['stageCodes'] > sc['programs'], name + ': several stages per program')
        check(('no sharing' in name) == (sc['codes'] >= sc['stageCodes'] * 0.8), name + ': sharing as named: ' + str((sc['codes'], sc['stageCodes'])))
    # The journal: one line per load in the candidate, with the load's counts; none in the control.
    lines = [line for line in sk['journal'] if line.startswith('shaderCache codeTable ')]
    check(len(lines) == len(sk['journal']) == REPETITIONS * (name != 'synthetic, 12,600 programs') + (name == 'synthetic, 12,600 programs') and
          not sc['journal'], name + ': one journal line per load, candidate only')
    numbers = re.fullmatch(r'shaderCache codeTable guest codes registered after the load in (\d+) ms: (\d+) graphics programs, (\d+) stage codes, '
                           r'(\d+) distinct \((\d+) KiB\); (\d+) compute programs, (\d+) distinct codes \((\d+) KiB\); each code hashed once, sizes reserved first',
                           lines[-1])
    check(numbers is not None, name + ': journal line: ' + lines[-1])
    ms, graphics, stage_codes, distinct, kib, compute, compute_distinct, compute_kib = map(int, numbers.groups())
    check(graphics == sk['programs'] - sk['computePrograms'] and compute == sk['computePrograms'] and
          stage_codes == sk['stageCodes'] - sk['computePrograms'] and distinct + compute_distinct == sk['codes'] and
          abs(kib + compute_kib - sk['codeBytes'] // 1024) <= 1, name + ': the journal counts are the load\'s: ' + lines[-1])
    # (b), (c) Cost. Counters come from the counted copies; times from the plain ones (best of the repetitions).
    check(skc['hashedBytes'] == sk['hashedOnce'], name + ': the candidate hashes each registered code once: ' + str((skc['hashedBytes'], sk['hashedOnce'])))
    check(scc['hashedBytes'] >= skc['hashedBytes'], name + ': never more bytes hashed than the control')
    check(scc['entriesAdded'] == skc['entriesAdded'] == sc['fullEntries'] + sc['partialEntries'], name + ': the same entries are created')
    # An array whose content another array registered, or that a longer code shadows, is looked up in every smaller size
    # of the batch; the control looked it up in the sizes present when it arrived. The adversarial sets have both (a real
    # cache has neither: one array per content, no code starting another), hence their allowance.
    check(skc['lookups'] <= scc['lookups'] * (1.2 if name.startswith('adversarial, ') else 1), name + ': table lookups: ' + str((scc['lookups'], skc['lookups'])))
    check(sk['loadMsBest'] <= sc['loadMsBest'] * 1.5 + 60, name + ': never slower than the control beyond noise: ' + str((sc['loadMsBest'], sk['loadMsBest'])))
    if name in LAUNCH_SHAPED and sc['programs'] >= 1000:
        compared_factor = 1 if sc['kind'] == 'real' else COMPARED_FACTOR
        check(scc['hashedBytes'] >= HASHED_FACTOR * skc['hashedBytes'], name + ': bytes hashed drop: ' + str((scc['hashedBytes'], skc['hashedBytes'])))
        check(scc['comparedBytes'] >= compared_factor * skc['comparedBytes'], name + ': bytes compared drop: ' + str((scc['comparedBytes'], skc['comparedBytes'])))
        check(skc['lookups'] <= scc['lookups'], name + ': no more lookups: ' + str((scc['lookups'], skc['lookups'])))
        check(sc['loadMsBest'] >= TIME_FACTOR * sk['loadMsBest'], name + ': time drops: ' + str((sc['loadMsBest'], sk['loadMsBest'])))
        check(sk['allocatedBytes'] * 3 <= sc['allocatedBytes'] * 2, name + ': a third less allocated: ' + str((sc['allocatedBytes'], sk['allocatedBytes'])))
    summary.append(dict(name=name, programs=sc['programs'], codes=sc['codes'], codeBytes=sc['codeBytes'], distinctSizes=sc['distinctSizes'],
                        entries=sc['fullEntries'] + sc['partialEntries'], controlMs=sc['loadMsBest'], candidateMs=sk['loadMsBest'],
                        controlLookups=scc['lookups'], candidateLookups=skc['lookups'], controlHashedBytes=scc['hashedBytes'],
                        candidateHashedBytes=skc['hashedBytes'], controlComparedBytes=scc['comparedBytes'], candidateComparedBytes=skc['comparedBytes'],
                        controlAllocatedBytes=sc['allocatedBytes'], candidateAllocatedBytes=sk['allocatedBytes'], probes=sc['playProbes']))
launch = next(s for s in c['sets'] if s['name'] == 'synthetic, 12,600 programs')
check(launch['programs'] == 12600 and launch['codes'] > 5000 and launch['distinctSizes'] > 1500, 'the launch-sized set: ' + str((launch['codes'], launch['distinctSizes'])))
check(c['reservation'] == {'present': False}, 'control: no reservation')
reservation = k['reservation']
check(reservation['present'] and reservation['cases'] == reservation['equal'] == 6 and reservation['released'] == reservation['expectedReleased'] > 100,
      'candidate: a reservation, also one not used, leaves the state of the adds alone: ' + str(reservation))

# Static: each file is the control's but for the adapter's hunks, and the paths of play are the control's text.
ck, kk = texts['control'], texts['candidate']
for name, pairs in FILE_PAIRS.items():
    reversed_text = kk[name]
    for old, new in pairs:
        check(ck[name].count(old) == 1 and kk[name].count(new) == 1, 'hunk applies once and is unique afterwards: ' + name + ': ' + new[:50].strip())
        reversed_text = reversed_text.replace(new, old)
    check(reversed_text == ck[name], name + ' is the control but for the adapter\'s hunks')
    removed = [line for line in difflib.ndiff(ck[name].splitlines(), kk[name].splitlines()) if line.startswith('- ')]
    check(len(removed) == {LOADER: 8, PARTITION: 1}.get(name, 0), name + ': lines removed: ' + str(removed[:3]))
partition, partitioned, graphics, compute, loader = kk[PARTITION], kk[PARTITIONED], kk[GRAPHICS], kk[COMPUTE], kk[LOADER]
for signature in ('public T GetOrAdd(byte[] data, uint dataHash, T item)', 'public bool Add(byte[] data, uint dataHash, T item)',
                  'public bool AddPartial(byte[] ownerData, uint dataHash, int ownSize)', 'private static void AddToBucket(ref Bucket bucket, ref Entry entry)',
                  'public void FillPartials(PartitionHashTable<T> newTable, int newEntrySize)', 'private bool TryFindItem(uint dataHash, ReadOnlySpan<byte> data, out T item)',
                  'public SearchResult TryFindItem(scoped ref SmartDataAccessor dataAccessor', 'private void Rebuild(int newPow2Count)',
                  'private ref Bucket GetBucketForHash(uint hash)', 'private static int GetPow2Count(int count)', 'private struct Entry', 'private struct Bucket'):
    check(member(ck[PARTITION], signature) == member(partition, signature), 'PartitionHashTable unchanged: ' + signature)
grow = member(partition, 'private void AddToBucket(uint dataHash, ref Entry entry)')
check(re.sub(r'            // RewindBox \(adapt_shader_code_table_load\): the table only grows here\..*\n            // .*\n', '', grow).replace(
      'if (pow2Count > _buckets.Length)', 'if (pow2Count != _buckets.Length)') == member(ck[PARTITION], 'private void AddToBucket(uint dataHash, ref Entry entry)'),
      'an add rebuilds the table when its count asks for more buckets, as before, and never for fewer')
room, trim = member(partition, 'public void Reserve(int entries)'), member(partition, 'public void TrimExcess()')
check('GetPow2Count(_count + entries)' in room and 'if (pow2Count > _buckets.Length)' in room and 'Rebuild(pow2Count);' in room and
      'GetPow2Count(_count) != _buckets.Length' in trim and 'Rebuild(GetPow2Count(_count));' in trim, 'room is a rebuild to a larger table, the trim one to the table of the count')
check(member(ck[PARTITIONED], 'public bool TryFindItem(IDataAccessor') == member(partitioned, 'public bool TryFindItem(IDataAccessor') and
      member(ck[PARTITIONED], 'private static int BinarySearch(') == member(partitioned, 'private static int BinarySearch('), 'the table lookup is unchanged')
get_or_add = member(partitioned, 'public T GetOrAdd(byte[] data, T item)')
check(get_or_add.replace('                _reservedSizes?.Remove(data.Length); // RewindBox (adapt_shader_code_table_load): the size now has its data\n', '') ==
      member(ck[PARTITIONED], 'public T GetOrAdd(byte[] data, T item)'), 'GetOrAdd only notes that a reserved size received data')
reserve = member(partitioned, 'public void ReserveSizes(List<int> sizes)')
check('_sizeTable.Insert(index, sizeEntry);' in reserve and '_sizeTable[i].FillPartials(sizeEntry);' in reserve and '_reservedSizes.Add(size);' in reserve and
      'continue;' in reserve and reserve.index('_reservedSizes.Add(size);') < reserve.index('_sizeTable[i].Reserve(sizes.Count - longer);'),
      'a reserved size is inserted and filled as GetOrAdd inserts one; a present size is left alone; then each table gets its room')
release = member(partitioned, 'public int ReleaseReservedSizes()')
check('_reservedSizes = null;' in release and '_sizeTable.RemoveAll(entry => reserved.Contains(entry.Size))' in release and
      release.index('RemoveAll') < release.index('entry.TrimExcess();'), 'the release drops the sizes never added and trims every table')
for signature in ('public void Add(CachedShaderProgram program)', 'public bool TryFind(', 'private static bool TryGetId(', 'public int Add(byte[] code)',
                  'public readonly bool TryFind(', 'public IEnumerable<CachedShaderProgram> GetPrograms()', 'private struct IdTable'):
    check(member(ck[GRAPHICS], signature) == member(graphics, signature), 'ShaderCacheHashTable unchanged: ' + signature)
for signature in ('public void Add(CachedShaderProgram program)', 'public bool TryFind(', 'public IEnumerable<CachedShaderProgram> GetPrograms()'):
    check(member(ck[COMPUTE], signature) == member(compute, signature), 'ComputeShaderCacheHashTable unchanged: ' + signature)
check(re.search(r'private struct IdCache\s*\{\s*private PartitionedHashTable<int> _cache;\s*private int _id;\s*/// <summary>', graphics) is not None and
      'Dictionary' not in member(graphics, 'private struct IdCache').split('/// <summary>')[0], 'the identifier cache a lookup copies keeps its two fields')
for text, name in ((graphics, 'graphics'), (compute, 'compute')):
    batch = member(text, 'public void AddRange(List<CachedShaderProgram> programs, out int references, out int codes, out long codeBytes)')
    check('ReferenceEqualityComparer.Instance' in batch and 'ReserveSizes(' in batch and 'finally' in batch and
          batch.index('ReserveSizes(') < batch.index('finally') < batch.index('ReleaseReservedSizes()') and batch.index('try') < batch.index('ReserveSizes('),
          name + ': sizes reserved inside the try, released in its finally; arrays known by reference')
batch = member(graphics, 'public void AddRange(List<CachedShaderProgram> programs, out int references, out int codes, out long codeBytes)')
add = member(graphics, 'public void Add(CachedShaderProgram program)')
tail = between(add, '            if (!_shaderPrograms.TryGetValue(idTable, out ShaderSpecializationList specList))', '            specList.Add(program);')
check(tail.replace('\n            ', '\n                    ').strip() in batch and 'LoadCache(slot).Add(shader.Code);' in batch, 'the batch registers with Add and files the program as Add does')
slot = member(graphics, 'private static int LoadSlot(CachedShaderStage shader)')
for stage, cache, number in (('Vertex', '_vertexBCache', 1), ('TessellationControl', '_tessControlCache', 2), ('TessellationEvaluation', '_tessEvaluationCache', 3),
                             ('Geometry', '_geometryCache', 4), ('Fragment', '_fragmentCache', 5)):
    check(f'ShaderStage.{stage} => {number},' in slot and f'case ShaderStage.{stage}:\n                            idTable' in add and
          re.search(r'(case %d|default):\s*return ref %s;' % (number, cache), member(graphics, 'private ref IdCache LoadCache(int slot)')) is not None and
          f'= {cache}.Add(shader.Code);' in add, 'the batch uses the table Add uses: ' + stage)
check('if (shader.Info == null)\n            {\n                return 0;' in slot and 'case 0:\n                    return ref _vertexACache;' in graphics, 'vertex A as Add')
i = loader.index
load = member(loader, 'public void LoadShaders()')
check(re.sub(r'\s+', ' ', load.split('// a load that leaves')[1].split('\n', 1)[1]).strip() ==
      'try { LoadShadersThenRegister(); } finally { RegisterLoadedPrograms(); } }', 'LoadShaders registers in a finally: ' + load[-200:])
inner = member(loader, 'private void LoadShadersThenRegister()')
check(inner.replace('private void LoadShadersThenRegister()', 'public void LoadShaders()').replace(
      '            RegisterLoadedPrograms(); // RewindBox (adapt_shader_code_table_load): before the "Loaded" state is published\n', '') ==
      member(ck[LOADER], 'public void LoadShaders()'), 'the load itself is the control\'s')
check(inner.index('CheckCompilationBlocking();\n            RegisterLoadedPrograms();') < inner.index('if (_needsHostRegen && Active)') <
      inner.index('_stateChangeCallback(ShaderCacheState.Loaded'), 'registered once the last program is compiled, before the rebuild and the Loaded state')
check(loader.count('_graphicsCache.Add(') == loader.count('_computeCache.Add(') == loader.count('_graphicsCache.AddRange(') ==
      loader.count('_computeCache.AddRange(') == 1 and loader.count('RegisterLoadedProgram(entry.CachedProgram, entry.IsCompute);') == 1 and
      loader.count('"shaderCache", "codeTable"') == 1, 'one registration path, one journal line')
register = member(loader, 'private void RegisterLoadedPrograms()')
check(register.index('if (_loadedRegistered)') < register.index('_loadedRegistered = true;') < register.index('_graphicsCache.AddRange(_loadedGraphics,') <
      register.index('_computeCache.AddRange(_loadedCompute,') < register.index('EmbeddedLaunchDiagnostics.Record('), 'registration happens once')
one = member(loader, 'private void RegisterLoadedProgram(')
check(one.index('if (_loadedRegistered)') < one.index('_computeCache.Add(program);') < one.index('_graphicsCache.Add(program);') <
      one.index('(isCompute ? _loadedCompute : _loadedGraphics).Add(program);'), 'a program compiled after the registration is added at once')
check(member(ck[LOADER], 'private void ProcessCompiledProgram(').replace(FILE_PAIRS[LOADER][-1][0], FILE_PAIRS[LOADER][-1][1]) ==
      member(loader, 'private void ProcessCompiledProgram('), 'ProcessCompiledProgram only hands the program over')
play = (FINAL_SOURCE / (SHADER + 'ShaderCache.cs')).read_text(encoding='utf-8-sig')
check(play.count('_graphicsShaderCache.Add(gpShaders);') == play.count('_computeShaderCache.Add(cpShader);') == 1 and 'AddRange(' not in play and
      'ReserveSizes' not in play, 'play adds with Add')
for name in WHOLE:
    text = (FINAL_SOURCE / (SHADER + name)).read_text(encoding='utf-8-sig')
    check('EmbeddedLaunchDiagnostics' not in text and 'Stopwatch' not in text, 'no journal and no clock in the tables: ' + name)

inputs = ['build-utils/melonx/adapt_shader_code_table_load.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_shader_code_table_load_test.py', 'test/melonx_shader_code_table_load/Double.cs',
          'test/melonx_shader_code_table_load/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE},
               summary=summary, reports=reports, sdk=sdk, physicalDeviceTested=False, productionGpuProjectBuilt=True,
               realCacheUsed=real_cache is not None,
               requiredFactors=dict(hashedBytes=HASHED_FACTOR, comparedBytesSynthetic=COMPARED_FACTOR, time=TIME_FACTOR, allocatedBytes=1.5),
               sourceBaseline=BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host replay (x86-64, JIT) of the registration alone, with the real table files and the loader\'s real lines; the '
                          'synthetic sets are generated, and the 12,600-program one only has the size of a Super Smash Bros. Ultimate '
                          'load, not its codes. The time saved on an iPhone is known only from the "shaderCache codeTable" line of a device run.')
out = ROOT / 'dist/melonx/shader-code-table-load-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, realCacheUsed=real_cache is not None, summary=summary)))
