#!/usr/bin/env python3
"""Screen-capture state, audio interruptions and drawable-acquisition intervals in the host journals.

Usage: melonx_capture_journal_test.py [--control-ref <commit>]

Instrumentation only (IPA 650 follow-up: the maintainer could not save a screen recording and the app journaled no
capture state; presentation gaps alone cannot tell a frame the engine produced late from one the display held).
The control is the three host files at the pinned commit, bound by sha256. Static checks bind that:
- the controller observes UIScreen.capturedDidChangeNotification through the observers array removed in deinit, and
  journals "lifecycle" "captured"/"notCaptured" with the memory field on each change of the game window's screen
  (another screen's change is skipped) and once at session start;
- the plugin journals interruption begins and ends inside its existing interruption observer, whose whole text is
  bound, so it still reactivates audio only on an end that allows resuming;
- the drawable layer reads the host time when the engine asks for a drawable (before CAMetalLayer may block for a
  free one), records request-to-request intervals of requests that return a drawable, bounded by
  Presentation.gapLimit, and the longest wait inside nextDrawable; both reset on each read, the intervals also on
  pause (restartPacing); the drawable and its presented handler are unchanged; the journal prints "acq=" and
  "acqw=" right after "gaps=" only when intervals are present;
- every removed control line is one of the expected replacements, every added code line of the three files is
  listed exactly, braces/parentheses/brackets balance, every new identifier is declared or a known SDK name, and no
  journal detail starts with a key=value entry (the scrubber would redact it) and no new status is "begin".
Where a Swift compiler exists (macOS), the real perf journal is executed, and the real interruption observer
extracted from the control and from the candidate runs on one notification matrix: the activations must match and
the journal lines appear only in the candidate. There is no Swift compiler on the Linux runner: those executions
are recorded as not run in the receipt.
No device, no UIKit run. Writes dist/melonx/capture-journal-checks.json.
"""
from pathlib import Path
import difflib, hashlib, json, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = 'packages/melonx_internal_bridge/ios/Classes/'
CONTROLLER = CLASSES + 'MeloNXMetalSessionViewController.swift'
JOURNAL = CLASSES + 'MeloNXPerfJournal.swift'
PLUGIN = CLASSES + 'MeloNXInternalBridgePlugin.swift'
CONTROL_REF = sys.argv[sys.argv.index('--control-ref') + 1] if '--control-ref' in sys.argv else '72eae3478c0c25fcbcbd05f86cdc5c7feab8c980'
# The control files (IPA 650 host), sha256. Fail closed on drift.
BASELINE = {
    CONTROLLER: '27b79cb9552757d84d482d73778335f2418f073d3f81c5bfc5334f1afaeea04a',
    JOURNAL: 'e05d77ce10a16be062a4bb317da6619a71ef15124fbf733dfd1a5cb46e74ca7e',
    PLUGIN: '1a4965daedfbbbb49eb53abbc8912ecc1b59d5c0fbf360bf4bb51b3cdf01be85',
}
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


control, candidate = {}, {}
for path, digest in BASELINE.items():
    raw = subprocess.run(['git', '-C', str(ROOT), 'show', f'{CONTROL_REF}:{path}'], capture_output=True, check=True).stdout
    check(sha(raw) == digest, f'control drift: {path} at {CONTROL_REF}')
    control[path] = raw.decode()
    candidate[path] = (ROOT / path).read_text()
    check(candidate[path] != control[path], f'no change in {path}')


def block(source, start, opener='{'):
    """Text from start through the brace that closes the first opener after it."""
    begin = source.index(start)
    index = source.index(opener, begin) + 1
    depth = 1
    while depth:
        depth += {'{': 1, '}': -1}.get(source[index], 0)
        index += 1
    return source[begin:index]


def diff(path):
    removed, added = [], []
    for line in difflib.ndiff(control[path].splitlines(), candidate[path].splitlines()):
        if line.startswith('- '):
            removed.append(line[2:])
        elif line.startswith('+ '):
            added.append(line[2:])
    return removed, added


