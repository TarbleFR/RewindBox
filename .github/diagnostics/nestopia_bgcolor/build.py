"""Compile only the proven Nestopia PPU reset fix; preserve the other 33 cores."""
import argparse, hashlib, json, os, shutil, subprocess, sys, tarfile, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'build-utils/libretro'))
import build_cores as package
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(args,**kwargs): subprocess.run([str(a) for a in args],check=True,**kwargs)
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--output',required=True);p.add_argument('--work',required=True);a=p.parse_args()
 base=Path(a.base).resolve();out=Path(a.output).resolve();work=Path(a.work).resolve();work.mkdir(parents=True,exist_ok=True)
 pin=json.loads((ROOT/'native/nestopia/source.json').read_text());identity=json.loads((base/'identity.json').read_text())
 assert identity['host_commit']==pin['baseHostCommit']
 for name,sha in identity['files'].items(): assert digest(base/name)==sha,name
 archive=work/'source.tar.gz'
 with urllib.request.urlopen(pin['upstream'].replace('github.com','codeload.github.com')+'/tar.gz/'+pin['revision'],timeout=120) as response: archive.write_bytes(response.read())
 assert digest(archive)==pin['archiveSha256']
 with tarfile.open(archive) as t:t.extractall(work,filter='data')
 source=work/('nestopia-'+pin['revision']);ppu=source/'source/core/NstPpu.cpp';patch=ROOT/'native/nestopia/reset-background.patch'
 assert digest(ppu)==pin['originalPpuSha256'];assert digest(patch)==pin['patchSha256']
 run(['git','apply','--check',patch],cwd=source);run(['git','apply',patch],cwd=source)
 assert digest(ppu)==pin['patchedPpuSha256']
 sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
 name='nestopia_libretro';install='@rpath/'+name+'.framework/'+name
 command=['make','-C',source/'libretro','-j4','platform=ios-arm64','DEBUG=0','GIT_VERSION=135dfa6-neostation-bgcolor1','IOSSDK='+sdk,
          'CC=xcrun --sdk iphoneos clang -arch arm64 -isysroot '+sdk,
          'CXX=xcrun --sdk iphoneos clang++ -arch arm64 -isysroot '+sdk,
          'PLATFORM_DEFINES=-miphoneos-version-min=18.0','LDFLAGS=-Wl,-install_name,'+install]
 with (work/'compile.log').open('w') as log:run(command,stdout=log,stderr=subprocess.STDOUT)
 binary=source/'libretro/nestopia_libretro_ios.dylib';info=package.macho(binary.read_bytes())
 assert info['platform']==2 and info['minimumOS']=='18.0',info
 package.check_dependencies(name,info);assert set(package.REQUIRED_EXPORTS)<=package.exported_symbols(binary)
 shutil.copytree(base,out)
 target=out/('Frameworks/'+name+'.framework');shutil.copy2(binary,target/name)
 (target/'Info.plist').write_bytes(package.framework_plist('com.neogamelab.neostation.libretro.nestopia',name,'18.0'))
 old=next(c for c in identity['cores'] if c['id']=='nestopia');original=dict(old)
 old.update(sha256=digest(binary),bytes=binary.stat().st_size,minimumOS='18.0',installName=install,dependencies=info['dependencies'],
            source=pin['upstream']+'/tree/'+pin['revision'],sourceRevision=pin['revision'],sourcePatchSha256=pin['patchSha256'],
            archive='source-135dfa6-neostation-bgcolor1',archiveSha256=pin['archiveSha256'],url=pin['upstream']+'/archive/'+pin['revision']+'.tar.gz')
 notices=out/'Libretro-Licenses/LIBRETRO_CORES.txt'
 notices.write_text(notices.read_text()+'\nNestopia only: NeoStation initializes the PPU background palette index during reset.\n'
                   +'Upstream '+old['source']+' (GPL-2.0-or-later); patch: TarbleFR/neostation-ios native/nestopia/reset-background.patch.\n')
 identity['host_commit']=os.environ['GITHUB_SHA']
 identity['nestopiaResetFix']={'source':pin,'originalCore':original,'compiledCoreSHA256':digest(binary),
                             'xcode':subprocess.check_output(['xcodebuild','-version'],text=True).strip()}
 allowed={'Frameworks/nestopia_libretro.framework/nestopia_libretro','Frameworks/nestopia_libretro.framework/Info.plist','Libretro-Licenses/LIBRETRO_CORES.txt'}
 for name,sha in identity['files'].items():
  if name not in allowed:assert digest(out/name)==sha,name
 identity['files']={f.relative_to(out).as_posix():digest(f) for f in out.rglob('*') if f.is_file() and f.name!='identity.json'}
 (out/'identity.json').write_text(json.dumps(identity,indent=2)+'\n')
 print('Compiled one corrected Nestopia; 33 other cores and all other assets preserved.',flush=True)
if __name__=='__main__':main()
