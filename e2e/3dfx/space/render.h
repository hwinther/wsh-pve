/*
 * render.h: batch submission, 6-plane 3D Sutherland-Hodgman frustum clipper (keeping every Glide
 * vertex inside the screen and W in [1..zfar]), dynamic star + point-light mesh shader, 3D laser
 * ribbons, billboards, planetary rings and 2D HUD helpers. Included by space.c.
 * Copyright 2026 WsHosting ENK, GPL-3.
 */
#ifndef WSH_SPACE_RENDER_H
#define WSH_SPACE_RENDER_H

#define MAX_BATCH_V 3600

static const struct backend *be;
struct view space_view;

static struct dvtx batch_v[MAX_BATCH_V];
static int batch_n;

static void r_flush(void)
{
	if (batch_n)
		be->tris(batch_v, batch_n);
	batch_n = 0;
}

static void r_state(int tex, int blend, int depth, int fog, int filter, int clamp, int mode2d)
{
	struct rstate s = {tex, blend, depth, fog, filter, clamp, mode2d};
	r_flush();
	be->state(&s);
}

static void r_tri_raw(const struct dvtx *a, const struct dvtx *b, const struct dvtx *c)
{
	if (batch_n + 3 > MAX_BATCH_V)
		r_flush();
	batch_v[batch_n++] = *a;
	batch_v[batch_n++] = *b;
	batch_v[batch_n++] = *c;
}

static void r_quad_raw(const struct dvtx *a, const struct dvtx *b, const struct dvtx *c, const struct dvtx *d)
{
	r_tri_raw(a, b, c);
	r_tri_raw(a, c, d);
}

static __attribute__((noinline)) struct dvtx v2d(float x, float y, uint32_t c, float s, float t)
{
	struct dvtx v;
	v.x = x; v.y = y; v.oow = 1.0f;
	v.vx = 0.0f; v.vy = 0.0f; v.vz = 1.0f;
	v.r = (float)((c >> 16) & 0xffU);
	v.g = (float)((c >> 8) & 0xffU);
	v.b = (float)(c & 0xffU);
	v.a = (float)((c >> 24) & 0xffU);
	v.s = s; v.t = t;
	return v;
}

static __attribute__((noinline)) void r_rect(float x0, float y0, float x1, float y1, uint32_t c)
{
	struct dvtx a = v2d(x0, y0, c, 0, 0), b = v2d(x1, y0, c, 0, 0);
	struct dvtx d = v2d(x1, y1, c, 0, 0), e = v2d(x0, y1, c, 0, 0);
	r_quad_raw(&a, &b, &d, &e);
}

static __attribute__((noinline)) void r_line2d(float x0, float y0, float x1, float y1, float thick, uint32_t c)
{
	float dx = x1 - x0, dy = y1 - y0;
	float l = m_sqrtf(dx * dx + dy * dy);
	if (l < 0.25f)
		return;
	float nx = -dy / l * (thick * 0.5f), ny = dx / l * (thick * 0.5f);
	struct dvtx a = v2d(x0 + nx, y0 + ny, c, 0, 0), b = v2d(x1 + nx, y1 + ny, c, 0, 0);
	struct dvtx d = v2d(x1 - nx, y1 - ny, c, 0, 0), e = v2d(x0 - nx, y0 - ny, c, 0, 0);
	r_quad_raw(&a, &b, &d, &e);
}

static void r_box_outline(float x0, float y0, float x1, float y1, float thick, uint32_t c)
{
	r_rect(x0, y0, x1, y0 + thick, c);
	r_rect(x0, y1 - thick, x1, y1, c);
	r_rect(x0, y0 + thick, x0 + thick, y1 - thick, c);
	r_rect(x1 - thick, y0 + thick, x1, y1 - thick, c);
}

static void r_text_state(void)
{
	r_state(TEX_FONT, BLEND_ALPHA, 0, 0, 0, 1, 1);
}

