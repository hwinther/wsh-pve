/*
 * wshkeep: .kkrieger-inspired procedural 3D subterranean dungeon & citadel crawler for 3dfx
 * Glide 2, Glide 3, and OpenGL 1.1 (<= 96 KB binary, Pentium-safe x87, zero external assets).
 *
 * Features:
 *   - 4 themed procedural multi-room dungeon floors (Obsidian Bastion, Flooded Catacombs,
 *     Ember Forge, Astral Sanctum) with vaulted ceilings, octagonal pillars, sunken canals/lava,
 *     sliding oak-and-iron doors, locked Runegate, and shimmering Descent Portals
 *   - Flickering colored dynamic point lights from wall sconces, flying spell bolts, lava, & runes
 *   - 4 sculpted 3D dungeon foes (Sentinel, Gargoyle, Iron Golem, Sanctum Archon)
 *   - 3 sculpted 3D first-person weapons (Iron Halberd, Ember Rod, Storm Scepter)
 *   - Breadth-first-search (BFS) dungeon exploration & combat autopilot (-auto / P)
 *   - Resolution parity up to 1600x1200 on Glide 2/3 and 1920x1080 on OpenGL, plus -check/-bench
 *
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>

#include "keep.h"
#include "font.h"
#include "audiosig.h"

void *memset(void *d, int c, size_t n);
void *memcpy(void *d, const void *s, size_t n);

struct view keep_view = {640, 480, 415.69f, 0.85f, 220.0f};

static const int RES[][2] = {
	{640, 480}, {800, 600}, {856, 480}, {960, 720}, {1024, 768},
	{1280, 960}, {1280, 1024}, {1600, 1200}, {1920, 1080},
};
enum { NRES = (int)(sizeof(RES) / sizeof(RES[0])) };

static const char *log_tag = "WSHKEEP";

static int str_eq(const char *a, const char *b)
{
	while (*a && *a == *b)
		a++, b++;
	return *a == *b;
}

static void str_copy(char *dst, const char *src, int cap)
{
	if (cap <= 0)
		return;
	int i = 0;
	while (src[i] && i + 1 < cap) {
		dst[i] = src[i];
		i++;
	}
	dst[i] = 0;
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

static uint32_t parse_uint_any(const char *s)
{
	uint32_t v = 0;
	if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
		s += 2;
		for (; *s; s++) {
			int d = (*s >= '0' && *s <= '9') ? *s - '0' :
				(*s >= 'a' && *s <= 'f') ? *s - 'a' + 10 :
				(*s >= 'A' && *s <= 'F') ? *s - 'A' + 10 : -1;
			if (d < 0)
				break;
			v = (v << 4) | (uint32_t)d;
		}
		return v;
	}
	while (*s >= '0' && *s <= '9')
		v = v * 10U + (uint32_t)(*s++ - '0');
	return v;
}

static float parse_float_or(const char *s, float def)
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
	return any ? v * sign : def;
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
		if (*fmt == '0')
			fmt++;
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

int keep_fmt(char *buf, int cap, const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	int n = vfmt(buf, cap, fmt, ap);
	va_end(ap);
	return n;
}

void keep_log(const char *fmt, ...)
{
	char body[240], line[280];
	va_list ap;
	va_start(ap, fmt);
	vfmt(body, sizeof(body), fmt, ap);
	va_end(ap);
	keep_fmt(line, sizeof(line), "%s: %s", log_tag, body);
	plat_out(line);
}

int keep_find_buildstr(const uint8_t *buf, uint32_t len, char *out, int outlen)
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

#include "gen.h"
#include "render.h"

/* --- Dungeon World & Entity Definitions --- */
#define MAP_N 32
#define CELL 16.0f
#define MAX_ROOMS 11
#define MAX_TORCHES 44
#define MAX_MONS 24
#define MAX_ITEMS 28
#define MAX_BOLTS 24

enum {
	TILE_WALL = 0,
	TILE_FLOOR = 1,
	TILE_LIQUID = 2,
	TILE_DOOR = 3,
	TILE_LOCKED = 4,
	TILE_PILLAR = 5,
};

enum {
	MON_SENTINEL = 0,
	MON_GARGOYLE = 1,
	MON_GOLEM = 2,
	MON_ARCHON = 3,
};

enum {
	ITEM_HEALTH = 0,
	ITEM_MANA = 1,
	ITEM_CHEST = 2,
	ITEM_KEY = 3,
};

struct room {
	int x0, z0, x1, z1;
	int cx, cz;
	float ceil_h;
};

struct torch {
	float x, y, z, yaw, phase;
};

struct monster {
	uint8_t kind;
	int hp, max_hp;
	float x, y, z, yaw;
	float cd, hurt_t, anim_t;
	uint8_t awake;
};

struct item {
	uint8_t type, active;
	float x, z, phase;
};

struct bolt {
	uint8_t active, from_plr, kind; /* 0=ember, 1=storm, 2=foe-orb */
	float x, y, z, vx, vy, vz, life;
};

static struct {
	int depth, floor_idx;
	uint32_t seed;
	uint8_t tile[MAP_N][MAP_N];
	uint8_t seen[MAP_N][MAP_N];
	float ceil_y[MAP_N][MAP_N];
	float door_open[MAP_N][MAP_N];
	uint8_t door_ns[MAP_N][MAP_N]; /* 1 if corridor runs N-S (door spans X), 0 if E-W */
	struct room rooms[MAX_ROOMS];
	int n_rooms;
	struct torch torches[MAX_TORCHES];
	int n_torches;
	struct monster mons[MAX_MONS];
	int n_mons, kills, total_mons;
	struct item items[MAX_ITEMS];
	int n_items;
	struct bolt bolts[MAX_BOLTS];
	float portal_x, portal_z;
} dun;

static struct {
	float x, y, z, yaw, pitch;
	float vx, vz, bob_t, step_t;
	int hp, gold, wpn, has_key;
	float mana, atk_t, atk_cd;
	float hurt_flash, bonus_flash;
	int autopilot, bfs_wait;
	float stuck_t, last_x, last_z, strafe_dir, strafe_t;
	char toast[64];
	float toast_t;
} plr;

static void set_toast(const char *msg)
{
	str_copy(plr.toast, msg, sizeof(plr.toast));
	plr.toast_t = 2.6f;
}

static int tile_at(int gx, int gz)
{
	if (gx < 0 || gx >= MAP_N || gz < 0 || gz >= MAP_N)
		return TILE_WALL;
	return dun.tile[gz][gx];
}

static int tile_blocks_move(int gx, int gz, int is_flyer)
{
	int t = tile_at(gx, gz);
	if (t == TILE_WALL || t == TILE_PILLAR)
		return 1;
	if (t == TILE_LIQUID && !is_flyer)
		return 0; /* shallow sunken canal/lava: traversable (lava singes if lingered!) */
	if (t == TILE_DOOR)
		return dun.door_open[gz][gx] < 0.72f;
	if (t == TILE_LOCKED)
		return dun.door_open[gz][gx] < 0.72f;
	return 0;
}

static int circle_blocked(float wx, float wz, float rad, int is_flyer)
{
	int x0 = (int)((wx - rad) / CELL), x1 = (int)((wx + rad) / CELL);
	int z0 = (int)((wz - rad) / CELL), z1 = (int)((wz + rad) / CELL);
	for (int gz = z0; gz <= z1; gz++) {
		for (int gx = x0; gx <= x1; gx++) {
			if (!tile_blocks_move(gx, gz, is_flyer))
				continue;
			float cx0 = gx * CELL, cx1 = (gx + 1) * CELL;
			float cz0 = gz * CELL, cz1 = (gz + 1) * CELL;
			float nx = wx < cx0 ? cx0 : wx > cx1 ? cx1 : wx;
			float nz = wz < cz0 ? cz0 : wz > cz1 ? cz1 : wz;
			float dx = wx - nx, dz = wz - nz;
			if (dx * dx + dz * dz < rad * rad)
				return 1;
		}
	}
	return 0;
}

static int has_los(float x0, float z0, float x1, float z1)
{
	float dx = x1 - x0, dz = z1 - z0;
	float dist = sqrtf(dx * dx + dz * dz);
	int steps = (int)(dist / (CELL * 0.35f)) + 1;
	for (int i = 1; i < steps; i++) {
		float f = (float)i / (float)steps;
		int gx = (int)((x0 + dx * f) / CELL), gz = (int)((z0 + dz * f) / CELL);
		int t = tile_at(gx, gz);
		if (t == TILE_WALL || t == TILE_PILLAR)
			return 0;
		if ((t == TILE_DOOR || t == TILE_LOCKED) && dun.door_open[gz][gx] < 0.6f)
			return 0;
	}
	return 1;
}

static void add_item(uint8_t type, float x, float z)
{
	if (dun.n_items >= MAX_ITEMS)
		return;
	struct item *it = &dun.items[dun.n_items++];
	it->type = type;
	it->active = 1;
	it->x = x, it->z = z;
	it->phase = rndf() * 6.28f;
}

static void add_monster(uint8_t kind, float x, float z, int depth)
{
	if (dun.n_mons >= MAX_MONS)
		return;
	static const int base_hp[4] = {64, 52, 118, 220};
	struct monster *m = &dun.mons[dun.n_mons++];
	memset(m, 0, sizeof(*m));
	m->kind = kind;
	m->max_hp = base_hp[kind & 3] + (depth - 1) * 14;
	m->hp = m->max_hp;
	m->x = x, m->z = z;
	m->y = (kind == MON_GARGOYLE) ? 1.4f : 0.0f;
	m->yaw = rndf() * 2.0f * PI;
	m->anim_t = rndf() * 6.0f;
}

static void carve_cell(int x, int z, float ch)
{
	if (x <= 0 || x >= MAP_N - 1 || z <= 0 || z >= MAP_N - 1)
		return;
	dun.tile[z][x] = TILE_FLOOR;
	if (ch > dun.ceil_y[z][x])
		dun.ceil_y[z][x] = ch;
}

