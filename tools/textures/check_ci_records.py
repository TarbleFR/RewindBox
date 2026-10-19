#!/usr/bin/env python3
"""Checks tools/textures/verified.jsonl against the CI runs that verified packs.

Packs published as repository archives (part "repositories") and the
authors' files of manual packs on file hosts (part "hosts", Build 489) are
downloaded and installed with the app's own code by
.github/workflows/hd-textures.yml, on GitHub's runners. Their records reach verified.jsonl through the run's log;
this check downloads the run's own artifacts (on a CI runner, with the
workflow token) and requires every record of every artifact to be present,
byte for byte as parsed JSON, in verified.jsonl. ci-records.json names the runs.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def records(path):
    found = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if line.strip():
            record = json.loads(line)
            if record['id'] in found:
                raise SystemExit(f'duplicate record {record["id"]} in {path}')
            found[record['id']] = record
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', default=str(ROOT / 'tools/textures/ci-records.json'))
    parser.add_argument('--verified', default=str(ROOT / 'tools/textures/verified.jsonl'))
    parser.add_argument('--repository', default='TarbleFR/neostation-ios')
    args = parser.parse_args()
    verified = records(args.verified)
    runs = json.loads(Path(args.runs).read_text(encoding='utf-8'))['runs']
    registered = {run['run'] for run in runs}
    checked = 0
    for run in runs:
        # A pack verified again by a later registered run (after a layout fix or a host quota):
        # this run's record of it is no longer the one in verified.jsonl; the later run's is.
        superseded = run.get('superseded', {})
        for identifier, later in superseded.items():
            if later not in registered or later <= run['run']:
                raise SystemExit(f'run {run["run"]}: {identifier} superseded by an unregistered or earlier run {later}')
        count = 0
        with tempfile.TemporaryDirectory(prefix='hdtex-ci-') as folder:
            for console in run['consoles']:
                # Repository-archive runs name their artifacts after the source; host runs
                # (manual packs fetched from file hosts) after the run.
                template = run.get('artifact_name', '{prefix}-{console}-{source}')
                name = template.format(prefix=run.get('artifact_prefix', ''), console=console, source=run['source'], run=run['run'])
                subprocess.run(['gh', 'run', 'download', str(run['run']), '--repo', args.repository, '--name', name,
                                '--dir', str(Path(folder) / console)], check=True)
                files = list((Path(folder) / console).rglob('*.jsonl'))
                if len(files) != 1:
                    raise SystemExit(f'{name}: expected one JSONL file, found {len(files)}')
                for identifier, record in records(files[0]).items():
                    if identifier in superseded:
                        count += 1
                        continue
                    if verified.get(identifier) != record:
                        raise SystemExit(f'{identifier}: verified.jsonl differs from run {run["run"]} ({console})')
                    count += 1
        if count != run['records']:
            raise SystemExit(f'run {run["run"]}: {count} records, expected {run["records"]}')
        checked += count
    print(f'PASS {checked} CI-verified records (repository archives, file hosts) in verified.jsonl are those of their CI runs')


if __name__ == '__main__':
    sys.exit(main())
