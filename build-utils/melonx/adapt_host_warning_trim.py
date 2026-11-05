"""Act on a host memory warning while the device has 12 % or less available, with the flush-free trim.

Build 658, 5 November 2026, first player (private logs, not in the repository), Hogwarts Legacy, pid 11152: the device
has 8-12 % of its RAM available from 03:11:04 to the end of the session while this process keeps 2.09 GiB or more of
headroom to its own limit. iOS sent one memoryWarning, at 03:20:04 ("memory 4553/2102/11/2": footprint 4553 MiB,
2102 MiB headroom, device 11 %). GpuContext.TrimCaches ignored it: it trims only when the headroom is under 768 MiB or
the device is at 7 % or less (DeviceShortPercent). The one trim of the session ran at 03:13:39 at device 7 % and released
87 MiB of GPU caches without a flush ("device short only: kept 18 MiB", the adapt_device_short_trim path).

Mechanism (read in the Core 658 preparation): a host report (the UIKit memoryWarning through report_memory_pressure, or
the dispatch memory pressure source) sets MemoryPressureMonitor's pending level; Switch.ProcessFrame hands it to
TrimCaches on the GPU thread. GpuContext.CheckHostMemory also calls TrimCaches, once every 10 s, but only while the
device is at DeviceShortPercent (7 %) or less. With a comfortable headroom TrimCaches then runs the freeOnly trim
(adapt_device_short_trim): only textures the cache alone holds and with no GPU-written data, destroyed without a flush;
the buffer cache trims as before.

Change (GpuContext.cs only): TrimCaches counts the device as short up to HostReportedDeviceShortPercent (12 %) instead of
7 %. The periodic trim of CheckHostMemory still calls it only at 7 % or less, so it is unchanged; a host report with the
device at 8-12 % and a comfortable headroom now runs the freeOnly trim instead of being ignored (above 12 % it is ignored
as before); the trims under this process's own pressure (headroom under 768 MiB) are unchanged, as are the 2 s minimum
interval, targets, floors and the buffer cache. Not measured on an iPhone. Fail closed on drift: GpuContext.cs must be
the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Gpu/GpuContext.cs': '6c476ac18590b0f02f41a3ce3b15215a92c148a80715a1fe4d3147032f7c0e52',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    context = paths['src/Ryujinx.Graphics.Gpu/GpuContext.cs']

    once(context, '''            bool deviceShort = device >= 0 && device <= DeviceShortPercent;
''', '''            // RewindBox (adapt_host_warning_trim): a host report counts the device short up to 12 %. The periodic trim of
            // CheckHostMemory calls this only at DeviceShortPercent or less, so it is unchanged.
            bool deviceShort = device >= 0 && device <= HostReportedDeviceShortPercent;
''')

    once(context, '''        private const int DeviceShortPercent = 7;
''', '''        private const int DeviceShortPercent = 7;
        // RewindBox (adapt_host_warning_trim): Hogwarts Legacy on an 8 GiB iPhone plays at 8-12 % device available and got its
        // memoryWarning at 11 %; with a comfortable headroom the trim it then runs is the flush-free one.
        private const int HostReportedDeviceShortPercent = 12;
''')
    return list(paths.values())
