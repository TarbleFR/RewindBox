#!/usr/bin/env python3
"""Execute production preflight/journal against the actual pinned LibHac API.

No proprietary keys/firmware/game data is used. Content/device I/O is doubled;
the separate ARM64 NativeAOT smoke exercises the real runtime.
"""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
package = Path(sys.argv[1])
assert hashlib.sha256(package.read_bytes()).hexdigest() == 'b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9'
with tempfile.TemporaryDirectory(prefix='melonx-launch-native-') as temporary:
    work = Path(temporary)
    for name in ['EmbeddedLaunchPreflight', 'EmbeddedLaunchDiagnostics', 'EmbeddedKeyValidation', 'EmbeddedGameHeader']:
        shutil.copyfile(ROOT / 'native/melonx' / (name + '.cs'), work / (name + '.cs'))
    with zipfile.ZipFile(package) as archive:
        (work / 'LibHac.dll').write_bytes(archive.read('lib/net8.0/LibHac.dll'))
    (work / 'Test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
      <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
      </PropertyGroup><ItemGroup><Reference Include="LibHac"><HintPath>LibHac.dll</HintPath></Reference></ItemGroup></Project>''')
    (work / 'Fixtures.cs').write_text(r'''using System;
using System.IO;
using System.Collections.Generic;
using LibHac.Fs.Fsa;
using LibHac.Tools.Ncm;
using LibHac.Common.Keys;
using LibHac.Tools.FsSystem.NcaUtils;
using LibHac.Tools.FsSystem;
namespace Ryujinx.Common.Configuration { public static class AppDataManager { public static string BaseDirPath; } }
namespace Ryujinx.HLE.Utilities {
 public static class PartitionFileSystemUtils {
  public static IFileSystem OpenApplicationFileSystem(string path, object fs) => throw new InvalidDataException("Synthetic fixture has no NCA payload.");
 }
}
namespace Ryujinx.HLE.Loaders.Processes.Extensions {
 public class ContentMetaData {public Nca GetNcaByType(KeySet keys,LibHac.Ncm.ContentType type,int index)=>null;}
 public static class ContentFixture {
  public static Dictionary<ulong,ContentMetaData> GetContentData(this IFileSystem fs, LibHac.Ncm.ContentMetaType type, object vfs, IntegrityCheckLevel level) => new();
 }
}
namespace Ryujinx.Library {
 class Files { public KeySet KeySet=KeySet.CreateDefaultKeySet(); public void ReloadKeySet(){} }
 class VersionFixture {public string VersionString="";}
 class Firmware {public int Reloads;public void LoadEntries(){Reloads++;}public VersionFixture GetCurrentFirmwareVersion()=>null;}
 class Account {public void Refresh(){} }
 partial class Library {
  static Files _virtualFileSystem=new();static Firmware _contentManager=new();static Account _accountManager=new();
  public static void Preflight(string path,System.Text.Json.Utf8JsonWriter json)=>EmbeddedLaunchPreflight(path,json);
  public static int Reloads=>_contentManager.Reloads;
  // EmbeddedRuntime.cs owns the code arena request; the preflight only sets it.
  static ulong EmbeddedJitArenaHint;static ulong EmbeddedJitArenaFor(ulong titleId,Nca program)=>0;
  public static ulong ArenaHint{get=>EmbeddedJitArenaHint;set=>EmbeddedJitArenaHint=value;}
 }
}
''')
    (work / 'Program.cs').write_text(r'''using System;
using System.IO;
using System.Text;
using System.Text.Json;
using Ryujinx.Common;
using Ryujinx.Common.Configuration;
using Ryujinx.Library;
int checks=0;void Check(bool ok){if(!ok)throw new Exception("Launch preflight assertion failed");checks++;}
void Probe(string path){using var memory=new MemoryStream();using var json=new Utf8JsonWriter(memory);json.WriteStartObject();Library.Preflight(path,json);json.WriteEndObject();}
var root=Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);AppDataManager.BaseDirPath=root;
try {
 try{Probe(Path.Combine(root,"missing.nsp"));throw new Exception("Accepted missing game");}catch(FileNotFoundException){checks++;}
 var game=Path.Combine(root,"test.nro");var bytes=new byte[0x80];Encoding.ASCII.GetBytes("NRO0").CopyTo(bytes,0x10);BitConverter.GetBytes(0x80).CopyTo(bytes,0x18);File.WriteAllBytes(game,bytes);
 Probe(game);Probe(game);Check(Library.Reloads==2); // Plain homebrew needs neither keys nor firmware.
 Library.ArenaHint=1UL<<30;Probe(game);Check(Library.ArenaHint==0); // A previous launch's larger code arena request never carries over.
 var nsp=Path.Combine(root,"empty.nsp");File.WriteAllBytes(nsp,Encoding.ASCII.GetBytes("PFS0"));
 try{Probe(nsp);throw new Exception("Accepted absent personal keys");}catch(InvalidDataException){Check(EmbeddedLaunchDiagnostics.ErrorCode=="keysMissing");}
 Directory.CreateDirectory(Path.Combine(root,"system"));File.WriteAllText(Path.Combine(root,"system/prod.keys"),"not a key file");
 try{Probe(nsp);throw new Exception("Accepted invalid personal keys");}catch(InvalidDataException){Check(EmbeddedLaunchDiagnostics.ErrorCode=="keysInvalid");}
 File.Delete(Path.Combine(root,"system/prod.keys"));Probe(game);Check(EmbeddedLaunchDiagnostics.ErrorCode=="");
 EmbeddedLaunchDiagnostics.Record("gpu","begin");Check(EmbeddedLaunchDiagnostics.Classify(new FileNotFoundException("Vulkan dependency absent"))=="runtimeUnavailable");
 EmbeddedLaunchDiagnostics.Record("file","begin");Check(EmbeddedLaunchDiagnostics.Classify(new FileNotFoundException("Game absent"))=="localGameRequired");
 var secret=new string('a',64);Check(!EmbeddedLaunchDiagnostics.Safe("header_key = "+secret).Contains(secret));
 EmbeddedLaunchDiagnostics.Fail("content","ncaDecryption",new InvalidDataException("Unable to decrypt NCA section. Key Name: key_area_key_application_16 "+secret),3);
 using(var doc=JsonDocument.Parse(EmbeddedLaunchDiagnostics.Snapshot())) {
  Check(doc.RootElement.GetProperty("errorCode").GetString()=="ncaDecryption");
  Check(doc.RootElement.GetProperty("diagnostic").GetString().Contains("key_area_key_application_16"));
  Check(!doc.RootElement.GetRawText().Contains(secret));
 }
 for(int i=0;i<200;i++)EmbeddedLaunchDiagnostics.Record("session","begin",detail:new string('x',6000));
 using(var doc=JsonDocument.Parse(EmbeddedLaunchDiagnostics.Snapshot()))Check(doc.RootElement.GetProperty("events").GetArrayLength()==64);
 Check(EmbeddedLaunchDiagnostics.Snapshot().Length<524288);
 Console.WriteLine($"{checks} production preflight/key-schema/journal checks passed; native guest execution is separate.");
}finally{Directory.Delete(root,true);}
''')
    subprocess.run(['dotnet', 'run', '--project', str(work / 'Test.csproj'), '-c', 'Release'], check=True, timeout=180)
