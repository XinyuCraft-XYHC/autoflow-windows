"""
AutoFlow Logo / Icon 生成脚本
生成多尺寸 PNG 然后合并为 ICO
设计理念：
  - 六边形背景（科技感）
  - 白色闪电符号（自动化/流程）
  - 右下角小齿轮（工具/设置）
  - 渐变色调：深蓝 → 紫色
"""
import math
import struct
import zlib
import os

# ─── 纯 Python PNG 生成（无需 Pillow）───

def _pack_png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    c = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", c)

def write_png(filename: str, width: int, height: int, pixels):
    """pixels: list of (R,G,B,A) tuples, row by row"""
    def row_bytes(y):
        raw = b""
        for x in range(width):
            r, g, b, a = pixels[y * width + x]
            raw += bytes([r, g, b, a])
        return raw

    raw_rows = b""
    for y in range(height):
        raw_rows += b"\x00" + row_bytes(y)

    compressed = zlib.compress(raw_rows, 9)

    with open(filename, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGBA
        # Actually RGBA = color type 6
        ihdr_data = struct.pack(">II", width, height) + bytes([8, 6, 0, 0, 0])
        f.write(_pack_png_chunk(b"IHDR", ihdr_data))
        f.write(_pack_png_chunk(b"IDAT", compressed))
        f.write(_pack_png_chunk(b"IEND", b""))


# ─── 绘制工具 ───

def lerp(a, b, t):
    return a + (b - a) * t

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def dist(x1, y1, x2, y2):
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def mix_alpha(bg, fg, alpha):
    """alpha in [0,1]"""
    r = int(clamp(lerp(bg[0], fg[0], alpha), 0, 255))
    g = int(clamp(lerp(bg[1], fg[1], alpha), 0, 255))
    b = int(clamp(lerp(bg[2], fg[2], alpha), 0, 255))
    return r, g, b

def aa_circle(px, py, cx, cy, r, feather=1.0):
    """返回 anti-aliased 圆形 alpha"""
    d = dist(px + 0.5, py + 0.5, cx, cy)
    return clamp(1.0 - (d - r) / feather, 0.0, 1.0)

def aa_hexagon(px, py, cx, cy, r, feather=1.2):
    """正六边形 signed distance"""
    x = px + 0.5 - cx
    y = py + 0.5 - cy
    # 正六边形 SDF
    k = [math.sqrt(3)/2, 0.5, math.tan(math.pi/6)]
    ax, ay = abs(x), abs(y)
    dot = 2.0 * min(k[0] * ax + k[1] * ay, 0.0)
    ax -= dot * k[0]
    ay -= dot * k[1]
    ax -= clamp(ax, -k[2] * r, k[2] * r)
    ay -= r
    d = math.sqrt(ax*ax + ay*ay) * (-1 if ay < 0 else 1)
    return clamp(1.0 - (d) / feather, 0.0, 1.0)

def gradient_color(cx, cy, r, px, py, c1, c2):
    """径向渐变，从中心 c1 到边缘 c2"""
    d = dist(px, py, cx, cy)
    t = clamp(d / r, 0, 1)
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))

def point_in_polygon(px, py, polygon):
    """Ray-casting algorithm"""
    n = len(polygon)
    inside = False
    x, y = px, py
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-10) + xi):
            inside = not inside
        j = i
    return inside

def polygon_sdf(px, py, polygon):
    """计算点到多边形的有符号距离（负=在内部）"""
    n = len(polygon)
    d = float('inf')
    s = 1.0
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        bax = b[0] - a[0]; bay = b[1] - a[1]
        pax = px - a[0]; pay = py - a[1]
        h = clamp((pax*bax + pay*bay) / (bax*bax + bay*bay + 1e-10), 0, 1)
        dx = pax - h*bax; dy = pay - h*bay
        d = min(d, dx*dx + dy*dy)
        c1 = pay >= 0; c2 = b[1] - py >= 0; c3 = bax*pay > bay*pax
        if (c1 == c2) != c3: s = -s  # parity
    return s * math.sqrt(d)

def aa_polygon(px, py, polygon, feather=1.0):
    """多边形 anti-alias alpha"""
    d = polygon_sdf(px + 0.5, py + 0.5, polygon)
    return clamp(1.0 - d / feather, 0.0, 1.0)

def aa_ring(px, py, cx, cy, r_outer, r_inner, feather=0.8):
    d = dist(px + 0.5, py + 0.5, cx, cy)
    outer_a = clamp(1.0 - (d - r_outer) / feather, 0, 1)
    inner_a = clamp(1.0 - (r_inner - d) / feather, 0, 1)
    return outer_a * inner_a


# ─── 主绘制函数 ───

