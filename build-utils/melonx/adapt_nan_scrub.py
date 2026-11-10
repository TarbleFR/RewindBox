"""Hogwarts Legacy: non-finite colour writes are made finite in the SPIR-V the shader translator emits.

IPA 666 (Core 663) and IPA 669 (Core 667), private screenshots, not in the repository: in the "Suivre le professeur
Fig" area the sky shows black regions with a blue then cyan rim, stair-stepped in large blocks and dithered at the
edge, behind every opaque object, growing over frames. That is the look of NaN or infinite values in a low-resolution
sky, cloud or atmosphere buffer that a later pass (temporal history, blur, upsample) spreads. Core 661's barrier lever
did not change it. Core 667 compiled Hogwarts with Metal safe math instead of fast math, which made MoltenVK 1.4.2
compile the whole pipeline cache again before the first frame (IPA 669: no frame in 232 s); Core 670 removed it.

Change, title-gated by SpirvNanScrub.Enabled (set by the launch preflight for Hogwarts Legacy only):
- every FP32 fragment colour output store and every FP32 image store passes through SpirvNanScrub.Scrub: NaN becomes
  0, +/-Inf becomes +/-65504 (the largest finite half), finite values are unchanged. The test is done on the integer
  bits (exponent all ones), which Metal's fast math cannot assume away; fast math stays on for every shader.
- the host shader cache version differs while it is enabled (DiskCacheHostStorage.CodeGenVersion), so Hogwarts'
  cached translations made without the scrub are rebuilt once from its guest cache; other titles keep their cache.
Only stores to colour outputs and images change; buffers, depth and every other title's shaders are untouched.
Fail closed on drift: the files must be the Core 670 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Shader/CodeGen/Spirv/SpirvGenerator.cs':
        '44886a62e980a4193b9801c995a899e068979cc06b04ae866e2ce239d0d7964b',
    'src/Ryujinx.Graphics.Shader/CodeGen/Spirv/Instructions.cs':
        '22f5bdf4b72a2bc2b3a7c80bca5ab9e4db5222cfd956754086b0cbe410fdda06',
    'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/DiskCacheHostStorage.cs':
        'abefaf59a80a9209f0df4fdabc649d0d833dfcbf2e9c8fc7151eb9968093e950',
}

GENERATOR_OLD = '''    static class SpirvGenerator
    {
'''
GENERATOR_NEW = '''    // RewindBox (adapt_nan_scrub): non-finite colour writes made finite for one title (Hogwarts Legacy's sky blocks).
    public static class SpirvNanScrub
    {
        // Set by the launch preflight before the shader cache loads; read by the translator threads.
        public static bool Enabled;

        public const uint ExponentMask = 0x7F800000u;
        public const uint MantissaMask = 0x007FFFFFu;
        public const uint SignMask = 0x80000000u;
        public const uint HalfMaxBits = 0x477FE000u; // 65504, the largest finite half

        // NaN -> 0, +/-Inf -> +/-65504, finite values unchanged. Integer bit tests, so fast math cannot fold them away.
        public static SpvInstruction Scrub(Spv.Generator.Module module, SpvInstruction value)
        {
            SpvInstruction u32 = module.TypeInt(32, 0);
            SpvInstruction f32 = module.TypeFloat(32);
            SpvInstruction boolType = module.TypeBool();

            SpvInstruction bits = module.Bitcast(u32, value);
            SpvInstruction exponentMask = module.Constant(u32, ExponentMask);
            SpvInstruction nonFinite = module.IEqual(boolType, module.BitwiseAnd(u32, bits, exponentMask), exponentMask);
            SpvInstruction mantissa = module.BitwiseAnd(u32, bits, module.Constant(u32, MantissaMask));
            SpvInstruction isNan = module.LogicalAnd(boolType, nonFinite, module.INotEqual(boolType, mantissa, module.Constant(u32, 0u)));
            SpvInstruction signedHalfMax = module.Bitcast(f32, module.BitwiseOr(u32,
                module.BitwiseAnd(u32, bits, module.Constant(u32, SignMask)), module.Constant(u32, HalfMaxBits)));
            SpvInstruction replacement = module.Select(f32, isNan, module.Constant(f32, 0f), signedHalfMax);

            return module.Select(f32, nonFinite, replacement, value);
        }
    }

    static class SpirvGenerator
    {
'''

STORE_OLD = '''            if (isStore)
            {
                context.Store(pointer, context.Get(varType, operation.GetSource(operation.SourcesCount - 1)));
                return OperationResult.Invalid;
            }
'''
STORE_NEW = '''            if (isStore)
            {
                SpvInstruction value = context.Get(varType, operation.GetSource(operation.SourcesCount - 1));

                // RewindBox (adapt_nan_scrub): an FP32 colour output never receives NaN or Inf for the scrubbed title.
                if (SpirvNanScrub.Enabled && varType == AggregateType.FP32 && operation.StorageKind == StorageKind.Output &&
                    operation.GetSource(0) is AstOperand { Type: OperandType.Constant } ioOperand &&
                    (IoVariable)ioOperand.Value == IoVariable.FragmentOutputColor)
                {
                    value = SpirvNanScrub.Scrub(context, value);
                }

                context.Store(pointer, value);
                return OperationResult.Invalid;
            }
'''

IMAGE_OLD = '''            SpvInstruction texel = context.CompositeConstruct(context.TypeVector(context.GetType(componentType), ComponentsCount), cElems);

            context.ImageWrite(image, pCoords, texel, ImageOperandsMask.MaskNone);
'''
IMAGE_NEW = '''            // RewindBox (adapt_nan_scrub): an FP32 image store never writes NaN or Inf for the scrubbed title.
            if (SpirvNanScrub.Enabled && componentType == AggregateType.FP32)
            {
                for (int i = 0; i < ComponentsCount; i++)
                {
                    cElems[i] = SpirvNanScrub.Scrub(context, cElems[i]);
                }
            }

            SpvInstruction texel = context.CompositeConstruct(context.TypeVector(context.GetType(componentType), ComponentsCount), cElems);

            context.ImageWrite(image, pCoords, texel, ImageOperandsMask.MaskNone);
'''

VERSION_OLD = '''        private const uint CodeGenVersion = 7353 + 0x5242_0002; // RewindBox: adapt_bindless, adapt_bindless_sources
'''
VERSION_NEW = '''        private const uint UnscrubbedCodeGenVersion = 7353 + 0x5242_0002; // RewindBox: adapt_bindless, adapt_bindless_sources

        // RewindBox (adapt_nan_scrub): translations made with the NaN scrub are another code generation, so a cache
        // written without it is translated again once from the guest cache (and the reverse).
        private const uint NanScrubCodeGenVersionStep = 0x0001_0000;

        private static uint CodeGenVersion => Ryujinx.Graphics.Shader.CodeGen.Spirv.SpirvNanScrub.Enabled
            ? UnscrubbedCodeGenVersion + NanScrubCodeGenVersionStep
            : UnscrubbedCodeGenVersion;
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    once(paths['src/Ryujinx.Graphics.Shader/CodeGen/Spirv/SpirvGenerator.cs'], GENERATOR_OLD, GENERATOR_NEW)
    instructions = paths['src/Ryujinx.Graphics.Shader/CodeGen/Spirv/Instructions.cs']
    once(instructions, STORE_OLD, STORE_NEW)
    once(instructions, IMAGE_OLD, IMAGE_NEW)
    once(paths['src/Ryujinx.Graphics.Gpu/Shader/DiskCache/DiskCacheHostStorage.cs'], VERSION_OLD, VERSION_NEW)
    return list(paths.values())
