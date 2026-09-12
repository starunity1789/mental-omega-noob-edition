"""Cameo (sidebar icon) generator for the starunity support powers.

Mental Omega cameos are 60x48 8-bit PCX with an embedded palette, referenced
from artmo.ini via `CameoPCX=` (units/buildings) and from rulesmo.ini via
`SidebarPCX=` (superweapons).

Icons are drawn at 4x and downsampled so edges and glyphs stay clean at 60x48.
"""
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 60, 48
S = 4                      # supersample factor
FONT = "C:/Windows/Fonts/simhei.ttf"

FACTIONS = {
    "allied":  {"label": "盟军", "color": (58, 120, 214),  "dark": (18, 38, 74)},
    "soviet":  {"label": "苏军", "color": (198, 46, 44),   "dark": (68, 16, 16)},
    "epsilon": {"label": "厄普", "color": (140, 74, 196),  "dark": (44, 22, 66)},
    "foehn":   {"label": "焚风", "color": (32, 176, 160),  "dark": (12, 56, 54)},
}

BAND_H = 13                # height of the bottom label band, in final pixels
FRAME = 2                  # frame thickness, in final pixels


def _font(px):
    return ImageFont.truetype(FONT, px)


def _centered_text(d, box, text, font, fill):
    x0, y0, x1, y1 = box
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    d.text((x0 + (x1 - x0 - (r - l)) / 2 - l,
            y0 + (y1 - y0 - (b - t)) / 2 - t), text, font=font, fill=fill)


def _finish(big):
    """Downsample the 4x canvas and quantize to a 256-colour palette."""
    im = big.resize((W, H), Image.LANCZOS)
    return im.convert("P", palette=Image.ADAPTIVE, colors=256)


def _band_and_frame(big, label, color, dark):
    """Draw the faction colour frame and the bottom label band."""
    d = ImageDraw.Draw(big)
    bh, fr = BAND_H * S, FRAME * S
    # bottom band
    d.rectangle([0, H * S - bh, W * S - 1, H * S - 1], fill=dark)
    d.rectangle([0, H * S - bh, W * S - 1, H * S - bh + S], fill=color)
    _centered_text(d, (0, H * S - bh + S, W * S, H * S - S),
                   label, _font(int(bh * 0.74)), (255, 255, 255))
    # frame
    for i in range(fr):
        d.rectangle([i, i, W * S - 1 - i, H * S - 1 - i], outline=color)


def mcv_icon(base_pcx, faction, out_path):
    """Stock faction MCV cameo + faction frame + faction label band."""
    f = FACTIONS[faction]
    big = Image.open(base_pcx).convert("RGB").resize((W * S, H * S), Image.LANCZOS)
    _band_and_frame(big, f["label"], f["color"], f["dark"])
    im = _finish(big)
    im.save(out_path)
    return out_path


