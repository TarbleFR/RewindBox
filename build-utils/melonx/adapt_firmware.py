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
            EmbeddedFirmwareProgress.Set(4);
            try
            {
                EmbeddedFirmwareStore.Commit(temporaryDirectory, registeredDirectory, () => {
                    LoadEntries();
                    EmbeddedFirmwareProgress.Check();
                    if (GetCurrentFirmwareVersion() == null)
                        throw new InvalidDataException("The installed firmware was not recognized by the engine.");
                });
            }
            catch
            {
                // The store has restored the previous files. Rebuild the live
                // index too; a rejected new archive must not leave stale NCAs.
                try { LoadEntries(); } catch { /* preserve the original failure */ }
                throw;
            }
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
                byte[] buffer = new byte[81920];
                int count;
                while ((count = src.Read(buffer, 0, buffer.Length)) != 0) {
                    EmbeddedFirmwareProgress.Check();
                    dest.Write(buffer, 0, count);
                }
                dest.Position = 0;
                return dest;
            }
            catch { dest.Dispose(); throw; }
        }''')
    text = path.read_text(encoding='utf-8-sig')
    assert text.count('switch (info.Extension)') == 2
    text = text.replace('switch (info.Extension)', 'switch (info.Extension.ToLowerInvariant())')
    text = text.replace('foreach (ZipArchiveEntry entry in archive.Entries)',
                        'foreach (ZipArchiveEntry entry in EmbeddedFirmwareArchive.Entries(archive))')
    text = text.replace('if (entry.FullName.EndsWith(".nca") || entry.FullName.EndsWith(".nca/00"))',
                        'if (EmbeddedFirmwareArchive.Name(entry) != null)')
    text = text.replace("string[] pathComponents = entry.FullName.Replace(\".cnmt\", string.Empty).Split('/');",
                        'string[] pathComponents = new[] { EmbeddedFirmwareArchive.Name(entry) };')
    text = text.replace('            FinishInstallation(temporaryDirectory, registeredDirectory);',
                        '            EmbeddedFirmwareProgress.Set(3);\n            if (VerifyFirmwarePackage(temporaryDirectory) == null) throw new InvalidDataException("Incomplete extracted firmware.");\n            FinishInstallation(temporaryDirectory, registeredDirectory);')
    text = text.replace('            if (Directory.Exists(firmwareSource))',
                        '            EmbeddedFirmwareProgress.Set(2);\n            if (Directory.Exists(firmwareSource))')
    # Verify content incrementally rather than allocating a whole NCA buffer.
    old = """                                    byte[] contentData = new byte[size];

                                    Span<byte> content = new(contentData);

                                    contentStorage.Read(0, content);

                                    Span<byte> hash = new(new byte[32]);

                                    LibHac.Crypto.Sha256.GenerateSha256Hash(content, hash);"""
    assert text.count(old) == 1
    text = text.replace(old, """                                    using Stream hashStream = contentStorage.AsStream();
                                    byte[] hash = System.Security.Cryptography.SHA256.HashData(hashStream);""")
    # The directory verifier has the same allocation with different indentation.
    old2 = old.replace('                                    ', '                                ')
    assert text.count(old2) == 1
    text = text.replace(old2, """                                using Stream hashStream = contentStorage.AsStream();
                                byte[] hash = System.Security.Cryptography.SHA256.HashData(hashStream);""")
    path.write_text(text)
    return [path]
