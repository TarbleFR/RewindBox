using System;
using System.Collections.Generic;

namespace S2A.Services
{
    // stub of Red.cs (same public signatures for Report / Note)
    public static class Red
    {
        public static readonly List<string> Lines = new();
        public static void Report(string what, string detail = null, bool allowFailFast = true) { Lines.Add("RED " + what + " : " + detail); Console.Error.WriteLine("  [red] " + what + " : " + detail); }
        public static void Note(string what, string detail) { Lines.Add("NOTE " + what + " : " + detail); Console.Error.WriteLine("  [note] " + what + " : " + detail); }
    }

    // stub of Native.cs: same Mark signature and body, BootMark is a managed function pointer here
    public static unsafe class Native
    {
        public static readonly List<string> Marks = new();
        public static delegate*<byte*, void> BootMark = &Record;
        private static void Record(byte* p)
        {
            int n = 0; while (p[n] != 0) n++;
            string s = System.Text.Encoding.UTF8.GetString(p, n);
            Marks.Add(s);
            Console.Error.WriteLine("  [mark] " + s);
        }
        public static void Mark(System.ReadOnlySpan<byte> stage)
        {
            if (BootMark != null)
            {
                fixed (byte* p = stage)
                {
                    BootMark(p);
                }
            }
        }
    }

    static class GuestMemory
    {
        public static Action<ulong, ulong> WriteHook;
        public static bool TryGuestAddress(ulong host, ulong len, out ulong va) { va = 0; return false; }
    }
}
namespace S2A.Services
{
    public static class ApplicationHelpers { }
}
