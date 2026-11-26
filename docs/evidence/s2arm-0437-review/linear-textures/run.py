import argparse,os,re,shutil,subprocess,sys
from pathlib import Path
from difflib import unified_diff

p=argparse.ArgumentParser()
p.add_argument("root",type=Path);p.add_argument("out",type=Path)
p.add_argument("--followup",action="store_true")
args=p.parse_args()
out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
tex=args.root.resolve()/"graphics/nvn/gfx/tex";nvn=tex.parent/"nvn"
file=tex/"nvn_deswizzle.c";source=file.read_text()
target="    for (uint32_t y = 0; y < rows; y++) { if (to_linear) memcpy(lin"
assert source.count(target)==1
code="""    if (sp == row_bytes && pitch == row_bytes) {
        uint64_t bytes = (uint64_t)rows * row_bytes;
        uintptr_t source = (uintptr_t)mem, destination = (uintptr_t)lin;
        uintptr_t distance = source > destination ? source - destination : destination - source;
        // Keep each row's original order when a later source row aliases an earlier destination.
        if (bytes && bytes <= SIZE_MAX && distance >= bytes) {
            if (to_linear) memcpy(lin, mem, (size_t)bytes);
            else memcpy(mem, lin, (size_t)bytes);
            return 0;
        }
    }
"""
other=source.replace(target,code+target)
(out/"candidate.c").write_text(other)
path="graphics/nvn/gfx/tex/nvn_deswizzle.c"
(out/"candidate.diff").write_text(''.join(unified_diff(source.splitlines(True),other.splitlines(True),fromfile='a/'+path,tofile='b/'+path)))
names="nvn_bl_offset nvn_gob_switch2 nvn_tile_is_zero nvn_deswizzle nvn_swizzle nvn_deswizzle_geom_ex nvn_deswizzle_geom nvn_deswizzle_from nvn_deswizzle_tile_mode nvn_deswizzle_tile".split()
fixture=Path(__file__).resolve().with_name("measure.c")
def make(extra,suffix):
    cmd=["clang",*(["-DS2_LINEAR_FOLLOWUP=1"] if args.followup else []),"-O2","-std=c11","-I",str(tex),"-I",str(nvn),*extra]
    objects=[]
    for name in ("base","candidate","control"):
        obj=out/(name+suffix+'.o');objects.append(obj)
        symbols=["-D"+sym+"="+name+"_"+sym for sym in names]
        subprocess.run([*cmd,*symbols,"-c",out/"candidate.c" if name=="candidate" else file,"-o",obj],check=True)
    for rev in range(1 if suffix else 2):
        exe=out/("test"+suffix+str(rev))
        subprocess.run([*cmd,fixture,*(reversed(objects) if rev else objects),nvn/'nvn_tex.c','-o',exe],check=True)
        argv=['taskset','-c',str(min(os.sched_getaffinity(0)))] if hasattr(os,'sched_getaffinity') else []
        with (out/("verify.txt" if suffix else f"timing-{rev}.csv")).open("w") as f:
            subprocess.run([*argv,exe,*(['verify'] if suffix else [])],check=True,stdout=f)
make(['-g','-fsanitize=address,undefined','-fno-sanitize-recover=all'],'-san')
make([],'')

# Guest pools may expose two virtual mappings of the same pages.
if sys.platform.startswith("linux"):
    alias_exe = out / "alias-mappings"
    subprocess.run(["clang", "-O2", "-std=c11", "-I", str(tex),
                    Path(__file__).with_name("alias_mappings.c"), out/"base.o", out/"candidate.o",
                    nvn/"nvn_tex.c", "-o", alias_exe], check=True)
    with (out/"alias-mappings.txt").open("w") as stream:
        subprocess.run([alias_exe], stdout=stream, check=True)