static float r_text(float x, float y, float sc, uint32_t c, const char *s)
{
	for (; *s; s++, x += 6.0f * sc) {
		int ch = (unsigned char)*s;
		if (ch >= 'a' && ch <= 'z')
			ch -= 'a' - 'A';
		if (ch == '|')
			ch = '!';
		if (ch < 32 || ch > 95)
			ch = '?';
		if (ch == ' ')
			continue;
		float s0 = (float)(((ch - 32) & 15) * 8) * (1.0f / 128.0f);
		float t0 = (float)(((ch - 32) >> 4) * 8) * (1.0f / 128.0f);
		float s1 = s0 + 5.0f * (1.0f / 128.0f);
		float t1 = t0 + 7.0f * (1.0f / 128.0f);
		struct dvtx a = v2d(x, y, c, s0, t0), b = v2d(x + 5.0f * sc, y, c, s1, t0);
		struct dvtx d = v2d(x + 5.0f * sc, y + 7.0f * sc, c, s1, t1), e = v2d(x, y + 7.0f * sc, c, s0, t1);
		r_quad_raw(&a, &b, &d, &e);
	}
	return x;
}

static float r_text_w(const char *s, float sc)
{
	int n = 0;
	while (s[n])
		n++;
	return (float)n * 6.0f * sc;
}

/* --- 3D camera & 6-plane frustum clipper ------------------------------------------------------ */

struct cam3d {
	v3f pos;
	v3f right, up, fwd;
	v3f light_dir;       /* unit vector FROM object TO star in world space */
	float light_rgb[3];  /* 0..1 */
	float amb_rgb[3];    /* 0..1 */
	/* Dynamic point light (nearest laser bolt or explosion) */
	int dyn_on;
	v3f dyn_pos;
	float dyn_rad;
	float dyn_rgb[3];
};

static struct cam3d cam;

static inline v3f world_to_view(v3f w)
{
	v3f d = v3_sub(w, cam.pos);
	return v3_make(v3_dot(d, cam.right), v3_dot(d, cam.up), v3_dot(d, cam.fwd));
}

static inline v3f dir_to_view(v3f d)
{
	return v3_make(v3_dot(d, cam.right), v3_dot(d, cam.up), v3_dot(d, cam.fwd));
}

/* Project a single 3D world point to 2D screen coordinates; returns 1 if in front of camera */
static int project_point(v3f w, float *sx, float *sy, float *vz_out)
{
	v3f v = world_to_view(w);
	if (vz_out)
		*vz_out = v.z;
	if (v.z < space_view.znear)
		return 0;
	float inv = space_view.f / v.z;
	*sx = space_view.w * 0.5f + v.x * inv;
	*sy = space_view.h * 0.5f - v.y * inv;
	return 1;
}

struct cvtx {
	float vx, vy, vz;
	float r, g, b, a;
	float s, t;
};

static struct cvtx cv_lerp(const struct cvtx *a, const struct cvtx *b, float t)
{
	struct cvtx o;
	o.vx = a->vx + (b->vx - a->vx) * t;
	o.vy = a->vy + (b->vy - a->vy) * t;
	o.vz = a->vz + (b->vz - a->vz) * t;
	o.r  = a->r  + (b->r  - a->r)  * t;
	o.g  = a->g  + (b->g  - a->g)  * t;
	o.b  = a->b  + (b->b  - a->b)  * t;
	o.a  = a->a  + (b->a  - a->a)  * t;
	o.s  = a->s  + (b->s  - a->s)  * t;
	o.t  = a->t  + (b->t  - a->t)  * t;
	return o;
}

static int clip_plane(const struct cvtx *in, int nin, struct cvtx *out, int plane, float kx, float ky)
{
	if (nin < 3)
		return 0;
	int nout = 0;
	for (int i = 0; i < nin; i++) {
		const struct cvtx *cur = &in[i];
		const struct cvtx *prv = &in[(i + nin - 1) % nin];
		float dc = 0.0f, dp = 0.0f;
		switch (plane) {
		case 0: dc = cur->vz - space_view.znear; dp = prv->vz - space_view.znear; break;
		case 1: dc = space_view.zfar - cur->vz;  dp = space_view.zfar - prv->vz;  break;
		case 2: dc = cur->vx + cur->vz * kx;     dp = prv->vx + prv->vz * kx;     break;
		case 3: dc = cur->vz * kx - cur->vx;     dp = prv->vz * kx - prv->vx;     break;
		case 4: dc = cur->vy + cur->vz * ky;     dp = prv->vy + prv->vz * ky;     break;
		case 5: dc = cur->vz * ky - cur->vy;     dp = prv->vz * ky - prv->vy;     break;
		}
		if (dc >= 0.0f) {
			if (dp < 0.0f) {
				float t = dp / (dp - dc);
				out[nout++] = cv_lerp(prv, cur, t);
			}
			out[nout++] = *cur;
		} else if (dp >= 0.0f) {
			float t = dp / (dp - dc);
			out[nout++] = cv_lerp(prv, cur, t);
		}
	}
	return nout;
}

