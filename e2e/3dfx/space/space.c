/*
 * space.c: wshspace's portable game core, without a C library or libm (see space.h).
 * Generates a 18-system procedural galaxy, stars, planets with rings, displaced 3D asteroids of
 * four mineral classes, collectible crystals, orbital ring stations, hostile interceptor drones,
 * 6DoF cockpit flight, hyperspace warp tunnels and soft-synth audio.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <stdarg.h>
#include <stddef.h>

#include "space.h"
#include "font.h"
#include "audiosig.h" /* e2e/wisp: the build scripts add -I for it */

void *memset(void *d, int c, size_t n);
void *memcpy(void *d, const void *s, size_t n);

static const char *tag = "WSHSPACE";

/* --- string formatting & wrapper build-string scanner ----------------------------------------- */

static int fmt_v(char *buf, int n, const char *f, va_list ap)
{
	int o = 0;
#define PUT(c)                       \
	do {                         \
		if (o < n - 1)       \
			buf[o] = (c); \
		o++;                 \
	} while (0)
	for (; *f; f++) {
		if (*f != '%') {
			PUT(*f);
			continue;
		}
		f++;
		int zero = 0, width = 0, prec = -1;
		if (*f == '0')
			zero = 1, f++;
		while (*f >= '0' && *f <= '9')
			width = width * 10 + (*f++ - '0');
		if (*f == '.') {
			prec = 0;
			for (f++; *f >= '0' && *f <= '9'; f++)
				prec = prec * 10 + (*f - '0');
		}
		char tmp[40];
		int len = 0, neg = 0;
		const char *s = tmp;
		switch (*f) {
		case 's':
			s = va_arg(ap, const char *);
			if (!s)
				s = "(null)";
			while (s[len] && (prec < 0 || len < prec))
				len++;
			break;
		case 'c':
			tmp[0] = (char)va_arg(ap, int);
			len = 1;
			break;
		case 'd':
		case 'u':
		case 'x': {
			uint32_t v;
			if (*f == 'd') {
				int32_t d = va_arg(ap, int32_t);
				neg = d < 0;
				v = neg ? (uint32_t)-d : (uint32_t)d;
			} else {
				v = va_arg(ap, uint32_t);
			}
			uint32_t base = *f == 'x' ? 16U : 10U;
			char r[12];
			int k = 0;
			do {
				r[k++] = "0123456789abcdef"[v % base];
				v /= base;
			} while (v);
			if (neg)
				tmp[len++] = '-';
			while (len + k < width && zero)
				tmp[len++] = '0';
			while (k)
				tmp[len++] = r[--k];
			break;
		}
		case 'f': {
			double d = va_arg(ap, double);
			if (prec < 0)
				prec = 2;
			if (d < 0)
				tmp[len++] = '-', d = -d;
			double scale = 1.0;
			for (int i = 0; i < prec; i++)
				scale *= 10.0;
			if (d > 4e9 / scale)
				d = 4e9 / scale;
			uint32_t sc_u = (uint32_t)scale;
			uint32_t whole = (uint32_t)(d * scale + 0.5);
			uint32_t ip = whole / sc_u, fp = whole % sc_u;
			char r[12];
			int k = 0;
			do {
				r[k++] = (char)('0' + ip % 10U);
				ip /= 10U;
			} while (ip);
			while (k)
				tmp[len++] = r[--k];
			if (prec) {
				tmp[len++] = '.';
				for (int i = prec - 1; i >= 0; i--) {
					uint32_t div = 1U;
					for (int j = 0; j < i; j++)
						div *= 10U;
					tmp[len++] = (char)('0' + (fp / div) % 10U);
				}
			}
			break;
		}
		default:
			tmp[0] = *f;
			len = 1;
			break;
		}
		for (int i = len; i < width && !zero; i++)
			PUT(' ');
		for (int i = 0; i < len; i++)
			PUT(s[i]);
	}
	if (n > 0)
		buf[o < n ? o : n - 1] = 0;
	return o;
#undef PUT
}

int space_fmt(char *buf, int n, const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	int r = fmt_v(buf, n, fmt, ap);
	va_end(ap);
	return r;
}

void space_log(const char *fmt, ...)
{
	char line[512];
	int o = space_fmt(line, sizeof(line), "%s: ", tag);
	va_list ap;
	va_start(ap, fmt);
	fmt_v(line + o, (int)sizeof(line) - o, fmt, ap);
	va_end(ap);
	plat_out(line);
}

static int str_eq(const char *a, const char *b)
{
	while (*a && *a == *b)
		a++, b++;
	return *a == *b;
}

static int to_int(const char *s)
{
	int v = 0;
	while (*s >= '0' && *s <= '9')
		v = v * 10 + (*s++ - '0');
	return v;
}

