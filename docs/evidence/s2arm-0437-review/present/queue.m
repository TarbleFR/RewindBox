#include <assert.h>
#include <stdio.h>
#include <objc/Object.h>
#include <objc/runtime.h>

@protocol MTL4CommandQueue
- (void)addResidencySet:(id)set;
- (void)removeResidencySet:(id)set;
@end
@interface TestQueue: Object <MTL4CommandQueue> {
@public int pending, wrong;
}
@end
@implementation TestQueue
- (void)addResidencySet:(id)set { assert(set); ++pending; }
- (void)removeResidencySet:(id)set { assert(set); if (pending) --pending; else ++wrong; }
@end
@interface Layer: Object
@property (readonly) id residencySet;
@end
@implementation Layer
- (id)residencySet { return self; }
@end
static id<MTL4CommandQueue> g_q4, g_rb_present_q;
static Layer *g_present_layer_resident;
static int g_m3;
SELECT_QUEUE
int main(void) {
    TestQueue *graphics = class_createInstance(objc_getClass("TestQueue"), 0);
    TestQueue *dedicated = class_createInstance(objc_getClass("TestQueue"), 0);
    Layer *layer = class_createInstance(objc_getClass("Layer"), 0);
    g_q4 = graphics;
    for (int session = 0; session < 300; session++) {
        g_m3 = session % 3 == 2;
        g_rb_present_q = session % 3 == 1 ? dedicated : nil;
        for (int frame = 0; frame < 16; frame++) {
            ATTACH_LAYER
        }
        DETACH_LAYER
        g_present_layer_resident = nil;
    }
    int mismatch = dedicated->pending + graphics->pending + graphics->wrong + dedicated->wrong;
    printf("sessions=300 attachments_left=%d wrong_queue_removals=%d\n",
        dedicated->pending + graphics->pending, graphics->wrong + dedicated->wrong);
    object_dispose(layer); object_dispose(graphics); object_dispose(dedicated);
    return mismatch != 0;
}
