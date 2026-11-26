/*
 * wshracer: 3D view-space Sutherland-Hodgman frustum clipper (znear=1.0 for Voodoo 16-bit W-buffer),
 * triangle batcher, basis-oriented 3D mesh lighting, ribbon/quad emitter, billboards, and 2D HUD.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_RACER_RENDER_H
#define WSH_RACER_RENDER_H

static const struct backend *cur_be;
static struct rstate cur_st = {-99, 0, 0, 0, 0, 0, 0};

#define BATCH_MAX 768
static struct dvtx batch[BATCH_MAX];
static int batch_n;

static void flush_tris(void)
{
	if (batch_n >= 3)
		cur_be->tris(batch, batch_n);
	batch_n = 0;
}

static void set_state(int tex, int blend, int depth, int fog, int filter, int clamp, int mode2d)
{
	struct rstate s = {tex, (uint8_t)blend, (uint8_t)depth, (uint8_t)fog, (uint8_t)filter, (uint8_t)clamp, (uint8_t)mode2d};
	if (s.tex == cur_st.tex && s.blend == cur_st.blend && s.depth == cur_st.depth &&
	    s.fog == cur_st.fog && s.filter == cur_st.filter && s.clamp == cur_st.clamp && s.mode2d == cur_st.mode2d)
		return;
	flush_tris();
	cur_st = s;
	cur_be->state(&s);
}

/* Camera basis (+Z forward into view, +X right, +Y up) & scene lighting */
static struct {
	v3 pos, right, up, fwd;
	v3 sun_dir;
	float sun_r, sun_g, sun_b;
	float amb_r, amb_g, amb_b;
} cam;

static inline v3 world_to_view(v3 w)
{
	v3 d = v3_sub(w, cam.pos);
	return v3_make(v3_dot(d, cam.right), v3_dot(d, cam.up), v3_dot(d, cam.fwd));
}

/* --- 6-plane view-space Sutherland-Hodgman polygon clipper -------------------------------------- */

struct cvtx {
	float x, y, z;
	float r, g, b, a;
	float s, t;
};

static float plane_eval(const struct cvtx *v, int plane, float kx, float ky)
{
	switch (plane) {
	case 0: return v->z - racer_view.znear;
	case 1: return racer_view.zfar - v->z;
	case 2: return v->x + kx * v->z;
	case 3: return kx * v->z - v->x;
	case 4: return v->y + ky * v->z;
	default: return ky * v->z - v->y;
	}
}

static struct cvtx cvtx_lerp(const struct cvtx *a, const struct cvtx *b, float t)
{
	struct cvtx o;
	o.x = a->x + (b->x - a->x) * t;
	o.y = a->y + (b->y - a->y) * t;
	o.z = a->z + (b->z - a->z) * t;
	o.r = a->r + (b->r - a->r) * t;
	o.g = a->g + (b->g - a->g) * t;
	o.b = a->b + (b->b - a->b) * t;
	o.a = a->a + (b->a - a->a) * t;
	o.s = a->s + (b->s - a->s) * t;
	o.t = a->t + (b->t - a->t) * t;
	return o;
}

