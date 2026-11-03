"""Unicorn test of the boxed-label width in vwf.py `border`: with a background colour the cell
is packed to the glyph's advance (rounded up to even) before the blit; without one, or for a
wide glyph, the blit gets the untouched 8-px cell.

usage: .venv/bin/python tools/dev/bgcelltest.py
"""
import os, struct, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import asm, vwf
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import (UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_A2, UC_MIPS_REG_A3,
                                UC_MIPS_REG_RA, UC_MIPS_REG_SP)

BASE, CTX, CELL, RET, SP = 0x801f0000, 0x80100000, 0x80100300, 0x80000100, 0x801ff000


def phys(a):
    return a & 0x1fffffff


def run(ch, bg):
    """-> (width passed to the blit, its stride-packed cell as 16 rows of bytes)"""
    lab, data = vwf.listing(BASE)
    uc = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 + UC_MODE_LITTLE_ENDIAN)
    uc.mem_map(0, 0x200000)
    uc.mem_write(phys(BASE), data)
    uc.mem_write(phys(RET), bytes(8))
    uc.mem_write(phys(vwf.CELL_BLIT), asm.assemble(vwf.CELL_BLIT, [('jr', 'ra'), ('nop',)]))
    uc.mem_write(phys(BASE), struct.pack('<I', ord(ch)))                 # char
    uc.mem_write(phys(CTX) + 0x14c, bytes([bg]))
    cell = bytes(r * 16 + k for r in range(16) for k in range(4))        # byte k of row r
    uc.mem_write(phys(CELL), cell)
    uc.mem_write(phys(SP) + 0x10, struct.pack('<II', 16, CELL))
    w = []
    uc.hook_add(1 << 2, lambda u, a, s, d: w.append(u.reg_read(UC_MIPS_REG_A3)) if not w else None,
                begin=vwf.CELL_BLIT, end=vwf.CELL_BLIT)
    for r, v in ((UC_MIPS_REG_A0, CTX), (UC_MIPS_REG_A1, 3), (UC_MIPS_REG_A2, 2), (UC_MIPS_REG_A3, 8),
                 (UC_MIPS_REG_SP, SP), (UC_MIPS_REG_RA, RET)):
        uc.reg_write(r, v)
    uc.emu_start(lab['border'], RET, count=100000)
    n = w[0] // 2
    out = bytes(uc.mem_read(phys(CELL), n * 16))
    return w[0], [out[i * n:(i + 1) * n] for i in range(16)]


def main():
    bad = 0
    for ch in 'iltaNm ':
        adv = vwf.width(ch)
        want = min((adv + 1) & ~1, 8)
        w, rows = run(ch, 12)
        ok = w == want and all(rows[r] == bytes(r * 16 + k for k in range(want // 2)) for r in range(16))
        w0, rows0 = run(ch, 0)
        ok = ok and w0 == 8 and rows0[5] == bytes(5 * 16 + k for k in range(4))
        print('%r advance %d box %d %s' % (ch, adv, w, 'OK' if ok else 'BAD'))
        bad += not ok
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
