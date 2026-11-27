# Included after S2Arm's Makefile and RewindBox host-tests.mk.
rb_mesh_source := $(dir $(lastword $(MAKEFILE_LIST)))mesh_raster.m
$(BUILD)/tests/t_nvn_rb_mesh_raster: $(rb_mesh_source) $(rb_shader_shell_object) $(NVN_MTL_DEPS) graphics/nvn/tests/t_nvn_mesh.m $(NVN_TEST_HOST_OBJS) $(NVN_TEST_LIB) $(NVN_TEST_WIDEN)
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -std=gnu11 -fobjc-arc -Wno-unused-function -Wno-unguarded-availability-new -Wno-unguarded-availability \
	  $(NATIVE_INC) -Igraphics/nvn/tests -Igraphics/nvn/host -Igraphics/nvn/gfx/nvn -Igraphics/nvn/gfx/nvn/include -Igraphics/nvn/third_party/vulkan-headers/include \
	  -o $@ $< $(NVN_TEST_HOST_OBJS) $(NVN_TEST_LIB) $(NVN_TEST_WIDEN) \
	  -Wl,-rpath,@executable_path/nvn/widen $(NVN_TEST_WEAK) $(rb_shader_shell_object) \
	  -framework Metal -framework Foundation -framework QuartzCore -framework CoreGraphics \
	  -framework ImageIO -framework UniformTypeIdentifiers -lc++
