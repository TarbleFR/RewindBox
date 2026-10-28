"""Shorten what the render thread spends on a new shader program with asyncShaders off (the embedded default).

Hogwarts Legacy, builds 564-572 app.log: during new-shader bursts the render
thread used 60-93 % of a core while the GPU thread used 2-21 %; session 564
logged 119 "Background pipeline compile missed on draw" among about 381 new
programs. Two causes, both in upstream code:

- ProgramQueue.WaitForProgram (render thread): binding a program that cannot
  bind while incomplete polled CheckProgramLink(false) with
  SpinWait.SpinOnce(-1), which never sleeps, until the program's shader
  modules and pipeline warm-up were done: about 500,000 polls and a whole
  core per wait. It now blocks in the backend's CheckProgramLink(true) (a
  Task.Wait on the same tasks), then retires finished programs and starts
  queued ones as the last poll did. A faulted warm-up counts as complete, as
  it did for the poll; a backend that answers Incomplete to a blocking check
  falls back to the poll.
- PipelineConverter: the warm-up's pipeline key for a pass with a depth
  target and no color target set LogicOpsAllowed false, where the draw's
  framebuffer sets it true (FramebufferParams: no color, or a color that is
  neither float nor sRGB). Every first draw of a depth-only pass (shadow
  maps, depth prepasses) therefore missed the warm-up and created its
  pipeline again on the render thread under PipelineCreationLock. The
  warm-up now computes it as the framebuffer does. The flag only gates
  logic-op enable, so the created pipelines are the same.

No pipeline state, shader or draw changes. Not measured on an iPhone; no
FPS gain is claimed. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    queue = source / 'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ProgramQueue.cs'
    once(queue, '''            while (!program.Compiled)
            {
                ProcessQueue();

                if (!program.Compiled)
                {
                    spinWait[0].SpinOnce(-1);
                }
            }
        }
''', '''            while (!program.Compiled)
            {
                ProcessQueue();

                if (!program.Compiled)
                {
                    // Sleep until the backend has compiled the program, instead of keeping
                    // this thread on a core polling it for the whole compilation.
                    if (WaitForLink(program.Base))
                    {
                        program.Compiled = true;

                        // Retire finished programs and start queued ones, as the last poll did.
                        ProcessQueue();
                    }
                    else
                    {
                        spinWait[0].SpinOnce(-1);
                    }
                }
            }
        }

        private static bool WaitForLink(IProgram program)
        {
            try
            {
                return program.CheckProgramLink(true) != ProgramLinkStatus.Incomplete;
            }
            catch (AggregateException)
            {
                // A compile task faulted, so it has completed. The non-blocking check
                // reports such a program complete without throwing; keep that.
                return true;
            }
        }
''')

    converter = source / 'src/Ryujinx.Graphics.Vulkan/PipelineConverter.cs'
    once(converter, '''            pipeline.Internal.LogicOpsAllowed = attachmentCount == 0 || !allFormatsFloatOrSrgb;
''', '''            // As FramebufferParams: a pass without a color target (depth-only included) allows logic ops.
            pipeline.Internal.LogicOpsAllowed = maxColorAttachmentIndex < 0 || !allFormatsFloatOrSrgb;
''')
    return [queue, converter]
