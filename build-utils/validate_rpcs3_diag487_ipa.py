"""Inspect the actual Build 487 IPA: the RPCS3 Core and the RPCS3 bridge carry the audit diagnostics.

Core (Frameworks/libRPCS3Core.dylib): the FREEZE_DUMP, MUTEX_DESTROY_BUSY, new
COREPROF and lever log formats of NEOSTATION_BUILD487_DIAGNOSTICS_V1 and the
three new settings catalogue keys.
Bridge (Frameworks/rpcs3_internal_bridge.framework): the admitted tokens, the
milestone stages, the new performance_sample fields and the rotated diagnostic
file. Compiled literals only; this proves the shipped bytes, not iPhone
behaviour.
"""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import zipfile

# Literals the compiled Core really keeps: logging format strings and settings
# catalogue entries (short std::string prefixes may be materialized as
# immediates, so the boot line prefixes are proven by the host tests instead).
CORE_MARKERS = (b'FREEZE_DUMP begin dump=%llu reason=%s', b'MUTEX_DESTROY_BUSY mutex_id=0x%x owner_id=0x%x',
                b'rsx_fifo_busy=%.1f rsx_thread_cpu=%.3f top=%s', b'SPU spin timing at Core init: spin_timing=%s',
                b'SPU object cache: retained %u other director', b'experimental.spu_spin_timing',
                b'experimental.spu_object_cache_retained_keys', b'experimental.spu_warmup_scope', b'Bounded sleep')
BRIDGE_MARKERS = (b'JITPROF_BOOT ', b'CONFIG_LAYERS ', b'NEOSTATION_RESTART ', b'SAVESTATE_BOOT ', b'FREEZE_DUMP begin ',
                  b'MUTEX_DESTROY_BUSY ', b'jitprof_boot', b'config_layers', b'internal_restart', b'savestate_boot',
                  b'freeze_dump', b'mutex_destroy_busy', b'emu_state=%@ boot_progress=%@ guest_frames=%@ native_ui=%@',
                  b'.1.log')


def validate(ipa, build):
    if build < 487:
        raise ValueError('The Build 487 diagnostics start with Build 487')
    with zipfile.ZipFile(ipa) as z:
        names = z.namelist()
        apps = {n.split('/')[1] for n in names if n.startswith('Payload/') and '.app/' in n}
        if len(apps) != 1:
            raise ValueError('Expected exactly one app')
        root = 'Payload/' + apps.pop() + '/'
        info = plistlib.loads(z.read(root + 'Info.plist'))
        if info['CFBundleVersion'] != str(build):
            raise ValueError('Wrong IPA build')
        core = z.read(root + 'Frameworks/libRPCS3Core.dylib')
        bridge = z.read(root + 'Frameworks/rpcs3_internal_bridge.framework/rpcs3_internal_bridge')
    missing = [m.decode() for m in CORE_MARKERS if m not in core]
    if missing:
        raise ValueError('The packaged RPCS3 Core lacks ' + ', '.join(missing))
    missing = [m.decode() for m in BRIDGE_MARKERS if m not in bridge]
    if missing:
        raise ValueError('The packaged RPCS3 bridge lacks ' + ', '.join(missing))
    return {'result': 'passed', 'build': build, 'coreSHA256': hashlib.sha256(core).hexdigest(),
            'bridgeSHA256': hashlib.sha256(bridge).hexdigest(), 'coreMarkers': len(CORE_MARKERS),
            'bridgeMarkers': len(BRIDGE_MARKERS), 'ipaSHA256': hashlib.sha256(Path(ipa).read_bytes()).hexdigest(),
            'physicalDeviceValidated': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('ipa', type=Path)
    p.add_argument('--build-number', type=int, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    result = validate(a.ipa, a.build_number)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, indent=2) + '\n')
    print(f"PASS Build 487 diagnostics in the actual IPA: {result['coreMarkers']} Core and "
          f"{result['bridgeMarkers']} bridge markers")
