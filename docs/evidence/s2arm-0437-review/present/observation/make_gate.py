import argparse,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("makefile",type=Path);p.add_argument("engine",type=Path)
a=p.parse_args()
with tempfile.TemporaryDirectory() as d:
 d=Path(d)
 extra=d/"audit.mk"
 extra.write_text("show_fi_build_flag:\n\t@echo 'gate=$(RB_FI_STATS_CFLAGS)'\n")
 for setting in ["0","1","0","1 2","1","0"]:
    out=subprocess.check_output(["make","--no-print-directory","-s","-f",a.makefile.resolve(),"-f",extra,
                  "OUT="+str(d/"out"),"ROOT="+str(a.engine.resolve()),"S2A_RB_COMPILE_FI_STATS="+setting,
                  "show_fi_build_flag"],cwd=a.engine/"graphics/nvn",text=True)
    expect="-DS2A_RB_COMPILE_FI_STATS=1" if setting=="1" else ""
    if out.strip()!="gate="+expect: raise ValueError((out,expect))
    assert ("-DS2A_RB_COMPILE_FI_STATS=1" in (d/"out/.srclist").read_text())==(setting=="1")
print("Six switches: the nondefault macro and build fingerprint toggle only for exact value 1")
