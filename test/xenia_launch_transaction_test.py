#!/usr/bin/env python3
"""The XeniOS launch ends its JIT transaction on every failure (review of #172).

Nothing native runs on this host: this reads the bridge sources and checks
the rules the device would otherwise reveal one restart at a time.
D1: every failure of `launch:` ends the transaction Dart opened, so the next
prepareJit is accepted (the helper refuses one only while activeSession or
operationInProgress is set, and the abort clears both). R2: the menu, quit
and pause act only once the launch reported success. R3: a Core stop/error
during the launch is reported once, by the launch result. R4: the detach
wait is short and its failure ends the transaction too. Plus the cached
refusal of an unusable Core.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages' / 'xenia_internal_bridge' / 'ios' / 'Classes'
PLUGIN = (CLASSES / 'XeniaInternalBridgePlugin.mm').read_text(encoding='utf-8')
JIT = (CLASSES / 'XeniaJitBridgePlugin.mm').read_text(encoding='utf-8')


def body(source: str, signature: str) -> str:
    start = source.index(signature)
    following = re.search(r'\n(?:- \(|\+ \(|@end|[A-Za-z].*\(.*\) \{)', source[start + len(signature):])
    return source[start:start + len(signature) + (following.start() if following else len(source))]


def function(source: str, signature: str) -> str:
    start = source.index(signature)
    depth = 0
    for index in range(source.index('{', start), len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(signature)


def main() -> int:
    failures = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    launch = function(PLUGIN, '- (void)launch:(id)arguments result:(FlutterResult)result {')
    fail = function(PLUGIN, '- (void)failLaunch:(NSDictionary*)report result:(FlutterResult)result {')
    check('XeniaJitAbortTransaction();' in fail and 'if (!_launchPending)' in fail,
          'failLaunch must end the transaction unless a launch is in flight')
    early = launch[:launch.index('[presenter presentViewController')]
    check('result(@{' not in early, 'an early launch failure answers without failLaunch')
    for reason in ('restartRequired', 'sessionActive', 'invalidArguments', 'gameUnreadable',
                   'renderViewFailed', 'noPresenter'):
        check(f'[self failLaunch:@{{@"success" : @NO, @"error" : @"{reason}"' in early,
              f'{reason} does not go through failLaunch')
    check('[self failLaunch:@{@"success" : @NO, @"error" : loadError' in early,
          'a Core load failure does not go through failLaunch')
    check(early.rstrip().endswith('_launchPending = YES;'), 'the launch is pending only once presented')
    late = launch[launch.index('[presenter presentViewController'):]
    check('if (stage) XeniaJitAbortTransaction();' in late, 'a stage failure must end the transaction')
    check('handshake && ![stage' not in late, 'the abort is no longer limited to handshake launches')
    check(late.count('result(@{@"success" : @NO') == 1, 'one failure answer after the presentation')
    check('self->_pendingEndReason' in late and 'outcome = @"bootFailed";' in late,
          'a stop/error during the launch must become its result')
    check('XeniaJitWaitForDetach(kXeniaDetachTimeout, &message)' in late, 'detach wait uses its constant')
    timeout = re.search(r'kXeniaDetachTimeout = ([0-9.]+);', PLUGIN)
    check(timeout is not None and float(timeout.group(1)) <= 30.0, 'detach wait must stay short (<= 30 s)')

    deliver = function(PLUGIN, '- (void)deliverEvent:(NSString*)event transaction:(uint64_t)transaction message:(NSString*)message {')
    check(deliver.index('if (_launchPending)') < deliver.index('[self teardownWithReason:'),
          'deliverEvent must hold events of a pending launch before any teardown')
    running = function(PLUGIN, '- (BOOL)sessionRunning {')
    check('!_launchPending' in running and '!_stopping' in running, 'sessionRunning excludes pending/stopping')
    check('!self.owner.sessionRunning' in function(PLUGIN, '- (void)openMenu {'), 'menu before the launch result')
    check('!self.sessionRunning' in function(PLUGIN, '- (void)requestStopFromMenu {'), 'quit before the launch result')
    check('self.sessionRunning' in function(PLUGIN, '- (void)applyPause {'), 'pause before the launch result')
    load = function(PLUGIN, '- (NSString*)loadCore {')
    check('if (_loadFailure) return _loadFailure;' in load and '_loadFailure = @"abiMismatch";' in load
          and '_loadFailure = @"coreLoadFailed";' in load, 'an unusable Core must stay refused, not reopened')
    check('if (_loadFailure) {' in function(PLUGIN, '- (NSDictionary*)availability {'),
          'availability must report a refused Core')
    check('@"abortJit"' in PLUGIN and 'if (!self.session) XeniaJitAbortTransaction();' in PLUGIN,
          'Dart must be able to end a transaction it could not hand to launch')

    # The helper side: refusal and abort act on the same two fields.
    abort = function(JIT, 'void XeniaJitAbortTransaction(void) {')
    check('activeSession = nil;' in abort and 'operationInProgress = NO;' in abort,
          'the abort must clear activeSession and operationInProgress')
    check('if (self.operationInProgress || self.activeSession != nil) {' in JIT,
          'prepareJit refuses on exactly the fields the abort clears')

    if failures:
        print('xenia launch transaction: FAIL\n- ' + '\n- '.join(failures))
        return 1
    print('xenia launch transaction: OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
