from pathlib import Path
import subprocess,sys
p=Path(__file__).resolve().parent
eng=Path(sys.argv[1]).resolve()/'graphics/nvn/gfx'
out=Path(sys.argv[2]).resolve()
objs=[out/(name+'True.o') for name in ['desw-base','desw-fixed','base','fixed','naive','staged','safe','suffix','control']]
subprocess.run(['clang','-std=c11','-O2','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',p,'-I',eng/'tex',p/'edge.c',*objs,eng/'nvn/nvn_tex.c','-lm','-o',out/'edges'],check=True)
with (out/'edges.txt').open('w') as f:subprocess.run([out/'edges'],stdout=f,check=True)
