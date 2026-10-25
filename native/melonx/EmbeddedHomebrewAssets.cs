using System.IO;
using LibHac.Fs;
using LibHac.Tools.Ro;

namespace Ryujinx.HLE.Loaders.Executables;

internal static class EmbeddedHomebrewAssets
{
    // ASET is optional. alpha.129's OpenNroAssetSection dereferences a missing
    // AssetHeader; a plain executable must never call that path.
    internal static IStorage Open(Nro executable, NroAssetType type, out long size)
    {
        size = 0;
        if (executable.AssetHeader == null) return null;
        IStorage storage = executable.OpenNroAssetSection(type, false);
        if (storage == null) throw new InvalidDataException("The NRO asset section could not be opened.");
        try
        {
            storage.GetSize(out size).ThrowIfFailure();
        }
        catch { storage.Dispose(); throw; }
        if (size > 0) return storage;
        storage.Dispose();
        return null;
    }
}
