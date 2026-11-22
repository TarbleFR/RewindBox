"""Register the guest codes of the disk shader cache once the load has them all: each code once, its sizes known first.

IPA 816-820, 22 November 2026 (private Core journal, not in the repository; times and counts only). LoadShaders takes
9.2-10.7 s for Super Smash Bros. Ultimate (12,607-12,617 programs) and 2.54 s for Hogwarts Legacy (2,116), all on the
GPU thread. The journal has no clock inside the load. Replayed on a host (x86-64, .NET 10, JIT, one thread) with the
real table files and a real private cache of 1,961 programs and 2,347 guest codes (16.6 MiB, 1,120 distinct sizes;
never in the repository), registering every program's guest codes in cache order takes 540-630 ms: 608,204 table
lookups, 969 MiB hashed and 188 MiB compared for 16.6 MiB of code, 79 MiB allocated, 83 % of the time in
PartitionHashTable.FillPartials. No code of that cache is the start of another; most share fewer than 400 first bytes
with another code.

Cause. A program compiled from the cache was registered at once (ParallelDiskCacheLoader.ProcessCompiledProgram ->
ShaderCacheHashTable.Add -> PartitionedHashTable.GetOrAdd). The table keeps one hash table per code size and, in each,
an entry for the first bytes of every longer code. (1) A code whose size is new and smaller than sizes already present
makes every longer code be hashed again from its first byte up to that size (FillPartials): with the sizes arriving in
cache order, the bytes hashed grow with codes x sizes. (2) A stage shared by several programs is the same array (the
guest cache is read once per index); each further registration looked its first bytes up in every smaller size and
compared them whole there, to add nothing. (3) Each size table was rebuilt, buckets and collision lists allocated
again, each time its count reached a power of two. All three grow faster than the cache: a synthetic cache with the
size of the Smash load (12,600 programs; 8,148 codes, 56 MiB and their sharing are a guess, the device cache was not
available) takes 10.8-11.7 s in the same replay, with 8.3 GiB hashed and 37 GiB compared.

Change. The loader keeps the programs it would have registered and registers them together when the load has compiled
its last one, before the rebuild and the "Loaded" state (and in a finally, should the load leave on an exception):
ShaderCacheHashTable.AddRange and ComputeShaderCacheHashTable.AddRange. They first reserve, in each stage's table, the
size of every code of the batch (PartitionedHashTable.ReserveSizes: sizes sorted, each appended, each size table given
the buckets of the entries the batch can bring it), then register the programs in the same order with the same Add;
a code array already registered in the batch gives its identifier back without touching the table. No size is new
when a code arrives, so no code is hashed twice, and no table is rebuilt while it fills. The batch ends with
ReleaseReservedSizes, also on an exception: a size no code took loses its table, and a table that received fewer
entries than reserved goes back to the buckets of its count. Adds made in play are unchanged: one null test in
GetOrAdd, and AddToBucket rebuilds on "more buckets needed" instead of "another bucket count", the same thing
whenever a table has the buckets of its count, which it has outside a batch. One durable journal line,
"shaderCache codeTable", gives the time and the counts. Nothing looks the tables up during the load: the GPU thread
processes its first command after it (also with adapt_guest_start_during_shader_load, which leaves that order alone).

Why later lookups are the same. A size table holds at most one entry per content, and a partial entry is always the
start of a full entry of a larger size. A reserved table therefore receives, code by code, exactly the entries
FillPartials would have given it from the full entries when its size first arrived; from that add on both tables see
the same operations. Registering an array again finds, in every table, the entries its first registration left: it
returns the same identifier and adds nothing. The bucket count of a table changes no lookup. Graphics and compute
tables are independent, so registering all graphics programs before the compute ones changes neither. Identifiers keep
their values (same first-registration order), the specialization lists their program order, GetPrograms its order. The
gate compares the complete table state (every size table and entry: hash, partial or full, item, content, bucket
count), the identifier counters and the answers of the real TryFind for the two versions, with codes that are the
start of others, equal sizes, the same content in two arrays, shared stages or none, in increasing, decreasing and
random size order, then after adds made as play makes them.

Left as it is: the compute table's Add throws a NullReferenceException for a compute code that a longer registered
code starts with (GetOrAdd returns the partial entry's null list), at a load and in play, before and after this change;
the measured cache has no such code.

Measured on the host only, same replay, best of three, two runs of the gate: real cache 540 -> 60 ms (16.6 MiB hashed
instead of 969, 43.5 MiB compared instead of 188, 540,785 lookups instead of 608,204, 36 MiB allocated instead of 79);
synthetic cache of the real one's shape 850-860 -> 77-90 ms; synthetic 12,600 programs 10.8-11.7 -> 1.1-1.2 s, 320 MiB
allocated instead of 702. What is left is the creation of the entries themselves (524,774 for the real cache, about
36 MiB that the tables keep), which every lookup of the table relies on. An array repeating the content of another, or shadowed by a longer code, costs more lookups than before (it is
looked up in every smaller size of the batch); a cache holds neither. Not measured on an iPhone: the share of
LoadShaders this removes there is unknown until a device run prints the "shaderCache codeTable" line.
Fail closed on drift: each file must be the preparation's after adapt_deferred_release_roots and every adapter
before it.
"""
import hashlib
from adapt_session import once

