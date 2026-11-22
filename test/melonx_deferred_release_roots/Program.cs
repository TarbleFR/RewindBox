// melonx_deferred_release_roots_test.py: what the action left to the loading thread keeps reachable after a close.
using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Ryujinx.Graphics.Vulkan;

static class Program
{
    [MethodImpl(MethodImplOptions.NoInlining)]
    static (WeakReference renderer, WeakReference session) Close(List<string> calls, PipelineCacheManager manager)
    {
        Session session = new();
        VulkanRenderer renderer = new(calls, manager, session);
        renderer.DisposeTail();
        return (new WeakReference(renderer), new WeakReference(session));
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static void EndLoads(List<PipelineCacheManager> loading)
    {
        foreach (PipelineCacheManager manager in loading) { manager.Deferred(); manager.Deferred = null; }
    }

    static void Collect()
    {
        for (int pass = 0; pass < 3; pass++)
        {
            GC.Collect(GC.MaxGeneration, GCCollectionMode.Forced, blocking: true, compacting: true);
            GC.WaitForPendingFinalizers();
        }
    }

    static int Main(string[] args)
    {
        // Eleven sessions closed while the load of each still runs: the loading threads keep their actions.
        List<string> calls = new();
        List<PipelineCacheManager> loading = new();
        List<(WeakReference renderer, WeakReference session)> closed = new();
        for (int index = 0; index < 11; index++)
        {
            PipelineCacheManager manager = new();
            loading.Add(manager);
            closed.Add(Close(calls, manager));
        }
        Collect();
        int renderersAlive = 0, sessionsAlive = 0;
        foreach (var item in closed) { if (item.renderer.IsAlive) renderersAlive++; if (item.session.IsAlive) sessionsAlive++; }
        int callsBeforeLoadEnd = calls.Count;

        // The loads return: each loading thread runs its action, once.
        EndLoads(loading);
        string[] deferredCalls = calls.ToArray();
        Collect();
        int sessionsAliveAfterLoads = 0;
        foreach (var item in closed) { if (item.session.IsAlive) sessionsAliveAfterLoads++; }

        // No load running: the release runs at once, on the closing thread.
        calls.Clear();
        PipelineCacheManager idle = new() { Loading = false };
        Close(calls, idle);
        GC.KeepAlive(loading);
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            variant = args[0], closed = closed.Count, renderersAlive, sessionsAlive, callsBeforeLoadEnd, deferredCalls,
            sessionsAliveAfterLoads, immediateCalls = calls.ToArray(), immediateDeferred = idle.Deferred != null,
        }));
        return 0;
    }
}
