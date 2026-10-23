"""Compile production save calls against pinned LibHac; exercise personal options.

The narrow host fixtures do not emulate NAND/game execution. The complete
NativeAOT engine and actual iOS bootstrap are separately verified by CI.
"""
from pathlib import Path
import hashlib,re,shutil,subprocess,sys,tempfile,zipfile
root=Path(__file__).resolve().parents[1]
source=Path(sys.argv[1])
package=Path(sys.argv[2])
assert hashlib.sha256(package.read_bytes()).hexdigest()=='b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9'
with tempfile.TemporaryDirectory(prefix='melonx-library-api-') as d:
 work=Path(d)
 with zipfile.ZipFile(package) as z:(work/'LibHac.dll').write_bytes(z.read('lib/net8.0/LibHac.dll'))
 for name in ['EmbeddedSaveTransfer.cs','EmbeddedPersonalOptions.cs','EmbeddedKeyValidation.cs']:
  shutil.copyfile(root/'native/melonx'/name,work/name)
 shutil.copyfile(source/'src/Ryujinx.HLE/HOS/Services/Account/Acc/Types/UserId.cs',work/'UserId.cs')
 (work/'Api.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks></PropertyGroup><ItemGroup><Reference Include="LibHac"><HintPath>LibHac.dll</HintPath></Reference></ItemGroup></Project>')
 enums=[]
 enum_sources={
  'Ryujinx.Common.Configuration':['AspectRatioExtensions','AntiAliasing','BackendThreading'],
  'Ryujinx.HLE.HOS.SystemState':['SystemLanguage','RegionCode']}
 for namespace,names in enum_sources.items():
  for name in names:
   text=(source/'src'/namespace.replace('.Configuration','/Configuration').replace('Ryujinx.HLE.HOS.SystemState','Ryujinx.HLE/HOS/SystemState')/(name+'.cs')).read_text()
   declaration=re.search(r'public enum \w+\s*\{[^}]*\}',text)[0]
   enums.append('namespace '+namespace+' { '+declaration+' }')
 personal=(root/'native/melonx/EmbeddedPersonalOptions.cs').read_text()
 options=(source/'src/Ryujinx.Library/Options.cs').read_text()
 fields=[]
 for name in sorted(set(re.findall(r'options\.(\w+)\s*=',personal))):
  match=re.search(r'public\s+([\w.]+)\s+'+name+r'\s*\{\s*get;',options)
  assert match,name
  fields.append('public '+match[1]+' '+name+' {get;set;}')
 (work/'Stubs.cs').write_text('''using System.Collections.Generic;
using System.IO;
using Ryujinx.Common.Configuration;
using Ryujinx.HLE.HOS.SystemState;
namespace Ryujinx.Common.Configuration {public static class AppDataManager {public static string BaseDirPath="";}}
namespace Ryujinx.HLE.FileSystem {public static class VirtualFileSystem {public static string GetNandPath()=>"/tmp/bis";}}
namespace Ryujinx.Library {
class Profile {public Ryujinx.HLE.HOS.Services.Account.Acc.UserId UserId=default;public string Name="test";}
class AccountManager {public IEnumerable<Profile> GetAllUsers()=>new Profile[0];}
class HorizonManager {public LibHac.HorizonClient RyujinxClient=null;}
class GameInfo {public string TitleId="0100123456780000";}
static class GameInfoLoader {public static GameInfo GetGameInfo(object fs,Stream stream,string extension)=>new();}
public class Options {'''+''.join(fields)+'''}
partial class Library {
 static object _virtualFileSystem=new();static AccountManager _accountManager=new();static HorizonManager _libHacHorizonManager=new();
 public static Options Probe(Options options,string game)=>ApplyEmbeddedPersonalOptions(options,game);
 public static void SaveProbe(string json,System.Text.Json.Utf8JsonWriter writer)=>EmbeddedSaveTarget(json,writer);
}}
'''+ '\n'.join(enums))
 (work/'Program.cs').write_text(r'''using System;
using System.IO;
using System.Text.Json;
using Ryujinx.Common.Configuration;
using Ryujinx.Library;
var root=Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
int count=0;void Check(bool value){if(!value)throw new Exception("personal options assertion");count++;}
try {
AppDataManager.BaseDirPath=root;var game=Path.Combine(root,"personal.nro");File.WriteAllText(game,"fixture");
var options=Library.Probe(new Options{AudioVolume=1},game);Check(options.AudioVolume==1);
File.WriteAllText(Path.Combine(root,"config.json"),"{\"audioVolume\":0.3,\"disableDockedMode\":true,\"systemLanguage\":2,\"useHypervisor\":true}");
options=Library.Probe(new Options(),game);Check(options.AudioVolume==0.3f&&options.DisableDockedMode);
Directory.CreateDirectory(Path.Combine(root,"config"));File.WriteAllText(Path.Combine(root,"config/0100123456780000_config.json"),"{\"audioVolume\":0.8,\"aspectRatio\":1}");
options=Library.Probe(new Options(),game);Check(options.AudioVolume==0.8f&&options.DisableDockedMode);
File.WriteAllText(Path.Combine(root,"config/0100123456780000_config.json"),"{\"audioVolume\":2}");try{Library.Probe(new Options(),game);throw new Exception("accepted invalid volume");}catch(InvalidDataException){count++;}
File.WriteAllText(Path.Combine(root,"config/0100123456780000_config.json"),"{\"aspectRatio\":999}");try{Library.Probe(new Options(),game);throw new Exception("accepted unknown enum");}catch(InvalidDataException){count++;}
using var stream=new MemoryStream();using var writer=new Utf8JsonWriter(stream);try{Library.SaveProbe("{\"titleId\":\"../invalid\",\"profileId\":\"invalid\"}",writer);throw new Exception("accepted invalid association");}catch(ArgumentException){count++;}
var prod=Path.Combine(root,"prod.keys");
File.WriteAllText(prod,"# personal export\n\nheader_key = "+new string('a',64)+"\n");EmbeddedKeyValidation.Validate(prod);count++;
foreach(var invalidKeys in new[]{"header_key = aa","unknown_key = "+new string('a',32),"header_key = "+new string('a',64)+"\nheader_key = "+new string('b',64)}) {
File.WriteAllText(prod,invalidKeys);try{EmbeddedKeyValidation.Validate(prod);throw new Exception("accepted invalid key schema");}catch(InvalidDataException){count++;}}
var title=Path.Combine(root,"title.keys");File.WriteAllText(title,new string('0',32)+" = "+new string('a',32));EmbeddedKeyValidation.Validate(title);count++;
File.WriteAllText(title,new string('0',32)+" = aa");try{EmbeddedKeyValidation.Validate(title);throw new Exception("accepted invalid title key");}catch(InvalidDataException){count++;}
Console.WriteLine($"{count} native personal configuration/save/key validation cases passed; LibHac API compile passed");
}finally{Directory.Delete(root,true);}''')
 subprocess.run(['dotnet','run','--project',str(work/'Api.csproj'),'-c','Release'],check=True,timeout=120)
