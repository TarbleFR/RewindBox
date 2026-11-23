// Fixture of test/melonx_variant_journal_capacity_test.py: the production PipelineVariantJournal of one variant (control
// or candidate), spliced at __JOURNAL__ as PipelineCacheManager.cs holds it, with the logger, the engine journal and
// EncodingPolicy replaced by doubles. Journal files are written here in the file's format (header, framed lines, the
// checksums) so that old, foreign, over-long and damaged files can be made; the real loader reads them. A program that
// replays is a double: Schedule only notes the record and completes on the thread pool (no Vulkan, no device).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Ryujinx.Common.Logging
{
    public enum LogClass { Gpu }

    public struct Log
    {
        public void PrintMsg(LogClass logClass, string message)
        {
            lock (Logger.Warnings)
            {
                Logger.Warnings.Add(message);
            }
        }
    }

    public static class Logger
    {
        public static readonly List<string> Warnings = new();
        public static Log? Warning = new Log();
        public static Log? Info = new Log();
    }
}

namespace Ryujinx.Common
{
    public static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Loaded = new();

        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        {
            if (stage == "pipelineVariants" && status == "loaded")
            {
                lock (Loaded)
                {
                    Loaded.Add(detail);
                }
            }
        }
    }
}

namespace Ryujinx.Graphics.Vulkan
{
    using Ryujinx.Common.Logging;

    static class EncodingPolicy
    {
        public static bool IncrementalArrayDescriptors;
    }

//__JOURNAL__

    // A state of a title: its program and its variant bytes (the journal only frames and checksums them).
    sealed class Item
    {
        public ulong Program;
        public byte[] Variant;
        public uint LastSession;
        public ushort Sessions;
        public uint FirstSeenMs;
        public uint CostMs;
        public ulong Id => PipelineVariantJournal.Checksum64(Variant);
    }

    sealed class Target : PipelineVariantJournal.ITarget
    {
        public readonly Dictionary<(ulong, ulong), PipelineVariantJournal.Record> Built = new();
        public int Scheduled, Repeats, InFlight, MostInFlight;

        public Task<long> Schedule(PipelineVariantJournal.Record record)
        {
            lock (Built)
            {
                Scheduled++;

                if (!Built.TryAdd((record.Program, record.Id), record))
                {
                    Repeats++;
                }

                InFlight++;
                MostInFlight = Math.Max(MostInFlight, InFlight);
            }

            return Task.Run(() =>
            {
                Thread.SpinWait(200);

                lock (Built)
                {
                    InFlight--;
                }

                return 1L;
            });
        }
    }

    static class Fixture
    {
        const int TypicalBytes = 420; // 5 vertex attributes, 2 bindings, 2 colour attachments
        const int LargestBytes = 1444; // the codec's largest variant
        const int LargestLine = 2 + 33 + LargestBytes + 4;
        const int MarkerLine = 28;

        static readonly Dictionary<string, object> Report = new();
        static string _directory;

        static ulong Schema => PipelineVariantJournal.Schema;

        static uint Fold(ReadOnlySpan<byte> body)
        {
            ulong hash = PipelineVariantJournal.Checksum64(body);

            return (uint)hash ^ (uint)(hash >> 32);
        }

        static byte[] Header(uint magic, uint version, ulong schema)
        {
            byte[] header = new byte[16];
            BitConverter.TryWriteBytes(header.AsSpan(0, 4), magic);
            BitConverter.TryWriteBytes(header.AsSpan(4, 4), version);
            BitConverter.TryWriteBytes(header.AsSpan(8, 8), schema);

            return header;
        }

