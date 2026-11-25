/*
 * ui.h: 3D polygon cockpit canopy, 3D holo-radar, target lead reticle, galaxy starmap, station
 * upgrade & field synthesizer computer, title screen, FPS HUD and -check verification scenes.
 * Included by space.c.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_SPACE_UI_H
#define WSH_SPACE_UI_H

static const char *api_version = "", *wrapper_rev = "not found";

#define GRAPH_N 64
static float ft_ms[GRAPH_N];
static int ft_pos;
static double hud_fps;

struct probe {
	int x, y;
	int rgb[3];
	const char *what;
};
#define MAXPROBES 12
static struct probe probes[MAXPROBES];
static int nprobes;

static void add_probe(int x, int y, int r, int g, int b, const char *what)
{
	if (nprobes >= MAXPROBES)
		return;
	struct probe *p = &probes[nprobes++];
	p->x = clampi(x, 0, space_view.w - 1);
	p->y = clampi(y, 0, space_view.h - 1);
	p->rgb[0] = clampi(r, 0, 255);
	p->rgb[1] = clampi(g, 0, 255);
	p->rgb[2] = clampi(b, 0, 255);
	p->what = what;
}

static void draw_bar(float x, float y, float w, float h, float frac, uint32_t col, uint32_t bg)
{
	frac = clampf(frac, 0.0f, 1.0f);
	r_rect(x, y, x + w, y + h, bg);
	if (frac > 0.005f)
		r_rect(x + 1.0f, y + 1.0f, x + 1.0f + (w - 2.0f) * frac, y + h - 1.0f, col);
	r_box_outline(x, y, x + w, y + h, 1.0f, 0xff507090U);
}

/* Draw 3D holo-radar disc + elevation stems on center dashboard */
static void draw_radar(float cx, float cy, float rx, float ry)
{
	r_state(-1, BLEND_ALPHA, 0, 0, 1, 0, 1);
	/* Dark radar backing & concentric range rings */
	const int N = 24;
	for (int i = 0; i < N; i++) {
		float a0 = (float)i / N * (float)TAU, a1 = (float)(i + 1) / N * (float)TAU;
		struct dvtx c0 = v2d(cx, cy, 0xc006121eU, 0, 0);
		struct dvtx p0 = v2d(cx + m_cosf(a0) * rx, cy + m_sinf(a0) * ry, 0xd00a2438U, 0, 0);
		struct dvtx p1 = v2d(cx + m_cosf(a1) * rx, cy + m_sinf(a1) * ry, 0xd00a2438U, 0, 0);
		r_tri_raw(&c0, &p0, &p1);
		r_line2d(p0.x, p0.y, p1.x, p1.y, 1.4f, 0xff3090c0U);
		r_line2d(cx + m_cosf(a0) * rx * 0.5f, cy + m_sinf(a0) * ry * 0.5f,
			 cx + m_cosf(a1) * rx * 0.5f, cy + m_sinf(a1) * ry * 0.5f, 1.0f, 0x80206080U);
	}
	/* Forward FOV V-cone on radar */
	r_line2d(cx, cy, cx - rx * 0.55f, cy - ry * 0.82f, 1.0f, 0x9040b0ffU);
	r_line2d(cx, cy, cx + rx * 0.55f, cy - ry * 0.82f, 1.0f, 0x9040b0ffU);

	const float range = 900.0f;
	/* Station blip (bright green) */
	if (gs.has_station) {
		v3f v = world_to_view(gs.st_pos);
		float px = clampf(v.x / range, -0.92f, 0.92f), pz = clampf(v.z / range, -0.92f, 0.92f);
		float py = clampf(v.y / range, -0.6f, 0.6f);
		float bx = cx + px * rx, bz = cy - pz * ry, by = bz - py * ry * 0.9f;
		r_line2d(bx, bz, bx, by, 1.2f, 0xa040ff80U);
		r_rect(bx - 3.0f, by - 3.0f, bx + 3.0f, by + 3.0f, 0xff40ff80U);
	}
	/* Asteroids (amber / ore-tinted) */
	for (int i = 0; i < MAX_AST; i++) {
		if (!gs.ast[i].active)
			continue;
		v3f v = world_to_view(gs.ast[i].pos);
		if (v.x * v.x + v.y * v.y + v.z * v.z > range * range)
			continue;
		float bx = cx + (v.x / range) * rx, bz = cy - (v.z / range) * ry;
		float by = bz - clampf(v.y / range, -0.55f, 0.55f) * ry * 0.85f;
		uint32_t col = ore_cols[gs.ast[i].ore];
		r_line2d(bx, bz, bx, by, 1.0f, (col & 0x00ffffffU) | 0x70000000U);
		r_rect(bx - 1.5f, by - 1.5f, bx + 1.5f, by + 1.5f, col);
	}
	/* Crystals (cyan) */
	for (int i = 0; i < MAX_CRYSTALS; i++) {
		if (!gs.crys[i].active)
			continue;
		v3f v = world_to_view(gs.crys[i].pos);
		if (v.x * v.x + v.y * v.y + v.z * v.z > range * range)
			continue;
		float bx = cx + (v.x / range) * rx, bz = cy - (v.z / range) * ry;
		r_rect(bx - 1.5f, bz - 1.5f, bx + 1.5f, bz + 1.5f, 0xff80ffffU);
	}
	/* Hostile Drones (bright red) */
	for (int i = 0; i < MAX_DRONES; i++) {
		if (!gs.drones[i].active)
			continue;
		v3f v = world_to_view(gs.drones[i].pos);
		float d = m_sqrtf(v.x * v.x + v.z * v.z);
		float s = d > range * 0.92f ? (range * 0.92f) / d : 1.0f;
		float bx = cx + (v.x * s / range) * rx, bz = cy - (v.z * s / range) * ry;
		float by = bz - clampf(v.y / range, -0.6f, 0.6f) * ry * 0.9f;
		r_line2d(bx, bz, bx, by, 1.4f, 0xc0ff3030U);
		r_rect(bx - 2.5f, by - 2.5f, bx + 2.5f, by + 2.5f, 0xffff3030U);
	}
}

