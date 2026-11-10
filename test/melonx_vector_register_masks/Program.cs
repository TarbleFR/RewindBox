using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Ryujinx.Cpu.LightningJit;
using Ryujinx.Cpu.LightningJit.Arm64;
using Ryujinx.Cpu.LightningJit.Arm64.Target.Arm64;
using Ryujinx.Cpu.LightningJit.Graph;

static class Program
{
    static int cases, checks, baselineFailures, register31Cases, wrappingCases, controls;
    static readonly ContextTransfers Transfers = new();
    static uint V(int index) => 1u << index;
    static uint G(int index) => index == 31 ? 0 : V(index);
    static uint ListMask(int first, int count) {
        uint result=0;
        for(int i=0;i<count;i++) result|=V((first+i)%32);
        return result;
    }
    static void Require(bool condition,string message) {
        checks++;
        if(!condition) throw new Exception(message);
    }
    static (uint rg,uint rv,uint wg,uint wv) Masks(uint encoding,bool corrected) {
        var (name,flags,form)=corrected?InstTable.GetInstNameAndFlags(encoding,IsaVersion.v89,(IsaFeature)ulong.MaxValue):BaselineInstTable.GetInstNameAndFlags(encoding,IsaVersion.v89,(IsaFeature)ulong.MaxValue);
        Require(name!=InstName.UdfPermUndef,$"actual decoder rejected {encoding:x8}");
        var read=corrected?RegisterUtils.PopulateReadMasks(name,flags,encoding):BaselineRegisterUtils.PopulateReadMasks(name,flags,encoding);
        var write=corrected?RegisterUtils.PopulateWriteMasks(name,flags,encoding):BaselineRegisterUtils.PopulateWriteMasks(name,flags,encoding);
        return(read.Item1,read.Item2,write.Item1,write.Item2);
    }
    // Independently decode actual context LDR/STR Q and LDP/STP Q words.
    // This executes their data transfers in a 128-bit register/context model;
    // it is not a claim that generated ARM64 ran on this host.
    static uint Transfer(bool load,uint mask,UInt128[] registers,UInt128[] context) {
        uint touched=0;
        void One(int reg,int offset) {
            Require(offset==256+reg*16,"wrong emitted context slot");
            Require((touched&V(reg))==0,"duplicate emitted context transfer");
            touched|=V(reg);
            if(load)registers[reg]=context[reg];else context[reg]=registers[reg];
        }
        foreach(uint word in Transfers.Emit(load,mask)) {
            Require(((word>>5)&31)==19,"wrong context base");
            int rt=(int)(word&31);
            if((word&0xffc00000u)==(load?0x3dc00000u:0x3d800000u))
                One(rt,(int)((word>>10)&4095)*16);
            else {
                Require((word&0xffc00000u)==(load?0xad400000u:0xad000000u),"unexpected emitted context opcode");
                int offset=((int)(word<<10)>>25)*16;
                One(rt,offset);One((int)((word>>10)&31),offset+16);
            }
        }
        Require(touched==mask,"emitted context transfers lost mask bits");
        return touched;
    }
    static void Case(string label,uint encoding,uint rg,uint rv,uint wg,uint wv,bool control=false) {
        var expected=(rg,rv,wg,wv);var before=Masks(encoding,false);var after=Masks(encoding,true);
        if(before!=expected)baselineFailures++;
        Require(after==expected,$"{label} {encoding:x8}: expected{expected}, got{after}");
        if(control){controls++;Require(before==after,"GPR-only control changed");}
        UInt128[] regs=new UInt128[32], context=new UInt128[32];
        for(int i=0;i<32;i++){regs[i]=((UInt128)(1000+i)<<64)|(uint)(0x100+i);context[i]=(uint)(0x200+i);}
        var initialRegs=(UInt128[])regs.Clone();var initialContext=(UInt128[])context.Clone();
        Transfer(false,after.wv,regs,context);
        for(int i=0;i<32;i++)Require(context[i]==(((wv&V(i))!=0)?initialRegs[i]:initialContext[i]),"store includes every live vector and preserves others");
        Array.Copy(initialContext,context,32);
        Transfer(true,after.rv,regs,context);
        for(int i=0;i<32;i++)Require(regs[i]==(((rv&V(i))!=0)?initialContext[i]:initialRegs[i]),"load includes every live vector and preserves others");
        if(((rv|wv)&V(31))!=0)register31Cases++;
        cases++;
    }
    static InstInfo Instruction(uint encoding,bool corrected) {
        var(name,flags,form)=corrected?InstTable.GetInstNameAndFlags(encoding,IsaVersion.v89,(IsaFeature)ulong.MaxValue):BaselineInstTable.GetInstNameAndFlags(encoding,IsaVersion.v89,(IsaFeature)ulong.MaxValue);
        var mask=Masks(encoding,corrected);
        return new(encoding,name,flags,form,new RegisterUse(new(mask.rg,mask.rv,0),new(mask.wg,mask.wv,0)));
    }
    static (uint read,uint write) Unit(uint encoding,bool corrected) {
        Block block=new(0x1000,0x1004,new(){Instruction(encoding,corrected)},false,true,false);block.Number(0);
        MultiBlock graph=new(new(){block},new(0,0,0),false,true);
        return(graph.ReadMasks[0].FpSimdMask,graph.WriteMasks[0].FpSimdMask);
    }
    static bool CrossUnitPointer(bool corrected) {
        // LDR Q31 literal in one translation, FMOV X0,D31 in the next. Both
        // decode with the real table; context masks come from Block/DataFlow.
        var producer=Unit(0x9c00001fu,corrected);var consumer=Unit(0x9e6603e0u,corrected);
        UInt128[] registers=new UInt128[32],context=new UInt128[32];
        UInt128 wanted=((UInt128)0xaabbccdd11223344UL<<64)|0x12345003UL;
        context[31]=0xfedc0003UL;registers[31]=wanted;
        Transfer(false,producer.write,registers,context);
        registers[31]=0xdead0003UL; // Host/another unit owns caller-saved V31.
        Transfer(true,consumer.read,registers,context);
        return registers[31]==wanted;
    }
    static bool TbxIncomingDestination(bool corrected) {
        // TBX V0.16B,{V1.16B},V2.16B retains the original destination for
        // every index255, so liveness must load V0 before the guest operation.
        var unit=Unit(0x4e021020u,corrected);
        UInt128[] registers=new UInt128[32],context=new UInt128[32];
        UInt128 wanted=((UInt128)0xaabbccdd11223344UL<<64)|0x12345003UL;
        context[0]=wanted;context[2]=UInt128.MaxValue;
        Transfer(true,unit.read,registers,context);
        UInt128 result=registers[0];
        for(int lane=0;lane<16;lane++) {
            int index=(int)((registers[2]>>(8*lane))&255);
            if(index<16) {
                UInt128 b=(registers[1]>>(8*index))&255;
                result=(result&~((UInt128)255<<(8*lane)))|(b<<(8*lane));
            }
        }
        return result==wanted;
    }
    static void Main() {
        for(int i=0;i<32;i++) {
            uint r=(uint)i;
            Case("FADD destination",0x1e622820u|r,0,V(1)|V(2),0,V(i));
            Case("FADD first source",0x1e622800u|(r<<5),0,V(i)|V(2),0,V(0));
            Case("FADD second source",0x1e602820u|(r<<16),0,V(1)|V(i),0,V(0));
            Case("FMADD accumulator",0x1f420020u|(r<<10),0,V(1)|V(2)|V(i),0,V(0));
            Case("BSL read-write destination",0x6e621c20u|r,0,V(i)|V(1)|V(2),0,V(i));
            Case("TBX read-write destination",0x4e021020u|r,0,V(i)|V(1)|V(2),0,V(i));
            Case("FMOV Xn,D2",0x9e660040u|r,0,V(2),G(i),0);
            Case("FMOV X0,Dn",0x9e660000u|(r<<5),0,V(i),V(0),0);
            Case("FMOV Dn,X2",0x9e670040u|r,G(2),0,0,V(i));
            Case("FMOV D0,Xn",0x9e670000u|(r<<5),G(i),0,0,V(0));
            Case("SCVTF Dn,X2",0x9e620040u|r,G(2),0,0,V(i));
            Case("SCVTF D0,Xn",0x9e620000u|(r<<5),G(i),0,0,V(0));
            Case("FCVTZS Xn,D2",0x9e780040u|r,0,V(2),G(i),0);
            Case("FCVTZS X0,Dn",0x9e780000u|(r<<5),0,V(i),V(0),0);
            Case("LDR Q literal",0x9c000000u|r,0,0,0,V(i));
            Case("LDR D literal",0x5c000000u|r,0,0,0,V(i));
            Case("LDR S literal",0x1c000000u|r,0,0,0,V(i));
            Case("LDR Q,[SP]",0x3dc003e0u|r,V(31),0,0,V(i));
            Case("STR Q,[SP]",0x3d8003e0u|r,V(31),V(i),0,0);
            Case("LDR Q0,[Xn]",0x3dc00000u|(r<<5),V(i),0,0,V(0));
            Case("STR Q0,[Xn]",0x3d800000u|(r<<5),V(i),V(0),0,0);
            Case("LDP Q2,Qn,[X1]",0xad400022u|(r<<10),V(1),0,0,V(2)|V(i));
            Case("STP Q2,Qn,[X1]",0xad000022u|(r<<10),V(1),V(2)|V(i),0,0);
            Case("LDR Q0,[X1,Xn]",0x3ce06820u|(r<<16),V(1)|G(i),0,0,V(0));
            Case("LD1 lane preserves remainder",0x0d4003e0u|r,V(31),V(i),0,V(i));
            Case("LD1 lane SP post-index",0x0ddf03e0u|r,V(31),V(i),V(31),V(i));
            Case("LD1 full vector SP post-index",0x4cdf73e0u|r,V(31),0,V(31),V(i));
            Case("LDR Q SP post-index",0x3cc107e0u|r,V(31),0,V(31),V(i));
            Case("STR Q SP post-index",0x3c8107e0u|r,V(31),V(i),V(31),0);
            Case("MOV Xn,X2",0xaa0203e0u|r,G(2),0,G(i),0,true);
            Case("MOV X0,Xn",0xaa0003e0u|(r<<16),G(i),0,V(0),0,true);
            Case("ADD Xn,SP,#0",0x910003e0u|r,V(31),0,V(i),0,true);
            Case("ADD SP,Xn,#0",0x9100001fu|(r<<5),V(i),0,V(31),0,true);
            Case("LDR Xn,[SP]",0xf94003e0u|r,V(31),0,G(i),0,true);
            Case("STR Xn,[SP]",0xf90003e0u|r,V(31)|G(i),0,0,0,true);
            Case("STXR Wn,X2,[SP]",0xc8007fe2u|(r<<16),V(31)|V(2),0,G(i),0,true);
        }
        for(int first=0;first<32;first++)for(int count=1;count<=4;count++) {
            uint opcode=count switch {1=>0x7000u,2=>0xa000u,3=>0x6000u,_=>0x2000u};
            uint vectors=ListMask(first,count);
            Case("LD1 list",0x4c400020u|opcode|(uint)first,V(1),0,0,vectors);
            Case("ST1 list",0x4c000020u|opcode|(uint)first,V(1),vectors,0,0);
            Case("TBL list",0x4e020003u|((uint)(count-1)<<13)|((uint)first<<5),0,vectors|V(2),0,V(3));
            Case("TBX list",0x4e021003u|((uint)(count-1)<<13)|((uint)first<<5),0,vectors|V(2)|V(3),0,V(3));
            if(first+count>32)wrappingCases+=4;
        }
        Require(baselineFailures>0,"must reproduce pre-fix mask loss");
        bool originalPreserved=CrossUnitPointer(false),fixedPreserved=CrossUnitPointer(true);
        Require(!originalPreserved,"original dispatch must lose V31 value");
        Require(fixedPreserved,"corrected dispatch must preserve all128 V31 bits");
        bool originalTbx=TbxIncomingDestination(false),correctedTbx=TbxIncomingDestination(true);
        Require(!originalTbx,"original TBX must lose incoming destination");
        Require(correctedTbx,"corrected TBX must preserve incoming destination");
        Console.WriteLine(JsonSerializer.Serialize(new {result="passed",cases,checks,baselineFailures,register31Cases,wrappingCases,controls,
            productionInstructionDecoder=true,productionMaskFunctions=true,productionBlockDataflow=true,
            productionContextMethodsAndAssembler=true,originalCrossUnitV31Preserved=originalPreserved,correctedCrossUnitV31Preserved=fixedPreserved,
            originalTbxDestinationPreserved=originalTbx,correctedTbxDestinationPreserved=correctedTbx}));
    }
}
