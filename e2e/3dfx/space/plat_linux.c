/*
 * wshspace's i386 Linux front end: Glide 2 through libglide.so.2, built with a custom _start so no
 * symbol newer than GLIBC_2.0 is required. Supports non-blocking Linux evdev (/dev/input/event*)
 * for true simultaneous held keys when present, plus raw termios + ANSI arrow escape decoding for
 * serial/SSH/VT terminals, and runtime-optional OSS /dev/dsp audio.
 * Copyright 2026 WsHosting ENK, GPL-3.
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

#include "space.h"
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
		s += w;
		n -= (size_t)w;
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

void plat_sleep(int ms)
{
	struct timeval tv = {ms / 1000, (ms % 1000) * 1000};
	select(0, 0, 0, 0, &tv);
}

/* --- Linux evdev + termios input -------------------------------------------------------------- */

struct ev_pkt {
	int32_t sec, usec;
	uint16_t type, code;
	int32_t val;
};

static int ev_fds[4] = {-1, -1, -1, -1};
static uint8_t ev_key[256];
static uint32_t tty_until[10]; /* hold decay timestamps (us) for termios keys */
static int kq[32], kq_head, kq_tail;

static void push_key(int k)
{
	int next = (kq_head + 1) & 31;
	if (next != kq_tail) {
		kq[kq_head] = k;
		kq_head = next;
	}
}

static void input_init(void)
{
	for (int i = 0; i < 4; i++) {
		char p[24];
		space_fmt(p, sizeof(p), "/dev/input/event%d", i);
		ev_fds[i] = open(p, O_RDONLY | O_NONBLOCK);
	}
}

static void input_close(void)
{
	for (int i = 0; i < 4; i++)
		if (ev_fds[i] >= 0)
			close(ev_fds[i]);
}

static void mark_tty_hold(int idx, uint32_t now)
{
	tty_until[idx] = now + 190000U;
}

static void pump_inputs(void)
{
	uint32_t now = plat_us();

	/* 1. Drain any evdev devices (32-bit i386 input_event is 16 bytes) */
	for (int i = 0; i < 4; i++) {
		if (ev_fds[i] < 0)
			continue;
		struct ev_pkt ev;
		while (read(ev_fds[i], &ev, sizeof(ev)) == (ssize_t)sizeof(ev)) {
			if (ev.type == 1 && ev.code < 256)
				ev_key[ev.code] = (ev.val != 0);
		}
	}

	/* 2. Non-blocking termios stdin + ANSI arrow escape parser */
	if (!tty_raw)
		return;
	for (;;) {
		fd_set r;
		struct timeval tv = {0, 0};
		FD_ZERO(&r);
		FD_SET(0, &r);
		if (select(1, &r, 0, 0, &tv) <= 0)
			break;
		unsigned char c = 0;
		if (read(0, &c, 1) != 1)
			break;
		if (c == 27) {
			/* Check immediately if an ANSI escape sequence follows */
			FD_ZERO(&r);
			FD_SET(0, &r);
			tv.tv_sec = 0; tv.tv_usec = 2000;
			if (select(1, &r, 0, 0, &tv) > 0) {
				unsigned char seq[2] = {0, 0};
				if (read(0, &seq[0], 1) == 1 && seq[0] == '[' && read(0, &seq[1], 1) == 1) {
					if (seq[1] == 'A') { mark_tty_hold(0, now); push_key(KEY_UP); continue; }
					if (seq[1] == 'B') { mark_tty_hold(1, now); push_key(KEY_DOWN); continue; }
					if (seq[1] == 'D') { mark_tty_hold(2, now); push_key(KEY_LEFT); continue; }
					if (seq[1] == 'C') { mark_tty_hold(3, now); push_key(KEY_RIGHT); continue; }
				}
			}
			push_key(27);
			continue;
		}
		if (c == 'a' || c == 'A' || c == 'q' || c == 'Q') mark_tty_hold(4, now);
		if (c == 'd' || c == 'D' || c == 'e' || c == 'E') mark_tty_hold(5, now);
		if (c == 'w' || c == 'W') mark_tty_hold(6, now);
		if (c == 's' || c == 'S') mark_tty_hold(7, now);
		if (c == 'b' || c == 'B') mark_tty_hold(8, now);
		if (c == ' ')             mark_tty_hold(9, now);
		push_key(c);
	}
}

int plat_key(void)
{
	if (quit_signal)
		return 27;
	pump_inputs();
	if (kq_head == kq_tail)
		return -1;
	int k = kq[kq_tail];
	kq_tail = (kq_tail + 1) & 31;
	return k;
}