/* Draw 3D cockpit struts, target lock HUD, lead indicator, gauges and cargo readout */
static void draw_cockpit_hud(void)
{
	float W = (float)space_view.w, H = (float)space_view.h;
	float u = H / 480.0f;
	float sx = gs.sway_x * 14.0f * u, sy = gs.sway_y * 10.0f * u;

	/* Target lock box + lead pip in 3D space */
	if (gs.tgt_kind > 0) {
		v3f tpos = v3_make(0, 0, 0), tvel = v3_make(0, 0, 0);
		float hp_frac = 1.0f;
		uint32_t tcol = 0xff60e0ffU;
		char tname[48];
		tname[0] = 0;
		if (gs.tgt_kind == 1 && gs.ast[gs.tgt_idx].active) {
			struct asteroid *a = &gs.ast[gs.tgt_idx];
			tpos = a->pos; tvel = a->vel;
			hp_frac = a->hp / a->max_hp;
			tcol = ore_cols[a->ore];
			space_fmt(tname, sizeof(tname), "%s ASTEROID", ore_names[a->ore]);
		} else if (gs.tgt_kind == 2 && gs.drones[gs.tgt_idx].active) {
			struct drone *d = &gs.drones[gs.tgt_idx];
			tpos = d->pos; tvel = d->vel;
			hp_frac = d->hp / d->max_hp;
			tcol = 0xffff4040U;
			space_fmt(tname, sizeof(tname), "SENTINEL DRONE");
		} else if (gs.tgt_kind == 3 && gs.has_station) {
			tpos = gs.st_pos;
			tcol = 0xff50ff90U;
			space_fmt(tname, sizeof(tname), "ORBITAL OUTPOST");
		} else {
			gs.tgt_kind = 0;
		}
		float px, py, vz;
		if (gs.tgt_kind > 0 && project_point(tpos, &px, &py, &vz) &&
		    px > 20.0f && px < W - 20.0f && py > 20.0f && py < H * 0.78f) {
			float bsz = clampf(1600.0f * u / (vz + 25.0f), 12.0f * u, 42.0f * u);
			r_state(-1, BLEND_ALPHA, 0, 0, 1, 0, 1);
			/* Corner brackets */
			float cl = bsz * 0.42f;
			r_rect(px - bsz, py - bsz, px - bsz + cl, py - bsz + 2.0f * u, tcol);
			r_rect(px - bsz, py - bsz, px - bsz + 2.0f * u, py - bsz + cl, tcol);
			r_rect(px + bsz - cl, py - bsz, px + bsz, py - bsz + 2.0f * u, tcol);
			r_rect(px + bsz - 2.0f * u, py - bsz, px + bsz, py - bsz + cl, tcol);
			r_rect(px - bsz, py + bsz - 2.0f * u, px - bsz + cl, py + bsz, tcol);
			r_rect(px - bsz, py + bsz - cl, px - bsz + 2.0f * u, py + bsz, tcol);
			r_rect(px + bsz - cl, py + bsz - 2.0f * u, px + bsz, py + bsz, tcol);
			r_rect(px + bsz - 2.0f * u, py + bsz - cl, px + bsz, py + bsz, tcol);
			draw_bar(px - bsz, py - bsz - 7.0f * u, bsz * 2.0f, 4.0f * u, hp_frac, tcol, 0x90000000U);

			/* Lead aiming indicator (bolt speed = 260 m/s) */
			if (gs.tgt_kind != 3) {
				float dt_lead = vz / 260.0f;
				v3f lead_w = v3_add(tpos, v3_scale(v3_sub(tvel, gs.vel), dt_lead));
				float lx, ly, lz;
				if (project_point(lead_w, &lx, &ly, &lz) && lx > 10 && lx < W - 10 && ly > 10 && ly < H - 80) {
					r_line2d(px, py, lx, ly, 1.0f, 0x70ffffffU);
					r_box_outline(lx - 4.0f * u, ly - 4.0f * u, lx + 4.0f * u, ly + 4.0f * u, 1.2f * u, 0xffffff60U);
				}
			}
			r_text_state();
			char dist_s[64];
			space_fmt(dist_s, sizeof(dist_s), "%s %dM", tname, (int)vz);
			r_text(px - r_text_w(dist_s, u) * 0.5f, py + bsz + 4.0f * u, u, tcol, dist_s);
		}
	}

	/* Center reticle & muzzle / shield screen flash */
	r_state(-1, BLEND_ALPHA, 0, 0, 1, 0, 1);
	if (gs.shield_flash > 0.01f) {
		int a = clampi((int)(gs.shield_flash * 110.0f), 0, 130);
		r_rect(0, 0, W, H, ((uint32_t)a << 24) | 0x00ff3020U);
	}
	float cx = W * 0.5f, cy = H * 0.44f;
	uint32_t rcol = 0xd070f0ffU;
	r_rect(cx - 12.0f * u, cy - 0.8f * u, cx - 4.0f * u, cy + 0.8f * u, rcol);
	r_rect(cx + 4.0f * u,  cy - 0.8f * u, cx + 12.0f * u, cy + 0.8f * u, rcol);
	r_rect(cx - 0.8f * u,  cy - 10.0f * u, cx + 0.8f * u, cy - 4.0f * u, rcol);
	r_rect(cx - 0.8f * u,  cy + 4.0f * u,  cx + 0.8f * u, cy + 10.0f * u, rcol);

	/* Textured 3D-shaded Cockpit Canopy Struts & Lower Instrument Console */
	r_state(TEX_HULL, BLEND_NONE, 0, 0, 1, 0, 1);
	uint32_t c_top = gs.shield_flash > 0.1f ? 0xffb06060U : 0xff7888a0U;
	uint32_t c_pan = gs.muzzle_flash > 0.1f ? 0xff90b8d0U : 0xff546276U;
	uint32_t c_drk = 0xff2a3240U;
	/* Left & right angled A-pillar struts */
	struct dvtx sl0 = v2d(0, 0, c_drk, 0.0f, 0.0f), sl1 = v2d(46.0f * u + sx, 0, c_top, 0.25f, 0.0f);
	struct dvtx sl2 = v2d(96.0f * u + sx, H * 0.77f + sy, c_pan, 0.25f, 2.0f), sl3 = v2d(0, H * 0.77f + sy, c_drk, 0.0f, 2.0f);
	r_quad_raw(&sl0, &sl1, &sl2, &sl3);
	struct dvtx sr0 = v2d(W - 46.0f * u + sx, 0, c_top, 0.75f, 0.0f), sr1 = v2d(W, 0, c_drk, 1.0f, 0.0f);
	struct dvtx sr2 = v2d(W, H * 0.77f + sy, c_drk, 1.0f, 2.0f), sr3 = v2d(W - 96.0f * u + sx, H * 0.77f + sy, c_pan, 0.75f, 2.0f);
	r_quad_raw(&sr0, &sr1, &sr2, &sr3);
	/* Upper canopy brow */
	struct dvtx tb0 = v2d(0, 0, c_drk, 0, 0), tb1 = v2d(W, 0, c_drk, 4, 0);
	struct dvtx tb2 = v2d(W - 36.0f * u, 22.0f * u + sy * 0.4f, c_top, 4, 0.25f), tb3 = v2d(36.0f * u, 22.0f * u + sy * 0.4f, c_top, 0, 0.25f);
	r_quad_raw(&tb0, &tb1, &tb2, &tb3);
	/* Lower cockpit dashboard trapezoid + side wings */
	float dy0 = H * 0.76f + sy, dy_mid = H * 0.72f + sy;
	struct dvtx db0 = v2d(0, dy0, c_top, 0, 0), db1 = v2d(W * 0.30f + sx, dy_mid, c_pan, 1.2f, 0);
	struct dvtx db2 = v2d(W * 0.30f + sx, H, c_drk, 1.2f, 1), db3 = v2d(0, H, c_drk, 0, 1);
	r_quad_raw(&db0, &db1, &db2, &db3);
	struct dvtx dc0 = v2d(W * 0.30f + sx, dy_mid, c_top, 1.2f, 0), dc1 = v2d(W * 0.70f + sx, dy_mid, c_top, 2.8f, 0);
	struct dvtx dc2 = v2d(W * 0.70f + sx, H, c_drk, 2.8f, 1), dc3 = v2d(W * 0.30f + sx, H, c_drk, 1.2f, 1);
	r_quad_raw(&dc0, &dc1, &dc2, &dc3);
	struct dvtx dr0 = v2d(W * 0.70f + sx, dy_mid, c_pan, 2.8f, 0), dr1 = v2d(W, dy0, c_top, 4.0f, 0);
	struct dvtx dr2 = v2d(W, H, c_drk, 4.0f, 1), dr3 = v2d(W * 0.70f + sx, H, c_drk, 2.8f, 1);
	r_quad_raw(&dr0, &dr1, &dr2, &dr3);

	/* Glowing cyan cockpit bezel trim lines */
	r_state(-1, BLEND_ALPHA, 0, 0, 1, 0, 1);
	r_line2d(46.0f * u + sx, 0, 96.0f * u + sx, dy0, 2.0f * u, 0xc040c8ffU);
	r_line2d(W - 46.0f * u + sx, 0, W - 96.0f * u + sx, dy0, 2.0f * u, 0xc040c8ffU);
	r_line2d(0, dy0, W * 0.30f + sx, dy_mid, 2.2f * u, 0xe050d8ffU);
	r_line2d(W * 0.30f + sx, dy_mid, W * 0.70f + sx, dy_mid, 2.2f * u, 0xe050d8ffU);
	r_line2d(W * 0.70f + sx, dy_mid, W, dy0, 2.2f * u, 0xe050d8ffU);

	/* Left & Right instrument screen wells */
	float lx = 14.0f * u + sx * 0.5f, ly = H * 0.79f + sy;
	float pw = W * 0.27f, ph = H * 0.19f;
	r_rect(lx, ly, lx + pw, ly + ph, 0xd806101aU);
	r_box_outline(lx, ly, lx + pw, ly + ph, 1.2f * u, 0xff2878a8U);

	float rx0 = W - 14.0f * u - pw + sx * 0.5f;
	r_rect(rx0, ly, rx0 + pw, ly + ph, 0xd806101aU);
	r_box_outline(rx0, ly, rx0 + pw, ly + ph, 1.2f * u, 0xff2878a8U);

	/* Left Console Bars: Shield, Hull, Boost, Speed */
	float bw = pw - 58.0f * u, bh = 8.0f * u;
	draw_bar(lx + 48.0f * u, ly + 8.0f * u,  bw, bh, gs.shield / gs.max_shield, 0xff40c8ffU, 0xff102438U);
	draw_bar(lx + 48.0f * u, ly + 22.0f * u, bw, bh, gs.hull / gs.max_hull,     0xff40f080U, 0xff102818U);
	draw_bar(lx + 48.0f * u, ly + 36.0f * u, bw, bh, gs.energy / 100.0f,        0xffffb830U, 0xff282010U);
	float spd = v3_len(gs.vel);
	draw_bar(lx + 48.0f * u, ly + 50.0f * u, bw, bh, spd / (95.0f + gs.lvl_engine * 18.0f), 0xffb080ffU, 0xff201434U);

	/* Right Console: Warp Fuel bar */
	draw_bar(rx0 + 48.0f * u, ly + 8.0f * u, bw, bh, gs.fuel / gs.max_fuel, 0xff30ffe0U, 0xff0c2828U);

	/* Center 3D Holo-Radar */
	draw_radar(W * 0.5f + sx * 0.7f, H * 0.865f + sy, W * 0.145f, H * 0.105f);

	/* Text readouts on Cockpit & Top Banner */
	r_text_state();
	float ts = u >= 1.5f ? 1.5f : 1.0f;
	r_text(lx + 6.0f * u, ly + 8.0f * u,  ts, 0xff80e0ffU, "SHLD");
	r_text(lx + 6.0f * u, ly + 22.0f * u, ts, 0xff80ffa0U, "HULL");
	r_text(lx + 6.0f * u, ly + 36.0f * u, ts, 0xffffd080U, "ENRG");
	r_text(lx + 6.0f * u, ly + 50.0f * u, ts, 0xffd0b0ffU, "SPD");

	char buf[96];
	space_fmt(buf, sizeof(buf), "%d M/S  THR %d%%  SCORE %d", (int)spd, (int)(gs.throttle * 100.0f), gs.score);
	r_text(lx + 6.0f * u, ly + 66.0f * u, ts, 0xffd0e8ffU, buf);

	r_text(rx0 + 6.0f * u, ly + 8.0f * u, ts, 0xff60ffe8U, "WARP");
	space_fmt(buf, sizeof(buf), "FE:%d  FUEL:%d", gs.cargo[ORE_FE], gs.cargo[ORE_FUEL]);
	r_text(rx0 + 6.0f * u, ly + 24.0f * u, ts, 0xffe0d0b0U, buf);
	space_fmt(buf, sizeof(buf), "AU:%d  PLAS:%d", gs.cargo[ORE_AU], gs.cargo[ORE_PLAS]);
	r_text(rx0 + 6.0f * u, ly + 38.0f * u, ts, 0xffffe070U, buf);
	space_fmt(buf, sizeof(buf), "L%d S%d E%d T%d", gs.lvl_laser, gs.lvl_shield, gs.lvl_engine, gs.lvl_tractor);
	r_text(rx0 + 6.0f * u, ly + 53.0f * u, ts, 0xff90d0ffU, buf);
	space_fmt(buf, sizeof(buf), "NAV: %s", gs.sys[gs.nav_sys].name);
	r_text(rx0 + 6.0f * u, ly + 67.0f * u, ts, 0xff80ffb0U, buf);

	/* Top canopy bar: current Star System, Danger, Quick Key Hints */
	const struct star_sys *cs = &gs.sys[gs.cur_sys];
	space_fmt(buf, sizeof(buf), "SYS: %s [DANGER %d]   M:MAP  J:JUMP  U:UPGRADE  T:TARGET", cs->name, cs->danger);
	r_text((W - r_text_w(buf, ts)) * 0.5f, 5.0f * u, ts, 0xffc0e8ffU, buf);

	if (gs.screen == SCR_PLAY && gs.near_station) {
		const char *dock = "OUTPOST IN RANGE - HULL REPAIRED - PRESS U FOR SHIP UPGRADES";
		r_text((W - r_text_w(dock, ts)) * 0.5f, 28.0f * u, ts, 0xff60ff90U, dock);
	}
	if (gs.screen == SCR_PLAY && gs.msg_t > 0.0f && gs.msg[0]) {
		r_text((W - r_text_w(gs.msg, ts * 1.2f)) * 0.5f, H * 0.14f, ts * 1.2f, 0xfffff080U, gs.msg);
	}
}

