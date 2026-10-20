#!/usr/bin/env python3
"""Replay real host observations through the one-tap publication boundary.

No textures are downloaded or extracted again. This checks that promotion
uses the exact known size/hash/layout, keeps nonreviewed providers manual,
and cannot turn a quota/protection response or a changed source URL into a
downloadable archive. Native HTTP transport is verified separately.
"""
import contextlib
import copy
import io
from pathlib import Path
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/textures'))
import build_catalogue as catalogue  # noqa: E402
import count_packs  # noqa: E402

entries, records = catalogue.load()
by_id = {entry['id']: entry for entry in entries}


def published(entry, record):
    index, _, _ = catalogue.build([entry], {entry['id']: record})
    catalogue.validate(index)
    return index['packs'][0]


def rejects(entry, record, message):
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            published(entry, record)
    except SystemExit as error:
        assert error.code == 1 and message in output.getvalue(), output.getvalue()
    else:
        raise AssertionError('Unsafe host record was published: ' + entry['id'])


accepted = 0
for source in entries:
    record = records.get(source['id']) or {}
    if record.get('status') != 'ok' or record.get('host') not in ('direct', 'gamebanana', 'dropbox') or \
            not (source.get('download') or {}).get('verify'):
        continue
    entry, observation = copy.deepcopy(source), copy.deepcopy(record)
    entry['download'].pop('in_app', None)
    manual = published(entry, observation)
    assert manual['availability'] == 'manual' and manual['download']['verified']['sha256'] == record['parts'][0]['sha256']
    entry['download']['in_app'] = True
    promoted = published(entry, observation)
    assert promoted['availability'] == 'available' and promoted['download']['automatable'] is True
    assert promoted['install'] == manual['install']
    assert promoted['games'] == manual['games'] and promoted['authors'] == manual['authors']
    part = promoted['download']['parts'][0]
    assert part['size'] == record['parts'][0]['size'] and part['sha256'] == record['parts'][0]['sha256']
    if record['host'] == 'dropbox':
        before = urllib.parse.urlsplit(record['parts'][0]['url'])
        after = urllib.parse.urlsplit(part['url'])
        assert (before.scheme, before.netloc, before.path) == (after.scheme, after.netloc, after.path)
        old_query = [(k, v) for k, v in urllib.parse.parse_qsl(before.query, keep_blank_values=True) if k not in ('dl', 'raw')]
        assert urllib.parse.parse_qsl(after.query, keep_blank_values=True) == old_query + [('dl', '1')]
    else:
        assert part['url'] == record['parts'][0]['url']
    assert observation == record
    accepted += 1

assert accepted >= 80, accepted

identifier = 'wii-animal-crossing-city-folk-hd-yttrium'
entry, record = copy.deepcopy(by_id[identifier]), copy.deepcopy(records[identifier])
entry['download']['in_app'] = True
for status in ('quota', 'protected', 'gone', 'unsupportedArchive'):
    failed = copy.deepcopy(record)
    failed['status'] = status
    result = published(entry, failed)
    assert result['availability'] == 'manual' and not result['download'].get('automatable') and 'install' not in result

changed = copy.deepcopy(entry)
changed['download']['verify']['url'] += '&another-file=1'
rejects(changed, record, 'verification record names other files')

for bad_url in ('https://www.dropbox.com.evil.invalid/s/key/file.zip',
                'http://www.dropbox.com/s/key/file.zip',
                'https://user:password@www.dropbox.com/s/key/file.zip',
                'https://www.dropbox.com/s/key/file.zip#temporary-key',
                'https://www.dropbox.com/sh/folder/file.zip'):
    bad_entry, bad_record = copy.deepcopy(entry), copy.deepcopy(record)
    bad_entry['download']['verify']['url'] = bad_record['parts'][0]['url'] = bad_url
    rejects(bad_entry, bad_record, 'not a reviewed stable original download')

for host in ('gdrive', 'mega', 'yandex'):
    # Resolver downloads retain a legacy manual fallback; only a new native
    # client may expand the complete capability descriptor to a one-tap pack.
    source = next(s for s in entries if (records.get(s['id']) or {}).get('host') == host and
                  records[s['id']].get('status') == 'ok' and (s.get('download') or {}).get('verify'))
    baseline = copy.deepcopy(source)
    baseline['download'].pop('in_app', None)
    original = published(baseline, records[source['id']])
    assert original['availability'] == 'manual' and 'in_app' not in original['download']
    baseline['download']['in_app'] = True
    capable = published(baseline, records[source['id']])
    assert capable['availability'] == 'manual' and capable['download']['automatable'] is False
    assert count_packs.native_one_tap(capable)
    assert capable['download']['verified'] == original['download']['verified']
    assert capable['install'] == original['install']
    spec = capable['download']['in_app']
    assert spec['automatable'] is True and spec['format'] == original['download']['verified']['format']
    assert spec['parts'] == [{**records[source['id']]['parts'][0], 'provider': host}]
    malformed = copy.deepcopy(capable)
    malformed['download']['in_app']['parts'][0]['sha256'] = '0' * 64
    assert not count_packs.native_one_tap(malformed)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        try:
            catalogue.validate({'packs': [malformed]})
        except SystemExit as error:
            assert error.code == 1 and 'differs from verified file' in output.getvalue()
        else:
            raise AssertionError('Capability metadata changed the verified file')

bad_entry, bad_record = copy.deepcopy(entry), copy.deepcopy(record)
bad_record['host'] = 'unimplemented-provider'
rejects(bad_entry, bad_record, 'not a reviewed stable original download')

print(f'PASS: {accepted} real direct/GameBanana/Dropbox profiles retain exact identity/hash/layout; '
      'Dropbox access queries retained; resolver metadata retains legacy fallback; '
      'unreviewed providers, changed URLs, altered hashes and failed transfers cannot be promoted')
