#!/usr/bin/env python3
"""Left-stick report (IPA 658, second player): stick arbitration, native return codes and the input capture.

Usage: melonx_input_stick_test.py [--controller <Melo-Controller checkout at the pinned revision>]

Static checks on the iOS host (there is no Swift compiler on the Linux runner; where swiftc exists the extracted
arbitration and the counters are compiled and executed on the same scenarios as the model below):
- MeloNXInputRouter.setStick no longer lets a physical stick off rest (|x|+|y| > 0.01) override every touch value of
  that stick on the shared pad 1. The source that most recently left rest owns the stick; small moves of a source
  already off rest (drift) never take it back; while the owner rests, another source off rest is used. The model
  replays the old and the new rule on a drifting controller stick and shows the old rule starves the touch stick;
- MeloNXRuntimeAPI.stick/button return the export's code (0, 1 invalid, 2 no input, 3 exception) without a journal
  dependency (the runtime smoke app compiles that file alone);
- the router counts per second, by source and stick, events and largest magnitude, the largest magnitude sent, button
  changes, inputs dropped while paused/closed and refused writes, and hands them to MeloNXPerfJournal as "in=";
- one "input" "state" launch-journal line at session start, then on a changed state after a resume (layout editor,
  mapping, menu toggles), a controller change or the hide-with-controller toggle: the layout origin and both sticks'
  hidden/hide/offset/scale/opacity, D-pad/ABXY cover, overlay shown/hidden, controllers with mapping origin and stick
  sources. No detail starts with a key=value entry (the journal scrubber) and no 32+ hex run;
- the stderr capture copies up to 64 of the guest's Hid lines (SetupNpad, Remap, SetSupportedNpadStyleSet/IdType)
  past its 500-line NSLog budget, which every 658 capture of that player had spent before the game set up its pads.
Writes dist/melonx/input-stick-checks.json. No device, no UIKit run, no game.
"""
from pathlib import Path
import hashlib, json, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ROOT / 'packages/melonx_internal_bridge/ios/Classes'
ROUTER = CLASSES / 'MeloNXInputRouter.swift'
DIAGNOSTICS = CLASSES / 'MeloNXInputDiagnostics.swift'
JOURNAL = CLASSES / 'MeloNXPerfJournal.swift'
RUNTIME = CLASSES / 'MeloNXRuntimeAPI.swift'
CONTROLLER = CLASSES / 'MeloNXMetalSessionViewController.swift'
VENDOR = ROOT / 'build-utils/melonx/vendor_controller.py'
melo = Path(sys.argv[sys.argv.index('--controller') + 1]) if '--controller' in sys.argv else None
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def block(source, start):
    begin = source.index(start)
    index = source.index('{', begin) + 1
    depth = 1
    while depth:
        depth += {'{': 1, '}': -1}.get(source[index], 0)
        index += 1
    return source[begin:index]


def balance(source):
    """Brackets balance outside comments and strings (interpolations followed)."""
    stack, index, pairs, interpolation, in_string = [], 0, {')': '(', '}': '{', ']': '['}, [], False
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


router, diagnostics, journal, runtime = (p.read_text() for p in (ROUTER, DIAGNOSTICS, JOURNAL, RUNTIME))
for path, text in ((ROUTER, router), (DIAGNOSTICS, diagnostics), (JOURNAL, journal), (RUNTIME, runtime)):
    check(balance(text) == 'balanced', f'{path.name}: {balance(text)}')

# --- Arbitration (the defect) ---
OLD_RULE = 'let value = abs(physical.0) + abs(physical.1) > 0.01 ? physical : (axes[pad]?["touch"]?[stick] ?? (0, 0))'
check(OLD_RULE not in router and 'axes[pad]?["physical"]' not in router, 'physical-wins rule still present')
ARBITRATION = '''    static func isOffRest(_ value: (Float, Float)) -> Bool { abs(value.0) + abs(value.1) > 0.01 }
    static func stickOwner(current: String?, source: String, previous: (Float, Float)?,
                           values: [String: [Int32: (Float, Float)]], stick: Int32) -> String? {
        guard isOffRest(values[source]?[stick] ?? (0, 0)) else { return current }
        if !isOffRest(previous ?? (0, 0)) { return source }
        guard let current, isOffRest(values[current]?[stick] ?? (0, 0)) else { return source }
        return current
    }
    static func stickValue(owner: String?, values: [String: [Int32: (Float, Float)]], stick: Int32) -> (Float, Float) {
        if let owner, let value = values[owner]?[stick], isOffRest(value) { return value }
        for source in ["touch", "physical"] where source != owner {
            if let value = values[source]?[stick], isOffRest(value) { return value }
        }
        return (0, 0)
    }'''
