"""Attribute where each presented image comes from: the GPU's rendering, or guest memory (diagnostics only).

IPA 643 (MeloNX Core 642, Hogwarts Legacy v1.0.5, 4 November 2026; private logs and a screen recording, not in the
repository): frames are presented about 30 times a second while the screen stays black at launch, and later the
recording shows single whole frames older than their neighbours (25 in 2 minutes) and two black or dim single frames.
The logs cannot tell which image Ryujinx.Graphics.Gpu.Window.Present handed to the host: the texture it finds or creates
for the guest's buffer can hold the GPU's rendering of that buffer, or bytes reloaded from guest memory (a texture
created at present, or one a guest write made dirty while the GPU had not modified it), which are black before the
guest wrote them and an older frame after. A re-created texture at the address of a swap buffer gives the same. Which
of these happens at the black launch and at the stale frames decides the correction (presentation path, texture cache
lifetime, or GPU ordering), so nothing is changed before it is known.

Change, diagnostics only (no decision, synchronisation, copy or lifetime changes): before Present synchronises the
texture, it records whether the GPU had modified it (TextureGroup.AnyHandleModified), whether its data will be reloaded
from guest memory (not modified and dirty: TextureGroup.CheckDirty without consuming), whether the texture object at that
address differs from the one presented there before (re-created), and whether the address repeats the previous present.
The first 8 presents from guest memory or from a re-created texture are logged once each (present index, address,
format, size, scale, flags); a summary of the counts every 300 presents, at most 64 times. The identities are kept as
object hash codes in a map of at most 16 addresses (no texture reference is held). Not measured on an iPhone.
Fail closed on drift: Window.cs must be the Core 642 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Gpu/Window.cs': '794edf455bb2945a77c23e971757f552fbe81fe26293dc3ea053360dde17cd39',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    window = paths['src/Ryujinx.Graphics.Gpu/Window.cs']
    once(window, '''        private volatile bool _unboundedPresentMode;
''', '''        private volatile bool _unboundedPresentMode;

        // RewindBox (adapt_present_source_attribution): where presented images come from, counted on the present thread.
        private const int PresentSourceLineLimit = 8;
        private const int PresentSourceSummaryInterval = 300;
        private const int PresentSourceSummaryLimit = 64;
        private const int PresentAddressLimit = 16;
        private readonly System.Collections.Generic.Dictionary<ulong, int> _presentedByAddress = new();
        private long _presents, _presentsFromGuest, _presentsNotModified, _presentsReplaced, _presentsRepeated, _presentsFirstAtAddress;
        private ulong _lastPresentAddress;
        private int _presentSourceLines, _presentSourceSummaries;
''')
    once(window, '''                pt.Cache.Tick();

                texture.SynchronizeMemory();
''', '''                pt.Cache.Tick();

                // RewindBox (adapt_present_source_attribution): before the synchronisation, diagnostics only.
                NotePresentSource(texture);

                texture.SynchronizeMemory();
''')
    once(window, '''        /// <summary>
        /// Presents all available ready frames, optionally capping unbounded present mode.
''', '''        /// <summary>
        /// RewindBox (adapt_present_source_attribution): records whether the presented texture holds the GPU's rendering or
        /// will be reloaded from guest memory, and whether it is a new texture object at an address presented before. Reads
        /// state only (CheckDirty does not consume the dirty flags); logs the first 8 such presents and a summary every 300.
        /// </summary>
        private void NotePresentSource(Image.Texture texture)
        {
            ulong address = texture.Range.Count != 0 ? texture.Range.GetSubRange(0).Address : 0;
            bool modified = texture.Group != null && texture.Group.AnyHandleModified();
            bool fromGuest = texture.Group != null && !modified && texture.Group.CheckDirty(texture, false);
            int identity = System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(texture);
            bool known = _presentedByAddress.TryGetValue(address, out int last);
            bool replaced = known && last != identity;
            bool repeated = _presents != 0 && address == _lastPresentAddress;

            if (!known && _presentedByAddress.Count >= PresentAddressLimit)
            {
                _presentedByAddress.Clear();
            }

            _presentedByAddress[address] = identity;
            _lastPresentAddress = address;
            _presents++;
            _presentsFromGuest += fromGuest ? 1 : 0;
            _presentsNotModified += modified ? 0 : 1;
            _presentsReplaced += replaced ? 1 : 0;
            _presentsRepeated += repeated ? 1 : 0;
            _presentsFirstAtAddress += known ? 0 : 1;

            if ((fromGuest || replaced) && _presentSourceLines < PresentSourceLineLimit)
            {
                _presentSourceLines++;
                Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu,
                    $"Present source #{_presentSourceLines}: present {_presents} at 0x{address:X}, {texture.Info.FormatInfo.Format} " +
                    $"{texture.Info.Width}x{texture.Info.Height} scale {texture.ScaleFactor}; GPU-modified {modified}, " +
                    $"reloaded from guest memory {fromGuest}, re-created texture {replaced}, same address as previous {repeated}");
            }

            if (_presents % PresentSourceSummaryInterval == 0 && _presentSourceSummaries < PresentSourceSummaryLimit)
            {
                _presentSourceSummaries++;
                Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu,
                    $"Present sources: {_presents} presents, from guest memory {_presentsFromGuest}, not GPU-modified " +
                    $"{_presentsNotModified}, re-created textures {_presentsReplaced}, same address as previous {_presentsRepeated}, " +
                    $"first at an address {_presentsFirstAtAddress}");
            }
        }

        /// <summary>
        /// Presents all available ready frames, optionally capping unbounded present mode.
''')
    return list(paths.values())