static void generate_floor(int depth, uint32_t seed)
{
	memset(&dun, 0, sizeof(dun));
	dun.depth = depth;
	dun.floor_idx = (depth - 1) & 3;
	dun.seed = seed;
	rng_s = seed ^ ((uint32_t)depth * 0x9e3779b9U);
	if (!rng_s)
		rng_s = 1;

	for (int z = 0; z < MAP_N; z++)
		for (int x = 0; x < MAP_N; x++)
			dun.ceil_y[z][x] = 15.0f;

	/* Room 0: Guaranteed grand entry hall at (3..8, 3..8) */
	dun.rooms[0] = (struct room){3, 3, 7, 7, 5, 5, 19.0f};
	dun.n_rooms = 1;
	for (int z = 3; z <= 7; z++)
		for (int x = 3; x <= 7; x++)
			carve_cell(x, z, 19.0f);

	/* Place up to MAX_ROOMS - 1 non-overlapping vaulted chambers */
	for (int tries = 0; tries < 140 && dun.n_rooms < MAX_ROOMS; tries++) {
		int rw = 4 + (int)(rnd() % 4), rz_h = 4 + (int)(rnd() % 4);
		int x0 = 2 + (int)(rnd() % (MAP_N - rw - 4));
		int z0 = 2 + (int)(rnd() % (MAP_N - rz_h - 4));
		int x1 = x0 + rw, z1 = z0 + rz_h;
		int ok = 1;
		for (int i = 0; i < dun.n_rooms; i++) {
			if (x0 <= dun.rooms[i].x1 + 2 && x1 >= dun.rooms[i].x0 - 2 &&
			    z0 <= dun.rooms[i].z1 + 2 && z1 >= dun.rooms[i].z0 - 2) {
				ok = 0;
				break;
			}
		}
		if (!ok)
			continue;
		float ch = 17.0f + (float)(rnd() % 4) * 3.0f;
		struct room *rm = &dun.rooms[dun.n_rooms++];
		rm->x0 = x0, rm->z0 = z0, rm->x1 = x1, rm->z1 = z1;
		rm->cx = (x0 + x1) >> 1, rm->cz = (z0 + z1) >> 1;
		rm->ceil_h = ch;
		for (int z = z0; z <= z1; z++)
			for (int x = x0; x <= x1; x++)
				carve_cell(x, z, ch);

		/* Optional sunken liquid moat + causeway or corner pillars in larger chambers */
		if (dun.n_rooms > 2 && rw >= 5 && rz_h >= 5) {
			if ((rnd() & 1) == 0) {
				for (int z = z0 + 1; z <= z1 - 1; z++)
					for (int x = x0 + 1; x <= x1 - 1; x++)
						if (x != rm->cx && z != rm->cz)
							dun.tile[z][x] = TILE_LIQUID;
			} else {
				dun.tile[z0 + 1][x0 + 1] = TILE_PILLAR;
				dun.tile[z0 + 1][x1 - 1] = TILE_PILLAR;
				dun.tile[z1 - 1][x0 + 1] = TILE_PILLAR;
				dun.tile[z1 - 1][x1 - 1] = TILE_PILLAR;
			}
		}
	}

	/* Sort rooms by distance from Room 0 so the farthest room becomes the Sanctum Exit! */
	for (int i = 1; i < dun.n_rooms; i++) {
		for (int j = i + 1; j < dun.n_rooms; j++) {
			int di = (dun.rooms[i].cx - 5) * (dun.rooms[i].cx - 5) + (dun.rooms[i].cz - 5) * (dun.rooms[i].cz - 5);
			int dj = (dun.rooms[j].cx - 5) * (dun.rooms[j].cx - 5) + (dun.rooms[j].cz - 5) * (dun.rooms[j].cz - 5);
			if (dj < di) {
				struct room tmp = dun.rooms[i];
				dun.rooms[i] = dun.rooms[j];
				dun.rooms[j] = tmp;
			}
		}
	}

	/* Connect rooms sequentially (spanning chain; Sanctum room [n_rooms-1] connects ONLY via its single corridor!) */
	int sanctum = dun.n_rooms - 1;
	int locked_placed = 0;
	for (int i = 1; i < dun.n_rooms; i++) {
		int prev = (i == sanctum) ? (i - 1) : ((i >= 3 && (rnd() & 3) == 0) ? (i - 2) : (i - 1));
		int x = dun.rooms[prev].cx, z = dun.rooms[prev].cz;
		int tx = dun.rooms[i].cx, tz = dun.rooms[i].cz;
		while (x != tx) {
			carve_cell(x, z, 14.5f);
			x += (tx > x) ? 1 : -1;
		}
		while (z != tz) {
			carve_cell(x, z, 14.5f);
			z += (tz > z) ? 1 : -1;
		}
		carve_cell(tx, tz, 14.5f);
	}

	/* Clear any liquid/pillar accidentally blocking room centers */
	for (int i = 0; i < dun.n_rooms; i++)
		dun.tile[dun.rooms[i].cz][dun.rooms[i].cx] = TILE_FLOOR;

	/* Place oak-and-iron doors at 1-tile corridor throats entering rooms (and the Runegate at the Sanctum throat!) */
	for (int z = 2; z < MAP_N - 2; z++) {
		for (int x = 2; x < MAP_N - 2; x++) {
			if (dun.tile[z][x] != TILE_FLOOR)
				continue;
			int ns_walls = (dun.tile[z][x - 1] == TILE_WALL && dun.tile[z][x + 1] == TILE_WALL &&
					dun.tile[z - 1][x] == TILE_FLOOR && dun.tile[z + 1][x] == TILE_FLOOR);
			int ew_walls = (dun.tile[z - 1][x] == TILE_WALL && dun.tile[z + 1][x] == TILE_WALL &&
					dun.tile[z][x - 1] == TILE_FLOOR && dun.tile[z][x + 1] == TILE_FLOOR);
			if (!ns_walls && !ew_walls)
				continue;
			/* Check if adjacent to Sanctum room */
			const struct room *sr = &dun.rooms[sanctum];
			int near_sanctum = (x >= sr->x0 - 1 && x <= sr->x1 + 1 && z >= sr->z0 - 1 && z <= sr->z1 + 1) &&
					   !(x >= sr->x0 && x <= sr->x1 && z >= sr->z0 && z <= sr->z1);
			if (near_sanctum && !locked_placed) {
				dun.tile[z][x] = TILE_LOCKED;
				dun.door_ns[z][x] = (uint8_t)ns_walls;
				locked_placed = 1;
			}
		}
	}
	/* Place regular doors at selected corridor throats (spaced out) */
	for (int z = 2; z < MAP_N - 2; z++) {
		for (int x = 2; x < MAP_N - 2; x++) {
			if (dun.tile[z][x] != TILE_FLOOR)
				continue;
			if (abs(x - 5) <= 3 && abs(z - 5) <= 3)
				continue;
			int ns_walls = (dun.tile[z][x - 1] == TILE_WALL && dun.tile[z][x + 1] == TILE_WALL &&
					dun.tile[z - 1][x] == TILE_FLOOR && dun.tile[z + 1][x] == TILE_FLOOR);
			int ew_walls = (dun.tile[z - 1][x] == TILE_WALL && dun.tile[z + 1][x] == TILE_WALL &&
					dun.tile[z][x - 1] == TILE_FLOOR && dun.tile[z][x + 1] == TILE_FLOOR);
			if (!ns_walls && !ew_walls)
				continue;
			/* Only at room doorway thresholds (where ceiling changes) and no adjacent door */
			int adj_door = (dun.tile[z - 1][x] >= TILE_DOOR || dun.tile[z + 1][x] >= TILE_DOOR ||
					dun.tile[z][x - 1] >= TILE_DOOR || dun.tile[z][x + 1] >= TILE_DOOR);
			int room_edge = (dun.ceil_y[z - 1][x] > 15.5f || dun.ceil_y[z + 1][x] > 15.5f ||
					 dun.ceil_y[z][x - 1] > 15.5f || dun.ceil_y[z][x + 1] > 15.5f);
			if (!adj_door && room_edge && (rnd() % 3) != 0) {
				dun.tile[z][x] = TILE_DOOR;
				dun.door_ns[z][x] = (uint8_t)ns_walls;
			}
		}
	}

	/* Place Wall Torches along room walls & corridors for warm flickering dynamic point lighting */
	for (int z = 1; z < MAP_N - 1 && dun.n_torches < MAX_TORCHES; z++) {
		for (int x = 1; x < MAP_N - 1 && dun.n_torches < MAX_TORCHES; x++) {
			if (dun.tile[z][x] != TILE_FLOOR)
				continue;
			if (((x + z) & 3) != 1)
				continue;
			static const int dirs[4][2] = {{0, -1}, {0, 1}, {-1, 0}, {1, 0}};
			static const float dyaw[4] = {0.0f, PI, PI * 0.5f, -PI * 0.5f};
			for (int d = 0; d < 4; d++) {
				int wx = x + dirs[d][0], wz = z + dirs[d][1];
				if (dun.tile[wz][wx] == TILE_WALL) {
					float tx = (x + 0.5f + dirs[d][0] * 0.44f) * CELL;
					float tz = (z + 0.5f + dirs[d][1] * 0.44f) * CELL;
					int too_close = 0;
					for (int k = 0; k < dun.n_torches; k++) {
						float dx = dun.torches[k].x - tx, dz = dun.torches[k].z - tz;
						if (dx * dx + dz * dz < (CELL * 2.2f) * (CELL * 2.2f)) {
							too_close = 1;
							break;
						}
					}
					if (!too_close) {
						struct torch *tc = &dun.torches[dun.n_torches++];
						tc->x = tx, tc->z = tz;
						tc->y = 8.2f;
						tc->yaw = dyaw[d];
						tc->phase = rndf() * 6.28f;
					}
					break;
				}
			}
		}
	}

	/* Key room (mid-late room before Sanctum) & Portal in Sanctum */
	int key_room = dun.n_rooms > 2 ? (dun.n_rooms - 2) : (dun.n_rooms - 1);
	add_item(ITEM_KEY, (dun.rooms[key_room].cx + 0.5f) * CELL, (dun.rooms[key_room].cz + 0.5f) * CELL);
	dun.portal_x = (dun.rooms[sanctum].cx + 0.5f) * CELL;
	dun.portal_z = (dun.rooms[sanctum].cz + 0.5f) * CELL;

	/* Populate rooms 1..sanctum with Monsters, Reliquary Chests, Vitality Vials & Mana Prisms */
	for (int i = 1; i < dun.n_rooms; i++) {
		const struct room *rm = &dun.rooms[i];
		float rcx = (rm->cx + 0.5f) * CELL, rcz = (rm->cz + 0.5f) * CELL;
		if (i == sanctum) {
			uint8_t boss = (dun.floor_idx == 3 || depth >= 4) ? MON_ARCHON : MON_GOLEM;
			add_monster(boss, rcx - 10.0f, rcz, depth);
			add_monster(MON_SENTINEL, rcx + 10.0f, rcz, depth);
		} else {
			int count = 1 + (int)((i + depth) % 2);
			for (int m = 0; m < count; m++) {
				int gx = rm->x0 + 1 + (int)(rnd() % (uint32_t)(rm->x1 - rm->x0 - 1));
				int gz = rm->z0 + 1 + (int)(rnd() % (uint32_t)(rm->z1 - rm->z0 - 1));
				if (dun.tile[gz][gx] == TILE_FLOOR) {
					uint8_t kind = (dun.floor_idx >= 2 && (m & 1)) ? MON_GOLEM :
						       ((i + m) & 1) ? MON_GARGOYLE : MON_SENTINEL;
					add_monster(kind, (gx + 0.5f) * CELL, (gz + 0.5f) * CELL, depth);
				}
			}
		}
		/* Pickups in room corners */
		int ix = rm->x0 + 1, iz = rm->z0 + 1;
		if (dun.tile[iz][ix] == TILE_FLOOR)
			add_item((i & 1) ? ITEM_HEALTH : ITEM_MANA, (ix + 0.5f) * CELL, (iz + 0.5f) * CELL);
		int cx2 = rm->x1 - 1, cz2 = rm->z1 - 1;
		if (dun.tile[cz2][cx2] == TILE_FLOOR && (i % 2) == 1)
			add_item(ITEM_CHEST, (cx2 + 0.5f) * CELL, (cz2 + 0.5f) * CELL);
	}
	/* Starter mana prism in Room 0 */
	add_item(ITEM_MANA, (dun.rooms[0].x1 - 0.5f) * CELL, (dun.rooms[0].z0 + 1.5f) * CELL);
	dun.total_mons = dun.n_mons;

	/* Place player in Room 0 facing the outgoing corridor */
	plr.x = (dun.rooms[0].cx + 0.5f) * CELL;
	plr.z = (dun.rooms[0].cz + 0.5f) * CELL;
	plr.y = 5.2f;
	plr.yaw = atan2f((dun.rooms[1].cx - dun.rooms[0].cx) * 1.0f, (dun.rooms[1].cz - dun.rooms[0].cz) * 1.0f);
	plr.pitch = 0.0f;
	plr.has_key = locked_placed ? 0 : 1;
	plr.last_x = plr.x, plr.last_z = plr.z, plr.stuck_t = 0.0f;
}