static struct dvtx project_cv(const struct cvtx *c)
{
	struct dvtx d;
	float z = c->vz < space_view.znear ? space_view.znear : c->vz;
	float oow = 1.0f / z;
	d.vx = c->vx; d.vy = c->vy; d.vz = z;
	d.oow = oow;
	d.x = clampf(space_view.w * 0.5f + c->vx * space_view.f * oow, 0.0f, (float)space_view.w);
	d.y = clampf(space_view.h * 0.5f - c->vy * space_view.f * oow, 0.0f, (float)space_view.h);
	d.r = clampf(c->r, 0.0f, 255.0f);
	d.g = clampf(c->g, 0.0f, 255.0f);
	d.b = clampf(c->b, 0.0f, 255.0f);
	d.a = clampf(c->a, 0.0f, 255.0f);
	d.s = c->s;
	d.t = c->t;
	return d;
}

static void r_tri3d(const struct cvtx *a, const struct cvtx *b, const struct cvtx *c)
{
	float kx = (space_view.w * 0.5f) / space_view.f;
	float ky = (space_view.h * 0.5f) / space_view.f;
	/* Fast trivial reject before clipping */
	if (a->vz < space_view.znear && b->vz < space_view.znear && c->vz < space_view.znear)
		return;
	if (a->vz > space_view.zfar && b->vz > space_view.zfar && c->vz > space_view.zfar)
		return;
	if (a->vx < -a->vz * kx && b->vx < -b->vz * kx && c->vx < -c->vz * kx)
		return;
	if (a->vx >  a->vz * kx && b->vx >  b->vz * kx && c->vx >  c->vz * kx)
		return;
	if (a->vy < -a->vz * ky && b->vy < -b->vz * ky && c->vy < -c->vz * ky)
		return;
	if (a->vy >  a->vz * ky && b->vy >  b->vz * ky && c->vy >  c->vz * ky)
		return;

	/* Fast path when completely inside all 6 frustum planes */
	if (a->vz >= space_view.znear && b->vz >= space_view.znear && c->vz >= space_view.znear &&
	    a->vz <= space_view.zfar  && b->vz <= space_view.zfar  && c->vz <= space_view.zfar &&
	    m_fabsf(a->vx) <= a->vz * kx && m_fabsf(b->vx) <= b->vz * kx && m_fabsf(c->vx) <= c->vz * kx &&
	    m_fabsf(a->vy) <= a->vz * ky && m_fabsf(b->vy) <= b->vz * ky && m_fabsf(c->vy) <= c->vz * ky) {
		struct dvtx da = project_cv(a), db = project_cv(b), dc = project_cv(c);
		r_tri_raw(&da, &db, &dc);
		return;
	}

	struct cvtx p0[12], p1[12];
	p0[0] = *a; p0[1] = *b; p0[2] = *c;
	int n = 3;
	n = clip_plane(p0, n, p1, 0, kx, ky);
	n = clip_plane(p1, n, p0, 1, kx, ky);
	n = clip_plane(p0, n, p1, 2, kx, ky);
	n = clip_plane(p1, n, p0, 3, kx, ky);
	n = clip_plane(p0, n, p1, 4, kx, ky);
	n = clip_plane(p1, n, p0, 5, kx, ky);
	if (n < 3)
		return;
	struct dvtx d0 = project_cv(&p0[0]);
	struct dvtx dp = project_cv(&p0[1]);
	for (int k = 2; k < n; k++) {
		struct dvtx dk = project_cv(&p0[k]);
		r_tri_raw(&d0, &dp, &dk);
		dp = dk;
	}
}

