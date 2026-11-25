#!/usr/bin/env python3
import fcntl
import math
import os
import random
import shutil
import signal
import struct
import sys
import termios
import time

THEMES = {
    "crimson":   (1.00, 0.08, 0.14),  # классический алый ринкаку (Канеки)
    "centipede": (0.86, 0.06, 0.38),  # тёмно-пурпурный какуджа
    "owl":       (1.00, 0.24, 0.06),  # огненно-багровый
}

RAMP = " .,:;-~=+*x#%@W"
RAMP_LEN = len(RAMP) - 1
LUMA_CHAR = [
    RAMP[max(1, min(RAMP_LEN, int(((i / 255.0) ** 0.85) * RAMP_LEN + 0.5)))]
    for i in range(256)
]

FLOOR_Y = -0.74
CYCLE = 9.0
KAGUNE_SEGS = 12
MAX_PARTS = 900

g_running = True


def _handle_sig(signum, frame):
    global g_running
    g_running = False


def write_all(data: bytes):
    fd = sys.stdout.fileno()
    view = memoryview(data)
    total = len(data)
    sent = 0
    while sent < total:
        try:
            n = os.write(fd, view[sent:])
            if n <= 0:
                break
            sent += n
        except InterruptedError:
            continue
        except BlockingIOError:
            time.sleep(0.001)


def get_term_size():
    try:
        buf = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\x00" * 8)
        rows, cols, xpix, ypix = struct.unpack("HHHH", buf)
        if cols > 0 and rows > 0:
            if xpix > 0 and ypix > 0:
                cw = xpix / cols
                ch = ypix / rows
                if cw > 0.5 and ch > 0.5:
                    aspect = ch / cw
                    aspect = 1.4 if aspect < 1.4 else (2.8 if aspect > 2.8 else aspect)
                    return cols, rows, aspect
            return cols, rows, 2.05
    except OSError:
        pass
    sz = shutil.get_terminal_size((80, 24))
    return sz.columns, sz.lines, 2.05


