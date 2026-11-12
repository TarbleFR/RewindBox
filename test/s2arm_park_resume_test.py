#!/usr/bin/env python3
"""Relaunch in the same session, step 1: Quit parks the Switch 2 session, the same game resumes (plain python3).

build-utils/s2arm/engine/patches/0010-guest-park-and-resume-the-same-game.patch builds only on S2Arm's own in-process
restart (session.c restart_session, the one its iOS settings page uses). A park is that restart stopped before the
rebuild; a resume is its second half. These checks read the patch, the host bridge and the Dart service; the patch
is compiled by .github/workflows/s2arm-engine.yml. Nothing here proves the behaviour on a device.

    python3 -B test/s2arm_park_resume_test.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'build-utils/s2arm/engine/patches/0010-guest-park-and-resume-the-same-game.patch'
CLASSES = ROOT / 'packages/s2arm_engine_bridge/ios/Classes'
failures, checks = [], 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def section(text, path):
    """The diff of one file, as text (context and changed lines, without the leading marker)."""
    start = text.index(f'diff --git a/{path} b/{path}')
    end = text.find('\ndiff --git ', start + 1)
    lines = text[start:end if end != -1 else len(text)].splitlines()[4:]
    return '\n'.join(l[1:] if l[:1] in ' +-' else l for l in lines if not l.startswith('-'))


patch = PATCH.read_text(encoding='utf-8')
files = re.findall(r'^diff --git a/(\S+) b/', patch, re.M)
check(files == ['ios/app.m', 'runtime/include/s2a_session.h', 'runtime/src/rb_guest.c', 'runtime/src/rb_guest.h',
                'runtime/src/session.c'], f'patch 0010 touches the session, the guest layer and the iOS entry only: {files}')
check(len(re.findall(r'^\+.*patch 0010', patch, re.M)) >= 8, 'the changes are marked "patch 0010"')

# session.c after the patch (its hunks, in file order).
session = section(patch, 'runtime/src/session.c')
resume_start = session.index('if (atomic_load(&g_parked)) {   // RewindBox (patch 0010): resume')
# In restart_session the generation CAS succeeds, then signals the retirement completion: the park block must follow that
# signal directly (the hunk's context lines), so it runs only once the old generation is retired.
cas = session.index('            dispatch_semaphore_signal(g_retirement_completion);\n#endif\n            if (atomic_exchange(&g_park_request, 0)) {')
park = session.index('if (atomic_exchange(&g_park_request, 0)) {')
rebuild = session.index('if (g_rebuild()) detail = "新会话启动失败，请查看应用日志";')
check(resume_start < session.index('const char *detail = retirement_error(old);'),
      'a resume skips the retirement (the park did it) at the top of restart_session')
resume = session[resume_start:session.index('const char *detail = retirement_error(old);')]
check('g_rebuild()' in resume and 'restart_guest_publish_running(old)' in resume and 'atomic_store(&g_parked, 0);' in resume,
      'a resume is the restart\'s second half: rebuild, then publish RUNNING')
check('s2a_session_service_failed(old)' in resume, 'a failed resume fails the session (no half-started game)')
check(cas < park < rebuild, 'the park comes after the generation CAS (old generation retired) and before the rebuild')
parked = session[park:rebuild]
check('atomic_store(&g_parked, 1);' in parked and 'atomic_store(&g_park_done, 1);' in parked and 'return NULL;' in parked,
      'a park marks the session parked and returns before the rebuild')
check('if (!detail && !parked) restart_done_notify();' in session,
      'no restart-done hook for a park: the first-frame barrier stays closed until the resume')
check('atomic_store(&g_park_request, 0);   // RewindBox (patch 0010): a failed park is a failed restart' in session,
      'a failed park clears its request')
host_park = session[session.index('int s2a_host_park('):session.index('int s2a_host_resume(')]
check(host_park.index('atomic_store(&g_park_request, 1);') < host_park.index('s2a_host_restart(callback, context)') <
      host_park.index('if (result) atomic_store(&g_park_request, 0);'), 's2a_host_park is s2a_host_restart, flagged before the request')
host_resume = session[session.index('int s2a_host_resume('):]
check('!atomic_load(&g_parked)' in host_resume and 'g_lifecycle_transition_active' in host_resume and 'wake_control();' in host_resume,
      's2a_host_resume runs only on a parked session, outside a lifecycle transition, through the control worker')

# The guest layer: stop parks only when the host can resume; any refusal or failure ends as before the patch.
guest = section(patch, 'runtime/src/rb_guest.c')
stop = guest[guest.index('void s2a_rb_guest_stop('):]
check('if (g_cfg.session_parked && s2a_session_rebuild_supported()) {' in stop and 's2a_host_park(park_result' in stop,
      'Quit parks only with a host callback and an engine that can rebuild in-process')
check(stop.count('s2a_host_shutdown(why)') == 1 and 'park_result' in guest and
      'dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ s2a_host_shutdown(why); });' in
      guest[guest.index('static void park_result('):guest.index('void s2a_rb_guest_stop(')],
      'a refused or failed park falls back to the orderly shutdown (session_ended follows)')
check('offsetof(s2a_rb_guest_config, session_parked)' in guest and 'memcpy(&g_cfg, c, c->size < sizeof g_cfg ? c->size : sizeof g_cfg);' in guest,
      'a host built before patch 0010 (shorter config) is still accepted, without park')
check('s2a_rb_guest_ended(EXIT_FAILURE' in guest[guest.index('static void resume_result('):], 'a failed resume ends the session for the host')
header = section(patch, 'runtime/src/rb_guest.h')
config = header[header.index('typedef struct s2a_rb_guest_config'):header.index('} s2a_rb_guest_config;')]
check(config.rstrip().endswith('void *parked_context;'), 'session_parked and parked_context are the last members')
app = section(patch, 'ios/app.m')
check('!g_rb_vc.view.window ? "the view controller is not in a window yet: present it first"' in app and
      's2a_rb_guest_resume_session(error, error_size)' in app, 'the resume waits for the view controller to be in a window again')

# Exports: the host looks the new entry points up with dlsym; the restricted export list must keep them.
exports = (ROOT / 'build-utils/s2arm/engine/export_list.py').read_text()
engine_yml = (ROOT / '.github/workflows/s2arm-engine.yml').read_text()
for name in ('s2a_rb_guest_parked', 's2a_rb_guest_view_controller', 's2a_rb_guest_resume'):
    check(f"'{name}'" in exports, f'{name} is in the restricted export list')
    check(f'_{name}' in engine_yml, f'the engine build checks that {name} is exported')

# The host bridge: the same game resumes without dlopen, configure or JIT; another game is still refused.
plugin = (CLASSES / 'S2ArmEngineBridgePlugin.m').read_text()
resume_method = plugin[plugin.index('- (NSDictionary *)resumeParkedGame:'):plugin.index('static NSDictionary *launchFail(')]
for absent in ('dlopen(', 'configure(', 'attachHelperWithPairing', 'jitSession', 's2arm_code_prepare_pool'):
    check(absent not in resume_method, f'resuming the parked game does not call {absent}')
check('resume(error, sizeof error)' in resume_method and 'presentViewController:vc' in resume_method and
      resume_method.index('presentViewController:vc') < resume_method.index('resume(error, sizeof error)'),
      'the bridge presents the parked view controller, then resumes in the presentation\'s completion')
check("[self.parkedGameId caseInsensitiveCompare:gid] == NSOrderedSame" in plugin, 'only the parked title id resumes')
check('config.session_parked = s2arm_session_parked;' in plugin and '@"parkedGameId" : self.parkedGameId ?: @""' in plugin,
      'the bridge asks for parks and reports the parked game in its status')
ended = plugin[plugin.index('static void s2arm_session_ended(int code, const char *reason, void *context) {'):]
check('self.parkedGameId = nil;' in ended[:400], 'an end (or a failed resume) leaves nothing to resume')

service = (ROOT / 'lib/services/s2arm_internal_service.dart').read_text()
check("final parked = (now['parkedGameId'] ?? '').toString().toUpperCase();" in service and
      "(detected['gid'] ?? '').toString().toUpperCase() != parked" in service, 'Dart lets only the parked game launch again')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks}))
sys.exit(1 if failures else 0)