def draw_icon(size: int):
    pixels = [(0, 0, 0, 0)] * (size * size)
    s = size

    def set_px(x, y, r, g, b, a):
        if 0 <= x < s and 0 <= y < s:
            idx = y * s + x
            # Alpha-compositing over existing
            ea = pixels[idx][3] / 255.0
            na = a / 255.0
            out_a = na + ea * (1 - na)
            if out_a < 1e-5:
                pixels[idx] = (0, 0, 0, 0)
                return
            nr = int((pixels[idx][0] * ea * (1-na) + r * na) / out_a)
            ng = int((pixels[idx][1] * ea * (1-na) + g * na) / out_a)
            nb = int((pixels[idx][2] * ea * (1-na) + b * na) / out_a)
            pixels[idx] = (clamp(nr,0,255), clamp(ng,0,255), clamp(nb,0,255), int(out_a*255))

    cx = s / 2.0
    cy = s / 2.0
    r_hex = s * 0.47

    # ── 背景色：透明（已用 alpha）──
    # 颜色：深蓝 #1A1B3A → 靛紫 #6C63FF
    C_DARK  = (26,  27,  58)
    C_MID   = (74,  55, 130)
    C_LIGHT = (108, 99, 255)
    # 渐变方向：从左上角 c_light 到右下角 c_dark
    SHADOW  = (10,  8,  40)

    for y in range(s):
        for x in range(s):
            # 六边形 alpha
            hex_a = aa_hexagon(x, y, cx, cy, r_hex, feather=1.5)
            if hex_a < 0.001:
                continue

            # 渐变色（从左上到右下）
            tx = (x - cx + r_hex) / (2 * r_hex)
            ty = (y - cy + r_hex) / (2 * r_hex)
            t  = clamp((tx * 0.4 + ty * 0.6), 0, 1)
            r = int(lerp(C_LIGHT[0], C_DARK[0], t))
            g = int(lerp(C_LIGHT[1], C_DARK[1], t))
            b = int(lerp(C_LIGHT[2], C_DARK[2], t))

            # 内圆角阴影（增加立体感）
            rim_d = dist(x + 0.5, y + 0.5, cx, cy)
            rim_t = clamp((rim_d - r_hex * 0.72) / (r_hex * 0.25), 0, 1)
            r = int(lerp(r, SHADOW[0], rim_t * 0.4))
            g = int(lerp(g, SHADOW[1], rim_t * 0.4))
            b = int(lerp(b, SHADOW[2], rim_t * 0.4))

            set_px(x, y, r, g, b, int(hex_a * 255))

    # ── 六边形描边 / 高光 ──
    r_hex_inner = r_hex * 0.93
    for y in range(s):
        for x in range(s):
            outer_a = aa_hexagon(x, y, cx, cy, r_hex, feather=1.5)
            inner_a = aa_hexagon(x, y, cx, cy, r_hex_inner, feather=1.5)
            stroke_a = outer_a * (1.0 - inner_a)
            if stroke_a < 0.01:
                continue
            # 高光色调：上半部分偏亮蓝，下半偏暗
            highlight_t = clamp(1.0 - (y / s), 0, 1)
            hr = int(lerp(120, 200, highlight_t))
            hg = int(lerp(110, 190, highlight_t))
            hb = int(lerp(220, 255, highlight_t))
            set_px(x, y, hr, hg, hb, int(stroke_a * 200))

    # ── 闪电形状 ──
    # 设计：粗体闪电，居中稍微偏上
    # 顶点（相对于 size=256 缩放）
    lx = cx
    ly = cy * 1.0
    sc = s / 256.0

    # 闪电多边形点（size 256 坐标）
    bolt = [
        (lx + (-8 ) * sc, ly + (-90) * sc),   # 顶部左
        (lx + ( 30) * sc, ly + (-90) * sc),   # 顶部右
        (lx + (  2) * sc, ly + (-12) * sc),   # 中部左顶
        (lx + ( 36) * sc, ly + (-12) * sc),   # 中部右顶
        (lx + (-30) * sc, ly + ( 90) * sc),   # 底部左
        (lx + (  8) * sc, ly + ( 90) * sc),   # 底部右（对称）
        (lx + (-2 ) * sc, ly + ( 12) * sc),   # 中部右底
        (lx + (-36) * sc, ly + ( 12) * sc),   # 中部左底
    ]

    for y in range(s):
        for x in range(s):
            ba = aa_polygon(x, y, bolt, feather=1.2)
            if ba < 0.01:
                continue
            # 闪电白色+淡黄色渐变（上白下淡黄）
            ty2 = clamp((y - (cy - 90*sc)) / (180 * sc), 0, 1)
            wr = int(lerp(255, 255, ty2))
            wg = int(lerp(255, 230, ty2))
            wb = int(lerp(255, 140, ty2))
            set_px(x, y, wr, wg, wb, int(ba * 240))

    # ── 右下角小齿轮（点缀）──
    gear_cx = cx + r_hex * 0.50
    gear_cy = cy + r_hex * 0.52
    gear_r  = r_hex * 0.22
    gear_inner_r = gear_r * 0.55
    gear_teeth   = 8
    gear_color   = (180, 200, 255)

    for y in range(int(gear_cy - gear_r*1.5), int(gear_cy + gear_r*1.5) + 1):
        for x in range(int(gear_cx - gear_r*1.5), int(gear_cx + gear_r*1.5) + 1):
            if not (0 <= x < s and 0 <= y < s):
                continue
            dx = x + 0.5 - gear_cx
            dy = y + 0.5 - gear_cy
            d  = math.sqrt(dx*dx + dy*dy)
            angle = math.atan2(dy, dx)
            # 齿轮轮廓（通过角度调制半径）
            tooth_mod = math.cos(gear_teeth * angle) * gear_r * 0.15
            outer_r = gear_r + tooth_mod
            inner_r = gear_inner_r
            outer_a = clamp(1.0 - (d - outer_r) / 1.0, 0, 1)
            inner_a = clamp(1.0 - (inner_r - d) / 1.0, 0, 1)
            ga = outer_a * inner_a
            if ga < 0.01:
                continue
            set_px(x, y, gear_color[0], gear_color[1], gear_color[2], int(ga * 200))

    # ── 中心光晕（点缀，增加质感）──
    for y in range(int(cy - r_hex*0.6), int(cy + r_hex*0.3) + 1):
        for x in range(int(cx - r_hex*0.4), int(cx + r_hex*0.4) + 1):
            if not (0 <= x < s and 0 <= y < s):
                continue
            # 只在闪电中点附近加光晕
            d = dist(x, y, lx, ly + (-12)*sc)
            glow_r = r_hex * 0.18
            if d > glow_r:
                continue
            t = 1.0 - (d / glow_r)
            ga = t * t * 0.35
            set_px(x, y, 200, 220, 255, int(ga * 255))

    return pixels


