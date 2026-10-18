#!/usr/bin/env python3
"""Exercise real pinned PicoDrive decode/set/apply/reset, without a core build.

Use --fetch or a directory containing patch.c, patch.h and libretro.c.
The real ROM mutation and patch logic run; the m68k bus is a bounded RAM
test double. This does not prove SH2 address equivalence or commercial games.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PIN='1890c2932234c9d30f4cd3851d02228baae8f09e'
META=ROOT/'test/unified_native_picodrive_vectors.json'


def function(text,name):
    start=text.index('void '+name+'('); end=text.index('{',start)+1; depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]


def check(source):
    metadata=json.loads(META.read_text())
    for name,wanted in metadata['source_sha256'].items():
        assert hashlib.sha256((source/name).read_bytes()).hexdigest()==wanted,name
    compiler=shutil.which('gcc') or shutil.which('clang');assert compiler
    with tempfile.TemporaryDirectory(prefix='unified-pico-test-') as tmp:
        work=Path(tmp);include=work/'include';include.mkdir()
        (include/'patch.h').write_bytes((source/'patch.h').read_bytes())
        (include/'pico_int.h').write_text('''#pragma once
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <stdbool.h>
#include <ctype.h>
typedef uint16_t u16;
#define PAHW_SMS (1<<4)
#define EL_STATUS 0
#define elprintf(...) ((void)0)
#define lprintf(...) ((void)0)
#define isspace_(c) isspace((unsigned char)(c))
struct PicoStub {unsigned char* rom;unsigned romsize;};extern struct PicoStub Pico;
struct InputStub {unsigned AHW;};extern struct InputStub PicoIn;
''')
        (include/'memory.h').write_text('#include <stdint.h>\nuint32_t m68k_read16(uint32_t);void m68k_write16(uint32_t,uint16_t);\n')
        original=(source/'libretro.c').read_text()
        (work/'entry.h').write_text(function(original,'retro_cheat_reset')+'\n'+function(original,'retro_cheat_set'))
        harness=r'''
#include <assert.h>
#include <stdarg.h>
#include "patch.c"
#include "LibretroPicoCheatDecoder.h"
typedef struct patch patch;
struct PicoStub Pico;struct InputStub PicoIn;static uint16_t ram[32768];
uint32_t m68k_read16(uint32_t a){assert(a>=0xFF0000&&a<=0xFFFFFE&&!(a&1));return ram[(a&0xFFFF)>>1];}
void m68k_write16(uint32_t a,uint16_t d){assert(a>=0xFF0000&&a<=0xFFFFFE&&!(a&1));ram[(a&0xFFFF)>>1]=d;}
static void log_cb(int a,const char* f,...){}
#define RETRO_LOG_ERROR 0
#include "entry.h"
int main(){
  Pico.romsize=0x400000;Pico.rom=calloc(1,Pico.romsize);assert(Pico.rom);
  const unsigned modes[]={0,1,2,8};
  for(unsigned mode=0;mode<4;mode++){
    PicoIn.AHW=modes[mode];ram[0x03B4/2]=0x1234;
    retro_cheat_set(0,false,"FF03B4:0060");assert(PicoPatchCount==1);
    PicoPatchApply();assert(ram[0x03B4/2]==0x1234);retro_cheat_reset();
    retro_cheat_set(0,true,"FF03B4:0060+FF03B4:0070");
    assert(PicoPatchCount==2&&PicoPatches[0].data==0x60&&PicoPatches[1].data==0x70);
    PicoPatchApply();assert(ram[0x03B4/2]==0x70);retro_cheat_reset();assert(ram[0x03B4/2]==0x1234);
  }
  PicoIn.AHW=2;*(uint16_t*)(Pico.rom+0xC8F4)=0x4567;
  retro_cheat_set(0,true,"AMEA-AA9Y");PicoPatchApply();assert(*(uint16_t*)(Pico.rom+0xC8F4)==0x6002);
  retro_cheat_reset();assert(*(uint16_t*)(Pico.rom+0xC8F4)==0x4567);
  // Separate calls append, ignore the index and do not apply ROM eagerly.
  // All calls in a host batch must therefore precede the next emulation frame.
  retro_cheat_set(0,true,"AMEA-AA9Y");retro_cheat_set(1,true,"00C8F4:7000");
  assert(PicoPatchCount==2&&PicoPatches[0].data_old==0x4567&&PicoPatches[1].data_old==0x4567);
  assert(*(uint16_t*)(Pico.rom+0xC8F4)==0x4567);
  PicoPatchApply();assert(*(uint16_t*)(Pico.rom+0xC8F4)==0x7000);
  retro_cheat_reset();assert(*(uint16_t*)(Pico.rom+0xC8F4)==0x4567);
  // Exercise the existing host's maximum 99 calls, each with 25 short tokens.
  // No additional patch quota is needed for this dynamically grown table.
  char batch[256];
  for(int i=0;i<99;i++){
    batch[0]=0;
    for(int j=0;j<25;j++){if(j)strcat(batch,"+");strcat(batch,i==98&&j==24?"00C8F4:7000":"AMEA-AA9Y");}
    assert(strlen(batch)<=255);retro_cheat_set(i,true,batch);
  }
  assert(PicoPatchCount==2475&&*(uint16_t*)(Pico.rom+0xC8F4)==0x4567);
  PicoPatchApply();assert(*(uint16_t*)(Pico.rom+0xC8F4)==0x7000);
  retro_cheat_reset();assert(*(uint16_t*)(Pico.rom+0xC8F4)==0x4567);
  const char* alphabet="ABCDEFGHJKLMNPRSTVWXYZ0123456789";
  srand(1543);
  for(int i=0;i<4096;i++){
    char code[12];for(int j=0;j<9;j++)code[j]=j==4?'-':alphabet[rand()%32];code[9]=0;
    struct patch actual;NeoPicoDecoded expected;decode(code,&actual);assert(NeoPicoDecodeMD(code,&expected));
    assert(actual.addr==expected.address&&actual.data==expected.value);
  }
  assert(NeoPicoMDTokenAllowed("FF03B4:0060",0));assert(NeoPicoMDTokenAllowed("AMEA-AA9Y",1));
  assert(!NeoPicoMDTokenAllowed("AMEA-AA9Y",0));assert(!NeoPicoMDTokenAllowed("FF8D67:0065",1));
  assert(!NeoPicoMDTokenAllowed("FF03B4:FFFF",1));assert(!NeoPicoMDTokenAllowed("06000000:0060",1));
  assert(!NeoPicoMDTokenAllowed("A15100:0001",1));assert(!NeoPicoMDTokenAllowed("FFFFFE:FFFF",1));
  assert(NeoPicoMDTokenAllowed("FFFFFE:0001",1));assert(NeoPicoMDTokenAllowed("3FFFFE:0001",1));
  assert(!NeoPicoMDTokenAllowed("400000:0001",1));
  PicoIn.AHW=16;struct patch sms;decode("C000:12",&sms);assert(sms.addr==0xFF0000);
  retro_cheat_set(0,true,"C000:12");PicoPatchApply();assert(ram[0]==0);retro_cheat_reset();
  free(Pico.rom);return 0;
}
'''
        (work/'driver.c').write_text(harness)
        subprocess.run([compiler,'-std=gnu11','-I',str(include),'-I',str(source),
                        '-I',str(ROOT/'packages/libretro_internal_bridge/ios/Classes'),
                        str(work/'driver.c'),'-o',str(work/'test')],check=True)
        subprocess.run([str(work/'test')],check=True)
    print('PASS: real PicoDrive decoder/set/apply/reset; shipping decoder4096vectors, maximum99batches/2475patches, overlapping ROM reset, no-op SMS RAM and rejected SH2/odd/FFFF.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',nargs='?',type=Path);parser.add_argument('--fetch',action='store_true');args=parser.parse_args()
    if bool(args.source)==args.fetch:parser.error('choose source or --fetch')
    if not args.fetch:check(args.source);return
    with tempfile.TemporaryDirectory(prefix='unified-pico-source-') as tmp:
        source=Path(tmp)
        def fetch(item):
            name,path=item
            with urllib.request.urlopen('https://raw.githubusercontent.com/libretro/picodrive/'+PIN+'/'+path,timeout=30) as response:data=response.read(1024*1024+1)
            assert len(data)<=1024*1024;(source/name).write_bytes(data)
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(fetch,{'patch.c':'pico/patch.c','patch.h':'pico/patch.h','libretro.c':'platform/libretro/libretro.c'}.items()))
        check(source)


if __name__=='__main__':main()
