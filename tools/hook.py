#!/usr/bin/env python3
"""Пересобирает начало рилса: быстрый хук «What if nature were your designer?».

Таймлайн нового начала:
  0.00–1.00  чистый кадр героя (без текста)
  1.00–2.55  текст; «designer?» оформлен в стиле героя (STYLES ниже)
  2.55–2.75  текст гаснет
  дальше     исходное видео с 3.75 с (подписи палитры → Wear/Style/Live → карточка)

Использование:
  python3 tools/hook.py <id> [<id> ...]        # пересобрать videos/<id>.mp4 (исходник берётся из git: SRC_REF)
  python3 tools/hook.py --preview <id> out.png # только кадр с текстом
Музыка берётся из поля "music" в queue.json.
"""
import json, os, random, subprocess, sys
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


def designer_layer(bg, st, cy):
    """RGBA слой со словом designer? в стиле героя."""
    f = font(190, 700)
    word, q = "designer", "?"
    ww = f.getlength(word + q)
    x0 = (W - ww) / 2
    base = cy + 55
    m_word = text_mask(word, f, (W, H), (x0 + f.getlength(word) / 2, base))
    m_q = text_mask(q, f, (W, H), (x0 + f.getlength(word) + f.getlength(q) / 2, base))
    m_all = ImageChops.lighter(m_word, m_q)
    bb = m_all.getbbox()
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]

    kind, arg = st["fill"]
    if kind == "texture":
        x0f, y0f, x1f, y1f = arg
        crop = bg.crop((int(x0f * W), int(y0f * H), int(x1f * W), int(y1f * H)))
        # cover-resize под рамку слова
        s = max(bw / crop.width, bh / crop.height)
        crop = crop.resize((int(crop.width * s) + 1, int(crop.height * s) + 1), Image.LANCZOS)
        cx, cy2 = (crop.width - bw) // 2, (crop.height - bh) // 2
        crop = crop.crop((cx, cy2, cx + bw, cy2 + bh))
        crop = ImageEnhance.Color(crop).enhance(st.get("boost", 1.0))
        crop = ImageEnhance.Brightness(crop).enhance(st.get("bright", 1.0))
        fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fill.paste(crop.convert("RGBA"), (bb[0], bb[1]))
    elif kind == "hgradient":
        fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fill.paste(gradient((bh, bw), arg).rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT), (bb[0], bb[1]))
    else:
        fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fill.paste(gradient((bw, bh), arg), (bb[0], bb[1]))

    d = ImageDraw.Draw(fill)
    rnd = random.Random(7)
    if st.get("dots"):  # пятнышки божьей коровки
        for _ in range(int(bw * bh / 5200)):
            x, y = bb[0] + rnd.random() * bw, bb[1] + rnd.random() * bh
            r = rnd.uniform(9, 15)
            d.ellipse((x - r, y - r, x + r, y + r), fill=hexc(st["dots"]))
    if st.get("speckles"):  # крапинки полярной совы
        for _ in range(int(bw * bh / 1500)):
            x, y = bb[0] + rnd.random() * bw, bb[1] + rnd.random() * bh
            s = rnd.uniform(5, 10)
            d.polygon([(x - s, y - s * 0.3), (x, y + s * 0.5), (x + s, y - s * 0.3), (x, y + s * 0.1)],
                      fill=hexc(st["speckles"], 230))
    if st.get("stripes"):  # ступени рисовых террас
        import math
        for k in range(9):
            y0 = bb[1] + bh * (k + 0.5) / 9
            pts = [(bb[0] + x, y0 + 6 * math.sin(x / 90 + k)) for x in range(0, bw + 1, 8)]
            d.line(pts, fill=hexc(st["stripes"], 200), width=4)
    if st.get("ripples"):  # рябь песчаных дюн
        import math
        for k in range(8):
            y0 = bb[1] + bh * (k + 0.5) / 8
            pts = [(bb[0] + x, y0 + 9 * math.sin(x / 55 + k * 1.7)) for x in range(0, bw + 1, 6)]
            d.line(pts, fill=hexc(st["ripples"], 190), width=5)
    if st.get("sparkle"):  # искорки инея
        for _ in range(int(bw * bh / 2500)):
            x, y = bb[0] + rnd.random() * bw, bb[1] + rnd.random() * bh
            s = rnd.uniform(3, 8)
            d.line([(x - s, y), (x + s, y)], fill=(255, 255, 255, 255), width=2)
            d.line([(x, y - s), (x, y + s)], fill=(255, 255, 255, 255), width=2)
    if st.get("shine"):  # глянцевый блик сверху
        sh = gradient((bw, bh // 2), ["#FFFFFF", "#FFFFFF"])
        a = Image.linear_gradient("L").resize((bw, bh // 2)).point(lambda v: int((255 - v) * 0.35))
        sh.putalpha(a)
        fill.alpha_composite(sh, (bb[0], bb[1]))
    if st.get("q"):  # знак вопроса — акцентный цвет героя (глаз совы, сердцевина подсолнуха…)
        qf = Image.new("RGBA", (W, H), hexc(st["q"]))
        fill = Image.composite(qf, fill, m_q)

    fill.putalpha(ImageChops.multiply(fill.getchannel("A"), m_all))

    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if st.get("shadow"):
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sh.putalpha(m_all.point(lambda v: v * 0.6).filter(ImageFilter.GaussianBlur(14)))
        out.alpha_composite(sh, (0, 6))
    if st.get("glow"):
        col, rad, n = st["glow"]
        gl = Image.new("RGBA", (W, H), hexc(col))
        gl.putalpha(m_all.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(rad)))
        for _ in range(n):
            out.alpha_composite(gl)
    if st.get("stroke"):
        col, wpx = st["stroke"]
        sm = m_all.filter(ImageFilter.MaxFilter(2 * wpx + 1))
        sl = Image.new("RGBA", (W, H), hexc(col))
        sl.putalpha(sm)
        out.alpha_composite(sl)
    out.alpha_composite(fill)
    return out


def top_lines_layer():
    f = font(96, 600)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    d.text((W / 2, 1230), "What if nature", font=f, fill=255, anchor="ms")
    d.text((W / 2, 1340), "were your", font=f, fill=255, anchor="ms")
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh.putalpha(m.point(lambda v: v * 0.7).filter(ImageFilter.GaussianBlur(10)))
    lay.alpha_composite(sh, (0, 4))
    wl = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    wl.putalpha(m)
    lay.alpha_composite(wl)
    return lay


def scrim():
    s = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    for y in range(1000, 1750):
        t = 1 - abs(y - 1375) / 375
        d.line([(0, y), (W, y)], fill=(0, 0, 0, int(120 * max(0, t) ** 1.2)))
    return s


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def render_frames(vid_id, bg):
    st = STYLES[vid_id]
    top = top_lines_layer()
    des = designer_layer(bg, st, 1440)
    scr = scrim()
    n = int(round((T_HOLD_END + T_OUT) * FPS))
    for i in range(n):
        t = i / FPS
        fr = bg.copy().convert("RGBA")
        if t >= T_IMG:
            out_a = 1 - ease((t - T_HOLD_END) / T_OUT) if t > T_HOLD_END else 1.0
            a_top = ease((t - T_IMG) / T_IN) * out_a
            a_des = ease((t - T_IMG - 0.12) / T_IN) * out_a
            for layer, a, dy in ((scr, min(a_top * 1.5, 1) * out_a, 0),
                                 (top, a_top, int(30 * (1 - ease((t - T_IMG) / T_IN)))),
                                 (des, a_des, 0)):
                if a <= 0:
                    continue
                L = layer
                if layer is des and a_des < 1:  # лёгкий «поп» слова
                    k = 0.88 + 0.12 * ease((t - T_IMG - 0.12) / T_IN)
                    L = layer.resize((int(W * k), int(H * k)), Image.BICUBIC)
                    tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    cx, cy = W / 2, 1440
                    tmp.alpha_composite(L, (int(cx - cx * k), int(cy - cy * k)))
                    L = tmp
                if a < 1:
                    L = L.copy()
                    L.putalpha(L.getchannel("A").point(lambda v: int(v * a)))
                fr.alpha_composite(L, (0, dy))
        yield fr.convert("RGB")


def src_video(vid_id, tmp):
    path = os.path.join(tmp, f"src_{vid_id}.mp4")
    with open(path, "wb") as fh:
        subprocess.run(["git", "-C", ROOT, "show", f"{SRC_REF}:videos/{vid_id}.mp4"], stdout=fh, check=True)
    return path


def build(vid_id, tmp, music):
    src = src_video(vid_id, tmp)
    bgp = os.path.join(tmp, f"bg_{vid_id}.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(CUT - 0.05), "-i", src, "-frames:v", "1", bgp], check=True)
    bg = Image.open(bgp).convert("RGB")
    intro = os.path.join(tmp, f"intro_{vid_id}.mp4")
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                          "-pix_fmt", "yuv420p", intro], stdin=subprocess.PIPE)
    for fr in render_frames(vid_id, bg):
        p.stdin.write(fr.tobytes())
    p.stdin.close(); p.wait()
    total = T_HOLD_END + T_OUT + (22.0 - CUT)
    out = os.path.join(ROOT, "videos", f"{vid_id}.mp4")
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", intro, "-ss", str(CUT), "-i", src, "-i", os.path.join(ROOT, music),
        "-filter_complex",
        f"[0:v]settb=1/{FPS},setpts=PTS-STARTPTS,fps={FPS}[a];[1:v]fps={FPS},setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[v];"
        f"[2:a]atrim=0:{total},afade=t=out:st={total - 1}:d=1[au]",
        "-map", "[v]", "-map", "[au]", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-movflags", "+faststart", out],
        check=True)
    return out


if __name__ == "__main__":
    tmp = os.environ.get("TMPDIR_HOOK", "/tmp")
    os.makedirs(tmp, exist_ok=True)
    if sys.argv[1] == "--preview":
        vid, out = sys.argv[2], sys.argv[3]
        src = src_video(vid, tmp)
        bgp = os.path.join(tmp, f"bg_{vid}.png")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(CUT - 0.05), "-i", src, "-frames:v", "1", bgp], check=True)
        for i, fr in enumerate(render_frames(vid, Image.open(bgp).convert("RGB"))):
            if i == int(2.2 * FPS):
                fr.save(out)
                break
        sys.exit()
    q = {x["id"]: x for x in json.load(open(os.path.join(ROOT, "queue.json")))}
    for vid in sys.argv[1:]:
        print(build(vid, tmp, q[vid]["music"]))
