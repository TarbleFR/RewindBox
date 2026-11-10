"""Bindless handles still unbound after adapt_bindless: nested phis, ORs of loads, spills.

Hogwarts Legacy v1.0.4, 28 October 2026 (hog586.log, build 586 session): the
translator still logged "Failed to find handle source for bindless access",
now with the handle's IR (adapt_bindless DescribeHandle), and replaced each
such access with 0 (black samples, dropped image stores). Six shapes, each
reproduced on synthetic Maxwell code with the unmodified 586 translator (same
log text):

1. textureCube Shadow, manual textureGrad: Shuffle(BitwiseOr(Load.StorageBuffer,
   cb2[0x578]), lane, 0x1C03).
2. texture2D Shadow LodLevel: BitwiseOr(Load.StorageBuffer, cb2[0x578 or 0x570]).
3. texture3D LodLevel: BitwiseOr(Load.StorageBuffer, cb2[0x568]).
4. texture2D LodLevel: nested phis whose every leaf is BitwiseOr(cb2[0x170],
   cb2[0x570]). TryGetOperation sees through one phi of identical inputs only;
   the full-pool rule checks no source of a nested phi.
5. imageBuffer stores and textureBuffer fetches (compute): Load.LocalMemory(0,
   word): the handle was spilled (STL) and reloaded (LDL). The most frequent.
6. texture3D phis that mix a handle with 0, other loads or float/address values
   (one register reused on another path).

The full-pool access (GenerateBindlessAccess) indexes the texture pool with
the handle's runtime value, which is what the hardware does with any handle;
upstream limits it to constant buffer, input and storage buffer handles so
that ordinary shaders do not bind the whole pool.

Only an access that the upstream rules cannot bind is retried, so every
access they bind keeps the same code (the extended rules never run first):

- Exact binding (TryConvertBindless): a phi is followed through nested phis
  (and loops) to its leaves; when all are the same combined constant buffer
  handle, the access binds its texture and sampler as for one phi (4). A
  handle reloaded from local memory is replaced by the value stored there,
  when that store is the last write to the word on every path: it dominates
  the load (same block earlier, or a dominator) and no block between them, nor
  the load's block again through a loop, writes that word, writes local memory
  at a register offset or calls a function (local memory is private to the
  thread). A spilled constant buffer handle then binds exactly (5).
- Full pool (GenerateBindlessAccess): a handle made only of constant buffer,
  storage buffer, input and local memory loads and constants (at least one
  load), combined by BitwiseOr, through Shuffle and phis at any depth (1, 2,
  3, 5, part of 6). The runtime value still indexes the pool. Not for image
  stores and atomics: bound to the whole pool, each dispatch would mark every
  texture of the pool as modified by the GPU (UpdateFromPool), forcing their
  write-back before eviction, against adapt_device_memory's trims; such a
  write keeps the failure log unless its handle binds exactly.

Leaves that are float or address arithmetic, texture results or undefined
values stay unbound and keep the failure log (most of 6). An access bound by
these rules logs once, with the binding used, so the device log shows which
accesses bind the whole pool: each such binding costs CPU time per draw or
dispatch in proportion to the pool (TextureBindingsArrayCache.UpdateFromPool),
and a full-pool image has no known format, as upstream's. The host shader
cache version changes again so cached shaders are translated again. Fail
closed on drift.
"""
from adapt_session import once


