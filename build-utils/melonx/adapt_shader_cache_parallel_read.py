"""Launch (every title): the disk shader cache is read by a few threads ahead of the GPU thread, which takes the programs in order.

IPA 816-821, 22 November 2026 (private Core journals, not in the repository; times and counts only). LoadShaders takes
9.2-10.7 s for Super Smash Bros. Ultimate (12,607-12,630 programs) and about 2.5 s for Hogwarts Legacy (2,116), on the
GPU thread. The journal's render-thread windows cover those loads: creating every program takes the render thread
0.49-0.82 s in all for Smash and 0.09-0.15 s for Hogwarts, and the GPU thread waits 0.25-0.40 s and 0.05-0.09 s in all
for link checks. The rest, 8 to 9.5 s and about 2.3 s (0.7 and 1.1 ms a program), is the GPU thread's own work.

Where it goes, measured on a host (x86-64, .NET 10, JIT; the production Ryujinx.Graphics.Gpu assembly with a renderer
double) with a real private cache (1,877 programs; 227.5 MiB of host code in 70.2 MiB of Brotli records, median 125 KB
a program, 674 KB the largest; 2,347 guest codes, 16.6 MiB): the load takes 1.15-1.32 s, of which decompressing the
host code 0.82-0.89 s (72 %), the guest codes 0.12-0.13 s, each program's shared entry 0.03 s, its host information
0.04 s, its specialization state 0.007 s, unpacking and building the shader information 0.012 s, creating and queueing
(double) 0.007 s, the code tables 0.06 s. Reading is 97 % of the load there, one program after another, each read
finished before the program is created. The buffers are already allocated at their exact size (an earlier note said
they grew): the cost is the decompression itself, about 290 MiB/s on that host.

Change (DiskCacheHostStorage.cs, DiskCacheGuestStorage.cs). LoadShaders keeps its loop, its order and everything it
does with a program once read (unpack, shader information, CreateProgram, QueueHostProgram or QueueGuestProgram, a
CheckCompilation every eight programs, the test of loader.Active before each program): that text is not touched. What
it read for a program (table entry, shared entry, guest codes, specialization state, host code, host information) is
now read by ProgramReader.Read, the same statements in the same order, and the loop takes each program from
ProgramReadAhead.Take(programIndex):
- a few threads (GPU.ShaderCacheReadThread.N), each with its own read-only streams, read the next program nobody has;
  the GPU thread reads too while the program it needs is still being read, and reads it itself when nobody took it;
- at most 8 programs are read, or being read, and not yet taken (the one the GPU thread is at included), and a thread
  reading ahead leaves a host code above 2 MiB to the GPU thread: the read-ahead holds at most 16 MiB of host code,
  about 1 MiB with the cache measured;
- a program whose read ahead threw, or was left for its size, is read again by the GPU thread when it reaches it, with
  the streams LoadShaders opened and no limit: every error is thrown by that read, on the GPU thread, after the
  programs before it were created and queued, as before. The first read ahead that throws ends the reading ahead;
- the host files are opened and checked by ReadHostCode's first call for each reader; a call that opened them without
  finding a host code closes them again, so that a reader asked again makes the same checks with the same answer. The
  load stopped asking for host code at the first program without any (no host file, older host files, a host table
  that ends early): each of those holds for every later program, so the first such index known to any reader is noted
  and no reader asks beyond it;
- guest codes are shared by the readers through DiskCacheGuestStorage.LoadShader, now under a lock for the table and
  one lock per code index (sixteen in all): a code is read once and every program gets the same arrays, as before. The
  table kept nothing when it grew (it only grows for an index past the guest table of contents, whose read then
  throws): it now keeps the codes read, so that a thread reading ahead cannot take away the codes of earlier programs;
- LoadShaders ends the reading ahead in its finally, before the guest codes are dropped: the threads are joined and
  every stream is closed when it returns (a cancelled load: at most one program read per reader later), then one
  journal line, "shaderCache read", gives the phases: programs taken, time, the GPU thread's wait for a program being
  read, its own reads, creating and queueing, link checks, the threads' count, programs and time, host code read, the
  most programs outstanding, and whether a read ahead failed.
- a cache of fewer than 16 programs is read by the GPU thread alone; a thread that cannot start or open its streams
  takes nothing.

How many threads. The guest and its translator now run while the cache loads (adapt_guest_start_during_shader_load),
and the launch waits for both. With the GPU thread, which reads too, at most half of the cores read: cores / 2 - 1
threads, at least 1 from two cores, never more than 3. Six cores (A18 Pro, two performance and four efficiency): 2
threads and the GPU thread; three cores stay for the guest threads, the render thread (busy 5 to 9 % of the load, see
above) and the pipeline workers. The threads ask the user-interactive class (Ryujinx.Common.HostThreadClass), where
the GPU thread, which made these reads alone, already is: in the default class they would yield to every guest
thread and the GPU thread would wait for them.

Why the result is the same. A program's read depends on the files alone: every reader runs the control's statements
on its own streams, and the two things the loop carried from one program to the next are functions of the files too
(the guest code of an index: one array per index either way; whether host code is still asked for: see above). The
loop takes the programs in index order and nothing is created, queued or reported from a read: the programs, their
order, their bytes, the state callbacks and the files are the control's. A corrupt or truncated entry is found by the
GPU thread's own read of that program. The gate compares all of it for 0, 1, 2 and 3 threads against the control.

Measured on the host only (4 shared cores, so 1 thread by the rule above). Real cache: 1.15-1.32 s -> 0.68-0.76 s with
1 thread, 0.52-0.63 s with 2 (the count on six cores), 1.11 s with none. Gate, launch-shaped synthetic cache (1,000
programs, 124 MiB of host code, same sizes and compression), best of alternated runs: 475 ms -> 300 ms with 1 thread,
226 ms with 2, 479 ms with none. Memory with the GPU thread held: 7.1-7.3 MiB more than the control with 64 programs
of 1 MiB (7 programs ahead), nothing more with host codes above the limit. Not measured on an iPhone: the share of
the 9-10 s this removes there depends on the cores the scheduler gives the threads while the guest starts; the
"shaderCache read" line of a device run says it (the GPU thread's wait and read times against the threads').
Left as it is: the host code arrays (one per program, large object heap), the Brotli format, the renderer's work.
Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift: both files must be the
preparation's of Core 64e49a84 (IPA 825).
"""
import hashlib
from adapt_session import once

