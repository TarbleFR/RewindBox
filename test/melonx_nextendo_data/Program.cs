// The Nextendo data lot (adapt_nextendo_data) on the production Ryujinx.HLE and Ryujinx.Horizon assemblies built from the
// final preparation: the host's BCAT folder read, validated and served through the delivery cache IPC services with
// LibHac's results (names, sizes, MD5 digests, content, partial reads, open limits, errors), only to the folder's own
// application and only while an online session carries it; the optional request parts (bcatDirectory, nsa,
// acceptedVersions) accepted or left out without making the session offline; the NSA as the account id; the session's
// journal line passing the version through. The IPC classes are internal and take Span buffers, so they are called
// through visibility-skipping DynamicMethod thunks. Host .NET runtime on Linux, not an iPhone.
using LibHac.Bcat;
using Ryujinx.HLE;
using Ryujinx.Horizon.Common;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

static class Program
{
    static int checks;
    static readonly Dictionary<string, object> report = new();
    const ulong Smash = 0x01006A800016E000UL;
    const BindingFlags Any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;

    static void Check(bool condition, string message)
    {
        checks++;
        if (!condition) throw new Exception("FAILED: " + message);
    }

    delegate Result Enumerate(object self, out int count, Span<DirectoryName> names);
    delegate Result CreateFile(object self, out object service);
    delegate Result CreateDirectory(object self, out object service);
    delegate Result OpenDirectory(object self, DirectoryName name);
    delegate Result ReadDirectory(object self, out int read, Span<DeliveryCacheDirectoryEntry> entries);
    delegate Result CountDirectory(object self, out int count);
    delegate Result OpenFile(object self, DirectoryName directory, FileName file);
    delegate Result ReadFile(object self, long offset, out long read, Span<byte> data);
    delegate Result SizeFile(object self, out long size);
    delegate Result DigestFile(object self, out Digest digest);

    // A static thunk (object self, args...) that casts self to the method's type and calls it, skipping visibility. Out
    // parameters typed object in the thunk receive the method's out value (an interface reference).
    static T Bind<T>(Type type, string name) where T : Delegate
    {
        MethodInfo invoke = typeof(T).GetMethod("Invoke");
        // The source generator adds command handlers of the same name; the service method is the instance one taking the
        // delegate's arguments after self.
        MethodInfo method = type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly)
            .Single(m => m.Name == name && m.GetParameters().Length == invoke.GetParameters().Length - 1);
        Type[] parameters = invoke.GetParameters().Select(p => p.ParameterType).ToArray();
        DynamicMethod thunk = new(name + "Thunk", invoke.ReturnType, parameters, typeof(Program).Module, true);
        ILGenerator il = thunk.GetILGenerator();
        ParameterInfo[] targets = method.GetParameters();
        LocalBuilder[] outs = new LocalBuilder[targets.Length];
        il.Emit(OpCodes.Ldarg_0);
        il.Emit(OpCodes.Castclass, type);
        for (int i = 0; i < targets.Length; i++)
        {
            Type target = targets[i].ParameterType;
            if (target.IsByRef && parameters[i + 1] != target)
            {
                outs[i] = il.DeclareLocal(target.GetElementType());
                il.Emit(OpCodes.Ldloca, outs[i]);
            }
            else
            {
                il.Emit(OpCodes.Ldarg, i + 1);
            }
        }

        il.Emit(OpCodes.Callvirt, method);
        for (int i = 0; i < targets.Length; i++)
        {
            if (outs[i] == null) continue;
            il.Emit(OpCodes.Ldarg, i + 1);
            il.Emit(OpCodes.Ldloc, outs[i]);
            il.Emit(OpCodes.Stind_Ref);
        }

