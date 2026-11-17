using System.Text.Json;
using Ryujinx.Library;

interface IProbeMirror
{
    int Held { get; }
    void Write(int offset, ReadOnlySpan<byte> data);
    void Fill(int offset, Span<byte> mapped, Span<byte> target);
    void Remove(int offset, int size);
    void Reserve(int offset, int size);
    bool Has(int offset, int size);
    void Fallback(int offset, int size);
}

interface IProbeDescriptors
{
    void Call(int start, int size, bool first);
    int State(int index);
}

class Probe
{
    static void Check(bool condition)
    {
        if (!condition) throw new Exception("Differential check failed");
    }

    static void Main()
    {
        var random = new Random(777);
        int checks = 0;
        foreach (int size in new[] { 97, 16385, 84999, 85000, 262144, 1048576 })
        {
            var before = new Before.Mirror(size);
            var after = new After.Mirror(size);
            var mapped = new byte[size];
            var expected = new byte[size];
            random.NextBytes(mapped);
            mapped.CopyTo(expected, 0);
            var input = new byte[20011];
            var left = new byte[34097];
            var right = new byte[left.Length];
            for (int step = 0; step < 3000; step++)
            {
                int length = random.Next(1, Math.Min(size, step % 17 == 0 ? input.Length : 257) + 1);
                int offset = random.Next(0, size - length + 1);
                if (step % 7 == 0)
                {
                    before.Remove(0, size);
                    after.Remove(0, size);
                    mapped.CopyTo(expected, 0);
                }
                random.NextBytes(input.AsSpan(0, length));
                before.Write(offset, input.AsSpan(0, length));
                after.Write(offset, input.AsSpan(0, length));
                input.AsSpan(0, length).CopyTo(expected.AsSpan(offset));
                if (step % 5 == 0)
                {
                    int cut = length / 3;
                    before.Remove(offset, cut);
                    after.Remove(offset, cut);
                    mapped.AsSpan(offset, cut).CopyTo(expected.AsSpan(offset));
                }
                int start = Math.Max(0, offset - random.Next(0, 16000));
                int count = Math.Min(left.Length, size - start);
                before.Fill(start, mapped.AsSpan(start, count), left.AsSpan(0, count));
                after.Fill(start, mapped.AsSpan(start, count), right.AsSpan(0, count));
                Check(left.AsSpan(0, count).SequenceEqual(expected.AsSpan(start, count)));
                Check(right.AsSpan(0, count).SequenceEqual(expected.AsSpan(start, count)));
                checks++;
            }
        }

        var oldMirror = new Before.Mirror(1 << 20);
        var newMirror = new After.Mirror(1 << 20);
        var write = new byte[128];
        for (int i = 0; i < 128; i++)
        {
            oldMirror.Remove(0, 1 << 20);
            newMirror.Remove(0, 1 << 20);
            int offset = (i * 8191) % ((1 << 20) - write.Length);
            oldMirror.Write(offset, write);
            newMirror.Write(offset, write);
        }
        int beforeSparse = oldMirror.Held;
        int afterSparse = newMirror.Held;
        Check(beforeSparse == 1048576 && afterSparse == 16384);
        newMirror.Write(7, write);
        Check(newMirror.Held == oldMirror.Held);
        oldMirror.Reserve(0, 4096);
        newMirror.Reserve(0, 4096);
        newMirror.Reserve(8192, 1024);
        oldMirror.Fallback(32, 128);
        newMirror.Fallback(32, 128);
        Check(oldMirror.Has(0, 4096) && !newMirror.Has(0, 4096) && newMirror.Has(8192, 1024));

        for (int texture = 0; texture <= 2; texture++)
            for (int image = 0; image <= 2; image++)
            {
                int flags = (texture == 1 ? 4 : 0) | (image == 2 ? 8 : 0);
                Check(Before.Descriptors.Classify(texture, image) == flags);
                Check(After.Descriptors.Classify(texture, image) == flags);
            }
        Check(After.Descriptors.Classify(1, 2, 0) == 0);
        Check(After.Descriptors.Classify(1, 2, 3) == 4);

        var oldDescriptors = new Before.Descriptors();
        var newDescriptors = new After.Descriptors();
        for (int call = 0; call < 4096; call++)
        {
            int offset = random.Next(0, 1024), size = random.Next(1, 42);
            oldDescriptors.Call(offset, size, call % 4 != 0);
            newDescriptors.Call(offset, size, call % 4 != 0);
            for (int binding = 0; binding < 128; binding++)
                Check(oldDescriptors.State(binding) == newDescriptors.State(binding));
        }
        // Warm all delegates and JIT call sites before the allocation measurements.
        Measure(oldDescriptors, 10000);
        Measure(newDescriptors, 10000);
        long beforeAlloc = Measure(oldDescriptors, 100000), afterAlloc = Measure(newDescriptors, 100000);
        Check(beforeAlloc > afterAlloc && afterAlloc == 0);

        var owner = new EmbeddedSessionCoordinator();
        long id = owner.Prepare();
        Check(owner.Pause(id, true));
        var changes = new List<bool>();
        Check(owner.Run(id, () => {
            owner.PublishControls(() => {}, changes.Add);
            Check(owner.Pause(id, true) && owner.Pause(id, false) && owner.Pause(id, false));
            Check(owner.Pause(id, true) && owner.Stop(id) && !owner.Pause(id, false));
            owner.WithdrawControls();
            return 0;
        }) == 0);
        Check(changes.SequenceEqual(new[] { true, false, true }));
        Check(!owner.Pause(id, true));
        Console.WriteLine(JsonSerializer.Serialize(new { mirrorComparisons = checks, beforeSparse, afterSparse,
            beforeAllocationBytes = beforeAlloc, afterAllocationBytes = afterAlloc, descriptorCalls = 100000,
            descriptorStateComparisons = 4096 * 128, staleSnapshotRemoved = true, duplicatePauseSuppressed = true }));
    }

    static long Measure(IProbeDescriptors descriptors, int calls)
    {
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < calls; i++) descriptors.Call(i & 1023, 24, true);
        return GC.GetAllocatedBytesForCurrentThread() - before;
    }
}
