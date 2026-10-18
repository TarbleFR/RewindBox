"""Pinned primary Beetle PCE/WonderSwan parsers and periodic RAM writers.

This runs extracted, unmodified primary C functions with allocated RAM. It
does not run Apple binaries or ROMs. PCE's source revision is correlated
with the delivered binary, which does not embed its source commit.
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

FIXTURE = Path(__file__).parent / "fixtures/unified_cheats/pce-wswan-primary-memory.json"
PRELUDE = r"""
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
typedef uint8_t uint8;
typedef uint32_t uint32;
typedef uint64_t uint64;
#define INLINE inline
#define RETRO_LOG_DEBUG 0
#define RETRO_LOG_WARN 2
static void log_sink(int level,const char *format,...) {(void)level;(void)format;}
static void (*log_cb)(int,const char*,...) = log_sink;
static bool MDFN_GetSettingB(const char *name) {(void)name;return true;}
"""
PCE_SUPPORT = r"""
#define strlcpy NUCPCEFixtureStrlcpy
static size_t strlcpy(char *d,const char *s,size_t n) {
 size_t z=strlen(s);if(n){size_t k=z<n-1?z:n-1;memcpy(d,s,k);d[k]=0;}return z;
}
// Periodic R writes never use read-substitution patches or conditions.
static void RebuildSubCheats(void) {}
static void MDFNMP_RemoveReadPatches(void) {}
static void MDFNMP_InstallReadPatches(void) {}
static bool TestConditions(const char *conditions) {
 (void)conditions;assert(!"Unexpected conditional path");return false;
}
"""
PCE_CASES = r"""
static uint8 ram[8192],cd_ram[0x40000];
static void reset(void) {
 retro_cheat_reset();memset(ram,0,sizeof(ram));memset(cd_ram,0,sizeof(cd_ram));
}
static void run(const char *code) {
 retro_cheat_set(0,true,code);MDFNMP_ApplyPeriodicCheats();
}
int main(void) {
 unsigned tests=0;
 assert(MDFNMP_Init(1024,0x200000/1024));
 MDFNMP_AddRAM(sizeof(ram),0x1F0000,ram);
 MDFNMP_AddRAM(sizeof(cd_ram),0x0D0000,cd_ram);
 reset();run("1F1548:64");assert(ram[0x1548]==0x64);tests++;
 reset();run("1F0000:AA+1F1FFF:BB");assert(ram[0]==0xAA&&ram[8191]==0xBB);tests++;
 reset();run("F82000:12+F83FFF:34");assert(ram[0]==0x12&&ram[8191]==0x34);tests++;
 reset();run("100000:56+10FFFF:78");assert(cd_ram[0x30000]==0x56&&cd_ram[0x3FFFF]==0x78);tests++;
 reset();run("0D0000:9A+0FFFFF:BC");assert(cd_ram[0]==0x9A&&cd_ram[0x2FFFF]==0xBC);tests++;
 reset();run("1F1548:64+1F155A:02+1F1549:40");assert(cheats_count==3&&ram[0x1548]==0x64&&ram[0x155A]==2&&ram[0x1549]==0x40);tests++;
 reset();run("1F0000:01+1F0000:02");assert(cheats_count==2&&ram[0]==2);tests++;
 reset();run("1F2000:FF+FFFFFF:FF");assert(cheats_count==0);tests++;
 reset();run("1F0000:AB");ram[0]=0;MDFNMP_ApplyPeriodicCheats();assert(ram[0]==0xAB);tests++;
 retro_cheat_reset();ram[0]=0;MDFNMP_ApplyPeriodicCheats();assert(ram[0]==0&&cheats_count==0);tests++;
 // 25 complete canonical lines fit the actual 256-byte copy (249 bytes).
 reset();char bounded[256]={0};
 for(unsigned i=0;i<25;i++){char c[16];snprintf(c,sizeof(c),"%s1F%04X:AA",i?"+":"",i);strcat(bounded,c);}
 assert(strlen(bounded)==249);run(bounded);assert(cheats_count==25&&ram[24]==0xAA);tests++;
 // Native truncates long calls: the host must batch complete independent writes.
 reset();char too_long[300];snprintf(too_long,sizeof(too_long),"%s+1F0019:BB",bounded);
 assert(strlen(too_long)==259);run(too_long);assert(cheats_count==25&&ram[25]==0);tests++;
 // Complete independent writes append across calls, before the next frame.
 reset();retro_cheat_set(0,true,bounded);retro_cheat_set(1,true,"1F0019:BB");
 MDFNMP_ApplyPeriodicCheats();assert(cheats_count==26&&ram[24]==0xAA&&ram[25]==0xBB);tests++;
 // Call boundaries retain overlap order; a later write still wins.
 reset();retro_cheat_set(0,true,bounded);retro_cheat_set(1,true,"1F0000:CC+1F0019:BB");
 MDFNMP_ApplyPeriodicCheats();assert(cheats_count==27&&ram[0]==0xCC&&ram[25]==0xBB);tests++;
 printf("PASS %u primary PCE parser/RAM writer behaviors; no Apple/gameplay\n",tests);
 retro_cheat_reset();free(cheats);free(RAMPtrs);return 0;
}
"""
WS_SUPPORT = r"""
static uint32 SRAMSize;
"""
WS_CASES = r"""
static uint8 ram[65536],sram[8192];
static void reset(void) {
 retro_cheat_reset();memset(ram,0,sizeof(ram));memset(sram,0,sizeof(sram));SRAMSize=0;
}
static void run(const char *code) {
 retro_cheat_set(0,true,code);MDFNMP_ApplyPeriodicCheats();
}
int main(void) {
 unsigned tests=0;
 assert(MDFNMP_Init(16384,0x100000/16384));
 MDFNMP_AddRAM(sizeof(ram),0,ram);MDFNMP_AddRAM(sizeof(sram),0x10000,sram);
 reset();run("1E24:09");assert(cheat_count==1&&ram[0x1E24]==9);tests++;
 reset();run("0000:12+FFFF:34");assert(ram[0]==0x12&&ram[65535]==0x34);tests++;
 reset();run("1E24:01+1E24:02");assert(cheat_count==2&&ram[0x1E24]==2);tests++;
 reset();run("001E24:09");assert(cheat_count==0);tests++;
 reset();run("4474943:EB");assert(cheat_count==0);tests++;
 reset();run("10000:FF");assert(cheat_count==0&&sram[0]==0);tests++;
 reset();SRAMSize=sizeof(sram);run("10000:11+11FFF:22+12000:33");assert(cheat_count==2&&sram[0]==0x11&&sram[8191]==0x22);tests++;
 reset();run("1E24:09+FFFF:ABC+FFFF:GG+FFFF:FFx");assert(cheat_count==1);tests++;
 reset();retro_cheat_set(0,false,"1E24:09");MDFNMP_ApplyPeriodicCheats();assert(cheat_count==0&&ram[0x1E24]==0);tests++;
 reset();run("1E24:09");ram[0x1E24]=0;MDFNMP_ApplyPeriodicCheats();assert(ram[0x1E24]==9);tests++;
 retro_cheat_reset();ram[0x1E24]=0;MDFNMP_ApplyPeriodicCheats();assert(cheat_count==0&&ram[0x1E24]==0);tests++;
 // This streaming native parser preserves complete programs beyond 255 bytes.
 reset();char large[2048]={0};
 for(unsigned i=0;i<128;i++){char c[16];snprintf(c,sizeof(c),"%s%04X:AB",i?"+":"",i);strcat(large,c);}
 assert(strlen(large)==1023);run(large);assert(cheat_count==128&&ram[127]==0xAB);tests++;
 printf("PASS %u primary WonderSwan parser/RAM writer behaviors; no Apple/gameplay\n",tests);
 MDFNMP_Kill();return 0;
}
"""


class PCEWonderSwanPrimaryTests(unittest.TestCase):
    def test_primary_fragment_integrity(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(fixture["schema_version"], 1)
        license_file = FIXTURE.with_name(fixture["license"]["path"])
        self.assertEqual(hashlib.sha256(license_file.read_bytes()).hexdigest(), fixture["license"]["sha256"])
        self.assertEqual({row["pin"] for row in fixture["sources"]}, {
            "3f946f277aef3aa99a95551618bbcd1dd2bda0d9", "4b01295838ea89e3f1355bbe4cb5cf98aa6108cd"})
        for row in fixture["fragments"].values():
            self.assertEqual(hashlib.sha256(row["source"].encode()).hexdigest(), row["sha256"])

    def test_real_parsers_and_periodic_ram_writers(self):
        compiler = shutil.which("clang") or shutil.which("cc")
        self.assertIsNotNone(compiler, "A C compiler is required")
        fixture = json.loads(FIXTURE.read_text())
        fragments = {name: row["source"] for name, row in fixture["fragments"].items()}
        pce_order = ("pce_globals", "pce_push", "pce_add_entry", "pce_add_cheat", "pce_init", "pce_add_ram", "pce_apply", "pce_flush", "pce_set", "pce_reset")
        ws_order = ("ws_memory", "ws_digit", "ws_separator", "ws_set", "ws_reset")
        programs = {"pce": PRELUDE + PCE_SUPPORT + "\n".join(fragments[key] for key in pce_order) + PCE_CASES,
                    "ws": PRELUDE + WS_SUPPORT + "\n".join(fragments[key] for key in ws_order) + WS_CASES}
        with tempfile.TemporaryDirectory(prefix="unified-pce-ws-primary-") as temporary:
            work = Path(temporary)
            for name, source in programs.items():
                c_file, executable = work / (name + ".c"), work / name
                c_file.write_text(source)
                result = subprocess.run([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", "-O1", "-g", "-fsanitize=address,undefined", str(c_file), "-o", str(executable)], capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                result = subprocess.run([str(executable)], env=dict(os.environ, ASAN_OPTIONS="detect_leaks=0"), capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS " + ("14" if name == "pce" else "12") + " primary", result.stdout)
                print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
