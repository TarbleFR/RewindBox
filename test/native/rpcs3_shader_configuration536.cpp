#include "ios/IOSShaderTiming.h"
#include <cassert>
#include <thread>
int main() {
    using namespace rpcs3::ios::shader_timing;
    ConfigurationProfile p;
    int old_owner{},new_owner{};
    assert(!p.capture().live);
    p.begin(&old_owner,2,0,false);
    auto old=p.capture();assert(old.captured && old.live && old.configured==2 && old.applied==0 && !old.interpreter_supported);
    p.begin(&new_owner,1,1,true);p.end(&old_owner);
    auto current=p.capture();assert(current.live && current.generation==old.generation+1 && current.applied==1);
    std::atomic<bool> done=false;
    std::thread writer([&]{for(unsigned i=0;i<10000;++i)p.begin(&new_owner,i,i+1,i%2);done=true;});
    while(!done.load()) { const auto c=p.capture();if(c.captured && c.generation>current.generation)assert(c.applied==c.configured+1 && c.interpreter_supported==bool(c.configured%2)); }
    writer.join();p.end(&new_owner);assert(!p.capture().live);
}
