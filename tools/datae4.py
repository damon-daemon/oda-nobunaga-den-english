"""Name tables of DATA/DATA.E4 other than the officers (names.py): items, battlefields, unit
classes, skills.

The loader (0x800254f8) reads the file whole and copies every section into RAM struct arrays
with fixed name fields (item parser 0x800138b4: name 16 + NUL, kana reading 20 + NUL; class
0x800127c0 and skill 0x8001431c: 10 + NUL; battlefield 0x800142b0: 8 + NUL). English replaces
the name in place (ASCII, NUL-padded), so the file keeps its size and layout. The item reading
(printed beside the name in the item info box) is blanked.

script/data.txt: "table:n<TAB>Japanese[<TAB>reading]" (made by setup.py).
tl/data.txt:     "table:n<TAB>English"; '#' lines are comments.

  datae4.py check     field fit report (bytes and pixels)
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import text, vwf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_E4 = os.path.join(ROOT, 'extract', 'DATA', 'DATA.E4')
SCRIPT = os.path.join(ROOT, 'script', 'data.txt')
TL = os.path.join(ROOT, 'tl', 'data.txt')
ISO_NAME = 'DATA/DATA.E4'
# table: (file offset, record size, count, name cap in characters, reading (offset, size) or None)
TABLES = {'item': (0xc201, 51, 255, 16, (17, 21)),
          'field': (0xf4ce, 15, 52, 8, None),
          'class': (0xf7da, 39, 33, 10, None),
          'skill': (0x101cb, 17, 54, 10, None)}
# item names: widest field = storehouse list (name x 200, quantity at x 284, build.QTY_X_AT;
# the merchant price column is at 128 px from the name)
ITEM_PX = 85
CLASS_PX = 55    # officer list: the unit type runs into the 3-digit Atk column


def _cstr(b):
    return b.split(b'\0')[0].decode('cp932')


def japanese(data=None):
    """-> [(key, name, reading)] of the non-empty records."""
    d = data or open(DATA_E4, 'rb').read()
    out = []
    for t, (off, size, count, cap, rd) in TABLES.items():
        for n in range(count):
            r = d[off + n * size: off + (n + 1) * size]
            name = _cstr(r[:cap + 1])
            if name:
                out.append(('%s:%d' % (t, n), name, _cstr(r[rd[0]:rd[0] + rd[1]]) if rd else ''))
    return out


def export():
    rows = japanese()
    with open(SCRIPT, 'w', encoding='utf-8') as f:
        for k, name, rd in rows:
            f.write('%s\t%s%s\n' % (k, name, '\t' + rd if rd else ''))
    return len(rows)


def load_tl(path=TL):
    out = {}
    if not os.path.exists(path):
        return out
    for ln in open(path, encoding='utf-8').read().splitlines():
        if ln.strip() and not ln.startswith('#'):
            k, _, en = ln.partition('\t')
            out[k] = en.strip()
    return out


def errors(tl):
    errs = []
    for k, en in tl.items():
        t, _, n = k.partition(':')
        if t not in TABLES or not n.isdigit() or int(n) >= TABLES[t][2]:
            errs.append('%s: no such record' % k)
            continue
        e = text.fold(en)
        if text.check(e) or '\\n' in e:
            errs.append('%s: bad characters %r' % (k, en))
        if len(e) > TABLES[t][3]:
            errs.append('%s: %d characters > %d (%s)' % (k, len(e), TABLES[t][3], en))
        if t == 'item' and vwf.width(e) > ITEM_PX:
            errs.append('%s: %d px > %d (%s)' % (k, vwf.width(e), ITEM_PX, en))
        if t == 'class' and vwf.width(e) > CLASS_PX:
            errs.append('%s: %d px > %d (%s)' % (k, vwf.width(e), CLASS_PX, en))
    return errs


def apply(data, tl):
    d = bytearray(data)
    for k, en in tl.items():
        t, _, n = k.partition(':')
        off, size, count, cap, rd = TABLES[t]
        o = off + int(n) * size
        d[o:o + cap + 1] = text.fold(en).encode('ascii').ljust(cap + 1, b'\0')
        if rd:
            d[o + rd[0]:o + rd[0] + rd[1]] = bytes(rd[1])
    return bytes(d)


def build(data):
    """DATA.E4 bytes -> (English bytes, count); exits on errors."""
    tl = load_tl()
    errs = errors(tl)
    if errs:
        sys.exit('\n'.join(errs) + '\n%d errors in tl/data.txt' % len(errs))
    return apply(data, tl), len(tl)


def main():
    tl = load_tl()
    for e in errors(tl):
        print(e)
    rows = japanese()
    missing = [k for k, _, _ in rows if k not in tl]
    wide = sorted(((text.pixels(text.fold(en)), k, en) for k, en in tl.items()), reverse=True)[:10]
    print('%d / %d names translated; widest: %s' % (len(rows) - len(missing), len(rows),
                                                   ', '.join('%s %s %dpx' % (k, en, w) for w, k, en in wide)))


if __name__ == '__main__':
    main()
