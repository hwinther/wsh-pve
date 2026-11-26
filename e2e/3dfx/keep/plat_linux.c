/*
 * wshkeep's i386 Linux front end: Glide 2 through libglide.so.2, built with a custom _start so no
 * symbol newer than GLIBC_2.0 is required. Supports non-blocking Linux evdev (/dev/input/event*)
 * for simultaneous held keys, raw termios + ANSI arrow escape decoding for serial/SSH/VT terminals,
 * and runtime-optional OSS /dev/dsp audio.
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

#include "keep.h"
#include "glide2.h"

#define DECL(ret, name, args, bytes) ret name args;
GLIDE2_FUNCS(DECL)
#define FILL(ret, name, args, bytes) g2.name = name;

static int console = -1, log_fd = -1, tty_raw, quit_signal;
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
	if (log_fd >= 0) {
		write_all(log_fd, line, n);
		write_all(log_fd, "\n", 1);
	}
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

struct ev_pkt {
	int32_t sec, usec;
	uint16_t type, code;
	int32_t val;
};

static int ev_fds[4] = {-1, -1, -1, -1};
static uint8_t ev_key[256];
static uint32_t tty_until[9]; /* 0:fwd 1:back 2:sl 3:sr 4:tl 5:tr 6:atk 7:use */
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
		keep_fmt(p, sizeof(p), "/dev/input/event%d", i);
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

	for (int i = 0; i < 4; i++) {
		if (ev_fds[i] < 0)
			continue;
		struct ev_pkt ev;
		while (read(ev_fds[i], &ev, sizeof(ev)) == (ssize_t)sizeof(ev)) {
			if (ev.type == 1 && ev.code < 256)
				ev_key[ev.code] = (ev.val != 0);
		}
	}

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
			FD_ZERO(&r);
			FD_SET(0, &r);
			tv.tv_sec = 0; tv.tv_usec = 2000;
			if (select(1, &r, 0, 0, &tv) > 0) {
				unsigned char seq[2] = {0, 0};
				if (read(0, &seq[0], 1) == 1 && seq[0] == '[' && read(0, &seq[1], 1) == 1) {
					if (seq[1] == 'A') { mark_tty_hold(0, now); push_key(KKEY_UP); continue; }
					if (seq[1] == 'B') { mark_tty_hold(1, now); push_key(KKEY_DOWN); continue; }
					if (seq[1] == 'D') { mark_tty_hold(4, now); push_key(KKEY_LEFT); continue; }
					if (seq[1] == 'C') { mark_tty_hold(5, now); push_key(KKEY_RIGHT); continue; }
				}
			}
			push_key(KKEY_ESC);
			continue;
		}
		if (c == 'w' || c == 'W') mark_tty_hold(0, now);
		if (c == 's' || c == 'S') mark_tty_hold(1, now);
		if (c == 'a' || c == 'A') mark_tty_hold(2, now);
		if (c == 'd' || c == 'D') mark_tty_hold(3, now);
		if (c == 'q' || c == 'Q') mark_tty_hold(4, now);
		if (c == 'c' || c == 'C') mark_tty_hold(5, now);
		if (c == ' ') mark_tty_hold(6, now);
		if (c == 'e' || c == 'E' || c == 13 || c == 10) mark_tty_hold(7, now);
		push_key(c);
	}
}

int plat_key(void)
{
	if (quit_signal)
		return KKEY_ESC;
	pump_inputs();
	if (kq_head == kq_tail)
		return 0;
	int k = kq[kq_tail];
	kq_tail = (kq_tail + 1) & 31;
	return k;
}

static inline int held_tty(int idx, uint32_t now)
{
	return (int32_t)(tty_until[idx] - now) > 0;
}

void plat_poll_input(struct plat_input *in)
{
	pump_inputs();
	uint32_t now = plat_us();
	/* Linux input-event-codes: W=17, S=31, A=30, D=32, Q=16, E=18, C=46, Enter=28, Space=57,
	 * LCtrl=29, LShift=42, RShift=54, Up=103, Left=105, Right=106, Down=108, PgUp=104, PgDn=109 */
	in->fwd = (ev_key[103] || ev_key[17] || held_tty(0, now)) ? 1 : 0;
	in->back = (ev_key[108] || ev_key[31] || held_tty(1, now)) ? 1 : 0;
	in->strafe_l = (ev_key[30] || held_tty(2, now)) ? 1 : 0;
	in->strafe_r = (ev_key[32] || held_tty(3, now)) ? 1 : 0;
	in->turn_l = (ev_key[105] || ev_key[16] || held_tty(4, now)) ? 1 : 0;
	in->turn_r = (ev_key[106] || ev_key[46] || held_tty(5, now)) ? 1 : 0;
	in->look_u = ev_key[104] ? 1 : 0;
	in->look_d = ev_key[109] ? 1 : 0;
	in->attack = (ev_key[57] || ev_key[29] || held_tty(6, now)) ? 1 : 0;
	in->use_door = (ev_key[18] || ev_key[28] || held_tty(7, now)) ? 1 : 0;
	in->sprint = (ev_key[42] || ev_key[54]) ? 1 : 0;
	in->mdx = in->mdy = 0;
	in->mb_l = in->mb_r = 0;
}

#define SND_MIX keep_audio_mix
#include "../audio/snd_oss.h"

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
	return len > 0 && keep_find_buildstr((const uint8_t *)filebuf, (uint32_t)len, buf, n);
}

static void on_signal(int sig)
{
	(void)sig;
	quit_signal = 1;
}

static int main_linux(int argc, char **argv)
{
	for (int i = 1; i + 1 < argc; i++) {
		if (!strcmp(argv[i], "-log"))
			log_fd = open(argv[++i], O_WRONLY | O_CREAT | O_TRUNC, 0644);
	}
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
	int status = keep_main(argc, argv, &glide2_backend);
	input_close();
	if (log_fd >= 0)
		close(log_fd);
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

__attribute__((used, noreturn)) void wshkeep_start(uint32_t *sp)
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
	"\tcall wshkeep_start\n"
	"\thlt\n");
