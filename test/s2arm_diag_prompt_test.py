#!/usr/bin/env python3
"""Patch 0018: in a RewindBox guest the diagnostics question comes from the engine's own session marker (plain python3).

Device, 13 Nov (IPA 734, screenshot of the load page at `Prepare game`): an alert `Send us diagnostics from last time?`
/ `The system reported that S2Arm crashed or froze last time`. The engine log of that start has both of the engine's
reasons to ask: `诊断包：上次会话标记 前台未收尾` (its own session marker: the last Switch 2 session did not end) and
`诊断包：MetricKit 交来 1 份诊断（新的崩溃 / 卡顿 1）`. The alert shown was MetricKit's. MetricKit reports the whole
host app: that payload held this engine's abort of 04:43 (process 61801) and the disk-write and CPU reports of
process 1236, which never started this engine (it is absent from the Switch 2 launch journal). A crash or a hang of any
other part of RewindBox was thus put to the player as `S2Arm crashed or froze`.

Patch 0018:
- in a guest (s2a_rb_guest_on) a MetricKit payload no longer asks; it is still written to the bundle's folder. The
  session marker asks, as before, when the last Switch 2 session did not end normally;
- the in-game Quit of a guest parks the session (patch 0010) instead of shutting the engine down, so the orderly end
  that deletes the marker never came: the marker stayed "fg" for a game the player had quit, and an end of the host app
  in the foreground afterwards asked the question at that game's next start. A parked session now deletes its marker
  and does not write it while parked; a resume writes it again (review of 13 Nov);
- the button builds a ZIP and opens the share sheet, nothing is sent: the title and the button say `Export`;
- a French table with the question's six strings; S2AL reads a key a table lacks from the English one.

After a session that really ended abnormally (the crash of 13 Nov is one) the question is asked once at the next
start: that is the engine saying so, not a fault of the start. What the marker does not see is no longer asked about
in a guest, since MetricKit was the second net: an engine that hangs while the app goes to the background (the marker
already says "bg" then), a crash in the background or before the engine's diagnostics are attached, and hangs. The
payloads are still kept, so an export made by hand holds them.
The marker's functions are compiled from the patch and run here (parks, resumes, and parks against changes from
another thread). The engine is compiled by s2arm-engine.yml; the alert itself is only seen on a device.

    python3 -B test/s2arm_diag_prompt_test.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / 'build-utils/s2arm/engine/patches'
PATCH = PATCHES / '0018-guest-diagnostics-question-from-the-session-marker.patch'
HARNESS = ROOT / 'test/s2arm_session_marker_harness.c'
failures, checks = [], 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)


def ordered(text, *parts):
    at = -1
    for part in parts:
        at = text.find(part, at + 1)
        if at < 0:
            return False
    return True


def sections(patch):
    found = {}
    for part in re.split(r'^(?=diff --git )', patch, flags=re.M):
        match = re.match(r'diff --git a/(\S+) b/', part)
        if match:
            found[match.group(1)] = part
    return found


def plus(part):
    return '\n'.join(line[1:] for line in part.splitlines() if line.startswith('+') and not line.startswith('+++'))


def minus(part):
    return '\n'.join(line[1:] for line in part.splitlines() if line.startswith('-') and not line.startswith('---'))


def table(text):
    return dict(re.findall(r'^"([^"]+)" = "(.*)";$', text, re.M))


patch = PATCH.read_text(encoding='utf-8') if PATCH.is_file() else ''
check(bool(patch), 'patch 0018 exists')
files = sections(patch)
EN, ZH, FR = 'ios/l10n/en.lproj/S2ArmHost.strings', 'ios/l10n/zh-Hans.lproj/S2ArmHost.strings', 'ios/l10n/fr.lproj/S2ArmHost.strings'
MARK_C, MARK_H, GUEST = 'runtime/src/sesdiag.c', 'runtime/include/s2a_sesdiag.h', 'runtime/src/rb_guest.c'
check(sorted(files) == sorted(['ios/diag.m', 'ios/s2a_l10n.h', EN, ZH, FR, MARK_C, MARK_H, GUEST]),
      f'patch 0018 touches diag.m, s2a_l10n.h, the three string tables, the session marker and the guest\'s park: {sorted(files)}')

# ---- who asks ----
diag = files.get('ios/diag.m', '')
check(ordered(diag, '     mk_trim(dir, NO);', '     LOG("诊断包：MetricKit 交来 %lu 份诊断（新的崩溃 / 卡顿 %d）"',
              '+    int (*guest)(void) = (int (*)(void))dlsym(RTLD_DEFAULT, "s2a_rb_guest_on");', '+    if (bad && guest && guest()) {', 'return; }',
              '     if (bad) dispatch_async(dispatch_get_main_queue()', 's2a_diag_prompt(S2AL(@"diag.prompt.crash"))'),
      'a MetricKit payload is written, trimmed and counted as before (the change comes after them); in a guest it does not ask, outside a guest it asks as S2Arm does')
check(not minus(diag).strip(), 'nothing of the diagnostics code is removed: the session marker still asks (s2a_diag_attach), the payloads are still kept')
check('the session marker decides' in plus(diag), 'the engine log says why MetricKit did not ask')

# ---- what the alert says ----
en, zh, fr = files.get(EN, ''), files.get(ZH, ''), files.get(FR, '')
check(table(minus(en)) == {'diag.prompt.send': 'Send diagnostics', 'diag.prompt.title': 'Send us diagnostics from last time?'}
      and table(plus(en)) == {'diag.prompt.send': 'Export diagnostics', 'diag.prompt.title': 'Export diagnostics from last time?'},
      'English: the title and the button say Export (the button opens the share sheet with a ZIP; nothing is sent); no other string changes')
check(sorted(table(minus(zh))) == ['diag.prompt.send', 'diag.prompt.title'] and sorted(table(plus(zh))) == ['diag.prompt.send', 'diag.prompt.title']
      and all('发' not in value for value in table(plus(zh)).values()) and all('导出' in value for value in table(plus(zh)).values()),
      'Chinese: the same two strings, and they say export, not send')
check('new file mode' in fr and not minus(fr), 'fr.lproj/S2ArmHost.strings is a new file')
french = table(plus(fr))
QUESTION = ['diag.prompt.abnormalExit', 'diag.prompt.crash', 'diag.prompt.message', 'diag.prompt.no', 'diag.prompt.send', 'diag.prompt.title']
check(sorted(french) == QUESTION,
      f'the French table holds the six strings of the question and nothing else (diag.export is also a row of the settings page and a button of the notice pages, which stay English): {sorted(french)}')
check(french.get('diag.prompt.message', '').count('%@') == 1 and french.get('diag.prompt.message', '').startswith('%@. ') and all('%' not in french.get(key, '') for key in QUESTION if key != 'diag.prompt.message'),
      'the French message takes the reason where the English one does (one %@, first), and no other string has a placeholder')
check(all(value and '"' not in value and '\\' not in value for value in french.values()), 'no French string needs escaping in a .strings file')
check('Exporter' in french.get('diag.prompt.title', '') and french.get('diag.prompt.send') == 'Exporter le diagnostic' and 'transmis à personne' in french.get('diag.prompt.message', ''),
      'French: export, and the message says the file is sent to no one')

# ---- a table that holds only some keys ----
l10n = files.get('ios/s2a_l10n.h', '')
check(minus(l10n).strip() == '#define S2AL(key) [s2a_l10n_bundle() localizedStringForKey:(key) value:nil table:@"S2ArmHost"]', 'S2AL was a direct lookup in the bundle\'s chosen table')
helper = plus(l10n)
check(ordered(helper, 'static inline NSString *s2a_l10n(NSString *key) {', '[bundle localizedStringForKey:key value:@"\\x01" table:@"S2ArmHost"]', 'if (![text isEqualToString:@"\\x01"]) return text;',
              '[bundle pathForResource:@"en" ofType:@"lproj"]', '[NSBundle bundleWithPath:path]', 'return [(english ?: bundle) localizedStringForKey:key value:nil table:@"S2ArmHost"];',
              '#define S2AL(key) s2a_l10n(key)'),
      'a key the chosen table holds is returned as before; one it lacks is read from en.lproj (and shown as its id only when English lacks it too, as before)')

# ---- a parked session is at rest ----
guest = files.get(GUEST, '')
check(ordered(guest, ' static void park_result(int result, const char *detail, void *context) {', ' LOG("RewindBox guest: session parked (%s); the same game can resume in this process", why);',
              '+        s2a_sesmark_rest_home(1);', ' int s2a_rb_guest_resume_session(char *error, size_t error_size) {',
              ' if (rc) return refuse(error, error_size, "the parked session could not resume now (%d)", rc);', '+    s2a_sesmark_rest_home(0);', ' LOG("RewindBox guest: resume requested");')
      and '+#include "s2a_sesdiag.h"' in guest and len(plus(guest).splitlines()) == 3 and not minus(guest).strip(),
      'the guest tells the marker when its session is parked (the in-game Quit) and when a resume is accepted (from there on a failed resume or a crash is asked about); '
      'a park that fails still goes to the orderly shutdown, which deletes the marker')
marker = files.get(MARK_C, '')
post = '\n'.join(line[1:] for line in marker.splitlines() if line[:1] in (' ', '+') and not line.startswith('+++')) + '\n'
check(ordered(post, 'static pthread_mutex_t g_mark_mu = PTHREAD_MUTEX_INITIALIZER;', 'static void mark_write(const char *docs, int state) {', 'void s2a_sesmark_set(const char *docs, int state) {',
              'if (state != S2A_SESMARK_NONE) g_mark_last = state;', 'if (state == S2A_SESMARK_NONE || !g_mark_rest) mark_write(docs, state);', 'void s2a_sesmark_rest(const char *docs, int rest) {',
              'g_mark_rest = rest != 0;', 'mark_write(docs, rest ? S2A_SESMARK_NONE : g_mark_last);', 'static int mark_home(char *d, size_t n) {', 'void s2a_sesmark_clear_home(void) {',
              'void s2a_sesmark_rest_home(int rest) {', 's2a_sesmark_rest(d, rest);'),
      'at rest the marker is deleted and not written; the app\'s last change is kept and written at the resume; an orderly end always deletes; one lock over the state and the file')
check(ordered(minus(marker), 'void s2a_sesmark_set(const char *docs, int state) {', 'char d[1030]; int r = s2a_container_docs(d, sizeof d);') and 'unlink' not in minus(marker) and 'O_TRUNC' not in minus(marker),
      "the write of the marker itself is S2Arm's, unchanged (it moved into mark_write); the folder is found as before (mark_home)")
check('+void s2a_sesmark_rest(const char *docs, int rest);' in files.get(MARK_H, '') and '+void s2a_sesmark_rest_home(int rest);' in files.get(MARK_H, ''), 's2a_sesdiag.h declares both')
check(HARNESS.is_file(), 'test/s2arm_session_marker_harness.c exists')
compiler = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
check(bool(compiler), 'a C compiler is available (cc, clang or gcc)')
ran = ''
if compiler and HARNESS.is_file() and 'static pthread_mutex_t g_mark_mu' in post and 'void s2a_sesmark_rest(const char *docs, int rest) {' in post:
    start = post.index('static pthread_mutex_t g_mark_mu = PTHREAD_MUTEX_INITIALIZER;')
    end = post.index('\n}\n', post.index('void s2a_sesmark_rest(const char *docs, int rest) {')) + 3
    with tempfile.TemporaryDirectory() as work:
        (Path(work) / 'rb_sesmark.inc').write_text(post[start:end], encoding='utf-8')
        (Path(work) / 'docs').mkdir()
        binary = Path(work) / 'marker'
        build = subprocess.run([compiler, '-std=c11', '-D_GNU_SOURCE', '-D_DARWIN_C_SOURCE', '-Wall', '-Wextra', '-Werror', '-O1', '-I', work, '-o', str(binary), str(HARNESS), '-lpthread'],
                               capture_output=True, text=True)
        check(build.returncode == 0, 'the marker functions of the patch and the harness compile without a warning: ' + build.stderr[-700:])
        if build.returncode == 0:
            run = subprocess.run([str(binary), str(Path(work) / 'docs')], capture_output=True, text=True, timeout=300)
            ran = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else ''
            check(run.returncode == 0 and ran.startswith('PASSED'), 'the marker harness passes: ' + run.stdout[-900:] + run.stderr[-300:])

guest_mk = (ROOT / 'build-utils/s2arm/engine/guest.mk').read_text(encoding='utf-8')
check('cp -R ios/l10n/*.lproj' in guest_mk, 'guest.mk copies every table of ios/l10n into the framework, the French one with them')
check(plus(patch).count('RewindBox (patch 0018)') >= 5 and plus(patch).count('patch 0018') >= 8, 'the changes are marked RewindBox (patch 0018)')
series = sorted(p.name for p in PATCHES.glob('*.patch'))
check(len(series) >= 18 and series[17] == PATCH.name, f'0018 is the 18th engine patch: {series[16:19]}')
notices = (ROOT / 'docs/s2arm-legal-notices.md').read_text(encoding='utf-8')
check(PATCH.name in notices and FR in notices, 'the legal notices list patch 0018 and its new file')
readme = (ROOT / 'build-utils/s2arm/engine/README.md').read_text(encoding='utf-8')
check(PATCH.name in readme, 'the engine README explains patch 0018')

for failure in failures:
    print('FAIL ' + failure)
print(json.dumps({'result': 'failed' if failures else 'passed', 'checks': checks, 'harness': ran}))
sys.exit(1 if failures else 0)
