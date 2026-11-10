#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <limits>
#include <mutex>
#include <vector>
using u32=std::uint32_t; using u64=std::uint64_t;
constexpr u64 umax=std::numeric_limits<u64>::max();
struct { struct { u32 clocks_scale{100}; } core; } g_cfg;
using shared_mutex=std::mutex;
struct entry
	{
		u64 due;
		u32 id;
		u64 token;
	};
[[gnu::noinline]] u64 baseline(std::vector<entry>& armed, std::vector<entry>& due_entries, u64 now) {
shared_mutex mutex; u64 sleep_us=umax;

			{
				std::lock_guard lock(mutex);
				const auto pending_end = std::remove_if(armed.begin(), armed.end(), [&](const entry& pending)
				{
					if (pending.due <= now)
					{
						if (due_entries.empty())
						{
							// Allocate before compacting the queue. Entry copies and
							// moves cannot throw, so no allocation can interrupt it.
							due_entries.reserve(armed.size());
						}
						due_entries.push_back(pending);
						return true;
					}
					// The guest timebase runs at 80 MHz times clocks_scale / 100.
					const u64 us = (pending.due - now) * 100 / (80 * std::max<u64>(g_cfg.core.clocks_scale, 1)) + 1;
					sleep_us = std::min(sleep_us, us);
					return false;
				});
				// Preserve notification and pending-entry order while moving each
				// survivor at most once, rather than shifting it after every expiry.
				armed.erase(pending_end, armed.end());
			}
return sleep_us;
}
[[gnu::noinline]] u64 candidate(std::vector<entry>& armed, std::vector<entry>& due_entries, u64 now) {
shared_mutex mutex; u64 sleep_us=umax;

			{
				std::lock_guard lock(mutex);
				u64 sleep_scaled_ticks = umax;
				const auto pending_end = std::remove_if(armed.begin(), armed.end(), [&](const entry& pending)
				{
					if (pending.due <= now)
					{
						if (due_entries.empty())
						{
							// Allocate before compacting the queue. Entry copies and
							// moves cannot throw, so no allocation can interrupt it.
							due_entries.reserve(armed.size());
						}
						due_entries.push_back(pending);
						return true;
					}
					// Keep the original unsigned multiplication before taking the
					// minimum, including its wraparound for distant deadlines.
					sleep_scaled_ticks = std::min(sleep_scaled_ticks, (pending.due - now) * 100);
					return false;
				});
				// Preserve notification and pending-entry order while moving each
				// survivor at most once, rather than shifting it after every expiry.
				armed.erase(pending_end, armed.end());
				if (!armed.empty())
				{
					// The monotone conversion needs one division per sweep, rather
					// than one per pending entry. No allocation when nothing expires.
					sleep_us = sleep_scaled_ticks / (80 * std::max<u64>(g_cfg.core.clocks_scale, 1)) + 1;
				}
			}
return sleep_us;
}

using Sweep=u64(*)(std::vector<entry>&,std::vector<entry>&,u64);
u64 sink{};
double measure(Sweep f,const std::vector<entry>& input,u32 iterations) {
    std::vector<entry> armed; armed.reserve(input.size());
    const auto start=std::chrono::steady_clock::now();
    for(u32 i=0;i<iterations;++i) {
        armed=input; std::vector<entry> due;
        sink+=f(armed,due,1000)+armed.size()+due.size();
    }
    return std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/iterations;
}
int main() {
    std::cout<<"{\"samples\":7,\"cases\":["; bool first=true;
    for(u32 count:{6u,32u,128u,1024u}) for(u32 pattern=0;pattern<3;++pattern) {
        std::vector<entry> input;
        for(u32 i=0;i<count;++i) input.push_back({pattern==0 || (pattern==1 && i%2==0)?1000u:2000u,i,u64{i}+1});
        const u32 iterations=std::max(64u,100000u/(count+1));
        std::array<double,7> old{},fresh{};
        for(u32 i=0;i<7;++i) {
            if(i%2) { fresh[i]=measure(candidate,input,iterations); old[i]=measure(baseline,input,iterations); }
            else { old[i]=measure(baseline,input,iterations); fresh[i]=measure(candidate,input,iterations); }
        }
        if(!first) std::cout<<',';
        first=false;
        std::cout<<"{\"entries\":"<<count<<",\"pattern\":\""<<(pattern==0?"all_due":pattern==1?"alternating":"none_due")
            <<"\",\"iterationsPerSample\":"<<iterations<<",\"baselineNs\":[";
        for(u32 i=0;i<7;++i) { if(i) std::cout<<','; std::cout<<old[i]; }
        std::cout<<"],\"candidateNs\":[";
        for(u32 i=0;i<7;++i) { if(i) std::cout<<','; std::cout<<fresh[i]; }
        std::sort(old.begin(),old.end()); std::sort(fresh.begin(),fresh.end());
        std::cout<<"],\"baselineMedianNs\":"<<old[3]<<",\"candidateMedianNs\":"<<fresh[3]<<'}';
    }
    std::cout<<"],\"sink\":"<<sink<<"}\n";
}
