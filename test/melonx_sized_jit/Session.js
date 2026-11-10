// Execute the complete packaged script from attachment through detach.
// Only the debugserver/VM boundary is doubled; no production function is cut out.
var helperTestState;
var helperTestOptions;
function helperTestHex(value) {
    var bytes = [];
    for (var i = 0; i < 8; i++) { bytes.push(Number(value & 255n).toString(16).padStart(2, '0')); value >>= 8n; }
    return bytes.join('');
}
function helperTestNumber(hex) {
    var value = 0n;
    for (var i = 7; i >= 0; i--) value = (value << 8n) | BigInt('0x' + hex.slice(i * 2, i * 2 + 2));
    return value;
}
function helperTestBegin(options) {
    helperTestOptions = options;
    helperTestState = { index: -1, returns: [], allocations: [], prepared: [], logs: [], detached: false,
        fields: [], writes: 0, currentReturn: null, packets: 0 };
}
function get_pid() { return 1234; }
function log(message) { helperTestState.logs.push(String(message)); }
function prepare_memory_region(address, size) {
    helperTestState.prepared.push([String(address), String(size)]);
    return helperTestOptions.prepareFailure ? 'E01' : 'OK';
}
function send_command(packet) {
    var state = helperTestState, options = helperTestOptions;
    if (++state.packets > 100) throw Error('Unbounded helper loop');
    if (packet === 'vAttach;4d2') return options.attachFailure ? 'E01' : 'T05thread:abc;';
    if (packet === 'qProcessInfo') return 'pid:' + (options.wrongPid ? '4d3' : '4d2') + ';';
    if (packet === 'c') {
        if (state.index >= 0) state.returns.push({ kind: options.events[state.index], returned: state.currentReturn, fields: state.fields.map(String) });
        state.currentReturn = null;
        var kind = options.events[++state.index];
        if (!kind) throw Error('Unexpected extra continue');
        var command = kind === 'probe' ? 3n : kind === 'detach' ? 0n : 1n;
        var address = kind === 'probe' ? 41n : kind === 'sized' ? 0x10000n : 0n;
        var length = kind === 'sized' ? 0x5242574a49543031n : kind === 'legacy' ? 512n << 20n : 0n;
        if (kind === 'sized') state.fields = [0x5242574a49543031n, 1024n << 20n, 512n << 20n, 64n << 20n, 0n, 0n, 0n, 0n];
        return 'T05thread:abc;20:' + helperTestHex(0x20000n) + ';10:' + helperTestHex(command) + ';00:' + helperTestHex(address) + ';01:' + helperTestHex(length) + ';';
    }
    if (packet === 'm20000,4') return 'a0013ed4';
    if (packet === 'm10000,40') return state.fields.map(helperTestHex).join('');
    if (packet.startsWith('_M')) {
        state.allocations.push(String(BigInt('0x' + packet.slice(2).split(',')[0])));
        return state.allocations.length <= (options.refused || 0) ? 'E05' : '400000000';
    }
    if (packet.startsWith('M10000,40:')) {
        var hex = packet.split(':')[1];
        state.fields = Array.from({ length: 8 }, function (_, i) { return helperTestNumber(hex.slice(i * 16, i * 16 + 16)); });
        state.writes++;
        return 'OK';
    }
    if (packet.startsWith('P20=')) return 'OK';
    if (packet.startsWith('P0=')) { state.currentReturn = String(helperTestNumber(packet.slice(3).split(';')[0])); return 'OK'; }
    if (packet === 'D') { state.detached = true; return 'OK'; }
    throw Error('Unexpected packet: ' + packet);
}
