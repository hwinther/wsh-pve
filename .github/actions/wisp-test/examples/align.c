/*
 * An alignment bug: a packed record (a 1-byte type, then a 4-byte length) read by casting a byte
 * pointer to uint32_t *. x86 allows the unaligned load; sparc traps and the kernel sends SIGBUS.
 * Built with -DFIXED, the length is copied out with memcpy and it passes everywhere.
 *
 * Builds with nolibc (the wisp-test action) and with a normal C library: cc align.c
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static unsigned char buf[16] __attribute__((aligned(8)));
/*
 * Where the record starts, as a parser would know it at run time. volatile, so the compiler
 * can't see that the length field is at an odd address: when it can, gcc reads it byte by byte
 * on sparc by itself and the bug stays hidden.
 */
static volatile unsigned int pos;

static uint32_t length_of(const unsigned char *rec)
{
#ifdef FIXED
	uint32_t v;

	memcpy(&v, rec + 1, sizeof(v));
	return v;
#else
	return *(const uint32_t *)(rec + 1); /* the bug: an unaligned 4-byte load */
#endif
}

int main(void)
{
	const unsigned char *rec = buf + pos;
	uint32_t len = 1234, got;

	buf[pos] = 7;
	memcpy(buf + pos + 1, &len, sizeof(len));
	printf("type %u, reading the length at offset %u\n", rec[0], pos + 1);
	got = length_of(rec);
	if (got != len) {
		printf("FAIL: length %u, want %u\n", (unsigned int)got, (unsigned int)len);
		return 1;
	}
	printf("length %u\nPASS\n", (unsigned int)got);
	return 0;
}