static int is_hex(uint8_t c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'); }
static int is_dig(uint8_t c) { return c >= '0' && c <= '9'; }

int space_find_buildstr(const uint8_t *b, uint32_t len, char *out, int n)
{
	for (uint32_t p = 28; p + 6 <= len; p++) {
		if (b[p] != ' ' || b[p + 1] != 'b' || b[p + 2] != 'u' || b[p + 3] != 'i' || b[p + 4] != 'l' || b[p + 5] != 'd')
			continue;
		const uint8_t *s = b + p - 28;
		int ok = s[7] == '-' && s[10] == ':' && s[13] == ':' && s[16] == ' ' && s[20] == ' ' && s[23] == ' ';
		for (int i = 0; ok && i < 7; i++)
			ok = is_hex(s[i]);
		ok = ok && is_dig(s[8]) && is_dig(s[9]) && is_dig(s[24]) && is_dig(s[27]) && is_dig(s[22]);
		if (!ok)
			continue;
		char rev[8], date[12], tm[9];
		memcpy(rev, s, 7), rev[7] = 0;
		memcpy(date, s + 17, 11), date[11] = 0;
		memcpy(tm, s + 8, 8), tm[8] = 0;
		space_fmt(out, n, "%s (built %s %s)", rev, date, tm);
		return 1;
	}
	return 0;
}

#include "gen.h"
#include "render.h"

/* --- galaxy, star systems & game state -------------------------------------------------------- */

#define N_SYSTEMS    18
#define MAX_PLANETS  4
#define MAX_AST      56
#define MAX_CRYSTALS 48
#define MAX_BOLTS    48
#define MAX_PARTS    96
#define MAX_DRONES   8
#define N_STARS      220
#define N_DUST       48

enum { ORE_FE, ORE_FUEL, ORE_AU, ORE_PLAS, ORE_COUNT };
enum { SCR_TITLE, SCR_PLAY, SCR_MAP, SCR_UPGRADE, SCR_WARP };

static const char *ore_names[4] = {"FE", "FUEL", "AU", "PLAS"};
static const uint32_t ore_cols[4] = {0xffd8bfa0U, 0xff50e0ffU, 0xffffd848U, 0xff70ff98U};
static const float ore_tints[4][3] = {
	{0.88f, 0.80f, 0.72f},
	{0.58f, 0.88f, 1.00f},
	{1.00f, 0.84f, 0.44f},
	{0.55f, 1.00f, 0.74f}
};

struct star_sys {
	char name[24];
	float gx, gy;
	int spectral, danger, has_station;
	uint32_t seed;
	float star_rgb[3];
	float neb_rgb[3];
};

struct planet {
	v3f pos;
	float rad;
	float tint[3];
	int has_ring;
	uint32_t ring_col;
	float tilt_x, tilt_z, u_off;
};

struct asteroid {
	int active, mesh_id, ore, tier;
	v3f pos, vel;
	float rad, hp, max_hp;
	float rx, ry, vrx, vry;
	float hit_flash;
};

struct crystal {
	int active, ore, amount;
	v3f pos, vel;
	float life, phase;
};

struct bolt {
	int active, from_player;
	v3f pos, vel;
	float life, dmg;
	uint32_t col;
};

struct particle {
	int active;
	v3f pos, vel;
	float life, max_life, size;
	uint32_t col;
};

struct drone {
	int active;
	v3f pos, vel;
	float rx, ry;
	float hp, max_hp, cd, hit_flash, phase;
};

static struct {
	uint32_t galaxy_seed, rng;
	struct star_sys sys[N_SYSTEMS];
	int cur_sys, nav_sys;

	v3f star_pos;
	float star_rad;
	int has_station;
	v3f st_pos;
	float st_rad, st_rot;

	int n_planets;
	struct planet planets[MAX_PLANETS];
	struct asteroid ast[MAX_AST];
	struct crystal crys[MAX_CRYSTALS];
	struct bolt bolts[MAX_BOLTS];
	struct particle parts[MAX_PARTS];
	struct drone drones[MAX_DRONES];

	v3f sky_dir[N_STARS];
	uint32_t sky_col[N_STARS];
	float sky_sz[N_STARS];
	v3f dust[N_DUST];

	/* Player ship */
	v3f pos, vel, right, up, fwd;
	float hull, max_hull, shield, max_shield, energy, fuel, max_fuel;
	float throttle, fire_cd, shield_flash, muzzle_flash, sway_x, sway_y;
	int cargo[ORE_COUNT];
	int lvl_laser, lvl_shield, lvl_engine, lvl_tractor;
	int score, jumps, kills, mined;
	int tgt_kind, tgt_idx;
	int near_station;

	/* Modes */
	int screen;
	float warp_t;
	char msg[80];
	float msg_t;
	int autopilot;
	float auto_timer;
} gs;

static void set_msg(const char *s)
{
	int i = 0;
	while (s[i] && i < (int)sizeof(gs.msg) - 1) {
		gs.msg[i] = s[i];
		i++;
	}
	gs.msg[i] = 0;
	gs.msg_t = 3.2f;
}

static float jump_dist(int a, int b)
{
	float dx = gs.sys[a].gx - gs.sys[b].gx;
	float dy = gs.sys[a].gy - gs.sys[b].gy;
	return m_sqrtf(dx * dx + dy * dy);
}

static int jump_fuel_cost(int a, int b)
{
	if (a == b)
		return 0;
	int c = (int)(jump_dist(a, b) * 75.0f) + 8;
	return c;
}

static void spawn_particle(v3f pos, v3f vel, float size, float life, uint32_t col)
{
	for (int i = 0; i < MAX_PARTS; i++) {
		if (!gs.parts[i].active) {
			gs.parts[i].active = 1;
			gs.parts[i].pos = pos;
			gs.parts[i].vel = vel;
			gs.parts[i].size = size;
			gs.parts[i].life = gs.parts[i].max_life = life;
			gs.parts[i].col = col;
			return;
		}
	}
}

static void spawn_explosion(v3f pos, float scale, uint32_t col, int count)
{
	for (int i = 0; i < count; i++) {
		v3f dir = v3_norm(v3_make(rnd_next(&gs.rng) * 2.0f - 1.0f,
					  rnd_next(&gs.rng) * 2.0f - 1.0f,
					  rnd_next(&gs.rng) * 2.0f - 1.0f));
		float sp = (8.0f + rnd_next(&gs.rng) * 38.0f) * scale;
		spawn_particle(pos, v3_scale(dir, sp), (1.8f + rnd_next(&gs.rng) * 3.5f) * scale,
			       0.35f + rnd_next(&gs.rng) * 0.55f, col);
	}
}

static void spawn_crystal(v3f pos, int ore, int amount)
{
	for (int i = 0; i < MAX_CRYSTALS; i++) {
		if (!gs.crys[i].active) {
			gs.crys[i].active = 1;
			gs.crys[i].ore = ore;
			gs.crys[i].amount = amount;
			gs.crys[i].pos = pos;
			gs.crys[i].vel = v3_make((rnd_next(&gs.rng) - 0.5f) * 14.0f,
						 (rnd_next(&gs.rng) - 0.5f) * 14.0f,
						 (rnd_next(&gs.rng) - 0.5f) * 14.0f);
			gs.crys[i].life = 45.0f;
			gs.crys[i].phase = rnd_next(&gs.rng) * 6.28f;
			return;
		}
	}
}

static int spawn_asteroid(v3f pos, int tier, int ore, uint32_t *sd)
{
	for (int i = 0; i < MAX_AST; i++) {
		if (!gs.ast[i].active) {
			struct asteroid *a = &gs.ast[i];
			a->active = 1;
			a->tier = tier;
			a->ore = ore;
			a->mesh_id = MESH_AST0 + ((int)(*sd >> 4) & 3);
			a->pos = pos;
			a->vel = v3_make((rnd_next(sd) - 0.5f) * (tier == 0 ? 10.0f : 3.0f),
					 (rnd_next(sd) - 0.5f) * (tier == 0 ? 10.0f : 2.0f),
					 (rnd_next(sd) - 0.5f) * (tier == 0 ? 10.0f : 3.0f));
			a->rad = tier == 2 ? (14.0f + rnd_next(sd) * 10.0f) :
				 tier == 1 ? (7.5f  + rnd_next(sd) * 4.5f) :
					     (3.8f  + rnd_next(sd) * 2.2f);
			a->max_hp = a->hp = tier == 2 ? 55.0f : tier == 1 ? 26.0f : 12.0f;
			a->rx = rnd_next(sd) * 6.28f;
			a->ry = rnd_next(sd) * 6.28f;
			a->vrx = (rnd_next(sd) - 0.5f) * 1.1f;
			a->vry = (rnd_next(sd) - 0.5f) * 1.1f;
			a->hit_flash = 0.0f;
			return i;
		}
	}
	return -1;
}

static void init_galaxy(uint32_t seed)
{
	static const char *p1[18] = {
		"SOLARIS", "VEGA", "CYGNUS", "KRONOS", "ALTAIR", "ORION",
		"LYRA", "DRACO", "SIRIUS", "TAU", "EPSILON", "NOVA",
		"RIGEL", "ANTARES", "DENEB", "CASTOR", "CAPELLA", "HYDRA"
	};
	static const char *p2[8] = {
		"PRIME", "BELT", "RIFT", "REACH", "GATE", "FORGE", "HAVEN", "CORE"
	};
	static const float s_cols[4][3] = {
		{0.72f, 0.88f, 1.00f}, /* O/B Blue Giant */
		{1.00f, 0.93f, 0.76f}, /* G Solar Yellow */
		{1.00f, 0.62f, 0.42f}, /* M Red Giant */
		{0.62f, 1.00f, 0.88f}  /* Emerald Pulsar */
	};
	static const float n_cols[4][3] = {
		{0.14f, 0.28f, 0.58f},
		{0.22f, 0.16f, 0.44f},
		{0.48f, 0.14f, 0.18f},
		{0.10f, 0.44f, 0.38f}
	};

	gs.galaxy_seed = seed;
	uint32_t s = seed;
	for (int i = 0; i < N_SYSTEMS; i++) {
		struct star_sys *sy = &gs.sys[i];
		sy->seed = hash32(seed ^ ((uint32_t)i * 0x9e3779b9U));
		/* Spread cleanly across 6x3 jittered cells so no two stars overlap on the starmap */
		int col = i % 6, row = i / 6;
		sy->gx = (col + 0.22f + 0.56f * rnd_next(&s)) / 6.0f;
		sy->gy = (row + 0.22f + 0.56f * rnd_next(&s)) / 3.0f;
		sy->spectral = i == 0 ? 1 : ((int)(sy->seed >> 3) & 3);
		sy->danger = i == 0 ? 0 : clampi((col * 4) / 5 + ((int)(sy->seed >> 7) & 1), 1, 4);
		sy->has_station = (i == 0) ? 1 : (((sy->seed >> 11) % 3U) != 0U);
		memcpy(sy->star_rgb, s_cols[sy->spectral], sizeof(sy->star_rgb));
		memcpy(sy->neb_rgb, n_cols[sy->spectral], sizeof(sy->neb_rgb));
		space_fmt(sy->name, sizeof(sy->name), "%s %s", p1[i], p2[(sy->seed >> 14) & 7U]);
	}
}

static void load_system(int idx, int arrive_from_warp)
{
	gs.cur_sys = idx;
	/* Pick nearest neighbor as default nav target if nav_sys == cur_sys */
	if (gs.nav_sys == idx) {
		float best = 999.0f;
		for (int i = 0; i < N_SYSTEMS; i++) {
			if (i == idx)
				continue;
			float d = jump_dist(idx, i);
			if (d < best) {
				best = d;
				gs.nav_sys = i;
			}
		}
	}
	const struct star_sys *sy = &gs.sys[idx];
	uint32_t sd = sy->seed;
	gs.rng = sd ^ 0x5a5a5a5aU;
	syn.sys_key = sd;
	syn.mood = 0;

	memset(gs.ast, 0, sizeof(gs.ast));
	memset(gs.crys, 0, sizeof(gs.crys));
	memset(gs.bolts, 0, sizeof(gs.bolts));
	memset(gs.parts, 0, sizeof(gs.parts));
	memset(gs.drones, 0, sizeof(gs.drones));
	gs.tgt_kind = 0;

	/* Central blazing star */
	gs.star_pos = v3_make(-420.0f, 190.0f, 1480.0f);
	gs.star_rad = 135.0f + rnd_next(&sd) * 45.0f;

	/* Skybox stars */
	for (int i = 0; i < N_STARS; i++) {
		float z = rnd_next(&sd) * 2.0f - 1.0f;
		float a = rnd_next(&sd) * (float)TAU;
		float r = m_sqrtf(1.0f - z * z);
		gs.sky_dir[i] = v3_make(r * m_cosf(a), z, r * m_sinf(a));
		int br = 130 + (int)(rnd_next(&sd) * 125.0f);
		int tint = (int)(rnd_next(&sd) * 45.0f);
		gs.sky_col[i] = pack_argb(255, br, br - tint / 2, clampi(br + tint, 0, 255));
		gs.sky_sz[i] = 0.8f + rnd_next(&sd) * 1.4f;
	}

	/* Orbital Outpost Station */
	gs.has_station = sy->has_station;
	gs.st_pos = v3_make(125.0f, -18.0f, 250.0f);
	gs.st_rad = 46.0f;

	/* Procedural Planets (3..4 per system, at least 1 ringed giant) */
	gs.n_planets = 3 + ((int)sd & 1);
	for (int i = 0; i < gs.n_planets; i++) {
		struct planet *p = &gs.planets[i];
		float ang = 0.45f + (float)i * 1.35f + rnd_next(&sd) * 0.4f;
		float dist = 680.0f + (float)i * 340.0f;
		p->pos = v3_make(m_sinf(ang) * dist, (rnd_next(&sd) - 0.45f) * 220.0f, 380.0f + m_cosf(ang) * dist);
		p->rad = 48.0f + rnd_next(&sd) * 68.0f;
		p->tint[0] = 0.45f + rnd_next(&sd) * 0.55f;
		p->tint[1] = 0.45f + rnd_next(&sd) * 0.55f;
		p->tint[2] = 0.50f + rnd_next(&sd) * 0.50f;
		p->has_ring = (i == 0) || (rnd_next(&sd) > 0.55f);
		p->ring_col = pack_argb(175, (int)(p->tint[0] * 230), (int)(p->tint[1] * 215), (int)(p->tint[2] * 245));
		p->tilt_x = 0.35f + rnd_next(&sd) * 0.5f;
		p->tilt_z = (rnd_next(&sd) - 0.5f) * 0.7f;
		p->u_off = rnd_next(&sd);
	}

	/* Asteroid belt right ahead of arrival zone so action starts immediately */
	int n_ast = 34 + sy->danger * 4;
	if (n_ast > MAX_AST - 12)
		n_ast = MAX_AST - 12;
	for (int i = 0; i < n_ast; i++) {
		float a = (rnd_next(&sd) - 0.5f) * 2.6f;
		float d = 75.0f + rnd_next(&sd) * 560.0f;
		v3f p = v3_make(m_sinf(a) * d, (rnd_next(&sd) - 0.5f) * 130.0f, m_cosf(a) * d + 40.0f);
		float r = rnd_next(&sd);
		int ore = r < 0.34f ? ORE_FE : r < 0.64f ? ORE_FUEL : r < (0.88f - sy->danger * 0.04f) ? ORE_AU : ORE_PLAS;
		int tier = rnd_next(&sd) > 0.38f ? 2 : 1;
		spawn_asteroid(p, tier, ore, &sd);
	}

	/* Hostile Sentinel / Pirate Drones in dangerous systems */
	int nd = sy->danger == 0 ? 0 : (sy->danger + 1);
	if (nd > MAX_DRONES)
		nd = MAX_DRONES;
	for (int i = 0; i < nd; i++) {
		struct drone *d = &gs.drones[i];
		d->active = 1;
		float a = (rnd_next(&sd) - 0.5f) * 2.0f;
		float dist = 240.0f + rnd_next(&sd) * 320.0f;
		d->pos = v3_make(m_sinf(a) * dist, (rnd_next(&sd) - 0.5f) * 90.0f, m_cosf(a) * dist + 120.0f);
		d->vel = v3_make(0, 0, 0);
		d->max_hp = d->hp = 28.0f + sy->danger * 10.0f;
		d->cd = 1.5f + rnd_next(&sd) * 2.0f;
		d->phase = rnd_next(&sd) * 6.28f;
	}

	/* Reset player ship at jump-in point facing into the system */
	gs.pos = v3_make(0.0f, 0.0f, 0.0f);
	gs.vel = v3_make(0.0f, 0.0f, arrive_from_warp ? 42.0f : 0.0f);
	gs.right = v3_make(1.0f, 0.0f, 0.0f);
	gs.up    = v3_make(0.0f, 1.0f, 0.0f);
	gs.fwd   = v3_make(0.0f, 0.0f, 1.0f);

	for (int i = 0; i < N_DUST; i++) {
		gs.dust[i] = v3_make((rnd_next(&sd) - 0.5f) * 120.0f,
				     (rnd_next(&sd) - 0.5f) * 120.0f,
				     (rnd_next(&sd) - 0.5f) * 120.0f);
	}

	char banner[72];
	space_fmt(banner, sizeof(banner), "ARRIVED IN %s", sy->name);
	set_msg(banner);
}

static void init_new_game(uint32_t seed)
{
	memset(&gs, 0, sizeof(gs));
	init_galaxy(seed);
	gs.lvl_laser = 1;
	gs.lvl_shield = 1;
	gs.lvl_engine = 1;
	gs.lvl_tractor = 1;
	gs.max_hull = gs.hull = 100.0f;
	gs.max_shield = gs.shield = 100.0f;
	gs.energy = 100.0f;
	gs.max_fuel = gs.fuel = 100.0f;
	gs.cargo[ORE_FE] = 2;
	gs.cargo[ORE_FUEL] = 2;
	gs.nav_sys = 1;
	load_system(0, 0);
	gs.screen = SCR_TITLE;
}

static void start_warp(void)
{
	if (gs.nav_sys == gs.cur_sys) {
		set_msg("SELECT ANOTHER STAR SYSTEM ON STARMAP (M)");
		return;
	}
	float max_d = 0.36f + gs.lvl_engine * 0.04f;
	if (jump_dist(gs.cur_sys, gs.nav_sys) > max_d) {
		set_msg("DESTINATION OUT OF JUMP RANGE - UPGRADE THRUSTERS");
		return;
	}
	int cost = jump_fuel_cost(gs.cur_sys, gs.nav_sys);
	if (gs.fuel < (float)cost) {
		set_msg("LOW WARP FUEL - MINE CRYO-FUEL ASTEROIDS OR PRESS U");
		return;
	}
	gs.fuel -= (float)cost;
	gs.screen = SCR_WARP;
	gs.warp_t = 0.0f;
	syn.mood = 2;
	synth_trigger(SFX_WARP);
}

static void try_upgrade(int slot)
{
	if (slot == 1 && gs.lvl_laser < 5) {
		int c = gs.lvl_laser * 4;
		if (gs.cargo[ORE_AU] >= c && gs.cargo[ORE_FE] >= c) {
			gs.cargo[ORE_AU] -= c; gs.cargo[ORE_FE] -= c;
			gs.lvl_laser++;
			synth_trigger(SFX_PICKUP);
			set_msg("PLASMA LASERS UPGRADED!");
			return;
		}
	} else if (slot == 2 && gs.lvl_shield < 5) {
		int c = gs.lvl_shield * 3;
		if (gs.cargo[ORE_PLAS] >= c && gs.cargo[ORE_FE] >= c) {
			gs.cargo[ORE_PLAS] -= c; gs.cargo[ORE_FE] -= c;
			gs.lvl_shield++;
			gs.max_shield = 100.0f + (gs.lvl_shield - 1) * 35.0f;
			gs.shield = gs.max_shield;
			synth_trigger(SFX_PICKUP);
			set_msg("DEFLECTOR SHIELDS UPGRADED!");
			return;
		}
	} else if (slot == 3 && gs.lvl_engine < 5) {
		int c = gs.lvl_engine * 4;
		if (gs.cargo[ORE_PLAS] >= c && gs.cargo[ORE_AU] >= c) {
			gs.cargo[ORE_PLAS] -= c; gs.cargo[ORE_AU] -= c;
			gs.lvl_engine++;
			synth_trigger(SFX_PICKUP);
			set_msg("HYPER THRUSTERS & JUMP RANGE UPGRADED!");
			return;
		}
	} else if (slot == 4 && gs.lvl_tractor < 5) {
		int c = gs.lvl_tractor * 3;
		if (gs.cargo[ORE_AU] >= c && gs.cargo[ORE_FUEL] >= c) {
			gs.cargo[ORE_AU] -= c; gs.cargo[ORE_FUEL] -= c;
			gs.lvl_tractor++;
			synth_trigger(SFX_PICKUP);
			set_msg("TRACTOR BEAM & MINING YIELD UPGRADED!");
			return;
		}
	} else if (slot == 5) {
		if (gs.cargo[ORE_FUEL] >= 2 && gs.fuel < gs.max_fuel) {
			gs.cargo[ORE_FUEL] -= 2;
			gs.fuel = clampf(gs.fuel + 35.0f, 0.0f, gs.max_fuel);
			synth_trigger(SFX_PICKUP);
			set_msg("WARP FUEL REFINED (+35)");
			return;
		}
	} else if (slot == 6) {
		if (gs.cargo[ORE_FE] >= 3 && gs.hull < gs.max_hull) {
			gs.cargo[ORE_FE] -= 3;
			gs.hull = clampf(gs.hull + 40.0f, 0.0f, gs.max_hull);
			synth_trigger(SFX_PICKUP);
			set_msg("HULL PLATING REPAIRED (+40)");
			return;
		}
	}
	set_msg("INSUFFICIENT RESOURCES OR MAX LEVEL");
}

/* --- 6DoF orientation helpers, targeting & weapons -------------------------------------------- */

static void ship_rotate(v3f *a, v3f *b, float ang)
{
	float c = m_cosf(ang), s = m_sinf(ang);
	v3f na = v3_add(v3_scale(*a, c), v3_scale(*b, s));
	v3f nb = v3_sub(v3_scale(*b, c), v3_scale(*a, s));
	*a = na;
	*b = nb;
}

static void ship_orthonormalize(void)
{
	gs.fwd = v3_norm(gs.fwd);
	gs.right = v3_norm(v3_cross(gs.up, gs.fwd));
	gs.up = v3_cross(gs.fwd, gs.right);
}

static void lock_best_target(void)
{
	float best_score = 99999.0f;
	int bkind = 0, bidx = 0;
	for (int i = 0; i < MAX_DRONES; i++) {
		if (!gs.drones[i].active)
			continue;
		v3f v = world_to_view(gs.drones[i].pos);
		if (v.z > 2.0f && v.z < 1200.0f) {
			float off = (m_fabsf(v.x) + m_fabsf(v.y)) / v.z;
			float sc = off * 400.0f + v.z * 0.2f;
			if (sc < best_score) { best_score = sc; bkind = 2; bidx = i; }
		}
	}
	if (!bkind) {
		for (int i = 0; i < MAX_AST; i++) {
			if (!gs.ast[i].active)
				continue;
			v3f v = world_to_view(gs.ast[i].pos);
			if (v.z > 2.0f && v.z < 900.0f) {
				float off = (m_fabsf(v.x) + m_fabsf(v.y)) / v.z;
				float sc = off * 500.0f + v.z * 0.35f;
				if (sc < best_score) { best_score = sc; bkind = 1; bidx = i; }
			}
		}
	}
	if (!bkind && gs.has_station) {
		bkind = 3; bidx = 0;
	}
	gs.tgt_kind = bkind;
	gs.tgt_idx = bidx;
}

static void fire_bolt(v3f pos, v3f dir, v3f base_vel, int from_player, float dmg, uint32_t col)
{
	for (int i = 0; i < MAX_BOLTS; i++) {
		if (!gs.bolts[i].active) {
			gs.bolts[i].active = 1;
			gs.bolts[i].from_player = from_player;
			gs.bolts[i].pos = pos;
			gs.bolts[i].vel = v3_add(base_vel, v3_scale(dir, from_player ? 260.0f : 175.0f));
			gs.bolts[i].life = 2.6f;
			gs.bolts[i].dmg = dmg;
			gs.bolts[i].col = col;
			return;
		}
	}
}

static void player_fire(void)
{
	float cd = 0.22f - (gs.lvl_laser - 1) * 0.025f;
	if (gs.fire_cd > 0.0f)
		return;
	gs.fire_cd = cd;
	gs.muzzle_flash = 1.0f;
	float dmg = 9.0f + (gs.lvl_laser - 1) * 4.5f;
	uint32_t col = gs.lvl_laser >= 4 ? 0xff70ff98U : gs.lvl_laser >= 2 ? 0xff50e8ffU : 0xffffa840U;

	/* Converge dual wingtip cannons onto reticle distance */
	float conv_d = 180.0f;
	if (gs.tgt_kind == 1 && gs.ast[gs.tgt_idx].active)
		conv_d = clampf(v3_len(v3_sub(gs.ast[gs.tgt_idx].pos, gs.pos)), 30.0f, 600.0f);
	else if (gs.tgt_kind == 2 && gs.drones[gs.tgt_idx].active)
		conv_d = clampf(v3_len(v3_sub(gs.drones[gs.tgt_idx].pos, gs.pos)), 30.0f, 600.0f);
	v3f aim_pt = v3_add(gs.pos, v3_scale(gs.fwd, conv_d));

	v3f muzzle_l = v3_add(gs.pos, v3_add(v3_scale(gs.right, -1.8f), v3_add(v3_scale(gs.up, -0.7f), v3_scale(gs.fwd, 2.2f))));
	v3f muzzle_r = v3_add(gs.pos, v3_add(v3_scale(gs.right,  1.8f), v3_add(v3_scale(gs.up, -0.7f), v3_scale(gs.fwd, 2.2f))));
	fire_bolt(muzzle_l, v3_norm(v3_sub(aim_pt, muzzle_l)), gs.vel, 1, dmg, col);
	fire_bolt(muzzle_r, v3_norm(v3_sub(aim_pt, muzzle_r)), gs.vel, 1, dmg, col);
	if (gs.lvl_laser >= 3) {
		v3f muzzle_c = v3_add(gs.pos, v3_add(v3_scale(gs.up, -0.9f), v3_scale(gs.fwd, 2.6f)));
		fire_bolt(muzzle_c, v3_norm(v3_sub(aim_pt, muzzle_c)), gs.vel, 1, dmg * 0.85f, 0xffffffffU);
	}
	synth_trigger(SFX_LASER);
}

/* Autopilot AI for -auto showcase mode: mines asteroids, scoops crystals, fights drones & warps */
static void update_autopilot(float dt, struct plat_input *in)
{
	gs.auto_timer += dt;
	if (gs.screen == SCR_TITLE) {
		if (gs.auto_timer > 1.8f) {
			gs.screen = SCR_PLAY;
			gs.auto_timer = 0.0f;
		}
		return;
	}
	if (gs.screen != SCR_PLAY)
		return;

	/* Every ~22 seconds in autopilot, engage hyperspace jump to next reachable star system */
	if (gs.auto_timer > 22.0f) {
		gs.auto_timer = 0.0f;
		gs.fuel = gs.max_fuel;
		float max_d = 0.36f + gs.lvl_engine * 0.04f;
		for (int k = 1; k <= N_SYSTEMS; k++) {
			int cand = (gs.cur_sys + k) % N_SYSTEMS;
			if (cand != gs.cur_sys && jump_dist(gs.cur_sys, cand) <= max_d) {
				gs.nav_sys = cand;
				start_warp();
				return;
			}
		}
	}

	/* Steer towards nearest crystal, active drone, or asteroid */
	v3f goal = v3_add(gs.pos, v3_scale(gs.fwd, 100.0f));
	int want_fire = 0;
	float best_d = 9999.0f;
	for (int i = 0; i < MAX_CRYSTALS; i++) {
		if (!gs.crys[i].active)
			continue;
		float d = v3_len(v3_sub(gs.crys[i].pos, gs.pos));
		if (d < 220.0f && d < best_d) { best_d = d; goal = gs.crys[i].pos; want_fire = 0; }
	}
	if (best_d > 900.0f) {
		for (int i = 0; i < MAX_DRONES; i++) {
			if (!gs.drones[i].active)
				continue;
			float d = v3_len(v3_sub(gs.drones[i].pos, gs.pos));
			if (d < best_d) { best_d = d; goal = gs.drones[i].pos; want_fire = 1; gs.tgt_kind = 2; gs.tgt_idx = i; }
		}
	}
	if (best_d > 900.0f) {
		for (int i = 0; i < MAX_AST; i++) {
			if (!gs.ast[i].active)
				continue;
			float d = v3_len(v3_sub(gs.ast[i].pos, gs.pos));
			if (d > 28.0f && d < best_d) { best_d = d; goal = gs.ast[i].pos; want_fire = 1; gs.tgt_kind = 1; gs.tgt_idx = i; }
		}
	}

	v3f v = world_to_view(goal);
	if (v.x >  4.0f) in->held |= IN_YAW_RIGHT;
	if (v.x < -4.0f) in->held |= IN_YAW_LEFT;
	if (v.y >  4.0f) in->held |= IN_PITCH_UP;
	if (v.y < -4.0f) in->held |= IN_PITCH_DOWN;
	if (best_d > 55.0f)
		in->held |= IN_THRUST;
	else if (best_d < 32.0f)
		in->held |= IN_BRAKE;
	if (want_fire && v.z > 15.0f && v.z < 420.0f && m_fabsf(v.x) < v.z * 0.22f && m_fabsf(v.y) < v.z * 0.22f)
		in->held |= IN_FIRE;
}

/* --- world simulation tick -------------------------------------------------------------------- */

static void sim_step(float dt, const struct plat_input *in)
{
	if (gs.msg_t > 0.0f)
		gs.msg_t -= dt;
	if (gs.fire_cd > 0.0f)
		gs.fire_cd -= dt;
	gs.shield_flash *= (1.0f - clampf(dt * 4.0f, 0.0f, 1.0f));
	gs.muzzle_flash *= (1.0f - clampf(dt * 12.0f, 0.0f, 1.0f));
	gs.st_rot += dt * 0.28f;

	if (gs.screen == SCR_TITLE) {
		/* Slow cinematic orbit camera on title screen */
		ship_rotate(&gs.fwd, &gs.right, dt * 0.09f);
		ship_orthonormalize();
		syn.thrust_amt = 0.0f;
		return;
	}
	if (gs.screen == SCR_WARP) {
		gs.warp_t += dt;
		syn.thrust_amt = 0.9f;
		if (gs.warp_t >= 2.5f) {
			gs.jumps++;
			gs.score += 100;
			load_system(gs.nav_sys, 1);
			gs.screen = SCR_PLAY;
		}
		return;
	}
	if (gs.screen != SCR_PLAY) {
		syn.thrust_amt = 0.0f;
		return;
	}

	/* 1. 6DoF flight controls */
	float turn_rate = 1.45f + (gs.lvl_engine - 1) * 0.14f;
	float pitch_in = 0.0f, yaw_in = 0.0f, roll_in = 0.0f;
	if (in->held & IN_PITCH_UP)   pitch_in += 1.0f;
	if (in->held & IN_PITCH_DOWN) pitch_in -= 1.0f;
	if (in->held & IN_YAW_RIGHT)  yaw_in   += 1.0f;
	if (in->held & IN_YAW_LEFT)   yaw_in   -= 1.0f;
	if (in->held & IN_ROLL_RIGHT) roll_in  += 1.0f;
	if (in->held & IN_ROLL_LEFT)  roll_in  -= 1.0f;
	if (in->mlook) {
		yaw_in   += clampf((float)in->mdx * 0.09f, -2.2f, 2.2f);
		pitch_in -= clampf((float)in->mdy * 0.09f, -2.2f, 2.2f);
	}

	ship_rotate(&gs.fwd, &gs.up,    pitch_in * turn_rate * dt);
	ship_rotate(&gs.fwd, &gs.right, yaw_in   * turn_rate * dt);
	ship_rotate(&gs.right, &gs.up,  (roll_in * 1.8f - yaw_in * 0.25f) * dt);
	ship_orthonormalize();

	gs.sway_x += (-yaw_in * 0.6f - gs.sway_x) * clampf(dt * 6.0f, 0.0f, 1.0f);
	gs.sway_y += (pitch_in * 0.6f - gs.sway_y) * clampf(dt * 6.0f, 0.0f, 1.0f);

	float max_spd = 85.0f + (gs.lvl_engine - 1) * 18.0f;
	int boosting = (in->held & IN_BOOST) && gs.energy > 5.0f;
	if (boosting) {
		max_spd *= 1.75f;
		gs.energy = clampf(gs.energy - 28.0f * dt, 0.0f, 100.0f);
	} else {
		gs.energy = clampf(gs.energy + 16.0f * dt, 0.0f, 100.0f);
	}

	if (in->held & IN_THRUST)
		gs.throttle = clampf(gs.throttle + 1.4f * dt, 0.0f, 1.0f);
	else if (in->held & IN_BRAKE)
		gs.throttle = clampf(gs.throttle - 1.8f * dt, 0.0f, 1.0f);

	float target_spd = boosting ? max_spd : gs.throttle * max_spd;
	v3f desired_v = v3_scale(gs.fwd, target_spd);
	gs.vel = v3_add(gs.vel, v3_scale(v3_sub(desired_v, gs.vel), clampf(dt * 2.6f, 0.0f, 1.0f)));
	if ((in->held & IN_BRAKE) && gs.throttle <= 0.01f)
		gs.vel = v3_scale(gs.vel, 1.0f - clampf(dt * 3.0f, 0.0f, 1.0f));
	gs.pos = v3_add(gs.pos, v3_scale(gs.vel, dt));

	syn.thrust_amt = boosting ? 1.0f : gs.throttle * 0.65f;
	gs.shield = clampf(gs.shield + (3.5f + gs.lvl_shield * 1.6f) * dt, 0.0f, gs.max_shield);

	if (in->held & IN_FIRE)
		player_fire();
	if (gs.tgt_kind == 0)
		lock_best_target();

	/* Check Orbital Station proximity (auto-repairs hull & unlocks station services) */
	gs.near_station = 0;
	if (gs.has_station) {
		float sd = v3_len(v3_sub(gs.st_pos, gs.pos));
		if (sd < 105.0f) {
			gs.near_station = 1;
			gs.hull = clampf(gs.hull + 20.0f * dt, 0.0f, gs.max_hull);
			gs.shield = clampf(gs.shield + 20.0f * dt, 0.0f, gs.max_shield);
		}
		if (sd < gs.st_rad * 0.55f) {
			v3f push = v3_norm(v3_sub(gs.pos, gs.st_pos));
			gs.pos = v3_add(gs.st_pos, v3_scale(push, gs.st_rad * 0.56f));
		}
	}

	/* 2. Asteroids physics & ship collision */
	for (int i = 0; i < MAX_AST; i++) {
		struct asteroid *a = &gs.ast[i];
		if (!a->active)
			continue;
		a->pos = v3_add(a->pos, v3_scale(a->vel, dt));
		a->rx += a->vrx * dt;
		a->ry += a->vry * dt;
		if (a->hit_flash > 0.0f)
			a->hit_flash -= dt * 4.0f;
		v3f diff = v3_sub(gs.pos, a->pos);
		float d = v3_len(diff);
		if (d < a->rad + 2.8f) {
			v3f n = d > 0.01f ? v3_scale(diff, 1.0f / d) : v3_make(0, 0, 1);
			gs.pos = v3_add(a->pos, v3_scale(n, a->rad + 3.0f));
			gs.vel = v3_scale(n, 28.0f);
			gs.shield -= 16.0f;
			if (gs.shield < 0.0f) { gs.hull += gs.shield; gs.shield = 0.0f; }
			gs.shield_flash = 1.0f;
			synth_trigger(SFX_SHIELD);
		}
	}

	/* 3. Resource crystals + Tractor beam magnet */
	float pull_r = 38.0f + (gs.lvl_tractor - 1) * 22.0f;
	for (int i = 0; i < MAX_CRYSTALS; i++) {
		struct crystal *c = &gs.crys[i];
		if (!c->active)
			continue;
		c->life -= dt;
		c->phase += dt * 4.0f;
		if (c->life <= 0.0f) {
			c->active = 0;
			continue;
		}
		v3f to_ship = v3_sub(gs.pos, c->pos);
		float d = v3_len(to_ship);
		if (d < pull_r && d > 0.1f) {
			v3f pull = v3_scale(to_ship, (1.0f / d) * (75.0f + gs.lvl_tractor * 18.0f));
			c->vel = v3_add(c->vel, v3_scale(v3_sub(pull, c->vel), clampf(dt * 6.0f, 0.0f, 1.0f)));
		} else {
			c->vel = v3_scale(c->vel, 1.0f - clampf(dt * 1.2f, 0.0f, 1.0f));
		}
		c->pos = v3_add(c->pos, v3_scale(c->vel, dt));
		if (d < 6.5f) {
			c->active = 0;
			int gain = c->amount + (gs.lvl_tractor >= 3 ? 1 : 0);
			gs.cargo[c->ore] += gain;
			if (c->ore == ORE_FUEL)
				gs.fuel = clampf(gs.fuel + 10.0f * gain, 0.0f, gs.max_fuel);
			gs.score += 25 * gain;
			gs.mined += gain;
			synth_trigger(SFX_PICKUP);
			char m[64];
			space_fmt(m, sizeof(m), "SCOOPED +%d %s", gain, ore_names[c->ore]);
			set_msg(m);
		}
	}

	/* 4. Hostile Sentinel / Pirate Drones AI */
	int any_combat = 0;
	for (int i = 0; i < MAX_DRONES; i++) {
		struct drone *d = &gs.drones[i];
		if (!d->active)
			continue;
		v3f to_p = v3_sub(gs.pos, d->pos);
		float dist = v3_len(to_p);
		if (dist < 520.0f)
			any_combat = 1;
		d->phase += dt * 2.1f;
		if (d->hit_flash > 0.0f)
			d->hit_flash -= dt * 4.0f;

		v3f dir = dist > 0.1f ? v3_scale(to_p, 1.0f / dist) : v3_make(0, 0, 1);
		/* Orbit / weave when close, pursue when far */
		v3f side = v3_norm(v3_make(-dir.z, m_sinf(d->phase) * 0.5f, dir.x));
		v3f wish = dist > 110.0f ? v3_add(v3_scale(dir, 0.85f), v3_scale(side, 0.45f)) :
			   dist < 55.0f  ? v3_add(v3_scale(dir, -0.7f), side) : side;
		wish = v3_scale(v3_norm(wish), 52.0f + gs.sys[gs.cur_sys].danger * 6.0f);
		d->vel = v3_add(d->vel, v3_scale(v3_sub(wish, d->vel), clampf(dt * 2.2f, 0.0f, 1.0f)));
		d->pos = v3_add(d->pos, v3_scale(d->vel, dt));

		/* Face velocity / player */
		v3f face = dist < 340.0f ? dir : v3_norm(d->vel);
		d->ry = m_atan2f(face.x, face.z);
		d->rx = -m_atan2f(face.y, m_sqrtf(face.x * face.x + face.z * face.z));

		d->cd -= dt;
		if (d->cd <= 0.0f && dist < 380.0f && dist > 20.0f) {
			d->cd = 1.65f - gs.sys[gs.cur_sys].danger * 0.14f;
			fire_bolt(d->pos, dir, d->vel, 0, 8.0f + gs.sys[gs.cur_sys].danger * 2.0f, 0xffff3830U);
		}
	}
	syn.mood = any_combat ? 1 : 0;

	/* 5. Laser bolts & hit detection */
	for (int i = 0; i < MAX_BOLTS; i++) {
		struct bolt *b = &gs.bolts[i];
		if (!b->active)
			continue;
		b->life -= dt;
		if (b->life <= 0.0f) {
			b->active = 0;
			continue;
		}
		b->pos = v3_add(b->pos, v3_scale(b->vel, dt));

		if (b->from_player) {
			/* Hit asteroids */
			for (int j = 0; j < MAX_AST; j++) {
				struct asteroid *a = &gs.ast[j];
				if (!a->active)
					continue;
				v3f d = v3_sub(b->pos, a->pos);
				if (v3_dot(d, d) <= (a->rad + 1.8f) * (a->rad + 1.8f)) {
					b->active = 0;
					a->hp -= b->dmg;
					a->hit_flash = 1.0f;
					spawn_explosion(b->pos, 0.55f, ore_cols[a->ore], 6);
					if (a->hp <= 0.0f) {
						v3f apos = a->pos;
						int ore = a->ore, tier = a->tier;
						a->active = 0;
						spawn_explosion(apos, tier == 2 ? 1.5f : 1.0f, 0xffffa040U, 18);
						synth_trigger(SFX_BOOM);
						int drops = tier + 1;
						for (int k = 0; k < drops; k++)
							spawn_crystal(apos, ore, 1);
						if (tier > 0) {
							spawn_asteroid(v3_add(apos, v3_make(3.0f, 1.0f, 0)), tier - 1, ore, &gs.rng);
							spawn_asteroid(v3_add(apos, v3_make(-3.0f, -1.0f, 2.0f)), tier - 1, ore, &gs.rng);
						}
						gs.score += 40 * (tier + 1);
					} else {
						synth_trigger(SFX_HIT);
					}
					break;
				}
			}
			/* Hit hostile drones */
			if (!b->active)
				continue;
			for (int j = 0; j < MAX_DRONES; j++) {
				struct drone *dr = &gs.drones[j];
				if (!dr->active)
					continue;
				v3f d = v3_sub(b->pos, dr->pos);
				if (v3_dot(d, d) <= 42.0f) {
					b->active = 0;
					dr->hp -= b->dmg;
					dr->hit_flash = 1.0f;
					spawn_explosion(b->pos, 0.7f, 0xffff6030U, 8);
					if (dr->hp <= 0.0f) {
						dr->active = 0;
						spawn_explosion(dr->pos, 1.8f, 0xffff8030U, 24);
						synth_trigger(SFX_BOOM);
						spawn_crystal(dr->pos, ORE_PLAS, 2);
						spawn_crystal(dr->pos, ORE_AU, 2);
						gs.kills++;
						gs.score += 150;
						set_msg("SENTINEL DRONE DESTROYED!");
					} else {
						synth_trigger(SFX_HIT);
					}
					break;
				}
			}
		} else {
			/* Enemy plasma bolt vs Player ship */
			v3f d = v3_sub(b->pos, gs.pos);
			if (v3_dot(d, d) <= 18.0f) {
				b->active = 0;
				gs.shield -= b->dmg;
				if (gs.shield < 0.0f) {
					gs.hull += gs.shield;
					gs.shield = 0.0f;
				}
				gs.shield_flash = 1.0f;
				synth_trigger(SFX_SHIELD);
				if (gs.hull <= 0.0f) {
					/* Emergency jump/rescue back to starter outpost with cargo intact */
					gs.hull = gs.max_hull;
					gs.shield = gs.max_shield;
					gs.fuel = gs.max_fuel;
					load_system(0, 0);
					set_msg("EMERGENCY ESCAPE POD -> SOLARIS OUTPOST");
					return;
				}
			}
		}
	}

	/* 6. Particles */
	for (int i = 0; i < MAX_PARTS; i++) {
		struct particle *p = &gs.parts[i];
		if (!p->active)
			continue;
		p->life -= dt;
		if (p->life <= 0.0f) {
			p->active = 0;
			continue;
		}
		p->pos = v3_add(p->pos, v3_scale(p->vel, dt));
	}
}

/* --- 3D star-system & hyperspace warp rendering ----------------------------------------------- */

static void draw_world(double t)
{
	const struct star_sys *sy = &gs.sys[gs.cur_sys];
	be->clear(pack_argb(255, (int)(sy->neb_rgb[0] * 22.0f), (int)(sy->neb_rgb[1] * 22.0f), (int)(sy->neb_rgb[2] * 28.0f)));

	cam.pos = gs.pos;
	cam.right = gs.right;
	cam.up = gs.up;
	cam.fwd = gs.fwd;
	cam.light_dir = v3_norm(v3_sub(gs.star_pos, gs.pos));
	cam.light_rgb[0] = sy->star_rgb[0] * 0.92f;
	cam.light_rgb[1] = sy->star_rgb[1] * 0.92f;
	cam.light_rgb[2] = sy->star_rgb[2] * 0.92f;
	cam.amb_rgb[0] = 0.16f + sy->neb_rgb[0] * 0.25f;
	cam.amb_rgb[1] = 0.16f + sy->neb_rgb[1] * 0.25f;
	cam.amb_rgb[2] = 0.18f + sy->neb_rgb[2] * 0.28f;

	/* Pick brightest active player bolt or explosion as dynamic point light */
	cam.dyn_on = 0;
	for (int i = 0; i < MAX_BOLTS; i++) {
		if (gs.bolts[i].active && gs.bolts[i].from_player) {
			cam.dyn_on = 1;
			cam.dyn_pos = gs.bolts[i].pos;
			cam.dyn_rad = 65.0f;
			cam.dyn_rgb[0] = 0.4f; cam.dyn_rgb[1] = 0.9f; cam.dyn_rgb[2] = 1.0f;
			break;
		}
	}

	/* 1. Infinite Skybox: Nebula clouds + 3D starfield (depth = 0) */
	r_state(TEX_NEBULA, BLEND_ADD, 0, 0, 1, 0, 0);
	static const float neb_dirs[6][9] = {
		{ 0, 0, 1,  1, 0, 0,  0, 1, 0},
		{ 0, 0,-1, -1, 0, 0,  0, 1, 0},
		{ 1, 0, 0,  0, 0,-1,  0, 1, 0},
		{-1, 0, 0,  0, 0, 1,  0, 1, 0},
		{ 0, 1, 0,  1, 0, 0,  0, 0,-1},
		{ 0,-1, 0,  1, 0, 0,  0, 0, 1}
	};
	float nr = sy->neb_rgb[0] * 170.0f, ng = sy->neb_rgb[1] * 170.0f, nb = sy->neb_rgb[2] * 170.0f;
	for (int f = 0; f < 6; f++) {
		const float *F = neb_dirs[f];
		v3f c0 = dir_to_view(v3_make((F[0] - F[3] - F[6]) * 900.0f, (F[1] - F[4] - F[7]) * 900.0f, (F[2] - F[5] - F[8]) * 900.0f));
		v3f c1 = dir_to_view(v3_make((F[0] + F[3] - F[6]) * 900.0f, (F[1] + F[4] - F[7]) * 900.0f, (F[2] + F[5] - F[8]) * 900.0f));
		v3f c2 = dir_to_view(v3_make((F[0] + F[3] + F[6]) * 900.0f, (F[1] + F[4] + F[7]) * 900.0f, (F[2] + F[5] + F[8]) * 900.0f));
		v3f c3 = dir_to_view(v3_make((F[0] - F[3] + F[6]) * 900.0f, (F[1] - F[4] + F[7]) * 900.0f, (F[2] - F[5] + F[8]) * 900.0f));
		struct cvtx q[4] = {
			{c0.x, c0.y, c0.z, nr, ng, nb, 255.0f, 0.0f, 0.0f},
			{c1.x, c1.y, c1.z, nr, ng, nb, 255.0f, 1.0f, 0.0f},
			{c2.x, c2.y, c2.z, nr, ng, nb, 255.0f, 1.0f, 1.0f},
			{c3.x, c3.y, c3.z, nr, ng, nb, 255.0f, 0.0f, 1.0f},
		};
		r_quad3d(&q[0], &q[1], &q[2], &q[3]);
	}

	r_state(-1, BLEND_ADD, 0, 0, 0, 0, 1);
	float u_sc = space_view.h / 480.0f;
	for (int i = 0; i < N_STARS; i++) {
		v3f v = dir_to_view(gs.sky_dir[i]);
		if (v.z <= 0.05f)
			continue;
		float sx = space_view.w * 0.5f + v.x * space_view.f / v.z;
		float sy_p = space_view.h * 0.5f - v.y * space_view.f / v.z;
		if (sx < 0.0f || sx >= (float)space_view.w || sy_p < 0.0f || sy_p >= (float)space_view.h)
			continue;
		float sz = gs.sky_sz[i] * u_sc;
		r_rect(sx - sz, sy_p - sz, sx + sz, sy_p + sz, gs.sky_col[i]);
	}

	/* 2. Depth-buffered 3D Celestial Objects */
	uint32_t fog_c = pack_argb(255, (int)(sy->neb_rgb[0] * 36.0f), (int)(sy->neb_rgb[1] * 36.0f), (int)(sy->neb_rgb[2] * 48.0f));
	be->fog(950.0f, 3400.0f, fog_c);

	/* Central Star core */
	r_state(TEX_PLANET, BLEND_NONE, 1, 0, 1, 0, 0);
	r_mesh(&meshes[MESH_SPHERE], gs.star_pos, gs.star_rad, 0.0f, (float)t * 0.05f, sy->star_rgb, 1, 1, 0.0f, 0.0f);

	/* Planets */
	r_state(TEX_PLANET, BLEND_NONE, 1, 1, 1, 0, 0);
	for (int i = 0; i < gs.n_planets; i++) {
		const struct planet *p = &gs.planets[i];
		cam.light_dir = v3_norm(v3_sub(gs.star_pos, p->pos));
		r_mesh(&meshes[MESH_SPHERE], p->pos, p->rad, p->tilt_x * 0.4f, (float)t * 0.03f + p->u_off * 6.0f,
		       p->tint, 0, 1, p->u_off, 0.0f);
	}

	/* Orbital Space Station */
	cam.light_dir = v3_norm(v3_sub(gs.star_pos, gs.pos));
	if (gs.has_station) {
		static const float st_tint[3] = {0.92f, 0.96f, 1.00f};
		r_state(TEX_HULL, BLEND_NONE, 1, 1, 1, 0, 0);
		r_mesh(&meshes[MESH_STATION], gs.st_pos, gs.st_rad, 0.32f, gs.st_rot, st_tint, 0, 0, 0.0f, 0.0f);
	}

	/* Hostile Sentinel Drones */
	r_state(TEX_HULL, BLEND_NONE, 1, 1, 1, 0, 0);
	for (int i = 0; i < MAX_DRONES; i++) {
		const struct drone *d = &gs.drones[i];
		if (!d->active)
			continue;
		float dtint[3] = {
			d->hit_flash > 0.05f ? 1.6f : 1.05f,
			d->hit_flash > 0.05f ? 1.2f : 0.62f,
			d->hit_flash > 0.05f ? 1.2f : 0.58f
		};
		r_mesh(&meshes[MESH_DRONE], d->pos, 4.8f, d->rx, d->ry, dtint, 0, 0, 0.0f, 0.0f);
	}

	/* 3D Displaced Asteroids */
	r_state(TEX_ROCK, BLEND_NONE, 1, 1, 1, 0, 0);
	for (int i = 0; i < MAX_AST; i++) {
		const struct asteroid *a = &gs.ast[i];
		if (!a->active)
			continue;
		float atint[3] = {
			ore_tints[a->ore][0] + a->hit_flash * 0.7f,
			ore_tints[a->ore][1] + a->hit_flash * 0.5f,
			ore_tints[a->ore][2] + a->hit_flash * 0.4f
		};
		r_mesh(&meshes[a->mesh_id], a->pos, a->rad, a->rx, a->ry, atint, 0, 1, 0.0f, 0.0f);
	}

	/* Collectible Resource Crystals */
	r_state(TEX_WARP, BLEND_NONE, 1, 0, 1, 0, 0);
	for (int i = 0; i < MAX_CRYSTALS; i++) {
		const struct crystal *c = &gs.crys[i];
		if (!c->active)
			continue;
		r_mesh(&meshes[MESH_CRYSTAL], c->pos, 2.2f, 0.35f, c->phase, ore_tints[c->ore], 1, 0, 0.0f, 0.0f);
	}

	/* 3. Translucent & Additive 3D Effects (depth = 0 or blended over world) */
	r_state(TEX_WARP, BLEND_ALPHA, 1, 1, 1, 0, 0);
	for (int i = 0; i < gs.n_planets; i++) {
		const struct planet *p = &gs.planets[i];
		if (p->has_ring)
			r_planet_ring(p->pos, p->rad * 1.38f, p->rad * 2.15f, p->tilt_x, p->tilt_z, p->ring_col);
	}

	/* Blazing Star Corona, Station Docking Beacons, Crystal Glows, Thrusters, Lasers & Explosions */
	r_state(TEX_FLARE, BLEND_ADD, 0, 0, 1, 1, 0);
	uint32_t scol = pack_argb(235, (int)(sy->star_rgb[0] * 255), (int)(sy->star_rgb[1] * 255), (int)(sy->star_rgb[2] * 255));
	r_billboard(gs.star_pos, gs.star_rad * 3.2f, scol);
	r_billboard(gs.star_pos, gs.star_rad * 1.8f, 0xffffffffU);

	if (gs.has_station) {
		float pulse = 0.65f + 0.35f * m_sinf((float)t * 4.5f);
		r_billboard(gs.st_pos, 14.0f * pulse, 0xd040ff98U);
	}
	for (int i = 0; i < MAX_CRYSTALS; i++) {
		if (gs.crys[i].active)
			r_billboard(gs.crys[i].pos, 4.6f, (ore_cols[gs.crys[i].ore] & 0x00ffffffU) | 0xb0000000U);
	}
	for (int i = 0; i < MAX_DRONES; i++) {
		if (gs.drones[i].active)
			r_billboard(gs.drones[i].pos, 5.5f, 0xb0ff3820U);
	}
	for (int i = 0; i < MAX_BOLTS; i++) {
		const struct bolt *b = &gs.bolts[i];
		if (!b->active)
			continue;
		v3f tail = v3_sub(b->pos, v3_scale(v3_norm(b->vel), b->from_player ? 9.5f : 7.0f));
		r_beam3d(tail, b->pos, b->from_player ? 0.68f : 0.85f, b->col);
		r_billboard(b->pos, 2.0f, b->col);
	}
	for (int i = 0; i < MAX_PARTS; i++) {
		const struct particle *p = &gs.parts[i];
		if (!p->active)
			continue;
		int a = clampi((int)((p->life / p->max_life) * 255.0f), 0, 255);
		r_billboard(p->pos, p->size, (p->col & 0x00ffffffU) | ((uint32_t)a << 24));
	}

	/* Space motion dust streaks around canopy to convey 6DoF velocity vector */
	float spd = v3_len(gs.vel);
	if (spd > 4.0f) {
		r_state(-1, BLEND_ADD, 0, 0, 0, 0, 0);
		v3f streak = v3_scale(gs.vel, -0.045f);
		for (int i = 0; i < N_DUST; i++) {
			v3f rel = v3_sub(gs.dust[i], gs.pos);
			/* Wrap dust in a 120x120x120 cube around player ship */
			while (rel.x >  60.0f) { gs.dust[i].x -= 120.0f; rel.x -= 120.0f; }
			while (rel.x < -60.0f) { gs.dust[i].x += 120.0f; rel.x += 120.0f; }
			while (rel.y >  60.0f) { gs.dust[i].y -= 120.0f; rel.y -= 120.0f; }
			while (rel.y < -60.0f) { gs.dust[i].y += 120.0f; rel.y += 120.0f; }
			while (rel.z >  60.0f) { gs.dust[i].z -= 120.0f; rel.z -= 120.0f; }
			while (rel.z < -60.0f) { gs.dust[i].z += 120.0f; rel.z += 120.0f; }
			v3f p0 = gs.dust[i];
			v3f p1 = v3_add(p0, streak);
			int br = clampi((int)(spd * 2.2f), 30, 200);
			r_beam3d(p0, p1, 0.08f, pack_argb(255, br, br, 255));
		}
	}
}

/* Hyperspace Interstellar Tunnel Scene */
static void draw_warp_scene(double t)
{
	const struct star_sys *dst = &gs.sys[gs.nav_sys];
	uint32_t fog_c = pack_argb(255, (int)(dst->star_rgb[0] * 40), (int)(dst->star_rgb[1] * 50), 95);
	be->clear(fog_c);
	be->fog(8.0f, 52.0f, fog_c);
	cam.pos = v3_make(0, 0, 0);
	cam.right = v3_make(1, 0, 0);
	cam.up = v3_make(0, 1, 0);
	cam.fwd = v3_make(0, 0, 1);

	r_state(TEX_WARP, BLEND_NONE, 1, 1, 1, 0, 0);
#define WARP_RINGS 40
#define WARP_SEGS 16
	static struct cvtx ring[2][WARP_SEGS + 1];
	float scroll = -(float)t * 3.2f, spin = (float)t * 1.1f;
	for (int k = 0; k < WARP_RINGS; k++) {
		float z = 1.2f + k * 1.35f;
		float ox = 0.7f * m_sinf(z * 0.08f + (float)t * 2.4f) * (z / 38.0f);
		float oy = 0.5f * m_cosf(z * 0.07f + (float)t * 1.9f) * (z / 38.0f);
		for (int s = 0; s <= WARP_SEGS; s++) {
			float a = (float)s / WARP_SEGS * (float)TAU + spin + z * 0.035f;
			float sh = 0.65f + 0.35f * m_sinf(a * 2.0f + (float)t * 4.0f);
			ring[k & 1][s].vx = ox + m_cosf(a) * 2.4f;
			ring[k & 1][s].vy = oy + m_sinf(a) * 2.4f;
			ring[k & 1][s].vz = z;
			ring[k & 1][s].r = dst->star_rgb[0] * 255.0f * sh;
			ring[k & 1][s].g = dst->star_rgb[1] * 255.0f * sh;
			ring[k & 1][s].b = 255.0f * sh;
			ring[k & 1][s].a = 255.0f;
			ring[k & 1][s].s = (float)s / WARP_SEGS * 3.0f;
			ring[k & 1][s].t = z * 0.14f + scroll;
		}
		if (k) {
			for (int s = 0; s < WARP_SEGS; s++)
				r_quad3d(&ring[(k - 1) & 1][s], &ring[(k - 1) & 1][s + 1],
					 &ring[k & 1][s + 1], &ring[k & 1][s]);
		}
	}

	r_text_state();
	float W = (float)space_view.w, H = (float)space_view.h, sc = H >= 600 ? 2.5f : 2.0f;
	char msg[64];
	space_fmt(msg, sizeof(msg), "HYPERSPACE JUMP -> %s", dst->name);
	r_text((W - r_text_w(msg, sc)) * 0.5f, H * 0.36f, sc, 0xffffffffU, msg);
}

#include "ui.h"

/* --- deterministic -check verification & -bench ----------------------------------------------- */

#define TOLERANCE 32

static int read_and_check(const char *name)
{
	if (!be->read()) {
		space_log("CHECK part=%s FAIL read-back failed", name);
		return 1;
	}
	int bad = 0;
	for (int i = 0; i < nprobes; i++) {
		struct probe *p = &probes[i];
		uint8_t got[3];
		be->pixel(p->x, p->y, got);
		int ok = 1;
		for (int c = 0; c < 3; c++) {
			int d = (int)got[c] - p->rgb[c];
			ok &= (d >= -TOLERANCE && d <= TOLERANCE);
		}
		space_log("INFO %s %s (%d,%d) got #%02x%02x%02x want #%02x%02x%02x %s",
			  name, ok ? "ok  " : "FAIL", p->x, p->y, got[0], got[1], got[2],
			  p->rgb[0], p->rgb[1], p->rgb[2], p->what);
		if (!ok)
			bad++;
	}
	if (bad)
		space_log("CHECK part=%s FAIL %d of %d probes", name, bad, nprobes);
	else
		space_log("CHECK part=%s PASS %d probes", name, nprobes);
	return bad != 0;
}

static int run_check(void)
{
	int failed = 0;
	init_new_game(0x3df02026U);
	gs.screen = SCR_PLAY;

	/* Scene 1: Star system + 3D cockpit wells */
	nprobes = 0;
	draw_world(0.0);
	draw_cockpit_hud();
	r_flush();
	float W = (float)space_view.w, H = (float)space_view.h, u = H / 480.0f;
	/* Probe inside dark right console panel & deep space sky */
	add_probe((int)(W - 24.0f * u), (int)(H * 0.94f), 10, 18, 28, "cockpit right console well");
	add_probe((int)(W * 0.5f), (int)(H * 0.865f), 8, 22, 36, "cockpit holo-radar center");
	failed += read_and_check("cockpit");
	be->swap(1);

	/* Scene 2: Hyperspace warp tunnel fog core */
	nprobes = 0;
	gs.nav_sys = 1;
	draw_warp_scene(0.0);
	r_flush();
	const struct star_sys *dst = &gs.sys[gs.nav_sys];
	add_probe((int)(W * 0.5f), (int)(H * 0.5f),
		  (int)(dst->star_rgb[0] * 40), (int)(dst->star_rgb[1] * 50), 95, "warp tunnel fog center");
	failed += read_and_check("warp");
	be->swap(1);
	return failed;
}

static void run_bench(int frames)
{
	init_new_game(0x3df02026U);
	gs.screen = SCR_PLAY;
	gs.autopilot = 1;
	uint32_t t0 = plat_us();
	for (int f = 0; f < frames; f++) {
		struct plat_input in = {0, 0, 0, 0};
		update_autopilot(1.0f / 60.0f, &in);
		sim_step(1.0f / 60.0f, &in);
		if (gs.screen == SCR_WARP)
			draw_warp_scene(f / 60.0);
		else {
			draw_world(f / 60.0);
			draw_cockpit_hud();
		}
		r_flush();
		be->swap(0);
	}
	double secs = (uint32_t)(plat_us() - t0) / 1e6;
	space_log("BENCH part=system frames=%d secs=%.2f fps=%.1f", frames, secs, secs > 0 ? frames / secs : 0);
}

/* --- display setup & interactive main loop ---------------------------------------------------- */

static const int RES[3][2] = {{640, 480}, {800, 600}, {1024, 768}};
static const double GAMMAS[6] = {1.0, 1.2, 1.4, 1.7, 2.0, 0.8};

static void upload_textures(void)
{
	be->tex_load(TEX_FONT,   128, 1,              tex_font,   1);
	be->tex_load(TEX_ROCK,   256, mip_levels_256, tex_rock,   0);
	be->tex_load(TEX_PLANET, 256, mip_levels_256, tex_planet, 0);
	be->tex_load(TEX_HULL,   256, mip_levels_256, tex_hull,   0);
	be->tex_load(TEX_FLARE,   64, 1,              tex_flare,  1);
	be->tex_load(TEX_NEBULA, 256, mip_levels_256, tex_nebula, 0);
	be->tex_load(TEX_WARP,   256, mip_levels_256, tex_warp,   0);
}

static int set_res(int w, int h)
{
	space_view.w = w;
	space_view.h = h;
	space_view.f = (float)(h * 0.866);
	space_view.znear = 1.0f;
	space_view.zfar = 3800.0f;
	return be->open(w, h);
}

static void cycle_starmap(int dir)
{
	gs.nav_sys = (gs.nav_sys + dir + N_SYSTEMS) % N_SYSTEMS;
}

static int run_game(int total_secs, int show_hud, int start_auto, uint32_t seed)
{
	init_new_game(seed);
	if (start_auto) {
		gs.autopilot = 1;
		gs.screen = SCR_PLAY;
	}

	int gi = 0, ri = 0;
	for (int i = 0; i < 3; i++)
		if (RES[i][0] == space_view.w && RES[i][1] == space_view.h)
			ri = i;

	uint32_t t_start = plat_us(), t_prev = t_start, t_sec = t_start;
	int frames_sec = 0;
	double ms_sum = 0.0;

	for (;;) {
		uint32_t now = plat_us();
		float dt = (float)((uint32_t)(now - t_prev)) * 1e-6f;
		t_prev = now;
		if (dt > 0.1f)
			dt = 0.1f;
		double elapsed = (uint32_t)(now - t_start) * 1e-6;
		if (total_secs > 0 && (uint32_t)(now - t_start) / 1000000U >= (uint32_t)total_secs)
			break;

		/* Discrete UI & hotkey events */
		int quit = 0;
		for (int k; (k = plat_key()) >= 0;) {
			if (k == 27) {
				if (gs.screen == SCR_MAP || gs.screen == SCR_UPGRADE)
					gs.screen = SCR_PLAY;
				else {
					quit = 1;
					break;
				}
				continue;
			}
			if (gs.screen == SCR_TITLE) {
				if (k == ' ' || k == '\r' || k == '\n') {
					gs.screen = SCR_PLAY;
					gs.autopilot = 0;
				}
				continue;
			}
			if (gs.autopilot && (k == ' ' || k == 'w' || k == 'W' || k == 'm' || k == 'M'))
				gs.autopilot = 0;

			if (k == 'm' || k == 'M' || k == '\t')
				gs.screen = (gs.screen == SCR_MAP) ? SCR_PLAY : SCR_MAP;
			else if (k == 'u' || k == 'U')
				gs.screen = (gs.screen == SCR_UPGRADE) ? SCR_PLAY : SCR_UPGRADE;
			else if (k == 'j' || k == 'J' || (gs.screen == SCR_MAP && (k == '\r' || k == '\n')))
				start_warp();
			else if (k == 't' || k == 'T')
				lock_best_target();
			else if (k == 'f' || k == 'F')
				show_hud = !show_hud;
			else if (k == '+' || k == '=')
				gs.throttle = clampf(gs.throttle + 0.25f, 0.0f, 1.0f);
			else if (k == '-' || k == '_')
				gs.throttle = clampf(gs.throttle - 0.25f, 0.0f, 1.0f);
			else if (gs.screen == SCR_MAP) {
				if (k == KEY_RIGHT || k == KEY_DOWN || k == 'd' || k == 'D' || k == 's' || k == 'S')
					cycle_starmap(1);
				else if (k == KEY_LEFT || k == KEY_UP || k == 'a' || k == 'A' || k == 'w' || k == 'W')
					cycle_starmap(-1);
			} else if (gs.screen == SCR_UPGRADE && k >= '1' && k <= '6') {
				try_upgrade(k - '0');
			} else if (k == 'g' || k == 'G') {
				gi = (gi + (k == 'g' ? 1 : 5)) % 6;
				be->gamma((float)GAMMAS[gi]);
			} else if (k == 'r' || k == 'R') {
				int ow = space_view.w, oh = space_view.h, n = ri;
				do
					n = (n + 1) % 3;
				while (n != ri && !be->res_ok(RES[n][0], RES[n][1]));
				if (n != ri) {
					be->close(0);
					if (set_res(RES[n][0], RES[n][1]) == 0)
						ri = n;
					else if (set_res(ow, oh) != 0)
						return 2;
					upload_textures();
					if (GAMMAS[gi] != 1.0)
						be->gamma((float)GAMMAS[gi]);
				}
			}
		}
		if (quit)
			break;

		struct plat_input in = {0, 0, 0, 0};
		plat_poll(&in);
		if (gs.autopilot)
			update_autopilot(dt, &in);

		sim_step(dt, &in);
		plat_audio_tick();

		if (gs.screen == SCR_WARP) {
			draw_warp_scene(elapsed);
		} else {
			draw_world(elapsed);
			if (gs.screen == SCR_TITLE)
				draw_title_overlay(elapsed);
			else {
				draw_cockpit_hud();
				if (gs.screen == SCR_MAP)
					draw_starmap_overlay(elapsed);
				else if (gs.screen == SCR_UPGRADE)
					draw_upgrade_overlay();
			}
		}
		if (show_hud)
			draw_fps_hud(GAMMAS[gi]);
		r_flush();
		be->swap(1);

		uint32_t after = plat_us();
		double ms = (uint32_t)(after - now) / 1000.0;
		ft_ms[ft_pos] = (float)ms;
		ft_pos = (ft_pos + 1) % GRAPH_N;
		frames_sec++;
		ms_sum += ms;
		if ((uint32_t)(after - t_sec) >= 1000000U) {
			hud_fps = frames_sec * 1e6 / (uint32_t)(after - t_sec);
			space_log("FPS sys=%s fps=%.1f ms=%.2f score=%d",
				  gs.sys[gs.cur_sys].name, hud_fps, ms_sum / frames_sec, gs.score);
			t_sec = after;
			frames_sec = 0;
			ms_sum = 0.0;
		}
	}
	return 0;
}

/* -audiotest: the audio signature through the platform's own backend, no display. Done when the
 * whole signal has been mixed and 500 ms of silence more (what the device still had buffered). */
static int run_audiotest(void)
{
	space_log("START api=%s mode=audiotest", be->api);
	atest.on = 1;
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
		if ((!atest.rate && now - t0 > 2000000U) || now - t0 > 20000000U || plat_key() == 27)
			break;
		plat_sleep(5);
	}
	plat_audio_close();
	space_log("AUDIOTEST rate=%d frames=%u of %d secs=%.2f", atest.rate, atest.sig_frames,
		  AUDIOSIG_FRAMES(atest.rate), (uint32_t)(plat_us() - t0) / 1e6);
	space_log(!atest.rate ? "FAIL no audio device" : status ? "FAIL the signature did not play to the end" : "PASS");
	space_log("CLOSED");
	return status;
}

