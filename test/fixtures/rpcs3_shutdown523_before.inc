// SPDX-License-Identifier: GPL-2.0-only
// Exact Core 40f0337122e8bd83a22b10acfb515ee56638600d shutdown; negative control.
extern "C" rpcs3_ios_status rpcs3_ios_shutdown(void) noexcept
{
	std::unique_lock lock(g_api_mutex);
    // NEOSTATION_SAVE_EXCLUSIVE: asynchronous preparation still owns the game.
    if (neostation::savestate::current.read().active)
    {
        set_error("A savestate is in progress. Wait for creation and restoration to finish.");
        return RPCS3_IOS_INVALID_STATE;
    }
	restore_jobs().cancel();

	bool should_run = false;
	if (const auto result = g_lifecycle.begin_shutdown(should_run); result != RPCS3_IOS_OK)
	{
		set_error("RPCS3Core is busy");
		return result;
	}
	if (!should_run)
	{
		return RPCS3_IOS_OK;
	}
	g_accept_display_surfaces = false;
	g_accept_pad_state = false;
	rpcs3::ios::shared_pad_states().clear();
	rpcs3::ios::shared_pad_feedback().clear();
	try
	{
		if (g_emu_started)
		{
			Emu.DeactivateBigPictureMode();
			Emu.SetForceBoot(false);
			if (Emu.GetStatus(false) != system_state::stopped)
			{
				Emu.GracefulShutdown(false, false);
				if (!wait_for_emulation_stop())
				{
					set_error("RPCS3 did not finish stopping emulation during core shutdown");
					g_lifecycle.finish_shutdown(false);
					return RPCS3_IOS_STOP_FAILED;
				}
			}
			jit_runtime::finalize();
			g_emu_started = false;
		}
		g_rpcn_client.reset();
		g_cfg_rpcn.clear_runtime_credentials();
		g_display_surface.clear();
		emit_jit_arena_statistics("before core shutdown completion");
		logs::listener::sync_all();
		g_lifecycle.finish_shutdown(true);
		emit_log(4, "RPCS3Core shutdown completed");
		// A dequeued task may still be waiting for this mutex. Release it before
		// joining the owned worker; its generation/lifecycle check then cancels it.
		lock.unlock();
		restore_jobs().close();
		return RPCS3_IOS_OK;
	}
	catch (const std::exception& error)
	{
		set_error(error.what());
	}
	catch (...)
	{
		set_error("Unknown exception during RPCS3Core shutdown");
	}

	g_lifecycle.finish_shutdown(false);
	return RPCS3_IOS_INTERNAL_ERROR;
}
