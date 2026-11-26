/*
 * wshracer: .kkrieger-inspired procedural 3D anti-gravity hover-racer for 3dfx Glide 2/3 & OpenGL.
 * Features 4 procedural 3D spline circuits (banked turns, hills, enclosed neon tunnels, canyon/
 * coastal/viaduct/glacier vistas, turbo boost chevrons, overhead gantries), 6 hovercraft teams,
 * projected ground shadows, plasma trails, 138 BPM electronic soundtrack, and E2E self-tests.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>

#include "racer.h"
#include "font.h"
#include "gen.h"
#include "render.h"

void *memset(void *d, int c, size_t n);
void *memcpy(void *d, const void *s, size_t n);

struct view racer_view = {640, 480, 360.0f, 1.0f, 2600.0f};
static const char *log_tag = "WSHRACER";

/* --- Freestanding formatting & wrapper revision scanner ----------------------------------------- */

static int str_eq(const char *a, const char *b)
{
	while (*a && *a == *b)
		a++, b++;
	return *a == *b;
}

static int parse_int(const char *s, int *out)
{
	int sign = 1, v = 0, any = 0;
	if (*s == '-')
		sign = -1, s++;
	while (*s >= '0' && *s <= '9')
		v = v * 10 + (*s++ - '0'), any = 1;
	if (!any || *s)
		return -1;
	*out = v * sign;
	return 0;
}

static int parse_float(const char *s, float *out)
{
	float sign = 1.0f, v = 0.0f, frac = 0.1f;
	int any = 0;
	if (*s == '-')
		sign = -1.0f, s++;
	while (*s >= '0' && *s <= '9')
		v = v * 10.0f + (float)(*s++ - '0'), any = 1;
	if (*s == '.') {
		s++;
		while (*s >= '0' && *s <= '9')
			v += (float)(*s++ - '0') * frac, frac *= 0.1f, any = 1;
	}
	if (!any || *s)
		return -1;
	*out = v * sign;
	return 0;
}

static int parse_res(const char *s, int *w, int *h)
{
	int vw = 0, vh = 0;
	while (*s >= '0' && *s <= '9')
		vw = vw * 10 + (*s++ - '0');
	if (*s != 'x' && *s != 'X')
		return -1;
	s++;
	while (*s >= '0' && *s <= '9')
		vh = vh * 10 + (*s++ - '0');
	if (*s || vw <= 0 || vh <= 0)
		return -1;
	*w = vw, *h = vh;
	return 0;
}

static void put_ch(char *buf, int cap, int *pos, char c)
{
	if (*pos + 1 < cap)
		buf[*pos] = c;
	(*pos)++;
}

static void put_uint(char *buf, int cap, int *pos, uint32_t v, int base, int width)
{
	char tmp[16];
	int n = 0;
	if (!v)
		tmp[n++] = '0';
	while (v) {
		int d = (int)(v % (uint32_t)base);
		tmp[n++] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
		v /= (uint32_t)base;
	}
	while (n < width)
		tmp[n++] = '0';
	while (n > 0)
		put_ch(buf, cap, pos, tmp[--n]);
}

static int vfmt(char *buf, int cap, const char *fmt, va_list ap)
{
	int pos = 0;
	for (; *fmt; fmt++) {
		if (*fmt != '%') {
			put_ch(buf, cap, &pos, *fmt);
			continue;
		}
		fmt++;
		int left = 0, width = 0, prec = -1;
		if (*fmt == '-')
			left = 1, fmt++;
		while (*fmt >= '0' && *fmt <= '9')
			width = width * 10 + (*fmt++ - '0');
		if (*fmt == '.') {
			fmt++, prec = 0;
			while (*fmt >= '0' && *fmt <= '9')
				prec = prec * 10 + (*fmt++ - '0');
		}
		if (*fmt == 's') {
			const char *s = va_arg(ap, const char *);
			if (!s)
				s = "(null)";
			int len = 0;
			while (s[len] && (prec < 0 || len < prec))
				len++;
			if (!left)
				for (int p = len; p < width; p++)
					put_ch(buf, cap, &pos, ' ');
			for (int i = 0; i < len; i++)
				put_ch(buf, cap, &pos, s[i]);
			if (left)
				for (int p = len; p < width; p++)
					put_ch(buf, cap, &pos, ' ');
		} else if (*fmt == 'd') {
			int v = va_arg(ap, int);
			if (v < 0) {
				put_ch(buf, cap, &pos, '-');
				put_uint(buf, cap, &pos, (uint32_t)(-v), 10, width > 0 ? width - 1 : 0);
			} else {
				put_uint(buf, cap, &pos, (uint32_t)v, 10, width);
			}
		} else if (*fmt == 'u') {
			put_uint(buf, cap, &pos, va_arg(ap, uint32_t), 10, width);
		} else if (*fmt == 'x') {
			put_uint(buf, cap, &pos, va_arg(ap, uint32_t), 16, width);
		} else if (*fmt == 'f') {
			double fv = va_arg(ap, double);
			if (fv < 0)
				put_ch(buf, cap, &pos, '-'), fv = -fv;
			int pr = prec < 0 ? 2 : prec;
			double mul = 1.0;
			for (int i = 0; i < pr; i++)
				mul *= 10.0;
			uint32_t whole = (uint32_t)(fv + 0.5 / mul);
			uint32_t fr = (uint32_t)((fv - (double)(uint32_t)fv) * mul + 0.5);
			if (fr >= (uint32_t)mul)
				fr -= (uint32_t)mul;
			put_uint(buf, cap, &pos, whole, 10, 0);
			if (pr > 0) {
				put_ch(buf, cap, &pos, '.');
				put_uint(buf, cap, &pos, fr, 10, pr);
			}
		} else if (*fmt == '%') {
			put_ch(buf, cap, &pos, '%');
		}
	}
	if (cap > 0)
		buf[pos < cap ? pos : cap - 1] = 0;
	return pos;
}

int racer_fmt(char *buf, int cap, const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	int n = vfmt(buf, cap, fmt, ap);
	va_end(ap);
	return n;
}

void racer_log(const char *fmt, ...)
{
	char body[384], line[420];
	va_list ap;
	va_start(ap, fmt);
	vfmt(body, sizeof(body), fmt, ap);
	va_end(ap);
	racer_fmt(line, sizeof(line), "%s: %s", log_tag, body);
	plat_out(line);
}

int racer_find_buildstr(const uint8_t *buf, uint32_t len, char *out, int outlen)
{
	static const char needle[] = "qemu-3dfx";
	for (uint32_t i = 0; i + 16 < len; i++) {
		int ok = 1;
		for (int k = 0; k < 9; k++)
			if (buf[i + (uint32_t)k] != (uint8_t)needle[k])
				ok = 0;
		if (!ok)
			continue;
		uint32_t s = i;
		while (s > 0 && i - s < 32 && buf[s - 1] >= 32 && buf[s - 1] < 127)
			s--;
		int k = 0;
		while (s + (uint32_t)k < len && k + 1 < outlen && buf[s + (uint32_t)k] >= 32 && buf[s + (uint32_t)k] < 127) {
			out[k] = (char)buf[s + (uint32_t)k];
			k++;
		}
		out[k] = 0;
		return 1;
	}
	return 0;
}

/* --- 4 Procedural Closed-Loop 3D Spline Circuits & 6 Racing Teams ------------------------------- */

#define N_SEG        256
#define TRACK_HALF_W 14.5f
#define N_RACERS     6
#define TOTAL_LAPS   3
#define MAX_SPARKS   96

struct circuit_def {
	const char *name;
	float rx, rz;
	float ax2, px2, ax3, px3;
	float az2, pz2, az3, pz3;
	float h1, ph1, h2, ph2, h3, ph3;
	uint32_t sky_top, sky_hor, fog_rgb;
	uint8_t road_r, road_g, road_b;
	uint8_t curb_r, curb_g, curb_b;
	uint8_t ter_r, ter_g, ter_b;
	uint8_t cliff_mode; /* 0 = canyon cliffs, 1 = elevated neon viaduct, 2 = ocean + island, 3 = alpine glacier */
};

