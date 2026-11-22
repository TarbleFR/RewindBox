"""Build a small .NET probe using the supplied final prepared source."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PIN = 'build-utils/melonx/source.json'
JIT = 'src/Ryujinx.Cpu/LightningJit/'
TABLE = 'src/Ryujinx.Cpu/Jit/HostTracked/NativePageTable.cs'
EMITTER = JIT + 'Arm64/Target/Arm64/InstEmitMemory.cs'
ADAPTER = ['build-utils/melonx/adapt_native_page_bounds.py', 'build-utils/melonx/native-page-bounds.patch']


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--candidate-source', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    return parser.parse_args()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(work, entry):
    sdk = json.loads((ROOT / PIN).read_text())['dotnet']
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': sdk, 'rollForward': 'disable'}}))
    (work / 'Probe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
    <StartupObject>{entry}</StartupObject><LangVersion>preview</LangVersion><NuGetAudit>false</NuGetAudit>
  </PropertyGroup>
</Project>''')
    output = subprocess.check_output(['dotnet', 'run', '-c', 'Release', '--project', 'Probe.csproj'],
                                     cwd=work, text=True, timeout=180)
    return [json.loads(line) for line in output.splitlines() if line.startswith('{')]


def report(args, data, inputs, names, compiled=()):
    if data.get('result') != 'passed' or not data.get('checks'):
        raise ValueError('Incomplete native bounds probe output')
    paths = [*ADAPTER, PIN, 'test/melonx_native_bounds_probe.py', *inputs]
    data.update(sourceKind='finalPrepared', physicalDeviceTested=False, inputs={name: sha(ROOT / name) for name in paths},
                preimages={name: sha(args.source / name) for name in names},
                postimages={name: sha(args.candidate_source / name) for name in names},
                compiledSourceInputs={name: sha(args.candidate_source / name) for name in compiled})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps(data))
