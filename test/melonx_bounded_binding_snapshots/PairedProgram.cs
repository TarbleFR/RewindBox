extern alias Control;
extern alias Candidate;

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json;

static class PairedProgram
{
    static void Main()
    {
        List<object> cases = new();
        for (int kind = 0; kind < 3; kind++)
        {
            foreach (int length in new[] { 0, 1, 2, 8, 256, 4096, 4097 })
            {
                var control = Control::PairedBridge.Create(kind, length);
                var candidate = Candidate::PairedBridge.Create(kind, length);
                int iterations = length >= 256 ? 2000 : 20000;
                double[] controlNs = new double[12], candidateNs = new double[12];
                long[] controlBytes = new long[12], candidateBytes = new long[12];
                for (int sample = 0; sample < controlNs.Length; sample++)
                {
                    (long Ticks, long Bytes) oldResult, newResult;
                    if ((sample & 1) == 0)
                    {
                        oldResult = control.Run(iterations); newResult = candidate.Run(iterations);
                    }
                    else
                    {
                        newResult = candidate.Run(iterations); oldResult = control.Run(iterations);
                    }
                    controlNs[sample] = oldResult.Ticks * (1e9 / Stopwatch.Frequency) / iterations;
                    candidateNs[sample] = newResult.Ticks * (1e9 / Stopwatch.Frequency) / iterations;
                    controlBytes[sample] = oldResult.Bytes;
                    candidateBytes[sample] = newResult.Bytes;
                }
                control.Dispose(); candidate.Dispose();
                cases.Add(new { kind, length, iterations, controlNs, candidateNs, controlBytes, candidateBytes });
            }
        }
        Console.WriteLine(JsonSerializer.Serialize(new { sameProcess = true, alternatingOrder = true, cases }));
    }
}