SHADER = 'src/Ryujinx.Graphics.Gpu/Shader/'
PARTITION = SHADER + 'HashTable/PartitionHashTable.cs'
PARTITIONED = SHADER + 'HashTable/PartitionedHashTable.cs'
GRAPHICS = SHADER + 'ShaderCacheHashTable.cs'
COMPUTE = SHADER + 'ComputeShaderCacheHashTable.cs'
LOADER = SHADER + 'DiskCache/ParallelDiskCacheLoader.cs'

BASELINE = {
    PARTITION: '10cf44b70e3af2265bac193401b5af0fc773e5918338a27618df1a1ccf7c9c6a',
    PARTITIONED: '5a298573ac73bea1b347880e11af5f132f36f160d95dc3b23119d42e7fc525d1',
    GRAPHICS: '5f3cd97b55f5f923ec8642c3675297642bff297744aee4c4e28f7d8b67367c91',
    COMPUTE: '323c0f574013646461a04966a506cec6d8826ba1f66257e2cb24ad6f20bd043c',
    LOADER: 'cc34c3487fd48b771379248a5712a4a2e1c3a1072177f631bf83e989a33f8bcd',
}

PARTITION_PAIRS = (
    ('''            int pow2Count = GetPow2Count(++_count);
            if (pow2Count != _buckets.Length)
            {
                Rebuild(pow2Count);
            }
''', '''            // RewindBox (adapt_shader_code_table_load): the table only grows here. Outside a batch it has exactly the
            // buckets of its count, as before; inside one, Reserve gave it those of the count the batch leads to.
            int pow2Count = GetPow2Count(++_count);
            if (pow2Count > _buckets.Length)
            {
                Rebuild(pow2Count);
            }
'''),
    ('''        /// <summary>
        /// Rebuilds the table for a new count.
        /// </summary>
''', '''        // RewindBox (adapt_shader_code_table_load): room for the entries a batch may add, so that the adds of the batch do
        // not rebuild the table at each power of two (each rebuild allocated the buckets and their lists again). The
        // caller ends the batch with TrimExcess.
        public void Reserve(int entries)
        {
            if (entries > 0)
            {
                int pow2Count = GetPow2Count(_count + entries);
                if (pow2Count > _buckets.Length)
                {
                    Rebuild(pow2Count);
                }
            }
        }

        // RewindBox (adapt_shader_code_table_load): back to the buckets of the count, when the batch added fewer entries
        // than reserved (data sharing their first bytes share one partial entry).
        public void TrimExcess()
        {
            if (_count == 0)
            {
                _buckets = [];
            }
            else if (GetPow2Count(_count) != _buckets.Length)
            {
                Rebuild(GetPow2Count(_count));
            }
        }

        /// <summary>
        /// Rebuilds the table for a new count.
        /// </summary>
'''),
)

