#!/usr/bin/env python3
"""Preserve the verified catalogue baseline while reaching 400 native downloads.

Read-only metadata gate: no archive download, extraction, or installation.
The Git checkout must contain baseline 730e065ffb5d1b66735f6e440cbdbedc886c8163
(use fetch-depth: 0 in CI). All default evidence is committed in the repository.
An optional --output writes the full JSON report; stdout always contains it.
"""
import argparse
import ast
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/textures'))
import build_catalogue as catalogue
import count_packs

BASE = '730e065ffb5d1b66735f6e440cbdbedc886c8163'
INDEX = 'native/textures/catalogue/manifest.json.gz'
VERIFIED = 'tools/textures/verified.jsonl'


def previous(path):
    try:
        return subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{BASE}:{path}'])
    except subprocess.CalledProcessError as error:
        raise SystemExit(f'Required Git baseline {BASE} is unavailable; use a full-history CI checkout.') from error


def rows(raw):
    lines = [line for line in raw.splitlines() if line.strip()]
    pairs = [(json.loads(line)['id'], line, json.loads(line)) for line in lines]
    if len({p[0] for p in pairs}) != len(pairs):
        raise ValueError('Duplicate canonical record ID')
    return {identifier: (line, record) for identifier, line, record in pairs}


def historical_rows(raw):
    """A provenance ledger may retain several real observations of one ID."""
    found = {}
    for line in raw.splitlines():
        if line.strip():
            record = json.loads(line)
            found.setdefault(record['id'], []).append((line, record))
    return found


