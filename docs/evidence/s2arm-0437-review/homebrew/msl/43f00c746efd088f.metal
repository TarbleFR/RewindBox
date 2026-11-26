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

struct _18
{
    float4 _m0[4096];
};

struct _23
{
    uint _m0[1];
};

kernel void vk_43f00c746efd088f(device _23& cp_s0 [[buffer(2)]])
{
    cp_s0._m0[1] = cp_s0._m0[0];
    cp_s0._m0[2] = 42u;
}

