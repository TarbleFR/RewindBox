#!/usr/bin/env python3
"""In-pass read barrier ordering under MoltenVK 1.4.2 (adapt_moltenvk_barrier_ordering) on the real prepared engine.

Usage: melonx_moltenvk_barrier_ordering_test.py <prepared MeloNX tree>

The tree is prepare_embedded.py's output on 13700519 for Core 639 (the IPA 640 engine: Core 631 plus the PR #153 lot).
Control is the tree as prepared, candidate adds the adapter. In each, the production Vulkan backend (with GAL, Common,
Shader, Spv) is built as an executable with test/melonx_moltenvk_barrier_ordering/Program.cs, which runs the real
PipelineBase.TryDeferInPassReadBarrier: under the 640 configuration (Hogwarts policy, MoltenVK on a tile-based GPU
without Metal hazard tracking for argument buffers) the control defers the barrier and the candidate records it; the
MoltenVK 1.4.0 case, feedback loops, other titles and non-TBDR GPUs keep the delivered result in both. Static checks
bind the driver-version rule (MVK_VERSION 10400 or less) and its single log line. No device; no FPS claim.
Writes dist/melonx/moltenvk-barrier-ordering-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_moltenvk_barrier_ordering import apply, BASELINE, LAST_TRACKING_MOLTENVK

for name, expected in BASELINE.items():
    assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 639 preparation: ' + name
DOTNET = os.environ.get('DOTNET', 'dotnet')
PROJECTS = ['Ryujinx.Graphics.Vulkan', 'Ryujinx.Common', 'Ryujinx.Graphics.GAL', 'Ryujinx.Graphics.Shader', 'Spv.Generator']
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


reports = {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-barrier-ordering-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        for name in ('Directory.Build.props', 'Directory.Packages.props', 'global.json', '.editorconfig'):
            if (SOURCE / name).exists():
                (work).mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SOURCE / name, work / name)
        for project in PROJECTS:
            shutil.copytree(SOURCE / 'src' / project, work / 'src' / project, ignore=shutil.ignore_patterns('bin', 'obj'))
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            renderer = (work / 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs').read_text()
            rule = f'MoltenVkTracksArgumentBufferHazards = IsMoltenVk && properties.DriverVersion <= {LAST_TRACKING_MOLTENVK};'
            check(renderer.count(rule) == 1 and LAST_TRACKING_MOLTENVK == 10400, 'driver-version rule (MVK 1.4.0 = 10400)')
            check(renderer.index('GpuVersion = $"Vulkan v') < renderer.index(rule), 'rule must read the device properties')
            check(renderer.count('in-pass read barriers are recorded') == 1, 'one log line for the decision')
            pipeline = (work / 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs').read_text()
            check(pipeline.count('!Gd.MoltenVkTracksArgumentBufferHazards)') == 1, 'deferral gate')
            storage = (work / 'src/Ryujinx.Graphics.Vulkan/TextureStorage.cs').read_text()
            check(storage.count('TryDeferInPassReadBarrier(this, dstStageFlags)') == 1 and
                  storage.index('TryDeferInPassReadBarrier(this, dstStageFlags)') < storage.index('_gd.Barriers.QueueBarrier(barrier, this, _lastModificationStage, dstStageFlags)'),
                  'a barrier not deferred is queued as delivered')
        project = work / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'
        tree = ET.parse(project)
        group = ET.SubElement(tree.getroot(), 'PropertyGroup')
        for name, value in [('OutputType', 'Exe'), ('StartupObject', 'Program'), ('NuGetAudit', 'false'),
                            ('EnableNETAnalyzers', 'false'), ('TreatWarningsAsErrors', 'false')]:
            ET.SubElement(group, name).text = value
        tree.write(project)
        shutil.copyfile(ROOT / 'test/melonx_moltenvk_barrier_ordering/Program.cs', project.parent / 'Program.cs')
        for command in ([DOTNET, 'build', str(project), '-c', 'Release', '-nologo', '-m:1'],
                        [DOTNET, str(project.parent / 'bin/Release/net10.0/Ryujinx.Graphics.Vulkan.dll'), variant]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=work)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant]), flush=True)

check(reports['control']['deferred']['moltenvk142-hogwarts'] is True and
      reports['candidate']['deferred']['moltenvk142-hogwarts'] is False, 'MoltenVK 1.4.2 deferral not corrected')
others = [k for k in reports['control']['deferred'] if k != 'moltenvk142-hogwarts']
check(all(reports['control']['deferred'][k] == reports['candidate']['deferred'][k] for k in others), 'other cases changed')
inputs = ['build-utils/melonx/adapt_moltenvk_barrier_ordering.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_moltenvk_barrier_ordering_test.py', 'test/melonx_moltenvk_barrier_ordering/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, reports=reports, sdk=sdk, physicalDeviceTested=False, nativeCallsUsed=False,
               fullProductionVulkanAssembly=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host fixture of the deferral decision; the MoltenVK 1.4.2 GPU ordering and the stale frames '
                          'are not reproduced off device.')
out = ROOT / 'dist/melonx/moltenvk-barrier-ordering-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
