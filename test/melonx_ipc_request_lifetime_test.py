#!/usr/bin/env python3
"""Run real IPC request storage, descriptor table and pool with memory doubles.

The entire production request, pool and descriptor table execute. Server
cleanup call sites are bound byte-for-byte and their exact return expression
executes; the large IPC transport and scheduler are not simulated or claimed.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_ipc_request_lifetime import apply

FILES = ['src/Ryujinx.HLE/HOS/Kernel/Ipc/KSessionRequest.cs',
         'src/Ryujinx.HLE/HOS/Kernel/Ipc/KServerSession.cs']
SUPPORT = ['src/Ryujinx.Common/Pools/ObjectPool.cs',
           'src/Ryujinx.Common/Utilities/BitUtils.cs',
           'src/Ryujinx.Memory/MemoryPermission.cs',
           'src/Ryujinx.HLE/HOS/Kernel/Ipc/KBufferDescriptorTable.cs',
           'src/Ryujinx.HLE/HOS/Kernel/Ipc/KBufferDescriptor.cs',
           'src/Ryujinx.HLE/HOS/Kernel/Memory/MemoryState.cs',
           'src/Ryujinx.HLE/HOS/Kernel/Memory/MemoryAttribute.cs',
           'src/Ryujinx.HLE/HOS/Kernel/Memory/KMemoryPermission.cs',
           *['src/Ryujinx.Horizon.Common/' + name for name in [
               'Result.cs', 'KernelResult.cs', 'ResultNames.cs',
               'InvalidResultException.cs', 'ThreadTerminatedException.cs']]]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == pin['revision']
assert not subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--', *FILES, *SUPPORT], text=True).strip()
reports, compiled, postimages = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-ipc-request-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary) / variant
        source = work / 'source'
        for relative in FILES:
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            apply(source)
        postimages[variant] = {name: digest(source / name) for name in FILES}
        server = (source / FILES[1]).read_text()
        original = (SOURCE / FILES[1]).read_text()
        expression = ('RequestPool.Release(request.ClearReferences());' if variant == 'candidate'
                      else 'RequestPool.Release(request);')
        assert server.count(expression) == 5
        # No server statement, ordering or completion algorithm may change.
        assert server.replace(expression, 'RequestPool.Release(request);') == original
        generated = '''using Ryujinx.Common;
namespace Ryujinx.HLE.HOS.Kernel.Ipc {
class ReturnBoundary {
public readonly ObjectPool<KSessionRequest> RequestPool = new(() => new KSessionRequest());
public void Return(KSessionRequest request) { ''' + expression + ''' }
}}
'''
        (work / 'ReturnBoundary.cs').write_text(generated)
        shutil.copyfile(source / FILES[0], work / 'KSessionRequest.cs')
        for relative in SUPPORT:
            shutil.copyfile(SOURCE / relative, work / Path(relative).name)
        shutil.copyfile(ROOT / 'test/melonx_ipc_request_lifetime/Program.cs', work / 'Program.cs')
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit>
</PropertyGroup><ItemGroup><Compile Remove="source/**/*.cs" /></ItemGroup></Project>''')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        result = subprocess.run(['dotnet', 'run', '--project', str(work), '-c', 'Release', '-v', 'q', '--', variant], cwd=work, capture_output=True, text=True, timeout=180)
        if result.returncode:
            print(result.stdout + result.stderr)
            result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        compiled[variant] = {'returnBoundarySha256': digest(work / 'ReturnBoundary.cs'),
                             'returnExpression': expression,
                             'programSha256': digest(work / 'Program.cs')}
assert reports['control']['retainedParticipants'] == 3
assert reports['candidate']['retainedParticipants'] == 0
assert reports['control']['descriptorDigest'] == reports['candidate']['descriptorDigest']
report = dict(result='passed', upstreamRevision=pin['revision'], reports=reports,
              physicalDeviceTested=False, ipcTransportExecuted=False,
              unchangedServerReturnSites=5, compiledInputs=compiled, postimages=postimages,
              upstreamInputs={path: digest(SOURCE / path) for path in [*FILES, *SUPPORT]},
              inputs={str(path.relative_to(ROOT)): digest(path) for path in [
                  ROOT / 'build-utils/melonx/adapt_ipc_request_lifetime.py',
                  Path(__file__), ROOT / 'test/melonx_ipc_request_lifetime/Program.cs']})
output = ROOT / 'dist/melonx/ipc-request-lifetime-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
