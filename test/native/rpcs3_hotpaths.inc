// Range storage/GPU adapters for the exact production texture selection body.
namespace rsx {
enum texture_upload_context : u32 { shader_read=1, blit_engine_dst=2, blit_engine_src=4, framebuffer_storage=8 };
template<bool> bool pitch_compatible(const auto* texture, u32 pitch, int) { return texture->pitch==pitch; }
}
enum { full_range=0 };
struct Range { bool inside(const Range&) const { return true; } };
using address_range32=Range;
struct Log { template<class... Args> void warning(Args&&...) {} };
inline Log rsx_log;
struct Texture {
    u32 id=0, context=rsx::shader_read, address=10, format=2, width=64, height=2, depth=1, pitch=256;
    bool dirty=false, locked=true, swizzled=false, valid_hash=true;
    u32 sync_calls=0;
    bool is_dirty() const { return dirty; }
    u32 get_context() const { return context; }
    bool matches(u32 a,u32 f,u32 w,u32 h,u32 d,u32) const { return address==a && format==f && width==w && height==h && depth==d; }
    bool sync_protection() { ++sync_calls; if (!valid_hash) {dirty=true;locked=false;return false;} return true; }
    bool is_swizzled() const { return swizzled; }
    void unprotect() { locked=false; }
    void set_dirty(bool value) { dirty=value; }
    u32 get_view(u32) const { return id; }
    u32 get_format_class() const { return 3; }
    u32 get_image_type() const { return 4; }
    u32 get_section_base() const { return address; }
    Range get_confirmed_range() const { return {}; }
};
struct Storage {
    std::vector<Texture> textures;
    u64 visits=0;
    struct Iterator {
        Storage* storage; usz index;
        void skip() { while(index<storage->textures.size() && !storage->textures[index].locked) ++index; }
        Texture& operator*() const { ++storage->visits; return storage->textures[index]; }
        Texture* operator->() const { return &operator*(); }
        void operator++(int) { ++index;skip(); }
        bool operator!=(const Iterator& other) const { return index!=other.index; }
    };
    Iterator range_begin(Range,int,bool) { Iterator i{this,0};i.skip();return i; }
    Iterator range_end() { return {this,textures.size()}; }
};
struct Attributes { u32 address=10,gcm_format=2,width=64,height=2,depth=1,pitch=256; bool swizzled=false; };
struct Options { u32 lookup_mask=7; };
struct Result {
    u32 view=0, context=0, format=0, scale=0, image=0, address=0;
    std::vector<u32> merge{};
    bool operator==(const Result&) const=default;
};
struct TextureAdapter {
    using section_storage_type=Texture;
    Storage m_storage;
    Attributes attr;
    Options options;
    Range memory_range;
    u32 remap=0,scale=1;
    explicit TextureAdapter(const std::vector<Texture>& textures) { m_storage.textures=textures; }
};
// VERSIONED_TEXTURE_CLASSES

