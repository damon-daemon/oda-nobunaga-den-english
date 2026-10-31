"""Redraw the Japanese floating battle labels of GRAPHIC/HEX_EFF.E4 in English.

HEX_EFF.E4 is 57 columns of 32x96 4bpp pixels (0x600 bytes each: three 32x32 animation
frames stacked), uploaded by 0x8003f8ec to VRAM x 896+ (columns 0-32 = hex effect icons,
33-48 and 49-56 = the labels shown over a unit when a stat changes or a status is applied).
A label is drawn by 0x8003fa68 (sprite n -> column 33 + n, frame 0-2; CLUT 0x60 +
0x80106850[n] from CHR_PAL.E4).

Labels 0-7, 12-14 and 19-23 are a stat name on a triangle (up = rose, down = fell): the
triangle (colours 9-14) is rebuilt from all labels of the same direction (it is the same
in every one), the English is drawn with the VWF pixel font in the original's row colours
(a vertical gradient) with the dark outline (colour 1). Labels 8-11 (status applied) and
15-18 (status cured) grow over the three frames: frames 0-1 get the text scaled down,
frame 2 the text over the glow/ring, whose hidden middle is inpainted ring by ring.

tl/hexeff.txt: "index<TAB>English" (0-23); labels without a line are left as they are.

  python tools/hexeff.py preview out.png    labels before/after (needs extract/)
"""
import collections, math, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import pixfont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = os.path.join(ROOT, 'tl', 'hexeff.txt')
ISO_NAME = 'GRAPHIC/HEX_EFF.E4'
PAL_NAME = 'GRAPHIC/CHR_PAL.E4'
COL, FIRST, COUNT, W, H, FRAMES = 0x600, 33, 24, 32, 32, 3
UP = (0, 1, 3, 5, 6, 7, 19, 20, 21, 22, 23)
DOWN = (2, 4, 12, 13, 14)
STATUS = (8, 9, 10, 11, 15, 16, 17, 18)
CLUT = [0x17] * 8 + [0x15] * 4 + [0x17] * 3 + [0x16] * 4 + [0x17] * 5     # 0x80106850
TRI = range(9, 15)                  # triangle colours
OUTLINE = 1
TEXT_ROWS = (8, 26)                 # rows of the kanji (status labels, frame 2)
SCALE = (0.5, 0.72)                 # text size of the status frames 0 and 1
CAPS = 9                            # pixfont capital height (rows 0-8 of the cell)


def load_tl(path=TL):
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#'):
            continue
        k, _, en = line.partition('\t')
        out[int(k)] = en
    return out


