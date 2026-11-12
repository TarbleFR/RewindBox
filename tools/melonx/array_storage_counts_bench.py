#!/usr/bin/env python3
"""Host cost of a texture array barrier pass after an element change, before and after adapt_array_storage_counts.

    DOTNET=/path/to/dotnet python3 tools/melonx/array_storage_counts_bench.py <control prepared tree> <candidate prepared tree>

Builds the production TextureStorage and TextureArray barrier members of each tree into the adapt_array_storage_counts
fixture (test/melonx_array_storage_counts/Program.cs, whose script is replaced by a timing loop with no logging and no
attachment writes, so a pass is its walk and its storage loop), with EncodingPolicy.IncrementalArrayDescriptors on, then
times, per configuration: one change of 40 elements (some to storages new to the set), then one barrier pass. Prints the
microseconds per pass and per element change of each tree. The array sizes cover the device's average walk (IPA 727
Hogwarts Legacy: 61-64 million elements over 806-1 125 rebuilds per 5 s, about 54 000 per rebuild) and the largest
bindless array (524 288). Host figures are not iPhone figures: they rank the two code paths and give the share of the
walk in a pass; the device's own "texture array barrier passes ... ms" line is the measurement that counts.
"""
from pathlib import Path
import json, os, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_descriptor_updates import method  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
STORAGE_METHODS = ('        public void AddStoreOpUsage(bool depthStencil)',
                   '        public void QueueLoadOpBarrier(CommandBufferScoped cbs, bool depthStencil)',
                   '        public void QueueWriteToReadBarrier(CommandBufferScoped cbs, AccessFlags dstAccessFlags, PipelineStageFlags dstStageFlags)')
ARRAY_METHODS = ('        public void SetTextures(int index, ITexture[] textures)', '        private void SetDirty(bool storageChanged)',
                 '        public void QueueWriteToReadBarriers(CommandBufferScoped cbs, PipelineStageFlags stageFlags)',
                 '        private static string BarrierText()')
MOVE = '        private void MoveStorage(TextureStorage previous, TextureStorage current)'
CONFIGS = [(54000, 600, '1.0'), (54000, 600, '0.3'), (524288, 200, '1.0'), (524288, 200, '0.3')]
DISTINCT, CHANGE = 36, 40

BENCH_MAIN = '''    public static int Main(string[] args)
    {
        int size = int.Parse(args[0]); int rounds = int.Parse(args[1]);
        double fill = double.Parse(args[2], System.Globalization.CultureInfo.InvariantCulture);
        int distinct = int.Parse(args[3]); int change = int.Parse(args[4]);
        var random = new Random(7);
        var gd = new Ryujinx.Graphics.Vulkan.VulkanRenderer { IsMoltenVk = true, MoltenVkTracksArgumentBufferHazards = false };
        gd.PipelineInternal = new Ryujinx.Graphics.Vulkan.PipelineInternal { Gd = gd, DeferPolicy = false, IsTBDR = true };
        int storageCount = distinct * 2;
        var views = new Ryujinx.Graphics.Vulkan.TextureView[storageCount];
        for (int i = 0; i < storageCount; i++)
            views[i] = new Ryujinx.Graphics.Vulkan.TextureView(new Ryujinx.Graphics.Vulkan.TextureStorage(i, gd, Ryujinx.Graphics.GAL.Format.R8G8B8A8Unorm, 1, 1), "v" + i);
        var array = new Ryujinx.Graphics.Vulkan.TextureArray(gd, size, true);
        var all = new Ryujinx.Graphics.GAL.ITexture[size];
        for (int i = 0; i < size; i++) all[i] = random.NextDouble() < fill ? views[random.Next(distinct)] : null;
        array.SetTextures(0, all);
        var cbs = new Ryujinx.Graphics.Vulkan.CommandBufferScoped { CommandBufferIndex = 0 };
        array.QueueWriteToReadBarriers(cbs, PipelineStageFlags.FragmentShaderBit);
        var batch = new Ryujinx.Graphics.GAL.ITexture[change];
        long ticks = 0;
        for (int pass = 0; pass < 2; pass++) // the first loop warms the code up; the second is timed
        {
            ticks = 0;
            for (int r = 0; r < rounds; r++)
            {
                int start = random.Next(size - change);
                for (int i = 0; i < change; i++) batch[i] = views[random.Next(storageCount)];
                array.SetTextures(start, batch);
                long t0 = System.Diagnostics.Stopwatch.GetTimestamp();
                array.QueueWriteToReadBarriers(cbs, PipelineStageFlags.FragmentShaderBit);
                ticks += System.Diagnostics.Stopwatch.GetTimestamp() - t0;
                Ryujinx.Graphics.Vulkan.World.Log.Clear();
            }
        }
        double usPass = ticks * 1e6 / System.Diagnostics.Stopwatch.Frequency / rounds;
        long t1 = System.Diagnostics.Stopwatch.GetTimestamp();
        for (int r = 0; r < rounds; r++)
        {
            int start = random.Next(size - change);
            for (int i = 0; i < change; i++) batch[i] = views[random.Next(storageCount)];
            array.SetTextures(start, batch);
        }
        double usSet = (System.Diagnostics.Stopwatch.GetTimestamp() - t1) * 1e6 / System.Diagnostics.Stopwatch.Frequency / rounds;
        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object> { ["usPerPass"] = Math.Round(usPass, 2), ["usPerSetTextures"] = Math.Round(usSet, 2) }));
        return 0;
    }
}
'''


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def between(text, start, end_line):
    first = text.index(start)
    last = text.index(end_line, first) + len(end_line)
    return text[first:text.index('\n', last) + 1]


