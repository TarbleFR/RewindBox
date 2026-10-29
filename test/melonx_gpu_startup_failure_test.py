#!/usr/bin/env python3
"""Run the real GPU startup, guest entry/exit and embedded shutdown boundaries.

The CPU engine, GPU backend, shader loader and scheduler services are controlled
boundaries. GpuContext initialization/disposal, ArmProcessContext, KThread's
entry/exit/termination, KProcess's termination loop and EmbeddedWindowLifetime
execute production code. No device execution or timing claim is made.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_gpu_startup_failure import apply, BASELINE

GPU = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
ARM = 'src/Ryujinx.HLE/HOS/ArmProcessContext.cs'
WINDOW = 'src/Ryujinx.Library/Window/WindowBase.cs'
THREAD = 'src/Ryujinx.HLE/HOS/Kernel/Threading/KThread.cs'
PROCESS = 'src/Ryujinx.HLE/HOS/Kernel/Process/KProcess.cs'
FLAGS = 'src/Ryujinx.HLE/HOS/Kernel/Threading/ThreadSchedState.cs'
FILES = [GPU, ARM, WINDOW, THREAD, PROCESS, FLAGS]
PRISTINE_GPU = 'e64798cc48550b7f8408d1fa8c432575618f11337a93b37defea8cec99e72e7b'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def block(text, start):
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


def member(text, signature):
    assert text.count(signature) == 1, (signature, text.count(signature))
    return block(text, text.index(signature))


reports, hashes, full_inputs, postimages = {}, {}, {}, {}
preparation_inputs = {}
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
with tempfile.TemporaryDirectory(prefix='melonx-gpu-startup-') as temporary:
    temporary = Path(temporary).resolve()
    baseline = temporary / 'baseline'
    if digest(SOURCE / GPU) == BASELINE[GPU]:
        preparation = 'accepted_exact_preceding_engine'
        for relative in FILES:
            target = baseline / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
    else:
        assert digest(SOURCE / GPU) == PRISTINE_GPU, 'Unknown GPU source baseline'
        preparation = 'prepared_full_preceding_engine_in_isolated_repository'
        # Keep prepare_embedded's receipts and copied sources entirely isolated.
        # Its only excluded adapter is this candidate, which is compared below.
        repo = temporary / 'repository'
        recipes = repo / 'build-utils/melonx'
        recipes.mkdir(parents=True)
        for path in (ROOT / 'build-utils/melonx').glob('*.py'):
            shutil.copyfile(path, recipes / path.name)
            preparation_inputs[str(path.relative_to(ROOT))] = digest(path)
        native = repo / 'native/melonx'
        native.mkdir(parents=True)
        for path in (ROOT / 'native/melonx').glob('*.cs'):
            shutil.copyfile(path, native / path.name)
            preparation_inputs[str(path.relative_to(ROOT))] = digest(path)
        shutil.copytree(SOURCE / 'src', baseline / 'src', ignore=shutil.ignore_patterns('bin', 'obj'))
        prepare = subprocess.run([sys.executable, '-c',
            'import sys; import prepare_embedded as p; '
            'p.adapt_gpu_startup_failure = lambda source: []; '
            'sys.argv = [p.__file__, sys.argv[1]]; p.main()', str(baseline)],
            cwd=recipes, capture_output=True, text=True, timeout=90)
        if prepare.returncode: print(prepare.stdout + prepare.stderr, flush=True)
        prepare.check_returncode()
    for relative, expected in BASELINE.items():
        assert digest(baseline / relative) == expected, relative
    prepared = {relative: digest(baseline / relative) for relative in FILES}

    for variant in ('control', 'candidate'):
        work = temporary / variant
        source = work / 'source'
        for relative in FILES:
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(baseline / relative, target)
        if variant == 'candidate':
            postimages = {str(p.relative_to(source)): digest(p) for p in apply(source)}
        full_inputs[variant] = {relative: digest(source / relative) for relative in FILES}
        hashes[variant] = {}

        def extract(relative, signatures):
            text = (source / relative).read_text()
            parts = [member(text, signature) for signature in signatures]
            hashes[variant][relative] = {
                signature.strip(): hashlib.sha256(part.encode()).hexdigest()
                for signature, part in zip(signatures, parts, strict=True)}
            return text, '\n\n'.join(parts)

        gpu_members = ['        public ' + ('bool' if variant == 'candidate' else 'void') + ' InitializeShaderCache(',
                       '        public ' + ('bool' if variant == 'candidate' else 'void') + ' WaitUntilGpuReady(',
                       '        public void RegisterProcess(', '        public void UnregisterProcess(',
                       '        private void ShaderCacheStateUpdate(', '        public void Dispose()']
        if variant == 'candidate': gpu_members += ['        public void CancelShaderCacheInitialization()']
        text, parts = extract(GPU, gpu_members)
        begin = text.index('        private readonly ManualResetEvent _gpuReadyEvent;')
        end = text.index('        /// <summary>\n        /// Creates a new instance', begin)
        fields = text[begin:end]
        hashes[variant][GPU]['startupFields'] = hashlib.sha256(fields.encode()).hexdigest()
        prefix = '''using System; using System.Collections.Generic; using System.Collections.Concurrent;
using System.Threading; using Ryujinx.Graphics.Gpu.Memory; using Ryujinx.Graphics.Gpu.Shader;
'''
        (work / 'GpuContext.cs').write_text(prefix + 'namespace Ryujinx.Graphics.Gpu { partial class GpuContext {\n' + fields + parts + '\n} }\n')
        shutil.copyfile(source / ARM, work / 'ArmProcessContext.cs')
        shutil.copyfile(source / FLAGS, work / 'ThreadSchedState.cs')
        text, parts = extract(THREAD, ['        private void ThreadStart()', '        public ThreadSchedState PrepareForTermination()',
            '        public void Terminate()', '        public void HandlePostSyscall()', '        public void Exit()',
            '        private bool ExitImpl()'])
        prefix = '''using System; using System.Threading; using Ryujinx.Cpu;
using Ryujinx.HLE.HOS.Kernel.Process; using Ryujinx.HLE.HOS.Kernel.Threading;
'''
        (work / 'KThread.cs').write_text(prefix + 'namespace Ryujinx.HLE.HOS.Kernel.Threading { partial class KThread {\n' + parts + '\n} }\n')
        text, parts = extract(PROCESS, ['        private void UnpauseAndTerminateAllThreadsExcept('])
        (work / 'KProcess.cs').write_text(prefix + 'namespace Ryujinx.HLE.HOS.Kernel.Process { partial class KProcess {\n' + parts + '\n} }\n')
        text, parts = extract(WINDOW, ['        public void Execute()'])
        # Preserve the real GPU callback prefix, while condition and flush/drain
        # suffix. Only its frame work is doubled; cancellation must never enter it.
        render = member(text, '        public void Render()')
        start = render.index('                Device.Gpu.SetGpuThread();')
        loop = render.index('                while (', start)
        body = block(render, loop)
        loop_header = body[:body.index('{')]
        end = loop + len(body)
        suffix = render[end:render.index('\n            });', end)]
        callback = render[start:loop] + loop_header + '{ Device.ProcessFrame(); }\n' + suffix
        hashes[variant][WINDOW]['gpuCallbackWithFrameBodyDoubled'] = hashlib.sha256(callback.encode()).hexdigest()
        (work / 'WindowBase.cs').write_text('using System; using Ryujinx.Graphics.GAL.Multithreading;\nnamespace Ryujinx.Library { partial class WindowBase {\n' +
            parts + '\n void RunGpuCallback() {\n' + callback + '\n} } }\n')
        shutil.copyfile(ROOT / 'native/melonx/EmbeddedWindowLifetime.cs', work / 'EmbeddedWindowLifetime.cs')
        for name in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(ROOT / 'test/melonx_gpu_startup_failure' / name, work / name)
        define = '<DefineConstants>GPU_STARTUP_ADAPTED</DefineConstants>' if variant == 'candidate' else ''
        (work / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0414;0162</NoWarn><NuGetAudit>false</NuGetAudit>{define}
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        environment = os.environ.copy()
        environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'],
            cwd=work, capture_output=True, text=True, timeout=120, env=environment)
        print(result.stdout, flush=True)
        if result.returncode: print(result.stderr, flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

inputs = ['build-utils/melonx/adapt_gpu_startup_failure.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_gpu_startup_failure_test.py', 'test/melonx_gpu_startup_failure/Program.cs',
          'test/melonx_gpu_startup_failure/Boundaries.cs', 'native/melonx/EmbeddedWindowLifetime.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False, productionMembersVerbatim=True,
    cpuEngineDoubled=True, schedulerServicesDoubled=True, shaderLoaderDoubled=True,
    nativeRendererDoubled=True, frameBodyDoubled=True, timingGate=False,
    inputs={p: digest(ROOT / p) for p in inputs}, preparation=preparation,
    preparationInputs=preparation_inputs, upstreamInputs={p: digest(SOURCE / p) for p in FILES},
    preparedBaselineInputs=prepared, productionInputs=full_inputs, productionMemberHashes=hashes,
    postimages=postimages)
output = ROOT / 'dist/melonx/gpu-startup-failure-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Production GPU startup failure, cancellation, kernel exit and shutdown checks passed.', flush=True)
