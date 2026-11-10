using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Format = Ryujinx.Graphics.GAL.Format;

// Compiled into the production Ryujinx.Graphics.Vulkan assembly of the Core 658 preparation (control) and of that
// preparation plus adapt_moltenvk_stage_ordering (candidate). It runs the production TextureStorage.QueueWriteToReadBarrier,
// TextureArray.QueueWriteToReadBarriers and BarrierBatch.QueueBarrier on objects created without their Vulkan
// constructors (no Vulkan or Metal call), takes the barriers they queue, and replays them, with the render passes and
// dispatches of each scenario, on a model of MoltenVK 1.4.2's barrier fences (MVKCommandBuffer.mm setBarrier,
// getBarrierStageFence, barrierWait, barrierUpdate; MVKCmdPipeline.mm; mvk_datatypes.mm; the Python test binds that source).
// A reader is ordered after its writer when the model's waits link its encoder stage to the writer's fragment stage.
// The candidate also runs the production EncoderOrdering decisions (render/compute switches) through the same model.
static class Program
{
    const BindingFlags Any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
    static int _checks;

    static void Check(bool condition, string message)
    {
        _checks++;
        if (!condition) throw new Exception(message);
    }

    static FieldInfo Field(Type type, string name)
    {
        while (type != null)
        {
            FieldInfo field = type.GetField(name, Any) ?? type.GetField($"<{name}>k__BackingField", Any);
            if (field != null) return field;
            type = type.BaseType;
        }
        throw new MissingFieldException(name);
    }

    static void Set(object target, string name, object value) => Field(target.GetType(), name).SetValue(target, value);
    static object Get(object target, string name) => Field(target.GetType(), name).GetValue(target);
    static T New<T>() => (T)RuntimeHelpers.GetUninitializedObject(typeof(T));

    // ---------------------------------------------------------------------------------------------------------------
    // MoltenVK 1.4.2 with a residency set: Metal tracks no argument-buffer read, only these fences order encoders.
    sealed class Mvk
    {
        public const int V = 0, F = 1, C = 2, Copy = 3, Count = 4, FenceCount = 64;
        readonly int[] _update = new int[Count];
        readonly int[,] _wait = new int[Count, Count];
        int _dirty;
        readonly Dictionary<(int Stage, int Slot), int> _lastUpdater = new();
        readonly List<List<int>> _preds = new();
        public readonly List<string> Names = new();
        int _openCompute = -1;

        // mvkBarrierStagesFromPipelineStageFlags (Vulkan 1.0 bits).
        public static int Stages(PipelineStageFlags f)
        {
            const PipelineStageFlags any = PipelineStageFlags.TopOfPipeBit | PipelineStageFlags.BottomOfPipeBit | PipelineStageFlags.AllCommandsBit;
            int r = 0;
            if ((f & (any | PipelineStageFlags.VertexInputBit | PipelineStageFlags.VertexShaderBit | PipelineStageFlags.TessellationControlShaderBit |
                      PipelineStageFlags.TessellationEvaluationShaderBit | PipelineStageFlags.AllGraphicsBit | PipelineStageFlags.DrawIndirectBit |
                      PipelineStageFlags.GeometryShaderBit | PipelineStageFlags.TransformFeedbackBitExt)) != 0) r |= 1 << V;
            if ((f & (any | PipelineStageFlags.FragmentShaderBit | PipelineStageFlags.AllGraphicsBit | PipelineStageFlags.EarlyFragmentTestsBit |
                      PipelineStageFlags.LateFragmentTestsBit | PipelineStageFlags.ColorAttachmentOutputBit)) != 0) r |= 1 << F;
            if ((f & (any | PipelineStageFlags.ComputeShaderBit)) != 0) r |= 1 << C;
            if ((f & (any | PipelineStageFlags.TransferBit)) != 0) r |= 1 << Copy;
            return r;
        }

        int Node(string name)
        {
            _preds.Add(new List<int>());
            Names.Add(name);
            return _preds.Count - 1;
        }