CACHE = 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/'
STORAGE = CACHE + 'DiskCacheHostStorage.cs'
GUEST = CACHE + 'DiskCacheGuestStorage.cs'

# The preparation of Core 64e49a84 (IPA 825).
BASELINE = {
    STORAGE: '67c363f7664cafae2cb6ba187214f6be418d610020447c57c6b6045b49a26d37',
    GUEST: 'ab8aca1e0bb618f6d50abb5d15d10c78169ffae6e67bf774500567093035fd4c',
}

FIELD_OLD = '''        private readonly DiskCacheGuestStorage _guestStorage;

        /// <summary>
        /// Creates a disk cache host storage.
        /// </summary>
'''
FIELD_NEW = '''        private readonly DiskCacheGuestStorage _guestStorage;

        // RewindBox (adapt_shader_cache_parallel_read): begin
        // The threads that read the programs of a load ahead of the GPU thread. With the GPU thread, which reads too, at
        // most half of the cores read (two threads and the GPU thread on six cores): the guest, started during the load,
        // its translator and the render thread keep the others. Never more than three, none on a single core.
        private const int MaximumReadAheadThreads = 3;
        private readonly int _readAheadThreads = ReadAheadThreadCount(Environment.ProcessorCount);

        private static int ReadAheadThreadCount(int processors)
        {
            return Math.Clamp(processors / 2 - 1, processors > 1 ? 1 : 0, MaximumReadAheadThreads);
        }

        // What ReadHostCode answers, instead of reading it, for a host code above the size it was given.
        private static readonly byte[] _hostCodeLeftToCaller = new byte[1];

        /// <summary>
        /// One program of the shared cache as LoadShaders reads it, before anything is created from it.
        /// </summary>
        private sealed class ProgramRead
        {
            // A read ahead that threw, and one that left its host code to the GPU thread: the GPU thread reads these
            // programs itself when it reaches them.
            public static readonly ProgramRead Failed = new();
            public static readonly ProgramRead LeftToGpuThread = new();

            public bool IsCompute;
            public GuestCodeAndCbData?[] GuestShaders;
            public ShaderSpecializationState SpecState;
            public byte[] HostCode;
            public CachedShaderStage[] Shaders;
        }

        /// <summary>
        /// Reads programs of the shared cache with its own streams: the statements LoadShaders ran for each program,
        /// in their order. One per reading thread.
        /// </summary>
        private sealed class ProgramReader
        {
            private readonly DiskCacheHostStorage _storage;
            private readonly ProgramReadAhead _load;
            private readonly Stream _tocFileStream;
            private readonly Stream _dataFileStream;
            private readonly Stream _guestTocFileStream;
            private readonly Stream _guestDataFileStream;
            private readonly bool _ownsStreams;
            private Stream _hostTocFileStream;
            private Stream _hostDataFileStream;

            public ProgramReader(
                DiskCacheHostStorage storage,
                ProgramReadAhead load,
                Stream tocFileStream,
                Stream dataFileStream,
                Stream guestTocFileStream,
                Stream guestDataFileStream,
                bool ownsStreams)
            {
                _storage = storage;
                _load = load;
                _tocFileStream = tocFileStream;
                _dataFileStream = dataFileStream;
                _guestTocFileStream = guestTocFileStream;
                _guestDataFileStream = guestDataFileStream;
                _ownsStreams = ownsStreams;
            }

            /// <summary>
            /// Reads one program. Throws what the load threw for it.
            /// </summary>
            /// <param name="programIndex">Index of the program on the cache</param>
            /// <param name="maximumHostCodeSize">Largest host code read; for a larger one the answer is LeftToGpuThread</param>
            /// <returns>The program as read</returns>
            public ProgramRead Read(int programIndex, uint maximumHostCodeSize)
            {
                BinarySerializer tocReader = new(_tocFileStream);
                BinarySerializer dataReader = new(_dataFileStream);

                _tocFileStream.Seek(_load.FirstEntry + (long)programIndex * sizeof(ulong), SeekOrigin.Begin);

                ulong dataOffset = 0;
                tocReader.Read(ref dataOffset);

                if ((ulong)dataOffset >= (ulong)_dataFileStream.Length)
                {
                    throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric);
                }

                _dataFileStream.Seek((long)dataOffset, SeekOrigin.Begin);

                DataEntry entry = new();

                dataReader.BeginCompression();
                dataReader.Read(ref entry);
                uint stagesBitMask = entry.StagesBitMask;

                if ((stagesBitMask & ~0x3fu) != 0)
                {
                    throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric);
                }

                bool isCompute = stagesBitMask == 0;
                if (isCompute)
                {
                    stagesBitMask = 1;
                }

                GuestCodeAndCbData?[] guestShaders = new GuestCodeAndCbData?[isCompute ? 1 : Constants.ShaderStages + 1];

                DataEntryPerStage stageEntry = new();

                while (stagesBitMask != 0)
                {
                    int stageIndex = BitOperations.TrailingZeroCount(stagesBitMask);

                    dataReader.Read(ref stageEntry);

                    guestShaders[stageIndex] = _storage._guestStorage.LoadShader(
                        _guestTocFileStream,
                        _guestDataFileStream,
                        stageEntry.GuestCodeIndex);

                    stagesBitMask &= ~(1u << stageIndex);
                }

                ShaderSpecializationState specState = ShaderSpecializationState.Read(ref dataReader);
                dataReader.EndCompression();

                byte[] hostCode = null;
                CachedShaderStage[] shaders = null;

                // The load stops reading host code at the first program that has none (no host files, files older than
                // the shared cache, or a host table that ends before this program): every later program has none either,
                // whichever thread reads it. Until one is known, each thread asks its own streams.
                if (_load.LoadHostCache && programIndex < _load.FirstProgramWithoutHostCode)
                {
                    // ReadHostCode opens the host files and checks them when it is given no stream. The load made that
                    // call once, for its first program, and no other call after one that threw or found no host code.
                    // Here a reader may be asked again after such a call (for a program before the one it read ahead):
                    // its streams are then closed again, so that the next call makes the same checks, with the same
                    // answer, instead of going on with files the first call refused.
                    bool opens = _hostTocFileStream == null && _hostDataFileStream == null;
                    bool hasCode = false;

                    try
                    {
                        (hostCode, shaders) = _storage.ReadHostCode(
                            _load.Context,
                            ref _hostTocFileStream,
                            ref _hostDataFileStream,
                            guestShaders,
                            programIndex,
                            _load.Timestamp,
                            maximumHostCodeSize);

                        hasCode = hostCode != null;
                    }
                    finally
                    {
                        if (opens && !hasCode)
                        {
                            CloseHostStreams();
                        }
                    }

                    if (hostCode == null)
                    {
                        _load.NoteProgramWithoutHostCode(programIndex);
                    }
                    else if (ReferenceEquals(hostCode, _hostCodeLeftToCaller))
                    {
                        return ProgramRead.LeftToGpuThread;
                    }
                }

                return new ProgramRead
                {
                    IsCompute = isCompute,
                    GuestShaders = guestShaders,
                    SpecState = specState,
                    HostCode = hostCode,
                    Shaders = shaders,
                };
            }

            private void CloseHostStreams()
            {
                _hostTocFileStream?.Dispose();
                _hostDataFileStream?.Dispose();
                _hostTocFileStream = null;
                _hostDataFileStream = null;
            }

            public void Dispose()
            {
                CloseHostStreams();

                if (_ownsStreams)
                {
                    _tocFileStream.Dispose();
                    _dataFileStream.Dispose();
                    _guestTocFileStream.Dispose();
                    _guestDataFileStream.Dispose();
                }
            }
        }

        /// <summary>
        /// The programs of one load, read ahead of the GPU thread by a few threads and handed to it in cache order.
        /// </summary>
        /// <remarks>
        /// The GPU thread takes the programs one by one, in order, as its loop read them. A thread reads the next
        /// program nobody has, with its own streams; so does the GPU thread while the program it needs is still being
        /// read. A program read ahead that threw, or whose host code is above MaximumHostCodeSize, is read again by
        /// the GPU thread when it reaches it, as it always was: what a corrupt or truncated entry does, and when,
        /// comes from that read alone. The first read ahead that throws ends the reading ahead.
        /// </remarks>
        private sealed class ProgramReadAhead
        {
            // Programs read, or being read, and not yet taken by the GPU thread, the one it is at included.
            public const int Window = 8;

            // A larger host code is read by the GPU thread when it reaches the program: the window holds at most
            // Window * MaximumHostCodeSize of host code.
            public const uint MaximumHostCodeSize = 2 * 1024 * 1024;

            // Below this many programs the GPU thread reads alone.
            private const int MinimumPrograms = 2 * Window;

            public readonly GpuContext Context;
            public readonly bool LoadHostCache;
            public readonly ulong Timestamp;
            public readonly long FirstEntry;

            private readonly DiskCacheHostStorage _storage;
            private readonly ProgramReader _reader;
            private readonly int _entries;
            private readonly object _sync = new();
            private readonly ProgramRead[] _ring = new ProgramRead[Window];
            private readonly Thread[] _threads;
            private int _startedThreads;
            private bool _started;
            private bool _closed;
            private int _next;
            private int _consumed;
            private int _firstProgramWithoutHostCode = int.MaxValue;

            // For the journal line.
            private readonly long _start = System.Diagnostics.Stopwatch.GetTimestamp();
            private long _waitTicks;
            private long _gpuThreadReadTicks;
            private long _threadReadTicks;
            private long _hostCodeBytes;
            private int _taken;
            private int _readByThreads;
            private int _readAheadByGpuThread;
            private int _readInOrder;
            private int _leftToGpuThread;
            private int _mostOutstanding;
            private bool _failed;

            public ProgramReadAhead(
                DiskCacheHostStorage storage,
                GpuContext context,
                bool loadHostCache,
                ulong timestamp,
                Stream tocFileStream,
                Stream dataFileStream,
                Stream guestTocFileStream,
                Stream guestDataFileStream,
                int entries)
            {
                _storage = storage;
                Context = context;
                LoadHostCache = loadHostCache;
                Timestamp = timestamp;
                FirstEntry = tocFileStream.Position;
                _entries = entries;
                _reader = new ProgramReader(storage, this, tocFileStream, dataFileStream, guestTocFileStream, guestDataFileStream, ownsStreams: false);
                _threads = new Thread[Math.Max(storage._readAheadThreads, 0)];
            }

            public int FirstProgramWithoutHostCode => Volatile.Read(ref _firstProgramWithoutHostCode);

            public void NoteProgramWithoutHostCode(int programIndex)
            {
                int current;

                while (programIndex < (current = Volatile.Read(ref _firstProgramWithoutHostCode)))
                {
                    if (Interlocked.CompareExchange(ref _firstProgramWithoutHostCode, programIndex, current) == current)
                    {
                        break;
                    }
                }
            }

            /// <summary>
            /// Gives the GPU thread the next program, in cache order. Throws what the load threw for it.
            /// </summary>
            /// <param name="programIndex">Index of the program on the cache; the calls are made in increasing order</param>
            /// <returns>The program as read</returns>
            public ProgramRead Take(int programIndex)
            {
                if (!_started)
                {
                    _started = true;
                    StartThreads();
                }

                while (true)
                {
                    ProgramRead read;
                    int ahead = -1;

                    lock (_sync)
                    {
                        if (_consumed != programIndex)
                        {
                            _consumed = programIndex;
                            Monitor.PulseAll(_sync);
                        }

                        read = _ring[programIndex % Window];

                        if (read != null)
                        {
                            _ring[programIndex % Window] = null;
                        }
                        else if (_next == programIndex)
                        {
                            // Nobody has it: the GPU thread reads it now.
                            _next++;
                        }
                        else if (!_closed && _next < _entries && _next < programIndex + Window)
                        {
                            // A thread is reading it: the GPU thread reads another program meanwhile.
                            ahead = _next++;
                            _mostOutstanding = Math.Max(_mostOutstanding, _next - _consumed);
                        }
                        else
                        {
                            long waitStart = System.Diagnostics.Stopwatch.GetTimestamp();
                            Monitor.Wait(_sync);
                            _waitTicks += System.Diagnostics.Stopwatch.GetTimestamp() - waitStart;
                            continue;
                        }
                    }

                    long readStart = System.Diagnostics.Stopwatch.GetTimestamp();

                    if (ahead >= 0)
                    {
                        ProgramRead aheadRead = TryRead(_reader, ahead);

                        _gpuThreadReadTicks += System.Diagnostics.Stopwatch.GetTimestamp() - readStart;

                        lock (_sync)
                        {
                            _ring[ahead % Window] = aheadRead;

                            if (aheadRead == ProgramRead.Failed)
                            {
                                _closed = true;
                                Monitor.PulseAll(_sync);
                            }
                            else if (aheadRead != ProgramRead.LeftToGpuThread)
                            {
                                _readAheadByGpuThread++;
                            }
                        }

                        continue;
                    }

                    if (read == null || read == ProgramRead.Failed || read == ProgramRead.LeftToGpuThread)
                    {
                        if (read == ProgramRead.Failed)
                        {
                            _failed = true;
                        }
                        else if (read == ProgramRead.LeftToGpuThread)
                        {
                            _leftToGpuThread++;
                        }

                        // In order, on the GPU thread, with the streams LoadShaders opened: the read the load always made.
                        try
                        {
                            read = _reader.Read(programIndex, uint.MaxValue);
                        }
                        finally
                        {
                            _gpuThreadReadTicks += System.Diagnostics.Stopwatch.GetTimestamp() - readStart;
                        }

                        _readInOrder++;
                    }

                    _taken++;
                    _hostCodeBytes += read.HostCode?.Length ?? 0;

                    return read;
                }
            }

            private static ProgramRead TryRead(ProgramReader reader, int programIndex)
            {
                try
                {
                    return reader.Read(programIndex, MaximumHostCodeSize);
                }
                catch (Exception)
                {
                    return ProgramRead.Failed;
                }
            }

            private void StartThreads()
            {
                if (_entries < MinimumPrograms)
                {
                    return;
                }

                for (int index = 0; index < _threads.Length; index++)
                {
                    Thread thread = new(ReadAheadThread) { Name = $"GPU.ShaderCacheReadThread.{index}", IsBackground = true };

                    try
                    {
                        thread.Start();
                    }
                    catch (Exception)
                    {
                        // The threads already started and the GPU thread read.
                        break;
                    }

                    _threads[_startedThreads++] = thread;
                }
            }

            private void ReadAheadThread()
            {
                // The launch waits for this read, which the GPU thread made alone in its class.
                Ryujinx.Common.HostThreadClass.RaiseCurrentThread();

                ProgramReader reader = null;

                try
                {
                    reader = new ProgramReader(
                        _storage,
                        this,
                        DiskCacheCommon.OpenFile(_storage._basePath, SharedTocFileName, writable: false),
                        DiskCacheCommon.OpenFile(_storage._basePath, SharedDataFileName, writable: false),
                        _storage._guestStorage.OpenTocFileStream(),
                        _storage._guestStorage.OpenDataFileStream(),
                        ownsStreams: true);

                    while (true)
                    {
                        int programIndex;

                        lock (_sync)
                        {
                            while (!_closed && _next < _entries && _next >= _consumed + Window)
                            {
                                Monitor.Wait(_sync);
                            }

                            if (_closed || _next >= _entries)
                            {
                                break;
                            }

                            programIndex = _next++;
                            _mostOutstanding = Math.Max(_mostOutstanding, _next - _consumed);
                        }

                        long readStart = System.Diagnostics.Stopwatch.GetTimestamp();
                        ProgramRead read = TryRead(reader, programIndex);
                        long readTicks = System.Diagnostics.Stopwatch.GetTimestamp() - readStart;

                        lock (_sync)
                        {
                            _ring[programIndex % Window] = read;
                            _threadReadTicks += readTicks;

                            if (read == ProgramRead.Failed)
                            {
                                _closed = true;
                            }
                            else if (read != ProgramRead.LeftToGpuThread)
                            {
                                _readByThreads++;
                            }

                            Monitor.PulseAll(_sync);
                        }
                    }
                }
                catch (Exception)
                {
                    // Its streams could not be opened: it took no program; the other threads and the GPU thread read.
                }

                try
                {
                    reader?.Dispose();
                }
                catch (Exception)
                {
                }
            }

            /// <summary>
            /// Ends the reading ahead: its threads have ended and their streams are closed when this returns.
            /// </summary>
            public void End(bool completed, bool cancelled, long createTicks, long checkTicks)
            {
                lock (_sync)
                {
                    _closed = true;
                    Monitor.PulseAll(_sync);
                }

                for (int index = 0; index < _startedThreads; index++)
                {
                    _threads[index].Join();
                }

                _reader.Dispose();

                static long Milliseconds(long ticks) => ticks * 1000 / System.Diagnostics.Stopwatch.Frequency;

                long elapsed = Milliseconds(System.Diagnostics.Stopwatch.GetTimestamp() - _start);

                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("shaderCache", "read", detail:
                    $"{_taken} of {_entries} programs read and queued in {elapsed} ms ({(completed ? "all" : cancelled ? "cancelled" : "stopped by an error")}); " +
                    $"GPU thread: waited {Milliseconds(_waitTicks)} ms for a program being read, read {_readInOrder + _readAheadByGpuThread} programs itself in " +
                    $"{Milliseconds(_gpuThreadReadTicks)} ms ({_readAheadByGpuThread} ahead; {_leftToGpuThread} with a host code above {MaximumHostCodeSize / 1024} KiB), " +
                    $"created and queued the programs in {Milliseconds(createTicks)} ms (link waits of a full queue included), other link checks {Milliseconds(checkTicks)} ms; " +
                    $"{_startedThreads} read-ahead threads of {_threads.Length} read {_readByThreads} programs in {Milliseconds(_threadReadTicks)} ms of their own; " +
                    $"host code {_hostCodeBytes / 1048576} MiB; at most {Window} programs read and not yet used (most: {_mostOutstanding}); " +
                    $"reading ahead {(_failed ? "ended at a read that failed" : "never failed")} (adapt_shader_cache_parallel_read)");
            }
        }
        // RewindBox (adapt_shader_cache_parallel_read): end

        /// <summary>
        /// Creates a disk cache host storage.
        /// </summary>
'''

