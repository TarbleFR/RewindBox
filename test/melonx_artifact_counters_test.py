#!/usr/bin/env python3
"""Artifact path counters (adapt_artifact_counters) on the real prepared engine. Instrumentation only.

Usage: melonx_artifact_counters_test.py <Core 649 prepared MeloNX tree>
       melonx_artifact_counters_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the Core 649 preparation, candidate adds the adapter. In each, the production Vulkan backend (with Common, GAL,
Shader, Spv) is built as an executable with test/melonx_artifact_counters/Program.cs, which runs the real
TextureArray.GetImageInfos (delivered walk and incremental path) and PipelineBase.CreateFramebuffer (write-mask filter)
with doubles: every descriptor value and filtered framebuffer equals the control's, and the candidate counts the elements
of a destroyed view on the dummy (not an unbound element) and each removed attachment once (not the slot the delivered
loop empties again). The complete production BarrierBatch of both variants is compiled with doubled driver boundaries
(test/melonx_artifact_counters/barrier): every API barrier, pass end and forced fence equals the control's in every
scenario, and InPassAttachmentBarriersKept moves only for attachment-only image barriers kept in a pass on a tile-based
MoltenVK without argument-buffer hazard tracking, once per loop turn of Flush that keeps them; not when a memory barrier
queued for DrawIndirect or for compute ends the pass in that same turn. Static checks bind that each file is the
preparation plus inserted counter lines only, and where each increment and the log segment sit. No device.
Writes dist/melonx/artifact-counters-checks.json.
"""
from pathlib import Path
import difflib, hashlib, json, os, re, shutil, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_artifact_counters', _HOLD)
from adapt_artifact_counters import apply, BASELINE, COUNTERS  # noqa: E402

PIPELINE = 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'
BATCH = 'src/Ryujinx.Graphics.Vulkan/BarrierBatch.cs'
ARRAY = 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs'
NATIVE = 'src/Ryujinx.Graphics.Vulkan/NativeArray.cs'
FIXTURE = ROOT / 'test/melonx_artifact_counters'
DOTNET = os.environ.get('DOTNET', 'dotnet')
PROJECTS = ['Ryujinx.Graphics.Vulkan', 'Ryujinx.Common', 'Ryujinx.Graphics.GAL', 'Ryujinx.Graphics.Shader', 'Spv.Generator']
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


NAMES = '|'.join(COUNTERS)
# The only lines the adapter may add: comments, counter increments and declarations, the log segment, the local that
# remembers whether the element resolved last had a destroyed view, and the counting branch of BarrierBatch.
INSERTED = [r'', r'// .*', r'{', r'}',
            rf'RenderDetail\.({NAMES}) \+= (destroyedView|colors\[[ij]\] != null) \? 1 : 0;',
            r'RenderDetail\.InPassAttachmentBarriersKept \+= attachmentBarriersKeptInPass && inRenderPass \? 1 : 0;',
            r'bool (destroyedView|attachmentBarriersKeptInPass) = false;',
            r'attachmentBarriersKeptInPass = true;',
            r'destroyedView = refs\.View != null && (texture\.ImageView|view)\.Handle == 0;',
            r'public static long ArrayDestroyedViewWalkElements, ArrayDestroyedViewRefreshElements;',
            r'public static long (InPassAttachmentBarriersKept|MaskedAttachmentsRemoved);',
            r'text\.Append\("; artifact paths: [^"]*"\)',
            rf'\.Append\(System\.Threading\.Interlocked\.Exchange\(ref ({NAMES}), 0\)\)(\.Append\("[^"]*"\))?(;)?',
            r'\.Append\("[^"]*"\)\.Append\(System\.Threading\.Interlocked\.Exchange\(ref MaskedAttachmentsRemoved, 0\)\);',
            r'\.Append\("[^"]*"\)',
            r'else if \(!_gd\.MoltenVkTracksArgumentBufferHazards\)']


def inserted_only(control, candidate, name):
    a, b = control.splitlines(), candidate.splitlines()
    added = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        check(tag in ('equal', 'insert'), f'{name}: {tag} of delivered lines {i1 + 1}-{i2}')
        if tag == 'insert':
            added += b[j1:j2]
    for line in added:
        check(any(re.fullmatch(p, line.strip()) for p in INSERTED), f'{name}: unexpected inserted line: {line.strip()}')
    return added