def clampf(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


def lerpf(a, b, t):
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    t = (x - e0) / (e1 - e0)
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def hashf(s):
    s = (s ^ ((s << 13) & 0xFFFFFFFF)) & 0xFFFFFFFF
    s = (s ^ (s >> 17)) & 0xFFFFFFFF
    s = (s ^ ((s << 5) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return (s & 0x00FFFFFF) / 16777216.0


def rot2d(x, y, ox, oy, ang):
    c = math.cos(ang)
    s = math.sin(ang)
    dx = x - ox
    dy = y - oy
    return ox + dx * c - dy * s, oy + dx * s + dy * c


def build_background(W, H, aspect):
    """Предвычисляет ночной переулок Токио: здания, фонарь, провода, луну, хиганбаны и асфальт."""
    unit = min(H * 0.49, W / (3.35 * aspect))
    if unit < 1.0:
        unit = 1.0
    ux = unit * aspect
    uy = unit
    cx = W * 0.5
    cy = H * 0.5
    inv_ux = 1.0 / ux
    inv_uy = 1.0 / uy

    n = W * H
    bg_r = [0] * n
    bg_g = [0] * n
    bg_b = [0] * n
    moon_pixels = []
    floor_pixels = []

    buildings = [
        (-2.20, -1.52,  0.48, 11, 0),
        (-1.55, -1.04,  0.18, 23, 1),
        (-1.08, -0.58,  0.56, 37, 0),
        (-0.62, -0.10,  0.08, 53, 2),
        (-0.14,  0.34,  0.34, 71, 0),
        ( 0.30,  0.88,  0.12, 89, 0),
        ( 0.84,  1.38,  0.52, 101, 1),
        ( 1.34,  2.20,  0.36, 131, 0),
    ]

    moon_x, moon_y, moon_r = 0.46, 0.54, 0.23
    lamp_x, lamp_top = -1.36, 0.58

    exp = math.exp
    hypot = math.hypot
    sin = math.sin
    cos = math.cos
    floor_rows = max(1, min(6, int(uy * 0.22 + 0.5)))
    floor_sy = int(cy - FLOOR_Y * uy)

    for y in range(H):
        row = y * W
        wy = (cy - (y + 0.5)) * inv_uy

        for x in range(W):
            wx = ((x + 0.5) - cx) * inv_ux
            idx = row + x

            if wy < FLOOR_Y:
                dy = clampf((FLOOR_Y - wy) / 0.28, 0.0, 1.0)
                fade = 1.0 - dy * 0.78
                base = (0.055 + 0.030 * exp(-wx * wx * 0.6)) * fade
                lamp_ref = exp(-((wx - (lamp_x + 0.14)) ** 2) * 3.8) * 0.18 * fade
                r = base * 0.90 + lamp_ref * 0.72
                g = base * 0.95 + lamp_ref * 0.84
                b = base * 1.25 + lamp_ref * 1.05
                bg_r[idx] = int(clampf(r, 0.0, 1.0) * 255)
                bg_g[idx] = int(clampf(g, 0.0, 1.0) * 255)
                bg_b[idx] = int(clampf(b, 0.0, 1.0) * 255)
                if y < floor_sy + floor_rows + 2:
                    floor_pixels.append((idx, wx, dy))
                continue

            hor = clampf(1.0 - (wy - FLOOR_Y) / 1.85, 0.0, 1.0)
            cloud = 0.5 + 0.5 * sin(wx * 2.3 + wy * 1.9) * cos(wx * 1.4 - wy * 3.1)
            r = 0.015 + 0.025 * hor + 0.014 * cloud * hor
            g = 0.018 + 0.028 * hor + 0.016 * cloud * hor
            b = 0.036 + 0.052 * hor + 0.026 * cloud * hor

            md = hypot(wx - moon_x, wy - moon_y)
            if md < moon_r * 2.5:
                halo = (1.0 - md / (moon_r * 2.5)) ** 2.6 * 0.24
                r += halo * 0.62
                g += halo * 0.68
                b += halo * 0.86
                mw = halo * 0.9
                if md <= moon_r:
                    nx = (wx - moon_x) / moon_r
                    ny = (wy - moon_y) / moon_r
                    crater = 0.86 + 0.14 * sin(nx * 5.4 + ny * 3.2) * cos(ny * 6.0 - nx * 2.6)
                    limb = 0.78 + 0.22 * math.sqrt(max(0.0, 1.0 - nx * nx - ny * ny))
                    f = crater * limb
                    r = 0.62 * f
                    g = 0.66 * f
                    b = 0.78 * f
                    mw = 0.95 * f
                moon_pixels.append((idx, mw))

            in_bldg = False
            for bx0, bx1, btop, seed, neon in buildings:
                if bx0 <= wx <= bx1 and wy <= btop:
                    in_bldg = True
                    r, g, b = 0.020, 0.022, 0.035
                    gx = int((wx - bx0) * 18.0)
                    gy = int((btop - wy) * 14.0)
                    fx = ((wx - bx0) * 18.0) - gx
                    fy = ((btop - wy) * 14.0) - gy
                    if gy >= 1 and 0.24 < fx < 0.72 and 0.28 < fy < 0.74:
                        h = hashf(seed * 997 + gx * 131 + gy * 313)
                        if h > 0.83:
                            if h > 0.93:
                                r, g, b = 0.24, 0.32, 0.44
                            else:
                                r, g, b = 0.36, 0.28, 0.16
                    if neon and abs(wx - (bx1 - 0.04)) < 0.022 and btop - 0.34 < wy < btop - 0.08:
                        if neon == 1:
                            r, g, b = 0.42, 0.07, 0.16
                        else:
                            r, g, b = 0.08, 0.30, 0.42
                    break

            if not in_bldg:
                for p_y0, sag in ((0.76, 0.11), (0.64, 0.14)):
                    wire_y = p_y0 - sag * cos(wx * 1.15)
                    if abs(wy - wire_y) < max(0.008, 0.45 * inv_uy):
                        r *= 0.25
                        g *= 0.25
                        b *= 0.30

            if abs(wx - lamp_x) < max(0.015, 0.5 * inv_ux) and wy < lamp_top:
                r, g, b = 0.04, 0.045, 0.06
            if lamp_x <= wx <= lamp_x + 0.16 and abs(wy - lamp_top) < max(0.014, 0.45 * inv_uy):
                r, g, b = 0.06, 0.065, 0.08

            lx_head = lamp_x + 0.15
            ly_head = lamp_top - 0.02
            ld = hypot(wx - lx_head, wy - ly_head)
            if ld < 0.22:
                lg = ((1.0 - ld / 0.22) ** 2.2) * 0.55
                r += lg * 0.72
                g += lg * 0.82
                b += lg * 1.00
            if wy < ly_head:
                drop = ly_head - wy
                cone_w = 0.08 + drop * 0.34
                cdx = abs(wx - (lx_head + drop * 0.08))
                if cdx < cone_w:
                    cf = ((1.0 - cdx / cone_w) ** 1.8) * exp(-drop * 1.35) * 0.16
                    r += cf * 0.65
                    g += cf * 0.78
                    b += cf * 1.00

            bg_r[idx] = int(clampf(r, 0.0, 1.0) * 255)
            bg_g[idx] = int(clampf(g, 0.0, 1.0) * 255)
            bg_b[idx] = int(clampf(b, 0.0, 1.0) * 255)

    # Силуэты красных паучьих лилий (хиганбана) по краям асфальта
    for fx, fh in ((-1.48, 0.19), (-1.40, 0.13), (1.44, 0.17), (1.53, 0.12)):
        steps = max(3, int(fh * uy * 1.5))
        for s in range(steps + 1):
            u = s / steps
            sx = int(cx + (fx + 0.015 * sin(u * 2.5)) * ux)
            sy = int(cy - (FLOOR_Y + u * fh) * uy)
            if 0 <= sx < W and 0 <= sy < H:
                ii = sy * W + sx
                bg_r[ii] = max(bg_r[ii], 18)
                bg_g[ii] = max(bg_g[ii], 36)
                bg_b[ii] = max(bg_b[ii], 26)
        top_x = fx + 0.015 * sin(2.5)
        top_y = FLOOR_Y + fh
        for k in range(7):
            ang = -0.35 + k * 0.62
            for r_step in (0.02, 0.045, 0.07):
                px = top_x + cos(ang) * r_step
                py = top_y + sin(ang) * r_step - r_step * r_step * 2.2
                sx = int(cx + px * ux)
                sy = int(cy - py * uy)
                if 0 <= sx < W and 0 <= sy < H:
                    ii = sy * W + sx
                    bg_r[ii] = min(255, bg_r[ii] + int(175 * (1.0 - r_step * 6.0)))
                    bg_g[ii] = min(255, bg_g[ii] + 10)
                    bg_b[ii] = min(255, bg_b[ii] + 22)

    return {
        "W": W, "H": H, "unit": unit, "aspect": aspect,
        "ux": ux, "uy": uy, "inv_ux": inv_ux, "inv_uy": inv_uy,
        "cx": cx, "cy": cy,
        "bg_r": bg_r, "bg_g": bg_g, "bg_b": bg_b,
        "moon_pixels": moon_pixels,
        "floor_pixels": floor_pixels,
    }


def draw_capsule(
    r_buf, g_buf, b_buf, z_buf, sc,
    ax, ay, bx, by, ra, rb, z_int,
    cr, cg, cb, rim_r, rim_g, rim_b, rim_dx, alpha=1.0
):
    if alpha <= 0.01:
        return
    W, H = sc["W"], sc["H"]
    cx, cy = sc["cx"], sc["cy"]
    ux, uy = sc["ux"], sc["uy"]
    inv_ux, inv_uy = sc["inv_ux"], sc["inv_uy"]

    pix = 1.0 / (uy if uy > 0.5 else 0.5)
    aa = 0.55 * pix
    if aa > 0.030:
        aa = 0.030
    min_r = 0.24 * pix
    if min_r > 0.034:
        min_r = 0.034
    ra_e = ra if ra > min_r else min_r
    rb_e = rb if rb > min_r else min_r
    rmax = (ra_e if ra_e > rb_e else rb_e) + aa + 0.015

    x0 = int(math.floor(cx + ((ax if ax < bx else bx) - rmax) * ux))
    x1 = int(math.ceil(cx + ((ax if ax > bx else bx) + rmax) * ux))
    y0 = int(math.floor(cy - ((ay if ay > by else by) + rmax) * uy))
    y1 = int(math.ceil(cy - ((ay if ay < by else by) - rmax) * uy))
    if x1 < 0 or x0 >= W or y1 < 0 or y0 >= H:
        return
    if x0 < 0: x0 = 0
    if x1 >= W: x1 = W - 1
    if y0 < 0: y0 = 0
    if y1 >= H: y1 = H - 1

    bax = bx - ax
    bay = by - ay
    denom = bax * bax + bay * bay
    inv_denom = 1.0 / denom if denom > 1e-8 else 0.0
    inv_2aa = 1.0 / (2.0 * aa)
    dr_rad = rb_e - ra_e
    sqrt = math.sqrt

    cr255, cg255, cb255 = cr * 255.0, cg * 255.0, cb * 255.0
    rr255, rg255, rb255 = rim_r * 255.0, rim_g * 255.0, rim_b * 255.0

    for y in range(y0, y1 + 1):
        row = y * W
        pay = (cy - (y + 0.5)) * inv_uy - ay
        for x in range(x0, x1 + 1):
            pax = ((x + 0.5) - cx) * inv_ux - ax
            h = (pax * bax + pay * bay) * inv_denom
            if h < 0.0:
                h = 0.0
            elif h > 1.0:
                h = 1.0
            dx = pax - bax * h
            dy = pay - bay * h
            rad = ra_e + dr_rad * h
            rad_aa = rad + aa
            d2 = dx * dx + dy * dy
            if d2 > rad_aa * rad_aa:
                continue

            idx = row + x
            if z_int < z_buf[idx]:
                continue

            d = sqrt(d2)
            cov = (rad_aa - d) * inv_2aa
            if cov > 1.0:
                cov = 1.0
            cov *= alpha
            if cov <= 0.02:
                continue

            inv_rad = 1.0 / (rad if rad > 1e-4 else 1e-4)
            nx = dx * inv_rad
            ny = dy * inv_rad
            n2 = nx * nx + ny * ny
            nz = sqrt(1.0 - n2) if n2 < 1.0 else 0.0

            shade = 0.44 + 0.56 * nz
            rv = nx * rim_dx + 0.25 * ny + 0.15
            rim = (rv * rv * (1.0 - nz * 0.65)) if rv > 0.0 else 0.0

            pr = cr255 * shade + rr255 * rim
            pg = cg255 * shade + rg255 * rim
            pb = cb255 * shade + rb255 * rim

            if cov >= 0.96:
                r_buf[idx] = int(pr)
                g_buf[idx] = int(pg)
                b_buf[idx] = int(pb)
                z_buf[idx] = z_int
            else:
                ic = 1.0 - cov
                r_buf[idx] = int(r_buf[idx] * ic + pr * cov)
                g_buf[idx] = int(g_buf[idx] * ic + pg * cov)
                b_buf[idx] = int(b_buf[idx] * ic + pb * cov)
                if cov > 0.45:
                    z_buf[idx] = z_int


def draw_glow(r_buf, g_buf, b_buf, sc, wx0, wy0, rad_x, rad_y, gr, gg, gb, power):
    if gr + gg + gb <= 0.005 or rad_x <= 1e-4 or rad_y <= 1e-4:
        return
    W, H = sc["W"], sc["H"]
    cx, cy = sc["cx"], sc["cy"]
    ux, uy = sc["ux"], sc["uy"]
    inv_ux, inv_uy = sc["inv_ux"], sc["inv_uy"]

    x0 = int(math.floor(cx + (wx0 - rad_x) * ux))
    x1 = int(math.ceil(cx + (wx0 + rad_x) * ux))
    y0 = int(math.floor(cy - (wy0 + rad_y) * uy))
    y1 = int(math.ceil(cy - (wy0 - rad_y) * uy))
    if x1 < 0 or x0 >= W or y1 < 0 or y0 >= H:
        return
    if x0 < 0: x0 = 0
    if x1 >= W: x1 = W - 1
    if y0 < 0: y0 = 0
    if y1 >= H: y1 = H - 1

    inv_rx = 1.0 / rad_x
    inv_ry = 1.0 / rad_y
    gr255, gg255, gb255 = gr * 255.0, gg * 255.0, gb * 255.0
    sqrt = math.sqrt

    for y in range(y0, y1 + 1):
        row = y * W
        dy = ((cy - (y + 0.5)) * inv_uy - wy0) * inv_ry
        dy2 = dy * dy
        for x in range(x0, x1 + 1):
            dx = (((x + 0.5) - cx) * inv_ux - wx0) * inv_rx
            r2 = dx * dx + dy2
            if r2 >= 1.0:
                continue
            f = (1.0 - sqrt(r2)) ** power
            idx = row + x
            r_buf[idx] += int(gr255 * f)
            g_buf[idx] += int(gg255 * f)
            b_buf[idx] += int(gb255 * f)


def draw_ring(r_buf, g_buf, b_buf, sc, ox, oy, rad, width, cr, cg, cb, alpha):
    if alpha <= 0.01 or rad <= 0.005:
        return
    W, H = sc["W"], sc["H"]
    cx, cy = sc["cx"], sc["cy"]
    ux, uy = sc["ux"], sc["uy"]
    inv_ux, inv_uy = sc["inv_ux"], sc["inv_uy"]

    outer = rad + width * 2.0
    x0 = max(0, int(math.floor(cx + (ox - outer) * ux)))
    x1 = min(W - 1, int(math.ceil(cx + (ox + outer) * ux)))
    y0 = max(0, int(math.floor(cy - (oy + outer) * uy)))
    y1 = min(H - 1, int(math.ceil(cy - (oy - outer) * uy)))
    if x0 > x1 or y0 > y1:
        return

    inv_w = 1.0 / max(width, 0.01)
    cr255, cg255, cb255 = cr * 255.0 * alpha, cg * 255.0 * alpha, cb * 255.0 * alpha
    sqrt = math.sqrt
    exp = math.exp

    for y in range(y0, y1 + 1):
        row = y * W
        dy = (cy - (y + 0.5)) * inv_uy - oy
        dy2 = dy * dy
        for x in range(x0, x1 + 1):
            dx = ((x + 0.5) - cx) * inv_ux - ox
            d = sqrt(dx * dx + dy2)
            diff = abs(d - rad) * inv_w
            if diff >= 1.8:
                continue
            f = exp(-diff * diff * 2.4)
            idx = row + x
            r_buf[idx] += int(cr255 * f)
            g_buf[idx] += int(cg255 * f)
            b_buf[idx] += int(cb255 * f)


def draw_rc_lightning(r_buf, g_buf, b_buf, sc, x0, y0, x1, y1, tr, tg, tb, intensity, seed):
    if intensity <= 0.02:
        return
    W, H = sc["W"], sc["H"]
    cx, cy = sc["cx"], sc["cy"]
    ux, uy = sc["ux"], sc["uy"]
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-4:
        return
    nx, ny = -dy / length, dx / length

    segs = 8
    pts = []
    for i in range(segs + 1):
        u = i / segs
        off = 0.0 if (i == 0 or i == segs) else (hashf(seed + i * 7919) * 2.0 - 1.0) * 0.11 * math.sin(u * math.pi)
        pts.append((x0 + dx * u + nx * off, y0 + dy * u + ny * off))

    cr = int((180 + 75 * tr) * intensity)
    cg = int((85 + 110 * tg) * intensity)
    cb = int((95 + 110 * tb) * intensity)
    gr = int(120 * tr * intensity)
    gg = int(90 * tg * intensity)
    gb = int(100 * tb * intensity)

    for i in range(segs):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        sx0, sy0 = cx + ax * ux, cy - ay * uy
        sx1, sy1 = cx + bx * ux, cy - by * uy
        steps = max(2, int(max(abs(sx1 - sx0), abs(sy1 - sy0)) * 1.3))
        for s in range(steps + 1):
            f = s / steps
            ix = int(sx0 + (sx1 - sx0) * f)
            iy = int(sy0 + (sy1 - sy0) * f)
            if 0 <= ix < W and 0 <= iy < H:
                idx = iy * W + ix
                r_buf[idx] += cr
                g_buf[idx] += cg
                b_buf[idx] += cb
                if ix + 1 < W:
                    r_buf[idx + 1] += gr
                    g_buf[idx + 1] += gg
                    b_buf[idx + 1] += gb


def draw_kagune_tendril(
    r_buf, g_buf, b_buf, z_buf, sc,
    x0, y0, x1, y1, x2, y2, x3, y3,
    grow_u, thick, phase, ct, z_int, theme
):
    if grow_u <= 0.02:
        return
    tr, tg, tb = theme
    W, H = sc["W"], sc["H"]
    cx, cy = sc["cx"], sc["cy"]
    ux, uy = sc["ux"], sc["uy"]
    inv_ux, inv_uy = sc["inv_ux"], sc["inv_uy"]

    sin = math.sin
    sqrt = math.sqrt
    pi = math.pi

    px = [0.0] * (KAGUNE_SEGS + 1)
    py = [0.0] * (KAGUNE_SEGS + 1)
    for i in range(KAGUNE_SEGS + 1):
        u = (i / KAGUNE_SEGS) * grow_u
        iu = 1.0 - u
        iu2 = iu * iu
        u2 = u * u
        bx = iu2 * iu * x0 + 3.0 * iu2 * u * x1 + 3.0 * iu * u2 * x2 + u2 * u * x3
        by = iu2 * iu * y0 + 3.0 * iu2 * u * y1 + 3.0 * iu * u2 * y2 + u2 * u * y3
        wig = 0.045 * sin(u * pi) * sin(u * 10.0 - ct * 6.8 + phase)
        px[i] = bx
        py[i] = by + wig

    pix = 1.0 / (uy if uy > 0.5 else 0.5)
    aa = min(0.55 * pix, 0.030)
    min_r = min(0.24 * pix, 0.034)
    inv_2aa = 1.0 / (2.0 * aa)

    for i in range(KAGUNE_SEGS):
        ua = (i / KAGUNE_SEGS) * grow_u
        ub = ((i + 1) / KAGUNE_SEGS) * grow_u
        prof_a = (0.48 + 0.65 * sin((ua ** 0.7) * pi)) * (1.0 - 0.85 * (ua ** 3))
        prof_b = (0.48 + 0.65 * sin((ub ** 0.7) * pi)) * (1.0 - 0.85 * (ub ** 3))
        ra = max(min_r, thick * prof_a)
        rb = max(min_r * 0.85, thick * prof_b)

        ax, ay = px[i], py[i]
        bx, by = px[i + 1], py[i + 1]
        rmax = ra if ra > rb else rb
        aura_r = rmax * 2.15 + 0.025

        ix0 = int(math.floor(cx + ((ax if ax < bx else bx) - aura_r) * ux))
        ix1 = int(math.ceil(cx + ((ax if ax > bx else bx) + aura_r) * ux))
        iy0 = int(math.floor(cy - ((ay if ay > by else by) + aura_r) * uy))
        iy1 = int(math.ceil(cy - ((ay if ay < by else by) - aura_r) * uy))
        if ix1 < 0 or ix0 >= W or iy1 < 0 or iy0 >= H:
            continue
        if ix0 < 0: ix0 = 0
        if ix1 >= W: ix1 = W - 1
        if iy0 < 0: iy0 = 0
        if iy1 >= H: iy1 = H - 1

        bax = bx - ax
        bay = by - ay
        denom = bax * bax + bay * bay
        inv_denom = 1.0 / denom if denom > 1e-8 else 0.0
        dr_rad = rb - ra
        du_seg = ub - ua

        for y in range(iy0, iy1 + 1):
            row = y * W
            pay = (cy - (y + 0.5)) * inv_uy - ay
            for x in range(ix0, ix1 + 1):
                pax = ((x + 0.5) - cx) * inv_ux - ax
                h = (pax * bax + pay * bay) * inv_denom
                if h < 0.0:
                    h = 0.0
                elif h > 1.0:
                    h = 1.0
                dx = pax - bax * h
                dy = pay - bay * h
                rad = ra + dr_rad * h
                a_lim = rad * 2.15 + 0.025
                d2 = dx * dx + dy * dy
                if d2 >= a_lim * a_lim:
                    continue

                d = sqrt(d2)
                idx = row + x

                if d > rad * 0.55:
                    af = 1.0 - (d - rad * 0.55) / (rad * 1.60 + 0.025)
                    if af > 0.0:
                        af2 = af * af * 56.0
                        r_buf[idx] += int(tr * af2)
                        g_buf[idx] += int(tg * af2 * 0.5)
                        b_buf[idx] += int(tb * af2 * 0.7)

                rad_aa = rad + aa
                if d > rad_aa or z_int < z_buf[idx]:
                    continue

                cov = (rad_aa - d) * inv_2aa
                if cov > 1.0:
                    cov = 1.0
                norm_d = d / (rad if rad > 1e-4 else 1e-4)
                if norm_d > 1.0:
                    norm_d = 1.0
                core = 1.0 - norm_d * norm_d
                u_here = ua + du_seg * h

                pulse = 0.5 + 0.5 * sin(u_here * 18.0 - ct * 11.5 + phase)
                scales = 0.72 + 0.28 * sin(u_here * 40.0 + norm_d * 5.0)
                tip_glow = smoothstep(0.74, 1.0, u_here)

                kr = ((0.32 + 0.78 * core + 0.24 * pulse * core) * scales * tr + 0.42 * tip_glow * core) * 255.0
                kg = ((0.02 + 0.22 * core * core + 0.16 * pulse * core * core * core) * (0.5 + tg) + 0.22 * tip_glow * core) * 255.0
                kb = ((0.04 + 0.16 * core + 0.12 * (1.0 - core)) * (0.5 + tb) + 0.10 * tip_glow * core) * 255.0

                if cov >= 0.95:
                    r_buf[idx] = int(kr)
                    g_buf[idx] = int(kg)
                    b_buf[idx] = int(kb)
                    z_buf[idx] = z_int
                else:
                    ic = 1.0 - cov
                    r_buf[idx] = int(r_buf[idx] * ic + kr * cov)
                    g_buf[idx] = int(g_buf[idx] * ic + kg * cov)
                    b_buf[idx] = int(b_buf[idx] * ic + kb * cov)
                    if cov > 0.5:
                        z_buf[idx] = z_int


def draw_ghoul(r_buf, g_buf, b_buf, z_buf, sc, gx, ct, kagune_glow, kakugan_v, theme):
    tr, tg, tb = theme
    lunge = smoothstep(2.98, 3.36, ct) * (1.0 - smoothstep(5.35, 6.25, ct))
    breath = 0.012 * math.sin(ct * 2.4)
    lean = 0.08 + 0.14 * lunge

    hip_x = gx + 0.04 * lunge
    hip_y = FLOOR_Y + 0.44 + breath * 0.5
    sh_x = hip_x + lean
    sh_y = hip_y + 0.34 + breath
    head_x = sh_x + 0.04 + 0.03 * lunge
    head_y = sh_y + 0.14

    back_x = hip_x - 0.05
    back_y = hip_y + 0.08

    rr = 0.92 * tr * kagune_glow + 0.14
    rg = 0.10 * kagune_glow + 0.18
    rb = 0.14 * kagune_glow + 0.28

    wind = math.sin(ct * 4.2) * 0.05 + 0.09 * kagune_glow

    # Многослойный развевающийся плащ
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, sh_x - 0.05, sh_y - 0.02, hip_x - 0.21 - wind, FLOOR_Y + 0.14,
                 0.068, 0.098, 150, 0.07, 0.07, 0.10, rr, rg, rb, -1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hip_x - 0.02, hip_y + 0.04, hip_x - 0.15 - wind * 1.45, FLOOR_Y + 0.07,
                 0.060, 0.088, 155, 0.055, 0.055, 0.085, rr, rg, rb, -1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hip_x + 0.04, hip_y + 0.02, hip_x - 0.04 - wind * 0.9, FLOOR_Y + 0.11,
                 0.048, 0.068, 160, 0.065, 0.065, 0.095, rr, rg, rb, 1.0)

    # Ноги
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hip_x - 0.04, hip_y, gx - 0.13, FLOOR_Y + 0.22,
                 0.055, 0.045, 170, 0.09, 0.09, 0.12, rr, rg, rb, 1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, gx - 0.13, FLOOR_Y + 0.22, gx - 0.17, FLOOR_Y + 0.01,
                 0.044, 0.036, 170, 0.08, 0.08, 0.11, rr, rg, rb, 1.0)

    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hip_x + 0.04, hip_y, gx + 0.14 + 0.05 * lunge, FLOOR_Y + 0.22,
                 0.056, 0.046, 190, 0.11, 0.11, 0.14, rr, rg, rb, 1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, gx + 0.14 + 0.05 * lunge, FLOOR_Y + 0.22, gx + 0.12 + 0.06 * lunge, FLOOR_Y + 0.01,
                 0.045, 0.036, 190, 0.10, 0.10, 0.13, rr, rg, rb, 1.0)

    # Торс и высокий воротник
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hip_x, hip_y + 0.02, sh_x, sh_y + 0.02,
                 0.078, 0.096, 200, 0.10, 0.10, 0.13, rr, rg, rb, 1.0)

    # Руки
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, sh_x - 0.03, sh_y - 0.03, sh_x - 0.14, hip_y + 0.06,
                 0.040, 0.034, 165, 0.09, 0.09, 0.12, rr, rg, rb, -1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, sh_x + 0.04, sh_y - 0.03, sh_x + 0.13 + 0.06 * lunge, hip_y + 0.07,
                 0.042, 0.035, 220, 0.12, 0.12, 0.15, rr, rg, rb, 1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, sh_x + 0.13 + 0.06 * lunge, hip_y + 0.07,
                 sh_x + 0.20 + 0.10 * lunge, hip_y - 0.03 + 0.08 * lunge,
                 0.034, 0.028, 220, 0.12, 0.12, 0.15, rr, rg, rb, 1.0)

    # Шея, голова и маска Канеки с бликом молнии
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, sh_x, sh_y, head_x - 0.01, head_y - 0.06,
                 0.038, 0.034, 205, 0.14, 0.13, 0.15, rr, rg, rb, 1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, head_x, head_y - 0.01, head_x + 0.01, head_y + 0.02,
                 0.088, 0.086, 210, 0.17, 0.16, 0.19, rr * 0.7, rg, rb, 1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, head_x + 0.01, head_y - 0.045, head_x + 0.072, head_y - 0.035,
                 0.042, 0.034, 218, 0.045, 0.045, 0.06, rr * 0.6, rg * 0.5, rb * 0.5, 1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, head_x + 0.025, head_y - 0.046, head_x + 0.075, head_y - 0.042,
                 0.010, 0.010, 222, 0.55, 0.56, 0.62, rr * 0.5, rg, rb, 1.0)

    # Белые взъерошенные волосы
    hw = 0.018 * math.sin(ct * 4.8) + 0.02 * kagune_glow
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, head_x - 0.05, head_y + 0.05, head_x + 0.06, head_y + 0.09,
                 0.055, 0.048, 230, 0.76, 0.78, 0.85, rr * 0.9, rg, rb, 1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, head_x - 0.04, head_y + 0.07, head_x - 0.16 - hw, head_y + 0.02,
                 0.042, 0.014, 235, 0.70, 0.72, 0.80, rr, rg, rb, -1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, head_x - 0.02, head_y + 0.09, head_x - 0.13 - hw, head_y + 0.14,
                 0.035, 0.011, 235, 0.82, 0.84, 0.90, rr, rg, rb, -1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, head_x + 0.02, head_y + 0.09, head_x + 0.12 + hw * 0.5, head_y + 0.06,
                 0.032, 0.011, 235, 0.82, 0.84, 0.90, rr, rg, rb, 1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, head_x + 0.04, head_y + 0.07, head_x + 0.10, head_y + 0.005,
                 0.024, 0.009, 235, 0.72, 0.74, 0.82, rr, rg, rb, 1.0)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, head_x - 0.07, head_y + 0.03, head_x - 0.15 - hw * 1.1, head_y - 0.04,
                 0.028, 0.010, 232, 0.66, 0.68, 0.76, rr, rg, rb, -1.0)

    # Какуган с крестообразным бликом
    eye_x = head_x + 0.056
    eye_y = head_y + 0.008
    if kakugan_v > 0.02:
        draw_glow(r_buf, g_buf, b_buf, sc, eye_x, eye_y, 0.12 * kakugan_v, 0.075 * kakugan_v,
                  0.95 * tr * kakugan_v, 0.06 * kakugan_v, 0.10 * kakugan_v, 2.0)
        draw_glow(r_buf, g_buf, b_buf, sc, eye_x + 0.02, eye_y, 0.34 * kakugan_v, 0.022,
                  1.20 * tr * kakugan_v, 0.22 * kakugan_v, 0.22 * kakugan_v, 2.3)
        draw_glow(r_buf, g_buf, b_buf, sc, eye_x, eye_y, 0.022, 0.12 * kakugan_v,
                  1.05 * tr * kakugan_v, 0.18 * kakugan_v, 0.18 * kakugan_v, 2.2)
        draw_glow(r_buf, g_buf, b_buf, sc, eye_x, eye_y, 0.028, 0.022,
                  1.55 * kakugan_v, 0.50 * kakugan_v, 0.50 * kakugan_v, 1.5)

    return back_x, back_y, eye_x, eye_y