check(router.count(ARBITRATION) == 1, 'arbitration text differs from the model bound here')
SET_STICK = '''    private func setStick(pad: Int32, source: String, stick: Int32, x: Float, y: Float) {
        guard x.isFinite, y.isFinite else { return }
        guard !closed, !suspended else { counters.dropped(); return }
        let previous = axes[pad]?[source]?[stick]
        axes[pad, default: [:]][source, default: [:]][stick] = (x, y)
        let values = axes[pad] ?? [:]
        let owner = Self.stickOwner(current: stickOwners[pad]?[stick], source: source, previous: previous, values: values, stick: stick)
        stickOwners[pad, default: [:]][stick] = owner
        let value = Self.stickValue(owner: owner, values: values, stick: stick)
        let code = runtime.stick(generation, pad: pad, stick: stick, x: value.0, y: value.1)
        counters.stick(source: source, stick: stick, value: (x, y), sent: value, code: code)
    }'''
check(router.count(SET_STICK) == 1, 'setStick differs from the model')
# Ownership is cleared with the axes on every reset path (suspend, close, reconnect).
check(router.count('axes.removeAll(); stickOwners.removeAll()') == 3 and router.count('axes.removeAll()') == 3, 'owners not reset with the axes')
# Touch sticks: stick 1 left / 2 right with UIKit's Y inverted, physical sticks through the mapping, unchanged.
check('setStick(pad: 1, source: "touch", stick: right ? 2 : 1, x: Float(position.x), y: Float(-position.y))' in router, 'touch stick index/inversion')
check('for (axis, configuration) in [(Int32(1),mapping.leftStick),(Int32(2),mapping.rightStick)] where configuration.source == source {' in router and
      'self.setStick(pad:pad,source:"physical",stick:axis,x:value.x,y:value.y)' in router, 'physical stick routing')


def off_rest(v):
    return abs(v[0]) + abs(v[1]) > 0.01


def owner_of(current, source, previous, values, stick):
    if not off_rest(values.get(source, {}).get(stick, (0, 0))):
        return current
    if not off_rest(previous or (0, 0)):
        return source
    if current is None or not off_rest(values.get(current, {}).get(stick, (0, 0))):
        return source
    return current


def value_of(owner, values, stick):
    if owner is not None and off_rest(values.get(owner, {}).get(stick, (0, 0))):
        return values[owner][stick]
    for source in ('touch', 'physical'):
        if source != owner and off_rest(values.get(source, {}).get(stick, (0, 0))):
            return values[source][stick]
    return (0, 0)


def replay(events, rule):
    axes, owners, sent = {}, {}, []
    for source, stick, x, y in events:
        previous = axes.get(source, {}).get(stick)
        axes.setdefault(source, {})[stick] = (x, y)
        if rule == 'old':
            physical = axes.get('physical', {}).get(stick, (0, 0))
            sent.append(physical if abs(physical[0]) + abs(physical[1]) > 0.01 else axes.get('touch', {}).get(stick, (0, 0)))
        else:
            owners[stick] = owner_of(owners.get(stick), source, previous, axes, stick)
            sent.append(value_of(owners[stick], axes, stick))
    return sent


# StickMapping.apply (upstream ControllerMapping.swift, vendored unchanged): 0.1 radial deadzone, rescaled.
def apply(x, y, deadzone=0.1):
    magnitude = (x * x + y * y) ** 0.5
    if magnitude <= deadzone or magnitude == 0:
        return (0.0, 0.0)
    scaled = min((magnitude - deadzone) / (1 - deadzone), 1) / magnitude
    return (x * scaled, y * scaled)


