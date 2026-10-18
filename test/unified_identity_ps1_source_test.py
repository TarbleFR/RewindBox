"""Offline tests of pinned Beetle PSX decoder and periodic cheat application.

The fixture contains unmodified GPL-2.0-or-later primary source fragments.
Only RAM callbacks, patch storage, libc helpers and test inputs are supplied
by this harness. It does not execute Apple cores, games or ROMs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

FIXTURE = Path(__file__).parent / "fixtures/unified_cheats/ps1-primary-memory.json"
COMMIT = "10e4b0c6ceae20daa65ddf436a4445dddd0982d2"
SOURCE_HASHES = {'libretro.c': '9923fe0bc41904291b04c378309bb8361114d24042b2f7e46a36d2c5436dbf3d', 'mednafen/mempatcher.c': 'df073b271f9d8b96cd91e10be6cc4bd71f2376b99ef7fd40a28dd4c7ac53b179', 'mednafen/mempatcher-driver.h': '0132d7eae8c5045a1c55d070e8fa6f16df036eababcc2a5a0ca1af5802a924ce'}
PRELUDE = r"""
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <assert.h>
#define strlcpy NUCPS1FixtureStrlcpy
#define strlcat NUCPS1FixtureStrlcat
static size_t strlcpy(char *d,const char *s,size_t n) {size_t z=strlen(s);if(n){size_t k=z<n-1?z:n-1;memcpy(d,s,k);d[k]=0;}return z;}
static size_t strlcat(char*d,const char*s,size_t n) {size_t z=strnlen(d,n);if(z==n)return n+strlen(s);return z+strlcpy(d+z,s,n-z);}
static void log_cb(int level,const char *fmt,...) {(void)level;(void)fmt;}
#define RETRO_LOG_ERROR 0
#define ISHEXDEC ((codeLine[cursor]>='0') && (codeLine[cursor]<='9')) || ((codeLine[cursor]>='a') && (codeLine[cursor]<='f')) || ((codeLine[cursor]>='A') && (codeLine[cursor]<='F'))

