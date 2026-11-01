"""Variable-width English text: our proportional font (pixfont.py) in place of ANK1, a
per-character advance in the printer, and pixel measuring where the game sizes or centres text.

Printer: putchar 0x8001611c draws a character with 0x800164f4 (single bytes 0x20-0x7f from
ANK1, 8x12 cells, blitted into the 4bpp text bitmap at any x) and then advances x by 8 (x2 if
the double-width flag 0x40 is set). The hook remembers the character of the draw call and
advances single bytes 0x20-0x7f by their width from a table in the blob instead.

Measuring sites (blob functions pixw = width of a line, maxw = widest line of a text):
- line builder 0x8003abdc (dialogue/narration box 0x8003b694, limit 36 columns; battle box
  0x8003cacc, limit 26): copies one line to an 88-byte stack buffer, cutting it after `limit`
  columns (1 per single byte, 2 per SJIS pair), and may centre it by (limit - columns) * 3 px.
  English is wrapped by pixels at build time (text.py), so the cut goes up to LINE_MAX bytes,
  and the centring uses pixw.
- place caption 0x8003b5a0 (op 0x29): box strlen * 6 + 32 wide, centred -> pixw.
- message window 0x8003c654 (modes other than 3): box (widest line in bytes) * 6 + 2 * single
  bytes + 32 wide, centred -> maxw.
- menu box 0x8003befc (choices): item width (singles + strlen * 3) * 2 -> pixw.
- strlen * 6 (TIMES6: centred print 0x800169cc, menu and box widths) and strlen * 8 (council
  room name label) -> pixw.

Outline (issue #2): the ANK glyph routine 0x80015e88 draws every single-byte glyph over a copy
of itself in colour 8 shifted by 1 px (0x80015d5c mode 1): a one-sided drop shadow, which
reads badly on the translucent narration/battle-info boxes (white text, colour 8 dark). The
copy is replaced by an 8-neighbour dilation inside the 8-px cell (`outline`), and the cell blit
in DRAW (0x80016a84) is followed by `border`, which plots the outline pixels that fall outside
the cell (column x-1, rows y-1 and y+12) straight into the text bitmap where it is empty.
Where colour 8 is invisible (dialogue box, blue panels) nothing changes.

  font() -> ANK1.BIN bytes; width(text) -> pixels; blob(at) -> (bytes, patch function)
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, pixfont

ANK1 = 'DATA/ANK1.BIN'
ANK1_RAM = 0x801ee5a4             # where the font loader puts it
DRAW = 0x800164f4                 # glyph draw (a3 = character)
ADV_STORE = 0x800164cc            # sw v0, 0x108(s2) in putchar
LINE_MAX = 0x50

_G = pixfont.glyphs()
WIDTHS = bytes(_G[chr(c)][1] if chr(c) in _G else 8 for c in range(0x20, 0x80))


def font():
    out = bytearray()
    for c in range(0x20, 0x80):
        out += _G[chr(c)][0] if chr(c) in _G else bytes(12)
    return bytes(out)


def width(s):
    """Pixel width of an ASCII string."""
    return sum(WIDTHS[ord(c) - 0x20] for c in s)


SETMODE, SETCOL = 0x800167d4, 0x80016668
# outlined prints (8 passes in the outline colour at +-1, then the text) set blit mode 4
# (transparent) at these calls and restore it at the second
OUTLINED = [(0x80016d50, 0x80016dec), (0x80016f2c, 0x80016fc8), (0x80017108, 0x800171a0)]
SHADOW = 0x80015ec0               # ANK glyph: jal SETCOL with a1 = 8 (1-px shadow colour)
GLCOL = 0x80015ef4                # then jal SETCOL with a1 = the text colour
OUTLINE_AT = 0x80015ee8           # ANK glyph: jal 0x80015d5c (shadow copy, mode 1) -> outline
BORDER_AT = 0x80016600            # DRAW 0x800164f4: jal CELL_BLIT -> border
CELL_BLIT = 0x80016a84            # (ctx, x, y, w, [sp+0x10] h, [sp+0x14] cell) -> 0x8003112c
BITMAP, BM_W, BM_H = 0x8018c388, 320, 240    # 4bpp text bitmap, 160 bytes per row
OUTLINE_COL = 8
TEXT_CTX = 0x800c9814
LIST_START = 0x80017da4           # item list printer: jal 0x80016634 before the rows
LIST_START_FN = 0x80016634
LIST_END = 0x80017e7c             # its epilogue: lw ra / lw s5


def _code(char, widths, flag, vars):
    pend, svra, svx, svy, scr = vars, vars + 4, vars + 8, vars + 12, vars + 16
    lmode, lra = vars + 80, vars + 84
    # scr: 16 words = glyph rows -2..13 (rows 0-11 written by `outline`, the rest stay 0)
    return [
        'lstart:',          # item list printer 0x80017cb4: transparent cells (the list is
        ('lui', 't0', asm.hi(lmode)),             # cleared before it prints). Opaque ones wiped
        ('sw', 'ra', asm.lo(lra), 't0'),          # the Smith Skill label after an 84-px name
        ('lbu', 'a1', 0, 'a0'),
        ('nop',),
        ('sw', 'a1', asm.lo(lmode), 't0'),
        ('andi', 'a1', 'a1', 0xf0),
        ('jal', SETMODE),
        ('ori', 'a1', 'a1', 4),
        ('lui', 't0', asm.hi(lmode)),
        ('lw', 'ra', asm.lo(lra), 't0'),
        ('lui', 'a0', asm.hi(TEXT_CTX)),
        ('addiu', 'a0', 'a0', asm.lo(TEXT_CTX)),
        ('j', LIST_START_FN),
        ('addu', 'a1', 'zero', 'zero'),
        'lend:',            # its epilogue: mode back
        ('lui', 'a0', asm.hi(TEXT_CTX)),
        ('addiu', 'a0', 'a0', asm.lo(TEXT_CTX)),
        ('lui', 't0', asm.hi(lmode)),
        ('lw', 'a1', asm.lo(lmode), 't0'),
        ('jal', SETMODE),
        ('nop',),
        ('lw', 'ra', 0x30, 'sp'),
        ('j', LIST_END + 8),
        ('nop',),

        'on:',                                    # outlined print starts: shadow off
        ('lui', 't0', asm.hi(flag)),
        ('addiu', 't1', 'zero', 1),
        ('j', SETMODE),
        ('sw', 't1', asm.lo(flag), 't0'),
        'off:',
        ('lui', 't0', asm.hi(flag)),
        ('j', SETMODE),
        ('sw', 'zero', asm.lo(flag), 't0'),
        'shcol:',                                 # the ANK shadow: colour 0 (none) in outlined
        ('lui', 't0', asm.hi(flag)),              # text, else 8. The ring menu draws its text in
        ('lw', 't0', asm.lo(flag), 't0'),         # colour 8 itself: the shadow made it bold and
        ('nop',),                                 # the outline filled our 1-px letter gaps
        ('beqz', 't0', 'sh8'),
        ('nop',),
        ('addu', 'a1', 'zero', 'zero'),
        'sh8:',
        ('j', SETCOL),
        ('nop',),
        'glcol:',                                 # the glyph colour (a1): outlined text asks
        ('lui', 't0', asm.hi(flag)),              # for 0 in the outline passes (the shadow was
        ('lw', 't0', asm.lo(flag), 't0'),         # the outline) -> 8, the shadow colour
        ('nop',),
        ('beqz', 't0', 'gl'),
        ('nop',),
        ('bnez', 'a1', 'gl'),
        ('nop',),
        ('addiu', 'a1', 'zero', 8),
        'gl:',
        ('j', SETCOL),
        ('nop',),

        'wrap:',                                  # jal DRAW in putchar comes here
        ('lui', 't0', asm.hi(char)),
        ('j', DRAW),
        ('sw', 'a3', asm.lo(char), 't0'),
        'adv:',                                   # v0 = 8 * v1 (v1 = 1, or 2 if double width)
        ('lui', 't0', asm.hi(char)),
        ('lw', 't0', asm.lo(char), 't0'),
        ('nop',),
        ('addiu', 't1', 't0', -0x20),
        ('sltiu', 't2', 't1', 0x60),
        ('beqz', 't2', 'add'),
        ('lui', 't2', asm.hi(widths)),
        ('addu', 't2', 't2', 't1'),
        ('lbu', 't1', asm.lo(widths), 't2'),
        ('nop',),
        ('multu', 't1', 'v1'),
        ('mflo', 'v0'),
        'add:',
        ('lw', 'v1', 0x108, 's2'),
        ('nop',),
        ('j', ADV_STORE),
        ('addu', 'v0', 'v0', 'v1'),

        'pixw:',            # a0 = text -> v0 = width of its first line, a0 after the line's
        ('addu', 'v0', 'zero', 'zero'),           # end, v1 = the end ('\n' or 0); uses t0-t2
        'next:',
        ('lbu', 't0', 0, 'a0'),
        ('nop',),
        ('beqz', 't0', 'ret'),
        ('addiu', 'a0', 'a0', 1),
        ('sltiu', 't1', 't0', 0x80),
        ('beqz', 't1', 'high'),
        ('sltiu', 't1', 't0', 0x20),
        ('bnez', 't1', 'ctl'),
        ('lui', 't2', asm.hi(widths - 0x20)),
        ('addu', 't2', 't2', 't0'),
        ('lbu', 't1', asm.lo(widths - 0x20), 't2'),
        ('b', 'next'),
        ('addu', 'v0', 'v0', 't1'),
        'high:',                                  # SJIS pair 12 px, ANK2 0xa0-0xdf 8 px
        ('sltiu', 't1', 't0', 0xa0),
        ('bnez', 't1', 'pair'),
        ('sltiu', 't1', 't0', 0xe0),
        ('beqz', 't1', 'pair'),
        ('nop',),
        ('b', 'next'),
        ('addiu', 'v0', 'v0', 8),
        'pair:',
        ('addiu', 'a0', 'a0', 1),
        ('b', 'next'),
        ('addiu', 'v0', 'v0', 12),
        'ctl:',
        ('addiu', 't1', 'zero', 0x0a),
        ('beq', 't0', 't1', 'ret'),
        ('addiu', 't1', 'zero', 0x1b),
        ('bne', 't0', 't1', 'next'),              # ESC + 2 bytes: no width
        ('nop',),
        ('b', 'next'),
        ('addiu', 'a0', 'a0', 2),
        'ret:',
        ('jr', 'ra'),
        ('addu', 'v1', 't0', 'zero'),

        'maxw:',                                  # a0 = text -> v0 = width of its widest line
        ('addu', 't4', 'ra', 'zero'),
        ('addu', 't5', 'zero', 'zero'),
        'line:',
        ('jal', 'pixw'),
        ('nop',),
        ('sltu', 't1', 't5', 'v0'),
        ('beqz', 't1', 'less'),
        ('nop',),
        ('addu', 't5', 'v0', 'zero'),
        'less:',
        ('bnez', 'v1', 'line'),
        ('nop',),
        ('jr', 't4'),
        ('addu', 'v0', 't5', 'zero'),

        'outline:',         # in place of the shadow copy: a0 = ctx, a1 = glyph (12 rows of 4
        ('lbu', 't5', 0x14c, 'a0'),               # bytes, nibbles = shadow colour or 0),
        ('lui', 't6', asm.hi(scr)),               # a2 = cell (0x80 bytes). cell[r] = rows
        ('addiu', 't6', 't6', asm.lo(scr)),       # r-1..r+1 OR-ed, shifted +-1 px (ink is
        ('addu', 't4', 'zero', 'zero'),           # overlaid afterwards by the caller); the
        ('addu', 't3', 'zero', 'zero'),           # glyph rows go to scr for `border`; pend =
        ('addu', 't0', 'zero', 'zero'),           # any ink, unless the cell has a background
        'orow:',                                  # colour (ctx+0x14c: boxed labels)
        ('lw', 't1', 0, 'a1'),
        ('addiu', 't7', 't0', -11),
        ('beqz', 't7', 'olast'),
        ('addu', 't2', 'zero', 'zero'),
        ('lw', 't2', 4, 'a1'),
        'olast:',
        ('or', 't7', 't4', 't1'),
        ('or', 't7', 't7', 't2'),
        ('sll', 't8', 't7', 4),
        ('srl', 't9', 't7', 4),
        ('or', 't8', 't8', 't7'),
        ('or', 't8', 't8', 't9'),
        ('sw', 't8', 0, 'a2'),
        ('sw', 't1', 8, 't6'),
        ('or', 't3', 't3', 't1'),
        ('addu', 't4', 't1', 'zero'),
        ('addiu', 't0', 't0', 1),
        ('addiu', 'a1', 'a1', 4),
        ('addiu', 'a2', 'a2', 4),
        ('sltiu', 't7', 't0', 12),
        ('bnez', 't7', 'orow'),
        ('addiu', 't6', 't6', 4),
        ('addiu', 't0', 'zero', 20),              # cell rows 12-31 = 0 (the original memset)
        'ozero:',
        ('sw', 'zero', 0, 'a2'),
        ('addiu', 't0', 't0', -1),
        ('bnez', 't0', 'ozero'),
        ('addiu', 'a2', 'a2', 4),
        ('bnez', 't5', 'onopend'),
        ('lui', 't7', asm.hi(pend)),
        ('sltu', 't3', 'zero', 't3'),
        ('jr', 'ra'),
        ('sw', 't3', asm.lo(pend), 't7'),
        'onopend:',
        ('jr', 'ra'),
        ('sw', 'zero', asm.lo(pend), 't7'),

        'border:',          # in place of the cell blit in DRAW (same arguments, passed on)
        ('lui', 't7', asm.hi(svra)),
        ('sw', 'ra', asm.lo(svra), 't7'),
        ('sw', 'a1', asm.lo(svx), 't7'),
        ('jal', CELL_BLIT),
        ('sw', 'a2', asm.lo(svy), 't7'),
        ('lui', 't7', asm.hi(pend)),
        ('lw', 't0', asm.lo(pend), 't7'),
        ('lw', 't5', asm.lo(svra), 't7'),
        ('beqz', 't0', 'bret'),
        ('sw', 'zero', asm.lo(pend), 't7'),
        ('lw', 'a1', asm.lo(svx), 't7'),
        ('lw', 'a2', asm.lo(svy), 't7'),
        ('addiu', 't0', 'zero', -1),              # row r = -1..12; m = rows r-1..r+1 of the
        ('lui', 't6', asm.hi(scr)),               # glyph: column x-1 gets a pixel if m has
        ('addiu', 't6', 't6', asm.lo(scr)),       # one in column 0; rows -1 and 12 get the
        'brow:',                                  # dilated m over columns 0-7
        ('lw', 't1', 0, 't6'),
        ('lw', 't2', 4, 't6'),
        ('lw', 't3', 8, 't6'),
        ('addu', 'a3', 'a2', 't0'),
        ('or', 't1', 't1', 't2'),
        ('or', 't1', 't1', 't3'),
        ('andi', 't2', 't1', 0xf),
        ('beqz', 't2', 'bedge'),
        ('addiu', 'a0', 'a1', -1),
        ('jal', 'plot'),
        ('nop',),
        'bedge:',
        ('addiu', 't2', 't0', 1),
        ('beqz', 't2', 'bfull'),
        ('addiu', 't2', 't0', -12),
        ('bnez', 't2', 'bnext'),
        ('nop',),
        'bfull:',
        ('sll', 't2', 't1', 4),
        ('srl', 't3', 't1', 4),
        ('or', 't1', 't1', 't2'),
        ('or', 't1', 't1', 't3'),
        ('addu', 'a0', 'a1', 'zero'),
        ('addiu', 't4', 'zero', 8),
        'bcol:',
        ('andi', 't2', 't1', 0xf),
        ('beqz', 't2', 'bskip'),
        ('nop',),
        ('jal', 'plot'),
        ('nop',),
        'bskip:',
        ('srl', 't1', 't1', 4),
        ('addiu', 't4', 't4', -1),
        ('bnez', 't4', 'bcol'),
        ('addiu', 'a0', 'a0', 1),
        'bnext:',
        ('addiu', 't0', 't0', 1),
        ('slti', 't2', 't0', 13),
        ('bnez', 't2', 'brow'),
        ('addiu', 't6', 't6', 4),
        'bret:',
        ('jr', 't5'),
        ('nop',),

        'plot:',            # pixel (a0, a3) of the text bitmap = OUTLINE_COL if it is empty
        ('bltz', 'a0', 'pret'),                   # and inside the bitmap; uses v0, v1, t8, t9
        ('sltiu', 'v0', 'a0', BM_W),
        ('beqz', 'v0', 'pret'),
        ('sltiu', 'v0', 'a3', BM_H),
        ('beqz', 'v0', 'pret'),
        ('sll', 'v1', 'a3', 5),
        ('sll', 'v0', 'a3', 7),
        ('addu', 'v1', 'v1', 'v0'),               # y * 160
        ('srl', 'v0', 'a0', 1),
        ('addu', 'v1', 'v1', 'v0'),
        ('lui', 'v0', asm.hi(BITMAP)),
        ('addiu', 'v0', 'v0', asm.lo(BITMAP)),
        ('addu', 'v1', 'v1', 'v0'),
        ('lbu', 'v0', 0, 'v1'),
        ('andi', 't8', 'a0', 1),
        ('bnez', 't8', 'phigh'),
        ('andi', 't9', 'v0', 0xf),
        ('bnez', 't9', 'pret'),
        ('ori', 'v0', 'v0', OUTLINE_COL),
        ('jr', 'ra'),
        ('sb', 'v0', 0, 'v1'),
        'phigh:',
        ('andi', 't9', 'v0', 0xf0),
        ('bnez', 't9', 'pret'),
        ('ori', 'v0', 'v0', OUTLINE_COL << 4),
        ('jr', 'ra'),
        ('sb', 'v0', 0, 'v1'),
        'pret:',
        ('jr', 'ra'),
        ('nop',)]


STRLEN = 0x80091e98
TIMES6 = [(0x800169f8, 'v1'), (0x8003edcc, 'a3'), (0x80062160, 'v1'), (0x8006af0c, 'v1'),
          (0x8006af38, 'v1'), (0x8006af78, 'v1'), (0x8006af9c, 'v1')]


def _times6(va, reg, exe_word, pixw):
    """jal strlen / (delay) / sll r, v0, 1 / addu r, r, v0 / sll r, r, 1 -> r = pixw"""
    old = asm.assemble(va, [('jal', STRLEN), ('nop',), ('sll', reg, 'v0', 1), ('addu', reg, reg, 'v0'),
                            ('sll', reg, reg, 1)])
    old = list(struct.unpack('<5I', old))
    old[1] = exe_word(va + 4)
    new = [('jal', pixw), None, ('addu', reg, 'v0', 'zero'), ('nop',), ('nop',)]
    return va, old, new


def _sites(lab):
    """[(address, original words, new instructions)] of the program patches."""
    pixw, maxw = lab['pixw'], lab['maxw']
    return [
        (0x8001641c, [0x0c00593d], [('jal', lab['wrap'])]),          # putchar: jal DRAW
        (0x800164ac, [0x8e430108, 0x08005933, 0x00431021], [          # single-byte advance
            ('j', lab['adv']), ('nop',), ('nop',)]),
        (0x8003ac30, [0x32f500ff], [('addiu', 's5', 'zero', LINE_MAX)]),   # andi s5, s7, 0xff
        (0x8003ad88, [0x0c0247a6, 0x27a40018, 0x32e300ff, 0x304200ff,       # centring: s6 +=
                      0x00621823, 0x00031040, 0x00431021, 0x02c2b021], [    # (s7 - strlen) * 3
            ('jal', pixw),
            ('addiu', 'a0', 'sp', 0x18),
            ('andi', 'v1', 's7', 0xff),
            ('sll', 't0', 'v1', 1),
            ('addu', 'v1', 'v1', 't0'),
            ('srl', 'v0', 'v0', 1),
            ('subu', 'v1', 'v1', 'v0'),                               # s7 * 3 - width / 2
            ('addu', 's6', 's6', 'v1')]),
        (0x8003b5b8, [0x0c0247a6, 0x00809821, 0x00022042, 0x2403001a,       # place caption:
                      0x00641823, 0x00023840, 0x00e23821, 0x00073840,       # a3 = box width - 32,
                      0x00038840, 0x02238821, 0x00118840], [                # s1 = text x
            ('jal', pixw),
            ('addu', 's3', 'a0', 'zero'),
            ('addiu', 'v0', 'v0', 3),
            ('srl', 'v0', 'v0', 2),
            ('sll', 'v0', 'v0', 2),
            ('addu', 'a3', 'v0', 'zero'),
            ('srl', 'v0', 'v0', 1),
            ('addiu', 's1', 'zero', 0x9c),
            ('subu', 's1', 's1', 'v0'),
            ('nop',),
            ('nop',)]),
        (0x8003c7c0, [0x10400003, 0x32420001, 0x00609021, 0x32420001,       # message window:
                      0x10400002, 0x24150078, 0x26520001, 0x00121840,       # s2 = widest line,
                      0x00721821, 0x00032040, 0x97a50162, 0x00000000,       # fp = box width,
                      0x00051040, 0x24420020, 0x0082f021, 0x329300ff,       # s3 = height,
                      0x00131100, 0x24530030, 0x00651821, 0x240900a0,       # s7 = box x + 16;
                      0x0123b823], [                                        # text x = 0xa0 -
            ('lui', 'a0', 0x8010),                                    # 3 * s2 - [sp+0x162]
            ('jal', maxw),
            ('addiu', 'a0', 'a0', 0x64d4),
            ('addiu', 'v0', 'v0', 3),
            ('srl', 'v0', 'v0', 2),
            ('sll', 'v0', 'v0', 2),
            ('srl', 'v1', 'v0', 1),
            ('sh', 'v1', 0x162, 'sp'),
            ('addu', 's2', 'zero', 'zero'),
            ('addiu', 'fp', 'v0', 0x20),
            ('addiu', 's5', 'zero', 0x78),
            ('andi', 's3', 's4', 0xff),
            ('sll', 's3', 's3', 4),
            ('addiu', 's3', 's3', 0x30),
            ('addiu', 't1', 'zero', 0xa0),
            ('nop',),
            ('nop',),
            ('nop',),
            ('nop',),
            ('nop',),
            ('subu', 's7', 't1', 'v1')]),
        (0x8003bf90, [0x0c00eb90, 0x00000000, 0x00402821, 0x8e020000,       # menu (choice) box 0x8003befc:
                      0x00000000], [                                        # item width = (singles +
            ('jal', pixw),                                            # strlen * 3) * 2 -> pixw
            ('nop',),
            ('lbu', 'a0', 0x58, 'sp'),
            ('j', 0x8003c008),
            ('nop',)]),                                               # (load delay before sltu)
        (0x8005f778, [0x0c0247a6, 0x02202021, 0x000210c0], [           # council room label:
            ('jal', pixw), None, ('nop',)]),                          # x = (0x128 - strlen*8)/2
        (SHADOW, [0x0c00599a], [('jal', lab['shcol'])]),
        (GLCOL, [0x0c00599a], [('jal', lab['glcol'])]),
        (OUTLINE_AT, [0x0c005757], [('jal', lab['outline'])]),
        (BORDER_AT, [0x0c005aa1], [('jal', lab['border'])]),
        (LIST_START, [0x0c00598d], [('jal', lab['lstart'])]),
        (LIST_END, [0x8fbf0030], [('j', lab['lend'])]),
    ] + [s for on, off in OUTLINED for s in (
        (on, [0x0c0059f5], [('jal', lab['on'])]), (off, [0x0c0059f5], [('jal', lab['off'])]))]


VARS = 88                         # pend, svra, svx, svy, scr[16], lmode, lra


def listing(at):
    """-> (labels, bytes) of the blob at `at`: char, flag, widths, VARS, code."""
    char, flag, widths = at, at + 4, at + 8
    vars = widths + len(WIDTHS)
    code_at = vars + VARS
    lines = _code(char, widths, flag, vars)
    return asm.labels(code_at, lines), bytes(8) + WIDTHS + bytes(VARS) + asm.assemble(code_at, lines)


def blob(at):
    """Code + data at `at` -> (bytes, patch(exe, exe_base))."""
    lab, data = listing(at)

    def patch(exe, exe_base):
        word = lambda va: struct.unpack_from('<I', exe, va - exe_base)[0]
        sites = _sites(lab) + [_times6(va, r, word, lab['pixw']) for va, r in TIMES6]
        for va, old, new in sites:
            o = va - exe_base
            assert list(struct.unpack_from('<%dI' % len(old), exe, o)) == old, 'unexpected code at %#x' % va
            code = b''.join(struct.pack('<I', w) if n is None else asm.assemble(va + 4 * i, [n])
                            for i, (w, n) in enumerate(zip(old, new)))
            assert len(code) == 4 * len(old), hex(va)
            exe[o:o + len(code)] = code
    return data, patch
