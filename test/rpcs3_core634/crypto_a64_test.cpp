// REWINDBOX_CRYPTO_A64_634: the real rpcs3/Crypto sources. The instruction path against the C path on
// random data and split updates, and FIPS vectors. Apple ARM64 runs the instructions; another host
// builds with RPCS3_TEST_CRYPTO_A64 and neon_shim/arm_neon.h, the same rounds in C.
#include "Crypto/aes.h"
#include "Crypto/sha1.h"
#include "Crypto/sha256.h"
#include "ios/IOSCryptoA64.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <vector>

namespace a64 = rpcs3::ios::crypto_a64;

// Crypto/utils.cpp, which brings the rest of the emulator with it.
void mbedtls_zeroize(void* data, std::size_t size) { std::memset(data, 0, size); }

static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

static std::vector<unsigned char> hex(const char* text)
{
	std::vector<unsigned char> out;
	for (; text[0] && text[1]; text += 2)
	{
		const char pair[3] = {text[0], text[1], 0};
		out.push_back(static_cast<unsigned char>(std::strtoul(pair, nullptr, 16)));
	}
	return out;
}

static std::vector<unsigned char> sha1_of(const std::vector<unsigned char>& data, std::size_t chunk)
{
	sha1_context ctx;
	sha1_starts(&ctx);
	for (std::size_t pos = 0; pos < data.size(); pos += chunk)
	{
		sha1_update(&ctx, data.data() + pos, std::min(chunk, data.size() - pos));
	}
	std::vector<unsigned char> digest(20);
	sha1_finish(&ctx, digest.data());
	return digest;
}

static std::vector<unsigned char> sha256_of(const std::vector<unsigned char>& data, std::size_t chunk)
{
	mbedtls_sha256_context ctx;
	mbedtls_sha256_init(&ctx);
	mbedtls_sha256_starts_ret(&ctx, 0);
	for (std::size_t pos = 0; pos < data.size(); pos += chunk)
	{
		mbedtls_sha256_update_ret(&ctx, data.data() + pos, std::min(chunk, data.size() - pos));
	}
	std::vector<unsigned char> digest(32);
	mbedtls_sha256_finish_ret(&ctx, digest.data());
	mbedtls_sha256_free(&ctx);
	return digest;
}

static std::vector<unsigned char> ctr_of(const std::vector<unsigned char>& key, std::vector<unsigned char> nonce, const std::vector<unsigned char>& data, std::size_t chunk)
{
	aes_context ctx;
	aes_setkey_enc(&ctx, key.data(), static_cast<unsigned>(key.size() * 8));
	std::vector<unsigned char> out(data.size());
	unsigned char stream[16]{};
	size_t offset = 0;
	for (std::size_t pos = 0; pos < data.size(); pos += chunk)
	{
		aes_crypt_ctr(&ctx, std::min(chunk, data.size() - pos), &offset, nonce.data(), stream, data.data() + pos, out.data() + pos);
	}
	out.insert(out.end(), nonce.begin(), nonce.end());
	return out;
}

int main()
{
	std::mt19937 random(0x634);
	const auto bytes = [&](std::size_t size)
	{
		std::vector<unsigned char> out(size);
		for (auto& byte : out) byte = static_cast<unsigned char>(random());
		return out;
	};

	for (const bool on : {false, true})
	{
		a64::enabled = on;
		CHECK(sha1_of({'a', 'b', 'c'}, 3) == hex("a9993e364706816aba3e25717850c26c9cd0d89d"));
		CHECK(sha256_of({'a', 'b', 'c'}, 3) == hex("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
		std::vector<unsigned char> million(1000000, 'a');
		CHECK(sha1_of(million, 777) == hex("34aa973cd4c4daa4f61eeb2bdbad27316534016f"));
		CHECK(sha256_of(million, 777) == hex("cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"));

		const auto key128 = hex("000102030405060708090a0b0c0d0e0f");
		const auto key256 = hex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f");
		const auto plain = hex("00112233445566778899aabbccddeeff");
		unsigned char out[16];
		aes_context ctx;
		aes_setkey_enc(&ctx, key128.data(), 128);
		aes_crypt_ecb(&ctx, AES_ENCRYPT, plain.data(), out);
		CHECK(std::memcmp(out, hex("69c4e0d86a7b0430d8cdb78070b4c55a").data(), 16) == 0);
		aes_setkey_dec(&ctx, key128.data(), 128);
		aes_crypt_ecb(&ctx, AES_DECRYPT, hex("69c4e0d86a7b0430d8cdb78070b4c55a").data(), out);
		CHECK(std::memcmp(out, plain.data(), 16) == 0);
		aes_setkey_enc(&ctx, key256.data(), 256);
		aes_crypt_ecb(&ctx, AES_ENCRYPT, plain.data(), out);
		CHECK(std::memcmp(out, hex("8ea2b7ca516745bfeafc49904b496089").data(), 16) == 0);
		aes_setkey_dec(&ctx, key256.data(), 256);
		aes_crypt_ecb(&ctx, AES_DECRYPT, hex("8ea2b7ca516745bfeafc49904b496089").data(), out);
		CHECK(std::memcmp(out, plain.data(), 16) == 0);
	}

	// The round functions themselves, on the key schedules of the C code.
	for (const unsigned bits : {128u, 192u, 256u})
	{
		const auto key = bytes(bits / 8);
		aes_context enc, dec;
		a64::enabled = false;
		aes_setkey_enc(&enc, key.data(), bits);
		aes_setkey_dec(&dec, key.data(), bits);
		for (int i = 0; i < 64; i++)
		{
			const auto block = bytes(16);
			unsigned char reference[16], fast[16];
			aes_crypt_ecb(&enc, AES_ENCRYPT, block.data(), reference);
			a64::ecb(enc.rk, enc.nr, false, block.data(), fast);
			CHECK(std::memcmp(reference, fast, 16) == 0);
			aes_crypt_ecb(&dec, AES_DECRYPT, block.data(), reference);
			a64::ecb(dec.rk, dec.nr, true, block.data(), fast);
			CHECK(std::memcmp(reference, fast, 16) == 0);
		}
	}

	unsigned compared = 0;
	for (const std::size_t size : {0ull, 1ull, 15ull, 16ull, 17ull, 55ull, 56ull, 63ull, 64ull, 65ull, 119ull, 120ull, 4096ull, 70001ull})
	{
		for (const std::size_t chunk : {1ull, 7ull, 16ull, 33ull, 64ull, 65ull, 4096ull, 100000ull})
		{
			if (size > 4096 && chunk == 1) continue;
			const auto data = bytes(size);
			const auto key = bytes(16);
			auto nonce = bytes(16);
			if (size % 2) { std::memset(nonce.data() + 8, 0xff, 8); } // the counter carries past bit 64

			a64::enabled = false;
			const auto sha1_c = sha1_of(data, chunk), sha256_c = sha256_of(data, chunk), ctr_c = ctr_of(key, nonce, data, chunk);
			a64::enabled = true;
			CHECK(sha1_of(data, chunk) == sha1_c);
			CHECK(sha256_of(data, chunk) == sha256_c);
			CHECK(ctr_of(key, nonce, data, chunk) == ctr_c);
			compared++;
		}
	}

	a64::enabled = true;
	const int instructions = int{a64::aes()} + int{a64::sha1()} + int{a64::sha256()};
	std::printf("{\"crypto_compared\": %u, \"instructions\": %d, \"failures\": %d}\n", compared, instructions, failures);
	return failures != 0;
}