def make_ico(sizes, output_path):
    """将多尺寸 PNG 数据打包为 ICO 文件"""
    import io
    png_data_list = []
    for size in sizes:
        pixels = draw_icon(size)
        buf = io.BytesIO()

        # 手动写 PNG 到 BytesIO
        def _pack_png_chunk2(ct, data):
            c = zlib.crc32(ct + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + ct + data + struct.pack(">I", c)

        def write_png_to_buf(fbuf, w, h, pxs):
            def row_bytes(yy):
                raw = b""
                for xx in range(w):
                    r2, g2, b2, a2 = pxs[yy * w + xx]
                    raw += bytes([r2, g2, b2, a2])
                return raw
            raw_rows = b""
            for yy in range(h):
                raw_rows += b"\x00" + row_bytes(yy)
            compressed = zlib.compress(raw_rows, 9)
            fbuf.write(b"\x89PNG\r\n\x1a\n")
            ihdr = struct.pack(">II", w, h) + bytes([8, 6, 0, 0, 0])
            fbuf.write(_pack_png_chunk2(b"IHDR", ihdr))
            fbuf.write(_pack_png_chunk2(b"IDAT", compressed))
            fbuf.write(_pack_png_chunk2(b"IEND", b""))

        write_png_to_buf(buf, size, size, pixels)
        png_data_list.append((size, buf.getvalue()))

    # ICO 头
    count = len(png_data_list)
    header = struct.pack("<HHH", 0, 1, count)  # reserved, type=1 (ICO), count
    offset = 6 + count * 16

    dir_entries = b""
    image_data  = b""
    for size, data in png_data_list:
        w = size if size < 256 else 0
        h = size if size < 256 else 0
        dir_entries += struct.pack("<BBBBHHII",
            w, h,          # width, height (0=256)
            0, 0,          # color count (0=truecolor), reserved
            1, 32,         # planes, bit count
            len(data),     # data size
            offset         # offset
        )
        offset += len(data)
        image_data += data

    with open(output_path, "wb") as f:
        f.write(header + dir_entries + image_data)
    print(f"[OK] ICO: {output_path}")


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    sizes = [16, 32, 48, 64, 128, 256]

    print("Generating AutoFlow icon...")

    # 生成单个 PNG（256px 预览）
    png_path = os.path.join(out_dir, "assets", "autoflow_icon.png")
    os.makedirs(os.path.dirname(png_path), exist_ok=True)
    pixels_256 = draw_icon(256)

    # 写 PNG 文件
    def row_bytes(y, pxs, w):
        raw = b""
        for x in range(w):
            r, g, b, a = pxs[y * w + x]
            raw += bytes([r, g, b, a])
        return raw

    raw_rows = b""
    for y in range(256):
        raw_rows += b"\x00" + row_bytes(y, pixels_256, 256)
    compressed = zlib.compress(raw_rows, 9)

    def pack_chunk(ct, data):
        c = zlib.crc32(ct + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + ct + data + struct.pack(">I", c)

    with open(png_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        ihdr = struct.pack(">II", 256, 256) + bytes([8, 6, 0, 0, 0])
        f.write(pack_chunk(b"IHDR", ihdr))
        f.write(pack_chunk(b"IDAT", compressed))
        f.write(pack_chunk(b"IEND", b""))
    print(f"[OK] PNG: {png_path}")

    # 生成 ICO
    ico_path = os.path.join(out_dir, "assets", "autoflow.ico")
    make_ico(sizes, ico_path)
    print(f"[OK] ICO: {ico_path}")
    print(f"     sizes: {sizes}")


if __name__ == "__main__":
    main()
