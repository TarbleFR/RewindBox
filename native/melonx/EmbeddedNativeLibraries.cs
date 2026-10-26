using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;

namespace Ryujinx.Common;

// This belongs to the MeloNX NativeAOT image only. No DYLD search path, shared
// MoltenVK or other engine handle is used. The one upstream prebuilt library
// is the standalone MeloNX app's own MoltenVK, shipped privately next to the
// source-built one for an A/B of the Persona flicker; the host selects one per
// process before anything is loaded.
public static class EmbeddedNativeLibraries
{
    private static readonly object Gate = new();
    private static readonly Dictionary<string, nint> Handles = new();
    private static string Root;
    private static int JitMode = -1;
    public static bool UniversalJit { get { lock (Gate) return JitMode == 1; } }
    // 0: RewindBox's source-built Khronos MoltenVK; 1: the standalone MeloNX
    // app's libMoltenVK.dylib. 0 when the host never selects.
    private static readonly string[] MoltenVkFrameworks = { "MeloNXMoltenVK", "MeloNXMoltenVKStandalone" };
    private static int MoltenVkVariant;
    private static string MoltenVkIdentity = "";
    public static string MoltenVk { get { lock (Gate) return MoltenVkFrameworks[MoltenVkVariant] + MoltenVkIdentity; } }

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
            // Name the exact MoltenVK binary in the launch journal.
            using var binary = File.OpenRead(PathFor("libMoltenVK.dylib"));
            MoltenVkIdentity = " sha256:" + Convert.ToHexString(SHA256.HashData(binary)).ToLowerInvariant()[..16];
        }
    }

    public static void SelectMoltenVk(int variant)
    {
        if (variant != 0 && variant != 1) throw new ArgumentOutOfRangeException(nameof(variant));
        lock (Gate)
        {
            if (Root != null && variant != MoltenVkVariant)
                throw new InvalidOperationException("MoltenVK is already loaded for this process.");
            MoltenVkVariant = variant;
            Names["libMoltenVK.dylib"] = MoltenVkFrameworks[variant];
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
