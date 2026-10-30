"""Exact runtime-helper relocation; compiled Core sources and identities stay frozen."""
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = 'packages/melonx_jit_helper/ios/Resources/melonx-universal.js'
BASE = 'd042eefbaf5544e58faac91bf1680f7ff2f6dc93'
ORIGINAL_SHA256 = '879df6151e9b292b5c8dab7f8a88634aa92a3f25518d080c68722d243adaf0b3'
COMMENT = '// Initialize protocol state before the first continue can dispatch command 1.\n'


def relocate(original):
    start = original.index('// REWINDBOX_SIZED_ARENA_V1_BEGIN')
    end = original.index('// REWINDBOX_SIZED_ARENA_V1_END') + len('// REWINDBOX_SIZED_ARENA_V1_END')
    block = original[start:end]
    rest = original[:start] + original[end:]
    assert rest.count('let totalBreakpoints = 0;') == 1
    return rest.replace('let totalBreakpoints = 0;', COMMENT + block + '\n\nlet totalBreakpoints = 0;', 1)


def verify(original_digest=ORIGINAL_SHA256):
    original = subprocess.check_output(['git','show',BASE+':'+SCRIPT],cwd=ROOT)
    assert hashlib.sha256(original).hexdigest() == original_digest == ORIGINAL_SHA256
    current = (ROOT/SCRIPT).read_bytes()
    assert current == relocate(original.decode()).encode(), 'Unexpected helper behavior change'
    return dict(baseline=BASE,originalSHA256=ORIGINAL_SHA256,currentSHA256=hashlib.sha256(current).hexdigest(),
                exactBlockRelocation=True,compiledCoreChanged=False)
