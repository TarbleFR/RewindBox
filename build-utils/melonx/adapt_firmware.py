"""Keep firmware extraction bounded and make replacement recoverable."""
from adapt_session import once, section


def apply(source):
    path = source / 'src/Ryujinx.HLE/FileSystem/ContentManager.cs'
    once(path, '            AocData = new SortedList<ulong, AocItem>();', '''            AocData = new SortedList<ulong, AocItem>();
            if (ContentPath.TryGetContentPath(StorageId.BuiltInSystem, out string embeddedContent) &&
                ContentPath.TryGetRealPath(embeddedContent, out string embeddedDirectory))
                EmbeddedFirmwareStore.Recover(Path.Combine(embeddedDirectory, "registered"));''')
    section(path, '        private void FinishInstallation(string temporaryDirectory, string registeredDirectory)',
            '        private void InstallFromDirectory', '''        private void FinishInstallation(string temporaryDirectory, string registeredDirectory)
        {
            EmbeddedFirmwareStore.Commit(temporaryDirectory, registeredDirectory, () => LoadEntries());
        }''')
    section(path, '        private static MemoryStream GetZipStream(ZipArchiveEntry entry)',
            '        public SystemVersion VerifyFirmwarePackage', '''        private static Stream GetZipStream(ZipArchiveEntry entry)
        {
            if (entry.Length < 0 || entry.Length > 512L * 1024 * 1024)
                throw new InvalidDataException("Firmware entry exceeds the bounded import size.");
            string path = Path.Combine(Path.GetTempPath(), "rewindbox-melonx-fw-" + Guid.NewGuid().ToString("N"));
            var dest = new FileStream(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None,
                                      81920, FileOptions.DeleteOnClose | FileOptions.RandomAccess);
            try
            {
                using Stream src = entry.Open();
                src.CopyTo(dest);
                dest.Position = 0;
                return dest;
            }
            catch { dest.Dispose(); throw; }
        }''')
    return [path]