def next_code(text, after):
    """The first line after `after` that is neither blank nor a comment."""
    rest = text[text.index(after) + len(after):].splitlines()[1:]
    return next(line.strip() for line in rest if line.strip() and not line.strip().startswith('//'))


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 649 preparation: ' + name)
reports, texts = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-artifact-counters-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        work.mkdir(parents=True)
        for name in ('Directory.Build.props', 'Directory.Packages.props', 'global.json', '.editorconfig', 'nuget.config'):
            if (SOURCE / name).exists():
                shutil.copyfile(SOURCE / name, work / name)
        for project in PROJECTS:
            shutil.copytree(SOURCE / 'src' / project, work / 'src' / project, ignore=shutil.ignore_patterns('bin', 'obj'))
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                # Files a later adapter also edits (Core 661: the Hogwarts lots in PipelineBase) are proven by control_source's forward check; the others
                # must be the final preparation's bytes here.
                later = files_edited_later('adapt_artifact_counters')
                for name in BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in [*BASELINE, NATIVE]}
        project = work / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'
        tree = ET.parse(project)
        group = ET.SubElement(tree.getroot(), 'PropertyGroup')
        for name, value in [('OutputType', 'Exe'), ('StartupObject', 'Program'), ('NuGetAudit', 'false'),
                            ('EnableNETAnalyzers', 'false'), ('TreatWarningsAsErrors', 'false')]:
            ET.SubElement(group, name).text = value
        tree.write(project)
        shutil.copyfile(FIXTURE / 'Program.cs', project.parent / 'Program.cs')
        for command in ([DOTNET, 'build', str(project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                        [DOTNET, str(project.parent / 'bin/Release/net10.0/Ryujinx.Graphics.Vulkan.dll'), variant]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=1800, env=environment, cwd=work)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            check(result.returncode == 0, variant + ': ' + ' '.join(command[1:3]))
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant])[:2000], flush=True)

    control, candidate = texts['control'], texts['candidate']
    # Static: the preparation plus inserted counter lines only.
    for name in BASELINE:
        inserted_only(control[name], candidate[name], name)
    all_text = '\n'.join(candidate[name] for name in BASELINE)
    uses = re.findall(r'.*\bdestroyedView\b.*', all_text)
    check(len(uses) == 2 * 4 and all(re.search(r'bool destroyedView = false;|destroyedView = refs\.View != null|\+= destroyedView \? 1 : 0;', u)
                                     for u in uses), 'destroyedView is read only by the counters')
    pipeline, batch, array = candidate[PIPELINE], candidate[BATCH], candidate[ARRAY]
    log = member(pipeline, 'public static void Log(string window, long frames)')
    for counter in COUNTERS:
        check(log.count(f'System.Threading.Interlocked.Exchange(ref {counter}, 0)') == 1 and
              all_text.count(counter) >= 2, f'{counter}: logged and reset every window')
    check(log.index('; in-pass image barriers ending the pass ') < log.index('; artifact paths: ') < log.index('text.Append("; GPU ")') <
          log.index('Logger.Warning?.Print'), 'the segment is on the pass and GPU detail line, before the GPU figure')
    tbdr = batch[batch.index('if (_gd.IsTBDR)'):batch.index('// Generic pipeline memory barriers will work for desktop GPUs.')]
    check(tbdr.index('if (EndsPassForInPassImageBarriers(anyIsNonAttachment))') < tbdr.index('else if (!_gd.IsMoltenVk)') <
          tbdr.index('else if (!_gd.MoltenVkTracksArgumentBufferHazards)') < tbdr.index('attachmentBarriersKeptInPass = true;'),
          'marking branch after the delivered ones')
    branch = member(tbdr, 'else if (!_gd.MoltenVkTracksArgumentBufferHazards)')
    check([l.strip() for l in branch.splitlines()[1:] if l.strip() and not l.strip().startswith('//')] ==
          ['{', 'attachmentBarriersKeptInPass = true;', '}'], 'the marking branch holds only the mark')
    check(tbdr.count('endRenderPass();') == 2 and tbdr.count('inRenderPass = false;') == 2, 'pass endings unchanged')
    # The barrier counter: declared false at the top of each loop turn, set only by the branch, read only by the increment,
    # which follows the delivered memory-barrier check (the last place a turn ends the pass) and precedes the recording.
    turn = member(batch, 'while (_queuedBarrierCount > 0)')
    mark = 'attachmentBarriersKeptInPass'
    increment = 'RenderDetail.InPassAttachmentBarriersKept += attachmentBarriersKeptInPass && inRenderPass ? 1 : 0;'
    memory_check = turn.index('if (inRenderPass && _memoryBarriers.Count > 0)')
    check(batch.count(mark) == 3 and turn.count(mark) == 3 and batch.count('InPassAttachmentBarriersKept +=') == 1 and
          'InPassAttachmentBarriersKept++' not in batch, 'one mark: declared, set, read once')
    check(next_code(turn, 'bool attachmentBarriersKeptInPass = false;') == 'if (inRenderPass && _imageBarriers.Count > 0)' and
          turn.index('bool attachmentBarriersKeptInPass = false;') < turn.index('if (inRenderPass && _imageBarriers.Count > 0)'),
          'the mark is reset every loop turn, before the image-barrier decision')
    check(memory_check < turn.index('endRenderPass();', memory_check) < turn.index(increment) <
          turn.index('AddBarriers(_memoryBarrierBatch.AsSpan()') and turn.count('endRenderPass();') == 3 and
          turn.rindex('endRenderPass();') < turn.index(increment) and next_code(turn, increment).startswith('AddBarriers(_memoryBarrierBatch'),
          'the barrier counter follows the last pass end of the turn, before the barriers are recorded')
    walk = member(array, 'public ReadOnlySpan<DescriptorImageInfo> GetImageInfos(')
    check(next_code(walk, 'destroyedView = refs.View != null && texture.ImageView.Handle == 0;') ==
          'RenderDetail.ArrayDestroyedViewWalkElements += destroyedView ? 1 : 0;' and
          walk.index('RenderDetail.ArrayDestroyedViewWalkElements += destroyedView ? 1 : 0;\n\n                if (texture.ImageView.Handle == 0)') > 0,
          'walk counter at the dummy decision')
    check(next_code(walk, 'texture = textures[i - 1];') == 'RenderDetail.ArrayDestroyedViewWalkElements += destroyedView ? 1 : 0;',
          'walk counter on copied elements')
    resolve = member(array, 'private void ResolveValues(int start, int end)')
    check(next_code(resolve, 'destroyedView = refs.View != null && view.Handle == 0;') ==
          'RenderDetail.ArrayDestroyedViewRefreshElements += destroyedView ? 1 : 0;' and
          next_code(resolve, 'textures[i] = textures[i - 1];') == 'RenderDetail.ArrayDestroyedViewRefreshElements += destroyedView ? 1 : 0;',
          'refresh counter at the dummy decision and on copied elements')
    check('ImageView = view.Handle != 0 ? view : dummyView,' in resolve and
          resolve.index('destroyedView = refs.View != null && view.Handle == 0;') < resolve.index('ImageView = view.Handle != 0 ? view : dummyView,'),
          'refresh counter before the dummy choice')
    frame = member(pipeline, 'private void CreateFramebuffer(Span<ITexture> colors, ITexture depthStencil, bool filterWriteMasked)')
    check(next_code(frame, 'RenderDetail.MaskedAttachmentsRemoved += colors[i] != null ? 1 : 0;') == 'colors[i] = null;' and
          next_code(frame, 'RenderDetail.MaskedAttachmentsRemoved += colors[j] != null ? 1 : 0;') == 'colors[j] = null;',
          'filter counters at the removals')
    check(sum(all_text.count(f'RenderDetail.{c}') for c in COUNTERS) == 4 + 2 + 1, 'seven increments')

    # BarrierBatch: the complete production class of both variants against doubled driver boundaries.
    barrier = Path(temporary).resolve() / 'barrier'
    barrier.mkdir()
    check(control[NATIVE] == candidate[NATIVE] and control[BATCH].count('namespace Ryujinx.Graphics.Vulkan') == 1, 'one namespace')
    (barrier / 'Control.cs').write_text(control[BATCH].replace('namespace Ryujinx.Graphics.Vulkan', 'namespace Ryujinx.Graphics.Vulkan.Control'))
    (barrier / 'Candidate.cs').write_text(candidate[BATCH])
    (barrier / 'NativeArray.cs').write_text(candidate[NATIVE])
    for path in sorted((FIXTURE / 'barrier').glob('*.cs')):
        shutil.copyfile(path, barrier / path.name)
    (barrier / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><NuGetAudit>false</NuGetAudit>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableNETAnalyzers>false</EnableNETAnalyzers>
</PropertyGroup><ItemGroup><PackageReference Include="Silk.NET.Vulkan" Version="2.22.0" /></ItemGroup></Project>''')
    (barrier / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
    for command in ([DOTNET, 'build', str(barrier / 'test.csproj'), '-c', 'Release', '-nologo', '-m:1'],
                    [DOTNET, str(barrier / 'bin/Release/net10.0/test.dll')]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=barrier)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, 'BarrierBatch fixture: ' + ' '.join(command[1:3]))
    reports['barrier'] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    print(json.dumps(reports['barrier']), flush=True)

# Behaviour: same descriptors and framebuffers, counters only on their paths.
c, k = reports['control'], reports['candidate']
for path in ('delivered', 'incremental'):
    check([s['views'] for s in c[path]] == [s['views'] for s in k[path]] and
          [s['samplers'] for s in c[path]] == [s['samplers'] for s in k[path]], path + ': descriptor values unchanged')
    check(all(s['views'][6] == 'D0' for s in k[path]) and k[path][0]['views'] == ['11', '11', '11', '22', '22', '22', 'D0', '33'] and
          k[path][1]['views'] == ['11', '11', '11', 'D0', 'D0', 'D0', 'D0', '33'], path + ': the destroyed view takes the dummy')
    check(all(s['counted'] == -1 for s in c[path]), path + ': no counter in the control')
check([s['counted'] for s in k['delivered']] == [0, 3, 0, 3], 'walk: three elements per command-buffer walk, cached walk not counted')
check([s['counted'] for s in k['incremental']] == [0, 3, 0, 0], 'refresh: three elements when the destroyed view is refreshed, once')
strip = lambda rows: [{key: value for key, value in row.items() if key != 'removed'} for row in rows]
check(strip(c['filter']) == strip(k['filter']), 'write-mask filter decisions unchanged')
check([row['removed'] for row in k['filter']] == [1, 1, 1, 2, 0, 0, 0] and all(row['removed'] == -1 for row in c['filter']),
      'removed attachments counted once each: ' + json.dumps(k['filter']))
check(k['filter'][2]['colors'] == [0, -1, -1] and k['filter'][3]['colors'] == [0, -1, -1] and k['filter'][1]['colors'] == [-1, 0],
      'filter fixture exercised the removals')
b = reports['barrier']
check(b['result'] == 'passed' and b['keptScenarios'] == 5 and b['passEndingMemoryScenarios'] == 3 and b['keptOnPath'] == {
    'none': 0, 'one attachment': 1, 'attachments only, one stage': 1, 'attachments only, two stages': 2,
    '20 attachments (two batches of at most 16)': 2, 'memory barrier first, then an attachment': 2,
    'memory barrier to DrawIndirect, then an attachment': 0, 'an attachment, then a memory barrier to DrawIndirect': 0,
    'memory barrier to compute, then an attachment': 0, 'one non-attachment': 0, 'mixed': 0}, 'BarrierBatch counter on its path only')

inputs = ['build-utils/melonx/adapt_artifact_counters.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_adapter_control.py',
          'test/melonx_artifact_counters_test.py', 'test/melonx_artifact_counters/Program.cs',
          'test/melonx_artifact_counters/barrier/Boundaries.cs', 'test/melonx_artifact_counters/barrier/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core649Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               reports=reports, sdk=sdk, physicalDeviceTested=False, nativeCallsUsed=False, fullProductionVulkanAssembly=True,
               sourceBaseline=BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Counters only; whether any of these paths produces the black artifacts is known only from a device '
                          'run whose detail lines count them while the artifacts appear.')
out = ROOT / 'dist/melonx/artifact-counters-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
