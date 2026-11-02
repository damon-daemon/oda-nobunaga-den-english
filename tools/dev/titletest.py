"""Run build.title_load (save loader: chapter title from the slot list / header field) and the
game's strstr split of a slot title in a MIPS emulator (unicorn).

usage: .venv/bin/python tools/dev/titletest.py
"""
import os, struct, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import asm, build
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import UC_MIPS_REG_A0, UC_MIPS_REG_A1, UC_MIPS_REG_V0, UC_MIPS_REG_RA, UC_MIPS_REG_SP, UC_MIPS_REG_GP

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
EXE = open(os.path.join(ROOT, 'extract', 'SLPS_015.95'), 'rb').read()[0x800:]
GP = 0x8012a068
CODE, SEP, HDR, RET = 0x801f7000, 0x801f6ff0, 0x801a0000, 0x80000100
ENTRIES = 0x80130f38
ODA = '織田信長伝'.encode('cp932')


def machine():
    uc = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 + UC_MODE_LITTLE_ENDIAN)
    uc.mem_map(0, 0x200000)
    uc.mem_write(0x10000, EXE)
    uc.mem_write(SEP & 0x1fffffff, b'Lv\0\0')
    uc.mem_write(CODE & 0x1fffffff, build.title_load(CODE, SEP))
    uc.mem_write(RET & 0x1fffffff, struct.pack('<2I', 0, 0))
    uc.reg_write(UC_MIPS_REG_GP, GP)
    uc.reg_write(UC_MIPS_REG_RA, RET)
    uc.reg_write(UC_MIPS_REG_SP, 0x801ff000)
    return uc


def load(entry_title, header, card=1, idx=2, stale=b''):
    """-> bytes left in TITLE_BUF after title_load(TITLE_BUF, header field)"""
    uc = machine()
    uc.mem_write((GP + 0x210) & 0x1fffffff, struct.pack('<2I', card, idx))
    uc.mem_write((ENTRIES + card * 0x5a0 + idx * 72 + 4) & 0x1fffffff, entry_title.ljust(64, b'\0'))
    uc.mem_write(HDR & 0x1fffffff, header)
    uc.mem_write(build.TITLE_BUF & 0x1fffffff, stale.ljust(64, b'\0'))
    uc.reg_write(UC_MIPS_REG_A0, build.TITLE_BUF)
    uc.reg_write(UC_MIPS_REG_A1, HDR)
    uc.emu_start(CODE, RET, count=100000)
    out = bytes(uc.mem_read(build.TITLE_BUF & 0x1fffffff, 64))
    return out[:out.index(b'\0')]


def split(title):
    """-> (line 1, line 2) as the patched list routine would cut the slot title"""
    uc = machine()
    uc.mem_write(HDR & 0x1fffffff, title + b'\0')
    uc.reg_write(UC_MIPS_REG_A0, HDR)
    uc.reg_write(UC_MIPS_REG_A1, SEP)
    uc.emu_start(build.STRSTR, RET, count=100000)
    pos = uc.reg_read(UC_MIPS_REG_V0)
    if not pos:
        return None
    return title[:pos - HDR], title[pos - HDR:]


def main():
    bad = 0
    def check(what, got, want):
        nonlocal bad
        ok = got == want
        bad += not ok
        print('%s %-34s %r' % ('ok ' if ok else 'BAD', what, got) + ('' if ok else '  want %r' % want))
    long = b'"Hills of Corpses, Rivers of Blood"'           # 35 bytes
    mid = b'"Masahide\'s Final Remonstrance"'                # 31 bytes
    short = b'"The Fool Heir"'
    # header field: first 30 bytes of the title, no NUL when longer (the next fields follow)
    hdr = lambda t: t[:30].ljust(30, b'\0') + b'\x03\x01\x07garbage\0'
    check('long title from the list', load(ODA + long + b'Lv12', hdr(long), stale=b'x' * 63), long)
    check('mid title from the list', load(ODA + mid + b'Lv3', hdr(mid)), mid)
    check('short title from the list', load(ODA + short + b'Lv1', hdr(short)), short)
    check('battle save title', load(ODA + b'"Battle of Okehazama"Lv5-3 Turn', hdr(b'"Battle of Okehazama"')), b'"Battle of Okehazama"')
    check('empty chapter title', load(ODA + b'Lv1', hdr(b'')), b'')
    check('no list entry -> header, 30 B', load(b'', hdr(mid), stale=b'y' * 63), mid[:30])
    check('no list entry -> header, short', load(b'', hdr(short)), short)
    check('junk entry -> header', load(b'New Data', hdr(short)), short)
    check('entry without Lv -> header', load(ODA + mid, hdr(mid)), mid[:30])
    check('other card/slot untouched', load(ODA + mid + b'Lv3', hdr(short), card=0, idx=7), mid)
    check('split intact title', split(ODA + mid + b'Lv3'), (ODA + mid, b'Lv3'))
    check('split truncated title', split(ODA + mid[:30] + b'Lv3'), (ODA + mid[:30], b'Lv3'))
    check('split battle title', split(ODA + b'"Okehazama"Lv5-3 Turn'), (ODA + b'"Okehazama"', b'Lv5-3 Turn'))
    check('split New Data', split(b'New Data'), None)
    sys.exit('%d failures' % bad if bad else 0)


if __name__ == '__main__':
    main()
