#!/usr/bin/env python3
"""Execute the production firmware swap with real files and interrupted states."""
from pathlib import Path
import subprocess
import tempfile
import json
import hashlib

root = Path(__file__).resolve().parents[1]
source = root / 'native/melonx/EmbeddedFirmwareStore.cs'
with tempfile.TemporaryDirectory(prefix='melonx-firmware-') as temporary:
    work = Path(temporary)
    (work / 'Store.cs').write_bytes(source.read_bytes())
    (work / 'Firmware.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>''')
    (work / 'Program.cs').write_text(r'''using System;
using System.IO;
using Ryujinx.HLE.FileSystem;
var root = Path.Combine(Path.GetTempPath(), "melonx-fw-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
int count = 0;
void Check(bool ok) { if (!ok) throw new Exception("Firmware transaction assertion failed"); }
void Case(string name, Action<string> test) {
    var path = Path.Combine(root, (++count).ToString()); Directory.CreateDirectory(path); test(path); Console.WriteLine("PASS " + name);
}
void Put(string path, string value) { Directory.CreateDirectory(path); File.WriteAllText(Path.Combine(path,"content"),value); }
string Read(string path) => File.ReadAllText(Path.Combine(path,"content"));
try {
Case("first installation commits only after loading entries", p => {
    var live = Path.Combine(p,"registered"); var staged = Path.Combine(p,"temp"); Put(staged,"new");
    bool loaded = false; EmbeddedFirmwareStore.Commit(staged,live,()=>{Check(Read(live)=="new"); loaded=true;});
    Check(loaded && Read(live)=="new" && !File.Exists(live+".rewindbox-transaction"));
});
Case("replacement retains old firmware through index loading", p => {
    var live=Path.Combine(p,"registered");var staged=Path.Combine(p,"temp");Put(live,"old");Put(staged,"new");
    EmbeddedFirmwareStore.Commit(staged,live,()=>Check(Read(live+".rewindbox-previous")=="old"));
    Check(Read(live)=="new" && !Directory.Exists(live+".rewindbox-previous"));
});
Case("index failure rolls back files and reloads the old index", p => {
    var live=Path.Combine(p,"registered");var staged=Path.Combine(p,"temp");Put(live,"old");Put(staged,"new");int calls=0;
    try { EmbeddedFirmwareStore.Commit(staged,live,()=>{calls++;if(calls==1)throw new IOException("index rejected");Check(Read(live)=="old");});throw new Exception("No failure"); }
    catch(IOException error) { Check(error.Message=="index rejected"); }
    Check(calls==2 && Read(live)=="old");
});
Case("interruption after old directory move restores old firmware", p => {
    var live=Path.Combine(p,"registered");Put(live+".rewindbox-previous","old");File.WriteAllText(live+".rewindbox-transaction","");
    EmbeddedFirmwareStore.Recover(live);Check(Read(live)=="old");
});
Case("interruption after new move rolls back an uncommitted replacement", p => {
    var live=Path.Combine(p,"registered");Put(live,"uncommitted");Put(live+".rewindbox-previous","old");File.WriteAllText(live+".rewindbox-transaction","");
    EmbeddedFirmwareStore.Recover(live);Check(Read(live)=="old");
});
Case("interruption before old move never erases the existing firmware", p => {
    var live=Path.Combine(p,"registered");Put(live,"old");File.WriteAllText(live+".rewindbox-transaction","");
    EmbeddedFirmwareStore.Recover(live);Check(Read(live)=="old");
});
Case("interruption after commit preserves new firmware", p => {
    var live=Path.Combine(p,"registered");Put(live,"new");Put(live+".rewindbox-previous","old");
    EmbeddedFirmwareStore.Recover(live);Check(Read(live)=="new" && !Directory.Exists(live+".rewindbox-previous"));
});
Case("first installation failure removes the rejected firmware", p => {
    var live=Path.Combine(p,"registered");var staged=Path.Combine(p,"temp");Put(staged,"rejected");int calls=0;
    try { EmbeddedFirmwareStore.Commit(staged,live,()=>{if(++calls==1)throw new IOException("first rejected");Check(!Directory.Exists(live));});throw new Exception("No failure"); }
    catch(IOException error) { Check(error.Message=="first rejected"); }
    Check(calls==2 && !Directory.Exists(live));
});
Case("interrupted first installation is not reported as committed", p => {
    var live=Path.Combine(p,"registered");Put(live,"uncommitted");File.WriteAllText(live+".rewindbox-transaction","empty");
    EmbeddedFirmwareStore.Recover(live);Check(!Directory.Exists(live));
});
Case("missing staged replacement cannot destroy old firmware", p => {
    var live=Path.Combine(p,"registered");Put(live,"old");
    try{EmbeddedFirmwareStore.Commit(Path.Combine(p,"missing"),live,()=>{});throw new Exception("No failure");}catch(IOException){}
    Check(Read(live)=="old");
});
Console.WriteLine($"Production firmware transaction: {count} cases passed.");
} finally { Directory.Delete(root,true); }
''')
    result = subprocess.run(['dotnet','run','--project',str(work/'Firmware.csproj'),'-c','Release'],check=True,text=True,capture_output=True,timeout=120)
    print(result.stdout,end='')
out = root / 'dist/melonx/firmware-transaction-checks.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'productionSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                          'result':result.stdout.strip(),'proprietaryFirmwareUsed':False},indent=2)+'\n')
