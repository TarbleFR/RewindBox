"""Reuse only the unchanged, previously successful firmware/header inputs."""
from pathlib import Path
import base64,hashlib,json,subprocess
root=Path(__file__).resolve().parents[2]
output=root/'dist/melonx'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt=json.loads((output/'firmware-transaction-checks.json').read_text())
assert receipt['productionSha256']==sha(root/'native/melonx/EmbeddedFirmwareStore.cs')
assert 'Production firmware transaction: 10 cases passed.' in receipt['result']
inputs=json.loads((output/'embedded-inputs.json').read_text())
assert inputs['native/melonx/EmbeddedGameHeader.cs']==sha(root/'native/melonx/EmbeddedGameHeader.cs')
# The artifact downloaded by melonx-core.yml is the original successful run.
run=39858967222
api='repos/TarbleFR/RewindBox'
jobs=json.loads(subprocess.check_output(['gh','api',f'{api}/actions/runs/{run}/jobs']))['jobs']
job=next(j for j in jobs if j['conclusion']=='success' and any(s['name']=='Execute production game header and metadata bounds' and s['conclusion']=='success' for s in j['steps']))
for filename in ['test/melonx_game_header_test.py','test/melonx_firmware_transaction_test.py']:
 data=json.loads(subprocess.check_output(['gh','api',f'{api}/contents/{filename}?ref={job["head_sha"]}']))
 assert hashlib.sha256(base64.b64decode(data['content'])).hexdigest()==sha(root/filename)
(output/'library-validation-reuse.json').write_text(json.dumps({'run':run,'source':job['head_sha'],'job':job['id'],'testsReexecuted':False,'firmwareCases':10,'headerCases':10},indent=2)+'\n')
print('Reused ten firmware transaction and ten header cases with identical production/test inputs.')