/* Reveal tiles around player for minimap / automap */
static void reveal_around(float wx, float wz)
{
	int cx = (int)(wx / CELL), cz = (int)(wz / CELL);
	for (int dz = -5; dz <= 5; dz++) {
		for (int dx = -5; dx <= 5; dx++) {
			if (dx * dx + dz * dz > 28)
				continue;
			int gx = cx + dx, gz = cz + dz;
			if (gx >= 0 && gx < MAP_N && gz >= 0 && gz < MAP_N)
				dun.seen[gz][gx] = 1;
		}
	}
}

/* Open adjacent doors or unlock Runegate */
static void try_use_door(float wx, float wz)
{
	int cx = (int)(wx / CELL), cz = (int)(wz / CELL);
	for (int dz = -1; dz <= 1; dz++) {
		for (int dx = -1; dx <= 1; dx++) {
			int gx = cx + dx, gz = cz + dz;
			int t = tile_at(gx, gz);
			if (t == TILE_DOOR && dun.door_open[gz][gx] < 0.05f) {
				dun.door_open[gz][gx] = 0.06f;
				keep_sfx(SFX_DOOR);
			} else if (t == TILE_LOCKED && dun.door_open[gz][gx] < 0.05f) {
				if (plr.has_key) {
					dun.door_open[gz][gx] = 0.06f;
					keep_sfx(SFX_DOOR);
					set_toast("RUNEGATE UNSEALED!");
				} else {
					set_toast("SEALED! SEEK THE GOLDEN RUNIC KEY");
				}
			}
		}
	}
}

static void spawn_bolt(uint8_t from_plr, uint8_t kind, float x, float y, float z, float dx, float dy, float dz, float spd)
{
	for (int i = 0; i < MAX_BOLTS; i++) {
		if (!dun.bolts[i].active) {
			struct bolt *b = &dun.bolts[i];
			b->active = 1;
			b->from_plr = from_plr;
			b->kind = kind;
			b->x = x, b->y = y, b->z = z;
			b->vx = dx * spd, b->vy = dy * spd, b->vz = dz * spd;
			b->life = 2.6f;
			return;
		}
	}
}

static void damage_monster(int idx, int dmg, float kx, float kz)
{
	struct monster *m = &dun.mons[idx];
	if (m->hp <= 0)
		return;
	m->hp -= dmg;
	m->hurt_t = 0.22f;
	m->awake = 1;
	float nx = m->x + kx * 2.2f, nz = m->z + kz * 2.2f;
	if (!circle_blocked(nx, nz, 2.6f, m->kind == MON_GARGOYLE)) {
		m->x = nx;
		m->z = nz;
	}
	keep_sfx(SFX_MON_HIT);
	if (m->hp <= 0) {
		dun.kills++;
		plr.gold += (m->kind == MON_ARCHON) ? 150 : (m->kind == MON_GOLEM) ? 60 : 25;
	}
}

static void player_attack(void)
{
	if (plr.atk_cd > 0.0f)
		return;
	int w = plr.wpn;
	if (w == 1 && plr.mana < 8.0f)
		w = 0;
	if (w == 2 && plr.mana < 18.0f)
		w = (plr.mana >= 8.0f) ? 1 : 0;
	plr.wpn = w;

	float fx = sinf(plr.yaw) * cosf(plr.pitch);
	float fy = sinf(plr.pitch);
	float fz = cosf(plr.yaw) * cosf(plr.pitch);

	if (w == 0) {
		/* [1] Iron Halberd sweeping melee cleave */
		plr.atk_cd = 0.40f;
		plr.atk_t = 0.40f;
		keep_sfx(SFX_SWING);
		for (int i = 0; i < dun.n_mons; i++) {
			struct monster *m = &dun.mons[i];
			if (m->hp <= 0)
				continue;
			float dx = m->x - plr.x, dz = m->z - plr.z;
			float d = sqrtf(dx * dx + dz * dz);
			if (d < 14.5f && d > 0.01f) {
				float dot = (dx * sinf(plr.yaw) + dz * cosf(plr.yaw)) / d;
				if (dot > 0.42f && has_los(plr.x, plr.z, m->x, m->z))
					damage_monster(i, 42, dx / d, dz / d);
			}
		}
	} else if (w == 1) {
		/* [2] Ember Rod rapid dynamic-light firebolt */
		plr.mana -= 8.0f;
		plr.atk_cd = 0.28f;
		plr.atk_t = 0.28f;
		keep_sfx(SFX_FIREBOLT);
		spawn_bolt(1, 0, plr.x + fx * 2.0f, plr.y - 0.5f + fy * 2.0f, plr.z + fz * 2.0f, fx, fy, fz, 84.0f);
	} else {
		/* [3] Storm Scepter high-damage shock orb */
		plr.mana -= 18.0f;
		plr.atk_cd = 0.48f;
		plr.atk_t = 0.48f;
		keep_sfx(SFX_SCEPTER);
		spawn_bolt(1, 1, plr.x + fx * 2.0f, plr.y - 0.4f + fy * 2.0f, plr.z + fz * 2.0f, fx, fy, fz, 70.0f);
	}
}

/* --- Breadth-First-Search (BFS) Dungeon Exploration & Combat Autopilot --- */
static int bfs_step(int sx, int sz, int tx, int tz, int allow_locked, int *out_nx, int *out_nz)
{
	if (sx == tx && sz == tz)
		return 0;
	static int16_t prev[MAP_N][MAP_N];
	static uint16_t q[MAP_N * MAP_N];
	for (int z = 0; z < MAP_N; z++)
		for (int x = 0; x < MAP_N; x++)
			prev[z][x] = -1;
	int qh = 0, qt = 0;
	prev[sz][sx] = (int16_t)(sz * MAP_N + sx);
	q[qt++] = (uint16_t)(sz * MAP_N + sx);
	static const int dirs[4][2] = {{0, 1}, {0, -1}, {1, 0}, {-1, 0}};
	int found = 0;
	while (qh < qt) {
		uint16_t cur = q[qh++];
		int cx = cur % MAP_N, cz = cur / MAP_N;
		if (cx == tx && cz == tz) {
			found = 1;
			break;
		}
		for (int d = 0; d < 4; d++) {
			int nx = cx + dirs[d][0], nz = cz + dirs[d][1];
			if (nx < 1 || nx >= MAP_N - 1 || nz < 1 || nz >= MAP_N - 1)
				continue;
			if (prev[nz][nx] != -1)
				continue;
			int t = dun.tile[nz][nx];
			if (t == TILE_WALL || t == TILE_PILLAR)
				continue;
			if (t == TILE_LOCKED && !allow_locked && dun.door_open[nz][nx] < 0.5f)
				continue;
			prev[nz][nx] = (int16_t)cur;
			q[qt++] = (uint16_t)(nz * MAP_N + nx);
		}
	}
	if (!found)
		return 0;
	int cx = tx, cz = tz;
	while (1) {
		int p = prev[cz][cx];
		int px = p % MAP_N, pz = p / MAP_N;
		if (px == sx && pz == sz) {
			*out_nx = cx;
			*out_nz = cz;
			return 1;
		}
		cx = px, cz = pz;
	}
}