PARTITIONED_PAIRS = (
    ('''            public void FillPartials(SizeEntry newEntry)
            {
                Debug.Assert(newEntry.Size < Size);
                _table.FillPartials(newEntry._table, newEntry.Size);
            }
''', '''            public void FillPartials(SizeEntry newEntry)
            {
                Debug.Assert(newEntry.Size < Size);
                _table.FillPartials(newEntry._table, newEntry.Size);
            }

            // RewindBox (adapt_shader_code_table_load): see PartitionHashTable.Reserve and TrimExcess.
            public void Reserve(int entries)
            {
                _table.Reserve(entries);
            }

            public void TrimExcess()
            {
                _table.TrimExcess();
            }
'''),
    ('''            if (index < _sizeTable.Count && _sizeTable[index].Size == data.Length)
            {
                sizeEntry = _sizeTable[index];
            }
''', '''            if (index < _sizeTable.Count && _sizeTable[index].Size == data.Length)
            {
                sizeEntry = _sizeTable[index];
                _reservedSizes?.Remove(data.Length); // RewindBox (adapt_shader_code_table_load): the size now has its data
            }
'''),
    ('''        /// <summary>
        /// Performs binary search on a list of hash tables, each one with a fixed data size.
''', '''        // RewindBox (adapt_shader_code_table_load): sizes created by ReserveSizes that no data has been added for yet;
        // null outside a batch.
        private HashSet<int> _reservedSizes;

        // RewindBox (adapt_shader_code_table_load): creates now the table of each size a batch of GetOrAdd calls is about to
        // use, so that none of them inserts a size below data already added (which hashes all that data again, see
        // FillPartials). A reserved table receives the same partial entries FillPartials would give it when its size first
        // arrives: those of the full entries present now, here, and those of each later GetOrAdd, as for any smaller size.
        // Each table also gets the buckets of the entries the batch can give it: one per datum of its size or longer.
        // The list holds the size of each datum of the batch (a size as many times as data have it) and is sorted here.
        // The caller ends the batch with ReleaseReservedSizes, before the next TryFindItem.
        public void ReserveSizes(List<int> sizes)
        {
            sizes.Sort();
            _reservedSizes ??= [];

            foreach (int size in sizes)
            {
                int index = BinarySearch(_sizeTable, size);
                if (index < _sizeTable.Count && _sizeTable[index].Size == size)
                {
                    continue;
                }

                if (index < _sizeTable.Count && _sizeTable[index].Size < size)
                {
                    index++;
                }

                SizeEntry sizeEntry = new(size);

                _sizeTable.Insert(index, sizeEntry);

                for (int i = index + 1; i < _sizeTable.Count; i++)
                {
                    _sizeTable[i].FillPartials(sizeEntry);
                }

                _reservedSizes.Add(size);
            }

            int longer = 0;

            for (int i = 0; i < _sizeTable.Count && longer < sizes.Count; i++)
            {
                while (longer < sizes.Count && sizes[longer] < _sizeTable[i].Size)
                {
                    longer++;
                }

                _sizeTable[i].Reserve(sizes.Count - longer);
            }
        }

        // RewindBox (adapt_shader_code_table_load): ends a batch. A size created by ReserveSizes and never added (the batch
        // stopped on an exception) loses its table, which only held partial entries: the table list is the one the adds
        // alone make. Every table goes back to the buckets of its count.
        public int ReleaseReservedSizes()
        {
            HashSet<int> reserved = _reservedSizes;
            int released = 0;

            if (reserved != null)
            {
                _reservedSizes = null;

                if (reserved.Count != 0)
                {
                    released = _sizeTable.RemoveAll(entry => reserved.Contains(entry.Size));
                }

                foreach (SizeEntry entry in _sizeTable)
                {
                    entry.TrimExcess();
                }
            }

            return released;
        }

        /// <summary>
        /// Performs binary search on a list of hash tables, each one with a fixed data size.
'''),
)

