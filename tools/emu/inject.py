"""Write the current build's program patches and English blob into the running emulator
(GDB stub), so a save state made with an older build can be tested without a fresh boot.
The redrawn UI sheet (gfx, VRAM) needs a cold boot or tools/emu/vram.py put into the state.
Only RAM-resident parts: program words that differ from the original, and the blob at
build.BLOB and the ANK1 font (vwf). Script files (EEX) are read from the disc image when the game loads them.

usage: .venv/bin/python tools/emu/inject.py      (headless emulator running, build done)
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build, gfx, iso, setup, vwf
from gdbmem import G


def main():
    disc = iso.Disc(setup.CLEAN)
    recs = disc.records()
    files = build.build_files(disc, recs)
    old, new = disc.file(iso.EXE_NAME, recs), files[iso.EXE_NAME]
    g = G()
    g.cmd('?')
    n, o = 0, 0x800
    while o < len(new):                   # runs of changed words (gaps < 16 B), <= 0x200 B a packet
        if new[o:o + 4] == old[o:o + 4]:
            o += 4
            continue
        e = o + 4
        while e < len(new) and e - o < 0x200 and new[e:e + 16] != old[e:e + 16]:
            e += 4
        g.cmd('M%x,%x:%s' % (o + build.EXE_BASE, e - o, new[o:e].hex()))
        n += sum(new[k:k + 4] != old[k:k + 4] for k in range(o, e, 4))
        o = e
    blob = files[build.KANJITBL][build.BLOB - build.KANJITBL_LOAD:]
    for i in range(0, len(blob), 0x200):
        part = blob[i:i + 0x200]
        g.cmd('M%x,%x:%s' % (build.BLOB + i, len(part), part.hex()))
    # sprite table whole (an entry put back to its original rect by a later build)
    o = gfx.TABLE - build.EXE_BASE
    g.cmd('M%x,%x:%s' % (gfx.TABLE, 12 * gfx.SPRITES, new[o:o + 12 * gfx.SPRITES].hex()))
    font = files[vwf.ANK1]
    g.cmd('M%x,%x:%s' % (vwf.ANK1_RAM, len(font), font.hex()))
    g.resume()
    print('injected %d program words, blob %d bytes' % (n, len(blob)))


if __name__ == '__main__':
    main()
