"""Model a tie breaker between equally urgent observed pipeline recipes, using measured build costs."""
import argparse
import csv
import ctypes as ct
import itertools
from pathlib import Path
import random
import subprocess
import tempfile


def compile_order(tree, scratch):
    lib = Path(scratch) / "order.so"
    header = tree / "graphics/nvn/gfx/nvn"
    subprocess.run(["cc", "-O2", "-shared", "-fPIC", "-I", header,
                    Path(__file__).with_name("warm-order.c"), "-o", lib], check=True)
    module = ct.CDLL(str(lib))
    module.warm_row_bytes.restype = ct.c_size_t
    module.observed_order.argtypes = [ct.c_uint, ct.POINTER(ct.c_uint64), ct.POINTER(ct.c_uint),
                                      ct.c_void_p, ct.POINTER(ct.c_uint)]
    def sort(frames):
        n = len(frames)
        indexes = (ct.c_uint * n)()
        module.observed_order(n, (ct.c_uint64 * n)(*frames), indexes,
                              ct.create_string_buffer(n * module.warm_row_bytes()), (ct.c_uint * n)())
        return list(indexes)
    return sort


def fixture(case, seed):
    rng = random.Random(seed)
    vertices = list(range(10))
    fragments = list(range(10))
    rng.shuffle(vertices)
    rng.shuffle(fragments)
    bank = [(v, f) for v in vertices for f in fragments]
    rows = bank[:]
    if case != "fan":
        rng.shuffle(rows)
    # The order supplied to the sorter is the order within a first-frame bucket.
    frames = [i // 12 for i in range(len(rows))]
    if case == "exact":
        draws = rows[:20]
    elif case == "fan":
        draws = rows[:10] + rows[10:20:2]
    elif case == "crossed":
        draws = [bank[(i % 10)*10 + (i*3+2) % 10] for i in range(20)]
    elif case == "drift":
        draws = rng.sample(bank,20)
    else:
        raise ValueError(case)
    return rows, frames, draws


def spread_ties(order, rows, frames):
    warmed_v, warmed_f = set(), set()
    spread = []
    for _, group in itertools.groupby(order, key=frames.__getitem__):
        waiting = list(group)
        while waiting:
            # max is stable on ties, exactly preserving the original preference.
            selected = max(waiting, key=lambda i: int(rows[i][0] not in warmed_v) + int(rows[i][1] not in warmed_f))
            waiting.remove(selected)
            v, f = rows[selected]
            warmed_v.add(v)
            warmed_f.add(f)
            spread.append(selected)
    assert sorted(spread) == sorted(order) and [frames[i] for i in spread] == [frames[i] for i in order]
    return spread


def model(order, rows, draws, costs, budget):
    vertices, fragments, ready = set(), set(), set()
    def cost(recipe):
        v, f = recipe
        if recipe in ready:
            return 0.0
        if v not in vertices:
            return costs["fresh" if f not in fragments else "vertex_fresh"]
        return costs["one_fresh" if f not in fragments else "crossed"]
    def remember(recipe):
        vertices.add(recipe[0])
        fragments.add(recipe[1])
        ready.add(recipe)
    upfront = 0.0
    for index in order:
        recipe = rows[index]
        delay = cost(recipe)
        if upfront + delay > budget:
            break
        upfront += delay
        remember(recipe)
    prepared = len(ready)
    stalls = []
    for recipe in draws:
        stalls.append(cost(recipe))
        remember(recipe)
    return prepared, upfront, sum(stalls), max(stalls)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tree", type=Path)
    ap.add_argument("timings", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    costs = {}
    with args.timings.open() as stream:
        for row in csv.DictReader(stream):
            c = costs.setdefault(int(row["pair"]), {})
            stage = row["stage_pair"]
            if stage in c or float(row["build_ms"]) <= 0:
                raise ValueError(row)
            c[stage] = float(row["build_ms"])
    if len(costs) < 5 or any(set(c) != {"fresh","crossed","one_fresh","vertex_fresh","repeated"} for c in costs.values()):
        raise ValueError("each profile requires five measured stage classes")
    with tempfile.TemporaryDirectory() as tmp, args.output.open("x", newline="") as output:
        sort = compile_order(args.tree,tmp)
        writer = csv.writer(output)
        writer.writerow(("pair","case","budget_ms","order","ready","model_startup_ms","model_draw_wait_ms","model_longest_wait_ms"))
        for pair, profile in sorted(costs.items()):
            for case in ("exact", "fan", "crossed", "drift"):
                rows, frames, draws = fixture(case,7001 + pair)
                current = sort(frames)
                for label, indexes in (("current",current),("spread",spread_ties(current,rows,frames))):
                    for budget in (4, 12, 24):
                        writer.writerow((pair,case,budget,label,*model(indexes,rows,draws,profile,budget)))

if __name__ == "__main__":
    main()
