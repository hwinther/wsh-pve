/*
 * 3D dynamic-torchlight renderer, 6-plane view-space Sutherland-Hodgman frustum clipper,
 * additive flare billboards, first-person 3D weapon pass, and 2D HUD helpers for wshkeep.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_KEEP_RENDER_H
#define WSH_KEEP_RENDER_H

static const struct backend *R;
static struct dvtx batch[1536];
static int n_batch;
static struct rstate cur_st = {-2, 0, 0, 0, 0, 0, 0};

static void flush(void)
{
	if (n_batch > 0) {
		R->tris(batch, n_batch);
		n_batch = 0;
	}
}

static void set_state(int tex, uint8_t blend, uint8_t depth, uint8_t fog, uint8_t filter, uint8_t clamp, uint8_t mode2d)
{
	if (cur_st.tex == tex && cur_st.blend == blend && cur_st.depth == depth && cur_st.fog == fog &&
	    cur_st.filter == filter && cur_st.clamp == clamp && cur_st.mode2d == mode2d)
		return;
	flush();
	cur_st.tex = tex, cur_st.blend = blend, cur_st.depth = depth, cur_st.fog = fog;
	cur_st.filter = filter, cur_st.clamp = clamp, cur_st.mode2d = mode2d;
	R->state(&cur_st);
}

static void reset_state(void)
{
	n_batch = 0;
	cur_st.tex = -2;
}

/* --- Dynamic Colored Point Lights (torches, spell bolts, lava, key, portal) --- */
#define MAX_DLIGHTS 28
struct dlight {
	float x, y, z;
	float r, g, b; /* 0..2.0 intensity */
	float rad2;
};
static struct dlight dlights[MAX_DLIGHTS];
static int n_dlights;
static float amb_r = 0.20f, amb_g = 0.20f, amb_b = 0.26f;

static void clear_dlights(float ar, float ag, float ab)
{
	n_dlights = 0;
	amb_r = ar, amb_g = ag, amb_b = ab;
}

static void add_dlight(float x, float y, float z, float r, float g, float b, float radius)
{
	if (n_dlights >= MAX_DLIGHTS)
		return;
	struct dlight *dl = &dlights[n_dlights++];
	dl->x = x, dl->y = y, dl->z = z;
	dl->r = r, dl->g = g, dl->b = b;
	dl->rad2 = radius * radius;
}

static void eval_light(float wx, float wy, float wz, float nx, float ny, float nz,
		       float *or_c, float *og_c, float *ob_c)
{
	float lr = amb_r, lg = amb_g, lb = amb_b;
	for (int i = 0; i < n_dlights; i++) {
		const struct dlight *dl = &dlights[i];
		float dx = dl->x - wx, dy = dl->y - wy, dz = dl->z - wz;
		float d2 = dx * dx + dy * dy + dz * dz;
		if (d2 > dl->rad2 * 2.2f)
			continue;
		float att = dl->rad2 / (d2 + 0.28f * dl->rad2) - 0.31f;
		if (att <= 0.0f)
			continue;
		float ndl = 1.0f;
		if (nx != 0.0f || ny != 0.0f || nz != 0.0f) {
			float inv = 1.0f / sqrtf(d2 + 0.5f);
			float dot = (dx * nx + dy * ny + dz * nz) * inv;
			ndl = 0.35f + 0.65f * (dot < 0.0f ? 0.0f : dot);
		}
		float w = att * ndl;
		lr += dl->r * w;
		lg += dl->g * w;
		lb += dl->b * w;
	}
	if (lr > 1.28f)
		lr = 1.28f;
	if (lg > 1.28f)
		lg = 1.28f;
	if (lb > 1.28f)
		lb = 1.28f;
	*or_c = lr;
	*og_c = lg;
	*ob_c = lb;
}

/* --- Camera & 6-Plane View-Space Sutherland-Hodgman Frustum Clipper --- */
static struct {
	float x, y, z;
	float rx[3], ux[3], fx[3];
} cam;