        // getBarrierStageFence: a stage marked by a barrier moves to its next slot (never 0) at its next update.
        int UpdateSlot(int stage)
        {
            if ((_dirty & (1 << stage)) != 0)
            {
                _dirty &= ~(1 << stage);
                _update[stage] = (_update[stage] + 1) % FenceCount;
                if (_update[stage] == 0) _update[stage] = 1;
            }
            return _update[stage];
        }

        // barrierWait: an encoder stage waits on one fence per stage, the slot its wait row holds.
        void Wait(int node, int stage)
        {
            for (int i = 0; i < Count; i++)
            {
                if (_lastUpdater.TryGetValue((i, _wait[stage, i]), out int updater)) _preds[node].Add(updater);
            }
        }

        void EndEncoders()
        {
            if (_openCompute >= 0)
            {
                _lastUpdater[(C, UpdateSlot(C))] = _openCompute;
                _openCompute = -1;
            }
        }

        // vkCmdPipelineBarrier outside a render encoder: end the encoders, then setBarrier.
        public void Barrier(PipelineStageFlags source, PipelineStageFlags destination)
        {
            EndEncoders();
            int src = Stages(source), dst = Stages(destination);
            for (int i = 0; i < Count; i++)
            {
                if ((src & (1 << i)) == 0) continue;
                for (int j = 0; j < Count; j++)
                {
                    if ((dst & (1 << j)) != 0) _wait[j, i] = _update[i];
                }
                _wait[i, i] = _update[i];
                _dirty |= 1 << i;
            }
        }

        // One Vulkan render pass: one Metal render encoder (waits at begin for vertex and fragment, updates at end).
        public (int Vertex, int Fragment) RenderPass(string name)
        {
            EndEncoders();
            int v = Node(name + ".vertex"), f = Node(name + ".fragment");
            Wait(v, V);
            Wait(f, F);
            _preds[f].Add(v);
            _lastUpdater[(V, UpdateSlot(V))] = v;
            _lastUpdater[(F, UpdateSlot(F))] = f;
            return (v, f);
        }

        // Dispatches share the open compute encoder (serial) until a barrier or another encoder ends it.
        public int Dispatch(string name)
        {
            if (_openCompute < 0)
            {
                _openCompute = Node(name);
                Wait(_openCompute, C);
            }
            return _openCompute;
        }

        public bool After(int later, int earlier)
        {
            var seen = new HashSet<int>();
            var stack = new Stack<int>();
            stack.Push(later);
            while (stack.Count > 0)
            {
                int node = stack.Pop();
                if (node == earlier) return node != later;
                if (!seen.Add(node)) continue;
                foreach (int p in _preds[node]) stack.Push(p);
            }
            return false;
        }
    }

    // ---------------------------------------------------------------------------------------------------------------
    // Production objects, with only the state the barrier paths read.
    static VulkanRenderer Renderer(bool tracksArgumentBufferHazards, bool moltenVk = true)
    {
        VulkanRenderer gd = New<VulkanRenderer>();
        Set(gd, "IsMoltenVk", moltenVk);
        Set(gd, "IsTBDR", true);
        Set(gd, "MoltenVkTracksArgumentBufferHazards", tracksArgumentBufferHazards);
        Set(gd, "Barriers", new BarrierBatch(gd));
        Set(gd, "_pipeline", null);
        return gd;
    }

    static TextureStorage Storage(VulkanRenderer gd)
    {
        TextureStorage storage = New<TextureStorage>();
        Set(storage, "_gd", gd);
        Set(storage, "_info", new TextureCreateInfo(64, 64, 1, 1, 1, 1, 1, 4, Format.R8G8B8A8Unorm, DepthStencilMode.Depth,
            Target.Texture2D, SwizzleComponent.Red, SwizzleComponent.Green, SwizzleComponent.Blue, SwizzleComponent.Alpha));
        Auto<DisposableImage> image = New<Auto<DisposableImage>>();
        Set(image, "_destroyed", true); // Get(cbs) then returns the handle without command buffer bookkeeping
        Set(storage, "_imageAuto", image);
        return storage;
    }

    sealed record Queued(PipelineStageFlags Source, PipelineStageFlags Dest, AccessFlags SrcAccess, AccessFlags DstAccess);

