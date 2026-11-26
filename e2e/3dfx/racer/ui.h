/*
 * wshracer: futuristic anti-gravity racing HUD, 2D circuit minimap, start light tree,
 * nose-cam canopy frame, race standings overlay, and FPS graph.
 * Included by racer.c after circuit & racer state declarations.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_RACER_UI_H
#define WSH_RACER_UI_H

static void fmt_lap_time(char *buf, int cap, float sec)
{
	if (sec <= 0.0f || sec > 5999.0f) {
		racer_fmt(buf, cap, "--:--.--");
		return;
	}
	int cs = (int)(sec * 100.0f + 0.5f);
	int mins = cs / 6000;
	int secs = (cs / 100) % 60;
	int rem = cs % 100;
	racer_fmt(buf, cap, "%d%d:%d%d.%d%d", mins / 10, mins % 10, secs / 10, secs % 10, rem / 10, rem % 10);
}

static float text_scale(float u)
{
	return u >= 2.2f ? 2.0f : u >= 1.5f ? 1.5f : 1.0f;
}

static void draw_minimap(float x, float y, float w, float h, float u, float ts)
{
	draw_box_border(x, y, w, h, 0xb808101cU, 0xd038b8e8U);

	/* Compute track X/Z bounding box for clean aspect-preserving fit */
	float min_x = 1e9f, max_x = -1e9f, min_z = 1e9f, max_z = -1e9f;
	for (int i = 0; i < N_SEG; i += 2) {
		v3 p = trk[i].pos;
		if (p.x < min_x) min_x = p.x;
		if (p.x > max_x) max_x = p.x;
		if (p.z < min_z) min_z = p.z;
		if (p.z > max_z) max_z = p.z;
	}
	float dx = max_x - min_x, dz = max_z - min_z;
	if (dx < 1.0f) dx = 1.0f;
	if (dz < 1.0f) dz = 1.0f;
	float pad = 12.0f * u;
	float sx = (w - pad * 2.0f) / dx;
	float sz = (h - pad * 2.0f - 12.0f * u) / dz;
	float sc = sx < sz ? sx : sz;
	float ox = x + w * 0.5f - (min_x + max_x) * 0.5f * sc;
	float oy = y + (h + 10.0f * u) * 0.5f + (min_z + max_z) * 0.5f * sc;

	/* Circuit outline */
	for (int i = 0; i < N_SEG; i += 4) {
		int j = (i + 4) & (N_SEG - 1);
		float x0 = ox + trk[i].pos.x * sc, y0 = oy - trk[i].pos.z * sc;
		float x1 = ox + trk[j].pos.x * sc, y1 = oy - trk[j].pos.z * sc;
		uint32_t col = trk[i].tunnel ? 0xd0a060ffU : 0xd05898b8U;
		line2d(x0, y0, x1, y1, 2.2f * u, col);
	}

	/* Start/finish tick */
	float sfx = ox + trk[0].pos.x * sc, sfy = oy - trk[0].pos.z * sc;
	rect2d(sfx - 3.0f * u, sfy - 3.0f * u, 6.0f * u, 6.0f * u, 0xffffffffU);

	/* Live hovercraft blips (rivals first, player on top) */
	for (int r = N_RACERS - 1; r >= 0; r--) {
		v3 p = racers[r].wpos;
		float bx = ox + p.x * sc, by = oy - p.z * sc;
		uint32_t c = 0xff000000U | ((uint32_t)teams[r].r << 16) | ((uint32_t)teams[r].g << 8) | teams[r].b;
		if (r == 0) {
			rect2d(bx - 4.0f * u, by - 4.0f * u, 8.0f * u, 8.0f * u, 0xffffffffU);
			rect2d(bx - 2.5f * u, by - 2.5f * u, 5.0f * u, 5.0f * u, 0xff20f8ffU);
		} else {
			rect2d(bx - 2.5f * u, by - 2.5f * u, 5.0f * u, 5.0f * u, c);
		}
	}

	draw_str(x + 6.0f * u, y + 3.0f * u, 0.85f * ts, 0xff90e4ffU, circuits[gs.track_id].name);
}