LOAD_OLD = '''            Stream hostTocFileStream = null;
            Stream hostDataFileStream = null;

            try
            {
                using FileStream tocFileStream = DiskCacheCommon.OpenFile(_basePath, SharedTocFileName, writable: false);
                using FileStream dataFileStream = DiskCacheCommon.OpenFile(_basePath, SharedDataFileName, writable: false);

                using Stream guestTocFileStream = _guestStorage.OpenTocFileStream();
                using Stream guestDataFileStream = _guestStorage.OpenDataFileStream();

                BinarySerializer tocReader = new(tocFileStream);
                BinarySerializer dataReader = new(dataFileStream);

                TocHeader header = new();
'''
LOAD_NEW = '''            // RewindBox (adapt_shader_cache_parallel_read): the programs are read by ProgramReadAhead (the GPU thread and a
            // few threads, each with its own streams) and taken here one by one, in cache order.
            ProgramReadAhead readAhead = null;
            bool completed = false;
            long createTicks = 0;
            long checkTicks = 0;

            try
            {
                using FileStream tocFileStream = DiskCacheCommon.OpenFile(_basePath, SharedTocFileName, writable: false);
                using FileStream dataFileStream = DiskCacheCommon.OpenFile(_basePath, SharedDataFileName, writable: false);

                using Stream guestTocFileStream = _guestStorage.OpenTocFileStream();
                using Stream guestDataFileStream = _guestStorage.OpenDataFileStream();

                BinarySerializer tocReader = new(tocFileStream);

                TocHeader header = new();
'''

