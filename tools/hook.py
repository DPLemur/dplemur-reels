#!/usr/bin/env python3
"""Пересобирает начало рилса: быстрый хук «What if nature were your designer?».

Таймлайн нового начала:
  0.00–1.00  чистый кадр героя (без текста)
  1.00–2.55  крючок (HOOKS), последнее слово оформлено в стиле героя (STYLES), под ним — кружки палитры
  2.55–2.75  текст гаснет
  дальше     исходное видео с 3.75 с (подписи палитры → Wear/Style/Live → карточка)
  последние 0.5 с — плавный переход в первый кадр (закольцовка)

Ещё делает обложку covers/<id>.jpg (вариант Б): герой + «colour palette» + имя героя в его стиле + кружки палитры.
Всё важное — в центральной зоне 3:4, которую показывает сетка профиля.

Использование:
  python3 tools/hook.py <id> [<id> ...]        # пересобрать videos/<id>.mp4 и covers/<id>.jpg (исходник из git: SRC_REF)
  python3 tools/hook.py --preview <id> out.png # только кадр с текстом
  python3 tools/hook.py --cover <id> ...       # только обложки
Музыка — поле "music" в queue.json, палитра и имя героя — из "first_comment".
"""
import json, math, os, random, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops, ImageEnhance

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = "/usr/share/fonts/truetype/google-fonts/Lora-Italic-Variable.ttf"
W, H, FPS = 1080, 1920, 30
CUT = 3.75            # с какой секунды исходника продолжаем
T_IMG, T_IN, T_HOLD_END, T_OUT = 1.0, 0.3, 2.55, 0.2
SRC_REF = os.environ.get("SRC_REF", "8f1a5f0")  # коммит с исходными видео (до замены музыки)

# Стиль слова «designer?» для каждого героя.
# fill: ("texture", (x0,y0,x1,y1) доли кадра) — буквы «вырезаны» из фото героя
#       ("gradient", [цвета сверху вниз])
STYLES = {
    "bioluminescence": dict(fill=("gradient", ["#E8FFFF", "#5CE1E6", "#00B4FF"]),
                            glow=("#00E5FF", 26, 2), stroke=("#0A1931", 3)),
    "malachite":   dict(fill=("gradient", ["#B8F0D8", "#3CC48C", "#0B6E4F"]), stripes="#0B5A3E",
                        glow=("#A8E6CF", 12, 1), stroke=("#073B2C", 4), shadow=True),
    "lagoon":      dict(fill=("gradient", ["#E9FBF8", "#40E0D0", "#00A6A6"]), shine=True,
                        stroke=("#005F73", 4), shadow=True),
    "persimmon":   dict(fill=("gradient", ["#FBC076", "#F28C28", "#D76514"]), shine=True,
                        stroke=("#5C3A1B", 4), shadow=True),
    "snowyowl":    dict(fill=("gradient", ["#FFFFFF", "#F1F3F5"]), speckles="#2E2E2E",
                        stroke=("#3B3B3B", 4), shadow=True, q="#F2B705"),
    "labradorite": dict(fill=("hgradient", ["#E3C64A", "#7FD3C8", "#3C9FE0", "#2A6FD0", "#7FD3C8"]),
                        glow=("#4FB0C6", 18, 1), stroke=("#1B2328", 4)),
    "frost":       dict(fill=("gradient", ["#FFFFFF", "#DDEFFB", "#B9D9EB"]), sparkle=True,
                        glow=("#EAF6FF", 18, 1), stroke=("#5B6C7D", 4)),
    "bloodorange": dict(fill=("texture", (0.05, 0.47, 0.90, 0.80)), boost=1.2, bright=1.1,
                        stroke=("#F7A35C", 5), shadow=True),
    "riceterraces": dict(fill=("gradient", ["#EEDC6A", "#C9B74A", "#7BB661"]), stripes="#3E6B3A",
                         stroke=("#2E3A1C", 4), shadow=True),
    "ladybug":     dict(fill=("gradient", ["#EE3B2E", "#D7261E", "#A9160F"]), dots="#111111", shine=True,
                        stroke=("#111111", 5), shadow=True, q="#111111"),
    "bluelaceagate": dict(fill=("texture", (0.10, 0.10, 0.90, 0.45)), boost=1.1, bright=1.0,
                          stroke=("#1F3A68", 4), shadow=True),
    "sunflower":   dict(fill=("gradient", ["#FFE14D", "#F7C600", "#E89B00"]), shine=True,
                        stroke=("#4A2C10", 5), shadow=True),
    "dunes":       dict(fill=("gradient", ["#F8D3A4", "#E8975A", "#C0602E"]), ripples="#9A4520",
                        stroke=("#4A2412", 4), shadow=True),
}


