// Scenarios for the (future) gate of adapt_mirror_pending_pages (not wired yet): the adapted BufferHolder.PendingPages (extracted from the variant's
// real BufferHolder.cs) and the real BufferMirrorRangeList.cs, against the delivered model: a byte[Size] copy of the
// whole buffer and BufferMirrorRangeList.FillData. Each operation follows the production path of BufferHolder:
//   mirrorWrite  SetData while the GPU may read the range: Write, then the range's Add;
//   directWrite  SetData when the range is free (or the fall-through path): Remove, then Release;
//   mirror       TryGetMirror's fill of a staging copy from the buffer's bytes and the pending bytes;
//   upload       UploadPendingData: FindOverlaps, Remove, Gather, one SetData per range (each one releasing pages, as
//                the direct path does), then Return and Release.
// Every result is compared byte for byte; after each operation the pages are exactly the pages the pending ranges
// overlap. Variant "noRelease" (Release does nothing) must break that invariant.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Ryujinx.Graphics.Vulkan;

string variant = args[0];
var report = new Dictionary<string, object> { ["variant"] = variant };
var failures = new List<string>();
long operations = 0, compared = 0, invariantChecks = 0, invariantFailures = 0;
const int PageSize = BufferHolderPages.PendingPages.PageSize;

int CoveredPages(BufferMirrorRangeList ranges)
{
    var pages = new HashSet<int>();
    if (ranges.All() is List<BufferMirrorRangeList.Range> list)
        foreach (var range in list)
            for (int page = range.Offset / PageSize; page <= (range.End - 1) / PageSize; page++) pages.Add(page);
    return pages.Count;
}

void Check(bool condition, string message) { if (!condition && failures.Count < 20) failures.Add(message); }

// One buffer: the reference (full copy) and the candidate (pages) driven by the same operations.
(long PeakPages, int Size) Run(Random random, int size, int steps, Func<Random, int, (int Offset, int Length)> pick, double[] mix)
{
    var full = new byte[size];
    var refRanges = new BufferMirrorRangeList();
    var ranges = new BufferMirrorRangeList();
    var pages = new BufferHolderPages.PendingPages(size);
    var baseData = new byte[size];
    random.NextBytes(baseData);
    long peak = 0;

    for (int step = 0; step < steps; step++)
    {
        operations++;
        var (offset, length) = pick(random, size);
        double roll = random.NextDouble();
        if (roll < mix[0])
        {
            var data = new byte[length];
            random.NextBytes(data);
            data.CopyTo(full.AsSpan(offset));
            refRanges.Add(offset, length);
            pages.Write(offset, data);
            ranges.Add(offset, length);
        }
        else if (roll < mix[1])
        {
            refRanges.Remove(offset, length);
            ranges.Remove(offset, length);
            pages.Release(ranges, offset, length);
            random.NextBytes(baseData.AsSpan(offset, length)); // the direct write changed the buffer's own bytes
        }
        else if (roll < mix[2])
        {
            if (refRanges.OverlapsWith(offset, length) != ranges.OverlapsWith(offset, length)) Check(false, "range lists diverged");
            if (ranges.OverlapsWith(offset, length))
            {
                var expected = new byte[length];
                var actual = new byte[length];
                refRanges.FillData(baseData.AsSpan(offset, length), full.AsSpan(offset, length), offset, expected);
                pages.Fill(ranges, baseData.AsSpan(offset, length), offset, actual);
                compared++;
                Check(expected.AsSpan().SequenceEqual(actual), $"mirror fill differs at {offset}+{length} (size {size})");
            }
        }
        else
        {
            List<BufferMirrorRangeList.Range> refList = refRanges.FindOverlaps(offset, length);
            List<BufferMirrorRangeList.Range> list = ranges.FindOverlaps(offset, length);
            Check((refList == null) == (list == null), "upload ranges diverged");
            if (list != null)
            {
                refRanges.Remove(offset, length);
                ranges.Remove(offset, length);
                byte[] gathered = pages.Gather(list, offset, length);
                int position = 0;
                try
                {
                    foreach (var range in list)
                    {
                        int rangeOffset = Math.Max(offset, range.Offset);
                        int rangeSize = Math.Min(offset + length, range.End) - rangeOffset;
                        // The data the delivered upload sends for this range, then the inner SetData's direct path.
                        compared++;
                        Check(gathered.AsSpan(position, rangeSize).SequenceEqual(full.AsSpan(rangeOffset, rangeSize)),
                              $"upload data differs at {rangeOffset}+{rangeSize}");
                        position += rangeSize;
                        ranges.Remove(rangeOffset, rangeSize);
                        pages.Release(ranges, rangeOffset, rangeSize);
                        full.AsSpan(rangeOffset, rangeSize).CopyTo(baseData.AsSpan(rangeOffset)); // now in the buffer
                    }
                }
                finally
                {
                    System.Buffers.ArrayPool<byte>.Shared.Return(gathered);
                    pages.Release(ranges, offset, length);
                }
            }
        }

        invariantChecks++;
        if (pages.PageCount != CoveredPages(ranges)) { invariantFailures++; Check(variant != "candidate", $"pages {pages.PageCount} != covered {CoveredPages(ranges)}"); }
        peak = Math.Max(peak, (long)pages.PageCount * PageSize);
        if (ranges.Count() != refRanges.Count()) Check(false, "range counts diverged");
    }

    // Everything still pending reads back the same, then the disposal returns every page.
    if (ranges.All() is List<BufferMirrorRangeList.Range> remaining)
        foreach (var range in remaining)
        {
            var actual = new byte[range.Size];
            pages.CopyTo(range.Offset, actual);
            compared++;
            Check(actual.AsSpan().SequenceEqual(full.AsSpan(range.Offset, range.Size)), $"pending bytes differ at {range.Offset}");
        }
    pages.ReleaseAll();
    pages.ReleaseAll(); // idempotent, as Dispose may be
    return (peak, size);
}