struct PropsHash { usz operator()(const vk::pipeline_props& props) const { return rpcs3::hash_struct(props); } };
vk::pipeline_props pipeline_base() {
    vk::pipeline_props p{};
    p.renderpass_key=(u64{VK_FORMAT_D24_UNORM_S8_UINT}<<8)|(1u<<16);
    p.state.set_attachment_count(1);
    p.state.set_color_mask(0,true,true,true,true);
    p.state.enable_depth_test(VK_COMPARE_OP_LESS);
    p.state.set_depth_mask(true);
    p.state.enable_stencil_test(VK_STENCIL_OP_KEEP,VK_STENCIL_OP_INCREMENT_AND_WRAP,VK_STENCIL_OP_REPLACE,VK_COMPARE_OP_LESS,255,123);
    p.state.set_stencil_mask(255);
    return p;
}
bool compare(u32 a,u32 b,VkCompareOp op) {
    switch(op) {
    case VK_COMPARE_OP_NEVER:return false;
    case VK_COMPARE_OP_LESS:return a<b;
    case VK_COMPARE_OP_EQUAL:return a==b;
    case VK_COMPARE_OP_LESS_OR_EQUAL:return a<=b;
    case VK_COMPARE_OP_GREATER:return a>b;
    case VK_COMPARE_OP_NOT_EQUAL:return a!=b;
    case VK_COMPARE_OP_GREATER_OR_EQUAL:return a>=b;
    case VK_COMPARE_OP_ALWAYS:return true;
    default:std::abort();
    }
}
u32 stencil_op(u32 old,u32 ref,VkStencilOp op) {
    switch(op) {
    case VK_STENCIL_OP_KEEP:return old;
    case VK_STENCIL_OP_ZERO:return 0;
    case VK_STENCIL_OP_REPLACE:return ref;
    case VK_STENCIL_OP_INCREMENT_AND_CLAMP:return std::min(old+1,255u);
    case VK_STENCIL_OP_DECREMENT_AND_CLAMP:return old?old-1:0;
    case VK_STENCIL_OP_INVERT:return old^255;
    case VK_STENCIL_OP_INCREMENT_AND_WRAP:return (old+1)&255;
    case VK_STENCIL_OP_DECREMENT_AND_WRAP:return (old-1)&255;
    default:std::abort();
    }
}
u32 sample_stencil(const VkStencilOpState& compiled,const VkStencilOpState& commands,u32 stencil,bool depth_pass) {
    const bool pass=compare(commands.reference&commands.compareMask,stencil&commands.compareMask,compiled.compareOp);
    const auto op=!pass?compiled.failOp:(depth_pass?compiled.passOp:compiled.depthFailOp);
    const u32 value=stencil_op(stencil,commands.reference,op);
    return ((stencil&~commands.writeMask)|(value&commands.writeMask))&255;
}
std::pair<usz,usz> pipeline_test() {
    std::unordered_map<vk::pipeline_props,u32,PropsHash> old_cache,new_cache;
    for(u32 i=0;i<512;++i) {
        auto guest=pipeline_base();
        guest.state.rs.lineWidth=float(1+i);
        guest.state.rs.depthBiasConstantFactor=float(i);
        guest.state.rs.depthBiasClamp=-float(i);
        guest.state.rs.depthBiasSlopeFactor=float(i)*.25f;
        guest.state.ds.minDepthBounds=float(i)*.0001f;
        guest.state.ds.maxDepthBounds=1.f-float(i)*.0001f;
        for(auto* face : {&guest.state.ds.front,&guest.state.ds.back}) {
            face->compareMask=i;face->writeMask=i*3;face->reference=i*7;
        }
        for(auto& value:guest.state.cs.blendConstants) value=float(i)*.001f;
        auto b=guest,a=guest;
        before::validate_pipeline_properties(Shader{},Shader{},b);
        after::validate_pipeline_properties(Shader{},Shader{},a);
        old_cache.emplace(b,i);new_cache.emplace(a,i);
        assert(guest.state.ds.front.reference==i*7 && guest.state.rs.lineWidth==float(i+1));
        assert(a.state.ds.front.passOp==guest.state.ds.front.passOp);
    }
    assert(old_cache.size()==512 && new_cache.size()==1);
    // Every static change below must survive canonicalization.
    auto base=pipeline_base();after::validate_pipeline_properties(Shader{},Shader{},base);
    for(u32 i=0;i<10;++i) {
        auto different=pipeline_base();
        switch(i) {
        case 0:different.state.rs.cullMode=VK_CULL_MODE_BACK_BIT;break;
        case 1:different.state.rs.frontFace=VK_FRONT_FACE_CLOCKWISE;break;
        case 2:different.state.rs.depthBiasEnable=VK_TRUE;break;
        case 3:different.state.ds.depthCompareOp=VK_COMPARE_OP_GREATER;break;
        case 4:different.state.ds.front.passOp=VK_STENCIL_OP_INVERT;break;
        case 5:different.state.ds.back.compareOp=VK_COMPARE_OP_ALWAYS;break;
        case 6:different.state.att_state[0].colorWriteMask=0;break;
        case 7:different.state.ds.depthWriteEnable=VK_FALSE;break;
        case 8:different.state.ia.topology=VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP;break;
        case 9:different.state.ms.alphaToCoverageEnable=VK_TRUE;break;
        }
        after::validate_pipeline_properties(Shader{},Shader{},different);
        assert(!(different==base));
    }
    // An independent stencil equation consumes dynamic masks/reference from
    // commands and the static operations from each compiled pipeline.
    std::mt19937 rng(593);
    for(u32 i=0;i<100000;++i) {
        auto guest=pipeline_base();
        for(auto* face : {&guest.state.ds.front,&guest.state.ds.back}) {
            face->failOp=VkStencilOp(rng()%8);face->passOp=VkStencilOp(rng()%8);
            face->depthFailOp=VkStencilOp(rng()%8);face->compareOp=VkCompareOp(rng()%8);
            face->compareMask=rng()&255;face->writeMask=rng()&255;face->reference=rng()&255;
        }
        auto compiled=guest;after::validate_pipeline_properties(Shader{},Shader{},compiled);
        const u32 stencil=rng()&255;const bool depth=rng()&1;
        assert(sample_stencil(guest.state.ds.front,guest.state.ds.front,stencil,depth)==sample_stencil(compiled.state.ds.front,guest.state.ds.front,stencil,depth));
        assert(sample_stencil(guest.state.ds.back,guest.state.ds.back,stencil,depth)==sample_stencil(compiled.state.ds.back,guest.state.ds.back,stencil,depth));
    }
    return {old_cache.size(),new_cache.size()};
}
void equal_texture_case(const std::vector<Texture>& textures,Attributes attr,Options options) {
    before_texture b(textures);after_texture a(textures);b.attr=a.attr=attr;b.options=a.options=options;
    const auto rb=b.query(),ra=a.query();assert(rb==ra);
    assert(a.m_storage.visits<=b.m_storage.visits);
    for(usz i=0;i<textures.size();++i) {
        const auto& bt=b.m_storage.textures[i];const auto& at=a.m_storage.textures[i];
        assert(bt.dirty==at.dirty && bt.locked==at.locked && bt.sync_calls==at.sync_calls);
    }
}
void texture_test() {
    std::mt19937 rng(20261029);
    for(u32 n=0;n<12000;++n) {
        std::vector<Texture> textures(rng()%129);
        for(u32 i=0;i<textures.size();++i) {
            auto& t=textures[i];t.id=i+1;
            t.context=1u<<(rng()%4);t.dirty=(rng()%8)==0;t.locked=(rng()%8)!=0;
            t.address=10+(rng()%3);t.format=2+(rng()%2);t.width=64+(rng()%2);
            t.pitch=256+(rng()%2);t.swizzled=rng()&1;t.valid_hash=(rng()%4)!=0;
        }
        Attributes attr{};attr.height=(rng()%8)?2:1;attr.swizzled=rng()&1;
        equal_texture_case(textures,attr,Options{static_cast<u32>(rng()%16)});
    }
    // First exact entry with the wrong swizzle must prevent a later exact
    // entry from winning, while preserving all later blit merge candidates.
    std::vector<Texture> special(40);
    for(u32 i=0;i<special.size();++i) {special[i].id=i+1;special[i].context=rsx::blit_engine_dst;}
    special[0].swizzled=true;equal_texture_case(special,{},{});
    special[0].valid_hash=false;equal_texture_case(special,{},{});
    for(auto& t:special) {t.width=65;t.valid_hash=true;}equal_texture_case(special,{},{});
}
// RECENT_PIPELINE_TESTS
int main(int argc,char**) {
    const auto [bp,ap]=pipeline_test();texture_test();
    recent_pipeline_test();
    std::vector<Texture> same(128);
    for(u32 i=0;i<same.size();++i) same[i].id=i+1;
    before_texture b(same);after_texture a(same);
    allocations=0;const auto rb=b.query();const u64 ba=allocations;
    allocations=0;const auto ra=a.query();const u64 aa=allocations;
    assert(rb==ra && b.m_storage.visits==128 && a.m_storage.visits==1 && ba>0 && aa==0);
    std::cout<<"{\"dynamicVariants\":512,\"beforePipelineKeys\":"<<bp<<",\"afterPipelineKeys\":"<<ap
             <<",\"staticDifferencesPreserved\":10,\"stencilCases\":200000,\"textureCases\":12003"
             <<",\"recentPipelineHashBypasses\":10000,\"concurrentLookups\":80000,\"clearRehashAndPendingCasesPassed\":true"
             <<",\"firstHit128Overlaps\":{\"beforeVisits\":"<<b.m_storage.visits<<",\"afterVisits\":"<<a.m_storage.visits
             <<",\"beforeAllocations\":"<<ba<<",\"afterAllocations\":"<<aa<<"}";
    if(argc>1) {
        auto bench=[](auto& cache) {
            const auto begin=std::chrono::steady_clock::now();u64 sum=0;
            for(unsigned i=0;i<30000;++i) sum+=cache.query().view;
            assert(sum==30000);
            return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
        };
        std::array<double,7> old_ms{},new_ms{};
        for(usz i=0;i<old_ms.size();++i) {
            if(i&1) {new_ms[i]=bench(a);old_ms[i]=bench(b);}
            else {old_ms[i]=bench(b);new_ms[i]=bench(a);}
        }
        std::sort(old_ms.begin(),old_ms.end());std::sort(new_ms.begin(),new_ms.end());
        std::cout<<",\"syntheticLookup30000MedianMs\":{\"before\":"<<old_ms[3]<<",\"after\":"<<new_ms[3]<<"}";
    }
    std::cout<<"}\n";
}
