const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[2],'utf8');
const block=source.split('// REWINDBOX_SIZED_ARENA_V1_BEGIN')[1].split('// REWINDBOX_SIZED_ARENA_V1_END')[0];
const utilities=source.split('// utilities')[1].split('// For making your own script')[0];
const magic=0x5242574a49543031n,MiB=1n<<20n;
let checks=0;
function check(v){checks++;assert(v);}
function encode(fields){const b=Buffer.alloc(64);fields.forEach((n,i)=>b.writeBigUInt64LE(n,i*8));return b.toString('hex');}
function decode(hex){const b=Buffer.from(hex,'hex');return Array.from({length:8},(_,i)=>b.readBigUInt64LE(i*8));}
function setup(options={}){
 const state={fields:[magic,1024n*MiB,512n*MiB,64n*MiB,0n,0n,0n,0n],alloc:[],prepare:[],ret:null};
 const context={x0:0x10000n,x1:magic,pc:0x20000n,tid:'abc',log:()=>{},log_verbose:()=>{},
  prepare_memory_region:(address,size)=>{state.prepare.push([address,size]);if(options.prepareThrows)throw Error('injected partial preparation');return options.prepare??'OK';},
  send_command:packet=>{
   if(packet==='m20000,4')return 'a0013ed4';
   if(packet==='m10000,40')return options.read??encode(state.fields);
   if(packet.startsWith('_M')){state.alloc.push(BigInt('0x'+packet.slice(2).split(',')[0]));if(options.allocateThrows)throw Error('transport lost');return state.alloc.length<=(options.refused??0)?'E05':options.allocate??'400000000';}
   if(packet.startsWith('M10000,40:')){if(options.writeFailure)return 'E01';state.fields=decode(packet.split(':')[1]);return 'OK';}
   if(packet.startsWith('P0=')){if(options.registerFailure)return 'E01';const b=Buffer.from(packet.slice(3).split(';')[0],'hex');state.ret=b.readBigUInt64LE();return 'OK';}
   throw Error('Unexpected packet '+packet);
  }};
 vm.createContext(context);vm.runInContext(block+utilities,context);return{state,context,run:()=>vm.runInContext('JIT26PrepareRegion("")',context)};
}
for(let refused=0;refused<=8;refused++){
 const t=setup({refused});t.run();
 check(t.state.alloc.length===refused+1);check(t.state.alloc.every((size,i)=>size===(1024n-64n*BigInt(i))*MiB));
 check(t.state.prepare.length===1);check(t.state.fields[4]===(1024n-64n*BigInt(refused))*MiB);check(t.state.fields[6]===1n);check(t.state.ret===0x400000000n);
 // Reentry in the same process never reserves another arena.
 t.state.fields=[magic,1024n*MiB,512n*MiB,64n*MiB,0n,0n,0n,0n];t.run();check(t.state.alloc.length===refused+1);check(t.state.fields[6]===4n);
}
const denied=setup({refused:9});denied.run();check(denied.state.alloc.length===9&&denied.state.prepare.length===0&&denied.state.ret===0n&&denied.state.fields[6]===2n);
for(const allocate of ['', 'OK','Ezz','-1','0','1','10001','ffffffffffffffff']){
 const t=setup({allocate});t.run();check(t.state.alloc.length===1&&t.state.prepare.length===0&&t.state.fields[6]===4n);
}
for(const prepare of ['E01','', 'unsupported']){
 const t=setup({prepare});t.run();check(t.state.alloc.length===1&&t.state.prepare.length===1&&t.state.fields[6]===3n&&t.state.ret===0n);
}
for(const options of [{allocateThrows:true},{prepareThrows:true},{writeFailure:true},{registerFailure:true}]){
 const t=setup(options);assert.throws(t.run);check(t.state.alloc.length===1);
}
for(const [index,value]of [[0,0n],[1,1088n*MiB],[1,1023n*MiB],[2,448n*MiB],[3,32n*MiB],[4,1n],[6,1n]]){
 const t=setup();t.state.fields[index]=value;assert.throws(t.run);check(t.state.alloc.length===0&&t.state.prepare.length===0);
}
for(const read of ['','E01','00','g'.repeat(128)]){const t=setup({read});assert.throws(t.run);check(t.state.alloc.length===0);}
const cap=setup();cap.context.x0=0n;cap.context.x1=0n;cap.run();check(cap.state.ret===magic&&cap.state.alloc.length===0&&cap.state.prepare.length===0);
const legacy=setup();legacy.context.x0=0n;legacy.context.x1=512n*MiB;legacy.run();check(legacy.state.alloc.length===1&&legacy.state.prepare.length===1&&legacy.state.ret===0x400000000n);
console.log(JSON.stringify({checks,result:'passed',nativeDebugserverDoubled:true,stagedPreparationFailureNeverRetried:true}));
