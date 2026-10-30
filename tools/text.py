"""EEX strings <-> translation segments, and the English encoder.

A string operand of the event scripts (eex.py) is split into segments:
  op 0x27 dialogue  '&Speaker\\ntext\\n&Speaker\\ntext' -> one segment per speech; the speaker
                    header (a DATA.E4 record name, or 'Id&Display') stays as it is for now and is
                    not part of the translation
  op 0x4f history   '&Ntext' (N = icon digit) -> the text; the '&N' prefix is kept
  every other op    the whole string (a trailing newline is kept)

English (tl/): plain ASCII; '\\n' forces a line break, a blank line = '\\n\\n'. build wraps every
line at the width of its op (WIDTH, in pixels of the proportional font, vwf.py). Typographic quotes,
dashes and ellipses are folded to ASCII; '&', '\\' (other than \\n), '%' and '{' are refused.
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
from vwf import width as pixels

# pixels per line, by op; None = no wrapping (short labels). Dialogue box text 216 px (cleared
# area 0xd8), narration box 244 px (x 30) with text at x 38.
WIDTH = {0x27: 216, 0x28: 220, 0x29: None, 0x2a: None, 0x2b: None, 0x2c: 216, 0x12: None, 0x4f: 216,
         0x17: None}
# lines per page of the auto-paging boxes: the Japanese pads with blank lines to start a new
# page, so build turns every blank-line paragraph break into padding up to the next page.
PAGE = {0x27: 3, 0x28: 4}
KIND = {0x12: 'choice', 0x17: 'str17', 0x27: 'talk', 0x28: 'narr', 0x29: 'place', 0x2a: 'title',
        0x2b: 'title2', 0x2c: 'battle', 0x4f: 'history'}
FOLD = {'‘': "'", '’': "'", '“': '"', '”': '"', '—': '--', '–': '-',
        '…': '...', ' ': ' '}
_SPEECH = re.compile(r'\n(?=&)')


def decode(b):
    return b.decode('cp932')


def segments(op, s):
    """Japanese string (str) -> (list of segment texts, template). The template rebuilds the
    string from English segments: build(template, [en...])."""
    if op == 0x27:
        heads, segs, tails = [], [], []
        for sp in _SPEECH.split(s):
            head, _, body = sp.partition('\n')
            assert head.startswith('&'), repr(sp)
            core = body.rstrip('\n')
            heads.append(head)
            segs.append(core)
            tails.append(body[len(core):])
        return segs, ('talk', heads, tails)
    if op == 0x4f and re.match(r'&\d', s):
        return [s[2:]], ('prefix', s[:2], '')
    tail = s[len(s.rstrip('\n')):]
    return [s[:len(s) - len(tail)]], ('prefix', '', tail)


def join(tmpl, segs):
    if tmpl[0] == 'talk':
        return '\n'.join(h + '\n' + t + z for h, t, z in zip(tmpl[1], segs, tmpl[2]))
    return tmpl[1] + segs[0] + tmpl[2]


def check(en):
    """-> list of problems with an English segment."""
    errs = []
    s = fold(en)
    bad = sorted(set(c for c in s if not (' ' <= c <= '~')))
    if bad:
        errs.append('non-ASCII characters %r' % ''.join(bad))
    if re.search(r'[&%{}]|\\(?!n)', s):
        errs.append("reserved character (& %% { } or \\ other than \\n)")
    return errs


def fold(en):
    return ''.join(FOLD.get(c, c) for c in en)


def wrap(en, width, page=None):
    """English (one tl paragraph, '\\n' = forced break) -> lines joined by real newlines.
    page: lines per box page; a run of blank lines then pads to the next page."""
    out = []
    for para in fold(en).split('\\n'):
        para = ' '.join(para.split())
        if width is None or pixels(para) <= width:
            out.append(para)
            continue
        line = ''
        for w in para.split(' '):
            if line and pixels(line + ' ' + w) > width:
                out.append(line)
                line = w
            else:
                line = line + ' ' + w if line else w
        out.append(line)
    if page:
        blocks, cur = [], []
        for ln in out:
            if ln:
                cur.append(ln)
            elif cur:
                blocks.append(cur)
                cur = []
        if cur:
            blocks.append(cur)
        out = []
        for b in blocks:
            out += [''] * (-len(out) % page) + b
    return '\n'.join(out)


def lines(en, width):
    return wrap(en, width).count('\n') + 1


def jp_show(seg):
    """Japanese segment as one tl-style line (newlines as \\n)."""
    return seg.replace('\n', '\\n')