        static byte[] Line(Item item)
        {
            int bodyLength = 33 + item.Variant.Length;
            byte[] line = new byte[2 + bodyLength + 4];
            Span<byte> body = line.AsSpan(2, bodyLength);

            BitConverter.TryWriteBytes(line.AsSpan(0, 2), (ushort)bodyLength);
            body[0] = 1;
            BitConverter.TryWriteBytes(body.Slice(1, 8), item.Program);
            BitConverter.TryWriteBytes(body.Slice(9, 8), item.Id);
            BitConverter.TryWriteBytes(body.Slice(17, 4), item.LastSession);
            BitConverter.TryWriteBytes(body.Slice(21, 2), item.Sessions);
            BitConverter.TryWriteBytes(body.Slice(23, 4), item.FirstSeenMs);
            BitConverter.TryWriteBytes(body.Slice(27, 4), item.CostMs);
            BitConverter.TryWriteBytes(body.Slice(31, 2), (ushort)item.Variant.Length);
            item.Variant.CopyTo(body[33..]);
            BitConverter.TryWriteBytes(line.AsSpan(2 + bodyLength, 4), Fold(body));

            return line;
        }

        static void WriteFile(string path, IEnumerable<Item> lines, uint version = PipelineVariantJournal.Version, ulong? schema = null,
            uint magic = PipelineVariantJournal.Magic)
        {
            using FileStream stream = new(path, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 16);
            stream.Write(Header(magic, version, schema ?? Schema));

            foreach (Item item in lines)
            {
                stream.Write(Line(item));
            }
        }

        static Item Make(Random random, ulong program, int bytes, uint lastSession, ushort sessions, uint costMs = 3)
        {
            byte[] variant = new byte[bytes];
            random.NextBytes(variant);

            return new Item
            {
                Program = program,
                Variant = variant,
                LastSession = lastSession,
                Sessions = sessions,
                FirstSeenMs = (uint)random.Next(1000, 600_000),
                CostMs = costMs,
            };
        }

        static Item With(Item item, uint lastSession, ushort sessions) => new()
        {
            Program = item.Program,
            Variant = item.Variant,
            LastSession = lastSession,
            Sessions = sessions,
            FirstSeenMs = item.FirstSeenMs,
            CostMs = item.CostMs,
        };

        static PipelineVariantJournal Open(string path, bool policy = false)
        {
            EncodingPolicy.IncrementalArrayDescriptors = policy;

            return new PipelineVariantJournal(path, Schema, () => 100, loadInBackground: false, primaryCacheReady: policy ? () => true : null);
        }

        static string LastLoaded()
        {
            lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Loaded)
            {
                return Ryujinx.Common.EmbeddedLaunchDiagnostics.Loaded[^1];
            }
        }

        // Every line a session queued is written: the journal appends on the thread pool. Quiet means nothing pending,
        // nothing completed and the file unchanged over 8 polls.
        static void Settle(string path)
        {
            long completed = -1, length = -1;
            int quiet = 0;
            Stopwatch watch = Stopwatch.StartNew();

            while (quiet < 8)
            {
                Thread.Sleep(15);

                long nowCompleted = ThreadPool.CompletedWorkItemCount;
                long nowLength = File.Exists(path) ? new FileInfo(path).Length : 0;

                quiet = ThreadPool.PendingWorkItemCount == 0 && nowCompleted == completed && nowLength == length ? quiet + 1 : 0;
                completed = nowCompleted;
                length = nowLength;

                if (watch.ElapsedMilliseconds > 120_000)
                {
                    throw new InvalidOperationException("the journal's appends did not settle");
                }
            }
        }

        // Every program offers its states; returns once each loaded state was scheduled or refused.
        static Target Replay(PipelineVariantJournal journal, IEnumerable<ulong> programs)
        {
            Target target = new();

            foreach (ulong program in programs.Distinct())
            {
                journal.Offer(program, target);
            }

            Stopwatch watch = Stopwatch.StartNew();

            while (journal.Replayed + journal.ReplayFailed + journal.ReplayTemporary + journal.ReplaySkipped < journal.Loaded)
            {
                Thread.Sleep(5);

                if (watch.ElapsedMilliseconds > 120_000)
                {
                    break;
                }
            }

            return target;
        }

        static void Note(PipelineVariantJournal journal, Item item, bool builtForSkipped = false) =>
            journal.NoteLate(item.Program, item.Variant, item.CostMs, joined: false, replayJoined: false, builtForSkipped: builtForSkipped);

