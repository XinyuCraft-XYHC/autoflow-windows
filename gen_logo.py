"""
AutoFlow Logo v3 - Glass style infinity symbol
Reference: White/light glass card with blue infinity loop + 'autoflow' text
"""
import math, struct, zlib, os


# ─── utility ──────────────────────────────────────────────────────────────────

def clamp(v, lo=0, hi=255):
    return max(lo, min(hi, int(round(v))))

def lerp(a, b, t):
    return a + (b - a) * t

def alpha_blend(src_r, src_g, src_b, src_a, dst_r, dst_g, dst_b, dst_a=255):
    if src_a <= 0:
        return dst_r, dst_g, dst_b, dst_a
    if src_a >= 255:
        return src_r, src_g, src_b, 255
    t = src_a / 255.0
    oa = clamp(src_a + dst_a * (1 - t))
    if oa == 0:
        return 0, 0, 0, 0
    return (clamp(lerp(dst_r, src_r, t)),
            clamp(lerp(dst_g, src_g, t)),
            clamp(lerp(dst_b, src_b, t)),
            oa)

def encode_png(width, height, pixels_rgba):
    def chunk(ct, data):
        leng = struct.pack('>I', len(data))
        c = ct + data
        crc = struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        return leng + c + crc
    ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    raw = bytearray()
    for row in pixels_rgba:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend([clamp(r), clamp(g), clamp(b), clamp(a)])
    png  = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', ihdr)
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    png += chunk(b'IEND', b'')
    return png


# ─── canvas ───────────────────────────────────────────────────────────────────

class Canvas:
    def __init__(self, w, h, bg=(0, 0, 0, 0)):
        self.w, self.h = w, h
        self.buf = [[list(bg) for _ in range(w)] for _ in range(h)]

    def _set(self, x, y, r, g, b, a):
        if 0 <= x < self.w and 0 <= y < self.h:
            p = self.buf[y][x]
            nr, ng, nb, na = alpha_blend(r, g, b, a, p[0], p[1], p[2], p[3])
            p[0], p[1], p[2], p[3] = nr, ng, nb, na

    def fill_circle(self, cx, cy, radius, r, g, b, a):
        ir = int(radius) + 2
        for py in range(int(cy) - ir, int(cy) + ir + 1):
            for px in range(int(cx) - ir, int(cx) + ir + 1):
                d = math.hypot(px + 0.5 - cx, py + 0.5 - cy)
                if d <= radius - 0.5:
                    self._set(px, py, r, g, b, a)
                elif d <= radius + 0.5:
                    aa = clamp(a * (radius + 0.5 - d))
                    self._set(px, py, r, g, b, aa)

    def fill_rounded_rect(self, x0, y0, x1, y1, rad,
                          top_col, bot_col, alpha=255):
        w = x1 - x0
        h = y1 - y0
        for py in range(y0, y1 + 1):
            t = (py - y0) / max(h, 1)
            r = clamp(lerp(top_col[0], bot_col[0], t))
            g = clamp(lerp(top_col[1], bot_col[1], t))
            b = clamp(lerp(top_col[2], bot_col[2], t))
            for px in range(x0, x1 + 1):
                aa = 1.0
                cx_corner = None
                if   px < x0 + rad and py < y0 + rad:
                    cx_corner = (x0 + rad, y0 + rad)
                elif px > x1 - rad and py < y0 + rad:
                    cx_corner = (x1 - rad, y0 + rad)
                elif px < x0 + rad and py > y1 - rad:
                    cx_corner = (x0 + rad, y1 - rad)
                elif px > x1 - rad and py > y1 - rad:
                    cx_corner = (x1 - rad, y1 - rad)

                if cx_corner:
                    d = math.hypot(px + 0.5 - cx_corner[0],
                                   py + 0.5 - cx_corner[1])
                    if d > rad + 0.7:
                        continue
                    elif d > rad - 0.7:
                        aa = (rad + 0.7 - d) / 1.4
                self._set(px, py, r, g, b, clamp(alpha * aa))

    def draw_stroke_curve(self, pts, thickness, color_fn, global_alpha=255):
        half = thickness / 2.0
        for (px, py, t) in pts:
            r, g, b = color_fn(t)
            self.fill_circle(px, py, half, r, g, b, global_alpha)

    def to_png(self):
        rows = [[(p[0], p[1], p[2], p[3]) for p in row] for row in self.buf]
        return encode_png(self.w, self.h, rows)


# ─── lemniscate (infinity symbol) ─────────────────────────────────────────────

def lemniscate(cx, cy, a, n=8000):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        s, c = math.sin(t), math.cos(t)
        denom = 1 + s * s
        x = cx + a * c / denom
        y = cy + a * s * c / denom
        pts.append((x, y, i / n))
    return pts


# ─── colour helpers ───────────────────────────────────────────────────────────