static const struct circuit_def circuits[4] = {
	{
		"REDROCK CANYON",
		430.0f, 320.0f,
		88.0f, 0.4f, 52.0f, 1.3f,
		74.0f, 1.1f, 46.0f, 2.4f,
		26.0f, 0.3f, 16.0f, 1.7f, 8.0f, 0.8f,
		0x183c84U, 0xe88a48U, 0xd87c44U,
		224, 212, 200,
		255, 110, 72,
		224, 118, 68,
		0,
	},
	{
		"NEON METROPOLIS",
		465.0f, 295.0f,
		105.0f, 1.2f, 62.0f, 0.2f,
		82.0f, 0.5f, 58.0f, 1.9f,
		20.0f, 1.0f, 14.0f, 0.4f, 6.0f, 2.1f,
		0x08061aU, 0x261252U, 0x1c1042U,
		175, 192, 232,
		64, 245, 255,
		72, 54, 138,
		1,
	},
	{
		"PACIFIC ATOLL",
		445.0f, 355.0f,
		76.0f, 2.1f, 48.0f, 0.9f,
		92.0f, 1.5f, 42.0f, 0.3f,
		18.0f, 0.6f, 12.0f, 2.2f, 5.0f, 1.1f,
		0x1464c8U, 0x74d4f8U, 0x62c4ecU,
		222, 226, 232,
		255, 128, 108,
		112, 198, 118,
		2,
	},
	{
		"GLACIER PEAK",
		405.0f, 335.0f,
		94.0f, 0.8f, 56.0f, 2.5f,
		78.0f, 2.0f, 52.0f, 1.1f,
		34.0f, 1.4f, 20.0f, 0.5f, 9.0f, 2.6f,
		0x102448U, 0x5c96c8U, 0x4e86b8U,
		210, 226, 246,
		108, 212, 255,
		196, 224, 252,
		3,
	},
};

struct team_def {
	const char *name;
	uint8_t r, g, b;
	uint8_t fr, fg, fb; /* plasma thruster tint */
};

static const struct team_def teams[N_RACERS] = {
	{"SOLARIS GP",     72, 235, 255,   80, 240, 255},
	{"CRIMSON VORTEX", 255, 86,  64,  255, 165,  60},
	{"COBALT NOVA",    95, 135, 255,  140, 175, 255},
	{"APEX VIPER",     92, 245, 128,  120, 255, 150},
	{"HYPERION GOLD", 255, 212,  68,  255, 235, 120},
	{"PHANTOM PULSE", 232,  95, 255,  255, 120, 255},
};

struct trk_node {
	v3 pos, fwd, right, up;
	float len, curv, bank;
	float cliff_l, cliff_r;
	uint8_t tunnel;    /* 1 inside enclosed neon tunnel */
	uint8_t pad_type;  /* 0 none, 1 turbo chevron pad, 2 energy recharge strip */
	float pad_lat;     /* lateral center of boost/recharge pad */
};

static struct trk_node trk[N_SEG];

struct racer {
	float seg;         /* 0..N_SEG continuous spline coordinate */
	float lat;         /* lateral offset along node->right (-TRACK_HALF_W..+TRACK_HALF_W) */
	float hover_h;     /* height above road surface */
	float vel_h;
	float vel_fwd;     /* forward speed (m/s) */
	float vel_lat;     /* lateral drift speed (m/s) */
	float yaw_rel;     /* heading angle relative to track tangent */
	float roll;        /* visual banking roll relative to track surface */
	float energy;      /* 0..100 boost/shield capacitor */
	float boost_t;     /* active turbo timer */
	float pad_cd;      /* pad trigger cooldown */
	int lap;           /* 0-based completed laps (0 = lap 1) */
	int half_ok;       /* passed halfway checkpoint on current lap */
	int rank;          /* 0..5 race position */
	float progress;    /* total continuous race distance for ranking */
	float cur_lap_t, best_lap_t;
	float ai_lane, ai_lane_t, ai_skill;
	v3 wpos, bx, by, bz;
};

static struct racer racers[N_RACERS];

struct spark {
	v3 pos, vel;
	float life, max_life, size;
	uint32_t argb;
};

static struct spark sparks[MAX_SPARKS];
static int spark_next;

static struct {
	int track_id;
	int cam_mode;      /* 0 chase cam, 1 nose cockpit cam */
	int auto_play;
	int hud_on;
	int show_fps;
	int finished;
	int check_mode;
	uint32_t rng;
	float time_s;
	float countdown;   /* 3.0 -> 0.0 -> negative during race */
	float banner_t;
	char banner[64];
	float fps_disp;
	float ft_hist[64];
	int ft_pos;
} gs;

#include "ui.h"

/* --- Spline Circuit Generator & Continuous Interpolation ---------------------------------------- */

static v3 eval_circuit_raw(const struct circuit_def *c, float u, int idx)
{
	/* Straighten curvature near start/finish (u ~ 0) slightly for a clean grid & -check view */
	float x = c->rx * m_cosf(u) + c->ax2 * m_cosf(2.0f * u + c->px2) + c->ax3 * m_sinf(3.0f * u + c->px3);
	float z = c->rz * m_sinf(u) + c->az2 * m_sinf(2.0f * u + c->pz2) + c->az3 * m_cosf(3.0f * u + c->pz3);
	float y = 24.0f + c->h1 * m_sinf(2.0f * u + c->ph1) + c->h2 * m_cosf(3.0f * u + c->ph2) + c->h3 * m_sinf(5.0f * u + c->ph3);
	(void)idx;
	return v3_make(x, y, z);
}

static void build_circuit(int id)
{
	gs.track_id = id & 3;
	syn.track_key = gs.track_id;
	const struct circuit_def *c = &circuits[gs.track_id];

	for (int i = 0; i < N_SEG; i++) {
		float u = (float)i * ((float)TAU / (float)N_SEG);
		trk[i].pos = eval_circuit_raw(c, u, i);
	}

	v3 world_up = v3_make(0.0f, 1.0f, 0.0f);
	for (int i = 0; i < N_SEG; i++) {
		int prev = (i - 1) & (N_SEG - 1);
		int next = (i + 1) & (N_SEG - 1);
		v3 seg_d = v3_sub(trk[next].pos, trk[i].pos);
		trk[i].len = v3_len(seg_d);
		if (trk[i].len < 1.0f)
			trk[i].len = 1.0f;
		trk[i].fwd = v3_norm(v3_sub(trk[next].pos, trk[prev].pos));
	}

	for (int i = 0; i < N_SEG; i++) {
		int prev2 = (i - 3) & (N_SEG - 1);
		int next2 = (i + 3) & (N_SEG - 1);
		v3 right0 = v3_norm(v3_cross(world_up, trk[i].fwd));
		v3 up0 = v3_norm(v3_cross(trk[i].fwd, right0));
		float turn = v3_dot(v3_sub(trk[next2].fwd, trk[prev2].fwd), right0);
		trk[i].curv = turn;
		/* Smooth banking into curves (superelevation), flat across start/finish straight */
		float start_flat = (i < 10 || i > N_SEG - 10) ? 0.15f : 1.0f;
		float bank = clampf(turn * 1.15f * start_flat, -0.44f, 0.44f);
		trk[i].bank = bank;
		float cb = m_cosf(bank), sb = m_sinf(bank);
		trk[i].right = v3_add(v3_scale(right0, cb), v3_scale(up0, -sb));
		trk[i].up = v3_add(v3_scale(up0, cb), v3_scale(right0, sb));

		/* Tunnel sections: two dramatic enclosed light-tunnels per lap */
		trk[i].tunnel = ((i >= 36 && i <= 62) || (i >= 148 && i <= 176)) ? 1 : 0;

		/* Procedural cliff/scenery heights on left & right */
		float u = (float)i * (1.0f / (float)N_SEG);
		float nl = fbm2(u, 0.17f, 8, 3, 0x1100U + (uint32_t)gs.track_id * 37U);
		float nr = fbm2(u, 0.73f, 8, 3, 0x2200U + (uint32_t)gs.track_id * 53U);
		if (c->cliff_mode == 0 || c->cliff_mode == 3) {
			trk[i].cliff_l = 18.0f + nl * 52.0f;
			trk[i].cliff_r = 18.0f + nr * 52.0f;
		} else if (c->cliff_mode == 2) {
			trk[i].cliff_l = 16.0f + nl * 42.0f; /* island cliffs on left */
			trk[i].cliff_r = -14.0f;             /* open ocean on right */
		} else {
			trk[i].cliff_l = -26.0f + nl * 10.0f; /* viaduct dropoff */
			trk[i].cliff_r = -26.0f + nr * 10.0f;
		}

		/* Turbo boost pads & pit energy recharge strips */
		trk[i].pad_type = 0;
		trk[i].pad_lat = 0.0f;
		if (i >= 18 && i <= 20) {
			trk[i].pad_type = 1, trk[i].pad_lat = 0.0f;
		} else if ((i >= 54 && i <= 56) || (i >= 142 && i <= 144) || (i >= 228 && i <= 230)) {
			trk[i].pad_type = 1;
			trk[i].pad_lat = ((i >> 5) & 1) ? -5.5f : 5.5f;
		} else if (i >= 170 && i <= 178) {
			trk[i].pad_type = 2;
			trk[i].pad_lat = -8.5f;
		}
	}
}

