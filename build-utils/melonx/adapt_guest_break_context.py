"""Write the game's own break (svcBreak) into the Core journal: its reason, the info it passes, the thread and the stack.

IPA 767, Super Smash Bros. Ultimate (pid 33274, 17 November 2026, private journals, counts only): after 29 minutes at 60
frames per second the game called svcBreak at 10:32:14 and the process ended (GuestBrokeExecutionException unhandled);
the app went back to the home screen. It was not iOS ending the process for memory: the last per-second line, in the
same second, reads footprint 4 995 MiB, 1 660 MiB still available to the process, device 9 % available, 237 pages read
from files; the last memory warning was at 10:18:41.
The Core journal holds only "The guest program broke execution!" and the managed stack of the break. Upstream prints the
guest stack and registers first (KThread.PrintGuestStackTrace and PrintGuestRegisterPrintout), at Info level: the Core
journal keeps warnings and errors only (native/melonx/EmbeddedRuntime.cs), and the stderr capture, where Info lines go,
had used its line budget by 10:06 (826 of its lines are MoltenVK's periodic statistics). So nothing says why the game
stopped: an assertion, an abort on a failed result from a service, or a guest allocation failure.

Change (Syscall.cs only): in Break, for a break that ends the process (bit 31 clear, the process not already exiting),
before the existing error line, one journal line (stage "guestBreak", status "context"):
- the reason (svcBreak's X0) and its kind (Panic, Assert, User, Pre/PostLoadDll, Pre/PostUnloadDll, CppException);
- the info address and size the game passes (X1, X2), and, when 1 to 256 bytes at that address are mapped, those bytes
  in hexadecimal (groups of four bytes); when the size is 4, the word is also read as a Horizon result code
  (module 2000+n, description), which names the service that failed;
- the guest thread id and name, the FP, LR, SP and PC lines of the debugger's register printout (at a supervisor call
  the context is the thread's own, not a stale JIT one), and the frame-pointer walk (at most 34 lines).
The text is collected on a background thread joined for at most 250 ms (GuestFaultContext.Capture, adapt_guest_fault_
context) and cut to 3600 characters. Only X0, X1 and X2 are kept from the general-purpose registers: they are the
supervisor call's arguments (the Core journal keeps no register dump). It reads guest memory only through IsRangeMapped
and Read on the process's address space; it writes nothing, takes no lock and changes no thread or process state.
Not changed: what Break does (the stack and register Info lines, the error line, TerminateCurrentProcess, the
exception) and every other supervisor call. It does not stop the game from ending: it says why it ended, which is what
the next fix needs. Not measured on an iPhone. Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail
closed on drift.
"""
import hashlib
from adapt_session import once

SYSCALL = 'src/Ryujinx.HLE/HOS/Kernel/SupervisorCall/Syscall.cs'
# The preparation of Core 58319c2c (IPA 766/767).
BASELINE = {SYSCALL: '12f1d70303a7cbed4d49c3021043163f5d7e76e199d4d88d75b66f902e754539'}

BREAK_OLD = '''                // As the process is exiting, this is probably caused by emulation termination.
                if (currentThread.Owner.State == ProcessState.Exiting)
                {
                    return;
                }

                Logger.Error?.Print(LogClass.KernelSvc, "The guest program broke execution!");
'''
BREAK_NEW = '''                // As the process is exiting, this is probably caused by emulation termination.
                if (currentThread.Owner.State == ProcessState.Exiting)
                {
                    return;
                }

                // RewindBox (adapt_guest_break_context): why the game stopped, in the Core journal (the two lines above are
                // Info, which the journal does not keep): reason, info bytes, thread, control registers and guest stack.
                EmbeddedLaunchDiagnostics.Record("guestBreak", "context", detail: GuestBreakContext.Describe(currentThread, reason, 250));

                Logger.Error?.Print(LogClass.KernelSvc, "The guest program broke execution!");
'''

