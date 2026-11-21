#!/usr/bin/env python3
"""Compare six private 803 / F14-off pairs on two named circuits. Print aggregates only."""
import argparse
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path
from statistics import median

import compare_benchmarks as bench
from compare_heap_windows import BASELINE_BUILD, BASELINE_ENGINE

FIELDS = ("p95_ms", "gt100_per_min", "gt200_per_min", "gt500_per_min", "fps")
TRIAL_FIELDS = ("eligible_worker_picks", "rank_candidates", "claimed_course_rows")
SHARED = ("game_id", "game_version", "device_model", "os_version", "settings", "cache_protocol", "diagnostics")


def metadata(run):
    data = run.begin.get("metadata")
    return data if isinstance(data, dict) else {}


def check_trial(run):
    trial = run.end.get("course_priority_trial")
    if not isinstance(trial, dict):
        return "marqueur F14 absent"
    if (trial.get("family") != "F14_COURSE_PRIORITY" or trial.get("ablation") != 1
            or trial.get("base_policy") != "803" or trial.get("exact_title_and_build") != 1):
        return "traitement ou identité MKW non confirmé"
    for field in TRIAL_FIELDS:
        counter = trial.get(field)
        if not isinstance(counter, dict):
            return f"compteur absent · {field}"
        for part in ("at_start", "in_window"):
            value = counter.get(part)
            if type(value) is not int or value < 0:
                return f"compteur indisponible · {field}.{part}"
            if field == "claimed_course_rows" and value:
                return "priorité F14 exercée dans le bras désactivé"
    return None


def analyze(pairs, candidate_engine):
    refused, identifiers, groups = [], set(), defaultdict(list)
    settings = None
    for index, (a, aid, b, bid) in enumerate(pairs, 1):
        left = bench.read_run(Path(a), f"803-{index}", bench.argument_id(aid))
        right = bench.read_run(Path(b), f"F14-{index}", bench.argument_id(bid))
        for run, version, engine in ((left, BASELINE_BUILD, BASELINE_ENGINE), (right, "809", candidate_engine)):
            info = metadata(run)
            if run.selected_id in identifiers:
                refused.append(f"{run.role} · fenêtre réutilisée")
            identifiers.add(run.selected_id)
            if info.get("app_build") != version or info.get("engine_build") != engine:
                refused.append(f"{run.role} · identité de version inattendue")
            game = str(info.get("game_id", "")).upper()
            if (game != "0400C3F00006E000" or info.get("device_model") != "iPhone17,2"
                    or str(info.get("os_version", "")).split(".")[0] != "27"):
                refused.append(f"{run.role} · jeu, appareil ou OS inattendu")
            actual = {key: info.get(key) for key in SHARED}
            actual["game_id"] = game
            if settings is None:
                settings = actual
            elif settings != actual:
                refused.append(f"{run.role} · conditions différentes entre circuits ou répétitions")
        reason = check_trial(right)
        if reason:
            refused.append(f"{right.role} · {reason}")
        result = bench.compare(left, right)
        if not result["comparable"]:
            refused.append({"paire": index, "raisons": result["reasons"],
                            "803": left.issues, "809": right.issues})
        name = metadata(left).get("scenario")
        if isinstance(name, str) and name.strip():
            groups[name].append((left, right))
        else:
            refused.append(f"{left.role} · circuit sans scénario")
    if len(groups) != 2 or any(len(rows) != 3 for rows in groups.values()):
        refused.append("deux scénarios distincts et trois paires par scénario requis")
    for name, rows in groups.items():
        for a, b in combinations([run for pair in rows for run in pair], 2):
            result = bench.compare(a, b)
            if not result["comparable"]:
                refused.append({"circuit": name, "observations": [a.role,b.role], "raisons": result["reasons"]})
    if refused:
        return {"comparable": False, "raisons": refused, "circuits": {}}

    courses = {}
    for name, rows in groups.items():
        metrics = {}
        for field in FIELDS:
            base = [a.end["display"].get(field) for a, _ in rows]
            off = [b.end["display"].get(field) for _, b in rows]
            if not all(bench.numeric(x) for x in base + off):
                return {"comparable": False, "raisons": [f"{name} · {field} indisponible"], "circuits": {}}
            metrics[field] = {"803": base, "809_F14_off": off, "mediane_803": median(base),
                              "mediane_809": median(off), "ecart_des_medianes": median(off)-median(base),
                              "ecarts_apparies": [y-x for x,y in zip(base,off)]}
        exposure = [b.end["course_priority_trial"] for _, b in rows]
        courses[name] = {"affichage": metrics, "exposition_809": exposure}
    return {"comparable": True, "circuits": courses,
            "decision": "Revue sur les deux circuits avec le rendu, le son et la vitesse observés. "
                        "Un delta descriptif ou une absence d’occasion de préchauffage ne suffit pas à conclure à l’équivalence."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", action="append", nargs=4, required=True,
                        metavar=("LOG_803", "UUID_803", "LOG_809", "UUID_809"))
    args = parser.parse_args()
    if len(args.pair) != 6:
        parser.error("six paires sont nécessaires")
    try:
        proof = json.loads(Path(__file__).with_name("engine205-build.json").read_text())
        report = analyze(args.pair, proof["source"])
    except (OSError, KeyError, ValueError, argparse.ArgumentTypeError) as exc:
        report = {"comparable": False, "raisons": [str(exc)], "circuits": {}}
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["comparable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
