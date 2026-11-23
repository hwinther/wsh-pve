/*
 * PID 1 of wisp, the tiny test system: built static against the kernel's nolibc
 * (tools/include/nolibc), no C library, no other file in the initramfs.
 *
 * Batch mode (the default) prints a banner, a few checks (uname, CPU count,
 * memory, a compute loop with its time) and one result line, then powers the
 * machine off:
 *
 *   WISP-BANNER wsh-pve wisp v1
 *   WISP-RESULT v=1 arch=... machine=... release=... cpus=N mem_kb=N
 *               uptime_ms=N loops=N crc=0x........ loop_ms=N status=ok
 *
 * (one line). run.py parses it. The CRC is the same on every architecture
 * for the same loop count, so it also checks that the emulated CPU computed
 * the right thing. "loops=N" on the kernel command line (it reaches PID 1 as
 * an environment variable) sets the loop count.
 *
 * "wisp=shell" on the kernel command line starts a small interactive shell on
 * the console instead (help, info, bench, crc, mandel, banner, clear,
 * poweroff, reboot). The console stays in the kernel's canonical mode: the
 * line discipline echoes and edits the line (Backspace, Ctrl-U, Ctrl-W), and
 * the shell also drops ^H and arrow-key escape sequences from what it reads.
 *
 * Tier 2, each part optional and set on the kernel command line (it reaches
 * PID 1 as environment variables, like loops=): wisp_disk=sda,vda writes a
 * pattern to raw block devices and reads it back, wisp_net=eth0 gives the
 * interface 10.0.2.15 and sends ICMP echoes to QEMU's user-mode network at
 * 10.0.2.2, wisp_smp=1 runs the compute loop on every CPU. Each prints a line
 * after the result line (WISP-DISK, WISP-NET, WISP-SMP) that run.py --tier2
 * checks; the shell has them as disk, net and smp. Without them the output
 * is unchanged.
 *
 * "wisp=test" runs /test instead, a program that an external initramfs (QEMU's -initrd) adds
 * next to this one, with PID 1's arguments, then prints "WISP-TEST v=1 exit=N signal=N ms=N"
 * and powers off: the wisp-test GitHub Action (.github/actions/wisp-test).
 * "wisp=run" also announces startup and uses WISP-RUN for the service lifecycle.
 *
 * The same file builds against glibc on the host ("cc -o init-host init.c"),
 * where it is not PID 1: tests/test_shell.py drives that build.
 */
#ifdef __sparc__
/* nolibc's _start out of the way, see below */
#define _start wisp_nolibc_start
#endif
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/syscall.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <linux/fb.h>
/* nolibc uses 64-bit time_t on 32-bit targets. Select the evdev wire layout. */
#if defined(NOLIBC) && __SIZEOF_LONG__ == 4
#define __USE_TIME_BITS64
#endif
#include <linux/input.h>
#include <linux/ioctl.h>
#include <linux/reboot.h>
#include <linux/sysinfo.h>

#ifndef WISP_ARCH
#define WISP_ARCH "unknown"
#endif

#ifdef __sparc__
#undef _start
#endif
#if defined(NOLIBC) && defined(__sparc__)
/*
 * nolibc's _start for sparc is a C function holding the asm that passes the
 * address of argc to _start_c. gcc has no "naked" functions on sparc and puts
 * a "save %sp, -96, %sp" in front of it, so _start_c read argc, argv and the
 * environment 96 bytes too low: argc 0 and no loops= or wisp= from the kernel
 * command line. This _start is the same asm without a prologue (nolibc's is
 * renamed above).
 */
__asm__(".pushsection .text\n"
	".global _start\n"
	".type _start, #function\n"
	"_start:\n"
#ifdef __arch64__
	"	add %sp, 128 + 2047, %o0\n"
#else
	"	add %sp, 64, %o0\n"
#endif
	"	b,a _start_c\n"
	".size _start, . - _start\n"
	".popsection\n");
#endif

#define DEFAULT_LOOPS 4096
#define MAX_LOOPS 1000000
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

/* Total (or free) memory in kB. */
static unsigned long mem_kb(int want_free)
{
	struct sysinfo si;
	unsigned long v;

	memset(&si, 0, sizeof(si));
	if (syscall(__NR_sysinfo, &si))
		return 0;
	v = want_free ? si.freeram : si.totalram;
	/* totalram is in units of mem_unit bytes */
	if (si.mem_unit >= 1024)
		return v * (si.mem_unit / 1024);
	return v / (1024 / (si.mem_unit ? si.mem_unit : 1));
}

/* A decimal number at s, 0 if there is none. */
static unsigned int parse_uint(const char *s)
{
	unsigned int n = 0;

	for (; *s >= '0' && *s <= '9'; s++)
		n = n * 10 + (unsigned int)(*s - '0');
	return n;
}

/* The value of "key=" in the environment, or NULL. */
static const char *env(char **envp, const char *key)
{
	size_t len = strlen(key);

	for (; envp && *envp; envp++)
		if (strncmp(*envp, key, len) == 0 && (*envp)[len] == '=')
			return *envp + len + 1;
	return NULL;
}

static unsigned int parse_loops(char **envp)
{
	const char *v = env(envp, "loops");
	unsigned int n = v ? parse_uint(v) : 0;

	return n ? n : DEFAULT_LOOPS;
}

static void power(int cmd)
{
	if (getpid() != 1)
		exit(0);
	reboot(cmd);
	/* still here: power-off (or restart) is not wired up on this machine */
	printf("WISP-POWEROFF-FAILED\n");
	for (;;)
		sleep(3600);
}

/* Tier 2: disk, network, SMP ------------------------------------------------------------------ */

/* Microseconds of CLOCK_MONOTONIC; wraps after 71 minutes on 32-bit, fine for differences. */
static unsigned long clock_us(void)
{
	struct timespec ts;

	if (clock_gettime(CLOCK_MONOTONIC, &ts))
		return 0;
	return (unsigned long)ts.tv_sec * 1000000UL + (unsigned long)ts.tv_nsec / 1000UL;
}

/* The next word of a xorshift32 stream (the compute loop's generator). */
static unsigned int xorshift(unsigned int *x)
{
	*x ^= *x << 13;
	*x ^= *x >> 17;
	*x ^= *x << 5;
	return *x;
}

static void put_le32(unsigned char *p, unsigned int w)
{
	p[0] = w;
	p[1] = w >> 8;
	p[2] = w >> 16;
	p[3] = w >> 24;
}

static unsigned int get_le32(const unsigned char *p)
{
	return p[0] | p[1] << 8 | p[2] << 16 | (unsigned int)p[3] << 24;
}

static unsigned int crc_bytes(unsigned int crc, const unsigned char *p, unsigned long n)
{
	while (n--)
		crc = crc_table[(crc ^ *p++) & 0xff] ^ (crc >> 8);
	return crc;
}