GRAPHICS_PAIRS = (
    ('''            /// <summary>
            /// Tries to find cached guest code.
            /// </summary>
''', '''            // RewindBox (adapt_shader_code_table_load): the batch of ShaderCacheHashTable.AddRange.
            public readonly void ReserveSizes(List<int> sizes)
            {
                _cache.ReserveSizes(sizes);
            }

            public readonly int ReleaseReservedSizes()
            {
                return _cache.ReleaseReservedSizes();
            }

            /// <summary>
            /// Tries to find cached guest code.
            /// </summary>
'''),
    ('''        /// <summary>
        /// Tries to find a cached program.
        /// </summary>
        /// <remarks>
        /// Even if false is returned, <paramref name="guestCode"/> might still contain cached guest code.
''', '''        // RewindBox (adapt_shader_code_table_load): the stage table a cached stage belongs to, as Add chooses it; -1 for a
        // stage Add registers no code for.
        private static int LoadSlot(CachedShaderStage shader)
        {
            if (shader.Info == null)
            {
                return 0;
            }

            return shader.Info.Stage switch
            {
                ShaderStage.Vertex => 1,
                ShaderStage.TessellationControl => 2,
                ShaderStage.TessellationEvaluation => 3,
                ShaderStage.Geometry => 4,
                ShaderStage.Fragment => 5,
                _ => -1,
            };
        }

        private ref IdCache LoadCache(int slot)
        {
            switch (slot)
            {
                case 0:
                    return ref _vertexACache;
                case 1:
                    return ref _vertexBCache;
                case 2:
                    return ref _tessControlCache;
                case 3:
                    return ref _tessEvaluationCache;
                case 4:
                    return ref _geometryCache;
                default:
                    return ref _fragmentCache;
            }
        }

        // RewindBox (adapt_shader_code_table_load): Add for every program of the disk cache load, in the same order, with
        // the same result. The sizes of all their codes are reserved first in each stage's table, so no code is hashed
        // again for a size that arrives after it, and a code array shared by several programs is registered once: Add
        // again would find every entry its first registration left, return the same identifier and add nothing.
        // Not for play: the lists and the reservation only pay for a batch.
        public void AddRange(List<CachedShaderProgram> programs, out int references, out int codes, out long codeBytes)
        {
            const int Slots = 6;
            const int Unregistered = int.MinValue; // Add returns 0 (a longer code shadows it) or a positive identifier

            Dictionary<byte[], int>[] ids = new Dictionary<byte[], int>[Slots];
            List<int>[] sizes = new List<int>[Slots];

            references = 0;
            codes = 0;
            codeBytes = 0;

            foreach (CachedShaderProgram program in programs)
            {
                foreach (CachedShaderStage shader in program.Shaders)
                {
                    int slot = shader == null ? -1 : LoadSlot(shader);
                    if (slot < 0)
                    {
                        continue;
                    }

                    references++;

                    if ((ids[slot] ??= new Dictionary<byte[], int>(ReferenceEqualityComparer.Instance)).TryAdd(shader.Code, Unregistered))
                    {
                        (sizes[slot] ??= []).Add(shader.Code.Length);
                        codes++;
                        codeBytes += shader.Code.Length;
                    }
                }
            }

            try
            {
                for (int slot = 0; slot < Slots; slot++)
                {
                    if (sizes[slot] != null)
                    {
                        LoadCache(slot).ReserveSizes(sizes[slot]);
                    }
                }

                foreach (CachedShaderProgram program in programs)
                {
                    IdTable idTable = new();

                    foreach (CachedShaderStage shader in program.Shaders)
                    {
                        int slot = shader == null ? -1 : LoadSlot(shader);
                        if (slot < 0)
                        {
                            continue;
                        }

                        Dictionary<byte[], int> known = ids[slot];
                        int id = known[shader.Code];

                        if (id == Unregistered)
                        {
                            id = LoadCache(slot).Add(shader.Code);
                            known[shader.Code] = id;
                        }

                        switch (slot)
                        {
                            case 0:
                                idTable.VertexAId = id;
                                break;
                            case 1:
                                idTable.VertexBId = id;
                                break;
                            case 2:
                                idTable.TessControlId = id;
                                break;
                            case 3:
                                idTable.TessEvaluationId = id;
                                break;
                            case 4:
                                idTable.GeometryId = id;
                                break;
                            default:
                                idTable.FragmentId = id;
                                break;
                        }
                    }

                    if (!_shaderPrograms.TryGetValue(idTable, out ShaderSpecializationList specList))
                    {
                        specList = [];
                        _shaderPrograms.Add(idTable, specList);
                    }

                    specList.Add(program);
                }
            }
            finally
            {
                for (int slot = 0; slot < Slots; slot++)
                {
                    if (sizes[slot] != null)
                    {
                        LoadCache(slot).ReleaseReservedSizes();
                    }
                }
            }
        }

        /// <summary>
        /// Tries to find a cached program.
        /// </summary>
        /// <remarks>
        /// Even if false is returned, <paramref name="guestCode"/> might still contain cached guest code.
'''),
)

COMPUTE_PAIRS = (
    ('''        /// <summary>
        /// Tries to find a cached program.
        /// </summary>
        /// <param name="channel">GPU channel</param>
''', '''        // RewindBox (adapt_shader_code_table_load): Add for every compute program of the disk cache load, in the same
        // order, with the same result (see ShaderCacheHashTable.AddRange): sizes reserved first, a code array shared by
        // several programs looked up once.
        public void AddRange(List<CachedShaderProgram> programs, out int references, out int codes, out long codeBytes)
        {
            Dictionary<byte[], ShaderSpecializationList> lists = new(ReferenceEqualityComparer.Instance);
            List<int> sizes = [];

            references = programs.Count;
            codes = 0;
            codeBytes = 0;

            foreach (CachedShaderProgram program in programs)
            {
                byte[] code = program.Shaders[0].Code;

                if (lists.TryAdd(code, null))
                {
                    sizes.Add(code.Length);
                    codes++;
                    codeBytes += code.Length;
                }
            }

            try
            {
                _cache.ReserveSizes(sizes);

                foreach (CachedShaderProgram program in programs)
                {
                    byte[] code = program.Shaders[0].Code;
                    ShaderSpecializationList specList = lists[code];

                    if (specList == null)
                    {
                        specList = _cache.GetOrAdd(code, []);
                        lists[code] = specList;
                    }

                    specList.Add(program);
                    _shaderPrograms.Add(program);
                }
            }
            finally
            {
                _cache.ReleaseReservedSizes();
            }
        }

        /// <summary>
        /// Tries to find a cached program.
        /// </summary>
        /// <param name="channel">GPU channel</param>
'''),
)