static void sample_track(float seg, v3 *pos, v3 *right, v3 *up, v3 *fwd, float *curv, float *seg_len)
{
	while (seg < 0.0f)
		seg += (float)N_SEG;
	while (seg >= (float)N_SEG)
		seg -= (float)N_SEG;
	int i0 = (int)seg & (N_SEG - 1);
	int i1 = (i0 + 1) & (N_SEG - 1);
	float f = seg - (float)(int)seg;
	*pos = v3_make(lerpf(trk[i0].pos.x, trk[i1].pos.x, f),
		       lerpf(trk[i0].pos.y, trk[i1].pos.y, f),
		       lerpf(trk[i0].pos.z, trk[i1].pos.z, f));
	*fwd = v3_norm(v3_make(lerpf(trk[i0].fwd.x, trk[i1].fwd.x, f),
			       lerpf(trk[i0].fwd.y, trk[i1].fwd.y, f),
			       lerpf(trk[i0].fwd.z, trk[i1].fwd.z, f)));
	v3 r = v3_norm(v3_make(lerpf(trk[i0].right.x, trk[i1].right.x, f),
			       lerpf(trk[i0].right.y, trk[i1].right.y, f),
			       lerpf(trk[i0].right.z, trk[i1].right.z, f)));
	*right = r;
	*up = v3_norm(v3_cross(*fwd, r));
	if (curv)
		*curv = lerpf(trk[i0].curv, trk[i1].curv, f);
	if (seg_len)
		*seg_len = lerpf(trk[i0].len, trk[i1].len, f);
}

static void sync_racer_pose(struct racer *rc)
{
	v3 tpos, tr, tu, tf;
	sample_track(rc->seg, &tpos, &tr, &tu, &tf, NULL, NULL);
	rc->wpos = v3_add(tpos, v3_add(v3_scale(tr, rc->lat), v3_scale(tu, rc->hover_h)));

	/* Yaw in track plane, then roll around craft forward axis */
	float cy = m_cosf(rc->yaw_rel), sy = m_sinf(rc->yaw_rel);
	v3 bz = v3_norm(v3_add(v3_scale(tf, cy), v3_scale(tr, sy)));
	v3 bx0 = v3_norm(v3_add(v3_scale(tr, cy), v3_scale(tf, -sy)));
	float cr = m_cosf(rc->roll), sr = m_sinf(rc->roll);
	rc->bz = bz;
	rc->bx = v3_add(v3_scale(bx0, cr), v3_scale(tu, -sr));
	rc->by = v3_add(v3_scale(tu, cr), v3_scale(bx0, sr));
}

static void reset_race(int track_id)
{
	build_circuit(track_id);
	memset(sparks, 0, sizeof(sparks));
	gs.finished = 0;
	gs.countdown = gs.auto_play ? 0.0f : 3.0f;
	gs.banner_t = 2.4f;
	racer_fmt(gs.banner, sizeof(gs.banner), "%s", circuits[gs.track_id].name);

	/* Staggered 2x3 F1/AG starting grid behind start/finish line (player starts P4 or P1 in -check) */
	for (int i = 0; i < N_RACERS; i++) {
		struct racer *rc = &racers[i];
		memset(rc, 0, sizeof(*rc));
		int grid_slot = gs.check_mode ? i : (N_RACERS - 1 - i);
		rc->seg = (float)((N_SEG - 3 - grid_slot * 2) & (N_SEG - 1));
		rc->lat = gs.check_mode && i == 0 ? 0.0f : ((grid_slot & 1) ? 4.8f : -4.8f);
		rc->hover_h = 1.65f;
		rc->energy = 100.0f;
		rc->lap = -1;
		rc->half_ok = 1; /* starting just behind seg 0; crossing line begins lap 0 (LAP 1/3) */
		rc->rank = grid_slot;
		rc->progress = -(float)(grid_slot * 2 + 3);
		rc->ai_lane = rc->lat;
		rc->ai_skill = 0.87f + (float)i * 0.022f;
		if (gs.auto_play)
			rc->vel_fwd = 145.0f;
		sync_racer_pose(rc);
	}
	if (gs.check_mode) {
		racers[0].seg = 3.0f;
		racers[0].lat = 0.0f;
		racers[0].hover_h = 1.65f;
		sync_racer_pose(&racers[0]);
	}
}

/* --- Particle Sparks & Thruster Wake ------------------------------------------------------------ */

static void spawn_spark(v3 pos, v3 vel, float life, float size, uint32_t argb)
{
	struct spark *s = &sparks[spark_next];
	spark_next = (spark_next + 1) % MAX_SPARKS;
	s->pos = pos, s->vel = vel;
	s->life = s->max_life = life;
	s->size = size, s->argb = argb;
}

static void update_sparks(float dt)
{
	for (int i = 0; i < MAX_SPARKS; i++) {
		if (sparks[i].life <= 0.0f)
			continue;
		sparks[i].life -= dt;
		sparks[i].pos = v3_add(sparks[i].pos, v3_scale(sparks[i].vel, dt));
	}
}

/* --- Hovercraft Physics, AI Steering, Collisions, & Camera -------------------------------------- */

