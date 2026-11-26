#include <metal_stdlib>
#include <simd/simd.h>

using namespace metal;

struct _12
{
    uint4 _m0;
    uint _m1[8];
    float4 _m2;
    float4 _m3;
    int _m4;
    float _m5[73];
    int4 _m6;
    int _m7;
    int4 _m8;
    int4 _m9;
    int4 _m10;
    float _m11[73];
    int4 _m12[73];
};

struct vk_d450c0bd06ebc4b8_out
{
    float4 m_21 [[color(0)]];
};

struct vk_d450c0bd06ebc4b8_in
{
    float4 m_18 [[user(locn0)]];
};

fragment vk_d450c0bd06ebc4b8_out vk_d450c0bd06ebc4b8(vk_d450c0bd06ebc4b8_in in [[stage_in]])
{
    vk_d450c0bd06ebc4b8_out out = {};
    out.m_21.x = in.m_18.w;
    out.m_21.y = in.m_18.z;
    out.m_21.z = in.m_18.y;
    out.m_21.w = in.m_18.x;
    return out;
}