LOOP_OLD = '''                int programIndex = 0;

                DataEntry entry = new();

                while (tocFileStream.Position < tocFileStream.Length && loader.Active)
                {
                    ulong dataOffset = 0;
                    tocReader.Read(ref dataOffset);

                    if ((ulong)dataOffset >= (ulong)dataFileStream.Length)
                    {
                        throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric);
                    }

                    dataFileStream.Seek((long)dataOffset, SeekOrigin.Begin);

                    dataReader.BeginCompression();
                    dataReader.Read(ref entry);
                    uint stagesBitMask = entry.StagesBitMask;

                    if ((stagesBitMask & ~0x3fu) != 0)
                    {
                        throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric);
                    }

                    bool isCompute = stagesBitMask == 0;
                    if (isCompute)
                    {
                        stagesBitMask = 1;
                    }

                    GuestCodeAndCbData?[] guestShaders = new GuestCodeAndCbData?[isCompute ? 1 : Constants.ShaderStages + 1];

                    DataEntryPerStage stageEntry = new();

                    while (stagesBitMask != 0)
                    {
                        int stageIndex = BitOperations.TrailingZeroCount(stagesBitMask);

                        dataReader.Read(ref stageEntry);

                        guestShaders[stageIndex] = _guestStorage.LoadShader(
                            guestTocFileStream,
                            guestDataFileStream,
                            stageEntry.GuestCodeIndex);

                        stagesBitMask &= ~(1u << stageIndex);
                    }

                    ShaderSpecializationState specState = ShaderSpecializationState.Read(ref dataReader);
                    dataReader.EndCompression();

                    if (loadHostCache)
                    {
                        (byte[] hostCode, CachedShaderStage[] shaders) = ReadHostCode(
                            context,
                            ref hostTocFileStream,
                            ref hostDataFileStream,
                            guestShaders,
                            programIndex,
                            header.Timestamp);

                        bool vulkan = context.Capabilities.Api == TargetApi.Vulkan;
'''
LOOP_NEW = '''                int programIndex = 0;

                // RewindBox (adapt_shader_cache_parallel_read): one pass per entry of the table, as the loop on the
                // stream's position made them; a truncated last entry is a pass too (its read throws).
                int entries = (int)((tocFileStream.Length - tocFileStream.Position + sizeof(ulong) - 1) / sizeof(ulong));

                readAhead = new ProgramReadAhead(
                    this,
                    context,
                    loadHostCache,
                    header.Timestamp,
                    tocFileStream,
                    dataFileStream,
                    guestTocFileStream,
                    guestDataFileStream,
                    entries);

                while (programIndex < entries && loader.Active)
                {
                    ProgramRead read = readAhead.Take(programIndex);

                    long taken = System.Diagnostics.Stopwatch.GetTimestamp();
                    bool isCompute = read.IsCompute;
                    GuestCodeAndCbData?[] guestShaders = read.GuestShaders;
                    ShaderSpecializationState specState = read.SpecState;

                    if (loadHostCache)
                    {
                        (byte[] hostCode, CachedShaderStage[] shaders) = (read.HostCode, read.Shaders);

                        bool vulkan = context.Capabilities.Api == TargetApi.Vulkan;
'''

