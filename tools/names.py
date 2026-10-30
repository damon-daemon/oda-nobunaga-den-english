"""Officer names: the records keep their Japanese, the name printer returns English.

DATA/DATA.E4 starts with 646 officer records of 77 bytes (name [13] SJIS, reading [15]
half-width kana, stats); the game copies the first 645 to the officer table in RAM
(OFFICERS, 0x70 bytes each, name at +0x0c). The event scripts name their speaker by that
Japanese record name (`&Id` is matched with strcmp, 0x80010024; the program also looks up
~200 officers by name literals, 0x8005ec38), so the records cannot change. Every name that is
printed goes through GETNAME 0x80012864 (record -> name with the trailing digits of portrait
variants like 織田信長2 / 刀兵12 removed): build.py redirects it to English by record number
(names_blob/hook below, in the blob that build.py appends to KANJITBL.BIN).

tl/names/officers.json: one row per line, {"id": record, "en": "Family Given", "short": ...};
"short" (optional) is printed where the field is narrow (SHORT_SITES, SHORT_PX) when the full
name does not fit there, "given" (optional) overrides it in GIVEN_SITES; records without a row
keep their Japanese (the empty なし slots).
tl/names/speakers.json: {"id": n, "en": ...} for the display names of speaker headers
`&Id&Display` (n = order of first appearance over NB000..NB199, see `speakers`).

usage:
    names.py show [TEXT]     records: number, Japanese, English
    names.py speakers        display names of the scripts: number, Japanese, English
    names.py check
"""
import json, os, re, struct, sys

sys.path.insert(0, os.path.dirname(__file__))
import asm, eex, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL_NAMES = os.path.join(ROOT, 'tl', 'names')
DATA_E4 = os.path.join(ROOT, 'extract', 'DATA', 'DATA.E4')
RECORD, COUNT = 77, 645
OFFICERS, OFFICER_SIZE = 0x800b20d8, 0x70
GETNAME = 0x80012864
GETNAME_FIRST = 0x00003021              # move a2, zero
SPRINTF = 0x80092a38
MAX_NAME = 24                           # longest English name (speaker box, labels: to be measured)
SPEAKER_PX = 160                        # `&Id&Display` names: speaker box only (216 px wide)
SHORT_PX = 72                           # SHORT_SITES field (6 kanji)
GIVEN_PX = 58                           # GIVEN_SITES field (battle unit list: generic units too)
_HEAD = re.compile(r'&([^&\n]*)&([^\n]*)$')


def japanese():
    d = open(DATA_E4, 'rb').read()
    return [text.decode(d[i * RECORD:i * RECORD + 13].split(b'\0')[0]) for i in range(COUNT)]


def _rows(name, full=False):
    path = os.path.join(TL_NAMES, name + '.json')
    if not os.path.exists(path):
        return {}
    rows = json.load(open(path, encoding='utf-8'))
    return {r['id']: r if full else r['en'] for r in rows}


def officers():
    return _rows('officers')


def speakers_jp():
    """Display names of `&Id&Display` headers, in order of first appearance."""
    out = []
    for f in eex.files():
        for op, args, i in eex.strings(eex.parse(open(f, 'rb').read())):
            if op != 0x27:
                continue
            for ln in text.decode(args[i][1]).split('\n'):
                m = _HEAD.match(ln)
                if m and m.group(2) not in out:
                    out.append(m.group(2))
    return out


_heads = None


def head(h):
    """Speaker header of the Japanese script -> header for the English one."""
    global _heads
    if _heads is None:
        en = _rows('speakers')
        _heads = {jp: en[n] for n, jp in enumerate(speakers_jp()) if n in en}
    m = _HEAD.match(h)
    if m and m.group(2) in _heads:
        return '&%s&%s' % (m.group(1), _heads[m.group(2)])
    return h


