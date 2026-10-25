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


accepted = legacy_accepted = rar_capable = 0
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
    if record['format'] == 'rar':
        # RAR requires the new native reader. Publishing it as an ordinary
        # available pack would advertise an unusable download to older apps.
        assert promoted['availability'] == 'manual' and promoted['download']['automatable'] is False
        assert promoted['download']['verified'] == manual['download']['verified']
        spec = promoted['download']['in_app']
        invalid_legacy = copy.deepcopy(promoted)
        invalid_legacy['availability'] = 'available'
        invalid_legacy['download'] = copy.deepcopy(spec)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                catalogue.validate({'packs': [invalid_legacy]})
            except SystemExit as error:
                assert error.code == 1 and 'download format/parts' in output.getvalue()
            else:
                raise AssertionError('RAR bypassed the native-capability compatibility gate')
        rar_capable += 1
    else:
        assert record['format'] in ('zip', '7z')
        assert promoted['availability'] == 'available' and promoted['download']['automatable'] is True
        assert 'in_app' not in promoted['download']
        spec = promoted['download']
        legacy_accepted += 1
    assert count_packs.native_one_tap(promoted)
    assert spec['automatable'] is True and spec['format'] == record['format']
    assert promoted['install'] == manual['install']
    assert promoted['games'] == manual['games'] and promoted['authors'] == manual['authors']
    part = spec['parts'][0]
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

assert legacy_accepted >= 87, legacy_accepted
assert rar_capable >= 1, 'The ingested GameBanana RAR success must exercise the native-capability branch'

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

# PAW is served directly by its creator's Xenogears community host. The
# published URL has remained the original page's download link; it needs no
# resolver. Promotion must retain the real CI archive and default-only plan.
paw_id = 'ps1-linnaealyn-xenogears-perfect-art-works'
if paw_id in by_id and records.get(paw_id, {}).get('status') == 'ok':
    paw_source, paw_record = copy.deepcopy(by_id[paw_id]), copy.deepcopy(records[paw_id])
    paw = published(paw_source, paw_record)
    assert paw['availability'] == 'available'
    assert paw['download']['parts'] == paw_record['parts']
    assert paw['install']['files'] == 399
    assert paw['install']['folders'] == [{'from': '[your .cue or .m3u file name here]-texture-replacements/', 'to': '{id}'}]
    original = paw_source['download']['verify']['url']
    for url in (
            original.replace('lifehold.godsibb.net/', 'lifehold.godsibb.net.evil.invalid/'),
            original.replace('/seafhttp/f/', '/accounts/login/'),
            original.replace('?op=view', '?op=delete'),
            original + '&redirect=https://evil.invalid/',
            original.replace('https://', 'https://user:password@')):
        unsafe_source, unsafe_record = copy.deepcopy(paw_source), copy.deepcopy(paw_record)
        unsafe_source['download']['verify']['url'] = unsafe_record['parts'][0]['url'] = url
        rejects(unsafe_source, unsafe_record, 'not a reviewed stable original download')

# Actual SotC creator archive metadata uses Drive's /u/0/uc account-context
# alias. Canonicalising that path must not rewrite the observed source URL,
# file ID, query/access key, size or SHA, nor invent an installation success.
sotc_id = 'ps2-ktx-shadow-of-the-colossus-curse-arms'
sotc_source, sotc_record = copy.deepcopy(by_id[sotc_id]), copy.deepcopy(records[sotc_id])
sotc_source['download']['in_app'] = True
source_before, record_before = copy.deepcopy(sotc_source), copy.deepcopy(sotc_record)
original_url = sotc_source['download']['verify']['url']
assert original_url == 'https://drive.google.com/u/0/uc?id=1G_FlX3Wi721zDuEZq5kQtZMnmCTqiQh1&export=download'
assert sotc_record['parts'][0]['url'] == original_url
assert sotc_record['parts'][0]['size'] == 1106962372
assert sotc_record['parts'][0]['sha256'] == '3422496c42f16259998ab3b42747a51407c190acfe3ed24add8360f74799a7f7'
canonical = catalogue.hosted_in_app_download(sotc_source, sotc_record)
assert canonical == {'provider': 'gdrive', 'url': original_url.replace('/u/0/uc?', '/uc?')}
assert {**sotc_record['parts'][0], **canonical} == {
    'provider': 'gdrive', 'url': canonical['url'],
    'size': sotc_record['parts'][0]['size'], 'sha256': sotc_record['parts'][0]['sha256']}
with_key = copy.deepcopy(sotc_source)
with_key['download']['verify']['url'] += '&resourcekey=0-AbCd_123'
assert catalogue.hosted_in_app_download(with_key, sotc_record)['url'] == canonical['url'] + '&resourcekey=0-AbCd_123'
assert sotc_source == source_before and sotc_record == record_before
for bad_url in (
        original_url.replace('/u/0/uc', '/u/alice/uc'),
        original_url.replace('/u/0/uc', '/u/-1/uc'),
        original_url.replace('/u/0/uc', '/u/0/open'),
        original_url.replace('drive.google.com/', 'drive.google.com.evil.invalid/'),
        'https://drive.google.com/u/0/uc?export=download',
        'https://drive.google.com/u/0/uc?id=short&export=download',
        'https://drive.google.com/u/0/uc?id=malformed%2Ffileid&export=download'):
    bad = copy.deepcopy(sotc_source)
    bad['download']['verify']['url'] = bad_url
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        try:
            catalogue.hosted_in_app_download(bad, sotc_record)
        except SystemExit as error:
            assert error.code == 1 and 'not a reviewed stable original download' in output.getvalue()
        else:
            raise AssertionError('Malformed Drive alias/file ID was accepted')

print(f'PASS: {accepted} real direct/GameBanana/Dropbox profiles ({legacy_accepted} legacy ZIP/7z, '
      f'{rar_capable} native RAR) retain exact identity/hash/layout; '
      'Dropbox access queries retained; resolver metadata retains legacy fallback; '
      'SotC Drive account alias normalised without changing provenance; '
      'unreviewed providers, changed URLs, malformed IDs, altered hashes and failed transfers cannot be promoted')
