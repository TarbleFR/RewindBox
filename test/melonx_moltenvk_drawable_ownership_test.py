#!/usr/bin/env python3
"""MoltenVK drawable ownership (build-utils/melonx/moltenvk/rewindbox-drawable-ownership.patch).

Crash (maintainer, IPA 718, Super Mario 3D World, vsync unbounded): SIGSEGV in objc_retain <- _Block_object_assign <-
_Block_copy <- MTLDispatchListAppendBlock <- MVKPresentableSwapchainImage::presentCAMetalDrawable <-
MVKQueuePresentSurfaceSubmission::execute (MoltenVK 1.4.2, KhronosGroup/MoltenVK#2791, open). MeloNX submits
asynchronously (SynchronousQueueSubmits = false), so a present runs on MoltenVK's submission thread while
vkAcquireNextImageKHR, on the render thread, may return the same image still in flight and released its drawable
without a lock.

Checks:
1. The pin names the patch by digest and marker; the patch changes only MVKImage.{h,mm} and has the four properties:
   acquisition releases no drawable, a present takes its drawable under _mtlDrawableLock (no separate retain), every
   release of _mtlDrawable is under the lock, and nextDrawable is called outside it.
2. A model of the original and patched functions (test/melonx_moltenvk_drawable_ownership/model.cpp) under
   AddressSanitizer with the reported interleaving: the original frees the drawable before the handler block retains
   it (heap-use-after-free in the block copy); the patch does not, and releases every drawable once.
3. The same model under ThreadSanitizer, both threads free for 20000 presents: a data race on _mtlDrawable before,
   none after, every drawable released.
A host model is not the iOS build: the patched MoltenVK is compiled by melonx-moltenvk-rebuild.yml, and no iPhone
session has run it.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / 'build-utils/melonx/moltenvk-rebuild.json').read_text())
PATCH = ROOT / 'build-utils/melonx/moltenvk/rewindbox-moltenvk.patch'  # the drawable hunks; the size hunks too (lot 9)
MODEL = ROOT / 'test/melonx_moltenvk_drawable_ownership/model.cpp'


def require(condition, message):
    if not condition:
        raise SystemExit('melonx moltenvk drawable ownership: ' + message)


def added_function(text, name, owner='MVKPresentableSwapchainImage'):
    """The patched body of one method (added and context lines of the patch)."""
    lines = [line[1:] for line in text.splitlines() if line[:1] in ('+', ' ')]
    body = '\n'.join(lines)
    start = body.find(owner + '::' + name + '(')
    require(start >= 0, f'{name} not in the patch')
    end = body.find('\n}', start)
    return body[start:end]


def check_patch():
    require(PIN['tag'] == 'v1.4.2' and PIN['revision'] == 'db66022459ffb663aa2b50f6b018bc2e124f5edf', 'pinned MoltenVK')
    require(PIN['patch'] == PATCH.relative_to(ROOT).as_posix(), 'the pin names the patch')
    require(hashlib.sha256(PATCH.read_bytes()).hexdigest() == PIN['patchSha256'], 'the patch digest matches its pin')
    text = PATCH.read_text()
    files = re.findall(r'^diff --git a/(\S+)', text, re.M)
    # Lot 10, fifth part (cache keys): MVKShaderModule.mm and the converter's configuration join the patch.
    require(files == ['Common/MVKStrings.h', 'MoltenVK/MoltenVK/GPUObjects/MVKImage.h', 'MoltenVK/MoltenVK/GPUObjects/MVKImage.mm',
                      'MoltenVK/MoltenVK/GPUObjects/MVKPipeline.h', 'MoltenVK/MoltenVK/GPUObjects/MVKPipeline.mm',
                      'MoltenVK/MoltenVK/GPUObjects/MVKShaderModule.h', 'MoltenVK/MoltenVK/GPUObjects/MVKShaderModule.mm',
                      'MoltenVK/MoltenVK/Utility/MVKCodec.h',
                      'MoltenVKShaderConverter/MoltenVKShaderConverter/SPIRVToMSLConverter.cpp',
                      'MoltenVKShaderConverter/MoltenVKShaderConverter/SPIRVToMSLConverter.h'], files)
    key = added_function(text, 'cacheKey', 'SPIRVToMSLConversionConfiguration')
    require('bool keep = rb.outIsUsedByShader;' in key and 'kept.outIsUsedByShader && kept.matches(rb)' in key and
            text.count('rewindBoxCacheKey(') == 4, 'a cached library is kept under its key: added, read and merged')
    # Lot 9, second part: the size query counts each entry once (measured by test/melonx_library_share/run_cache_size.py).
    count = added_function(text, 'countData', 'MVKPipelineCache')
    require('if (entrySize == 0)' in count and 'entrySize = cb.buffSize;' in count and 'total += entrySize;' in count and
            'writer(cacheIter.getCompressedMSL());' in count, 'an entry is counted once and its size kept')
    require('_dataSize = countData();' in text and '_pipelineCacheEntrySize = 0;' in text, 'the size query uses the kept sizes')
    require('\n-\t\t\t\twriteData(outStream, true);\n' in text, 'the full counting pass is gone from the size query')
    for marker in PIN['patchMarkers']:
        require(marker in text, 'the marker is compiled in: ' + marker)
    acquire = added_function(text, 'acquireAndSignalWhenAvailable')
    require('releaseMetalDrawable()' not in acquire.split('lock_guard<mutex> lock(_availabilityLock);')[0],
            'acquisition no longer releases the drawable')
    present = added_function(text, 'presentCAMetalDrawable')
    require('takeCAMetalDrawable()' in present and 'getCAMetalDrawable()' not in present, 'a present takes its drawable')
    # The hunk drops the separate keep-alive retain; the completion handler's [mtlDrwbl release] (unchanged, outside
    # the hunk's context) now releases the reference the present took.
    require('\n-\t[mtlDrwbl retain];\n' in text and not re.search(r'^\+.*\[mtlDrwbl retain\]', text, re.M),
            "the presentation's reference is the one taken (no separate retain)")
    take = added_function(text, 'takeCAMetalDrawable')
    require(re.search(r'lock_guard<mutex> lock\(_mtlDrawableLock\);\s*drawable = _mtlDrawable;\s*_mtlDrawable = nil;', take),
            'take reads and clears under the lock')
    release = added_function(text, 'releaseMetalDrawable')
    require(re.search(r'lock_guard<mutex> lock\(_mtlDrawableLock\);\s*drawable = _mtlDrawable;\s*_mtlDrawable = nil;', release)
            and release.rstrip().endswith('[drawable release];\t// Outside the lock: the release may run a completion callback.'),
            'release clears under the lock and releases outside it')
    get = added_function(text, 'getCAMetalDrawable')
    fetch = added_function(text, 'fetchCAMetalDrawable')
    require('nextDrawable' in fetch and '_mtlDrawableLock' not in fetch and 'nextDrawable' not in get,
            'nextDrawable is called with no lock held')
    require(get.count('lock_guard<mutex> lock(_mtlDrawableLock);') == 2, 'get reads and publishes under the lock')
    added = [line for line in text.splitlines() if line.startswith('+') and not line.startswith('+++')]
    require(not any('_mtlDrawable release]' in line for line in added), 'no unlocked release of _mtlDrawable is added')


def run_model(work, patched, sanitizer, mode, *extra):
    binary = work / f'model-{patched}-{sanitizer}'
    if not binary.exists():
        subprocess.run([COMPILER, '-std=c++17', '-O1', '-g', f'-fsanitize={sanitizer}', f'-DPATCHED={patched}',
                        str(MODEL), '-o', str(binary), '-lpthread'], check=True)
    env = {'TSAN_OPTIONS': 'halt_on_error=1', 'ASAN_OPTIONS': 'detect_leaks=0', 'PATH': '/usr/bin:/bin'}
    result = subprocess.run([str(binary), mode, *extra], capture_output=True, text=True, env=env, timeout=600)
    return result.returncode, result.stdout + result.stderr


COMPILER = shutil.which('g++')


def check_model():
    require(COMPILER is not None, 'g++ with AddressSanitizer and ThreadSanitizer is required')
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        code, out = run_model(work, 0, 'address', 'interleave')
        require(code != 0 and 'heap-use-after-free' in out and 'in retain' in out and 'addHandler' in out
                and 'presentCAMetalDrawable' in out,
                'control: the original frees the drawable before the handler block copy retains it\n' + out[-1500:])
        code, out = run_model(work, 1, 'address', 'interleave')
        require(code == 0 and 'still alive 0' in out, 'patched: no use after free, every drawable released\n' + out[-1500:])
        code, out = run_model(work, 0, 'thread', 'stress', '20000')
        require(code != 0 and 'data race' in out, 'control: a data race on the drawable\n' + out[-1500:])
        code, out = run_model(work, 1, 'thread', 'stress', '20000')
        require(code == 0 and 'drawables vended 20000, still alive 0' in out, 'patched: no race in 20000 presents\n' + out[-1500:])


def main():
    check_patch()
    check_model()
    print('melonx moltenvk drawable ownership: ok (patch pinned, 4 properties; model: use after free and race before, '
          'none after, 20000 presents balanced)')


if __name__ == '__main__':
    main()