def check():
    errs = []
    jp = japanese()
    for kind, rows, n in (('officers', officers(), COUNT), ('speakers', _rows('speakers'), len(speakers_jp()))):
        for i, en in rows.items():
            if not 0 <= i < n:
                errs.append('%s %d: no such entry' % (kind, i))
            errs += ['%s %d: %s' % (kind, i, e) for e in text.check(en)]
            if kind == 'speakers' and text.pixels(en) > SPEAKER_PX:
                errs.append('%s %d: %d px > %d' % (kind, i, text.pixels(en), SPEAKER_PX))
            if kind == 'officers' and len(en) > MAX_NAME:
                errs.append('%s %d: %d characters > %d' % (kind, i, len(en), MAX_NAME))
    for i, r in _rows('officers', full=True).items():
        if text.pixels(_short(r)) > SHORT_PX:
            errs.append('officers %d: %r wider than %d px (needs a "short")' % (i, _short(r), SHORT_PX))
        if text.pixels(_given(r)) > GIVEN_PX:
            errs.append('officers %d: %r wider than %d px (needs a "short")' % (i, _given(r), GIVEN_PX))
    return errs


def _short(row):
    return row['en'] if text.pixels(row['en']) <= SHORT_PX else row.get('short', row['en'])


def _given(row):
    return row['en'] if text.pixels(row['en']) <= GIVEN_PX else row.get('given', row.get('short', row['en']))


# ---------------------------------------------------------------- program patch
def blob_names(base):
    """English names at `base`: three tables of u16 offsets (from base; 0 = keep the Japanese)
    per record: full names, short forms for SHORT_PX ("short" if the full name is wider, else
    the full name), given names for GIVEN_PX (the same with GIVEN_PX); then the NUL-terminated
    strings (shared). -> bytes"""
    rows = _rows('officers', full=True)
    strs, offs = bytearray(), {}
    head = 6 * COUNT

    def off(s):
        if s is None:
            return 0
        if s not in offs:
            offs[s] = head + len(strs)
            strs.extend(s.encode('ascii') + b'\0')
        return offs[s]
    full = [off(rows[i]['en']) if i in rows else 0 for i in range(COUNT)]
    short = [off(_short(rows[i])) if i in rows else 0 for i in range(COUNT)]
    given = [off(_given(rows[i])) if i in rows else 0 for i in range(COUNT)]
    return struct.pack('<%dH' % (3 * COUNT), *(full + short + given)) + bytes(strs)


def hook(at, base):
    """New GETNAME at `at` (full names), `at` + 8 (short forms, SHORT_SITES call it) and
    `at` + 16 (given names, GIVEN_SITES), and a sprintf wrapper for RAW_SITES:
    English of the record if the table has it, else the original (which continues at
    GETNAME + 4; its first instruction, replaced by the jump to here, runs in the delay slot).
    -> (code, short entry, given entry, raw entry)"""
    lines = [
        ('b', 'common'),
        ('addiu', 't3', 'zero', 0),             # full table: offset 0
        ('b', 'common'),
        ('addiu', 't3', 'zero', 2 * COUNT),     # short entry: second table
        ('addiu', 't3', 'zero', 4 * COUNT),     # given entry: third table
        'common:',
        ('lui', 't0', asm.hi(OFFICERS)),
        ('addiu', 't0', 't0', asm.lo(OFFICERS)),
        ('subu', 't1', 'a0', 't0'),
        ('addiu', 't2', 'zero', OFFICER_SIZE),
        ('divu', 't1', 't2'),
        ('mflo', 't1'),
        ('sltiu', 'v0', 't1', COUNT),
        ('beqz', 'v0', 'jp'),
        ('sll', 't1', 't1', 1),
        ('addu', 't1', 't1', 't3'),
        ('lui', 't2', asm.hi(base)),
        ('addu', 't2', 't2', 't1'),
        ('lhu', 't1', asm.lo(base), 't2'),
        ('nop',),
        ('beqz', 't1', 'jp'),
        ('lui', 'v0', asm.hi(base)),
        ('addiu', 'v0', 'v0', asm.lo(base)),
        ('jr', 'ra'),
        ('addu', 'v0', 'v0', 't1'),
        'jp:',
        ('j', GETNAME + 4),
        ('addu', 'a2', 'zero', 'zero')]
    raw = at + 4 * len([x for x in lines if not isinstance(x, str)])
    lines += [                                  # RAW_SITES: sprintf with a2 = record + 0x0c
        ('addiu', 'sp', 'sp', -32),
        ('sw', 'ra', 28, 'sp'),
        ('sw', 'a0', 16, 'sp'),
        ('sw', 'a1', 20, 'sp'),
        ('sw', 'a3', 24, 'sp'),
        ('jal', at),
        ('addiu', 'a0', 'a2', -0x0c),
        ('addu', 'a2', 'v0', 'zero'),
        ('lw', 'ra', 28, 'sp'),
        ('lw', 'a0', 16, 'sp'),
        ('lw', 'a1', 20, 'sp'),
        ('lw', 'a3', 24, 'sp'),
        ('j', SPRINTF),
        ('addiu', 'sp', 'sp', 32)]
    return asm.assemble(at, lines), at + 8, at + 16, raw