static void autopilot_control(float dt, struct plat_input *in)
{
	/* Auto-open any adjacent doors along our path */
	try_use_door(plr.x, plr.z);
	try_use_door(plr.x + sinf(plr.yaw) * 10.0f, plr.z + cosf(plr.yaw) * 10.0f);

	/* 1. Find nearest visible monster in line-of-sight */
	int best_mon = -1;
	float best_md = 1e9f;
	for (int i = 0; i < dun.n_mons; i++) {
		const struct monster *m = &dun.mons[i];
		if (m->hp <= 0)
			continue;
		float dx = m->x - plr.x, dz = m->z - plr.z;
		float d = sqrtf(dx * dx + dz * dz);
		if (d < 135.0f && d < best_md && has_los(plr.x, plr.z, m->x, m->z)) {
			best_md = d;
			best_mon = i;
		}
	}

	float goal_x = dun.portal_x, goal_z = dun.portal_z;
	/* Priority: low HP -> health vial; missing key -> key; nearby chest/mana -> pickup; else portal */
	if (plr.hp < 65) {
		for (int i = 0; i < dun.n_items; i++) {
			if (dun.items[i].active && (dun.items[i].type == ITEM_HEALTH || dun.items[i].type == ITEM_CHEST)) {
				goal_x = dun.items[i].x, goal_z = dun.items[i].z;
				break;
			}
		}
	} else if (!plr.has_key) {
		for (int i = 0; i < dun.n_items; i++) {
			if (dun.items[i].active && dun.items[i].type == ITEM_KEY) {
				goal_x = dun.items[i].x, goal_z = dun.items[i].z;
				break;
			}
		}
	} else {
		/* Grab nearby chests/vials within 2.5 tiles on the way to the portal */
		for (int i = 0; i < dun.n_items; i++) {
			if (!dun.items[i].active)
				continue;
			float dx = dun.items[i].x - plr.x, dz = dun.items[i].z - plr.z;
			if (dx * dx + dz * dz < (CELL * 2.8f) * (CELL * 2.8f)) {
				goal_x = dun.items[i].x, goal_z = dun.items[i].z;
				break;
			}
		}
	}

	if (best_mon >= 0) {
		const struct monster *m = &dun.mons[best_mon];
		float tyaw = atan2f(m->x - plr.x, m->z - plr.z);
		float diff = tyaw - plr.yaw;
		while (diff > PI)
			diff -= 2.0f * PI;
		while (diff < -PI)
			diff += 2.0f * PI;
		plr.yaw += diff * (dt * 7.5f > 1.0f ? 1.0f : dt * 7.5f);
		float dy = (m->y + 4.2f) - plr.y;
		float tpitch = atan2f(dy, best_md > 4.0f ? best_md : 4.0f);
		plr.pitch += (tpitch - plr.pitch) * (dt * 6.0f);

		/* Choose optimal weapon based on range & mana */
		if (best_md < 12.5f)
			plr.wpn = 0;
		else if (plr.mana >= 28.0f && (m->kind >= MON_GOLEM || best_md > 36.0f))
			plr.wpn = 2;
		else if (plr.mana >= 10.0f)
			plr.wpn = 1;
		else
			plr.wpn = 0;

		if (fabsf(diff) < 0.28f)
			in->attack = 1;

		/* Tactical footwork: advance if using halberd or distant, circle-strafe at mid-range */
		plr.strafe_t -= dt;
		if (plr.strafe_t <= 0.0f) {
			plr.strafe_t = 0.85f + rndf() * 0.7f;
			plr.strafe_dir = (plr.strafe_dir > 0.0f) ? -1.0f : 1.0f;
		}
		if (plr.strafe_dir > 0.0f)
			in->strafe_r = 1;
		else
			in->strafe_l = 1;

		if (plr.wpn == 0 || best_md > 34.0f)
			in->fwd = 1;
		else if (best_md < 15.0f)
			in->back = 1;
		return;
	}

	/* Navigate via BFS to goal_x, goal_z */
	int sx = (int)(plr.x / CELL), sz = (int)(plr.z / CELL);
	int gx = (int)(goal_x / CELL), gz = (int)(goal_z / CELL);
	int nx = gx, nz = gz;
	float wp_x = goal_x, wp_z = goal_z;
	if (bfs_step(sx, sz, gx, gz, plr.has_key, &nx, &nz)) {
		wp_x = (nx + 0.5f) * CELL;
		wp_z = (nz + 0.5f) * CELL;
	}
	float tyaw = atan2f(wp_x - plr.x, wp_z - plr.z);
	float diff = tyaw - plr.yaw;
	while (diff > PI)
		diff -= 2.0f * PI;
	while (diff < -PI)
		diff += 2.0f * PI;
	plr.yaw += diff * (dt * 6.2f > 1.0f ? 1.0f : dt * 6.2f);
	plr.pitch += (0.0f - plr.pitch) * (dt * 4.5f);
	if (fabsf(diff) < 0.95f)
		in->fwd = 1;

	/* Unstick nudge if blocked on a corner */
	float moved = (plr.x - plr.last_x) * (plr.x - plr.last_x) + (plr.z - plr.last_z) * (plr.z - plr.last_z);
	if (moved < 0.25f) {
		plr.stuck_t += dt;
		if (plr.stuck_t > 0.45f)
			in->strafe_r = 1;
	} else {
		plr.stuck_t = 0.0f;
		plr.last_x = plr.x, plr.last_z = plr.z;
	}
}

static void sim_step(float dt, const struct plat_input *raw_in, float world_t)
{
	struct plat_input in = *raw_in;
	if (plr.autopilot)
		autopilot_control(dt, &in);

	/* Camera look */
	float turn_spd = 2.35f;
	if (in.turn_l)
		plr.yaw -= turn_spd * dt;
	if (in.turn_r)
		plr.yaw += turn_spd * dt;
	if (in.look_u)
		plr.pitch += 1.6f * dt;
	if (in.look_d)
		plr.pitch -= 1.6f * dt;
	plr.yaw += in.mdx * 0.0032f;
	plr.pitch -= in.mdy * 0.0026f;
	if (plr.pitch > 0.72f)
		plr.pitch = 0.72f;
	if (plr.pitch < -0.72f)
		plr.pitch = -0.72f;

	/* Player movement with smooth wall-sliding */
	float move_f = (float)in.fwd - (float)in.back;
	float move_s = (float)in.strafe_r - (float)in.strafe_l;
	float ml = sqrtf(move_f * move_f + move_s * move_s);
	if (ml > 1.0f)
		move_f /= ml, move_s /= ml;
	float spd = (in.sprint ? 42.0f : 31.0f);
	float cy = cosf(plr.yaw), sy = sinf(plr.yaw);
	float dx = (sy * move_f + cy * move_s) * spd * dt;
	float dz = (cy * move_f - sy * move_s) * spd * dt;
	if (!circle_blocked(plr.x + dx, plr.z, 3.3f, 0))
		plr.x += dx;
	if (!circle_blocked(plr.x, plr.z + dz, 3.3f, 0))
		plr.z += dz;

	int pgx = (int)(plr.x / CELL), pgz = (int)(plr.z / CELL);
	int on_liquid = (tile_at(pgx, pgz) == TILE_LIQUID);
	float base_eye = on_liquid ? 3.9f : 5.2f;
	if (ml > 0.15f) {
		plr.bob_t += dt * 9.5f;
		plr.step_t += dt;
		if (plr.step_t > 0.36f) {
			plr.step_t = 0.0f;
			if (snd.sfx_type < 0)
				keep_sfx(SFX_STEP);
		}
	}
	plr.y = base_eye + sinf(plr.bob_t) * (ml > 0.15f ? 0.26f : 0.04f);

	/* Lava floor hazard on Ember Forge */
	if (on_liquid && dun.floor_idx == 2) {
		static float lava_tick;
		lava_tick += dt;
		if (lava_tick > 0.55f) {
			lava_tick = 0.0f;
			plr.hp -= 4;
			plr.hurt_flash = 0.45f;
		}
	}

	reveal_around(plr.x, plr.z);

	if (in.use_door || in.mb_r)
		try_use_door(plr.x + sy * 8.0f, plr.z + cy * 8.0f);
	if (in.attack || in.mb_l)
		player_attack();

	if (plr.atk_cd > 0.0f)
		plr.atk_cd -= dt;
	if (plr.atk_t > 0.0f)
		plr.atk_t -= dt;
	if (plr.hurt_flash > 0.0f)
		plr.hurt_flash -= dt * 1.8f;
	if (plr.bonus_flash > 0.0f)
		plr.bonus_flash -= dt * 1.8f;
	if (plr.toast_t > 0.0f)
		plr.toast_t -= dt;
	plr.mana += dt * 3.8f;
	if (plr.mana > 100.0f)
		plr.mana = 100.0f;

	/* Animate sliding doors */
	for (int z = 1; z < MAP_N - 1; z++) {
		for (int x = 1; x < MAP_N - 1; x++) {
			if ((dun.tile[z][x] == TILE_DOOR || dun.tile[z][x] == TILE_LOCKED) &&
			    dun.door_open[z][x] > 0.0f && dun.door_open[z][x] < 1.0f) {
				dun.door_open[z][x] += dt * 1.35f;
				if (dun.door_open[z][x] > 1.0f)
					dun.door_open[z][x] = 1.0f;
			}
		}
	}

	/* Collect pickups */
	for (int i = 0; i < dun.n_items; i++) {
		struct item *it = &dun.items[i];
		if (!it->active)
			continue;
		float ix = it->x - plr.x, iz = it->z - plr.z;
		if (ix * ix + iz * iz < 6.2f * 6.2f) {
			it->active = 0;
			plr.bonus_flash = 0.65f;
			keep_sfx(SFX_PICKUP);
			if (it->type == ITEM_KEY) {
				plr.has_key = 1;
				plr.gold += 100;
				set_toast("GOLDEN RUNIC KEY ACQUIRED!");
			} else if (it->type == ITEM_HEALTH) {
				plr.hp = plr.hp + 35 > 100 ? 100 : plr.hp + 35;
				set_toast("VITALITY VIAL +35");
			} else if (it->type == ITEM_MANA) {
				plr.mana = plr.mana + 45.0f > 100.0f ? 100.0f : plr.mana + 45.0f;
				set_toast("ARCANA PRISM +45");
			} else {
				plr.gold += 75;
				plr.hp = plr.hp + 20 > 100 ? 100 : plr.hp + 20;
				plr.mana = plr.mana + 25.0f > 100.0f ? 100.0f : plr.mana + 25.0f;
				set_toast("RELIQUARY CHEST +75 GOLD!");
			}
		}
	}

	/* Update flying spell bolts */
	for (int i = 0; i < MAX_BOLTS; i++) {
		struct bolt *b = &dun.bolts[i];
		if (!b->active)
			continue;
		b->x += b->vx * dt;
		b->y += b->vy * dt;
		b->z += b->vz * dt;
		b->life -= dt;
		int gx = (int)(b->x / CELL), gz = (int)(b->z / CELL);
		int hit_wall = (b->life <= 0.0f || b->y < 0.2f || b->y > dun.ceil_y[gz & 31][gx & 31] ||
				tile_blocks_move(gx, gz, 1));
		if (b->from_plr) {
			int hit_m = -1;
			for (int m = 0; m < dun.n_mons; m++) {
				if (dun.mons[m].hp <= 0)
					continue;
				float dx2 = dun.mons[m].x - b->x, dz2 = dun.mons[m].z - b->z;
				if (dx2 * dx2 + dz2 * dz2 < 3.6f * 3.6f && fabsf(b->y - (dun.mons[m].y + 4.0f)) < 4.5f) {
					hit_m = m;
					break;
				}
			}
			if (hit_m >= 0 || hit_wall) {
				if (b->kind == 1) {
					/* Storm Scepter area shockwave */
					for (int m = 0; m < dun.n_mons; m++) {
						if (dun.mons[m].hp <= 0)
							continue;
						float dx2 = dun.mons[m].x - b->x, dz2 = dun.mons[m].z - b->z;
						float d2 = dx2 * dx2 + dz2 * dz2;
						if (d2 < 16.0f * 16.0f) {
							float d = sqrtf(d2) + 0.1f;
							damage_monster(m, m == hit_m ? 68 : 36, dx2 / d, dz2 / d);
						}
					}
				} else if (hit_m >= 0) {
					float vl = sqrtf(b->vx * b->vx + b->vz * b->vz) + 0.1f;
					damage_monster(hit_m, 34, b->vx / vl, b->vz / vl);
				}
				b->active = 0;
			}
		} else {
			/* Monster projectile vs player */
			float dx2 = plr.x - b->x, dz2 = plr.z - b->z;
			if (dx2 * dx2 + dz2 * dz2 < 3.2f * 3.2f && fabsf(plr.y - b->y) < 3.8f) {
				plr.hp -= 12;
				plr.hurt_flash = 0.65f;
				keep_sfx(SFX_HURT);
				b->active = 0;
			} else if (hit_wall) {
				b->active = 0;
			}
		}
	}

	/* Update Monsters + audio danger intensity */
	float max_danger = 0.0f;
	for (int i = 0; i < dun.n_mons; i++) {
		struct monster *m = &dun.mons[i];
		if (m->hp <= 0)
			continue;
		m->anim_t += dt * 4.2f;
		if (m->hurt_t > 0.0f)
			m->hurt_t -= dt;
		if (m->cd > 0.0f)
			m->cd -= dt;
		if (m->kind == MON_GARGOYLE)
			m->y = 1.3f + sinf(world_t * 3.6f + i) * 0.55f;

		float dx2 = plr.x - m->x, dz2 = plr.z - m->z;
		float d = sqrtf(dx2 * dx2 + dz2 * dz2);
		if (!m->awake && d < 96.0f && has_los(m->x, m->z, plr.x, plr.z))
			m->awake = 1;
		if (!m->awake)
			continue;
		float dg = 1.0f - d * (1.0f / 96.0f);
		if (dg > max_danger)
			max_danger = dg;

		m->yaw = atan2f(dx2, dz2);
		float mspd = m->kind == MON_GARGOYLE ? 20.0f : m->kind == MON_GOLEM ? 11.5f : 15.5f;
		if (d > 6.5f) {
			float mx = (dx2 / d) * mspd * dt, mz = (dz2 / d) * mspd * dt;
			int fly = (m->kind == MON_GARGOYLE);
			if (!circle_blocked(m->x + mx, m->z, 2.5f, fly))
				m->x += mx;
			if (!circle_blocked(m->x, m->z + mz, 2.5f, fly))
				m->z += mz;
		}
		if (d < 8.2f && m->cd <= 0.0f) {
			m->cd = 1.05f;
			plr.hp -= (m->kind == MON_GOLEM) ? 16 : 10;
			plr.hurt_flash = 0.75f;
			keep_sfx(SFX_HURT);
		} else if ((m->kind == MON_GARGOYLE || m->kind == MON_ARCHON) &&
			   d > 16.0f && d < 90.0f && m->cd <= 0.0f && has_los(m->x, m->z, plr.x, plr.z)) {
			m->cd = (m->kind == MON_ARCHON) ? 1.55f : 2.35f;
			float inv = 1.0f / d;
			float vy = (plr.y - (m->y + 5.2f)) * inv;
			spawn_bolt(0, 2, m->x + dx2 * inv * 2.2f, m->y + 5.2f, m->z + dz2 * inv * 2.2f,
				   dx2 * inv, vy, dz2 * inv, 44.0f);
		}
	}
	snd.danger = max_danger < 0.0f ? 0.0f : max_danger > 1.0f ? 1.0f : max_danger;

	/* Respawn on defeat (keeps crawl flowing smoothly) */
	if (plr.hp <= 0) {
		plr.hp = 100;
		plr.mana = 100.0f;
		plr.x = (dun.rooms[0].cx + 0.5f) * CELL;
		plr.z = (dun.rooms[0].cz + 0.5f) * CELL;
		set_toast("REVIVED AT CITADEL ENTRANCE!");
	}

	/* Descent Portal check */
	{
		float px = dun.portal_x - plr.x, pz = dun.portal_z - plr.z;
		if (px * px + pz * pz < 6.5f * 6.5f) {
			keep_sfx(SFX_PICKUP);
			generate_floor(dun.depth + 1, dun.seed);
			plr.hp = plr.hp + 30 > 100 ? 100 : plr.hp + 30;
			plr.mana = 100.0f;
			char msg[64];
			keep_fmt(msg, sizeof(msg), "DESCENDED TO FLOOR %d!", dun.depth);
			set_toast(msg);
		}
	}
}