static void cam_setup(float x, float y, float z, float yaw, float pitch)
{
	cam.x = x, cam.y = y, cam.z = z;
	float cy = cosf(yaw), sy = sinf(yaw), cp = cosf(pitch), sp = sinf(pitch);
	/* +X right, +Y up, yaw=0 looks along +Z */
	cam.fx[0] = sy * cp, cam.fx[1] = sp, cam.fx[2] = cy * cp;
	cam.rx[0] = cy, cam.rx[1] = 0.0f, cam.rx[2] = -sy;
	cam.ux[0] = -sy * sp, cam.ux[1] = cp, cam.ux[2] = -cy * sp;
}

struct cvtx {
	float vx, vy, vz;
	float r, g, b, a;
	float s, t;
};

static int clip_plane(const struct cvtx *in, int n, struct cvtx *out, int p, float k)
{
	if (n < 3)
		return 0;
	int m = 0;
	const struct cvtx *prev = &in[n - 1];
	float dp = p == 0 ? prev->vz - k : p == 1 ? k - prev->vz :
		   p == 2 ? prev->vx + k * prev->vz : p == 3 ? k * prev->vz - prev->vx :
		   p == 4 ? prev->vy + k * prev->vz : k * prev->vz - prev->vy;
	for (int i = 0; i < n; i++) {
		const struct cvtx *cur = &in[i];
		float dc = p == 0 ? cur->vz - k : p == 1 ? k - cur->vz :
			   p == 2 ? cur->vx + k * cur->vz : p == 3 ? k * cur->vz - cur->vx :
			   p == 4 ? cur->vy + k * cur->vz : k * cur->vz - cur->vy;
		if ((dp >= 0.0f) != (dc >= 0.0f)) {
			float f = dp / (dp - dc);
			struct cvtx *q = &out[m++];
			q->vx = prev->vx + (cur->vx - prev->vx) * f;
			q->vy = prev->vy + (cur->vy - prev->vy) * f;
			q->vz = prev->vz + (cur->vz - prev->vz) * f;
			q->r = prev->r + (cur->r - prev->r) * f;
			q->g = prev->g + (cur->g - prev->g) * f;
			q->b = prev->b + (cur->b - prev->b) * f;
			q->a = prev->a + (cur->a - prev->a) * f;
			q->s = prev->s + (cur->s - prev->s) * f;
			q->t = prev->t + (cur->t - prev->t) * f;
		}
		if (dc >= 0.0f)
			out[m++] = *cur;
		prev = cur;
		dp = dc;
	}
	return m;
}

static void emit_view_poly(const struct cvtx *in, int n)
{
	struct cvtx b0[16], b1[16];
	float kx = (keep_view.w * 0.5f) / keep_view.f;
	float ky = (keep_view.h * 0.5f) / keep_view.f;
	int c = clip_plane(in, n, b0, 0, keep_view.znear);
	c = clip_plane(b0, c, b1, 1, keep_view.zfar);
	c = clip_plane(b1, c, b0, 2, kx);
	c = clip_plane(b0, c, b1, 3, kx);
	c = clip_plane(b1, c, b0, 4, ky);
	c = clip_plane(b0, c, b1, 5, ky);
	if (c < 3)
		return;
	float cx = keep_view.w * 0.5f, cy = keep_view.h * 0.5f;
	struct dvtx pv[16];
	for (int i = 0; i < c; i++) {
		float oow = 1.0f / b1[i].vz;
		pv[i].vx = b1[i].vx, pv[i].vy = b1[i].vy, pv[i].vz = b1[i].vz;
		pv[i].oow = oow;
		pv[i].x = cx + b1[i].vx * keep_view.f * oow;
		pv[i].y = cy - b1[i].vy * keep_view.f * oow;
		pv[i].r = b1[i].r < 0 ? 0 : b1[i].r > 255 ? 255 : b1[i].r;
		pv[i].g = b1[i].g < 0 ? 0 : b1[i].g > 255 ? 255 : b1[i].g;
		pv[i].b = b1[i].b < 0 ? 0 : b1[i].b > 255 ? 255 : b1[i].b;
		pv[i].a = b1[i].a < 0 ? 0 : b1[i].a > 255 ? 255 : b1[i].a;
		pv[i].s = b1[i].s;
		pv[i].t = b1[i].t;
	}
	for (int i = 1; i + 1 < c; i++) {
		if (n_batch + 3 > (int)(sizeof(batch) / sizeof(batch[0])))
			flush();
		batch[n_batch++] = pv[0];
		batch[n_batch++] = pv[i];
		batch[n_batch++] = pv[i + 1];
	}
}