# officer screen 0x8006e8c8: the name, then the kana reading (+0x19) at x 0x70 -> print the
# NUL that ends the Japanese name (+0x18) instead
READING_AT, READING_OLD, READING_NEW = 0x8006e900, 0x26860019, 0x26860018   # addiu a2, s4, ...
# calls of GETNAME that print into a narrow field: they get the short forms
SHORT_SITES = [
    0x8006a514,     # battle: unit panel (name, then a level icon at 6 kanji = 72 px)
    0x80017b98,     # blacksmith: officer list (name, then the class icon at ~74 px)
]
# calls of GETNAME for fields narrower still (given names)
GIVEN_SITES = [
    0x80028530,     # storehouse: officer panel header (name, class icon, class; build.CLASS_X)
    0x8006fdb4,     # battle unit list (name, then Lv at ~68 px)
    0x8001a684,     # blacksmith upgrade screen header (name at x 24, Atk label at 92)
    0x80029420,     # item info "Equip By" list (68-px slots, 0x800293bc)
]

# sprintf calls that pass the Japanese record name (a2 = record + 0x0c in the delay slot)
RAW_SITES = [
    0x80011d5c,     # level-up message "%s reached level %u!"
]


def _word(exe, exe_base, va, old=None):
    o = va - exe_base
    if old is not None:
        assert struct.unpack_from('<I', exe, o)[0] == old, 'unexpected code at %#x' % va
    return o


def patch(exe, exe_base, at, short_entry, given_entry, raw_entry):
    o = _word(exe, exe_base, GETNAME, GETNAME_FIRST)
    exe[o:o + 4] = asm.assemble(GETNAME, [('j', at)])     # delay slot: its lbu v0, 0xc(a0)
    struct.pack_into('<I', exe, _word(exe, exe_base, READING_AT, READING_OLD), READING_NEW)
    jal = asm.assemble(0, [('jal', GETNAME)])
    for sites, entry in ((SHORT_SITES, short_entry), (GIVEN_SITES, given_entry)):
        for va in sites:
            o = _word(exe, exe_base, va)
            assert exe[o:o + 4] == jal, 'no jal GETNAME at %#x' % va
            exe[o:o + 4] = asm.assemble(va, [('jal', entry)])
    for va in RAW_SITES:
        o = _word(exe, exe_base, va)
        assert exe[o:o + 4] == asm.assemble(0, [('jal', SPRINTF)]), 'no jal sprintf at %#x' % va
        w = struct.unpack_from('<I', exe, o + 4)[0]
        assert w >> 26 == 9 and (w >> 16) & 31 == 6 and w & 0xffff == 0x0c, 'no addiu a2, rX, 0xc at %#x' % va
        exe[o:o + 4] = asm.assemble(va, [('jal', raw_entry)])


# ---------------------------------------------------------------- commands
def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == 'show':
        en = officers()
        for i, jp in enumerate(japanese()):
            if len(a) < 2 or a[1] in jp or a[1] in en.get(i, ''):
                print('%3d  %-14s %s' % (i, jp, en.get(i, '')))
    elif a[0] == 'speakers':
        en = _rows('speakers')
        for i, jp in enumerate(speakers_jp()):
            print('%3d  %-14s %s' % (i, jp, en.get(i, '')))
    elif a[0] == 'check':
        errs = check()
        print('\n'.join(errs) or 'ok: %d officers, %d speakers' % (len(officers()), len(_rows('speakers'))))
        sys.exit(1 if errs else 0)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
