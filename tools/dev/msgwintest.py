"""Run the battle message window 0x8003c654 (mode 5, as the level-up popups) on a test text in a
MIPS emulator (unicorn): RAM from a save state + the current build's program words, blob and
ANK1 font (as tools/emu/inject.py), stopped before the window waits for a button. Prints
every write outside the stack and the text bitmap (issue #12: none for texts up to 72 bytes).
Limit: the glyph blits run but leave the bitmap blank here (cause not found), so the PNG
only shows the cleared box; use it for the write check, not for looks.

usage: .venv/bin/python tools/dev/msgwintest.py STATE.sav OUT.png 'text' [mode]
"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'emu'))
import build, iso, setup, vwf
from ram import state_ram
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
from unicorn.mips_const import *

BITMAP, BM_SIZE = 0x8018c388, 0x9600
WIN, STOP, RET = 0x8003c654, 0x8003c984, 0x80000100
GP = 0x8012a068
TEXT = 0x801ff800


def machine(state):
    disc = iso.Disc(setup.CLEAN)
    recs = disc.records()
    files = build.build_files(disc, recs)
    old, new = disc.file(iso.EXE_NAME, recs), files[iso.EXE_NAME]
    ram = bytearray(state_ram(state))
    for o in range(0x800, len(new), 4):
        if new[o:o + 4] != old[o:o + 4]:
            a = (o + build.EXE_BASE) & 0x1fffff
            ram[a:a + 4] = new[o:o + 4]
    blob = files[build.KANJITBL][build.BLOB - build.KANJITBL_LOAD:]
    a = build.BLOB & 0x1fffff
    ram[a:a + len(blob)] = blob
    font = files[vwf.ANK1]
    a = vwf.ANK1_RAM & 0x1fffff
    ram[a:a + len(font)] = font
    uc = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 + UC_MODE_LITTLE_ENDIAN)
    uc.mem_map(0, 0x200000)
    uc.mem_write(0, bytes(ram))
    uc.mem_map(0x1f800000, 0x10000)          # scratchpad + I/O (stubbed)
    return uc, ram


def run(state, text, mode=5):
    uc, ram = machine(state)
    uc.mem_write(TEXT & 0x1fffff, text + b'\0')
    uc.mem_write(RET & 0x1fffff, b'\0' * 8)
    uc.mem_write(BITMAP & 0x1fffff, bytes(BM_SIZE))
    sp = 0x801fe000
    uc.reg_write(UC_MIPS_REG_SP, sp)
    uc.reg_write(UC_MIPS_REG_RA, RET)
    uc.reg_write(UC_MIPS_REG_GP, GP)
    uc.reg_write(UC_MIPS_REG_A0, mode)
    uc.reg_write(UC_MIPS_REG_A1, TEXT)
    writes = {}

    def w(uc, access, addr, size, value, data):
        a = addr & 0x1fffffff
        if sp - 0x2000 <= (a | 0x80000000) < sp + 0x100:
            return
        if BITMAP <= (a | 0x80000000) < BITMAP + BM_SIZE:
            return
        pc = uc.reg_read(UC_MIPS_REG_PC)
        writes.setdefault(pc, set()).add(a | 0x80000000)
    uc.hook_add(UC_HOOK_MEM_WRITE, w)
    try:
        uc.emu_start(WIN, STOP, count=20_000_000)
    except Exception as e:
        print('stopped:', e, hex(uc.reg_read(UC_MIPS_REG_PC)))
    print('pc %#x' % uc.reg_read(UC_MIPS_REG_PC))
    for pc, s in sorted(writes.items()):
        s = sorted(s)
        print('  write from %#x: %d bytes %#x..%#x' % (pc, len(s), s[0], s[-1]))
    return uc


def png(uc, out):
    from PIL import Image
    bm = uc.mem_read(BITMAP & 0x1fffff, BM_SIZE)
    img = Image.new('L', (320, 240))
    pal = [0] + [255] * 7 + [90] + [255] * 7
    for y in range(240):
        for x in range(320):
            b = bm[y * 160 + x // 2]
            img.putpixel((x, y), pal[(b >> (4 * (x & 1))) & 15])
    img.resize((960, 720), Image.NEAREST).save(out)


if __name__ == '__main__':
    st, out, text = sys.argv[1:4]
    mode = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    uc = run(st, text.encode('latin-1'), mode)
    png(uc, out)
