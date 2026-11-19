#!/usr/bin/env python3
"""Exercise the shipped decoder, including an unknown content size (raw zstd block)."""
from pathlib import Path
import ctypes as C
import os
import subprocess
import tempfile

def main():
    repo=Path(os.getenv('RB_TEST_REPO',Path(__file__).resolve().parents[4]))
    with tempfile.TemporaryDirectory() as d:
        lib=Path(d)/'inflate.so'
        subprocess.run([os.getenv('CC','cc'),'-O2','-shared','-fPIC',str(repo/'native/s2arm/prepare/s2arm_zstd.c'),'-o',str(lib)],check=True)
        call=C.CDLL(str(lib)).rb_s2arm_shader_inflate
        call.argtypes=[C.c_void_p,C.c_size_t,C.POINTER(C.c_void_p),C.POINTER(C.c_size_t),C.c_size_t]
        free=C.CDLL(None).free
        free.argtypes=[C.c_void_p]
        def decode(blob,limit):
            out=C.c_void_p(42); size=C.c_size_t(42)
            if not call(blob,len(blob),C.byref(out),C.byref(size),limit):
                assert not out.value and size.value==0
                return None
            try: return C.string_at(out,size.value)
            finally: free(out)
        payload=b'actual shader resource'
        block=(len(payload)*8+1).to_bytes(3,'little')+payload
        for hdr in (bytes([0x20,len(payload)]),b'\x00\x00'):
            frame=bytes.fromhex('28b52ffd')+hdr+block
            assert decode(frame,len(payload))==payload
            for bad in (frame[:-1],frame+b'extra',frame[:7],b'',frame+frame):
                assert decode(bad,1024) is None
            assert decode(frame,len(payload)-1) is None
        huge=bytes.fromhex('28b52ffda0')+(1<<30).to_bytes(4,'little')+block
        assert decode(huge,1<<20) is None
        print('PASS shipped zstd shader decoder, declared/unknown size, truncation, trailing data, concatenation and allocation bounds')
        fd_decode=C.CDLL(str(lib)).rb_s2arm_shader_inflate_fd
        callback=C.CFUNCTYPE(C.c_int,C.c_void_p)
        fd_decode.argtypes=[C.c_void_p,C.c_size_t,C.c_int,C.c_uint64,callback,C.c_void_p,C.POINTER(C.c_uint64)]
        total=(65<<20)+71
        data=bytearray(bytes.fromhex('28b52ffd8050')+total.to_bytes(4,'little'))
        left=total
        while left:
            take=min(left,128<<10);left-=take
            data.extend((take*8+2+int(not left)).to_bytes(3,'little')+b'R')
        frame=bytes(data)
        def streamed(frame,limit,stop=lambda:False):
            with tempfile.TemporaryFile() as tmp:
                size=C.c_uint64(99);rc=fd_decode(frame,len(frame),tmp.fileno(),limit,callback(lambda _:int(stop())),None,C.byref(size))
                assert tmp.seek(0,2)==size.value
                if rc==1:
                    tmp.seek(0)
                    assert all(chunk==b'R'*len(chunk) for chunk in iter(lambda:tmp.read(65536),b''))
                else: assert size.value==0
                return rc,size.value
        assert streamed(frame,total)==(1,total)
        assert streamed(frame,total-1)==(-2,0)
        assert streamed(frame[:-1],total)==(0,0)
        assert streamed(frame+b'!',total)==(0,0)
        calls=[0]
        def stop():
            calls[0]+=1
            return calls[0]==5
        assert streamed(frame,total,stop)==(-1,0) and calls[0]==5
        assert streamed(frame[:5]+b'\xa8'+frame[6:],total)==(-2,0)
        # A valid header can name a dictionary without containing its bytes.
        assert streamed(frame[:4]+b'\x81\x50\x07'+frame[6:],total)==(-3,0)
        print('PASS streamed 65 MiB zstd with 1 MiB window, cancellation/truncation cleanup, disk quota, dictionary and history limits')
if __name__=='__main__': main()