/*
 * The disk check, on a raw block device (no file system). run.py fills the
 * image with the host pattern (a xorshift32 stream from DISK_HOST_SEED plus
 * the disk's index, stored little-endian) before the boot. PID 1 reads up to
 * DISK_READ bytes and compares them with that stream, writes DISK_SPAN bytes
 * of its own pattern (DISK_GUEST_SEED plus the index) at offset DISK_SPAN,
 * fsyncs, drops the device's page cache (BLKFLSBUF, then close and open
 * again), reads them back and compares. After QEMU exits, run.py checks the
 * whole image: the guest pattern at DISK_SPAN, the host pattern elsewhere.
 */
#define DISK_HOST_SEED 0x686f7374u  /* "host" */
#define DISK_GUEST_SEED 0x67756573u /* "gues" */
#define DISK_SPAN (1024UL * 1024UL)
#define DISK_READ (4UL * DISK_SPAN)
#define DISK_CHUNK (BUF_WORDS * 4UL)
#define WISP_BLKGETSIZE64 _IOR(0x12, 114, size_t)
#define WISP_BLKFLSBUF _IO(0x12, 97)

static char **wisp_envp;

/* Reads (or with wr set, writes) len bytes at off in chunks through buf[], checking (or
 * generating) the xorshift32 stream from seed; returns the words that differed (-1 on an I/O
 * error) and the CRC-32 of what was read or written in *crc. */
static long disk_pass(int fd, unsigned long off, unsigned long len, unsigned int seed, int wr,
		      unsigned int *crc)
{
	unsigned char *p = (unsigned char *)buf;
	unsigned long done, i;
	unsigned int x = seed, c = 0xffffffffu;
	long bad = 0;

	if (lseek(fd, off, SEEK_SET) < 0)
		return -1;
	for (done = 0; done < len; done += DISK_CHUNK) {
		if (wr) {
			for (i = 0; i < DISK_CHUNK; i += 4)
				put_le32(p + i, xorshift(&x));
			if (write(fd, p, DISK_CHUNK) != (ssize_t)DISK_CHUNK)
				return -1;
		} else {
			if (read(fd, p, DISK_CHUNK) != (ssize_t)DISK_CHUNK)
				return -1;
			for (i = 0; i < DISK_CHUNK; i += 4)
				bad += get_le32(p + i) != xorshift(&x);
		}
		c = crc_bytes(c, p, DISK_CHUNK);
	}
	*crc = ~c;
	return bad;
}

/* Waits up to 10 s for a device node to appear (a disk is scanned asynchronously). */
static int open_wait(const char *path, int flags)
{
	int fd, i;

	for (i = 0; i < 200; i++) {
		fd = open(path, flags);
		if (fd >= 0 || getpid() != 1)
			return fd;
		usleep(50000);
	}
	return -1;
}

static void mount_dev(void)
{
	static int done;

	/* devtmpfs over the initramfs's /dev (/dev/console is in it too) */
	if (!done && getpid() == 1)
		mount("devtmpfs", "/dev", "devtmpfs", 0, NULL);
	done = 1;
}

/* One disk: "sda" is /dev/sda, a name with a '/' is a path (a file, on the host). */
static int disk_check(const char *name, unsigned int index, const char *prefix)
{
	char path[64];
	unsigned long long size = 0;
	unsigned long t0, t1, t2, t3, rlen;
	unsigned int rcrc = 0, wcrc = 0, vcrc = 0;
	long rbad = -1, vbad = -1;
	const char *status = "ok";
	int fd;

	mount_dev();
	if (strchr(name, '/'))
		snprintf(path, sizeof(path), "%s", name);
	else
		snprintf(path, sizeof(path), "/dev/%s", name);
	t0 = t1 = t2 = t3 = clock_ms(CLOCK_MONOTONIC);
	fd = open_wait(path, O_RDWR);
	if (fd < 0) {
		status = "no-device";
		goto out;
	}
	if (ioctl(fd, WISP_BLKGETSIZE64, &size) != 0)
		size = (unsigned long long)lseek(fd, 0, SEEK_END); /* a file */
	if (size < 2 * DISK_SPAN) {
		status = "too-small";
		goto out_close;
	}
	rlen = size < DISK_READ ? DISK_SPAN * 2 : DISK_READ;
	t0 = clock_ms(CLOCK_MONOTONIC);
	rbad = disk_pass(fd, 0, rlen, DISK_HOST_SEED + index, 0, &rcrc);
	t1 = clock_ms(CLOCK_MONOTONIC);
	if (rbad < 0) {
		status = "read-error";
		goto out_close;
	}
	if (disk_pass(fd, DISK_SPAN, DISK_SPAN, DISK_GUEST_SEED + index, 1, &wcrc) < 0 ||
	    fsync(fd) != 0) {
		status = "write-error";
		goto out_close;
	}
	/* from the device, not from the page cache */
	ioctl(fd, WISP_BLKFLSBUF, 0);
	close(fd);
	t2 = clock_ms(CLOCK_MONOTONIC);
	fd = open(path, O_RDONLY);
	if (fd < 0) {
		status = "reopen-failed";
		goto out;
	}
	vbad = disk_pass(fd, DISK_SPAN, DISK_SPAN, DISK_GUEST_SEED + index, 0, &vcrc);
	t3 = clock_ms(CLOCK_MONOTONIC);
	if (vbad < 0)
		status = "verify-error";
	else if (rbad)
		status = "read-mismatch";
	else if (vbad)
		status = "verify-mismatch";
out_close:
	close(fd);
out:
	printf("%sWISP-DISK v=1 dev=%s index=%u size_kb=%lu read_kb=%lu read_crc=0x%08x read_bad=%ld "
	       "read_ms=%lu write_kb=%lu write_crc=0x%08x write_ms=%lu verify_crc=0x%08x "
	       "verify_bad=%ld verify_ms=%lu status=%s\n",
	       prefix, name, index, (unsigned long)(size >> 10), rbad < 0 ? 0 : rlen >> 10, rcrc,
	       rbad, t1 - t0, DISK_SPAN >> 10, wcrc, t2 - t1, vcrc, vbad, t3 - t2, status);
	return strcmp(status, "ok") == 0;
}

/* Each comma- or space-separated name of list in turn. */
static void disks(const char *list, const char *prefix)
{
	char name[32];
	unsigned int index = 0, n;

	while (*list) {
		for (n = 0; *list && *list != ',' && *list != ' '; list++)
			if (n < sizeof(name) - 1)
				name[n++] = *list;
		name[n] = '\0';
		if (*list)
			list++;
		if (n)
			disk_check(name, index++, prefix);
	}
}

