// CI only (see ZbicBatch.csproj). Manifest lines: "frame|nso<TAB>input<TAB>expected length<TAB>output".
//   frame: ZbicDecoder.Decompress(input bytes, expected length)
//   nso:   NsoZbic.Normalize(input bytes, file name) - what nx_unpack --nso-normalize writes
// On success the result is written to output and "<line> ok" printed; an InvalidDataException
// prints "<line> err <message>"; any other exception prints "<line> crash <type>" (nx_unpack
// would exit 1 on it too) and nothing is written.
using System;
using System.IO;

static class ZbicBatch {
    static int Main(string[] args) {
        if (args.Length != 1) { Console.Error.WriteLine("usage: ZbicBatch <manifest>"); return 2; }
        int n = 0;
        foreach (var line in File.ReadAllLines(args[0])) {
            n++;
            var f = line.Split('\t');
            if (f.Length != 4) { Console.WriteLine($"{n} err bad manifest line"); continue; }
            try {
                var data = File.ReadAllBytes(f[1]);
                byte[] result = f[0] == "nso" ? NsoZbic.Normalize(data, Path.GetFileName(f[1])) : ZbicDecoder.Decompress(data, int.Parse(f[2]));
                File.WriteAllBytes(f[3], result);
                Console.WriteLine($"{n} ok");
            } catch (InvalidDataException e) {
                Console.WriteLine($"{n} err {e.Message.Replace('\n', ' ')}");
            } catch (Exception e) {
                Console.WriteLine($"{n} crash {e.GetType().Name}");
            }
        }
        return 0;
    }
}