# --- Lexical balance (comments and string contents skipped, interpolations followed) ---
def balance(source):
    stack, index, pairs = [], 0, {')': '(', '}': '{', ']': '['}
    interpolation = []  # stack depth at which each open interpolation returns to its string
    in_string = False
    while index < len(source):
        char = source[index]
        if in_string:
            if char == '\\' and source[index + 1] == '(':
                interpolation.append(len(stack)); stack.append('('); in_string = False; index += 2; continue
            if char == '\\':
                index += 2; continue
            if char == '"':
                in_string = False
            elif char == '\n':
                return 'unterminated string'
            index += 1; continue
        if source.startswith('//', index):
            index = source.index('\n', index); continue
        if source.startswith('/*', index):
            index = source.index('*/', index) + 2; continue
        if source.startswith('"""', index):
            return 'multi-line string not handled'
        if char == '"':
            in_string = True
        elif char in '({[':
            stack.append(char)
        elif char in ')}]':
            if not stack or stack[-1] != pairs[char]:
                return f'unbalanced {char} at {source.count(chr(10), 0, index) + 1}'
            stack.pop()
            if char == ')' and interpolation and interpolation[-1] == len(stack):
                interpolation.pop(); in_string = True
        index += 1
    return 'open ' + ''.join(stack) if stack or in_string else 'balanced'


for path in BASELINE:
    check(balance(control[path]) == 'balanced', 'lexer on control ' + path + ': ' + balance(control[path]))
    check(balance(candidate[path]) == 'balanced', path + ': ' + balance(candidate[path]))

# --- Only the expected control lines are replaced ---
removed, added_controller = diff(CONTROLLER)
check(removed == ['    // Gaps between presentations for the performance journal; the longest gap',
                  '    // and the list of gaps reset on each read.',
                  '    func restartPacing() { observationLock.lock(); lastPresented = 0; observationLock.unlock() }'],
      f'controller removed lines: {removed}')
removed, added_journal = diff(JOURNAL)
check(removed == [], f'journal removed lines: {removed}')
removed, added_plugin = diff(PLUGIN)
check(removed == ['            guard let self, self.previousAudio != nil,',
                  '                  (event.userInfo?[AVAudioSessionInterruptionTypeKey] as? NSNumber)?.uintValue == AVAudioSession.InterruptionType.ended.rawValue,',
                  '                  let raw = (event.userInfo?[AVAudioSessionInterruptionOptionKey] as? NSNumber)?.uintValue,',
                  '                  AVAudioSession.InterruptionOptions(rawValue:raw).contains(.shouldResume) else { return }'],
      f'plugin removed lines: {removed}')
# The plugin change stays inside the interruption observer.
plugin_c = candidate[PLUGIN]
observer = block(plugin_c, 'audioObservers.append(center.addObserver(forName:AVAudioSession.interruptionNotification')
code_added = [line for line in added_plugin if not line.strip().startswith('//')]
check(all(line in observer for line in code_added), 'plugin lines added outside the interruption observer')
comments = [line for line in added_plugin if line.strip().startswith('//')]
check(len(comments) == 3 and plugin_c.index(comments[-1]) < plugin_c.index(observer), 'observer comment')

# --- I6: capture state ---
ctl = candidate[CONTROLLER]
load = block(ctl, 'override func loadView()')
capture_observer = ('observers.append(NotificationCenter.default.addObserver(forName:UIScreen.capturedDidChangeNotification,'
                    'object:nil,queue:.main) { [weak self] event in\n            self?.recordCapture(event.object as? UIScreen)\n        })')
check(load.count(capture_observer) == 1, 'capture observer not added to the observers array in loadView')
check(load.index(capture_observer) > load.index('(UIApplication.didReceiveMemoryWarningNotification,"memoryWarning")'),
      'capture observer not next to the lifecycle observers')
check(ctl.count('NotificationCenter.default.addObserver(') == ctl.count('observers.append(NotificationCenter.default.addObserver(') == 3,
      'an observer outside the observers array')
deinit = block(ctl, 'deinit {')
check('observers.forEach { NotificationCenter.default.removeObserver($0) }' in deinit, 'observers not removed in deinit')
record = block(ctl, 'private func recordCapture(_ changed: UIScreen?)')
check(record == '''private func recordCapture(_ changed: UIScreen?) {
        guard let screen = view.window?.windowScene?.screen ?? changed, changed == nil || changed === screen else { return }
        MeloNXLaunchJournal.record("lifecycle",screen.isCaptured ? "captured" : "notCaptured",detail:"memory " + Self.memoryField())
    }''', 'capture journal line')
