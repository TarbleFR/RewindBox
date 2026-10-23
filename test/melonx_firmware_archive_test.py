"""Exercise production archive discovery and cancellation/rollback integration."""
from pathlib import Path
import os, subprocess, tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='melonx-archive-') as d:
 p=Path(d)
 for name in ['EmbeddedFirmwareArchive.cs','EmbeddedFirmwareStore.cs']:
  (p/name).write_bytes((root/'native/melonx'/name).read_bytes())
 (p/'Test.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>')
 (p/'Program.cs').write_text(r'''using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using Ryujinx.HLE.FileSystem;
int count=0;
void Check(bool b) { if(!b) throw new Exception("assertion failed"); }
void Case(string n,Action a) { EmbeddedFirmwareProgress.Begin();a();Console.WriteLine("PASS "+n);count++; }
ZipArchive Archive(params string[] names) { var memory=new MemoryStream();using(var z=new ZipArchive(memory,ZipArchiveMode.Create,true))foreach(var name in names){using var s=z.CreateEntry(name).Open();s.WriteByte(7);}memory.Position=0;return new ZipArchive(memory,ZipArchiveMode.Read); }
string nca=new string('a',32)+".nca";
Case("arbitrary parent and root firmware names",()=> {using var z=Archive(nca,"any folder/"+new string('b',32)+".nca");Check(EmbeddedFirmwareArchive.Entries(z).Count()==2);});
Case("case and fragmented NCA forms normalize identically",()=> {using var z=Archive("WRAPPER/"+nca.ToUpperInvariant()+"/00");Check(EmbeddedFirmwareArchive.Name(z.Entries[0])==nca);});
Case("macOS metadata is ignored before the NCA parser",()=> {using var z=Archive("__MACOSX/._"+nca,"other/._"+nca,nca);Check(EmbeddedFirmwareArchive.Entries(z).Count()==1);});
Case("duplicate IDs in distinct archive folders are refused",()=> {using var z=Archive(nca,"other/"+nca);try {EmbeddedFirmwareArchive.Entries(z).ToArray();throw new Exception("accepted duplicate");}catch(InvalidDataException){} });
Case("unsafe parent paths are refused",()=> {using var z=Archive("../"+nca);try{EmbeddedFirmwareArchive.Entries(z).ToArray();throw new Exception("accepted traversal");}catch(InvalidDataException){} });
Case("unrelated files do not masquerade as firmware",()=> {using var z=Archive("readme.txt","wrong.nca","image.png");Check(!EmbeddedFirmwareArchive.Entries(z).Any());});
Case("cancellation reaches the extraction enumerator",()=> {using var z=Archive(nca);EmbeddedFirmwareProgress.Cancel();try{EmbeddedFirmwareArchive.Entries(z).ToArray();throw new Exception("ignored cancellation");}catch(OperationCanceledException){} });
Case("engine rejection or cancellation after swap restores recognized old firmware",()=> {
 var work=Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString("N"));Directory.CreateDirectory(work);
 try {var old=Path.Combine(work,"registered");var stage=Path.Combine(work,"stage");Directory.CreateDirectory(old);Directory.CreateDirectory(stage);File.WriteAllText(Path.Combine(old,"version"),"old");File.WriteAllText(Path.Combine(stage,"version"),"new");
 try {EmbeddedFirmwareStore.Commit(stage,old,()=> {if(File.ReadAllText(Path.Combine(old,"version"))=="new")throw new InvalidDataException("engine did not recognize installed firmware");});throw new Exception("accepted rejection");}catch(InvalidDataException){}Check(File.ReadAllText(Path.Combine(old,"version"))=="old");
 }finally {Directory.Delete(work,true);}
});
Console.WriteLine($"{count} production firmware archive cases passed");''')
 subprocess.run(['dotnet','run','--project',str(p/'Test.csproj'),'-c','Release'],check=True,timeout=120)