def make_random_victim(cycle_idx):
    r = random.Random(1337 + (cycle_idx + 1) * 7919)
    palettes = [
        (0.22, 0.27, 0.36),  # тёмно-синий плащ
        (0.22, 0.30, 0.25),  # оливковая куртка
        (0.32, 0.25, 0.22),  # коричневое пальто
        (0.28, 0.25, 0.33),  # графитово-фиолетовый
        (0.30, 0.30, 0.32),  # серый костюм
    ]
    cr, cg, cb = r.choice(palettes)
    return {
        "hs": r.uniform(0.92, 1.08),
        "ws": r.uniform(0.90, 1.12),
        "hair": r.randint(0, 3),        # 0=короткие, 1=взъерошенные, 2=капюшон, 3=длинные
        "umbrella": r.random() < 0.65,  # зонт, который вылетает при ударе
        "cr": cr, "cg": cg, "cb": cb,
    }


def draw_victim(r_buf, g_buf, b_buf, z_buf, sc, vs, ct, kagune_glow, theme):
    tr, tg, tb = theme
    fade_in = smoothstep(0.0, 0.65, ct)
    fade_out = 1.0 - smoothstep(7.55, 8.65, ct)
    alpha = fade_in * fade_out
    if alpha <= 0.01:
        return 0.72, FLOOR_Y + 0.62

    hs, ws = vs["hs"], vs["ws"]
    walk_in = smoothstep(0.0, 0.95, ct)
    step_bak = smoothstep(1.85, 3.05, ct)
    impaled = smoothstep(3.32, 3.55, ct) * (1.0 - smoothstep(5.30, 5.70, ct))
    collapse = smoothstep(5.35, 6.15, ct)
    panic = smoothstep(1.75, 3.12, ct) * (1.0 - smoothstep(3.35, 3.60, ct))

    vx = lerpf(1.44, 0.66, walk_in) + 0.14 * step_bak + 0.13 * impaled + 0.08 * collapse
    lift = 0.23 * impaled
    pivot_x = vx
    pivot_y = FLOOR_Y + 0.05 + lift

    body_rot = -0.10 * step_bak - 0.25 * impaled - 1.48 * collapse * collapse
    twitch = 0.024 * math.sin(ct * 34.0) * impaled if (impaled > 0.2 and ct < 4.9) else 0.0
    walk_swing = (1.0 - walk_in) * math.sin(ct * 11.0) * 0.11

    hip_lx, hip_ly = vx, FLOOR_Y + 0.44 * hs + lift
    sh_lx, sh_ly = vx + 0.02 * step_bak + twitch, hip_ly + 0.33 * hs
    hd_lx, hd_ly = sh_lx + 0.02 + 0.05 * impaled, sh_ly + 0.14 * hs

    arm_raise = panic * 0.22
    limp = clampf(impaled + collapse, 0.0, 1.0)
    hold_u = (1.0 - smoothstep(2.85, 3.30, ct)) if vs["umbrella"] else 0.0

    el1_x = sh_lx - 0.10 - 0.06 * panic + 0.05 * limp
    el1_y = sh_ly - 0.14 + arm_raise + 0.06 * hold_u - 0.04 * limp
    hn1_x = el1_x - 0.08 - 0.05 * panic + 0.06 * limp + 0.08 * hold_u
    hn1_y = el1_y - 0.08 + arm_raise * 0.9 + 0.14 * hold_u - 0.08 * limp

    el2_x = sh_lx + 0.07
    el2_y = sh_ly - 0.15 + arm_raise * 0.6
    hn2_x = el2_x - 0.04 * panic + 0.05 * limp
    hn2_y = el2_y - 0.12 + arm_raise * 0.8

    kn1_x, kn1_y = vx - 0.06 + walk_swing - 0.04 * impaled, FLOOR_Y + 0.22 * hs + lift - 0.04 * impaled
    ft1_x, ft1_y = vx - 0.09 + walk_swing * 1.4 - 0.06 * impaled, FLOOR_Y + 0.01 + lift - 0.08 * impaled
    kn2_x, kn2_y = vx + 0.07 - walk_swing + 0.03 * impaled, FLOOR_Y + 0.22 * hs + lift - 0.02 * impaled
    ft2_x, ft2_y = vx + 0.10 - walk_swing * 1.4 + 0.02 * impaled, FLOOR_Y + 0.01 + lift - 0.06 * impaled

    hip_x, hip_y = rot2d(hip_lx, hip_ly, pivot_x, pivot_y, body_rot)
    sh_x, sh_y = rot2d(sh_lx, sh_ly, pivot_x, pivot_y, body_rot)
    hd_x, hd_y = rot2d(hd_lx, hd_ly, pivot_x, pivot_y, body_rot)
    e1x, e1y = rot2d(el1_x, el1_y, pivot_x, pivot_y, body_rot)
    h1x, h1y = rot2d(hn1_x, hn1_y, pivot_x, pivot_y, body_rot)
    e2x, e2y = rot2d(el2_x, el2_y, pivot_x, pivot_y, body_rot)
    h2x, h2y = rot2d(hn2_x, hn2_y, pivot_x, pivot_y, body_rot)
    k1x, k1y = rot2d(kn1_x, kn1_y, pivot_x, pivot_y, body_rot)
    f1x, f1y = rot2d(ft1_x, ft1_y, pivot_x, pivot_y, body_rot)
    k2x, k2y = rot2d(kn2_x, kn2_y, pivot_x, pivot_y, body_rot)
    f2x, f2y = rot2d(ft2_x, ft2_y, pivot_x, pivot_y, body_rot)

    if hip_y < FLOOR_Y + 0.05: hip_y = FLOOR_Y + 0.05
    if sh_y < FLOOR_Y + 0.06: sh_y = FLOOR_Y + 0.06
    if hd_y < FLOOR_Y + 0.07: hd_y = FLOOR_Y + 0.07
    if e1y < FLOOR_Y + 0.03: e1y = FLOOR_Y + 0.03
    if h1y < FLOOR_Y + 0.02: h1y = FLOOR_Y + 0.02
    if e2y < FLOOR_Y + 0.03: e2y = FLOOR_Y + 0.03
    if h2y < FLOOR_Y + 0.02: h2y = FLOOR_Y + 0.02

    chest_x = lerpf(hip_x, sh_x, 0.62)
    chest_y = lerpf(hip_y, sh_y, 0.62)

    rr = 1.00 * tr * kagune_glow + 0.08
    rg = 0.10 * kagune_glow + 0.10
    rb = 0.14 * kagune_glow + 0.14
    r, g, b = vs["cr"], vs["cg"], vs["cb"]

    # Зонт (вылетает из рук и вращается в воздухе при ударе)
    if vs["umbrella"]:
        if ct < 3.15:
            ux_b, uy_b = h1x, h1y
            u_ang = -0.10 - 0.30 * panic
        else:
            ut = ct - 3.15
            ux_b = h1x + 0.12 + 0.52 * min(ut, 1.35)
            uy_b = h1y + 0.72 * ut - 1.55 * ut * ut
            if uy_b < FLOOR_Y + 0.05:
                uy_b = FLOOR_Y + 0.05
                u_ang = -1.48
            else:
                u_ang = -0.40 - ut * 3.8
        top_x, top_y = rot2d(ux_b, uy_b + 0.44, ux_b, uy_b, u_ang)
        c_lx, c_ly = rot2d(ux_b - 0.25, uy_b + 0.34, ux_b, uy_b, u_ang)
        c_rx, c_ry = rot2d(ux_b + 0.25, uy_b + 0.34, ux_b, uy_b, u_ang)
        draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, ux_b, uy_b, top_x, top_y,
                     0.011, 0.011, 185, 0.32, 0.32, 0.36, rr, rg, rb, -1.0, alpha)
        draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, c_lx, c_ly, top_x, top_y,
                     0.016, 0.022, 226, 0.10, 0.11, 0.16, rr * 1.1, rg, rb, -1.0, alpha)
        draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, top_x, top_y, c_rx, c_ry,
                     0.022, 0.016, 226, 0.10, 0.11, 0.16, rr * 1.1, rg, rb, -1.0, alpha)

    # Задние конечности
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hip_x, hip_y, k2x, k2y, 0.050 * ws, 0.042 * ws, 170, r * 0.7, g * 0.7, b * 0.7, rr, rg, rb, -1.0, alpha)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, k2x, k2y, f2x, f2y, 0.041 * ws, 0.034 * ws, 170, r * 0.65, g * 0.65, b * 0.65, rr, rg, rb, -1.0, alpha)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, sh_x, sh_y, e2x, e2y, 0.038 * ws, 0.032 * ws, 175, r * 0.8, g * 0.8, b * 0.8, rr, rg, rb, -1.0, alpha)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, e2x, e2y, h2x, h2y, 0.031 * ws, 0.025 * ws, 175, r * 0.8, g * 0.8, b * 0.8, rr, rg, rb, -1.0, alpha)

    # Передняя нога и торс
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hip_x, hip_y, k1x, k1y, 0.052 * ws, 0.044 * ws, 190, r * 0.85, g * 0.85, b * 0.85, rr, rg, rb, -1.0, alpha)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, k1x, k1y, f1x, f1y, 0.042 * ws, 0.034 * ws, 190, r * 0.8, g * 0.8, b * 0.8, rr, rg, rb, -1.0, alpha)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hip_x, hip_y, sh_x, sh_y, 0.076 * ws, 0.090 * ws, 200, r, g, b, rr, rg, rb, -1.0, alpha)

    # Голова и причёска
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hd_x, hd_y - 0.01, hd_x, hd_y + 0.02, 0.082, 0.080, 205, 0.26, 0.24, 0.25, rr, rg, rb, -1.0, alpha)
    hair = vs["hair"]
    if hair == 0:
        draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hd_x - 0.03, hd_y + 0.05, hd_x + 0.05, hd_y + 0.06, 0.048, 0.046, 215, 0.13, 0.12, 0.15, rr, rg, rb, -1.0, alpha)
    elif hair == 1:
        draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hd_x - 0.05, hd_y + 0.06, hd_x + 0.08, hd_y + 0.09, 0.050, 0.030, 215, 0.17, 0.14, 0.13, rr, rg, rb, -1.0, alpha)
        draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hd_x + 0.02, hd_y + 0.08, hd_x + 0.11, hd_y + 0.12, 0.028, 0.012, 215, 0.17, 0.14, 0.13, rr, rg, rb, -1.0, alpha)
    elif hair == 2:
        draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hd_x - 0.02, hd_y + 0.03, hd_x + 0.06, hd_y + 0.07, 0.070, 0.062, 215, r * 0.9, g * 0.9, b * 0.9, rr, rg, rb, -1.0, alpha)
    else:
        draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hd_x - 0.03, hd_y + 0.05, hd_x + 0.07, hd_y + 0.06, 0.050, 0.045, 215, 0.15, 0.11, 0.14, rr, rg, rb, -1.0, alpha)
        draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, hd_x + 0.05, hd_y + 0.04, hd_x + 0.12, hd_y - 0.11, 0.035, 0.022, 214, 0.15, 0.11, 0.14, rr, rg, rb, -1.0, alpha)

    # Передняя рука
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, sh_x, sh_y, e1x, e1y, 0.039 * ws, 0.033 * ws, 215, r * 1.05, g * 1.05, b * 1.05, rr, rg, rb, -1.0, alpha)
    draw_capsule(r_buf, g_buf, b_buf, z_buf, sc, e1x, e1y, h1x, h1y, 0.032 * ws, 0.026 * ws, 215, 0.26, 0.24, 0.25, rr, rg, rb, -1.0, alpha)

    return chest_x, chest_y


