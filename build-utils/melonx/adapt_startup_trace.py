"""Localize the observed pre-cache GPU pause without changing cache policy."""
from adapt_session import once


def apply(source):
    renderer = source / 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs'
    operations = [
        ('instance', '            _instance = VulkanInitialization.CreateInstance(Api, logLevel, _getRequiredExtensions());'),
        ('surface', '            _surface = _getSurface(_instance.Instance, Api);'),
        ('physicalDevice', '            _physicalDevice = VulkanInitialization.FindSuitablePhysicalDevice(Api, _instance, _surface, _preferredGpuId);'),
        ('device', '            _device = VulkanInitialization.CreateDevice(Api, _physicalDevice, queueFamilyIndex, maxQueueCount);'),
        ('features', '            LoadFeatures(maxQueueCount, queueFamilyIndex);'),
        ('swapchain', '            _window = new Window(this, _surface, _physicalDevice.PhysicalDevice, _device);'),
    ]
    for name, statement in operations:
        once(renderer, statement, '            using (new Ryujinx.Common.EmbeddedStartupTrace("' + name + '"))\n            {\n    ' + statement + '\n            }')
    manager = source / 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
    once(manager, '            using (MappedSnapshot mainSnapshot = OpenSnapshot(mainCachePath, MainCacheBudget))',
         '            using (new Ryujinx.Common.EmbeddedStartupTrace("mainPipelineCache"))\n            using (MappedSnapshot mainSnapshot = OpenSnapshot(mainCachePath, MainCacheBudget))')
    once(manager, '                using MappedSnapshot workerSnapshot = OpenSnapshot(workerCachePaths[index], workerBudget);',
         '                using var startup = new Ryujinx.Common.EmbeddedStartupTrace("workerPipelineCache" + index);\n                using MappedSnapshot workerSnapshot = OpenSnapshot(workerCachePaths[index], workerBudget);')
    guard = source / 'src/Ryujinx.Cpu/Jit/HostTracked/NativePageTable.cs'
    once(guard, '                throw new InvalidMemoryRegionException();',
         '                throw new InvalidMemoryRegionException($"Native page-table guard: relativeOffset=0x{address:X}; size={size}; write={write}; tableBytes=0x{_nativePageTable.Size - _hostPageSize:X}.");')
    return [renderer, manager, guard]
