#!/usr/bin/env python3
"""Authenticate the produced Core, then test rejection of altered delivery evidence.

No native program, compiler, source preparation or historical test is executed.
The unmodified case must first authenticate the actual successful Apple archive.
"""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
import rpcs3runtime604_core as candidate


def run():
    manifest, inputs, identity, proof = candidate._core_contract()
    candidate.compatibility()
    candidate._bundle()
    cases = [
        ('identity producer', 'identity', ('host_commit',), '0' * 40),
        ('native producer', 'identity', ('native_source_commit',), '0' * 40),
        ('ABI', 'identity', ('abi_version',), 31),
        ('architecture', 'identity', ('architectures',), ['x86_64']),
        ('identity type', 'identity', ('type',), 'rpcs3-ios-device597-source-candidate'),
        ('binary identity', 'identity', ('sha256',), '0' * 64),
        ('codegen identity', 'identity', ('codegen', 'SPU'), '0' * 16),
        ('compiled patch', 'identity', ('source_patch_sha256',), '0' * 64),
        ('proof producer', 'proof', ('source',), '0' * 40),
        ('proof completion', 'proof', ('all_tests_passed',), False),
        ('compiler identity', 'proof', ('host', 'compiler'), 'another compiler'),
        ('Apple host', 'proof', ('host', 'system'), 'Linux'),
        ('current mode count', 'proof', ('native_modes_executed_now',), 12),
        ('reused mode count', 'proof', ('native_modes_reused',), 0),
        ('old Core mislabel', 'proof', ('native_reuse', 'old_core_built'), True),
        ('historical scope', 'proof', ('historical', 'validates_new_paths'), True),
        ('historical execution', 'proof', ('historical', 'native_executed_now'), 28),
        ('device claim', 'proof', ('physical_device_tested',), True),
        ('reused mode relabel', 'proof', ('tests', 'tiny-vertex-plain', 'native_executed_now'), True),
        ('fresh mode relabel', 'proof', ('tests', 'mfc-decrementer-plain', 'native_executed_now'), False),
        ('failed current mode', 'proof', ('tests', 'mfc-decrementer-plain', 'passed'), False),
        ('reused compiler execution', 'proof', ('tests', 'tiny-vertex-plain', 'current_relevance', 'compiler_executed'), True),
        ('reused provenance', 'proof', ('tests', 'tiny-vertex-plain', 'reused_from', 'run'), 0),
    ]
    first_core_input = sorted(identity['core_input_sha256'])[0]
    first_validation_input = sorted(proof['input_sha256'])[0]
    first_native_input = sorted(manifest['files_sha256'])[0]
    cases.extend([
        ('compiler source bytes', 'identity', ('core_input_sha256', first_core_input), '0' * 64),
        ('validation source bytes', 'proof', ('input_sha256', first_validation_input), '0' * 64),
        ('native postimage', 'identity', ('native_source_sha256', first_native_input), '0' * 64),
    ])
    rejected = []
    for label, target, keys, value in cases:
        original = {'identity': copy.deepcopy(identity), 'proof': copy.deepcopy(proof)}
        node = original[target]
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value
        try:
            candidate._validate_contract(original['identity'], original['proof'])
        except ValueError:
            rejected.append(label)
        else:
            raise AssertionError('Accepted altered evidence: ' + label)
    return dict(passed=True, coreSource=candidate.CORE_SOURCE,
                coreRun=candidate.CORE_RUN, coreSHA256=candidate.CORE_SHA256,
                originalAppleArtifactAuthenticated=True, rejectedMutations=rejected,
                canonicalPostimages=len(manifest['files_sha256']), compiledInputs=len(inputs),
                nativeExecutedNow=False, compilerExecutedNow=False,
                physicalDeviceTested=False)


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
