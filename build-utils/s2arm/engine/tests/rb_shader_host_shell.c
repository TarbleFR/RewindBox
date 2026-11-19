// The standalone macOS renderer fixtures have no RewindBox iOS guest UI.
// Entering either shell path is a fixture failure.
#include <stdio.h>
#include <stdlib.h>

int s2a_rb_guest_log_open(const char *directory) {
    (void)directory;
    fputs("unexpected iOS guest configuration in macOS shader test\n", stderr);
    abort();
}

void s2a_rb_guest_input_release(void) {
    fputs("unexpected iOS controller release in macOS shader test\n", stderr);
    abort();
}
