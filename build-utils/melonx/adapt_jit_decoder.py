"""End LightningJit translation units where the guest cannot fall through.

Hogwarts Legacy with its update (SDK 17.5.4), 27 October 2026 (Build 564
app.log): two sessions, one of them in a fresh process, ended about 32 s after
start with "System.OutOfMemoryException: JIT Cache exhausted" in
DualMappedNoWxCache.MemoryCache.Allocate, the 512 MB TXM code arena, which
never frees code. The base game had run 727 s in the same process.

The A64 decoder keeps decoding after a BRK or a permanently undefined
instruction, and after every BL/BLR, until a return, a far jump or 10,000
instructions. Clang places a no-return call (or a trap) at the end of a
function and the next function right after it, so each entry point translated
the following functions too, up to the cap, and each of those functions, when
called, translated its own copy. Measured offline with this engine's compiler
on the 93,318 function starts of a clang ARM64 C++ binary (libRPCS3Core,
46 MB of text): 293 MiB of host code for 64 MiB of guest code translated.

Stop where the code cannot continue: after a trap (the unit then resumes after
it through the dispatcher, as for a truncated unit, should its handler return),
and after a call or jump when the next instruction opens a stack frame
(STP/STR pre-indexed on SP, SUB SP): that is another function. A call keeps its
usual host call and return check; only its continuation becomes a separate unit,
translated if the call ever returns there. A branch target already known at that
address keeps the unit going. Same measurement: 123 MiB of host code (-58 %),
compile time -53 %, largest unit 898 KiB -> 232 KiB. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    decoder = source / 'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs'
    once(decoder, '''                if (!block.IsTruncated && TryGetBranchTarget(block, out ulong targetAddress))
                {
                    branchTargets.Add(targetAddress);
                }

                blocks.Add(block);

                if (block.IsTruncated || !HasNextBlock(block, block.EndAddress - 4UL, branchTargets))
                {
                    break;
                }

                address = block.EndAddress;''', '''                if (!block.IsTruncated && TryGetBranchTarget(block, out ulong targetAddress))
                {
                    branchTargets.Add(targetAddress);
                }

                bool nextIsTarget = branchTargets.Contains(block.EndAddress);

                if (!nextIsTarget && EndsWithTrap(block))
                {
                    // A trap does not fall through: end the unit here, and resume after
                    // it through the dispatcher should its handler ever return.
                    block = new(block.Address, block.EndAddress, block.Instructions, block.EndsWithBranch, true, block.IsLoopEnd);
                }

                blocks.Add(block);

                if (block.IsTruncated || !HasNextBlock(block, block.EndAddress - 4UL, branchTargets))
                {
                    break;
                }

                if (!nextIsTarget && EndsWithCallOrJump(block) && StartsFunction(memoryManager, block.EndAddress))
                {
                    // The next function starts here: the callee does not return or the
                    // jump was a tail call. A call keeps its return check; if it does
                    // return here, the dispatcher translates the continuation then.
                    if (block.Instructions[^1].Name != InstName.BUncond)
                    {
                        blocks.Add(new(block.EndAddress, block.EndAddress, [], false, true, false));
                    }

                    break;
                }

                address = block.EndAddress;''')
    once(decoder, '''        private static bool TryGetBranchTarget(Block block, out ulong targetAddress)
        {
            return TryGetBranchTarget(''', '''        private static bool EndsWithTrap(Block block)
        {
            return !block.IsTruncated && block.Instructions[^1].Name is InstName.Brk or InstName.UdfPermUndef;
        }

        private static bool EndsWithCallOrJump(Block block)
        {
            return block.Instructions[^1].Name is InstName.Bl or InstName.Blr or InstName.BUncond;
        }

        private static bool StartsFunction(IMemoryManager memoryManager, ulong address)
        {
            for (int index = 0; index < 4; index++)
            {
                ulong current = address + (ulong)index * 4UL;

                if (index != 0 && (current & 0xfffUL) == 0)
                {
                    break; // Only read the page the decoder would read next anyway.
                }

                uint encoding = memoryManager.Read<uint>(current);

                if (encoding == 0xd503201fu)
                {
                    continue; // NOP padding.
                }

                return (encoding & 0xffc003e0u) == 0xa98003e0u || // STP Xt, Xt2, [SP, #-imm]!
                       (encoding & 0xffc003e0u) == 0x6d8003e0u || // STP Dt, Dt2, [SP, #-imm]!
                       (encoding & 0xffe00fe0u) == 0xf8000fe0u || // STR Xt, [SP, #-imm]!
                       (encoding & 0xff8003ffu) == 0xd10003ffu;   // SUB SP, SP, #imm
            }

            return false;
        }

        private static bool TryGetBranchTarget(Block block, out ulong targetAddress)
        {
            return TryGetBranchTarget(''')
    return [decoder]