END_OLD = '''                    programIndex++;
                    if ((programIndex & 7) == 0)
                    {
                        loader.CheckCompilation();
                    }
                }
            }
            finally
            {
                _guestStorage.ClearMemoryCache();

                hostTocFileStream?.Dispose();
                hostDataFileStream?.Dispose();
            }
        }
'''
END_NEW = '''                    programIndex++;

                    long queued = System.Diagnostics.Stopwatch.GetTimestamp();
                    createTicks += queued - taken;

                    if ((programIndex & 7) == 0)
                    {
                        loader.CheckCompilation();
                        checkTicks += System.Diagnostics.Stopwatch.GetTimestamp() - queued;
                    }
                }

                completed = programIndex == entries;
            }
            finally
            {
                // RewindBox (adapt_shader_cache_parallel_read): the reading threads have ended, and every host stream is
                // closed, before the guest codes they share are dropped and before the loader goes on (it may rebuild
                // the files).
                readAhead?.End(completed, !loader.Active, createTicks, checkTicks);

                _guestStorage.ClearMemoryCache();
            }
        }
'''

SIGNATURE_OLD = '''            int programIndex,
            ulong expectedTimestamp)
        {
            if (tocFileStream == null && dataFileStream == null)
'''
SIGNATURE_NEW = '''            int programIndex,
            ulong expectedTimestamp,
            uint maximumSize = uint.MaxValue)
        {
            if (tocFileStream == null && dataFileStream == null)
'''

