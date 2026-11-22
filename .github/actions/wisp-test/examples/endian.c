/*
 * An endianness bug: a little-endian record (as a file format or protocol defines it) read with
 * memcpy into a uint32_t, which gives the host's byte order. Passes on x86, fails on sparc.
 * Built with -DFIXED, the fields are put together byte by byte and it passes everywhere.
 *
 * Builds with nolibc (the wisp-test action) and with a normal C library: cc endian.c
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* magic "WISP", u16 version, u16 count, then count u32 values; all little-endian */
static const unsigned char record[] = {
	'W', 'I', 'S', 'P', 2, 0, 3, 0, 0x10, 0, 0, 0, 0x20, 0, 0, 0, 0x30, 0x01, 0, 0,
};

#ifdef FIXED
static uint32_t le32(const unsigned char *p)
{
	return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24;
}

static uint16_t le16(const unsigned char *p)
{
	return p[0] | p[1] << 8;
}
#else
static uint32_t le32(const unsigned char *p)
{
	uint32_t v;

	memcpy(&v, p, sizeof(v)); /* the bug: host byte order */
	return v;
}

static uint16_t le16(const unsigned char *p)
{
	uint16_t v;

	memcpy(&v, p, sizeof(v));
	return v;
}
#endif

int main(void)
{
	uint32_t magic = le32(record), sum = 0;
	unsigned int version = le16(record + 4), count = le16(record + 6), i;

	printf("magic 0x%08x version %u count %u\n", (unsigned int)magic, version, count);
	if (magic != 0x50534957 || version != 2 || count != 3) {
		printf("FAIL: bad header (want magic 0x50534957 version 2 count 3)\n");
		return 1;
	}
	for (i = 0; i < count; i++)
		sum += le32(record + 8 + 4 * i);
	printf("sum %u\n", (unsigned int)sum);
	if (sum != 0x160) {
		printf("FAIL: sum %u, want %u\n", (unsigned int)sum, 0x160);
		return 1;
	}
	printf("PASS\n");
	return 0;
}
