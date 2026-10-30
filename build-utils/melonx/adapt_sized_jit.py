"""Negotiate a large TXM arena before its sole preparation, using a typed helper reply.

Only a documented clean debugserver allocation refusal can select a smaller
size. Alias/protection/preparation failures remain terminal; no constructor retry.
"""
import hashlib,json
from pathlib import Path
PATH='src/Ryujinx.Memory/DualMappedJitAllocator.cs'

def edits(source):
 p=source/PATH;s=p.read_text(encoding='utf-8-sig')
 old='''                    _mmapPtr = BreakGetJITMapping((nuint)Size);'''
 new='''                    // Only updated Hogwarts requests more than the TXM default.
                    // The helper negotiates before preparing exactly one RX region.
                    _mmapPtr = Size > (512UL << 20) ? PrepareSizedArena() : BreakGetJITMapping((nuint)Size);'''
 if s.count(old)!=1:raise RuntimeError('Sized arena allocation anchor drift')
 s=s.replace(old,new)
 marker='        private void AllocateDualMapping(nint? mapping = null)'
 addition='''        private unsafe nint PrepareSizedArena()
        {
            const ulong protocol = 0x5242574a49543031UL;
            ulong requested = Size;
            if (requested < (512UL << 20) || requested > (1024UL << 20) || requested % (64UL << 20) != 0)
                throw new ArgumentOutOfRangeException(nameof(Size));
            // An old helper treats null/zero as a no-op and returns zero. Never
            // hand it a descriptor that it might mistake for executable pages.
            if ((ulong)BreakGetJITMappingPub(null, 0) != protocol)
                throw new InvalidOperationException("The sized JIT helper protocol is required.");
            ulong* reply = stackalloc ulong[8];
            reply[0] = protocol; reply[1] = requested;
            reply[2] = 512UL << 20; reply[3] = 64UL << 20;
            reply[4] = reply[5] = reply[6] = reply[7] = 0;
            byte* returned = BreakGetJITMappingPub((byte*)reply, (nuint)protocol);
            if (reply[0] != protocol || reply[1] != requested || reply[2] != (512UL << 20) || reply[3] != (64UL << 20))
                throw new InvalidOperationException("The sized JIT request was corrupted.");
            if (reply[6] == 2 && returned == null && reply[4] == 0 && reply[5] == 0)
                throw new OutOfMemoryException("All JIT arena sizes were explicitly refused before preparation.");
            ulong actual = reply[4];
            if (reply[6] != 1 || actual < (512UL << 20) || actual > requested ||
                actual % (64UL << 20) != 0 || reply[7] < 1 || reply[7] > 9 ||
                returned == null || (ulong)returned != reply[5] || (reply[5] & 0x3fff) != 0)
                throw new InvalidOperationException("The sized JIT mapping is unproven; restart required.");
            Size = actual; // Every alias, cache allocator and RX/RW probe uses this size.
            return (nint)returned;
        }

'''
 if s.count(marker)!=1:raise RuntimeError('Sized arena method anchor drift')
 return {p:s.replace(marker,addition+marker)}

def apply(source):
 c=json.loads(Path(__file__).with_name('sized-jit-adapter-contract.json').read_text());before={p:hashlib.sha256((source/p).read_bytes()).hexdigest()for p in c['before']}
 if before==c['after']:return[source/p for p in before]
 if before!=c['before']:raise RuntimeError('Sized JIT preimage drift')
 out=edits(source)
 if {str(p.relative_to(source)):hashlib.sha256(s.encode()).hexdigest()for p,s in out.items()}!=c['after']:raise RuntimeError('Sized JIT postimage drift')
 for p,s in out.items():p.write_text(s)
 return list(out)