drift = apply(0.22, 0.0)  # a worn stick resting at 0.22: 0.133 after the deadzone, reported once at connect/settle
check(off_rest(drift), 'drift model')
touch_drag = [('touch', 1, 0.0, v) for v in (0.2, 0.5, 0.8, 1.0, 1.0)]
jitter = [('physical', 1, *apply(0.23, 0.01)), ('physical', 1, *apply(0.21, -0.01))]
scenario = [('physical', 1, *drift), *touch_drag[:3], *jitter, *touch_drag[3:], ('touch', 1, 0.0, 0.0),
            ('physical', 1, *apply(0.0, 0.0)), ('physical', 1, *apply(0.0, 0.9)), ('touch', 1, 0.5, 0.0), ('physical', 1, 0.0, 0.0),
            ('touch', 1, 0.6, 0.0)]
old, new = replay(scenario, 'old'), replay(scenario, 'new')
touch_indices = [1, 2, 3, 6, 7]  # the touch drag while the controller stick rests off zero
# Old rule: with the controller stick resting off zero, no touch value of the left stick ever reaches the engine.
check(all(old[i] == drift or old[i] == (jitter[0][2], jitter[0][3]) or old[i] == (jitter[1][2], jitter[1][3]) for i in touch_indices),
      'old rule did not starve the touch stick in the model')
# New rule: every touch drag value is sent, drift jitter does not take the stick back while the touch is held.
check([new[i] for i in touch_indices] == [(e[2], e[3]) for i, e in enumerate(scenario) if i in touch_indices], 'touch values not sent')
check(new[4] == new[5] == (0.0, 0.8) and new[6] == new[7] == (0.0, 1.0), 'drift jitter took the stick from an active touch')
check(new[8] == (jitter[1][2], jitter[1][3]), 'once the touch rests, a controller stick held off rest is used (as before)')
check(new[9] == (0.0, 0.0) and new[10] == apply(0.0, 0.9), 'controller pushed from rest takes the stick')
check(new[11] == (0.5, 0.0) and new[12] == (0.5, 0.0) and new[13] == (0.6, 0.0),
      'a touch leaving rest takes the stick from a held controller; the controller resting does not take it back')
# Without a controller the rule is the old one exactly.
alone = [('touch', s, x, y) for s in (1, 2) for x, y in ((0.1, 0.2), (0.9, -0.4), (0.0, 0.0), (0.3, 0.3))]
check(replay(alone, 'old') == replay(alone, 'new'), 'touch-only behaviour changed')
# And a controller alone too.
pad_only = [('physical', 1, *apply(x, y)) for x, y in ((0.05, 0), (0.5, 0.5), (1, 0), (0.0, 0.0))]
check(replay(pad_only, 'old') == replay(pad_only, 'new'), 'controller-only behaviour changed')

# --- Native return codes ---
check('''    @discardableResult
    func button(_ id: Int64, pad: Int32, button: Int32, pressed: Bool) -> Int32 {
        buttonFunction(id, pad, button, pressed ? 1 : 0)
    }
    @discardableResult
    func stick(_ id: Int64, pad: Int32, stick: Int32, x: Float, y: Float) -> Int32 {
        stickFunction(id, pad, stick, max(-1, min(1, x)), max(-1, min(1, y)))
    }''' in runtime, 'runtime stick/button do not return the export code')
check('MeloNXPerfJournal' not in runtime and 'MeloNXStdioCapture' not in runtime and 'MeloNXInputCounters' not in runtime,
      'runtime API depends on host diagnostics')
native = (ROOT / 'native/melonx/EmbeddedInput.cs').read_text()
check('return EmbeddedSessions.WithInputs(generation, action) ? 0 : 2;' in native and 'return 3;' in native and
      "if ((stick != 1 && stick != 2) || !float.IsFinite(x) || !float.IsFinite(y)) return 1;" in native, 'export codes')
check('if before != after { counters.button(code: runtime.button(generation, pad: pad, button: index, pressed: after)) }' in router,
      'button code not counted')
check('guard !closed, !suspended else { counters.dropped(); return }' in block(router, 'private func setButton('), 'button drops')

# --- Counters and the perf field ---
counters = block(diagnostics, 'final class MeloNXInputCounters {')
check(counters.count('lock.lock()') == 4 and counters.count('defer { lock.unlock() }') == 3 and 'drops += 1; lock.unlock()' in counters,
      'counters not under their lock')
