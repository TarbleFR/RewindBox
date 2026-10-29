using System;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;

bool control = args[0] == "control";
int checks = 0;
void Check(bool condition, string message) {
    checks++;
    if (!condition) throw new Exception(message);
}
var gd = new VulkanRenderer();
var handle = new BufferHandle(1);
gd.BufferManager.Create(handle);
var texture = new TextureBuffer(gd, new TextureCreateInfo { Width = 32, Height = 1 });
var range = new BufferRange(handle, 0, 128);
texture.SetStorage(range);
var first = texture.GetBufferView(new(), false);
Check(gd.BufferManager.ViewCreates == 1, "Initial view missing");
for (int i = 0; i < 512; i++) {
    // Unrelated staging/temporary buffers come and go between draws.
    var unrelated = new BufferHandle(i + 100);
    gd.BufferManager.Create(unrelated);
    gd.BufferManager.Delete(unrelated);
    texture.SetStorage(range);
    var view = texture.GetBufferView(new(), i % 2 == 0);
    if (!control) Check(view == first, "Unrelated buffer invalidated the view");
}
int steadyCreates = gd.BufferManager.ViewCreates;
Check(steadyCreates == (control ? 513 : 1), "Wrong view reuse count");

gd.BufferManager.Delete(handle);
gd.BufferManager.Create(handle); // IdList may recycle a numeric handle.
texture.SetStorage(range);
var replaced = texture.GetBufferView(new(), true);
Check(replaced != first, "Recycled handle kept stale view");
int before = gd.BufferManager.ViewCreates;
texture.SetStorage(new BufferRange(handle, 16, 112));
texture.GetBufferView(new(), false);
Check(gd.BufferManager.ViewCreates == before + 1, "Changed range kept stale view");
before = gd.BufferManager.ViewCreates;
texture.SetStorage(new BufferRange(handle, 16, 96));
texture.GetBufferView(new(), true);
Check(gd.BufferManager.ViewCreates == before + 1, "Changed size kept stale view");
texture.SetStorage(new BufferRange(new BufferHandle(9999), 0, 32));
Check(texture.GetBufferView(new(), false).Id == 0, "Missing buffer acquired a native view");
texture.SetStorage(range);
Check(texture.GetBufferView(new(), false).Id != 0, "Valid storage failed after missing buffer");
texture.Release();
Check(gd.Textures.Count == 0, "Texture release failed");
Console.WriteLine(JsonSerializer.Serialize(new { mode = control ? "control" : "fixed", checks,
    unrelatedCreations = 512, steadyViewCreates = steadyCreates, physicalDeviceTested = false }));
