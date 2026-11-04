"""Release a closed session's layer binders, so its emulated Switch can be collected, and journal what stays reachable.

IPA 650 (Core 649), maintainer's iPhone, 4 November 2026 (private logs, not in the repository): two Hogwarts Legacy
sessions (S1, S2) in one process (pid 8767). Each closed session's managed heap survives the forced full collection of
its teardown (S1 342 MB, S2 690 MB still live afterwards); the next session starts about 400 MB higher. Older builds
show the same growth.

Mechanism (a code root, read in the Core 649 preparation): HOSBinderDriverServer._registeredBinderObjects is a static
dictionary. SurfaceFlinger.CreateLayerFromId registers every layer's producer there (RegisterBinderObject); the
producer holds its BufferQueueCore, whose KEvents hold KAutoObject.KernelContext, whose Device is the whole Switch
(guest memory, kernel, services, GpuContext and its caches). Entries are removed only when the guest itself destroys a
layer (DestroyManagedLayer, DestroyStrayLayer). SurfaceFlinger.Dispose (called once, by Horizon.Dispose's termination
thread after the application process is terminated and before the HLE services are) only calls PrepareForExit on each
layer's queue, so the layers the game still owned at the close keep the closed session reachable from a static root for
the rest of the process.

Change:
- SurfaceFlinger.Dispose: after each remaining layer's PrepareForExit, UnregisterBinderObject(layer.ProducerBinderId).
  Nothing else changes: no lock is added (Dispose already walks _layers as before), _layers is not cleared, the
  composer flag and PrepareForExit are kept in their order. Binder ids only grow (_lastBinderId is never reused), a
  layer the guest destroyed is no longer in _layers, and Dictionary.Remove of an absent id is a no-op, so no other
  session's binder can be removed and a second unregister changes nothing. After Dispose the application is already
  terminated; a binder request still reaching vi for a removed id takes the existing "Invalid binder id" path, the same
  as a guest request on a destroyed layer today.
- HOSBinderDriverServer: an internal count of registered binders (under its lock) and a public read-only accessor
  (BinderRegistryDiagnostics.RegisteredBinderCount), since HOSBinderDriverServer is internal to Ryujinx.HLE.
- Library (journal only): when LoadApplication's owner releases a session (after its context and window are disposed
  and their fields cleared), weak references to its Switch and GpuContext are kept (at most 8 sessions); they never
  extend a lifetime. After the existing final collection at the end of Load, one durable Core journal line, stage
  "sessionRetention" (status "released", "retained" or "none", never "begin"), gives how many tracked closed sessions'
  Switch and GpuContext are still reachable, the binder registry count and the managed heap size.

Limits: other roots of a closed session (if any) are not removed here; the journal line shows whether the Switch is
still reachable after this correction. The 756 ms compacting collection in S2, the black artifacts and the screen
recording are not addressed. Not measured on an iPhone.
Fail closed on drift: each file must be the Core 649 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/SurfaceFlinger.cs': 'bb8e2a892da1ce7ef72e874b91d8dc83b38bdc33eb739698c7c7c4a17ffa15d2',
    'src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/HOSBinderDriverServer.cs': '837826419182425ed24d1ddbbb5f0e599b1ac95fd9680c49b5f294e9f1af4d3e',
    'src/Ryujinx.Library/Library.cs': 'f1586edba910524326c5cd0552e7d13f626b44f8ccf7a1e382e19daa084359ea',
}

# The end of Load as prepared (its blank line carries 12 spaces).
FINAL_COLLECTION = '            GC.WaitForPendingFinalizers();\n' + ' ' * 12 + '\n            GC.Collect();\n'


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    flinger = paths['src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/SurfaceFlinger.cs']
    once(flinger, '''            foreach (Layer layer in _layers.Values)
            {
                layer.Core.PrepareForExit();
            }''', '''            foreach (Layer layer in _layers.Values)
            {
                layer.Core.PrepareForExit();
                // RewindBox (adapt_binder_teardown): the static binder registry otherwise keeps this producer, and
                // through its queue's kernel events the whole closed Switch, reachable for the rest of the process.
                HOSBinderDriverServer.UnregisterBinderObject(layer.ProducerBinderId);
            }''')

    server = paths['src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/HOSBinderDriverServer.cs']
    once(server, '''        public static void UnregisterBinderObject(int binderId)''', '''        // RewindBox (adapt_binder_teardown): registered binder count, for the sessionRetention journal line.
        internal static int RegisteredBinderCount
        {
            get
            {
                lock (_lock)
                {
                    return _registeredBinderObjects.Count;
                }
            }
        }

        public static void UnregisterBinderObject(int binderId)''')
    once(server, '''            return binder.OnTransact(code, flags, inputParcel, outputParcel);
        }
    }
}''', '''            return binder.OnTransact(code, flags, inputParcel, outputParcel);
        }
    }

    // RewindBox (adapt_binder_teardown): read-only, for the host's sessionRetention journal line.
    public static class BinderRegistryDiagnostics
    {
        public static int RegisteredBinderCount => HOSBinderDriverServer.RegisteredBinderCount;
    }
}''')

    library = paths['src/Ryujinx.Library/Library.cs']
    once(library, FINAL_COLLECTION + '''        }
''', FINAL_COLLECTION + '''            // RewindBox (adapt_binder_teardown): journal only, after the final collection.
            RecordSessionRetention();
        }

        // RewindBox (adapt_binder_teardown): whether a closed session's Switch and GpuContext are still reachable after
        // the final collection of its teardown, and how many binder objects stay registered. Weak references only:
        // they never extend a session's lifetime. Journal only.
        private const int ReleasedSessionsTracked = 8;
        private static readonly List<(WeakReference Device, WeakReference Gpu)> _releasedSessions = new();
        private static readonly object _releasedSessionsLock = new();

        [MethodImpl(MethodImplOptions.NoInlining)]
        private static void NoteReleasedSession(Ryujinx.HLE.Switch context)
        {
            WeakReference device = new(context);
            WeakReference gpu = new(context.Gpu);

            lock (_releasedSessionsLock)
            {
                if (_releasedSessions.Count >= ReleasedSessionsTracked)
                {
                    _releasedSessions.RemoveAt(0);
                }

                _releasedSessions.Add((device, gpu));
            }
        }

        private static void RecordSessionRetention()
        {
            int tracked, devices = 0, gpus = 0;
            bool latestDevice = false, latestGpu = false;

            lock (_releasedSessionsLock)
            {
                tracked = _releasedSessions.Count;

                for (int i = 0; i < tracked; i++)
                {
                    bool device = _releasedSessions[i].Device.IsAlive;
                    bool gpu = _releasedSessions[i].Gpu.IsAlive;
                    devices += device ? 1 : 0;
                    gpus += gpu ? 1 : 0;

                    if (i == tracked - 1)
                    {
                        latestDevice = device;
                        latestGpu = gpu;
                    }
                }
            }

            string latest(bool alive) => tracked == 0 ? "none" : alive ? "yes" : "no";
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("sessionRetention",
                tracked == 0 ? "none" : latestDevice ? "retained" : "released", devices,
                $"after the final collection: closed sessions tracked {tracked}; Switch still reachable {devices}/{tracked} " +
                $"(latest {latest(latestDevice)}); GpuContext still reachable {gpus}/{tracked} (latest {latest(latestGpu)}); " +
                $"binder registry entries {Ryujinx.HLE.HOS.Services.SurfaceFlinger.BinderRegistryDiagnostics.RegisteredBinderCount}; " +
                $"managed heap {GC.GetTotalMemory(false) / (1024 * 1024)} MB");
        }
''')
    once(library, '''                _emulationContext = null;
                _window = null;
            }
        }''', '''                _emulationContext = null;
                _window = null;
                // RewindBox (adapt_binder_teardown): weak references only, for the sessionRetention journal line.
                if (context != null) NoteReleasedSession(context);
            }
        }''')
    return list(paths.values())