/*
 * The network check, on QEMU's user-mode network (slirp), which answers
 * ARP and ICMP echo requests for its gateway address 10.0.2.2 itself,
 * without the host's network or a DNS server. The kernel has no IP stack
 * (packet sockets only, which keeps it smaller): PID 1 brings the interface
 * up and builds the frames itself, as 10.0.2.15 (no DHCP). An ARP request
 * for 10.0.2.2 goes out every 200 ms until slirp answers (the link may come
 * up late); then NET_ECHOES ICMP echo requests with a NET_PAYLOAD-byte
 * pattern measure the round trip, and each reply must carry the payload
 * sent, with good IP and ICMP checksums. ARP requests for 10.0.2.15 are
 * answered on the way.
 */
#define NET_PAYLOAD 1400
#define NET_ECHOES 8
#define NET_TRIES 50
#define NET_ID 0x5749 /* "WI" */
#define WISP_AF_PACKET 17
#define WISP_SOCK_RAW 3
#define WISP_ETH_P_ALL 0x0003
#define WISP_SIOCGIFFLAGS 0x8913
#define WISP_SIOCSIFFLAGS 0x8914
#define WISP_SIOCGIFHWADDR 0x8927
#define WISP_SIOCGIFINDEX 0x8933
#define WISP_IFF_UP 0x1

/* struct ifreq: the name, then a union of at most 24 bytes */
struct wisp_ifreq {
	char name[16];
	union {
		struct {
			unsigned short family;
			unsigned char data[14];
		} hw;
		short flags;
		int index;
		char pad[24];
	} u;
};

struct wisp_sockaddr_ll {
	unsigned short family;
	unsigned short protocol; /* network byte order */
	int ifindex;
	unsigned short hatype;
	unsigned char pkttype, halen, addr[8];
};

static const unsigned char net_me[4] = { 10, 0, 2, 15 }, net_gw[4] = { 10, 0, 2, 2 };
static const unsigned char net_bcast[6] = { 255, 255, 255, 255, 255, 255 };

static unsigned short htons16(unsigned short v)
{
#if __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
	return v;
#else
	return (unsigned short)(v << 8 | v >> 8);
#endif
}

static void put_be16(unsigned char *p, unsigned int v)
{
	p[0] = v >> 8;
	p[1] = v;
}

static unsigned int get_be16(const unsigned char *p)
{
	return p[0] << 8 | p[1];
}

static unsigned int ip_checksum(const unsigned char *p, int n)
{
	unsigned int sum = 0;
	int i;

	for (i = 0; i + 1 < n; i += 2)
		sum += p[i] << 8 | p[i + 1];
	if (n & 1)
		sum += p[n - 1] << 8;
	while (sum >> 16)
		sum = (sum & 0xffff) + (sum >> 16);
	return ~sum & 0xffff;
}

/* An ARP frame (op 1 request, 2 reply) from us to tha/tpa. */
static int arp_frame(unsigned char *f, const unsigned char *mac, int op, const unsigned char *tha,
		     const unsigned char *tpa)
{
	memset(f, 0, 60);
	memcpy(f, op == 1 ? net_bcast : tha, 6);
	memcpy(f + 6, mac, 6);
	put_be16(f + 12, 0x0806);
	put_be16(f + 14, 1);      /* Ethernet */
	put_be16(f + 16, 0x0800); /* IPv4 */
	f[18] = 6;
	f[19] = 4;
	put_be16(f + 20, op);
	memcpy(f + 22, mac, 6);
	memcpy(f + 28, net_me, 4);
	if (op == 2)
		memcpy(f + 32, tha, 6);
	memcpy(f + 38, tpa, 4);
	return 60; /* padded to the Ethernet minimum */
}

/* An ICMP echo request frame with sequence seq to gw. */
static int echo_frame(unsigned char *f, const unsigned char *mac, const unsigned char *gw,
		      unsigned int seq)
{
	unsigned char *ip = f + 14, *icmp = ip + 20;
	unsigned int x = DISK_GUEST_SEED + seq, i;

	memcpy(f, gw, 6);
	memcpy(f + 6, mac, 6);
	put_be16(f + 12, 0x0800);
	memset(ip, 0, 28);
	ip[0] = 0x45;
	put_be16(ip + 2, 20 + 8 + NET_PAYLOAD);
	put_be16(ip + 4, seq);
	ip[8] = 64; /* TTL */
	ip[9] = 1;  /* ICMP */
	memcpy(ip + 12, net_me, 4);
	memcpy(ip + 16, net_gw, 4);
	put_be16(ip + 10, ip_checksum(ip, 20));
	icmp[0] = 8; /* echo request */
	put_be16(icmp + 4, NET_ID);
	put_be16(icmp + 6, seq);
	for (i = 0; i < NET_PAYLOAD; i += 4)
		put_le32(icmp + 8 + i, xorshift(&x));
	put_be16(icmp + 2, ip_checksum(icmp, 8 + NET_PAYLOAD));
	return 14 + 20 + 8 + NET_PAYLOAD;
}

/*
 * Sends frame f (len bytes), then reads frames for up to wait_ms: answers ARP
 * requests for 10.0.2.15, and returns 1 when the reply it waits for came (an
 * ARP reply from 10.0.2.2, its MAC into gw; or with seq, that echo reply),
 * -1 on an echo reply with a bad payload or checksum, 0 on none. *us is the
 * time from sending to the reply.
 */
static int net_exchange(int fd, const unsigned char *mac, unsigned char *gw, unsigned char *f,
			int len, unsigned int seq, int wait_ms, unsigned long *us)
{
	unsigned char *in = (unsigned char *)buf + 4096, *ip = in + 14, *icmp;
	unsigned char reply[60];
	struct pollfd pfd;
	unsigned long t0, left;
	long n;
	int hl;

	t0 = clock_us();
	if (write(fd, f, len) != len)
		return 0;
	for (;;) {
		left = (unsigned long)wait_ms * 1000UL - (clock_us() - t0);
		if ((long)left <= 0)
			return 0;
		pfd.fd = fd;
		pfd.events = POLLIN;
		pfd.revents = 0;
		if (poll(&pfd, 1, (int)(left / 1000UL) + 1) <= 0)
			return 0;
		n = read(fd, in, 4096);
		if (n < 42 || memcmp(in + 6, mac, 6) == 0) /* short, or one of ours going out */
			continue;
		if (get_be16(in + 12) == 0x0806 && memcmp(in + 38, net_me, 4) == 0) {
			if (get_be16(in + 20) == 1) { /* who has 10.0.2.15: we do */
				if (write(fd, reply, arp_frame(reply, mac, 2, in + 22, in + 28)) < 0)
					return 0;
			} else if (!seq && get_be16(in + 20) == 2 &&
				   memcmp(in + 28, net_gw, 4) == 0) {
				memcpy(gw, in + 22, 6);
				*us = clock_us() - t0;
				return 1;
			}
			continue;
		}
		if (!seq || get_be16(in + 12) != 0x0800 || memcmp(in, mac, 6) != 0 ||
		    (ip[0] >> 4) != 4 || ip[9] != 1 || memcmp(ip + 12, net_gw, 4) != 0)
			continue;
		hl = (ip[0] & 0xf) * 4;
		icmp = ip + hl;
		if (n < 14 + hl + 8 || icmp[0] != 0 || get_be16(icmp + 4) != NET_ID ||
		    get_be16(icmp + 6) != seq)
			continue;
		*us = clock_us() - t0;
		if (get_be16(ip + 2) != (unsigned int)(hl + 8 + NET_PAYLOAD) ||
		    n < 14 + hl + 8 + NET_PAYLOAD || ip_checksum(ip, hl) != 0 ||
		    ip_checksum(icmp, 8 + NET_PAYLOAD) != 0 ||
		    memcmp(icmp + 8, f + 14 + 20 + 8, NET_PAYLOAD) != 0)
			return -1;
		return 1;
	}
}

