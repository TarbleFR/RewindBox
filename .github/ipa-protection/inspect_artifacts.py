"""Inspect existing artifacts without deleting or changing anything.

Encrypted envelopes are checked structurally using bounded range reads. Other
artifacts are downloaded, digest-checked and inspected by the same upload guard.
Signed download URLs, credentials and artifact contents are never in the report.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import audit_artifacts

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ipa_guard', ROOT/'.github/actions/upload-protected-artifact/scan.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
FORMAT = {'cipher': 'AES-256-CBC PBKDF2 200000', 'keyEnvelope': 'RSA OAEP SHA256',
          'content': 'tar', 'publication': 'encrypted delivery only'}


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def artifact_url(artifact_id):
    if not isinstance(artifact_id, int) or artifact_id <= 0:
        raise ValueError('Invalid artifact ID')
    request = urllib.request.Request(audit_artifacts.API + '/actions/artifacts/' + str(artifact_id) + '/zip',
        headers={'Authorization': 'Bearer '+os.environ['GITHUB_TOKEN'],
                 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    try:
        urllib.request.build_opener(NoRedirects()).open(request, timeout=30)
    except urllib.error.HTTPError as error:
        if error.code != 302:
            raise RuntimeError('Artifact download API HTTP '+str(error.code)) from None
        url = error.headers.get('Location', '')
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username:
            raise ValueError('Invalid signed artifact destination')
        if not parsed.hostname.endswith(('.blob.core.windows.net', '.githubusercontent.com', '.s3.amazonaws.com')):
            raise ValueError('Unrecognized signed artifact destination host')
        return url
    raise ValueError('Expected a signed artifact download redirect')


class RemoteZip(io.RawIOBase):
    def __init__(self, url, size):
        self.url, self.size, self.position = url, size, 0
        self.cache = {}
        self.transferred = 0

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position

    def seek(self, offset, whence=0):
        position = offset if whence == 0 else self.position+offset if whence == 1 else self.size+offset
        if position < 0:
            raise ValueError('Negative archive offset')
        self.position = position
        return position

    def read(self, size=-1):
        if size < 0: size = self.size-self.position
        size = min(size, max(0, self.size-self.position))
        if size == 0: return b''
        if size > 2*1024**2:
            raise guard.InspectionError('Unexpected large range read')
        output = bytearray()
        while len(output) < size:
            block = self.position//65536
            if block not in self.cache:
                start, end = block*65536, min(self.size-1, (block+1)*65536-1)
                req = urllib.request.Request(self.url, headers={'Range': f'bytes={start}-{end}'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    if response.status == 200 and self.size <= 65536:
                        data = response.read(65537)
                        if len(data) != self.size: raise ValueError('Unexpected archive length')
                    else:
                        if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{self.size}':
                            raise guard.InspectionError('Artifact host did not honor a bounded range')
                        data = response.read(end-start+2)
                        if len(data) != end-start+1: raise ValueError('Truncated archive range')
                self.transferred += len(data)
                if len(self.cache) >= 32: self.cache.pop(next(iter(self.cache)))
                self.cache[block] = data
            data = self.cache[block]
            offset = self.position-block*65536
            piece = data[offset:offset+size-len(output)]
            if not piece: raise ValueError('Empty archive range')
            output.extend(piece)
            self.position += len(piece)
        return bytes(output)


class StoredMember(io.RawIOBase):
    def __init__(self, remote, info):
        if info.compress_type != zipfile.ZIP_STORED or info.flag_bits & 1:
            raise guard.InspectionError('Envelope requires a complete download')
        remote.seek(info.header_offset)
        header = remote.read(30)
        if header[:4] != b'PK\x03\x04': raise ValueError('Invalid ZIP local header')
        name_len, extra_len = struct.unpack('<HH', header[26:30])
        self.remote, self.offset, self.size = remote, info.header_offset+30+name_len+extra_len, info.file_size
        self.position = 0

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position
    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position+offset if whence == 1 else self.size+offset
        if self.position < 0: raise ValueError('Negative member offset')
        return self.position
    def read(self, size=-1):
        if size < 0: size = self.size-self.position
        size = min(size, max(0, self.size-self.position))
        self.remote.seek(self.offset+self.position)
        value = self.remote.read(size)
        self.position += len(value)
        return value


def encrypted_envelope(archive, remote, artifact):
    entries = {x.filename: x for x in archive.infolist() if not x.is_dir()}
    names = set(entries)
    complete = names == {'artifact.tar.enc', 'password.rsa', 'format.json'}
    part = names == {'data.bin', 'password.rsa', 'format.json', 'manifest.json'}
    if not (complete or part): return None
    for name in names-{'artifact.tar.enc', 'data.bin'}:
        if entries[name].file_size > 16384: raise ValueError('Oversized envelope metadata')
    if json.loads(archive.read('format.json')) != FORMAT: raise ValueError('Unknown encrypted delivery format')
    key = archive.read('password.rsa')
    if len(key) not in (256, 384, 512, 1024): raise ValueError('Invalid RSA envelope length')
    payload_name = 'artifact.tar.enc' if complete else 'data.bin'
    if entries[payload_name].compress_type != zipfile.ZIP_STORED:
        return None  # A compressed member is checked by the full-download path.
    payload = StoredMember(remote, entries[payload_name])
    prefix = payload.read(16)
    payload.seek(0)
    if complete and not prefix.startswith(b'Salted__'): raise ValueError('Missing encrypted payload header')
    if part:
        manifest = json.loads(archive.read('manifest.json'))
        match = re.search(r'-part(0[0-3])$', artifact['name'])
        run = artifact['workflow_run']
        if not match or manifest.get('schemaVersion') != 1 or manifest.get('encrypted') is not True:
            raise ValueError('Unrecognized encrypted transport manifest')
        index = int(match.group(1))
        if manifest.get('source') != run['head_sha'] or manifest.get('run') != run['id']:
            raise ValueError('Transport provenance mismatch')
        pieces = manifest.get('parts', [])
        if len(pieces) != 4 or pieces[index]['index'] != index or pieces[index]['bytes'] != entries['data.bin'].file_size:
            raise ValueError('Transport piece length mismatch')
        for name in ('format.json', 'password.rsa'):
            value = archive.read(name)
            if manifest['files'][name] != {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}:
                raise ValueError('Transport metadata digest mismatch')
        if index == 0 and not prefix.startswith(b'Salted__'): raise ValueError('Missing first-piece encryption header')
    # Reject renamed, prefixed ZIP/tar packages even inside an alleged envelope.
    guard.scan_stream(payload, payload_name)
    return 'encrypted-envelope-structure' if complete else 'encrypted-transport-structure'


def inspect_one(artifact):
    result = {k: artifact[k] for k in ('id','name','size_in_bytes','digest','workflow_run')}
    try:
        url = artifact_url(artifact['id'])
        remote = RemoteZip(url, artifact['size_in_bytes'])
        with zipfile.ZipFile(remote) as archive:
            for entry in archive.infolist(): guard.check_name(entry.filename)
            classification = encrypted_envelope(archive, remote, artifact)
            if classification:
                return {**result, 'result': classification, 'rangeBytesRead': remote.transferred}
        if artifact['size_in_bytes'] > 8*1024**3:
            raise guard.InspectionError('Artifact exceeds complete-download budget')
        with tempfile.TemporaryFile() as output:
            digest = hashlib.sha256()
            total = 0
            with urllib.request.urlopen(url, timeout=60) as response:
                while block := response.read(1024**2):
                    total += len(block)
                    if total > artifact['size_in_bytes']: raise ValueError('Artifact grew during download')
                    digest.update(block)
                    output.write(block)
            if total != artifact['size_in_bytes']: raise ValueError('Artifact size mismatch')
            if artifact.get('digest') and artifact['digest'] != 'sha256:'+digest.hexdigest():
                raise ValueError('Artifact digest mismatch')
            output.seek(0)
            guard.scan_stream(output, 'artifact.zip', guard.Budget(seconds=300))
        return {**result, 'result': 'no-plaintext-ipa', 'downloadedBytes': total}
    except guard.UnsafeArtifact as error:
        return {**result, 'result': 'plaintext-ipa', 'evidence': str(error)}
    except Exception as error:
        # Do not serialize HTTPError URLs or response bodies.
        reason = str(error) if isinstance(error, (guard.InspectionError, ValueError, RuntimeError)) else type(error).__name__
        return {**result, 'result': 'unverified', 'reason': reason[:500]}


def main():
    folder = Path('build/ipa-artifact-inspection')
    folder.mkdir(parents=True, exist_ok=True)
    inventory = audit_artifacts.inventory()
    (folder/'inventory.json').write_text(json.dumps(inventory, indent=2)+'\n')
    targets = [a for a in inventory['artifacts'] if not a['expired']]
    results = []
    with (folder/'results.jsonl').open('w') as journal, ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(inspect_one, artifact) for artifact in targets]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            journal.write(json.dumps(result, sort_keys=True)+'\n')
            journal.flush()
            if len(results) % 50 == 0:
                print(json.dumps({'inspected':len(results),'total':len(targets),
                                  'plaintext':sum(x['result']=='plaintext-ipa' for x in results),
                                  'unverified':sum(x['result']=='unverified' for x in results)}), flush=True)
    counts = {key:sum(x['result']==key for x in results) for key in sorted({x['result'] for x in results})}
    summary = {'schema':1,'repository':audit_artifacts.REPO,'source':os.environ.get('GITHUB_SHA'),
               'runId':os.environ.get('GITHUB_RUN_ID'),'counts':counts,'total':len(results),
               'mutations':0,'releaseAssetsTouched':False,
               'encryptedEnvelopeContentDecrypted':False,
               'findings':[x for x in results if x['result'] in ('plaintext-ipa','unverified')]}
    (folder/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='findings'}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
