/*
 * PID 1 of wisp-netbsd, the NetBSD sibling of wisp (e2e/wisp): a static program
 * against NetBSD's own libc, the only program on the kernel's memory-disk root.
 *
 * It prints wisp's batch markers, so the runner parses its result line with
 * wisp's own run.py code:
 *
 *   WISP-BANNER wsh-pve wisp-netbsd v1
 *   WISP-INFO uname: NetBSD 11.1 sparc
 *   WISP-INFO cpus: 1 memory: 131072 kB pid: 1
 *   WISP-CHECK name=clock ok=1 ...
 *   WISP-CHECK name=file ok=1 ...
 *   WISP-RESULT v=1 arch=... machine=... release=... cpus=N mem_kb=N
 *               uptime_ms=N loops=N crc=0x........ loop_ms=N status=ok
 *
 * (the result is one line), then halts and powers the machine off with
 * reboot(RB_HALT | RB_POWERDOWN). If that returns, it prints
 * WISP-POWEROFF-FAILED. status is "ok" only when both checks passed and it
 * runs as PID 1.
 *
 * The compute loop is wisp's (init.c, compute()): the same CRC for the same
 * loop count on every architecture. NetBSD hands init no kernel command line,
 * so the loop count is always 4096.
 *
 * The same file builds on a Linux host with glibc ("cc -o init-host init.c"),
 * where it is not PID 1: it then runs its checks in the current directory and
 * exits (tests/test_init.py).
 */
#include <sys/param.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#ifdef __NetBSD__
#include <sys/sysctl.h>
#include <ufs/ufs/ufsmount.h>
#endif
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#ifndef WISP_ARCH
#define WISP_ARCH "unknown"
#endif

#define LOOPS 4096
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

/* wisp's compute loop: xorshift32 into the buffer, CRC-32 over it in little-endian byte order. */
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

/* Milliseconds of a clock. On NetBSD CLOCK_MONOTONIC counts from boot. */
static unsigned long clock_ms(clockid_t id)
{
	struct timespec ts;

	if (clock_gettime(id, &ts))
		return 0;
	return (unsigned long)ts.tv_sec * 1000UL + (unsigned long)ts.tv_nsec / 1000000UL;
}

static int count_cpus(void)
{
#ifdef __NetBSD__
	int mib[2] = { CTL_HW, HW_NCPU }, n = 0;
	size_t len = sizeof(n);

	if (sysctl(mib, 2, &n, &len, NULL, 0))
		return -1;
	return n;
#else
	return (int)sysconf(_SC_NPROCESSORS_ONLN);
#endif
}

static unsigned long mem_kb(void)
{
#ifdef __NetBSD__
	int mib[2] = { CTL_HW, HW_PHYSMEM64 };
	uint64_t mem = 0;
	size_t len = sizeof(mem);

	if (sysctl(mib, 2, &mem, &len, NULL, 0))
		return 0;
	return (unsigned long)(mem >> 10);
#else
	return (unsigned long)sysconf(_SC_PHYS_PAGES) * (unsigned long)(sysconf(_SC_PAGESIZE) / 1024);
#endif
}

/*
 * The clock check: a 200 ms nanosleep must take 150-2000 ms on CLOCK_MONOTONIC and move
 * CLOCK_REALTIME by about as much (the guest's timer interrupt and its clock source agree).
 */
static int check_clock(void)
{
	struct timespec req = { 0, 200000000L };
	unsigned long m0, m1, r0, r1, dm, dr;
	int ok;

	m0 = clock_ms(CLOCK_MONOTONIC);
	r0 = clock_ms(CLOCK_REALTIME);
	while (nanosleep(&req, &req) && errno == EINTR)
		;
	m1 = clock_ms(CLOCK_MONOTONIC);
	r1 = clock_ms(CLOCK_REALTIME);
	dm = m1 - m0;
	dr = r1 - r0;
	ok = dm >= 150 && dm <= 2000 && dr + 100 >= dm && dr <= dm + 100;
	printf("WISP-CHECK name=clock ok=%d sleep_ms=200 mono_ms=%lu real_ms=%lu\n", ok, dm, dr);
	return ok;
}

