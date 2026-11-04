"""Write a durable mark at each phase of a MeloNX close, so a close that never ends shows where it stopped.

IPA 643, 4 November 2026: the maintainer reports that closing Super Smash Bros. Ultimate loads forever only while the
screen is being recorded, and closes normally otherwise; Hogwarts Legacy closed in 3 s during a recording (12:16:23
UTC). app.log shows "close begin" and nothing after it until the app was killed (13:22:07 and 13:23:03 UTC); a screen
recording continues across the app's relaunch, so both closes ran while recording. Core 647 corrects one cause of a
long close (adapt_teardown_compile_cancel: queued compiles no longer compiled on the way out) and journals the GPU
teardown in one line written only after the pipeline cache is saved, so a close stuck before that line is not located.

Two causes fit "SSBU, only while recording" and need different corrections:
- the recording's capture and encoding slow the remaining compile and the guest's own teardown (covered by Core 647
  when it is the compile queue);
- presentation: SSBU presents at 60 frames a second, so every swapchain image is in flight and each acquire waits on the
  presentation of an earlier image (MoltenVK signals image availability from the drawable's presented handler).
  MoltenVK documents that Metal may never complete the last one or two presentations and forces them only when the
  swapchain is destroyed (MVKSwapchain::forceUnpresentedImageCompletion); VulkanRenderer.Dispose waits for the device
  (vkDeviceWaitIdle) before it destroys the window's swapchain. A command buffer waiting on such an image would then
  hold the close in DeviceWaitIdle. Hogwarts, at 30 frames a second, keeps a free image.

Change, journal only (no order, wait, decision or resource change): durable Core journal lines (EmbeddedLaunchDiagnostics,
one O_APPEND write each, kept when the app is killed) at each phase of the close:
- WindowBase.Execute: "teardown guestStop" before the guest is terminated, "teardown guestStopped" with its duration
  after it, "teardown gpuRelease" when the render loop has drained and the GPU release starts, "teardown gpuReleased"
  with its duration when it returns;
- VulkanRenderer.Dispose: "gpuTeardown deviceIdleWait" with the compile counts and timings before vkDeviceWaitIdle,
  then the existing "gpuTeardown compiles" line after the cache save, and "gpuTeardown swapchainReleased" after the
  window's swapchain is destroyed.
The last mark of a close that never ends names its phase: the guest, the render-loop drain, the compiles, the device
wait (presentations) or the swapchain. Not measured on an iPhone.
Fail closed on drift: each file must be the Core 647 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Library/Window/WindowBase.cs': 'b49beb7f8cee379c590ae227098255873a000e5cfd33ea5164c5ae3497635489',
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': '7c1b77f9c296514c11601e4dea4a60a6fc185fea3566996d343212ec1ad92a82',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    window = paths['src/Ryujinx.Library/Window/WindowBase.cs']
    once(window, '''            try { _embeddedLifetime.Run(MainLoop, Render, () =>
            {
                Library.WithdrawEmbeddedControls();
                // Also covers renderer setup failing before shader-cache entry.
                Device.Gpu.CancelShaderCacheInitialization();
                _gpuCancellationTokenSource.Cancel();
                Device.System.Dispose();
            }, () =>
            {
                // Exactly one attempt. A failure quarantines the session;
                // never retry native GPU destruction on another thread.
                EmbeddedGpuReleased = true;
                try { Device.DisposeGpu(); }
                finally { FinalizeWindowRenderer(); }
            }); }''', '''            try { _embeddedLifetime.Run(MainLoop, Render, () =>
            {
                // RewindBox (adapt_teardown_phase_marks): durable marks, so a close that never ends shows its phase.
                long guestStopStart = Stopwatch.GetTimestamp();
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("teardown", "guestStop", detail: "terminating the guest; the render loop still serves it");
                Library.WithdrawEmbeddedControls();
                // Also covers renderer setup failing before shader-cache entry.
                Device.Gpu.CancelShaderCacheInitialization();
                _gpuCancellationTokenSource.Cancel();
                Device.System.Dispose();
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("teardown", "guestStopped", detail:
                    $"{(Stopwatch.GetTimestamp() - guestStopStart) * 1000 / Stopwatch.Frequency} ms; waiting for the render loop to drain");
            }, () =>
            {
                long gpuReleaseStart = Stopwatch.GetTimestamp();
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("teardown", "gpuRelease", detail: "render loop drained; releasing the GPU");
                // Exactly one attempt. A failure quarantines the session;
                // never retry native GPU destruction on another thread.
                EmbeddedGpuReleased = true;
                try
                {
                    Device.DisposeGpu();
                    Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("teardown", "gpuReleased", detail:
                        $"{(Stopwatch.GetTimestamp() - gpuReleaseStart) * 1000 / Stopwatch.Frequency} ms");
                }
                finally { FinalizeWindowRenderer(); }
            }); }''')

    renderer = paths['src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs']
    once(renderer, '''            long programsWaited = System.Diagnostics.Stopwatch.GetTimestamp();

            Api.DeviceWaitIdle(_device);''', '''            long programsWaited = System.Diagnostics.Stopwatch.GetTimestamp();

            // RewindBox (adapt_teardown_phase_marks): written before the device wait, which also waits for swapchain
            // presentations; a close that never ends after this line is held there.
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("gpuTeardown", "deviceIdleWait", detail:
                $"programs {shaders.Length}; cancelled shader modules {BackgroundCompilationScheduler.CancelledShaderCompiles}, " +
                $"pipelines {BackgroundCompilationScheduler.CancelledPipelineCompiles}; cancel and join " +
                $"{TeardownMs(teardownStart, compilesCancelled)} ms, program waits {TeardownMs(compilesCancelled, programsWaited)} ms");

            Api.DeviceWaitIdle(_device);''')
    once(renderer, '''            _window.Dispose();
            HelperShader.Dispose();''', '''            _window.Dispose();
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("gpuTeardown", "swapchainReleased");
            HelperShader.Dispose();''')
    return list(paths.values())
