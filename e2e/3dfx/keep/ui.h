/*
 * Resolution-scaled Gothic HUD, Corner Minimap, Full-Screen Automap Overlay (Tab/M),
 * Weapon Bar, Toast Banner, and FPS Graph for wshkeep.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_KEEP_UI_H
#define WSH_KEEP_UI_H

static float frame_ms_hist[120];
static int frame_ms_idx;

static float text_scale(float u)
{
	return u >= 2.2f ? 2.0f : u >= 1.5f ? 1.5f : 1.0f;
}

static void hud_panel(float x0, float y0, float x1, float y1, uint32_t bg, uint32_t border)
{
	hud_quad(x0, y0, x1, y1, bg);
	hud_quad(x0, y0, x1, y0 + 1.5f, border);
	hud_quad(x0, y1 - 1.5f, x1, y1, border);
	hud_quad(x0, y0, x0 + 1.5f, y1, border);
	hud_quad(x1 - 1.5f, y0, x1, y1, border);
}

static void draw_automap(float x0, float y0, float sz, int full)
{
	hud_panel(x0, y0, x0 + sz, y0 + sz, full ? 0xd00c0e16U : 0xb80c0e16U, 0xd8a8843cU);
	float pad = full ? 10.0f : 4.0f;
	float cell = (sz - pad * 2.0f) / (float)MAP_N;
	float ox = x0 + pad, oy = y0 + pad;

	for (int z = 0; z < MAP_N; z++) {
		for (int x = 0; x < MAP_N; x++) {
			if (!full && !dun.seen[z][x])
				continue;
			uint8_t t = dun.tile[z][x];
			if (t == TILE_WALL)
				continue;
			uint32_t col = 0xff363a48U;
			if (!dun.seen[z][x])
				col = 0x8820222cU;
			else if (t == TILE_LIQUID)
				col = dun.floor_idx == 2 ? 0xffb84414U : dun.floor_idx == 3 ? 0xff2868a8U : 0xff205478U;
			else if (t == TILE_DOOR)
				col = dun.door_open[z][x] > 0.8f ? 0xff524838U : 0xffb88234U;
			else if (t == TILE_LOCKED)
				col = 0xffe84838U;
			else if (t == TILE_PILLAR)
				col = 0xff6e7282U;
			hud_quad(ox + x * cell, oy + z * cell, ox + (x + 1) * cell - 0.4f, oy + (z + 1) * cell - 0.4f, col);
		}
	}

	/* Items & Portal markers */
	for (int i = 0; i < dun.n_items; i++) {
		const struct item *it = &dun.items[i];
		if (!it->active)
			continue;
		int gx = (int)(it->x / CELL), gz = (int)(it->z / CELL);
		if (gx < 0 || gx >= MAP_N || gz < 0 || gz >= MAP_N)
			continue;
		if (!full && !dun.seen[gz][gx] && it->type != ITEM_KEY)
			continue;
		uint32_t ic = it->type == ITEM_KEY ? 0xffffdc40U : it->type == ITEM_CHEST ? 0xffe8a030U : 0xff48d8ffU;
		float px = ox + (it->x / CELL) * cell, pz = oy + (it->z / CELL) * cell;
		float r = full ? 3.2f : 1.8f;
		hud_quad(px - r, pz - r, px + r, pz + r, ic);
	}
	{
		float px = ox + (dun.portal_x / CELL) * cell, pz = oy + (dun.portal_z / CELL) * cell;
		float r = full ? 4.2f : 2.4f;
		hud_quad(px - r, pz - r, px + r, pz + r, 0xff58f8ffU);
	}

	/* Nearby / visible monsters */
	for (int i = 0; i < dun.n_mons; i++) {
		const struct monster *m = &dun.mons[i];
		if (m->hp <= 0)
			continue;
		int gx = (int)(m->x / CELL), gz = (int)(m->z / CELL);
		if (gx < 0 || gx >= MAP_N || gz < 0 || gz >= MAP_N)
			continue;
		if (!full && !dun.seen[gz][gx])
			continue;
		float px = ox + (m->x / CELL) * cell, pz = oy + (m->z / CELL) * cell;
		float r = full ? 3.0f : 1.7f;
		hud_quad(px - r, pz - r, px + r, pz + r, m->kind == MON_ARCHON ? 0xffff44ffU : 0xffff3828U);
	}

	/* Player position & facing arrow */
	{
		float px = ox + (plr.x / CELL) * cell, pz = oy + (plr.z / CELL) * cell;
		float dir_x = sinf(plr.yaw), dir_z = cosf(plr.yaw);
		float len = full ? 9.0f : 5.5f;
		hud_line(px, pz, px + dir_x * len, pz + dir_z * len, full ? 2.2f : 1.6f, 0xff80ff90U);
		float r = full ? 3.2f : 2.0f;
		hud_quad(px - r, pz - r, px + r, pz + r, 0xffffffffU);
	}
}

