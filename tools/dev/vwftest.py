"""Run the blob's measuring functions (vwf.py pixw/maxw) in a MIPS emulator (unicorn) and compare
with the Python widths.

usage: .venv/bin/python tools/dev/vwftest.py
"""
import os, struct, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import asm, vwf
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_V0, UC_MIPS_REG_RA, UC_MIPS_REG_SP

BASE = 0x801f0000
STR = 0x80100000
RET = 0x80000100


def run(entry, data, s):
    uc = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 + UC_MODE_LITTLE_ENDIAN)
    uc.mem_map(0, 0x200000)                             # KSEG0 0x80000000 -> physical 0
    uc.mem_write(BASE & 0x1fffffff, data)
    uc.mem_write(STR & 0x1fffffff, s + b'\0')
    uc.mem_write(RET & 0x1fffffff, struct.pack('<2I', 0, 0))        # nop; nop
    uc.reg_write(UC_MIPS_REG_A0, STR)
    uc.reg_write(UC_MIPS_REG_RA, RET)
    uc.reg_write(UC_MIPS_REG_SP, 0x801ff000)
    uc.emu_start(entry, RET, count=100000)
    return uc.reg_read(UC_MIPS_REG_V0)


def main():
    data, _ = vwf.blob(BASE)
    lab = asm.labels(BASE + 4 + len(vwf.WIDTHS), vwf._code(BASE, BASE + 4))
    bad = 0
    tests = ['', 'Owari Province', 'The quick brown fox, jumps!', 'iiii', 'WWW mmm 0123']
    for t in tests:
        got, want = run(lab['pixw'], data, t.encode()), vwf.width(t)
        bad += got != want
        print('pixw %-30r %3d %3d' % (t, got, want))
    jp = '尾張の国'.encode('cp932')
    got = run(lab['pixw'], data, b'A' + jp + b'\x1b=1B')
    print('pixw A+4 kanji+ESC  %d %d' % (got, vwf.width('AB') + 48))
    bad += got != vwf.width('AB') + 48
    multi = ['Short line', 'A much longer line of text here', 'mid line']
    got, want = run(lab['maxw'], data, '\n'.join(multi).encode()), max(map(vwf.width, multi))
    print('maxw %d %d' % (got, want))
    bad += got != want
    sys.exit('%d failures' % bad if bad else 0)


if __name__ == '__main__':
    main()
