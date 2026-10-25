using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;

namespace Ryujinx.Common;

// This belongs to the MeloNX NativeAOT image only. No DYLD search path, shared
// MoltenVK, other engine handle or upstream prebuilt library is used.
public static class EmbeddedNativeLibraries
{
    private static readonly object Gate = new();
    private static readonly Dictionary<string, nint> Handles = new();
    private static string Root;
    private static int JitMode = -1;
    public static bool UniversalJit { get { lock (Gate) return JitMode == 1; } }

    private static readonly Dictionary<string, string> Names = new()
    {
        ["libMoltenVK.dylib"] = "MeloNXMoltenVK",
        ["SDL3"] = "MeloNXSDL3",
        ["avcodec"] = "MeloNXAvCodec", ["avutil"] = "MeloNXAvUtil",
        ["MeloNXJitSupport"] = "MeloNXJitSupport",
    };

    public static void Configure(string root)
    {
        if (string.IsNullOrWhiteSpace(root) || !Path.IsPathFullyQualified(root))
            throw new ArgumentException("An absolute Frameworks directory is required.");
        root = Path.GetFullPath(root);
        lock (Gate)
        {
            if (Root != null && Root != root) throw new InvalidOperationException("Native root already fixed.");
            foreach (string name in Names.Values)
                if (!File.Exists(Path.Combine(root, name + ".framework", name)))
                    throw new FileNotFoundException("Missing private MeloNX framework: " + name);
            Root = root;
            // Validate dependency closure before bootstrap creates SDL objects.
            // NativeAOT and these handles remain process-owned after shutdown.
            foreach (string name in new[] { "avutil", "avcodec", "SDL3", "libMoltenVK.dylib", "MeloNXJitSupport" })
                Load(name);
        }
    }

    public static void ConfigureJit(int mode)
    {
        if (mode != 0 && mode != 1) throw new ArgumentOutOfRangeException(nameof(mode));
        lock (Gate)
        {
            if (Root == null) throw new InvalidOperationException("Native dependencies unconfigured.");
            if (JitMode != -1 && JitMode != mode)
                throw new InvalidOperationException("The JIT arena's mode cannot change during this process.");
            JitMode = mode;
        }
    }

    public static string PathFor(string name)
    {
        lock (Gate)
        {
            if (Root == null) throw new InvalidOperationException("Native dependencies unconfigured.");
            return Path.Combine(Root, Names[name] + ".framework", Names[name]);
        }
    }

    public static nint Load(string name)
    {
        lock (Gate)
        {
            if (!Handles.TryGetValue(name, out nint handle))
            {
                handle = NativeLibrary.Load(PathFor(name));
                Handles.Add(name, handle);
            }
            return handle;
        }
    }

    public static nint Resolve(string name, Assembly assembly, DllImportSearchPath? searchPath) =>
        Names.ContainsKey(name) ? Load(name) : nint.Zero;
}