    // The image barriers BarrierBatch holds, taken (as Flush would record them) and cleared.
    static List<Queued> Take(VulkanRenderer gd)
    {
        object batch = Get(gd, "Barriers");
        IList list = (IList)Get(batch, "_imageBarriers");
        var result = new List<Queued>();
        foreach (object item in list)
        {
            object flags = Get(item, "Flags");
            ImageMemoryBarrier barrier = (ImageMemoryBarrier)Get(item, "Barrier");
            result.Add(new Queued((PipelineStageFlags)Get(flags, "Source"), (PipelineStageFlags)Get(flags, "Dest"),
                barrier.SrcAccessMask, barrier.DstAccessMask));
        }
        list.Clear();
        Set(batch, "_queuedBarrierCount", 0);
        return result;
    }

    const PipelineStageFlags Vs = PipelineStageFlags.VertexShaderBit, Fs = PipelineStageFlags.FragmentShaderBit, Cs = PipelineStageFlags.ComputeShaderBit;

    static string StageName(PipelineStageFlags s) => s == Vs ? "vertex" : s == Fs ? "fragment" : s == Cs ? "compute" : s.ToString();

    sealed class Outcome
    {
        public List<string> Steps { get; } = new();
        public List<bool> Ordered { get; } = new();
        public int Barriers { get; set; }
        public List<string> Recorded { get; } = new();
    }

    // A scenario: "W" a render pass writing the texture as a color attachment (AddStoreOpUsage at its end), "V"/"F"/"C" a
    // bind for that reader stage followed by its encoder (render pass or dispatch) reading it.
    static Outcome Scenario(string script, bool tracks, int textures = 1, bool moltenVk = true)
    {
        VulkanRenderer gd = Renderer(tracks, moltenVk);
        var mvk = new Mvk();
        TextureStorage[] storages = Enumerable.Range(0, textures).Select(_ => Storage(gd)).ToArray();
        TextureArray array = null;
        if (textures > 1)
        {
            array = New<TextureArray>();
            Set(array, "_storages", new HashSet<TextureStorage>(storages));
            Set(array, "_storagesDirty", false);
        }
        var outcome = new Outcome();
        int writer = -1, n = 0;
        foreach (char step in script)
        {
            n++;
            if (step == 'B')
            {
                // Another texture's write-to-read barrier earlier in the command buffer (a frame records dozens): the
                // fragment stage moves to its next fence slot, so later waits name slots, not the start of the buffer.
                mvk.Barrier(PipelineStageFlags.ColorAttachmentOutputBit, PipelineStageFlags.FragmentShaderBit);
                continue;
            }
            if (step == 'W')
            {
                foreach (TextureStorage s in storages) s.AddStoreOpUsage(false);
                writer = mvk.RenderPass("writer" + n).Fragment;
                outcome.Steps.Add("write");
                continue;
            }
            PipelineStageFlags stage = step == 'V' ? Vs : step == 'F' ? Fs : Cs;
            if (array != null) array.QueueWriteToReadBarriers(default, stage);
            else storages[0].QueueWriteToReadBarrier(default, AccessFlags.ShaderReadBit, stage);
            foreach (Queued q in Take(gd))
            {
                Check(q.DstAccess == AccessFlags.ShaderReadBit && q.SrcAccess == AccessFlags.ColorAttachmentWriteBit &&
                      q.Source == PipelineStageFlags.ColorAttachmentOutputBit, "barrier from the attachment write: " + q);
                outcome.Barriers++;
                outcome.Recorded.Add($"{q.Source}->{q.Dest}");
                mvk.Barrier(q.Source, q.Dest);
            }
            int reader = step == 'C' ? mvk.Dispatch("reader" + n) : step == 'V' ? mvk.RenderPass("reader" + n).Vertex : mvk.RenderPass("reader" + n).Fragment;
            outcome.Steps.Add(StageName(stage));
            outcome.Ordered.Add(writer >= 0 && mvk.After(reader, writer));
        }
        return outcome;
    }

    static long[] Counters(string name)
    {
        FieldInfo field = typeof(VulkanRenderer).Assembly.GetType("Ryujinx.Graphics.Vulkan.RenderDetail").GetField(name, Any);
        return field == null ? null : ((long[])field.GetValue(null)).ToArray();
    }

