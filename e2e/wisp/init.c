/*
 * PID 1 of wisp, the tiny test system: built static against the kernel's nolibc
 * (tools/include/nolibc), no C library, no other file in the initramfs.
 *
 * It prints a banner, a few checks (uname, CPU count, memory, a compute loop
 * with its time) and one result line, then powers the machine off:
 *
 *   WISP-BANNER wsh-pve wisp v1
 *   WISP-RESULT v=1 arch=... machine=... release=... cpus=N mem_kb=N
 *               uptime_ms=N loops=N crc=0x........ loop_ms=N status=ok
 *
 * (one line). run.py parses it. The CRC is the same on every architecture
 * for the same loop count, so it also checks that the emulated CPU computed
 * the right thing. "loops=N" on the kernel command line (it reaches PID 1 as
 * an environment variable) sets the loop count.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/reboot.h>
#include <sys/syscall.h>
#include <sys/utsname.h>
#include <linux/reboot.h>
#include <linux/sysinfo.h>

#ifndef WISP_ARCH
#define WISP_ARCH "unknown"
#endif

#define DEFAULT_LOOPS 4096
#define BUF_WORDS 4096 /* 16 KiB */

static unsigned int buf[BUF_WORDS];
static unsigned int crc_table[256];

static void crc_init(void)
{
	unsigned int i, j, c;

	for (i = 0; i < 256; i++) {
		c = i;
		for (j = 0; j < 8; j++)
			c = (c & 1) ? 0xedb88320u ^ (c >> 1) : c >> 1;
		crc_table[i] = c;
	}
}

/*
 * One loop: refill the buffer from a xorshift32 stream that carries over
 * from the previous loop, then CRC-32 it byte by byte in little-endian order
 * (so big-endian sparc and little-endian x86 hash the same bytes).
 */
static unsigned int compute(unsigned int loops)
{
	unsigned int x = 2463534242u, crc = 0xffffffffu, l, i, w;

	for (l = 0; l < loops; l++) {
		for (i = 0; i < BUF_WORDS; i++) {
			x ^= x << 13;
			x ^= x >> 17;
			x ^= x << 5;
			buf[i] = x;
		}
		for (i = 0; i < BUF_WORDS; i++) {
			w = buf[i];
			crc = crc_table[(crc ^ w) & 0xff] ^ (crc >> 8);
			crc = crc_table[(crc ^ (w >> 8)) & 0xff] ^ (crc >> 8);
			crc = crc_table[(crc ^ (w >> 16)) & 0xff] ^ (crc >> 8);
			crc = crc_table[(crc ^ (w >> 24)) & 0xff] ^ (crc >> 8);
		}
	}
	return ~crc;
}

/* Milliseconds of a clock, without 64-bit division (no libgcc on sparc32). */
static unsigned long clock_ms(clockid_t id)
{
	struct timespec ts;

	if (clock_gettime(id, &ts))
		return 0;
	return (unsigned long)ts.tv_sec * 1000UL + (unsigned long)ts.tv_nsec / 1000000UL;
}

static int count_cpus(void)
{
	unsigned char mask[128];
	long n, i;
	unsigned int b;
	int cpus = 0;

	memset(mask, 0, sizeof(mask));
	n = syscall(__NR_sched_getaffinity, 0, sizeof(mask), mask);
	if (n <= 0)
		return -1;
	/* bit by bit: __builtin_popcount needs libgcc on sparc32, which -m32 doesn't have here */
	for (i = 0; i < n; i++)
		for (b = mask[i]; b; b >>= 1)
			cpus += b & 1;
	return cpus;
}

static unsigned long mem_kb(void)
{
	struct sysinfo si;

	memset(&si, 0, sizeof(si));
	if (syscall(__NR_sysinfo, &si))
		return 0;
	/* totalram is in units of mem_unit bytes */
	if (si.mem_unit >= 1024)
		return si.totalram * (si.mem_unit / 1024);
	return si.totalram / (1024 / (si.mem_unit ? si.mem_unit : 1));
}

static unsigned int parse_loops(char **envp)
{
	unsigned int n = 0;
	const char *p;

	for (; envp && *envp; envp++) {
		if (strncmp(*envp, "loops=", 6) != 0)
			continue;
		for (p = *envp + 6; *p >= '0' && *p <= '9'; p++)
			n = n * 10 + (unsigned int)(*p - '0');
	}
	return n ? n : DEFAULT_LOOPS;
}

int main(int argc, char **argv, char **envp)
{
	struct utsname u;
	unsigned long up, t0, t1;
	unsigned int loops, crc;
	int cpus;

	(void)argc;
	(void)argv;
	up = clock_ms(CLOCK_BOOTTIME);
	printf("WISP-BANNER wsh-pve wisp v1\n");

	memset(&u, 0, sizeof(u));
	uname(&u);
	cpus = count_cpus();
	loops = parse_loops(envp);
	printf("WISP-INFO uname: %s %s %s\n", u.sysname, u.release, u.machine);
	printf("WISP-INFO cpus: %d memory: %lu kB pid: %d\n", cpus, mem_kb(), getpid());

	crc_init();
	t0 = clock_ms(CLOCK_MONOTONIC);
	crc = compute(loops);
	t1 = clock_ms(CLOCK_MONOTONIC);

	printf("WISP-RESULT v=1 arch=%s machine=%s release=%s cpus=%d mem_kb=%lu uptime_ms=%lu "
	       "loops=%u crc=0x%08x loop_ms=%lu status=%s\n",
	       WISP_ARCH, u.machine, u.release, cpus, mem_kb(), up, loops, crc, t1 - t0,
	       getpid() == 1 ? "ok" : "notpid1");

	if (getpid() != 1)
		return 0;
	reboot(LINUX_REBOOT_CMD_POWER_OFF);
	/* still here: power-off is not wired up on this machine */
	printf("WISP-POWEROFF-FAILED\n");
	for (;;)
		sleep(3600);
}
