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
compile time -53 %, largest unit 898 KiB -> 232 KiB.

The update still exhausted the arena after this (engine 566, 18:51 session of
the same day, about 30 s). One more unbounded case: after a forward B within
4 KB the decoder reads on through the code the jump passes over. A switch case,
entered through its jump table (BR), ends with a jump to the end of the switch,
so each case translated every case after it. Stop at such a jump when it passes
over 64 instructions or more and nothing in the unit enters them: no earlier
branch targets them, and the code at the jump target does not branch back into
them before its next unconditional branch (a rotated loop keeps its body).
Shorter skips keep the upstream unit. Measured with this engine's compiler on
the 20,543 jump-table targets of the same binary (1,116 tables): 26.6 -> 19.5
MiB of host code (-27 %); following every exit as the dispatcher would,
56.6 -> 41.6 MiB, and 408 -> 386 MiB from all function starts (-5 %) with
fewer units and exits. Fail closed on drift.
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

                if (!nextIsTarget && block.Instructions[^1].Name == InstName.BUncond &&
                    TryGetBranchTarget(block, out ulong jumpTarget) && jumpTarget >= block.EndAddress + 256UL &&
                    !IsSkippedCodeReachable(memoryManager, block.EndAddress, jumpTarget, branchTargets))
                {
                    // Nothing decoded so far enters the 64 or more instructions this forward
                    // jump passes over (the other cases of a switch): end the unit with the
                    // jump, whose target is then translated once for every unit reaching it.
                    // Upstream decoded on, so each case entered through a jump table
                    // translated every case after it as well. Shorter skips keep their unit.
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

        private static bool IsSkippedCodeReachable(IMemoryManager memoryManager, ulong start, ulong end, List<ulong> branchTargets)
        {
            foreach (ulong target in branchTargets)
            {
                if (target > start && target < end)
                {
                    return true; // An earlier branch enters the skipped code.
                }
            }

            // A rotated loop: the jump enters the loop condition, which branches back
            // into the skipped body. Look at the code at the jump target, up to its
            // first unconditional branch, without leaving its page.
            for (ulong address = end; address < end + 32 * 4UL; address += 4UL)
            {
                if (address != end && (address & 0xfffUL) == 0)
                {
                    break;
                }

                uint encoding = memoryManager.Read<uint>(address);
                long offset;

                if ((encoding & 0x7c000000u) == 0x14000000u) // B, BL
                {
                    offset = ImmUtils.ExtractSImm26Times4(encoding);
                }
                else if ((encoding & 0xff000010u) == 0x54000000u || (encoding & 0x7e000000u) == 0x34000000u) // B.cond, CBZ, CBNZ
                {
                    offset = ImmUtils.ExtractSImm19Times4(encoding);
                }
                else if ((encoding & 0x7e000000u) == 0x36000000u) // TBZ, TBNZ
                {
                    offset = ImmUtils.ExtractSImm14Times4(encoding);
                }
                else if ((encoding & 0xfe000000u) == 0xd6000000u && (encoding & 0xfffffc1fu) != 0xd63f0000u)
                {
                    break; // BR, RET, ERET (BLR returns: keep looking).
                }
                else
                {
                    continue;
                }

                if ((encoding & 0xfc000000u) == 0x94000000u)
                {
                    continue; // BL returns.
                }

                ulong target = address + (ulong)offset;

                if (target >= start && target < end)
                {
                    return true;
                }

                if ((encoding & 0xfc000000u) == 0x14000000u)
                {
                    break;
                }
            }

            return false;
        }

        private static bool TryGetBranchTarget(Block block, out ulong targetAddress)
        {
            return TryGetBranchTarget(''')
    return [decoder]