check('for key in ["tL", "tR", "pL", "pR"] {' in counters and 'for key in ["oL", "oR"] {' in counters and
      'parts.append("e\\(refused):\\(lastRefusal)")' in counters and
      'events.removeAll(); largest.removeAll(); buttons = 0; drops = 0; refused = 0; lastRefusal = 0' in counters and
      'return parts.isEmpty ? nil : parts.joined(separator: ",")' in counters, 'in= format or reset')
check('if let text = Self.input() { fields.append("in=" + text) }' in journal and
      journal.index('fields.append("mem=" + text)') < journal.index('fields.append("in=" + text)') < journal.index('fields.append("th="'),
      'in= not between mem= and th=')
check('//   in=    input the session' in journal, 'in= not documented')
setter = block(journal, 'static func setInput(owner: AnyObject, _ source: (() -> String?)?)')
check('if let source { inputOwner = ObjectIdentifier(owner); inputSource = source }' in setter and
      'else if inputOwner == ObjectIdentifier(owner) { inputOwner = nil; inputSource = nil }' in setter,
      'a closing router could clear the next session\'s counters')
init = block(router, 'init(runtime: MeloNXRuntimeAPI, generation: Int64, game: URL, titleID: String? = nil)')
check(init.index('MeloNXPerfJournal.setInput(owner: self) { counters.take() }') < init.index('\n        reconnect()\n') < init.index('journalState("start")'),
      'counters not installed at session start')
check('[weak self]' not in init[init.index('let counters = self.counters'):init.index('\n        reconnect()\n')] and 'self.' not in init[init.index('{ counters.take() }') - 1:init.index('{ counters.take() }') + 20], 'the hook must not capture the router')
close = block(router, 'func close()')
check('MeloNXPerfJournal.setInput(owner: self, nil)' in close and close.index('releaseTouch()') < close.index('MeloNXPerfJournal.setInput(owner: self, nil)'),
      'counters not removed at close')
# The journal file stays compilable alone (melonx_perf_journal_test, capture test).
check('MeloNXInputCounters' not in journal and 'MeloNXInputRouter' not in journal, 'perf journal depends on the router')
# Lot 9 adds the stall watch's two writes in its own class (bound by melonx_perf_journal_test); the sampler's own
# writes stay these four.
sampler = journal[:journal.index('final class MeloNXStallWatch {')]
check(sampler.count('MeloNXStdioCapture.appendLine(') == 4 and journal.count('MeloNXStdioCapture.appendLine(') == 6, 'journal writes changed')

# --- Launch-journal state line ---
state = block(router, 'func journalState(_ reason: String)')
check('MeloNXLaunchJournal.record("input", "state", detail: reason + "; " + state)' in state and
      'guard reason == "start" || state != journaled else { return }' in state, 'state line or its change filter')
reasons = re.findall(r'journalState\("(\w+)"\)', router)
check(sorted(set(reasons)) == ['controllers', 'hideWithController', 'resume', 'start'], reasons)
check('if !value { journalState("resume") }' in block(router, 'func suspend(_ value: Bool)'), 'resume line')
check('if journaled != nil { journalState("controllers") }' in block(router, 'func reconnect()'), 'controller line')
check('journalState("hideWithController")' in router[router.index('@Published var hideWithController'):router.index('private let legacyGameID')],
      'toggle line')
check('mapping=\\(resolved.origin) \\(sources) dz=\\(deadzones)' in state and
      'let sources = "L=\\(resolved.mapping.leftStick.source.rawValue) R=\\(resolved.mapping.rightStick.source.rawValue)"' in state,
      'mapping origin and sources')
resolved = block(router, 'private func resolvedMapping(for controller: GCController)')
check([o for o in re.findall(r'"(game|legacy|global|standard)"', resolved)] == ['game', 'legacy', 'global', 'standard'], 'mapping origins')
check('func mapping(for controller: GCController) -> ControllerMapping { resolvedMapping(for: controller).mapping }' in router, 'mapping(for:)')
layout = block(diagnostics, 'static func layout(gameID: String) -> String')
check('if let game = decode(gameID + ".json")' in layout and 'decode("default.json")' in layout and 'var layout = LayoutConfig()' in layout,
      'layout origin does not follow LayoutManager.load (game file, default.json, built-in)')
