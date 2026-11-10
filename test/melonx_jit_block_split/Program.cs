using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using Ryujinx.Cpu.LightningJit;
using Ryujinx.Cpu.LightningJit.Arm64;
using Ryujinx.Cpu.LightningJit.Graph;

static class Program
{
    static int _cases;
    static void Require(bool condition, string message)
    {
        if (!condition) throw new Exception($"Case {_cases}: {message}");
    }
    static List<Block> Clone(List<Block> blocks) => blocks.Select(block =>
        new Block(block.Address, block.EndAddress, new(block.Instructions), block.EndsWithBranch, block.IsTruncated, block.IsLoopEnd)).ToList();
    static void Compare(List<Block> original, List<ulong> targets, bool link = true)
    {
        var before = Clone(original);
        var after = Clone(original);
        Baseline.Split(before, new(targets)); Adapted.Split(after, new(targets));
        Require(before.Count == after.Count, "number of blocks");
        if (link) { Baseline.Link(before); Adapted.Link(after); }
        for (int index = 0; index < before.Count; index++)
        {
            Block b = before[index], a = after[index];
            Require((b.Address, b.EndAddress, b.EndsWithBranch, b.IsTruncated, b.IsLoopEnd, b.Index) ==
                    (a.Address, a.EndAddress, a.EndsWithBranch, a.IsTruncated, a.IsLoopEnd, a.Index), "block flags and interval");
            Require(b.Instructions.SequenceEqual(a.Instructions), "all instruction fields");
            RegisterUse bu = b.ComputeUseMasks(), au = a.ComputeUseMasks();
            Require(bu.Read == au.Read && bu.Write == au.Write, "register use masks");
            Require(b.EndsWithContextLoad() == a.EndsWithContextLoad() && b.EndsWithContextStore() == a.EndsWithContextStore(), "context transfers");
            Require(b.PredecessorsCount == a.PredecessorsCount && b.SuccessorsCount == a.SuccessorsCount, "edge counts");
            for (int edge = 0; edge < b.PredecessorsCount; edge++)
                Require(b.GetPredecessor(edge).Index == a.GetPredecessor(edge).Index, "predecessor edge");
            for (int edge = 0; edge < b.SuccessorsCount; edge++)
                Require(b.GetSuccessor(edge).Index == a.GetSuccessor(edge).Index, "successor edge");
        }
        _cases++;
    }
    static InstInfo Instruction(Random random, InstName name, uint encoding) => new(
        encoding, name, InstFlags.None, AddressForm.None,
        new RegisterUse((uint)random.Next(), (uint)random.Next(), (uint)random.Next(), (uint)random.Next(), (uint)random.Next(), (uint)random.Next()));
    static List<Block> Layout(Random random, int count, out int instructionCount)
    {
        List<Block> blocks = new();
        ulong address = 0x10000;
        instructionCount = 0;
        InstName[] endings = [InstName.BCond, InstName.BUncond, InstName.Cbz, InstName.Tbz, InstName.Bl, InstName.Blr, InstName.Br, InstName.Ret, InstName.Svc];
        for (int block = 0; block < count; block++)
        {
            int length = random.Next(1, 40);
            List<InstInfo> instructions = new();
            for (int index = 0; index < length - 1; index++) instructions.Add(Instruction(random, InstName.AddAddsubImm, 0x91000400));
            InstName last = endings[random.Next(endings.Length)];
            int displacement = random.Next(-2000, 2000);
            uint encoding = last == InstName.BUncond || last == InstName.Bl ? (uint)displacement & 0x3ffffffu :
                            last == InstName.Tbz ? ((uint)displacement & 0x3fffu) << 5 : ((uint)displacement & 0x7ffffu) << 5;
            instructions.Add(Instruction(random, last, encoding));
            blocks.Add(new(address, address + (ulong)length * 4, instructions, last != InstName.Svc,
                           block == count - 1 && random.Next(2) == 0, random.Next(3) == 0));
            address += (ulong)length * 4;
            instructionCount += length;
        }
        return blocks;
    }
    static (long bytes, double ms) Measure(Action<List<Block>, List<ulong>> split, List<Block> input, List<ulong> targets)
    {
        var blocks = Clone(input);
        GC.Collect();
        long before = GC.GetAllocatedBytesForCurrentThread();
        Stopwatch watch = Stopwatch.StartNew();
        split(blocks, targets);
        watch.Stop();
        return (GC.GetAllocatedBytesForCurrentThread() - before, watch.Elapsed.TotalMilliseconds);
    }
    static void Main()
    {
        Random random = new(587591);
        Compare([], []);
        for (int iteration = 0; iteration < 10000; iteration++)
        {
            var blocks = Layout(random, random.Next(1, 80), out int instructions);
            List<ulong> targets = new() { 0, 0, 0x10000, 0x10000, blocks[^1].EndAddress, ulong.MaxValue - 3 };
            for (int target = 0; target < 100; target++)
            {
                ulong address = 0x10000 + (ulong)random.Next(-50, instructions + 50) * 4;
                targets.Add(address);
                if (random.Next(4) == 0) targets.Add(address);
            }
            targets.Sort();
            Compare(blocks, targets);
            if (iteration % 100 == 0)
            {
                // A zero-length, truncated last block (e.g. ending before an unmapped page).
                ulong end = blocks[^1].EndAddress;
                blocks.Add(new(end, end, [], false, true, false));
                Compare(blocks, targets);
                Compare(blocks, []);
                // A synthetic unaligned target or unsorted list preserves the old path.
                var unaligned = new List<ulong>(targets) { blocks[0].Address + 3 };
                unaligned.Sort();
                Compare(blocks, unaligned, link: false);
                targets.Reverse();
                Compare(blocks, targets, link: false);
            }
        }
        // Wrapping ranges and reordered blocks preserve the original general path.
        var wrap = Layout(random, 2, out _);
        Block old = wrap[0];
        wrap[0] = new(ulong.MaxValue - 7, old.EndAddress, old.Instructions, old.EndsWithBranch, old.IsTruncated, old.IsLoopEnd);
        Compare(wrap, [0, 4, 0x10004], link: false);
        wrap = Layout(random, 2, out _);
        wrap.Reverse();
        Compare(wrap, [0x10000, 0x10004, 0x10008], link: false);

        List<InstInfo> longCode = Enumerable.Range(0, 2048).Select(index => Instruction(random, InstName.AddAddsubImm, (uint)index)).ToList();
        List<Block> dense = [new(0x10000, 0x12000, longCode, false, true, false)];
        List<ulong> denseTargets = Enumerable.Range(1, 511).Select(index => 0x10000UL + (ulong)index * 16).ToList();
        Compare(dense, denseTargets);
        // Warm JITs before measuring only the splitting work, excluding fixture construction.
        Baseline.Split(Clone(dense), denseTargets); Adapted.Split(Clone(dense), denseTargets);
        var b = Measure(Baseline.Split, dense, denseTargets);
        var a = Measure(Adapted.Split, dense, denseTargets);
        Require(a.bytes < b.bytes / 10, "dense branch targets no longer repeatedly copy the remaining instructions");
        var external = Layout(random, 512, out _);
        List<ulong> externalTargets = Enumerable.Range(0, 4096).Select(index => (ulong)index * 4).ToList();
        Compare(external, externalTargets);
        var eb = Measure(Baseline.Split, external, externalTargets);
        var ea = Measure(Adapted.Split, external, externalTargets);
        Console.WriteLine(JsonSerializer.Serialize(new {
            equivalentLayouts = _cases,
            denseSplitInstructions = 2048,
            denseSplitTargets = denseTargets.Count,
            denseAllocatedBytesBefore = b.bytes, denseAllocatedBytesAfter = a.bytes,
            denseMillisecondsBefore = b.ms, denseMillisecondsAfter = a.ms,
            externalTargets = externalTargets.Count,
            externalMillisecondsBefore = eb.ms, externalMillisecondsAfter = ea.ms,
        }));
    }
}
