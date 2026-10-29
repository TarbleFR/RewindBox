using System;
using System.Buffers;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using Ryujinx.Cpu.LightningJit;
using Ryujinx.Cpu.LightningJit.Arm64;
using Ryujinx.Cpu.LightningJit.Graph;

sealed class Node : IBlock
{
    public int Index { get; }
    public List<IBlock> Predecessors = new();
    public List<IBlock> Successors = new();
    public RegisterUse Use;
    public bool Store, Load;
    public bool FailUse, FailEdge;
    public static long EdgeReads;
    public int PredecessorsCount => Predecessors.Count;
    public int SuccessorsCount => Successors.Count;
    public Node(int index) { Index = index; }
    public IBlock GetPredecessor(int index) { if (FailEdge) throw new InvalidOperationException(); EdgeReads++; return Predecessors[index]; }
    public IBlock GetSuccessor(int index) { if (FailEdge) throw new InvalidOperationException(); EdgeReads++; return Successors[index]; }
    public RegisterUse ComputeUseMasks() { if (FailUse) throw new InvalidOperationException(); return Use; }
    public bool EndsWithContextLoad() => Load;
    public bool EndsWithContextStore() => Store;
}

sealed class Graph : IBlockList
{
    public readonly Node[] Nodes;
    public int Count => Nodes.Length;
    public IBlock this[int index] => Nodes[index];
    public Graph(int count) { Nodes = Enumerable.Range(0, count).Select(index => new Node(index)).ToArray(); }
    public void Edge(int from, int to) { Nodes[from].Successors.Add(Nodes[to]); Nodes[to].Predecessors.Add(Nodes[from]); }
}

sealed class RealGraph : IBlockList
{
    public readonly Block[] Blocks;
    public int Count => Blocks.Length;
    public IBlock this[int index] => Blocks[index];
    public RealGraph(Block[] blocks) { Blocks = blocks; }
    public void Edge(int from, int to) { Blocks[from].AddSuccessor(Blocks[to]); Blocks[to].AddPredecessor(Blocks[from]); }
}

sealed class SpyPool<T> : ArrayPool<T>
{
    public static new readonly SpyPool<T> Shared = new();
    public static int Rentals, Returns;
    public static bool FailRent;
    public static void Reset() { Rentals = Returns = 0; FailRent = false; }
    public override T[] Rent(int length) { if (FailRent) throw new InvalidOperationException(); Rentals++; return ArrayPool<T>.Shared.Rent(length); }
    public override void Return(T[] array, bool clearArray = false) { Returns++; ArrayPool<T>.Shared.Return(array, clearArray); }
}

