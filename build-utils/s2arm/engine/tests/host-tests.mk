# Load after S2Arm's Makefile. Only these standalone host binaries use the
# iOS shell adapter; the actual renderer, translator host and warm workers link normally.
rb_shader_test_dir := $(dir $(lastword $(MAKEFILE_LIST)))
rb_shader_shell_object := $(BUILD)/tests/rb_shader_host_shell.o
rb_shader_host_targets := $(NVN_SHADER_FLIGHT_BINARY) $(BUILD)/tests/t_nvn_warmbump $(BUILD)/tests/t_nvn_up_tex_src

$(rb_shader_shell_object): $(rb_shader_test_dir)rb_shader_host_shell.c
	@mkdir -p $(dir $@)
	$(CC) -std=c11 -Wall -Wextra -Werror -c $< -o $@

$(rb_shader_host_targets): NVN_TEST_WEAK += $(rb_shader_shell_object)
$(rb_shader_host_targets): $(rb_shader_shell_object)