static int net_check(const char *ifname, const char *prefix)
{
	struct wisp_sockaddr_ll ll;
	struct wisp_ifreq ifr;
	unsigned char *f = (unsigned char *)buf, mac[6], gw[6];
	unsigned long t0, arp_ms = 0, us = 0, rmin = 0, rmax = 0, rsum = 0;
	unsigned int seq, tries = 0, echoes = 0, bad = 0;
	const char *status = "ok";
	char macs[18] = "-", gws[18] = "-";
	int fd, r = 0;

	t0 = clock_ms(CLOCK_MONOTONIC);
	fd = (int)syscall(__NR_socket, WISP_AF_PACKET, WISP_SOCK_RAW, htons16(WISP_ETH_P_ALL));
	if (fd < 0) {
		status = "no-socket";
		goto out;
	}
	memset(&ifr, 0, sizeof(ifr));
	snprintf(ifr.name, sizeof(ifr.name), "%s", ifname);
	if (ioctl(fd, WISP_SIOCGIFHWADDR, &ifr) != 0) {
		status = "no-interface";
		goto out;
	}
	memcpy(mac, ifr.u.hw.data, 6);
	snprintf(macs, sizeof(macs), "%02x:%02x:%02x:%02x:%02x:%02x", mac[0], mac[1], mac[2],
		 mac[3], mac[4], mac[5]);
	if (ioctl(fd, WISP_SIOCGIFFLAGS, &ifr) == 0) {
		ifr.u.flags |= WISP_IFF_UP;
		ioctl(fd, WISP_SIOCSIFFLAGS, &ifr);
	}
	memset(&ll, 0, sizeof(ll));
	if (ioctl(fd, WISP_SIOCGIFINDEX, &ifr) == 0)
		ll.ifindex = ifr.u.index;
	ll.family = WISP_AF_PACKET;
	ll.protocol = htons16(WISP_ETH_P_ALL);
	if (syscall(__NR_bind, fd, &ll, sizeof(ll)) != 0) {
		status = "bind-failed";
		goto out;
	}
	while (tries < NET_TRIES && r <= 0) {
		tries++;
		r = net_exchange(fd, mac, gw, f, arp_frame(f, mac, 1, net_bcast, net_gw), 0, 200,
				 &us);
	}
	arp_ms = clock_ms(CLOCK_MONOTONIC) - t0;
	if (r <= 0) {
		status = "no-arp-reply";
		goto out;
	}
	snprintf(gws, sizeof(gws), "%02x:%02x:%02x:%02x:%02x:%02x", gw[0], gw[1], gw[2], gw[3],
		 gw[4], gw[5]);
	for (seq = 1; seq <= NET_ECHOES; seq++) {
		r = net_exchange(fd, mac, gw, f, echo_frame(f, mac, gw, seq), seq, 2000, &us);
		if (r == 0) {
			status = "lost";
			break;
		}
		if (r < 0)
			bad++;
		if (!echoes || us < rmin)
			rmin = us;
		if (us > rmax)
			rmax = us;
		rsum += us;
		echoes++;
	}
	if (bad)
		status = "bad-reply";
out:
	if (fd >= 0)
		close(fd);
	printf("%sWISP-NET v=1 if=%s mac=%s addr=10.0.2.15 peer=10.0.2.2 peer_mac=%s arp_tries=%u "
	       "arp_ms=%lu payload=%d echoes=%u rtt_min_us=%lu rtt_avg_us=%lu rtt_max_us=%lu "
	       "status=%s\n",
	       prefix, ifname, macs, gws, tries, arp_ms, NET_PAYLOAD, echoes, rmin,
	       echoes ? rsum / echoes : 0, rmax, status);
	return strcmp(status, "ok") == 0;
}

/*
 * The SMP check: one child per CPU in PID 1's affinity mask, each pinned to
 * its CPU with sched_setaffinity (and checked with getcpu where there is
 * one), runs the compute loop and sends its CRC and time through a pipe.
 * All children run at once; every CRC must be the same (run.py also checks
 * it against the model). fork is clone without CLONE_VM, so no futex is
 * needed (sparc32 SMP kernels have none).
 */
#define SMP_MAX 64
#define LONG_BITS (8 * (int)sizeof(unsigned long))

struct smp_result {
	int cpu, ran_on;
	unsigned int crc;
	unsigned long ms;
};