CODE_OLD = '''            dataFileStream.Seek((long)offsetAndSize.Offset, SeekOrigin.Begin);

            byte[] hostCode = new byte[offsetAndSize.UncompressedSize];

            BinarySerializer.ReadCompressed(dataFileStream, hostCode);
'''
CODE_NEW = '''            dataFileStream.Seek((long)offsetAndSize.Offset, SeekOrigin.Begin);

            // RewindBox (adapt_shader_cache_parallel_read): a thread reading ahead of the GPU thread does not read a host
            // code above the size it gives; the GPU thread, which gives none, reads it when it reaches the program.
            if (offsetAndSize.UncompressedSize > maximumSize)
            {
                return (_hostCodeLeftToCaller, null);
            }

            byte[] hostCode = new byte[offsetAndSize.UncompressedSize];

            BinarySerializer.ReadCompressed(dataFileStream, hostCode);
'''

USING_OLD = '''using System.Runtime.CompilerServices;

namespace Ryujinx.Graphics.Gpu.Shader.DiskCache
{
    /// <summary>
    /// On-disk shader cache storage for host code.
    /// </summary>
'''
USING_NEW = '''using System.Runtime.CompilerServices;
using System.Threading; // RewindBox (adapt_shader_cache_parallel_read)

namespace Ryujinx.Graphics.Gpu.Shader.DiskCache
{
    /// <summary>
    /// On-disk shader cache storage for host code.
    /// </summary>
'''