def build(tree, work):
    program = (ROOT / 'test/melonx_array_storage_counts/Program.cs').read_text()
    program = program[:program.index('    public static int Main(string[] args)')] + BENCH_MAIN
    storage = read(tree, VULKAN + 'TextureStorage.cs')
    array = read(tree, VULKAN + 'TextureArray.cs')
    members = [method(array, s) for s in ARRAY_METHODS] + ([method(array, MOVE)] if MOVE in array else [])
    work.mkdir(parents=True)
    (work / 'Program.cs').write_text(
        program.replace('//__STORAGE_FIELDS__\n', between(storage, '        private AccessFlags _lastModificationAccess;', 'private PipelineStageFlags _readCoveredStages;'))
        .replace('//__STORAGE_METHODS__\n', '\n\n'.join(method(storage, s) for s in STORAGE_METHODS) + '\n')
        .replace('//__ARRAY_FIELDS__\n', between(array, '        private HashSet<TextureStorage> _storages;', '_barrierTicks, _barrierSkips;'))
        .replace('//__ARRAY_METHODS__\n', '\n\n'.join(members) + '\n'))
    (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks><Optimize>true</Optimize>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0162;0169;0414;8500;CS0649;CS0169</NoWarn>
<NuGetAudit>false</NuGetAudit></PropertyGroup>
<ItemGroup><PackageReference Include="Silk.NET.Vulkan" Version="2.22.0" /></ItemGroup></Project>''')
    pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
    result = subprocess.run([DOTNET, 'build', str(work / 'Probe.csproj'), '-c', 'Release', '-nologo'], cwd=work, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(result.stdout[-4000:] + result.stderr[-2000:])
    return work / 'bin/Release/net10.0/Probe.dll'


def main():
    trees = {'control': Path(sys.argv[1]).resolve(), 'candidate': Path(sys.argv[2]).resolve()}
    with tempfile.TemporaryDirectory(prefix='melonx-array-storage-bench-') as temporary:
        probes = {side: build(tree, Path(temporary) / side) for side, tree in trees.items()}
        print('elements fill   control us/pass  candidate us/pass   control us/change  candidate us/change')
        for size, rounds, fill in CONFIGS:
            row = {}
            for side, probe in probes.items():
                out = subprocess.run([DOTNET, str(probe), str(size), str(rounds), fill, str(DISTINCT), str(CHANGE)],
                                     capture_output=True, text=True, check=True).stdout
                row[side] = json.loads(next(line for line in out.splitlines() if line.startswith('{')))
            print('%8d %4s %16.2f %18.2f %19.2f %20.2f' % (size, fill, row['control']['usPerPass'], row['candidate']['usPerPass'],
                                                       row['control']['usPerSetTextures'], row['candidate']['usPerSetTextures']))


if __name__ == '__main__':
    main()