def font(size, weight):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_axes([weight])
    return f


def hexc(c, a=255):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def text_mask(txt, f, size, xy):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).text(xy, txt, font=f, fill=255, anchor="ms")
    return m


def gradient(size, colors):
    w, h = size
    g = Image.new("RGBA", size)
    d = ImageDraw.Draw(g)
    cols = [hexc(c) for c in colors]
    for y in range(h):
        t = y / max(1, h - 1) * (len(cols) - 1)
        i = min(int(t), len(cols) - 2) if len(cols) > 1 else 0
        k = t - i
        a, b = cols[i], cols[min(i + 1, len(cols) - 1)]
        d.line([(0, y), (w, y)], fill=tuple(int(a[j] + (b[j] - a[j]) * k) for j in range(4)))
    return g


# Короткие имена для обложки, если имя из first_comment слишком длинное
COVER_NAMES = {"bioluminescence": "Glowing Waves"}

# Крючки чередуются, чтобы не приедались. (строка 1, строка 2, слово в стиле героя)
DESIGNER = ("What if nature", "were your", "designer?")
HOOKS = {
    "malachite": ("Your next palette", "is hiding in", "malachite"),
    "lagoon": ("Steal the colours", "of a tropical", "lagoon"),
    "snowyowl": ("This outfit was", "styled by a", "snowy owl"),
    "labradorite": ("Your next palette", "is hiding in", "labradorite"),
    "bloodorange": ("Steal the colours", "of a", "blood orange"),
    "riceterraces": ("Your next palette", "is hiding in", "rice terraces"),
    "bluelaceagate": ("Your next palette", "is hiding in an", "agate"),
    "sunflower": ("This outfit was", "styled by a", "sunflower"),
}


