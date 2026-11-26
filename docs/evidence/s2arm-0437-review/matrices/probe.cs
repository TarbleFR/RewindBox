using System;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using S2Arm.Gfx.Widen;
class Program {
    const int Trials=131072;
    [DllImport("s2arm_bench_clock", EntryPoint="thread_nanoseconds")]
    static extern ulong ThreadNanoseconds();
    static ulong Add(ulong h, long n) => unchecked((h ^ (ulong)n) * 1099511628211UL);
    static float[] Matrix(int i, int type) {
        var m = new float[16];
        float x = 1f + (i % 61) / 128f;
        m[0] = x; m[5] = x * 16f/9f; m[10] = -0.75f;
        switch (type) {
            case 0: m[11]=0.03f; m[14]=-1; break;
            case 1: m[11]=-1; m[14]=0.03f; break;
            case 2: m[15]=1; m[(i&1)==0?11:14]=1; break;
            case 3: m[1]=0.03f; m[15]=1; m[14]=1; break;
            case 4: m[14]=-1; m[5]=x*2.16f; break;
            case 5: for(int j=0;j<16;j++) m[j]=MathF.Sin(i*17+j*53); break;
            // Pass the fast shape filter but fail both orientations of the full classifier.
            case 6: m[5]=x*(16f/9f)*1.015f; m[10]=-.25f; m[11]=.07f; m[14]=-1f; break;
        }
        return m;
    }
    delegate void Note(ReadOnlySpan<float> m);
    static ulong Work(string mode, bool verify) {
        var rewriter=new WidenRewriter(2.16f);
        var note=typeof(WidenRewriter).GetMethod("NoteSymOrtho",BindingFlags.Instance|BindingFlags.NonPublic).CreateDelegate<Note>(rewriter);
        float[] special={0f,-0f,0.00001f,-0.00001f,float.NaN,float.NegativeInfinity,float.PositiveInfinity,float.Epsilon,1.001f,1,-1};
        var matrices=new float[verify?8192:1024][];
        for(int i=0;i<matrices.Length;i++) {
            var m=Matrix(i, mode switch {"row"=>0,"column"=>1,"ortho"=>2,"invalid"=>5,"near-miss"=>6,_=>i%6});
            if(verify && i>=192 && (i%3!=0)) m[(i/12)%16]=special[(i/192)%special.Length];
            matrices[i]=m;
        }
        var dst=new float[16]; ulong h=1469598103934665603UL;
        bool timed=!verify;
        long alloc=GC.GetAllocatedBytesForCurrentThread(), start=Stopwatch.GetTimestamp();
        ulong cpuStart=ThreadNanoseconds();
        for(int i=0;i<(verify?matrices.Length:Trials);i++) {
            var m=matrices[i & (matrices.Length-1)];
            if(verify) {
                bool row=WidenRewriter.Match(m,false,out var rk), column=WidenRewriter.Match(m,true,out var ck);
                h=Add(Add(Add(Add(h,row?1:0),(long)rk),column?1:0),(long)ck);
                note(m);
                h=Add(Add(h,rewriter.Cameras),rewriter.CameraVersion);
                Array.Fill(dst,-17.5f);
            }
            bool result=rewriter.RewriteWindow(m,dst,out var kind,out var col);
            h=Add(h,(result ? 512L : 0L)+(col?256L:0L)+(long)kind);
            if(verify) {
                foreach(float f in dst) h=Add(h,BitConverter.SingleToInt32Bits(f));
                var src=MemoryMarshal.AsBytes(m.AsSpan());
                Array.Fill(dst,-29.75f);
                bool full=rewriter.Rewrite(src,0,MemoryMarshal.AsBytes(dst.AsSpan()));
                h=Add(Add(Add(h,full?1:0),rewriter.Cameras),rewriter.CameraVersion);
                foreach(float f in dst) h=Add(h,BitConverter.SingleToInt32Bits(f));
            }
        }
        double cpuMs=(ThreadNanoseconds()-cpuStart)/1_000_000.0;
        double ms=Stopwatch.GetElapsedTime(start).TotalMilliseconds;
        long delta=GC.GetAllocatedBytesForCurrentThread()-alloc;
        if(timed) Console.WriteLine(FormattableString.Invariant($"{mode},{ms:F6},{h:x16},{delta},{cpuMs:F6}"));
        return h;
    }
    static void Main(string[] args) {
        if(args[0]=="verify") { Console.WriteLine(Work("mixed",true).ToString("x16")); return; }
        foreach(var m in args) Work(m,false);
        foreach(var m in args) Work(m,false);
    }
}
