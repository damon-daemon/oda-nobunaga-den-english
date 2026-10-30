"""DATA/IMSG.E4: 1,034 fixed 100-byte records (NUL-terminated SJIS, literal '\\n' = new line).

Read one record at a time by 0x800133fc(dst, n): seek n * 100, read 100 bytes, '\\n' -> 0x0a,
copy 101 bytes to dst (callers' buffers are 101 bytes; 0x800297fc cuts at 80). English stays in
the 100-byte records: at most 99 bytes, line breaks stored as raw 0x0a (copied unchanged).

Sections (record = index + base, by the getters 0x800134bc..0x800135c4):
  item    0-254    item descriptions (item info box)
  skill   256-304  skill descriptions
  sortie  331-356  sortie lines (Nobunaga, Nobutada ... 25 people)
  retreat 391-415  retreat lines
  battle  451-519  battle names (<= 10 full-width characters)
  trait   695-725  officer trait descriptions
Records 255/330/390/450/570/694 are developer comments, 570-674 a debug sound list, '終端' filler:
not translated.

script/imsg.txt: "@n section" + Japanese (literal \\n), first occurrence of each text only
                 (repeats listed as "@n = @k").
tl/imsg/*.txt:   "@n" + English ('\\n' forces a break; build wraps at WIDTH pixels); a record
                 without English takes the English of an identical Japanese record.

  imsg.py check    errors, size and line-count report
"""
import glob, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMSG = os.path.join(ROOT, 'extract', 'DATA', 'IMSG.E4')
SCRIPT = os.path.join(ROOT, 'script', 'imsg.txt')
TL = os.path.join(ROOT, 'tl', 'imsg')          # *.txt, read in name order
ISO_NAME = 'DATA/IMSG.E4'
REC = 100
SECTIONS = [('item', 0, 255), ('skill', 256, 305), ('sortie', 331, 357), ('retreat', 391, 416),
            ('battle', 451, 520), ('trait', 695, 726)]
# pixels per line and lines per record, by section (item info box: 2 lines, text x 16 .. ~244)
WIDTH = {'item': 228, 'skill': 228, 'sortie': 216, 'retreat': 216, 'battle': None, 'trait': 228}
LINES = {'item': 2, 'skill': 2, 'sortie': 3, 'retreat': 3, 'battle': 1, 'trait': 2}
FILLER = '終端'


def records(data=None):
    d = data or open(IMSG, 'rb').read()
    return [d[i:i + REC].split(b'\0')[0].decode('cp932') for i in range(0, len(d), REC)]


def section(n):
    for s, lo, hi in SECTIONS:
        if lo <= n < hi:
            return s
    return None


def japanese(recs=None):
    """-> {n: (section, Japanese)} of the records to translate."""
    recs = recs or records()
    return {n: (section(n), r) for n, r in enumerate(recs) if section(n) and r and r != FILLER}


def export():
    jp, first, done = japanese(), {}, 0
    with open(SCRIPT, 'w', encoding='utf-8') as f:
        for n, (s, r) in sorted(jp.items()):
            if r in first:
                f.write('@%d = @%d\n\n' % (n, first[r]))
                continue
            first[r] = n
            f.write('@%d %s\n%s\n\n' % (n, s, r))
            done += 1
    return done


def load_tl(path=TL):
    out, key = {}, None
    files = sorted(glob.glob(os.path.join(path, '*.txt')))
    for ln in (ln for f in files for ln in open(f, encoding='utf-8').read().splitlines()):
        if ln.startswith('@'):
            key = int(ln[1:].split()[0])
        elif ln.strip() and key is not None:
            out[key] = ln.strip()
            key = None
    return out


def english():
    """-> ({n: wrapped English}, errors)"""
    jp, tl = japanese(), load_tl()
    memory = {}
    for n, en in tl.items():
        if n in jp:
            memory.setdefault(jp[n][1], en)
    out, errs = {}, []
    for n in tl:
        if n not in jp:
            errs.append('@%d: not a translatable record' % n)
    for n, (s, r) in jp.items():
        en = tl.get(n, memory.get(r))
        if en is None:
            continue
        es = text.check(en)
        if es:
            errs += ['@%d: %s' % (n, e) for e in es]
            continue
        w = text.wrap(en, WIDTH[s])
        b = w.encode('ascii')
        if len(b) > REC - 1:
            errs.append('@%d: %d bytes > %d' % (n, len(b), REC - 1))
        if w.count('\n') + 1 > LINES[s]:
            errs.append('@%d: %d lines > %d' % (n, w.count('\n') + 1, LINES[s]))
        if WIDTH[s] is None and text.pixels(w) > 200:
            errs.append('@%d: %d px (unwrapped label)' % (n, text.pixels(w)))
        out[n] = w
    return out, errs


def build(data):
    """IMSG.E4 bytes -> (English bytes, count); exits on errors."""
    en, errs = english()
    if errs:
        sys.exit('\n'.join(errs) + '\n%d errors in tl/imsg/ (tools/imsg.py)' % len(errs))
    d = bytearray(data)
    for n, w in en.items():
        d[n * REC:(n + 1) * REC] = w.encode('ascii').ljust(REC, b'\0')
    return bytes(d), len(en)


def main():
    en, errs = english()
    for e in errs:
        print(e)
    print('%d / %d records translated, %d errors' % (len(en), len(japanese()), len(errs)))


if __name__ == '__main__':
    main()