var seeds = new Random(7121);
// S1: random sizes, offsets and lengths, every operation mixed (differential).
long randomPeak = 0, randomSizes = 0;
for (int buffer = 0; buffer < 400; buffer++)
{
    var random = new Random(seeds.Next());
    int size = random.Next(1, 6) switch { 1 => random.Next(1, 4096), 2 => random.Next(4096, 70_000), 3 => random.Next(70_000, 600_000), _ => random.Next(600_000, 3_000_000) };
    var (peak, s) = Run(random, size, 300, (r, sz) => { int o = r.Next(sz); int l = Math.Max(1, Math.Min(sz - o, r.Next(3) == 0 ? r.Next(1, 200_000) : r.Next(1, 5000))); return (o, l); },
                        new[] { 0.40, 0.60, 0.85 });
    randomPeak += peak; randomSizes += s;
}
report["random"] = new Dictionary<string, object> { ["buffers"] = 400, ["peakPageBytesSum"] = randomPeak, ["fullCopyBytesSum"] = randomSizes };

// S2: a 32 MiB buffer with small updates (256 B-16 KiB) at random places, the GPU still reading it: what the pages
// hold against the delivered full copy when only part of a buffer is pending. (A ring of per-frame data rewritten in
// place becomes pending almost everywhere: there the pages hold about as much as the copy; see the adapter.)
{
    var random = new Random(9);
    int size = 32 << 20;
    var (peak, _) = Run(random, size, 6000, (r, sz) => { int length = r.Next(256, 16_384); return (r.Next(sz - length), length); },
                        new[] { 0.34, 0.67, 0.90 });
    report["partialUpdates"] = new Dictionary<string, object> { ["bufferBytes"] = size, ["peakPageBytes"] = peak };
}

report["journal"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Records.Take(20).ToList();
report["operations"] = operations; report["compared"] = compared; report["invariantChecks"] = invariantChecks;
report["invariantFailures"] = invariantFailures; report["missingPages"] = BufferHolderPages.PendingPages.MissingPages;
report["pageBytesAfter"] = BufferHolderPages.PendingPages.PageBytes; report["fullBytesAfter"] = BufferHolderPages.PendingPages.FullBytes;
report["failures"] = failures;
Console.WriteLine(JsonSerializer.Serialize(report));
