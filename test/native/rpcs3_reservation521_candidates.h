// SPDX-License-Identifier: GPL-2.0-only
// Measurement candidates only: no production reservation or fence change.
#pragma once
#include <arm_neon.h>
#include <cstdint>
namespace rpcs3_reservation521 {
inline bool xor_tree(const uint8_t* a,const uint8_t* b) noexcept {
    const auto d0=veorq_u8(vld1q_u8(a),vld1q_u8(b));
    const auto d1=veorq_u8(vld1q_u8(a+16),vld1q_u8(b+16));
    const auto d2=veorq_u8(vld1q_u8(a+32),vld1q_u8(b+32));
    const auto d3=veorq_u8(vld1q_u8(a+48),vld1q_u8(b+48));
    const auto d4=veorq_u8(vld1q_u8(a+64),vld1q_u8(b+64));
    const auto d5=veorq_u8(vld1q_u8(a+80),vld1q_u8(b+80));
    const auto d6=veorq_u8(vld1q_u8(a+96),vld1q_u8(b+96));
    const auto d7=veorq_u8(vld1q_u8(a+112),vld1q_u8(b+112));
    return vmaxvq_u8(vorrq_u8(vorrq_u8(vorrq_u8(d0,d1),vorrq_u8(d2,d3)),
                            vorrq_u8(vorrq_u8(d4,d5),vorrq_u8(d6,d7))))==0;
}
inline bool equality_tree(const uint8_t* a,const uint8_t* b) noexcept {
    const auto d0=vceqq_u8(vld1q_u8(a),vld1q_u8(b));
    const auto d1=vceqq_u8(vld1q_u8(a+16),vld1q_u8(b+16));
    const auto d2=vceqq_u8(vld1q_u8(a+32),vld1q_u8(b+32));
    const auto d3=vceqq_u8(vld1q_u8(a+48),vld1q_u8(b+48));
    const auto d4=vceqq_u8(vld1q_u8(a+64),vld1q_u8(b+64));
    const auto d5=vceqq_u8(vld1q_u8(a+80),vld1q_u8(b+80));
    const auto d6=vceqq_u8(vld1q_u8(a+96),vld1q_u8(b+96));
    const auto d7=vceqq_u8(vld1q_u8(a+112),vld1q_u8(b+112));
    return vminvq_u8(vandq_u8(vandq_u8(vandq_u8(d0,d1),vandq_u8(d2,d3)),
                            vandq_u8(vandq_u8(d4,d5),vandq_u8(d6,d7))))==255;
}
}
