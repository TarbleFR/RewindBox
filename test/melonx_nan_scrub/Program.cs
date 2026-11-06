// Probe of adapt_nan_scrub, built against the production Ryujinx.Graphics.Vulkan and Ryujinx.Graphics.Gpu of one
// variant (control: the Core 670 preparation; candidate: the final preparation).
// - codeGenVersion: the REAL DiskCacheHostStorage.CodeGenVersion (reflection) with the scrub off and on.
// - candidate: the REAL SpirvNanScrub.Scrub emits a SPIR-V function (Spv.Generator, as the translator does); the probe
//   decodes the emitted words and evaluates them with a small interpreter of exactly the opcodes found (every value is
//   32 bits; Bitcast keeps the bits), on edge inputs. Unknown opcodes in the function body fail the probe.
// - candidate: the native title note (EmbeddedNoteLaunchTitle) as delivered, on Hogwarts, SSBU and the reset.
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;

#if CANDIDATE
static partial class Library
{
//__CORE671_RUNTIME__
    public static void NoteTitle(ulong title) => EmbeddedNoteLaunchTitle(title);
}
#endif

static class Probe
{
    static uint CodeGenVersion()
    {
        Type storage = typeof(Ryujinx.Graphics.Gpu.GpuContext).Assembly.GetType("Ryujinx.Graphics.Gpu.Shader.DiskCache.DiskCacheHostStorage", true);
        const BindingFlags Flags = BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public;
        PropertyInfo property = storage.GetProperty("CodeGenVersion", Flags);
        if (property != null) return (uint)property.GetValue(null);
        return (uint)storage.GetField("CodeGenVersion", Flags).GetRawConstantValue();
    }

#if CANDIDATE
    static readonly Dictionary<ushort, string> Known = new()
    {
        [124] = "Bitcast", [199] = "BitwiseAnd", [197] = "BitwiseOr", [170] = "IEqual", [171] = "INotEqual",
        [167] = "LogicalAnd", [169] = "Select",
    };

    // Returns the function's result bits for each input, and the opcode histogram of its body.
    static (Dictionary<string, string> results, Dictionary<string, int> opcodes) Evaluate(uint[] inputs)
    {
        var module = new Spv.Generator.Module(0x00010300);
        module.AddCapability(Spv.Specification.Capability.Shader);
        module.SetMemoryModel(Spv.Specification.AddressingModel.Logical, Spv.Specification.MemoryModel.GLSL450);
        Spv.Generator.Instruction f32 = module.TypeFloat(32);
        Spv.Generator.Instruction function = module.Function(f32, Spv.Specification.FunctionControlMask.MaskNone, module.TypeFunction(f32, false, f32));
        module.AddFunction(function);
        Spv.Generator.Instruction parameter = module.FunctionParameter(f32);
        module.AddLabel(module.Label());
        module.ReturnValue(Ryujinx.Graphics.Shader.CodeGen.Spirv.SpirvNanScrub.Scrub(module, parameter));
        module.FunctionEnd();
        byte[] bytes = module.Generate();

        var words = new uint[bytes.Length / 4];
        Buffer.BlockCopy(bytes, 0, words, 0, bytes.Length);
        if (words[0] != 0x07230203) throw new InvalidOperationException("not SPIR-V");

        var constants = new Dictionary<uint, uint>();
        var body = new List<uint[]>();
        uint parameterId = 0, returnId = 0;
        bool inFunction = false;
        var histogram = new Dictionary<string, int>();
        for (int i = 5; i < words.Length;)
        {
            ushort opcode = (ushort)(words[i] & 0xFFFF);
            int count = (int)(words[i] >> 16);
            uint[] operands = words[(i + 1)..(i + count)];
            i += count;
            switch (opcode)
            {
                case 43: constants[operands[1]] = operands[2]; break;           // OpConstant
                case 54: inFunction = true; break;                              // OpFunction
                case 55: parameterId = operands[1]; break;                     // OpFunctionParameter
                case 248: break;                                                // OpLabel
                case 254: returnId = operands[0]; break;                       // OpReturnValue
                case 56: inFunction = false; break;                            // OpFunctionEnd
                default:
                    if (!inFunction) break;
                    if (!Known.ContainsKey(opcode)) throw new InvalidOperationException("unexpected opcode " + opcode);
                    var op = new uint[operands.Length + 1];
                    op[0] = opcode;
                    operands.CopyTo(op, 1);
                    body.Add(op);
                    histogram[Known[opcode]] = histogram.GetValueOrDefault(Known[opcode]) + 1;
                    break;
            }
        }

        var results = new Dictionary<string, string>();
        foreach (uint input in inputs)
        {
            var values = new Dictionary<uint, uint>(constants) { [parameterId] = input };
            foreach (uint[] op in body)
            {
                uint result = op[2];
                uint A(int k) => values[op[3 + k]];
                values[result] = (ushort)op[0] switch
                {
                    124 => A(0),
                    199 => A(0) & A(1),
                    197 => A(0) | A(1),
                    170 => A(0) == A(1) ? 1u : 0u,
                    171 => A(0) != A(1) ? 1u : 0u,
                    167 => (A(0) != 0 && A(1) != 0) ? 1u : 0u,
                    169 => A(0) != 0 ? A(1) : A(2),
                    _ => throw new InvalidOperationException(),
                };
            }

            results[input.ToString("X8")] = values[returnId].ToString("X8");
        }

        return (results, histogram);
    }
#endif

    static void Main()
    {
        var report = new Dictionary<string, object>();
#if CANDIDATE
        Ryujinx.Graphics.Shader.CodeGen.Spirv.SpirvNanScrub.Enabled = false;
        report["codeGenVersionOff"] = CodeGenVersion();
        Ryujinx.Graphics.Shader.CodeGen.Spirv.SpirvNanScrub.Enabled = true;
        report["codeGenVersionOn"] = CodeGenVersion();
        Ryujinx.Graphics.Shader.CodeGen.Spirv.SpirvNanScrub.Enabled = false;

        uint[] inputs =
        {
            0x00000000, 0x80000000, 0x3FC00000, 0xC0000000, 0x477FE000, 0x7149F2CA, 0x7F7FFFFF, 0xFF7FFFFF, 0x00000001,
            0x7F800000, 0xFF800000, 0x7FC00000, 0x7F800001, 0xFFC00000, 0xFFFFFFFF,
        };
        (Dictionary<string, string> results, Dictionary<string, int> opcodes) = Evaluate(inputs);
        report["scrub"] = results;
        report["opcodes"] = opcodes;

        var notes = new Dictionary<string, bool>();
        foreach ((string name, ulong title) in new[] { ("hogwarts", 0x0100F7E00C70E000UL), ("smash", 0x01006A800016E000UL), ("reset", 0UL) })
        {
            Library.NoteTitle(title);
            notes[name] = Ryujinx.Graphics.Shader.CodeGen.Spirv.SpirvNanScrub.Enabled;
        }

        report["notedNanScrub"] = notes;
#else
        report["codeGenVersion"] = CodeGenVersion();
        report["scrubType"] = Type.GetType("Ryujinx.Graphics.Shader.CodeGen.Spirv.SpirvNanScrub, Ryujinx.Graphics.Shader") != null;
#endif
        Console.WriteLine(JsonSerializer.Serialize(report));
    }
}
