// SPDX-License-Identifier: GPL-2.0-or-later

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <zlib.h>

// The object writer produces one gzip member. Decode into the final owner's
// buffer, with bounded compressed/decompressed sizes and mandatory CRC/ISIZE.
// ReadAt reads bytes from the same open file, never a second path lookup.
namespace baseline
{
inline constexpr std::size_t maximum_object_bytes = 256 * 1024 * 1024;
inline constexpr std::size_t input_chunk_bytes = 64 * 1024;

template <class ReadAt>
std::size_t gzip_size(std::uint64_t file_size, ReadAt read)
{
    if (file_size < 18 || file_size > maximum_object_bytes) return 0;
    std::array<unsigned char, 4> footer{};
    if (read(file_size - 4, footer.data(), footer.size()) != footer.size()) return 0;
    const auto size = std::uint32_t(footer[0]) | (std::uint32_t(footer[1]) << 8) |
        (std::uint32_t(footer[2]) << 16) | (std::uint32_t(footer[3]) << 24);
    return size && size <= maximum_object_bytes ? size : 0;
}

template <class ReadAt>
bool inflate(std::uint64_t file_size, ReadAt read, void* output, std::size_t output_size)
{
    if (!output || !output_size || output_size > maximum_object_bytes ||
        file_size < 18 || file_size > maximum_object_bytes) return false;
    z_stream stream{};
    if (inflateInit2(&stream, 15 + 16) != Z_OK) return false;
    struct cleanup { z_stream& stream; ~cleanup() { inflateEnd(&stream); } } guard{stream};
    std::array<unsigned char, input_chunk_bytes> input;
    unsigned char overflow = 0;
    stream.next_out = static_cast<unsigned char*>(output);
    stream.avail_out = static_cast<uInt>(output_size);
    std::uint64_t offset = 0;
    for (;;)
    {
        if (!stream.avail_in && offset < file_size)
        {
            const auto requested = static_cast<std::size_t>(std::min<std::uint64_t>(input.size(), file_size - offset));
            const auto got = read(offset, input.data(), requested);
            if (!got || got > requested) return false;
            offset += got;
            stream.next_in = input.data();
            stream.avail_in = static_cast<uInt>(got);
        }
        if (!stream.avail_out)
        {
            // Permit zlib to consume a trailer after filling the exact output.
            stream.next_out = &overflow;
            stream.avail_out = 1;
        }
        const auto before_in = stream.total_in;
        const auto before_out = stream.total_out;
        const int status = ::inflate(&stream, Z_NO_FLUSH);
        if (stream.total_out > output_size) return false;
        if (status == Z_STREAM_END)
            return stream.total_out == output_size && stream.total_in == file_size;
        if (status != Z_OK || (stream.total_in == before_in && stream.total_out == before_out)) return false;
    }
}
}

// SPDX-License-Identifier: GPL-2.0-or-later

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <zlib.h>

// The object writer produces one gzip member. Decode into the final owner's
// buffer, with bounded compressed/decompressed sizes and mandatory CRC/ISIZE.
// ReadAt reads bytes from the same open file, never a second path lookup.
namespace candidate
{
inline constexpr std::size_t maximum_object_bytes = 256 * 1024 * 1024;
inline constexpr std::size_t input_chunk_bytes = 64 * 1024;

#ifdef RPCS3_IOS
namespace detail
{
struct inflater_state
{
    z_stream stream{};
    bool initialized = false;
    bool busy = false;

    ~inflater_state()
    {
        if (initialized) ::inflateEnd(&stream);
    }

    bool prepare()
    {
        if (initialized && ::inflateReset2(&stream, 15 + 16) != Z_OK)
        {
            ::inflateEnd(&stream);
            stream = {};
            initialized = false;
        }
        if (!initialized)
        {
            initialized = inflateInit2(&stream, 15 + 16) == Z_OK;
            if (!initialized) return false;
        }
        stream.next_in = nullptr;
        stream.avail_in = 0;
        stream.next_out = nullptr;
        stream.avail_out = 0;
        return true;
    }
};

struct inflater_lease
{
    inflater_state fallback;
    inflater_state* state;