LOADER_PAIRS = (
    ('''        private readonly int _backendParallelCompileThreads;
''', '''        // RewindBox (adapt_shader_code_table_load): the programs of the load, in the order they would have been registered;
        // RegisterLoadedPrograms registers them together.
        private readonly List<CachedShaderProgram> _loadedGraphics = new();
        private readonly List<CachedShaderProgram> _loadedCompute = new();
        private bool _loadedRegistered;

        private readonly int _backendParallelCompileThreads;
'''),
    ('''        public void LoadShaders()
        {
            // Reading the host table itself requires no translation thread.
''', '''        public void LoadShaders()
        {
            // RewindBox (adapt_shader_code_table_load): the load registers its programs when it has compiled the last one;
            // a load that leaves on an exception registers here those it had, as it had done one by one.
            try
            {
                LoadShadersThenRegister();
            }
            finally
            {
                RegisterLoadedPrograms();
            }
        }

        private void LoadShadersThenRegister()
        {
            // Reading the host table itself requires no translation thread.
'''),
    ('''            CheckCompilationBlocking();

            if (_needsHostRegen && Active)
''', '''            CheckCompilationBlocking();
            RegisterLoadedPrograms(); // RewindBox (adapt_shader_code_table_load): before the "Loaded" state is published

            if (_needsHostRegen && Active)
'''),
    ('''        /// <summary>
        /// Process a compiled program result.
        /// </summary>
''', '''        // RewindBox (adapt_shader_code_table_load): a program compiled from the cache waits here for the others. Registering
        // each at once made every code whose size was new hash all the longer codes again, and looked a shared stage up in
        // every smaller size for each program using it. Nothing looks the tables up before the load ends.
        private void RegisterLoadedProgram(CachedShaderProgram program, bool isCompute)
        {
            if (_loadedRegistered)
            {
                if (isCompute)
                {
                    _computeCache.Add(program);
                }
                else
                {
                    _graphicsCache.Add(program);
                }
            }
            else
            {
                (isCompute ? _loadedCompute : _loadedGraphics).Add(program);
            }
        }

        // RewindBox (adapt_shader_code_table_load): once per load, on the loading thread. Graphics and compute tables are
        // independent, so each keeps the order its programs were compiled in.
        private void RegisterLoadedPrograms()
        {
            if (_loadedRegistered)
            {
                return;
            }

            _loadedRegistered = true;

            long start = System.Diagnostics.Stopwatch.GetTimestamp();

            _graphicsCache.AddRange(_loadedGraphics, out int references, out int codes, out long codeBytes);
            _computeCache.AddRange(_loadedCompute, out _, out int computeCodes, out long computeCodeBytes);

            long elapsed = (System.Diagnostics.Stopwatch.GetTimestamp() - start) * 1000 / System.Diagnostics.Stopwatch.Frequency;

            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("shaderCache", "codeTable", detail:
                $"guest codes registered after the load in {elapsed} ms: {_loadedGraphics.Count} graphics programs, {references} stage codes, " +
                $"{codes} distinct ({codeBytes / 1024} KiB); {_loadedCompute.Count} compute programs, {computeCodes} distinct codes " +
                $"({computeCodeBytes / 1024} KiB); each code hashed once, sizes reserved first");

            _loadedGraphics.Clear();
            _loadedCompute.Clear();
        }

        /// <summary>
        /// Process a compiled program result.
        /// </summary>
'''),
    ('''                // Compilation successful, add to memory cache.
                if (entry.IsCompute)
                {
                    _computeCache.Add(entry.CachedProgram);
                }
                else
                {
                    _graphicsCache.Add(entry.CachedProgram);
                }
''', '''                // Compilation successful, add to memory cache.
                RegisterLoadedProgram(entry.CachedProgram, entry.IsCompute); // RewindBox (adapt_shader_code_table_load)
'''),
)

FILE_PAIRS = {
    PARTITION: PARTITION_PAIRS,
    PARTITIONED: PARTITIONED_PAIRS,
    GRAPHICS: GRAPHICS_PAIRS,
    COMPUTE: COMPUTE_PAIRS,
    LOADER: LOADER_PAIRS,
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
