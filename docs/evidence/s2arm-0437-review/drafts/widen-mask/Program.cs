using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using S2Arm.Gfx.Widen;
static class Program {
    delegate int Build(ReadOnlySpan<int> shader, int stage);
    delegate int Cam(ReadOnlySpan<int> shader, bool sync);
    const BindingFlags NonPublic = BindingFlags.Instance | BindingFlags.NonPublic;
    static uint Mix(uint h,int v) => (h^(uint)v)*16777619u;
    static unsafe int Main(string[] args) {
        string mode=args[0]; bool verify=mode=="verify";
        var session=new WidenSession(1920,1080,false,false,false);
        var build=typeof(WidenSession).GetMethod("BuildReads",NonPublic).CreateDelegate<Build>(session);
        var cam=typeof(WidenSession).GetMethod("CamReads",NonPublic).CreateDelegate<Cam>(session);
        var read=(CbufRead[])typeof(WidenSession).GetField("_camReads",NonPublic).GetValue(session);
        byte* mem=(byte*)NativeMemory.AlignedAlloc(65536,65536);
        if(mem==null) return 2;
        try {
            new Span<byte>(mem,65536).Clear();
            var shaders=new int[32][];
            for(int i=0;i<32;i++){
                shaders[i]=new int[6];
                for(int s=0;s<6;s++) {
                    var text=new List<string>();
                    for(int k=0;k<18;k++){
                        bool used=mode switch {"dense"=>true, "single"=>(k==7),
                            "none"=>false, _=>((k*17+i*13+s*7)%11 < (verify?i%12:3))};
                        if(used) text.Add(k+":"+(k%2==0?"*":"0,2"));
                    }
                    shaders[i][s]=session.Shader(text.Count==0 ? "unused" : string.Join(";",text),i%2==0);
                }
            }
            for(int s=0;s<6;s++) for(int k=0;k<18;k++)
                if(mode!="sparse-bind" || k==s)
                    session.CbufBind(s,k,(nint)(mem+(s*18+k)*256),128);
            uint h=2166136261; int n=verify?4096:100000;
            for(int pass=0;pass<2;pass++){
                long alloc=GC.GetAllocatedBytesForCurrentThread();
                var time=Stopwatch.GetTimestamp();
                for(int i=0;i<n;i++){
                    int[] sh=shaders[i%32];int a=cam(sh,false);
                    int b=build(sh,i%7-1);h=Mix(Mix(h,a),b);
                    if(verify) for(int j=0;j<a;j++){
                        ref readonly var r=ref read[j];
                        long address=((long)r.Buffer<<24)+r.Offset;
                        h=Mix(Mix(Mix(h,(int)(address-(long)mem)),r.Size),r.Use.Binding);
                        h=Mix(h,r.Use.Dynamic?1:0);
                        foreach(int ix in r.Use.Indices) h=Mix(h,ix);
                    }
                }
                var ms=Stopwatch.GetElapsedTime(time).TotalMilliseconds;
                long delta=GC.GetAllocatedBytesForCurrentThread()-alloc;
                if(pass==1) Console.WriteLine(FormattableString.Invariant($"{mode} {ms:F6} {h:x8} {delta}"));
            }
        } finally {NativeMemory.AlignedFree(mem);}
        return 0;
    }
}
