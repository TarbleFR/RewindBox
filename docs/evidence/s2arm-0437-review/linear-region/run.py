from pathlib import Path
import subprocess,os,sys
here=Path(__file__).resolve().parent
engine=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve() if len(sys.argv)>2 else here/'out'
subprocess.run([sys.executable,here/'prepare.py',engine,out],check=True)
t=engine/'graphics/nvn/gfx/tex';n=t.parent/'nvn'
names=['base','fixed','naive','staged','safe','suffix','control']
syms=['nvn_deswizzle_geom_ex','nvn_deswizzle_geom','nvn_deswizzle','nvn_swizzle','nvn_deswizzle_from','nvn_deswizzle_tile','nvn_deswizzle_tile_mode','nvn_tile_is_zero','nvn_bl_offset','nvn_gob_switch2']
for san in [True,False]:
    cc=['clang','-std=c11','-O2','-g','-I',str(here),'-I',str(out),'-I',str(t),*(['-fsanitize=address,undefined','-fno-sanitize-recover=all'] if san else [])]
    def de(v):return ['-D'+s+'='+s+'_'+v for s in syms]
    objs=[]
    for v in ['base','fixed']:
        obj=out/('desw-'+v+str(san)+'.o')
        subprocess.run([*cc,*de(v),'-c',out/('deswizzle_'+v+'.c'),'-o',obj],check=True);objs.append(obj)
    for v in names:
        obj=out/(v+str(san)+'.o')
        subprocess.run([*cc,*de('base' if v=='base' else 'fixed'),'-Wall','-Werror','-Wextra','-DNAME='+v,'-DSOURCE_FILE="'+('fixed' if v=='control' else v)+'.inc"',*(['-DIS_SAFE'] if v=='safe' else []),'-c',here/'wrapper.c','-o',obj],check=True);objs.append(obj)
    if not san and hasattr(os,'sched_getaffinity') and hasattr(os,'sched_setaffinity'):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    for order in ([0] if san else [0,1]):
        exe=out/('verify' if san else 'bench'+str(order))
        subprocess.run([*cc,here/('verify.c' if san else 'bench.c'),*(list(reversed(objs)) if order else objs),n/'nvn_tex.c','-lm','-o',exe],check=True)
        for temp in (['verify'] if san else ['warm','cold']):
            dest=out/('verify.txt' if san else temp+str(order)+'.csv')
            with dest.open('w') as f:subprocess.run([exe,*([temp] if not san else [])],check=True,stdout=f)
    if san:subprocess.run([sys.executable,here/'edge.py',engine,out],check=True)
