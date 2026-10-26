XXH_FORCE_INLINE void accumulate_texture_stripes(xxh_u64* XXH_RESTRICT acc,
 const xxh_u8* XXH_RESTRICT input, const xxh_u8* XXH_RESTRICT secret,
 size_t stripe_count)
{
 size_t stripe = 0;
 for (; stripe + 3 < stripe_count; stripe += 4)
 {
  XXH_PREFETCH(input + stripe * XXH_STRIPE_LEN + XXH_PREFETCH_DIST);
  #if defined(__clang__)
#pragma clang loop unroll(full)
#endif
  for (size_t round = 0; round < 4; ++round)
  {
   XXH3_scalarRound(acc, input + (stripe + round) * XXH_STRIPE_LEN, secret + (stripe + round) * XXH_SECRET_CONSUME_RATE, 6);
   XXH3_scalarRound(acc, input + (stripe + round) * XXH_STRIPE_LEN, secret + (stripe + round) * XXH_SECRET_CONSUME_RATE, 7);
  }
  #if defined(__clang__)
#pragma clang loop unroll(full)
#endif
  for (size_t group = 0; group < 1; ++group)
  {
   const size_t lane = group * 32;
   const auto* data = input + stripe * XXH_STRIPE_LEN + lane;
   const auto* key = secret + stripe * XXH_SECRET_CONSUME_RATE + lane;
   const uint64x2_t d00 = XXH_vld1q_u64(data), d01 = XXH_vld1q_u64(data + 16);
   const uint64x2_t d10 = XXH_vld1q_u64(data + 64), d11 = XXH_vld1q_u64(data + 80);
   const uint64x2_t d20 = XXH_vld1q_u64(data + 128), d21 = XXH_vld1q_u64(data + 144);
   const uint64x2_t d30 = XXH_vld1q_u64(data + 192), d31 = XXH_vld1q_u64(data + 208);
   const uint64x2_t k00 = veorq_u64(d00, XXH_vld1q_u64(key));
   const uint64x2_t k01 = veorq_u64(d01, XXH_vld1q_u64(key + 16));
   const uint64x2_t k10 = veorq_u64(d10, XXH_vld1q_u64(key + 8));
   const uint64x2_t k11 = veorq_u64(d11, XXH_vld1q_u64(key + 24));
   const uint64x2_t k20 = veorq_u64(d20, XXH_vld1q_u64(key + 16));
   const uint64x2_t k21 = veorq_u64(d21, XXH_vld1q_u64(key + 32));
   const uint64x2_t k30 = veorq_u64(d30, XXH_vld1q_u64(key + 24));
   const uint64x2_t k31 = veorq_u64(d31, XXH_vld1q_u64(key + 40));
   const uint32x4x2_t u0 = vuzpq_u32(vreinterpretq_u32_u64(k00), vreinterpretq_u32_u64(k01));
   const uint32x4x2_t u1 = vuzpq_u32(vreinterpretq_u32_u64(k10), vreinterpretq_u32_u64(k11));
   const uint32x4x2_t u2 = vuzpq_u32(vreinterpretq_u32_u64(k20), vreinterpretq_u32_u64(k21));
   const uint32x4x2_t u3 = vuzpq_u32(vreinterpretq_u32_u64(k30), vreinterpretq_u32_u64(k31));
   const uint64x2_t d0 = vaddq_u64(vaddq_u64(d00, d10),vaddq_u64(d20, d30)), d1 = vaddq_u64(vaddq_u64(d01, d11),vaddq_u64(d21, d31));
   auto product0a = XXH_vmlal_low_u32(vdupq_n_u64(0), u0.val[0], u0.val[1]);
   product0a = XXH_vmlal_low_u32(product0a, u2.val[0], u2.val[1]);
   auto product0b = XXH_vmlal_low_u32(vdupq_n_u64(0), u1.val[0], u1.val[1]);
   product0b = XXH_vmlal_low_u32(product0b, u3.val[0], u3.val[1]);
   XXH_COMPILER_GUARD_CLANG_NEON(product0a);
   XXH_COMPILER_GUARD_CLANG_NEON(product0b);
   const auto sum0 = vaddq_u64(vextq_u64(d0, d0, 1), vaddq_u64(product0a, product0b));
   auto product1a = XXH_vmlal_high_u32(vdupq_n_u64(0), u0.val[0], u0.val[1]);
   product1a = XXH_vmlal_high_u32(product1a, u2.val[0], u2.val[1]);
   auto product1b = XXH_vmlal_high_u32(vdupq_n_u64(0), u1.val[0], u1.val[1]);
   product1b = XXH_vmlal_high_u32(product1b, u3.val[0], u3.val[1]);
   XXH_COMPILER_GUARD_CLANG_NEON(product1a);
   XXH_COMPILER_GUARD_CLANG_NEON(product1b);
   const auto sum1 = vaddq_u64(vextq_u64(d1, d1, 1), vaddq_u64(product1a, product1b));
   auto* xacc = reinterpret_cast<xxh_aliasing_uint64x2_t*>(acc);
   xacc[group * 2] = vaddq_u64(xacc[group * 2], sum0);
   xacc[group * 2 + 1] = vaddq_u64(xacc[group * 2 + 1], sum1);
  }
  {
   const auto* data = input + stripe * XXH_STRIPE_LEN + 32;
   const auto* key = secret + stripe * XXH_SECRET_CONSUME_RATE + 32;
   const auto d0 = XXH_vld1q_u64(data), d1 = XXH_vld1q_u64(data + 64);
   const auto d2 = XXH_vld1q_u64(data + 128), d3 = XXH_vld1q_u64(data + 192);
   const auto k0 = veorq_u64(d0, XXH_vld1q_u64(key)), k1 = veorq_u64(d1, XXH_vld1q_u64(key + 8));
   const auto k2 = veorq_u64(d2, XXH_vld1q_u64(key + 16)), k3 = veorq_u64(d3, XXH_vld1q_u64(key + 24));
   const auto u01 = vuzpq_u32(vreinterpretq_u32_u64(k0), vreinterpretq_u32_u64(k1));
   const auto u23 = vuzpq_u32(vreinterpretq_u32_u64(k2), vreinterpretq_u32_u64(k3));
   const auto data_sum = vaddq_u64(vaddq_u64(d0,d1),vaddq_u64(d2,d3));
   auto producta = XXH_vmlal_low_u32(vdupq_n_u64(0), u01.val[0], u01.val[1]);
   producta = XXH_vmlal_low_u32(producta, u23.val[0], u23.val[1]);
   auto productb = XXH_vmlal_high_u32(vdupq_n_u64(0), u01.val[0], u01.val[1]);
   productb = XXH_vmlal_high_u32(productb, u23.val[0], u23.val[1]);
   XXH_COMPILER_GUARD_CLANG_NEON(producta);
   XXH_COMPILER_GUARD_CLANG_NEON(productb);
   const auto sum = vaddq_u64(vextq_u64(data_sum, data_sum, 1), vaddq_u64(producta, productb));
   auto* xacc = reinterpret_cast<xxh_aliasing_uint64x2_t*>(acc);
   xacc[2] = vaddq_u64(xacc[2],sum);
  }
 }
 for (; stripe < stripe_count; ++stripe)
  XXH3_accumulate_512_neon(acc, input + stripe * XXH_STRIPE_LEN, secret + stripe * XXH_SECRET_CONSUME_RATE);
}
