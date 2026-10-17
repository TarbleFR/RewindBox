"""CI device selection shared by exact-source launch and memory probes."""
import json
import subprocess

def pick_notched_device():
    listing = json.loads(subprocess.check_output(
        ['xcrun','simctl','list','devices','available','--json'], text=True))
    candidates = [(runtime, device['name'], device['udid'])
                  for runtime, devices in listing['devices'].items() for device in devices
                  if device.get('isAvailable') and device['name'].startswith('iPhone')
                  and 'Pro' in device['name'] and 'SE' not in device['name']]
    if not candidates:
        raise RuntimeError('No notched iPhone Simulator available')
    runtime, name, udid = sorted(candidates, reverse=True)[0]
    print('notched Simulator:',name,runtime,udid,flush=True)
    return udid, name + ' ' + runtime