        static string Journal(string summary) => summary[summary.IndexOf("Journal: ", StringComparison.Ordinal)..];

        // --- A session shaped like Hogwarts Legacy's session 40 in the IPA 821 log (counts only) ---
        // The title's file as the load for session 40 found it: 3330 lines for 2028 states of 426 programs met in sessions
        // 32 to 39 and 33 states last met in session 31. The session meets 1168 of the loaded states (853 created late by
        // a draw, 315 built for skipped draws) and 398 states the journal does not know (211 created late, 187 built for
        // skipped draws), in the order of a session: old and new states mixed. Then the next launch: every program offers
        // its states, and the player draws everything both sessions drew.
        static void LogSession(string name, bool policy)
        {
            Random random = new(821);
            const int Programs = 426, Loaded = 2028, Stale = 33, Lines = 3330, Frequent = 1168;
            const int LatePlanned = 853, LateNew = 211, SkippedNew = 187;
            List<Item> loaded = new();

            for (int index = 0; index < Loaded; index++)
            {
                bool frequent = index < Frequent;

                // The states a session meets again are those met most often; the others were met in 1 to 3 sessions.
                loaded.Add(Make(random, 0x1000UL + (ulong)(index % Programs), random.Next(360, 481),
                    frequent ? 39u : (uint)random.Next(33, 39), frequent ? (ushort)random.Next(4, 9) : (ushort)random.Next(1, 4)));
            }

            List<Item> stale = new();

            for (int index = 0; index < Stale; index++)
            {
                stale.Add(Make(random, 0x1000UL + (ulong)(index % Programs), random.Next(360, 481), 31, 1));
            }

            // 3330 lines: an older line of 1269 of the kept states (a refresh was appended after it), then every state.
            List<Item> lines = new();

            for (int index = 0; index < Lines - Loaded - Stale; index++)
            {
                Item item = loaded[index];
                lines.Add(With(item, item.LastSession - 1, (ushort)Math.Max(1, item.Sessions - 1)));
            }

            lines.AddRange(stale);
            lines.AddRange(loaded);

            string path = Path.Combine(_directory, name + ".variants");
            WriteFile(path, lines);

            PipelineVariantJournal journal = Open(path, policy);
            Dictionary<string, object> report = new()
            {
                ["loadedLine"] = LastLoaded(),
                ["loaded"] = journal.Loaded,
                ["session"] = journal.Session,
            };

            List<Item> fresh = new();

            for (int index = 0; index < LateNew + SkippedNew; index++)
            {
                fresh.Add(Make(random, 0x1000UL + (ulong)random.Next(Programs), random.Next(360, 481), 0, 0));
            }

            // (item, built for a skipped draw): the loaded states met and the new ones, mixed.
            List<(Item Item, bool Skipped)> events = new();

            for (int index = 0; index < Frequent; index++)
            {
                events.Add((loaded[index], index >= LatePlanned));
            }

            for (int index = 0; index < fresh.Count; index++)
            {
                events.Add((fresh[index], index >= LateNew));
            }

            foreach ((Item item, bool skipped) in events.OrderBy(_ => random.Next()).ToList())
            {
                Note(journal, item, skipped);
            }

            Settle(path);

            string summary = journal.Summary("session, at close");
            report["summary"] = summary;
            report["journal"] = Journal(summary);
            report["lateNew"] = journal.LateNew;
            report["latePlanned"] = journal.LatePlanned;
            report["builtForSkipped"] = journal.DrawQueued;
            report["evicted"] = journal.Evicted;
            report["notRecorded"] = journal.NotRecorded;
            report["compactions"] = journal.Compactions;
            report["linesNotWritten"] = journal.LinesNotWritten;
            report["fileBytes"] = new FileInfo(path).Length;
            journal.Stop();

            // The next launch.
            List<Item> known = loaded.Concat(fresh).ToList();
            PipelineVariantJournal next = Open(path, policy);

            report["nextLoadedLine"] = LastLoaded();
            report["nextLoaded"] = next.Loaded;
            report["nextGivenUpAtLoad"] = next.GivenUpAtLoad;

            Target target = Replay(next, known.Select(item => item.Program));

            report["nextReplayed"] = next.Replayed;
            report["nextScheduledTwice"] = target.Repeats;
            report["nextMostInFlight"] = target.MostInFlight;

            int ready = 0, late = 0;

            foreach (Item item in known)
            {
                if (target.Built.TryGetValue((item.Program, item.Id), out PipelineVariantJournal.Record record))
                {
                    next.NoteReplayUsed(record);
                    ready++;
                }
                else
                {
                    Note(next, item);
                    late++;
                }
            }

            Settle(path);
            report["nextStatesDrawn"] = known.Count;
            report["nextReadyBeforeFirstDraw"] = next.ReadyBeforeUse;
            report["nextLateCreations"] = next.LateNew + next.LatePlanned;
            report["nextLateNew"] = next.LateNew;
            report["nextNotRecorded"] = next.NotRecorded;
            report["nextJournal"] = Journal(next.Summary("session, at close"));
            report["nextReady"] = ready;
            report["nextLate"] = late;
            next.Stop();

            Report[name] = report;
        }

