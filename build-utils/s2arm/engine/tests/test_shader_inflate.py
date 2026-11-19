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
if __name__=='__main__': main()