def compact(counts):
    return {key: {k: v for k, v in value.items() if k != 'families'} for key, value in counts.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=ROOT / INDEX)
    parser.add_argument('--require-generated', action='store_true', default=True)
    parser.add_argument('--expect-one-tap', type=int, default=400)
    parser.add_argument('--superseded-evidence', type=Path,
                        default=ROOT / 'docs/evidence/hd-direct400-superseded-observations.jsonl')
    parser.add_argument('--artifact-jsonl', type=Path, action='append', default=[])
    parser.add_argument('--artifacts-evidence', type=Path,
                        default=ROOT / 'docs/evidence/hd-direct400-ci-artifacts.json',
                        help='CI artifact ledger with repository-relative, SHA-pinned evidence_path members')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    checks, failures = {}, []

    def check(name, result, detail=None):
        checks[name] = {'passed': bool(result), **({'detail': detail} if detail is not None else {})}
        if not result:
            failures.append(name)

    baseline = json.loads(gzip.decompress(previous(INDEX)))
    old_rows = rows(previous(VERIFIED))
    old = {pack['id']: pack for pack in baseline['packs']}
    entries, records = catalogue.load()
    built, excluded, pending = catalogue.build(entries, records)
    candidate = json.loads(gzip.decompress(args.index.read_bytes())) if args.index else built
    catalogue.validate(candidate)
    packs = {pack['id']: pack for pack in candidate['packs']}
    check('baseline1086_ids_unique', len(old) == len(baseline['packs']) == 1086)
    check('candidate_ids_unique', len(packs) == len(candidate['packs']))
    missing = sorted(set(old) - set(packs))
    check('all1086_baseline_ids_retained', not missing, missing)
    check('no_unverified_automatable_pending', not pending, pending)
    direct = {key: pack for key, pack in old.items() if pack['availability'] == 'available'}
    changed_direct = sorted(key for key, pack in direct.items() if packs.get(key) != pack)
    check('old209_direct_profiles_164_families_unchanged', len(direct) == 209 and not changed_direct, changed_direct)

    before = count_packs.count(baseline, count_packs.sources())
    after = count_packs.count(candidate, count_packs.sources())
    check('baseline_distinct355_and_direct164', before['total']['distinct'] == 355 and before['total']['oneTapFamilies'] == 164)
    manual = {key: pack for key, pack in old.items() if pack['availability'] == 'manual' and pack['download'].get('verified')}
    stable_fields = ('id', 'system', 'systems', 'engine', 'games', 'title', 'version', 'authors', 'credits',
                     'page_url', 'source_id', 'install', 'verified_at')
    bad_manual, no_longer_one_tap = [], []
    for key, pack in manual.items():
        new = packs.get(key)
        if not new or any(new.get(field) != pack.get(field) for field in stable_fields) or new['licence']['summary'] != pack['licence']['summary']:
            bad_manual.append(key)
            continue
        proof = pack['download']['verified']
        effective = new['download'].get('in_app') or new['download']
        if not effective.get('automatable'):
            bad_manual.append(key)
            continue
        digest = effective.get('sha256') or effective['parts'][0]['sha256']
        size = effective.get('size') or effective['parts'][0]['size']
        if digest != proof['sha256'] or size != proof['size'] or effective['format'] != proof['format']:
            bad_manual.append(key)
        original_url = old_rows[key][1]['parts'][0]['url']
        if proof['host'] == 'dropbox':
            url = urllib.parse.urlsplit(original_url)
            query = [(k, v) for k, v in urllib.parse.parse_qsl(url.query, keep_blank_values=True) if k not in ('dl', 'raw')]
            original_url = urllib.parse.urlunsplit(url._replace(query=urllib.parse.urlencode(query + [('dl', '1')])))
        expected_part = {'url': original_url, 'size': proof['size'], 'sha256': proof['sha256']}
        if proof['host'] in ('gdrive', 'mega', 'yandex'):
            expected_part['provider'] = proof['host']
        if effective['parts'] != [expected_part]:
            bad_manual.append(key)
        if not count_packs.native_one_tap(new):
            no_longer_one_tap.append(key)
    check('old231_manual_profiles_keep_identity_plan_hash_size_original_url_and_licence', len(manual) == 231 and not bad_manual, bad_manual)
    check('old191_manual_families_have_validated_native_downloads', not no_longer_one_tap, no_longer_one_tap)
    legacy_bad = [pack['id'] for pack in packs.values() if pack['availability'] == 'available' and (
        not pack['download'].get('automatable') or pack['download'].get('format') not in ('zip', '7z') or
        pack['download'].get('in_app') or any(part.get('provider') for part in pack['download'].get('parts', [])))]
    check('legacy_available_packs_need_no_new_provider_or_rar_capability', not legacy_bad, legacy_bad)

    new_rows = rows((ROOT / VERIFIED).read_bytes())
    check('666_baseline_record_ids_retained_once', len(old_rows) == 666 and set(old_rows) <= set(new_rows))
    superseded = historical_rows(args.superseded_evidence.read_bytes()) if args.superseded_evidence.exists() else {}
    changed = {key for key in old_rows if key in new_rows and old_rows[key][0] != new_rows[key][0]}
    check('only_explicit_superseded_records_changed', changed <= set(superseded), sorted(changed - set(superseded)))
    check('superseded_old_raw_bytes_preserved', all(any(line == old_rows[key][0] for line, _ in superseded.get(key, [])) for key in changed))
    unchanged_ids = set(old_rows) - changed
    actual_order = [key for key in new_rows if key in unchanged_ids]
    check('other_old_raw_records_and_order_unchanged', actual_order == [key for key in old_rows if key in unchanged_ids])
    artifact_rows, artifact_history = {}, {}
    artifact_paths = args.artifact_jsonl
    if not artifact_paths:
        artifacts = json.loads(args.artifacts_evidence.read_text())['artifacts']
        pinned_members = []
        bad_members = []
        for artifact in sorted(artifacts, key=lambda item: item['run']):
            for member in artifact['members']:
                relative = Path(member['evidence_path'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Artifact evidence_path must remain repository-relative')
                path = ROOT / relative
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != member['sha256'] or \
                        ('bytes' in member and len(raw) != member['bytes']) or \
                        ('records' in member and len(rows(raw)) != member['records']):
                    bad_members.append(str(relative))
                pinned_members.append(path)
        check('ci_evidence_members_match_pinned_sha256', bool(pinned_members) and not bad_members, bad_members)
        artifact_paths = pinned_members
    for path in artifact_paths:
        for key, value in rows(path.read_bytes()).items():
            # Inputs are chronological: the last real observation is canonical,
            # earlier versions remain required in the historical evidence.
            artifact_history.setdefault(key, []).append(value)
            artifact_rows[key] = value
    new_or_changed = changed | (set(new_rows) - set(old_rows))
    mismatched = sorted(key for key in new_or_changed if key not in artifact_rows or artifact_rows[key][0] != new_rows[key][0])
    check('new_and_reverified_raw_records_match_artifacts_exactly', not mismatched, mismatched)
    unknown_history = []
    for key, observations in superseded.items():
        known_lines = {value[0] for value in artifact_history.get(key, [])}
        if key in old_rows:
            known_lines.add(old_rows[key][0])
        for line, _ in observations:
            if key not in new_rows or line not in known_lines or line == new_rows[key][0]:
                unknown_history.append(key)
    check('historical_raw_records_are_real_superseded_observations', not unknown_history, sorted(set(unknown_history)))
    missing_intermediates = [key for key, observations in artifact_history.items()
                             for line, _ in observations[:-1]
                             if line != artifact_rows[key][0] and not any(line == raw for raw, _ in superseded.get(key, []))]
    check('all_intermediate_superseded_artifact_records_preserved', not missing_intermediates, sorted(set(missing_intermediates)))
    registry = json.loads((ROOT / 'tools/textures/ci-records.json').read_text())['runs']
    previous_latest_run = max(run['run'] for run in json.loads(previous('tools/textures/ci-records.json'))['runs'])
    registered = {run['run'] for run in registry}
    mappings = {key: later for run in registry for key, later in run.get('superseded', {}).items()}
    check('changed_records_registered_as_superseded', all(key in mappings and mappings[key] in registered and
          mappings[key] > previous_latest_run for key in changed), sorted(changed - set(mappings)))

    switch = json.loads((ROOT / 'tools/textures/research/future-switch.json').read_text())
    check('zero_switch_runtime_packs', not any(pack['system'] == 'switch' or 'switch' in pack.get('systems', []) for pack in packs.values()))
    check('five_future_switch_references_stay_disabled', len(switch['entries']) == 5 and all(
        entry.get('runtime_enabled') is False and entry.get('engine_validated') is False and entry.get('automatable') is False and
        not entry.get('payload_verified') for entry in switch['entries']))
    native = (ROOT / INDEX).read_bytes()
    bundled = (ROOT / 'packages/neo_texture_catalog/ios/Resources/manifest.json.gz').read_bytes()
    check('published_and_bundled_manifests_identical', native == bundled)
    generated = catalogue.serialize(built)[1]
    if args.require_generated:
        check('published_manifests_match_current_sources', native == generated)
    if args.expect_one_tap is not None:
        check('requested_native_one_tap_minimum', after['total']['oneTapFamilies'] >= args.expect_one_tap,
              {'actual': after['total']['oneTapFamilies'], 'required': args.expect_one_tap})

    # Verify the family grouping/scope definition stayed byte-semantically the
    # same; new native transports change availability, never family identity.
    original_ast = ast.parse(previous('tools/textures/count_packs.py').decode())
    current_ast = ast.parse((ROOT / 'tools/textures/count_packs.py').read_text())
    def definitions(tree):
        found = {}
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in ('family', 'scope'):
                found[node.name] = ast.dump(node, include_attributes=False)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in ('GROUPS', 'VARIANT_WORDS', 'SCOPE', 'SCOPE_OF'):
                        found[target.id] = ast.dump(node.value, include_attributes=False)
        return found
    check('family_and_scope_definition_unchanged', definitions(original_ast) == definitions(current_ast))
    network_path = ROOT / 'docs/evidence/hd-direct400-native-network-2026-10-20.json'
    if network_path.exists():
        observations = json.loads(network_path.read_text())['results']
        mismatches = []
        for result in observations:
            pack = packs[result['id']]
            spec = pack['download'].get('in_app') or pack['download']
            if result['status'] != 'ok' or not result['size_sha_verified_by_store'] or result['physical_device_rendering'] or \
                    result['expected_archive_bytes'] != (spec.get('size') or spec['parts'][0]['size']) or \
                    result['expected_archive_sha256'] != (spec.get('sha256') or spec['parts'][0]['sha256']):
                mismatches.append(result['id'])
        check('six_native_network_installs_bind_to_same_archives', len(observations) == 6 and not mismatches, mismatches)

    report = {'baseline': BASE, 'candidate_revision': candidate['revision'], 'source': str(args.index) if args.index else 'in-memory current sources',
              'before': compact(before), 'after': compact(after), 'checks': checks, 'passed': not failures, 'failed_checks': failures,
              'old_record_ids': len(old_rows), 'current_record_ids': len(new_rows), 'superseded_records': len(changed),
              'historical_observations': sum(len(value) for value in superseded.values()),
              'artifact_observations': sum(len(value) for value in artifact_history.values()),
              'new_record_ids': len(set(new_rows) - set(old_rows)), 'runtime_ids_before': len(old), 'runtime_ids_after': len(packs),
              'current_sources_match_manifest': native == generated, 'current_manifest_sha256': hashlib.sha256(native).hexdigest()}
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.write_text(serialized)
    print(serialized, end='')
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