check('appendingPathComponent("MeloNX/controller_layouts")' in layout and
      "text.replace(old, 'return docDir.appendingPathComponent(\"MeloNX/controller_layouts\")')" in VENDOR.read_text(),
      'layout directory differs from the vendored LayoutManager')
check('let key = gameID.count == 16 ? gameID : "path-keyed"' in layout, 'a 64-hex path key would be redacted')
for field in ('hidden=', 'hide=', 'offset=', 'scale=', 'opacity='):
    check(field in block(layout, 'func stick(_ id: String) -> String'), field)
check('stick("leftJoystick")' in layout and 'stick("rightJoystick")' in layout, 'stick ids')
# A model of one detail exercises the journal's two scrubbers exactly as MeloNXLaunchJournal.record applies them.
detail = ('resume; layout game 0100f7e00c70e000; left hidden=1 hide=1 offset=0,0 scale=1.00 opacity=-; right default; '
          'dpad hidden=0 scale=1.00; abxy hidden=0 scale=1.00; size=1.00 slide=1 dpadStick=0; overlay shown hideWithController=1; '
          'controllers 1; pad1 Xbox Wireless Controller|Xbox One mapping=game L=unbound R=right dz=0.10/0.10')
check(not re.search(r'(?im)^\s*[a-z0-9_]+\s*=\s*[^\r\n]+', detail) and not re.search(r'(?i)\b[0-9a-f]{32,}\b', detail), 'detail scrubbed')
check(all(r in ('start', 'resume', 'controllers', 'hideWithController') for r in reasons), 'reason words')
name = block(diagnostics, 'static func name(_ text: String) -> String')
check('$0 == ";" || $0 == "=" || $0 == "|" || $0.isNewline ? "_" : $0' in name and '.prefix(40)' in name, 'controller name not bounded')
# The vendored layout model has every member read here (vendor_controller.py adds opacity).
vendor = VENDOR.read_text()
check("text.replace('    var hidden: Bool = false', '    var hidden: Bool = false\\n    var opacity: CGFloat? = nil')" in vendor, 'opacity member')
if melo:
    model = (melo / 'Sources/Melo-Controller/Models/Layout.swift').read_text()
    for member in ('var offset: CGSize = .zero', 'var scale: CGFloat = 1.0', 'var hide: Bool = true', 'var hidden: Bool = false',
                   'var buttons: [String: ButtonLayout] = [:]', 'var joysticks: [String: JoystickLayout] = [:]', 'public init() {}'):
        check(member in model, 'layout model member ' + member)
    manager = (melo / 'Sources/Melo-Controller/Layout/LayoutManager.swift').read_text()
    check('let fileName = gameId?.isEmpty == false ? "\\(gameId!).json" : "default.json"' in manager and 'return load(for: nil)' in manager,
          'LayoutManager.load fallback changed')
    view = (melo / 'Sources/Melo-Controller/ControllerView.swift').read_text()
    check(view.count('editableJoystick(id: "leftJoystick", showBackground: $hideDpad)') == 2 and
          view.count('editableJoystick(id: "rightJoystick", iscool: true, showBackground: $hideABXY)') == 2, 'stick ids in the layouts')
    for key in ('On-ScreenControllerScale', 'buttonSlide', 'joystickDpad'):
        check(f'@AppStorage("{key}")' in (melo / 'Sources/Melo-Controller/Buttons/ButtonView.swift').read_text(), key)
# The host files strictly bound by older tests stay untouched (no new observer, no new controller line).
controller = CONTROLLER.read_text()
check('MeloNXInputCounters' not in controller and 'journalState' not in controller, 'session controller changed')

# --- The guest's controller setup survives the NSLog budget (bounded) ---
parity = (CLASSES / 'MeloNXStandaloneParity.swift').read_text()
check('static let hidLineLimit = 64' in parity and parity.count('hidLines') == 3, 'Hid exemption bound')
pump = block(parity, 'private static func pump(')
exemption = 'if nslogLines >= nslogLineLimit, hidLines < hidLineLimit, message.contains("{Hid}") || message.contains("| Hid ") { hidLines += 1 }'
check(exemption in pump and pump.index('if let count = seen[message] {') < pump.index(exemption) < pump.index('guard nslogLines < nslogLineLimit else { dropped += 1; return }'),
      'Hid lines are exempted only past the budget, after the repeat filter')
