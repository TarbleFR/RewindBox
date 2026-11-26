"""Compare actual C routines from two already-patched S2Arm trees. No Metal calls."""
import argparse
from pathlib import Path
from statistics import median
import subprocess
import tempfile


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index("\n}", start) + 2]


def build(root, path):
    inc = root / "graphics/nvn/gfx/nvn"
    source = (inc / "nvn_mtl.m").read_text()
    compact = "static uint64_t g_pp_used[" in source
    routine = function(source, "static int pso_pend_find_live(const pso_key *live)\n{")
    code = """
#include <stdio.h>
#include <time.h>
#include <pthread.h>
#include <stdatomic.h>
#include "nvn_hmap.h"
#include "nvn_pso_skey.h"
#define MIN(a,b) ((a)<(b)?(a):(b))
#define PSO_PEND_MAX 384
typedef struct { uint64_t bits[8], h[512]; } gpw_blk;
static nvn_hmap g_gpw = {.klen=8};
static pthread_mutex_t g_gpw_mu = PTHREAD_MUTEX_INITIALIZER;
static _Atomic uint64_t g_gpw_nblk;
static uint64_t g_gpw_gen;
static uint64_t g_pp_used[6];
static struct { pso_key k; void *ps, *error; int used, done, late, stuck;
                uint8_t way; uint64_t began, build, compile; pthread_t worker; } g_pp[384];
"""
    layout = (inc / "nvn_pso_skey.h").read_text().split("} pso_key;", 1)[0]
    code = code.replace('#include "nvn_pso_skey.h"', layout.replace("#pragma once", "") + "} pso_key;")
    if compact:
        code = code.replace("int used, done", "int done")
    code += function(source, "static void gpw_unmark(uint64_t g) {")
    code += function(source, "static void gpw_clear(uint64_t lo, uint64_t n) {")
    if compact:
        for name in ("pp_claim", "pp_release"):
            code += function(source, "static inline void " + name + "(")
    code += routine
    code += """
static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}
int main(void) {
    const unsigned loads[] = {0,4,64,384};
    for (unsigned j=0; j<4; j++) {
        for (unsigned i=0; i<384; i++) {
            int occupied = (i * 101 % 384) < loads[j];
            SET_OCCUPIED;
            g_pp[i].k.samples = i + 1;
        }
        unsigned sum=0;
        double start=now();
        for (unsigned q=0; q<80000; q++) {
            pso_key key={0};
            key.samples = (q * 12347u) % 768 + 1;
            sum += pso_pend_find_live(&key) + 1;
        }
        printf("slots%u %u %.6f\\n", loads[j], sum, now()-start);
    }
    for (unsigned j=0; j<3; j++) {
        uint64_t digest=0;
        double elapsed=0;
        for (unsigned iter=0; iter<1200; iter++) {
            for (uint64_t k=0; k<8; k++) {
                gpw_blk *b=calloc(1,sizeof *b);
                if (!b) abort();
                for (int w=0; w<8; w++)
                    b->bits[w] = (iter % 2) ? UINT64_MAX : 0x8040201008040201ULL;
                nvn_hm_put(&g_gpw, &k, b);
                g_gpw_nblk++;
            }
            unsigned long long addr=(iter*23467u) % 260000;
            const unsigned bytes[]={1,4111,1499800};
            double start=now();
            gpw_clear(addr, bytes[j]);
            elapsed += now()-start;
            digest = digest*31 + g_gpw_gen + atomic_load(&g_gpw_nblk);
            for (uint64_t k=0; k<8; k++) {
                gpw_blk *b=nvn_hm_get(&g_gpw,&k);
                if (b) for (int w=0; w<8; w++) digest = digest*31 + b->bits[w];
            }
            nvn_hm_clear(&g_gpw, free);
            g_gpw_nblk = 0;
        }
        printf("clear%u %llu %.6f\\n",j,(unsigned long long)digest,elapsed);
    }
}
"""
    path.with_suffix(".c").write_text(code.replace("SET_OCCUPIED", "if (occupied) pp_claim(i); else pp_release(i)" if compact else "g_pp[i].used = occupied"))
    subprocess.run(["clang", "-O2", "-pthread", "-I", inc, "-I", inc/"include",
                    path.with_suffix(".c"), "-o", path], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trees", nargs=2, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        results = [{}, {}]
        hashes = {}
        for idx, tree in enumerate(args.trees):
            build(tree, Path(temp)/str(idx))
        for repeat in range(8):
            for idx in (range(2) if repeat % 2 == 0 else (1, 0)):
                output = subprocess.check_output([Path(temp)/str(idx)], text=True)
                for line in output.splitlines():
                    label, digest, seconds = line.split()
                    if hashes.setdefault(label, digest) != digest:
                        raise ValueError(f"divergence in {label}")
                    results[idx].setdefault(label, []).append(1000 * float(seconds))
        for label, digest in hashes.items():
            print(label, digest, *(round(median(r[label]), 3) for r in results))


if __name__ == "__main__":
    main()
