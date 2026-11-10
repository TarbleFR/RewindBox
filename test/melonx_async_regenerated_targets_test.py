#!/usr/bin/env python3
"""adapt_async_regenerated_targets on the final preparation, against the Core 687 Vulkan files as control.

Usage: melonx_async_regenerated_targets_test.py <control> --candidate-source <final preparation containing the adapter>
       melonx_async_regenerated_targets_test.py <Core 687 prepared MeloNX tree>

IPA 688 (Hogwarts Legacy, async shaders on): texture corruption. With async shaders a draw whose program compiles is
skipped unless VulkanRenderer.IsCriticalOffscreenTarget, which held only targets that never had a complete pass. For each
variant the production Vulkan assembly is built, and the real IsCriticalOffscreenTarget, FramebufferParams and
TextureStorage members (with the candidate's frame members) are extracted and run with doubles that make the render
thread's calls in PipelineBase's order (test/melonx_async_regenerated_targets/Program.cs). The candidate must skip only
into targets regenerated each frame (every attachment drawn in the previous frame, one cleared whole in this one) and
the presented image; a capture drawn once, an atlas cleared by scissor, a post-process target never cleared, a layered
target cleared on one layer and a target back after a frame away must wait. The control skips into all of them once
complete. PipelineBase's held-draw path, pass and clear notes are checked in source. No device; no pixel or FPS claim.
Writes dist/melonx/async-regenerated-targets-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_async_regenerated_targets', _HOLD)
import adapt_async_regenerated_targets as adapter  # noqa: E402

def _forward_matches(module_name, work, final_source, names, tmp):
    """The candidate plus the later adapters sharing its files (re-applied forward) is the final preparation."""
    import importlib as _importlib
    from melonx_adapter_control import later_sharing as _later_sharing
    forward = Path(tmp) / ('forward-' + module_name)
    later = _later_sharing(module_name)
    files = set(names).union(*(set(_importlib.import_module(n).BASELINE) for n in later)) if later else set(names)
    for name in files:
        (forward / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(work / name, forward / name)
    for n in later:
        _importlib.import_module(n).apply(forward)
    return {name: (forward / name).read_bytes() == (final_source / name).read_bytes() for name in names}

DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.index(signature)
    start = text.rindex('\n', 0, start) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def extract(tree):
    storage = (tree / adapter.STORAGE).read_text(encoding='utf-8-sig')
    framebuffer = (tree / adapter.FRAMEBUFFER).read_text(encoding='utf-8-sig')
    renderer = (tree / adapter.RENDERER).read_text(encoding='utf-8-sig')
    parts = {'STORAGE': '', 'FRAMEBUFFER': '', 'RENDERER': ''}
    if 'NoteAsyncPass' in storage:
        start = storage.index('        // RewindBox (adapt_async_regenerated_targets): the last frame')
        parts['STORAGE'] = storage[start:storage.index('\n', storage.index('return _asyncClearFrame == frame;')) + 1] + '        }\n'
    methods = ['public bool HasIncompleteAttachments(', 'public bool HasAttachment(']
    if 'IsRegeneratedEachFrame' in framebuffer:
        methods += ['public bool IsRegeneratedEachFrame(', 'public void NoteAsyncPass(', 'public bool ClearsWhole(']
    parts['FRAMEBUFFER'] = '\n'.join(member(framebuffer, m) for m in methods) + '\n'
    field = '        internal ulong AsyncFrame = 1;\n' if 'internal ulong AsyncFrame = 1;' in renderer else ''
    parts['RENDERER'] = field + member(renderer, 'internal bool IsCriticalOffscreenTarget(') + '\n'
    return parts


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 687 preparation: ' + name)

texts, reports = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-async-regenerated-targets-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = adapter.apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                # Later adapters editing these files (Core 691: adapt_pipeline_failure_identity, PipelineBase.cs) are re-applied forward.
                forward_ok = _forward_matches('adapt_async_regenerated_targets', work, FINAL_SOURCE, adapter.BASELINE, temporary)
                for name in adapter.BASELINE:
                    check(forward_ok[name], 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800,
                                env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Vulkan assembly builds')

        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        program = (ROOT / 'test/melonx_async_regenerated_targets/Program.cs').read_text()
        for key, value in extract(work).items():
            program = program.replace('//__' + key + '__\n', value)
        (fixture / 'Program.cs').write_text(program)
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><TreatWarningsAsErrors>false</TreatWarningsAsErrors>'
            '<NoWarn>CS0169;CS0414;CS0649;CS8632</NoWarn></PropertyGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant]), flush=True)

c, k = reports['control']['skips'], reports['candidate']['skips']
F, T = False, True
# The control skips into every complete target; the first frame draws with ready programs.
for name in ('onScreen', 'gbuffer', 'atlas', 'post', 'cleared', 'layered'):
    check(c[name] == [F] + [T] * 7, 'control skips into ' + name + ': ' + str(c[name]))
check(c['capture'] == [F, T] and c['gbufferAfterGap'] == [T, T, T], 'control skips into the capture and after a gap')
# The candidate skips only into regenerated targets and the presented image.
check(k['onScreen'] == [F] + [T] * 7, 'candidate: the presented image stays skippable')
check(k['gbuffer'] == [F] + [T] * 7 and k['cleared'] == [F] + [T] * 7, 'candidate: per-frame cleared targets stay skippable')
check(k['capture'] == [F, F], 'candidate: a capture drawn once waits')
check(k['atlas'] == [F] * 8, 'candidate: an atlas cleared by scissor waits')
check(k['post'] == [F] * 8, 'candidate: a target never cleared waits')
check(k['layered'] == [F] * 8, 'candidate: a layered target cleared on one layer waits')
check(k['gbufferAfterGap'] == [F, T, T], 'candidate: a target back after a frame away waits once')
check(reports['control']['beforePresentation'] is reports['candidate']['beforePresentation'] is False, 'nothing held before presentation')

# Source: PipelineBase and Window in the candidate.
pc, pk = texts['control'][adapter.PIPELINE], texts['candidate'][adapter.PIPELINE]
prepare = member(pk, 'private bool PrepareGraphicsDraw(')
check(prepare.index('bool held = requiresCompletePipeline &&') < prepare.index('if (!held)') and
      prepare.index('_program.WaitForShaderModules(Timeout.Infinite) &&') < prepare.index('UpdateProgramStagesIfReady(blocking: false);\n\n                if (requiresCompletePipeline)'),
      'held draw: the same wait and readiness test, timed')
check(prepare.count('_renderPassHadSkippedDraw = true;') == member(pc, 'private bool PrepareGraphicsDraw(').count('_renderPassHadSkippedDraw = true;'),
      'no skip added')
check(member(pk, 'private unsafe void BeginRenderPass(').count('FramebufferParams.NoteAsyncPass(Gd.AsyncFrame);') == 1, 'passes noted')
check(member(pk, 'public unsafe void ClearRenderTargetColor(').count('NoteAsyncFullClear(Gd.AsyncFrame)') == 1 and
      member(pk, 'public unsafe void ClearRenderTargetDepthStencil(').count('(flags & ImageAspectFlags.DepthBit) != 0 && FramebufferParams.ClearsWhole') == 1,
      'whole clears noted, depth aspect for depth')
check('"; async draws held for their program " + AsyncHeld' in pk and 'AsyncHeld = AsyncHeldTicks = 0;' in pk, 'held draws logged')
check(texts['candidate'][adapter.WINDOW].count('_gd.AsyncFrame++;') == 1, 'frames counted at Present')
for method in ('private bool CanSkipForBackgroundCompile(', 'private bool UpdateProgramStagesIfReady(', 'public void EndRenderPass('):
    check(member(pc, method) == member(pk, method), 'unchanged: ' + method)

inputs = ['build-utils/melonx/adapt_async_regenerated_targets.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_async_regenerated_targets_test.py', 'test/melonx_async_regenerated_targets/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core687Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionVulkanAssemblyBuilt=True, sourceBaseline=adapter.BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Doubles around the real members; whether the corruption is gone and how often draws wait is known only '
                          'after a device run ("async draws held for their program" in the Vulkan render stages line).')
out = ROOT / 'dist/melonx/async-regenerated-targets-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
