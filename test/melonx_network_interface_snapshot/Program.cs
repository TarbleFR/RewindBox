// Gate fixture of adapt_network_interface_snapshot: the production NetworkHelpers.cs of each variant next to the two nifm
// call sites as IGeneralService makes them (GetInternetConnectionStatus: is the network available; GetLocalInterface: is
// it available, then NetworkHelpers.GetLocalInterface of the configured interface, "0"). Counts the first-chance
// exceptions and the answers, with /etc/resolv.conf hidden (LD_PRELOAD shim, as in the iOS sandbox) or present.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.NetworkInformation;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Common.Utilities;

static class Program
{
    static long _exceptions, _fileNotFound;

    // IGeneralService's own call (the variant's text: the runtime's in the control, NetworkHelpers' in the candidate).
    static bool Available() =>
#if CANDIDATE
        NetworkHelpers.GetIsNetworkAvailable();
#else
        NetworkInterface.GetIsNetworkAvailable();
#endif

    // IGeneralService.GetLocalInterface without its per-object cache (which keeps only an answer that is not "none").
    static string LocalInterface()
    {
        if (!Available()) return "unavailable";
        (IPInterfaceProperties properties, UnicastIPAddressInformation address) = NetworkHelpers.GetLocalInterface("0");
        return properties == null || address == null ? "none" : address.Address + "/" + properties.GatewayAddresses.Count + "/" + properties.DnsAddresses.Count;
    }

    static int Main(string[] args)
    {
        string variant = args[0];
        AppDomain.CurrentDomain.FirstChanceException += (_, e) =>
        {
            Interlocked.Increment(ref _exceptions);
            if (e.Exception is FileNotFoundException) Interlocked.Increment(ref _fileNotFound);
        };
        bool resolverPresent = File.Exists("/etc/resolv.conf");

        // A game going online: for 6 s, every 100 ms, a status request and an address request.
        List<string> answers = new();
        long start = Environment.TickCount64;
        for (int i = 0; i < 60; i++)
        {
            answers.Add((Available() ? "up" : "down") + "|" + LocalInterface());
            Thread.Sleep(100);
        }
        long elapsed = Environment.TickCount64 - start;
        long exceptions = Interlocked.Read(ref _exceptions), fileNotFound = Interlocked.Read(ref _fileNotFound);

        // Eight threads at once: the same answers, no exception of their own.
        long beforeParallel = Interlocked.Read(ref _exceptions);
        string[] parallel = new string[8 * 50];
        Parallel.For(0, 8, lane =>
        {
            for (int i = 0; i < 50; i++) parallel[lane * 50 + i] = (Available() ? "up" : "down") + "|" + LocalInterface();
        });
        long parallelExceptions = Interlocked.Read(ref _exceptions) - beforeParallel;

        // The runtime's own answer at the same moment.
        bool runtime = NetworkInterface.GetIsNetworkAvailable();
        string[] names = NetworkInterface.GetAllNetworkInterfaces().Select(n => n.Name + ":" + n.NetworkInterfaceType + ":" + n.OperationalStatus).ToArray();
        long enumerations = -1;
        bool sameSnapshot = false, refreshed = false;
#if CANDIDATE
        enumerations = NetworkHelpers.Enumerations;
        NetworkInterface[] first = NetworkHelpers.GetAllNetworkInterfaces(), second = NetworkHelpers.GetAllNetworkInterfaces();
        sameSnapshot = ReferenceEquals(first, second);
        Thread.Sleep((int)NetworkHelpers.SnapshotMilliseconds + 100);
        refreshed = !ReferenceEquals(first, NetworkHelpers.GetAllNetworkInterfaces()) && NetworkHelpers.GetIsNetworkAvailable() == runtime;
#endif
        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["variant"] = variant, ["resolverPresent"] = resolverPresent, ["calls"] = answers.Count, ["elapsedMs"] = elapsed,
            ["exceptions"] = exceptions, ["fileNotFound"] = fileNotFound, ["parallelExceptions"] = parallelExceptions,
            ["answers"] = answers.Distinct().ToArray(), ["parallelAnswers"] = parallel.Distinct().ToArray(), ["runtimeAvailable"] = runtime,
            ["interfaces"] = names, ["enumerations"] = enumerations, ["sameSnapshot"] = sameSnapshot, ["refreshed"] = refreshed,
        }));
        return 0;
    }
}
