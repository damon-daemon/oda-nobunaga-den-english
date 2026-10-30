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
# boxes whose auto-paging ends a page at the last sentence end on it rather than mid-sentence
# (when that still leaves SENT_MIN lines on the page)
SENT_PAGE = {0x28}
SENT_MIN = 2
# numbered list item ('  2. ', 'Victory: 1. '): wrapped lines hang under the item text
_ITEM = re.compile(r' *(?:[A-Z][A-Za-z ()]*: )?\d+\. ')
_SENT_END = re.compile(r'(?<!^)(?<![\d ])[.!?][)"\']*$')       # not a list number '2.'
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


def _para(p):
    """forced-break paragraph -> word list; leading spaces (list indents) stay on the first word"""
    words = p.split()
    if words and p[0] == ' ':
        words[0] = ' ' * (len(p) - len(p.lstrip(' '))) + words[0]
    return words


def _lines(words, width):
    """one paragraph (word list) -> list of word lists, one per line"""
    if width is None or pixels(' '.join(words)) <= width:
        return [words]
    m = _ITEM.match(' '.join(words))
    hang = ' ' * round(pixels(m.group()) / pixels(' ')) if m else ''
    out, line = [], []
    for w in words:
        if line and pixels(' '.join(line + [w])) > width:
            out.append(line)
            line = [hang + w]
        else:
            line.append(w)
    out.append(line)
    return out


def _sent_pages(paras, width, page):
    """paragraphs of one block (word lists) -> lines, padded so that no page ends mid-sentence
    when the page holds an earlier sentence end (after its first SENT_MIN lines)"""
    out = []
    paras = [list(p) for p in paras]
    while paras:
        lines, src = [], []                       # src: (paragraph index, words before the line end)
        for i, p in enumerate(paras):
            n = 0
            for ln in _lines(p, width):
                n += len(ln)
                lines.append(ln)
                src.append((i, n))
        if len(lines) <= page:
            out += [' '.join(ln) for ln in lines]
            break
        last = lines[page - 1]
        i, n = src[page - 1]
        if n == len(paras[i]) or _SENT_END.search(last[-1]):
            cut = (i, n)
        else:
            cut = None
            for j in range(page - 1, SENT_MIN - 1, -1):
                ln = lines[j]
                k = max((m for m in range(len(ln) - (j == page - 1)) if _SENT_END.search(ln[m])), default=None)
                if k is not None:
                    cut = (src[j][0], src[j][1] - len(ln) + k + 1)
                    break
            if cut is None:
                cut = (i, n)
        i, n = cut
        for ln, (pi, pn) in zip(lines, src):
            if (pi, pn) > cut and (pi, pn - len(ln)) < cut:
                ln = ln[:len(ln) - (pn - n)]
            elif (pi, pn) > cut:
                break
            out.append(' '.join(ln))
        out += [''] * (-len(out) % page)
        paras = ([paras[i][n:]] if n < len(paras[i]) else []) + paras[i + 1:]
    return out


def wrap(en, width, page=None, sent=False):
    """English (one tl paragraph, '\\n' = forced break) -> lines joined by real newlines.
    page: lines per box page; a run of blank lines then pads to the next page.
    sent: pages end at a sentence end where possible (SENT_PAGE)."""
    paras = [_para(p) for p in fold(en).split('\\n')]
    if not page:
        return '\n'.join(' '.join(ln) for p in paras for ln in _lines(p, width))
    blocks, cur = [], []
    for p in paras:
        if p:
            cur.append(p)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    out = []
    for b in blocks:
        out += [''] * (-len(out) % page)
        if sent:
            out += _sent_pages(b, width, page)
        else:
            out += [' '.join(ln) for p in b for ln in _lines(p, width)]
    while out and not out[-1]:
        out.pop()
    return '\n'.join(out)


def lines(en, width):
    return wrap(en, width).count('\n') + 1


def jp_show(seg):
    """Japanese segment as one tl-style line (newlines as \\n)."""
    return seg.replace('\n', '\\n')