static void world_to_view(float wx, float wy, float wz, float *vx, float *vy, float *vz)
{
	float dx = wx - cam.x, dy = wy - cam.y, dz = wz - cam.z;
	*vx = dx * cam.rx[0] + dy * cam.rx[1] + dz * cam.rx[2];
	*vy = dx * cam.ux[0] + dy * cam.ux[1] + dz * cam.ux[2];
	*vz = dx * cam.fx[0] + dy * cam.fx[1] + dz * cam.fx[2];
}

/* Lit world quad (a,b,c,d) with normal (nx,ny,nz) and base tint rgb */
static void draw_lit_quad(const float p[4][3], const float uv[4][2],
			  float nx, float ny, float nz, uint32_t rgb, int unlit)
{
	float br = (float)((rgb >> 16) & 0xff), bg = (float)((rgb >> 8) & 0xff), bb = (float)(rgb & 0xff);
	struct cvtx v[4];
	int front = 0;
	for (int k = 0; k < 4; k++) {
		world_to_view(p[k][0], p[k][1], p[k][2], &v[k].vx, &v[k].vy, &v[k].vz);
		if (v[k].vz > keep_view.znear)
			front = 1;
		if (unlit) {
			v[k].r = br, v[k].g = bg, v[k].b = bb;
		} else {
			float lr, lg, lb;
			eval_light(p[k][0], p[k][1], p[k][2], nx, ny, nz, &lr, &lg, &lb);
			v[k].r = br * lr, v[k].g = bg * lg, v[k].b = bb * lb;
		}
		v[k].a = 255.0f;
		v[k].s = uv[k][0], v[k].t = uv[k][1];
	}
	if (front)
		emit_view_poly(v, 4);
}

/* Draw a sculpted 3D mesh in world space with yaw, non-uniform scale (sx,sy,sz), and tint */
static void draw_mesh_world(int id, float wx, float wy, float wz, float yaw,
			    float sx, float sy, float sz, uint32_t tint, float flash)
{
	float vx0, vy0, vz0;
	world_to_view(wx, wy + 3.0f * sy, wz, &vx0, &vy0, &vz0);
	if (vz0 < -14.0f || vz0 > keep_view.zfar + 16.0f)
		return;

	/* Evaluate local dynamic point lighting at the entity center + top */
	float lr0, lg0, lb0, lr1, lg1, lb1;
	eval_light(wx, wy + 1.5f * sy, wz, 0, 1, 0, &lr0, &lg0, &lb0);
	eval_light(wx, wy + 5.0f * sy, wz, 0, 1, 0, &lr1, &lg1, &lb1);
	float lr = (lr0 + lr1) * 0.5f, lg = (lg0 + lg1) * 0.5f, lb = (lb0 + lb1) * 0.5f;
	float tr = ((tint >> 16) & 0xff) * (1.0f / 255.0f);
	float tg = ((tint >> 8) & 0xff) * (1.0f / 255.0f);
	float tb = (tint & 0xff) * (1.0f / 255.0f);

	float cy = cosf(yaw), syw = sinf(yaw);
	const struct mesh_span *ms = &meshes[id];
	for (int i = 0; i < ms->count; i++) {
		const struct mtri *mt = &mtris[ms->first + i];
		struct cvtx cv[3];
		int vis = 0;
		for (int k = 0; k < 3; k++) {
			float lx = mt->v[k][0] * sx, ly = mt->v[k][1] * sy, lz = mt->v[k][2] * sz;
			float px = wx + lx * cy + lz * syw;
			float py = wy + ly;
			float pz = wz - lx * syw + lz * cy;
			world_to_view(px, py, pz, &cv[k].vx, &cv[k].vy, &cv[k].vz);
			if (cv[k].vz > keep_view.znear)
				vis = 1;
			if (mt->glow) {
				cv[k].r = mt->r, cv[k].g = mt->g, cv[k].b = mt->b;
			} else {
				cv[k].r = mt->r * tr * lr + flash * 160.0f;
				cv[k].g = mt->g * tg * lg + flash * 60.0f;
				cv[k].b = mt->b * tb * lb + flash * 40.0f;
			}
			cv[k].a = 255.0f;
			cv[k].s = mt->u[k], cv[k].t = mt->t[k];
		}
		if (vis)
			emit_view_poly(cv, 3);
	}
}

