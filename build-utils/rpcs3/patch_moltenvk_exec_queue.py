#!/usr/bin/env python3
"""REWINDBOX_MOLTENVK_EXEC_BARRIER_V1: let the RPCS3 Core see MoltenVK's encoding queue.

With asynchronous submits, MoltenVK 1.4.2 creates one serial GCD queue per
VkQueue (MVKQueue::initExecQueue, MVKQueue.mm:324) with
    dispatch_queue_create((getName() + "-Dispatch").c_str(), dqAttr)
and encodes every vkQueueSubmit and vkQueuePresentKHR on it after the call
has returned. The RPCS3 Core 587 waits on that queue before
vkAcquireNextImageKHR (rpcs3/ios/IOSMoltenVKExec.h), which it can do only if
it knows the queue.

That call is the archive's only relocation to _dispatch_queue_create. This
tool renames the undefined symbol, in place and with the same length, to
_rbx_mvk_exec_q_create, which the RPCS3 Core defines
(rpcs3/ios/RPCS3IOSPlatform.mm) and which creates the queue unchanged. It runs
on the archive patched by patch_moltenvk_compile_qos.py; nothing else in the
archive changes. Input and output digests are pinned.

Usage: patch_moltenvk_exec_queue.py <libMoltenVK.a> [--check]
"""
import hashlib, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import patch_moltenvk_compile_qos as qos

ORIGINAL_SHA256 = qos.PATCHED_SHA256
PATCHED_SHA256 = '0ee6ae968193749e56d76be71dafb7c36ce4aa19b84f5bb69acd8154d38e06a1'
OLD = b'_dispatch_queue_create\0'
NEW = b'_rbx_mvk_exec_q_create\0'
assert len(OLD) == len(NEW)


def main():
    path = Path(sys.argv[1])
    check = '--check' in sys.argv[2:]
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest == PATCHED_SHA256:
        qos.symbol(data, NEW)
        qos.symbol(data, qos.NEW)
        print(f'MoltenVK encoding queue: already patched ({digest})')
        return
    assert not check, f'{path} is not the patched archive ({digest})'
    assert digest == ORIGINAL_SHA256, f'expected the compile-QoS archive, got {digest}'
    member, at = qos.symbol(data, OLD)
    assert NEW not in data
    patched = data[:at] + NEW + data[at + len(NEW):]
    assert len(patched) == len(data) and sum(a != b for a, b in zip(data, patched)) <= len(NEW)
    qos.symbol(patched, NEW)
    qos.symbol(patched, qos.NEW)
    out = hashlib.sha256(patched).hexdigest()
    assert out == PATCHED_SHA256, out
    tmp = path.with_suffix('.exec-tmp')
    tmp.write_bytes(patched)
    tmp.replace(path)
    print(f'MoltenVK encoding queue: {member}: _dispatch_queue_create -> _rbx_mvk_exec_q_create ({digest} -> {out})')


if __name__ == '__main__':
    main()
