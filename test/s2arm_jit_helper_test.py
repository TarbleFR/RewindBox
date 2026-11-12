#!/usr/bin/env python3
"""The S2Arm JIT helper package is the RPCS3 helper with documented renames only, and its script works.

    python3 -B test/s2arm_jit_helper_test.py

- every file of packages/s2arm_jit_helper is the RPCS3 source named in copy-of-rpcs3.json with exactly the
  recorded replacements (and the recorded source bytes): the debugger protocol cannot drift by accident;
- the identifiers the host, the configure script and the IPA validator rely on agree with each other;
- the actual s2arm-universal.js runs under Node against a deterministic debugserver: attach, PID check,
  probe round trip (nonce + 1), region preparation at a given address and at an allocated one, detach, and
  the refusals of the RPCS3 harness (test/rpcs3_debugger_handshake_test.js). Skipped without Node.
Nothing here builds Swift or runs on an iPhone.
"""
from __future__ import annotations

import hashlib
import json
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/s2arm_jit_helper'
RECORD = PACKAGE / 'copy-of-rpcs3.json'
SCRIPT = PACKAGE / 'ios/Resources/s2arm-universal.js'
HANDLER = PACKAGE / 'ios/Classes/S2ArmJITRequestHandlerBase.swift'
JOURNAL = PACKAGE / 'ios/Classes/S2ArmHelperJournal.swift'
ENTRY = PACKAGE / 'extension/S2ArmJITExtensionEntry.swift'
INFO = PACKAGE / 'extension/Info.plist'
PODSPEC = PACKAGE / 'ios/s2arm_jit_helper.podspec'
REQUEST_TYPE = 'com.neogamelab.neostation.s2arm-jit-request'
MARKERS = ('NEOSTATION_S2ARM_STIKJIT_UNIVERSAL_V1', 'NEOSTATION_S2ARM_DEBUGGER_ATTACHED_V1',
           'NEOSTATION_S2ARM_DEBUGGER_PROBE_V1')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def renamed(spec):
    text = (ROOT / spec['source']).read_text()
    for old, new, count in spec['replacements']:
        if text.count(old) != count:
            raise AssertionError(f'{spec["source"]}: {old!r} occurs {text.count(old)} times, the record says {count}')
        text = text.replace(old, new)
    return text


class Copy(unittest.TestCase):
    def test_every_file_is_the_recorded_rename_of_its_source(self):
        record = json.loads(RECORD.read_text())
        self.assertEqual(record['schema'], 1)
        listed = {path for path in record['files']}
        actual = {path.relative_to(ROOT).as_posix() for path in PACKAGE.rglob('*') if path.is_file()} - {
            RECORD.relative_to(ROOT).as_posix()}
        self.assertEqual(listed, actual, 'every file of the package comes from a recorded source')
        for target, spec in record['files'].items():
            with self.subTest(target=target):
                source = (ROOT / spec['source']).read_bytes()
                self.assertEqual(sha(source), spec['sourceSha256'],
                                 f'{spec["source"]} changed since the S2Arm copy was made: review whether the copy '
                                 'follows, then update the copy and its record')
                self.assertEqual((ROOT / target).read_text(), renamed(spec))
                self.assertNotRegex((ROOT / target).read_text(), r'(?i)rpcs3')

    def test_the_protocol_is_not_renamed(self):
        original = (ROOT / 'packages/rpcs3_jit_helper/ios/Resources/rpcs3-universal.js').read_text()
        script = SCRIPT.read_text()

        def protocol(text):
            commands = re.search(r'const commands = \{(.*?)\};', text, re.S).group(1)
            legacy = re.search(r'const legacyCommands = \{(.*?)\};', text, re.S).group(1)
            constants = re.findall(r'^const (CMD_\w+) = (\d+);', text, re.M)
            return commands, legacy, constants
        self.assertEqual(protocol(script), protocol(original))
        self.assertEqual(protocol(script)[2], [('CMD_DETACH', '0'), ('CMD_PREPARE_REGION', '1'),
                                               ('CMD_NEW_BREAKPOINTS', '2')])
        self.assertIn('[3]: NeoStationDebuggerProbe', protocol(script)[0])
        # Same request fields and reporter events as the RPCS3 helper.
        handler, rpcs3 = HANDLER.read_text(), (ROOT / 'packages/rpcs3_jit_helper/ios/Classes/'
                                                       'Rpcs3JITRequestHandlerBase.swift').read_text()
        fields = re.compile(r'object\["(\w+)"\]')
        events = re.compile(r'event: "(\w+)"')
        self.assertEqual(fields.findall(handler), fields.findall(rpcs3))
        self.assertEqual(set(fields.findall(handler)), {'protocolVersion', 'targetPID', 'port', 'token', 'pairingData',
                                                         'probeNonce', 'requiresCoreHandshake'})
        self.assertEqual(events.findall(handler), events.findall(rpcs3))
        self.assertEqual(set(events.findall(handler)), {'helper_connected', 'log', 'pid_attached', 'complete'})


