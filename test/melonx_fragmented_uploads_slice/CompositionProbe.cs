using System;

// Native conversion is a boundary double. Record every byte it receives so the
// historical Slice implementation remains an independent cross-variant oracle.
// This probe allocates nothing in the measured production upload loop.
static class SliceCompositionProbe
{
    public static int Calls;
    public static long Bytes;
    private static ulong _digest = 14695981039346656037UL;
    public static string Digest => _digest.ToString("X16");

    public static void Record(ReadOnlySpan<byte> data, int level)
    {
        Calls++;
        Bytes += data.Length;
        Mix(unchecked((uint)level));
        Mix((uint)data.Length);
        foreach (byte value in data)
        {
            _digest = unchecked((_digest ^ value) * 1099511628211UL);
        }
    }

    private static void Mix(uint value)
    {
        for (int index = 0; index < sizeof(uint); index++)
        {
            _digest = unchecked((_digest ^ (byte)value) * 1099511628211UL);
            value >>= 8;
        }
    }
}