static void emit_tri_view(const struct cvtx tri[3])
{
	float kx = (racer_view.w * 0.5f) / racer_view.f;
	float ky = (racer_view.h * 0.5f) / racer_view.f;
	struct cvtx buf_a[12], buf_b[12];
	buf_a[0] = tri[0], buf_a[1] = tri[1], buf_a[2] = tri[2];
	int n = 3;
	struct cvtx *src = buf_a, *dst = buf_b;

	for (int p = 0; p < 6; p++) {
		int out_n = 0;
		struct cvtx prev = src[n - 1];
		float d_prev = plane_eval(&prev, p, kx, ky);
		for (int i = 0; i < n; i++) {
			struct cvtx cur = src[i];
			float d_cur = plane_eval(&cur, p, kx, ky);
			if (d_cur >= 0.0f) {
				if (d_prev < 0.0f)
					dst[out_n++] = cvtx_lerp(&prev, &cur, d_prev / (d_prev - d_cur));
				dst[out_n++] = cur;
			} else if (d_prev >= 0.0f) {
				dst[out_n++] = cvtx_lerp(&prev, &cur, d_prev / (d_prev - d_cur));
			}
			prev = cur;
			d_prev = d_cur;
		}
		n = out_n;
		if (n < 3)
			return;
		struct cvtx *tmp = src;
		src = dst;
		dst = tmp;
	}

	float cx = racer_view.w * 0.5f, cy = racer_view.h * 0.5f, f = racer_view.f;
	for (int i = 1; i + 1 < n; i++) {
		if (batch_n + 3 > BATCH_MAX)
			flush_tris();
		const struct cvtx *vp[3] = {&src[0], &src[i], &src[i + 1]};
		for (int k = 0; k < 3; k++) {
			float iz = 1.0f / vp[k]->z;
			struct dvtx *d = &batch[batch_n++];
			d->vx = vp[k]->x, d->vy = vp[k]->y, d->vz = vp[k]->z;
			d->oow = iz;
			d->x = cx + vp[k]->x * f * iz;
			d->y = cy - vp[k]->y * f * iz;
			d->r = clampf(vp[k]->r, 0.0f, 255.0f);
			d->g = clampf(vp[k]->g, 0.0f, 255.0f);
			d->b = clampf(vp[k]->b, 0.0f, 255.0f);
			d->a = clampf(vp[k]->a, 0.0f, 255.0f);
			d->s = vp[k]->s;
			d->t = vp[k]->t;
		}
	}
}

/* World-space quad emitter with per-vertex colors & UVs */
static void emit_quad_world(v3 p0, v3 p1, v3 p2, v3 p3,
			    float s0, float t0, float s1, float t1, float s2, float t2, float s3, float t3,
			    uint32_t c0, uint32_t c1, uint32_t c2, uint32_t c3)
{
	v3 wp[4] = {p0, p1, p2, p3};
	float ss[4] = {s0, s1, s2, s3};
	float tt[4] = {t0, t1, t2, t3};
	uint32_t cc[4] = {c0, c1, c2, c3};
	struct cvtx v[4];
	for (int i = 0; i < 4; i++) {
		v3 vp = world_to_view(wp[i]);
		v[i].x = vp.x, v[i].y = vp.y, v[i].z = vp.z;
		v[i].a = (float)((cc[i] >> 24) & 255);
		v[i].r = (float)((cc[i] >> 16) & 255);
		v[i].g = (float)((cc[i] >> 8) & 255);
		v[i].b = (float)(cc[i] & 255);
		v[i].s = ss[i], v[i].t = tt[i];
	}
	/* Quick reject when all 4 corners are behind near plane or beyond far plane */
	if (v[0].z < racer_view.znear && v[1].z < racer_view.znear && v[2].z < racer_view.znear && v[3].z < racer_view.znear)
		return;
	if (v[0].z > racer_view.zfar && v[1].z > racer_view.zfar && v[2].z > racer_view.zfar && v[3].z > racer_view.zfar)
		return;
	struct cvtx t_a[3] = {v[0], v[1], v[2]};
	struct cvtx t_b[3] = {v[0], v[2], v[3]};
	emit_tri_view(t_a);
	emit_tri_view(t_b);
}