#include "ui.h"

/* --- 3D Torchlit Dungeon World + Entities + Viewmodel Render Pass --- */
static void render_world(float world_t, const char *api_name, float fps, int show_hud, int show_fps, int show_map, int check_mode)
{
	/* Per-floor atmospheric fog, stone tint, and liquid tint */
	static const uint32_t fog_cols[4] = {0x0c0e18U, 0x0a1616U, 0x1e0c08U, 0x0c0c22U};
	static const uint32_t wall_tints[4] = {0xd8dce8U, 0xc4dcd4U, 0xe8c8b8U, 0xc8ccf0U};
	static const uint32_t liq_tints[4] = {0x3888e8U, 0x30c8a8U, 0xff6818U, 0x58c8ffU};
	int fi = dun.floor_idx & 3;
	uint32_t fog_rgb = fog_cols[fi];
	uint32_t wall_rgb = wall_tints[fi];
	uint32_t liq_rgb = liq_tints[fi];

	R->clear(fog_rgb);
	R->fog(28.0f, 185.0f, fog_rgb);
	reset_state();
	cam_setup(plr.x, plr.y, plr.z, plr.yaw, plr.pitch);

	/* Gather nearest dynamic point lights around the camera */
	if (fi == 2)
		clear_dlights(0.28f, 0.19f, 0.17f);
	else if (fi == 1)
		clear_dlights(0.19f, 0.25f, 0.24f);
	else
		clear_dlights(0.21f, 0.22f, 0.28f);

	/* Subtle player personal lantern aura so pitch-black corners remain readable */
	add_dlight(plr.x, plr.y + 0.5f, plr.z, 0.42f, 0.36f, 0.28f, 22.0f);

	/* Flying spell bolts cast bright colored dynamic light! */
	for (int i = 0; i < MAX_BOLTS; i++) {
		const struct bolt *b = &dun.bolts[i];
		if (!b->active)
			continue;
		if (b->kind == 0)
			add_dlight(b->x, b->y, b->z, 1.45f, 0.65f, 0.18f, 34.0f);
		else if (b->kind == 1)
			add_dlight(b->x, b->y, b->z, 0.35f, 1.15f, 1.55f, 40.0f);
		else
			add_dlight(b->x, b->y, b->z, 1.25f, 0.30f, 1.20f, 30.0f);
	}

	/* Portal & Runic Key dynamic lights */
	add_dlight(dun.portal_x, 5.5f, dun.portal_z, 0.35f, 1.15f, 1.45f, 42.0f);
	for (int i = 0; i < dun.n_items; i++) {
		if (dun.items[i].active && dun.items[i].type == ITEM_KEY)
			add_dlight(dun.items[i].x, 3.5f, dun.items[i].z, 1.25f, 0.95f, 0.25f, 32.0f);
	}

	/* Nearest flickering wall sconces */
	for (int pass = 0; pass < 2 && n_dlights < MAX_DLIGHTS; pass++) {
		float max_d2 = pass == 0 ? (96.0f * 96.0f) : (190.0f * 190.0f);
		float min_d2 = pass == 0 ? 0.0f : (96.0f * 96.0f);
		for (int i = 0; i < dun.n_torches && n_dlights < MAX_DLIGHTS; i++) {
			const struct torch *tc = &dun.torches[i];
			float dx = tc->x - plr.x, dz = tc->z - plr.z;
			float d2 = dx * dx + dz * dz;
			if (d2 < min_d2 || d2 >= max_d2)
				continue;
			float flk = check_mode ? 1.0f : (0.92f + 0.12f * sinf(world_t * 8.5f + tc->phase) +
							 0.06f * sinf(world_t * 19.3f + tc->phase * 2.1f));
			add_dlight(tc->x - sinf(tc->yaw) * 1.2f, tc->y + 0.6f, tc->z - cosf(tc->yaw) * 1.2f,
				   1.28f * flk, 0.72f * flk, 0.24f * flk, 40.0f);
		}
	}

	int cx = (int)(plr.x / CELL), cz = (int)(plr.z / CELL);
	int rad_tiles = 12;
	int gz0 = cz - rad_tiles < 1 ? 1 : cz - rad_tiles;
	int gz1 = cz + rad_tiles > MAP_N - 2 ? MAP_N - 2 : cz + rad_tiles;
	int gx0 = cx - rad_tiles < 1 ? 1 : cx - rad_tiles;
	int gx1 = cx + rad_tiles > MAP_N - 2 ? MAP_N - 2 : cx + rad_tiles;

	/* Pass 1: Subdivided Flagstone Floors & Vaulted Ceilings (TEX_FLOOR) */
	set_state(TEX_FLOOR, BLEND_NONE, DEPTH_RW, 1, 1, CLAMP_WRAP, 0);
	for (int gz = gz0; gz <= gz1; gz++) {
		for (int gx = gx0; gx <= gx1; gx++) {
			uint8_t t = dun.tile[gz][gx];
			if (t == TILE_WALL)
				continue;
			float x0 = gx * CELL, z0 = gz * CELL;
			float ch = dun.ceil_y[gz][gx];
			int near_cam = (abs(gx - cx) <= 5 && abs(gz - cz) <= 5);
			int sub = near_cam ? 2 : 1;
			float step = CELL / (float)sub, ustep = 1.0f / (float)sub;

			if (t != TILE_LIQUID) {
				for (int sz = 0; sz < sub; sz++) {
					for (int sx = 0; sx < sub; sx++) {
						float fx0 = x0 + sx * step, fz0 = z0 + sz * step;
						float u0 = sx * ustep, v0 = sz * ustep;
						float fp[4][3] = {
							{fx0, 0.0f, fz0}, {fx0 + step, 0.0f, fz0},
							{fx0 + step, 0.0f, fz0 + step}, {fx0, 0.0f, fz0 + step},
						};
						float fuv[4][2] = {{u0, v0}, {u0 + ustep, v0}, {u0 + ustep, v0 + ustep}, {u0, v0 + ustep}};
						draw_lit_quad(fp, fuv, 0.0f, 1.0f, 0.0f, wall_rgb, 0);
					}
				}
			}
			/* Vaulted stone ceiling */
			for (int sz = 0; sz < sub; sz++) {
				for (int sx = 0; sx < sub; sx++) {
					float fx0 = x0 + sx * step, fz0 = z0 + sz * step;
					float u0 = sx * ustep, v0 = sz * ustep;
					float cp[4][3] = {
						{fx0, ch, fz0 + step}, {fx0 + step, ch, fz0 + step},
						{fx0 + step, ch, fz0}, {fx0, ch, fz0},
					};
					float fuv[4][2] = {{u0, v0 + ustep}, {u0 + ustep, v0 + ustep}, {u0 + ustep, v0}, {u0, v0}};
					draw_lit_quad(cp, fuv, 0.0f, -1.0f, 0.0f, 0xa8acb8U, 0);
				}
			}
		}
	}

	/* Pass 2: Animated Sunken Liquid Canals / Molten Magma / Astral Ether (TEX_LIQUID) */
	set_state(TEX_LIQUID, BLEND_NONE, DEPTH_RW, 1, 1, CLAMP_WRAP, 0);
	float ushift = check_mode ? 0.0f : world_t * 0.14f;
	float vshift = check_mode ? 0.0f : sinf(world_t * 0.8f) * 0.12f;
	for (int gz = gz0; gz <= gz1; gz++) {
		for (int gx = gx0; gx <= gx1; gx++) {
			if (dun.tile[gz][gx] != TILE_LIQUID)
				continue;
			float x0 = gx * CELL, z0 = gz * CELL, ly = -1.6f;
			float lp[4][3] = {
				{x0, ly, z0}, {x0 + CELL, ly, z0},
				{x0 + CELL, ly, z0 + CELL}, {x0, ly, z0 + CELL},
			};
			float luv[4][2] = {
				{ushift, vshift}, {ushift + 1.0f, vshift},
				{ushift + 1.0f, vshift + 1.0f}, {ushift, vshift + 1.0f},
			};
			draw_lit_quad(lp, luv, 0.0f, 1.0f, 0.0f, liq_rgb, fi >= 2);
		}
	}

	/* Pass 3: Ashlar Stone Walls, Ceiling Step Lintels & Canal Pit Curbs (TEX_WALL) */
	set_state(TEX_WALL, BLEND_NONE, DEPTH_RW, 1, 1, CLAMP_WRAP, 0);
	static const int nb[4][2] = {{0, -1}, {0, 1}, {-1, 0}, {1, 0}};
	for (int gz = gz0; gz <= gz1; gz++) {
		for (int gx = gx0; gx <= gx1; gx++) {
			uint8_t t = dun.tile[gz][gx];
			if (t == TILE_WALL)
				continue;
			float x0 = gx * CELL, x1 = x0 + CELL, z0 = gz * CELL, z1 = z0 + CELL;
			float ch = dun.ceil_y[gz][gx];
			float by = (t == TILE_LIQUID) ? -1.6f : 0.0f;
			int near_cam = (abs(gx - cx) <= 5 && abs(gz - cz) <= 5);

			for (int d = 0; d < 4; d++) {
				int nx = gx + nb[d][0], nz = gz + nb[d][1];
				uint8_t nt = tile_at(nx, nz);
				float ax0 = (d == 0) ? x0 : (d == 1) ? x1 : (d == 2) ? x0 : x1;
				float az0 = (d == 0) ? z0 : (d == 1) ? z1 : (d == 2) ? z1 : z0;
				float ax1 = (d == 0) ? x1 : (d == 1) ? x0 : (d == 2) ? x0 : x1;
				float az1 = (d == 0) ? z0 : (d == 1) ? z1 : (d == 2) ? z0 : z1;
				float wnx = (float)-nb[d][0], wnz = (float)-nb[d][1];

				if (nt == TILE_WALL) {
					int sh = near_cam ? 2 : 1;
					for (int s = 0; s < sh; s++) {
						float f0 = (float)s / sh, f1 = (float)(s + 1) / sh;
						float sx0 = ax0 + (ax1 - ax0) * f0, sz0 = az0 + (az1 - az0) * f0;
						float sx1 = ax0 + (ax1 - ax0) * f1, sz1 = az0 + (az1 - az0) * f1;
						float ym = (by + ch) * 0.5f;
						float vt = (ch - by) / CELL;
						float wp0[4][3] = {{sx0, ym, sz0}, {sx1, ym, sz1}, {sx1, by, sz1}, {sx0, by, sz0}};
						float wuv0[4][2] = {{f0, vt * 0.5f}, {f1, vt * 0.5f}, {f1, vt}, {f0, vt}};
						float wp1[4][3] = {{sx0, ch, sz0}, {sx1, ch, sz1}, {sx1, ym, sz1}, {sx0, ym, sz0}};
						float wuv1[4][2] = {{f0, 0.0f}, {f1, 0.0f}, {f1, vt * 0.5f}, {f0, vt * 0.5f}};
						draw_lit_quad(wp0, wuv0, wnx, 0.0f, wnz, wall_rgb, 0);
						draw_lit_quad(wp1, wuv1, wnx, 0.0f, wnz, wall_rgb, 0);
					}
				} else {
					/* Upper lintel where high room ceiling meets lower corridor ceiling */
					float nch = dun.ceil_y[nz][nx];
					if (ch > nch + 0.1f) {
						float vt = (ch - nch) / CELL;
						float lp[4][3] = {{ax0, ch, az0}, {ax1, ch, az1}, {ax1, nch, az1}, {ax0, nch, az0}};
						float luv[4][2] = {{0.0f, 0.0f}, {1.0f, 0.0f}, {1.0f, vt}, {0.0f, vt}};
						draw_lit_quad(lp, luv, wnx, 0.0f, wnz, wall_rgb, 0);
					}
					/* Sunken canal stone curb */
					if (t == TILE_LIQUID && nt != TILE_LIQUID) {
						float cp2[4][3] = {{ax0, 0.0f, az0}, {ax1, 0.0f, az1}, {ax1, -1.6f, az1}, {ax0, -1.6f, az0}};
						float cuv[4][2] = {{0.0f, 0.0f}, {1.0f, 0.0f}, {1.0f, 0.2f}, {0.0f, 0.2f}};
						draw_lit_quad(cp2, cuv, wnx, 0.0f, wnz, wall_rgb, 0);
					}
				}
			}
		}
	}

	/* Pass 4: Sliding Iron-Bound Oak Doors & Glowing Runegate (TEX_DOOR) */
	set_state(TEX_DOOR, BLEND_NONE, DEPTH_RW, 1, 1, CLAMP_ALL, 0);
	for (int gz = gz0; gz <= gz1; gz++) {
		for (int gx = gx0; gx <= gx1; gx++) {
			uint8_t t = dun.tile[gz][gx];
			if (t != TILE_DOOR && t != TILE_LOCKED)
				continue;
			float open = dun.door_open[gz][gx];
			if (open >= 0.99f)
				continue;
			float ch = dun.ceil_y[gz][gx];
			float y0 = open * (ch - 1.2f), y1 = y0 + ch;
			uint32_t dtint = (t == TILE_LOCKED) ? 0xffb878U : 0xffffffU;
			float cx0 = (gx + 0.5f) * CELL, cz0 = (gz + 0.5f) * CELL;
			float hx = dun.door_ns[gz][gx] ? CELL * 0.5f : 1.1f;
			float hz = dun.door_ns[gz][gx] ? 1.1f : CELL * 0.5f;
			float duv[4][2] = {{0, 0}, {1, 0}, {1, 1}, {0, 1}};
			float f1[4][3] = {{cx0 - hx, y1, cz0 - hz}, {cx0 + hx, y1, cz0 - hz}, {cx0 + hx, y0, cz0 - hz}, {cx0 - hx, y0, cz0 - hz}};
			float f2[4][3] = {{cx0 + hx, y1, cz0 + hz}, {cx0 - hx, y1, cz0 + hz}, {cx0 - hx, y0, cz0 + hz}, {cx0 + hx, y0, cz0 + hz}};
			float f3[4][3] = {{cx0 - hx, y1, cz0 + hz}, {cx0 - hx, y1, cz0 - hz}, {cx0 - hx, y0, cz0 - hz}, {cx0 - hx, y0, cz0 + hz}};
			float f4[4][3] = {{cx0 + hx, y1, cz0 - hz}, {cx0 + hx, y1, cz0 + hz}, {cx0 + hx, y0, cz0 + hz}, {cx0 + hx, y0, cz0 - hz}};
			draw_lit_quad(f1, duv, 0, 0, -1, dtint, t == TILE_LOCKED);
			draw_lit_quad(f2, duv, 0, 0, 1, dtint, t == TILE_LOCKED);
			draw_lit_quad(f3, duv, -1, 0, 0, dtint, 0);
			draw_lit_quad(f4, duv, 1, 0, 0, dtint, 0);
		}
	}

	/* Pass 5: Sculpted 3D Dungeon Columns, Wall Sconces, Pickups, Portal & Monsters (TEX_MESH) */
	set_state(TEX_MESH, BLEND_NONE, DEPTH_RW, 1, 1, CLAMP_WRAP, 0);
	for (int gz = gz0; gz <= gz1; gz++) {
		for (int gx = gx0; gx <= gx1; gx++) {
			if (dun.tile[gz][gx] == TILE_PILLAR)
				draw_mesh_world(MESH_PILLAR, (gx + 0.5f) * CELL, 0.0f, (gz + 0.5f) * CELL,
						0.0f, 1.35f, dun.ceil_y[gz][gx], 1.35f, wall_rgb, 0.0f);
		}
	}
	for (int i = 0; i < dun.n_torches; i++) {
		const struct torch *tc = &dun.torches[i];
		float dx = tc->x - plr.x, dz = tc->z - plr.z;
		if (dx * dx + dz * dz < 195.0f * 195.0f)
			draw_mesh_world(MESH_SCONCE, tc->x, tc->y, tc->z, tc->yaw + PI, 1.0f, 1.0f, 1.0f, 0xffffffU, 0.0f);
	}
	draw_mesh_world(MESH_PORTAL, dun.portal_x, 0.0f, dun.portal_z, 0.0f, 1.0f, 1.0f, 1.0f, 0xd8e8ffU, 0.0f);

	for (int i = 0; i < dun.n_items; i++) {
		const struct item *it = &dun.items[i];
		if (!it->active)
			continue;
		float bob = check_mode ? 0.4f : (0.55f + 0.35f * sinf(world_t * 3.2f + it->phase));
		float spin = check_mode ? 0.6f : (world_t * 1.9f + it->phase);
		if (it->type == ITEM_CHEST)
			draw_mesh_world(MESH_CHEST, it->x, 0.0f, it->z, it->phase, 1.0f, 1.0f, 1.0f, 0xffffffU, 0.0f);
		else if (it->type == ITEM_KEY)
			draw_mesh_world(MESH_KEY, it->x, 1.2f + bob, it->z, spin, 1.15f, 1.15f, 1.15f, 0xffdf60U, 0.25f);
		else if (it->type == ITEM_HEALTH)
			draw_mesh_world(MESH_VIAL, it->x, 0.6f + bob, it->z, spin, 1.0f, 1.0f, 1.0f, 0xff4048U, 0.2f);
		else
			draw_mesh_world(MESH_VIAL, it->x, 0.6f + bob, it->z, spin, 1.0f, 1.0f, 1.0f, 0x48b8ffU, 0.2f);
	}

	for (int i = 0; i < dun.n_mons; i++) {
		const struct monster *m = &dun.mons[i];
		if (m->hp <= 0)
			continue;
		int mid = m->kind == MON_GARGOYLE ? MESH_GARGOYLE :
			  m->kind == MON_GOLEM ? MESH_GOLEM :
			  m->kind == MON_ARCHON ? MESH_ARCHON : MESH_SENTINEL;
		float sway = check_mode ? 0.0f : sinf(m->anim_t) * 0.08f;
		draw_mesh_world(mid, m->x, m->y, m->z, m->yaw + sway, 0.92f, 0.92f, 0.92f, 0xffffffU,
				m->hurt_t > 0.0f ? 1.0f : 0.0f);
	}

	/* Pass 6: Additive Torch Flames, Portal Rift & Spell Bolt Coronas (TEX_FLARE, DEPTH_RO) */
	set_state(TEX_FLARE, BLEND_ADD, DEPTH_RO, 0, 1, CLAMP_ALL, 0);
	for (int i = 0; i < dun.n_torches; i++) {
		const struct torch *tc = &dun.torches[i];
		float dx = tc->x - plr.x, dz = tc->z - plr.z;
		if (dx * dx + dz * dz > 195.0f * 195.0f)
			continue;
		float flk = check_mode ? 1.0f : (0.90f + 0.16f * sinf(world_t * 11.0f + tc->phase));
		float fx = tc->x - sinf(tc->yaw) * 0.28f, fz = tc->z - cosf(tc->yaw) * 0.28f;
		draw_billboard(fx, tc->y + 0.95f, fz, 1.45f * flk, 0xff8824U, 0.92f);
		draw_billboard(fx, tc->y + 1.05f, fz, 0.72f * flk, 0xfff0a0U, 0.95f);
	}
	/* Shimmering Descent Portal vortex */
	draw_billboard(dun.portal_x, 4.8f, dun.portal_z, 3.6f, 0x28b8ffU, 0.85f);
	draw_billboard(dun.portal_x, 4.8f, dun.portal_z, 2.0f, 0xb8f8ffU, 0.92f);

	for (int i = 0; i < MAX_BOLTS; i++) {
		const struct bolt *b = &dun.bolts[i];
		if (!b->active)
			continue;
		uint32_t bc = b->kind == 0 ? 0xff7820U : b->kind == 1 ? 0x48f0ffU : 0xe848ffU;
		draw_billboard(b->x, b->y, b->z, b->kind == 1 ? 2.1f : 1.45f, bc, 0.95f);
		draw_billboard(b->x, b->y, b->z, 0.75f, 0xffffffU, 0.95f);
	}

	/* Pass 7: First-Person 3D Held Weapon Viewmodel */
	set_state(TEX_MESH, BLEND_NONE, DEPTH_RW, 0, 1, CLAMP_WRAP, 0);
	{
		int wmesh = plr.wpn == 1 ? MESH_WPN_ROD : plr.wpn == 2 ? MESH_WPN_SCEPTER : MESH_WPN_HALBERD;
		float bobx = check_mode ? 0.0f : cosf(plr.bob_t * 0.5f) * 0.06f;
		float boby = check_mode ? 0.0f : fabsf(sinf(plr.bob_t * 0.5f)) * -0.06f;
		float sw = plr.atk_t > 0.0f ? sinf((plr.atk_t / (plr.wpn == 0 ? 0.40f : 0.32f)) * PI) : 0.0f;
		float ox = 0.88f + bobx - (plr.wpn == 0 ? sw * 0.52f : 0.0f);
		float oy = -0.82f + boby - (plr.wpn != 0 ? sw * 0.14f : sw * 0.10f);
		float oz = 2.05f - (plr.wpn != 0 ? sw * 0.28f : -sw * 0.22f);
		float wpitch = 0.28f + (plr.wpn == 0 ? sw * 0.95f : sw * 0.22f);
		float wroll = 0.16f + (plr.wpn == 0 ? sw * 0.65f : 0.0f);
		draw_weapon_view(wmesh, ox, oy, oz, wpitch, wroll, -0.18f, 0.68f);
	}

	/* Pass 8: Scaled 2D Gothic HUD + Automap */
	if (show_hud)
		draw_hud(api_name, fps, show_fps, show_map, check_mode);
	flush();
}

