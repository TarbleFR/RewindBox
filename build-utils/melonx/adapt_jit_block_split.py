"""Split A64 translation blocks by a linear merge with sorted branch targets.

The decoder already sorts branch targets, but SplitBlocks restarted a scan
of every block for each target outside the unit and inserted splits into the
middle of the block list. Splitting one long block at many targets repeatedly
copied its remaining instructions. Merge once and copy each resulting range
once; preserve the original block objects when no split is necessary.
Unordered, wrapping or unaligned synthetic layouts retain the original path.
"""
from adapt_session import once


def apply(source):
    decoder = source / 'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs'
    declaration = '        private static void SplitBlocks(List<Block> blocks, List<ulong> branchTargets)\n'
    once(decoder, declaration, '''        private static void SplitBlocks(List<Block> blocks, List<ulong> branchTargets)
        {
            if (blocks.Count == 0 || branchTargets.Count == 0)
            {
                return;
            }

            // DecodeMulti emits consecutive blocks and relative A64 branches.
            // Preserve the original general path for an unusual/wrapping layout.
            for (int index = 0; index < blocks.Count; index++)
            {
                Block block = blocks[index];

                if (block.EndAddress < block.Address || ((block.EndAddress - block.Address) & 3UL) != 0 ||
                    ((block.Address ^ blocks[0].Address) & 3UL) != 0 ||
                    (index != 0 && block.Address < blocks[index - 1].EndAddress))
                {
                    SplitBlocksUnordered(blocks, branchTargets);
                    return;
                }
            }

            for (int index = 0; index < branchTargets.Count; index++)
            {
                ulong target = branchTargets[index];

                if (((target ^ blocks[0].Address) & 3UL) != 0 ||
                    (index != 0 && target < branchTargets[index - 1]))
                {
                    SplitBlocksUnordered(blocks, branchTargets);
                    return;
                }
            }

            List<Block> result = null;
            int targetIndex = 0;

            for (int blockIndex = 0; blockIndex < blocks.Count; blockIndex++)
            {
                Block block = blocks[blockIndex];

                while (targetIndex < branchTargets.Count && branchTargets[targetIndex] <= block.Address)
                {
                    targetIndex++;
                }

                if (targetIndex == branchTargets.Count || branchTargets[targetIndex] >= block.EndAddress)
                {
                    result?.Add(block);
                    continue;
                }

                if (result == null)
                {
                    result = new(blocks.Count);

                    for (int previous = 0; previous < blockIndex; previous++)
                    {
                        result.Add(blocks[previous]);
                    }
                }

                ulong start = block.Address;
                int firstInstruction = 0;

                while (targetIndex < branchTargets.Count && branchTargets[targetIndex] < block.EndAddress)
                {
                    ulong target = branchTargets[targetIndex++];

                    if (target == start)
                    {
                        continue; // Duplicate branch target.
                    }

                    int count = (int)((target - start) / 4UL);
                    result.Add(new(start, target, block.Instructions.GetRange(firstInstruction, count), false, false, false));
                    firstInstruction += count;
                    start = target;
                }

                result.Add(new(start, block.EndAddress,
                    block.Instructions.GetRange(firstInstruction, block.Instructions.Count - firstInstruction),
                    block.EndsWithBranch, block.IsTruncated, block.IsLoopEnd));
            }

            if (result != null)
            {
                blocks.Clear();
                blocks.AddRange(result);
            }
        }

        private static void SplitBlocksUnordered(List<Block> blocks, List<ulong> branchTargets)
''')
    return [decoder]