static void step_simulation(float dt, const struct plat_input *in)
{
	if (dt > 0.05f)
		dt = 0.05f;
	gs.time_s += dt;
	if (gs.banner_t > 0.0f)
		gs.banner_t -= dt;

	/* Countdown beep sequence (3 - 2 - 1 - GO!) */
	if (!gs.check_mode && gs.countdown > -1.0f) {
		float prev = gs.countdown;
		gs.countdown -= dt;
		if ((prev > 3.0f && gs.countdown <= 3.0f) ||
		    (prev > 2.0f && gs.countdown <= 2.0f) ||
		    (prev > 1.0f && gs.countdown <= 1.0f)) {
			syn.sfx_beep = 1.0f;
			syn.sfx_beep_hi = 0.0f;
		} else if (prev > 0.0f && gs.countdown <= 0.0f) {
			syn.sfx_beep = 1.0f;
			syn.sfx_beep_hi = 1.0f;
		}
	}

	int racing = (gs.countdown <= 0.0f) && !gs.check_mode;

	for (int i = 0; i < N_RACERS; i++) {
		struct racer *rc = &racers[i];
		v3 tpos, tr, tu, tf;
		float curv = 0.0f, slen = 10.0f;
		sample_track(rc->seg, &tpos, &tr, &tu, &tf, &curv, &slen);

		float steer = 0.0f, airbrake = 0.0f, throt = 0.0f, brk = 0.0f;
		int want_boost = 0;

		if (i == 0 && !gs.auto_play && !gs.finished) {
			steer = (float)in->steer_r - (float)in->steer_l + clampf((float)in->mdx * 0.028f, -1.0f, 1.0f);
			steer = clampf(steer, -1.0f, 1.0f);
			airbrake = (float)in->air_r - (float)in->air_l;
			throt = (in->throttle || in->mb_r) ? 1.0f : 0.0f;
			brk = in->brake ? 1.0f : 0.0f;
			want_boost = (in->boost || in->mb_l) ? 1 : 0;
		} else {
			/* AI / Autopilot: look ahead for curves & turbo pads, weave smoothly around traffic */
			rc->ai_lane_t -= dt;
			if (rc->ai_lane_t <= 0.0f) {
				rc->ai_lane_t = 1.4f + rng_f01(&gs.rng) * 2.0f;
				rc->ai_lane = rng_fsym(&gs.rng) * 7.5f;
			}
			int look_seg = ((int)rc->seg + 6) & (N_SEG - 1);
			float target_lat = rc->ai_lane;
			if (trk[look_seg].pad_type == 1 || (rc->energy < 55.0f && trk[look_seg].pad_type == 2))
				target_lat = trk[look_seg].pad_lat;
			float lat_err = target_lat - rc->lat;
			float des_yaw = clampf(lat_err * 0.065f + trk[look_seg].curv * 0.55f, -0.42f, 0.42f);
			steer = clampf((des_yaw - rc->yaw_rel) * 3.8f, -1.0f, 1.0f);
			throt = 1.0f;
			if (m_fabsf(trk[look_seg].curv) > 0.28f && rc->vel_fwd > 175.0f)
				airbrake = trk[look_seg].curv > 0.0f ? 0.65f : -0.65f;
			if (i == 0 && gs.auto_play && rc->energy > 68.0f && m_fabsf(curv) < 0.12f)
				want_boost = 1;
		}

		if (!racing) {
			throt = 0.0f, brk = 1.0f, steer = 0.0f, airbrake = 0.0f, want_boost = 0;
		}

		/* Manual capacitor turbo boost */
		if (want_boost && rc->energy >= 24.0f && rc->boost_t <= 0.05f) {
			rc->energy -= 24.0f;
			rc->boost_t = 1.15f;
			if (i == 0)
				syn.sfx_boost = 1.0f;
		}
		if (rc->boost_t > 0.0f)
			rc->boost_t -= dt;
		if (rc->pad_cd > 0.0f)
			rc->pad_cd -= dt;

		/* Forward acceleration, aerodynamic drag, airbrake drag, & turbo surge */
		float top_spd = (i == 0 ? 196.0f : 186.0f * rc->ai_skill) + (rc->boost_t > 0.0f ? 62.0f : 0.0f);
		float accel = throt * (rc->boost_t > 0.0f ? 155.0f : 92.0f) - brk * 125.0f;
		rc->vel_fwd += accel * dt;
		float drag = 0.36f + m_fabsf(airbrake) * 0.24f;
		rc->vel_fwd -= rc->vel_fwd * drag * dt;
		if (rc->vel_fwd > top_spd)
			rc->vel_fwd -= (rc->vel_fwd - top_spd) * 3.2f * dt;
		if (rc->vel_fwd < 0.0f)
			rc->vel_fwd = 0.0f;

		/* Steering, airbrake drift, & centrifugal cornering push */
		float turn_rate = (steer * 1.95f + airbrake * 1.15f);
		rc->yaw_rel += turn_rate * dt;
		rc->yaw_rel -= curv * (rc->vel_fwd / slen) * 0.14f * dt;
		rc->yaw_rel *= (1.0f - 2.6f * dt);
		rc->yaw_rel = clampf(rc->yaw_rel, -0.78f, 0.78f);

		float lat_push = m_sinf(rc->yaw_rel) * rc->vel_fwd - curv * rc->vel_fwd * 0.22f + airbrake * 18.0f;
		rc->vel_lat = lerpf(rc->vel_lat, lat_push, clampf(6.5f * dt, 0.0f, 1.0f));
		rc->lat += rc->vel_lat * dt;

		/* Visual craft banking roll + gentle anti-gravity hover spring */
		float target_roll = clampf((steer * 0.52f + airbrake * 0.38f), -0.68f, 0.68f);
		rc->roll = lerpf(rc->roll, target_roll, clampf(8.5f * dt, 0.0f, 1.0f));
		float bob = 1.62f + 0.16f * m_sinf(gs.time_s * 5.2f + (float)i * 1.3f);
		rc->vel_h += (bob - rc->hover_h) * 38.0f * dt - rc->vel_h * 6.5f * dt;
		rc->hover_h = clampf(rc->hover_h + rc->vel_h * dt, 0.85f, 3.6f);

		/* Guardrail collision + metallic spark shower */
		float wall_lim = TRACK_HALF_W - 1.85f;
		if (rc->lat < -wall_lim || rc->lat > wall_lim) {
			float side = rc->lat > 0.0f ? 1.0f : -1.0f;
			rc->lat = side * wall_lim;
			rc->vel_lat = -side * 12.0f;
			rc->yaw_rel *= 0.45f;
			rc->vel_fwd *= (1.0f - 0.85f * dt);
			rc->energy = clampf(rc->energy - 8.0f * dt, 5.0f, 100.0f);
			if (i == 0)
				syn.sfx_scrape = 0.85f;
			v3 sp_p = v3_add(rc->wpos, v3_scale(tr, side * 1.6f));
			for (int k = 0; k < 2; k++) {
				v3 sv = v3_make(rng_fsym(&gs.rng) * 14.0f, 4.0f + rng_f01(&gs.rng) * 12.0f, rng_fsym(&gs.rng) * 14.0f);
				spawn_spark(sp_p, sv, 0.28f, 0.65f, 0xffffc850U);
			}
		}

		/* Advance spline segment, lap counter, & turbo/recharge strip triggers */
		float ds = (m_cosf(rc->yaw_rel) * rc->vel_fwd * dt) / slen;
		float prev_seg = rc->seg;
		rc->seg += ds;
		rc->progress += ds;
		if (rc->seg >= (float)N_SEG) {
			rc->seg -= (float)N_SEG;
			if (rc->half_ok) {
				if (rc->lap >= 0 && rc->cur_lap_t > 5.0f) {
					if (rc->best_lap_t <= 0.0f || rc->cur_lap_t < rc->best_lap_t) {
						rc->best_lap_t = rc->cur_lap_t;
						if (i == 0) {
							gs.banner_t = 2.5f;
							racer_fmt(gs.banner, sizeof(gs.banner), "NEW BEST LAP!");
						}
					}
				}
				rc->lap++;
				rc->cur_lap_t = 0.0f;
				rc->half_ok = 0;
				if (rc->lap > 0)
					rc->energy = clampf(rc->energy + 22.0f, 0.0f, 100.0f);
				if (i == 0 && rc->lap > 0) {
					syn.sfx_lap = 1.0f;
					if (rc->lap >= TOTAL_LAPS) {
						if (gs.auto_play)
							reset_race((gs.track_id + 1) & 3);
						else
							gs.finished = 1;
					} else if (rc->lap == TOTAL_LAPS - 1) {
						gs.banner_t = 2.4f;
						racer_fmt(gs.banner, sizeof(gs.banner), "FINAL LAP!");
					}
				}
			}
		}
		if (prev_seg < (float)(N_SEG / 2) && rc->seg >= (float)(N_SEG / 2))
			rc->half_ok = 1;
		if (racing && !gs.finished)
			rc->cur_lap_t += dt;

		/* Track pad check */
		int iseg = (int)rc->seg & (N_SEG - 1);
		if (trk[iseg].pad_type == 1 && m_fabsf(rc->lat - trk[iseg].pad_lat) < 4.5f && rc->pad_cd <= 0.0f) {
			rc->boost_t = 1.25f;
			rc->pad_cd = 0.65f;
			rc->vel_h += 3.5f;
			if (i == 0)
				syn.sfx_boost = 1.0f;
		} else if (trk[iseg].pad_type == 2 && m_fabsf(rc->lat - trk[iseg].pad_lat) < 4.8f) {
			rc->energy = clampf(rc->energy + 45.0f * dt, 0.0f, 100.0f);
		}

		sync_racer_pose(rc);

		/* Emit glowing engine plasma trail particles at high speed */
		if (rc->vel_fwd > 40.0f && ((int)(gs.time_s * 60.0f) + i) % 2 == 0) {
			uint32_t fc = (190U << 24) | ((uint32_t)teams[i].fr << 16) | ((uint32_t)teams[i].fg << 8) | teams[i].fb;
			for (int s = -1; s <= 1; s += 2) {
				v3 noz = v3_add(rc->wpos, v3_add(v3_scale(rc->bz, -3.3f), v3_scale(rc->bx, 0.46f * (float)s)));
				spawn_spark(noz, v3_scale(rc->bz, -12.0f), 0.16f, rc->boost_t > 0.0f ? 1.15f : 0.72f, fc);
			}
		}
	}

	/* Craft-to-craft bump collisions */
	for (int i = 0; i < N_RACERS; i++) {
		for (int j = i + 1; j < N_RACERS; j++) {
			v3 d = v3_sub(racers[i].wpos, racers[j].wpos);
			float dist = v3_len(d);
			if (dist > 0.01f && dist < 3.4f) {
				float sep = (3.4f - dist) * 0.5f;
				float push = racers[i].lat >= racers[j].lat ? 1.0f : -1.0f;
				racers[i].lat += push * sep;
				racers[j].lat -= push * sep;
				racers[i].vel_lat += push * 14.0f;
				racers[j].vel_lat -= push * 14.0f;
				if (i == 0 || j == 0)
					syn.sfx_bump = 0.9f;
				spawn_spark(v3_scale(v3_add(racers[i].wpos, racers[j].wpos), 0.5f),
					    v3_make(0.0f, 8.0f, 0.0f), 0.25f, 0.9f, 0xffffe070U);
			}
		}
	}

	/* Compute live 1st..6th race standings */
	for (int i = 0; i < N_RACERS; i++) {
		int better = 0;
		for (int j = 0; j < N_RACERS; j++)
			if (j != i && racers[j].progress > racers[i].progress)
				better++;
		racers[i].rank = better;
	}

	update_sparks(dt);

	/* Update synthesizer engine pitch & boost intensity */
	syn.speed_norm = racers[0].vel_fwd * (1.0f / 196.0f);
	syn.boost_lvl = clampf(racers[0].boost_t, 0.0f, 1.0f);

	/* Update Chase / Nose-Cockpit Camera */
	const struct racer *pl = &racers[0];
	v3 tpos, tr, tu, tf;
	sample_track(pl->seg, &tpos, &tr, &tu, &tf, NULL, NULL);
	if (gs.cam_mode == 1 && !gs.check_mode) {
		/* First-person nose cockpit camera */
		cam.pos = v3_add(pl->wpos, v3_add(v3_scale(pl->by, 0.75f), v3_scale(pl->bz, 1.25f)));
		cam.fwd = pl->bz;
		cam.right = pl->bx;
		cam.up = pl->by;
	} else {
		/* Dynamic 90s 3dfx chase camera: trails craft along track tangent + craft heading */
		float back = 10.6f + clampf(pl->boost_t, 0.0f, 1.0f) * 1.6f;
		v3 chase_dir = v3_norm(v3_add(v3_scale(tf, 0.68f), v3_scale(pl->bz, 0.32f)));
		v3 des_pos = v3_add(pl->wpos, v3_add(v3_scale(chase_dir, -back), v3_scale(tu, 4.15f)));
		if (gs.check_mode) {
			cam.pos = des_pos;
		} else {
			float sm = clampf(14.0f * dt, 0.0f, 1.0f);
			cam.pos = v3_make(lerpf(cam.pos.x, des_pos.x, sm),
					  lerpf(cam.pos.y, des_pos.y, sm),
					  lerpf(cam.pos.z, des_pos.z, sm));
		}
		v3 look_at = v3_add(pl->wpos, v3_add(v3_scale(chase_dir, 9.5f), v3_scale(tu, 1.15f)));
		cam.fwd = v3_norm(v3_sub(look_at, cam.pos));
		v3 tilt_up = v3_norm(v3_add(tu, v3_make(0.0f, 0.55f, 0.0f)));
		cam.right = v3_norm(v3_cross(tilt_up, cam.fwd));
		cam.up = v3_norm(v3_cross(cam.fwd, cam.right));
	}
}

