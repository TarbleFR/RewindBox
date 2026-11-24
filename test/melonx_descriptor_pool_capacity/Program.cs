using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System.Text.Json;

static (Vk Driver, int Pools) Allocate(uint[] counts, int perSet, int number, bool updateAfterBind = false,
                                      Result secondCreate = Result.Success)
{
    var driver = new Vk();
    using var manager = new DescriptorSetManager(default, 1);
    var sizes = counts.Select(count => new DescriptorPoolSize { DescriptorCount = count }).ToArray();
    var sets = new List<Auto<DescriptorSetCollection>>();
    try
    {
        for (int i = 0; i < number; i++)
        {
            if (i == 1) driver.NextCreateResult = secondCreate;
            sets.Add(manager.AllocateDescriptorSet(driver, default, sizes, 0, perSet, updateAfterBind));
        }
        if (driver.Allocations != number || driver.Destructions.Count != 0 ||
            !sizes.Select(size => size.DescriptorCount).SequenceEqual(counts))
            throw new Exception("Changed set count, premature retirement, or mutation of layout budgets");
    }
    finally
    {
        manager.Dispose();
        foreach (var set in sets) set.Value.Dispose();
    }
    if ((ulong)driver.Destructions.Distinct().Count() != driver.Created ||
        (ulong)driver.Destructions.Count != driver.Created) throw new Exception("Pool lifetime");
    return (driver, (int)driver.Created);
}

bool candidate = args.Single() == "candidate";
var repeated = Allocate([1, 2], 3, 65);
if (!repeated.Driver.RequestedSizes.First().SequenceEqual(new uint[] { 1, 2 }) ||
    !repeated.Driver.RequestedSizes.Skip(1).All(s => s.SequenceEqual(candidate ? new uint[] { 8, 16 } : new uint[] { 1, 2 })) ||
    repeated.Pools != (candidate ? 9 : 65)) throw new Exception("Wrong per-type capacities");
if (Allocate([1, 2], 3, 1).Pools != 1 || Allocate([17], 17, 9).Pools != 9 ||
    Allocate([1], 1, 9, true).Pools != 9 || Allocate([8], 1, 9).Pools != 2)
    throw new Exception("Cold, large, update-after-bind, or pre-sized layout changed");
Lifetime.CheckConcurrentRelease();
if (candidate)
{
    foreach (var result in new[] { Result.ErrorOutOfHostMemory, Result.ErrorOutOfDeviceMemory })
    {
        var retry = Allocate([1], 1, 2, secondCreate: result);
        if (retry.Pools != 2 || !retry.Driver.RequestedSizes.Select(s => s.Single()).SequenceEqual(new uint[] { 1, 8, 1 }))
            throw new Exception("Original budget missing on allocation failure");
    }
    try
    {
        Allocate([1], 1, 2, secondCreate: Result.ErrorUnknown);
        throw new Exception("Driver error hidden");
    }
    catch (VulkanException e) when (e.ResultCode == Result.ErrorUnknown) { }
}
Console.WriteLine(JsonSerializer.Serialize(new { pools = repeated.Pools, sets = 65 }));