/* Interactive Galaxy Starmap Overlay (M / Tab) */
static void draw_starmap_overlay(double t)
{
	float W = (float)space_view.w, H = (float)space_view.h, u = H / 480.0f;
	float x0 = W * 0.08f, y0 = H * 0.08f, x1 = W * 0.92f, y1 = H * 0.74f;
	r_state(-1, BLEND_ALPHA, 0, 0, 1, 0, 1);
	r_rect(x0, y0, x1, y1, 0xe4050c18U);
	r_box_outline(x0, y0, x1, y1, 2.0f * u, 0xff40b8ffU);

	float mx0 = x0 + 24.0f * u, my0 = y0 + 36.0f * u;
	float mw = (x1 - x0) * 0.62f, mh = (y1 - y0) - 64.0f * u;
	r_rect(mx0, my0, mx0 + mw, my0 + mh, 0xc002060eU);
	r_box_outline(mx0, my0, mx0 + mw, my0 + mh, 1.0f * u, 0xff205078U);

	/* Jump range circle around current system */
	const struct star_sys *cur = &gs.sys[gs.cur_sys];
	float cx = mx0 + cur->gx * mw, cy = my0 + cur->gy * mh;
	float max_d = 0.36f + gs.lvl_engine * 0.04f;
	for (int i = 0; i < 32; i++) {
		float a0 = (float)i / 32.0f * (float)TAU, a1 = (float)(i + 1) / 32.0f * (float)TAU;
		float px0 = clampf(cx + m_cosf(a0) * max_d * mw, mx0, mx0 + mw);
		float py0 = clampf(cy + m_sinf(a0) * max_d * mh, my0, my0 + mh);
		float px1 = clampf(cx + m_cosf(a1) * max_d * mw, mx0, mx0 + mw);
		float py1 = clampf(cy + m_sinf(a1) * max_d * mh, my0, my0 + mh);
		r_line2d(px0, py0, px1, py1, 1.0f * u, 0x6030b090U);
	}

	/* Hyperlane lines from current system to reachable systems */
	for (int i = 0; i < N_SYSTEMS; i++) {
		if (i == gs.cur_sys)
			continue;
		float d = jump_dist(gs.cur_sys, i);
		if (d <= max_d) {
			float sx = mx0 + gs.sys[i].gx * mw, sy = my0 + gs.sys[i].gy * mh;
			uint32_t lc = (i == gs.nav_sys) ? 0xe060ff90U : 0x504090c0U;
			r_line2d(cx, cy, sx, sy, (i == gs.nav_sys ? 2.2f : 1.0f) * u, lc);
		}
	}

	/* Star icons */
	for (int i = 0; i < N_SYSTEMS; i++) {
		float sx = mx0 + gs.sys[i].gx * mw, sy = my0 + gs.sys[i].gy * mh;
		uint32_t sc = pack_argb(255, (int)(gs.sys[i].star_rgb[0] * 255),
					(int)(gs.sys[i].star_rgb[1] * 255), (int)(gs.sys[i].star_rgb[2] * 255));
		float r = (i == gs.cur_sys || i == gs.nav_sys) ? 5.0f * u : 3.5f * u;
		r_rect(sx - r, sy - r, sx + r, sy + r, sc);
		if (i == gs.cur_sys)
			r_box_outline(sx - 8.0f * u, sy - 8.0f * u, sx + 8.0f * u, sy + 8.0f * u, 1.5f * u, 0xff40e0ffU);
		if (i == gs.nav_sys) {
			float pulse = 9.0f * u + 2.0f * u * m_sinf((float)t * 6.0f);
			r_box_outline(sx - pulse, sy - pulse, sx + pulse, sy + pulse, 1.6f * u, 0xfffff050U);
		}
	}

	r_text_state();
	float ts = u >= 1.5f ? 1.5f : 1.0f;
	r_text(mx0, y0 + 10.0f * u, ts * 1.3f, 0xff80e8ffU, "SECTOR GALAXY STARMAP");

	/* Selected system details panel on the right */
	const struct star_sys *sel = &gs.sys[gs.nav_sys];
	float ix = mx0 + mw + 16.0f * u, iy = my0 + 6.0f * u;
	char line[64];
	static const char *spec_names[4] = {"BLUE GIANT", "SOLAR G-STAR", "RED GIANT", "EMERALD PULSAR"};
	r_text(ix, iy, ts * 1.2f, 0xfffff070U, sel->name);
	r_text(ix, iy += 18.0f * u, ts, 0xffa0d8ffU, spec_names[sel->spectral & 3]);
	space_fmt(line, sizeof(line), "DANGER:  %d / 4", sel->danger);
	r_text(ix, iy += 16.0f * u, ts, sel->danger >= 3 ? 0xffff7070U : 0xff90ff90U, line);
	space_fmt(line, sizeof(line), "OUTPOST: %s", sel->has_station ? "YES" : "DEEP SPACE");
	r_text(ix, iy += 16.0f * u, ts, 0xffd0e8ffU, line);

	float d = jump_dist(gs.cur_sys, gs.nav_sys);
	int cost = jump_fuel_cost(gs.cur_sys, gs.nav_sys);
	space_fmt(line, sizeof(line), "DIST:    %.1f LY", (double)(d * 25.0f));
	r_text(ix, iy += 20.0f * u, ts, 0xffd0e8ffU, line);
	space_fmt(line, sizeof(line), "FUEL:    %d / %d", cost, (int)gs.fuel);
	r_text(ix, iy += 16.0f * u, ts, (d <= max_d && gs.fuel >= cost) ? 0xff50ffa0U : 0xffff6060U, line);
	r_text(ix, iy += 22.0f * u, ts, d <= max_d ? 0xff60ffb0U : 0xffff7050U,
	       gs.nav_sys == gs.cur_sys ? "CURRENT SYSTEM" : (d <= max_d ? "IN JUMP RANGE" : "OUT OF RANGE"));

	const char *help = "ARROWS/WASD: SELECT SYSTEM   J/ENTER: ENGAGE WARP   M/ESC: BACK";
	r_text((W - r_text_w(help, ts)) * 0.5f, y1 - 20.0f * u, ts, 0xff90ffc0U, help);
}