/* --- 3D World Rendering (Sky Dome, Track Ribbon, Cliffs/Water, Tunnels, Craft, Shadows) --------- */

static uint32_t scale_rgb(uint8_t r, uint8_t g, uint8_t b, float shade)
{
	return pack_argb(255, (int)(r * shade), (int)(g * shade), (int)(b * shade));
}

static void draw_sky_dome(const struct circuit_def *c)
{
	set_state(TEX_SKY, BLEND_NONE, DEPTH_OFF, 0, 1, CLAMP_WRAP, 0);
	int slices = 16;
	float rad = 1800.0f;
	uint32_t c_top = 0xff000000U | c->sky_top;
	uint32_t c_hor = 0xff000000U | c->sky_hor;
	uint32_t c_low = 0xff000000U | c->fog_rgb;
	float drift = gs.check_mode ? 0.0f : gs.time_s * 0.008f;

	for (int i = 0; i < slices; i++) {
		float a0 = (float)i * ((float)TAU / (float)slices);
		float a1 = (float)(i + 1) * ((float)TAU / (float)slices);
		float x0 = m_cosf(a0) * rad, z0 = m_sinf(a0) * rad;
		float x1 = m_cosf(a1) * rad, z1 = m_sinf(a1) * rad;
		float u0 = (float)i / (float)slices * 3.0f + drift;
		float u1 = (float)(i + 1) / (float)slices * 3.0f + drift;

		/* Upper atmospheric band */
		v3 p0 = v3_add(cam.pos, v3_make(x0, 950.0f, z0));
		v3 p1 = v3_add(cam.pos, v3_make(x1, 950.0f, z1));
		v3 p2 = v3_add(cam.pos, v3_make(x1, 35.0f, z1));
		v3 p3 = v3_add(cam.pos, v3_make(x0, 35.0f, z0));
		emit_quad_world(p0, p1, p2, p3, u0, 0.0f, u1, 0.0f, u1, 1.0f, u0, 1.0f,
				c_top, c_top, c_hor, c_hor);

		/* Horizon skirt below y=35 so banked rolls never show clear gaps */
		v3 p4 = v3_add(cam.pos, v3_make(x1, -700.0f, z1));
		v3 p5 = v3_add(cam.pos, v3_make(x0, -700.0f, z0));
		emit_quad_world(p3, p2, p4, p5, u0, 1.0f, u1, 1.0f, u1, 2.0f, u0, 2.0f,
				c_hor, c_hor, c_low, c_low);
	}

	/* Glowing sun / moon corona in the sky */
	v3 sun_pos = v3_add(cam.pos, v3_scale(cam.sun_dir, 1450.0f));
	uint32_t sun_c = c->cliff_mode == 1 ? 0xd0ff50d8U : c->cliff_mode == 3 ? 0xd0a8e8ffU : 0xe0ffe090U;
	draw_billboard(sun_pos, 240.0f, sun_c, 0);
	draw_billboard(sun_pos, 95.0f, 0xffffffffU, 0);
}

