#!/usr/bin/env python3
"""Execute production game/header bounds with synthetic, non-game file bytes."""
from pathlib import Path
import subprocess,tempfile,json,hashlib
root=Path(__file__).resolve().parents[1];source=root/'native/melonx/EmbeddedGameHeader.cs'
with tempfile.TemporaryDirectory(prefix='melonx-headers-') as temporary:
 work=Path(temporary);(work/'Header.cs').write_bytes(source.read_bytes())
 (work/'Header.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>')
 (work/'Program.cs').write_text(r'''using System;
using System.IO;
using System.Text;
using System.Buffers.Binary;
using Ryujinx.Library;
int cases=0;
void Check(byte[] bytes,string extension,bool accepted){bool result=true;try{EmbeddedGameHeader.Validate(new MemoryStream(bytes),extension);}catch(InvalidDataException){result=false;}if(result!=accepted)throw new Exception("Header case "+cases);cases++;}
byte[] Header(string magic,int offset,int length){var data=new byte[length];Encoding.ASCII.GetBytes(magic).CopyTo(data,offset);return data;}
Check(Header("NSO0",0,128),"nso",true);Check(Header("PFS0",0,16),"nsp",true);Check(Header("HEAD",0x100,512),"xci",true);
Check(new byte[3],"nsp",false);Check(Header("WRNG",0,32),"nsp",false);
var nro=Header("NRO0",0x10,0x80);BinaryPrimitives.WriteInt32LittleEndian(nro.AsSpan(0x18),0x80);Check(nro,"nro",true);
BinaryPrimitives.WriteInt32LittleEndian(nro.AsSpan(0x18),0x81);Check(nro,"nro",false);
var assets=Header("NRO0",0x10,0x100);BinaryPrimitives.WriteInt32LittleEndian(assets.AsSpan(0x18),0x80);Encoding.ASCII.GetBytes("ASET").CopyTo(assets,0x80);Check(assets,"nro",true);
BinaryPrimitives.WriteInt64LittleEndian(assets.AsSpan(0x90),long.MaxValue);Check(assets,"nro",false);
BinaryPrimitives.WriteInt64LittleEndian(assets.AsSpan(0x90),0);BinaryPrimitives.WriteInt64LittleEndian(assets.AsSpan(0xa0),0x4001);Check(assets,"nro",false);
Console.WriteLine($"Production game header bounds: {cases} cases passed.");
''')
 print(subprocess.check_output(['dotnet','run','--project',str(work/'Header.csproj'),'-c','Release'],text=True))