static int smp_check(unsigned int loops, const char *prefix)
{
	/* the kernel's CPU masks are arrays of unsigned long (bit 0 of word 0 is CPU 0) */
	unsigned long mask[1024 / LONG_BITS], one[1024 / LONG_BITS];
	int cpus[SMP_MAX], fds[SMP_MAX], n = 0, i, ok = 1, pinned = 1;
	struct smp_result res[SMP_MAX];
	unsigned long t0, t1;
	char list[SMP_MAX * 24], *l = list;
	int p[2];

	memset(mask, 0, sizeof(mask));
	if (syscall(__NR_sched_getaffinity, 0, sizeof(mask), mask) <= 0)
		return 0;
	for (i = 0; i < SMP_MAX; i++)
		if (mask[i / LONG_BITS] & (1UL << (i % LONG_BITS)))
			cpus[n++] = i;
	fflush(stdout);
	t0 = clock_ms(CLOCK_MONOTONIC);
	for (i = 0; i < n; i++) {
		fds[i] = -1;
		if (pipe(p) != 0)
			continue;
		if (fork() == 0) {
			struct smp_result r;
			unsigned long c0;

			close(p[0]);
			memset(&r, 0, sizeof(r));
			memset(one, 0, sizeof(one));
			one[cpus[i] / LONG_BITS] = 1UL << (cpus[i] % LONG_BITS);
			r.cpu = cpus[i];
			r.ran_on = -1;
			if (syscall(__NR_sched_setaffinity, 0, sizeof(one), one) == 0) {
#ifdef __NR_getcpu
				unsigned int cpu = ~0u;

				if (syscall(__NR_getcpu, &cpu, NULL, NULL) == 0)
					r.ran_on = (int)cpu;
#else
				r.ran_on = cpus[i];
#endif
			}
			c0 = clock_ms(CLOCK_MONOTONIC);
			r.crc = compute(loops);
			r.ms = clock_ms(CLOCK_MONOTONIC) - c0;
			if (write(p[1], &r, sizeof(r)) != (ssize_t)sizeof(r))
				_exit(1);
			_exit(0);
		}
		close(p[1]);
		fds[i] = p[0];
	}
	for (i = 0; i < n; i++) {
		memset(&res[i], 0, sizeof(res[i]));
		res[i].cpu = cpus[i];
		res[i].ran_on = -2;
		if (fds[i] < 0 || read(fds[i], &res[i], sizeof(res[i])) != (ssize_t)sizeof(res[i]))
			ok = 0;
		if (fds[i] >= 0)
			close(fds[i]);
	}
	while (wait(NULL) > 0)
		;
	t1 = clock_ms(CLOCK_MONOTONIC);
	*l = '\0';
	for (i = 0; i < n; i++) {
		if (res[i].crc != res[0].crc)
			ok = 0;
		if (res[i].ran_on != res[i].cpu)
			pinned = 0;
		l += snprintf(l, list + sizeof(list) - l, "%s%d:0x%08x:%lu", i ? "," : "", res[i].cpu,
			      res[i].crc, res[i].ms);
	}
	printf("%sWISP-SMP v=1 cpus=%d loops=%u crc=0x%08x wall_ms=%lu pinned=%s percpu=%s "
	       "status=%s\n",
	       prefix, n, loops, n ? res[0].crc : 0, t1 - t0, pinned ? "yes" : "no", list,
	       !ok ? "crc-mismatch" : !pinned ? "not-pinned" : "ok");
	return ok && pinned;
}

/* The interactive shell ----------------------------------------------------------------------- */

/*
 * The Mandelbrot set in 4.12 fixed point (4096 = 1.0) with 32-bit ints only:
 * while |z| <= 2, |x| and |y| stay below 6.5 after one more step, so x * y
 * stays below 2^31. shell.py's mandel_rows() models it (tests/test_shell.py).
 */
#define MANDEL_COLS 78
#define MANDEL_ROWS 20
#define MANDEL_ITER 32
#define MANDEL_X0 (-9216) /* x from -2.25 */
#define MANDEL_DX 158     /* to 0.72 in 78 columns */
#define MANDEL_DY 248     /* half a row: y from -1.15 to 1.15 in 20 rows */

static const char mandel_chars[] = " .:-=+*#%@";

static int mandel_count(int cx, int cy)
{
	int x = 0, y = 0, n;

	for (n = 0; n < MANDEL_ITER; n++) {
		int x2 = (x * x) >> 12;
		int y2 = (y * y) >> 12;

		if (x2 + y2 > 4 << 12)
			break;
		y = ((x * y) >> 11) + cy;
		x = x2 - y2 + cx;
	}
	return n;
}

static void mandel_row(int row, char *out)
{
	int col, cy = (2 * row - (MANDEL_ROWS - 1)) * MANDEL_DY;

	for (col = 0; col < MANDEL_COLS; col++) {
		int n = mandel_count(MANDEL_X0 + col * MANDEL_DX, cy);

		out[col] = n == MANDEL_ITER ? '@' : mandel_chars[n * 9 / MANDEL_ITER];
	}
	out[MANDEL_COLS] = '\0';
}

/*
 * endian: a small game about the thing wisp tests for. Each round shows a word's four bytes as
 * they sit in memory, low address first, and asks for the 32-bit value this machine's CPU reads
 * from them: on a big-endian CPU, the bytes shown read straight through; on a little-endian one,
 * the same bytes read the other way around (the byte-swap of the word). "endian <hex>" is a
 * guess; "endian" alone shows the round again without spending one. Three wrong guesses end the
 * game; a right one scores a point and deals another round. The words come from the same
 * xorshift32 stream the compute loop and the tier-2 checks use (xorshift(), above), seeded with
 * "endi", so a game is the same sequence of rounds every time; shell.py's endian_words() and
 * endian_answer(big_endian) model it for the tests.
 */
#define ENDIAN_SEED 0x656e6469u /* "endi" */
#define ENDIAN_LIVES 3

static struct {
	unsigned int x;    /* this game's xorshift32 state */
	unsigned int word; /* the current round's bytes, as one 32-bit value, high byte first */
	unsigned int score;
	int lives;
	int playing;
} eg;

/* 1 if this machine's CPU is big-endian: a known word's first byte (its lowest address) comes out
 * as its most significant, not its least. */
static int machine_is_big_endian(void)
{
	union {
		unsigned int w;
		unsigned char b[4];
	} u;

	u.w = 1;
	return u.b[0] == 0;
}

/*
 * The 32-bit value this machine's CPU reads from bytes b0..b3 as they'd sit in memory, lowest
 * address first: each byte is stored on its own, at the address a real word's byte would have,
 * then the whole word is read back in one load, so the CPU's own byte order decides the result
 * (not an order assumed in the arithmetic, as a shift-and-mask byte-swap would).
 */
static unsigned int bytes_to_word(unsigned char b0, unsigned char b1, unsigned char b2,
				  unsigned char b3)
{
	union {
		unsigned int w;
		unsigned char b[4];
	} u;

	u.b[0] = b0;
	u.b[1] = b1;
	u.b[2] = b2;
	u.b[3] = b3;
	return u.w;
}

/* The short line after a wrong guess, naming this machine's byte order. */
static const char *endian_explain(void)
{
	return machine_is_big_endian() ? "big-endian: the first byte is the most significant"
				       : "little-endian: the first byte is the least significant";
}

/* A hex number (an optional "0x" or "0X" first) at s; ~0u if s has no hex digit. */
static unsigned int parse_hex(const char *s)
{
	unsigned int n = 0;
	int any = 0, d;

	if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X'))
		s += 2;
	for (; *s; s++) {
		if (*s >= '0' && *s <= '9')
			d = *s - '0';
		else if (*s >= 'a' && *s <= 'f')
			d = *s - 'a' + 10;
		else if (*s >= 'A' && *s <= 'F')
			d = *s - 'A' + 10;
		else
			break;
		n = n * 16 + (unsigned int)d;
		any = 1;
	}
	return any ? n : ~0u;
}

static void endian_show(void)
{
	printf("  bytes %02x %02x %02x %02x\n", eg.word >> 24 & 0xff, eg.word >> 16 & 0xff,
	       eg.word >> 8 & 0xff, eg.word & 0xff);
}

/* Deals the next round (one more word off the stream) and shows it. */
static void endian_next(void)
{
	eg.word = xorshift(&eg.x);
	endian_show();
}

