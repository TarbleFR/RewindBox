import argparse, hashlib, shutil, subprocess, tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('engine',type=Path);p.add_argument('out',type=Path);args=p.parse_args()
here=Path(__file__).resolve().parent
d=args.engine.resolve()/'graphics/nvn/gfx';out=args.out.resolve();out.mkdir(exist_ok=True,parents=True)
def core_of(text):
    start=text.index('static int write_region_bl(')
    end=text.index('\nNVN(nvnTextureWriteTexels,',start)
    return text[start:end]

def exact_patch_versions(text):
    name='graphics/nvn/gfx/nvn/hle_nvn.c'
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);target=root/name;target.parent.mkdir(parents=True);target.write_text(text)
        def apply(label,reverse=False,check=False):
            flags=(['--reverse'] if reverse else [])+(['--check'] if check else [])
            return subprocess.run(['git','apply',*flags,here/(label+'.patch')],cwd=root,
                                  stderr=subprocess.PIPE,stdout=subprocess.PIPE)
        if 'static int write_region_linear(' in text:
            matches=[label for label in ('safe','suffix') if apply(label,True,True).returncode==0]
            if len(matches)!=1:raise ValueError('Unknown WriteTexels modification; cannot recover the pinned base')
            apply(matches[0],True).check_returncode()
        clean=target.read_text();core=core_of(clean)
        if hashlib.sha256(core.encode()).hexdigest()!='3a503bb253f75063e2d58cc8fb25505f686e0da4b0857cc112b5779650e8cd13':
            raise ValueError('The extracted WriteTexels base differs from the retained experiment')
        variants={}
        for label in ('safe','suffix'):
            target.write_text(clean)
            apply(label).check_returncode()
            variants[label]=core_of(target.read_text())
        return clean,core,variants

h=d/'nvn/hle_nvn.c'
s,core,official=exact_patch_versions(h.read_text())
start='static void write_texels('
hook='        int ok = 1;\n        for (int z = 0; z < nz && ok; z++)'
assert s.count(hook)==1
guard='''        if ((t->d.flags & (NVN_TEXTURE_FLAGS_LINEAR | NVN_TEXTURE_FLAGS_LINEAR_RENDER_TARGET)) &&
            t->d.target == NVN_TEXTURE_TARGET_2D && t->d.samples <= 1 && !level && !layer0 &&
            t->d.levels <= 1 && t->d.depth <= 1 && write_region_linear(t, r, src, row, bw, bh, bpb)) {
            nvn_be_tex_cpu_written(t);
            return;
        }
'''
region=(here/'region.inc').read_text()
for name in ['base','fixed','naive','staged','safe','suffix']:
    mod=core
    if name in ['naive','staged','safe','suffix']:
        helper=region
        if name in ['naive','staged']:
            left=helper.index('    // The old encoder');right=helper.index('    uint64_t useful =',left)
            helper=helper[:left]+helper[right:]
            helper=helper.replace('    if (useful > (unsigned)page) return 0;\n','')
        if name=='suffix':
            helper=helper.replace('    if (page <= 0 || (t->L.size > (unsigned)page && !suffix)) return 0;', '    if (!suffix || page <= 0) return 0;')
        if name=='naive':
            left=helper.index('    uint8_t local[512];');right=helper.index('    return 1;',left)
            helper=helper[:left]+'''    dm_guest_write_prepare(t->mem, t->L.size);
    for (size_t i=0;i<count;i++) memcpy(first+i*(size_t)pitch, src+i*row, bytes);
'''+helper[right:]
        mod=mod.replace(start,helper+'\n'+start).replace(hook,guard+hook)
    (out/(name+'.inc')).write_text(mod+'\n')
    if name in ('safe','suffix'):
        if mod!=official[name]:raise ValueError('Fixture does not match retained patch: '+name)
        shutil.copyfile(here/(name+'.patch'),out/(name+'.patch'))
base=(d/'tex/nvn_deswizzle.c').read_text();before='|| (d->flags & 0x10) || d->samples > 1) return -1;'
after=before.replace('0x10','(0x10 | 0x40)')
assert base.count(before)+base.count(after)==1
base=base.replace(after,before)
fixed=base.replace(before,after)
(out/'deswizzle_base.c').write_text(base)
(out/'deswizzle_fixed.c').write_text(fixed)