/*
 * The file check: remount the memory-disk root read-write, write 64 KiB of a pattern to a
 * file, read it back, compare and remove it. On the host, in the current directory.
 */
static int check_file(void)
{
	static unsigned char wbuf[65536], rbuf[65536];
	const char *path = "wisp-file-check";
	unsigned int x = 12345u, i;
	int fd, ok = 0, remount = 0;
	ssize_t n;

#ifdef __NetBSD__
	if (getpid() == 1) {
		struct ufs_args args;

		memset(&args, 0, sizeof(args));
		args.fspec = NULL;
		if (mount(MOUNT_FFS, "/", MNT_UPDATE, &args, sizeof(args)) == 0) {
			remount = 1;
		} else {
			args.fspec = "/dev/md0a";
			remount = mount(MOUNT_FFS, "/", MNT_UPDATE, &args, sizeof(args)) == 0 ? 2 : -errno;
		}
		path = "/wisp-file-check";
	}
#endif
	for (i = 0; i < sizeof(wbuf); i++) {
		x ^= x << 13;
		x ^= x >> 17;
		x ^= x << 5;
		wbuf[i] = (unsigned char)x;
	}
	fd = open(path, O_RDWR | O_CREAT | O_TRUNC, 0644);
	if (fd >= 0) {
		n = write(fd, wbuf, sizeof(wbuf));
		if (n == (ssize_t)sizeof(wbuf) && fsync(fd) == 0 && lseek(fd, 0, SEEK_SET) == 0) {
			n = read(fd, rbuf, sizeof(rbuf));
			ok = n == (ssize_t)sizeof(rbuf) && memcmp(wbuf, rbuf, sizeof(rbuf)) == 0;
		}
		close(fd);
		if (unlink(path))
			ok = 0;
	}
	printf("WISP-CHECK name=file ok=%d bytes=%u remount=%d errno=%d\n", ok,
	       (unsigned int)sizeof(wbuf), remount, ok ? 0 : errno);
	return ok;
}

/* PID 1 starts without open files: the console becomes stdin, stdout and stderr. */
static void console(void)
{
	int fd;

	if (getpid() != 1)
		return;
	fd = open("/dev/console", O_RDWR);
	if (fd < 0)
		return;
	dup2(fd, 0);
	dup2(fd, 1);
	dup2(fd, 2);
	if (fd > 2)
		close(fd);
}

static void power_off(void)
{
	fflush(stdout);
	if (getpid() != 1)
		exit(0);
#ifdef __NetBSD__
	reboot(RB_HALT | RB_POWERDOWN, NULL);
#endif
	printf("WISP-POWEROFF-FAILED\n");
	fflush(stdout);
	for (;;)
		sleep(3600);
}

int main(void)
{
	struct utsname u;
	unsigned long up, t0, t1;
	unsigned int crc;
	int cpus, ok;

	up = clock_ms(CLOCK_MONOTONIC);
	console();
	setvbuf(stdout, NULL, _IOLBF, 0);
	printf("WISP-BANNER wsh-pve wisp-netbsd v1\n");

	memset(&u, 0, sizeof(u));
	uname(&u);
	cpus = count_cpus();
	crc_init();
	printf("WISP-INFO uname: %s %s %s\n", u.sysname, u.release, u.machine);
	printf("WISP-INFO cpus: %d memory: %lu kB pid: %d\n", cpus, mem_kb(), (int)getpid());

	ok = check_clock();
	ok &= check_file();

	t0 = clock_ms(CLOCK_MONOTONIC);
	crc = compute(LOOPS);
	t1 = clock_ms(CLOCK_MONOTONIC);

	printf("WISP-RESULT v=1 arch=%s machine=%s release=%s cpus=%d mem_kb=%lu uptime_ms=%lu "
	       "loops=%u crc=0x%08x loop_ms=%lu status=%s\n",
	       WISP_ARCH, u.machine, u.release, cpus, mem_kb(), up, LOOPS, crc, t1 - t0,
	       getpid() != 1 ? "notpid1" : ok ? "ok" : "checkfailed");
	power_off();
	return 0;
}