        // The file a session like the log's left (name), copied before the next launch touched it, is kept for the other
        // variant: LogSession writes it again here and stops before the next launch.
        static void LeaveSessionFile(string name)
        {
            Random random = new(821);
            const int Programs = 426, Loaded = 2028, Frequent = 1168, New = 398;
            List<Item> loaded = new();

            for (int index = 0; index < Loaded; index++)
            {
                bool frequent = index < Frequent;
                loaded.Add(Make(random, 0x1000UL + (ulong)(index % Programs), random.Next(360, 481),
                    frequent ? 39u : (uint)random.Next(33, 39), frequent ? (ushort)random.Next(4, 9) : (ushort)random.Next(1, 4)));
            }

            string path = Path.Combine(_directory, name + ".variants");
            WriteFile(path, loaded);

            PipelineVariantJournal journal = Open(path);

            for (int index = 0; index < Frequent; index++)
            {
                Note(journal, loaded[index]);
            }

            for (int index = 0; index < New; index++)
            {
                Note(journal, Make(random, 0x1000UL + (ulong)random.Next(Programs), random.Next(360, 481), 0, 0));
            }

            Settle(path);
            journal.Stop();
            Report[name] = new Dictionary<string, object>
            {
                ["journal"] = Journal(journal.Summary("session, at close")),
                ["path"] = path,
                ["fileBytes"] = new FileInfo(path).Length,
            };
        }

        // The other variant's file (a build before or after the adapter), loaded and replayed by this one.
        static void Cross(string path)
        {
            string copy = Path.Combine(_directory, "cross.variants");
            File.Copy(path, copy, overwrite: true);

            PipelineVariantJournal journal = Open(copy);
            List<ulong> programs = Enumerable.Range(0, 426).Select(index => 0x1000UL + (ulong)index).ToList();
            Target target = Replay(journal, programs);

            Settle(copy);
            Report["cross"] = new Dictionary<string, object>
            {
                ["loadedLine"] = LastLoaded(),
                ["loaded"] = journal.Loaded,
                ["givenUpAtLoad"] = journal.GivenUpAtLoad,
                ["replayed"] = journal.Replayed,
                ["fileBytesAfter"] = new FileInfo(copy).Length,
                ["warnings"] = Logger.Warnings.Count,
            };
            journal.Stop();
        }