class Sheet:
    def __init__(self, data):
        self.d = bytearray(data)

    def get(self, n, f, x, y):
        b = self.d[COL * (FIRST + n) + (32 * f + y) * 16 + x // 2]
        return b >> 4 if x & 1 else b & 15

    def put(self, n, f, x, y, i):
        o = COL * (FIRST + n) + (32 * f + y) * 16 + x // 2
        self.d[o] = (self.d[o] & 0x0f) | (i << 4) if x & 1 else (self.d[o] & 0xf0) | i

    def frame(self, n, f):
        return [[self.get(n, f, x, y) for x in range(W)] for y in range(H)]


def triangle(sh, labels, f):
    """The triangle of frame f common to labels: colour per pixel (0 = outside)."""
    t = [[0] * W for _ in range(H)]
    for n in labels:
        for y in range(H):
            for x in range(W):
                v = sh.get(n, f, x, y)
                if v in TRI and not t[y][x]:
                    t[y][x] = v
    for y in range(H):                      # a row is one colour: close the gaps
        xs = [x for x in range(W) if t[y][x]]
        if xs:
            c = collections.Counter(t[y][x] for x in xs).most_common(1)[0][0]
            for x in range(min(xs), max(xs) + 1):
                t[y][x] = c
    return t


def text_pixels(text, g):
    """{(x, y)} of text in the pixel font, x from 0, y 0 = cap top."""
    ink, x = set(), 0
    for c in text:
        rows, adv = g[c]
        for r in range(pixfont.CELL_H):
            for i in range(pixfont.CELL_W):
                if rows[r] & (0x80 >> i):
                    ink.add((x + i, r))
        x += adv
    return ink


def scaled(ink, s):
    """ink scaled by s (< 1): a target pixel is set when any source pixel maps into it."""
    return {(int(x * s), int(y * s)) for x, y in ink}


def place(ink, cx, cy):
    """Centre ink (its bounding box) on (cx, cy) -> {(x, y)}; raises if it leaves the sprite."""
    xs = [x for x, _ in ink]
    ys = [y for _, y in ink]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    ox, oy = cx - (x0 + x1 + 1) // 2, cy - (y0 + y1 + 1) // 2
    out = {(x + ox, y + oy) for x, y in ink}
    if any(not (1 <= x < W - 1 and 1 <= y < H - 1) for x, y in out):
        raise ValueError('text %d px does not fit the 32 px label' % (x1 - x0 + 1))
    return out


def paint(fr, ink, colour):
    """Draw ink pixels into frame fr (list of rows) with colour (per row if a dict) and
    the outline around them."""
    for x, y in ink:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (x + dx, y + dy) not in ink and 0 <= x + dx < W and 0 <= y + dy < H:
                    fr[y + dy][x + dx] = OUTLINE
    for x, y in ink:
        fr[y][x] = colour[y] if isinstance(colour, dict) else colour


def row_colours(fr, cands):
    """Dominant text colour per row of the original frame (nearest row where none)."""
    rows = {}
    for y in range(H):
        c = collections.Counter(v for v in fr[y] if v in cands)
        if c:
            rows[y] = c.most_common(1)[0][0]
    return {y: rows[min(rows, key=lambda r: abs(r - y))] for y in range(H)}


def dominant(fr, y0, y1):
    c = collections.Counter(v for y in range(y0, y1) for v in fr[y] if v not in (0, OUTLINE))
    return c.most_common(1)[0][0]


def arrow(sh, n, text, tri, g):
    """Stat label: English on the rebuilt triangle, row colours like the original's."""
    for f in range(FRAMES):
        orig = sh.frame(n, f)
        colours = row_colours(orig, range(2, 9))
        fr = [row[:] for row in tri[f]]
        paint(fr, place(text_pixels(text, g), W // 2, H // 2), colours)
        write(sh, n, f, fr)


def inpaint_rings(fr, y0, y1):
    """Fill rows y0..y1-1 from the pixels outside them at the same distance from the centre."""
    cx = cy = (W - 1) / 2
    known = [(math.hypot(x - cx, y - cy), x, y) for y in range(H) for x in range(W) if not y0 <= y < y1]
    known.sort()
    for y in range(y0, y1):
        for x in range(W):
            r = math.hypot(x - cx, y - cy)
            best = min(known, key=lambda k: (abs(k[0] - r), abs(k[1] - x) + abs(k[2] - y)))
            fr[y][x] = fr[best[2]][best[1]]


def status(sh, n, text, g):
    """Status label: scaled text on the empty frames 0-1, text over the inpainted glow on 2."""
    full = text_pixels(text, g)
    for f in range(FRAMES):
        orig = sh.frame(n, f)
        colour = dominant(orig, *TEXT_ROWS)
        if f < 2:
            fr = [[0] * W for _ in range(H)]
            ink = place(scaled(full, SCALE[f]), W // 2, H // 2)
        else:
            fr = [row[:] for row in orig]
            inpaint_rings(fr, *TEXT_ROWS)
            ink = place(full, W // 2, H // 2)
        paint(fr, ink, colour)
        write(sh, n, f, fr)


def write(sh, n, f, fr):
    for y in range(H):
        for x in range(W):
            sh.put(n, f, x, y, fr[y][x])


def build(data, tl=None, strict=True):
    """-> (new HEX_EFF.E4 bytes, number of labels)."""
    tl = load_tl() if tl is None else tl
    sh = Sheet(data)
    g = pixfont.glyphs()
    tri = {'up': [triangle(sh, UP, f) for f in range(FRAMES)],
           'down': [triangle(sh, DOWN, f) for f in range(FRAMES)]}
    errs = []
    for n, en in sorted(tl.items()):
        try:
            if n in UP or n in DOWN:
                arrow(sh, n, en, tri['up' if n in UP else 'down'], g)
            elif n in STATUS:
                status(sh, n, en, g)
            else:
                raise ValueError('not a label')
        except ValueError as e:
            errs.append('hexeff %d %r: %s' % (n, en, e))
    if errs and strict:
        raise ValueError('\n'.join(errs))
    for e in errs:
        print(e)
    return bytes(sh.d), len(tl)


def image(data, pal, scale=3):
    """The 24 labels (3 frames) as RGB in their CLUTs (preview)."""
    from PIL import Image
    sh = Sheet(data)
    cluts = []
    for c in CLUT:
        b = pal[32 * c:32 * c + 32]
        cluts.append([(((v & 31) << 3), (((v >> 5) & 31) << 3), (((v >> 10) & 31) << 3))
                      for v in (b[2 * i] | (b[2 * i + 1] << 8) for i in range(16))])
    im = Image.new('RGB', (W * COUNT, H * FRAMES), (255, 0, 255))
    for n in range(COUNT):
        for f in range(FRAMES):
            for y in range(H):
                for x in range(W):
                    v = sh.get(n, f, x, y)
                    if v:
                        im.putpixel((W * n + x, H * f + y), cluts[n][v])
    return im.resize((im.width * scale, im.height * scale), Image.NEAREST)


def main():
    a = sys.argv[1:]
    if a[:1] == ['preview']:
        from PIL import Image
        data = open(os.path.join(ROOT, 'extract', ISO_NAME), 'rb').read()
        pal = open(os.path.join(ROOT, 'extract', PAL_NAME), 'rb').read()
        before = image(data, pal)
        new, n = build(data, strict=False)
        after = image(new, pal)
        out = Image.new('RGB', (before.width, before.height * 2 + 6), (0, 0, 0))
        out.paste(before, (0, 0))
        out.paste(after, (0, before.height + 6))
        out.save(a[1])
        print('%d labels' % n)
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
