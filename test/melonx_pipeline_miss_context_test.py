#!/usr/bin/env python3
"""Pipeline miss context (adapt_pipeline_miss_context) on the real prepared engine.

Usage: melonx_pipeline_miss_context_test.py <Core 639 prepared MeloNX tree>

Builds the production Vulkan backend (with GAL, Common, Shader, Spv) from the candidate (Core 639 preparation plus the
adapter) and checks statically that only the once-per-program warning text gains the count, that the count runs inside
TryGetGraphicsPipeline's lock on that miss only, and that no lookup or key code changed. No device.
Writes dist/melonx/pipeline-miss-context-checks.json.
"""
from pathlib import Path
import difflib, hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
# Core gate form: <control> --candidate-source <final preparation>; the control tree is not read (the exact Core 639
# control is rebuilt from the final preparation). Standalone form: <Core 639 prepared tree>.
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
# The Core 639 preparation, or the final preparation (prepare_embedded.py runs this adapter): its exact control.
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_pipeline_miss_context', _HOLD)
from adapt_pipeline_miss_context import apply, BASELINE

NAME = 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


check(hashlib.sha256((SOURCE / NAME).read_bytes()).hexdigest() == BASELINE[NAME], 'not the Core 639 preparation')
with tempfile.TemporaryDirectory(prefix='melonx-miss-context-') as temporary:
    work = Path(temporary).resolve()
    for name in ('Directory.Build.props', 'Directory.Packages.props', 'global.json', '.editorconfig'):
        if (SOURCE / name).exists():
            shutil.copyfile(SOURCE / name, work / name)
    for project in ('Ryujinx.Graphics.Vulkan', 'Ryujinx.Common', 'Ryujinx.Graphics.GAL', 'Ryujinx.Graphics.Shader', 'Spv.Generator'):
        shutil.copytree(SOURCE / 'src' / project, work / 'src' / project, ignore=shutil.ignore_patterns('bin', 'obj'))
    before = (work / NAME).read_text()
    apply(work)
    after = (work / NAME).read_text()
    result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=900,
                            env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1'), cwd=work)
    if result.returncode:
        print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'Vulkan assembly builds')
removed = [l[2:].strip() for l in difflib.ndiff(before.splitlines(), after.splitlines()) if l.startswith('- ')]
check(removed == ['DescribeInitialKeyDifference(ref key));'], 'only the warning line changes: ' + str(removed))
lookup = after[after.index('public bool TryGetGraphicsPipeline('):]
lookup = lookup[:lookup.index('public bool TryWaitForBackgroundGraphicsPipeline(')]
check(lookup.count('DescribeMissContext()') == 1 and lookup.index('lock (_pipelineCacheLock)') < lookup.index('DescribeMissContext()') and
      lookup.index('if (!CompilesInBackground && _firstBackgroundUse)') < lookup.index('DescribeMissContext()'),
      'count only on the once-per-program miss, under the lock')
inputs = ['build-utils/melonx/adapt_pipeline_miss_context.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_pipeline_miss_context_test.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core639Preparation', postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {}, sdk=sdk, physicalDeviceTested=False, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Diagnostics only; which case the two 640 misses are needs the next device log.')
out = ROOT / 'dist/melonx/pipeline-miss-context-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