/* --- Deterministic -check Scene & Pixel Probe Verification --- */
struct probe {
	const char *name;
	int x, y;
	uint8_t rgb[3];
	int ok;
};

static void setup_check_scene(void)
{
	generate_floor(1, 0x5753484bU);
	plr.x = 5.5f * CELL;
	plr.z = 4.2f * CELL;
	plr.y = 5.2f;
	plr.yaw = 0.0f; /* Looking straight +Z across Torchlit Entry Hall */
	plr.pitch = 0.0f;
	plr.hp = 100;
	plr.mana = 100.0f;
	plr.wpn = 1;
	plr.has_key = 1;
	plr.autopilot = 0;
	/* Place guaranteed wall torches & Sentinel + Key directly in camera view */
	dun.n_torches = 0;
	dun.torches[dun.n_torches++] = (struct torch){3.15f * CELL, 8.0f, 6.5f * CELL, -PI * 0.5f, 0.0f};
	dun.torches[dun.n_torches++] = (struct torch){7.85f * CELL, 8.0f, 6.5f * CELL, PI * 0.5f, 0.0f};
	dun.torches[dun.n_torches++] = (struct torch){5.5f * CELL, 8.0f, 7.9f * CELL, PI, 0.0f};
	dun.n_mons = 1;
	dun.mons[0] = (struct monster){MON_SENTINEL, 80, 80, 5.5f * CELL, 0.0f, 6.4f * CELL, PI, 0, 0, 0, 1};
	reveal_around(plr.x, plr.z);
}