/* Basis-oriented 3D mesh renderer (supports arbitrary craft roll/pitch/yaw without gimbal lock) */
static void draw_mesh_basis(int id, v3 pos, v3 bx, v3 by, v3 bz, float scale,
			    float tr, float tg, float tb, int tex, int fog)
{
	v3 vc = world_to_view(pos);
	float rad = 22.0f * scale;
	if (vc.z + rad < racer_view.znear || vc.z - rad > racer_view.zfar)
		return;

	set_state(tex, BLEND_NONE, DEPTH_RW, fog, 1, CLAMP_WRAP, 0);
	bx = v3_scale(bx, scale);
	by = v3_scale(by, scale);
	bz = v3_scale(bz, scale);

	int first = meshes[id].first, count = meshes[id].count;
	for (int i = 0; i < count; i++) {
		const struct mtri *m = &mesh_pool[first + i];
		v3 wn = v3_norm(v3_make(
			bx.x * m->n.x + by.x * m->n.y + bz.x * m->n.z,
			bx.y * m->n.x + by.y * m->n.y + bz.y * m->n.z,
			bx.z * m->n.x + by.z * m->n.y + bz.z * m->n.z));
		float ndl = v3_dot(wn, cam.sun_dir);
		if (ndl < 0.0f)
			ndl = -ndl * 0.22f;
		/* Subtle sky-hemisphere rim highlight */
		float sky_up = clampf(wn.y * 0.5f + 0.5f, 0.0f, 1.0f) * 0.22f;
		float lr = clampf(cam.amb_r + sky_up + ndl * cam.sun_r, 0.0f, 1.45f);
		float lg = clampf(cam.amb_g + sky_up + ndl * cam.sun_g, 0.0f, 1.45f);
		float lb = clampf(cam.amb_b + sky_up + ndl * cam.sun_b, 0.0f, 1.45f);

		/* Keep white/dark cockpit glass & bright rear nozzles distinct from team hull tint */
		int neutral = (m->cb > m->cr + 25 && m->cr < 100) || (m->cr == 255 && m->cg == 220);
		float mr = neutral ? (float)m->cr : (m->cr * tr) * (1.0f / 255.0f);
		float mg = neutral ? (float)m->cg : (m->cg * tg) * (1.0f / 255.0f);
		float mb = neutral ? (float)m->cb : (m->cb * tb) * (1.0f / 255.0f);

		struct cvtx cv[3];
		for (int k = 0; k < 3; k++) {
			v3 lp = m->p[k];
			v3 wp = v3_make(
				pos.x + bx.x * lp.x + by.x * lp.y + bz.x * lp.z,
				pos.y + bx.y * lp.x + by.y * lp.y + bz.y * lp.z,
				pos.z + bx.z * lp.x + by.z * lp.y + bz.z * lp.z);
			v3 vp = world_to_view(wp);
			cv[k].x = vp.x, cv[k].y = vp.y, cv[k].z = vp.z;
			cv[k].r = mr * lr;
			cv[k].g = mg * lg;
			cv[k].b = mb * lb;
			cv[k].a = 255.0f;
			cv[k].s = m->u[k], cv[k].t = m->v[k];
		}
		emit_tri_view(cv);
	}
}

/* Camera-facing additive sprite (thruster plasma, sun corona, tunnel lamps, sparks) */
static void draw_billboard(v3 wpos, float radius, uint32_t argb, int depth_ro)
{
	v3 vc = world_to_view(wpos);
	if (vc.z < racer_view.znear || vc.z > racer_view.zfar)
		return;
	set_state(TEX_FLARE, BLEND_ADD, depth_ro ? DEPTH_RO : DEPTH_OFF, 0, 1, CLAMP_ALL, 0);
	float a = (float)((argb >> 24) & 255);
	float r = (float)((argb >> 16) & 255);
	float g = (float)((argb >> 8) & 255);
	float b = (float)(argb & 255);
	struct cvtx q[4] = {
		{vc.x - radius, vc.y + radius, vc.z, r, g, b, a, 0, 0},
		{vc.x + radius, vc.y + radius, vc.z, r, g, b, a, 1, 0},
		{vc.x + radius, vc.y - radius, vc.z, r, g, b, a, 1, 1},
		{vc.x - radius, vc.y - radius, vc.z, r, g, b, a, 0, 1},
	};
	struct cvtx t0[3] = {q[0], q[1], q[2]};
	struct cvtx t1[3] = {q[0], q[2], q[3]};
	emit_tri_view(t0);
	emit_tri_view(t1);
}

/* --- 2D HUD drawing helpers --------------------------------------------------------------------- */

