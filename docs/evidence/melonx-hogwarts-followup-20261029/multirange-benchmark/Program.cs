using System;
using System.Diagnostics;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Collections.Generic;
static class Program {
    static long Sink;
    static readonly (string name, ulong offset, ulong size, int iterations)[] Scenarios = {
        ("single-first",16,32,500000), ("single-middle",256UL*4096+16,32,100000),
        ("single-last",511UL*4096+16,32,100000), ("two",4080,32,300000),
        ("whole",0,512UL*4096,10000), ("middle-16",247UL*4096+16,16UL*4096,20000),
        ("middle-half",247UL*4096+16,256UL*4096,10000)
    };
    static readonly ControlRange.MultiRange ControlInput = new(Enumerable.Range(0, 512).Select(i => new ControlRange.MemoryRange((ulong)i * 0x2000, 4096)).ToArray());
    static readonly SpanRange.MultiRange SpanInput = new(Enumerable.Range(0, 512).Select(i => new SpanRange.MemoryRange((ulong)i * 0x2000, 4096)).ToArray());
    static readonly ArrayRange.MultiRange ArrayInput = new(Enumerable.Range(0, 512).Select(i => new ArrayRange.MemoryRange((ulong)i * 0x2000, 4096)).ToArray());
    static readonly TwoPassRange.MultiRange TwoPassInput = new(Enumerable.Range(0, 512).Select(i => new TwoPassRange.MemoryRange((ulong)i * 0x2000, 4096)).ToArray());
    static void Run(string variant, int scenario, int iterations) {
        switch(variant) {
            case "Control": Sink += RunControl(scenario, iterations); break;
            case "Span": Sink += RunSpan(scenario, iterations); break;
            case "Array": Sink += RunArray(scenario, iterations); break;
            case "TwoPass": Sink += RunTwoPass(scenario, iterations); break;
        }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static long RunControl(int scenario, int iterations)
    {
        var input = ControlInput;
        var test = Scenarios[scenario];
        long sink = 0;
        for (int i = 0; i < iterations; i++)
        {
            var value = input.Slice(test.offset, test.size);
            sink += value.Count;
            if (value.Count > 0) sink += (long)value.GetSubRange(0).Address;
        }
        return sink;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static long RunSpan(int scenario, int iterations)
    {
        var input = SpanInput;
        var test = Scenarios[scenario];
        long sink = 0;
        for (int i = 0; i < iterations; i++)
        {
            var value = input.Slice(test.offset, test.size);
            sink += value.Count;
            if (value.Count > 0) sink += (long)value.GetSubRange(0).Address;
        }
        return sink;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static long RunArray(int scenario, int iterations)
    {
        var input = ArrayInput;
        var test = Scenarios[scenario];
        long sink = 0;
        for (int i = 0; i < iterations; i++)
        {
            var value = input.Slice(test.offset, test.size);
            sink += value.Count;
            if (value.Count > 0) sink += (long)value.GetSubRange(0).Address;
        }
        return sink;
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static long RunTwoPass(int scenario, int iterations)
    {
        var input = TwoPassInput;
        var test = Scenarios[scenario];
        long sink = 0;
        for (int i = 0; i < iterations; i++)
        {
            var value = input.Slice(test.offset, test.size);
            sink += value.Count;
            if (value.Count > 0) sink += (long)value.GetSubRange(0).Address;
        }
        return sink;
    }

    static void Main() {
        string[] variants={"Control","Span","Array","TwoPass"};
        var data = new List<object>();
        for(int scenario=0;scenario<Scenarios.Length;scenario++) {
            foreach(string variant in variants) Run(variant,scenario,5000);
            for(int repeat=0;repeat<12;repeat++) {
                for(int n=0;n<variants.Length;n++) {
                    string variant=variants[(n+repeat)%variants.Length];
                    long before=GC.GetAllocatedBytesForCurrentThread(); long tick=Stopwatch.GetTimestamp();
                    Run(variant,scenario,Scenarios[scenario].iterations);
                    double ns=Stopwatch.GetElapsedTime(tick).TotalNanoseconds / Scenarios[scenario].iterations;
                    long allocated=GC.GetAllocatedBytesForCurrentThread()-before;
                    data.Add(new{variant,scenario=Scenarios[scenario].name,repeat,ns,bytesPerCall=(double)allocated/Scenarios[scenario].iterations});
                }
            }
        }
        Console.WriteLine(JsonSerializer.Serialize(new{data,sink=Sink}));
    }
}
