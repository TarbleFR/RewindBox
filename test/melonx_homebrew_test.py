#!/usr/bin/env python3
"""Read original synthetic NROs with production code and exact embedded LibHac."""
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
package = Path(sys.argv[1])
assert hashlib.sha256(package.read_bytes()).hexdigest() == 'b68e88ab73aa48a0af2bb9575e5b07410a27f3cd03e9808920d863e1753279c9'
with tempfile.TemporaryDirectory(prefix='melonx-homebrew-') as temporary:
    work = Path(temporary)
    with zipfile.ZipFile(package) as archive: (work / 'LibHac.dll').write_bytes(archive.read('lib/net8.0/LibHac.dll'))
    shutil.copy2(ROOT / 'native/melonx/EmbeddedHomebrewAssets.cs', work)
    shutil.copy2(Path(sys.argv[2]) / 'src/Ryujinx.HLE/Loaders/Executables/NroExecutable.cs', work)
    shutil.copy2(Path(sys.argv[2]) / 'src/Ryujinx.HLE/Loaders/Executables/IExecutable.cs', work)
    plain = bytearray(0x3000)
    for offset, value in [(0,0x14000020),(0x10,0x304f524e),(0x18,0x3000),(0x20,0),(0x24,0x1000),(0x28,0x1000),(0x2c,0x1000),(0x30,0x2000),(0x34,0x1000),(0x38,0x1000),(0x80,0xd2800000),(0x84,0xd40000e1),(0x88,0x14000000)]: struct.pack_into('<I',plain,offset,value)
    (work / 'plain.nro').write_bytes(plain)
    assets = bytearray(0x38); struct.pack_into('<I',assets,0,0x54455341)
    (work / 'empty-assets.nro').write_bytes(plain + assets)
    struct.pack_into('<QQ',assets,0x18,0x38,16)
    (work / 'nacp-assets.nro').write_bytes(plain + assets + bytes([0x5a])*16)
    (work / 'Test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks></PropertyGroup><ItemGroup><Reference Include="LibHac"><HintPath>LibHac.dll</HintPath></Reference></ItemGroup></Project>''')
    (work / 'Program.cs').write_text(r'''using System;using System.IO;using LibHac.Fs;using LibHac.FsSystem;using LibHac.Tools.Fs;using LibHac.Tools.FsSystem;using LibHac.Tools.Ro;using Ryujinx.HLE.Loaders.Executables;
Span<byte> probe=stackalloc byte[1];int count=0;void Check(bool valid){if(!valid)throw new Exception("NRO production asset assertion failed");count++;}
foreach(var name in new[]{"plain.nro","empty-assets.nro","nacp-assets.nro"}) {
 using var stream=new FileStream(System.IO.Path.Combine(args[0],name),FileMode.Open);
 var executable=new NroExecutable(stream.AsStorage());Check(executable.Text.Length==0x1000&&executable.Ro.Length==0x1000&&executable.Data.Length==0x1000);
 using var romfs=EmbeddedHomebrewAssets.Open(executable,NroAssetType.RomFs,out long romSize);Check(romfs==null&&romSize==0);
 using var nacp=EmbeddedHomebrewAssets.Open(executable,NroAssetType.Nacp,out long nacpSize);
 if(name=="nacp-assets.nro") {Check(nacp!=null&&nacpSize==16);nacp.Read(0,probe).ThrowIfFailure();Check(probe[0]==0x5a);probe.Clear();}
 else Check(nacp==null&&nacpSize==0);
}
Console.WriteLine($"PASS {count} real LibHac/production executable checks: optional NRO assets and present assets.");
''')
    subprocess.run(['dotnet', 'run', '--project', str(work / 'Test.csproj'), '-c', 'Release', '--', str(work)], check=True, timeout=180)
