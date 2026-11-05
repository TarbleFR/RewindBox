"""The GPU thread's disk-cache save poll no longer waits for the render thread.

Hogwarts Legacy on IPA 658 (pid 11152, private logs, not in the repository): 14 '{Nv}' syncpoint waits gave up after 1 s
and resumed the guest without its fence (03:13:01-03:20:00 UTC), every one inside a burst of first-time Metal compiles.
At each of them the GPU thread (GPU.MainThread, the only thread that increments syncpoint 1) was inside ProcessFrame
(FIFO 100 % or 96 %) but outside DispatchCalls in 10 of the 11 core-performance windows with a synchronous render call
in flight for 1 s or more: syncInvoke in flight up to 8164 ms, and up to 163 completed invokes / 10583 ms in one 5 s
window. The disk-cache writer thread ran only 3 times in the whole session, each time when one of the long waits ended.

Mechanism, in the Core 658 preparation:
- Ryujinx.HLE/Switch.cs ProcessFrame runs Gpu.ProcessShaderCacheQueue() before PreFrame and DispatchCalls on every GPU
  loop pass (Ryujinx.Library/Window/WindowBase.cs render loop, GPU thread).
- Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs ProcessShaderCacheQueue polls the head of the save queue with
  HostProgram.CheckProgramLink(false) until it is not Incomplete. A program enters that queue when it is created during
  play (EnqueueProgramToSave), which is exactly during a compile burst.
- With the threaded backend (BackendThreading.On, forced by the embedded session), HostProgram is a ThreadedProgram whose
  CheckProgramLink queues a ProgramCheckLinkCommand and InvokeCommand()s it: the GPU thread waits until the render thread
  has run every command queued before it (ThreadedRenderer.InvokeCommand, PD.Phase.SyncInvoke).
- A program compiled during play with asyncShaders=False reports Incomplete until its warm-up pipeline exists
  (Vulkan ShaderCollection.CheckProgramLink, !_compileTask.IsCompleted), and the render thread is meanwhile blocked in
  SetProgram (ProgramQueue.WaitForProgram) or in draw-time pipeline builds. So every GPU loop pass drains the whole
  render queue, the GPU thread can never run ahead of a render thread stuck on a compile, and syncpoint increments wait
  for every first-time pipeline build. For Vulkan the save needs nothing from the render thread: the SPIR-V is packed
  into BinaryCode when the program is queued (EnqueueProgramToSave), so GetBinary is not called.

Change:
- IProgram gains PeekLinkStatus(), a default member returning CheckProgramLink(false): Vulkan, OpenGL and a
  non-threaded renderer answer exactly as before.
- ThreadedProgram.PeekLinkStatus never waits and never touches the backend program from the calling thread. It returns
  the status the render thread last published for this program (Incomplete until then, so also while Base does not
  exist yet), read with Volatile. While that is Incomplete it queues, without waiting, one non-blocking
  ProgramCheckLinkCommand at a time (no result box); at most one is outstanding per program.
- ProgramCheckLinkCommand.Run, on the render thread, publishes the status it obtains (every caller: the queued request
  and the existing blocking and non-blocking invokes) and, for a queued request, allows the next one. It still ensures
  the program exists and still marks it Compiled, as before.
- ShaderCache.ProcessShaderCacheQueue uses PeekLinkStatus. A program not yet known to be linked is retried on a later
  pass; programs are still saved in order and only on Success, and Failure still drops a program unsaved.

Not changed: what is rendered, every draw, SetProgram's wait (adapt_shader_warmup), the pipeline builds and their lock,
the queued-syncpoint policy (adapt_queued_syncpoints), the startup cache loader (ParallelDiskCacheLoader keeps its own
CheckProgramLink polls), the backends' CheckProgramLink and the render thread's command order. Only when the GPU thread
learns that a new program can be written to the disk cache changes: a pass or a render-queue drain later than before.
This is not a quality or synchronisation trade-off, so it applies to every title; it does not unblock a guest whose
syncpoint waits for reports the stuck render thread has not submitted yet (the Hogwarts queued increments).
Not measured on an iPhone. On a device the gain reads as no syncInvoke in flight for 1 s or more outside gpuDispatch in
the core-performance lines of a compile burst, and fewer 1 s syncpoint timeouts if no report wait takes their place.
Fail closed on drift: each file must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.GAL/IProgram.cs': '1213108b8dfe8a766174e3821d2a8109284bde7ff2a746cc6b0f2b275a6ddba3',
    'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ThreadedProgram.cs': '300d40dd5b67ed36a7fcc6d2bbf9e1a8b74f34717ac9d4c0e537ab7eba1afaee',
    'src/Ryujinx.Graphics.GAL/Multithreading/Commands/Program/ProgramCheckLinkCommand.cs': '537127abb5949be9c10e51c2511dc215b922b37c30d184eaffab0adf6afff767',
    'src/Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs': '755a1308ff4047be4078c59560dabc4b712b54b52e2f08cde84169792ca1b7f5',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    once(paths['src/Ryujinx.Graphics.GAL/IProgram.cs'], '''        ProgramLinkStatus CheckProgramLink(bool blocking);
''', '''        ProgramLinkStatus CheckProgramLink(bool blocking);

        /// <summary>
        /// RewindBox (adapt_shader_save_poll): link status for a caller that must not wait, such as the GPU thread's
        /// disk-cache save poll. Incomplete means "not known yet, ask again later". Backends answer as a non-blocking
        /// link check; the threaded wrapper answers without waiting for the render thread.
        /// </summary>
        ProgramLinkStatus PeekLinkStatus() => CheckProgramLink(false);
''')

    program = paths['src/Ryujinx.Graphics.GAL/Multithreading/Resources/ThreadedProgram.cs']
    once(program, '''using Ryujinx.Graphics.GAL.Multithreading.Model;
''', '''using Ryujinx.Graphics.GAL.Multithreading.Model;
using System.Threading;
''')
    once(program, '''        internal bool Compiled;
''', '''        internal bool Compiled;

        // RewindBox (adapt_shader_save_poll): the link status the render thread last obtained for this program once it was
        // no longer Incomplete (written by the render thread, read by the GPU thread), and whether a non-blocking check
        // queued by PeekLinkStatus has not run yet (at most one per program).
        private int _publishedLinkStatus = (int)ProgramLinkStatus.Incomplete;
        private int _linkCheckQueued;
''')
    once(program, '''            _renderer.InvokeCommand();

            return box.Result;
        }
    }
}''', '''            _renderer.InvokeCommand();

            return box.Result;
        }

        // RewindBox (adapt_shader_save_poll): the GPU thread's save poll must not drain the render queue (InvokeCommand)
        // while the render thread is blocked on a first-time pipeline build: syncpoint increments wait behind it. Answer
        // from the published status and, while it is unknown, queue one non-blocking check without waiting for it.
        // Called on the producer (GPU) thread, like every other member here.
        public unsafe ProgramLinkStatus PeekLinkStatus()
        {
            ProgramLinkStatus status = (ProgramLinkStatus)Volatile.Read(ref _publishedLinkStatus);

            if (status == ProgramLinkStatus.Incomplete && Interlocked.Exchange(ref _linkCheckQueued, 1) == 0)
            {
                _renderer.New<ProgramCheckLinkCommand>()->Set(Ref(this), false, Ref<ResultBox<ProgramLinkStatus>>(null));
                _renderer.QueueCommand();
            }

            return status;
        }

        // RewindBox (adapt_shader_save_poll): render thread, from ProgramCheckLinkCommand. A final status is written before
        // the next queued check is allowed; until one is written, every poll finds a check outstanding or queues one, so
        // a linked program is always found (no lost save).
        internal void PublishLinkStatus(ProgramLinkStatus status, bool queuedCheck)
        {
            if (status != ProgramLinkStatus.Incomplete)
            {
                Volatile.Write(ref _publishedLinkStatus, (int)status);
            }

            if (queuedCheck)
            {
                Volatile.Write(ref _linkCheckQueued, 0);
            }
        }
    }
}''')

    once(paths['src/Ryujinx.Graphics.GAL/Multithreading/Commands/Program/ProgramCheckLinkCommand.cs'], '''            command._result.Get(threaded).Result = result;
''', '''            // RewindBox (adapt_shader_save_poll): publish the status for ThreadedProgram.PeekLinkStatus. A check that
            // PeekLinkStatus queued has no result box and nobody waits for it.
            ResultBox<ProgramLinkStatus> box = command._result.Get(threaded);

            program.PublishLinkStatus(result, box == null);

            if (box != null)
            {
                box.Result = result;
            }
''')

    once(paths['src/Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs'], '''                ProgramLinkStatus result = programToSave.HostProgram.CheckProgramLink(false);
''', '''                // RewindBox (adapt_shader_save_poll): a status query that never waits for the render thread; a program
                // not known to be linked yet stays at the head and is checked again on a later GPU loop pass.
                ProgramLinkStatus result = programToSave.HostProgram.PeekLinkStatus();
''')
    return list(paths.values())