def apply(source):
    elimination = source / 'src/Ryujinx.Graphics.Shader/Translation/Optimizations/BindlessElimination.cs'
    host_cache = source / 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/DiskCacheHostStorage.cs'

    once(elimination, '''                if (!TryConvertBindless(block, resourceManager, gpuAccessor, texOp) &&
                    !GenerateBindlessAccess(block, resourceManager, gpuAccessor, texOp, node))
                {
''', '''                // RewindBox: the upstream rules first, unchanged, so every access they bind keeps the
                // same code; only an access they cannot bind tries the extended handle sources.
                if (!TryConvertBindless(block, resourceManager, gpuAccessor, texOp, extendedSources: false) &&
                    !GenerateBindlessAccess(block, resourceManager, gpuAccessor, texOp, node, extendedSources: false) &&
                    !TryBindExtendedSources(block, resourceManager, gpuAccessor, texOp, node))
                {
''')
    once(elimination, '''        private static string DescribeHandle(Operand operand, int depth)
''', '''        // RewindBox: bound on the phis and operations walked (recursively) for one handle.
        private const int MaxHandleSourceNodes = 1024;

        private enum LocalMemoryWrite
        {
            None,
            Same,
            Unknown,
        }

        private static bool TryBindExtendedSources(
            BasicBlock block,
            ResourceManager resourceManager,
            IGpuAccessor gpuAccessor,
            TextureOperation texOp,
            LinkedListNode<INode> node)
        {
            string handle = DescribeHandle(texOp.GetSource(0), 3);
            string binding;

            if (TryConvertBindless(block, resourceManager, gpuAccessor, texOp, extendedSources: true))
            {
                binding = "its constant buffer handle";
            }
            // An image write bound to the whole pool would mark every texture of the pool as modified by the
            // GPU on each dispatch (TextureBindingsArrayCache.UpdateFromPool) and so force their write-back
            // before any eviction; such a write stays unbound unless its handle binds exactly.
            else if (!texOp.Inst.IsImageStore() &&
                GenerateBindlessAccess(block, resourceManager, gpuAccessor, texOp, node, extendedSources: true))
            {
                binding = "the whole texture pool";
            }
            else
            {
                return false;
            }

            gpuAccessor.Log($"Bound bindless {texOp.Inst} {texOp.Type} through {binding} (extended handle source). [handle={handle}]");

            return true;
        }

        private static bool AreAllPhiLeavesSame(PhiNode phi, ref Operand firstLeaf, HashSet<PhiNode> visited)
        {
            // A phi reached again (a loop, or shared by two inputs) adds no other value.
            if (!visited.Add(phi))
            {
                return true;
            }

            if (visited.Count > MaxHandleSourceNodes)
            {
                return false;
            }

            for (int index = 0; index < phi.SourcesCount; index++)
            {
                Operand source = phi.GetSource(index);

                if (source.AsgOp is PhiNode sourcePhi)
                {
                    if (!AreAllPhiLeavesSame(sourcePhi, ref firstLeaf, visited))
                    {
                        return false;
                    }
                }
                else if (firstLeaf == null)
                {
                    firstLeaf = source;
                }
                else if (!IsSameOperand(firstLeaf, source))
                {
                    return false;
                }
            }

            return true;
        }

        private static bool IsHandleFromMemory(Operand handle)
        {
            bool hasMemorySource = false;

            return IsHandleFromMemory(handle, new HashSet<INode>(), ref hasMemorySource) && hasMemorySource;
        }

        private static bool IsHandleFromMemory(Operand operand, HashSet<INode> visited, ref bool hasMemorySource)
        {
            if (operand.Type == OperandType.ConstantBuffer)
            {
                hasMemorySource = true;

                return true;
            }

            if (operand.Type == OperandType.Constant)
            {
                return true;
            }

            INode asgOp = operand.AsgOp;

            if (asgOp == null)
            {
                return false;
            }

            // Checked already, or being checked (a loop through a phi).
            if (!visited.Add(asgOp))
            {
                return true;
            }

            if (visited.Count > MaxHandleSourceNodes)
            {
                return false;
            }

            if (asgOp is PhiNode phi)
            {
                for (int index = 0; index < phi.SourcesCount; index++)
                {
                    if (!IsHandleFromMemory(phi.GetSource(index), visited, ref hasMemorySource))
                    {
                        return false;
                    }
                }

                return true;
            }

            if (asgOp is not Operation operation)
            {
                return false;
            }

            switch (operation.Inst)
            {
                case Instruction.Shuffle:
                    return IsHandleFromMemory(operation.GetSource(0), visited, ref hasMemorySource);
                case Instruction.BitwiseOr:
                    return IsHandleFromMemory(operation.GetSource(0), visited, ref hasMemorySource) &&
                        IsHandleFromMemory(operation.GetSource(1), visited, ref hasMemorySource);
                case Instruction.Load when operation.StorageKind is StorageKind.Input or StorageKind.StorageBuffer or StorageKind.LocalMemory:
                    hasMemorySource = true;

                    return true;
            }

            return false;
        }

        private static Operand GetSpilledHandleSource(Operand handle, BasicBlock useBlock)
        {
            if (handle.AsgOp is not Operation load ||
                load.Inst != Instruction.Load ||
                load.StorageKind != StorageKind.LocalMemory ||
                load.SourcesCount != 2 ||
                load.GetSource(0).Type != OperandType.Constant ||
                load.GetSource(1).Type != OperandType.Constant)
            {
                return handle;
            }

            int memoryId = load.GetSource(0).Value;
            int wordOffset = load.GetSource(1).Value;

            // The load dominates its use: it is in the use block or in one of its dominators.
            BasicBlock loadBlock = useBlock;
            LinkedListNode<INode> node = null;

            while (loadBlock != null && (node = FindNode(loadBlock, load)) == null)
            {
                loadBlock = loadBlock.ImmediateDominator != loadBlock ? loadBlock.ImmediateDominator : null;
            }

            if (node == null)
            {
                return handle;
            }

            // The last write to that word before the load, in its block or in a dominator.
            BasicBlock storeBlock = loadBlock;
            Operation store = null;

            while (store == null)
            {
                node = node.Previous;

                while (node == null)
                {
                    BasicBlock dominator = storeBlock.ImmediateDominator;

                    if (dominator == null || dominator == storeBlock)
                    {
                        return handle;
                    }

                    storeBlock = dominator;
                    node = storeBlock.Operations.Last;
                }

                switch (GetLocalMemoryWrite(node.Value, memoryId, wordOffset))
                {
                    case LocalMemoryWrite.Same:
                        store = (Operation)node.Value;
                        break;
                    case LocalMemoryWrite.Unknown:
                        return handle;
                }
            }

            if (storeBlock != loadBlock)
            {
                // No block on a path from the store's block to the load, the load's block again
                // included (a loop), may write that word.
                HashSet<BasicBlock> visited = new();
                Stack<BasicBlock> pending = new(loadBlock.Predecessors);

                while (pending.Count != 0)
                {
                    BasicBlock block = pending.Pop();

                    if (block == storeBlock || !visited.Add(block))
                    {
                        continue;
                    }

                    foreach (INode blockNode in block.Operations)
                    {
                        if (GetLocalMemoryWrite(blockNode, memoryId, wordOffset) != LocalMemoryWrite.None)
                        {
                            return handle;
                        }
                    }

                    foreach (BasicBlock predecessor in block.Predecessors)
                    {
                        pending.Push(predecessor);
                    }
                }
            }

            return store.GetSource(2);
        }

        private static LinkedListNode<INode> FindNode(BasicBlock block, INode value)
        {
            for (LinkedListNode<INode> node = block.Operations.First; node != null; node = node.Next)
            {
                if (node.Value == value)
                {
                    return node;
                }
            }

            return null;
        }

        private static LocalMemoryWrite GetLocalMemoryWrite(INode node, int memoryId, int wordOffset)
        {
            if (node is not Operation operation)
            {
                return LocalMemoryWrite.None;
            }

            // The callee may write local memory.
            if (operation.Inst == Instruction.Call)
            {
                return LocalMemoryWrite.Unknown;
            }

            if (operation.StorageKind != StorageKind.LocalMemory || operation.Inst == Instruction.Load)
            {
                return LocalMemoryWrite.None;
            }

            if (operation.Inst == Instruction.Store &&
                operation.SourcesCount == 3 &&
                operation.GetSource(0).Type == OperandType.Constant &&
                operation.GetSource(1).Type == OperandType.Constant)
            {
                if (operation.GetSource(0).Value != memoryId)
                {
                    return LocalMemoryWrite.None;
                }

                return operation.GetSource(1).Value == wordOffset ? LocalMemoryWrite.Same : LocalMemoryWrite.None;
            }

            return LocalMemoryWrite.Unknown;
        }

        private static string DescribeHandle(Operand operand, int depth)
''')
    once(elimination, '''            TextureOperation texOp,
            LinkedListNode<INode> node)
        {
            if (!gpuAccessor.QueryHostSupportsSeparateSampler())
''', '''            TextureOperation texOp,
            LinkedListNode<INode> node,
            bool extendedSources)
        {
            if (!gpuAccessor.QueryHostSupportsSeparateSampler())
''')
    once(elimination, '''            Operand bindlessHandle = texOp.GetSource(0);

            if (bindlessHandle.AsgOp is PhiNode phi)
            {
''', '''            Operand bindlessHandle = texOp.GetSource(0);

            if (extendedSources)
            {
                // RewindBox: a handle made only of values read from memory and constants.
                if (!IsHandleFromMemory(bindlessHandle))
                {
                    return false;
                }
            }
            else if (bindlessHandle.AsgOp is PhiNode phi)
            {
''')
    once(elimination, '''        private static bool TryConvertBindless(BasicBlock block, ResourceManager resourceManager, IGpuAccessor gpuAccessor, TextureOperation texOp)
''', '''        private static bool TryConvertBindless(BasicBlock block, ResourceManager resourceManager, IGpuAccessor gpuAccessor, TextureOperation texOp, bool extendedSources)
''')
    once(elimination, '''                    bindlessHandle = shuffleOp.GetSource(0);
                }

                bindlessHandle = Utils.FindLastOperation(bindlessHandle, block);
''', '''                    bindlessHandle = shuffleOp.GetSource(0);
                }

                if (extendedSources)
                {
                    // RewindBox: a handle spilled to local memory and reloaded is the value stored there.
                    bindlessHandle = GetSpilledHandleSource(bindlessHandle, block);
                }

                bindlessHandle = Utils.FindLastOperation(bindlessHandle, block);
''')
    once(elimination, '''                if (!TryGetOperation(bindlessHandle.AsgOp, out Operation handleCombineOp))
''', '''                if (!TryGetOperation(bindlessHandle.AsgOp, extendedSources, out Operation handleCombineOp))
''')
    once(elimination, '''                Operand src0 = Utils.FindLastOperation(texOp.GetSource(0), block);

                if (src0.Type == OperandType.ConstantBuffer)
''', '''                Operand src0 = texOp.GetSource(0);

                if (extendedSources)
                {
                    // RewindBox: as above, for an image handle.
                    src0 = GetSpilledHandleSource(src0, block);
                }

                src0 = Utils.FindLastOperation(src0, block);

                if (src0.Type == OperandType.ConstantBuffer)
''')
    once(elimination, '''        private static bool TryGetOperation(INode asgOp, out Operation outOperation)
        {
            if (asgOp is PhiNode phi)
            {
                // If we have a phi, let's check if all inputs are effectively the same value.
                // If so, we can "see through" the phi and pick any of the inputs (since they are all the same).

''', '''        private static bool TryGetOperation(INode asgOp, bool extendedSources, out Operation outOperation)
        {
            if (asgOp is PhiNode phi)
            {
                // If we have a phi, let's check if all inputs are effectively the same value.
                // If so, we can "see through" the phi and pick any of the inputs (since they are all the same).

                if (extendedSources)
                {
                    // RewindBox: inputs that are phis themselves (nested branches, loops) are followed
                    // to their other inputs, which must all be the same value.
                    Operand firstLeaf = null;

                    if (!AreAllPhiLeavesSame(phi, ref firstLeaf, new HashSet<PhiNode>()) ||
                        firstLeaf?.AsgOp is not Operation leafOperation)
                    {
                        outOperation = null;

                        return false;
                    }

                    outOperation = leafOperation;

                    return true;
                }

''')
    once(host_cache, '        private const uint CodeGenVersion = 7353 + 0x5242_0001; // RewindBox: adapt_bindless',
         '        private const uint CodeGenVersion = 7353 + 0x5242_0002; // RewindBox: adapt_bindless, adapt_bindless_sources')
    return [elimination, host_cache]