GUEST_OLD = '''        public GuestCodeAndCbData LoadShader(Stream tocFileStream, Stream dataFileStream, int index)
        {
            if (_cache == null || index >= _cache.Length)
            {
                _cache = new (byte[], byte[])[Math.Max(index + 1, GetShadersCountFromLength(tocFileStream.Length))];
            }

            (byte[] guestCode, byte[] cb1Data) = _cache[index];

            if (guestCode == null || cb1Data == null)
            {
                BinarySerializer tocReader = new(tocFileStream);
                tocFileStream.Seek(Unsafe.SizeOf<TocHeader>() + index * Unsafe.SizeOf<TocEntry>(), SeekOrigin.Begin);

                TocEntry entry = new();
                tocReader.Read(ref entry);

                guestCode = new byte[entry.CodeSize];
                cb1Data = new byte[entry.Cb1DataSize];

                if (entry.Offset >= (ulong)dataFileStream.Length)
                {
                    throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric);
                }

                dataFileStream.Seek((long)entry.Offset, SeekOrigin.Begin);
                dataFileStream.ReadExactly(cb1Data);
                BinarySerializer.ReadCompressed(dataFileStream, guestCode);

                _cache[index] = (guestCode, cb1Data);
            }

            return new GuestCodeAndCbData(guestCode, cb1Data);
        }
'''
GUEST_NEW = '''        public GuestCodeAndCbData LoadShader(Stream tocFileStream, Stream dataFileStream, int index)
        {
            // RewindBox (adapt_shader_cache_parallel_read): several threads read the programs of a load, each with its own
            // streams. A code is still read once and every program gets the same arrays for the same index: a thread that
            // needs a code another thread is reading waits for it (one lock per index, sixteen for all the indices), and
            // _cacheLock guards the table. One thread alone runs the statements it ran, in their order.
            byte[] guestCode;
            byte[] cb1Data;

            lock (_cacheLock)
            {
                if (_cache == null || index >= _cache.Length)
                {
                    // The codes already read stay in the table (it was made anew). Only an index past the table of
                    // contents comes here with codes read, and its read below throws: one thread never saw the
                    // difference, but a thread reading ahead must not take away the codes of the programs before it.
                    Array.Resize(ref _cache, Math.Max(index + 1, GetShadersCountFromLength(tocFileStream.Length)));
                }

                (guestCode, cb1Data) = _cache[index];
            }

            if (guestCode == null || cb1Data == null)
            {
                lock (_readLocks[index % _readLocks.Length])
                {
                    lock (_cacheLock)
                    {
                        (guestCode, cb1Data) = _cache[index];
                    }

                    if (guestCode == null || cb1Data == null)
                    {
                        BinarySerializer tocReader = new(tocFileStream);
                        tocFileStream.Seek(Unsafe.SizeOf<TocHeader>() + index * Unsafe.SizeOf<TocEntry>(), SeekOrigin.Begin);

                        TocEntry entry = new();
                        tocReader.Read(ref entry);

                        guestCode = new byte[entry.CodeSize];
                        cb1Data = new byte[entry.Cb1DataSize];

                        if (entry.Offset >= (ulong)dataFileStream.Length)
                        {
                            throw new DiskCacheLoadException(DiskCacheLoadResult.FileCorruptedGeneric);
                        }

                        dataFileStream.Seek((long)entry.Offset, SeekOrigin.Begin);
                        dataFileStream.ReadExactly(cb1Data);
                        BinarySerializer.ReadCompressed(dataFileStream, guestCode);

                        lock (_cacheLock)
                        {
                            _cache[index] = (guestCode, cb1Data);
                        }
                    }
                }
            }

            return new GuestCodeAndCbData(guestCode, cb1Data);
        }

        // RewindBox (adapt_shader_cache_parallel_read): see LoadShader.
        private readonly object _cacheLock = new();
        private readonly object[] _readLocks = NewReadLocks();

        private static object[] NewReadLocks()
        {
            object[] locks = new object[16];

            for (int index = 0; index < locks.Length; index++)
            {
                locks[index] = new object();
            }

            return locks;
        }
'''

PAIRS = [
    (STORAGE, USING_OLD, USING_NEW),
    (STORAGE, FIELD_OLD, FIELD_NEW),
    (STORAGE, LOAD_OLD, LOAD_NEW),
    (STORAGE, LOOP_OLD, LOOP_NEW),
    (STORAGE, END_OLD, END_NEW),
    (STORAGE, SIGNATURE_OLD, SIGNATURE_NEW),
    (STORAGE, CODE_OLD, CODE_NEW),
    (GUEST, GUEST_OLD, GUEST_NEW),
]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
