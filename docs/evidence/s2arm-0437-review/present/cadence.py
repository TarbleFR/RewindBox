"""Compare selector source, native menu, producer period and a synthetic decision grid."""
import pathlib, sys, re, tempfile, subprocess
root=pathlib.Path(sys.argv[1])
roots=[root/x/'graphics/nvn/gfx/nvn' for x in ['843','844']]
def texts(file): return [(x/file).read_text() for x in roots]
def identical(name,a,b): assert a==b,name; print("identical",name)
for name in ["rb_present_hold.h","nvn_fi_rule.h"]:
    identical(name,*texts(name))
for name in ["S2ArmEngineBridgePlugin.m","S2ArmSettings.m","S2ArmSessionMenu.m"]:
    identical(name,*[(root/x/'packages/s2arm_engine_bridge/ios/Classes'/name).read_bytes() for x in ('843','844')])
def defn(text, name):
    pat=re.compile(r'^.*?\b'+name+r'\([^;\n]*?\)\s*\{',re.M)
    mat=next(m for m in pat.finditer(text) if (text[m.start():m.end()].startswith(('static','__attribute__'))))
    line=text[mat.start():text.index('\n',mat.start())]
    return line if '}' in line.split('//')[0] else text[mat.start():text.index('\n}',mat.end())+2]
for name in ["present_itv","present_period"]:
    identical(name,*[defn(t,name) for t in texts('hle_nvn.c')])
for name in ["rb_fi_requested","rb_fi_link_start"]:
    identical(name,*[defn(t,name) for t in texts('nvn_mtl.m')])
for name in ["fi_wanted_for","fi_wanted_now","fi_link_follow","fi_get","fi_job","fi_frame","s2a_rb_guest_set_frame_interp"]:
    identical(name,*[defn(t,name) for t in texts('nvn_present_fi.inc')])
for name,start,end in [('producer','        rb_sent_period = present_period(o);','        rb_itv_hold_ns = hold;'),('routing','    if (layer.pixelFormat == MTLPixelFormatBGRA8Unorm && fi_wanted_for','\n')]:
    file='hle_nvn.c' if name=='producer' else 'nvn_mtl.m'
    identical(name,*[t[t.index(start):t.index(end,t.index(start)+len(start))] for t in texts(file)])
with tempfile.TemporaryDirectory() as tmp:
    dest=pathlib.Path(tmp)
    for i in range(2):
        (dest/f'v{i}.c').write_text(f'#include "nvn_fi_rule.h"\nint v{i}(double p,double g){{return dm_fi_tier(p)*2+dm_fi_should_interp(p,g);}}')
        subprocess.run(['cc','-O2','-I'+str(roots[i]),'-c',str(dest/f'v{i}.c'),'-o',str(dest/f'v{i}.o')],check=True)
    (dest/'main.c').write_text(r'''
#include <math.h>
#include <assert.h>
#include <stdio.h>
int v0(double,double),v1(double,double);
int main(void) {
    unsigned cases=0,allows=0;
    const double eps[] = {-1.,0.,1./60,1./45,1./30,1./20,0.1,NAN,INFINITY};
    for(unsigned i=0;i<sizeof eps/sizeof *eps;i++){
        double p=eps[i];
        for(int e=-1;e<=1;e++){
            double x=e?nextafter(p,e<0?-INFINITY:INFINITY):p;
            const double gaps[]={0.,1./60,1./30,0.05,0.06,NAN,INFINITY,nextafter(x*1.25,-INFINITY),x*1.25,nextafter(x*1.25,INFINITY)};
            for(unsigned k=0;k<sizeof gaps/sizeof *gaps;k++){
                int a=v0(x,gaps[k]),b=v1(x,gaps[k]);assert(a==b);allows+=a%2;cases++;
            }
        }
    }
    for(int hz=1;hz<=240;hz++)for(int us=-1;us<=100000;us+=17){
        double p=1./hz,g=us/1e6;
        int a=v0(p,g);assert(a==v1(p,g));assert((a%2)==(hz<=45 && us>0 && g<=1.25*p));allows+=a%2;cases++;
    }
    printf("%u decisions; %u allowed; zero differences\n",cases,allows);
}''')
    subprocess.run(['cc','-O2',str(dest/'main.c'),*(str(dest/f'v{i}.o') for i in range(2)),'-lm','-o',str(dest/'grid')],check=True)
    subprocess.run([str(dest/'grid')],check=True)
