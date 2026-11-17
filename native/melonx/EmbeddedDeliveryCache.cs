using LibHac.Bcat;
using Ryujinx.Common.Logging;
using Ryujinx.Horizon.Common;
using Ryujinx.Horizon.Sdk.Arp;
using Ryujinx.Horizon.Sdk.Bcat;
using Ryujinx.Horizon.Sdk.Sf;
using Ryujinx.Horizon.Sdk.Sf.Hipc;
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace Ryujinx.Horizon.Bcat.Ipc
{
    /// <summary>
    /// RewindBox (adapt_nextendo_data): the delivery cache (BCAT data) of the running online session, served from the host's
    /// folder. Nextendo's integration guide (wiki.nextendo.network/integration, "BCAT data", read 17 November 2026): some
    /// titles need their delivery data to show menus or rotations (Super Smash Bros. Ultimate: "otherwise the menu banner
    /// asks to connect to the Internet"); download it as a zip from nextendo.network/api/bcat/&lt;titleId&gt; and serve it
    /// from a writable folder. RewindBox's host downloads and unpacks it to
    /// &lt;data root&gt;/nextendo/bcat/&lt;title id, 16 hex&gt;/&lt;directory&gt;/&lt;file&gt; and names that folder in the online request
    /// (EmbeddedOnline.Configure); EmbeddedOnline hands it here when an online session begins and clears it otherwise.
    ///
    /// The folder is read once at the session's start: its directories and files are listed, sized and digested, then
    /// served read-only to the application whose id the folder names, through the same IPC commands and with the same
    /// results as LibHac's delivery cache services (LibHac 23e402eb, Bcat/Impl/Service): eight open file and eight open
    /// directory services at most per storage, InvalidArgument for a name nn::bcat refuses, AlreadyOpen, NotOpen and
    /// NotFound as there. Limits are LibHac's: 100 directories, 100 files per directory. A file's digest is the MD5 of its
    /// content, the choice of yuzu's HLE BCAT ("the digest is only used to determine if a file is unique compared to others
    /// of the same name"); LibHac stores the digest the downloader recorded and computes none.
    ///
    /// Entries nn::bcat could not name (a directory name outside [0-9A-Za-z_-], a file name outside [0-9A-Za-z_.] or ending
    /// with '.', 32 characters or more), files at the top level, nested directories and links are skipped and counted.
    /// Without a served folder, for another application, or when the process's application cannot be told, every request
    /// takes LibHac's path unchanged.
    /// </summary>
    public static class EmbeddedDeliveryCache
    {
        public const int MaxDirectories = 100; // LibHac DeliveryCacheDirectoryMetaAccessor.MaxEntryCount
        public const int MaxFilesPerDirectory = 100; // LibHac DeliveryCacheFileMetaAccessor.MaxEntryCount
        public const long MaxFolderBytes = 256L * 1024 * 1024;
        public const int NameCapacity = 0x20; // DirectoryName, FileName

        internal sealed class CacheFile
        {
            public FileName Name;
            public string Key;
            public string Path;
            public long Size;
            public Digest Digest;
        }

        internal sealed class CacheDirectory
        {
            public DirectoryName Name;
            public string Key;
            public CacheFile[] Files;
        }

        internal sealed class Cache
        {
            public ulong ApplicationId;
            public CacheDirectory[] Directories;
            public int FileCount;
            public int Skipped;
        }

        private static volatile Cache _cache;
        private static readonly object _arpGate = new();
        private static ArpApi _arp;

        // Tests replace it (the gate's fixture, by reflection): the application id of a client process, or null when it
        // cannot be told.
        internal static Func<ulong, ulong?> ApplicationOfProcess = ProcessApplication;

        /// <summary>The application whose delivery cache is served, or null.</summary>
        public static ulong? ServedApplication => _cache?.ApplicationId;

        /// <summary>Stops serving: offline, or a session without BCAT data.</summary>
        public static void Clear() => _cache = null;

        /// <summary>
        /// Serves the folder for the session that begins (null stops serving). Returns the number of files served, or -1
        /// when the folder is refused (reason set; nothing is served then and LibHac's path stays).
        /// </summary>
        public static int Serve(string directory, out string reason)
        {
            _cache = null;
            reason = null;
            if (directory == null) return 0;
            Cache cache = Load(directory, out reason);
            _cache = cache;
            if (cache == null) return -1;
            if (cache.Skipped > 0) reason = cache.Skipped + " entries nn::bcat cannot name were skipped";
            return cache.FileCount;
        }

        internal static Cache Load(string directory, out string reason)
        {
            reason = null;
            try
            {
                if (!Path.IsPathFullyQualified(directory))
                {
                    reason = "the folder is not a full path";
                    return null;
                }

                DirectoryInfo root = new(Path.TrimEndingDirectorySeparator(Path.GetFullPath(directory)));
                if (!root.Exists || root.LinkTarget != null || (root.Attributes & FileAttributes.ReparsePoint) != 0)
                {
                    reason = "the folder does not exist or is a link";
                    return null;
                }

                string title = root.Name;
                if (title.Length != 16 || !ulong.TryParse(title, System.Globalization.NumberStyles.AllowHexSpecifier, null, out ulong applicationId) ||
                    applicationId == 0)
                {
                    reason = "the folder is not named after a title id";
                    return null;
                }

                string rootPath = root.FullName + Path.DirectorySeparatorChar;
                int skipped = 0, files = 0;
                long bytes = 0;
                List<CacheDirectory> directories = [];
                foreach (FileSystemInfo entry in root.EnumerateFileSystemInfos())
                {
                    if (entry is not DirectoryInfo sub || entry.LinkTarget != null || (entry.Attributes & FileAttributes.ReparsePoint) != 0 ||
                        !TryDirectoryName(entry.Name, out DirectoryName directoryName) || directories.Count >= MaxDirectories)
                    {
                        skipped++;
                        continue;
                    }

                    List<CacheFile> content = [];
                    foreach (FileSystemInfo item in sub.EnumerateFileSystemInfos())
                    {
                        if (item is not FileInfo file || item.LinkTarget != null || (item.Attributes & FileAttributes.ReparsePoint) != 0 ||
                            !TryFileName(item.Name, out FileName fileName) || content.Count >= MaxFilesPerDirectory ||
                            !file.FullName.StartsWith(rootPath, StringComparison.Ordinal))
                        {
                            skipped++;
                            continue;
                        }

                        byte[] data = File.ReadAllBytes(file.FullName);
                        bytes += data.LongLength;
                        if (bytes > MaxFolderBytes)
                        {
                            reason = "the folder holds more than " + (MaxFolderBytes >> 20) + " MiB";
                            return null;
                        }

                        Digest digest = default;
                        MD5.HashData(data).CopyTo(digest.Value.AsSpan());
                        content.Add(new CacheFile { Name = fileName, Key = item.Name, Path = file.FullName, Size = data.LongLength, Digest = digest });
                    }

                    content.Sort((a, b) => string.CompareOrdinal(a.Key, b.Key));
                    files += content.Count;
                    directories.Add(new CacheDirectory { Name = directoryName, Key = entry.Name, Files = content.ToArray() });
                }

                directories.Sort((a, b) => string.CompareOrdinal(a.Key, b.Key));
                return new Cache { ApplicationId = applicationId, Directories = directories.ToArray(), FileCount = files, Skipped = skipped };
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.Security.SecurityException)
            {
                reason = "the folder could not be read (" + error.GetType().Name + ")";
                return null;
            }
        }

        /// <summary>nn::bcat's directory name rule (LibHac DirectoryName.IsValid): 1 to 31 of [0-9A-Za-z_-].</summary>
        internal static bool TryDirectoryName(string text, out DirectoryName name)
        {
            name = default;
            if (string.IsNullOrEmpty(text) || text.Length >= NameCapacity) return false;
            foreach (char c in text)
                if (!(c is >= '0' and <= '9' or >= 'a' and <= 'z' or >= 'A' and <= 'Z' or '_' or '-')) return false;
            Encoding.ASCII.GetBytes(text, name.Value.AsSpan());
            return true;
        }

        /// <summary>nn::bcat's file name rule (LibHac FileName.IsValid): 1 to 31 of [0-9A-Za-z_.], not ending with '.'.</summary>
        internal static bool TryFileName(string text, out FileName name)
        {
            name = default;
            if (string.IsNullOrEmpty(text) || text.Length >= NameCapacity || text[^1] == '.') return false;
            foreach (char c in text)
                if (!(c is >= '0' and <= '9' or >= 'a' and <= 'z' or >= 'A' and <= 'Z' or '_' or '.')) return false;
            Encoding.ASCII.GetBytes(text, name.Value.AsSpan());
            return true;
        }

        internal static string Text(ReadOnlySpan<byte> name)
        {
            int length = name.IndexOf((byte)0);
            return Encoding.ASCII.GetString(length < 0 ? name : name[..length]);
        }

        /// <summary>The served storage for a client process (CreateDeliveryCacheStorageService), when its application is the served one.</summary>
        internal static bool TryCreateForProcess(ulong processId, out IDeliveryCacheStorageService service)
        {
            service = null;
            Cache cache = _cache;
            if (cache == null) return false;
            ulong? application = ApplicationOfProcess(processId);
            if (application != cache.ApplicationId) return false;
            service = new EmbeddedDeliveryCacheStorageService(cache);
            Logger.Info?.Print(LogClass.ServiceBcat, $"Online play: delivery cache of {cache.ApplicationId:x16} served from the host folder ({cache.FileCount} files).");
            return true;
        }

        /// <summary>The served storage for an application id (CreateDeliveryCacheStorageServiceWithApplicationId).</summary>
        internal static bool TryCreateForApplication(ulong applicationId, out IDeliveryCacheStorageService service)
        {
            service = null;
            Cache cache = _cache;
            if (cache == null || cache.ApplicationId != applicationId) return false;
            service = new EmbeddedDeliveryCacheStorageService(cache);
            return true;
        }

        // The application of a process, as LibHac's ServiceCreator asks arp for it (here through Horizon's arp:r, which the
        // loader registers each program with). Null when arp has no answer.
        private static ulong? ProcessApplication(ulong processId)
        {
            lock (_arpGate)
            {
                try
                {
                    _arp ??= new ArpApi(new HeapAllocator());
                    if (_arp.GetApplicationInstanceId(out ulong instance, processId).IsFailure) return null;
                    if (_arp.GetApplicationLaunchProperty(out ApplicationLaunchProperty property, instance).IsFailure) return null;
                    return property.ApplicationId.Id;
                }
                catch (Exception error)
                {
                    Logger.Warning?.Print(LogClass.ServiceBcat, $"Online play: the delivery cache's application could not be read ({error.GetType().Name}).");
                    return null;
                }
            }
        }
    }

    /// <summary>RewindBox (adapt_nextendo_data): IDeliveryCacheStorageService over the served folder (LibHac's semantics).</summary>
    partial class EmbeddedDeliveryCacheStorageService : IDeliveryCacheStorageService
    {
        private const int MaxOpenCount = 8; // LibHac DeliveryCacheStorageService

        private readonly EmbeddedDeliveryCache.Cache _cache;
        private readonly object _gate = new();
        private int _files;
        private int _directories;

        internal EmbeddedDeliveryCacheStorageService(EmbeddedDeliveryCache.Cache cache)
        {
            _cache = cache;
        }

        [CmifCommand(0)]
        public Result CreateFileService(out IDeliveryCacheFileService service)
        {
            lock (_gate)
            {
                service = null;
                if (_files >= MaxOpenCount) return BcatResult.ServiceOpenLimitReached;
                _files++;
                service = new EmbeddedDeliveryCacheFileService(_cache, this);
                return Result.Success;
            }
        }

        [CmifCommand(1)]
        public Result CreateDirectoryService(out IDeliveryCacheDirectoryService service)
        {
            lock (_gate)
            {
                service = null;
                if (_directories >= MaxOpenCount) return BcatResult.ServiceOpenLimitReached;
                _directories++;
                service = new EmbeddedDeliveryCacheDirectoryService(_cache, this);
                return Result.Success;
            }
        }

        [CmifCommand(10)]
        public Result EnumerateDeliveryCacheDirectory(out int count, [Buffer(HipcBufferFlags.Out | HipcBufferFlags.MapAlias)] Span<DirectoryName> directoryNames)
        {
            int i;
            for (i = 0; i < directoryNames.Length && i < _cache.Directories.Length; i++)
            {
                directoryNames[i] = _cache.Directories[i].Name;
            }

            count = i;
            return Result.Success;
        }

        internal void CloseFile()
        {
            lock (_gate) _files--;
        }

        internal void CloseDirectory()
        {
            lock (_gate) _directories--;
        }

        internal static EmbeddedDeliveryCache.CacheDirectory Find(EmbeddedDeliveryCache.Cache cache, in DirectoryName name)
        {
            string key = EmbeddedDeliveryCache.Text(name.Value);
            foreach (EmbeddedDeliveryCache.CacheDirectory directory in cache.Directories)
                if (string.Equals(directory.Key, key, StringComparison.Ordinal)) return directory;
            return null;
        }
    }

    /// <summary>RewindBox (adapt_nextendo_data): IDeliveryCacheDirectoryService over the served folder (LibHac's semantics).</summary>
    partial class EmbeddedDeliveryCacheDirectoryService : IDeliveryCacheDirectoryService, IDisposable
    {
        private readonly EmbeddedDeliveryCache.Cache _cache;
        private readonly EmbeddedDeliveryCacheStorageService _parent;
        private readonly object _gate = new();
        private EmbeddedDeliveryCache.CacheDirectory _directory;
        private int _disposalState;

        internal EmbeddedDeliveryCacheDirectoryService(EmbeddedDeliveryCache.Cache cache, EmbeddedDeliveryCacheStorageService parent)
        {
            _cache = cache;
            _parent = parent;
        }

        [CmifCommand(0)]
        public Result Open(DirectoryName directoryName)
        {
            if (!directoryName.IsValid()) return BcatResult.InvalidArgument;
            lock (_gate)
            {
                if (_directory != null) return BcatResult.AlreadyOpen;
                EmbeddedDeliveryCache.CacheDirectory directory = EmbeddedDeliveryCacheStorageService.Find(_cache, in directoryName);
                if (directory == null) return BcatResult.NotFound;
                _directory = directory;
                return Result.Success;
            }
        }

        [CmifCommand(1)]
        public Result Read(out int entriesRead, [Buffer(HipcBufferFlags.Out | HipcBufferFlags.MapAlias)] Span<DeliveryCacheDirectoryEntry> entriesBuffer)
        {
            lock (_gate)
            {
                entriesRead = 0;
                if (_directory == null) return BcatResult.NotOpen;
                int i;
                for (i = 0; i < entriesBuffer.Length && i < _directory.Files.Length; i++)
                {
                    EmbeddedDeliveryCache.CacheFile file = _directory.Files[i];
                    entriesBuffer[i] = new DeliveryCacheDirectoryEntry(in file.Name, file.Size, in file.Digest);
                }

                entriesRead = i;
                return Result.Success;
            }
        }

        [CmifCommand(2)]
        public Result GetCount(out int count)
        {
            lock (_gate)
            {
                count = 0;
                if (_directory == null) return BcatResult.NotOpen;
                count = _directory.Files.Length;
                return Result.Success;
            }
        }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposalState, 1) == 0) _parent.CloseDirectory();
        }
    }

    /// <summary>RewindBox (adapt_nextendo_data): IDeliveryCacheFileService over the served folder (LibHac's semantics, read-only).</summary>
    partial class EmbeddedDeliveryCacheFileService : IDeliveryCacheFileService, IDisposable
    {
        private readonly EmbeddedDeliveryCache.Cache _cache;
        private readonly EmbeddedDeliveryCacheStorageService _parent;
        private readonly object _gate = new();
        private EmbeddedDeliveryCache.CacheFile _file;
        private FileStream _stream;
        private int _disposalState;

        internal EmbeddedDeliveryCacheFileService(EmbeddedDeliveryCache.Cache cache, EmbeddedDeliveryCacheStorageService parent)
        {
            _cache = cache;
            _parent = parent;
        }

        [CmifCommand(0)]
        public Result Open(DirectoryName directoryName, FileName fileName)
        {
            if (!directoryName.IsValid() || !fileName.IsValid()) return BcatResult.InvalidArgument;
            lock (_gate)
            {
                if (_file != null) return BcatResult.AlreadyOpen;
                EmbeddedDeliveryCache.CacheDirectory directory = EmbeddedDeliveryCacheStorageService.Find(_cache, in directoryName);
                if (directory == null) return BcatResult.NotFound;
                string key = EmbeddedDeliveryCache.Text(fileName.Value);
                foreach (EmbeddedDeliveryCache.CacheFile file in directory.Files)
                {
                    if (!string.Equals(file.Key, key, StringComparison.Ordinal)) continue;
                    try
                    {
                        _stream = new FileStream(file.Path, FileMode.Open, FileAccess.Read, FileShare.Read);
                    }
                    catch (Exception error) when (error is IOException or UnauthorizedAccessException)
                    {
                        return BcatResult.NotFound;
                    }

                    _file = file;
                    return Result.Success;
                }

                return BcatResult.NotFound;
            }
        }

        [CmifCommand(1)]
        public Result Read(long offset, out long bytesRead, [Buffer(HipcBufferFlags.Out | HipcBufferFlags.MapAlias)] Span<byte> data)
        {
            lock (_gate)
            {
                bytesRead = 0;
                if (_file == null) return BcatResult.NotOpen;
                // As LibHac's file read (Fs/Fsa/IFile.cs): nothing to read is a success; a negative offset or one past the end
                // is out of range (ResultFs.OutOfRange, 2002-3005); at the end, nothing is read.
                if (data.IsEmpty) return Result.Success;
                if (offset < 0 || offset > _file.Size) return new Result(2, 3005);
                int length = (int)Math.Min(data.Length, _file.Size - offset);
                _stream.Position = offset;
                int total = 0;
                while (total < length)
                {
                    int read = _stream.Read(data.Slice(total, length - total));
                    if (read <= 0) break;
                    total += read;
                }

                bytesRead = total;
                return Result.Success;
            }
        }

        [CmifCommand(2)]
        public Result GetSize(out long size)
        {
            lock (_gate)
            {
                size = 0;
                if (_file == null) return BcatResult.NotOpen;
                size = _file.Size;
                return Result.Success;
            }
        }

        [CmifCommand(3)]
        public Result GetDigest(out Digest digest)
        {
            lock (_gate)
            {
                digest = default;
                if (_file == null) return BcatResult.NotOpen;
                digest = _file.Digest;
                return Result.Success;
            }
        }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposalState, 1) == 0)
            {
                lock (_gate) _stream?.Dispose();
                _parent.CloseFile();
            }
        }
    }
}