check(ctl.count('recordCapture(') == 3, 'recordCapture callers')
appear = block(ctl, 'override func viewDidAppear(_ animated: Bool)')
check(appear.index('guard !started else { return }; started = true') < appear.index('if closing {') <
      appear.index('recordCapture(nil)') < appear.index('try host.start('), 'capture state not journaled once at session start')
check(appear.count('recordCapture(nil)') == 1 and appear.index('recordCapture(nil)') > appear.index('return\n        }'),
      'start line also written for a closed controller')
check('UIScreen.main' not in ctl, 'deprecated UIScreen.main')

# --- I6: audio interruptions ---
# The whole observer is bound: journal lines only, and the control's decision (reactivate only on an end whose
# options contain shouldResume, with previousAudio set) unchanged.
check(observer == '''audioObservers.append(center.addObserver(forName:AVAudioSession.interruptionNotification,object:AVAudioSession.sharedInstance(),queue:.main) { [weak self] event in
            guard let self, self.previousAudio != nil else { return }
            let type = (event.userInfo?[AVAudioSessionInterruptionTypeKey] as? NSNumber)?.uintValue
            let raw = (event.userInfo?[AVAudioSessionInterruptionOptionKey] as? NSNumber)?.uintValue
            let ended = type == AVAudioSession.InterruptionType.ended.rawValue
            let resume = raw.map { AVAudioSession.InterruptionOptions(rawValue:$0).contains(.shouldResume) } ?? false
            if type == AVAudioSession.InterruptionType.began.rawValue { MeloNXLaunchJournal.record("audio","interruptionBegan") }
            else if ended { MeloNXLaunchJournal.record("audio","interruptionEndReceived",detail:resume ? "shouldResume: yes" : "shouldResume: no") }
            guard ended, resume else { return }
            do { try self.activateAudio(reason:"interruptionEnded") }
            catch { MeloNXLaunchJournal.record("audio","failed",detail:String(describing:error)) }
        }''', 'interruption observer differs from the expected text')
observer_o = block(control[PLUGIN], 'audioObservers.append(center.addObserver(forName:AVAudioSession.interruptionNotification')
check(observer_o.endswith('''AVAudioSession.InterruptionOptions(rawValue:raw).contains(.shouldResume) else { return }
            do { try self.activateAudio(reason:"interruptionEnded") }
            catch { MeloNXLaunchJournal.record("audio","failed",detail:String(describing:error)) }
        }'''), 'control interruption observer')

check(plugin_c.count('AVAudioSession.interruptionNotification') == 1, 'second interruption observer')

# --- I3: acquisition intervals ---
journal = candidate[JOURNAL]
presentation = block(journal, 'struct Presentation {')
check(presentation == '''struct Presentation {
        var frames: UInt64 = 0, maxGapMs = 0.0, over20: UInt64 = 0, over40: UInt64 = 0
        var over50: UInt64 = 0, over100: UInt64 = 0, gapsMs: [UInt16] = []
        var acquireGapsMs: [UInt16] = []
        var maxAcquireWaitMs = 0.0
        static let gapLimit = 240
    }''', 'Presentation: the new list must follow the existing members (memberwise initializer order)')
gaps_line = 'if !shown.gapsMs.isEmpty { fields.append("gaps=" + shown.gapsMs.map { String($0) }.joined(separator:",")) }'
acq_line = 'if !shown.acquireGapsMs.isEmpty { fields.append("acq=" + shown.acquireGapsMs.map { String($0) }.joined(separator:",")) }'
acqw_line = 'if !shown.acquireGapsMs.isEmpty { fields.append("acqw=" + Self.decimal(shown.maxAcquireWaitMs)) }'
check(journal.count(acq_line) == 1 and journal.index(acq_line) == journal.index(gaps_line) + len(gaps_line) + 9, 'acq= not right after gaps=')
check(journal.count(acqw_line) == 1 and journal.index(acqw_line) == journal.index(acq_line) + len(acq_line) + 9, 'acqw= not right after acq=')
check(journal.count('MeloNXStdioCapture.appendLine(') == journal.count(', to:path, limit:Self.fileLimit)') == 4, 'journal writes changed')
check('//   acq=   every interval between two drawable requests in the interval\n'
      '//          (host time when the engine asked CAMetalLayer.nextDrawable for a' in journal, 'acq= not documented')
