"""Materialize pinned MeloNX RamDonor, with checked retirement and bounded IPC.
The allocator, XPC chunk transport and donor remain upstream implementations.
"""
import hashlib,json,shutil
from pathlib import Path

def generate(root, source):
    original=source/'src/MeloNX/MeloNX/Core/Memory'
    target=root/'packages/melonx_internal_bridge/ios/Memory'
    target.mkdir(parents=True,exist_ok=True)
    for name in ['MLXRamDonor.h','MLXRamDonor.m','MLXRamDonorProtocol.h']:
        shutil.copyfile(original/name,target/name)
    def replace(path,old,new):
        s=path.read_text();assert s.count(old)==1,(path,old[:80],s.count(old));path.write_text(s.replace(old,new))
    header=target/'MLXRamDonor.h'
    replace(header,'- (void)releaseRegionAt:(void *)base;','- (void)releaseRegionAt:(void *)base;\n- (BOOL)releaseRegionChecked:(void *)base;')
    replace(header, '@property (nonatomic) NSUInteger maxDonors;', '@property (nonatomic) NSUInteger maxDonors;\n@property (nonatomic, copy, nullable) BOOL (^shouldContinue)(void);')
    code=target/'MLXRamDonor.m'
    replace(code, '    while (offset < size)', '    while (offset < size && (!self.shouldContinue || self.shouldContinue()))')

    # Only one serialized host owner; a repeated request may never replace a live region.
    replace(code,'''    if (size == 0)
    {
        return NULL;
    }''','''    if (size == 0 || size > 4ull * 1024 * 1024 * 1024 || self.regions.count != 0)
    {
        self.lastError = @"Invalid request or an earlier region is still owned";
        return NULL;
    }''')
    # Keep even a timed-out request reachable so shutdown can stop late callbacks.
    replace(code,'''    [extension beginExtensionRequestWithInputItems:@[item] completion:''','''    @synchronized (self) { [self.extensions addObject:extension]; }
    [extension beginExtensionRequestWithInputItems:@[item] completion:''')
    replace(code,'''    @synchronized (self)
    {
        [self.extensions addObject:extension];
    }

    return YES;''','''    return YES;''')
    replace(code,'                            timeout:30.0];','                            timeout:3.0];')
    replace(code,'[self startOneDonorWithTimeout:10.0]','[self startOneDonorWithTimeout:3.0]')
    replace(code,'''    if (mapped < length || !scratch)
    {
        self.lastError''','''    if (mapped < length || !scratch)
    {
        if (scratch && mapped) mach_vm_deallocate(mach_task_self(), (mach_vm_address_t)scratch, mapped);
        self.lastError''')
    # Do not lose references if the OS refuses retirement; the Swift lease stays rooted.
    replace(code,'''- (void)tearDownRegion:(MLXDonatedRegion *)region
{
    [region.shmems removeAllObjects];

    if (region.base)
    {
        mach_vm_deallocate(mach_task_self(), region.base, region.size);
    }
}''','''- (BOOL)tearDownRegion:(MLXDonatedRegion *)region
{
    if (region.base && mach_vm_deallocate(mach_task_self(), region.base, region.size) != KERN_SUCCESS)
        return NO;
    region.base = 0;
    [region.shmems removeAllObjects];
    return YES;
}''')
    start='- (void)releaseRegionAt:(void *)base\n'
    end='#pragma mark Reporting and teardown'
    s=code.read_text();left=s.index(start);right=s.index(end,left)
    s=s[:left]+'''- (void)releaseRegionAt:(void *)base { (void)[self releaseRegionChecked:base]; }

- (BOOL)releaseRegionChecked:(void *)base
{
    @synchronized (self)
    {
        NSNumber *key = @((mach_vm_address_t)base);
        MLXDonatedRegion *region = self.regions[key];
        if (!region) return NO;
        if (![self tearDownRegion:region]) return NO;
        [self.regions removeObjectForKey:key];
        return YES;
    }
}

'''+s[right:];code.write_text(s)
    # Shutdown is allowed only after checked release. Never tear down a guest's
    # remaining mapping as an incidental effect of closing an extension.
    replace(code,'''        extensions = [self.extensions copy];
        regions = self.regions.allValues;

        [self.extensions removeAllObjects];''','''        if (self.regions.count != 0) return;
        extensions = [self.extensions copy];
        regions = self.regions.allValues;

        [self.extensions removeAllObjects];''')
    # Preserve ownership even when cleanup of an unoffered failed mapping fails.
    replace(code,'''        [self tearDownRegion:region];
        return NULL;''','''        if (![self tearDownRegion:region]) {
            @synchronized (self) { self.regions[@(region.base)] = region; }
        }
        return NULL;''')
    replace(header, '- (BOOL)releaseRegionChecked:(void *)base;', '- (BOOL)releaseRegionChecked:(void *)base;\n@property (nonatomic, readonly) BOOL hasOutstandingRegions;')
    replace(code, '#pragma mark Reporting and teardown', '- (BOOL)hasOutstandingRegions { @synchronized(self) { return self.regions.count != 0; } }\n\n#pragma mark Reporting and teardown')
    # Keep the full reservation when tail unmapping fails; the allocator receives
    # only the successful donated prefix, but checked retirement owns the tail too.
    replace(code, '        mach_vm_deallocate(mach_task_self(), base + offset, size - offset);\n        region.size = offset;', '        if (mach_vm_deallocate(mach_task_self(), base + offset, size - offset) == KERN_SUCCESS)\n            region.size = offset;')
    replace(code, '@property (nonatomic) NSMutableArray *shmems;', '@property (nonatomic) NSMutableArray *shmems;\n@property (nonatomic) NSMutableDictionary<NSNumber *, NSNumber *> *aliases;')
    replace(code, '    region.shmems = [NSMutableArray array];', '    region.shmems = [NSMutableArray array];\n    region.aliases = [NSMutableDictionary dictionary];')
    replace(code, '        if (scratch && mapped) mach_vm_deallocate(mach_task_self(), (mach_vm_address_t)scratch, mapped);', '        if (scratch && mapped && mach_vm_deallocate(mach_task_self(), (mach_vm_address_t)scratch, mapped) != KERN_SUCCESS)\n            region.aliases[@((mach_vm_address_t)scratch)] = @(mapped);')
    replace(code, '    mach_vm_deallocate(mach_task_self(), (mach_vm_address_t)scratch, mapped);', '    if (mach_vm_deallocate(mach_task_self(), (mach_vm_address_t)scratch, mapped) != KERN_SUCCESS)\n        region.aliases[@((mach_vm_address_t)scratch)] = @(mapped);')
    replace(code, '- (BOOL)tearDownRegion:(MLXDonatedRegion *)region\n{', '- (BOOL)tearDownRegion:(MLXDonatedRegion *)region\n{\n    for (NSNumber *address in region.aliases.allKeys) {\n        if (mach_vm_deallocate(mach_task_self(), address.unsignedLongLongValue, region.aliases[address].unsignedLongLongValue) != KERN_SUCCESS) return NO;\n        [region.aliases removeObjectForKey:address];\n    }')
    # A fresh endpoint per acquisition prevents a late previous helper connecting
    # to the next game's lease. Ignore callbacks from already-retired listeners.
    replace(code, '@property (nonatomic) NSUInteger nextDonor;', '@property (nonatomic) NSUInteger nextDonor;\n@property (nonatomic) NSUInteger listenerGeneration;')
    replace(code, '    _listener = xpc_connection_create(NULL, dispatch_get_global_queue(QOS_CLASS_UTILITY, 0));', '    [self resetListener];\n    return self;\n}\n\n- (void)resetListener\n{\n    if (_listener) xpc_connection_cancel(_listener);\n    const NSUInteger generation = ++self.listenerGeneration;\n    _listener = xpc_connection_create(NULL, dispatch_get_global_queue(QOS_CLASS_UTILITY, 0));')
    replace(code, '        [weakSelf acceptConnection:(xpc_connection_t)event];', '        MLXRamDonor *owner = weakSelf;\n        @synchronized(owner) {\n            if (!owner || owner.listenerGeneration != generation) { xpc_connection_cancel((xpc_connection_t)event); return; }\n            [owner acceptConnection:(xpc_connection_t)event];\n        }')
    replace(code, '    xpc_connection_resume(_listener);\n\n    return self;', '    xpc_connection_resume(_listener);')
    replace(code, '    NSMutableArray<MLXDonorSlot *> *slots = [NSMutableArray array];', '    @synchronized(self) { [self resetListener]; }\n    NSMutableArray<MLXDonorSlot *> *slots = [NSMutableArray array];')
    replace(code, '        if (self.regions.count != 0) return;', '        if (self.regions.count != 0) return;\n        ++self.listenerGeneration;\n        if (self.listener) { xpc_connection_cancel(self.listener); self.listener = nil; }')
    helper=target/'Helper';helper.mkdir(exist_ok=True)
    text=(source/'src/MeloNX/MeloNXRamDonor/main.m').read_text()
    text=text.replace('#import "../MeloNX/Core/Memory/MLXRamDonorProtocol.h"','#import "MLXRamDonorProtocol.h"')
    (helper/'MeloNXRamDonor.m').write_text(text)
    receipt=dict(upstream='13700519f3abc4e6d7ed8a065b118b2cc59bcd67',
        originals={name:hashlib.sha256((original/name).read_bytes()).hexdigest() for name in ['MLXRamDonor.h','MLXRamDonor.m','MLXRamDonorProtocol.h']},
        helperOriginal=hashlib.sha256((source/'src/MeloNX/MeloNXRamDonor/main.m').read_bytes()).hexdigest(),
        adapted={str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file() and p.name!='adaptation.json'})
    (target/'adaptation.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    import sys
    generate(Path(__file__).resolve().parents[2],Path(sys.argv[1]).resolve())
