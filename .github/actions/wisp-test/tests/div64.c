/*
 * The action's check of 64-bit division: `/` and `%` on uint64_t and int64_t, which on sparc32
 * are calls to the helpers in libgcc-sparc32.c (__udivdi3, __umoddi3, __divdi3, __moddi3). The
 * operands are volatile so that the compiler cannot work the results out itself. Covers divisors
 * above 32 bits, negative operands (C truncates towards zero), INT64_MIN and a divisor larger than
 * the dividend. Must pass on every architecture.
 */
#include <stdint.h>
#include <stdio.h>

struct ucase { uint64_t a, b, q, r; };
struct scase { int64_t a, b, q, r; };

static const struct ucase ucases[] = {
	{ 0xFFFFFFFFFFFFFFFFull, 10, 1844674407370955161ull, 5 },
	{ 0xFEDCBA9876543210ull, 0x123456789ull, 3758096384ull, 2522100240ull },
	{ 0x8000000000000000ull, 0xFFFFFFFFull, 2147483648ull, 2147483648ull },
	{ 5, 0x100000000ull, 0, 5 },
	{ 1000000, 7, 142857, 1 },
};

static const struct scase scases[] = {
	{ -1000000000000000007ll, 1000000007, -999999993, -56 },
	{ 1000000000000000007ll, -1000000007, -999999993, 56 },
	{ -1000000000000000007ll, -1000000007, 999999993, -56 },
	{ INT64_MIN, 3, -3074457345618258602ll, -2 },
	{ INT64_MIN, -4294967297ll, 2147483647, -2147483649ll },
	{ -7, 2, -3, -1 },
	{ INT64_MAX, -2, -4611686018427387903ll, 1 },
};

int main(void)
{
	unsigned int i, bad = 0;

	for (i = 0; i < sizeof(ucases) / sizeof(ucases[0]); i++) {
		volatile uint64_t a = ucases[i].a, b = ucases[i].b;
		uint64_t q = a / b, r = a % b;
		int ok = q == ucases[i].q && r == ucases[i].r;

		printf("%s %llu / %llu = %llu rem %llu\n", ok ? "ok  " : "FAIL",
		       (unsigned long long)a, (unsigned long long)b, (unsigned long long)q,
		       (unsigned long long)r);
		bad += !ok;
	}
	for (i = 0; i < sizeof(scases) / sizeof(scases[0]); i++) {
		volatile int64_t a = scases[i].a, b = scases[i].b;
		int64_t q = a / b, r = a % b;
		int ok = q == scases[i].q && r == scases[i].r;

		printf("%s %lld / %lld = %lld rem %lld\n", ok ? "ok  " : "FAIL", (long long)a,
		       (long long)b, (long long)q, (long long)r);
		bad += !ok;
	}
	printf("%s\n", bad ? "FAIL" : "PASS");
	return bad != 0;
}
