/*
 * wshdemo's Linux front end (i386): Glide 2 through libglide.so.2, the Linux guest library of the
 * qemu-3dfx-drivers release (scripts/build-3dfx-linux-glide.sh), linked dynamically (-lglide2x).
 *
 * Built for old distributions like the library itself (build-linux.sh checks it): i586, no stdio,
 * and its own _start instead of the toolchain's crt1.o, which since glibc 2.34 asks for
 * __libc_start_main@GLIBC_2.34. The dynamic loader still runs libc's initialisers before _start,
 * so the plain system calls (write, read, select, gettimeofday...) need nothing newer than glibc 2.0.
 *
 * Output goes to standard output and to /dev/console. Keys come from standard input when it is a
 * terminal (no echo, no line buffering while the demo runs). Sound goes to OSS /dev/dsp
 * (e2e/3dfx/audio/snd_oss.h; snd-pcm-oss on ALSA). Run as root: the wrapper maps the
 * glidept device through /dev/mem. As PID 1 (the /init of a test guest, e2e/3dfx/test.sh) it mounts
 * devtmpfs and proc, takes its arguments from the kernel command line after "--" and powers the VM
 * off at the end. Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <termios.h>
#include <unistd.h>

#include "demo.h"
#include "glide2.h"

#define DECL(ret, name, args, bytes) ret name args;
GLIDE2_FUNCS(DECL)
#define FILL(ret, name, args, bytes) g2.name = name;

static int console = -1, tty_raw, quit_signal;
static struct termios tty_saved;

uint32_t plat_us(void)
{
	struct timeval tv;
	gettimeofday(&tv, 0);
	return (uint32_t)tv.tv_sec * 1000000U + (uint32_t)tv.tv_usec;
}

static void write_all(int fd, const char *s, size_t n)
{
	while (n) {
		ssize_t w = write(fd, s, n);
		if (w <= 0)
			return;
		s += w, n -= (size_t)w;
	}
}

void plat_out(const char *line)
{
	size_t n = strlen(line);
	write_all(1, line, n);
	write_all(1, "\n", 1);
	if (console >= 0) {
		write_all(console, line, n);
		write_all(console, "\r\n", 2);
	}
}

int plat_key(void)
{
	if (quit_signal)
		return 27;
	if (!tty_raw)
		return -1;
	fd_set r;
	struct timeval tv = {0, 0};
	FD_ZERO(&r);
	FD_SET(0, &r);
	if (select(1, &r, 0, 0, &tv) <= 0)
		return -1;
	unsigned char c;
	return read(0, &c, 1) == 1 ? c : -1;
}

void plat_sleep(int ms)
{
	struct timeval tv = {ms / 1000, (ms % 1000) * 1000};
	select(0, 0, 0, 0, &tv);
}

/* Sound: OSS /dev/dsp (silent without it) */
#define SND_MIX demo_audio_mix
#include "../audio/snd_oss.h"

/* The build string in the libglide the loader mapped (its path from /proc/self/maps) */
static char filebuf[512 * 1024];
int plat_wrapper_rev(char *buf, int n)
{
	int fd = open("/proc/self/maps", O_RDONLY);
	if (fd < 0)
		return 0;
	ssize_t len = read(fd, filebuf, sizeof(filebuf) - 1), got;
	while (len > 0 && len < (ssize_t)sizeof(filebuf) - 1 && (got = read(fd, filebuf + len, sizeof(filebuf) - 1 - (size_t)len)) > 0)
		len += got;
	close(fd);
	if (len <= 0)
		return 0;
	filebuf[len] = 0;
	char path[256] = "";
	for (char *l = filebuf; *l;) {
		char *e = l;
		while (*e && *e != '\n')
			e++;
		char *p = strstr(l, "libglide");
		if (p && p < e) {
			char *s = p;
			while (s > l && s[-1] != ' ')
				s--;
			size_t k = (size_t)(e - s) < sizeof(path) - 1 ? (size_t)(e - s) : sizeof(path) - 1;
			memcpy(path, s, k);
			path[k] = 0;
			break;
		}
		l = *e ? e + 1 : e;
	}
	if (!path[0] || (fd = open(path, O_RDONLY)) < 0)
		return 0;
	len = 0;
	while (len < (ssize_t)sizeof(filebuf) && (got = read(fd, filebuf + len, sizeof(filebuf) - (size_t)len)) > 0)
		len += got;
	close(fd);
	return len > 0 && demo_find_buildstr((const uint8_t *)filebuf, (uint32_t)len, buf, n);
}

static void on_signal(int sig)
{
	(void)sig;
	quit_signal = 1;
}

static int main_linux(int argc, char **argv)
{
	int pid1 = getpid() == 1;
	if (pid1) {
		mkdir("/dev", 0755);
		mount("devtmpfs", "/dev", "devtmpfs", 0, 0);
		mkdir("/proc", 0755);
		mount("proc", "/proc", "proc", 0, 0);
		if (chdir("/")) {
		}
	} else {
		console = open("/dev/console", O_WRONLY | O_NOCTTY);
	}
	if (tcgetattr(0, &tty_saved) == 0) {
		struct termios t = tty_saved;
		t.c_lflag &= ~(tcflag_t)(ICANON | ECHO);
		t.c_cc[VMIN] = 1, t.c_cc[VTIME] = 0;
		tty_raw = tcsetattr(0, TCSANOW, &t) == 0;
	}
	signal(SIGINT, on_signal);
	signal(SIGTERM, on_signal);
	GLIDE2_FUNCS(FILL)
	int status = demo_main(argc, argv, &glide2_backend);
	if (tty_raw)
		tcsetattr(0, TCSANOW, &tty_saved);
	if (pid1) {
		sync();
		plat_sleep(1000);
		reboot(RB_POWER_OFF);
		for (;;)
			pause();
	}
	return status;
}

/* _start: argc and argv from the stack; libc is set up already (by the dynamic loader) */
__attribute__((used, noreturn)) void wshdemo_start(uint32_t *sp)
{
	_exit(main_linux((int)sp[0], (char **)(sp + 1)));
}
__asm__(".text\n"
	".globl _start\n"
	".type _start, @function\n"
	"_start:\n"
	"\txorl %ebp, %ebp\n"
	"\tmovl %esp, %eax\n"
	"\tandl $-16, %esp\n"
	"\tsubl $12, %esp\n"
	"\tpushl %eax\n"
	"\tcall wshdemo_start\n"
	"\thlt\n");