static void draw_hud(void)
{
	float w = (float)racer_view.w, h = (float)racer_view.h;
	float u = h / 480.0f, ts = text_scale(u);
	const struct racer *pl = &racers[0];
	char buf[96], tbuf[32];

	/* Nose/cockpit cam canopy struts & velocity pitch ladder */
	if (gs.cam_mode == 1) {
		uint32_t strut = 0xc8142030U, trim = 0xb030d8ffU;
		line2d(0, h * 0.82f, w * 0.24f, h, 8.0f * u, strut);
		line2d(w, h * 0.82f, w * 0.76f, h, 8.0f * u, strut);
		line2d(0, h * 0.82f, w * 0.24f, h, 1.5f * u, trim);
		line2d(w, h * 0.82f, w * 0.76f, h, 1.5f * u, trim);
		float cx = w * 0.5f - pl->yaw_rel * 90.0f * u, cy = h * 0.54f;
		line2d(cx - 14.0f * u, cy, cx - 5.0f * u, cy, 1.5f * u, 0x9040f0ffU);
		line2d(cx + 5.0f * u, cy, cx + 14.0f * u, cy, 1.5f * u, 0x9040f0ffU);
		line2d(cx, cy - 8.0f * u, cx, cy - 3.0f * u, 1.5f * u, 0x9040f0ffU);
	}

	/* Top telemetry bar */
	draw_box_border(10.0f * u, 8.0f * u, 206.0f * u, 48.0f * u, 0xd80a1424U, 0xe038c8ffU);
	static const char *ord[6] = {"1ST", "2ND", "3RD", "4TH", "5TH", "6TH"};
	int rk = clampi(pl->rank, 0, 5);
	uint32_t rk_col = rk == 0 ? 0xffffe040U : rk <= 2 ? 0xff50f8b0U : 0xffd8e8f8U;
	racer_fmt(buf, sizeof(buf), "POS %s / %d", ord[rk], N_RACERS);
	draw_str(18.0f * u, 13.0f * u, 1.25f * ts, rk_col, buf);
	int disp_lap = clampi(pl->lap + 1, 1, TOTAL_LAPS);
	racer_fmt(buf, sizeof(buf), "LAP %d / %d", disp_lap, TOTAL_LAPS);
	draw_str(18.0f * u, 34.0f * u, 1.05f * ts, 0xffa8dcffU, buf);

	/* Top-right lap & best-lap digital chronometer */
	draw_box_border(w - 224.0f * u, 8.0f * u, 214.0f * u, 48.0f * u, 0xd80a1424U, 0xe038c8ffU);
	fmt_lap_time(tbuf, sizeof(tbuf), pl->cur_lap_t);
	racer_fmt(buf, sizeof(buf), "TIME %s", tbuf);
	draw_str(w - 214.0f * u, 13.0f * u, 1.1f * ts, 0xffffffffU, buf);
	fmt_lap_time(tbuf, sizeof(tbuf), pl->best_lap_t);
	racer_fmt(buf, sizeof(buf), "BEST %s", tbuf);
	draw_str(w - 214.0f * u, 34.0f * u, 1.0f * ts, 0xff58f8c0U, buf);

	/* Top-center circuit & mode badge */
	if (gs.auto_play)
		draw_str_center(w * 0.5f, 12.0f * u, 1.0f * ts, 0xffffd860U, "AUTOPILOT DEMO  [1-4 TRACK  C CAM]");

	/* Bottom-left Speedometer + Segmented RPM/Velocity Bar + Turbo Energy Bar */
	float sx = 10.0f * u, sy = h - 78.0f * u;
	draw_box_border(sx, sy, 238.0f * u, 68.0f * u, 0xd80a1424U, 0xe038c8ffU);
	int kmh = (int)(m_fabsf(pl->vel_fwd) * 3.85f + 0.5f);
	uint32_t spd_col = pl->boost_t > 0.05f ? 0xfffff060U : 0xff58f4ffU;
	racer_fmt(buf, sizeof(buf), "%d KM/H", kmh);
	draw_str(sx + 10.0f * u, sy + 7.0f * u, 1.35f * ts, spd_col, buf);
	if (pl->boost_t > 0.05f)
		draw_str(sx + 144.0f * u, sy + 10.0f * u, 1.0f * ts, 0xffff9830U, "TURBO!");
	else if (gs.cam_mode == 1)
		draw_str(sx + 146.0f * u, sy + 10.0f * u, 0.9f * ts, 0xff90c8e8U, "NOSE CAM");

	/* 20-segment rising velocity bar */
	float frac = clampf(kmh / 920.0f, 0.0f, 1.0f);
	for (int i = 0; i < 20; i++) {
		float bx = sx + (10.0f + i * 11.0f) * u;
		float bh = (7.0f + (float)i * 0.55f) * u;
		float by = sy + 44.0f * u - bh;
		int lit = ((float)(i + 1) / 20.0f) <= frac + 0.025f;
		uint32_t c = !lit ? 0x601c3048U : i < 12 ? 0xff28e8ffU : i < 17 ? 0xffffd030U : 0xffff4838U;
		rect2d(bx, by, 8.5f * u, bh, c);
	}

	/* Turbo Energy / Shield capacitor bar */
	draw_str(sx + 10.0f * u, sy + 49.0f * u, 0.85f * ts, 0xffa8dcffU, "ENERGY");
	rect2d(sx + 64.0f * u, sy + 51.0f * u, 164.0f * u, 10.0f * u, 0x90142438U);
	float ew = 162.0f * u * clampf(pl->energy * 0.01f, 0.0f, 1.0f);
	uint32_t ecol = pl->energy < 25.0f ? 0xffff4444U : 0xff30f8a8U;
	rect2d(sx + 65.0f * u, sy + 52.0f * u, ew, 8.0f * u, ecol);

	/* Bottom-right 2D circuit minimap */
	float mw = 136.0f * u, mh = 110.0f * u;
	draw_minimap(w - mw - 10.0f * u, h - mh - 10.0f * u, mw, mh, u, ts);

	/* Race start countdown light tree */
	if (gs.countdown > -0.85f && !gs.check_mode) {
		float lx = w * 0.5f - 82.0f * u, ly = h * 0.20f;
		draw_box_border(lx, ly, 164.0f * u, 44.0f * u, 0xd80c1220U, 0xe060c8ffU);
		for (int i = 0; i < 3; i++) {
			uint32_t lc;
			if (gs.countdown <= 0.0f)
				lc = 0xff30ff78U;
			else if (gs.countdown <= (float)(3 - i))
				lc = 0xffff3838U;
			else
				lc = 0x70283040U;
			rect2d(lx + (18.0f + i * 48.0f) * u, ly + 9.0f * u, 32.0f * u, 26.0f * u, lc);
		}
		draw_str_center(w * 0.5f, ly + 50.0f * u, 1.45f * ts,
				gs.countdown <= 0.0f ? 0xff40ff90U : 0xffffd850U,
				gs.countdown <= 0.0f ? "GO! GO! GO!" :
				gs.countdown > 2.0f ? "READY  3" :
				gs.countdown > 1.0f ? "SET    2" : "IGNITE 1");
	}

	/* Sector / New Best Lap banner */
	if (gs.banner_t > 0.0f && gs.banner[0])
		draw_str_center(w * 0.5f, h * 0.28f, 1.3f * ts, 0xfffff068U, gs.banner);

	/* Race finish standings table */
	if (gs.finished && !gs.auto_play) {
		float pw = 360.0f * u, ph = 212.0f * u;
		float px = (w - pw) * 0.5f, py = (h - ph) * 0.5f;
		draw_box_border(px, py, pw, ph, 0xe8081222U, 0xff48dcffU);
		draw_str_center(w * 0.5f, py + 12.0f * u, 1.35f * ts, 0xffffe058U, "CIRCUIT RESULTS");
		draw_str_center(w * 0.5f, py + 34.0f * u, 0.95f * ts, 0xff98dcffU, circuits[gs.track_id].name);
		for (int rank = 0; rank < N_RACERS; rank++) {
			int idx = 0;
			for (int j = 0; j < N_RACERS; j++)
				if (racers[j].rank == rank)
					idx = j;
			uint32_t tc = idx == 0 ? 0xff58ffffU : 0xffd8e4f4U;
			fmt_lap_time(tbuf, sizeof(tbuf), racers[idx].best_lap_t);
			racer_fmt(buf, sizeof(buf), "%s  %-14s  BEST %s", ord[rank], teams[idx].name, tbuf);
			draw_str(px + 20.0f * u, py + (60.0f + rank * 20.0f) * u, 0.95f * ts, tc, buf);
		}
		draw_str_center(w * 0.5f, py + ph - 24.0f * u, 0.95f * ts, 0xff60f8a8U,
				"ENTER: NEXT CIRCUIT   1-4: SELECT   ESC: QUIT");
	}

	/* Optional FPS & frame-time graph (F key) */
	if (gs.show_fps) {
		float gx = w * 0.5f - 75.0f * u, gy = 30.0f * u;
		draw_box_border(gx, gy, 150.0f * u, 38.0f * u, 0xc008101cU, 0xa040a8d8U);
		racer_fmt(buf, sizeof(buf), "%.1f FPS", gs.fps_disp);
		draw_str(gx + 6.0f * u, gy + 3.0f * u, 0.9f * ts, 0xff70f8b0U, buf);
		for (int i = 0; i < 64; i++) {
			float ms = gs.ft_hist[(gs.ft_pos + i) & 63];
			float bh = clampf(ms * 0.8f, 1.0f, 20.0f) * u;
			rect2d(gx + (10.0f + i * 2.0f) * u, gy + 35.0f * u - bh, 1.5f * u, bh,
			       ms > 22.0f ? 0xffff6040U : 0xff38d8ffU);
		}
	}
}

#endif