static class Program
{
    static int _cases;
    static void Require(bool condition, string message)
    {
        if (!condition) throw new Exception($"Graph {_cases}: {message}");
    }
    static uint Bits(Random random) => (uint)random.NextInt64(1L << 32);
    static RegisterUse Use(Random random) => new(Bits(random), Bits(random), Bits(random), Bits(random), Bits(random), Bits(random));
    static void Compare(IBlockList blocks)
    {
        var (beforeInputs, beforeOutputs) = BaselineDataFlow.GetGlobalUses(blocks);
        var (afterInputs, afterOutputs) = DataFlow.GetGlobalUses(blocks);
        Require(beforeInputs.SequenceEqual(afterInputs), "input masks differ");
        Require(beforeOutputs.SequenceEqual(afterOutputs), "output masks differ");
        _cases++;
    }
    static Graph RandomGraph(Random random, int count)
    {
        Graph graph = new(count);
        for (int index = 0; index < count; index++)
        {
            Node node = graph.Nodes[index];
            node.Use = Use(random);
            node.Store = random.Next(4) == 0;
            node.Load = random.Next(4) == 0;
            for (int edge = random.Next(5); edge > 0; edge--) graph.Edge(index, random.Next(count));
        }
        return graph;
    }
    static RealGraph RandomRealGraph(Random random, int count)
    {
        List<Block> blocks = new();
        for (int index = 0; index < count; index++)
        {
            List<InstInfo> instructions = new();
            for (int instruction = random.Next(1, 8); instruction > 0; instruction--)
                instructions.Add(new(0x91000400u, InstName.AddAddsubImm, InstFlags.None, AddressForm.None, Use(random)));
            if (random.Next(4) == 0) instructions.Add(new(0x94000000u, InstName.Bl, InstFlags.None, AddressForm.None, Use(random)));
            else if (random.Next(4) == 0) instructions.Add(new(0xd4000001u, InstName.Svc, InstFlags.None, AddressForm.None, Use(random)));
            Block block = new((ulong)index * 256, (ulong)index * 256 + (ulong)instructions.Count * 4,
                              instructions, true, random.Next(5) == 0, random.Next(4) == 0);
            block.Number(index);
            blocks.Add(block);
        }
        RealGraph graph = new(blocks.ToArray());
        for (int index = 0; index < count; index++)
            for (int edge = random.Next(4); edge > 0; edge--) graph.Edge(index, random.Next(count));
        return graph;
    }
    static Graph Chain(int count, bool cycle)
    {
        Graph graph = new(count);
        for (int index = count - 1; index > 0; index--) graph.Edge(index, index - 1);
        if (cycle) graph.Edge(0, count - 1);
        graph.Nodes[^1].Use = new(0, 1u << 31, 0, 1u << 31, 0, 1u << 31);
        return graph;
    }
    static void FaultChecks()
    {
        foreach (string failure in new[] { "intRent", "byteRent", "use", "edge" })
        {
            Graph graph = Chain(129, true);
            SpyPool<int>.Reset(); SpyPool<byte>.Reset();
            SpyPool<int>.FailRent = failure == "intRent";
            SpyPool<byte>.FailRent = failure == "byteRent";
            graph.Nodes[64].FailUse = failure == "use";
            graph.Nodes[64].FailEdge = failure == "edge";
            bool failed = false;
            try { PoolProbeDataFlow.GetGlobalUses(graph); }
            catch (InvalidOperationException) { failed = true; }
            Require(failed, $"{failure}: exception is preserved");
            Require(SpyPool<int>.Rentals == SpyPool<int>.Returns && SpyPool<byte>.Rentals == SpyPool<byte>.Returns,
                    $"{failure}: all successful scratch rentals returned");
            // Dirty pooled queue storage from an interrupted iteration must not
            // suppress a block in the next translation.
            Compare(Chain(129, true));
        }
    }
    static (long edges, long bytes, double ms) Measure(Func<IBlockList, (RegisterMask[], RegisterMask[])> solve, Graph graph)
    {
        GC.Collect();
        Node.EdgeReads = 0;
        long bytes = GC.GetAllocatedBytesForCurrentThread();
        Stopwatch watch = Stopwatch.StartNew();
        solve(graph);
        watch.Stop();
        return (Node.EdgeReads, GC.GetAllocatedBytesForCurrentThread() - bytes, watch.Elapsed.TotalMilliseconds);
    }
    static void Main()
    {
        Random random = new(588592);
        Compare(new Graph(0));
        for (int iteration = 0; iteration < 20000; iteration++)
            Compare(RandomGraph(random, random.Next(1, iteration % 8 == 0 ? 256 : 64)));
        for (int iteration = 0; iteration < 5000; iteration++) Compare(RandomRealGraph(random, random.Next(1, 128)));
        foreach (int count in new[] { 1, 2, 3, 4, 127, 128, 129, 256, 1000 })
        {
            Compare(Chain(count, false)); Compare(Chain(count, true));
            Graph unreachable = Chain(count, true);
            unreachable.Nodes[^1].Use = default;
            Compare(unreachable);
        }
        // Context cuts before/after the first ordinary predecessor, including
        // entry block with a back edge and every combination of load/store cuts.
        for (int pattern = 0; pattern < 256; pattern++)
        {
            Graph graph = Chain(4, true);
            graph.Edge(0, 2); graph.Edge(1, 2); graph.Edge(2, 2);
            for (int index = 0; index < 4; index++)
            {
                graph.Nodes[index].Store = (pattern & (1 << (index * 2))) != 0;
                graph.Nodes[index].Load = (pattern & (2 << (index * 2))) != 0;
                graph.Nodes[index].Use = Use(random);
            }
            Compare(graph);
        }
        FaultChecks();
        Graph adverse = Chain(1000, true);
        BaselineDataFlow.GetGlobalUses(adverse); DataFlow.GetGlobalUses(adverse);
        var before = Measure(BaselineDataFlow.GetGlobalUses, adverse);
        var after = Measure(DataFlow.GetGlobalUses, adverse);
        Require(after.edges < before.edges / 20, "worklist avoids repeated whole-graph scans");
        Require(after.bytes <= before.bytes + 128, "warmed large-unit scratch adds no per-call allocation");
        Graph small = RandomGraph(random, 4);
        var smallBefore = Measure(BaselineDataFlow.GetGlobalUses, small);
        var smallAfter = Measure(DataFlow.GetGlobalUses, small);
        Require(smallAfter.bytes == smallBefore.bytes, "small units use stack scratch with unchanged allocation");
        Graph single = Chain(1, true);
        var singleBefore = Measure(BaselineDataFlow.GetGlobalUses, single);
        var singleAfter = Measure(DataFlow.GetGlobalUses, single);
        Require(singleAfter.bytes < singleBefore.bytes, "single block omits both local scratch arrays");
        Console.WriteLine(JsonSerializer.Serialize(new {
            equivalentGraphs = _cases,
            realBlockGraphs = 5000,
            adverseBlocks = adverse.Count,
            adverseEdgeReadsBefore = before.edges, adverseEdgeReadsAfter = after.edges,
            adverseAllocatedBytesBefore = before.bytes, adverseAllocatedBytesAfter = after.bytes,
            adverseMillisecondsBefore = before.ms, adverseMillisecondsAfter = after.ms,
            smallAllocatedBytesBefore = smallBefore.bytes, smallAllocatedBytesAfter = smallAfter.bytes,
            singleAllocatedBytesBefore = singleBefore.bytes, singleAllocatedBytesAfter = singleAfter.bytes,
            exceptionOwnershipCases = 4,
        }));
    }
}