static void draw_hud(const char *api_name, float fps, int show_fps, int show_map, int check_mode)
{
	static const char *const floor_names[4] = {
		"OBSIDIAN BASTION", "FLOODED CATACOMBS", "EMBER FORGE", "ASTRAL SANCTUM",
	};
	static const char *const wpn_names[3] = {
		"1:HALBERD", "2:EMBER ROD", "3:SCEPTER",
	};
	float W = (float)keep_view.w, H = (float)keep_view.h;
	float u = H * (1.0f / 480.0f);
	float ts = text_scale(u);
	char buf[96];

	/* Damage / pickup screen flash tint */
	if (plr.hurt_flash > 0.01f && !check_mode) {
		int a = (int)(plr.hurt_flash * 95.0f);
		if (a > 110)
			a = 110;
		hud_quad(0, 0, W, H, ((uint32_t)a << 24) | 0x00cc1810U);
	} else if (plr.bonus_flash > 0.01f && !check_mode) {
		int a = (int)(plr.bonus_flash * 65.0f);
		if (a > 80)
			a = 80;
		hud_quad(0, 0, W, H, ((uint32_t)a << 24) | 0x00ffd860U);
	}

	/* Top-left: Floor & Quest Status Panel */
	float px0 = 10.0f * u, py0 = 10.0f * u;
	float pw = 236.0f * u, ph = 56.0f * u;
	hud_panel(px0, py0, px0 + pw, py0 + ph, 0xb810121cU, 0xd8a8843cU);
	keep_fmt(buf, sizeof(buf), "FL %d: %s", dun.depth, floor_names[dun.floor_idx & 3]);
	hud_text(px0 + 7.0f * u, py0 + 6.0f * u, ts, 0xfff8dc88U, buf);
	keep_fmt(buf, sizeof(buf), "KEY:%s  GOLD:%d  FOES:%d/%d",
		 plr.has_key ? "READY" : "SEEK", plr.gold, dun.kills, dun.total_mons);
	hud_text(px0 + 7.0f * u, py0 + 22.0f * u, ts, plr.has_key ? 0xff78ff98U : 0xffd8dce8U, buf);

	/* Weapon selector strip inside top-left panel */
	for (int w = 0; w < 3; w++) {
		float wx = px0 + (7.0f + w * 75.0f) * u, wy = py0 + 38.0f * u;
		int sel = (plr.wpn == w);
		if (sel)
			hud_quad(wx - 2.0f * u, wy - 2.0f * u, wx + 70.0f * u, wy + 13.0f * u, 0x90785420U);
		hud_text(wx, wy, ts, sel ? 0xffffe890U : 0xff8c92a4U, wpn_names[w]);
	}

	/* Top-right: Corner Minimap */
	float msz = 108.0f * u;
	float mx0 = W - msz - 10.0f * u, my0 = 10.0f * u;
	draw_automap(mx0, my0, msz, 0);
	keep_fmt(buf, sizeof(buf), "%s %dx%d", api_name, keep_view.w, keep_view.h);
	hud_text(mx0, my0 + msz + 4.0f * u, ts, 0xc8b8c0d4U, buf);
	if (plr.autopilot && !check_mode)
		hud_text(mx0, my0 + msz + 17.0f * u, ts, 0xff78f0ffU, "AUTOPILOT [P]");

	/* Bottom-left: Vitality Bar (probed by -check!) */
	float bw = 186.0f * u, bh = 36.0f * u;
	float bx0 = 10.0f * u, by0 = H - bh - 10.0f * u;
	hud_panel(bx0, by0, bx0 + bw, by0 + bh, 0xc0121018U, 0xd8a8843cU);
	keep_fmt(buf, sizeof(buf), "VITALITY  %d / 100", plr.hp > 0 ? plr.hp : 0);
	hud_text(bx0 + 8.0f * u, by0 + 5.0f * u, ts, 0xffffd8d0U, buf);
	float bar_x0 = bx0 + 8.0f * u, bar_x1 = bx0 + bw - 8.0f * u;
	float bar_y0 = by0 + 19.0f * u, bar_y1 = by0 + bh - 5.0f * u;
	hud_quad(bar_x0, bar_y0, bar_x1, bar_y1, 0xff2c1014U);
	float hfrac = plr.hp * 0.01f;
	if (hfrac < 0.0f)
		hfrac = 0.0f;
	if (hfrac > 1.0f)
		hfrac = 1.0f;
	hud_quad(bar_x0, bar_y0, bar_x0 + (bar_x1 - bar_x0) * hfrac, bar_y1, 0xffe42824U);

	/* Bottom-right: Arcane Mana Bar (probed by -check!) */
	float mx1 = W - 10.0f * u, mx_l = mx1 - bw;
	hud_panel(mx_l, by0, mx1, by0 + bh, 0xc0101420U, 0xd8a8843cU);
	keep_fmt(buf, sizeof(buf), "ARCANA    %d / 100", (int)plr.mana);
	hud_text(mx_l + 8.0f * u, by0 + 5.0f * u, ts, 0xffd0ecffU, buf);
	float mbar_x0 = mx_l + 8.0f * u, mbar_x1 = mx1 - 8.0f * u;
	hud_quad(mbar_x0, bar_y0, mbar_x1, bar_y1, 0xff101c34U);
	float mfrac = plr.mana * 0.01f;
	if (mfrac < 0.0f)
		mfrac = 0.0f;
	if (mfrac > 1.0f)
		mfrac = 1.0f;
	hud_quad(mbar_x0, bar_y0, mbar_x0 + (mbar_x1 - mbar_x0) * mfrac, bar_y1, 0xff2484f4U);

	/* Center reticle */
	if (!show_map && !check_mode) {
		float cx = W * 0.5f, cy = H * 0.5f, cr = 4.0f * u;
		hud_quad(cx - cr, cy - 0.8f * u, cx + cr, cy + 0.8f * u, 0xc0ffe8a8U);
		hud_quad(cx - 0.8f * u, cy - cr, cx + 0.8f * u, cy + cr, 0xc0ffe8a8U);
	}

	/* Toast message banner */
	if (plr.toast_t > 0.0f && plr.toast[0] && !check_mode) {
		float tw = text_w(plr.toast, ts) + 20.0f * u;
		float tx = (W - tw) * 0.5f, ty = 74.0f * u;
		hud_panel(tx, ty, tx + tw, ty + 22.0f * u, 0xc8181422U, 0xffe8c058U);
		hud_text(tx + 10.0f * u, ty + 6.0f * u, ts, 0xffffec98U, plr.toast);
	}

	/* Optional FPS & frame-time graph [F] */
	if (show_fps && !check_mode) {
		float gx = 10.0f * u, gy = py0 + ph + 8.0f * u, gw = 132.0f * u, gh = 38.0f * u;
		hud_panel(gx, gy, gx + gw, gy + gh, 0xb010141cU, 0xc0687898U);
		keep_fmt(buf, sizeof(buf), "%.1f FPS", fps);
		hud_text(gx + 6.0f * u, gy + 4.0f * u, ts, 0xff90f8a8U, buf);
		for (int i = 0; i < 60; i++) {
			float ms = frame_ms_hist[(frame_ms_idx + 60 + i) % 120];
			float h = ms * 0.65f * u;
			if (h > gh - 16.0f * u)
				h = gh - 16.0f * u;
			float bx = gx + 6.0f * u + i * 2.0f * u;
			hud_quad(bx, gy + gh - 3.0f * u - h, bx + 1.5f * u, gy + gh - 3.0f * u, 0xd058d8ffU);
		}
	}

	/* Full-screen Automap Overlay [Tab / M] */
	if (show_map && !check_mode) {
		float asz = (H < W ? H : W) * 0.62f;
		float ax = (W - asz) * 0.5f, ay = (H - asz) * 0.5f + 16.0f * u;
		draw_automap(ax, ay, asz, 1);
		hud_text(ax + 8.0f * u, ay - 14.0f * u, ts, 0xffffe490U, "CITADEL AUTOMAP [TAB / M]");
	}
}

#endif