        il.Emit(OpCodes.Ret);
        return (T)thunk.CreateDelegate(typeof(T));
    }

    static DirectoryName Dir(string text)
    {
        DirectoryName name = default;
        Encoding.ASCII.GetBytes(text, name.Value.AsSpan());
        return name;
    }

    static FileName Name(string text)
    {
        FileName name = default;
        Encoding.ASCII.GetBytes(text, name.Value.AsSpan());
        return name;
    }

    static string Text(ReadOnlySpan<byte> bytes)
    {
        int end = bytes.IndexOf((byte)0);
        return Encoding.ASCII.GetString(end < 0 ? bytes : bytes[..end]);
    }

    static string Request(Dictionary<string, object> extra = null)
    {
        Dictionary<string, object> request = new()
        {
            ["nexToken"] = "nx2.fixture-token", ["pid"] = 12345678901L, ["serverAddress"] = "192.0.2.10", ["natAddress"] = "192.0.2.20",
        };
        foreach (KeyValuePair<string, object> pair in extra ?? []) request[pair.Key] = pair.Value;
        return JsonSerializer.Serialize(request);
    }

    public static int Main(string[] args)
    {
        try
        {
            Run(args[0]);
            report["checks"] = checks;
            Console.WriteLine(JsonSerializer.Serialize(report));
            return 0;
        }
        catch (Exception error)
        {
            // Also into a file: the engine's logger may own the console streams.
            File.WriteAllText(Path.Combine(args[0], "failure.txt"), error.ToString());
            Console.Error.WriteLine(error);
            return 1;
        }
    }

    static void Run(string work)
    {
        Assembly horizon = Assembly.Load("Ryujinx.Horizon");
        Type cacheType = horizon.GetType("Ryujinx.Horizon.Bcat.Ipc.EmbeddedDeliveryCache", true);
        Type storageType = horizon.GetType("Ryujinx.Horizon.Bcat.Ipc.EmbeddedDeliveryCacheStorageService", true);
        Type directoryType = horizon.GetType("Ryujinx.Horizon.Bcat.Ipc.EmbeddedDeliveryCacheDirectoryService", true);
        Type fileType = horizon.GetType("Ryujinx.Horizon.Bcat.Ipc.EmbeddedDeliveryCacheFileService", true);
        FieldInfo resolver = cacheType.GetField("ApplicationOfProcess", Any);
        MethodInfo serve = cacheType.GetMethod("Serve", Any);
        MethodInfo forProcess = cacheType.GetMethod("TryCreateForProcess", Any);
        MethodInfo forApplication = cacheType.GetMethod("TryCreateForApplication", Any);
        PropertyInfo served = cacheType.GetProperty("ServedApplication", Any);

        // The host's folder, as Nextendo's zip for Super Smash Bros. Ultimate lays it out, plus entries nn::bcat cannot name.
        string root = Path.Combine(work, "MeloNX", "nextendo", "bcat", "01006a800016e000");
        Dictionary<string, byte[]> files = new()
        {
            ["line_news/nx_line_news_0001"] = Enumerable.Range(0, 70000).Select(i => (byte)(i * 7 + 3)).ToArray(),
            ["popup_news/nx_popup_0001"] = Encoding.UTF8.GetBytes("first popup"),
            ["popup_news/nx_popup_0002"] = Encoding.UTF8.GetBytes("second popup, longer"),
            ["present2/nx_present_0001"] = [],
        };
        foreach (KeyValuePair<string, byte[]> pair in files)
        {
            string path = Path.Combine(root, pair.Key);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllBytes(path, pair.Value);
        }

        File.WriteAllText(Path.Combine(root, "stray.bin"), "top-level file");
        Directory.CreateDirectory(Path.Combine(root, "bad.dir"));
        File.WriteAllText(Path.Combine(root, "bad.dir", "a"), "x");
        File.WriteAllText(Path.Combine(root, "popup_news", "bad-name"), "x");
        File.WriteAllText(Path.Combine(root, "popup_news", "ends."), "x");
        File.WriteAllText(Path.Combine(root, "popup_news", new string('a', 32)), "x");
        Directory.CreateDirectory(Path.Combine(root, "line_news", "nested"));
        string outside = Path.Combine(work, "outside-secret");
        File.WriteAllText(outside, "must never be served");
        File.CreateSymbolicLink(Path.Combine(root, "popup_news", "linked"), outside);
        Directory.CreateSymbolicLink(Path.Combine(root, "linkdir"), Path.GetDirectoryName(outside));

        object[] serveArgs = [root, null];
        int count = (int)serve.Invoke(null, serveArgs);
        Check(count == 4, "the four files nn::bcat can name are served: " + count);
        Check(((string)serveArgs[1])?.Contains("8 entries") == true, "the eight unnameable, nested, stray or linked entries are skipped and counted: " + serveArgs[1]);
        Check((ulong?)served.GetValue(null) == Smash, "the folder's title is the served application");

        foreach ((string path, string why) in new[]
        {
            ("relative/01006a800016e000", "a relative folder"),
            (Path.Combine(work, "missing", "01006a800016e000"), "a missing folder"),
            (Path.Combine(work, "MeloNX"), "a folder not named after a title id"),
            (Path.Combine(work, "MeloNX", "nextendo", "bcat", "0000000000000000"), "title id zero"),
        })
        {
            if (why == "title id zero") Directory.CreateDirectory(path);
            object[] refused = [path, null];
            Check((int)serve.Invoke(null, refused) == -1 && refused[1] != null && served.GetValue(null) == null, "refused: " + why);
        }

        object[] none = [null, null];
        Check((int)serve.Invoke(null, none) == 0 && served.GetValue(null) == null, "no folder: nothing served");

        // IPC over the served folder (the process's application read through the replaced arp lookup).
        serve.Invoke(null, [root, null]);
        Func<ulong, ulong?> smashProcess = pid => pid == 81 ? Smash : pid == 82 ? 0x0100152000022000UL : null;
        resolver.SetValue(null, smashProcess);
        object[] other = [82UL, null];
        Check(!(bool)forProcess.Invoke(null, other) && other[1] == null, "another application's process takes LibHac's path");
        object[] unknown = [83UL, null];
        Check(!(bool)forProcess.Invoke(null, unknown), "a process arp cannot tell takes LibHac's path");
        Check(!(bool)forApplication.Invoke(null, [0x0100152000022000UL, null]), "another application id takes LibHac's path");
        object[] byId = [Smash, null];
        Check((bool)forApplication.Invoke(null, byId) && byId[1]?.GetType() == storageType, "the served application id gets the served storage");
        object[] mine = [81UL, null];
        Check((bool)forProcess.Invoke(null, mine) && mine[1]?.GetType() == storageType, "the folder's own process gets the served storage");
        object storage = mine[1];

        Enumerate enumerate = Bind<Enumerate>(storageType, "EnumerateDeliveryCacheDirectory");
        DirectoryName[] names = new DirectoryName[8];
        Check(enumerate(storage, out int dirs, names).IsSuccess && dirs == 3, "three directories enumerated: " + dirs);
        string[] listed = names.Take(dirs).Select(n => Text(n.Value.AsReadOnlySpan())).ToArray();
        Check(listed.SequenceEqual(["line_news", "popup_news", "present2"]), "directories in name order: " + string.Join(",", listed));
        DirectoryName[] small = new DirectoryName[2];
        Check(enumerate(storage, out int partial, small).IsSuccess && partial == 2, "enumeration stops at the buffer's size");
        report["directories"] = listed;

        CreateDirectory createDirectory = Bind<CreateDirectory>(storageType, "CreateDirectoryService");
        OpenDirectory openDirectory = Bind<OpenDirectory>(directoryType, "Open");
        ReadDirectory readDirectory = Bind<ReadDirectory>(directoryType, "Read");
        CountDirectory countDirectory = Bind<CountDirectory>(directoryType, "GetCount");
        Check(createDirectory(storage, out object directory).IsSuccess && directory.GetType() == directoryType, "a directory service");
        Check(countDirectory(directory, out _) == new Result(122, 7), "GetCount before Open: NotOpen (2122-0007)");
        Check(readDirectory(directory, out _, new DeliveryCacheDirectoryEntry[4]) == new Result(122, 7), "Read before Open: NotOpen");
        Check(openDirectory(directory, Dir("bad.dir")) == new Result(122, 1), "a directory name nn::bcat refuses: InvalidArgument");
        Check(openDirectory(directory, Dir("nothing_here")) == new Result(122, 2), "an absent directory: NotFound");
        Check(openDirectory(directory, Dir("popup_news")).IsSuccess, "the directory opens");
        Check(openDirectory(directory, Dir("popup_news")) == new Result(122, 6), "a second Open: AlreadyOpen");
        Check(countDirectory(directory, out int popupCount).IsSuccess && popupCount == 2, "two files in popup_news: " + popupCount);
        DeliveryCacheDirectoryEntry[] entries = new DeliveryCacheDirectoryEntry[8];
        Check(readDirectory(directory, out int read, entries).IsSuccess && read == 2, "two entries read");
        for (int i = 0; i < read; i++)
        {
            string key = "popup_news/" + Text(entries[i].Name.Value);
            Check(files.ContainsKey(key) && entries[i].Size == files[key].Length, "entry name and size: " + key);
            Check(entries[i].Digest.Value.AsReadOnlySpan().SequenceEqual(MD5.HashData(files[key])), "entry digest is the MD5 of its content: " + key);
        }

        Check(Text(entries[0].Name.Value) == "nx_popup_0001" && Text(entries[1].Name.Value) == "nx_popup_0002", "entries in name order");
        ((IDisposable)directory).Dispose();

        CreateFile createFile = Bind<CreateFile>(storageType, "CreateFileService");
        OpenFile openFile = Bind<OpenFile>(fileType, "Open");
        ReadFile readFile = Bind<ReadFile>(fileType, "Read");
        SizeFile sizeFile = Bind<SizeFile>(fileType, "GetSize");
        DigestFile digestFile = Bind<DigestFile>(fileType, "GetDigest");
        Check(createFile(storage, out object file).IsSuccess && file.GetType() == fileType, "a file service");
        Check(readFile(file, 0, out _, new byte[4]) == new Result(122, 7), "Read before Open: NotOpen");
        Check(sizeFile(file, out _) == new Result(122, 7) && digestFile(file, out _) == new Result(122, 7), "GetSize and GetDigest before Open: NotOpen");
        Check(openFile(file, Dir("line_news"), Name("bad-name")) == new Result(122, 1), "a file name nn::bcat refuses: InvalidArgument");
        Check(openFile(file, Dir("bad.dir"), Name("a")) == new Result(122, 1), "a directory name nn::bcat refuses: InvalidArgument");
        Check(openFile(file, Dir("nothing_here"), Name("x")) == new Result(122, 2), "an absent directory: NotFound");
        Check(openFile(file, Dir("popup_news"), Name("linked")) == new Result(122, 2), "a linked file was never served: NotFound");
        Check(openFile(file, Dir("line_news"), Name("nx_line_news_0001")).IsSuccess, "the file opens");
        Check(openFile(file, Dir("line_news"), Name("nx_line_news_0001")) == new Result(122, 6), "a second Open: AlreadyOpen");
        byte[] expected = files["line_news/nx_line_news_0001"];
        Check(sizeFile(file, out long size).IsSuccess && size == expected.Length, "GetSize: " + size);
        Check(digestFile(file, out Digest digest).IsSuccess && digest.Value.AsReadOnlySpan().SequenceEqual(MD5.HashData(expected)), "GetDigest is the MD5");
        byte[] whole = new byte[expected.Length + 100];
        Check(readFile(file, 0, out long wholeRead, whole).IsSuccess && wholeRead == expected.Length &&
              whole.AsSpan(0, expected.Length).SequenceEqual(expected), "the whole content read, the buffer larger than the file");
        byte[] middle = new byte[1000];
        Check(readFile(file, 40000, out long middleRead, middle).IsSuccess && middleRead == 1000 &&
              middle.AsSpan().SequenceEqual(expected.AsSpan(40000, 1000)), "a read at an offset");
        Check(readFile(file, expected.Length - 10, out long tailRead, middle).IsSuccess && tailRead == 10, "a read crossing the end stops at it");
        Check(readFile(file, expected.Length, out long endRead, middle).IsSuccess && endRead == 0, "a read at the end reads nothing");
        Check(readFile(file, expected.Length + 1, out _, middle) == new Result(2, 3005), "an offset past the end: OutOfRange (2002-3005)");
        Check(readFile(file, -1, out _, middle) == new Result(2, 3005), "a negative offset: OutOfRange");
        Check(readFile(file, 5, out long emptyRead, Span<byte>.Empty).IsSuccess && emptyRead == 0, "an empty buffer reads nothing");
        ((IDisposable)file).Dispose();

        Check(createFile(storage, out object empty).IsSuccess && openFile(empty, Dir("present2"), Name("nx_present_0001")).IsSuccess &&
              sizeFile(empty, out long emptySize).IsSuccess && emptySize == 0 && readFile(empty, 0, out long none0, new byte[8]).IsSuccess && none0 == 0,
              "an empty file is served");
        ((IDisposable)empty).Dispose();

        List<object> open = [];
        for (int i = 0; i < 8; i++)
        {
            Check(createFile(storage, out object service).IsSuccess, "file service " + (i + 1) + " of eight");
            open.Add(service);
        }

        Check(createFile(storage, out _) == new Result(122, 9), "a ninth file service: ServiceOpenLimitReached");
        ((IDisposable)open[0]).Dispose();
        Check(createFile(storage, out object again).IsSuccess, "a closed service frees its place");
        ((IDisposable)again).Dispose();
        foreach (object service in open.Skip(1)) ((IDisposable)service).Dispose();

        // The online request's optional parts, through EmbeddedOnline (the production native file).
        string served1 = root;
        Check(EmbeddedOnline.Configure(Request(new() { ["bcatDirectory"] = served1, ["nsa"] = "0a1b2c3d4e5f6071", ["acceptedVersions"] = new[] { "13.0.5" } })),
              "a request with the three parts is online");
        serve.Invoke(null, [null, null]);
        Check(served.GetValue(null) == null, "nothing served before the session begins");
        EmbeddedOnline.BeginSession(true);
        Check((ulong?)served.GetValue(null) == Smash, "the session that begins serves its BCAT folder");
        Check(EmbeddedOnline.AccountId(0xcafe) == 0x0a1b2c3d4e5f6071L, "the NSA is the account id the game reads");
        Check(EmbeddedOnline.NoteVersion("01006a800016e000", "13.0.5") == "13.0.5" && EmbeddedOnline.NoteVersion("01006a800016e000", "13.0.5") == "13.0.5",
              "the journal line passes the version through (and is written once)");
        EmbeddedOnline.BeginSession(false);
        Check((ulong?)served.GetValue(null) == Smash, "a program the game starts keeps the session's BCAT data");
        EmbeddedOnline.Clear();
        Check(served.GetValue(null) == null && !EmbeddedOnline.Enabled, "back offline: nothing served");
        Check(EmbeddedOnline.NoteVersion("01006a800016e000", "1.0.0") == "1.0.0", "offline, the version passes through");

        Check(EmbeddedOnline.Configure(Request()), "a request without the parts is online");
        EmbeddedOnline.BeginSession(true);
        Check(served.GetValue(null) == null && EmbeddedOnline.AccountId(0xcafe) == 12345678901L, "without the parts: no BCAT data, the PID as account id");

        Check(!EmbeddedOnline.Configure("{}"), "an empty request is offline");
        EmbeddedOnline.BeginSession(true);
        Check(served.GetValue(null) == null && EmbeddedOnline.AccountId(0xcafe) == 0xcafe, "offline: no BCAT data, the engine's own account id");

        foreach ((object value, string why) in new (object, string)[]
        {
            ("relative/01006a800016e000", "a relative bcatDirectory"),
            (Path.Combine(work, "MeloNX", "nextendo", "bcat", "01006A800016E000"), "an upper-case title folder"),
            (Path.Combine(work, "MeloNX", "nextendo", "bcat", "..", "bcat", "01006a800016e000"), "a '..' segment"),
            (Path.Combine(work, "MeloNX"), "a folder not named after a title"),
            (42, "a number"),
        })
        {
            Check(EmbeddedOnline.Configure(Request(new() { ["bcatDirectory"] = value })), "malformed bcatDirectory leaves the request online: " + why);
            EmbeddedOnline.BeginSession(true);
            Check(served.GetValue(null) == null && EmbeddedOnline.Enabled, "malformed bcatDirectory is left out: " + why);
        }

        foreach ((object value, string why) in new (object, string)[]
        {
            ("0A1B2C3D4E5F6071", "upper case"), ("0a1b2c3d4e5f607", "15 digits"), ("0000000000000000", "zero"), ("0a1b2c3d4e5f607g", "not hex"), (123, "a number"),
        })
        {
            Check(EmbeddedOnline.Configure(Request(new() { ["nsa"] = value })), "malformed nsa leaves the request online: " + why);
            EmbeddedOnline.BeginSession(true);
            Check(EmbeddedOnline.AccountId(0xcafe) == 12345678901L, "malformed nsa is left out, the PID stays: " + why);
        }

        foreach ((object value, string why) in new (object, string)[]
        {
            (Enumerable.Range(0, 17).Select(i => "1." + i).ToArray(), "17 versions"), (new[] { new string('9', 33) }, "a 33-character version"),
            (new object[] { 13 }, "a number"), (new[] { "13.0 .5" }, "a space"), ("13.0.5", "a string, not an array"),
        })
        {
            Check(EmbeddedOnline.Configure(Request(new() { ["acceptedVersions"] = value })), "malformed acceptedVersions leaves the request online: " + why);
            EmbeddedOnline.BeginSession(true);
            Check(EmbeddedOnline.Enabled && EmbeddedOnline.NoteVersion("01006a800016e000", "13.0.5") == "13.0.5", "malformed acceptedVersions is left out: " + why);
        }

        Check(EmbeddedOnline.Configure(Request(new() { ["acceptedVersions"] = Enumerable.Range(0, 16).Select(i => "1." + i).ToArray() })),
              "sixteen versions are accepted");
        EmbeddedOnline.Clear();
        report["servedFiles"] = count;
        report["digest"] = "md5";
    }
}