    inflater_lease()
    {
        static thread_local inflater_state shared;
        state = shared.busy ? &fallback : &shared;
        state->busy = true;
    }
    inflater_lease(const inflater_lease&) = delete;
    inflater_lease& operator=(const inflater_lease&) = delete;
    ~inflater_lease()
    {
        state->stream.next_in = nullptr;
        state->stream.avail_in = 0;
        state->stream.next_out = nullptr;
        state->stream.avail_out = 0;
        state->busy = false;
    }
};
}
#endif

template <class ReadAt>
std::size_t gzip_size(std::uint64_t file_size, ReadAt read)
{
    if (file_size < 18 || file_size > maximum_object_bytes) return 0;
    std::array<unsigned char, 4> footer{};
    if (read(file_size - 4, footer.data(), footer.size()) != footer.size()) return 0;
    const auto size = std::uint32_t(footer[0]) | (std::uint32_t(footer[1]) << 8) |
        (std::uint32_t(footer[2]) << 16) | (std::uint32_t(footer[3]) << 24);
    return size && size <= maximum_object_bytes ? size : 0;
}

template <class ReadAt>
bool inflate(std::uint64_t file_size, ReadAt read, void* output, std::size_t output_size)
{
    if (!output || !output_size || output_size > maximum_object_bytes ||
        file_size < 18 || file_size > maximum_object_bytes) return false;
#ifdef RPCS3_IOS
    detail::inflater_lease lease;
    if (!lease.state->prepare()) return false;
    z_stream& stream = lease.state->stream;
#else
    z_stream stream{};
    if (inflateInit2(&stream, 15 + 16) != Z_OK) return false;
    struct cleanup { z_stream& stream; ~cleanup() { inflateEnd(&stream); } } guard{stream};
#endif
    std::array<unsigned char, input_chunk_bytes> input;
    unsigned char overflow = 0;
    stream.next_out = static_cast<unsigned char*>(output);
    stream.avail_out = static_cast<uInt>(output_size);
    std::uint64_t offset = 0;
    for (;;)
    {
        if (!stream.avail_in && offset < file_size)
        {
            const auto requested = static_cast<std::size_t>(std::min<std::uint64_t>(input.size(), file_size - offset));
            const auto got = read(offset, input.data(), requested);
            if (!got || got > requested) return false;
            offset += got;
            stream.next_in = input.data();
            stream.avail_in = static_cast<uInt>(got);
        }
        if (!stream.avail_out)
        {
            // Permit zlib to consume a trailer after filling the exact output.
            stream.next_out = &overflow;
            stream.avail_out = 1;
        }
        const auto before_in = stream.total_in;
        const auto before_out = stream.total_out;
        const int status = ::inflate(&stream, Z_NO_FLUSH);
        if (stream.total_out > output_size) return false;
        if (status == Z_STREAM_END)
            return stream.total_out == output_size && stream.total_in == file_size;
        if (status != Z_OK || (stream.total_in == before_in && stream.total_out == before_out)) return false;
    }
}
}


#include <chrono>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <fstream>
#include <iterator>
#include <cassert>
using bytes=std::vector<unsigned char>;
bytes gzip(const bytes& input){z_stream s{};assert(deflateInit2(&s,1,Z_DEFLATED,31,8,Z_DEFAULT_STRATEGY)==Z_OK);bytes out(deflateBound(&s,input.size()));s.next_in=const_cast<Bytef*>(input.data());s.avail_in=input.size();s.next_out=out.data();s.avail_out=out.size();assert(deflate(&s,Z_FINISH)==Z_STREAM_END);out.resize(s.total_out);assert(deflateEnd(&s)==Z_OK);return out;}
struct reader{const bytes& data;std::size_t operator()(std::uint64_t offset,void* out,std::size_t count)const{if(offset>data.size()||count>data.size()-offset)return 0;std::memcpy(out,data.data()+offset,count);return count;}};
using inflate_fn=bool(*)(std::uint64_t, reader, void*,std::size_t);
volatile std::size_t sink=0;
double time(inflate_fn fn,const bytes& zipped,bytes& output,int n){auto t=std::chrono::steady_clock::now();for(int i=0;i<n;i++){if(!fn(zipped.size(),reader{zipped},output.data(),output.size()))std::abort();}sink=output[output.size()/2];return std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-t).count()/n;}
int main(){std::ifstream f("/usr/bin/bash",std::ios::binary);bytes corpus((std::istreambuf_iterator<char>(f)),{});assert(!corpus.empty());std::puts("{\"results\":[");bool first=true;for(std::size_t size:{32ul,512ul,3072ul,16384ul,262144ul,2097152ul})for(int kind=0;kind<3;kind++){bytes input(size);unsigned seed=17;for(size_t i=0;i<size;i++){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;input[i]=kind==0?0:kind==1?seed:corpus[i%corpus.size()];}auto zipped=gzip(input);bytes output(size);assert(baseline::inflate(zipped.size(),reader{zipped},output.data(),size));assert(input==output);assert(candidate::inflate(zipped.size(),reader{zipped},output.data(),size));assert(input==output);std::vector<double>old,newer;int n=size<16384?5000:size<262144?500:20;for(int j=0;j<9;j++){if(j%2){newer.push_back(time(candidate::inflate<reader>,zipped,output,n));old.push_back(time(baseline::inflate<reader>,zipped,output,n));}else{old.push_back(time(baseline::inflate<reader>,zipped,output,n));newer.push_back(time(candidate::inflate<reader>,zipped,output,n));}}auto sorted_old=old,sorted_new=newer;std::sort(sorted_old.begin(),sorted_old.end());std::sort(sorted_new.begin(),sorted_new.end());if(!first)std::puts(",");first=false;std::printf("{\"size\":%zu,\"kind\":%d,\"gzip_size\":%zu,\"iterations\":%d,\"before_ns\":%.3f,\"after_ns\":%.3f,\"change_pct\":%.2f,\"before_samples\":[",size,kind,zipped.size(),n,sorted_old[4],sorted_new[4],(sorted_new[4]/sorted_old[4]-1)*100);for(size_t i=0;i<old.size();i++)std::printf("%s%.3f",i?",":"",old[i]);std::printf("],\"after_samples\":[");for(size_t i=0;i<newer.size();i++)std::printf("%s%.3f",i?",":"",newer[i]);std::printf("]}");}std::puts("]}");}