static void r_quad3d(const struct cvtx *a, const struct cvtx *b, const struct cvtx *c, const struct cvtx *d)
{
	r_tri3d(a, b, c);
	r_tri3d(a, c, d);
}

/* Camera-facing billboard quad in 3D view space (coronas, particles, engine flares) */
static void r_billboard(v3f wpos, float radius, uint32_t argb_col)
{
	v3f v = world_to_view(wpos);
	if (v.z + radius < space_view.znear || v.z - radius > space_view.zfar)
		return;
	float r = (float)((argb_col >> 16) & 0xffU);
	float g = (float)((argb_col >> 8) & 0xffU);
	float b = (float)(argb_col & 0xffU);
	float a = (float)((argb_col >> 24) & 0xffU);
	struct cvtx q[4] = {
		{v.x - radius, v.y + radius, v.z, r, g, b, a, 0.0f, 0.0f},
		{v.x + radius, v.y + radius, v.z, r, g, b, a, 1.0f, 0.0f},
		{v.x + radius, v.y - radius, v.z, r, g, b, a, 1.0f, 1.0f},
		{v.x - radius, v.y - radius, v.z, r, g, b, a, 0.0f, 1.0f},
	};
	r_quad3d(&q[0], &q[1], &q[2], &q[3]);
}

/* 3D oriented glowing beam / streak quad (laser bolts, engine trails, space dust) */
static void r_beam3d(v3f w0, v3f w1, float half_w, uint32_t argb_col)
{
	v3f v0 = world_to_view(w0), v1 = world_to_view(w1);
	v3f seg = v3_sub(v1, v0);
	v3f mid = v3_scale(v3_add(v0, v1), 0.5f);
	v3f side = v3_norm(v3_cross(seg, mid));
	side = v3_scale(side, half_w);
	float r = (float)((argb_col >> 16) & 0xffU);
	float g = (float)((argb_col >> 8) & 0xffU);
	float b = (float)(argb_col & 0xffU);
	float a = (float)((argb_col >> 24) & 0xffU);
	struct cvtx q[4] = {
		{v0.x - side.x, v0.y - side.y, v0.z - side.z, r, g, b, a, 0.0f, 0.2f},
		{v0.x + side.x, v0.y + side.y, v0.z + side.z, r, g, b, a, 1.0f, 0.2f},
		{v1.x + side.x, v1.y + side.y, v1.z + side.z, r, g, b, a, 1.0f, 0.8f},
		{v1.x - side.x, v1.y - side.y, v1.z - side.z, r, g, b, a, 0.0f, 0.8f},
	};
	r_quad3d(&q[0], &q[1], &q[2], &q[3]);
}

