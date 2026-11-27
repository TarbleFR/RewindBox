// Reuse the upstream NVN harness, its real draw path and its 8 x 4 RGB readback.
#define main upstream_mesh_harness_main
#include "t_nvn_mesh.m"
#undef main

static int verify_rgba(int mask) {
    id<MTLBuffer> bytes = [g_dev newBufferWithLength:128 options:MTLResourceStorageModeShared];
    REQUIRE(bytes);
    id<MTLCommandBuffer> cb = q_cb();
    id<MTLBlitCommandEncoder> blit = [cb blitCommandEncoder];
    [blit copyFromTexture:tex_mtl(&g_rt) sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0)
               sourceSize:MTLSizeMake(8,4,1) toBuffer:bytes destinationOffset:0
   destinationBytesPerRow:32 destinationBytesPerImage:128];
    [blit endEncoding];
    [cb commit];
    [cb waitUntilCompleted];
    REQUIRE(cb.status == MTLCommandBufferStatusCompleted);
    const uint8_t *rgba = bytes.contents;
    for (unsigned y = 0; y < 4; y++)
        for (unsigned x = 0; x < 8; x++) {
            uint8_t value = mask & (1u << x) ? 255 : 0;
            const uint8_t expected[4] = {value, value, value, 255};
            if (memcmp(expected, rgba + 4 * (y * 8 + x), 4)) return 0;
        }
    return 1;
}

int main(int argc, const char **argv) {
    if (argc != 2) return 2;
    @autoreleasepool {
        setenv("DM_PRESENT_LINK", "0", 1);
        char user_pso[] = "/tmp/rb_mesh_pso_XXXXXX";
        int fd = mkstemp(user_pso);
        REQUIRE(fd >= 0);
        close(fd);
        setenv("DM_PSO_USER", user_pso, 1);
        if (![MTLCreateSystemDefaultDevice() supportsFamily:MTLGPUFamilyMetal3]) {
            fprintf(stderr, "No Metal mesh shader device\n");
            unlink(user_pso);
            return 77;
        }
        mtl_init();
        if (!g_mesh_ok) {
            fprintf(stderr, "GPU lacks Metal mesh shader support\n");
            unlink(user_pso);
            return 77;
        }
        NSString *dir = @(argv[1]);
        g_msl_dir = dir;
        nvn_be_set_depth_zero(1);
        put_json(dir, @"1111111111111111_b", @{@"stage": @"ts", @"msl_entry_kind": @"object", @"mesh_threads": @32, @"mesh_payload": @12});
        put_json(dir, @"2222222222222222_b", @{@"stage": @"ms", @"msl_entry_kind": @"mesh", @"entry_z": @"main0_z", @"mesh_threads": @32, @"mesh_payload": @12, @"mesh_task": @1, @"max_vertices": @4, @"max_primitives": @2});
        put_json(dir, @"3333333333333333_b", @{@"stage": @"ms", @"msl_entry_kind": @"mesh", @"entry_z": @"main0_z", @"mesh_threads": @32, @"max_vertices": @4, @"max_primitives": @2});
        NvShader *ts = shader_get(@"1111111111111111_b", 3);
        NvShader *mt = shader_get(@"2222222222222222_b", 4);
        NvShader *ms = shader_get(@"3333333333333333_b", 4);
        REQUIRE(ts && mt && ms);
        NSError *error = nil;
        NSString *fragment = @"#include <metal_stdlib>\nusing namespace metal;\nfragment float4 main0() { return float4(1); }";
        id<MTLLibrary> library = [g_dev newLibraryWithSource:fragment options:nil error:&error];
        REQUIRE(library);
        NvShader *fs = [NvShader new];
        fs->stage = 1;
        strlcpy(fs->key, "ffffffffffffffff_b", sizeof fs->key);
        fs->ventry = @"main0";
        fs->fn = [library newFunctionWithName:@"main0"];
        REQUIRE(fs->fn);
        NvProg *direct = [NvProg new], *with_task = [NvProg new];
        direct->sh[1] = with_task->sh[1] = fs;
        direct->sh[4] = ms;
        with_task->sh[3] = ts;
        with_task->sh[4] = mt;
        static prog_t gp[2];
        for (int i = 0; i < 2; i++) {
            gp[i].magic = MAGIC('P','R','O','G');
            gp[i].serial = nvn_new_serial();
            serial_put(gp[i].serial, i ? with_task : direct);
        }
        rt_make();
        for (int rep = 0; rep < 6; rep++) {
            for (int task = 0; task <= 1; task++) {
                frame_begin();
                S.prog = &gp[task];
                const p_draw draw = {.prim = DM_PRIM_MESH_TASKS, .first = task ? 1 : 2, .count = task ? 2 : 3, .instances = 1};
                int waited = 0;
                mesh_draw(&draw, &waited);
                const int mask = frame_columns();
                printf("repeat=%d task=%d mask=%#x\n", rep, task, mask);
                REQUIRE(mask == (task ? 0x3c : 0x1c));
                REQUIRE(verify_rgba(task ? 0x3c : 0x1c));
            }
        }
        unlink(user_pso);
    }
    return 0;
}