check('//   acqw=  the longest wait inside nextDrawable in the interval' in journal, 'acqw= not documented')
check([line for line in added_journal if not line.strip().startswith('//')] ==
      ['        var acquireGapsMs: [UInt16] = []', '        var maxAcquireWaitMs = 0.0', '        ' + acq_line, '        ' + acqw_line],
      'journal code additions')
layer_c = block(ctl, 'private final class MeloNXObservedMetalLayer: CAMetalLayer {')
layer_o = block(control[CONTROLLER], 'private final class MeloNXObservedMetalLayer: CAMetalLayer {')
check('    private var lastAcquired: CFTimeInterval = 0' in layer_c, 'lastAcquired')
check('pacing.acquireGapsMs.removeAll(keepingCapacity: true)\n        pacing.maxAcquireWaitMs = 0\n        return result' in layer_c,
      'acquisition list or longest wait not reset on read')
check('func restartPacing() { observationLock.lock(); lastPresented = 0; lastAcquired = 0; observationLock.unlock() }' in layer_c,
      'acquisitions not restarted on pause')
next_c = block(layer_c, 'override func nextDrawable() -> CAMetalDrawable? {')
next_o = block(layer_o, 'override func nextDrawable() -> CAMetalDrawable? {')
handler = block(next_o, 'drawable.addPresentedHandler {')
check(block(next_c, 'drawable.addPresentedHandler {') == handler, 'presented handler changed')
# The request time is read before super.nextDrawable() (which blocks while the display holds every drawable), so
# the wait is not folded into acq=; it is kept apart as the longest wait. Only requests that return a drawable count.
measure = '''    override func nextDrawable() -> CAMetalDrawable? {
        // Measurement only: the host time the engine asked for a drawable, read
        // before CAMetalLayer waits for a free one (the display or compositor
        // may hold them all), and the longest such wait. Only requests that
        // return a drawable are recorded, bounded like the presentation gaps.
        // The drawable is unchanged.
        let requested = CACurrentMediaTime()
        guard let drawable = super.nextDrawable() else { return nil }
        let waitMs = (CACurrentMediaTime() - requested) * 1000
        observationLock.lock()
        pacing.maxAcquireWaitMs = max(pacing.maxAcquireWaitMs, waitMs)
        if lastAcquired > 0, requested > lastAcquired,
           pacing.acquireGapsMs.count < MeloNXPerfJournal.Presentation.gapLimit {
            pacing.acquireGapsMs.append(UInt16(min(((requested - lastAcquired) * 1000).rounded(), 65535)))
        }
        lastAcquired = requested
        observationLock.unlock()
        drawable.addPresentedHandler {'''
check(next_c.startswith(measure[4:]), 'acquisition measurement')
check(next_c.index('let requested = CACurrentMediaTime()') < next_c.index('super.nextDrawable()') <
      next_c.index('let waitMs = (CACurrentMediaTime() - requested) * 1000') < next_c.index('lastAcquired = requested'),
      'request time not read before the blocking nextDrawable')
check(next_c.replace(measure[4:], 'override func nextDrawable() -> CAMetalDrawable? {\n        guard let drawable = super.nextDrawable() else { return nil }\n        drawable.addPresentedHandler {') == next_o,
      'nextDrawable differs from the control beyond the measurement')
code_c = '\n'.join(line for line in next_c.splitlines() if not line.strip().startswith('//'))
check(code_c.count('super.nextDrawable()') == 1 and code_c.count('return') == next_o.count('return') == 3 and
      code_c.count('observationLock.lock()') == 2 and code_c.count('observationLock.unlock()') == 2,
      'drawable path, returns or lock pairing changed')
