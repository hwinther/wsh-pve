/*
 * hello: a smoke test for the wisp uClibc-ng toolchain, ordinary libc rather than nolibc
 * (e2e/wisp/README.md, "A libc toolchain (uClibc-ng)"; nolibc has no qsort, and sparc32 has no
 * libgcc for 64-bit division there, see .github/actions/wisp-test/README.md, "Limits").
 *
 * Exercises printf, snprintf, malloc/free, qsort, strtol, a struct with 64-bit fields and 64-bit
 * division, then prints one fixed checksum line and exits 0. Every value below is fixed (a
 * constant seed, a constant string), so the checksum is the same on every architecture; it does
 * not depend on pointer values, struct layout or memory order, only on 64-bit integer arithmetic,
 * so it also checks that this toolchain's 64-bit division works on sparc32 (V8 has no divide
 * instruction wide enough; the compiler calls libgcc's __udivdi3 and friends, which this
 * toolchain's own gcc builds correctly for V8, unlike Debian's packaged 32-bit sparc libgcc).
 *
 * Under wisp=test, PID 1 runs this binary as /test from an external initramfs.
 * See the adjacent README for the build command and expected console output.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct record {
	uint64_t a;
	uint64_t b;
};

static int cmp_u64(const void *pa, const void *pb)
{
	uint64_t a = *(const uint64_t *)pa;
	uint64_t b = *(const uint64_t *)pb;

	if (a < b)
		return -1;
	if (a > b)
		return 1;
	return 0;
}

int main(void)
{
	enum { N = 16 };
	uint64_t state = 0x1234567890abcdefULL; /* fixed seed: xorshift64 */
	uint64_t values[N];
	uint64_t *sorted;
	struct record rec;
	uint64_t quotient, remainder, checksum;
	long parsed;
	char buf[256];
	int i, n;

	for (i = 0; i < N; i++) {
		state ^= state << 13;
		state ^= state >> 7;
		state ^= state << 17;
		values[i] = state;
	}

	/* malloc/free and qsort on the heap copy, not the stack array. */
	sorted = malloc(sizeof(values));
	if (!sorted) {
		fprintf(stderr, "hello: malloc failed\n");
		return 1;
	}
	memcpy(sorted, values, sizeof(values));
	qsort(sorted, N, sizeof(uint64_t), cmp_u64);

	/* A struct with 64-bit fields, and 64-bit division on them. */
	rec.a = sorted[N - 1];
	rec.b = sorted[0] != 0 ? sorted[0] : 1;
	quotient = rec.a / rec.b;
	remainder = rec.a % rec.b;

	/* strtol on a fixed string. */
	parsed = strtol("424242", NULL, 10);

	checksum = (uint64_t)parsed;
	for (i = 0; i < N; i++)
		checksum += sorted[i] * (uint64_t)(i + 1);
	checksum += quotient ^ remainder;

	/* snprintf, folded into the checksum byte by byte so its own output affects the result. */
	n = snprintf(buf, sizeof(buf), "quotient=%llu remainder=%llu parsed=%ld",
		     (unsigned long long)quotient, (unsigned long long)remainder, parsed);
	for (i = 0; i < n; i++)
		checksum += (unsigned char)buf[i];

	free(sorted);

	printf("WISP-HELLO v=1 checksum=0x%016llx status=ok\n", (unsigned long long)checksum);
	return 0;
}
