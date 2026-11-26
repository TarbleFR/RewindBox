from pathlib import Path
import argparse,os,shutil,subprocess
p=argparse.ArgumentParser();p.add_argument("engine",type=Path);p.add_argument("patches",type=Path);p.add_argument("out",type=Path);a=p.parse_args()
me=Path(__file__).resolve().parent;s0=a.engine/"graphics/widen/WidenRewriter.cs"
for mode in ["base","all","compatible"]:
 root=a.out/mode;w=root/"graphics/widen";w.mkdir(parents=True,exist_ok=True)
 shutil.copy2(s0,w/s0.name)
 if mode!="base":
    subprocess.run(["patch","--batch","-p1","-i",str((a.patches/(mode+".patch")).resolve())],cwd=root,check=True)
 shutil.copy2(me/"Review.cs",w/"Review.cs")
 (w/"review.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion><AllowUnsafeBlocks>true</AllowUnsafeBlocks></PropertyGroup></Project>')
 subprocess.run(["dotnet","build","review.csproj","-c","Release","--nologo"],cwd=w,stdout=(root/"build.log").open("w"),check=True)
 for disabled in ["0","1"]:
  env={**os.environ,"S2A_WIDEN_NOCAM":disabled,"DOTNET_TieredCompilation":"0"}
  out=subprocess.check_output(["dotnet",str(w.resolve()/"bin/Release/net10.0/review.dll")],env=env,text=True);(root/("nocam-"+disabled+".txt")).write_text(out)
  print(mode,"nocam",disabled,out.replace("\n"," | ")[:360],flush=True)

for disabled in ["0","1"]:
    name=f"nocam-{disabled}.txt"
    reference=(a.out/"base"/name).read_bytes()
    if reference != (a.out/"compatible"/name).read_bytes():
        raise AssertionError(f"compatible differs from reference: {name}")
    other=(a.out/"all"/name).read_bytes()
    if other == reference or other.splitlines()[3:] != reference.splitlines()[3:]:
        raise AssertionError(f"expected a length-only regression in all.patch: {name}")
print("Both configurations passed differential comparison. The original all.patch fails the length control.")