# The interval is rounded milliseconds, never negative (requested > lastAcquired) and clamped to UInt16 (bound by
# measure above).
check(layer_c.count('MeloNXPerfJournal.Presentation.gapLimit') == 2, 'both lists bounded by gapLimit')
# Every added controller code line, exactly (comments are free text).
check([line for line in added_controller if not line.strip().startswith('//')] == [
    '    private var lastAcquired: CFTimeInterval = 0',
    '        pacing.acquireGapsMs.removeAll(keepingCapacity: true)',
    '        pacing.maxAcquireWaitMs = 0',
    '    func restartPacing() { observationLock.lock(); lastPresented = 0; lastAcquired = 0; observationLock.unlock() }',
    *[line for line in measure.splitlines()[1:-1] if not line.strip().startswith('//') and 'super.nextDrawable()' not in line],
    '        ' + capture_observer.splitlines()[0],
    *capture_observer.splitlines()[1:],
    '    }',  # ndiff pairs loadView's own closing brace with the control's; the function's is the extra one
    '    ' + record.splitlines()[0],
    *record.splitlines()[1:-1],
    '        recordCapture(nil)',
], 'controller code additions')

# --- New identifiers are declared (or SDK names) ---
SDK = {'UIScreen', 'capturedDidChangeNotification', 'isCaptured', 'CACurrentMediaTime', 'windowScene', 'screen', 'object',
       'AVAudioSessionInterruptionTypeKey', 'AVAudioSessionInterruptionOptionKey', 'InterruptionType', 'InterruptionOptions',
       'began', 'ended', 'shouldResume', 'uintValue', 'userInfo', 'rawValue', 'map', 'contains', 'rounded', 'count', 'append',
       'removeAll', 'keepingCapacity', 'Self', 'yes', 'no'}
KEYWORDS = set('let var if else guard return func private nil self weak in as is true false static struct'.split())
for path, added in ((CONTROLLER, added_controller), (JOURNAL, added_journal), (PLUGIN, added_plugin)):
    code = '\n'.join(re.sub(r'"(?:[^"\\]|\\.)*"', '""', line) for line in added if not line.strip().startswith('//'))
    known = set(re.findall(r'[A-Za-z_]\w*', control[path]))
    for name in sorted(set(re.findall(r'(?<![.\w])[A-Za-z_]\w*|(?<=\.)[A-Za-z_]\w*', code)) - known - KEYWORDS - SDK):
        declared = re.search(rf'(?:\blet|\bvar|\bfunc|\(_)\s+{name}\b', '\n'.join(candidate.values()))
        check(declared, f'{path}: {name} is not declared')

# --- Journal strings: no "begin", nothing the scrubber would redact ---
statuses = re.findall(r'MeloNXLaunchJournal\.record\("(\w+)",\s*([^,)]*)', '\n'.join(added_controller + added_plugin))
check(sorted(set(s for s, _ in statuses)) == ['audio', 'lifecycle'], statuses)
new_statuses = re.findall(r'"(interruptionBegan|interruptionEndReceived|captured|notCaptured)"', '\n'.join(added_controller + added_plugin))
check(sorted(set(new_statuses)) == ['captured', 'interruptionBegan', 'interruptionEndReceived', 'notCaptured'], new_statuses)
check('"begin"' not in '\n'.join(added_controller + added_plugin), 'begin status')
scrubber = re.compile(r'^\s*[a-z0-9_]+\s*=\s*[^\r\n]+', re.I | re.M)
for detail in ('shouldResume: yes', 'shouldResume: no', 'memory 812/2900/41/2', 'memory -/-/-1/0'):
    check(not scrubber.search(detail), 'scrubbed detail ' + detail)

