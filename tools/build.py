"""Rebuild track 1 of the disc with the translation and produce a patch.

Output: build/oda_nobunaga_den_en_track1.bin, a copy of the audio track 2 and a .cue next to
them (boots in an emulator), and build/oda_nobunaga_den_en.xdelta (clean track 1 -> English
track 1; the audio track is not changed).

usage: .venv/bin/python tools/build.py [clean_track1.bin] [out_track1.bin]
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, datae4, gfx, hexeff, imsg, iso, names, progstr, setup, tl, vwf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'build', 'oda_nobunaga_den_en_track1.bin')
EXE_BASE = 0x80010000 - 0x800            # file offset of an address = va - EXE_BASE
FIXED = (iso.EXE_NAME, iso.FAT_NAME)     # must keep their place


def poke(exe, va, words):
    for i, w in enumerate(words):
        struct.pack_into('<I', exe, va - EXE_BASE + 4 * i, w)


def peek(exe, va, n):
    return list(struct.unpack_from('<%dI' % n, exe, va - EXE_BASE))


# Script string decompressor 0x80023338: single bytes 0x20-0x72 stand for hiragana and 0x73-0x76
# for punctuation (no script uses them). Copy every single byte < 0x80 as it is instead, so
# ASCII reaches the printer, which draws 0x20-0x7f with the 8x12 ANK1 font.
ASCII_AT = 0x800233b4
ASCII_OLD = [0x2c420073, 0x1040000a, 0x00000000, 0x90c30000, 0x00000000]


def patch_exe(exe):
    assert peek(exe, ASCII_AT, 5) == ASCII_OLD, 'unexpected code at %#x' % ASCII_AT
    code = asm.assemble(ASCII_AT, [
        ('sltiu', 'v0', 'v0', 0x80),
        ('beqz', 'v0', 0x8002347c),      # >= 0x80: SJIS pair
        ('nop',),
        ('j', 0x80023490),               # copy one byte
        ('nop',)])
    exe[ASCII_AT - EXE_BASE:ASCII_AT - EXE_BASE + len(code)] = code
    # item info box 0x80029774 and the officer screen's skill (0x8006d774) and trait (0x8006da2c)
    # pages: IMSG record read to sp+0x20 (101 bytes, saved registers from sp+0x88) and cut at
    # 80 bytes; English uses the whole record (imsg.py: <= 99 bytes)
    for at in IMSG_CUT_AT:
        assert peek(exe, at, 1) == [0xa3a00070], 'unexpected code at %#x' % at
        poke(exe, at, [0xa3a00084])  # sb zero, 0x84(sp)
    # council talk list (Square; 0x8002e77c): box 76 px wide at x 16 / 228 with a 60-px text
    # clear and the page/L1-R1 hints at x + 72; English names up to 111 px (issue #1) -> 128 px
    # wide, the right-hand box keeping its right edge (x 176)
    for at, old, new in LIST_BOX:
        assert peek(exe, at, 1) == [old], 'unexpected code at %#x' % at
        poke(exe, at, [new])
    # level-up "%s can now be equipped!" joins weapon types with ",%s": add a space
    o = LIST_SEP - EXE_BASE
    assert exe[o:o + 8] == b',%s\0\0\0\0\0', 'unexpected bytes at %#x' % LIST_SEP
    exe[o:o + 5] = b', %s\0'
    # merchant wares list 0x80067400: price "%4u" printed at column 15 over the end of long
    # English item names -> column 16 (header "Wares   Price" spaced to match in tl/progstr)
    assert peek(exe, PRICE_COL_AT, 1) == [0x2405000f], 'unexpected code at %#x' % PRICE_COL_AT
    poke(exe, PRICE_COL_AT, [0x24050010])  # addiu a1, zero, 16
    # storehouse list 0x80028cc8: item name at x 200, quantity "%2u" at x 280 -> 284
    # (item names <= 84 px, datae4.ITEM_PX)
    # staff credits 0x80039990: the cards at x 190/230 clip long English names at the screen edge
    for va, x in CREDIT_X.items():
        assert peek(exe, va, 1)[0] & 0xffff == x + CREDIT_DX, 'unexpected code at %#x' % va
        poke(exe, va, [0x24050000 | x])
    # 'Technical Support' took its y from x (move a2, a1): keep y 190
    assert peek(exe, 0x80039b20, 1) == [0x00a03021], 'unexpected code at 0x80039b20'
    poke(exe, 0x80039b20, [0x240600be])
    assert peek(exe, QTY_X_AT, 1) == [0x24050118], 'unexpected code at %#x' % QTY_X_AT
    poke(exe, QTY_X_AT, [0x2405011c])      # addiu a1, zero, 0x11c
    # storehouse officer panel 0x800284e0: name (given names, names.GIVEN_SITES) at x 24, class
    # icon at x 104, class name at x 120 (clipped by the panel at ~157) -> icon 82, class 99
    for va, old, new in CLASS_X:
        assert peek(exe, va, 1) == [old], 'unexpected code at %#x' % va
        poke(exe, va, [new])
    # blacksmith officer panel 0x800184c0 (issue #1): the equipped weapon's name at x 228 had
    # 72 px to the frame (item names up to 85 px ran over it and outside the 156-px clear
    # rect). Class icon dropped (the officer list shows it), class name at x 144, weapon icon
    # 212 -> 204 and name 228 -> 220 (90 px), clear rect 156 -> 166 wide
    for va, old, new in SMITH_PANEL:
        assert peek(exe, va, 1) == [old], 'unexpected code at %#x' % va
        poke(exe, va, [new])
    # save list line split (see SAVE_SEP): line 1 = prefix + 1 byte of the separator
    assert peek(exe, SAVE_SPLIT_AT, 1) == [0x02028021], 'unexpected code at %#x' % SAVE_SPLIT_AT
    poke(exe, SAVE_SPLIT_AT, [0x26100001])  # addu s0, s0, v0 (strlen) -> addiu s0, s0, 1


IMSG_CUT_AT = (0x80029804, 0x8006d940, 0x8006dabc)
LIST_BOX = [(0x8002e7a0, 0x240200e4, 0x240200b0),     # right-hand x 228 -> 176
            (0x8002e894, 0x2407004c, 0x24070080),     # box width 76 -> 128
            (0x8002e924, 0x2406003c, 0x24060070),     # text clear width 60 -> 112
            (0x8002e61c, 0x24060044, 0x24060078),     # box clear width 68 -> 120
            (0x8002e9a8, 0x24c60048, 0x24c6007c),     # page arrow x + 72 -> + 124
            (0x8002e9d4, 0x24c60048, 0x24c6007c)]     # R1 hint x + 72 -> + 124
LIST_SEP = 0x8012a098
PRICE_COL_AT = 0x80067588
QTY_X_AT = 0x80028dc4
CREDIT_DX = 24
CREDIT_X = {0x80039a64: 166, 0x80039a7c: 206, 0x80039a94: 166, 0x80039aac: 206, 0x80039ad4: 166,
            0x80039aec: 206, 0x80039b04: 206, 0x80039b1c: 166, 0x80039b34: 206}
SAVE_SEP = 0x8012a664
SAVE_SPLIT_AT = 0x8003df50
CLASS_X = [(0x8002855c, 0x24060068, 0x24060052),     # addiu a2, zero, icon x
           (0x8002856c, 0x24050078, 0x24050063)]     # addiu a1, zero, class x
SMITH_PANEL = [(0x800184e4, 0x2406009c, 0x240600a6),  # clear rect width 156 -> 166
               (0x80018570, 0x0c009a04, 0x00000000),  # class icon sprite: nop
               (0x800185a8, 0x240500a0, 0x24050090),  # class name x 160 -> 144
               (0x80018614, 0x240600d4, 0x240600cc),  # weapon icon x 212 -> 204
               (0x8001866c, 0x240500e4, 0x240500dc),  # weapon name x 228 -> 220
               # its item list 0x8001802c: icons at x 144, names at 160, clear rect 158..235,
               # Smith Skill icons at 240 -> icons 140, names 156, clear 154..240 (names <= 84 px)
               (0x80018050, 0x2404009e, 0x2404009a),  # clear rect x 158 -> 154
               (0x80018058, 0x2406004d, 0x24060056),  # clear rect width 77 -> 86
               (0x80018070, 0x240500a0, 0x2405009c),  # name x 160 -> 156
               (0x80018124, 0x24060090, 0x2406008c)]  # icon x 144 -> 140


# English blob: appended to DATA/KANJITBL.BIN, which the font loader 0x80016090 reads to
# 0x801eefc4 with an explicit size (KANJITBL_SIZE_AT: ori a2, zero, size); the table ends at
# 0x801f0000, so the blob lands at BLOB (stack reserve below 0x801fff00; the stack never went
# under 0x801feb50 in event/battle states, so BLOB..BLOB_END is free).
KANJITBL = 'DATA/KANJITBL.BIN'
KANJITBL_LOAD = 0x801eefc4
BLOB, BLOB_END = 0x801f0000, 0x801f8000
KANJITBL_SIZE_AT = 0x800160fc
KANJITBL_SIZE_OLD = 0x2406103c          # addiu a2, zero, 0x103c


def make_blob():
    """-> (blob bytes, [(exe patch function)])"""
    data = names.blob_names(BLOB)
    data += bytes(-len(data) % 4)
    at = BLOB + len(data)
    code, short, given, raw = names.hook(at, BLOB)
    data += code
    data += bytes(-len(data) % 4)
    vdata, vpatch = vwf.blob(BLOB + len(data))
    data += vdata
    assert BLOB + len(data) <= BLOB_END, 'blob too large: %d bytes' % len(data)
    return data, [lambda exe: names.patch(exe, EXE_BASE, at, short, given, raw), lambda exe: vpatch(exe, EXE_BASE)]


def build_files(disc, recs):
    """{iso path: bytes} of every rebuilt file."""
    eexs, done, errs = tl.english()
    if errs:
        sys.exit('\n'.join(errs) + '\n%d errors in tl/ (tools/tl.py check)' % len(errs))
    print('EEX: %d English segments in %d files' % (done, len(eexs)))
    out = {'DATA/%s.EEX' % n: d for n, d in eexs.items()}
    out[datae4.ISO_NAME], n = datae4.build(disc.file(datae4.ISO_NAME, recs))
    print('DATA.E4: %d names' % n)
    out[imsg.ISO_NAME], n = imsg.build(disc.file(imsg.ISO_NAME, recs))
    print('IMSG.E4: %d texts' % n)
    clean_exe = disc.file(iso.EXE_NAME, recs)
    exe = bytearray(clean_exe)
    patch_exe(exe)
    out[gfx.ISO_NAME], n = gfx.build(disc.file(gfx.ISO_NAME, recs), exe, EXE_BASE)
    print('MARK.E4: %d labels' % n)
    out[hexeff.ISO_NAME], n = hexeff.build(disc.file(hexeff.ISO_NAME, recs))
    print('HEX_EFF.E4: %d labels' % n)
    blob, patches = make_blob()
    for p in patches:
        p(exe)
    # program strings last: a repointed reference must still hold its clean word
    blob += bytes(-len(blob) % 4)
    try:
        n, moved, pool, extra = progstr.apply({'PROG': exe}, {'PROG': clean_exe}, (BLOB + len(blob), BLOB_END - BLOB - len(blob)))
    except ValueError as e:
        sys.exit('%s\nprogstr errors (tools/progstr.py check)' % e)
    print('program strings: %d (%d moved, %d bytes in the blob)' % (n, moved, len(extra)))
    blob += extra
    # save list: the slot title (Oda Nobunaga Den + chapter + level) is drawn as two lines,
    # split after the separator found by the game's strstr 0x80091fc8 (separator pointer
    # table SAVE_SEP; the Japanese splits after the closing 』). English: split at '"Lv' (the
    # chapter's closing quote + "Lv", PROG:8012a674), keeping only the quote on line 1
    # (SAVE_SPLIT_AT). That strstr returns the string start for 1-byte patterns, so the
    # separator is not just '"' (PROG:8012a660, also the closing quote of battle saves).
    blob += bytes(-len(blob) % 4)
    assert peek(exe, SAVE_SEP, 1) == [0x8012a660], 'save-list separator moved'
    poke(exe, SAVE_SEP, [BLOB + len(blob)])
    blob += b'"Lv\0'
    assert BLOB + len(blob) <= BLOB_END, 'blob too large: %d bytes' % len(blob)
    tbl = disc.file(KANJITBL, recs)
    assert KANJITBL_LOAD + len(tbl) == BLOB
    out[KANJITBL] = tbl + blob
    out[vwf.ANK1] = vwf.font()
    assert len(out[vwf.ANK1]) == len(disc.file(vwf.ANK1, recs))
    assert peek(exe, KANJITBL_SIZE_AT, 1) == [KANJITBL_SIZE_OLD]
    poke(exe, KANJITBL_SIZE_AT, [0x34060000 | len(out[KANJITBL])])     # ori a2, zero, size
    print('blob: %d bytes at %#x' % (len(blob), BLOB))
    out[iso.EXE_NAME] = bytes(exe)
    return out


def write(clean, out, files):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    moved = iso.write_image(clean, out, files)
    print('rebuilt %s%s' % (out, ' (moved: %s)' % ', '.join(moved) if moved else ''))
    if set(moved) & set(FIXED):
        sys.exit('%s moved on the disc' % ', '.join(set(moved) & set(FIXED)))
    iso.verify(out, files)
    audio = []
    for t, src in enumerate(setup.AUDIO, 2):
        dst = out.replace('_track1.bin', '_track%d.bin' % t)
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
            shutil.copyfile(src, dst)
        audio.append(dst)
    iso.write_cue(out.replace('_track1.bin', '.cue'), out, audio)
    patch = os.path.join(os.path.dirname(out), 'oda_nobunaga_den_en.xdelta')
    try:
        subprocess.run(['xdelta3', '-e', '-f', '-9', '-S', 'djw', '-B', str(1 << 28), '-s', clean, out, patch], check=True)
        print('patch %s (%d bytes)' % (patch, os.path.getsize(patch)))
    except FileNotFoundError:
        print('xdelta3 not installed; skipped patch')
    return moved


def main():
    args = sys.argv[1:]
    clean = args[0] if args else setup.CLEAN
    out = args[1] if len(args) > 1 else OUT
    disc = iso.Disc(clean)
    write(clean, out, build_files(disc, disc.records()))


if __name__ == '__main__':
    main()
