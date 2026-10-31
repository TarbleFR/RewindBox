using System;
namespace Ryujinx.Common;
public static class EmbeddedLaunchDiagnostics
{
    public static Action PerformanceObserver;
    public static void BeginPerformance(long generation) { }
    public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0) { }
}
