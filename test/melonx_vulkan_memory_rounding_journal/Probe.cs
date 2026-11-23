// Run against the candidate's production Ryujinx.Graphics.Vulkan assembly (test-only InternalsVisibleTo, no Vulkan
// device): real blocks published by the production InsertBlock and removed by the production Free, a real MemoryAllocator
// whose AllocateDeviceMemory finds no memory type (so it returns before any Vulkan call, through the timing wrapper), its
// UsageText, and one "vulkanMemory sample" line written by RenderStageTimer.Log to a temporary engine journal.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

const ulong KiB = 1024;
var flags = BindingFlags.NonPublic | BindingFlags.Instance;
var insert = typeof(MemoryAllocatorBlockList).GetMethod("InsertBlock", flags);
var buffers = new MemoryAllocatorBlockList(null, default, 1, 16, true);
var buffer20 = new MemoryAllocatorBlockList.Block(default, nint.Zero, 20 * KiB, true);
var buffer48 = new MemoryAllocatorBlockList.Block(default, nint.Zero, 48 * KiB, true);
var images = new MemoryAllocatorBlockList(null, default, 0, 16, false);
var image52 = new MemoryAllocatorBlockList.Block(default, nint.Zero, 52 * KiB, true);
foreach (var (list, block) in new[] { (buffers, buffer20), (buffers, buffer48), (images, image52) })
{
    block.Allocate(block.Size, 256);
    insert.Invoke(list, new object[] { block });
}
var allocator = (MemoryAllocator)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(MemoryAllocator));
typeof(MemoryAllocator).GetField("_blockLists", flags).SetValue(allocator, new List<MemoryAllocatorBlockList> { images, buffers });
typeof(MemoryAllocator).GetField("_lock", flags).SetValue(allocator, new ReaderWriterLockSlim(LockRecursionPolicy.NoRecursion));
var requirements = new MemoryRequirements { Size = 4096, Alignment = 256, MemoryTypeBits = 1 };
int empty = 0;
for (int i = 0; i < 3; i++) empty += allocator.AllocateDeviceMemory(requirements, MemoryPropertyFlags.HostVisibleBit, isBuffer: true).Memory.Handle == 0 ? 1 : 0;
for (int i = 0; i < 2; i++) empty += allocator.AllocateDeviceMemory(requirements, MemoryPropertyFlags.DeviceLocalBit).Memory.Handle == 0 ? 1 : 0;
string first = allocator.UsageText();
string second = allocator.UsageText();
images.Free(image52, 0, image52.Size);
string third = allocator.UsageText();

string journal = Path.Combine(Path.GetTempPath(), "melonx-vulkan-rounding-" + Environment.ProcessId, "MeloNX-core.log");
Directory.CreateDirectory(Path.GetDirectoryName(journal));
Ryujinx.Common.EmbeddedLaunchDiagnostics.ConfigureJournal(journal);
RenderStageTimer.MemoryUsage = allocator.UsageText;
typeof(RenderStageTimer).GetMethod("Log", BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, new object[] { 1000L });
string[] journaled = File.ReadAllLines(journal).Where(l => l.Contains("\"stage\":\"vulkanMemory\"")).ToArray();
Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, object>
{
    ["empty"] = empty, ["first"] = first, ["second"] = second, ["third"] = third, ["journaled"] = journaled,
}));
