#!/usr/bin/env python3
"""Derive the Core-swap variant of a private delivery workflow.

The variant keeps every job and step of the full delivery and changes two
things in its macOS job:

- the Xcode compile is replaced by core_swap_base.py, which puts the published
  base application where Xcode would have left it (Core-only deliveries ship
  the base product byte for byte; see that script);
- the four RPCS3 Core steps (Core run wait, component wait, artifact download,
  verification and installation) move from before the host configuration to
  the place of the compile, just before the Core is embedded: everything that
  does not need the new Core runs while its Core run is still compiling.

The checks job gains one step after its pin: core_swap_base.py --check, which
fails within a minute when the release, the base receipt or the product trees
do not allow a Core swap. core_swap_base.py joins the push paths: it is part of
the recipe, so a change to it runs the delivery again. Every other step, its order and every validator are
unchanged; the result is checked against that description before it is
written. The tree module of the build must list build-utils/core_swap_base.py
in its recipe, or the pin removes it.

Run: python3 build-utils/make_core_swap_workflow.py FULL.yml OUT.yml --tag TAG
     --asset NAME --sha256 HEX --base-build N --base-receipt PATH
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

import yaml

COMPILE = 'Compile Release device binary with measured AOT and Xcode phases'
CORE_STEPS = ('Require completed exact NeoSwap Core before artifact download',
              'Wait for the exact source-built',
              'Download pinned passive RPCS3 Core',
              'Verify and install passive RPCS3 Core')
FIRST_EMBED = 'Embed NeoPlay source identity and dependency acknowledgements'
CORE_EMBED = 'Embed verified RPCS3 Core and signing metadata'
SCRIPT = 'build-utils/core_swap_base.py'


class Dumper(yaml.SafeDumper):
    pass


def _string(dumper: yaml.SafeDumper, data: str):
    # Multi-line scripts as literal blocks; PyYAML falls back when a block is not representable.
    style = '|' if '\n' in data else None
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, style=style)


Dumper.add_representer(str, _string)


def core_indices(steps: list) -> list[int]:
    found = []
    for prefix in CORE_STEPS:
        hits = [i for i, s in enumerate(steps) if s.get('name', '').startswith(prefix)]
        assert len(hits) == 1, (prefix, hits)
        found.append(hits[0])
    assert found == list(range(found[0], found[0] + len(CORE_STEPS))), found
    return found


def swap_step(tag: str, asset: str, sha256: str, base_build: str, receipt: str) -> dict:
    return {
        'name': f'Use the published {tag} application (build {base_build}) instead of recompiling: '
                'only the RPCS3 Core changes',
        'run': ('set -euo pipefail\n'
                'python3 build-utils/delivery_metrics.py core_swap_base python3 build-utils/core_swap_base.py \\\n'
                f'  --tag {tag} --asset {asset} \\\n'
                f'  --sha256 {sha256} \\\n'
                f'  --base-build {base_build} --base-receipt {receipt}\n'),
    }


def check_step(tag: str, asset: str, sha256: str, base_build: str, receipt: str) -> dict:
    return {
        'name': f'Require the published {tag} application (build {base_build}) and unchanged shipped sources for the Core swap',
        'run': ('set -euo pipefail\n'
                'python3 build-utils/core_swap_base.py --check \\\n'
                f'  --tag {tag} --asset {asset} \\\n'
                f'  --sha256 {sha256} \\\n'
                f'  --base-build {base_build} --base-receipt {receipt}\n'),
    }


def pin_index(steps: list) -> int:
    hits = [i for i, s in enumerate(steps) if s.get('name', '').startswith('Pin the delivered')]
    assert len(hits) == 1, hits
    return hits[0]


def transform(workflow: dict, tag: str, asset: str, sha256: str, base_build: str, receipt: str) -> dict:
    result = copy.deepcopy(workflow)
    note = f' — Core swap on the published {tag} application (build {base_build})'
    result['name'] = workflow['name'] + note
    result['run-name'] = workflow['run-name'].replace(' — ${{ github.sha }}', note + ' — ${{ github.sha }}')
    paths = result['on']['push']['paths']
    assert SCRIPT not in paths, 'The full workflow already names the Core-swap script'
    paths.append(SCRIPT)
    steps = result['jobs']['cold']['steps']
    names = [s.get('name', '') for s in steps]
    compile_at = names.index(COMPILE)
    assert names.count(COMPILE) == 1
    moved = core_indices(steps)
    assert moved[-1] < compile_at, 'The Core steps already follow the compile'
    assert names[compile_at + 1] == FIRST_EMBED and names[compile_at + 2] == CORE_EMBED, names[compile_at + 1:compile_at + 3]
    core = [steps[i] for i in moved]
    kept = [s for i, s in enumerate(steps) if i not in moved]
    at = next(i for i, s in enumerate(kept) if s.get('name') == COMPILE)
    kept[at:at + 1] = [swap_step(tag, asset, sha256, base_build, receipt)] + core
    result['jobs']['cold']['steps'] = kept
    checks = result['jobs']['checks']['steps']
    checks.insert(pin_index(checks) + 1, check_step(tag, asset, sha256, base_build, receipt))
    check(workflow, result, tag, asset, sha256, base_build, receipt)
    return result


def check(full: dict, swap: dict, *base) -> None:
    """The variant is the full workflow with exactly the documented changes."""
    assert set(full) == set(swap) and set(full['jobs']) == set(swap['jobs'])
    for key in full:
        if key not in ('name', 'run-name', 'jobs', 'on'):
            assert full[key] == swap[key], key
    on = copy.deepcopy(full['on'])
    on['push']['paths'] = on['push']['paths'] + [SCRIPT]
    assert swap['on'] == on
    for job in full['jobs']:
        a, b = full['jobs'][job], swap['jobs'][job]
        assert {k: v for k, v in a.items() if k != 'steps'} == {k: v for k, v in b.items() if k != 'steps'}, job
        if job not in ('cold', 'checks'):
            assert a == b, job
    old_checks = full['jobs']['checks']['steps']
    at = pin_index(old_checks) + 1
    assert swap['jobs']['checks']['steps'] == old_checks[:at] + [check_step(*base)] + old_checks[at:]
    old, new = full['jobs']['cold']['steps'], swap['jobs']['cold']['steps']
    assert len(new) == len(old), (len(old), len(new))
    moved = core_indices(old)
    expected = [s for i, s in enumerate(old) if i not in moved]
    at = next(i for i, s in enumerate(expected) if s.get('name') == COMPILE)
    expected[at:at + 1] = [swap_step(*base)] + [old[i] for i in moved]
    assert new == expected
    names = [s.get('name', '') for s in new]
    # Nothing compiles the host any more (the diagnostics step only copies a log when present).
    assert COMPILE not in names and not any('xcodebuild -workspace' in (s.get('run') or '') for s in new)
    # The Core is installed after the host is configured and before it is embedded.
    assert names.index('Configure release host') < core_indices(new)[0] < names.index(CORE_EMBED)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('full', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--base-build', required=True)
    parser.add_argument('--base-receipt', required=True)
    a = parser.parse_args()
    full = yaml.safe_load(a.full.read_text())
    swap = transform(full, a.tag, a.asset, a.sha256, a.base_build, a.base_receipt)
    text = yaml.dump(swap, Dumper=Dumper, sort_keys=False, width=120, allow_unicode=True)
    assert yaml.safe_load(text) == swap
    a.output.write_text(text)
    print(f'{a.output}: {len(swap["jobs"]["cold"]["steps"])} macOS steps, Xcode compile replaced by the published {a.tag} application')


if __name__ == '__main__':
    main()