class Identifiers(unittest.TestCase):
    def test_request_type_marker_principal_class_and_markers_agree(self):
        handler = HANDLER.read_text()
        self.assertIn(f'private let s2armRequestType = "{REQUEST_TYPE}"', handler)
        info = plistlib.loads(INFO.read_bytes())
        self.assertEqual(info['NeoStationS2ArmJITHelper'], '1')
        self.assertNotIn('NeoStationRPCS3JITHelper', info)
        self.assertEqual(info['NSExtension']['NSExtensionPointIdentifier'], 'com.apple.share-services')
        self.assertEqual(info['NSExtension']['NSExtensionPrincipalClass'], 'S2ArmJITRequestHandler')
        self.assertEqual(info['CFBundlePackageType'], 'XPC!')
        self.assertEqual(info['NSExtension']['NSExtensionAttributes'], {'NSExtensionActivationRule': 'FALSEPREDICATE'})
        self.assertIn('@objc(S2ArmJITRequestHandler)', ENTRY.read_text())
        self.assertIn('import s2arm_jit_helper', ENTRY.read_text())
        podspec = PODSPEC.read_text()
        self.assertIn("s.name             = 's2arm_jit_helper'", podspec)
        self.assertIn("s.module_name = 's2arm_jit_helper'", podspec)
        self.assertIn("s.resources        = 'Resources/*.js'", podspec)
        # The attach line the script logs is the one the handler waits for before reporting pid_attached.
        script = SCRIPT.read_text()
        self.assertIn('log(`NEOSTATION_S2ARM_DEBUGGER_ATTACHED_V1 pid=${pid} nonce=${neostationProbeNonce}`);', script)
        self.assertIn('let attached = "NEOSTATION_S2ARM_DEBUGGER_ATTACHED_V1 pid=\\(targetPID) nonce=\\(probeNonce.uint64Value)"',
                      handler)
        self.assertIn('"const neostationProbeNonce = \\(probeNonce.uint64Value);\\n" + source', handler)
        self.assertIn('forResource: "s2arm-universal", withExtension: "js"', handler)
        for marker in MARKERS:
            self.assertIn(marker, script)
        # The journal keeps every S2Arm debugger line and nothing of another engine.
        journal = JOURNAL.read_text()
        prefixes = re.findall(r'message\.hasPrefix\("(\w+)"\)', journal)
        self.assertEqual(prefixes, ['S2ARM_', 'NEOSTATION_S2ARM_PREPARE_', 'NEOSTATION_S2ARM_DEBUGGER_'])
        for marker in MARKERS[1:]:
            self.assertTrue(any(marker.startswith(prefix) for prefix in prefixes), marker)
        self.assertFalse(any('NEOSTATION_DEBUGGER_ATTACHED_V1'.startswith(prefix) for prefix in prefixes))
        self.assertIn('append("S2ARM_JOURNAL_BEGIN")', journal)

    def test_temporary_and_library_folders_are_the_helpers_own(self):
        handler = HANDLER.read_text()
        self.assertIn('.appendingPathComponent("NeoStationS2ArmJIT", isDirectory: true)', handler)
        self.assertIn('"NeoStationS2ArmStikJIT",', handler)
        names = set()
        for path in ROOT.glob('packages/*_jit_helper/ios/Classes/*JITRequestHandlerBase.swift'):
            if path != HANDLER:
                names.update(re.findall(r'"(NeoStation\w*JIT)"', path.read_text()))
        self.assertTrue(names)
        self.assertFalse({'NeoStationS2ArmJIT', 'NeoStationS2ArmStikJIT'} & names)


