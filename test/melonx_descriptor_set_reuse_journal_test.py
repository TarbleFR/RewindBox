#!/usr/bin/env python3
"""The descriptor set reuse measurement (adapt_descriptor_set_reuse_journal): nothing the engine writes or binds changes,
and the journal counts what a reuse would have spared, real engine code.

Usage: melonx_descriptor_set_reuse_journal_test.py <final preparation containing the adapter>
       melonx_descriptor_set_reuse_journal_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the final preparation with the adapter reversed (melonx_adapter_control); candidate is the adapter applied to
it (only its replacements, each once, fail closed; the final preparation reproduced byte for byte). Static checks: the
file has the control's binds, set lists and template commits, in the same order; the reasons the measurement is exact
(each set of a layout's list handed out once per submission, the resources referenced by the command buffer, the
command buffer change signals, only the main pipeline's updater with the hazard list, every bind in this file). The
candidate's production Ryujinx.Graphics.Vulkan assembly builds.

Executed (test/melonx_descriptor_set_reuse_journal): the production DescriptorSetUpdater members, in the candidate with the
measurement's members and journal, with Vulkan boundaries that hash every write (set, template, bytes) and bind (bind
point, layout, index, set) in call order, keep the set bound per (bind point, set index) with its layout and the bytes
each set holds; the descriptors every draw and dispatch reads are decoded, checked against what was bound and hashed.
Streams: scripted steps, a stream shaped like the IPA 822 Hogwarts Legacy window, the same with no repeated descriptors,
array policy on and off, the candidate measuring every command buffer start (1) and one in eight (8, as delivered).
Control and candidate make the same calls with the same bytes in the same order, read the same descriptors, take,
write and bind the same sets and reference the same resources. Measuring every start, the counts are those the
withdrawn reuse adapter (adapt_descriptor_set_reuse, 23 Nov) kept and bound again on the same streams; one in eight
gives about an eighth. A variant that writes without copying the scratch must fail. Every journal line survives the
core journal's redaction (EmbeddedLaunchDiagnostics.Safe). Timing: control, candidate 8 and candidate 1 alternated.
No device, no MoltenVK. Writes dist/melonx/descriptor-set-reuse-journal-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, statistics, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_descriptor_set_reuse_journal', _HOLD)
import adapt_descriptor_set_reuse_journal as adapter  # noqa: E402
from adapt_descriptor_set_reuse_journal import (apply, BASELINE, UPDATER, TAG, MEMBERS_BEGIN, MEMBERS_END,  # noqa: E402
                                                JOURNAL_BEGIN, JOURNAL_END)
from adapt_descriptor_updates import method  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
FIXTURE = ROOT / 'test/melonx_descriptor_set_reuse_journal'
DOTNET = os.environ.get('DOTNET', 'dotnet')
import importlib as _importlib  # noqa: E402
import melonx_adapter_control as _control  # noqa: E402
ADAPTED_FILES = {path for name in _control.ORDER for path in _importlib.import_module(name).BASELINE}
FILES = ['src/Ryujinx.Graphics.Vulkan/DescriptorSetTemplateUpdater.cs', 'src/Ryujinx.Graphics.Vulkan/NativeArray.cs',
         'src/Ryujinx.Graphics.Vulkan/BitMapStruct.cs', 'src/Ryujinx.Graphics.Vulkan/ResourceBindingSegment.cs',
         'src/Ryujinx.Graphics.Vulkan/Constants.cs', 'src/Ryujinx.Common/Memory/IArray.cs',
         'src/Ryujinx.Common/Memory/StructArrayHelpers.cs', 'src/Ryujinx.Common/Utilities/BitUtils.cs',
         'src/Ryujinx.Graphics.GAL/BufferAssignment.cs', 'src/Ryujinx.Graphics.GAL/BufferRange.cs',
         'src/Ryujinx.Graphics.GAL/BufferHandle.cs', 'src/Ryujinx.Graphics.GAL/ResourceLayout.cs',
         'src/Ryujinx.Graphics.Shader/ShaderStage.cs']
SIGNATURES = [
    '        private record struct BufferRef', '        private record struct TextureRef', '        private record struct ImageRef',
    '        internal enum DirtyFlags', '        private static bool BindingOverlaps(', '        internal void Rebind(',
    '        public void AdvancePdSequence(', '        public void CopyFrom(', '        public void SetProgram(',
    '        private static bool SameBindings(', '        private static bool SameSegments(',
    '        internal static DirtyFlags BufferViewSets(',
    '        public void SetImage(CommandBufferScoped cbs, ShaderStage stage, int binding, ITexture image)',
    '        public void SetStorageBuffers(CommandBuffer commandBuffer, ReadOnlySpan<BufferAssignment> buffers)',
    '        public void SetTextureAndSampler(\n', '        public void SetTextureArraySeparate(',
    '        private static ref ArrayRef<T> GetArrayRef<T>(', '        public void SetUniformBuffers(',
    '        private static Span<T> TemplateScratch<T>(', '        private void SignalDirty(',
    '        public void UpdateAndBindDescriptorSets(', '        private static bool UpdateBuffer(',
    '        private void UpdateAndBind(CommandBufferScoped cbs, ShaderCollection program, int setIndex, PipelineBindPoint pbp)',
    '        private void UpdateAndBindUniformBufferPd(', '        private void Initialize(CommandBufferScoped cbs, int setIndex, DescriptorSetCollection dsc)',
    '        private void BindExtraSets(', '        public void SignalCommandBufferChange(', '        public void ForceTextureDirty(',
    '        public void ForceImageDirty(', '        private static void SwapBuffer(', '        public void SwapBuffer(',
]
# What the withdrawn reuse adapter (adapt_descriptor_set_reuse, 23 Nov, same fixture streams) kept bound and bound again,
# per set (uniform, storage, texture, image), its descriptors not written and the array sets not bound again.
REUSE = {'scripted': ([5, 3, 5, 1], [2, 2, 3, 0], 59, 3), 'log-shaped': ([23, 32, 340, 9], [374, 1142, 16899, 1162], 470053, 53),
         'no-repeat': ([0, 0, 0, 0], [0, 0, 0, 0], 0, 36)}
# Sensitivity: the template data not given the scratch's bytes (a write that is not the control's) must be detected.
NO_COPY = [('                written.Push<byte>(_reusePending.AsSpan(0, template.Size));\n', '')]
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


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def between(text, begin, end):
    check(text.count(begin) == 1 and text.count(end) == 1, 'one block: ' + begin.strip())
    return text[text.index(begin):text.index(end) + len(end)]


check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the adapter\'s preparation: ' + name)

# Why the measurement follows what a reuse would see, in the preparation.
entry = read(SOURCE, VULKAN + 'PipelineLayoutCacheEntry.cs')
update_index = member(entry, 'public void UpdateCommandBufferIndex(int commandBufferIndex)')
check('if (_dsLastCbIndex != commandBufferIndex || _dsLastSubmissionCount != submissionCount)' in update_index and
      'Array.Clear(_dsCacheCursor);' in update_index, 'a layout\'s set lists restart only at another command buffer or submission')
check('int index = _dsCacheCursor[setIndex]++;' in member(entry, 'public Auto<DescriptorSetCollection> GetNewDescriptorSetCollection('),
      'each set of a list is handed out once per submission')
auto = read(SOURCE, VULKAN + 'Auto.cs')
check('AddCommandBufferDependencies(cbs);' in member(auto, 'public T Get(CommandBufferScoped cbs)') and
      'return mirror.Get(cbs);' in member(auto, 'public T GetMirrorable('), 'a resource resolved into a descriptor is referenced by the command buffer')
full = read(SOURCE, VULKAN + 'PipelineFull.cs')
base = read(SOURCE, VULKAN + 'PipelineBase.cs')
helper = read(SOURCE, VULKAN + 'PipelineHelperShader.cs')
check('Restore();' in member(full, 'private void SubmitCommands()') and 'SignalCommandBufferChange();' in member(full, 'public void Restore()') and
      '_descriptorSetUpdater.SignalCommandBufferChange();' in member(base, 'protected void SignalCommandBufferChange()'),
      'the main pipeline signals a command buffer change after each submission')
check('SignalCommandBufferChange();' in member(helper, 'public void SetCommandBuffer(CommandBufferScoped cbs)') and
      'gd.PipelineInternal.Restore();' in member(helper, 'public void Finish(VulkanRenderer gd, CommandBufferScoped cbs)'),
      'a helper shader on the main command buffer restores the main pipeline')
check('IsMainPipeline = true;' in full and '_descriptorSetUpdater.Initialize(IsMainPipeline);' in base and
      'FeedbackLoopHazards = [];' in member(read(SOURCE, UPDATER), 'public void Initialize(bool isMainPipeline)'),
      'only the main pipeline\'s updater has the hazard list')
others = sorted(p.relative_to(SOURCE / VULKAN).as_posix() for p in (SOURCE / VULKAN).rglob('*.cs')
                if 'CmdBindDescriptorSets' in p.read_text(errors='ignore'))
check(others == ['DescriptorSetUpdater.cs'], 'every descriptor set bind is in DescriptorSetUpdater: ' + str(others))
# The engine's warnings reach the core journal through EmbeddedLaunchDiagnostics.RecordEngine, which applies Safe.
runtime = read(SOURCE, 'src/Ryujinx.Library/EmbeddedRuntime.cs')
diagnostics = read(SOURCE, 'src/Ryujinx.Common/EmbeddedLaunchDiagnostics.cs')
check('EmbeddedLaunchDiagnostics.RecordEngine(entry.Level == LogLevel.Error, entry.Message);' in runtime and
      'string safeDetail = Safe(detail);' in member(diagnostics, 'public static void Record(string stage, string status'),
      'an engine warning is journaled through Safe')
safe_source = (ROOT / 'native/melonx/EmbeddedLaunchDiagnostics.cs').read_text()
safe_rules = re.findall(r'value = Regex\.Replace\(value, @"([^"]+)", "(\[redacted[^"]*\])"\);', safe_source)
check(len(safe_rules) >= 2 and member(safe_source, 'public static string Safe(string value)') ==
      member(diagnostics, 'public static string Safe(string value)'), 'the journal\'s redaction rules, as the engine has them: ' + str(len(safe_rules)))


def survives(detail):
    out = detail
    for pattern, replacement in safe_rules:
        out = re.sub(pattern.replace('(?i)', '').replace('(?im)', ''), replacement, out,
                     flags=(re.I | re.M) if '(?im)' in pattern else re.I if '(?i)' in pattern else 0)
    return out == detail


check(not survives('reuseWritten=1 (kept 0)'), 'the redaction check sees a "name=" detail as redacted')

replacements, reports = [], {}
original_once = adapter.once
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
with tempfile.TemporaryDirectory(prefix='melonx-descriptor-set-reuse-journal-') as temporary:
    temporary = Path(temporary).resolve()
    candidate_tree = temporary / 'candidate-tree'
    shutil.copytree(SOURCE, candidate_tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(candidate_tree, ROOT)

    def recording_once(path, old, new):
        replacements.append((path.relative_to(candidate_tree).as_posix(), old, new))
        original_once(path, old, new)

    adapter.once = recording_once
    try:
        changed = apply(candidate_tree)
    finally:
        adapter.once = original_once
    check(sorted(p.relative_to(candidate_tree).as_posix() for p in changed) == sorted(BASELINE), 'adapter changed other files')
    duplicate = temporary / 'duplicate'
    (duplicate / UPDATER).parent.mkdir(parents=True)
    shutil.copyfile(candidate_tree / UPDATER, duplicate / UPDATER)
    try:
        apply(duplicate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    undone = read(candidate_tree, UPDATER)
    for path, old, new in reversed(replacements):
        check(undone.count(new) == 1, 'each replacement once: ' + new[:60])
        undone = undone.replace(new, old)
    control_text = read(SOURCE, UPDATER)
    check(undone == control_text, 'the file is the preparation but the adapter\'s replacements')
    candidate_text = read(candidate_tree, UPDATER)
    check(candidate_text.count(TAG) >= 12, 'commented')
    if UPDATER not in files_edited_later('adapt_descriptor_set_reuse_journal'):
        check((candidate_tree / UPDATER).read_bytes() == (FINAL_SOURCE / UPDATER).read_bytes(), 'final preparation is the adapter')
    # Measurement only: the same binds, set takes, template commits and writes, in the same order.
    for call in ('_gd.Api.CmdBindDescriptorSets(', 'GetNewDescriptorSetCollection(', '_templateUpdater.Commit(',
                 'CommitPushDescriptor(', 'UpdateDescriptorSetWithTemplate(', 'InitializeBuffers(', '.Get(cbs'):
        check(candidate_text.count(call) == control_text.count(call), 'the control\'s calls: ' + call)
    template_path = member(candidate_text, 'private void UpdateAndBind(CommandBufferScoped cbs, ShaderCollection program, int setIndex, PipelineBindPoint pbp)')
    i = template_path.index
    check(i('program.GetNewDescriptorSetCollection(') < i('Initialize(cbs, setIndex, dsc);') < i('foreach (ResourceBindingSegment segment in bindingSegments)') <
          i('MeasureReuse(') < i('written.Push<byte>(_reusePending.AsSpan(0, template.Size));') < i('_templateUpdater.Commit(') <
          i('_gd.Api.CmdBindDescriptorSets(') < i('NoteSetWritten('), 'the control\'s order; measured between the resolution and the write')
    members_text = between(candidate_text, MEMBERS_BEGIN, MEMBERS_END)
    check('CmdBindDescriptorSets' not in members_text and 'UpdateDescriptorSet' not in members_text and '.Get(' not in members_text and
          '_dirty' not in members_text, 'the measurement members call no Vulkan function, reference nothing, mark nothing dirty')
    texts = {p.relative_to(candidate_tree).as_posix(): p.read_text(errors='ignore') for p in (candidate_tree / 'src').rglob('*.cs')}
    check(sorted(n for n, t in texts.items() if 'DescriptorReuseJournal' in t) == [UPDATER], 'the change stays in its file')

    result = subprocess.run([DOTNET, 'build', str(candidate_tree / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400,
                            env=dict(environment, DOTNET_TieredCompilation='1'), cwd=candidate_tree)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')

    no_copy = candidate_text
    for old, new in NO_COPY:
        check(no_copy.count(old) == 1, 'sensitivity edit applies once')
        no_copy = no_copy.replace(old, new)
    variants = {'control': control_text, 'candidate': candidate_text, 'noCopy': no_copy}
    member_hashes, projects = {}, {}
    for variant, text in variants.items():
        members = [method(text, signature) for signature in SIGNATURES]
        journal = ''
        if variant != 'control':
            members.append(between(text, MEMBERS_BEGIN, MEMBERS_END))
            journal = between(text, JOURNAL_BEGIN, JOURNAL_END)
        member_hashes[variant] = hashlib.sha256('\n'.join(members + [journal]).encode()).hexdigest()
        work = temporary / variant
        work.mkdir()
        (work / 'Production.cs').write_text('''using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Silk.NET.Vulkan;
using Buffer = Silk.NET.Vulkan.Buffer;
namespace Ryujinx.Graphics.Vulkan { partial class DescriptorSetUpdater {
''' + '\n\n'.join(members) + '\n}\n' + journal + '}\n')
        tree = SOURCE if variant == 'control' else candidate_tree
        for relative in FILES:
            shutil.copyfile(tree / relative, work / Path(relative).name)
        for name in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(FIXTURE / name, work / name)
        defines = '' if variant == 'control' else '<DefineConstants>CANDIDATE</DefineConstants>'
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0162;0169;0414;8500;0219</NoWarn>
<NuGetAudit>false</NuGetAudit><ServerGarbageCollection>false</ServerGarbageCollection>''' + defines + '''</PropertyGroup>
<ItemGroup><PackageReference Include="Silk.NET.Vulkan" Version="2.22.0" /></ItemGroup></Project>''')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        result = subprocess.run([DOTNET, 'build', str(work / 'Probe.csproj'), '-c', 'Release', '-nologo'], cwd=work,
                                capture_output=True, text=True, timeout=900, env=environment)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, variant + ': fixture builds')
        projects[variant] = work / 'bin/Release/net10.0/Probe.dll'

    def run(variant, *arguments):
        return subprocess.run([DOTNET, str(projects[variant]), *arguments], capture_output=True, text=True, timeout=1800, env=environment)

    runs = [('control', '0')] + [('candidate', s) for s in ('1', '8')]
    for variant, sample in runs:
        for policy in ('on', 'off'):
            result = run(variant, 'verify', policy, sample)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            check(result.returncode == 0, f'{variant} {sample} ({policy}): every draw and dispatch read the descriptors bound')
            reports[(variant, sample, policy)] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
            summary = {r['name']: {k: r[k] for k in ('ops', 'setWrites', 'binds', 'callHash')} | {
                'measured': {k: r['journal'].get(k) for k in ('sampledStarts', 'starts', 'wouldKeep', 'wouldBindAgain', 'descriptorsSpared')}}
                for r in reports[(variant, sample, policy)]['results']}
            print(variant, sample, policy, json.dumps(summary), flush=True)
    result = run('noCopy', 'verify', 'on', '1')
    failure = result.stdout + result.stderr
    check(result.returncode != 0 and 'expected' in failure, 'sensitivity: a write without the scratch\'s bytes is detected: ' + failure[-400:])
    sensitivity = next(line.strip() for line in failure.splitlines() if 'InvalidOperationException' in line)[:300]
    timings = {'control': {}, 'candidate8': {}, 'candidate1': {}}
    order = [('control', '0'), ('candidate8', '8'), ('candidate1', '1')]
    for round_ in range(4):
        for name, sample in (order if round_ % 2 == 0 else list(reversed(order))):
            result = run('control' if name == 'control' else 'candidate', 'time', 'on', sample, '3')
            check(result.returncode == 0, name + ': timing run')
            report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
            for stream, values in report['timings'].items():
                timings[name].setdefault(stream, []).extend(values)
    print('timings', json.dumps(timings), flush=True)
    result = run('candidate', 'time-samples', 'on', '0', '6')
    check(result.returncode == 0, 'in-process sampling timing run')
    least = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))['least']
    print('least', json.dumps(least), flush=True)

# The control's calls, bytes and order; the same descriptors read.
compared = {}
journal_lines = []
for policy in ('on', 'off'):
    c = reports[('control', '0', policy)]
    for sample in ('1', '8'):
        k = reports[('candidate', sample, policy)]
        check([s for s in c['steps']] == [s for s in k['steps']], f'sample {sample} ({policy}): the scripted steps write and bind as the control')
        for rc, rk in zip(c['results'], k['results'], strict=True):
            name = rc['name']
            for key in ('callHash', 'descriptorHash', 'observations', 'ops', 'programSets', 'setWrites', 'writesBySet', 'descriptorsWritten',
                        'binds', 'setsTaken', 'setsAllocated', 'resourceGets', 'arraySetLookups', 'renderDetail'):
                check(rc[key] == rk[key], f'{name} sample {sample} ({policy}): {key} as the control')
            journal = rk['journal']
            journal_lines += journal['lines']
            written = sum(journal['written'])
            check(written <= rk['setWrites'] and (journal['sampledStarts'] >= 1 and written >= 1 or (name == 'scripted' and sample == '8')),
                  f'{name} sample {sample}: measured: {journal}')
            if sample == '1':
                check(journal['sampledStarts'] == journal['starts'], f'{name}: every start measured')
                keep, again, spared, arrays = REUSE[name]
                check((journal['wouldKeep'], journal['wouldBindAgain'], journal['descriptorsSpared'], journal['arraySetsWouldKeep']) ==
                      (keep, again, spared, arrays), f'{name} ({policy}): what the reuse adapter spared on this stream: {journal}')
                check(journal['draw'][0] > 0 and journal['compute'][0] > 0 or name == 'scripted', f'{name}: draw and compute updates timed')
            compared[f'{name}/{sample}/{policy}'] = dict(
                ops=rc['ops'], draws=rc['draws'], dispatches=rc['dispatches'], setWrites=rc['setWrites'], binds=rc['binds'],
                callHash=rc['callHash'], measured={x: journal[x] for x in ('starts', 'sampledStarts', 'written', 'wouldKeep', 'wouldBindAgain',
                                                                          'descriptorsSpared', 'descriptorsWritten', 'arraySetsWouldKeep',
                                                                          'arraySetBinds', 'draw', 'compute')})
log1, log8 = compared['log-shaped/1/on']['measured'], compared['log-shaped/8/on']['measured']
rate = lambda m: (sum(m['wouldKeep']) + sum(m['wouldBindAgain'])) / sum(m['written'])
check(7 <= log1['starts'] / log8['sampledStarts'] <= 9 and 0.5 <= rate(log8) / rate(log1) <= 2,
      'one start in eight measured, the same rate within a factor of two: ' + str((log8['sampledStarts'], log1['starts'], rate(log8), rate(log1))))
check(sum(compared['no-repeat/1/on']['measured']['wouldKeep']) + sum(compared['no-repeat/1/on']['measured']['wouldBindAgain']) == 0,
      'no repeated descriptors: nothing would be spared')
check(journal_lines and all(survives(line) for line in journal_lines) and
      all(line.startswith('Vulkan descriptor set reuse measured (not applied) over ') for line in journal_lines),
      'every journal line survives the redaction: ' + journal_lines[0])


def median(values):
    return round(statistics.median(values), 2)


timing = {stream: {name: median(timings[name][stream]) for name in timings} for stream in timings['control']}
for stream, value in timing.items():
    value['candidate8OverControl'] = round(value['candidate8'] / value['control'], 3)
    value['candidate1OverControl'] = round(value['candidate1'] / value['control'], 3)
    value['runs'] = {name: timings[name][stream] for name in timings}
check(all(0 < value['candidate8OverControl'] < 2 for value in timing.values()), 'host time measured: ' + str(timing))
sampling_cost = {stream: dict(off=least[stream + '/0'], one_in_8=least[stream + '/8'], every=least[stream + '/1'],
                              one_in_8_over_off=round(least[stream + '/8'] / least[stream + '/0'], 3),
                              every_over_off=round(least[stream + '/1'] / least[stream + '/0'], 3)) for stream in ('log-shaped', 'no-repeat')}
check(all(v['off'] > 0 for v in sampling_cost.values()), 'in-process sampling cost measured: ' + str(sampling_cost))

inputs = ['build-utils/melonx/adapt_descriptor_set_reuse_journal.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/adapt_descriptor_updates.py', 'test/melonx_descriptor_set_reuse_journal_test.py', 'test/melonx_adapter_control.py',
          'test/melonx_descriptor_set_reuse_journal/Program.cs', 'test/melonx_descriptor_set_reuse_journal/Boundaries.cs',
          'native/melonx/EmbeddedLaunchDiagnostics.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE},
               behaviourIdentical=True, comparison=compared, journalLine=journal_lines[0], journalLineSurvivesRedaction=True,
               journalPath='Ryujinx Logger warning (stderr relay; core journal engineWarning through EmbeddedLaunchDiagnostics.Safe)',
               sampling='one command buffer start in 8 measured (DescriptorSetUpdater.ReuseSampleEvery)', sensitivity=sensitivity,
               fixtureChecks={f'{v}/{s}/{p}': reports[(v, s, p)]['checks'] for v, s, p in reports},
               hostTiming=timing, samplingCostInProcess=sampling_cost, productionMemberHashes=member_hashes, sdk=sdk, physicalDeviceTested=False,
               productionVulkanAssemblyBuilt=True, productionUpdaterMembersExecuted=True, vulkanBoundariesDoubled=True,
               sourceBaseline=BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               # Files no adapter edits are upstream inputs (equal to every control); a file an earlier adapter edits
               # (BitMapStruct.cs, adapt_buffer_mirror_windows) is bound as the final preparation's.
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES if p not in ADAPTED_FILES},
               finalInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in FILES if p in ADAPTED_FILES},
               limitation='Production updater members with Vulkan boundaries doubled; the host time is the engine\'s side only. '
                          'The repeat rate on a device is what the journal line of a device run reports.')
out = ROOT / 'dist/melonx/descriptor-set-reuse-journal-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, line=journal_lines[0], logShaped1=log1, logShaped8=log8, hostTiming=timing,
                     samplingCost=sampling_cost)))