def _backdrop(top, bottom):
    big = Image.new("RGB", (W * S, H * S))
    d = ImageDraw.Draw(big)
    for y in range(H * S):
        t = y / (H * S - 1)
        d.line([(0, y), (W * S, y)],
               fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return big


# Art lives strictly inside the frame and above the label band:
# x 3..57, y 3..34 in final pixels.  Design coordinates below are final
# pixels; _p() scales them onto the 4x canvas.
ART = (3, 3, 57, 34)


def _p(x, y):
    return (x * S, y * S)


def _poly(d, pts, fill, outline=None, w=None):
    d.polygon([_p(*q) for q in pts], fill=fill, outline=outline, width=w or max(1, S // 2))


def hybrid_tower_icon(out_path):
    """Hybrid Tower: armoured pylon with a charged coil and twin emitters."""
    color, dark = (60, 195, 210), (10, 44, 52)
    big = _backdrop((26, 58, 68), (6, 14, 20))
    d = ImageDraw.Draw(big)
    cx, gy = 30, 32                      # centre / ground line
    steel, edge, shade = (124, 138, 150), (196, 212, 224), (70, 82, 92)

    d.ellipse([_p(cx - 17, gy - 3), _p(cx + 17, gy + 2)], fill=(8, 22, 28))
    # stepped plinth
    _poly(d, [(cx - 15, gy), (cx + 15, gy), (cx + 12, gy - 4), (cx - 12, gy - 4)], shade, edge)
    _poly(d, [(cx - 11, gy - 4), (cx + 11, gy - 4), (cx + 8, gy - 8), (cx - 8, gy - 8)], steel, edge)
    # shaft with a lit seam
    _poly(d, [(cx - 6, gy - 8), (cx + 6, gy - 8), (cx + 4, gy - 19), (cx - 4, gy - 19)], steel, edge)
    d.rectangle([_p(cx - 1, gy - 18), _p(cx + 1, gy - 9)], fill=color)
    # twin side emitters (the "hybrid" part: ground + air)
    for sx in (-1, 1):
        _poly(d, [(cx + sx * 6, gy - 12), (cx + sx * 12, gy - 15),
                  (cx + sx * 12, gy - 18), (cx + sx * 6, gy - 16)], shade, edge)
        d.ellipse([_p(cx + sx * 12 - 1.6, gy - 18), _p(cx + sx * 12 + 1.6, gy - 15)],
                  fill=(206, 250, 255))
    # coil head
    _poly(d, [(cx - 8, gy - 19), (cx + 8, gy - 19), (cx + 5, gy - 23), (cx - 5, gy - 23)], edge)
    for i, yy in enumerate((gy - 24, gy - 26)):
        d.rectangle([_p(cx - 5 + i, yy - 1), _p(cx + 5 - i, yy)], fill=steel, outline=edge)
    # discharge
    d.line([_p(cx, gy - 27), _p(cx - 4, gy - 30), _p(cx + 2, gy - 31), _p(cx - 1, gy - 34)],
           fill=(210, 250, 255), width=int(1.2 * S))
    d.line([_p(cx, gy - 27), _p(cx + 5, gy - 30), _p(cx + 3, gy - 32)],
           fill=color, width=max(1, int(0.8 * S)))
    d.ellipse([_p(cx - 3, gy - 29), _p(cx + 3, gy - 25)], fill=(235, 253, 255))
    _band_and_frame(big, "混合塔", color, dark)
    im = _finish(big)
    im.save(out_path)
    return out_path


def decimator_icon(out_path):
    """Shin Tsurugi Decimator: heavy walker holding a raised blade."""
    color, dark = (232, 142, 44), (62, 30, 8)
    big = _backdrop((62, 44, 26), (12, 9, 8))
    d = ImageDraw.Draw(big)
    cx, gy = 26, 32
    steel, edge, shade = (122, 124, 134), (196, 202, 214), (66, 68, 78)

    d.ellipse([_p(cx - 15, gy - 3), _p(cx + 19, gy + 2)], fill=(16, 11, 8))
    # legs: thigh wedge + planted foot
    for sx in (-1, 1):
        _poly(d, [(cx + sx * 3, gy - 15), (cx + sx * 8, gy - 15),
                  (cx + sx * 10, gy - 7), (cx + sx * 5, gy - 7)], steel, edge)
        _poly(d, [(cx + sx * 5, gy - 7), (cx + sx * 11, gy - 7),
                  (cx + sx * 12, gy - 1), (cx + sx * 4, gy - 1)], shade, edge)
    # torso
    _poly(d, [(cx - 9, gy - 15), (cx + 9, gy - 15), (cx + 8, gy - 24), (cx - 8, gy - 24)], steel, edge)
    d.rectangle([_p(cx - 5, gy - 22), _p(cx + 5, gy - 18)], fill=(38, 40, 48))
    d.rectangle([_p(cx - 4, gy - 21), _p(cx + 4, gy - 20)], fill=color)
    # shoulder pods
    for sx in (-1, 1):
        _poly(d, [(cx + sx * 8, gy - 24), (cx + sx * 13, gy - 23),
                  (cx + sx * 13, gy - 18), (cx + sx * 8, gy - 18)], shade, edge)
    # head
    _poly(d, [(cx - 3, gy - 24), (cx + 3, gy - 24), (cx + 2, gy - 28), (cx - 2, gy - 28)], edge)
    d.rectangle([_p(cx - 1.4, gy - 27), _p(cx + 1.4, gy - 26)], fill=(255, 214, 126))
    # raised blade in the right hand
    bx = cx + 15
    d.rectangle([_p(bx - 3, gy - 21), _p(bx + 3, gy - 18)], fill=color, outline=edge)
    d.line([_p(bx, gy - 21), _p(bx, gy - 24)], fill=steel, width=int(1.2 * S))
    _poly(d, [(bx - 2.4, gy - 24), (bx + 2.4, gy - 24), (bx + 2.0, gy - 31),
              (bx, gy - 34), (bx - 2.0, gy - 31)], (222, 232, 244), (255, 255, 255))
    d.line([_p(bx, gy - 32), _p(bx, gy - 24)], fill=(158, 170, 186), width=max(1, S // 2))
    _band_and_frame(big, "长剑", color, dark)
    im = _finish(big)
    im.save(out_path)
    return out_path


def contact_sheet(paths, out_png, scale=4):
    ims = [Image.open(p).convert("RGB") for p in paths]
    sheet = Image.new("RGB", (W * len(ims), H), (0, 0, 0))
    for i, im in enumerate(ims):
        sheet.paste(im, (W * i, 0))
    sheet.resize((W * len(ims) * scale, H * scale), Image.NEAREST).save(out_png)
    return out_png
