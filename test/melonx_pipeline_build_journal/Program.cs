// Scenarios for melonx_pipeline_build_journal_test.py on the variant's real PipelineCacheManager.cs (control: Core 683
// postimage, no journal; candidate: with adapt_pipeline_build_journal, CANDIDATE). The Vulkan double is
// test/melonx_main_cache_checkpoint/Double.cs. Two sessions of one title share a cache directory.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using FixtureSupport;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

var report = new Dictionary<string, object> { ["variant"] = args[0] };
string root = Path.Combine(Path.GetTempPath(), "melonx-pipeline-build-journal-" + Environment.ProcessId);
Directory.CreateDirectory(root);
Ryujinx.Common.Configuration.AppDataManager.BaseDirPath = root;

PipelineCacheManager Session()
{
    var vk = new Vk();
    var mainLock = new Lock();
    vk.MainLock = mainLock;
    Ryujinx.Common.Logging.Logger.Info.Messages.Clear();
    return new PipelineCacheManager(vk, new VulkanPhysicalDevice(), default, 2, mainLock);
}

string Journal() => Directory.Exists(Path.Combine(root, "cache", "vulkan"))
    ? Directory.GetFiles(Path.Combine(root, "cache", "vulkan"), "*.builds").SingleOrDefault() : null;

void Age(PipelineCacheManager manager) =>
    typeof(PipelineCacheManager).GetField("_buildSummaryTimestamp", BindingFlags.Instance | BindingFlags.NonPublic)
        .SetValue(manager, Environment.TickCount64 - 120_000);

#if CANDIDATE
// Session 1: three render-thread compilations (one key twice) and one worker compilation.
{
    var manager = Session();
    report["session1Start"] = Ryujinx.Common.Logging.Logger.Info.Messages.FirstOrDefault(m => m.StartsWith("Pipeline build journal"));
    manager.NotePipelineBuild(0xA, 600, true);
    manager.NotePipelineBuild(0xB, 900, true);
    manager.NotePipelineBuild(0xB, 700, true);
    Age(manager);
    manager.NotePipelineBuild(0xC, 120, false);
    report["session1Summary"] = Ryujinx.Common.Logging.Logger.Info.Messages.LastOrDefault(m => m.StartsWith("Pipeline compilations"));
    report["journalBytesAfterSession1"] = new FileInfo(Journal()).Length;
    manager.Dispose();
}

// Session 2: A again (lost by session 1) and a new D on the render thread; C again on a worker; then the app is paused.
{
    var manager = Session();
    report["session2Start"] = Ryujinx.Common.Logging.Logger.Info.Messages.FirstOrDefault(m => m.StartsWith("Pipeline build journal"));
    manager.NotePipelineBuild(0xA, 650, true);
    manager.NotePipelineBuild(0xD, 800, true);
    manager.NotePipelineBuild(0xC, 100, false);
    manager.LogBuildSummaryOnPause();
    report["session2Pause"] = Ryujinx.Common.Logging.Logger.Info.Messages.LastOrDefault(m => m.StartsWith("Pipeline compilations"));
    report["journalBytesAfterSession2"] = new FileInfo(Journal()).Length;
    manager.Dispose();
}

// A torn journal tail (a record cut by a crash) is ignored.
{
    using (var stream = new FileStream(Journal(), FileMode.Append)) stream.Write(new byte[5]);
    var manager = Session();
    report["tornTailStart"] = Ryujinx.Common.Logging.Logger.Info.Messages.FirstOrDefault(m => m.StartsWith("Pipeline build journal"));
    manager.Dispose();
}
#else
{
    var manager = Session();
    report["journalFile"] = Journal() != null;
    manager.Dispose();
}
#endif

report["errors"] = Ryujinx.Common.Logging.Logger.Error.Lines;
report["warnings"] = Ryujinx.Common.Logging.Logger.Warning.Lines;
Directory.Delete(root, true);
Console.WriteLine(JsonSerializer.Serialize(report));