static int collect_probes(const struct backend *be, struct probe out[6])
{
	int W = keep_view.w, H = keep_view.h;
	float u = H * (1.0f / 480.0f);
	float bw = 186.0f * u, bh = 36.0f * u;
	int by_mid = (int)(H - 10.0f * u - bh + 25.0f * u);
	int msz = (int)(108.0f * u);

	out[0] = (struct probe){"vitality-bar", (int)(10.0f * u + bw * 0.45f), by_mid, {0}, 0};
	out[1] = (struct probe){"mana-bar", (int)(W - 10.0f * u - bw * 0.55f), by_mid, {0}, 0};
	out[2] = (struct probe){"torchlit-hall", W / 2, (int)(H * 0.44f), {0}, 0};
	out[3] = (struct probe){"flagstone-floor", (int)(W * 0.36f), (int)(H * 0.74f), {0}, 0};
	out[4] = (struct probe){"quest-hud-panel", (int)(24.0f * u), (int)(24.0f * u), {0}, 0};
	out[5] = (struct probe){"minimap-panel", W - msz / 2 - (int)(10.0f * u), (int)(10.0f * u) + msz / 2, {0}, 0};

	for (int i = 0; i < 6; i++)
		be->pixel(out[i].x, out[i].y, out[i].rgb);

	/* 0: Bright crimson Vitality bar */
	out[0].ok = (out[0].rgb[0] >= 140 && out[0].rgb[0] > out[0].rgb[2] + 70);
	/* 1: Bright sapphire Arcana Mana bar */
	out[1].ok = (out[1].rgb[2] >= 140 && out[1].rgb[2] > out[1].rgb[0] + 70);
	/* 2: Torchlit hall center / Sentinel (non-black lit geometry) */
	out[2].ok = ((int)out[2].rgb[0] + out[2].rgb[1] + out[2].rgb[2] >= 80);
	/* 3: Torchlit flagstone floor */
	out[3].ok = ((int)out[3].rgb[0] + out[3].rgb[1] + out[3].rgb[2] >= 65);
	/* 4: Dark gothic HUD panel interior */
	out[4].ok = (out[4].rgb[0] < 160 && out[4].rgb[2] < 180);
	/* 5: Top-right minimap explored tile / marker */
	out[5].ok = ((int)out[5].rgb[0] + out[5].rgb[1] + out[5].rgb[2] >= 35);

	int bad = 0;
	for (int i = 0; i < 6; i++)
		if (!out[i].ok)
			bad++;
	return bad;
}

static void list_res_for(const struct backend *be, char *buf, int cap)
{
	int p = 0;
	buf[0] = 0;
	for (int i = 0; i < NRES; i++) {
		if (be->res_ok(RES[i][0], RES[i][1]))
			p += keep_fmt(buf + p, cap - p, "%s%dx%d", p ? ", " : "", RES[i][0], RES[i][1]);
	}
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
		if ((!atest.rate && now - t0 > 2000000U) || now - t0 > 20000000U || plat_key() == KKEY_ESC)
			break;
		plat_sleep(5);
	}
	plat_audio_close();
	keep_log("AUDIOTEST rate=%d frames=%u of %d secs=%.2f", atest.rate, atest.sig_frames,
		 AUDIOSIG_FRAMES(atest.rate), (uint32_t)(plat_us() - t0) / 1e6);
	keep_log(!atest.rate ? "FAIL no audio device" : status ? "FAIL the signature did not play to the end" : "PASS");
	keep_log("CLOSED");
	return status;
}

