# Load after S2Arm's Makefile. Only these standalone host binaries use the
# iOS shell adapter; the actual renderer, translator host and warm workers link normally.
rb_shader_test_dir := $(dir $(lastword $(MAKEFILE_LIST)))
rb_shader_shell_object := $(BUILD)/tests/rb_shader_host_shell.o
rb_shader_host_targets := $(LINK_RESTART_BINARY) $(NVN_SHADER_FLIGHT_BINARY) $(BUILD)/tests/t_nvn_warmbump $(BUILD)/tests/t_nvn_up_tex_src $(BUILD)/tests/t_nvn_pso_batch $(BUILD)/tests/t_rb_clear_batch_metal $(BUILD)/tests/t_nvn_scissored_ds $(BUILD)/tests/t_nvn_rscale $(BUILD)/tests/t_rb_scale_preflight $(BUILD)/tests/t_rb_drs_ownership $(BUILD)/tests/t_nvn_xqueue $(BUILD)/tests/t_nvn_ubd_index $(BUILD)/tests/t_rb_sparse_retire $(BUILD)/tests/t_nvn_alias_orphan
rb_shader_host_targets += $(BUILD)/tests/t_nvn_wait_event $(BUILD)/tests/t_nvn_visfold $(BUILD)/tests/t_nvn_gpu_halt

$(rb_shader_shell_object): $(rb_shader_test_dir)rb_shader_host_shell.c
	@mkdir -p $(dir $@)
	$(CC) -std=c11 -Wall -Wextra -Werror -c $< -o $@

$(rb_shader_host_targets): NVN_TEST_WEAK += $(rb_shader_shell_object)
$(rb_shader_host_targets): $(rb_shader_shell_object)

# RewindBox (patch 0469): reproducible NVN replay with hardware-independent backend metrics (t_rb_replay_metrics.m; records from the encode stream)
$(BUILD)/tests/t_nvn_rb_replay_metrics: NVN_TEST_WEAK += $(rb_shader_shell_object)
$(BUILD)/tests/t_nvn_rb_replay_metrics: $(rb_shader_test_dir)t_rb_replay_metrics.m $(rb_shader_shell_object) $(NVN_MTL_DEPS) graphics/nvn/gfx/nvn/nvn_protos.h $(NVN_TEST_HOST_OBJS) $(NVN_TEST_LIB) $(NVN_TEST_WIDEN)
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -fobjc-arc -Wno-unused-function -Wno-unguarded-availability-new -Wno-unguarded-availability \
	  $(NATIVE_INC) -Igraphics/nvn/host -Igraphics/nvn/gfx/nvn -Igraphics/nvn/gfx/nvn/include -Igraphics/nvn/third_party/vulkan-headers/include \
	  -o $@ $< $(NVN_TEST_HOST_OBJS) $(NVN_TEST_LIB) $(NVN_TEST_WIDEN) \
	  -Wl,-rpath,@executable_path/nvn/widen $(NVN_TEST_WEAK) \
	  -framework Metal -framework Foundation -framework QuartzCore -framework CoreGraphics \
	  -framework ImageIO -framework UniformTypeIdentifiers -lc++