/* Ship Upgrade & Field Synthesizer Overlay (U) */
static void draw_upgrade_overlay(void)
{
	float W = (float)space_view.w, H = (float)space_view.h, u = H / 480.0f;
	float x0 = W * 0.12f, y0 = H * 0.08f, x1 = W * 0.88f, y1 = H * 0.75f;
	r_state(-1, BLEND_ALPHA, 0, 0, 1, 0, 1);
	r_rect(x0, y0, x1, y1, 0xe806101cU);
	r_box_outline(x0, y0, x1, y1, 2.0f * u, gs.near_station ? 0xff50ff90U : 0xff40b8ffU);

	r_text_state();
	float ts = u >= 1.5f ? 1.5f : 1.0f;
	const char *hdr = gs.near_station ? "ORBITAL OUTPOST ENGINEERING BAY" : "SHIPBOARD FIELD SYNTHESIZER";
	r_text(x0 + 20.0f * u, y0 + 14.0f * u, ts * 1.3f, 0xff70ff98U, hdr);

	char line[96];
	space_fmt(line, sizeof(line), "CARGO  FE:%d   FUEL-ORE:%d   AU:%d   PLASMA:%d",
		  gs.cargo[ORE_FE], gs.cargo[ORE_FUEL], gs.cargo[ORE_AU], gs.cargo[ORE_PLAS]);
	r_text(x0 + 20.0f * u, y0 + 36.0f * u, ts, 0xffffe080U, line);

	float y = y0 + 62.0f * u;
	int c_las = gs.lvl_laser * 4, c_shd = gs.lvl_shield * 3, c_eng = gs.lvl_engine * 4, c_trc = gs.lvl_tractor * 3;
	space_fmt(line, sizeof(line), "[1] PLASMA LASERS   LVL %d -> %d   COST: %d AU + %d FE", gs.lvl_laser, gs.lvl_laser + 1, c_las, c_las);
	r_text(x0 + 20.0f * u, y, ts, gs.lvl_laser < 5 ? 0xffd0f0ffU : 0xff8090a0U, line);
	space_fmt(line, sizeof(line), "[2] DEFLECTOR SHLD  LVL %d -> %d   COST: %d PLAS + %d FE", gs.lvl_shield, gs.lvl_shield + 1, c_shd, c_shd);
	r_text(x0 + 20.0f * u, y += 23.0f * u, ts, gs.lvl_shield < 5 ? 0xffd0f0ffU : 0xff8090a0U, line);
	space_fmt(line, sizeof(line), "[3] HYPER THRUSTER  LVL %d -> %d   COST: %d PLAS + %d AU", gs.lvl_engine, gs.lvl_engine + 1, c_eng, c_eng);
	r_text(x0 + 20.0f * u, y += 23.0f * u, ts, gs.lvl_engine < 5 ? 0xffd0f0ffU : 0xff8090a0U, line);
	space_fmt(line, sizeof(line), "[4] MINING TRACTOR  LVL %d -> %d   COST: %d AU + %d FUEL", gs.lvl_tractor, gs.lvl_tractor + 1, c_trc, c_trc);
	r_text(x0 + 20.0f * u, y += 23.0f * u, ts, gs.lvl_tractor < 5 ? 0xffd0f0ffU : 0xff8090a0U, line);
	r_text(x0 + 20.0f * u, y += 26.0f * u, ts, 0xff70ffe0U, "[5] REFINE WARP FUEL (+35 WARP)    COST: 2 FUEL-ORE");
	r_text(x0 + 20.0f * u, y += 22.0f * u, ts, 0xff80ffa0U, "[6] PATCH HULL ARMOR (+40 HULL)    COST: 3 FE ORE");

	r_text(x0 + 20.0f * u, y1 - 22.0f * u, ts, 0xffa0ffc0U, "PRESS 1..6 TO BUILD/UPGRADE   U OR ESC TO CLOSE");
}