def spawn_blood(parts, rng, ox, oy, count, power, dir_x):
    for _ in range(count):
        if len(parts) >= MAX_PARTS:
            return
        kind = 1 if rng.random() < 0.16 else 0  # 0=кровь, 1=RC-туман
        ang = (rng.random() - 0.42) * 1.15 if rng.random() < 0.74 else rng.uniform(0.0, 6.283)
        spd = power * (0.35 + 1.35 * (rng.random() ** 0.7))
        vx = math.cos(ang) * spd * dir_x + dir_x * 0.45 * power
        vy = math.sin(ang) * spd + 0.35 * power * rng.random()
        ml = rng.uniform(0.45, 1.0) if kind == 1 else rng.uniform(2.8, 4.8)
        parts.append([
            ox + (rng.random() - 0.5) * 0.09,
            oy + (rng.random() - 0.5) * 0.14,
            vx, vy, ml, ml, rng.uniform(0.55, 1.0), 0, kind
        ])


def encode_frame(r_buf, g_buf, b_buf, W, H, shake_x, shake_y, color_cache):
    luma_char = LUMA_CHAR
    cc_get = color_cache.get
    out_parts = ["\033[?2026h"]
    append = out_parts.append
    last_key = -1

    for y in range(H):
        append(f"\033[{y + 1};1H")
        sy = y + shake_y
        if sy < 0:
            sy = 0
        elif sy >= H:
            sy = H - 1
        row = sy * W
        for x in range(W):
            sx = x + shake_x
            if sx < 0:
                sx = 0
            elif sx >= W:
                sx = W - 1
            idx = row + sx
            r = r_buf[idx]
            g = g_buf[idx]
            b = b_buf[idx]
            if r > 255: r = 255
            elif r < 0: r = 0
            if g > 255: g = 255
            elif g < 0: g = 0
            if b > 255: b = 255
            elif b < 0: b = 0

            mx = r if (r >= g and r >= b) else (g if g >= b else b)
            if mx < 12:
                append(" ")
                continue
            luma = (mx * 70 + ((r * 77 + g * 150 + b * 29) >> 8) * 30) // 100
            if luma < 11:
                append(" ")
                continue

            qr = r & 252
            qg = g & 252
            qb = b & 252
            key = (qr << 16) | (qg << 8) | qb
            if key != last_key:
                esc = cc_get(key)
                if esc is None:
                    esc = f"\033[38;2;{qr};{qg};{qb}m"
                    color_cache[key] = esc
                append(esc)
                last_key = key
            append(luma_char[luma])

    append("\033[0m\033[?2026l")
    return "".join(out_parts).encode("ascii")


