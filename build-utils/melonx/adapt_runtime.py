"""Private native loading and JIT symbols; exact replacements on the pinned tree."""
from adapt_session import once, section


def disable_ios_host_import(source):
    """Use the existing texture readback buffer on iOS instead of MoltenVK host imports.

    On the Build 529 iPhone session, VK_EXT_external_memory_host is advertised,
    but vkCreateBuffer with HOST_ALLOCATION_BIT_EXT returns ErrorFeatureNotPresent
    during TextureGroup.FlushIntoBuffer. The guest then loses its render worker.
    Do not change the behavior of macOS/Linux/Windows renderers.
    """
    initialization = source / 'src/Ryujinx.Graphics.Vulkan/VulkanInitialization.cs'
    renderer = source / 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs'
    texture_group = source / 'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs'

    # Ensure the pinned guest already contains the correct copy/readback path.
    fallback = texture_group.read_text(encoding='utf-8-sig')
    assert fallback.count('CreateBuffer((int)Storage.Size, BufferAccess.HostMemory)') == 1
    assert fallback.count('_flushBufferImported = false;') >= 1

    # Do not enable an extension on MoltenVK that is never safe to use here.
    # MoltenVK may expose it even when host-import buffer creation later fails.
    once(initialization,
         '            var enabledExtensions = _requiredExtensions.Union(_desirableExtensions.Intersect(physicalDevice.DeviceExtensions)).ToArray();',
         '''            var enabledExtensions = _requiredExtensions.Union(
                _desirableExtensions.Intersect(physicalDevice.DeviceExtensions)
                    .Where(extension => !OperatingSystem.IsIOS() || extension != ExtExternalMemoryHost.ExtensionName)).ToArray();''')
    # A physical device can advertise an extension that was deliberately not
    # enabled. Mask the capability too, so TextureGroup takes its proven
    # ordinary BufferAccess.HostMemory fallback rather than CreateHostImported.
    once(renderer,
         '                _physicalDevice.IsDeviceExtensionPresent(ExtExternalMemoryHost.ExtensionName),',
         '                !OperatingSystem.IsIOS() && _physicalDevice.IsDeviceExtensionPresent(ExtExternalMemoryHost.ExtensionName),')
    return [initialization, renderer]

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
    once(vk, '            if (path.EndsWith(VulkanLib))', '''            if (path.EndsWith(VulkanLib, StringComparison.Ordinal) ||
                path.EndsWith("libvulkan.1.dylib", StringComparison.Ordinal) ||
                path.EndsWith("libMoltenVK.dylib", StringComparison.Ordinal))''')
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
    # The standalone host explicitly calls init_dualmapping before a game. Do
    # the same through a status-preserving ABI; a tiny separate mmap probe does
    # not prove the real shared code cache or the signal mapping is ready.
    translator = source / 'src/Ryujinx.Cpu/LightningJit/Translator.cs'
    once(translator, '        public static bool InitMemoryCache()', '''        public static void PrepareEmbeddedMapping()
        {
            if (!MemoryBlock.DualMappedEnabled())
                throw new InvalidOperationException("MeloNX dual-mapped JIT is not enabled.");
            DualMappedNoWxCache.InitMemoryCache();
            NativeSignalHandler.InitializeSignalHandler();
            DualMappedNoWxCache.VerifyEmbeddedMapping();
            initialized = true;
        }

        public static bool InitMemoryCache()''')
    cache = source / 'src/Ryujinx.Cpu/LightningJit/Cache/DualMappedNoWxCache.cs'
    once(cache, 'private static readonly ulong SharedCacheSize =', 'private static ulong SharedCacheSize =>')
    once(cache, '_cacheAllocator = new((int)size);', '_cacheAllocator = new(checked((int)size - 16));')
    once(cache, '        public static void InitMemoryCache()', '''        private static bool _embeddedMappingVerified;
        public static unsafe void VerifyEmbeddedMapping()
        {
            if (_sharedCacheAlloc == null || _sharedCacheAlloc.RwPtr == 0 ||
                _sharedCacheAlloc.RxPtr == 0 || _sharedCacheAlloc.RwPtr == _sharedCacheAlloc.RxPtr)
                throw new InvalidOperationException("The real MeloNX JIT aliases are unavailable.");
            // The last 16 bytes are excluded from every cache allocator. Reuse
            // this reserved probe without overwriting translated guest code.
            nint offset = checked((nint)SharedCacheSize - 16);
            if (!_embeddedMappingVerified)
            {
                uint* code = (uint*)(_sharedCacheAlloc.RwPtr + offset);
                code[0] = 0x5289a980; code[1] = 0xd65f03c0;
                JitSupportDarwin.SysIcacheInvalidate(_sharedCacheAlloc.RxPtr + offset, 8);
            }
            var execute = (delegate* unmanaged<uint>)(_sharedCacheAlloc.RxPtr + offset);
            if (execute() != 0x4d4c)
                throw new InvalidOperationException("The real MeloNX JIT code-arena probe failed.");
            _embeddedMappingVerified = true;
        }

        public static void InitMemoryCache()''')
    registration = source / 'src/Ryujinx.Cpu/Signal/UnixSignalHandlerRegistration.cs'
    once(registration, '            int result = sigaction(SIGSEGV, nint.Zero, out SigAction old);',
         '            if (IsDarwin) return GetDarwin(SIGSEGV);\n            int result = sigaction(SIGSEGV, nint.Zero, out SigAction old);')
    once(registration, '            SigAction sig = new()',
         '            if (IsDarwin) return RegisterDarwin(action);\n            SigAction sig = new()')
    once(registration, '            return sigaction(SIGSEGV, ref oldAction, out SigAction _) == 0 &&',
         '            if (IsDarwin) return RestoreDarwin(oldAction);\n            return sigaction(SIGSEGV, ref oldAction, out SigAction _) == 0 &&')
    signal = source / 'src/Ryujinx.Cpu/Signal/NativeSignalHandler.cs'
    once(signal, '        public SignalHandlerRangeArray Ranges;',
         '        public nuint UnixOldBusSigaction;\n        public int UnixOldBusSigaction3Arg;\n        public SignalHandlerRangeArray Ranges;')
    once(signal, '                    _signalHandlerPtr = MapCode(NativeSignalHandlerGenerator.GenerateUnixSignalHandler(_handlerConfig, rangeStructSize));', '''                    // Populate fallbacks before the first handler is installed.
                    var prior = UnixSignalHandlerRegistration.GetSegfaultExceptionHandler();
                    var priorBus = UnixSignalHandlerRegistration.GetBusExceptionHandler();
                    config.UnixOldSigaction = (nuint)prior.sa_handler;
                    config.UnixOldSigaction3Arg = prior.sa_flags & UnixSignalHandlerRegistration.SigInfoFlag;
                    config.UnixOldBusSigaction = (nuint)priorBus.sa_handler;
                    config.UnixOldBusSigaction3Arg = priorBus.sa_flags & UnixSignalHandlerRegistration.SigInfoFlag;
                    _signalHandlerPtr = MapCode(NativeSignalHandlerGenerator.GenerateUnixSignalHandler(_handlerConfig, rangeStructSize));''')
    once(signal, 'config.UnixOldSigaction3Arg = old.sa_flags & 4;',
         'config.UnixOldSigaction3Arg = old.sa_flags & UnixSignalHandlerRegistration.SigInfoFlag;')
    generator = source / 'src/ARMeilleure/Signal/NativeSignalHandlerGenerator.cs'
    once(generator, 'private const int RangeOffset = 20;', 'private const int RangeOffset = 32;')
    once(generator, '''            Operand unixOldSigaction = context.Load(OperandType.I64, Const((ulong)signalStructPtr + UnixOldSigaction));
            Operand unixOldSigaction3Arg = context.Load(OperandType.I64, Const((ulong)signalStructPtr + UnixOldSigaction3Arg));''', '''            Operand unixOldSigaction = context.AllocateLocal(OperandType.I64);
            Operand unixOldSigaction3Arg = context.AllocateLocal(OperandType.I32);
            context.Copy(unixOldSigaction, context.Load(OperandType.I64, Const((ulong)signalStructPtr + UnixOldSigaction)));
            context.Copy(unixOldSigaction3Arg, context.Load(OperandType.I32, Const((ulong)signalStructPtr + UnixOldSigaction3Arg)));
            if (OperatingSystem.IsMacOS() || OperatingSystem.IsIOS())
            {
                Operand useSegv = Label();
                context.BranchIf(useSegv, context.LoadArgument(OperandType.I32, 0), Const(10), Comparison.NotEqual);
                context.Copy(unixOldSigaction, context.Load(OperandType.I64, Const((ulong)signalStructPtr + 20)));
                context.Copy(unixOldSigaction3Arg, context.Load(OperandType.I32, Const((ulong)signalStructPtr + 28)));
                context.MarkLabel(useSegv);
                // SIG_DFL and SIG_IGN are dispositions, never callable addresses.
                Operand callPrevious = Label();
                context.BranchIf(callPrevious, unixOldSigaction, Const(1UL), Comparison.GreaterUI);
                Operand returnIgnored = Label();
                context.BranchIf(returnIgnored, unixOldSigaction, Const(1UL), Comparison.Equal);
                nint system = NativeLibrary.Load("/usr/lib/libSystem.B.dylib");
                Operand signo = context.LoadArgument(OperandType.I32, 0);
                context.Call(Const((ulong)NativeLibrary.GetExport(system, "signal")), OperandType.I64, signo, Const(0UL));
                context.Call(Const((ulong)NativeLibrary.GetExport(system, "raise")), OperandType.I32, signo);
                context.MarkLabel(returnIgnored);
                context.Return();
                context.MarkLabel(callPrevious);
            }''')
    gpu_fallback = disable_ios_host_import(source)
    return [project, library, ffmpeg, vk, memory, translator, cache, registration, signal, generator, *gpu_fallback]
