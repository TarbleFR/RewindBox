"""Replay the synthetic feedback-wrapper bench on prepared S2Arm trees with Clang on Linux or macOS."""
import argparse
import csv
import os
import random
import statistics
import subprocess
import tempfile
from pathlib import Path


def build(tree, dest, sanitized):
    nvn = tree / 'graphics/nvn/gfx/nvn'
    source = (nvn / 'nvn_mtl.m').read_text()
    begin = source.index('static void fb_prepare(NvProg *pr) {')
    end = source.index('\n}', begin) + 2
    include = dest.with_suffix('.inc')
    include.write_text(source[begin:end] + '\n')
    flags = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'] if sanitized else []
    subprocess.run(['clang', '-O2', *flags, f'-DIMPL="{include}"', '-I', nvn,
                    Path(__file__).with_name('bench.c'), '-o', dest], check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('trees', nargs='+', type=Path, help='prepared trees, starting with reference')
    ap.add_argument('--csv', type=Path)
    ap.add_argument('--cpu', type=int, default=min(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None)
    args = ap.parse_args()
    if len(args.trees) < 2:
        ap.error('supply at least two trees to test equivalence')
    affinity = ["taskset", "-c", str(args.cpu)] if args.cpu is not None else []
    rng = random.Random(305)
    modes = ['empty', 'burst', 'same', 'varies', 'stale']
    verify = {}
    samples = []
    with tempfile.TemporaryDirectory() as tmp:
        bins = [Path(tmp) / str(i) for i in range(len(args.trees))]
        for binary, tree in zip(bins, args.trees):
            san = binary.with_name(binary.name + '-san')
            build(tree, san, True)
            _, *state = subprocess.check_output([san, 'verify'], text=True).split()
            if state != verify.setdefault('verify', state):
                raise ValueError(f'divergent intermediate state for {tree}')
            build(tree, binary, False)
        for pair in range(27):
            for mode in rng.sample(modes, len(modes)):
                for binary in rng.sample(bins, len(bins)):
                    output = subprocess.check_output([*affinity, binary, mode], text=True)
                    ms, *state = output.split()
                    if state != verify.setdefault(mode, state):
                        raise ValueError(f'divergent final state for {mode} {binary.name}')
                    if pair:
                        samples.append((pair, mode, binary.name, float(ms)))
    if args.csv:
        with args.csv.open('w', newline='') as out:
            writer = csv.writer(out, lineterminator='\n')
            writer.writerow(['pair', 'workload', 'tree_index', 'ms'])
            writer.writerows(samples)
    for mode in modes:
        for i, tree in enumerate(args.trees):
            ms = [sample for _, m, variant, sample in samples if m == mode and variant == str(i)]
            print(mode, tree, f'{statistics.median(ms):.4f} ms')

if __name__ == '__main__':
    main()