static void cmd_endian(const char *arg)
{
	unsigned int want;

	if (!eg.playing) {
		eg.x = ENDIAN_SEED;
		eg.score = 0;
		eg.lives = ENDIAN_LIVES;
		eg.playing = 1;
		printf("  this machine is %s-endian\n",
		       machine_is_big_endian() ? "big" : "little");
		printf("  bytes, low address first; type the 32-bit word this machine reads from\n"
		       "  them, in hex. endian <hex> to guess (wrong costs a life, %d to start);\n"
		       "  endian alone shows the round again.\n", ENDIAN_LIVES);
		endian_next();
		return;
	}
	if (!*arg) {
		endian_show();
		return;
	}
	want = bytes_to_word(eg.word >> 24 & 0xff, eg.word >> 16 & 0xff, eg.word >> 8 & 0xff,
			     eg.word & 0xff);
	if (parse_hex(arg) == want) {
		printf("  correct, 0x%08x. score %u\n", want, ++eg.score);
		endian_next();
		return;
	}
	if (--eg.lives > 0) {
		printf("  wrong, it was 0x%08x. %d lives left\n", want, eg.lives);
		printf("  %s\n", endian_explain());
		endian_next();
	} else {
		printf("  wrong, it was 0x%08x. game over, score %u\n", want, eg.score);
		printf("  %s\n", endian_explain());
		eg.playing = 0;
	}
}

static unsigned int sh_loops;

static void cmd_banner(const char *arg)
{
	struct utsname u;

	(void)arg;
	memset(&u, 0, sizeof(u));
	uname(&u);
	printf("\033[1;36m"
	       "            _\n"
	       " __      __(_) ___ _ __\n"
	       " \\ \\ /\\ / /| |/ __| '_ \\\n"
	       "  \\ V  V / | |\\__ \\ |_) |\n"
	       "   \\_/\\_/  |_||___/ .__/\n"
	       "                  |_|\033[0m   %s, Linux %s\n\n", WISP_ARCH, u.release);
}

static void cmd_help(const char *arg)
{
	(void)arg;
	printf("  help            this list\n"
	       "  info, uname     architecture, kernel, CPUs, memory, uptime\n"
	       "  bench           the CRC-32 compute loop (%u rounds) with its time\n"
	       "  crc <n>         the loop's checksum after n rounds\n"
	       "  fbtest          draw eight colour bars on /dev/fb0\n"
	       "  keytest         read keyboard presses until Esc or a 10-second timeout\n"
	       "  mandel fb       draw the Mandelbrot set on /dev/fb0\n"
	       "  mandel          the Mandelbrot set in fixed-point integer math\n"
	       "  endian          a byte-order guessing game\n"
	       "  disk [dev..]    write, sync and read back a pattern on a raw disk\n"
	       "  net [if]        ARP and ICMP echo to QEMU's user network at 10.0.2.2\n"
	       "  smp             the compute loop on every CPU at once\n"
	       "  banner          the logo\n"
	       "  clear           clear the screen\n"
	       "  poweroff        power the machine off\n"
	       "  reboot          restart the machine\n", sh_loops);
}

static void cmd_info(const char *arg)
{
	struct utsname u;
	unsigned long up = clock_ms(CLOCK_BOOTTIME);

	(void)arg;
	memset(&u, 0, sizeof(u));
	uname(&u);
	printf("  arch      %s (%s)\n"
	       "  kernel    %s %s %s\n"
	       "  cpus      %d\n"
	       "  memory    %lu kB, %lu kB free\n"
	       "  uptime    %lu.%03lu s\n"
	       "  pid       %d\n",
	       WISP_ARCH, u.machine, u.sysname, u.release, u.version, count_cpus(), mem_kb(0),
	       mem_kb(1), up / 1000, up % 1000, getpid());
}

/* Runs the loop, prints "crc32 0x... after N rounds (M KiB) in T ms"; returns the time. */
static unsigned long run_loop(unsigned int loops)
{
	unsigned long t0, t1;
	unsigned int crc;

	t0 = clock_ms(CLOCK_MONOTONIC);
	crc = compute(loops);
	t1 = clock_ms(CLOCK_MONOTONIC);
	printf("  crc32 0x%08x after %u rounds (%u KiB) in %lu ms\n", crc, loops, loops * 16,
	       t1 - t0);
	return t1 - t0;
}

static void cmd_bench(const char *arg)
{
	unsigned long ms;

	(void)arg;
	ms = run_loop(sh_loops);
	/* KiB/s without 64-bit division; sh_loops * 16 * 1000 fits in 32 bits up to 268435 */
	if (ms && sh_loops <= 268435)
		printf("  %lu KiB/s\n", (unsigned long)sh_loops * 16000UL / ms);
}

static void cmd_crc(const char *arg)
{
	unsigned int n = parse_uint(arg);

	if (n == 0 || n > MAX_LOOPS) {
		printf("  usage: crc <rounds>, 1 to %u\n", MAX_LOOPS);
		return;
	}
	run_loop(n);
}

/* Binary RGB order: black, blue, green, cyan, red, magenta, yellow, white. */
static unsigned int channel_mask(struct fb_bitfield field)
{
	return (~0U >> (32 - field.length)) << field.offset;
}