void plat_poll(struct plat_input *in)
{
	pump_inputs();
	uint32_t now = plat_us(), h = 0;
	for (int i = 0; i < 10; i++) {
		if ((int32_t)(tty_until[i] - now) > 0)
			h |= (1U << i);
	}
	/* Linux input-event-codes: W=17, S=31, A=30, D=32, Q=16, E=18, B=48, Space=57,
	 * LShift=42, RShift=54, Up=103, Left=105, Right=106, Down=108 */
	if (ev_key[103])               h |= IN_PITCH_UP;
	if (ev_key[108])               h |= IN_PITCH_DOWN;
	if (ev_key[105])               h |= IN_YAW_LEFT;
	if (ev_key[106])               h |= IN_YAW_RIGHT;
	if (ev_key[30] || ev_key[16])  h |= IN_ROLL_LEFT;
	if (ev_key[32] || ev_key[18])  h |= IN_ROLL_RIGHT;
	if (ev_key[17])                h |= IN_THRUST;
	if (ev_key[31])                h |= IN_BRAKE;
	if (ev_key[42] || ev_key[54] || ev_key[48]) h |= IN_BOOST;
	if (ev_key[57])                h |= IN_FIRE;
	in->held = h;
	in->mdx = in->mdy = 0;
	in->mlook = 0;
}

/* --- Runtime-optional OSS /dev/dsp audio (no extra .so dependencies) -------------------------- */

#define SNDCTL_DSP_SPEED       0xc0045002UL
#define SNDCTL_DSP_SETFMT      0xc0045005UL
#define SNDCTL_DSP_CHANNELS    0xc0045006UL
#define SNDCTL_DSP_SETFRAGMENT 0xc004500aUL

static int dsp_fd = -1, dsp_rate = 22050;
static uint32_t dsp_last_us;
static int16_t dsp_buf[1024 * 2];

void plat_audio_init(int enable)
{
	if (!enable || dsp_fd >= 0)
		return;
	dsp_fd = open("/dev/dsp", O_WRONLY | O_NONBLOCK);
	if (dsp_fd < 0)
		return;
	int frag = (4 << 16) | 12; /* 4 fragments of 4096 bytes */
	int fmt = 0x10;            /* AFMT_S16_LE */
	int ch = 2;
	int rate = 22050;
	ioctl(dsp_fd, SNDCTL_DSP_SETFRAGMENT, &frag);
	if (ioctl(dsp_fd, SNDCTL_DSP_SETFMT, &fmt) < 0 || fmt != 0x10 ||
	    ioctl(dsp_fd, SNDCTL_DSP_CHANNELS, &ch) < 0 || ch != 2 ||
	    ioctl(dsp_fd, SNDCTL_DSP_SPEED, &rate) < 0) {
		close(dsp_fd);
		dsp_fd = -1;
		return;
	}
	dsp_rate = rate;
	dsp_last_us = plat_us() - 50000U;
}

void plat_audio_tick(void)
{
	if (dsp_fd < 0)
		return;
	uint32_t now = plat_us();
	uint32_t dt_us = now - dsp_last_us;
	if (dt_us > 100000U)
		dt_us = 100000U;
	int frames = (int)((double)dt_us * (double)dsp_rate * 1e-6);
	if (frames < 128)
		return;
	if (frames > 1024)
		frames = 1024;
	space_audio_mix(dsp_buf, frames, dsp_rate);
	ssize_t w = write(dsp_fd, dsp_buf, (size_t)frames * 4);
	if (w > 0)
		dsp_last_us = now;
}

void plat_audio_close(void)
{
	if (dsp_fd >= 0) {
		close(dsp_fd);
		dsp_fd = -1;
	}
}

/* --- wrapper build string & custom GLIBC_2.0 _start ------------------------------------------- */

static char filebuf[512 * 1024];
int plat_wrapper_rev(char *buf, int n)
{
	int fd = open("/proc/self/maps", O_RDONLY);
	if (fd < 0)
		return 0;
	ssize_t len = read(fd, filebuf, sizeof(filebuf) - 1), got;
	while (len > 0 && len < (ssize_t)sizeof(filebuf) - 1 &&
	       (got = read(fd, filebuf + len, sizeof(filebuf) - 1 - (size_t)len)) > 0)
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
	return len > 0 && space_find_buildstr((const uint8_t *)filebuf, (uint32_t)len, buf, n);
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
		t.c_cc[VMIN] = 1;
		t.c_cc[VTIME] = 0;
		tty_raw = tcsetattr(0, TCSANOW, &t) == 0;
	}
	signal(SIGINT, on_signal);
	signal(SIGTERM, on_signal);
	input_init();
	GLIDE2_FUNCS(FILL)
	int status = space_main(argc, argv, &glide2_backend);
	input_close();
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

__attribute__((used, noreturn)) void wshspace_start(uint32_t *sp)
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
	"\tcall wshspace_start\n"
	"\thlt\n");
