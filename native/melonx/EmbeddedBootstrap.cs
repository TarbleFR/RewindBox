using System;
using System.IO;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace Ryujinx.Library;

partial class Library
{
    private static readonly EmbeddedInitializationState EmbeddedBootstrap = new();

    // This identifies the bootstrap contract, not session/playback readiness.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_bootstrap_abi")]
    public static int EmbeddedBootstrapAbi() => 1;

    // No ownership transfer: the caller retains its UTF-8 buffer for this call.
    // 0=initialized, 1=invalid root, 2=other initialization, 3=failed bootstrap.
    // Initialization is irreversible in this process. A partial failure is
    // quarantined instead of running initialization twice over native handles.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_initialize")]
    public static unsafe int InitializeEmbedded(nint rootUtf8)
    {
        try
        {
            int result = EmbeddedBootstrap.Initialize(
                Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                Marshal.PtrToStringUTF8(rootUtf8), () => _virtualFileSystem != null, root =>
            {
                Directory.CreateDirectory(root);
                InitializeCore(root);
                if (!string.Equals(Ryujinx.Common.Configuration.AppDataManager.BaseDirPath,
                                   root, StringComparison.Ordinal))
                    throw new InvalidOperationException("The engine did not adopt its isolated data root.");
            });
            if (result == 1 || result == 3)
                Console.Error.WriteLine("MeloNX embedded bootstrap: " + EmbeddedBootstrap.LastFailure);
            return result;
        }
        catch (Exception error)
        {
            // No managed exception is allowed to unwind through the C ABI.
            Console.Error.WriteLine("MeloNX embedded ABI: " + error);
            return 3;
        }
    }
}
