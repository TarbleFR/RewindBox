#!/usr/bin/env python3
"""Generate genuine NVN2/GLSLC-SARC data and exercise the shipped Apple binaries.

Called by test_native_stage_recovery.sh with its published NativeAOT translator,
Metal fragment runner, t_dsh_stats and the same zstd decoder as S2ArmPrepare.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import struct
import plistlib
import os
import shutil
import subprocess
import tempfile

def glslc(ctl,code):
    start=0x140
    out=bytearray(start+len(ctl)+len(code))
    struct.pack_into('<I',out,0,0x19866891)
    struct.pack_into('<I',out,8,0x00220015)
    struct.pack_into('<III',out,0x5c,len(out),start,1)
    struct.pack_into('<III',out,0xa8,len(ctl)+len(code),start,0)
    struct.pack_into('<IIII',out,0xd8,0,len(ctl),len(code),len(ctl))
    out[start:]=ctl+code
    return bytes(out)

def archive(blob):
    # One nameless SARC entry, legal little-endian 1.0 header.
    a=bytearray(0x40)
    a[:4]=b'SARC'
    struct.pack_into('<HHIIHH',a,4,0x14,0xfeff,len(a)+len(blob),len(a),0x100,0)
    a[0x14:0x18]=b'SFAT'
    struct.pack_into('<HHI',a,0x18,12,1,0x65)
    struct.pack_into('<IIII',a,0x20,0,0,0,len(blob))
    a[0x30:0x34]=b'SFNT'
    struct.pack_into('<HH',a,0x34,8,0)
    frame=bytes(a)+blob
    # zstd frame with a standard raw block. It needs the real decoder even
    # though the payload is intentionally incompressible for the test.
    return (bytes.fromhex('28b52ffd60')+struct.pack('<H',len(frame)-256)
            +(len(frame)*8+1).to_bytes(3,'little')+frame)

def large_resources(program):
    """Two legal resources with one real program and >64 MiB decoded payload."""
    size=(65<<20)+len(program)
    frame=bytearray(bytes.fromhex('28b52ffd8050')+size.to_bytes(4,'little'))
    frame.extend((len(program)*8).to_bytes(3,'little')+program)
    rest=size-len(program)
    while rest:
        n=min(rest,128<<10); rest-=n
        frame.extend((n*8+2+(not rest)).to_bytes(3,'little')+b'\x00')
    yaz=bytearray(b'Yaz0'+size.to_bytes(4,'big')+bytes(8))
    prefix=program+bytes(8-len(program)%8)
    for i in range(0,len(prefix),8):
        yaz.extend(b'\xff'+prefix[i:i+8])
    remain=size-len(prefix)
    while remain:
        ops=bytearray(); flags=0
        for j in range(8):
            if not remain: break
            n=min(remain,273)
            if n>=18: ops.extend([0,0,n-18])
            elif n>=3: ops.extend([(n-2)<<4,0])
            else: flags|=128>>j; ops.append(0); n=1
            remain-=n
        yaz.append(flags);yaz.extend(ops)
    return bytes(frame),bytes(yaz)

def run(tool,game,wire,profile,dsh,decoder):
    cp=subprocess.run([str(tool),'--rb-local-stages',str(game),str(wire),str(profile),str(dsh),str(decoder)],
                      text=True,stdout=subprocess.PIPE,check=True)
    print(cp.stdout,end='')
    return tuple(map(int,next(l[7:] for l in cp.stdout.splitlines() if l.startswith('STAGES ')).split()))

def main():
    p=argparse.ArgumentParser()
    for name in ['source','tool','dsh','decoder','pixel','red']: p.add_argument(name,type=Path)
    a=p.parse_args()
    spec=importlib.util.spec_from_file_location('ampere',a.source/'tests/ampere_isa/cases.py')
    ampere=importlib.util.module_from_spec(spec);spec.loader.exec_module(ampere)
    code,ctl=ampere.shader([ampere.MOVI(i,v) for i,v in enumerate([42,7,99,1])])
    key=hashlib.sha256(ctl[:0x48]+code).hexdigest()[:16]
    other='1111111111111111'
    with tempfile.TemporaryDirectory() as temp:
        base=Path(temp); game=base/'pack'; rom=base/'export'/'romfs'; rom.mkdir(parents=True)
        facts=game/'shaders'/'direct';facts.mkdir(parents=True)
        (game/'romfs').symlink_to(rom,target_is_directory=True)
        (facts/'shader_facts.tsv').write_text(key+'\t{"fout":{"0":"uint"}}\n')
        (facts/'shader_pairs.tsv').write_text('')
        shader=rom/'menu.sarc.zs';shader.write_bytes(archive(glslc(ctl,code)))
        fmt=lambda path: f'romfs/{path.name}\t{path.stat().st_size}\t{hashlib.sha256(path.read_bytes()).hexdigest()}\n'
        (game/'index.tsv').write_text(fmt(shader))
        wire=base/'wire'; shaders=wire/'shaders'; shaders.mkdir(parents=True)
        profile=wire/'pso_reference.tsv'
        profile.write_text(f'S\t{key}_b\t1\nS\t{other}_b\t1\nS\t{key}_b\t1\n')
        def check_case(w,counts):
            assert run(a.tool,game,w,profile,a.dsh,a.decoder)==counts
        check_case(wire,(2,0,0,1,1,1,0,1))
        msl=shaders/(key+'_b.metal'); sin=shaders/(key+'_b.in')
        assert sin.read_bytes()==struct.pack('<4I',0x314e4953,1,len(ctl),len(code))+ctl+code
        assert not (shaders/(other+'_b.in')).exists()
        rgba=subprocess.check_output([str(a.pixel),str(msl)],text=True).strip()
        assert rgba=='0000002a 00000007 00000063 00000001',rgba
        # Compatible launch, zero translations and no asset read. The probe
        # below would have appeared as unreadable if the resource was reopened.
        stamp=msl.stat().st_mtime_ns
        off=shader.with_suffix('.off');shader.rename(off)
        check_case(wire,(2,1,0,0,1,0,0,1))
        assert msl.stat().st_mtime_ns==stamp
        off.rename(shader)
        # 794-style history without any profile. Both old reflections are stale,
        # but only the real input can be recovered. Truncate the index record
        # to exercise restart of an interrupted write.
        wire2=base/'wire2'; out2=wire2/'shaders';out2.mkdir(parents=True)
        (wire2/'pso_user.tsv').write_bytes(profile.read_bytes())
        (wire2/'stage-index-v1.tsv').write_bytes((wire/'stage-index-v1.tsv').read_bytes()[:43])
        for k in [key,other]: (out2/(k+'_b.json')).write_text('{"xfp":"previous-build","stage":"ps"}')
        profile=base/'absent-profile'
        check_case(wire2,(2,0,0,1,1,1,0,1))
        rows=(wire2/'stage-recovery.tsv').read_text()
        assert key+'\tstale\tresource\ttranslated' in rows and other+'\tstale\tunavailable\tmissing' in rows
        assert msl.read_bytes()==(out2/(key+'_b.metal')).read_bytes()
        (out2/(key+'_b.metal')).unlink()
        check_case(wire2,(2,0,1,0,1,1,0,1))
        print('PASS RomFS symlink, zstd/SARC/GLSLC, fresh/794 history, interrupted index, hot run and exact RGBA32Uint '+rgba)
        def imported_generation(name,has_input=True,priority=True):
            target=base/name; target_src=target/'shaders'; target_src.mkdir(parents=True)
            for ext in ['metal','json']+(['in'] if has_input else []):
                src=shaders/f'{key}_b.{ext}'; shutil.copyfile(src,target_src/src.name)
            # A fully valid MSL source with the same translator fingerprint.
            live=target_src/msl.name
            live.write_bytes(live.read_bytes()+b'\n// marker from a compatible 794 generation\n')
            marker=live.read_bytes()
            listed=target/'pso_user.tsv'; listed.write_text(f'S\t{key}_b\t1\n')
            return target,listed if priority else target/'unused-profile',live,marker

        candidate,listed,live,marker=imported_generation('negative-0130')
        assert run(a.red,game,candidate,listed,a.dsh,a.decoder)==(1,1,0,0,0,0,0,1)
        assert live.read_bytes()==marker and not (candidate/'priority-stages-v1').exists()
        print('RED 0130 retained a compatible 794 MSL without invoking the native translator')

        candidate,listed,live,marker=imported_generation('generation-795')
        interrupt=subprocess.run([str(a.tool),'--rb-local-stages',str(game),str(candidate),str(listed),str(a.dsh),str(a.decoder)],
                                 env={**os.environ,'RB_TEST_CANCEL_AT_PRIORITY_PRODUCT':key},
                                 capture_output=True,text=True)
        print(interrupt.stdout,end='')
        assert interrupt.returncode==1 and 'STAGES 1 1 0 0 0 1 0 1' in interrupt.stdout
        assert (candidate/'priority-stages-v1'/key/'receipt.plist').is_file() and live.read_bytes()==marker
        assert run(a.tool,game,candidate,listed,a.dsh,a.decoder)==(1,1,0,0,0,0,0,1)
        assert live.read_bytes()==msl.read_bytes()
        assert 'priority-checkpoint' in (candidate/'stage-recovery.tsv').read_text()
        timestamp=live.stat().st_mtime_ns
        assert run(a.tool,game,candidate,listed,a.dsh,a.decoder)==(1,1,0,0,0,0,0,1)
        assert live.stat().st_mtime_ns==timestamp
        assert subprocess.check_output([str(a.pixel),str(live)],text=True).strip()==rgba

        candidate,listed,live,marker=imported_generation('history-only',priority=False)
        assert run(a.tool,game,candidate,listed,a.dsh,a.decoder)==(1,1,0,0,0,0,0,1)
        assert live.read_bytes()==marker and not (candidate/'priority-stages-v1').exists()

        candidate,listed,live,marker=imported_generation('no-original',has_input=False)
        no_assets=base/'no-assets';no_assets.mkdir()
        (no_assets/'index.tsv').write_text('')
        assert run(a.tool,no_assets,candidate,listed,a.dsh,a.decoder)==(1,1,0,0,0,0,0,0)
        assert live.read_bytes()==marker and 'preserved-no-input' in (candidate/'stage-recovery.tsv').read_text()
        print('GREEN NativeAOT retranslated one compatible priority stage, resumed before publication, emitted exact pixels; missing inputs and nonpriority MSL preserved')
        spill_game=base/'bigpack'; sr=spill_game/'romfs';sr.mkdir(parents=True)
        shutil.copytree(facts,spill_game/'shaders'/'direct')
        big_z,big_y=large_resources(glslc(ctl,code))
        (sr/'first-entry.zs').write_bytes(big_z)
        (sr/'second-entry.szs').write_bytes(big_y)
        (sr/'bad.zs').write_bytes(bytes.fromhex('28b52ffd0000'))
        (sr/'dict.zs').write_bytes(big_z[:4]+b'\x81\x50\x07'+big_z[6:])
        (sr/'quota.zs').write_bytes(big_z[:6]+(3<<30).to_bytes(4,'little')+big_z[10:])
        (spill_game/'index.tsv').write_text(''.join(fmt(f) for f in sorted(sr.iterdir())))
        big_wire=base/'large-wire';big_wire.mkdir()
        big_profile=big_wire/'pso_reference.tsv'
        big_profile.write_text(f'S\t{key}_b\t1\nS\t{other}_b\t1\n')
        counts=run(a.tool,spill_game,big_wire,big_profile,a.dsh,a.decoder)
        assert counts==(2,0,0,1,1,1,0,2),counts
        cov=plistlib.loads((big_wire/'stage-scan-coverage.plist').read_bytes())
        assert (cov['spooled'],cov['unavailableDictionary'],cov['corrupt'],cov['resourceLimits'],cov['ioErrors'])==(2,1,1,1,0),cov
        assert 'not-located-in-partial-scan' in (big_wire/'stage-recovery.tsv').read_text()
        assert not list(big_wire.glob('.stage-inflate-*'))
        assert subprocess.check_output([str(a.pixel),str(big_wire/'shaders'/msl.name)],text=True).strip()==rgba
        print('PASS second process read the true large zstd/Yaz0 stage through the production decoder, strict coverage reasons and exact pixel '+rgba)
if __name__=='__main__': main()
