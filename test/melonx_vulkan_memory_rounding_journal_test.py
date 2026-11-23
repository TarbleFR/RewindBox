#!/usr/bin/env python3
"""adapt_vulkan_memory_rounding_journal on the final preparation, against that preparation with the adapter reversed.

Usage: melonx_vulkan_memory_rounding_journal_test.py <final preparation>
       melonx_vulkan_memory_rounding_journal_test.py <control> --candidate-source <final preparation>

Static: the candidate is the control plus the adapter's replacements only; the block list's Allocate, the block's
Allocate and Free and the allocator's Allocate are the control's text; InsertBlock and the list's Free are the control's
text plus one counter call each; the untimed AllocateDeviceMemory body is the control's AllocateDeviceMemory body.
Executed, control and candidate alike (test/melonx_vulkan_memory_rounding_journal/Program.cs): the production
MemoryAllocator.cs, MemoryAllocatorBlockList.cs, MemoryAllocation.cs, VulkanException.cs and BitUtils.cs of each variant,
compiled with Doubles.cs (a driver modelling MoltenVK v1.4.2 on an Apple GPU: memory types private, shared, memoryless,
maxMemoryAllocationCount 2^30, one placement heap per VkDeviceMemory counted with its 16 KiB rounding, 20 us per
vkAllocateMemory) on a stream shaped like the IPA 822 Hogwarts Legacy line: 6 063 mapped buffers of 4 to 64 KiB in 4 KiB
steps, 8 736 images of 16 to 96 KiB in whole pages, 8 device-local buffers, 40 pooled temporaries; a trim (a quarter of
the buffers, half of the images); 795 buffers replaced; one buffer and one image allocation failing in the driver; eight
threads creating and freeing 4 000 buffers. Both variants must make the same native calls in the same order (sizes, types,
maps, unmaps, frees), return the same allocations (memory, offset, size, host pointer), hold the same bytes after each
phase and catch the same failures; the candidate's line must carry, for each list, exactly the 16 KiB rounding and the
count of dedicated blocks that are not whole pages that the stream implies (and that the driver double's heap rounding
shows), and the exact allocation calls since the previous line with at least the driver's time; the control's line must
be the candidate's without those segments. Host timing: allocation and free loops, control against candidate (ns and
managed bytes per allocation). The candidate's production Ryujinx.Graphics.Vulkan is built and a probe runs its real
blocks, allocator, UsageText and RenderStageTimer.Log (one "vulkanMemory sample" line in a temporary engine journal);
every line must leave the journal's redaction (EmbeddedLaunchDiagnostics.Safe) unchanged.
Writes dist/melonx/vulkan-memory-rounding-journal-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, statistics, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
CONTROL, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_vulkan_memory_rounding_journal', _HOLD)
import adapt_vulkan_memory_rounding_journal as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_vulkan_memory_rounding_journal'
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
FILES = [VULKAN + 'MemoryAllocator.cs', VULKAN + 'MemoryAllocatorBlockList.cs', VULKAN + 'MemoryAllocation.cs',
         VULKAN + 'VulkanException.cs', 'src/Ryujinx.Common/Utilities/BitUtils.cs']
KIB, MIB, PAGE = 1024, 1024 * 1024, 16384
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


def body(text, signature):
    whole = member(text, signature)
    return whole[whole.index('{'):]


# --- Static ---
check(FINAL_PREPARATION, 'the source given is a final preparation containing the adapter')
later = files_edited_later('adapt_vulkan_memory_rounding_journal')
texts = {}
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 827 preparation: ' + name)
    control_text = (CONTROL / name).read_text(encoding='utf-8-sig')
    final_text = (FINAL_SOURCE / name).read_text(encoding='utf-8-sig')
    rebuilt = control_text
    for old, new in adapter.EDITS[name]:
        check(rebuilt.count(old) == 1 and final_text.count(new) == 1, 'one site, reversible: ' + new.strip()[:60])
        rebuilt = rebuilt.replace(old, new)
    if name not in later:
        check(rebuilt == final_text, 'the final preparation is the control plus the replacements: ' + name)
    texts[name] = (control_text, rebuilt)
with tempfile.TemporaryDirectory(prefix='melonx-vulkan-rounding-refuse-') as refuse:
    for name in adapter.BASELINE:
        (Path(refuse) / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FINAL_SOURCE / name, Path(refuse) / name)
    try:
        adapter.apply(Path(refuse))
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
blocks_c, blocks_k = texts[adapter.BLOCKS]
for signature in ('public unsafe MemoryAllocation Allocate(ulong size, ulong alignment, bool map)',
                  'public ulong Allocate(ulong size, ulong alignment)', 'public void Free(ulong offset, ulong size)',
                  'public bool IsTotallyFree()', 'public unsafe void Destroy(Vk api, Device device)'):
    check(member(blocks_c, signature) == member(blocks_k, signature), 'unchanged: ' + signature)
for signature, line in (('public void Free(Block block, ulong offset, ulong size)', 'NoteDedicatedRounding(block.Size, published: false);'),
                        ('private void InsertBlock(Block block)', 'NoteDedicatedRounding(block.Size, published: true);')):
    candidate = member(blocks_k, signature)
    check(candidate.count(line) == 1 and
          candidate.replace('\n' + ' ' * (len(candidate.split(line)[0]) - len(candidate.split(line)[0].rstrip(' '))) + line, '') ==
          member(blocks_c, signature), 'the control\'s statements plus one counter call: ' + signature)
alloc_c, alloc_k = texts[adapter.ALLOCATOR]
check(member(alloc_c, 'private MemoryAllocation Allocate(int memoryTypeIndex') == member(alloc_k, 'private MemoryAllocation Allocate(int memoryTypeIndex'),
      'the allocator\'s Allocate is unchanged')
check(body(alloc_c, 'public MemoryAllocation AllocateDeviceMemory(') == body(alloc_k, 'private MemoryAllocation AllocateDeviceMemoryUntimed('),
      'the untimed allocation is the control\'s AllocateDeviceMemory body')
wrapper = member(alloc_k, 'public MemoryAllocation AllocateDeviceMemory(')
check(wrapper.count('return AllocateDeviceMemoryUntimed(requirements, flags, isBuffer, poolSmallBuffer);') == 1 and
      wrapper.index('try') < wrapper.index('return AllocateDeviceMemoryUntimed') < wrapper.index('finally') and
      ' new ' not in wrapper and 'Interlocked.Add(ref _bufferAllocationTicks, ticks)' in wrapper,
      'the wrapper: the untimed call inside try, counters in finally, no allocation')

# The engine journal's privacy filter, read from its source (test/melonx_jit_arena_usage_journal_test.py's survives).
safe_source = (ROOT / 'native/melonx/EmbeddedLaunchDiagnostics.cs').read_text()
safe_rules = re.findall(r'value = Regex\.Replace\(value, @"([^"]+)", "(\[redacted[^"]*\])"\);', safe_source)
check(len(safe_rules) >= 2, 'the journal\'s redaction rules are read from its source: ' + str(len(safe_rules)))


def survives(detail):
    out = detail
    for pattern, replacement in safe_rules:
        out = re.sub(pattern.replace('(?i)', '').replace('(?im)', ''), replacement, out,
                     flags=(re.I | re.M) if '(?im)' in pattern else re.I if '(?i)' in pattern else 0)
    return out == detail and len(detail) <= 4096


check(not survives('roundingKiB=12 (16 KiB pages)'), 'the redaction check sees a "name=" detail as redacted')

# --- The stream's expected figures (independent of the C# code) ---
SEG_LIST = re.compile(r', 16 KiB rounding \d+ KiB over \d+ of \d+ dedicated blocks')
SEG_CALLS = re.compile(r'; device memory allocations since the previous line \(adapt_vulkan_memory_rounding_journal\): '
                       r'buffers (\d+) in ([0-9.]+) ms, images (\d+) in ([0-9.]+) ms')


def slack(size):
    return (PAGE - size % PAGE) % PAGE


def expected_line(lists, calls):
    """lists: in creation order, (type, buffers, dedicated sizes, pooled blocks [(size, used)], mapped)."""
    rows = []
    for type_, is_buffer, dedicated, pooled, mapped in lists:
        blocks = len(dedicated) + len(pooled)
        size = sum(dedicated) + sum(s for s, _ in pooled)
        rows.append(dict(type=type_, buffers=is_buffer, blocks=blocks, bytes=size, dedicated=sum(dedicated), mapped=size if mapped else 0,
                         free=sum(s - u for s, u in pooled), count=len(dedicated), rounding=sum(slack(s) for s in dedicated),
                         unaligned=sum(1 for s in dedicated if slack(s))))
    total = {k: sum(r[k] for r in rows) for k in ('blocks', 'bytes', 'dedicated', 'mapped', 'free')}
    text = ('Vulkan device memory: %d blocks %d MiB (dedicated %d MiB, mapped %d MiB, pooled free %d MiB) in %d lists'
            % (total['blocks'], total['bytes'] // MIB, total['dedicated'] // MIB, total['mapped'] // MIB, total['free'] // MIB, len(rows)))
    for r in sorted(rows, key=lambda r: -r['bytes'])[:4]:  # List.Sort of four entries is an insertion sort: stable
        text += ('; type %d %s: %d blocks %d MiB (dedicated %d MiB, mapped %d MiB, pooled free %d MiB), 16 KiB rounding %d KiB over %d of %d dedicated blocks'
                 % (r['type'], 'buffers' if r['buffers'] else 'images', r['blocks'], r['bytes'] // MIB, r['dedicated'] // MIB, r['mapped'] // MIB,
                    r['free'] // MIB, r['rounding'] // KIB, r['unaligned'], r['count']))
    text += ('; device memory allocations since the previous line (adapt_vulkan_memory_rounding_journal): buffers %d in MS ms, images %d in MS ms'
             % calls)
    return text + ' (adapt_vulkan_memory_journal)', sum(r['rounding'] for r in rows)


buffers = [4096 * (1 + i % 16) for i in range(6063)]
images = [16384 * (1 + i % 6) for i in range(8736)]
local = [65536] * 8
temporaries = [4096 * (1 + i % 4) for i in range(40)]
pool = [(MIB, sum(temporaries))]
EXPECTED = []
EXPECTED.append(expected_line([(1, True, buffers, [], True), (0, False, images, [], False), (0, True, local, [], False),
                               (1, True, [], pool, True)], (6111, 8736)))
buffers2, images2 = buffers[1516:], images[4368:]
EXPECTED.append(expected_line([(1, True, buffers2, [], True), (0, False, images2, [], False), (0, True, local, [], False),
                               (1, True, [], [], True)], (0, 0)))
buffers3 = buffers2[795:] + [4096 * (1 + (6063 + j) % 16) for j in range(795)]
EXPECTED.append(expected_line([(1, True, buffers3, [], True), (0, False, images2, [], False), (0, True, local, [], False),
                               (1, True, [], [], True)], (795, 0)))
EXPECTED.append(expected_line([(1, True, buffers3, [], True), (0, False, images2, [], False), (0, True, local, [], False),
                               (1, True, [], [], True)], (1, 1)))
EXPECTED.append(expected_line([(1, True, buffers3, [], True), (0, False, images2, [], False), (0, True, local, [], False),
                               (1, True, [], [], True)], (4000, 0)))
EXPECTED.append(expected_line([(1, True, [], [], True), (0, False, [], [], False), (0, True, [], [], False),
                               (1, True, [], [], True)], (0, 0)))
check(EXPECTED[0][1] == 36384 * KIB, 'the stream: 4 548 of the 6 063 buffers are not whole pages, 36 384 KiB of rounding')

# --- Control and candidate on the stream ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
reports, timing, compiled = {}, {'control': [], 'candidate': []}, {}
temporary = tempfile.TemporaryDirectory(prefix='melonx-vulkan-rounding-')
WORK = Path(temporary.name).resolve()
programs = {}
for variant, tree in (('control', CONTROL), ('candidate', FINAL_SOURCE)):
    work = WORK / variant
    for relative in FILES:
        (work / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tree / relative, work / relative)
    for name in ('Doubles.cs', 'Program.cs'):
        shutil.copyfile(FIXTURE / name, work / name)
    sources = FILES + ['Doubles.cs', 'Program.cs']
    compiled[variant] = {p: sha(work / p) for p in sources}
    (work / 'Stream.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
                                        '<TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
                                        '<EnableDefaultCompileItems>false</EnableDefaultCompileItems><TieredPGO>false</TieredPGO></PropertyGroup><ItemGroup>' +
                                        ''.join(f'<Compile Include="{p}" />' for p in sources) + '</ItemGroup></Project>')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
    (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    build = subprocess.run([DOTNET, 'build', 'Stream.csproj', '-c', 'Release', '--nologo', '-v', 'quiet'], cwd=work, capture_output=True,
                           text=True, timeout=600, env=environment)
    if build.returncode:
        print(build.stdout[-4000:], build.stderr[-2000:], flush=True)
    check(build.returncode == 0, variant + ': the production allocator files build with the driver double')
    programs[variant] = work / 'bin/Release/net10.0/Stream.dll'


def run(variant, mode):
    result = subprocess.run([DOTNET, str(programs[variant]), mode], capture_output=True, text=True, timeout=900, env=environment)
    if result.returncode:
        print(result.stdout[-3000:], result.stderr[-3000:], flush=True)
    check(result.returncode == 0, variant + ' ' + mode + ' ran')
    return json.loads(result.stdout.strip().splitlines()[-1])


for variant in ('control', 'candidate'):
    reports[variant] = run(variant, 'main')
for _ in range(3):
    for variant in ('control', 'candidate'):
        timing[variant].append(run(variant, 'timing'))

c, k = reports['control'], reports['candidate']
for field in ('nativeTraceSha256', 'allocationTraceSha256', 'nativeTraceLength', 'after', 'caught'):
    check(c[field] == k[field], 'control and candidate alike: ' + field)
check(k['caught'] == 2, 'both driver failures reach the caller')
check(k['after'][-1]['live'] == 0 and k['after'][-1]['Allocations'] == k['after'][-1]['Frees'] and
      k['after'][-1]['Maps'] == k['after'][-1]['Unmaps'], 'everything freed at the end')
check(k['after'][1]['LiveBytes'] < k['after'][0]['LiveBytes'] and k['after'][1]['Frees'] - k['after'][0]['Frees'] == 1516 + 4368 + 1,
      'the trim gives the same blocks back to the driver in both (each dedicated block, and the empty temporary block)')
lines = []
for index, (expected, rounding) in enumerate(EXPECTED):
    line = k['lines'][index]
    calls = SEG_CALLS.search(line)
    check(calls is not None, 'line %d carries the allocation calls: %s' % (index + 1, line))
    shown = SEG_CALLS.sub('; device memory allocations since the previous line (adapt_vulkan_memory_rounding_journal): '
                          r'buffers \1 in MS ms, images \3 in MS ms', line)
    check(shown == expected, 'line %d is exact:\n%s\n%s' % (index + 1, line, expected))
    driver = k['after'][index]['LiveHeapBytes'] - k['after'][index]['LiveBytes']
    check(driver == rounding, 'line %d: the rounding is what the driver\'s 16 KiB heaps add: %d against %d' % (index + 1, driver, rounding))
    buffer_calls, buffer_ms, image_calls, image_ms = int(calls[1]), float(calls[2]), int(calls[3]), float(calls[4])
    spin = k['spinMicroseconds'] / 1000
    check(buffer_ms + 0.05 >= buffer_calls * spin and image_ms + 0.05 >= image_calls * spin and
          buffer_ms <= buffer_calls * spin + 10000 and image_ms <= image_calls * spin + 10000,
          'line %d: the time holds the driver\'s %.0f us a call, and little more: %s' % (index + 1, spin * 1000, calls.group(0)))
    check(SEG_LIST.sub('', SEG_CALLS.sub('', line)) == c['lines'][index], 'line %d: the control\'s line is the candidate\'s without the new segments' % (index + 1))
    check(survives(line), 'line %d survives the journal\'s redaction' % (index + 1))
    lines.append(line)

# A line of the device's size (the IPA 822 figures, four lists, the largest counts) stays within the journal's 4096 characters.
big = ('Vulkan device memory: 14807 blocks 633 MiB (dedicated 633 MiB, mapped 194 MiB, pooled free 0 MiB) in 4 lists' +
       ''.join('; type %d %s: 99999 blocks 99999 MiB (dedicated 99999 MiB, mapped 99999 MiB, pooled free 99999 MiB), 16 KiB rounding '
               '9999999 KiB over 99999 of 99999 dedicated blocks' % (t, kind) for t, kind in ((0, 'images'), (1, 'buffers'), (0, 'buffers'), (1, 'buffers'))) +
       '; device memory allocations since the previous line (adapt_vulkan_memory_rounding_journal): buffers 9999999 in 99999.9 ms, '
       'images 9999999 in 99999.9 ms (adapt_vulkan_memory_journal)')
check(survives(big) and len(big) < 1200, 'the largest line fits the journal: %d characters' % len(big))


def median(variant, field):
    return statistics.median(t[field] for t in timing[variant])


cost = {variant: {field: median(variant, field) for field in ('bufferNsPerAllocation', 'imageNsPerAllocation', 'bufferBytesPerAllocation',
                                                                   'imageBytesPerAllocation')} for variant in ('control', 'candidate')}
for kind in ('buffer', 'image'):
    check(cost['candidate'][kind + 'BytesPerAllocation'] <= cost['control'][kind + 'BytesPerAllocation'],
          kind + ': the timer allocates no managed memory: %s' % cost)
    check(cost['candidate'][kind + 'NsPerAllocation'] <= cost['control'][kind + 'NsPerAllocation'] + 1000,
          kind + ': the timer costs well under a microsecond an allocation on this host: %s' % cost)
check(all(t['live'] == 0 for v in timing for t in timing[v]), 'timing loops leave nothing allocated')

# --- The candidate's production assembly and its journal line ---
tree = WORK / 'tree'
shutil.copytree(FINAL_SOURCE, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
project = tree / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')
project.write_text(project.read_text(encoding='utf-8-sig').replace(
    '</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXRoundingProbe" /></ItemGroup>\n</Project>'))
probe = WORK / 'probe'
probe.mkdir()
shutil.copyfile(FIXTURE / 'Probe.cs', probe / 'Program.cs')
(probe / 'MeloNXRoundingProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NuGetAudit>false</NuGetAudit><ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally></PropertyGroup>
  <ItemGroup><ProjectReference Include="{project}" /></ItemGroup>
</Project>
''')
for extra in ('global.json', 'nuget.config'):
    if (tree / extra).exists():
        shutil.copyfile(tree / extra, probe / extra)
build = subprocess.run([DOTNET, 'build', str(probe / 'MeloNXRoundingProbe.csproj'), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                       capture_output=True, text=True, timeout=2400, env=environment, cwd=probe)
if build.returncode:
    print('\n'.join(sorted({l for l in build.stdout.splitlines() if ' error ' in l}))[:4000], flush=True)
check(build.returncode == 0, 'the probe builds against the candidate\'s production Vulkan assembly')
warned = sorted({l for l in build.stdout.splitlines() if 'warning' in l and ('MemoryAllocator.cs' in l or 'MemoryAllocatorBlockList.cs' in l)})
check(not warned, 'no warning in the edited files: ' + str(warned[:2]))
result = subprocess.run([DOTNET, str(probe / 'bin/Release/net10.0/MeloNXRoundingProbe.dll')], capture_output=True, text=True, timeout=600,
                        env=environment, cwd=probe)
if result.returncode:
    print(result.stdout[-2000:], result.stderr[-3000:], flush=True)
check(result.returncode == 0, 'the probe ran')
production = json.loads(result.stdout.strip().splitlines()[-1])
check(production['empty'] == 5, 'no memory type: the five calls return before any Vulkan call, through the wrapper')
HEAD = 'Vulkan device memory: %d blocks 0 MiB (dedicated 0 MiB, mapped 0 MiB, pooled free 0 MiB) in 2 lists'
BUFFERS = '; type 1 buffers: 2 blocks 0 MiB (dedicated 0 MiB, mapped 0 MiB, pooled free 0 MiB), 16 KiB rounding 12 KiB over 1 of 2 dedicated blocks'
IMAGES = '; type 0 images: %d blocks 0 MiB (dedicated 0 MiB, mapped 0 MiB, pooled free 0 MiB), 16 KiB rounding %d KiB over %d of %d dedicated blocks'
CALLS = '; device memory allocations since the previous line (adapt_vulkan_memory_rounding_journal): buffers %d in MS ms, images %d in MS ms'
TAIL = ' (adapt_vulkan_memory_journal)'


def masked(line):
    return re.sub(r'in [0-9.]+ ms', 'in MS ms', line)


check(masked(production['first']) == HEAD % 3 + BUFFERS + IMAGES % (1, 12, 1, 1) + CALLS % (3, 2) + TAIL,
      'production: 20 and 48 KiB buffers, a 52 KiB image, 3 buffer and 2 image calls: ' + production['first'])
check(masked(production['second']) == HEAD % 3 + BUFFERS + IMAGES % (1, 12, 1, 1) + CALLS % (0, 0) + TAIL,
      'production: the calls are counted from the previous line: ' + production['second'])
check(masked(production['third']) == BUFFERS.join([HEAD % 2, '']) + IMAGES % (0, 0, 0, 0) + CALLS % (0, 0) + TAIL,
      'production: the image block freed by the list\'s own Free takes its rounding with it: ' + production['third'])
check(len(production['journaled']) == 1, 'one vulkanMemory line from RenderStageTimer.Log')
record = json.loads(production['journaled'][0][production['journaled'][0].index('{'):])
check(record['stage'] == 'vulkanMemory' and record['status'] == 'sample' and
      masked(record['diagnostic']) == BUFFERS.join([HEAD % 2, '']) + IMAGES % (0, 0, 0, 0) + CALLS % (0, 0) + TAIL,
      'the engine journal holds the line as written, not redacted: ' + record['diagnostic'])
check(all(survives(production[key]) for key in ('first', 'second', 'third')) and survives(record['diagnostic']),
      'the production lines survive the journal\'s redaction')
shutil.rmtree(tree)
shutil.rmtree(probe)

inputs = ['build-utils/melonx/adapt_vulkan_memory_rounding_journal.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_vulkan_memory_rounding_journal_test.py', 'test/melonx_adapter_control.py',
          'test/melonx_vulkan_memory_rounding_journal/Doubles.cs', 'test/melonx_vulkan_memory_rounding_journal/Program.cs',
          'test/melonx_vulkan_memory_rounding_journal/Probe.cs', 'native/melonx/EmbeddedLaunchDiagnostics.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               physicalDeviceTested=False, productionVulkanAssemblyBuilt=True, allocationBehaviourIdentical=True,
               postimages={name: sha(FINAL_SOURCE / name) for name in adapter.BASELINE}, sourceBaseline=adapter.BASELINE,
               candidateLines=lines, productionLines={key: production[key] for key in ('first', 'second', 'third')},
               journaledDetail=record['diagnostic'], nativeTraceSha256=k['nativeTraceSha256'], phases=k['after'],
               hostCost=cost, timingRuns=timing, sdk=sdk, host=platform.system(), compiledSources=compiled,
               inputs={name: sha(ROOT / name) for name in inputs},
               limitation='Production allocator files with a driver double (no Vulkan device, no Metal): the rounding counted is that of '
                          'the requirement sizes the stream gives; on an iPhone the sizes are MoltenVK\'s (heapBufferSizeAndAlign and '
                          'heapTextureSizeAndAlign) and the times are the real vkAllocateMemory and vkMapMemory.')
out = ROOT / 'dist/melonx/vulkan-memory-rounding-journal-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
temporary.cleanup()
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, hostCost=cost)))