/* Title Card Overlay over live 3D star system backdrop */
static void draw_title_overlay(double t)
{
	float W = (float)space_view.w, H = (float)space_view.h, u = H / 480.0f;
	r_state(-1, BLEND_ALPHA, 0, 0, 1, 0, 1);
	r_rect(W * 0.08f, H * 0.10f, W * 0.92f, H * 0.88f, 0xb8040a16U);
	r_box_outline(W * 0.08f, H * 0.10f, W * 0.92f, H * 0.88f, 2.0f * u, 0xff40b8ffU);

	/* Glowing copper/cyan horizon bar behind title */
	float by = H * 0.21f + 4.0f * u * m_sinf((float)t * 2.2f);
	r_state(-1, BLEND_ADD, 0, 0, 1, 0, 1);
	struct dvtx p0 = v2d(W * 0.10f, by - 22.0f * u, 0xff000000U, 0, 0), p1 = v2d(W * 0.90f, by - 22.0f * u, 0xff000000U, 0, 0);
	struct dvtx p2 = v2d(W * 0.90f, by, 0xff2080d0U, 0, 0),             p3 = v2d(W * 0.10f, by, 0xff2080d0U, 0, 0);
	struct dvtx p4 = v2d(W * 0.90f, by + 22.0f * u, 0xff000000U, 0, 0), p5 = v2d(W * 0.10f, by + 22.0f * u, 0xff000000U, 0, 0);
	r_quad_raw(&p0, &p1, &p2, &p3);
	r_quad_raw(&p3, &p2, &p4, &p5);

	r_text_state();
	float big = H >= 600 ? 5.0f : 4.0f, sm = H >= 600 ? 2.0f : 1.5f, xs = H >= 600 ? 1.5f : 1.0f;
	const char *title = "WSHSPACE";
	r_text((W - r_text_w(title, big)) * 0.5f, by - 3.5f * big, big, 0xffffffffU, title);
	const char *sub = "PROCEDURAL 3DFX SPACE EXPLORATION & ASTEROID MINING";
	r_text((W - r_text_w(sub, xs)) * 0.5f, H * 0.30f, xs, 0xff80e8ffU, sub);

	float x0 = W * 0.13f, y = H * 0.38f;
	r_text(x0, y,             xs, 0xffffe080U, "ARROWS / MOUSE : PITCH & YAW      W / S : THRUST & BRAKE");
	r_text(x0, y += 16.0f * u, xs, 0xffffe080U, "A / D OR Q / E : ROLL             SPACE : FIRE PLASMA LASERS");
	r_text(x0, y += 16.0f * u, xs, 0xffffe080U, "SHIFT / B      : AFTERBURNER      T     : LOCK TARGET");
	r_text(x0, y += 16.0f * u, xs, 0xffffe080U, "M / TAB        : GALAXY STARMAP   J     : HYPERSPACE JUMP");
	r_text(x0, y += 16.0f * u, xs, 0xffffe080U, "U              : SHIP UPGRADES    V     : TOGGLE MOUSE LOOK");

	char info[128];
	space_fmt(info, sizeof(info), "API: %s  |  %dx%d  |  WRAPPER: %.34s", be->api, space_view.w, space_view.h, wrapper_rev);
	r_text((W - r_text_w(info, xs)) * 0.5f, H * 0.69f, xs, 0xffa0c8e0U, info);

	const char *go = (((int)(t * 3.0)) & 1) ? ">>> PRESS SPACE OR ENTER TO LAUNCH <<<" : "    PRESS SPACE OR ENTER TO LAUNCH    ";
	r_text((W - r_text_w(go, sm)) * 0.5f, H * 0.78f, sm, 0xff60ff90U, go);
}

/* Frame-rate & frame-time graph overlay (F key) */
static void draw_fps_hud(double gamma)
{
	float u = space_view.h >= 600 ? 2.0f : 1.0f, x0 = 54.0f * u, y0 = 26.0f * u;
	r_state(-1, BLEND_ALPHA, 0, 0, 1, 0, 1);
	r_rect(x0, y0, x0 + 144.0f * u, y0 + 54.0f * u, 0xa0000000U);
	for (int i = 0; i < GRAPH_N; i++) {
		float ms = ft_ms[(ft_pos + i) % GRAPH_N];
		float h = ms > 32.0f ? 32.0f : ms;
		uint32_t c = ms < 20.0f ? 0xff40e040U : ms < 34.0f ? 0xffe0e040U : 0xffe04040U;
		r_rect(x0 + (6.0f + i * 2.0f) * u, y0 + (50.0f - h) * u, x0 + (7.0f + i * 2.0f) * u, y0 + 50.0f * u, c);
	}
	r_text_state();
	char line[64];
	space_fmt(line, sizeof(line), "%.1f FPS G%.1f", hud_fps, gamma);
	r_text(x0 + 6.0f * u, y0 + 4.0f * u, u, 0xffffffffU, line);
}

#endif