static void usage(void)
{
	static const char *lines[] = {
		"usage: wshspace [-res WxH] [-auto] [-seed N] [-nosound] [-nohud] [-gamma G] [-time S]",
		"                [-check] [-bench N] [-hold S] [-wait S] [-tag NAME] [-audiotest]",
		"                [-api glide2|glide3|opengl] [-hostgl (Windows)] [-nocom (Windows/DOS)]",
		"flight: Arrows/Mouse pitch+yaw, W/S thrust+brake, A/D or Q/E roll, Space fire, Shift/B boost",
		"systems: M/Tab starmap, J hyperspace jump, U upgrades/synthesizer, T target, F fps, R res, Esc quit",
	};
	for (unsigned i = 0; i < sizeof(lines) / sizeof(lines[0]); i++)
		plat_out(lines[i]);
}

int space_main(int argc, char **argv, const struct backend *backend)
{
	be = backend;
	int check = 0, bench = 0, hold = 0, w = 640, h = 480, total = 0, show_hud = 0, start_auto = 0, wait = 0, sound = 1;
	int audiotest = 0;
	uint32_t seed = 0x3df02026U;
	double gamma = 1.0;

	for (int i = 1; i < argc; i++) {
		const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : 0;
		if (str_eq(a, "-check"))       check = 1;
		else if (str_eq(a, "-auto"))   start_auto = 1;
		else if (str_eq(a, "-hud"))    show_hud = 1;
		else if (str_eq(a, "-nohud"))  show_hud = 0;
		else if (str_eq(a, "-nosound")) sound = 0;
		else if (str_eq(a, "-audiotest")) audiotest = 1;
		else if (str_eq(a, "-nocom") || str_eq(a, "-hostgl")) ;
		else if (v && str_eq(a, "-wait"))  { wait = to_int(v); i++; }
		else if (v && str_eq(a, "-bench")) { bench = to_int(v); i++; }
		else if (v && str_eq(a, "-hold"))  { hold = to_int(v); i++; }
		else if (v && str_eq(a, "-time"))  { total = to_int(v); i++; }
		else if (v && str_eq(a, "-seed"))  { seed = (uint32_t)to_int(v); i++; }
		else if (v && str_eq(a, "-tag"))   { tag = v; i++; }
		else if (v && str_eq(a, "-api"))   { i++; }
		else if (v && str_eq(a, "-log"))   { i++; }
		else if (v && str_eq(a, "-gamma")) {
			gamma = to_int(v);
			for (const char *d = v; *d; d++)
				if (*d == '.') {
					double sc = 0.1;
					for (d++; *d >= '0' && *d <= '9'; d++, sc /= 10.0)
						gamma += (*d - '0') * sc;
					break;
				}
			i++;
		} else if (v && str_eq(a, "-res")) {
			w = to_int(v);
			const char *x = v;
			while (*x && *x != 'x' && *x != 'X')
				x++;
			h = *x ? to_int(x + 1) : 0;
			i++;
		} else {
			usage();
			return a[0] == '-' && (a[1] == 'h' || a[1] == '?') ? 0 : 2;
		}
	}

	if (audiotest)
		return run_audiotest();
	const char *mode = check && bench ? "check+bench" : check ? "check" : bench ? "bench" : start_auto ? "auto" : "game";
	space_log("START api=%s res=%dx%d mode=%s", be->api, w, h, mode);
	if (!be->res_ok(w, h)) {
		space_log("ERROR %s can't open %dx%d", be->api, w, h);
		space_log("CLOSED");
		return 2;
	}

	uint32_t t_gen = plat_us();
	gen_all_textures();
	gen_all_meshes();
	space_log("GEN procedural textures+meshes in %u ms", (uint32_t)(plat_us() - t_gen) / 1000U);

	for (int s = 0; s < wait * 50 && plat_key() != 27; s++)
		plat_sleep(20);

	uint32_t t0 = plat_us();
	if (set_res(w, h) != 0) {
		space_log("ERROR no %s device", be->api);
		space_log("CLOSED");
		return 2;
	}
	api_version = be->version();
	static char rev[96];
	if (plat_wrapper_rev(rev, sizeof(rev)))
		wrapper_rev = rev;
	space_log("VERSION %s, wrapper %s, opened %dx%d in %u ms",
		  api_version, wrapper_rev, w, h, (uint32_t)(plat_us() - t0) / 1000U);
	upload_textures();
	if (gamma != 1.0)
		be->gamma((float)gamma);

	if (sound && !check && !bench)
		plat_audio_init(1);

	int failed = 0, status = 0;
	if (bench > 0)
		run_bench(bench);
	if (check)
		failed = run_check();
	if (check || bench) {
		if (hold > 0) {
			for (int i = 0; check && i < nprobes; i++)
				space_log("PROBE %d %d %02x%02x%02x", probes[i].x, probes[i].y,
					  probes[i].rgb[0], probes[i].rgb[1], probes[i].rgb[2]);
			space_log("FRAME");
			uint32_t end = plat_us();
			while ((uint32_t)(plat_us() - end) < (uint32_t)hold * 1000000U) {
				if (plat_key() == 27)
					break;
				plat_sleep(20);
			}
		}
	} else {
		status = run_game(total, show_hud, start_auto, seed);
	}

	plat_audio_close();
	if (gamma != 1.0)
		be->gamma(1.0f);
	be->close(1);
	if (status)
		space_log("ERROR display reopen failed");
	else if (failed)
		space_log("FAIL %d", failed);
	else
		space_log("PASS");
	space_log("CLOSED");
	return status ? status : failed ? 1 : 0;
}
