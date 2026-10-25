#!/usr/bin/env python3
"""Execute the actual graphics parser, effective-options formatter and journal.

Reproduces the reported UI values and the old key-redaction false positive.
This is managed host coverage, not GPU rendering or device validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'cb3e5d5b'
parser = argparse.ArgumentParser()
parser.add_argument('upstream', type=Path)
args = parser.parse_args()
inputs = [
    'native/melonx/EmbeddedSession.cs',
    'native/melonx/EmbeddedGraphicsSettings.cs',
    'native/melonx/EmbeddedLaunchDiagnostics.cs',
    str(Path(__file__).relative_to(ROOT)),
]
upstream_inputs = ['src/Ryujinx.Library/Options.cs']


def formatter(source):
    match = re.search(
        r'EmbeddedLaunchDiagnostics.Record\("configuration", "effective", detail:\s*'
        r'FormattableString\.Invariant\(\$"[^\n]+"\)\);', source)
    assert match, 'Production effective configuration record was not found'
    return match[0]


old = subprocess.check_output(
    ['git', 'show', BASELINE + ':native/melonx/EmbeddedSession.cs'],
    cwd=ROOT, text=True)
current = (ROOT / inputs[0]).read_text()
graphics = (ROOT / inputs[1]).read_text().split('\npartial class Library')[0]
options = (args.upstream / upstream_inputs[0]).read_text()
fields = []
for name in sorted(set(re.findall(r'options\.(\w+)', graphics + formatter(current)))):
    match = re.search(r'public\s+([\w.]+)\s+' + name + r'\s*\{\s*get;', options)
    assert match, name
    fields.append('public ' + match[1] + ' ' + name + ' {get;set;}')
enums = []
for name in ['AspectRatioExtensions', 'ScalingFilter', 'VSyncMode', 'BackendThreading']:
    path = f'src/Ryujinx.Common/Configuration/{name}.cs'
    upstream_inputs.append(path)
    text = (args.upstream / path).read_text()
    enums.append(re.search(r'public enum \w+\s*\{[^}]*\}', text)[0])

with tempfile.TemporaryDirectory(prefix='melonx-effective-graphics-') as directory:
    work = Path(directory)
    shutil.copyfile(ROOT / inputs[2], work / 'Journal.cs')
    (work / 'Graphics.cs').write_text(graphics)
    (work / 'Options.cs').write_text(
        'using Ryujinx.Common.Configuration;\n'
        'namespace Ryujinx.Library { internal class Options {' + ''.join(fields) + '}}\n'
        'namespace Ryujinx.Common.Configuration {' + ''.join(enums) + '}\n')
    (work / 'Probe.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
        '<TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
        '</PropertyGroup></Project>')
    (work / 'Program.cs').write_text(r'''using System;
using System.Globalization;
using System.IO;
using System.Text.Json;
using Ryujinx.Common;
using Ryujinx.Library;
using Ryujinx.Common.Configuration;
int checks=0;
void Check(bool passed,string label) {if(!passed)throw new Exception(label);checks++;}
void Record(Options options) {''' + formatter(current) + r'''}
void OldRecord(Options options) {''' + formatter(old) + r'''}
string journal=Path.Combine(args[0],"app.log");
EmbeddedLaunchDiagnostics.ConfigureJournal(journal);
// Force comma-decimal host culture; logs must still use invariant values.
CultureInfo.CurrentCulture=CultureInfo.GetCultureInfo("fr-FR");
var video=EmbeddedGraphicsSettings.Parse("""
{"resolution":0.75,"shaderCache":true,"asyncShaders":false,"vsync":true,
 "hostMemoryBudget":true,"textureRecompression":false,"filter":"bilinear"}
""").Apply(new Options {DisableShaderCache=true,EnableAsyncShaderCompilation=true,
EnableHostMemoryBudgetTracking=false,EnableTextureRecompression=true,BackendThreading=BackendThreading.Off});
OldRecord(video);
Record(video);
var explicitOther=EmbeddedGraphicsSettings.Parse("""
{"resolution":1.5,"shaderCache":false,"asyncShaders":true,"vsync":false,
 "hostMemoryBudget":false,"textureRecompression":true}
""").Apply(new Options {BackendThreading=BackendThreading.Off});
Record(explicitOther);
EmbeddedLaunchDiagnostics.Record("keys","failed",detail:"header_key = "+new string('a',64));
using var snapshot=JsonDocument.Parse(EmbeddedLaunchDiagnostics.Snapshot());
var events=snapshot.RootElement.GetProperty("events");
Check(events.GetArrayLength()==4,"Unexpected journal events");
string Detail(int index)=>events[index].GetProperty("diagnostic").GetString();
Check(Detail(0)=="[redacted key entry]","Old production false positive was not reproduced");
foreach(string field in new[]{"resolution=0.75","shaderCache=True","asyncShaders=False",
 "vsync=Switch","hostMemoryBudget=True","textureRecompression=False","threading=Off"})
 Check(Detail(1).Contains(field),"Video options did not survive: "+field);
foreach(string field in new[]{"resolution=1.5","shaderCache=False","asyncShaders=True",
 "vsync=Unbounded","hostMemoryBudget=False","textureRecompression=True"})
 Check(Detail(2).Contains(field),"Explicit option did not survive: "+field);
Check(Detail(3)=="[redacted key entry]","Key assignment no longer redacted");
Check(!File.ReadAllText(journal).Contains(new string('a',64)),"Synthetic key reached file");
var lines=File.ReadAllLines(journal);
Check(lines.Length==4,"Journal record count");
for(int index=0;index<lines.Length;index++) {
 using var disk=JsonDocument.Parse(lines[index]["[MeloNX:core] ".Length..]);
 Check(disk.RootElement.GetProperty("diagnostic").GetString()==Detail(index),"File and snapshot differ");
}
Console.WriteLine($"PASS {checks} effective graphics/journal assertions; old masking reproduced; no GPU test.");
''')
    result = subprocess.run(
        ['dotnet', 'run', '--project', str(work / 'Probe.csproj'), '-c', 'Release', '--', str(work)],
        capture_output=True, text=True, timeout=120)
    print(result.stdout + result.stderr)
    assert result.returncode == 0, 'Production graphics journal regression failed'

evidence = {
    'result': 'passed',
    'summary': result.stdout.strip(),
    'baseline': subprocess.check_output(['git', 'rev-parse', BASELINE], cwd=ROOT, text=True).strip(),
    'upstream': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.upstream, text=True).strip(),
    'inputs': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
    'upstreamInputs': {p: hashlib.sha256((args.upstream / p).read_bytes()).hexdigest() for p in upstream_inputs},
    'gpuRenderingTested': False,
    'deviceTested': False,
}
output = ROOT / 'docs/evidence/melonx-effective-graphics-journal.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(evidence, indent=2) + '\n')