    static void Main(string[] args)
    {
        bool candidate = args[0] == "candidate";
        Type ordering = typeof(VulkanRenderer).Assembly.GetType("Ryujinx.Graphics.Vulkan.EncoderOrdering");
        Check((ordering != null) == candidate && (typeof(TextureStorage).GetField("_readCoveredStages", Any) != null) == candidate,
            "wrong source variant");

        var scenarios = new (string Name, string Script, bool Tracks, int Textures, bool MoltenVk)[]
        {
            ("fragment then compute", "BWFC", false, 1, true),
            ("compute then fragment", "BWCF", false, 1, true),
            ("fragment then vertex", "BWFV", false, 1, true),
            ("fragment twice", "BWFF", false, 1, true),
            ("written again", "BWFCWFC", false, 1, true),
            ("texture array (2 storages): fragment then compute", "BWFC", false, 2, true),
            ("no write", "BFC", false, 1, true),
            ("MoltenVK 1.4.0: fragment then compute", "BWFC", true, 1, true),
            ("not MoltenVK: fragment then compute", "BWFC", false, 1, false),
        };
        var results = new Dictionary<string, Outcome>();
        long[] firstBefore = Counters("WriteToReadFirst"), laterBefore = Counters("WriteToReadLater");
        foreach (var s in scenarios) results[s.Name] = Scenario(s.Script, s.Tracks, s.Textures, s.MoltenVk);
        long[] firstAfter = Counters("WriteToReadFirst"), laterAfter = Counters("WriteToReadLater");

        bool[] Ord(string name) => results[name].Ordered.ToArray();
        // The first reader is ordered in both variants (the delivered barrier).
        foreach (string name in new[] { "fragment then compute", "compute then fragment", "fragment then vertex", "fragment twice", "written again" })
        {
            Check(Ord(name)[0], name + ": first reader ordered");
        }
        Check(Ord("fragment twice").All(o => o) && results["fragment twice"].Barriers == 1, "same stage again: ordered by the first barrier, nothing added");
        Check(results["no write"].Barriers == 0, "no modification: no barrier");
        // Not MoltenVK: the delivered single barrier in both variants, the later compute reader gets none from the change.
        Check(results["not MoltenVK: fragment then compute"].Barriers == 1 &&
              Ord("not MoltenVK: fragment then compute").SequenceEqual(new[] { true, false }),
            "not MoltenVK: identical to the control (one barrier, no new-stage barrier)");

        // A disposed storage still held by a texture array: no barrier and no image handle access (the handle is gone;
        // here _imageAuto is null, so any access throws).
        {
            VulkanRenderer gd = Renderer(false);
            TextureStorage s = Storage(gd);
            s.AddStoreOpUsage(false);
            s.QueueWriteToReadBarrier(default, AccessFlags.ShaderReadBit, Fs);
            Check(Take(gd).Count == 1, "disposed: the first reader gets the delivered barrier");
            Set(s, "Disposed", true);
            Set(s, "_imageAuto", null);
            s.QueueWriteToReadBarrier(default, AccessFlags.ShaderReadBit, Cs);
            Check(Take(gd).Count == 0, "disposed storage: no barrier and no handle access for a later stage");
        }
        if (candidate)
        {
            Check(Ord("fragment then compute").SequenceEqual(new[] { true, true }) && results["fragment then compute"].Barriers == 2,
                "candidate: the compute reader is ordered after the writer by its own barrier");
            Check(Ord("compute then fragment").SequenceEqual(new[] { true, true }) && results["compute then fragment"].Barriers == 2,
                "candidate: the fragment reader after a compute reader is ordered");
            Check(Ord("fragment then vertex").SequenceEqual(new[] { true, true }), "candidate: vertex reader ordered");
            Check(results["written again"].Barriers == 4 && Ord("written again").All(o => o), "candidate: coverage starts again at each write");
            Check(results["texture array (2 storages): fragment then compute"].Barriers == 4 &&
                  Ord("texture array (2 storages): fragment then compute").All(o => o), "candidate: texture arrays covered per storage");
            Check(results["MoltenVK 1.4.0: fragment then compute"].Barriers == 1, "candidate: MoltenVK 1.4.0 keeps the delivered single barrier");
            Check(laterAfter.Zip(laterBefore, (a, b) => a - b).SequenceEqual(new long[] { 1, 1, 5 }) &&
                  firstAfter.Zip(firstBefore, (a, b) => a - b).SequenceEqual(new long[] { 0, 9, 1 }),
                  "candidate counters (vertex/fragment/compute): later " + string.Join('/', laterAfter.Zip(laterBefore, (a, b) => a - b)) +
                  ", first " + string.Join('/', firstAfter.Zip(firstBefore, (a, b) => a - b)));
        }
        else
        {
            // The defect: a later reader in another stage waits on no fence the writer updated.
            Check(Ord("fragment then compute").SequenceEqual(new[] { true, false }) && results["fragment then compute"].Barriers == 1,
                "control: compute after a fragment reader is not ordered");
            // A later fragment reader is ordered all the same: the first barrier's source is the fragment stage, and
            // setBarrier also chains that stage to its own previous fence (wait[i][i]).
            Check(Ord("compute then fragment").SequenceEqual(new[] { true, true }) && results["compute then fragment"].Barriers == 1,
                "control: a fragment reader after a compute reader is ordered by MoltenVK's fragment self-chain");
            Check(Ord("fragment then vertex").SequenceEqual(new[] { true, false }), "control: vertex after a fragment reader is not ordered");
            Check(results["written again"].Barriers == 2 && Ord("written again").SequenceEqual(new[] { true, false, true, false }),
                "control: each write orders only its first reader");
            Check(results["texture array (2 storages): fragment then compute"].Barriers == 2 &&
                  Ord("texture array (2 storages): fragment then compute").SequenceEqual(new[] { true, false }), "control: arrays too");
            Check(results["MoltenVK 1.4.0: fragment then compute"].Barriers == 1, "control: one barrier");
            Check(firstBefore == null && laterBefore == null, "control has no such counters");
        }

        // -----------------------------------------------------------------------------------------------------------
        // Render/compute switches (candidate only): the production decisions, replayed on the model.
        object switches = null;
        if (candidate)
        {
            MethodInfo note = ordering.GetMethod("NoteBarrier", Any), beforePass = ordering.GetMethod("BeforeRenderPass", Any),
                passBegun = ordering.GetMethod("RenderPassBegun", Any), beforeDispatch = ordering.GetMethod("BeforeDispatch", Any),
                dispatched = ordering.GetMethod("DispatchRecorded", Any);
            long Counter(string name) => (long)ordering.GetField(name, Any).GetValue(null);
            string[] names = { "RenderToCompute", "RenderToComputeCovered", "RenderToComputeOrdered", "ComputeToRender", "ComputeToRenderCovered", "ComputeToRenderOrdered" };
            long[] Snapshot() => names.Select(Counter).ToArray();
            nint cb = 0x100;

            // Each step as PipelineBase records it. Returns whether the last encoder's first stage (a pass's vertex stage, a
            // dispatch) is ordered after what the first encoder wrote (a pass's fragment stage, a dispatch).
            (bool ordered, long[] delta, int barriers) Run(string script, bool order)
            {
                cb += 0x10; // a fresh command buffer per scenario (EncoderOrdering state is per command buffer)
                var mvk = new Mvk();
                long[] before = Snapshot();
                int barriers = 0, first = -1, last = -1;
                void Barrier(PipelineStageFlags src, PipelineStageFlags dst)
                {
                    note.Invoke(null, new object[] { cb, src, dst });
                    mvk.Barrier(src, dst);
                }
                // Every scenario follows an earlier barrier of the command buffer (a frame records hundreds), so the waits
                // below name fence slots of this scenario's encoders, not the start of the command buffer.
                foreach (string step in ("all " + script).Split(' '))
                {
                    switch (step)
                    {
                        case "R":
                            if ((bool)beforePass.Invoke(null, new object[] { cb, order })) { Barrier(PipelineStageFlags.AllCommandsBit, PipelineStageFlags.AllCommandsBit); barriers++; }
                            passBegun.Invoke(null, new object[] { cb });
                            var pass = mvk.RenderPass("pass");
                            if (first < 0) first = pass.Fragment;
                            last = pass.Vertex;
                            break;
                        case "D":
                            if ((bool)beforeDispatch.Invoke(null, new object[] { cb, order })) { Barrier(PipelineStageFlags.AllCommandsBit, PipelineStageFlags.AllCommandsBit); barriers++; }
                            dispatched.Invoke(null, new object[] { cb });
                            int dispatch = mvk.Dispatch("dispatch");
                            if (first < 0) first = dispatch;
                            last = dispatch;
                            break;
                        case "all": Barrier(PipelineStageFlags.AllCommandsBit, PipelineStageFlags.AllCommandsBit); break;
                        case "c2f": Barrier(PipelineStageFlags.ComputeShaderBit, PipelineStageFlags.FragmentShaderBit); break;
                        case "f2c": Barrier(PipelineStageFlags.ColorAttachmentOutputBit, PipelineStageFlags.ComputeShaderBit); break;
                        case "cb": cb += 1; break; // the next command buffer: MoltenVK orders command buffers whole (syncFences)
                        default: throw new Exception(step);
                    }
                }
                long[] delta = Snapshot().Zip(before, (a, b) => a - b).ToArray();
                return (mvk.After(last, first), delta, barriers);
            }

            var cases = new Dictionary<string, object>();
            void Case(string name, string script, bool order, bool expectOrdered, long[] expectDelta, int expectBarriers)
            {
                var r = Run(script, order);
                cases[name] = new { script, order, r.ordered, delta = r.delta, r.barriers };
                Check(r.ordered == expectOrdered, name + ": ordered " + r.ordered);
                Check(r.delta.SequenceEqual(expectDelta), name + ": counters " + string.Join(',', r.delta));
                Check(r.barriers == expectBarriers, name + ": barriers " + r.barriers);
            }
            //                                                          r2c covered ordered  c2r covered ordered
            Case("render then dispatch, policy", "R D", true, true, new long[] { 1, 0, 1, 0, 0, 0 }, 1);
            Case("render then dispatch, counted only", "R D", false, false, new long[] { 1, 0, 0, 0, 0, 0 }, 0);
            Case("render, barrier to compute, dispatch", "R f2c D", true, true, new long[] { 1, 1, 0, 0, 0, 0 }, 0);
            Case("dispatch then render, policy", "D R", true, true, new long[] { 0, 0, 0, 1, 0, 1 }, 1);
            Case("dispatch then render, counted only", "D R", false, false, new long[] { 0, 0, 0, 1, 0, 0 }, 0);
            Case("dispatch, full barrier, render", "D all R", true, true, new long[] { 0, 0, 0, 1, 1, 0 }, 0);
            // A barrier to the fragment stage only leaves the vertex stage (vertex fetch, vertex shader reads) unordered.
            Case("dispatch, compute to fragment, render", "D c2f R", true, true, new long[] { 0, 0, 0, 1, 0, 1 }, 1);
            Case("dispatch, compute to fragment, render, counted only", "D c2f R", false, false, new long[] { 0, 0, 0, 1, 0, 0 }, 0);
            // Command buffer boundaries are ordered by MoltenVK's syncFences, which the model leaves out: no switch counted.
            Case("dispatch, next command buffer, render", "D cb R", true, false, new long[] { 0, 0, 0, 0, 0, 0 }, 0);
            Case("render then render (not a switch)", "R R", true, false, new long[] { 0, 0, 0, 0, 0, 0 }, 0);
            Case("render, two dispatches", "R D D", true, true, new long[] { 1, 0, 1, 0, 0, 0 }, 1);
            switches = cases;
        }

        Console.WriteLine(JsonSerializer.Serialize(new
        {
            variant = args[0],
            checks = _checks,
            readers = results.ToDictionary(p => p.Key, p => new { steps = p.Value.Steps, ordered = p.Value.Ordered, barriers = p.Value.Barriers, recorded = p.Value.Recorded }),
            switches,
            completeVulkanProductionSources = true,
            nativeCallsUsed = false,
        }));
    }
}