# --- Execution where a Swift compiler exists ---
swiftc = shutil.which('swiftc') or (['xcrun', 'swiftc'] if shutil.which('xcrun') else None)
command = None if not swiftc else [swiftc] if isinstance(swiftc, str) else swiftc
executed = []
AUDIO_DOUBLES = r'''import Foundation
let AVAudioSessionInterruptionTypeKey = "type"
let AVAudioSessionInterruptionOptionKey = "options"
struct UIApplication { static let didBecomeActiveNotification = Notification.Name("foreground") }
var records: [String] = []
enum MeloNXLaunchJournal { static func record(_ stage:String,_ status:String,detail:String="") { records.append(stage + " " + status + " " + detail) } }
final class AVAudioSession: NSObject {
    enum Category:String { case ambient, playback }
    enum Mode:String { case `default` }
    struct CategoryOptions:OptionSet { let rawValue:Int }
    struct InterruptionOptions:OptionSet { let rawValue:UInt; static let shouldResume=Self(rawValue:1) }
    enum InterruptionType:UInt { case ended=0, began=1 }
    struct Port { let rawValue="Speaker" }
    struct Output { let portType=Port() }
    struct Route { let outputs=[Output()] }
    static let routeChangeNotification=Notification.Name("route")
    static let interruptionNotification=Notification.Name("interruption")
    static let instance=AVAudioSession()
    static func sharedInstance()->AVAudioSession { instance }
    var category=Category.playback,mode=Mode.default,categoryOptions:CategoryOptions=[]
    var sampleRate=48000.0,ioBufferDuration=256.0/48000.0,currentRoute=Route()
    var activations=0
    func setCategory(_ c:Category,mode m:Mode,options:CategoryOptions) throws { category=c;mode=m;categoryOptions=options }
    func setActive(_ value:Bool) throws { activations += 1 }
}
final class GameAudio {
    var previousAudio:(Int)?=1
    private var audioObservers:[NSObjectProtocol]=[]
    init(){installAudioObservers()}
'''
# One matrix for control and candidate: began, ended without options, ended with options 0, ended with
# shouldResume, ended with shouldResume plus another option, nil userInfo, an unknown type, then previousAudio nil
# with began and with ended shouldResume. The activation count is printed after each notification.
AUDIO_MATRIX = r'''
}
let game=GameAudio(), audio=AVAudioSession.sharedInstance()
var counts:[String]=[]
func post(_ info:[String:Any]?) {
    NotificationCenter.default.post(name:AVAudioSession.interruptionNotification,object:audio,userInfo:info)
    counts.append(String(audio.activations))
}
post([AVAudioSessionInterruptionTypeKey:NSNumber(value:1)])
post([AVAudioSessionInterruptionTypeKey:NSNumber(value:0)])
post([AVAudioSessionInterruptionTypeKey:NSNumber(value:0),AVAudioSessionInterruptionOptionKey:NSNumber(value:0)])
post([AVAudioSessionInterruptionTypeKey:NSNumber(value:0),AVAudioSessionInterruptionOptionKey:NSNumber(value:1)])
post([AVAudioSessionInterruptionTypeKey:NSNumber(value:0),AVAudioSessionInterruptionOptionKey:NSNumber(value:3)])
post(nil)
post([AVAudioSessionInterruptionTypeKey:NSNumber(value:7)])
game.previousAudio=nil
post([AVAudioSessionInterruptionTypeKey:NSNumber(value:1)])
post([AVAudioSessionInterruptionTypeKey:NSNumber(value:0),AVAudioSessionInterruptionOptionKey:NSNumber(value:1)])
print(counts.joined(separator:","))
print(records.joined(separator:"|"))
'''


def run_audio(work, name, source):
    observers = block(source, '    private func installAudioObservers()')
    activate = block(source, '    private func activateAudio(reason: String)')
    (work / f'{name}.swift').write_text(AUDIO_DOUBLES + activate + '\n' + observers + AUDIO_MATRIX)
    subprocess.run([*command, '-swift-version', '5', str(work / f'{name}.swift'), '-o', str(work / name)], check=True, timeout=300)
    counts, _, lines = subprocess.check_output([str(work / name)], text=True, timeout=30).rstrip('\n').partition('\n')
    return counts.split(','), [line for line in lines.split('|') if line]