static void draw_track_and_scenery(const struct circuit_def *c)
{
	int base_seg = (int)racers[0].seg & (N_SEG - 1);
	/* Render segments around camera (-14 behind .. +92 ahead) so horizon fogs smoothly */
	int start_off = -14, end_off = 92;

	/* 1. Surrounding 3D Canyon Cliffs / Viaduct Grid / Ocean Water */
	set_state(TEX_TERRAIN, BLEND_NONE, DEPTH_RW, 1, 1, CLAMP_WRAP, 0);
	for (int d = start_off; d < end_off; d++) {
		int i0 = (base_seg + d) & (N_SEG - 1);
		int i1 = (i0 + 1) & (N_SEG - 1);
		const struct trk_node *n0 = &trk[i0], *n1 = &trk[i1];
		float tv0 = (float)i0 * 0.5f, tv1 = tv0 + 0.5f;

		v3 l_edge0 = v3_add(n0->pos, v3_scale(n0->right, -TRACK_HALF_W));
		v3 r_edge0 = v3_add(n0->pos, v3_scale(n0->right, TRACK_HALF_W));
		v3 l_edge1 = v3_add(n1->pos, v3_scale(n1->right, -TRACK_HALF_W));
		v3 r_edge1 = v3_add(n1->pos, v3_scale(n1->right, TRACK_HALF_W));

		v3 l_far0 = v3_add(l_edge0, v3_make(-n0->right.x * 58.0f, n0->cliff_l, -n0->right.z * 58.0f));
		v3 l_far1 = v3_add(l_edge1, v3_make(-n1->right.x * 58.0f, n1->cliff_l, -n1->right.z * 58.0f));
		v3 r_far0 = v3_add(r_edge0, v3_make(n0->right.x * 58.0f, n0->cliff_r, n0->right.z * 58.0f));
		v3 r_far1 = v3_add(r_edge1, v3_make(n1->right.x * 58.0f, n1->cliff_r, n1->right.z * 58.0f));

		float sh_l = 0.72f + 0.28f * clampf(n0->right.x * cam.sun_dir.x + n0->right.z * cam.sun_dir.z, -0.5f, 1.0f);
		float sh_r = 0.72f - 0.22f * clampf(n0->right.x * cam.sun_dir.x + n0->right.z * cam.sun_dir.z, -1.0f, 0.5f);
		uint32_t cl_lo = scale_rgb(c->ter_r, c->ter_g, c->ter_b, sh_l * 0.78f);
		uint32_t cl_hi = scale_rgb(c->ter_r, c->ter_g, c->ter_b, sh_l * 1.15f);
		uint32_t cr_lo = scale_rgb(c->ter_r, c->ter_g, c->ter_b, sh_r * 0.78f);
		uint32_t cr_hi = scale_rgb(c->ter_r, c->ter_g, c->ter_b, sh_r * 1.15f);

		emit_quad_world(l_far0, l_edge0, l_edge1, l_far1,
				0.0f, tv0, 2.0f, tv0, 2.0f, tv1, 0.0f, tv1,
				cl_hi, cl_lo, cl_lo, cl_hi);

		if (c->cliff_mode == 2) {
			/* Shimmering turquoise Pacific ocean stretching outward on the right */
			float wave = gs.check_mode ? 0.0f : gs.time_s * 0.25f;
			v3 sea_in0 = v3_make(r_edge0.x, 4.0f, r_edge0.z);
			v3 sea_in1 = v3_make(r_edge1.x, 4.0f, r_edge1.z);
			v3 sea_out0 = v3_add(sea_in0, v3_make(n0->right.x * 160.0f, 0.0f, n0->right.z * 160.0f));
			v3 sea_out1 = v3_add(sea_in1, v3_make(n1->right.x * 160.0f, 0.0f, n1->right.z * 160.0f));
			emit_quad_world(r_edge0, sea_in0, sea_in1, r_edge1,
					0.0f, tv0, 0.6f, tv0, 0.6f, tv1, 0.0f, tv1,
					0xffd8c898U, 0xff40b8d0U, 0xff40b8d0U, 0xffd8c898U);
			emit_quad_world(sea_in0, sea_out0, sea_out1, sea_in1,
					0.0f, tv0 + wave, 4.0f, tv0 + wave, 4.0f, tv1 + wave, 0.0f, tv1 + wave,
					0xff28c8e8U, 0xff1478b8U, 0xff1478b8U, 0xff28c8e8U);
		} else {
			emit_quad_world(r_edge0, r_far0, r_far1, r_edge1,
					0.0f, tv0, 2.0f, tv0, 2.0f, tv1, 0.0f, tv1,
					cr_lo, cr_hi, cr_hi, cr_lo);
		}
	}

	/* 2. Main Mipmapped Racing Roadbed + Raised Guardrails + Enclosed Tunnel Roofs */
	set_state(TEX_TRACK, BLEND_NONE, DEPTH_RW, 1, 1, CLAMP_S_WRAP_T, 0);
	for (int d = start_off; d < end_off; d++) {
		int i0 = (base_seg + d) & (N_SEG - 1);
		int i1 = (i0 + 1) & (N_SEG - 1);
		const struct trk_node *n0 = &trk[i0], *n1 = &trk[i1];
		float tv0 = (float)d * 0.5f, tv1 = tv0 + 0.5f;

		v3 l0 = v3_add(n0->pos, v3_scale(n0->right, -TRACK_HALF_W));
		v3 r0 = v3_add(n0->pos, v3_scale(n0->right, TRACK_HALF_W));
		v3 l1 = v3_add(n1->pos, v3_scale(n1->right, -TRACK_HALF_W));
		v3 r1 = v3_add(n1->pos, v3_scale(n1->right, TRACK_HALF_W));

		float sun_dot = clampf(v3_dot(n0->up, cam.sun_dir), 0.15f, 1.0f);
		float shade = n0->tunnel ? (((i0 & 3) == 0) ? 1.08f : 0.62f) : (0.58f + 0.52f * sun_dot);
		uint32_t rc_col = (i0 == 0) ? 0xffffffffU : scale_rgb(c->road_r, c->road_g, c->road_b, shade);
		emit_quad_world(l0, r0, r1, l1, 0.0f, tv0, 1.0f, tv0, 1.0f, tv1, 0.0f, tv1,
				rc_col, rc_col, rc_col, rc_col);

		/* Raised 3D inner guardrail walls on left & right */
		v3 lw0 = v3_add(l0, v3_scale(n0->up, 1.75f));
		v3 lw1 = v3_add(l1, v3_scale(n1->up, 1.75f));
		v3 rw0 = v3_add(r0, v3_scale(n0->up, 1.75f));
		v3 rw1 = v3_add(r1, v3_scale(n1->up, 1.75f));
		uint32_t wc = scale_rgb(c->curb_r, c->curb_g, c->curb_b, shade * 0.95f);
		emit_quad_world(lw0, l0, l1, lw1, 0.02f, tv0, 0.08f, tv0, 0.08f, tv1, 0.02f, tv1, wc, wc, wc, wc);
		emit_quad_world(r0, rw0, rw1, r1, 0.08f, tv0, 0.02f, tv0, 0.02f, tv1, 0.08f, tv1, wc, wc, wc, wc);

		/* Enclosed arched tunnel walls & ceiling ribs */
		if (n0->tunnel) {
			v3 tl0 = v3_add(n0->pos, v3_add(v3_scale(n0->right, -11.5f), v3_scale(n0->up, 10.5f)));
			v3 tr0 = v3_add(n0->pos, v3_add(v3_scale(n0->right, 11.5f), v3_scale(n0->up, 10.5f)));
			v3 tl1 = v3_add(n1->pos, v3_add(v3_scale(n1->right, -11.5f), v3_scale(n1->up, 10.5f)));
			v3 tr1 = v3_add(n1->pos, v3_add(v3_scale(n1->right, 11.5f), v3_scale(n1->up, 10.5f)));
			uint32_t tc = ((i0 & 3) == 0) ? 0xff78d8ffU : 0xff2c3852U;
			emit_quad_world(tl0, lw0, lw1, tl1, 0.2f, tv0, 0.5f, tv0, 0.5f, tv1, 0.2f, tv1, tc, wc, wc, tc);
			emit_quad_world(rw0, tr0, tr1, rw1, 0.5f, tv0, 0.2f, tv0, 0.2f, tv1, 0.5f, tv1, wc, tc, tc, wc);
			emit_quad_world(tl0, tr0, tr1, tl1, 0.2f, tv0, 0.8f, tv0, 0.8f, tv1, 0.2f, tv1, tc, tc, tc, tc);
		}
	}

	/* 3. Animated-UV Chevron Turbo Boost Pads & Energy Recharge Strips (DEPTH_RO) */
	set_state(TEX_BOOST, BLEND_ADD, DEPTH_RO, 1, 1, CLAMP_S_WRAP_T, 0);
	float uv_scroll = gs.check_mode ? 0.0f : gs.time_s * 3.4f;
	for (int d = -6; d < 76; d++) {
		int i0 = (base_seg + d) & (N_SEG - 1);
		if (!trk[i0].pad_type)
			continue;
		int i1 = (i0 + 1) & (N_SEG - 1);
		const struct trk_node *n0 = &trk[i0], *n1 = &trk[i1];
		float lat = n0->pad_lat, hw = 3.2f;
		v3 b0 = v3_add(n0->pos, v3_add(v3_scale(n0->right, lat - hw), v3_scale(n0->up, 0.14f)));
		v3 b1 = v3_add(n0->pos, v3_add(v3_scale(n0->right, lat + hw), v3_scale(n0->up, 0.14f)));
		v3 b2 = v3_add(n1->pos, v3_add(v3_scale(n1->right, lat + hw), v3_scale(n1->up, 0.14f)));
		v3 b3 = v3_add(n1->pos, v3_add(v3_scale(n1->right, lat - hw), v3_scale(n1->up, 0.14f)));
		uint32_t pc = n0->pad_type == 1 ? 0xff48f0ffU : 0xff40ff88U;
		float v0 = (float)d * 0.8f + uv_scroll;
		emit_quad_world(b0, b1, b2, b3, 0.0f, v0, 1.0f, v0, 1.0f, v0 + 0.8f, 0.0f, v0 + 0.8f, pc, pc, pc, pc);
	}

	/* 4. Overhead Start/Checkpoint Gantry Arches & Trackside Light Pylons */
	for (int d = -6; d < 78; d++) {
		int i0 = (base_seg + d) & (N_SEG - 1);
		const struct trk_node *n = &trk[i0];
		if ((i0 & 63) == 0) {
			float ar = i0 == 0 ? 255.0f : 185.0f;
			float ag = i0 == 0 ? 225.0f : 225.0f;
			draw_mesh_basis(MESH_ARCH, n->pos, n->right, n->up, n->fwd, 1.0f,
					ar, ag, 255.0f, TEX_HULL, 1);
		} else if (!n->tunnel && (i0 & 7) == 4) {
			for (int s = -1; s <= 1; s += 2) {
				v3 pp = v3_add(n->pos, v3_scale(n->right, (TRACK_HALF_W + 2.2f) * (float)s));
				draw_mesh_basis(MESH_PYLON, pp, n->right, n->up, n->fwd, 1.0f,
						210.0f, 225.0f, 250.0f, TEX_HULL, 1);
				v3 lp = v3_add(pp, v3_scale(n->up, 8.2f));
				uint32_t lc = c->cliff_mode == 1 ? 0xb0ff58e8U : 0xa070e8ffU;
				draw_billboard(lp, 2.2f, lc, 1);
			}
		}
	}
}

static void draw_racers_and_fx(void)
{
	/* 1. Projected dark hovercraft ground shadows hugging the road surface (DEPTH_RO, BLEND_ALPHA) */
	set_state(-1, BLEND_ALPHA, DEPTH_RO, 1, 0, CLAMP_ALL, 0);
	for (int i = 0; i < N_RACERS; i++) {
		if (i == 0 && gs.cam_mode == 1 && !gs.check_mode)
			continue;
		const struct racer *rc = &racers[i];
		v3 tpos, tr, tu, tf;
		sample_track(rc->seg, &tpos, &tr, &tu, &tf, NULL, NULL);
		v3 sc = v3_add(tpos, v3_add(v3_scale(tr, rc->lat), v3_scale(tu, 0.12f)));
		float cy = m_cosf(rc->yaw_rel), sy = m_sinf(rc->yaw_rel);
		v3 sf = v3_add(v3_scale(tf, cy), v3_scale(tr, sy));
		v3 sr = v3_add(v3_scale(tr, cy), v3_scale(tf, -sy));
		v3 p0 = v3_add(sc, v3_add(v3_scale(sr, -1.85f), v3_scale(sf, 3.3f)));
		v3 p1 = v3_add(sc, v3_add(v3_scale(sr, 1.85f), v3_scale(sf, 3.3f)));
		v3 p2 = v3_add(sc, v3_add(v3_scale(sr, 1.85f), v3_scale(sf, -3.1f)));
		v3 p3 = v3_add(sc, v3_add(v3_scale(sr, -1.85f), v3_scale(sf, -3.1f)));
		uint32_t sh = 0x9804060cU;
		emit_quad_world(p0, p1, p2, p3, 0, 0, 1, 0, 1, 1, 0, 1, sh, sh, sh, sh);
	}

	/* 2. 3D Sculpted Anti-Gravity Hovercraft Meshes */
	for (int i = 0; i < N_RACERS; i++) {
		if (i == 0 && gs.cam_mode == 1 && !gs.check_mode)
			continue;
		const struct racer *rc = &racers[i];
		draw_mesh_basis(i == 0 ? MESH_CRAFT_PLAYER : MESH_CRAFT_RIVAL,
				rc->wpos, rc->bx, rc->by, rc->bz, 1.0f,
				(float)teams[i].r, (float)teams[i].g, (float)teams[i].b, TEX_HULL, 1);
	}

	/* 3. Additive Twin Engine Plasma Plumes & Sparks */
	for (int i = 0; i < N_RACERS; i++) {
		if (i == 0 && gs.cam_mode == 1 && !gs.check_mode)
			continue;
		const struct racer *rc = &racers[i];
		float pulse = gs.check_mode ? 1.0f : (0.88f + 0.18f * m_sinf(gs.time_s * 38.0f + (float)i));
		float rad = (0.95f + clampf(rc->vel_fwd / 220.0f, 0.0f, 0.85f) + (rc->boost_t > 0.0f ? 0.75f : 0.0f)) * pulse;
		uint32_t fc = (235U << 24) | ((uint32_t)teams[i].fr << 16) | ((uint32_t)teams[i].fg << 8) | teams[i].fb;
		for (int s = -1; s <= 1; s += 2) {
			v3 noz = v3_add(rc->wpos, v3_add(v3_scale(rc->bz, -3.15f), v3_scale(rc->bx, 0.44f * (float)s)));
			draw_billboard(noz, rad, fc, 1);
			draw_billboard(noz, rad * 0.48f, 0xd8ffffffU, 1);
		}
	}

	for (int i = 0; i < MAX_SPARKS; i++) {
		if (sparks[i].life <= 0.0f)
			continue;
		float a = clampf(sparks[i].life / sparks[i].max_life, 0.0f, 1.0f);
		uint32_t c = (sparks[i].argb & 0x00ffffffU) | ((uint32_t)(a * 220.0f) << 24);
		draw_billboard(sparks[i].pos, sparks[i].size * (0.5f + 0.5f * a), c, 1);
	}
}