        // --- The bounds: disk, states held, replays ---
        static void Bounds()
        {
            Random random = new(4096);
            int max = PipelineVariantJournal.MaxRecords;
            long fileBound = PipelineVariantJournal.MaxFileBytes;
            string path = Path.Combine(_directory, "bounds.variants");
            List<Item> items = new();
            long mostBytes = 0;

            // Session 1: a journal filled with the largest variants.
            PipelineVariantJournal first = Open(path);

            for (int index = 0; index < max; index++)
            {
                items.Add(Make(random, 0x2000UL + (ulong)(index % 400), LargestBytes, 0, 0));
                Note(first, items[index]);
            }

            Settle(path);
            mostBytes = Math.Max(mostBytes, new FileInfo(path).Length);

            Dictionary<string, object> report = new()
            {
                ["maxRecords"] = max,
                ["maxFileBytes"] = fileBound,
                ["maxReplays"] = PipelineVariantJournal.MaxReplaysPerSession,
                ["recentSessions"] = PipelineVariantJournal.RecentSessions,
                ["largestCompaction"] = (long)max * LargestLine + 9L * PipelineVariantJournal.MaxReplaysPerSession * MarkerLine + 16,
                ["filledBytes"] = new FileInfo(path).Length,
                ["filledJournal"] = Journal(first.Summary("session")),
                ["filledNotRecorded"] = first.NotRecorded,
            };
            first.Stop();

            // Session 2: every state replayed and used (a refresh line each: the file passes its bound and is compacted).
            PipelineVariantJournal second = Open(path);
            Stopwatch offers = Stopwatch.StartNew();
            Target target = Replay(second, items.Select(item => item.Program));

            report["replayMs"] = offers.ElapsedMilliseconds;
            report["replayLoaded"] = second.Loaded;
            report["replayed"] = second.Replayed;
            report["replayScheduled"] = target.Scheduled;
            report["replayScheduledTwice"] = target.Repeats;
            report["replayMostInFlight"] = target.MostInFlight;
            report["replaySummaryPlanned"] = second.Summary("session").Contains($"still planned 0 of {max},");

            int used = 0;

            foreach (PipelineVariantJournal.Record record in target.Built.Values.ToList())
            {
                second.NoteReplayUsed(record);

                if (++used % 512 == 0)
                {
                    Settle(path);
                    mostBytes = Math.Max(mostBytes, new FileInfo(path).Length);
                }
            }

            Settle(path);
            mostBytes = Math.Max(mostBytes, new FileInfo(path).Length);
            report["refreshCompactions"] = second.Compactions;
            report["refreshLinesNotWritten"] = second.LinesNotWritten;
            report["refreshNotRecorded"] = second.NotRecorded;
            second.Stop();

            // Session 3: every state is there, last met in session 2.
            PipelineVariantJournal third = Open(path);

            report["afterRefreshLoaded"] = third.Loaded;
            report["afterRefreshLine"] = LastLoaded();
            report["afterRefreshSession"] = third.Session;

            // A full journal, nothing met yet, and 500 states it does not know: it gives up as many and stays at its bound.
            for (int index = 0; index < 500; index++)
            {
                Note(third, Make(random, 0x2000UL + (ulong)(index % 400), LargestBytes, 0, 0));
            }

            Settle(path);
            mostBytes = Math.Max(mostBytes, new FileInfo(path).Length);
            report["overEvicted"] = third.Evicted;
            report["overNotRecorded"] = third.NotRecorded;
            report["overJournal"] = Journal(third.Summary("session"));
            report["overLinesNotWritten"] = third.LinesNotWritten;
            third.Stop();

            PipelineVariantJournal fourth = Open(path);

            report["overNextLoaded"] = fourth.Loaded;
            report["overNextGivenUpAtLoad"] = fourth.GivenUpAtLoad;
            fourth.Stop();
            Settle(path);
            mostBytes = Math.Max(mostBytes, new FileInfo(path).Length);
            report["mostFileBytes"] = mostBytes;
            report["warnings"] = Logger.Warnings.Count;
            Report["bounds"] = report;
        }

