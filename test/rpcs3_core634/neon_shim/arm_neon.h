// The NEON and ARMv8 Crypto intrinsics of ios/IOSCryptoA64.h, in C, after the pseudocode of the Arm
// Architecture Reference Manual. Only for x86 hosts: test/rpcs3_core634/crypto_a64_test.cpp checks
// the header's rounds against the C code here, and on the real instructions on the Apple ARM64 runner.
#pragma once
#include <cstdint>
#include <cstring>

struct uint8x16_t { std::uint8_t b[16]; };
struct uint32x4_t { std::uint32_t w[4]; };

inline uint8x16_t vld1q_u8(const std::uint8_t* p) { uint8x16_t r; std::memcpy(r.b, p, 16); return r; }
inline void vst1q_u8(std::uint8_t* p, uint8x16_t v) { std::memcpy(p, v.b, 16); }
inline uint32x4_t vld1q_u32(const std::uint32_t* p) { uint32x4_t r; std::memcpy(r.w, p, 16); return r; }
inline void vst1q_u32(std::uint32_t* p, uint32x4_t v) { std::memcpy(p, v.w, 16); }
inline uint8x16_t veorq_u8(uint8x16_t a, uint8x16_t b) { for (int i = 0; i < 16; i++) a.b[i] ^= b.b[i]; return a; }
inline uint32x4_t vaddq_u32(uint32x4_t a, uint32x4_t b) { for (int i = 0; i < 4; i++) a.w[i] += b.w[i]; return a; }
inline uint32x4_t vdupq_n_u32(std::uint32_t v) { return {{v, v, v, v}}; }
inline uint8x16_t vrev32q_u8(uint8x16_t v) { uint8x16_t r; for (int i = 0; i < 16; i += 4) for (int j = 0; j < 4; j++) r.b[i + j] = v.b[i + 3 - j]; return r; }
inline uint32x4_t vreinterpretq_u32_u8(uint8x16_t v) { uint32x4_t r; std::memcpy(r.w, v.b, 16); return r; }
#define vgetq_lane_u32(v, lane) ((v).w[(lane)])

namespace neon_shim
{
inline std::uint32_t rol(std::uint32_t v, int n) { return n ? (v << n) | (v >> (32 - n)) : v; }
inline std::uint32_t ror(std::uint32_t v, int n) { return rol(v, 32 - n); }
inline std::uint32_t choose(std::uint32_t x, std::uint32_t y, std::uint32_t z) { return ((y ^ z) & x) ^ z; }
inline std::uint32_t parity(std::uint32_t x, std::uint32_t y, std::uint32_t z) { return x ^ y ^ z; }
inline std::uint32_t majority(std::uint32_t x, std::uint32_t y, std::uint32_t z) { return (x & y) | ((x | y) & z); }

inline const std::uint8_t* sbox()
{
	static std::uint8_t table[256];
	static bool ready = false;
	if (!ready)
	{
		std::uint8_t p = 1, q = 1;
		do
		{
			p = static_cast<std::uint8_t>(p ^ (p << 1) ^ ((p & 0x80) ? 0x1b : 0));
			q ^= static_cast<std::uint8_t>(q << 1); q ^= static_cast<std::uint8_t>(q << 2); q ^= static_cast<std::uint8_t>(q << 4);
			if (q & 0x80) q ^= 0x09;
			const std::uint8_t x = static_cast<std::uint8_t>(q ^ ((q << 1) | (q >> 7)) ^ ((q << 2) | (q >> 6)) ^ ((q << 3) | (q >> 5)) ^ ((q << 4) | (q >> 4)));
			table[p] = static_cast<std::uint8_t>(x ^ 0x63);
		} while (p != 1);
		table[0] = 0x63;
		ready = true;
	}
	return table;
}

inline const std::uint8_t* inverse_sbox()
{
	static std::uint8_t table[256];
	for (int i = 0; i < 256; i++) table[sbox()[i]] = static_cast<std::uint8_t>(i);
	return table;
}

inline std::uint8_t mul(std::uint8_t a, std::uint8_t b)
{
	std::uint8_t r = 0;
	for (; b; b >>= 1)
	{
		if (b & 1) r ^= a;
		a = static_cast<std::uint8_t>((a << 1) ^ ((a & 0x80) ? 0x1b : 0));
	}
	return r;
}

inline uint8x16_t mix(uint8x16_t s, std::uint8_t a, std::uint8_t b, std::uint8_t c, std::uint8_t d)
{
	uint8x16_t r;
	for (int col = 0; col < 4; col++)
	{
		const std::uint8_t* in = s.b + col * 4;
		std::uint8_t* out = r.b + col * 4;
		out[0] = mul(in[0], a) ^ mul(in[1], b) ^ mul(in[2], c) ^ mul(in[3], d);
		out[1] = mul(in[0], d) ^ mul(in[1], a) ^ mul(in[2], b) ^ mul(in[3], c);
		out[2] = mul(in[0], c) ^ mul(in[1], d) ^ mul(in[2], a) ^ mul(in[3], b);
		out[3] = mul(in[0], b) ^ mul(in[1], c) ^ mul(in[2], d) ^ mul(in[3], a);
	}
	return r;
}

template <typename F>
inline uint32x4_t sha1_rounds(uint32x4_t x, std::uint32_t y, uint32x4_t wk, F f)
{
	for (int e = 0; e < 4; e++)
	{
		y = y + rol(x.w[0], 5) + f(x.w[1], x.w[2], x.w[3]) + wk.w[e];
		x.w[1] = rol(x.w[1], 30);
		const std::uint32_t last = x.w[3];
		x.w[3] = x.w[2]; x.w[2] = x.w[1]; x.w[1] = x.w[0]; x.w[0] = y;
		y = last;
	}
	return x;
}

inline void sha256_rounds(uint32x4_t& x, uint32x4_t& y, uint32x4_t wk)
{
	for (int e = 0; e < 4; e++)
	{
		const std::uint32_t chs = choose(y.w[0], y.w[1], y.w[2]);
		const std::uint32_t maj = majority(x.w[0], x.w[1], x.w[2]);
		const std::uint32_t t = y.w[3] + (ror(y.w[0], 6) ^ ror(y.w[0], 11) ^ ror(y.w[0], 25)) + chs + wk.w[e];
		x.w[3] += t;
		y.w[3] = t + (ror(x.w[0], 2) ^ ror(x.w[0], 13) ^ ror(x.w[0], 22)) + maj;
		const std::uint32_t top = y.w[3];
		y.w[3] = y.w[2]; y.w[2] = y.w[1]; y.w[1] = y.w[0]; y.w[0] = x.w[3];
		x.w[3] = x.w[2]; x.w[2] = x.w[1]; x.w[1] = x.w[0]; x.w[0] = top;
	}
}
}

