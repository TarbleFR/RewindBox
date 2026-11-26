from pathlib import Path
import subprocess
area=Path('/tmp/s2arm-a18-work'); file='graphics/nvn/gfx/nvn/nvn_mtl.m'
orig=subprocess.check_output(['git','-C',str(area),'show','HEAD:'+file],text=True)
cand=(area/file).read_text()
def extract(src):
    start=src.index('static int draw_pass_state(id en')
    src=src[start:src.index('\n}',start)+2]
    return src.replace('id<MTLDepthStencilState>', 'id')
fixed=extract(cand).replace('    const unsigned ed_need =','''    static int last_widen;
    if (last_widen || g_wd > 0) g_rb_ed_dirty |= ED_VP | ED_SC;
    last_widen = g_wd > 0;
    const unsigned ed_need =''')
for mode,body in [('baseline_0443',extract(orig)),('draft',extract(cand)),('repaired',fixed)]:
    Path(mode+'.c').write_text('#include "encoder_shim.h"\n'+body+'\n#include "encoder_replay.inc"\n')
    subprocess.run(['clang','-O2',mode+'.c','-o',mode],check=True)