if command:
    with tempfile.TemporaryDirectory(prefix='melonx-capture-journal-') as temporary:
        work = Path(temporary)
        log = work / 'app.log'
        (work / 'main.swift').write_text(r'''import Foundation
let path = CommandLine.arguments[1]
var calls: UInt64 = 0
let journal = MeloNXPerfJournal(path:path, interval:0.2, lineLimit:3, fps:{ [:] },
    presentation:{
        calls += 1
        // The control's memberwise call (no acquisitions) and one with them.
        if calls % 2 == 0 { return MeloNXPerfJournal.Presentation(frames:calls * 60, maxGapMs:20, over20:0, over40:0, over50:0, over100:0, gapsMs:[17]) }
        var value = MeloNXPerfJournal.Presentation(frames:calls * 60, maxGapMs:20, over20:0, over40:0, over50:0, over100:0, gapsMs:[17, 16])
        value.acquireGapsMs = [16, 50]
        value.maxAcquireWaitMs = 2.54
        return value
    }, audio:{ nil })
journal.start()
usleep(1_000_000)
journal.stop()
for _ in 0..<100 {
    if (try? String(contentsOfFile:path, encoding:.utf8))?.contains("[MeloNX:perf] end:") == true { exit(0) }
    usleep(50_000)
}
exit(2)
''')
        subprocess.run([*command, '-swift-version', '5', str(ROOT / CLASSES / 'MeloNXStandaloneParity.swift'), str(ROOT / JOURNAL),
                        str(work / 'main.swift'), '-o', str(work / 'perf')], check=True, timeout=300)
        check(subprocess.run([str(work / 'perf'), str(log)], timeout=60).returncode == 0, 'perf journal run')
        samples = [line.split(' ') for line in log.read_text().splitlines() if ' t=' in line]
        check(samples and all(('acq=16,50' in fields) == ('gaps=17,16' in fields) for fields in samples), samples)
        check(all(fields.index('acq=16,50') == fields.index('gaps=17,16') + 1 and fields.index('acqw=2.5') == fields.index('acq=16,50') + 1
                  for fields in samples if 'acq=16,50' in fields), samples)
        check(any('gaps=17' in fields and not any(f.startswith('acq') for f in fields) for fields in samples), 'empty acq= or acqw= printed')
        executed.append('MeloNXPerfJournal')

        counts_o, lines_o = run_audio(work, 'audio_control', control[PLUGIN])
        counts_c, lines_c = run_audio(work, 'audio_candidate', candidate[PLUGIN])
        check(counts_c == counts_o == ['0', '0', '0', '1', '2', '2', '2', '2', '2'], f'activations: control {counts_o}, candidate {counts_c}')
        journaled = ('interruptionBegan', 'interruptionEndReceived')
        check([line for line in lines_c if line.split(' ')[1] not in journaled] == lines_o and
              [line.split(' ')[1] for line in lines_o] == ['interruptionEnded', 'interruptionEnded'], (lines_o, lines_c))
        check([line.split(' ')[1] for line in lines_c] == ['interruptionBegan', 'interruptionEndReceived', 'interruptionEndReceived',
                                                           'interruptionEndReceived', 'interruptionEnded', 'interruptionEndReceived',
                                                           'interruptionEnded'], lines_c)
        check([line.split(' ', 2)[2] for line in lines_c if 'interruptionEndReceived' in line] ==
              ['shouldResume: no', 'shouldResume: no', 'shouldResume: yes', 'shouldResume: yes'], lines_c)
        executed.append('installAudioObservers (control and candidate)')

inputs = [CONTROLLER, JOURNAL, PLUGIN, 'test/melonx_capture_journal_test.py']
receipt = dict(result='passed', checks=checks, controlRef=CONTROL_REF, sourceBaseline=BASELINE,
               inputs={p: sha((ROOT / p).read_bytes()) for p in inputs},
               sdk=subprocess.run([*command, '--version'], capture_output=True, text=True).stdout.strip() if command else 'swiftc unavailable',
               swiftExecution='run' if command else 'not run',
               swiftExecuted=executed,
               swiftSkipped=[] if command else ['MeloNXPerfJournal acq=/acqw= output',
                                                'installAudioObservers control vs candidate notification matrix'],
               physicalDeviceTested=False, uikitRun=False,
               limitation='Instrumentation only. Static checks of the Swift sources; the perf journal and the extracted '
                          'interruption observer (control and candidate) execute only where a Swift compiler exists, '
                          'so on a runner without one only the static half has run. UIScreen capture notifications, '
                          'real interruptions and CAMetalLayer request timing and waits are observed only on a device.')
out = ROOT / 'dist/melonx/capture-journal-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, swiftExecution=receipt['swiftExecution'],
                      swiftExecuted=executed or 'not run: no Swift compiler')))