inline uint8x16_t vaeseq_u8(uint8x16_t state, uint8x16_t key)
{
	state = veorq_u8(state, key);
	uint8x16_t r;
	for (int col = 0; col < 4; col++) for (int row = 0; row < 4; row++)
		r.b[col * 4 + row] = neon_shim::sbox()[state.b[((col + row) % 4) * 4 + row]];
	return r;
}

inline uint8x16_t vaesdq_u8(uint8x16_t state, uint8x16_t key)
{
	state = veorq_u8(state, key);
	uint8x16_t r;
	for (int col = 0; col < 4; col++) for (int row = 0; row < 4; row++)
		r.b[col * 4 + row] = neon_shim::inverse_sbox()[state.b[((col + 4 - row) % 4) * 4 + row]];
	return r;
}

inline uint8x16_t vaesmcq_u8(uint8x16_t state) { return neon_shim::mix(state, 2, 3, 1, 1); }
inline uint8x16_t vaesimcq_u8(uint8x16_t state) { return neon_shim::mix(state, 14, 11, 13, 9); }

inline std::uint32_t vsha1h_u32(std::uint32_t e) { return neon_shim::rol(e, 30); }
inline uint32x4_t vsha1cq_u32(uint32x4_t abcd, std::uint32_t e, uint32x4_t wk) { return neon_shim::sha1_rounds(abcd, e, wk, neon_shim::choose); }
inline uint32x4_t vsha1pq_u32(uint32x4_t abcd, std::uint32_t e, uint32x4_t wk) { return neon_shim::sha1_rounds(abcd, e, wk, neon_shim::parity); }
inline uint32x4_t vsha1mq_u32(uint32x4_t abcd, std::uint32_t e, uint32x4_t wk) { return neon_shim::sha1_rounds(abcd, e, wk, neon_shim::majority); }

inline uint32x4_t vsha1su0q_u32(uint32x4_t w0, uint32x4_t w1, uint32x4_t w2)
{
	const uint32x4_t concat = {{w0.w[2], w0.w[3], w1.w[0], w1.w[1]}};
	uint32x4_t r;
	for (int i = 0; i < 4; i++) r.w[i] = concat.w[i] ^ w0.w[i] ^ w2.w[i];
	return r;
}

inline uint32x4_t vsha1su1q_u32(uint32x4_t tw, uint32x4_t w)
{
	const uint32x4_t t = {{tw.w[0] ^ w.w[1], tw.w[1] ^ w.w[2], tw.w[2] ^ w.w[3], tw.w[3]}};
	uint32x4_t r;
	for (int i = 0; i < 4; i++) r.w[i] = neon_shim::rol(t.w[i], 1);
	r.w[3] ^= neon_shim::rol(t.w[0], 2);
	return r;
}

inline uint32x4_t vsha256hq_u32(uint32x4_t abcd, uint32x4_t efgh, uint32x4_t wk) { neon_shim::sha256_rounds(abcd, efgh, wk); return abcd; }
inline uint32x4_t vsha256h2q_u32(uint32x4_t efgh, uint32x4_t abcd, uint32x4_t wk) { neon_shim::sha256_rounds(abcd, efgh, wk); return efgh; }

inline uint32x4_t vsha256su0q_u32(uint32x4_t w0, uint32x4_t w1)
{
	const uint32x4_t t = {{w0.w[1], w0.w[2], w0.w[3], w1.w[0]}};
	uint32x4_t r;
	for (int i = 0; i < 4; i++) r.w[i] = w0.w[i] + (neon_shim::ror(t.w[i], 7) ^ neon_shim::ror(t.w[i], 18) ^ (t.w[i] >> 3));
	return r;
}

inline uint32x4_t vsha256su1q_u32(uint32x4_t tw, uint32x4_t w2, uint32x4_t w3)
{
	const auto sigma = [](std::uint32_t v) { return neon_shim::ror(v, 17) ^ neon_shim::ror(v, 19) ^ (v >> 10); };
	const std::uint32_t t0[4] = {w2.w[1], w2.w[2], w2.w[3], w3.w[0]};
	uint32x4_t r;
	r.w[0] = sigma(w3.w[2]) + tw.w[0] + t0[0];
	r.w[1] = sigma(w3.w[3]) + tw.w[1] + t0[1];
	r.w[2] = sigma(r.w[0]) + tw.w[2] + t0[2];
	r.w[3] = sigma(r.w[1]) + tw.w[3] + t0[3];
	return r;
}