"""
SUPPORT = r"""typedef struct {const char*name;const char*desc;bool (*DecodeCheat)(const char*,MemoryPatch*);} CheatFormatStruct;
static MemoryPatch cheats[64];static size_t cheats_count;static bool CheatsActive=true;
static uint8_t ram[0x200000];
static uint8_t PSX_MemPeek8(uint32_t a){assert(a<sizeof(ram));return ram[a];}
static void PSX_MemPoke8(uint32_t a,uint8_t v){assert(a<sizeof(ram));ram[a]=v;}
static void MDFNI_AddCheat(const MemoryPatch*p){assert(cheats_count<64);cheats[cheats_count++]=*p;}
"""
CASES = r"""
static void reset(void){memset(ram,0,sizeof(ram));cheats_count=0;}
static void run(const char*c){retro_cheat_set(0,true,c);MDFNMP_ApplyPeriodicCheats();}
int main(void){
 unsigned tests=0;
 // Each real decoder D/E comparison gates the immediately following write.
 const unsigned values[4]={0x1234,0x1235,0x1233,0x1235};
 const unsigned compare[4]={0x1234,0x1234,0x1234,0x1234};
 const unsigned failed[4]={0x1235,0x1234,0x1235,0x1233};
 for(unsigned mode=0;mode<4;mode++)for(unsigned byte=0;byte<2;byte++)for(unsigned pass=0;pass<2;pass++){
  reset();unsigned v=pass?values[mode]:failed[mode];ram[0x100]=v;ram[0x101]=v>>8;
  char c[64];snprintf(c,sizeof(c),"%02X000100 %04X+30000200 0077",(byte?0xE0:0xD0)+mode,compare[mode]&(byte?0xFF:0xFFFF));
  run(c);assert(cheats_count==1);assert(ram[0x200]==(pass?0x77:0));tests++;
 }
 // Conditional scope ends at the write, independent writes remain independent.
 reset();run("D0000100 1234+30000200 0077+30000201 0066");assert(ram[0x200]==0&&ram[0x201]==0x66);tests++;
 // Repeat count, address step, value step, full-word carry and byte wrap are actual code.
 reset();run("50000402 0001+80000300 00FE");assert(cheats_count==1);for(unsigned i=0;i<4;i++){assert(ram[0x300+i*2]==((0xFE + i)&255));assert(ram[0x301+i*2]==((0xFE + i)>>8));}tests++;
 reset();run("50000301 0001+30000300 00FE");assert(ram[0x300]==0xFE&&ram[0x301]==0xFF&&ram[0x302]==0);tests++;
 // Combined condition + repeater stays a single patch / toggle.
 reset();ram[0x100]=1;run("E0000100 0001+50000301 0001+30000300 0005");assert(cheats_count==1&&ram[0x300]==5&&ram[0x302]==7);tests++;
 reset();run("E0000100 0001+50000301 0001+30000300 0005");assert(cheats_count==1&&ram[0x300]==0&&ram[0x302]==0);tests++;
 // Engine intentionally masks repeat increment to 8bits: adaptation MUST reject >00FF.
 reset();run("50000201 0101+30000300 0005");assert(ram[0x300]==5&&ram[0x301]==6);tests++;
 // No writes when disabled, despite completed patch.
 reset();retro_cheat_set(0,false,"D0000100 0000+30000200 0077");MDFNMP_ApplyPeriodicCheats();assert(ram[0x200]==0);tests++;
 // 19 canonical lines is 246 bytes, well below 64 hex token capacity.
 reset();char joined[256]={0};for(unsigned i=0;i<19;i++){char c[16];snprintf(c,sizeof(c),"%s300004%02X00AA",i?"+":"",i);strlcat(joined,c,sizeof(joined));}assert(strlen(joined)==246);run(joined);assert(cheats_count==19);for(unsigned i=0;i<19;i++)assert(ram[0x400+i]==0xAA);tests++;
 printf("PASS %u primary PS1 decoder/memory behaviors; source10e4b0c; no ROM, no gameplay\n",tests);
}
"""


class PS1PrimarySourceTests(unittest.TestCase):
    def test_pinned_primary_fragments_and_license(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(fixture["commit"], COMMIT)
        self.assertEqual({row["path"]: row["sha256"] for row in fixture["source_files"]}, SOURCE_HASHES)
        self.assertEqual(fixture["license"]["identifier"], "GPL-2.0-or-later")
        license_file = FIXTURE.with_name(fixture["license"]["path"])
        self.assertTrue(license_file.is_file())
        self.assertIn("GNU GENERAL PUBLIC LICENSE", license_file.read_text())
        self.assertEqual(hashlib.sha256(license_file.read_bytes()).hexdigest(), fixture["license"]["sha256"])
        expected_names = {"memory_patch_definition", "memory_patch_init", "gs_condition", "decode_gs", "retro_cheat_set", "test_conditions", "apply_periodic"}
        self.assertEqual(set(fixture["fragments"]), expected_names)
        for row in fixture["fragments"].values():
            self.assertEqual(hashlib.sha256(row["source"].encode()).hexdigest(), row["sha256"])

    def test_24_real_decoder_and_memory_behaviors(self):
        compiler = shutil.which("clang") or shutil.which("cc")
        self.assertIsNotNone(compiler, "A C compiler is required for the primary-source behavior probe")
        fixture = json.loads(FIXTURE.read_text())
        f = {name: row["source"] for name, row in fixture["fragments"].items()}
        source = PRELUDE + f["memory_patch_definition"] + SUPPORT
        for name in ("memory_patch_init", "gs_condition", "decode_gs"):
            source += "\n" + f[name]
        source += '\nstatic CheatFormatStruct CheatFormats[]={{"GameShark","",DecodeGS}};\n'
        for name in ("retro_cheat_set", "test_conditions", "apply_periodic"):
            source += "\n" + f[name]
        source += CASES
        with tempfile.TemporaryDirectory(prefix="unified-ps1-primary-") as temporary:
            work = Path(temporary)
            c_file, executable = work / "probe.c", work / "probe"
            c_file.write_text(source)
            result = subprocess.run([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-O1", "-g", "-fsanitize=address,undefined", str(c_file), "-o", str(executable)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            environment = dict(os.environ, ASAN_OPTIONS="detect_leaks=0")
            result = subprocess.run([str(executable)], env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS 24 primary PS1 decoder/memory behaviors", result.stdout)
            print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