/* Draw first-person 3D weapon directly in view space (after world pass, depth-tested against close walls) */
static void draw_weapon_view(int id, float ox, float oy, float oz,
			     float pitch_ang, float roll_ang, float yaw_ang, float scale)
{
	float lr, lg, lb;
	eval_light(cam.x + cam.fx[0] * 2.0f, cam.y, cam.z + cam.fx[2] * 2.0f, 0, 1, 0, &lr, &lg, &lb);
	if (lr < 0.55f)
		lr = 0.55f;
	if (lg < 0.52f)
		lg = 0.52f;
	if (lb < 0.55f)
		lb = 0.55f;
	float cp = cosf(pitch_ang), sp = sinf(pitch_ang);
	float cr = cosf(roll_ang), sr = sinf(roll_ang);
	float cy = cosf(yaw_ang), sy = sinf(yaw_ang);
	const struct mesh_span *ms = &meshes[id];
	for (int i = 0; i < ms->count; i++) {
		const struct mtri *mt = &mtris[ms->first + i];
		struct cvtx cv[3];
		for (int k = 0; k < 3; k++) {
			float x = mt->v[k][0] * scale, y = mt->v[k][1] * scale, z = mt->v[k][2] * scale;
			/* Roll around Z, pitch around X, yaw around Y */
			float x1 = x * cr - y * sr, y1 = x * sr + y * cr;
			float y2 = y1 * cp - z * sp, z2 = y1 * sp + z * cp;
			float x3 = x1 * cy + z2 * sy, z3 = -x1 * sy + z2 * cy;
			cv[k].vx = ox + x3;
			cv[k].vy = oy + y2;
			cv[k].vz = oz + z3;
			if (mt->glow) {
				cv[k].r = mt->r, cv[k].g = mt->g, cv[k].b = mt->b;
			} else {
				cv[k].r = mt->r * lr, cv[k].g = mt->g * lg, cv[k].b = mt->b * lb;
			}
			cv[k].a = 255.0f;
			cv[k].s = mt->u[k], cv[k].t = mt->t[k];
		}
		emit_view_poly(cv, 3);
	}
}

/* Camera-facing additive flare billboard */
static void draw_billboard(float wx, float wy, float wz, float rad, uint32_t rgb, float alpha)
{
	float vx, vy, vz;
	world_to_view(wx, wy, wz, &vx, &vy, &vz);
	if (vz <= keep_view.znear || vz >= keep_view.zfar)
		return;
	float r = (float)((rgb >> 16) & 0xff), g = (float)((rgb >> 8) & 0xff), b = (float)(rgb & 0xff);
	float a = alpha * 255.0f;
	struct cvtx q[4] = {
		{vx - rad, vy + rad, vz, r, g, b, a, 0, 0},
		{vx + rad, vy + rad, vz, r, g, b, a, 1, 0},
		{vx + rad, vy - rad, vz, r, g, b, a, 1, 1},
		{vx - rad, vy - rad, vz, r, g, b, a, 0, 1},
	};
	emit_view_poly(q, 4);
}

/* --- 2D HUD Drawing Helpers --- */
static void hud_quad(float x0, float y0, float x1, float y1, uint32_t argb)
{
	set_state(-1, ((argb >> 24) < 255) ? BLEND_ALPHA : BLEND_NONE, DEPTH_OFF, 0, 0, CLAMP_ALL, 1);
	if (n_batch + 6 > (int)(sizeof(batch) / sizeof(batch[0])))
		flush();
	float a = (float)((argb >> 24) & 0xff), r = (float)((argb >> 16) & 0xff);
	float g = (float)((argb >> 8) & 0xff), b = (float)(argb & 0xff);
	struct dvtx v[4] = {
		{x0, y0, 1.0f, 0, 0, 1, r, g, b, a, 0, 0},
		{x1, y0, 1.0f, 0, 0, 1, r, g, b, a, 1, 0},
		{x1, y1, 1.0f, 0, 0, 1, r, g, b, a, 1, 1},
		{x0, y1, 1.0f, 0, 0, 1, r, g, b, a, 0, 1},
	};
	batch[n_batch++] = v[0], batch[n_batch++] = v[1], batch[n_batch++] = v[2];
	batch[n_batch++] = v[0], batch[n_batch++] = v[2], batch[n_batch++] = v[3];
}