static void render_frame(void)
{
	const struct circuit_def *c = &circuits[gs.track_id];
	cur_st.tex = -99;
	batch_n = 0;

	/* Scene sun direction & atmospheric fog per circuit */
	cam.sun_dir = v3_norm(v3_make(0.42f, 0.68f, 0.60f));
	if (c->cliff_mode == 1) {
		cam.amb_r = 0.42f, cam.amb_g = 0.40f, cam.amb_b = 0.58f;
		cam.sun_r = 0.85f, cam.sun_g = 0.75f, cam.sun_b = 1.05f;
	} else {
		cam.amb_r = 0.46f, cam.amb_g = 0.46f, cam.amb_b = 0.50f;
		cam.sun_r = 0.92f, cam.sun_g = 0.88f, cam.sun_b = 0.82f;
	}

	cur_be->clear(c->fog_rgb);
	cur_be->fog(220.0f, 1550.0f, c->fog_rgb);

	draw_sky_dome(c);
	draw_track_and_scenery(c);
	draw_racers_and_fx();

	if (gs.hud_on)
		draw_hud();
	flush_tris();
}

/* --- Deterministic Pixel-Probe Self-Test (-check) ----------------------------------------------- */

static const int RES[][2] = {
	{640, 480}, {856, 480}, {800, 600}, {960, 720}, {1024, 768},
	{1280, 960}, {1280, 1024}, {1600, 1200}, {1920, 1080},
};
#define NRES (int)(sizeof(RES) / sizeof(RES[0]))

static struct {
	int x, y;
	uint8_t exp[3];
} chk_probes[4];

static int run_check_probes(void)
{
	if (!cur_be->read()) {
		racer_log("FAIL framebuffer readback returned 0");
		return 1;
	}
	int w = racer_view.w, h = racer_view.h;
	float u = (float)h / 480.0f;
	struct {
		const char *name;
		int x, y;
		int r_lo, r_hi, g_lo, g_hi, b_lo, b_hi;
		uint8_t exp[3];
	} probes[4] = {
		/* 1. Top-left telemetry panel background (0x0a1424) */
		{"hud_panel", (int)(195.0f * u), (int)(22.0f * u), 0, 42, 4, 52, 14, 78, {14, 23, 41}},
		/* 2. Upper-center Redrock Canyon cobalt sky dome */
		{"sky_dome", w / 2, h * 5 / 100, 8, 120, 18, 150, 45, 220, {27, 41, 79}},
		/* 3. Sunlit racing roadbed ahead of player craft */
		{"track_road", w / 2, h * 56 / 100, 45, 235, 40, 230, 40, 235, {92, 89, 88}},
		/* 4. Bottom-left energy bar fill (0x30f8a8 emerald) */
		{"energy_bar", (int)(120.0f * u), (int)(h - 22.0f * u), 16, 110, 195, 255, 120, 215, {48, 248, 168}},
	};
	int fails = 0;
	for (int i = 0; i < 4; i++) {
		uint8_t rgb[3] = {0, 0, 0};
		cur_be->pixel(probes[i].x, probes[i].y, rgb);
		chk_probes[i].x = probes[i].x;
		chk_probes[i].y = probes[i].y;
		chk_probes[i].exp[0] = probes[i].exp[0];
		chk_probes[i].exp[1] = probes[i].exp[1];
		chk_probes[i].exp[2] = probes[i].exp[2];
		int ok = rgb[0] >= probes[i].r_lo && rgb[0] <= probes[i].r_hi &&
			 rgb[1] >= probes[i].g_lo && rgb[1] <= probes[i].g_hi &&
			 rgb[2] >= probes[i].b_lo && rgb[2] <= probes[i].b_hi;
		racer_log("CHECK %-10s (%d,%d) rgb=(%d,%d,%d) -> %s",
			  probes[i].name, probes[i].x, probes[i].y, rgb[0], rgb[1], rgb[2], ok ? "OK" : "FAIL");
		if (!ok)
			fails++;
	}
	if (fails)
		racer_log("CHECK part=circuit FAIL %d of 4 probes", fails);
	else
		racer_log("CHECK part=circuit PASS 4 probes");
	return fails ? 1 : 0;
}

static int run_audiotest(void)
{
	atest.on = 1;
	atest.rate = 0;
	atest.sig_frames = 0;
	plat_audio_init(1);
	uint32_t t0 = plat_us(), done = 0;
	int status = 1;
	for (;;) {
		plat_audio_tick();
		uint32_t now = plat_us();
		if (!done && atest.rate && atest.sig_frames >= (uint32_t)AUDIOSIG_FRAMES(atest.rate))
			done = now ? now : 1;
		if (done && (uint32_t)(now - done) >= 500000U) {
			status = 0;
			break;
		}
		if ((!atest.rate && now - t0 > 2000000U) || now - t0 > 20000000U || plat_key() == RKEY_ESC)
			break;
		plat_sleep(5);
	}
	plat_audio_close();
	racer_log("AUDIOTEST rate=%d frames=%u of %d secs=%.2f", atest.rate, atest.sig_frames,
		  AUDIOSIG_FRAMES(atest.rate), (uint32_t)(plat_us() - t0) / 1e6);
	racer_log(!atest.rate ? "FAIL no audio device" : status ? "FAIL the signature did not play to the end" : "PASS");
	racer_log("CLOSED");
	return status;
}

static void usage(void)
{
	static const char *lines[] = {
		"usage: wshracer [-res WxH] [-track 1..4] [-auto] [-seed N] [-nosound] [-nohud]",
		"                [-gamma G] [-time S] [-check] [-bench N] [-hold S] [-wait S]",
		"                [-tag NAME] [-audiotest] [-api glide2|glide3|opengl] [-hostgl]",
		"race:  Arrows / WASD / Mouse steer+thrust+brake, Q/E airbrakes, Space/LMB turbo boost",
		"keys:  C chase/nose cam, 1-4 circuit, Enter next race, M music, F fps, G gamma, R res, Esc quit",
	};
	for (unsigned i = 0; i < sizeof(lines) / sizeof(lines[0]); i++)
		plat_out(lines[i]);
}

/* --- Entry Point -------------------------------------------------------------------------------- */