/* Render an indexed 3D mesh with Euler rotation (rx, ry), scale, tint, UV shift, starlight & dynamic light */
static void r_mesh(const struct mesh *m, v3f wpos, float scale, float rx, float ry,
		   const float tint[3], int unlit, int cull, float u_off, float v_off)
{
	v3f vc = world_to_view(wpos);
	float bound = scale * 1.6f;
	if (vc.z + bound < space_view.znear || vc.z - bound > space_view.zfar)
		return;
	float kx = (space_view.w * 0.5f) / space_view.f;
	float ky = (space_view.h * 0.5f) / space_view.f;
	if (m_fabsf(vc.x) - bound > vc.z * kx && vc.z > 0.0f)
		return;
	if (m_fabsf(vc.y) - bound > vc.z * ky && vc.z > 0.0f)
		return;

	float sx = m_sinf(rx), cx = m_cosf(rx), sy = m_sinf(ry), cy = m_cosf(ry);
	/* Transform object-space basis into world space */
	v3f bx = v3_make(cy, sx * sy, -cx * sy);
	v3f by = v3_make(0.0f, cx, sx);
	v3f bz = v3_make(sy, -sx * cy, cx * cy);

	/* Transform vertices once into view space + compute per-vertex lighting */
	static v3f tv[MAX_MESH_V];
	static float vr[MAX_MESH_V], vg[MAX_MESH_V], vb_col[MAX_MESH_V];

	/* Transform star light and dynamic light into object space for super-fast vertex lighting */
	v3f l_obj = v3_make(v3_dot(cam.light_dir, bx), v3_dot(cam.light_dir, by), v3_dot(cam.light_dir, bz));
	int use_dyn = 0;
	v3f dyn_obj = v3_make(0, 0, 0);
	float inv_dyn_r2 = 0.0f;
	if (!unlit && cam.dyn_on) {
		v3f dw = v3_sub(cam.dyn_pos, wpos);
		float dist2 = v3_dot(dw, dw);
		float maxd = cam.dyn_rad + bound;
		if (dist2 < maxd * maxd) {
			use_dyn = 1;
			float invs = 1.0f / scale;
			dyn_obj = v3_make(v3_dot(dw, bx) * invs, v3_dot(dw, by) * invs, v3_dot(dw, bz) * invs);
			inv_dyn_r2 = 1.0f / (cam.dyn_rad * cam.dyn_rad);
		}
	}

	/* View-space axes of object basis */
	v3f vbx = dir_to_view(v3_scale(bx, scale));
	v3f vby = dir_to_view(v3_scale(by, scale));
	v3f vbz = dir_to_view(v3_scale(bz, scale));

	for (int i = 0; i < m->nv; i++) {
		v3f p = m->pos[i];
		tv[i] = v3_make(vc.x + vbx.x * p.x + vby.x * p.y + vbz.x * p.z,
				vc.y + vbx.y * p.x + vby.y * p.y + vbz.y * p.z,
				vc.z + vbx.z * p.x + vby.z * p.y + vbz.z * p.z);
		if (unlit) {
			vr[i] = tint[0] * 255.0f;
			vg[i] = tint[1] * 255.0f;
			vb_col[i] = tint[2] * 255.0f;
		} else {
			v3f n = m->nrm[i];
			float ndl = n.x * l_obj.x + n.y * l_obj.y + n.z * l_obj.z;
			if (ndl < 0.0f)
				ndl = 0.0f;
			/* Subtle rim/fill term on dark side so silhouettes stay readable against black space */
			float lr = cam.amb_rgb[0] + cam.light_rgb[0] * ndl;
			float lg = cam.amb_rgb[1] + cam.light_rgb[1] * ndl;
			float lb = cam.amb_rgb[2] + cam.light_rgb[2] * ndl;
			if (use_dyn) {
				v3f dl = v3_sub(dyn_obj, p);
				float d2 = v3_dot(dl, dl) * scale * scale;
				float att = 1.0f - d2 * inv_dyn_r2;
				if (att > 0.0f) {
					att *= att;
					lr += cam.dyn_rgb[0] * att;
					lg += cam.dyn_rgb[1] * att;
					lb += cam.dyn_rgb[2] * att;
				}
			}
			vr[i] = clampf(lr * tint[0] * 255.0f, 0.0f, 255.0f);
			vg[i] = clampf(lg * tint[1] * 255.0f, 0.0f, 255.0f);
			vb_col[i] = clampf(lb * tint[2] * 255.0f, 0.0f, 255.0f);
		}
	}

	for (int i = 0; i < m->nt; i++) {
		const struct mtri *t = &m->tri[i];
		int ia = t->a, ib = t->b, ic = t->c;
		/* View-space back-face culling: outward winding in view space has cross(b-a, c-a).v < 0
		 * Wait: let's check sign! In left-handed view space (+x right, +y up, +z into screen),
		 * front face (+x, +y, -z towards camera): a=(0,0,5), b=(0,1,5), c=(1,1,5) ->
		 * (b-a)=(0,1,0), (c-a)=(1,1,0), cross=(0,0,-1), dot(cross, a) = -5 < 0!
		 * Let's verify gen_uv_sphere front face at z=-1 (facing camera at z=0? No, camera is at z=0
		 * looking along +z, object is at z=+5, so front of sphere is z=+4, normal=(0,0,-1)).
		 * At th = -pi/2 (z = -1 on unit sphere): dir=(0,0,-1). Increasing r (+y), increasing s (+x)!
		 * Wait: th goes 0 -> pi/2 (+z) -> pi (-x) -> 3pi/2 (-z). At th = 3pi/2, d(cos th)/dth = +sin(3pi/2)?
		 * No: d(cos th)/dth = -sin(3pi/2) = +1 (+x)!
		 * So i0=(0,0), i3=(0,+1), i2=(+1,+1) -> cross(i3-i0, i2-i0) = (0,1,0)x(1,1,0) = (0,0,-1)!
		 * And dot((0,0,-1), (0,0,+4)) = -4 < 0!
		 * Keep slightly generous threshold (< 0) or skip culling on thin/open meshes so nothing ever pops. */
		v3f va = tv[ia], vbv = tv[ib], vcv = tv[ic];
		if (cull) {
			v3f fn = v3_cross(v3_sub(vbv, va), v3_sub(vcv, va));
			if (v3_dot(fn, va) > 0.0f)
				continue;
		}
		struct cvtx ca = {va.x,  va.y,  va.z,  vr[ia], vg[ia], vb_col[ia], 255.0f, t->uv[0][0] + u_off, t->uv[0][1] + v_off};
		struct cvtx cb = {vbv.x, vbv.y, vbv.z, vr[ib], vg[ib], vb_col[ib], 255.0f, t->uv[1][0] + u_off, t->uv[1][1] + v_off};
		struct cvtx cc = {vcv.x, vcv.y, vcv.z, vr[ic], vg[ic], vb_col[ic], 255.0f, t->uv[2][0] + u_off, t->uv[2][1] + v_off};
		r_tri3d(&ca, &cb, &cc);
	}
}