def main():
    theme_name = sys.argv[1].lower() if len(sys.argv) > 1 else "crimson"
    if theme_name not in THEMES:
        sys.stderr.write("Доступные темы: " + ", ".join(THEMES.keys()) + "\n")
        sys.exit(1)
    theme = THEMES[theme_name]
    tr, tg, tb = theme

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    rng = random.Random(1000 - 7)
    # Косой дождь: [x, y, vy, len, alpha]
    rain = [
        [rng.uniform(-1.95, 1.95), rng.uniform(-0.8, 1.15), rng.uniform(1.7, 3.0), rng.uniform(0.06, 0.12), rng.uniform(0.10, 0.22)]
        for _ in range(90)
    ]
    # Летящие лепестки хиганбаны: [x, y, vx, vy, phase, bright]
    petals = [
        [rng.uniform(-1.8, 1.9), rng.uniform(-0.6, 1.05), rng.uniform(-0.42, -0.18), rng.uniform(-0.14, -0.05), rng.uniform(0.0, 6.283), rng.uniform(0.6, 1.0)]
        for _ in range(28)
    ]

    parts = []
    color_cache = {}
    scene = None
    last_w = last_h = 0
    last_aspect = 0.0

    cur_cycle = -1
    hit1_done = False
    hit2_done = False
    vs = make_random_victim(0)

    kagune_cfg = (
        ( 0.07, 0.48,  0.58, 0.052, 0.0, 250),
        (-0.02, 0.56,  0.22, 0.056, 1.7, 260),
        (-0.11, 0.40, -0.18, 0.048, 3.4, 130),
        ( 0.16, 0.26,  0.80, 0.042, 5.1, 120),
    )

    write_all(b"\033[?1049h\033[?25l\033[?7l\033[2J")
    start_t = time.perf_counter()
    prev_t = start_t
    target_dt = 1.0 / 32.0

    try:
        while g_running:
            now = time.perf_counter()
            dt = now - prev_t
            if dt > 0.06:
                dt = 0.06
            prev_t = now

            W, H, aspect = get_term_size()
            if W < 6 or H < 4:
                time.sleep(0.04)
                continue

            if scene is None or W != last_w or H != last_h or abs(aspect - last_aspect) > 0.02:
                last_w, last_h, last_aspect = W, H, aspect
                scene = build_background(W, H, aspect)
                if len(color_cache) > 10000:
                    color_cache.clear()
                write_all(b"\033[?2026h\033[2J\033[H\033[?2026l")

            elapsed_total = now - start_t
            cycle_idx = int(elapsed_total // CYCLE)
            ct = elapsed_total % CYCLE

            if cycle_idx != cur_cycle:
                cur_cycle = cycle_idx
                hit1_done = False
                hit2_done = False
                vs = make_random_victim(cur_cycle)
                parts.clear()

            # Базовый буфер из предвычисленного фона Токио
            r_buf = scene["bg_r"][:]
            g_buf = scene["bg_g"][:]
            b_buf = scene["bg_b"][:]
            z_buf = [0] * (W * H)

            kakugan_v = smoothstep(0.65, 1.32, ct) * (1.0 - smoothstep(6.85, 7.95, ct))
            kagune_grow = smoothstep(1.30, 2.58, ct) * (1.0 - smoothstep(5.55, 6.40, ct))
            kagune_glow = clampf(kagune_grow * 0.92 + kakugan_v * 0.25, 0.0, 1.0)
            crimson_moon = smoothstep(3.25, 4.10, ct) * (1.0 - smoothstep(7.45, 8.65, ct))
            puddle = smoothstep(3.55, 5.95, ct) * (1.0 - smoothstep(7.55, 8.65, ct))

            # 1. Покраснение луны в момент убийства
            if crimson_moon > 0.01:
                cm_r = int(120 * tr * crimson_moon)
                cm_g = 1.0 - 0.78 * crimson_moon
                cm_b = 1.0 - 0.75 * crimson_moon
                for idx, mw in scene["moon_pixels"]:
                    r_buf[idx] = min(255, r_buf[idx] + int(cm_r * mw))
                    g_buf[idx] = int(g_buf[idx] * cm_g)
                    b_buf[idx] = int(b_buf[idx] * cm_b)

            # 2. Алый отблеск кагуне и растущая лужа крови на мокром асфальте
            if kagune_glow > 0.01 or puddle > 0.01:
                exp = math.exp
                pud_w = 0.13 + 0.50 * puddle
                inv_pud = 1.0 / pud_w
                for idx, wx, dy in scene["floor_pixels"]:
                    fade_y = 1.0 - dy * 0.78
                    if kagune_glow > 0.01:
                        rf = exp(-wx * wx * 0.85) * fade_y * kagune_glow * 68.0
                        r_buf[idx] += int(rf * tr)
                        g_buf[idx] += int(rf * tg * 0.4)
                        b_buf[idx] += int(rf * tb * 0.6)
                    if puddle > 0.01:
                        pd = abs(wx - 0.90) * inv_pud
                        if pd < 1.0:
                            pf = (1.0 - pd * pd) * fade_y * puddle
                            br = int(185 * pf)
                            if br > r_buf[idx]:
                                r_buf[idx] = br
                            g_buf[idx] = int(g_buf[idx] * (1.0 - 0.82 * pf))
                            b_buf[idx] = int(b_buf[idx] * (1.0 - 0.80 * pf))

            ux, uy = scene["ux"], scene["uy"]
            cx_s, cy_s = scene["cx"], scene["cy"]

            # 3. Косой дождь + мелкие брызги при ударе капель об асфальт
            rain_limit = len(rain) // 2 if W * H < 1400 else len(rain)
            r_steps = 1 if uy < 10.0 else 3
            for i in range(rain_limit):
                rd = rain[i]
                rd[1] -= rd[2] * dt
                rd[0] -= 0.28 * dt
                if rd[1] < FLOOR_Y:
                    # Мелкий всплеск капли на мокром асфальте
                    sx_spl = int(cx_s + rd[0] * ux)
                    sy_spl = int(cy_s - FLOOR_Y * uy)
                    if 0 <= sx_spl < W and 0 <= sy_spl < H:
                        si = sy_spl * W + sx_spl
                        r_buf[si] += 45
                        g_buf[si] += 55
                        b_buf[si] += 75
                    rd[1] = 1.12 + rng.random() * 0.2
                    rd[0] = rng.uniform(-1.95, 2.05)

                sx0, sy0 = cx_s + rd[0] * ux, cy_s - rd[1] * uy
                sx1, sy1 = cx_s + (rd[0] - 0.018) * ux, cy_s - (rd[1] - rd[3]) * uy
                dr = int(rd[4] * (150 + 60 * kagune_glow))
                dg = int(rd[4] * 165)
                db = int(rd[4] * 215)
                for s in range(r_steps + 1):
                    f = s / r_steps
                    ix = int(sx0 + (sx1 - sx0) * f)
                    iy = int(sy0 + (sy1 - sy0) * f)
                    if 0 <= ix < W and 0 <= iy < H:
                        ii = iy * W + ix
                        r_buf[ii] += dr
                        g_buf[ii] += dg
                        b_buf[ii] += db

            # 4. Гуль и рандомная жертва
            back_x, back_y, eye_x, eye_y = draw_ghoul(
                r_buf, g_buf, b_buf, z_buf, scene, -0.78, ct, kagune_glow, kakugan_v, theme
            )
            chest_x, chest_y = draw_victim(
                r_buf, g_buf, b_buf, z_buf, scene, vs, ct, kagune_glow, theme
            )

            # 5. Четыре щупальца ринкаку-кагуне + RC-разряды
            if kagune_grow > 0.01:
                windup = smoothstep(2.65, 3.06, ct) * (1.0 - smoothstep(3.06, 3.30, ct))
                strike = smoothstep(3.06, 3.34, ct) * (1.0 - smoothstep(5.25, 5.80, ct))
                retract = smoothstep(5.25, 5.95, ct)
                u_len = kagune_grow * (1.0 - 0.35 * retract)

                tips = []
                for off_y, pierce, arc_h, thick, ph, z_int in kagune_cfg:
                    idle_tx = back_x - 0.12 + 0.25 * math.sin(ct * 2.5 + ph) - 0.28 * windup
                    idle_ty = back_y + arc_h + 0.12 * math.cos(ct * 3.1 + ph)
                    hit_tx = chest_x + pierce + 0.03 * math.sin(ct * 9.0 + ph)
                    hit_ty = chest_y + off_y + 0.04 * math.sin(ct * 6.0 + ph)

                    tx = lerpf(idle_tx, hit_tx, strike)
                    ty = lerpf(idle_ty, hit_ty, strike)
                    tips.append((tx, ty))

                    c1x = lerpf(back_x - 0.45 - 0.20 * windup, back_x - 0.22, strike)
                    c1y = back_y + arc_h * (0.85 - 0.25 * strike) + 0.08 * math.sin(ct * 4.0 + ph)
                    c2x = lerpf(back_x - 0.25, lerpf(back_x, chest_x, 0.58), strike)
                    c2y = lerpf(idle_ty + 0.10, chest_y + off_y + arc_h * 0.26, strike)

                    draw_kagune_tendril(
                        r_buf, g_buf, b_buf, z_buf, scene,
                        back_x, back_y, c1x, c1y, c2x, c2y, tx, ty,
                        u_len, thick, ph, ct, z_int, theme
                    )

                draw_glow(r_buf, g_buf, b_buf, scene, back_x, back_y, 0.25, 0.22,
                          0.78 * tr * kagune_grow, 0.05 * kagune_grow, 0.09 * kagune_grow, 2.0)

                # Треск RC-молний на замахе и в момент удара
                if 2.55 <= ct < 3.65:
                    tick = int(ct * 24.0)
                    l_int = smoothstep(2.55, 2.90, ct) * (1.0 - smoothstep(3.35, 3.65, ct))
                    draw_rc_lightning(r_buf, g_buf, b_buf, scene, tips[0][0], tips[0][1], tips[1][0], tips[1][1], tr, tg, tb, l_int * 0.9, tick * 131 + 7)
                    draw_rc_lightning(r_buf, g_buf, b_buf, scene, back_x, back_y, tips[0][0], tips[0][1], tr, tg, tb, l_int * 0.7, tick * 257 + 19)

            # 6. Спавн крови, дыма из какугана и RC-искр
            if not hit1_done and ct >= 3.30:
                hit1_done = True
                spawn_blood(parts, rng, chest_x + 0.05, chest_y + 0.02, 340, 1.85, 1.0)
                spawn_blood(parts, rng, chest_x - 0.04, chest_y, 85, 0.85, -0.5)
            if not hit2_done and ct >= 5.28:
                hit2_done = True
                spawn_blood(parts, rng, chest_x, chest_y, 170, 1.05, -0.7)
            if 3.45 < ct < 5.35 and rng.random() < 0.72:
                spawn_blood(parts, rng, chest_x + 0.08, chest_y - 0.03, 5, 0.35, 0.4)

            # Тонкий алый дым от горящего какугана
            if kakugan_v > 0.35 and len(parts) < MAX_PARTS and rng.random() < 0.55:
                parts.append([
                    eye_x, eye_y,
                    -0.14 - rng.random() * 0.16, 0.16 + rng.random() * 0.14,
                    0.55, 0.55, 0.85, 0, 1
                ])

            # RC-искры от кагуне
            if kagune_grow > 0.3 and ct < 5.6 and len(parts) < MAX_PARTS and rng.random() < 0.5:
                parts.append([
                    back_x + (rng.random() - 0.5) * 0.45,
                    back_y + (rng.random() - 0.2) * 0.65,
                    (rng.random() - 0.3) * 0.35, 0.20 + rng.random() * 0.35,
                    0.75, 0.75, 0.9, 0, 1
                ])

            # 7. Симуляция и отрисовка крови и RC-тумана
            part_fade_end = 1.0 - smoothstep(7.55, 8.65, ct)
            alive = []
            for pt in parts:
                pt[4] -= dt
                if pt[4] <= 0.0:
                    continue
                if pt[8] == 0:  # кровь с гравитацией
                    if not pt[7]:
                        pt[3] -= 3.2 * dt
                        pt[2] *= (1.0 - 0.7 * dt)
                        pt[0] += pt[2] * dt
                        pt[1] += pt[3] * dt
                        if pt[1] <= FLOOR_Y:
                            pt[1] = FLOOR_Y - rng.random() * 0.03
                            pt[2] = pt[3] = 0.0
                            pt[7] = 1
                else:  # дым/искры
                    pt[0] += pt[2] * dt
                    pt[1] += pt[3] * dt
                    pt[2] *= (1.0 - 1.4 * dt)
                    pt[3] *= (1.0 - 1.4 * dt)

                alive.append(pt)
                la = clampf(pt[4] / max(pt[5] * 0.35, 0.1), 0.0, 1.0) * part_fade_end
                ix = int(cx_s + pt[0] * ux)
                iy = int(cy_s - pt[1] * uy)
                if 0 <= ix < W and 0 <= iy < H:
                    ii = iy * W + ix
                    if pt[8] == 0:
                        br = int((145 + 135 * pt[6]) * la)
                        if br > r_buf[ii]:
                            r_buf[ii] = br
                        g_buf[ii] = int(g_buf[ii] * 0.2 + br * 0.015)
                        b_buf[ii] = int(b_buf[ii] * 0.2 + br * 0.030)
                    else:
                        r_buf[ii] += int(145 * tr * la)
                        g_buf[ii] += int(24 * la)
                        b_buf[ii] += int(32 * tb * la)
            parts = alive

            # 8. Парящие лепестки хиганбаны на ветру
            for pl in petals:
                pl[0] += (pl[2] + 0.12 * math.sin(ct * 2.4 + pl[4])) * dt
                pl[1] += pl[3] * dt
                if pl[1] < FLOOR_Y or pl[0] < -2.0:
                    pl[0] = rng.uniform(-0.2, 2.1)
                    pl[1] = rng.uniform(0.45, 1.15)
                ix = int(cx_s + pl[0] * ux)
                iy = int(cy_s - pl[1] * uy)
                if 0 <= ix < W and 0 <= iy < H:
                    ii = iy * W + ix
                    r_buf[ii] = max(r_buf[ii], int(225 * pl[5]))
                    g_buf[ii] = max(g_buf[ii], int(18 * pl[5]))
                    b_buf[ii] = max(b_buf[ii], int(34 * pl[5]))

            # 9. Аниме-вспышка, ударное кольцо и росчерк в момент пробития
            if 3.28 <= ct < 3.75:
                u = (ct - 3.28) / 0.47
                fl = (1.0 - u) * (1.0 - u)
                draw_glow(r_buf, g_buf, b_buf, scene, chest_x, chest_y, 0.45 + u * 0.65, 0.35 + u * 0.50,
                          1.40 * tr * fl, 0.38 * fl, 0.38 * fl, 1.8)
                draw_glow(r_buf, g_buf, b_buf, scene, chest_x + 0.15, chest_y, 1.25 * (0.4 + u), 0.042 * (1.0 - u * 0.6),
                          1.65 * fl, 0.80 * fl, 0.80 * fl, 2.0)
                draw_ring(r_buf, g_buf, b_buf, scene, chest_x, chest_y, 0.10 + u * 0.85, 0.045, tr, 0.18, 0.22, fl * 1.1)

            # 10. Тряска камеры при ударе и выдёргивании кагуне
            shake_x = shake_y = 0
            if 3.30 <= ct < 3.82:
                amp = max(1, int((1.0 - (ct - 3.30) / 0.52) * 3.0))
                shake_x = rng.randint(-amp, amp)
                shake_y = rng.randint(-1, 1)
            elif 5.26 <= ct < 5.56:
                shake_x = rng.choice((-1, 0, 1))

            frame_bytes = encode_frame(r_buf, g_buf, b_buf, W, H, shake_x, shake_y, color_cache)
            write_all(frame_bytes)

            sleep_for = target_dt - (time.perf_counter() - now)
            if sleep_for > 0.0:
                time.sleep(sleep_for)
    finally:
        write_all(b"\033[0m\033[?7h\033[?25h\033[?1049l")


if __name__ == "__main__":
    main()
