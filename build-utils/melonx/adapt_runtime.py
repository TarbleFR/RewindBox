"""Private native loading and JIT symbols; exact replacements on the pinned tree."""
from adapt_session import once, section


def apply(source):
    project = source / 'src/Ryujinx.Library/Ryujinx.Library.csproj'
    once(project, '<RuntimeIdentifiers>ios-arm64</RuntimeIdentifiers>',
         '<RuntimeIdentifiers>ios-arm64;iossimulator-arm64</RuntimeIdentifiers>')
    library = source / 'src/Ryujinx.Library/Library.cs'
    once(library,
         'NativeLibrary.SetDllImportResolver(typeof(SDL3Type).Assembly, (_, assembly, path) => NativeLibrary.Load("@rpath/SDL3.framework/SDL3", assembly, path));',
         'NativeLibrary.SetDllImportResolver(typeof(SDL3Type).Assembly, Ryujinx.Common.EmbeddedNativeLibraries.Resolve);')
    ffmpeg = source / 'src/Ryujinx.Graphics.Nvdec.FFmpeg/Native/FFmpegApi.cs'
    section(ffmpeg, '        static FFmpegApi()\n',
            '        public unsafe delegate void av_log_set_callback_callback', '''        static FFmpegApi()
        {
            NativeLibrary.SetDllImportResolver(typeof(FFmpegApi).Assembly,
                Ryujinx.Common.EmbeddedNativeLibraries.Resolve);
        }''')
    vk = source / 'src/Ryujinx.Graphics.Vulkan/MoltenVK/MVKInitialization.cs'
    once(vk, 'path = path[..^VulkanLib.Length] + "libMoltenVK.dylib";',
         'path = Ryujinx.Common.EmbeddedNativeLibraries.PathFor("libMoltenVK.dylib");')
    once(vk, '        private const string VulkanLib', '        private static int EmbeddedResolverInitialized;\n        private const string VulkanLib')
    once(vk, '((DefaultPathResolver)PathResolver.Default).Resolvers.Insert(0, Resolver);', '''if (System.Threading.Interlocked.Exchange(ref EmbeddedResolverInitialized, 1) != 0) return;
            NativeLibrary.SetDllImportResolver(typeof(MVKInitialization).Assembly,
                Ryujinx.Common.EmbeddedNativeLibraries.Resolve);
            ((DefaultPathResolver)PathResolver.Default).Resolvers.Insert(0, Resolver);''')
    memory = source / 'src/Ryujinx.Memory/DualMappedJitAllocator.cs'
    text = memory.read_text(encoding='utf-8-sig')
    assert text.count('"BreakpointJIT.framework/BreakpointJIT"') == 3
    text = text.replace('"BreakpointJIT.framework/BreakpointJIT"', '"MeloNXJitSupport"')
    for old, new in [('BreakGetJITMapping', 'rewindbox_melonx_jit_map'),
                     ('BreakMarkJITMapping', 'rewindbox_melonx_jit_mark'),
                     ('BreakJITDetach', 'rewindbox_melonx_jit_detach')]:
        assert text.count('EntryPoint = "' + old + '"') == 1
        text = text.replace('EntryPoint = "' + old + '"', 'EntryPoint = "' + new + '"')
    memory.write_text(text)
    once(memory, 'Environment.GetEnvironmentVariable("HAS_TXM") == "1"',
         'Ryujinx.Common.EmbeddedNativeLibraries.UniversalJit')
    once(memory, 'Environment.GetEnvironmentVariable("DUAL_MAPPED_JIT") == "1"', 'true')
    once(memory, '        public nint RwPtr { get; private set; }', '''        static DualMappedJitAllocator()
        {
            NativeLibrary.SetDllImportResolver(typeof(DualMappedJitAllocator).Assembly,
                Ryujinx.Common.EmbeddedNativeLibraries.Resolve);
        }

        public nint RwPtr { get; private set; }''')
    return [project, library, ffmpeg, vk, memory]
