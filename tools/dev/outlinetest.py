"""Render a line with the blob's `outline` + `border` routines (vwf.py) in unicorn, the way the
game's ANK glyph routine and DRAW use them, and print the text bitmap as ASCII art:
'#' = ink (colour 7), '+' = outline (colour 8), '.' = empty.

usage: .venv/bin/python tools/dev/outlinetest.py [text]
"""
import os, struct, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import asm, pixfont, vwf
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
                                UC_MIPS_REG_RA, UC_MIPS_REG_SP)

BASE = 0x801f0000
CTX, SRC, DST = 0x80100000, 0x80100200, 0x80100300
RET = 0x80000100
INK = 7


def phys(a):
    return a & 0x1fffffff


def decode(bits, colour):
    """1bpp glyph rows -> 12 words of 4bpp (pixel 0 = low nibble)."""
    out = []
    for row in bits:
        w = 0
        for k in range(8):
            if row >> (7 - k) & 1:
                w |= colour << (4 * k)
        out.append(w)
    return out


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else 'Help! g'
    lab, data = vwf.listing(BASE)
    uc = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 + UC_MODE_LITTLE_ENDIAN)
    uc.mem_map(0, 0x200000)
    uc.mem_write(phys(BASE), data)
    uc.mem_write(phys(RET), bytes(8))
    uc.mem_write(phys(vwf.CELL_BLIT), asm.assemble(vwf.CELL_BLIT, [('jr', 'ra'), ('nop',)]))
    uc.reg_write(UC_MIPS_REG_SP, 0x801ff000)
    glyphs = pixfont.glyphs()
    x, y = 3, 2

    def call(entry, a0, a1, a2, a3):
        uc.reg_write(UC_MIPS_REG_A0, a0)
        uc.reg_write(UC_MIPS_REG_A1, a1)
        uc.reg_write(UC_MIPS_REG_A2, a2)
        uc.reg_write(UC_MIPS_REG_A3, a3)
        uc.reg_write(UC_MIPS_REG_RA, RET)
        uc.emu_start(entry, RET, count=100000)

    for ch in text:
        bits, w = glyphs[ch]
        uc.mem_write(phys(SRC), struct.pack('<12I', *decode(bits, vwf.OUTLINE_COL)))
        call(lab['outline'], CTX, SRC, DST, 1)
        cell = list(struct.unpack('<16I', uc.mem_read(phys(DST), 64)))
        for r, g in enumerate(decode(bits, INK)):              # the game's compose step
            for k in range(8):
                if g >> (4 * k) & 0xf:
                    cell[r] = cell[r] & ~(0xf << (4 * k)) | (g & 0xf << (4 * k))
        for r in range(12):                                     # opaque 8x12 blit
            for k in range(8):
                a = phys(vwf.BITMAP) + (y + r) * 160 + (x + k) // 2
                b = uc.mem_read(a, 1)[0]
                v = cell[r] >> (4 * k) & 0xf
                b = (b & 0x0f) | v << 4 if (x + k) & 1 else (b & 0xf0) | v
                uc.mem_write(a, bytes([b]))
        call(lab['border'], CTX, x, y, 8)
        x += w
    for row in range(y - 2, y + 14):
        line = ''
        for col in range(0, x + 3):
            b = uc.mem_read(phys(vwf.BITMAP) + row * 160 + col // 2, 1)[0]
            v = b >> 4 if col & 1 else b & 0xf
            line += {0: '.', INK: '#', vwf.OUTLINE_COL: '+'}.get(v, '?')
        print(line)
    pend = struct.unpack_from('<I', uc.mem_read(phys(BASE) + 8 + len(vwf.WIDTHS), 4))[0]
    print('pend after border: %d' % pend)


if __name__ == '__main__':
    main()