static void draw_fb(int mandel)
{
	struct fb_var_screeninfo v = { 0 };
	struct fb_fix_screeninfo f = { 0 };
	unsigned short red[8], green[8], blue[8];
	struct fb_cmap cmap = { 0, 8, red, green, blue, NULL };
	unsigned int pixels[8], x, y, i, bytes, sum = 0;
	int fd, tty, drawn = 0;

	mount_dev();
	fd = open_wait("/dev/fb0", O_RDWR);
	if (fd < 0 || ioctl(fd, FBIOGET_VSCREENINFO, &v) < 0 ||
	    ioctl(fd, FBIOGET_FSCREENINFO, &f) < 0)
		goto out;
	bytes = v.bits_per_pixel / 8;
	if ((v.bits_per_pixel != 8 && v.bits_per_pixel != 16 && v.bits_per_pixel != 32) ||
	    !v.xres || !v.yres || v.xres > sizeof(buf) / bytes ||
	    v.xres + v.xoffset > f.line_length / bytes)
		goto out;

	for (i = 0; i < 8; i++) {
		red[i] = i & 4 ? 65535 : 0;
		green[i] = i & 2 ? 65535 : 0;
		blue[i] = i & 1 ? 65535 : 0;
		if (f.visual == FB_VISUAL_PSEUDOCOLOR && bytes == 1)
			pixels[i] = i;
		else if (f.visual == FB_VISUAL_TRUECOLOR)
			pixels[i] = (red[i] ? channel_mask(v.red) : 0) |
				    (green[i] ? channel_mask(v.green) : 0) |
				    (blue[i] ? channel_mask(v.blue) : 0);
		else
			goto out;
	}
	if (f.visual == FB_VISUAL_PSEUDOCOLOR && ioctl(fd, FBIOPUTCMAP, &cmap) < 0)
		goto out;
	/* Keep fbcon's software cursor from repainting its cell over the image. */
	tty = open("/dev/tty0", O_WRONLY);
	if (tty >= 0) {
		/* Best effort: a visible cursor only costs one cell of the image. */
		ssize_t n = write(tty, "\033[?25l", 6);

		(void)n;
		close(tty);
	}
	/* Row writes also work on SBus devices with private mmap offsets. */
	for (y = 0; y < v.yres; y++) {
		int cy = -4712 + (int)(9424 * y / v.yres);

		for (x = 0; x < v.xres; x++) {
			if (mandel) {
				int cx = MANDEL_X0 + (int)(12288 * x / v.xres);
				int n = mandel_count(cx, cy);

				sum += n;
				i = n == MANDEL_ITER ? 0 : 1 + (n - 1) % 7;
			} else if (!x || !y || x == v.xres - 1 || y == v.yres - 1) {
				i = 7;
			} else {
				i = x * 8 / v.xres;
			}
			if (bytes == 1)
				((unsigned char *)buf)[x] = pixels[i];
			else if (bytes == 2) {
				unsigned short pixel = pixels[i];

				memcpy((unsigned char *)buf + x * 2, &pixel, 2);
			} else
				buf[x] = pixels[i];
		}
		if (lseek(fd, (y + v.yoffset) * f.line_length + v.xoffset * bytes, SEEK_SET) < 0 ||
		    write(fd, buf, v.xres * bytes) != (long)(v.xres * bytes))
			goto out;
	}
	drawn = 1;
out:
	if (mandel && drawn)
		printf("WISP-FBMANDEL v=1 xres=%u yres=%u bpp=%u iter=%u sum=%u\n",
		       v.xres, v.yres, v.bits_per_pixel, MANDEL_ITER, sum);
	else if (mandel)
		printf("WISP-FBMANDEL error drawing /dev/fb0\n");
	else
		printf("WISP-FB v=1 dev=/dev/fb0 xres=%u yres=%u bpp=%u visual=%u line=%u drawn=%d\n",
		       v.xres, v.yres, v.bits_per_pixel, f.visual, f.line_length, drawn);
	if (fd >= 0)
		close(fd);
}

static void cmd_mandel(const char *arg)
{
	char row[MANDEL_COLS + 1];
	unsigned long t0 = clock_ms(CLOCK_MONOTONIC);
	int r;

	if (!strcmp(arg, "fb")) {
		draw_fb(1);
		return;
	}
	for (r = 0; r < MANDEL_ROWS; r++) {
		mandel_row(r, row);
		printf(" %s\n", row);
	}
	printf("  %d x %d points, %d iterations, %lu ms\n", MANDEL_COLS, MANDEL_ROWS, MANDEL_ITER,
	       clock_ms(CLOCK_MONOTONIC) - t0);
}

/* Small fixed machine configurations, with devtmpfs naming devices in probe order. */
static int keyboard_fd(void)
{
	char path[32], name[80];
	unsigned long keys;
	int i, fd;

	mount_dev();
	for (i = 0; i < 32; i++) {
		snprintf(path, sizeof(path), "/dev/input/event%d", i);
		fd = open(path, O_RDONLY | O_NONBLOCK);
		if (fd < 0)
			continue;
		/* KEY_A fits in the first native word, including on big-endian SPARC. */
		keys = 0;
		if (ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(keys)), &keys) > 0 &&
		    (keys & (1UL << KEY_A)) && ioctl(fd, EVIOCGNAME(sizeof(name)), name) > 0) {
			printf("WISP-KEYBOARD dev=%s name=%s\n", path, name);
			return fd;
		}
		close(fd);
	}
	return -1;
}

static void cmd_keytest(void)
{
	struct input_event ev;
	struct pollfd pfd;
	unsigned long start, elapsed;
	int fd = keyboard_fd();

	if (fd < 0) {
		printf("keytest: keyboard unavailable\n");
		return;
	}
	pfd.fd = fd;
	pfd.events = POLLIN;
	start = clock_ms(CLOCK_MONOTONIC);
	while ((elapsed = clock_ms(CLOCK_MONOTONIC) - start) < 10000) {
		if (poll(&pfd, 1, 10000 - elapsed) <= 0)
			break;
		if (read(fd, &ev, sizeof(ev)) != sizeof(ev))
			break;
		if (ev.type != EV_KEY || ev.value != 1)
			continue;
		printf("WISP-KEY v=1 code=%u value=1\n", ev.code);
		if (ev.code == KEY_ESC)
			goto done;
	}
	printf("keytest: timed out or input stopped\n");
done:
	close(fd);
}

/* disk, net, smp: the tier-2 checks, with the kernel command line's devices by default */
static void cmd_disk(const char *arg)
{
	const char *list = *arg ? arg : env(wisp_envp, "wisp_disk");

	disks(list ? list : "sda", "  ");
}

static void cmd_net(const char *arg)
{
	const char *ifname = *arg ? arg : env(wisp_envp, "wisp_net");

	net_check(ifname ? ifname : "eth0", "  ");
}

static void cmd_smp(const char *arg)
{
	(void)arg;
	smp_check(sh_loops, "  ");
}

static void cmd_clear(const char *arg)
{
	(void)arg;
	printf("\033[H\033[2J");
}

static void cmd_poweroff(const char *arg)
{
	(void)arg;
	printf("  powering off\n");
	power(LINUX_REBOOT_CMD_POWER_OFF);
}

static void cmd_reboot(const char *arg)
{
	(void)arg;
	printf("  restarting\n");
	power(LINUX_REBOOT_CMD_RESTART);
}

/*
 * The command names, in the order of the switch in run_command(); a string
 * table rather than a table of function pointers, which would need a .data
 * section, and with it a segment padded to the 64 KiB (sparc32) or 1 MiB
 * (sparc64) page size of the target.
 */
static const char command_names[] =
	"help\0info\0uname\0bench\0crc\0mandel\0banner\0clear\0poweroff\0reboot\0disk\0net\0smp\0"
	"endian\0fbtest\0keytest\0";

static void run_command(const char *cmd, const char *arg)
{
	const char *name = command_names;
	int i = 0;

	while (*name && strcmp(cmd, name) != 0) {
		name += strlen(name) + 1;
		i++;
	}
	switch (i) {
	case 0: cmd_help(arg); break;
	case 1: /* fall through */
	case 2: cmd_info(arg); break;
	case 3: cmd_bench(arg); break;
	case 4: cmd_crc(arg); break;
	case 5: cmd_mandel(arg); break;
	case 6: cmd_banner(arg); break;
	case 7: cmd_clear(arg); break;
	case 8: cmd_poweroff(arg); break;
	case 9: cmd_reboot(arg); break;
	case 10: cmd_disk(arg); break;
	case 11: cmd_net(arg); break;
	case 12: cmd_smp(arg); break;
	case 13: cmd_endian(arg); break;
	case 14: draw_fb(0); break;
	case 15: cmd_keytest(); break;
	default: printf("  %s: unknown command, try help\n", cmd);
	}
}