CONTEXT_CLASS = '''
    // RewindBox (adapt_guest_break_context) begin
    // The game's own svcBreak, described for the Core journal before the process ends: the reason (X0), the info address
    // and size (X1, X2) and the bytes there (at most 256, when mapped; a 4-byte info is also read as a result code), the
    // guest thread, its FP, LR, SP and PC, and its guest stack. No other general-purpose register is kept.
    internal static class GuestBreakContext
    {
        internal const int MaxFrameLines = 34;
        internal const int MaxLength = 3600;
        internal const ulong MaxInfoBytes = 0x100;
        private const string FaultPrefix = "guestFaultContext; ";
        private const string Prefix = "guestBreakContext; ";

        internal static string Describe(KThread thread, ulong reason, int budgetMilliseconds)
        {
            try
            {
                if (thread == null)
                {
                    return Prefix + "reason=0x" + reason.ToString("x") + " (" + Kind(reason) + "); unavailable=no guest thread";
                }

                string text = Ryujinx.HLE.HOS.Kernel.GuestFaultContext.Capture(() => Collect(thread, reason), budgetMilliseconds);

                if (text != null && text.StartsWith(FaultPrefix, StringComparison.Ordinal))
                {
                    text = Prefix + "reason=0x" + reason.ToString("x") + " (" + Kind(reason) + "); " + text.Substring(FaultPrefix.Length);
                }

                return text;
            }
            catch (Exception e)
            {
                return Prefix + "unavailable=" + e.GetType().Name;
            }
        }

        internal static string Kind(ulong reason)
        {
            return (reason & 0x7FFFFFFF) switch
            {
                0 => "Panic",
                1 => "Assert",
                2 => "User",
                3 => "PreLoadDll",
                4 => "PostLoadDll",
                5 => "PreUnloadDll",
                6 => "PostUnloadDll",
                7 => "CppException",
                _ => "unknown",
            };
        }

        internal static string Collect(KThread thread, ulong reason)
        {
            ulong info = thread.Context.GetX(1);
            ulong size = thread.Context.GetX(2);
            string bytes = Part(() => InfoBytes(thread, info, size));
            string name = Part(thread.GetThreadName);
            string registers = Part(thread.GetGuestRegisterPrintout);
            string stack = Part(thread.GetGuestStackTrace);

            return Format(reason, info, size, bytes, thread.ThreadUid, name, registers, stack);
        }

        internal static string InfoBytes(KThread thread, ulong info, ulong size)
        {
            if (size == 0 || size > MaxInfoBytes || info == 0)
            {
                return "not read (size)";
            }

            IVirtualMemoryManager memory = thread.Owner.CpuMemory;

            if (!memory.IsRangeMapped(info, size))
            {
                return "not read (unmapped)";
            }

            byte[] data = new byte[(int)size];
            memory.Read(info, data);

            return Hex(data);
        }

        // Four-byte groups separated by spaces: the journal's redactor drops a run of 32 or more hexadecimal digits.
        internal static string Hex(byte[] data)
        {
            System.Text.StringBuilder text = new();

            for (int i = 0; i < data.Length; i++)
            {
                if (i > 0 && (i & 3) == 0)
                {
                    text.Append(' ');
                }

                text.Append(data[i].ToString("x2"));
            }

            if (data.Length == 4)
            {
                uint value = BitConverter.ToUInt32(data, 0);

                text.Append(" (as a result: 0x").Append(value.ToString("x8")).Append(", ")
                    .Append((2000 + (value & 0x1FF)).ToString("d4")).Append('-').Append(((value >> 9) & 0x1FFF).ToString("d4")).Append(')');
            }

            return text.ToString();
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

        internal static string Format(ulong reason, ulong info, ulong size, string bytes, ulong threadUid, string name, string registers, string stack)
        {
            System.Text.StringBuilder text = new();

            text.Append(Prefix).Append("reason=0x").Append(reason.ToString("x")).Append(" (").Append(Kind(reason)).Append(')');
            text.Append("; info=0x").Append(info.ToString("x16")).Append("; size=0x").Append(size.ToString("x"));
            text.Append("; guestThread=").Append(threadUid).Append("; guestThreadName=").Append(Clean(name));
            text.Append("\\ninfo bytes: ").Append(Clean(bytes));
            text.Append("\\nregisters at the break (FP LR SP PC):");

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

            foreach (char c in value ?? string.Empty)
            {
                text.Append(c == '\\t' ? ' ' : char.IsControl(c) ? '?' : c);
            }

            return text.ToString().Trim();
        }
    }
    // RewindBox (adapt_guest_break_context) end
}
'''

END_OLD = '''            return (address & 3) != 0;
        }
    }
}
'''
END_NEW = '''            return (address & 3) != 0;
        }
    }
''' + CONTEXT_CLASS

PAIRS = [
    (SYSCALL, BREAK_OLD, BREAK_NEW),
    (SYSCALL, END_OLD, END_NEW),
]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