        // --- The load's cost: a full journal of usual states after a session that refreshed every one ---
        static void LoadCost()
        {
            Random random = new(7);
            int max = PipelineVariantJournal.MaxRecords;
            string path = Path.Combine(_directory, "cost.variants");
            List<Item> items = new();

            for (int index = 0; index < max; index++)
            {
                items.Add(Make(random, 0x3000UL + (ulong)(index % 426), TypicalBytes, 9, 3));
            }

            WriteFile(path, items.Select(item => With(item, 8, 2)).Concat(items));

            long fileBytes = new FileInfo(path).Length;

            Open(path).Stop(); // the first load pays the runtime's start
            WriteFile(path, items.Select(item => With(item, 8, 2)).Concat(items));

            GC.Collect();
            GC.WaitForPendingFinalizers();
            GC.Collect();

            long heapBefore = GC.GetTotalMemory(true);
            long allocatedBefore = GC.GetAllocatedBytesForCurrentThread();
            Stopwatch watch = Stopwatch.StartNew();
            PipelineVariantJournal journal = Open(path);
            double loadMs = watch.Elapsed.TotalMilliseconds;
            long allocated = GC.GetAllocatedBytesForCurrentThread() - allocatedBefore;
            long heap = GC.GetTotalMemory(true) - heapBefore;

            // Every program offers its states (426 offers, each sorts what is ready), nothing replays: the device is short.
            PipelineVariantJournal held = new(path, Schema, () => 0, loadInBackground: false);
            Target target = new();
            watch.Restart();

            for (ulong program = 0; program < 426; program++)
            {
                held.Offer(0x3000UL + program, target);
            }

            double offerMs = watch.Elapsed.TotalMilliseconds;

            Report["loadCost"] = new Dictionary<string, object>
            {
                ["states"] = journal.Loaded,
                ["fileBytes"] = fileBytes,
                ["loadMs"] = Math.Round(loadMs, 1),
                ["loadAllocatedBytes"] = allocated,
                ["heapBytesHeld"] = heap,
                ["heapBytesPerState"] = heap / Math.Max(1, journal.Loaded),
                ["offers"] = 426,
                ["offersMs"] = Math.Round(offerMs, 1),
                ["heldScheduled"] = target.Scheduled,
                ["memoryHolds"] = held.MemoryHolds,
            };
            GC.KeepAlive(journal);
            journal.Stop();
            held.Stop();
        }

        // --- Files of another format, damaged, torn or over-long: ignored or read up to the damage, never thrown ---
        static Dictionary<string, object> LoadOf(string name, Action<string> write, bool reopen = true)
        {
            string path = Path.Combine(_directory, name + ".variants");
            write(path);

            int warnings = Logger.Warnings.Count;
            Dictionary<string, object> report = new();

            try
            {
                long allocatedBefore = GC.GetAllocatedBytesForCurrentThread();
                PipelineVariantJournal journal = Open(path);

                report["allocatedBytes"] = GC.GetAllocatedBytesForCurrentThread() - allocatedBefore;
                report["loaded"] = journal.Loaded;
                report["dropped"] = journal.Dropped;
                report["givenUpAtLoad"] = journal.GivenUpAtLoad;
                report["line"] = LastLoaded();
                report["fileBytesAfter"] = File.Exists(path) ? new FileInfo(path).Length : -1;

                if (reopen)
                {
                    // The journal still records: a state noted now is there at the next load.
                    Item item = Make(new Random(name.GetHashCode(StringComparison.Ordinal)), 0x4000, TypicalBytes, 0, 0);

                    Note(journal, item);
                    Settle(path);
                    journal.Stop();

                    PipelineVariantJournal next = Open(path);

                    report["nextLoaded"] = next.Loaded;
                    report["nextUnreadable"] = LastLoaded().Contains(" 0 unreadable");
                    next.Stop();
                }
                else
                {
                    journal.Stop();
                }

                report["threw"] = false;
            }
            catch (Exception exception)
            {
                report["threw"] = true;
                report["exception"] = exception.GetType().Name;
            }

            report["warnings"] = Logger.Warnings.Count - warnings;

            return report;
        }

