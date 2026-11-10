// Test double of MoltenVK's configuration entry points (vkGet/SetMoltenVKConfigurationMVK) for the Core 667 probe:
// the configuration is a byte buffer filled with a known pattern, copied out and back exactly as MoltenVK copies its
// MVKConfiguration (the size is the caller's struct size). No Vulkan, no Metal.
#include <stddef.h>
#include <string.h>

static unsigned char g_config[4096];

void stub_reset(void) {
    for (int i = 0; i < (int)sizeof g_config; i++) g_config[i] = (unsigned char)(i * 7 + 3);
}

void stub_read(unsigned char *output, size_t size) {
    memcpy(output, g_config, size);
}

int vkGetMoltenVKConfigurationMVK(void *instance, void *configuration, size_t *size) {
    (void)instance;
    if (*size > sizeof g_config) return -1;
    memcpy(configuration, g_config, *size);
    return 0;
}

int vkSetMoltenVKConfigurationMVK(void *instance, const void *configuration, size_t *size) {
    (void)instance;
    if (*size > sizeof g_config) return -1;
    memcpy(g_config, configuration, *size);
    return 0;
}
