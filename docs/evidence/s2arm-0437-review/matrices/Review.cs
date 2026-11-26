using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using S2Arm.Gfx.Widen;

static class Review {
    static BinaryWriter log;
    static HashSet<string> positive=new();
    static HashSet<string> activePairs=new();
    delegate bool E(ReadOnlySpan<float> matrix,out WidenKind k,out bool col);
    delegate void Ortho(ReadOnlySpan<float> matrix);
    delegate bool Pred(ReadOnlySpan<float> matrix);
    static readonly E either=typeof(WidenRewriter).GetMethod("MatchEither",BindingFlags.Static|BindingFlags.NonPublic).CreateDelegate<E>();
    static readonly Pred shape=typeof(WidenRewriter).GetMethod("MaybeMatrix",BindingFlags.Static|BindingFlags.NonPublic).CreateDelegate<Pred>();
    static readonly FieldInfo[] counters=typeof(WidenStats).GetFields().OrderBy(f=>f.Name).ToArray();
    static readonly float[] patterns={0f,BitConverter.Int32BitsToSingle(unchecked((int)0x80000000)),
        BitConverter.Int32BitsToSingle(unchecked((int)0xffa01234)),BitConverter.Int32BitsToSingle(0x7fc0cafe),
        float.PositiveInfinity,float.NegativeInfinity,float.Epsilon,-float.Epsilon,
        1e-6f,MathF.BitDecrement(1e-6f),MathF.BitIncrement(1e-6f),-1e-6f,
        1e-4f,MathF.BitDecrement(1e-4f),MathF.BitIncrement(1e-4f),1f,-1f,
        MathF.BitDecrement(1f),MathF.BitIncrement(1f),float.MaxValue,float.MinValue};
    static void Bytes(ReadOnlySpan<byte> bytes) {log.Write(bytes.Length); log.Write(bytes);}
    static void Words(ReadOnlySpan<float> x) => Bytes(MemoryMarshal.AsBytes(x));
    static void Session(WidenRewriter w) {
        log.Write(w.Cameras); log.Write(w.CameraVersion); log.Write(w.Pure2DRecent);
        foreach(var c in counters) { long v=(long)c.GetValue(w.Stats);log.Write(v);if(v>0)positive.Add(c.Name); }
    }
    sealed class Sink:IWidenHitSink {
        public void Hit(int off,int count,WidenKind k,bool column) {
            log.Write("S");log.Write(off);log.Write(count);log.Write((byte)k);log.Write(column);
        }
    }
    static float[] Matrix(int k) {
        float[] m=new float[16]; m[0]=1; m[5]=16f/9f; m[10]=-.25f;
        switch(k) {
            case 0: m[14]=-1;m[11]=.07f;break;
            case 1: m[14]=.07f;m[11]=-1;break;
            case 2: m[15]=1;m[11]=.8f;break;
            case 3: m[15]=1;m[14]=.8f;break;
            case 4: m[15]=1;break;
            case 5: m[14]=-1;m[11]=-1;break;
            case 6: m[1]=.6f;m[0]=.8f;m[4]=-.6f*(16f/9f);m[5]=.8f*(16f/9f);m[14]=-1;break;
            case 7: m[0]=16f/9f;m[5]=1;m[10]=0;m[11]=-1;break;
            case 8: for(int j=0;j<16;j++)m[j]=(j*17-83)/32f;break;
            case 9: m[0]=0;m[5]=0;m[10]=0;break;
            case 10: m[14]=.995f; m[11]=1;break;
            case 11: m[14]=1;m[11]=.995f;break;
            case 12: m[14]=.995f;m[11]=.995f;break;
        }return m;
    }
    static void Lengths() {
        for(int n=0;n<=35;n++) foreach(bool c in new[]{false,true}) {
            float[] a=new float[n]; if(n>15) Matrix(0).CopyTo(a,0); if(n>16)a[^1]=float.NaN;
            WidenKind k=(WidenKind)0x6d;string result;
            try {result=WidenRewriter.Match(a,c,out k)?"accepted":"rejected";}
            catch(Exception e){result=e.GetType().FullName;}
            log.Write(n);log.Write(c);log.Write(result);log.Write((byte)k);
            if(n==0) Console.WriteLine($"short[{c}]={result}, out={(int)k}");
        }
    }
    static string Digest(Action action) {
        using var hash=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        using var ms=new MemoryStream();log=new BinaryWriter(ms);action();log.Flush();
        return Convert.ToHexString(SHA256.HashData(ms.GetBuffer().AsSpan(0,(int)ms.Length)));
    }
    static void Differential(bool joined) {
        var sink=new Sink();
        foreach(float aspect in new[]{2.16f,4f/3f,16f/9f}) foreach(bool pure in new[]{false,true}) {
            var w=new WidenRewriter(aspect){Pure2DOff=pure};
            for(int k=0;k<13;k++) for(int j=0;j<16;j++) for(int i=-1;i<patterns.Length;i++) {
                float[] m=Matrix(k);if(i>=0)m[j]=patterns[i];
                bool row=WidenRewriter.Match(m,false,out var rk),column=WidenRewriter.Match(m,true,out var ck);
                log.Write(row);log.Write((byte)rk);log.Write(column);log.Write((byte)ck);
                bool both=either(m,out var picked,out var colChoice);
                bool preferRow=row && (rk!=WidenKind.ViewProjection || !column || ck==WidenKind.ViewProjection);
                if (both!=(row||column) || colChoice==preferRow || picked!=(preferRow?rk:ck))
                    throw new InvalidOperationException("Changed classification priority");
                if(row && column) activePairs.Add($"{rk}/{ck}");
                var dst=Enumerable.Repeat(-17.5f,20).ToArray();
                if(joined) {
                    bool h=w.RewriteWindow(m,dst,out var kind,out var col);
                    log.Write(h);log.Write((byte)kind);log.Write(col);Words(dst);Session(w);
                } else {
                    int offset=(j+k)&15, start=(16-offset)&15;
                    byte[] source=new byte[start+148], dest=Enumerable.Repeat((byte)0xc3,source.Length+13).ToArray();
                    Buffer.BlockCopy(m,0,source,start,64);Buffer.BlockCopy(Matrix((k+1)%10),0,source,start+64,64);
                    bool h=w.Rewrite(source,offset,dest,sink);
                    log.Write(h);Bytes(dest);Session(w);
                }
                if((i&7)==0) w.EndFrame();
            }
        }
    }
    static void Main(){
        Console.WriteLine("lengths "+Digest(Lengths));
        int invalidShape=0;
        for (int i=0;i<1024;i++) { float[] m=new float[16];for(int j=0;j<16;j++)m[j]=MathF.Sin(i*17+j*53);if(shape(m)) invalidShape++; }
        Console.WriteLine("timed invalid shape gate: "+invalidShape+"/1024");
        int routed=0, rejected=0;
        for(int i=0;i<1024;i++) {
            var m=Matrix(0); m[0]=1+(i%61)/128f; m[5]=m[0]*(16f/9f)*1.015f;
            if(shape(m))routed++;
            if(!either(m,out _,out _))rejected++;
        }
        Console.WriteLine($"near-miss shape gate/classifier rejection: {routed}/{rejected} of 1024");
        if(routed!=1024 || rejected!=1024)throw new InvalidOperationException("invalid negative control");
        Console.WriteLine("ortho flags "+Digest(()=>{
            var w=new WidenRewriter(2.16f);
            var note=typeof(WidenRewriter).GetMethod("NoteSymOrtho",BindingFlags.NonPublic|BindingFlags.Instance).CreateDelegate<Ortho>(w);
            var tick=typeof(WidenRewriter).GetField("_camTick",BindingFlags.NonPublic|BindingFlags.Instance);
            for(int k=2;k<=4;k++)for(int j=0;j<16;j++)foreach(var f in patterns){
                float[] m=Matrix(k);m[j]=f;long old=Convert.ToInt64(tick.GetValue(w));
                note(m);long now=Convert.ToInt64(tick.GetValue(w));
                log.Write(old);log.Write(now);log.Write(w.Cameras);log.Write(w.CameraVersion);
            }
        }));
        Console.WriteLine("window "+Digest(()=>Differential(true)));
        Console.WriteLine("window positive="+string.Join(",",positive.OrderBy(x=>x)));positive.Clear();
        Console.WriteLine("bulk "+Digest(()=>Differential(false)));
        Console.WriteLine("bulk positive="+string.Join(",",positive.OrderBy(x=>x)));
        Console.WriteLine("dual matches="+string.Join(",",activePairs.OrderBy(x=>x)));
        Console.WriteLine("stats="+string.Join(",",counters.Select(f=>f.Name)));
    }
}
