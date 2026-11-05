#!/usr/bin/env python3
"""Later reader stages and render/compute switches ordered under MoltenVK 1.4.2's fences (adapt_moltenvk_stage_ordering).

Usage: melonx_moltenvk_stage_ordering_test.py <Core 658 prepared MeloNX tree>
       melonx_moltenvk_stage_ordering_test.py <control> --candidate-source <final preparation containing the adapter>
When the MoltenVK v1.4.2 sources are present (/home/user/work/mvk/MoltenVK or $MOLTENVK_SOURCE), the fence model of the
fixture is bound to them.

Control is the Core 658 preparation, candidate adds the adapter. Steps:
1. Static: each candidate file is the preparation once the adapter's replacements are undone (nothing else changes);
   the coverage branch, the switch decisions, the barrier notes and the Library flag are where the change says; Ryujinx's
   render passes declare only their self-dependency, which MoltenVK skips (no fence at a pass boundary).
2. The production Ryujinx.Library assembly (with Ryujinx.Graphics.Vulkan, HLE, Gpu) builds from the candidate.
3. Fixture, both variants: the production Ryujinx.Graphics.Vulkan sources compiled as an executable with
   test/melonx_moltenvk_stage_ordering/Program.cs, which runs the real TextureStorage.QueueWriteToReadBarrier,
   TextureArray.QueueWriteToReadBarriers and BarrierBatch queue on objects created without Vulkan, and replays the queued
   barriers on a model of MoltenVK 1.4.2's barrier fences. Required: in the control, a later reader in another stage
   (compute after fragment, vertex after fragment, arrays) is not ordered after the attachment
   write; in the candidate it is, with one barrier per new stage and none for a stage already covered, the counters move
   by reader stage, and MoltenVK 1.4.0 keeps the single delivered barrier. Candidate only: the production EncoderOrdering
   decisions order render-to-compute and compute-to-render switches no barrier orders when the policy is on, count them
   when it is off, skip covered ones, ignore command buffer changes and render-to-render.
No device. Writes dist/melonx/moltenvk-stage-ordering-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_moltenvk_stage_ordering', _HOLD)
import adapt_moltenvk_stage_ordering  # noqa: E402
from adapt_moltenvk_stage_ordering import apply, BASELINE  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
MOLTENVK = Path(os.environ.get('MOLTENVK_SOURCE', '/home/user/work/mvk/MoltenVK'))
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
STORAGE, PIPELINE, BATCH, LIBRARY = (VULKAN + 'TextureStorage.cs', VULKAN + 'PipelineBase.cs', VULKAN + 'BarrierBatch.cs',
                                     'src/Ryujinx.Library/Library.cs')
PROJECTS = ['Ryujinx.Graphics.Vulkan', 'Ryujinx.Common', 'Ryujinx.Graphics.GAL', 'Ryujinx.Graphics.Shader', 'Spv.Generator']
UNCHANGED = [VULKAN + name for name in ('TextureArray.cs', 'ImageArray.cs', 'DescriptorSetUpdater.cs', 'RenderPassHolder.cs',
                                        'TextureView.cs', 'FramebufferParams.cs', 'BufferHolder.cs', 'VulkanRenderer.cs')]
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


def ordered(text, *parts):
    positions = [text.find(part) for part in parts]
    return all(p >= 0 for p in positions) and positions == sorted(positions)


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 658 preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
replacements = []
original_once = adapt_moltenvk_stage_ordering.once
reports = {}
library_build = {}
with tempfile.TemporaryDirectory(prefix='melonx-stage-ordering-') as temporary:
    # 1-2. The whole candidate tree: undo-and-compare, static checks, the production Library build.
    work = Path(temporary).resolve() / 'candidate-tree'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(work, ROOT)

    def recording_once(path, old, new):
        replacements.append((path.relative_to(work).as_posix(), old, new))
        original_once(path, old, new)

    adapt_moltenvk_stage_ordering.once = recording_once
    try:
        changed = apply(work)
    finally:
        adapt_moltenvk_stage_ordering.once = original_once
    check(sorted(p.relative_to(work).as_posix() for p in changed) == sorted(BASELINE), 'adapter changed other files')
    if FINAL_PREPARATION:
        for name in BASELINE:
            check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    for name in BASELINE:
        undone = (work / name).read_text(encoding='utf-8-sig')
        for path, old, new in reversed(replacements):
            if path == name:
                check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
                undone = undone.replace(new, old)
        check(undone == (SOURCE / name).read_text(encoding='utf-8-sig'), name + ' is the preparation but the adapter\'s replacements')
    for name in UNCHANGED:
        check((work / name).read_bytes() == (SOURCE / name).read_bytes(), 'unchanged: ' + name)
    check(len(replacements) == 10 and all('RewindBox (adapt_moltenvk_stage_ordering)' in new for _, _, new in replacements),
          'ten replacements, each with a production comment')

    storage = (work / STORAGE).read_text(encoding='utf-8-sig')
    pipeline = (work / PIPELINE).read_text(encoding='utf-8-sig')
    batch = (work / BATCH).read_text(encoding='utf-8-sig')
    library = (work / LIBRARY).read_text(encoding='utf-8-sig')
    control_storage = (SOURCE / STORAGE).read_text(encoding='utf-8-sig')

    read = member(storage, 'public void QueueWriteToReadBarrier(')
    control_read = member(control_storage, 'public void QueueWriteToReadBarrier(')
    check(control_read.count('_gd.Barriers.QueueBarrier(') == 1 and control_read.count('_lastModificationAccess = AccessFlags.None;') == 2,
          'control: one barrier, for the first reader only, then the modification is cleared')
    first = read[:read.index('else if (_readCoverageAccess != AccessFlags.None')]
    later = read[read.index('else if (_readCoverageAccess != AccessFlags.None'):]
    check(ordered(first, 'TryDeferInPassReadBarrier(this, dstStageFlags)', '_readCoverageAccess = AccessFlags.None;\n                    return;',
                  '_gd.Barriers.QueueBarrier(barrier, this, _lastModificationStage, dstStageFlags);',
                  '_readCoverageAccess = _lastModificationAccess;', '_readCoverageStage = _lastModificationStage;',
                  '_readCoveredStages = dstStageFlags;', 'RenderDetail.NoteWriteToRead(dstStageFlags, later: false);',
                  '_lastModificationAccess = AccessFlags.None;\n            }'),
          'first reader: the delivered barrier, then the coverage of this modification')
    check('(dstStageFlags & ~_readCoveredStages) != 0 &&\n                _gd.IsMoltenVk && !_gd.MoltenVkTracksArgumentBufferHazards && !Disposed)' in later and
          ordered(later, 'PipelineStageFlags newStages = dstStageFlags & ~_readCoveredStages;', '_readCoverageAccess,',
                  '_gd.Barriers.QueueBarrier(barrier, this, _readCoverageStage, newStages);', '_readCoveredStages |= newStages;',
                  'RenderDetail.NoteWriteToRead(newStages, later: true);') and re.search(r'\bnew\s+[A-Z(\[]', later) is None,
          'later reader: a barrier from the writer\'s stage to the new stages only, no allocation, MoltenVK 1.4.1+ only, disposed storage excluded')

    check(pipeline.count('public static bool OrderEncoderTransitions { get; set; }') == 1 and
          'private bool OrdersEncoderTransitions => MoltenVkPolicy.OrderEncoderTransitions && Gd.IsMoltenVk && !Gd.MoltenVkTracksArgumentBufferHazards;' in pipeline,
          'policy gate: Hogwarts flag, MoltenVK without argument-buffer hazard tracking')
    begin = member(pipeline, 'private unsafe void BeginRenderPass()')
    check(ordered(begin, 'FramebufferParams.InsertLoadOpBarriers(Gd, Cbs);', 'EncoderOrdering.BeforeRenderPass(CommandBuffer.Handle, OrdersEncoderTransitions)',
                  'RecordEncoderTransitionBarrier();', 'EncoderOrdering.RenderPassBegun(CommandBuffer.Handle);', 'Gd.Api.CmdBeginRenderPass('),
          'render pass begin: load-op barriers, the switch decision and barrier, then the pass')
    dispatch = member(pipeline, 'private bool PrepareComputeDispatch(bool allowAsyncSkip)')
    check(ordered(dispatch, 'Gd.Barriers.Flush(Cbs, _program', 'EncoderOrdering.BeforeDispatch(CommandBuffer.Handle, OrdersEncoderTransitions)',
                  'RecordEncoderTransitionBarrier();', 'EncoderOrdering.DispatchRecorded(CommandBuffer.Handle);',
                  'UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Compute)'), 'dispatch: flush, the switch decision and barrier, then descriptors')
    for name in ('public void DispatchCompute(', 'public void DispatchComputeIndirect('):
        body = member(pipeline, name)
        check(ordered(body, 'EndRenderPass();', 'RecreateComputePipelineIfNeeded(', 'Gd.Api.CmdDispatch'), name + ' records after the decision')
    record = member(pipeline, 'private void RecordEncoderTransitionBarrier()')
    check('PipelineStageFlags.AllCommandsBit,\n                PipelineStageFlags.AllCommandsBit,' in record and
          'SrcAccessMask = AccessFlags.MemoryWriteBit' in record and 'AccessFlags.MemoryReadBit | AccessFlags.MemoryWriteBit' in record and
          ordered(record, 'Gd.Api.CmdPipelineBarrier(', 'EncoderOrdering.NoteBarrier(CommandBuffer.Handle, PipelineStageFlags.AllCommandsBit'),
          'the switch barrier: AllCommands to AllCommands, memory write to read/write, noted')
    flush = member(batch, 'public unsafe void Flush(CommandBufferScoped cbs, ShaderCollection program')
    tail = flush[flush.index('if (hasBarrier)'):]
    check(ordered(tail, 'if (inRenderPass)', 'srcStageFlags &= ~PipelineStageFlags.ComputeShaderBit;', 'else',
                  'EncoderOrdering.NoteBarrier(cbs.CommandBuffer.Handle, srcStageFlags, flags.Dest);', '_gd.Api.CmdPipelineBarrier(') and
          batch.count('EncoderOrdering.NoteBarrier(') == 1, 'BarrierBatch notes only barriers recorded outside a render pass')
    log = member(pipeline, 'public static void Log(string window, long frames)')
    check(ordered(log, 'write-to-read barriers (vertex/fragment/compute): first reader', 'later reader in a new stage',
                  'encoder switches: render to compute', 'compute to render', 'text.Append("; GPU ")') and
          log.count('Interlocked.Exchange(ref WriteToRead') == 6 and log.count('Interlocked.Exchange(ref EncoderOrdering.') == 6,
          'the 5 s detail line reports and resets every counter')
    check(library.count('MoltenVkPolicy.OrderEncoderTransitions') == 1 and
          ordered(library, 'bool hogwarts = EmbeddedIsHogwarts(options.InputPath);', 'MoltenVkPolicy.DeferInPassReadBarriers = hogwarts;',
                  'Ryujinx.Graphics.Vulkan.MoltenVkPolicy.OrderEncoderTransitions = hogwarts;'),
          'the Library assigns the policy once per session from the launched title (Hogwarts Legacy)')
    converter = (work / VULKAN / 'PipelineConverter.cs').read_text(encoding='utf-8-sig')
    check(re.search(r'return new SubpassDependency\(\s*0,\s*0,\s*stages,', member(converter, 'public static SubpassDependency CreateSubpassDependency(')) is not None,
          'Ryujinx render passes declare only the self-dependency 0 -> 0 (no external dependency)')

    project = work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'
    result = subprocess.run([DOTNET, 'build', str(project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                            capture_output=True, text=True, timeout=3600, env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Library (with Ryujinx.Graphics.Vulkan) builds with the adapter')
    built = work / 'src/Ryujinx.Graphics.Vulkan/bin/Release/net10.0/Ryujinx.Graphics.Vulkan.dll'
    check(built.is_file() and b'EncoderOrdering' in built.read_bytes(), 'the built Vulkan assembly carries the change')
    library_build = {'project': 'src/Ryujinx.Library/Ryujinx.Library.csproj', 'vulkanAssemblySha256': hashlib.sha256(built.read_bytes()).hexdigest()}
    shutil.rmtree(work)

    # 3. Fixture, control and candidate.
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        work.mkdir(parents=True)
        for name in ('Directory.Build.props', 'Directory.Packages.props', 'global.json', '.editorconfig', 'nuget.config'):
            if (SOURCE / name).exists():
                shutil.copyfile(SOURCE / name, work / name)
        for project_name in PROJECTS:
            shutil.copytree(SOURCE / 'src' / project_name, work / 'src' / project_name, ignore=shutil.ignore_patterns('bin', 'obj'))
        (work / LIBRARY).parent.mkdir(parents=True)
        shutil.copyfile(SOURCE / LIBRARY, work / LIBRARY)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            apply(work)
        project = work / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'
        tree = ET.parse(project)
        group = ET.SubElement(tree.getroot(), 'PropertyGroup')
        for name, value in [('OutputType', 'Exe'), ('StartupObject', 'Program'), ('NuGetAudit', 'false'),
                            ('EnableNETAnalyzers', 'false'), ('TreatWarningsAsErrors', 'false')]:
            ET.SubElement(group, name).text = value
        tree.write(project)
        shutil.copyfile(ROOT / 'test/melonx_moltenvk_stage_ordering/Program.cs', project.parent / 'Program.cs')
        for command in ([DOTNET, 'build', str(project), '-c', 'Release', '-nologo', '-m:1'],
                        [DOTNET, str(project.parent / 'bin/Release/net10.0/Ryujinx.Graphics.Vulkan.dll'), variant]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=1800, env=environment, cwd=work)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            check(result.returncode == 0, variant + ': ' + ' '.join(command[1:2]))
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps({k: v for k, v in reports[variant].items() if k != 'switches'}), flush=True)
        shutil.rmtree(work)

c, k = reports['control']['readers'], reports['candidate']['readers']
for name in ('fragment then compute', 'fragment then vertex', 'texture array (2 storages): fragment then compute'):
    check(c[name]['ordered'][0] and not c[name]['ordered'][-1], 'control: the later reader is not ordered: ' + name)
    check(all(k[name]['ordered']), 'candidate: every reader ordered: ' + name)
# A later fragment reader is ordered in both (MoltenVK chains the fragment stage to itself at each barrier from it); the
# candidate's extra barrier there is the Vulkan-required one, redundant under MoltenVK.
check(c['compute then fragment']['ordered'] == [True, True] and k['compute then fragment']['ordered'] == [True, True] and
      c['compute then fragment']['barriers'] == 1 and k['compute then fragment']['barriers'] == 2, 'fragment after compute')
check(c['written again']['ordered'] == [True, False, True, False] and all(k['written again']['ordered']), 'each write')
check(c['fragment twice'] == k['fragment twice'] and k['fragment twice']['barriers'] == 1, 'a covered stage costs nothing')
check(c['MoltenVK 1.4.0: fragment then compute'] == k['MoltenVK 1.4.0: fragment then compute'], 'MoltenVK 1.4.0 unchanged')
check(c['not MoltenVK: fragment then compute'] == k['not MoltenVK: fragment then compute'] and
      k['not MoltenVK: fragment then compute']['barriers'] == 1, 'not MoltenVK: identical to the control')
check(c['no write'] == k['no write'] and k['no write']['barriers'] == 0, 'no modification, no barrier')
check(reports['control']['switches'] is None and len(reports['candidate']['switches']) == 11, 'switch scenarios ran on the candidate')
check(reports['control']['checks'] > 10 and reports['candidate']['checks'] > 40, 'fixture checks ran')

moltenvk = None
if (MOLTENVK / 'MoltenVK/Commands/MVKCommandBuffer.mm').is_file():
    mvk = MOLTENVK / 'MoltenVK'
    files = {p: (mvk / p).read_text() for p in ('GPUObjects/MVKPipeline.mm', 'Commands/MVKCmdPipeline.mm', 'Commands/MVKCommandBuffer.mm',
                                                 'Vulkan/mvk_datatypes.mm', 'GPUObjects/MVKDevice.h', 'GPUObjects/MVKDevice.mm',
                                                 'GPUObjects/MVKRenderPass.mm')}
    cmd = files['Commands/MVKCommandBuffer.mm']
    check(re.search(r'\} else if \(!_device->hasResidencySet\(\)\) \{\s*MVKDescriptorBindOperationCode useTex', files['GPUObjects/MVKPipeline.mm']) is not None and
          '_metalFeatures.residencySets = mvkOSVersionIsAtLeast(15.0, 18.0, 2.0);' in files['GPUObjects/MVKDevice.mm'],
          'MoltenVK: residency set on iOS 18, no UseResource for argument-buffer descriptors then')
    pipeline_cmd = files['Commands/MVKCmdPipeline.mm']
    check(re.search(r'if \(!cmdEncoder->_mtlRenderEncoder && cmdEncoder->isUsingMetalArgumentBuffers\(\) && cmdEncoder->getDevice\(\)->hasResidencySet\(\)\) \{\s*'
                    r'cmdEncoder->endCurrentMetalEncoding\(\);', pipeline_cmd) is not None and
          'cmdEncoder->setBarrier(sourceStageMask, destStageMask);' in pipeline_cmd and
          '#endif' not in pipeline_cmd[pipeline_cmd.rindex('#if MVK_MACOS', 0, pipeline_cmd.index('memoryBarrierWithScope')):
                                       pipeline_cmd.index('memoryBarrierWithScope')],
          'MoltenVK: fences only for a barrier outside a render encoder; the in-pass memory barrier is macOS only')
    check(re.search(r'fenceSlots\.wait\[j\]\[i\] = fenceSlots\.update\[i\];\s*\}\s*fenceSlots\.wait\[i\]\[i\] = fenceSlots\.update\[i\];\s*'
                    r'mvkEnableFlags\(fenceSlots\.updateDirtyBits, 1 << i\);', cmd) is not None, 'model: setBarrier')
    check(re.search(r'fenceSlots\.update\[stage\] = \(fenceSlots\.update\[stage\] \+ 1\) % kMVKBarrierFenceCount;\s*'
                    r'if \(fenceSlots\.update\[stage\] == 0\) fenceSlots\.update\[stage\] = 1;', cmd) is not None and
          'static const uint32_t kMVKBarrierFenceCount = 64;' in files['GPUObjects/MVKDevice.h'], 'model: getBarrierStageFence')
    check(cmd.count('auto fenceIndex = _pEncodingContext->fenceSlots.wait[stage][i];') == 3, 'model: barrierWait, one slot per stage')
    check(ordered(member(cmd, 'void MVKCommandEncoder::encodeBarrierWaits(MVKCommandUse use)'),
                  'barrierWait(kMVKBarrierStageVertex, _mtlRenderEncoder, MTLRenderStageVertex);',
                  'barrierWait(kMVKBarrierStageFragment, _mtlRenderEncoder, MTLRenderStageFragment);') and
          ordered(member(cmd, 'void MVKCommandEncoder::beginMetalRenderPass(MVKCommandUse cmdUse)'), 'renderCommandEncoderWithDescriptor', 'encodeBarrierWaits(cmdUse);') and
          ordered(member(cmd, 'void MVKCommandEncoder::endMetalRenderEncoding()'), 'encodeBarrierUpdates();', 'endMetalEncoding(_mtlRenderEncoder);'),
          'model: a render encoder waits at its begin (vertex, fragment) and updates at its end')
    compute = member(cmd, 'id<MTLComputeCommandEncoder> MVKCommandEncoder::getMTLComputeEncoder(MVKCommandUse cmdUse)')
    check('if (!_mtlComputeEncoder || shouldStartNewEncoder(_mtlComputeEncoderUse, cmdUse))' in compute and 'encodeBarrierWaits(cmdUse);' in compute,
          'model: dispatches share the open compute encoder')
    check(re.search(r'if \(!device->hasResidencySet\(\)\) return;.*\[encoder waitForFence:device->getFence\(\(MVKBarrierStage\)i, fenceIndex\)\];\s*'
                    r'\[encoder updateFence:device->getFence\(\(MVKBarrierStage\)i, 0\)\];', cmd, re.S) is not None,
          'MoltenVK: command buffers ordered whole (syncFences)')
    check('if (spDep.dstSubpass != dstSubpass || spDep.srcSubpass == spDep.dstSubpass) { continue; }' in files['GPUObjects/MVKRenderPass.mm'],
          'MoltenVK: a self-dependency sets no fence')
    datatypes = member(files['Vulkan/mvk_datatypes.mm'], 'uint64_t mvkBarrierStagesFromPipelineStageFlags(VkPipelineStageFlags2 flags)')
    check(all(token in datatypes for token in ('VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT', 'VK_PIPELINE_STAGE_2_DRAW_INDIRECT_BIT',
                                               'result |= 1 << kMVKBarrierStageCompute;', 'VK_PIPELINE_STAGE_2_TRANSFER_BIT')) and
          ordered(datatypes, 'VK_PIPELINE_STAGE_2_VERTEX_SHADER_BIT', 'kMVKBarrierStageVertex', 'VK_PIPELINE_STAGE_2_FRAGMENT_SHADER_BIT',
                  'kMVKBarrierStageFragment', 'VK_PIPELINE_STAGE_2_COMPUTE_SHADER_BIT', 'kMVKBarrierStageCompute'),
          'model: stage classes (mvkBarrierStagesFromPipelineStageFlags)')
    moltenvk = {p: hashlib.sha256((mvk / p).read_bytes()).hexdigest() for p in files}

inputs = ['build-utils/melonx/adapt_moltenvk_stage_ordering.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_moltenvk_stage_ordering_test.py', 'test/melonx_moltenvk_stage_ordering/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, fixtureChecks={v: reports[v]['checks'] for v in reports},
               finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core658Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               reports=reports, libraryBuild=library_build, moltenVkSourceChecked=moltenvk is not None, moltenVkSources=moltenvk or {},
               sdk=sdk, physicalDeviceTested=False, nativeCallsUsed=False, productionAssembliesBuilt=['Ryujinx.Library', 'Ryujinx.Graphics.Vulkan'],
               sourceBaseline=BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host fixture: the production barrier paths and decisions, replayed on a model of MoltenVK 1.4.2\'s '
                          'fences bound to its source; no GPU. Whether the white sky, black blocks and bands of Hogwarts Legacy '
                          'go, and the GPU cost of the switch barriers, are known only from a device run.')
out = ROOT / 'dist/melonx/moltenvk-stage-ordering-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
