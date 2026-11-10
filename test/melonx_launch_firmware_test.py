#!/usr/bin/env python3
"""Prove the launch preflight scans firmware once without caching its version.

Compile the actual preflight, ContentManager.LoadEntries and version reader,
ContentPath, LocationEntry and SystemVersion against the pinned LibHac package.
Only NCA decryption and the surrounding emulator services are doubled; the
directory scans, file opens, LibHac local filesystem and version parsing are real.
No personal firmware, key material or game data is used.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
PACKAGE = Path(sys.argv[2]).resolve()
PACKAGE_SHA = 'b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9'
assert hashlib.sha256(PACKAGE.read_bytes()).hexdigest() == PACKAGE_SHA, PACKAGE
FILES = {
    'src/Ryujinx.HLE/FileSystem/ContentPath.cs': 'aa0bebb29375a1b31b98973852683d18961e111eb393a19eb0bd7be136927f0c',
    'src/Ryujinx.HLE/FileSystem/SystemVersion.cs': '8841df9e48de7522aaa6fc4070a975e2e162684eb8ad98268f82659e4cc04dba',
    'src/Ryujinx.HLE/FileSystem/LocationEntry.cs': '3d4603fa97b32db3cce0c8cf96d270716715f0740c2cba0111938adf956c00fe',
}
MEMBERS = {
    'public void LoadEntries(Switch device = null)': ('src/Ryujinx.HLE/FileSystem/ContentManager.cs', 'e7df2b5ef95ee508994a1246e8d21115604578248a015cca99a02927bf23eea8'),
    'public SystemVersion GetCurrentFirmwareVersion()': ('src/Ryujinx.HLE/FileSystem/ContentManager.cs', 'b2c10c0aa9ab035eb53636ffff0919e8243b52a12dfc9f8e40a04ef2bea050ed'),
    'public static string ReadInlinedAsciiString(BinaryReader reader, int maxSize)': ('src/Ryujinx.HLE/Utilities/StringUtils.cs', 'acbb2ce3535649da77114b52fe234a28414bb59dcd43d7e38e4862855283e7af'),
}


def member(text, signature):
    assert text.count(signature) == 1, signature
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    for index in range(brace + 1, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


for relative, expected in FILES.items():
    assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative
bodies = {}
for signature, (relative, expected) in MEMBERS.items():
    bodies[signature] = member((SOURCE / relative).read_text(), signature)
    assert hashlib.sha256(bodies[signature].encode()).hexdigest() == expected, signature

preflight = (ROOT / 'native/melonx/EmbeddedLaunchPreflight.cs').read_text()
new = '        // The version reader refreshes the content index itself.\n        var version = _contentManager.GetCurrentFirmwareVersion();'
old = '        _contentManager.LoadEntries();\n        var version = _contentManager.GetCurrentFirmwareVersion();'
assert preflight.count(new) == 1 and old not in preflight
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-launch-firmware-') as temporary:
    base = Path(temporary).resolve()
    for variant in ('control', 'candidate'):
        work = base / variant
        work.mkdir()
        for relative in FILES:
            shutil.copyfile(SOURCE / relative, work / Path(relative).name)
        for name in ('EmbeddedGameHeader', 'EmbeddedKeyValidation', 'EmbeddedLaunchDiagnostics'):
            shutil.copyfile(ROOT / 'native/melonx' / (name + '.cs'), work / (name + '.cs'))
        (work / 'EmbeddedLaunchPreflight.cs').write_text(preflight.replace(new, old) if variant == 'control' else preflight)
        (work / 'ContentManager.cs').write_text('''using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using LibHac.Common;
using LibHac.Fs;
using LibHac.Fs.Fsa;
using LibHac.Ncm;
using LibHac.Tools.FsSystem;
using LibHac.Tools.FsSystem.NcaUtils;
using Nca = FirmwareProbe.Nca;
using Path = System.IO.Path;
namespace Ryujinx.HLE.FileSystem {
public partial class ContentManager {
''' + bodies['public void LoadEntries(Switch device = null)'] + '\n' +
            bodies['public SystemVersion GetCurrentFirmwareVersion()'] + '\n}}\n')
        (work / 'StringUtils.cs').write_text('using System;using System.IO;using System.Text;namespace Ryujinx.HLE.Utilities { static class StringUtils {' +
            bodies['public static string ReadInlinedAsciiString(BinaryReader reader, int maxSize)'] + '}}')
        shutil.copyfile(ROOT / 'test/melonx_launch_firmware/Program.cs', work / 'Program.cs')
        with zipfile.ZipFile(PACKAGE) as archive:
            (work / 'LibHac.dll').write_bytes(archive.read('lib/net8.0/LibHac.dll'))
        (work / 'Test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><EnableNETAnalyzers>false</EnableNETAnalyzers>
<NuGetAudit>false</NuGetAudit><NoWarn>0162</NoWarn><DefineConstants>''' +
            ('ADAPTED' if variant == 'candidate' else '') + '''</DefineConstants>
</PropertyGroup><ItemGroup><Reference Include="LibHac"><HintPath>LibHac.dll</HintPath></Reference></ItemGroup></Project>''')
        (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        environment = os.environ.copy()
        environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
        run = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work / 'Test.csproj'), '-c', 'Release'],
                             cwd=work, env=environment, capture_output=True, text=True, timeout=180)
        if run.returncode:
            print(run.stdout, run.stderr, flush=True)
        run.check_returncode()
        reports[variant] = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
        print(variant, json.dumps(reports[variant]), flush=True)

assert reports['control']['semanticTrace'] == reports['candidate']['semanticTrace']
assert reports['control']['freshLaunchScans'] == 2 and reports['candidate']['freshLaunchScans'] == 1
inputs = ['native/melonx/EmbeddedLaunchPreflight.cs', 'native/melonx/EmbeddedGameHeader.cs',
          'native/melonx/EmbeddedKeyValidation.cs', 'native/melonx/EmbeddedLaunchDiagnostics.cs',
          'build-utils/melonx/source.json', 'test/melonx_launch_firmware_test.py',
          'test/melonx_launch_firmware/Program.cs']
receipt = dict(result='passed', reports=reports, upstreamRevision=pin['revision'], dotnet=pin['dotnet'],
               libHacPackageSha256=PACKAGE_SHA, physicalDeviceTested=False,
               ncaDecryptionDoubled=True, realFileSystemAndVersionParsing=True,
               inputs={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in inputs},
               upstreamFiles=FILES,
               upstreamMembers={signature: {'path': path, 'sha256': digest} for signature, (path, digest) in MEMBERS.items()})
output = ROOT / 'dist/melonx/launch-firmware-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Production preflight and firmware discovery: one fresh scan, unchanged versions and errors.', flush=True)
