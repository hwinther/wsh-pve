/*
 * The 64-bit division helpers gcc calls on sparc32, linked in by wisp-test.sh for sparc32 only.
 *
 * SPARC V8 divides 32 bits by 32 in hardware (udiv, sdiv); a 64-bit `/` or `%` is a call to
 * __udivdi3, __divdi3, __umoddi3 or __moddi3 in libgcc. Ubuntu has no V8 libgcc (its 32-bit one
 * is V8+, which the sparc32 kernel refuses), so these are written here: restoring shift-subtract
 * long division, one quotient bit per step, with a 32-bit hardware division when both operands
 * fit in 32 bits. Nothing in this file divides a 64-bit value, so it calls nothing itself.
 *
 * Division by zero gives SIGFPE, as on sparc64 and x86_64: a 32-bit udiv by zero traps.
 */
typedef unsigned long long u64;
typedef long long s64;

u64 __udivmoddi4(u64 n, u64 d, u64 *rem);
s64 __divmoddi4(s64 a, s64 b, s64 *rem);
u64 __udivdi3(u64 n, u64 d);
u64 __umoddi3(u64 n, u64 d);
s64 __divdi3(s64 a, s64 b);
s64 __moddi3(s64 a, s64 b);

u64 __udivmoddi4(u64 n, u64 d, u64 *rem)
{
	u64 q = 0, bit = 1;

	if (d == 0) {
		/* Both volatile: gcc turns 1u / x into x == 1 */
		volatile unsigned int one = 1, zero = 0;

		return one / zero; /* udiv by zero: division_by_zero trap, SIGFPE */
	}
	if ((n >> 32) == 0 && (d >> 32) == 0) {
		unsigned int n32 = (unsigned int)n, d32 = (unsigned int)d;

		if (rem)
			*rem = n32 % d32;
		return n32 / d32;
	}
	if (d > n) {
		if (rem)
			*rem = n;
		return 0;
	}
	/* Line the divisor up under the dividend's top bit, then subtract back down. */
	while (!(d >> 63) && (d << 1) <= n) {
		d <<= 1;
		bit <<= 1;
	}
	while (bit) {
		if (n >= d) {
			n -= d;
			q |= bit;
		}
		d >>= 1;
		bit >>= 1;
	}
	if (rem)
		*rem = n;
	return q;
}

/* Truncating, as C requires: the quotient's sign is the operands' signs combined, the
 * remainder's that of the dividend. The magnitudes are taken in unsigned arithmetic, so
 * INT64_MIN has one too. */
s64 __divmoddi4(s64 a, s64 b, s64 *rem)
{
	u64 ua = a < 0 ? -(u64)a : (u64)a;
	u64 ub = b < 0 ? -(u64)b : (u64)b;
	u64 r, q = __udivmoddi4(ua, ub, &r);

	if (rem)
		*rem = a < 0 ? (s64)-r : (s64)r;
	return (a < 0) != (b < 0) ? (s64)-q : (s64)q;
}

u64 __udivdi3(u64 n, u64 d)
{
	return __udivmoddi4(n, d, 0);
}

u64 __umoddi3(u64 n, u64 d)
{
	u64 r;

	__udivmoddi4(n, d, &r);
	return r;
}

s64 __divdi3(s64 a, s64 b)
{
	return __divmoddi4(a, b, 0);
}

s64 __moddi3(s64 a, s64 b)
{
	s64 r;

	__divmoddi4(a, b, &r);
	return r;
}