int keep_main(int argc, char **argv, const struct backend *be)
{
	int w = 640, h = 480, check = 0, bench = 0, auto_mode = 0, sound_on = 1, hud_on = 1;
	int hold_s = 0, wait_s = 0, time_lim = 0, start_floor = 1, audiotest = 0;
	uint32_t seed = 0x5753484bU;
	float gamma_v = 1.0f;

	for (int i = 1; i < argc; i++) {
		const char *a = argv[i];
		if (str_eq(a, "-res") && i + 1 < argc) {
			if (parse_res(argv[++i], &w, &h) != 0)
				w = -1, h = -1;
		} else if (str_eq(a, "-check")) {
			check = 1;
		} else if (str_eq(a, "-bench") && i + 1 < argc) {
			if (parse_int(argv[++i], &bench) != 0 || bench < 1)
				bench = 1;
		} else if (str_eq(a, "-auto")) {
			auto_mode = 1;
		} else if (str_eq(a, "-seed") && i + 1 < argc) {
			seed = parse_uint_any(argv[++i]);
		} else if (str_eq(a, "-floor") && i + 1 < argc) {
			if (parse_int(argv[++i], &start_floor) != 0 || start_floor < 1)
				start_floor = 1;
		} else if (str_eq(a, "-nosound")) {
			sound_on = 0;
		} else if (str_eq(a, "-hud")) {
			hud_on = 1;
		} else if (str_eq(a, "-nohud")) {
			hud_on = 0;
		} else if (str_eq(a, "-gamma") && i + 1 < argc) {
			gamma_v = parse_float_or(argv[++i], 1.0f);
		} else if (str_eq(a, "-hold") && i + 1 < argc) {
			parse_int(argv[++i], &hold_s);
		} else if (str_eq(a, "-wait") && i + 1 < argc) {
			parse_int(argv[++i], &wait_s);
		} else if (str_eq(a, "-time") && i + 1 < argc) {
			parse_int(argv[++i], &time_lim);
		} else if (str_eq(a, "-tag") && i + 1 < argc) {
			log_tag = argv[++i];
		} else if (str_eq(a, "-log") && i + 1 < argc) {
			i++; /* handled by platform layer */
		} else if (str_eq(a, "-audiotest")) {
			audiotest = 1;
		}
	}

	if (audiotest)
		return run_audiotest();

	if (wait_s > 0)
		plat_sleep(wait_s * 1000);

	const char *mode = (check && bench) ? "check+bench" : check ? "check" : bench ? "bench" : auto_mode ? "auto" : "game";
	keep_log("START api=%s res=%dx%d mode=%s", be->name, w, h, mode);

	if (!be->res_ok(w, h)) {
		char ok_list[128];
		list_res_for(be, ok_list, sizeof(ok_list));
		keep_log("ERROR %s can't open %dx%d (it can: %s)", be->name, w, h, ok_list);
		keep_log("CLOSED");
		return 2;
	}

	R = be;
	keep_view.w = w, keep_view.h = h;
	keep_view.f = (float)(h * 0.866);
	keep_view.znear = 0.85f, keep_view.zfar = 220.0f;

	uint32_t t_open0 = plat_us();
	if (be->open(w, h) != 0) {
		keep_log("ERROR %s open %dx%d failed", be->name, w, h);
		keep_log("CLOSED");
		return 2;
	}
	uint32_t open_ms = (plat_us() - t_open0) / 1000U;
	char wrev[80] = "host";
	if (!plat_wrapper_rev(wrev, sizeof(wrev)))
		str_copy(wrev, "native", sizeof(wrev));
	keep_log("VERSION %s, wrapper %s, opened %dx%d in %u ms", be->version(), wrev, w, h, open_ms);

	build_meshes();
	build_textures(be);
	if (gamma_v != 1.0f)
		be->gamma(gamma_v);

	int rc = 0;

	/* 1. Optional deterministic -check self-test */
	if (check) {
		setup_check_scene();
		render_world(0.0f, be->name, 60.0f, 1, 0, 0, 1);
		if (!be->read()) {
			keep_log("CHECK part=citadel FAIL backbuffer read failed");
			rc = 1;
		} else {
			struct probe pr[6];
			int bad = collect_probes(be, pr);
			for (int i = 0; i < 6; i++) {
				if (!pr[i].ok)
					keep_log("PROBE_FAIL %s at (%d,%d) rgb=%02x%02x%02x",
						 pr[i].name, pr[i].x, pr[i].y, pr[i].rgb[0], pr[i].rgb[1], pr[i].rgb[2]);
			}
			if (bad == 0)
				keep_log("CHECK part=citadel PASS 6 probes");
			else {
				keep_log("CHECK part=citadel FAIL %d of 6 probes", bad);
				rc = 1;
			}
			if (hold_s > 0 && !bench) {
				be->swap(1);
				for (int i = 0; i < 6; i++)
					keep_log("PROBE %d %d %02x%02x%02x", pr[i].x, pr[i].y,
						 pr[i].rgb[0], pr[i].rgb[1], pr[i].rgb[2]);
				keep_log("FRAME");
				plat_sleep(hold_s * 1000);
			}
		}
		if (!bench) {
			keep_log(rc == 0 ? "PASS" : "FAIL check failed");
			be->close(1);
			keep_log("CLOSED");
			return rc;
		}
	}

	/* 2. Optional -bench N unthrottled benchmark */
	if (bench > 0) {
		memset(&plr, 0, sizeof(plr));
		plr.hp = 100, plr.mana = 100.0f, plr.wpn = 1, plr.autopilot = 1;
		generate_floor(start_floor, seed);
		uint32_t tb0 = plat_us();
		for (int f = 0; f < bench; f++) {
			struct plat_input zin = {0};
			sim_step(1.0f / 60.0f, &zin, f * (1.0f / 60.0f));
			render_world(f * (1.0f / 60.0f), be->name, 60.0f, hud_on, 0, 0, 0);
			be->swap(0);
		}
		double secs = (plat_us() - tb0) * 1e-6;
		if (secs < 1e-6)
			secs = 1e-6;
		keep_log("BENCH part=citadel frames=%d secs=%.2f fps=%.1f", bench, secs, bench / secs);
		if (hold_s > 0)
			plat_sleep(hold_s * 1000);
		keep_log(rc == 0 ? "PASS" : "FAIL check failed");
		be->close(1);
		keep_log("CLOSED");
		return rc;
	}

	/* 3. Interactive / Autopilot Dungeon Crawl Loop */
	memset(&plr, 0, sizeof(plr));
	plr.hp = 100, plr.mana = 100.0f, plr.wpn = 0, plr.autopilot = auto_mode;
	generate_floor(start_floor, seed);
	{
		static const char *const enter_msg[4] = {
			"ENTER THE OBSIDIAN BASTION!",
			"DESCEND INTO FLOODED CATACOMBS!",
			"BRAVE THE EMBER FORGE!",
			"APPROACH THE ASTRAL SANCTUM!",
		};
		set_toast(enter_msg[dun.floor_idx & 3]);
	}

	if (sound_on)
		plat_audio_init(1);

	int res_idx = 0;
	for (int i = 0; i < NRES; i++)
		if (RES[i][0] == w && RES[i][1] == h)
			res_idx = i;

	int show_fps = 0, show_map = 0, running = 1;
	uint32_t t_start = plat_us(), t_prev = t_start;
	float fps_smooth = 60.0f, world_t = 0.0f;

	while (running) {
		uint32_t now = plat_us();
		float dt = (now - t_prev) * 1e-6f;
		t_prev = now;
		if (dt < 0.0005f)
			dt = 0.0005f;
		if (dt > 0.08f)
			dt = 0.08f;
		world_t += dt;

		float inst_fps = 1.0f / dt;
		fps_smooth = fps_smooth * 0.92f + inst_fps * 0.08f;
		frame_ms_hist[frame_ms_idx % 120] = dt * 1000.0f;
		frame_ms_idx++;

		if (time_lim > 0 && (now - t_start) >= (uint32_t)time_lim * 1000000U)
			break;

		int key;
		while ((key = plat_key()) != 0) {
			if (key == KKEY_ESC) {
				running = 0;
			} else if (key == '1' || key == '2' || key == '3') {
				plr.wpn = key - '1';
			} else if (key == KKEY_TAB || key == 'm' || key == 'M') {
				show_map = !show_map;
			} else if (key == 'h' || key == 'H') {
				hud_on = !hud_on;
			} else if (key == 'f' || key == 'F') {
				show_fps = !show_fps;
			} else if (key == 'p' || key == 'P') {
				plr.autopilot = !plr.autopilot;
				set_toast(plr.autopilot ? "AUTOPILOT ENGAGED" : "MANUAL CONTROL");
			} else if (key == 'g' || key == 'G') {
				gamma_v += 0.2f;
				if (gamma_v > 1.85f)
					gamma_v = 1.0f;
				be->gamma(gamma_v);
			} else if (key == 'r' || key == 'R') {
				for (int step = 1; step <= NRES; step++) {
					int ni = (res_idx + step) % NRES;
					if (!be->res_ok(RES[ni][0], RES[ni][1]))
						continue;
					be->close(0);
					if (be->open(RES[ni][0], RES[ni][1]) == 0) {
						res_idx = ni;
						keep_view.w = RES[ni][0], keep_view.h = RES[ni][1];
						keep_view.f = (float)(keep_view.h * 0.866);
						build_textures(be);
						be->gamma(gamma_v);
					} else {
						be->open(keep_view.w, keep_view.h);
						build_textures(be);
					}
					break;
				}
			} else if (key == 'e' || key == 'E' || key == KKEY_ENTER) {
				try_use_door(plr.x + sinf(plr.yaw) * 8.0f, plr.z + cosf(plr.yaw) * 8.0f);
			}
		}

		struct plat_input in;
		memset(&in, 0, sizeof(in));
		plat_poll_input(&in);
		/* Disengage autopilot on deliberate movement keys so manual takeover feels instant */
		if (plr.autopilot && !auto_mode && (in.fwd || in.back || in.strafe_l || in.strafe_r))
			plr.autopilot = 0;

		sim_step(dt, &in, world_t);
		if (sound_on)
			plat_audio_tick();

		render_world(world_t, be->name, fps_smooth, hud_on, show_fps, show_map, 0);
		be->swap(1);
	}

	if (sound_on)
		plat_audio_close();
	be->close(1);
	keep_log("CLOSED");
	return 0;
}