        static void Loads()
        {
            Random random = new(99);
            List<Item> hundred = new();

            for (int index = 0; index < 100; index++)
            {
                hundred.Add(Make(random, 0x4100UL + (ulong)(index % 20), TypicalBytes, 5, 2));
            }

            Dictionary<string, object> report = new();

            report["good"] = LoadOf("good", path => WriteFile(path, hundred));
            report["otherVersion"] = LoadOf("otherVersion", path => WriteFile(path, hundred, version: PipelineVariantJournal.Version + 1));
            report["olderVersion"] = LoadOf("olderVersion", path => WriteFile(path, hundred, version: 0));
            report["otherSchema"] = LoadOf("otherSchema", path => WriteFile(path, hundred, schema: Schema ^ 1));
            report["otherMagic"] = LoadOf("otherMagic", path => WriteFile(path, hundred, magic: 0x12345678));
            report["empty"] = LoadOf("empty", path => File.WriteAllBytes(path, Array.Empty<byte>()));
            report["shortHeader"] = LoadOf("shortHeader", path => File.WriteAllBytes(path, Header(PipelineVariantJournal.Magic, PipelineVariantJournal.Version, Schema)[..9]));
            report["headerOnly"] = LoadOf("headerOnly", path => WriteFile(path, Array.Empty<Item>()));
            report["tornTail"] = LoadOf("tornTail", path =>
            {
                WriteFile(path, hundred);

                using FileStream stream = new(path, FileMode.Open, FileAccess.Write);
                stream.SetLength(stream.Length - 200);
            });
            report["flippedByte"] = LoadOf("flippedByte", path =>
            {
                WriteFile(path, hundred);

                byte[] data = File.ReadAllBytes(path);
                data[16 + 50 * (2 + 33 + TypicalBytes + 4) + 120] ^= 0x40;
                File.WriteAllBytes(path, data);
            });
            report["lyingLength"] = LoadOf("lyingLength", path =>
            {
                WriteFile(path, hundred);

                using FileStream stream = new(path, FileMode.Append, FileAccess.Write);
                stream.Write(new byte[] { 0xFF, 0xFF, 1, 2, 3 });
            });
            report["garbageAfterHeader"] = LoadOf("garbageAfterHeader", path =>
            {
                byte[] noise = new byte[256 * 1024];
                new Random(5).NextBytes(noise);
                Header(PipelineVariantJournal.Magic, PipelineVariantJournal.Version, Schema).CopyTo(noise, 0);
                File.WriteAllBytes(path, noise);
            });
            report["garbage"] = LoadOf("garbage", path =>
            {
                byte[] noise = new byte[256 * 1024];
                new Random(6).NextBytes(noise);
                File.WriteAllBytes(path, noise);
            });
            report["zeroLengthLines"] = LoadOf("zeroLengthLines", path =>
            {
                using FileStream stream = new(path, FileMode.Create, FileAccess.Write);
                stream.Write(Header(PipelineVariantJournal.Magic, PipelineVariantJournal.Version, Schema));
                stream.Write(new byte[64 * 1024]);
            });

            // Over-long: 40 MiB of valid lines, every state different (87 000 states), last met in the last session.
            const long OverLongBytes = 40L * 1024 * 1024;
            int overLongLines = 0;

            report["overLong"] = LoadOf("overLong", path =>
            {
                Random states = new(40);

                using FileStream stream = new(path, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 16);
                stream.Write(Header(PipelineVariantJournal.Magic, PipelineVariantJournal.Version, Schema));

                while (stream.Position < OverLongBytes)
                {
                    stream.Write(Line(Make(states, 0x5000UL + (ulong)(overLongLines % 426), TypicalBytes, 7, 1)));
                    overLongLines++;
                }
            });
            report["overLongBytes"] = OverLongBytes;
            report["overLongLines"] = overLongLines;
            report["typicalLine"] = 2 + 33 + TypicalBytes + 4;

            Report["loads"] = report;
        }

        static int Main(string[] arguments)
        {
            _directory = arguments[1];
            Directory.CreateDirectory(_directory);
            Report["variant"] = arguments[0];

            switch (arguments[2])
            {
                case "main":
                    LogSession("session", policy: false);
                    LogSession("sessionPolicy", policy: true);
                    LeaveSessionFile("left");
                    Bounds();
                    LoadCost();
                    Loads();
                    break;
                case "cross":
                    Cross(arguments[3]);
                    break;
                default:
                    return 2;
            }

            Console.WriteLine(JsonSerializer.Serialize(Report));

            return 0;
        }
    }
}
