#!/usr/bin/env node
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(process.argv[2], 'utf8');
const fixture = fs.readFileSync(__dirname + '/melonx_sized_jit/Session.js', 'utf8');
const magic = String(0x5242574a49543031n);
let checks = 0;
function check(value, message) { checks++; assert(value, message); }
function run(options) {
    const context = vm.createContext({ neostationProbeNonce: 41 });
    vm.runInContext(fixture, context);
    vm.runInContext('helperTestBegin(' + JSON.stringify(options) + ')', context);
    let error = null;
    try { vm.runInContext(source, context, { timeout: 1000 }); } catch (e) { error = String(e); }
    const state = JSON.parse(vm.runInContext('JSON.stringify(helperTestState, function(key,value) { return typeof value === "bigint" ? String(value) : value; })', context));
    return { state, error };
}
if (process.argv.includes('--observations')) {
    const cases = JSON.parse(fs.readFileSync(process.argv[process.argv.indexOf('--observations') + 1], 'utf8'));
    console.log(JSON.stringify(cases.map(run)));
    process.exit(0);
}
for (let refused = 0; refused <= 9; refused++) {
    const {state, error} = run({refused, events: ['probe', 'capability', 'sized', 'capability', 'sized', 'detach']});
    check(error === null, error); check(state.detached); check(state.returns[0].returned === '42');
    check(state.returns[1].returned === magic && state.returns[3].returned === magic);
    check(state.allocations.length === Math.min(refused + 1, 9));
    check(state.prepared.length === (refused === 9 ? 0 : 1));
    const first = state.returns[2];
    check(first.fields[6] === (refused === 9 ? '2' : '1'));
    check(first.returned === (refused === 9 ? '0' : String(0x400000000n)));
    check(state.returns[4].fields[6] === '4' && state.returns[4].returned === '0');
}
const failure = run({prepareFailure:true, events:['probe','capability','sized','sized','detach']});
check(failure.error === null && failure.state.detached);
check(failure.state.allocations.length === 1 && failure.state.prepared.length === 1);
check(failure.state.returns[2].fields[6] === '3' && failure.state.returns[2].returned === '0');
check(failure.state.returns[3].fields[6] === '4');
const legacy = run({events:['probe','legacy','detach']});
check(legacy.error === null && legacy.state.detached);
check(legacy.state.allocations.length === 1 && legacy.state.prepared.length === 1);
check(legacy.state.returns[1].returned === String(0x400000000n));
for (const option of [{attachFailure:true},{wrongPid:true}]) {
    const result = run({...option, events:['probe','capability','sized','detach']});
    check(result.error !== null && result.state.allocations.length === 0 && result.state.prepared.length === 0);
}
console.log(JSON.stringify({result:'passed', checks, completePackagedScript:true, debugserverAndVmDoubled:true, physicalDeviceTested:false}));
