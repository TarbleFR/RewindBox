"""Memory (every title): the shader cache load no longer keeps every cached program's host code until it ends.

Read in the Core (ParallelDiskCacheLoader.ProcessCompiledProgram): each program created from the host cache file is
added to _programList with its host code (the packed SPIR-V DiskCacheHostStorage.ReadHostCode read uncompressed), and
the list lives until LoadShaders returns. The list's code is used only by the rebuild of the cache files
(_needsHostRegen: a cache error or a program that had to be translated again), which is rare. So the whole cache's
SPIR-V is held in managed memory for the length of the load: for Super Smash Bros. Ultimate's 22 490 modules about
695 MiB of raw SPIR-V (the MoltenVK SPIR-V store's figure before its compression), for Hogwarts Legacy about 205 MiB.
Arrays of 85 000 bytes or more go to the large object heap, which the collector does not compact: IPA 767's SSBU
journal shows a large object heap of 735 MiB filled during the first minute with about 490 MiB of it free for the next
eight minutes (docs/melonx-ipa767-journals-2026-11-17.md).

Change (ParallelDiskCacheLoader.cs, DiskCacheHostStorage.cs):
- a program created from the host cache (entry.IsBinary) is added to _programList without its host code, and its index
  is remembered; a translated program keeps its code as before;
- before a rebuild clears the cache files, the host code of those programs is read back from the host cache files
  (DiskCacheHostStorage.ReadHostCodesForRebuild: the same table of contents and compressed data ReadHostCode reads, both
  files opened once); a program whose code cannot be read back is written without host code, as a translated program
  without code already is (it is translated again at the next launch).
Not changed: what is loaded, compiled, cached or drawn; the rebuild's files; the translated programs; when the load
ends. Not measured on an iPhone. Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

LOADER = 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/ParallelDiskCacheLoader.cs'
STORAGE = 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/DiskCacheHostStorage.cs'
# The preparation of Core 1df78c52 (IPA 771).
BASELINE = {
    LOADER: 'e5b62f19602d02246cabe8b3aab7e46c3871ce1354ed2194151105f513944d1c',
    STORAGE: '1e50f65672713b1bdaa03351b8e929c15f7ce0510d82f53f3dafc1e5ddec756b',
}

FIELD_OLD = '''        private readonly SortedList<int, (CachedShaderProgram, byte[])> _programList;
'''
FIELD_NEW = '''        private readonly SortedList<int, (CachedShaderProgram, byte[])> _programList;

        // RewindBox (adapt_shader_load_binary_release): programs created from the host cache whose host code is not kept.
        private readonly List<int> _releasedHostCode = new();
'''

PROCESS_OLD = '''                // Fetch the binary code from the backend if it isn't already present.
                byte[] binaryCode = entry.BinaryCode ?? entry.CachedProgram.HostProgram.GetBinary();

                _programList.Add(entry.ProgramIndex, (entry.CachedProgram, binaryCode));
'''
PROCESS_NEW = '''                // RewindBox (adapt_shader_load_binary_release): a program created from the host cache does not keep its host
                // code here: a rebuild (rare) reads it again from that cache. Keeping it held the whole cache's SPIR-V in
                // managed memory until the load ended.
                byte[] binaryCode = entry.IsBinary ? null : entry.BinaryCode ?? entry.CachedProgram.HostProgram.GetBinary();

                if (entry.IsBinary)
                {
                    _releasedHostCode.Add(entry.ProgramIndex);
                }

                _programList.Add(entry.ProgramIndex, (entry.CachedProgram, binaryCode));
'''

REBUILD_OLD = '''                try
                {
                    _hostStorage.ClearSharedCache();
                    _hostStorage.ClearHostCache(_context);
'''
REBUILD_NEW = '''                try
                {
                    // RewindBox (adapt_shader_load_binary_release): the host code not kept is read back before the files are cleared.
                    RestoreReleasedHostCode();

                    _hostStorage.ClearSharedCache();
                    _hostStorage.ClearHostCache(_context);
'''

METHOD_OLD = '''        /// <summary>
        /// Process a compiled program result.
        /// </summary>
'''
METHOD_NEW = '''        // RewindBox (adapt_shader_load_binary_release): reads back, from the host cache files, the host code of the programs
        // created from them, for the rebuild; a code that cannot be read stays null (written without host code).
        private void RestoreReleasedHostCode()
        {
            if (_releasedHostCode.Count == 0)
            {
                return;
            }

            byte[][] codes = _hostStorage.ReadHostCodesForRebuild(_context, _releasedHostCode);
            int missing = 0;

            for (int index = 0; index < _releasedHostCode.Count; index++)
            {
                int programIndex = _releasedHostCode[index];

                if (_programList.TryGetValue(programIndex, out (CachedShaderProgram, byte[]) value))
                {
                    _programList[programIndex] = (value.Item1, codes[index]);
                }

                if (codes[index] == null)
                {
                    missing++;
                }
            }

            Logger.Info?.Print(LogClass.Gpu, $"Host code read back for the rebuild: {_releasedHostCode.Count - missing} programs, {missing} unavailable (adapt_shader_load_binary_release).");
            _releasedHostCode.Clear();
        }

        /// <summary>
        /// Process a compiled program result.
        /// </summary>
'''

STORAGE_OLD = '''        private (byte[], CachedShaderStage[]) ReadHostCode(
'''
STORAGE_NEW = '''        // RewindBox (adapt_shader_load_binary_release): the host code of each listed program, read again from the host
        // cache files (the same table of contents and compressed data ReadHostCode reads; both files opened once), for the
        // loader's rebuild. An entry is null when its code cannot be read.
        public byte[][] ReadHostCodesForRebuild(GpuContext context, System.Collections.Generic.IReadOnlyList<int> programIndexes)
        {
            byte[][] codes = new byte[programIndexes.Count][];

            try
            {
                string tocFilePath = Path.Combine(_basePath, GetHostTocFileName(context));
                string dataFilePath = Path.Combine(_basePath, GetHostDataFileName(context));

                if (!File.Exists(tocFilePath) || !File.Exists(dataFilePath))
                {
                    return codes;
                }

                using FileStream tocFileStream = DiskCacheCommon.OpenFile(_basePath, GetHostTocFileName(context), writable: false);
                using FileStream dataFileStream = DiskCacheCommon.OpenFile(_basePath, GetHostDataFileName(context), writable: false);

                for (int index = 0; index < programIndexes.Count; index++)
                {
                    try
                    {
                        int offset = Unsafe.SizeOf<TocHeader>() + programIndexes[index] * Unsafe.SizeOf<OffsetAndSize>();

                        if (offset + Unsafe.SizeOf<OffsetAndSize>() > tocFileStream.Length)
                        {
                            continue;
                        }

                        tocFileStream.Seek(offset, SeekOrigin.Begin);

                        BinarySerializer tocReader = new(tocFileStream);
                        OffsetAndSize offsetAndSize = new();
                        tocReader.Read(ref offsetAndSize);

                        if (offsetAndSize.Offset >= (ulong)dataFileStream.Length)
                        {
                            continue;
                        }

                        dataFileStream.Seek((long)offsetAndSize.Offset, SeekOrigin.Begin);

                        byte[] hostCode = new byte[offsetAndSize.UncompressedSize];
                        BinarySerializer.ReadCompressed(dataFileStream, hostCode);
                        codes[index] = hostCode;
                    }
                    catch (Exception)
                    {
                        codes[index] = null;
                    }
                }
            }
            catch (Exception)
            {
                // The files could not be opened: every code stays null.
            }

            return codes;
        }

        private (byte[], CachedShaderStage[]) ReadHostCode(
'''

PAIRS = [
    (LOADER, FIELD_OLD, FIELD_NEW),
    (LOADER, PROCESS_OLD, PROCESS_NEW),
    (LOADER, REBUILD_OLD, REBUILD_NEW),
    (LOADER, METHOD_OLD, METHOD_NEW),
    (STORAGE, STORAGE_OLD, STORAGE_NEW),
]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
