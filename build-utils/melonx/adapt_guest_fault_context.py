"""Name the guest thread, its control registers and its guest stack when a guest memory fault ends the process.

IPA 658, 5 November 2026, second player (private Core journals, not in the repository): both in-game crashes of build
658 (pids 79315 and 80176, 03:50:13 and 04:01:34 UTC) are an unhandled InvalidMemoryRegionException from the native
page-table guard: one write at page offset 0x003 on guest thread 32, one read at page offset 0x018 on guest thread 80,
each an access to a never-mapped guest page (a null-based pointer). Each Core journal holds the guard message (offset,
size, write, guest thread id, last guest dispatch address, faultPcKnown=False) and nothing else: neither the guest
thread's name nor its code location, so the faulting game code (a hang detector killing the game after a stall, or a
null dereference from wrong emulation) cannot be told apart.

Mechanism (read in the Core 658 preparation):
- NativePageTable (src/Ryujinx.Cpu/Jit/HostTracked/NativePageTable.cs) points every unmapped page at a host guard page;
  a JIT access faults there and VirtualMemoryEvent throws InvalidMemoryRegionException with the message that
  adapt_guard_context extends (NativeInterface.DescribeLastGuestDispatch, which deliberately reads no guest memory).
- Nothing handles it on the guest thread, so AppDomain.UnhandledException runs on that thread and
  native/melonx/EmbeddedRuntime.cs journals it (EmbeddedLaunchDiagnostics.RecordCrash: 250 ms gate, written past the
  journal ceiling), then the process ends.
- Upstream's software-MMU path prints the guest stack and registers first (KProcess.InvalidAccessHandler:
  KThread.PrintGuestStackTrace and PrintGuestRegisterPrintout, through HleProcessDebugger). KernelStatic, KThread and
  the debugger are internal to Ryujinx.HLE, so the Library's handler cannot reach them.

Change (KernelStatic.cs, plus the crash handler in native/melonx/EmbeddedRuntime.cs):
- a public GuestFaultContext.Describe(exception, budget) in Ryujinx.HLE: for an InvalidMemoryRegionException (or one
  in its inner-exception chain) raised on a thread that runs guest code (KernelStatic.GetCurrentThread() is not null),
  it returns one bounded text: guest thread id and name (KThread.GetThreadName), the FP, LR, SP and PC lines of
  KThread.GetGuestRegisterPrintout (module+offset and symbol when the debugger resolves them; values as of the last
  guest dispatch, stale inside a JIT block, so PC is the last dispatch, not the faulting instruction) and the
  KThread.GetGuestStackTrace frame-pointer walk (at most 32 frames). The walk and the name read only mapped guest pages
  (IsMapped checks, InvalidMemoryRegionException caught); each part is caught on its own, the whole runs on a
  background thread joined for at most the budget (250 ms from the handler), and the text is cut to 3600 characters
  (the journal keeps 4096). The general-purpose registers X0-X28 are not kept: the Core journal never retains register
  dumps (EmbeddedLaunchDiagnostics header).
- EmbeddedRuntime.cs registers a second UnhandledException handler, after the existing RecordCrash one, which writes
  that text as a second crash line (stage "crash", status "unhandledException", diagnostic starting
  "guestFaultContext;") right after the crash line. Any other exception, or a fault on a host thread, writes nothing.

Not changed: the guard, its message, the signal path, page tables, mappings, execution and every successful path;
nothing runs before the process is already ending. Not measured on an iPhone.
Fail closed on drift: KernelStatic.cs must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.HLE/HOS/Kernel/KernelStatic.cs': '9fe7ff30e550816e44f8429edf5488767698165a30febe0c598955b7ba8e0471',
}

CONTEXT_CLASS = '''
    // RewindBox (adapt_guest_fault_context): post-mortem context of a guest memory fault that ends the process. The
    // native page-table guard throws InvalidMemoryRegionException on the faulting guest thread and reads no guest memory
    // (adapt_guard_context); the Library's crash handler asks for this only after the crash line is written. Upstream's
    // software-MMU path prints the same stack and registers (KProcess.InvalidAccessHandler). Only the control registers
    // are kept: the Core journal never retains register dumps.
    public static class GuestFaultContext
    {
        private const int MaxFrameLines = 34;
        private const int MaxLength = 3600;

        public static string Describe(object error, int budgetMilliseconds)
        {
            try
            {
                if (!IsGuestMemoryFault(error))
                {
                    return null;
                }

                KThread thread = KernelStatic.GetCurrentThread();

                if (thread == null)
                {
                    return null;
                }

                return Capture(() => Collect(thread), budgetMilliseconds);
            }
            catch (Exception e)
            {
                return "guestFaultContext; unavailable=" + e.GetType().Name;
            }
        }

        internal static bool IsGuestMemoryFault(object error)
        {
            Exception exception = error as Exception;

            for (int depth = 0; exception != null && depth < 8; depth++, exception = exception.InnerException)
            {
                if (exception is Ryujinx.Memory.InvalidMemoryRegionException)
                {
                    return true;
                }
            }

            return false;
        }

        // The stack walk reads guest memory: bound it in time on a background thread the dying process does not wait for.
        internal static string Capture(Func<string> collect, int budgetMilliseconds)
        {
            string[] result = new string[1];

            Thread worker = new(() =>
            {
                string text;

                try
                {
                    text = collect();
                }
                catch (Exception e)
                {
                    text = "guestFaultContext; unavailable=" + e.GetType().Name;
                }

                Volatile.Write(ref result[0], text);
            })
            {
                IsBackground = true,
                Name = "RewindBox.GuestFaultContext",
            };

            worker.Start();

            if (!worker.Join(Math.Max(1, budgetMilliseconds)))
            {
                return "guestFaultContext; unavailable=timeout after " + budgetMilliseconds + " ms";
            }

            return Volatile.Read(ref result[0]);
        }

        internal static string Collect(KThread thread)
        {
            string name = Part(thread.GetThreadName);
            string registers = Part(thread.GetGuestRegisterPrintout);
            string stack = Part(thread.GetGuestStackTrace);

            return Format(thread.ThreadUid, name, registers, stack);
        }

        private static string Part(Func<string> read)
        {
            try
            {
                return read() ?? string.Empty;
            }
            catch (Exception e)
            {
                // Not "name=value" at a line start: the journal redactor would drop the line.
                return "(unavailable: " + e.GetType().Name + ")";
            }
        }

        internal static string Format(ulong threadUid, string name, string registers, string stack)
        {
            System.Text.StringBuilder text = new();

            text.Append("guestFaultContext; guestThread=").Append(threadUid).Append("; guestThreadName=").Append(Clean(name));
            text.Append("; registers as of the last guest dispatch (FP LR SP PC):");

            foreach (string line in (registers ?? string.Empty).Split('\\n'))
            {
                string register = line.Trim();

                if (register.StartsWith("FP:", StringComparison.Ordinal) || register.StartsWith("LR:", StringComparison.Ordinal) ||
                    register.StartsWith("SP:", StringComparison.Ordinal) || register.StartsWith("PC:", StringComparison.Ordinal) ||
                    register.StartsWith("(unavailable: ", StringComparison.Ordinal))
                {
                    text.Append('\\n').Append(Clean(register));
                }
            }

            text.Append("\\nguest stack:");

            int lines = 0;

            foreach (string line in (stack ?? string.Empty).Split('\\n'))
            {
                string frame = Clean(line);

                if (frame.Length == 0)
                {
                    continue;
                }

                if (++lines > MaxFrameLines)
                {
                    text.Append("\\n(more frames not kept)");

                    break;
                }

                text.Append('\\n').Append(frame);
            }

            return text.Length > MaxLength ? text.ToString(0, MaxLength) : text.ToString();
        }

        private static string Clean(string value)
        {
            System.Text.StringBuilder text = new();

            foreach (char c in (value ?? string.Empty).Trim())
            {
                text.Append(c == '\\t' ? ' ' : char.IsControl(c) ? '?' : c);
            }

            return text.ToString();
        }
    }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    kernel = paths['src/Ryujinx.HLE/HOS/Kernel/KernelStatic.cs']
    once(kernel, '''            return null;
        }
    }
}
''', '''            return null;
        }
    }
''' + CONTEXT_CLASS + '''}
''')
    return [kernel]