HARNESS = r'''
// The actual bundled script against a deterministic debugserver (same harness as
// test/rpcs3_debugger_handshake_test.js, with the S2Arm markers and the region commands).
const fs = require('fs');
const vm = require('vm');
const assert = require('node:assert/strict');
const script = fs.readFileSync(process.argv[2], 'utf8');
const hex = n => { const b = Buffer.alloc(8); b.writeBigUInt64LE(BigInt(n)); return b.toString('hex'); };
function run({pid = 123, attach = 'T11thread:1;', nonce = 42, pcReply = 'OK', probeReply = 'OK', prepare = 'OK',
              stops = [[3, 42, 0], [0, 0, 0]], allocate = '9c000'} = {}) {
  const log = [], commands = [], prepared = [];
  let continues = 0, probeWritten = false, resumed = false;
  const stop = ([command, x0, x1]) => `T05thread:1;20:${hex(0x1000)};10:${hex(command)};00:${hex(x0)};01:${hex(x1)};`;
  const sandbox = {
    neostationProbeNonce: nonce, get_pid: () => 123,
    log: value => log.push(value),
    prepare_memory_region: (address, length) => { prepared.push([address, length]); return prepare; },
    send_command: command => {
      commands.push(command);
      if (command.startsWith('vAttach;')) return attach;
      if (command === 'qProcessInfo') return `pid:${pid.toString(16)};parent-pid:1;`;
      if (command === 'c') {
        const next = stops[continues++];
        if (continues > 1) resumed = resumed || probeWritten;
        if (!next) throw Error('continued past the last stop');
        return stop(next);
      }
      if (command === 'm1000,4' || command === 'm1004,4') return 'a0013ed4';
      if (command.startsWith('P20=')) return pcReply;
      if (command.startsWith('_M')) return allocate;
      if (command.startsWith('P0=')) {
        if (command === `P0=${hex(43)};thread:1;`) probeWritten = probeReply === 'OK';
        return command === `P0=${hex(43)};thread:1;` ? probeReply : 'OK';
      }
      if (command === 'D') return 'OK';
      throw Error(`Unexpected command ${command}`);
    },
  };
  let error;
  try { vm.runInNewContext(script, sandbox, {timeout: 500}); } catch (e) { error = e; }
  return {error, log, commands, resumed, prepared};
}
const ok = run();
assert.equal(ok.error, undefined);
assert.equal(ok.resumed, true);
assert.equal(ok.commands[0], 'vAttach;7b');
assert.ok(ok.log.includes('NEOSTATION_S2ARM_DEBUGGER_ATTACHED_V1 pid=123 nonce=42'));
assert.ok(ok.log.includes('NEOSTATION_S2ARM_DEBUGGER_PROBE_V1 pid=123 nonce=42'));
assert.equal(ok.log.some(v => v.startsWith('NEOSTATION_DEBUGGER_')), false);
assert.equal(ok.commands[ok.commands.length - 1], 'D');
for (const options of [{pid: 999}, {attach: 'E01'}, {nonce: 41, stops: [[3, 42, 0], [0, 0, 0]]}, {pcReply: 'E02'},
                       {probeReply: 'E03'}]) {
  const failed = run(options);
  assert.ok(failed.error, JSON.stringify(options));
  assert.equal(failed.resumed, false, JSON.stringify(options));
}
assert.equal(run({pid: 999}).log.some(v => v.includes('DEBUGGER_ATTACHED')), false);
// Command 1 with x0 = an address the caller mapped: prepared as given, x0 answered with that address.
const given = run({stops: [[3, 42, 0], [1, 0x7000000000, 0x1000000], [0, 0, 0]]});
assert.equal(given.error, undefined);
assert.deepEqual(given.prepared, [[0x7000000000n, 0x1000000n]]);
assert.ok(given.commands.includes(`P0=${hex(0x7000000000)};thread:1;`));
assert.equal(given.commands.some(c => c.startsWith('_M')), false);
// Command 1 with x0 = 0: debugserver allocates RX memory of length x1, that address is prepared and answered.
const allocated = run({stops: [[3, 42, 0], [1, 0, 0x4000], [0, 0, 0]]});
assert.equal(allocated.error, undefined);
assert.ok(allocated.commands.includes('_M4000,rx'));
assert.deepEqual(allocated.prepared, [[0x9c000n, 0x4000n]]);
assert.ok(allocated.commands.includes(`P0=${hex(0x9c000)};thread:1;`));
// A refused preparation answers zero, with the S2Arm marker in the log.
const refused = run({prepare: 'E09', stops: [[3, 42, 0], [1, 0x7000000000, 0x4000], [0, 0, 0]]});
assert.equal(refused.error, undefined);
assert.ok(refused.commands.includes(`P0=${hex(0)};thread:1;`));
assert.ok(refused.log.some(v => v.startsWith('NEOSTATION_S2ARM_STIKJIT_UNIVERSAL_V1: debugserver page preparation failed')));
// x0 = 0 and x1 = 0: nothing prepared, nothing answered.
const empty = run({stops: [[3, 42, 0], [1, 0, 0], [0, 0, 0]]});
assert.equal(empty.error, undefined);
assert.deepEqual(empty.prepared, []);
console.log('PASS: S2Arm script attach/PID/nonce/PC/probe/resume, five rejections, regions given/allocated/refused/empty, detach');
'''


class Script(unittest.TestCase):
    def test_the_actual_script_against_a_deterministic_debugserver(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not installed')
        with tempfile.TemporaryDirectory(prefix='s2arm-script-') as temporary:
            harness = Path(temporary) / 'harness.js'
            harness.write_text(HARNESS)
            result = subprocess.run([node, str(harness), str(SCRIPT)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS: S2Arm script', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