static void hud_line(float x0, float y0, float x1, float y1, float w, uint32_t argb)
{
	float dx = x1 - x0, dy = y1 - y0;
	float l = sqrtf(dx * dx + dy * dy);
	if (l < 0.2f)
		return;
	float nx = -dy / l * (w * 0.5f), ny = dx / l * (w * 0.5f);
	set_state(-1, ((argb >> 24) < 255) ? BLEND_ALPHA : BLEND_NONE, DEPTH_OFF, 0, 0, CLAMP_ALL, 1);
	if (n_batch + 6 > (int)(sizeof(batch) / sizeof(batch[0])))
		flush();
	float a = (float)((argb >> 24) & 0xff), r = (float)((argb >> 16) & 0xff);
	float g = (float)((argb >> 8) & 0xff), b = (float)(argb & 0xff);
	struct dvtx v[4] = {
		{x0 + nx, y0 + ny, 1.0f, 0, 0, 1, r, g, b, a, 0, 0},
		{x1 + nx, y1 + ny, 1.0f, 0, 0, 1, r, g, b, a, 1, 0},
		{x1 - nx, y1 - ny, 1.0f, 0, 0, 1, r, g, b, a, 1, 1},
		{x0 - nx, y0 - ny, 1.0f, 0, 0, 1, r, g, b, a, 0, 1},
	};
	batch[n_batch++] = v[0], batch[n_batch++] = v[1], batch[n_batch++] = v[2];
	batch[n_batch++] = v[0], batch[n_batch++] = v[2], batch[n_batch++] = v[3];
}

static void hud_text(float x, float y, float sc, uint32_t argb, const char *s)
{
	set_state(TEX_FONT, BLEND_ALPHA, DEPTH_OFF, 0, 0, CLAMP_ALL, 1);
	float a = (float)((argb >> 24) & 0xff), r = (float)((argb >> 16) & 0xff);
	float g = (float)((argb >> 8) & 0xff), b = (float)(argb & 0xff);
	float cx = x;
	for (; *s; s++) {
		int c = (unsigned char)*s;
		if (c == '\n') {
			cx = x;
			y += 11.0f * sc;
			continue;
		}
		if (c >= 'a' && c <= 'z')
			c -= 'a' - 'A';
		if (c == '|')
			c = '!';
		if (c < 32 || c > 95)
			c = '?';
		int idx = c - 32;
		float u0 = ((idx & 15) * 8) * (1.0f / 128.0f), u1 = u0 + 7.0f / 128.0f;
		float v0 = ((idx >> 4) * 16 + 1) * (1.0f / 128.0f), v1 = v0 + 10.0f / 128.0f;
		float w = 7.0f * sc, h = 10.0f * sc;
		if (n_batch + 6 > (int)(sizeof(batch) / sizeof(batch[0])))
			flush();
		struct dvtx q[4] = {
			{cx, y, 1.0f, 0, 0, 1, r, g, b, a, u0, v0},
			{cx + w, y, 1.0f, 0, 0, 1, r, g, b, a, u1, v0},
			{cx + w, y + h, 1.0f, 0, 0, 1, r, g, b, a, u1, v1},
			{cx, y + h, 1.0f, 0, 0, 1, r, g, b, a, u0, v1},
		};
		batch[n_batch++] = q[0], batch[n_batch++] = q[1], batch[n_batch++] = q[2];
		batch[n_batch++] = q[0], batch[n_batch++] = q[2], batch[n_batch++] = q[3];
		cx += 6.0f * sc;
	}
}

static float text_w(const char *s, float sc)
{
	int n = 0;
	while (s[n])
		n++;
	return n * 6.0f * sc;
}

#endif