/* Translucent planetary ring (annulus in tilted plane around planet) */
static void r_planet_ring(v3f wpos, float r_in, float r_out, float tilt_x, float tilt_z, uint32_t col)
{
	const int SEG = 28;
	float sx = m_sinf(tilt_x), cx = m_cosf(tilt_x);
	float sz = m_sinf(tilt_z), cz = m_cosf(tilt_z);
	v3f ux = v3_make(cz, sz * cx, sz * sx);
	v3f uz = v3_make(-sz, cz * cx, cz * sx);
	float cr = (float)((col >> 16) & 0xffU);
	float cg = (float)((col >> 8) & 0xffU);
	float cb = (float)(col & 0xffU);
	float ca = (float)((col >> 24) & 0xffU);
	for (int i = 0; i < SEG; i++) {
		float a0 = (float)i / SEG * (float)TAU, a1 = (float)(i + 1) / SEG * (float)TAU;
		v3f d0 = v3_add(v3_scale(ux, m_cosf(a0)), v3_scale(uz, m_sinf(a0)));
		v3f d1 = v3_add(v3_scale(ux, m_cosf(a1)), v3_scale(uz, m_sinf(a1)));
		v3f p0 = world_to_view(v3_add(wpos, v3_scale(d0, r_in)));
		v3f p1 = world_to_view(v3_add(wpos, v3_scale(d0, r_out)));
		v3f p2 = world_to_view(v3_add(wpos, v3_scale(d1, r_out)));
		v3f p3 = world_to_view(v3_add(wpos, v3_scale(d1, r_in)));
		float shade = 0.65f + 0.35f * v3_dot(d0, cam.light_dir);
		struct cvtx q[4] = {
			{p0.x, p0.y, p0.z, cr * shade, cg * shade, cb * shade, ca, (float)i / SEG * 4.0f, 0.0f},
			{p1.x, p1.y, p1.z, cr * shade, cg * shade, cb * shade, ca * 0.7f, (float)i / SEG * 4.0f, 1.0f},
			{p2.x, p2.y, p2.z, cr * shade, cg * shade, cb * shade, ca * 0.7f, (float)(i + 1) / SEG * 4.0f, 1.0f},
			{p3.x, p3.y, p3.z, cr * shade, cg * shade, cb * shade, ca, (float)(i + 1) / SEG * 4.0f, 0.0f},
		};
		r_quad3d(&q[0], &q[1], &q[2], &q[3]);
	}
}

#endif
