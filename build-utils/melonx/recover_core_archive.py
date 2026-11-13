"""Recover exact Core ZIP bytes from pinned 90-day delivery republications.

The original artifact API is deliberately unnecessary. A retained history is
not a recovered engine82 ZIP or a new execution of its historical tests.
"""
import json
from pathlib import Path
import sys

from validate_runtime_reuse import digest, require

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import retained_components


def configuration():
    return json.loads((ROOT / 'build-utils/melonx/core-baseline.json').read_bytes())['recovery']


def recover(core, path, api=None, download=None):
    spec = configuration()[str(core)]
    receipt = retained_components.republished_archive(
        'melonx-core', spec['origin'], spec['republished'], path, api, download)
    require(path.stat().st_size == spec['origin']['bytes'] and
            digest(path) == spec['origin']['sha256'], 'Recovered Core archive changed')
    return receipt
