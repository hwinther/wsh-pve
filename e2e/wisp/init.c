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
 * The same file builds against glibc on the host ("cc -o init-host init.c"),
 * where it is not PID 1: tests/test_shell.py drives that build.
 */
#ifdef __sparc__
/* nolibc's _start out of the way, see below */
#define _start wisp_nolibc_start
#endif
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

static void mandel_row(int row, char *out)
{
	int col, n, x, y, x2, y2, cx, cy;

	cy = (2 * row - (MANDEL_ROWS - 1)) * MANDEL_DY;
	for (col = 0; col < MANDEL_COLS; col++) {
		cx = MANDEL_X0 + col * MANDEL_DX;
		x = y = 0;
		for (n = 0; n < MANDEL_ITER; n++) {
			x2 = (x * x) >> 12;
			y2 = (y * y) >> 12;
			if (x2 + y2 > 4 << 12)
				break;
			y = ((x * y) >> 11) + cy;
			x = x2 - y2 + cx;
		}
		out[col] = n == MANDEL_ITER ? '@' : mandel_chars[n * 9 / MANDEL_ITER];
	}
	out[MANDEL_COLS] = '\0';
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
	       "  mandel          the Mandelbrot set in fixed-point integer math\n"
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

static void cmd_mandel(const char *arg)
{
	char row[MANDEL_COLS + 1];
	unsigned long t0 = clock_ms(CLOCK_MONOTONIC);
	int r;

	(void)arg;
	for (r = 0; r < MANDEL_ROWS; r++) {
		mandel_row(r, row);
		printf(" %s\n", row);
	}
	printf("  %d x %d points, %d iterations, %lu ms\n", MANDEL_COLS, MANDEL_ROWS, MANDEL_ITER,
	       clock_ms(CLOCK_MONOTONIC) - t0);
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
#if defined(__sparc__) && defined(__arch64__)
	/*
	 * Linux restarts a sun4u through the firmware's "boot" service, which
	 * OpenBIOS doesn't carry out: the kernel panics ("Reboot failed!") and,
	 * with panic=-1, tries again for ever.
	 */
	if (getpid() == 1) {
		printf("  reboot: not with OpenBIOS on sun4u, use poweroff\n");
		return;
	}
#endif
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
	"help\0info\0uname\0bench\0crc\0mandel\0banner\0clear\0poweroff\0reboot\0";

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

int main(int argc, char **argv, char **envp)
{
	struct utsname u;
	unsigned long up, t0, t1;
	unsigned int loops, crc;
	const char *mode;
	int cpus;

	(void)argc;
	(void)argv;
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

	printf("WISP-INFO uname: %s %s %s\n", u.sysname, u.release, u.machine);
	printf("WISP-INFO cpus: %d memory: %lu kB pid: %d\n", cpus, mem_kb(0), getpid());

	t0 = clock_ms(CLOCK_MONOTONIC);
	crc = compute(loops);
	t1 = clock_ms(CLOCK_MONOTONIC);

	printf("WISP-RESULT v=1 arch=%s machine=%s release=%s cpus=%d mem_kb=%lu uptime_ms=%lu "
	       "loops=%u crc=0x%08x loop_ms=%lu status=%s\n",
	       WISP_ARCH, u.machine, u.release, cpus, mem_kb(0), up, loops, crc, t1 - t0,
	       getpid() == 1 ? "ok" : "notpid1");

	if (getpid() != 1)
		return 0;
	power(LINUX_REBOOT_CMD_POWER_OFF);
	return 0;
}