check('record("capture end: \\(lines) lines, \\(nslogLines) NSLog lines, \\(repeated) repeats, \\(dropped) not copied")' in parity, 'capture summary changed')
# Ryujinx's own formats in the second player's 621 capture (no device data copied): matched; the parity harness stub is not.
for line, expected in (('00:00:00.576 |I| Hid SetupNpad: Connected Controller ProController to Player1', True),
                       ('00:01:11.380 |S| {Hid} ServiceHid SetSupportedNpadStyleSet: Stubbed. {}', True),
                       ('00:05:00.632 |W| Hid Remap: No matching controllers found.', True),
                       ('00:00:00.000 |S| {Common} ServiceHid GetNpadJoyHoldType: Stubbed. {}', False),
                       ('00:00:00.000 |S| stub 12', False)):
    check(('{Hid}' in line or '| Hid ' in line) == expected, 'Hid match ' + line)

# --- Execution where a Swift compiler exists ---
swiftc = shutil.which('swiftc')
executed = 'not run: no Swift compiler'
if swiftc:
    with tempfile.TemporaryDirectory(prefix='melonx-input-stick-') as temporary:
        work = Path(temporary)
        harness = 'import Foundation\nenum R {\n' + ARBITRATION + '\n}\n' + counters + '\n' + r'''
var axes: [String: [Int32: (Float, Float)]] = [:]
var owner: String?
var out: [String] = []
for line in CommandLine.arguments[1].split(separator: ";") {
    let f = line.split(separator: ","); let source = String(f[0]); let stick = Int32(f[1])!
    let previous = axes[source]?[stick]
    axes[source, default: [:]][stick] = (Float(f[2])!, Float(f[3])!)
    owner = R.stickOwner(current: owner, source: source, previous: previous, values: axes, stick: stick)
    let v = R.stickValue(owner: owner, values: axes, stick: stick)
    out.append(String(format: "%.4f,%.4f", v.0, v.1))
}
print(out.joined(separator: ";"))
let c = MeloNXInputCounters()
c.stick(source: "touch", stick: 1, value: (0, 1), sent: (0, 1), code: 0); c.stick(source: "physical", stick: 2, value: (0.5, 0), sent: (0.5, 0), code: 2)
c.button(code: 0); c.dropped()
print(c.take() ?? "nil"); print(c.take() ?? "nil")
'''
        (work / 'main.swift').write_text(harness)
        subprocess.run([swiftc, '-O', str(work / 'main.swift'), '-o', str(work / 'probe')], check=True, timeout=300)
        argument = ';'.join(f'{s},{k},{x:.6f},{y:.6f}' for s, k, x, y in scenario)
        lines = subprocess.run([str(work / 'probe'), argument], check=True, capture_output=True, text=True).stdout.splitlines()
        expected = ';'.join(f'{v[0]:.4f},{v[1]:.4f}' for v in new)
        check(lines[0] == expected, f'Swift arbitration differs from the model: {lines[0]} != {expected}')
        check(lines[1] == 'tL1/1.00,pR1/0.50,oL1.00,oR0.50,b1,d1,e1:2' and lines[2] == 'nil', 'counters ' + str(lines[1:]))
        executed = 'arbitration and counters compiled and executed'

out = ROOT / 'dist/melonx/input-stick-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(dict(result='passed', checks=checks, swiftExecution=executed, controllerSourceChecked=melo is not None,
    oldRuleTouchSent=[old[i] for i in touch_indices], newRuleTouchSent=[new[i] for i in touch_indices],
    inputs={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (ROUTER, DIAGNOSTICS, JOURNAL, RUNTIME, CLASSES / 'MeloNXStandaloneParity.swift', Path(__file__))}), indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, swiftExecution=executed,
                      oldRuleTouchSent=[old[i] for i in touch_indices], newRuleTouchSent=[new[i] for i in touch_indices])))