def blue_gradient(t):
    # Deep blue -> bright cyan -> electric blue cycle
    t2 = (math.sin(t * 2 * math.pi - math.pi / 2) + 1) / 2
    r = clamp(lerp(10, 80, t2))
    g = clamp(lerp(80, 200, t2))
    b = clamp(lerp(220, 255, t2))
    return r, g, b

def blue_gradient_bright(t):
    t2 = (math.sin(t * 2 * math.pi - math.pi / 2) + 1) / 2
    r = clamp(lerp(50, 130, t2))
    g = clamp(lerp(160, 240, t2))
    b = clamp(lerp(245, 255, t2))
    return r, g, b


# ─── main render ──────────────────────────────────────────────────────────────

def render(size):
    W = H = size
    s = size / 256

    canvas = Canvas(W, H, bg=(0, 0, 0, 0))

    pad  = int(12 * s)
    rad  = int(50 * s)

    # 1. outer dark shadow layer
    canvas.fill_rounded_rect(pad + 5, pad + 7, W - pad - 5, H - pad - 5, rad,
                             (0, 5, 20), (5, 12, 35), alpha=160)

    # 2. main glass body: top=near white, bottom=light blue
    canvas.fill_rounded_rect(pad, pad, W - pad, H - pad, rad,
                             (248, 252, 255), (215, 232, 255), alpha=250)

    # 3. top highlight strip (white gloss)
    hl_h = int((H - 2 * pad) * 0.40)
    canvas.fill_rounded_rect(pad + 2, pad + 2, W - pad - 2, pad + hl_h, rad,
                             (255, 255, 255), (240, 248, 255), alpha=140)
    # fade it out at the bottom with individual pixels
    fade_y0 = pad + int(hl_h * 0.55)
    fade_y1 = pad + hl_h
    for py in range(fade_y0, fade_y1):
        tt = (py - fade_y0) / max(1, fade_y1 - fade_y0)
        av = clamp(140 * (1 - tt))
        for px in range(pad + 2, W - pad - 2):
            canvas._set(px, py, 255, 255, 255, av)

    # 4. glass border (subtle dark outline)
    border_r = rad
    bw = max(1, int(1.5 * s))
    for py in range(pad, H - pad + 1):
        for px in range(pad, W - pad + 1):
            cx_corner = None
            if   px < pad + border_r and py < pad + border_r:
                cx_corner = (pad + border_r, pad + border_r)
            elif px > W - pad - border_r and py < pad + border_r:
                cx_corner = (W - pad - border_r, pad + border_r)
            elif px < pad + border_r and py > H - pad - border_r:
                cx_corner = (pad + border_r, H - pad - border_r)
            elif px > W - pad - border_r and py > H - pad - border_r:
                cx_corner = (W - pad - border_r, H - pad - border_r)

            is_edge = (px <= pad + bw or px >= W - pad - bw or
                       py <= pad + bw or py >= H - pad - bw)
            if not is_edge:
                continue

            if cx_corner:
                d = math.hypot(px + 0.5 - cx_corner[0], py + 0.5 - cx_corner[1])
                if d > border_r + 0.5 or d < border_r - bw - 0.5:
                    continue
                av_edge = min(1.0, (border_r + 0.5 - d)) * 60
            else:
                av_edge = 60
            canvas._set(px, py, 180, 200, 230, clamp(av_edge))

    # 5. infinity symbol
    inf_cx = W / 2
    inf_cy = H * 0.36
    inf_a  = W * 0.26

    pts = lemniscate(inf_cx, inf_cy, inf_a, n=10000)

    stroke = max(3, int(27 * s))

    # shadow pass
    shadow_pts = [(px + 2*s, py + 3*s, t) for (px, py, t) in pts]
    canvas.draw_stroke_curve(shadow_pts, stroke + 2,
                             lambda t: (0, 20, 60), global_alpha=55)

    # dark outline pass
    canvas.draw_stroke_curve(pts, stroke + 2,
                             lambda t: (5, 30, 100), global_alpha=80)

    # main body pass
    canvas.draw_stroke_curve(pts, stroke, blue_gradient, global_alpha=240)

    # inner bright highlight pass
    inner_pts = lemniscate(inf_cx, inf_cy, inf_a * 0.60, n=5000)
    canvas.draw_stroke_curve(inner_pts, max(1, int(stroke * 0.28)),
                             lambda t: (180, 230, 255), global_alpha=50)

    # specular dot on top-left arc
    spec_x = inf_cx - inf_a * 0.30
    spec_y = inf_cy - inf_a * 0.18
    canvas.fill_circle(spec_x, spec_y, max(2, int(7 * s)), 220, 245, 255, 180)

    # 6. "autoflow" text using pixel font
    _draw_autoflow(canvas, W // 2, int(H * 0.62), s)

    # 7. subtitle "Open Source AI"
    _draw_subtitle(canvas, W // 2, int(H * 0.795), s)

    # 8. corner shine (top-right)
    sx = int(W * 0.75)
    sy = int(H * 0.14)
    sr = int(16 * s)
    for dy in range(-sr, sr + 1):
        for dx in range(-sr, sr + 1):
            d = math.hypot(dx, dy)
            if d < sr:
                av = clamp(200 * (1 - d / sr) ** 2.2)
                canvas._set(sx + dx, sy + dy, 255, 255, 255, av)

    return canvas.to_png()


# ─── pixel font ───────────────────────────────────────────────────────────────

# 5×7 bitmaps
GLYPHS = {
    'a': ["01110","00001","01111","10001","01111","00000","00000"],
    'u': ["10001","10001","10001","10011","01101","00000","00000"],
    't': ["01110","00100","00100","00100","00011","00000","00000"],
    'o': ["01110","10001","10001","10001","01110","00000","00000"],
    'f': ["00111","01000","11100","01000","01000","00000","00000"],
    'l': ["11000","01000","01000","01000","01110","00000","00000"],
    'w': ["10001","10001","10101","10101","01010","00000","00000"],
    ' ': ["00000","00000","00000","00000","00000","00000","00000"],
    'O': ["01110","10001","10001","10001","01110","00000","00000"],
    'p': ["11110","10001","11110","10000","10000","00000","00000"],
    'e': ["01110","10001","11111","10000","01110","00000","00000"],
    'n': ["11110","10001","10001","10001","10001","00000","00000"],
    'S': ["01111","10000","01110","00001","11110","00000","00000"],
    's': ["01110","10000","01110","00001","11110","00000","00000"],
    'r': ["10110","11001","10000","10000","10000","00000","00000"],
    'c': ["01110","10000","10000","10000","01110","00000","00000"],
    'A': ["00100","01010","10001","11111","10001","00000","00000"],
    'I': ["11111","00100","00100","00100","11111","00000","00000"],
}


def _draw_glyph_string(canvas, text, cx, top_y, cell_w, cell_h, px_w, px_h, gap,
                       r, g, b, a):
    total_w = len(text) * (cell_w + gap) - gap
    x0 = cx - total_w // 2
    for ci, ch in enumerate(text):
        bmp = GLYPHS.get(ch, GLYPHS[' '])
        char_x = x0 + ci * (cell_w + gap)
        for ri, row in enumerate(bmp):
            for col, bit in enumerate(row):
                if bit == '1':
                    for dy in range(px_h):
                        for dx in range(px_w):
                            canvas._set(char_x + col * px_w + dx,
                                        top_y + ri * px_h + dy,
                                        r, g, b, a)


def _draw_autoflow(canvas, cx, top_y, s):
    cw = max(5, int(13 * s))
    ch = max(5, int(17 * s))
    pw = max(2, cw // 5)
    ph = max(2, ch // 7)
    gap = max(1, int(2 * s))
    _draw_glyph_string(canvas, "autoflow", cx, top_y,
                       cw, ch, pw, ph, gap, 10, 22, 78, 245)


def _draw_subtitle(canvas, cx, top_y, s):
    cw = max(3, int(7 * s))
    ch = max(3, int(9 * s))
    pw = max(1, cw // 5)
    ph = max(1, ch // 7)
    gap = max(1, int(1 * s))
    _draw_glyph_string(canvas, "Open Source AI", cx, top_y,
                       cw, ch, pw, ph, gap, 90, 110, 150, 200)


# ─── ICO builder ──────────────────────────────────────────────────────────────

def make_ico(sizes):
    pngs = []
    for sz in sizes:
        print(f"  {sz}x{sz}")
        pngs.append(render(sz))
    n = len(pngs)
    header  = struct.pack('<HHH', 0, 1, n)
    offset  = 6 + n * 16
    entries = b''
    for sz, png in zip(sizes, pngs):
        w = sz if sz < 256 else 0
        h = sz if sz < 256 else 0
        entries += struct.pack('<BBBBHHII', w, h, 0, 0, 1, 32, len(png), offset)
        offset  += len(png)
    return header + entries + b''.join(pngs)


# ─── entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    out = os.path.join(os.path.dirname(__file__), 'assets')
    os.makedirs(out, exist_ok=True)

    sizes = [16, 32, 48, 64, 128, 256]
    print("Generating AutoFlow logo ...")
    ico = make_ico(sizes)
    ico_path = os.path.join(out, 'autoflow.ico')
    with open(ico_path, 'wb') as f:
        f.write(ico)
    print(f"ICO -> {ico_path}  ({len(ico)//1024} KB)")

    big = render(512)
    preview = os.path.join(out, 'autoflow_preview.png')
    with open(preview, 'wb') as f:
        f.write(big)
    print(f"PNG -> {preview}")
