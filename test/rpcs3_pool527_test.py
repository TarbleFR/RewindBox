#!/usr/bin/env python3
"""Build527: actual retired-image pool methods, byte cap and lock ownership.

Vulkan images are lightweight host adapters carrying logical allocation sizes.
No GPU residency, game footprint, FPS or driver timing is measured.
"""
import argparse, hashlib, json, os, shlex, shutil, subprocess, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = 'c44eb1ab884562c573f0d4214bf016c964182c801f48f2ee5a8a6f76aaf83496'

def block(source, marker):
    start=source.index(marker); end=source.index('{',start)+1; depth=1
    while depth:
        depth += (source[end]=='{')-(source[end]=='}'); end+=1
    return source[start:end]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--report',type=Path)
    p.add_argument('--sanitize',action='store_true');p.add_argument('--benchmark',action='store_true')
    p.add_argument('--require-core-compiler',action='store_true')
    a=p.parse_args(); source=a.source.resolve()
    path='rpcs3/Emu/RSX/VK/VKTextureCache.cpp'
    after=(source/path).read_text()
    markers=('u64 hash_image_properties(',
        'texture_cache::cached_image_reference_t::cached_image_reference_t(',
        'texture_cache::cached_image_reference_t::~cached_image_reference_t()',
        'void texture_cache::clear()',
        'std::unique_ptr<vk::viewable_image> texture_cache::find_cached_image(',
        'bool texture_cache::handle_memory_pressure(',
        'void texture_cache::on_frame_end()',
        'u32 texture_cache::get_unreleased_textures_count() const')
    ctor=block(after,markers[2]);frame=block(after,markers[6])
    assert ctor.index('std::lock_guard lock(parent->m_cached_pool_lock)') < ctor.index('trim_to_fit(')
    assert ctor.index('incoming_bytes <= rpcs3::ios::recyclable_image_pool::byte_limit') < ctor.index('trim_to_fit(')
    assert frame.index('trim_to_fit(') < frame.index('texture_profile.publish') < frame.index('discarded_images.clear()')
    assert 'vk::get_resource_manager()->dispose(disposable);' in block(after,'void texture_cache::on_section_destroyed(')
    #528/526 GPU retirement stays the original event-scope ownership path.
    resource=(source/'rpcs3/Emu/RSX/VK/VKResourceManager.h').read_text()
    assert 'void eid_completed(u64 eid)' in resource and 'discarded_scopes' in resource
    cxx=shlex.split(os.environ.get('CXX','c++'))
    if a.require_core_compiler:
        config=os.environ.get('LLVM_CONFIG') or shutil.which('llvm-config')
        if not config: raise SystemExit('LLVM_CONFIG required')
        cxx=[str(Path(subprocess.check_output([config,'--bindir'],text=True).strip())/'clang++')]
        version=subprocess.check_output(cxx+['--version'],text=True)
        assert 'clang version 22.' in version, version
    if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
    with tempfile.TemporaryDirectory(prefix='pool527-') as d:
        w=Path(d); before_root=w/'before';target=before_root/path;target.parent.mkdir(parents=True)
        target.write_text(after)
        fixture=ROOT/'test/fixtures/rpcs3_pool527.diff'
        subprocess.run(['git','apply','--reverse',str(fixture)],cwd=before_root,check=True)
        before=target.read_text()
        assert hashlib.sha256(target.read_bytes()).hexdigest()==BASE_SHA
        outputs={};commands={}
        for variant,text in [('before',before),('after',after)]:
            (w/'VKImagePool.inc').write_text('namespace vk {\n'+'\n'.join(block(text,m) for m in markers)+'\n}\n')
            common=cxx+['-std=c++20','-O3','-g','-Wall','-Wextra','-Werror','-pthread','-DRPCS3_IOS',
                '-I'+str(w),'-I'+str(source),str(ROOT/'test/native/rpcs3_pool527.cpp')]
            cmd=common+['-o',str(w/(variant+'-bin'))]
            if a.sanitize and not a.benchmark:cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
            subprocess.run(cmd,check=True);commands[variant]=cmd
            run=subprocess.run([str(w/(variant+'-bin'))]+(['--benchmark'] if a.benchmark else []),capture_output=True,text=True,timeout=180,
                env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
            if variant=='before' and not a.benchmark:
                assert run.returncode != 0 and 'Image-pool ownership/accounting assertion failed' in run.stderr,run.stdout+run.stderr
                outputs[variant]={'negative_control_failed_as_expected':True,'cause':'single300MiB retired image admitted before frame end'}
            else:
                if run.returncode:print(run.stdout,run.stderr);run.check_returncode()
                outputs[variant]=json.loads(run.stdout)
            if variant=='after' and not a.benchmark:
                subprocess.run(common+['-fno-exceptions','-fsyntax-only','-DPOOL_NO_EXCEPTIONS'],check=True)
        result=dict(passed=True,scope='production pool admission/frame/lookup/pressure/clear methods with logical Vulkan image adapters; no GPU/iPhone/game measurement',
            sanitizers=bool(a.sanitize and not a.benchmark),compiler=subprocess.check_output(cxx+['--version'],text=True).splitlines()[0],
            commands=commands,results=outputs,before_sha256=BASE_SHA,after_sha256=hashlib.sha256(after.encode()).hexdigest(),
            fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest())
        if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
if __name__=='__main__':main()