static void quad2d_tex(int tex, int blend, int filter, float x0, float y0, float x1, float y1,
		       float s0, float t0, float s1, float t1, uint32_t argb)
{
	set_state(tex, blend, DEPTH_OFF, 0, filter, CLAMP_ALL, 1);
	if (batch_n + 6 > BATCH_MAX)
		flush_tris();
	float a = (float)((argb >> 24) & 255);
	float r = (float)((argb >> 16) & 255);
	float g = (float)((argb >> 8) & 255);
	float b = (float)(argb & 255);
	float xs[6] = {x0, x1, x1, x0, x1, x0};
	float ys[6] = {y0, y0, y1, y0, y1, y1};
	float ss[6] = {s0, s1, s1, s0, s1, s0};
	float ts[6] = {t0, t0, t1, t0, t1, t1};
	for (int i = 0; i < 6; i++) {
		struct dvtx *d = &batch[batch_n++];
		d->x = xs[i], d->y = ys[i], d->oow = 1.0f;
		d->vx = xs[i], d->vy = ys[i], d->vz = 1.0f;
		d->r = r, d->g = g, d->b = b, d->a = a;
		d->s = ss[i], d->t = ts[i];
	}
}

static void rect2d(float x, float y, float w, float h, uint32_t argb)
{
	quad2d_tex(-1, ((argb >> 24) & 255) < 255 ? BLEND_ALPHA : BLEND_NONE, 0,
		   x, y, x + w, y + h, 0, 0, 1, 1, argb);
}

static void line2d(float x0, float y0, float x1, float y1, float thick, uint32_t argb)
{
	float dx = x1 - x0, dy = y1 - y0;
	float l = m_sqrtf(dx * dx + dy * dy);
	if (l < 0.5f)
		return;
	float nx = -dy / l * (thick * 0.5f), ny = dx / l * (thick * 0.5f);
	set_state(-1, BLEND_ALPHA, DEPTH_OFF, 0, 0, CLAMP_ALL, 1);
	if (batch_n + 6 > BATCH_MAX)
		flush_tris();
	float a = (float)((argb >> 24) & 255);
	float r = (float)((argb >> 16) & 255);
	float g = (float)((argb >> 8) & 255);
	float b = (float)(argb & 255);
	float xs[6] = {x0 + nx, x1 + nx, x1 - nx, x0 + nx, x1 - nx, x0 - nx};
	float ys[6] = {y0 + ny, y1 + ny, y1 - ny, y0 + ny, y1 - ny, y0 - ny};
	for (int i = 0; i < 6; i++) {
		struct dvtx *d = &batch[batch_n++];
		d->x = xs[i], d->y = ys[i], d->oow = 1.0f;
		d->vx = xs[i], d->vy = ys[i], d->vz = 1.0f;
		d->r = r, d->g = g, d->b = b, d->a = a;
		d->s = 0, d->t = 0;
	}
}

static void draw_box_border(float x, float y, float w, float h, uint32_t fill, uint32_t border)
{
	rect2d(x, y, w, h, fill);
	rect2d(x, y, w, 1.5f, border);
	rect2d(x, y + h - 1.5f, w, 1.5f, border);
	rect2d(x, y, 1.5f, h, border);
	rect2d(x + w - 1.5f, y, 1.5f, h, border);
}

static void draw_str(float x, float y, float scale, uint32_t argb, const char *s)
{
	float cw = 8.0f * scale, ch = 16.0f * scale, adv = 6.5f * scale;
	for (; *s; s++, x += adv) {
		int c = (unsigned char)*s;
		if (c >= 'a' && c <= 'z')
			c -= 'a' - 'A';
		if (c == '|')
			c = '!';
		if (c <= 32 || c > 95)
			continue;
		float u0 = ((c & 15) * 8) * (1.0f / 128.0f);
		float v0 = (((c - 32) >> 4) * 16) * (1.0f / 128.0f);
		quad2d_tex(TEX_FONT, BLEND_ALPHA, 0, x, y, x + cw, y + ch,
			   u0, v0, u0 + 8.0f / 128.0f, v0 + 16.0f / 128.0f, argb);
	}
}

static void draw_str_center(float cx, float y, float scale, uint32_t argb, const char *s)
{
	int len = 0;
	while (s[len])
		len++;
	draw_str(cx - (float)len * 6.5f * scale * 0.5f, y, scale, argb, s);
}

#endif