def styled_word(bg, st, text, cy, size=190, max_w=980):
    """RGBA слой: text в стиле героя, по центру, базовая линия ~cy+55*size/190."""
    f = font(size, 700)
    if f.getlength(text) > max_w:
        size = int(size * max_w / f.getlength(text))
        f = font(size, 700)
    q = "?" if text.endswith("?") else ""
    word = text[:-1] if q else text
    ww = f.getlength(word + q)
    x0 = (W - ww) / 2
    base = cy + 55 * size / 190
    m_word = text_mask(word, f, (W, H), (x0 + f.getlength(word) / 2, base))
    m_q = text_mask(q, f, (W, H), (x0 + f.getlength(word) + f.getlength(q) / 2, base)) if q else Image.new("L", (W, H), 0)
    m_all = ImageChops.lighter(m_word, m_q)
    bb = m_all.getbbox()
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    k = size / 190  # масштаб деталей

    kind, arg = st["fill"]
    fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if kind == "texture":
        x0f, y0f, x1f, y1f = arg
        crop = bg.crop((int(x0f * W), int(y0f * H), int(x1f * W), int(y1f * H)))
        s = max(bw / crop.width, bh / crop.height)
        crop = crop.resize((int(crop.width * s) + 1, int(crop.height * s) + 1), Image.LANCZOS)
        cx, cy2 = (crop.width - bw) // 2, (crop.height - bh) // 2
        crop = crop.crop((cx, cy2, cx + bw, cy2 + bh))
        crop = ImageEnhance.Color(crop).enhance(st.get("boost", 1.0))
        crop = ImageEnhance.Brightness(crop).enhance(st.get("bright", 1.0))
        fill.paste(crop.convert("RGBA"), (bb[0], bb[1]))
    elif kind == "hgradient":
        fill.paste(gradient((bh, bw), arg).rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT), (bb[0], bb[1]))
    else:
        fill.paste(gradient((bw, bh), arg), (bb[0], bb[1]))

    d = ImageDraw.Draw(fill)
    rnd = random.Random(7)
    if st.get("dots"):  # пятнышки божьей коровки
        for _ in range(int(bw * bh / (5200 * k * k))):
            x, y = bb[0] + rnd.random() * bw, bb[1] + rnd.random() * bh
            r = rnd.uniform(9, 15) * k
            d.ellipse((x - r, y - r, x + r, y + r), fill=hexc(st["dots"]))
    if st.get("speckles"):  # крапинки полярной совы
        for _ in range(int(bw * bh / (1500 * k * k))):
            x, y = bb[0] + rnd.random() * bw, bb[1] + rnd.random() * bh
            s = rnd.uniform(5, 10) * k
            d.polygon([(x - s, y - s * 0.3), (x, y + s * 0.5), (x + s, y - s * 0.3), (x, y + s * 0.1)],
                      fill=hexc(st["speckles"], 230))
    if st.get("stripes"):  # ступени террас / полосы малахита
        for j in range(9):
            y0 = bb[1] + bh * (j + 0.5) / 9
            pts = [(bb[0] + x, y0 + 6 * k * math.sin(x / (90 * k) + j)) for x in range(0, bw + 1, 8)]
            d.line(pts, fill=hexc(st["stripes"], 200), width=max(2, int(4 * k)))
    if st.get("ripples"):  # рябь песчаных дюн
        for j in range(8):
            y0 = bb[1] + bh * (j + 0.5) / 8
            pts = [(bb[0] + x, y0 + 9 * k * math.sin(x / (55 * k) + j * 1.7)) for x in range(0, bw + 1, 6)]
            d.line(pts, fill=hexc(st["ripples"], 190), width=max(2, int(5 * k)))
    if st.get("sparkle"):  # искорки инея
        for _ in range(int(bw * bh / (2500 * k * k))):
            x, y = bb[0] + rnd.random() * bw, bb[1] + rnd.random() * bh
            s = rnd.uniform(3, 8) * k
            d.line([(x - s, y), (x + s, y)], fill=(255, 255, 255, 255), width=2)
            d.line([(x, y - s), (x, y + s)], fill=(255, 255, 255, 255), width=2)
    if st.get("shine"):  # глянцевый блик сверху
        sh = gradient((bw, bh // 2), ["#FFFFFF", "#FFFFFF"])
        a = Image.linear_gradient("L").resize((bw, bh // 2)).point(lambda v: int((255 - v) * 0.35))
        sh.putalpha(a)
        fill.alpha_composite(sh, (bb[0], bb[1]))
    if st.get("q") and q:  # знак вопроса — акцентный цвет героя
        qf = Image.new("RGBA", (W, H), hexc(st["q"]))
        fill = Image.composite(qf, fill, m_q)

    fill.putalpha(ImageChops.multiply(fill.getchannel("A"), m_all))

    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if st.get("shadow"):
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sh.putalpha(m_all.point(lambda v: v * 0.6).filter(ImageFilter.GaussianBlur(14 * k)))
        out.alpha_composite(sh, (0, int(6 * k)))
    if st.get("glow"):
        col, rad, n = st["glow"]
        gl = Image.new("RGBA", (W, H), hexc(col))
        gl.putalpha(m_all.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(rad * k)))
        for _ in range(n):
            out.alpha_composite(gl)
    if st.get("stroke"):
        col, wpx = st["stroke"]
        wpx = max(2, round(wpx * k))
        sm = m_all.filter(ImageFilter.MaxFilter(2 * wpx + 1))
        sl = Image.new("RGBA", (W, H), hexc(col))
        sl.putalpha(sm)
        out.alpha_composite(sl)
    out.alpha_composite(fill)
    return out


def white_text_layer(lines, size=96, weight=600, spacing=0):
    """lines: [(text, y_baseline)] — белый текст с мягкой тенью."""
    f = font(size, weight)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    for txt, y in lines:
        if spacing:
            total = sum(f.getlength(ch) for ch in txt) + spacing * (len(txt) - 1)
            x = (W - total) / 2
            for ch in txt:
                d.text((x, y), ch, font=f, fill=255, anchor="ls")
                x += f.getlength(ch) + spacing
        else:
            d.text((W / 2, y), txt, font=f, fill=255, anchor="ms")
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh.putalpha(m.point(lambda v: v * 0.7).filter(ImageFilter.GaussianBlur(10)))
    lay.alpha_composite(sh, (0, 4))
    wl = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    wl.putalpha(m)
    lay.alpha_composite(wl)
    return lay


def swatch_layers(colors, cy, r):
    """Отдельный слой на каждый кружок палитры (для поочерёдного появления)."""
    n = len(colors)
    gap = r * 2 + int(r * 0.6)
    x0 = W / 2 - gap * (n - 1) / 2
    layers = []
    for i, c in enumerate(colors):
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        x = x0 + i * gap
        sh = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sh).ellipse((x - r, cy - r + 6, x + r, cy + r + 6), fill=150)
        shl = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        shl.putalpha(sh.filter(ImageFilter.GaussianBlur(8)))
        lay.alpha_composite(shl)
        d = ImageDraw.Draw(lay)
        ring = max(4, r // 8)
        d.ellipse((x - r - ring, cy - r - ring, x + r + ring, cy + r + ring), fill=(255, 255, 255, 255))
        d.ellipse((x - r, cy - r, x + r, cy + r), fill=hexc(c))
        layers.append(lay)
    return layers


def scrim(y0=1000, y1=1750, peak=120):
    s = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    mid, half = (y0 + y1) / 2, (y1 - y0) / 2
    for y in range(y0, y1):
        t = 1 - abs(y - mid) / half
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(peak * max(0, t) ** 1.2)))
    return s


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def with_alpha(layer, a):
    if a >= 1:
        return layer
    L = layer.copy()
    L.putalpha(L.getchannel("A").point(lambda v: int(v * a)))
    return L


def entry_info(vid_id):
    q = {x["id"]: x for x in json.load(open(os.path.join(ROOT, "queue.json")))}
    e = q[vid_id]
    fc = e.get("first_comment", "")
    colors = re.findall(r"#[0-9A-Fa-f]{6}", fc)[:6]
    m = re.search(r"🎨\s*(?:a |an |the )?(.+?) palette", fc)
    name = COVER_NAMES.get(vid_id) or (m.group(1).strip() if m else vid_id)
    return e, colors, name


def render_frames(vid_id, bg):
    st = STYLES[vid_id]
    _, colors, _ = entry_info(vid_id)
    l1, l2, word = HOOKS.get(vid_id, DESIGNER)
    top = white_text_layer([(l1, 1230), (l2, 1340)])
    des = styled_word(bg, st, word, 1440)
    sw = swatch_layers(colors, 1610, 30)
    scr = scrim(1000, 1760, 130)
    n = int(round((T_HOLD_END + T_OUT) * FPS))
    for i in range(n):
        t = i / FPS
        fr = bg.copy().convert("RGBA")
        if t >= T_IMG:
            out_a = 1 - ease((t - T_HOLD_END) / T_OUT) if t > T_HOLD_END else 1.0
            a_top = ease((t - T_IMG) / T_IN) * out_a
            a_des = ease((t - T_IMG - 0.12) / T_IN) * out_a
            fr.alpha_composite(with_alpha(scr, min(a_top * 1.5, 1) * out_a))
            fr.alpha_composite(with_alpha(top, a_top), (0, int(30 * (1 - ease((t - T_IMG) / T_IN)))))
            if a_des > 0:
                L = des
                if a_des < 1:  # лёгкий «поп» слова
                    k = 0.88 + 0.12 * ease((t - T_IMG - 0.12) / T_IN)
                    tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    tmp.alpha_composite(des.resize((int(W * k), int(H * k)), Image.BICUBIC),
                                       (int(W / 2 * (1 - k)), int(1440 * (1 - k))))
                    L = tmp
                fr.alpha_composite(with_alpha(L, a_des))
            for j, lay in enumerate(sw):  # кружки палитры «выпрыгивают» по очереди
                a = ease((t - T_IMG - 0.3 - j * 0.07) / 0.2) * out_a
                if a > 0:
                    fr.alpha_composite(with_alpha(lay, a), (0, int(20 * (1 - a))))
        yield fr.convert("RGB")


def make_cover(vid_id, bg):
    st = STYLES[vid_id]
    _, colors, name = entry_info(vid_id)
    fr = bg.copy().convert("RGBA")
    # сетка профиля показывает центр 3:4 (y 240–1680) — всё важное внутри
    fr.alpha_composite(scrim(950, 1800, 175))
    fr.alpha_composite(white_text_layer([("COLOUR PALETTE", 1170)], size=46, weight=600, spacing=10))
    fr.alpha_composite(styled_word(bg, st, name, 1260, size=170, max_w=960))
    for lay in swatch_layers(colors, 1500, 50):
        fr.alpha_composite(lay)
    out = os.path.join(ROOT, "covers", f"{vid_id}.jpg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fr.convert("RGB").save(out, "JPEG", quality=90, optimize=True)
    return out


def src_video(vid_id, tmp):
    path = os.path.join(tmp, f"src_{vid_id}.mp4")
    with open(path, "wb") as fh:
        subprocess.run(["git", "-C", ROOT, "show", f"{SRC_REF}:videos/{vid_id}.mp4"], stdout=fh, check=True)
    return path


def hero_frame(vid_id, tmp):
    src = src_video(vid_id, tmp)
    bgp = os.path.join(tmp, f"bg_{vid_id}.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(CUT - 0.05), "-i", src, "-frames:v", "1", bgp], check=True)
    return src, bgp, Image.open(bgp).convert("RGB")


def build(vid_id, tmp):
    e, _, _ = entry_info(vid_id)
    src, bgp, bg = hero_frame(vid_id, tmp)
    make_cover(vid_id, bg)
    intro = os.path.join(tmp, f"intro_{vid_id}.mp4")
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                          "-pix_fmt", "yuv420p", intro], stdin=subprocess.PIPE)
    for fr in render_frames(vid_id, bg):
        p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait()
    total = T_HOLD_END + T_OUT + (22.0 - CUT)
    loop = 0.5
    out = os.path.join(ROOT, "videos", f"{vid_id}.mp4")
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", intro, "-ss", str(CUT), "-i", src, "-i", os.path.join(ROOT, e["music"]),
        "-loop", "1", "-t", str(loop + 0.2), "-framerate", str(FPS), "-i", bgp,
        "-filter_complex",
        f"[0:v]settb=1/{FPS},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p[a];"
        f"[1:v]fps={FPS},setpts=PTS-STARTPTS,format=yuv420p[b];[a][b]concat=n=2:v=1:a=0,settb=1/{FPS}[m];"
        f"[3:v]fps={FPS},format=yuv420p,settb=1/{FPS}[still];"
        f"[m][still]xfade=transition=fade:duration={loop}:offset={total - loop}[v];"
        f"[2:a]atrim=0:{total},afade=t=out:st={total - 1}:d=1[au]",
        "-map", "[v]", "-map", "[au]", "-t", str(total), "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", out], check=True)
    return out


if __name__ == "__main__":
    tmp = os.environ.get("TMPDIR_HOOK", "/tmp")
    os.makedirs(tmp, exist_ok=True)
    if sys.argv[1] == "--preview":
        vid, out = sys.argv[2], sys.argv[3]
        _, _, bg = hero_frame(vid, tmp)
        for i, fr in enumerate(render_frames(vid, bg)):
            if i == int(2.2 * FPS):
                fr.save(out)
                break
        sys.exit()
    if sys.argv[1] == "--cover":
        for vid in sys.argv[2:]:
            print(make_cover(vid, hero_frame(vid, tmp)[2]))
        sys.exit()
    for vid in sys.argv[1:]:
        print(build(vid, tmp))