int racer_main(int argc, char **argv, const struct backend *be)
{
	int res_w = 640, res_h = 480;
	int track_arg = 0, sound_on = 1, bench_frames = 0, audiotest = 0;
	float gamma_val = 1.0f, max_time = 0.0f, hold_s = 0.0f, wait_s = 0.0f;
	uint32_t seed = 0x20263df8U;

	memset(&gs, 0, sizeof(gs));
	memset(&syn, 0, sizeof(syn));
	gs.hud_on = 1;
	syn.music_on = 1;

	for (int i = 1; i < argc; i++) {
		const char *a = argv[i];
		if (str_eq(a, "-h") || str_eq(a, "--help")) {
			usage();
			return 0;
		} else if (str_eq(a, "-res") && i + 1 < argc) {
			if (parse_res(argv[++i], &res_w, &res_h)) {
				racer_log("ERROR invalid -res");
				return 2;
			}
		} else if (str_eq(a, "-track") && i + 1 < argc) {
			int t = 1;
			if (parse_int(argv[++i], &t) || t < 1 || t > 4) {
				racer_log("ERROR -track is 1..4");
				return 2;
			}
			track_arg = t - 1;
		} else if (str_eq(a, "-seed") && i + 1 < argc) {
			int sv = 0;
			if (parse_int(argv[++i], &sv)) {
				racer_log("ERROR invalid -seed");
				return 2;
			}
			seed = (uint32_t)sv;
		} else if (str_eq(a, "-auto")) {
			gs.auto_play = 1;
		} else if (str_eq(a, "-nosound")) {
			sound_on = 0;
		} else if (str_eq(a, "-nohud")) {
			gs.hud_on = 0;
		} else if (str_eq(a, "-hud")) {
			gs.hud_on = 1;
		} else if (str_eq(a, "-check")) {
			gs.check_mode = 1;
		} else if (str_eq(a, "-audiotest")) {
			audiotest = 1;
		} else if (str_eq(a, "-bench") && i + 1 < argc) {
			if (parse_int(argv[++i], &bench_frames) || bench_frames <= 0) {
				racer_log("ERROR invalid -bench");
				return 2;
			}
		} else if (str_eq(a, "-gamma") && i + 1 < argc) {
			if (parse_float(argv[++i], &gamma_val) || gamma_val < 0.3f || gamma_val > 3.0f) {
				racer_log("ERROR invalid -gamma");
				return 2;
			}
		} else if (str_eq(a, "-time") && i + 1 < argc) {
			if (parse_float(argv[++i], &max_time) || max_time < 0.0f) {
				racer_log("ERROR invalid -time");
				return 2;
			}
		} else if (str_eq(a, "-hold") && i + 1 < argc) {
			if (parse_float(argv[++i], &hold_s) || hold_s < 0.0f) {
				racer_log("ERROR invalid -hold");
				return 2;
			}
		} else if (str_eq(a, "-wait") && i + 1 < argc) {
			if (parse_float(argv[++i], &wait_s) || wait_s < 0.0f) {
				racer_log("ERROR invalid -wait");
				return 2;
			}
		} else if (str_eq(a, "-tag") && i + 1 < argc) {
			log_tag = argv[++i];
		} else if (str_eq(a, "-api") && i + 1 < argc) {
			i++;
		} else if (str_eq(a, "-hostgl") || str_eq(a, "-nocom")) {
			/* Handled by platform front-end */
		} else if (str_eq(a, "-log") && i + 1 < argc) {
			i++;
		}
	}

	if (audiotest)
		return run_audiotest();

	const char *mode = (gs.check_mode && bench_frames > 0) ? "check+bench" :
			   gs.check_mode ? "check" : bench_frames > 0 ? "bench" : gs.auto_play ? "auto" : "game";
	racer_log("START api=%s res=%dx%d mode=%s", be->name, res_w, res_h, mode);

	if (!be->res_ok(res_w, res_h)) {
		char ok[160];
		int len = 0;
		ok[0] = 0;
		for (int i = 0; i < NRES; i++)
			if (be->res_ok(RES[i][0], RES[i][1]))
				len += racer_fmt(ok + len, (int)sizeof(ok) - len, "%s%dx%d", len ? " " : "", RES[i][0], RES[i][1]);
		racer_log("ERROR %s can't open %dx%d (it can: %s)", be->name, res_w, res_h, ok);
		racer_log("CLOSED");
		return 2;
	}

	if (wait_s > 0.0f) {
		int steps = (int)(wait_s * 50.0f);
		for (int s = 0; s < steps && plat_key() != RKEY_ESC; s++)
			plat_sleep(20);
	}

	cur_be = be;
	racer_view.w = res_w;
	racer_view.h = res_h;
	racer_view.f = (float)((double)res_h * 0.866);

	uint32_t t_open = plat_us();
	if (be->open(res_w, res_h) != 0) {
		racer_log("ERROR no %s device", be->name);
		racer_log("CLOSED");
		return 2;
	}

	char wrev[96];
	const char *wr = plat_wrapper_rev(wrev, sizeof(wrev)) ? wrev : "not found";
	racer_log("VERSION %s, wrapper %s, opened %dx%d in %u ms",
		  be->version(), wr, res_w, res_h, (uint32_t)(plat_us() - t_open) / 1000U);

	if (gamma_val != 1.0f)
		be->gamma(gamma_val);

	gen_textures(be);
	gen_meshes();
	gs.rng = seed;
	reset_race(gs.check_mode ? 0 : track_arg);

	struct plat_input zero_in;
	memset(&zero_in, 0, sizeof(zero_in));

	if (gs.check_mode || bench_frames > 0) {
		int rc = 0;
		if (bench_frames > 0) {
			gs.check_mode = 0;
			gs.auto_play = 1;
			reset_race(track_arg);
			uint32_t bt0 = plat_us();
			for (int f = 0; f < bench_frames; f++) {
				step_simulation(1.0f / 60.0f, &zero_in);
				render_frame();
				be->swap(0);
			}
			double secs = (double)(uint32_t)(plat_us() - bt0) * 1e-6;
			racer_log("BENCH part=circuit frames=%d secs=%.2f fps=%.1f",
				  bench_frames, secs, secs > 1e-6 ? (double)bench_frames / secs : 0.0);
		}
		if (str_eq(mode, "check") || str_eq(mode, "check+bench")) {
			gs.check_mode = 1;
			gs.auto_play = 0;
			gs.hud_on = 1;
			reset_race(0);
			step_simulation(0.016f, &zero_in);
			render_frame();
			be->swap(0);
			render_frame();
			rc = run_check_probes();
			be->swap(1);
		}
		if (hold_s > 0.0f) {
			if (gs.check_mode) {
				for (int i = 0; i < 4; i++)
					racer_log("PROBE %d %d %02x%02x%02x", chk_probes[i].x, chk_probes[i].y,
						  chk_probes[i].exp[0], chk_probes[i].exp[1], chk_probes[i].exp[2]);
			}
			racer_log("FRAME");
			uint32_t h0 = plat_us();
			while ((uint32_t)(plat_us() - h0) < (uint32_t)(hold_s * 1e6f)) {
				if (plat_key() == RKEY_ESC)
					break;
				plat_sleep(20);
			}
		}
		if (gamma_val != 1.0f)
			be->gamma(1.0f);
		be->close(1);
		racer_log(rc == 0 ? "PASS" : "FAIL check probes failed");
		racer_log("CLOSED");
		return rc;
	}

	if (sound_on && !bench_frames)
		plat_audio_init(1);

	if (bench_frames > 0)
		gs.auto_play = 1;

	uint32_t t_start = plat_us(), t_prev = t_start, fps_t0 = t_start;
	int fps_frames = 0, ri = 0;
	for (int i = 0; i < NRES; i++)
		if (RES[i][0] == res_w && RES[i][1] == res_h)
			ri = i;

	for (;;) {
		uint32_t now = plat_us();
		float dt = (float)(uint32_t)(now - t_prev) * 1e-6f;
		t_prev = now;

		int quit = 0;
		for (int k = plat_key(); k; k = plat_key()) {
			if (k == RKEY_ESC) {
				quit = 1;
				break;
			} else if (k == 'c' || k == 'C' || k == 'v' || k == 'V') {
				gs.cam_mode ^= 1;
			} else if (k >= '1' && k <= '4') {
				reset_race(k - '1');
			} else if (k == RKEY_ENTER) {
				reset_race((gs.track_id + 1) & 3);
			} else if (k == 'f' || k == 'F') {
				gs.show_fps ^= 1;
			} else if (k == 'h' || k == 'H') {
				gs.hud_on ^= 1;
			} else if (k == 'm' || k == 'M') {
				syn.music_on ^= 1;
			} else if (k == 'p' || k == 'P') {
				gs.auto_play ^= 1;
			} else if (k == 'g' || k == 'G') {
				gamma_val += 0.2f;
				if (gamma_val > 1.9f)
					gamma_val = 1.0f;
				be->gamma(gamma_val);
			} else if (k == 'r' || k == 'R') {
				int n = ri;
				do
					n = (n + 1) % NRES;
				while (n != ri && !be->res_ok(RES[n][0], RES[n][1]));
				if (n != ri) {
					int nw = RES[n][0], nh = RES[n][1];
					be->close(0);
					if (be->open(nw, nh) == 0) {
						ri = n;
						res_w = nw, res_h = nh;
						racer_view.w = nw, racer_view.h = nh;
						racer_view.f = (float)((double)nh * 0.866);
						gen_textures(be);
					} else {
						be->open(res_w, res_h);
						gen_textures(be);
					}
					if (gamma_val != 1.0f)
						be->gamma(gamma_val);
				}
			}
		}
		if (quit)
			break;

		struct plat_input in;
		memset(&in, 0, sizeof(in));
		plat_poll_input(&in);

		step_simulation(dt, &in);
		render_frame();
		be->swap(1);
		plat_audio_tick();

		fps_frames++;
		gs.ft_hist[gs.ft_pos] = dt * 1000.0f;
		gs.ft_pos = (gs.ft_pos + 1) & 63;

		uint32_t fps_el = now - fps_t0;
		if (fps_el >= 500000U) {
			gs.fps_disp = (float)fps_frames * 1e6f / (float)fps_el;
			fps_frames = 0;
			fps_t0 = now;
		}

		if (max_time > 0.0f && (float)(uint32_t)(now - t_start) * 1e-6f >= max_time) {
			racer_log("PASS");
			break;
		}
	}

	if (hold_s > 0.0f) {
		uint32_t h0 = plat_us();
		while ((uint32_t)(plat_us() - h0) < (uint32_t)(hold_s * 1e6f)) {
			if (plat_key() == RKEY_ESC)
				break;
			plat_sleep(10);
		}
	}

	plat_audio_close();
	be->close(1);
	racer_log("CLOSED");
	return 0;
}