/*
 * One line from the console into line[], without the newline; -1 at end of
 * input. The kernel's canonical mode has already applied Backspace, Ctrl-U
 * and Ctrl-W; this also drops ^H with the character before it, other control
 * characters and ESC [ ... sequences (arrow keys), for a pipe or a raw
 * terminal as well.
 */
static int read_line(char *line, int size)
{
	static char in[256];
	static int pos, len;
	int n = 0, esc = 0;
	char c;

	for (;;) {
		if (pos == len) {
			len = (int)read(0, in, sizeof(in));
			pos = 0;
			if (len <= 0) {
				len = 0;
				return -1;
			}
		}
		c = in[pos++];
		if (esc) {
			/* ESC, then '[' and parameters, then a final byte from '@' to '~' */
			if (esc == 2 && c >= '@' && c <= '~')
				esc = 0;
			else if (esc == 1)
				esc = c == '[' ? 2 : 0;
			continue;
		}
		if (c == '\n' || c == '\r')
			break;
		if (c == '\b' || c == 0x7f) {
			if (n)
				n--;
		} else if (c == 0x1b) {
			esc = 1;
		} else if (c == '\t') {
			c = ' ';
		}
		if ((unsigned char)c >= ' ' && c != 0x7f && n < size - 1)
			line[n++] = c;
	}
	line[n] = '\0';
	return n;
}

static void shell(void)
{
	char line[128], *cmd, *arg;
	int eofs = 0;

	/* only emergencies from the kernel on the console from here on */
	syscall(__NR_syslog, 8 /* SYSLOG_ACTION_CONSOLE_LEVEL */, 0, 1);
	cmd_banner("");
	printf("  Type \033[1mhelp\033[0m for the commands.\n\n");
	for (;;) {
		printf("\033[1;32mwisp\033[0m:\033[1;34m%s\033[0m> ", WISP_ARCH);
		if (read_line(line, sizeof(line)) < 0) {
			/* Ctrl-D on a terminal; the end of a pipe on the host */
			printf("\n");
			if (getpid() != 1 || ++eofs > 100)
				power(LINUX_REBOOT_CMD_POWER_OFF);
			continue;
		}
		for (cmd = line; *cmd == ' '; cmd++)
			;
		for (arg = cmd; *arg && *arg != ' '; arg++)
			;
		if (*arg)
			*arg++ = '\0';
		while (*arg == ' ')
			arg++;
		if (!*cmd)
			continue;
		run_command(cmd, arg);
	}
}

/* Test mode ----------------------------------------------------------------------------------- */

/*
 * wisp=test and wisp=run: run /test (from an external initramfs given with -initrd, which the kernel unpacks
 * over the built-in one) with PID 1's arguments (what follows "--" on the kernel command line)
 * and environment, wait for it, print one line with how it ended and power off. The wisp-test
 * GitHub Action (.github/actions/wisp-test) reads the line.
 */
static void payload_mode(int argc, char **argv, char **envp, int run)
{
	const char *marker = run ? "WISP-RUN" : "WISP-TEST";
	char *targv[64];
	unsigned long t0, t1;
	int i, n = 0, status = 0;
	pid_t pid, w;

	targv[n++] = "/test";
	for (i = 1; i < argc && n < 63; i++)
		targv[n++] = argv[i];
	targv[n] = NULL;
	if (run)
		printf("%s v=1 start\n", marker);
	fflush(stdout);
	t0 = clock_ms(CLOCK_MONOTONIC);
	pid = fork();
	if (pid == 0) {
		execve("/test", targv, envp);
		printf("%s-ERROR exec /test failed: errno %d\n", marker, errno);
		fflush(stdout);
		_exit(127);
	}
	if (pid < 0) {
		printf("%s-ERROR fork failed: errno %d\n", marker, errno);
		power(LINUX_REBOOT_CMD_POWER_OFF);
	}
	/* PID 1 also reaps whatever /test leaves behind; only /test itself counts */
	do
		w = waitpid(-1, &status, 0);
	while ((w > 0 && w != pid) || (w < 0 && errno == EINTR));
	t1 = clock_ms(CLOCK_MONOTONIC);
	if (w != pid)
		printf("%s-ERROR waitpid failed: errno %d\n", marker, errno);
	else
		printf("%s v=1 exit=%d signal=%d ms=%lu\n", marker,
		       WIFEXITED(status) ? WEXITSTATUS(status) : -1,
		       WIFSIGNALED(status) ? WTERMSIG(status) : 0, t1 - t0);
	power(LINUX_REBOOT_CMD_POWER_OFF);
}

int main(int argc, char **argv, char **envp)
{
	struct utsname u;
	unsigned long up, t0, t1;
	unsigned int loops, crc;
	const char *mode, *t2;
	int cpus;

	wisp_envp = envp;
	up = clock_ms(CLOCK_BOOTTIME);
	printf("WISP-BANNER wsh-pve wisp v1\n");

	memset(&u, 0, sizeof(u));
	uname(&u);
	cpus = count_cpus();
	loops = parse_loops(envp);
	crc_init();

	mode = env(envp, "wisp");
	if (mode && strcmp(mode, "shell") == 0) {
		sh_loops = loops;
		shell();
	}
	if (mode && (!strcmp(mode, "test") || !strcmp(mode, "run")))
		payload_mode(argc, argv, envp, !strcmp(mode, "run"));

	printf("WISP-INFO uname: %s %s %s\n", u.sysname, u.release, u.machine);
	printf("WISP-INFO cpus: %d memory: %lu kB pid: %d\n", cpus, mem_kb(0), getpid());

	t0 = clock_ms(CLOCK_MONOTONIC);
	crc = compute(loops);
	t1 = clock_ms(CLOCK_MONOTONIC);

	printf("WISP-RESULT v=1 arch=%s machine=%s release=%s cpus=%d mem_kb=%lu uptime_ms=%lu "
	       "loops=%u crc=0x%08x loop_ms=%lu status=%s\n",
	       WISP_ARCH, u.machine, u.release, cpus, mem_kb(0), up, loops, crc, t1 - t0,
	       getpid() == 1 ? "ok" : "notpid1");

	/* tier 2, after the result line, each only when asked for */
	t2 = env(envp, "wisp_disk");
	if (t2)
		disks(t2, "");
	t2 = env(envp, "wisp_net");
	if (t2)
		net_check(t2, "");
	t2 = env(envp, "wisp_smp");
	if (t2 && parse_uint(t2))
		smp_check(loops, "");

	if (getpid() != 1)
		return 0;
	power(LINUX_REBOOT_CMD_POWER_OFF);
	return 0;
}
