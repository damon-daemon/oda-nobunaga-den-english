"""Apply Hepburn macrons (and temple hyphens) across the English text (issue #9).

Each entry: token -> (replacement, REQUIRE, KEEP). A token is replaced only when the Japanese
source of the same record contains one of REQUIRE (None = always); it is left alone silently
when the source contains one of KEEP, and reported for review otherwise. Chapter titles (EEX ops
0x2a/0x2b) are never changed: the BIOS memory-card list prints the raw ASCII codes.

usage: .venv/bin/python tools/dev/macronize.py [--apply]     (dry run without --apply)
"""
import glob, json, os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import names as officer_names, tl

ROOT = tl.ROOT
A = None   # always
D = {
    # officers (kana readings in DATA.E4)
    'Gamo': ('Gamō', A, ()), 'Tokichiro': ('Tōkichirō', A, ()), 'Hanzo': ('Hanzō', A, ()),
    'Okubo': ('Ōkubo', A, ()), 'Suden': ('Sūden', A, ()), 'Saito': ('Saitō', A, ()),
    'Jojo': ('Jōjō', A, ()), 'Kitajo': ('Kitajō', A, ()), 'Honjo': ('Honjō', A, ()),
    'Jinbo': ('Jinbō', A, ()), 'Hojo': ('Hōjō', A, ()), 'Genan': ("Gen'an", A, ()),
    'Fuma': ('Fūma', A, ()), 'Kotaro': ('Kotarō', A, ()), 'Cho': ('Chō', ('長',), ()),
    'Naito': ('Naitō', A, ()), 'Kosaka': ('Kōsaka', A, ()), 'Dosan': ('Dōsan', A, ()),
    'Doku': ('Dōkū', A, ()), 'Ando': ('Andō', A, ()), 'Kaiho': ('Kaihō', A, ()),
    'Kyonyo': ('Kyōnyo', A, ()), 'Raisho': ('Raishō', A, ()), 'Sadayu': ('Sadayū', A, ()),
    'Chokei': ('Chōkei', A, ()), 'Sogo': ('Sogō', A, ()), 'Chosokabe': ('Chōsokabe', A, ()),
    'Kosokabe': ('Kōsokabe', A, ()), 'Magoshiro': ('Magoshirō', A, ()), 'Kicho': ('Kichō', A, ()),
    'Sokyu': ('Sōkyū', A, ()), 'Soeki': ('Sōeki', A, ()), 'Nohime': ('Nōhime', A, ()),
    'Rikyu': ('Rikyū', A, ()), 'Soon': ('Shūon', ('宗恩', '沢彦'), ()), 'Hanbee': ('Hanbei', A, ()),
    'Mori': ('Mōri', ('毛利',), ('森',)), 'Jubei': ('Jūbei', A, ()), 'Goroza': ('Gorōza', A, ()),
    'Danjo': ('Danjō', A, ()), 'Chusaburo': ('Chūsaburō', A, ()), 'Shozaburo': ('Shōzaburō', A, ()),
    'Shirojiro': ('Shirōjirō', A, ()), 'Sotan': ('Sōtan', A, ()), 'Zenjubo': ('Zenjūbō', A, ()),
    'Joha': ('Jōha', A, ()), 'Chosaku': ('Chōsaku', A, ()), 'Kichizo': ('Kichizō', A, ()),
    'Kato': ('Katō', ('加藤',), ()), 'Nakajo': ('Nakajō', ('中條',), ()),
    'Rokuro': ('Koroku', ('小六',), ()),            # NB172: 蜂須賀小六, mistranscribed
    'Ono': ('Ōno', ('大野',), ('小野',)), 'Koga': ('Kōga', ('甲賀',), ('古河',)),
    'Koji': ('Kōji', ('弘治',), ()),
    # places, clans, eras, terms
    'Kyoto': ('Kyōto', A, ()), 'Osaka': ('Ōsaka', A, ()), 'Omi': ('Ōmi', A, ()),
    'Kozuki': ('Kōzuki', A, ()), 'Kozuke': ('Kōzuke', A, ()), 'Totomi': ('Tōtōmi', A, ()),
    'Etchu': ('Etchū', A, ()), 'Bitchu': ('Bitchū', A, ()), 'Chugoku': ('Chūgoku', A, ()),
    'Kyushu': ('Kyūshū', A, ()), 'Hoki': ('Hōki', A, ()), 'Suo': ('Suō', A, ()),
    'Kofu': ('Kōfu', A, ()), 'Tokaido': ('Tōkaidō', A, ()), 'Tokai': ('Tōkai', A, ()),
    'Nakasendo': ('Nakasendō', A, ()), 'Sanyo': ("San'yō", A, ()), 'Otomo': ('Ōtomo', A, ()),
    'Kanto': ('Kantō', A, ()), 'Tensho': ('Tenshō', A, ()), 'Ikko': ('Ikkō', A, ()),
    'Shozui': ('Shōzui', A, ()), 'Shoryuji': ('Shōryūji', A, ()), 'Ichijodani': ('Ichijōdani', A, ()),
    'Ichijoin': ('Ichijōin', A, ()), 'Kitanosho': ('Kitanoshō', A, ()), 'Hachioji': ('Hachiōji', A, ()),
    'Otsu': ('Ōtsu', A, ()), 'Ogaki': ('Ōgaki', A, ()), 'Ohama': ('Ōhama', A, ()),
    'Oiwayama': ('Ōiwayama', A, ()), 'Okawachi': ('Ōkawachi', A, ()), 'Otorii': ('Ōtorii', A, ()),
    'Koriyama': ('Kōriyama', A, ()), 'Ogimachi': ('Ōgimachi', A, ()), 'Oko': ('Okō', A, ()),
    'Inou': ('Inō', A, ()), 'Fuchu': ('Fuchū', A, ()), 'Koshin': ('Kōshin', A, ()),
    'Chudo': ('Chūdō', A, ()), 'Gobozuka': ('Gobōzuka', A, ()), 'Takato': ('Takatō', A, ()),
    'Daishoji': ('Daishōji', A, ()), 'Zenshoji': ('Zenshōji', A, ()), 'Senshu': ('Senshū', A, ()),
    'Sanno': ('Sannō', A, ()), 'Sanboshi': ('Sanbōshi', A, ()), 'Nijo': ('Nijō', A, ()),
    'Taishogun': ('Taishōgun', A, ()), 'Shincho': ('Shinchō', A, ()), 'Koki': ('Kōki', A, ()),
    'Jonin': ('Jōnin', A, ()), 'Myoo': ('Myōō', A, ()), 'Fudo': ('Fudō', A, ()),
    'Hocho': ('Hōchō', A, ()), 'Horoku': ('Hōroku', A, ()), 'Hozoin': ('Hōzōin', A, ()),
    'Kongo': ('Kongō', A, ()), 'Jumonji': ('Jūmonji', A, ()), 'Nihongo': ('Nihongō', A, ()),
    'Hayago': ('Hayagō', A, ()), 'Ozutsu': ('Ōzutsu', A, ()), 'Domaru': ('Dōmaru', A, ()),
    'domaru': ('dōmaru', A, ()), 'Hokoku': ('Hōkoku', A, ()), 'Fujin': ('Fūjin', ('風神',), ()),
    'shogun': ('shōgun', A, ()), 'Shogun': ('Shōgun', A, ()), 'daimyo': ('daimyō', A, ()),
    'ronin': ('rōnin', A, ()), 'Ronin': ('Rōnin', A, ()),
    # temples: hyphen before -ji (#4); castles/forts named after temples keep the joined form
    'Honnoji Temple': ('Honnō-ji', A, ()), 'Honnoji': ('Honnō-ji', A, ()), 'Honganji': ('Hongan-ji', A, ()),
    'Enryakuji': ('Enryaku-ji', A, ()), 'Banshoji': ('Banshō-ji', A, ()), 'Seishuji': ('Seishū-ji', A, ()),
    'Shotokuji': ('Shōtoku-ji', A, ()), 'Kenshoji': ('Kenshō-ji', A, ()), 'Myokakuji': ('Myōkaku-ji', A, ()),
    'Kofukuji': ('Kōfuku-ji', A, ()), 'Todaiji': ('Tōdai-ji', A, ()), 'Horyuji': ('Hōryū-ji', A, ()),
    'Ryuseiji': ('Ryūshō-ji', A, ()),               # 立政寺
}
PAT = re.compile(r'\b(' + '|'.join(sorted(map(re.escape, D), key=len, reverse=True)) + r')\b')
counts, flags, titles = {}, [], []


def sub(line, jp, where, title=False):
    def rep(m):
        t = m.group(1)
        new, req, keep = D[t]
        if title:
            titles.append('%s: %s (title, kept)' % (where, t))
            return t
        if req is not None and not any(r in jp for r in req):
            if not any(k in jp for k in keep):
                flags.append('%s: %s | %s' % (where, t, jp[:50].replace('\n', ' ')))
            return t
        counts[t] = counts.get(t, 0) + 1
        return new
    return PAT.sub(rep, line)


def eex(apply):
    for name in tl.names():
        path = tl.tl_path(name)
        if not os.path.exists(path):
            continue
        src = open(path, encoding='utf-8').read()
        if not PAT.search(src):
            continue
        sc, key, out = tl.load(name), None, []
        for ln in src.split('\n'):
            m = tl._REC.match(ln)
            if m:
                key = (int(m.group(1)), None if m.group(2) is None else int(m.group(2)))
            elif key is not None and not ln.startswith('#'):
                ln = sub(ln, sc.segs.get(key, ''), '%s %s' % (name, tl.key_str(key)), sc.kind.get(key) in (0x2a, 0x2b))
            out.append(ln)
        if apply:
            open(path, 'w', encoding='utf-8').write('\n'.join(out))


def keyed(path, jp_of, apply, sep='\t'):
    """KEY<TAB>text files (progstr, data) and @key files (imsg)."""
    src = open(path, encoding='utf-8').read()
    if not PAT.search(src):
        return
    out, key = [], None
    for ln in src.split('\n'):
        if ln.startswith('#'):
            pass
        elif sep == '\t' and '\t' in ln:
            key, en = ln.split('\t', 1)
            ln = key + '\t' + sub(en, jp_of(key), key)
        elif sep == '@':
            if ln.startswith('@'):
                key = ln.split()[0]
            elif key:
                ln = sub(ln, jp_of(key), os.path.basename(path) + ' ' + key)
        out.append(ln)
    if apply:
        open(path, 'w', encoding='utf-8').write('\n'.join(out))


def at_file(path):
    out, key = {}, None
    for ln in open(path, encoding='utf-8'):
        ln = ln.rstrip('\n')
        if ln.startswith('@'):
            key = ln.split()[0]
            out[key] = ''
        elif key:
            out[key] += ln
    return out


def names_json(apply):
    jp = officer_names.japanese()
    for fn, jp_of in (('officers', lambda r: jp[r['id']]), ('speakers', lambda r: '')):
        path = os.path.join(tl.TL, 'names', fn + '.json')
        rows = json.load(open(path, encoding='utf-8'))
        for r in rows:
            for f in ('en', 'short', 'given'):
                if f in r:
                    r[f] = sub(r[f], jp_of(r), '%s %d' % (fn, r['id']))
        if apply:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('[\n' + ',\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n]\n')


def main():
    apply = '--apply' in sys.argv
    eex(apply)
    pj = {r['key']: r['jp'] for r in json.load(open(os.path.join(ROOT, 'script', 'progstr.json'), encoding='utf-8'))}
    for p in sorted(glob.glob(os.path.join(tl.TL, 'progstr', '*.txt'))):
        keyed(p, lambda k: pj.get(k, ''), apply)
    jd = {l.split('\t')[0]: l for l in open(os.path.join(ROOT, 'script', 'data.txt'), encoding='utf-8')}
    keyed(os.path.join(tl.TL, 'data.txt'), lambda k: jd.get(k, ''), apply)
    ji = at_file(os.path.join(ROOT, 'script', 'imsg.txt'))
    for p in sorted(glob.glob(os.path.join(tl.TL, 'imsg', '*.txt'))):
        keyed(p, lambda k: ji.get(k, ''), apply, sep='@')
    names_json(apply)
    g = os.path.join(ROOT, 'notes', 'glossary.txt')
    if os.path.exists(g):
        keyed(g, lambda k: k, apply)      # JP<TAB>EN: the key is the Japanese
    print('%s: %d replacements, %d tokens' % ('applied' if apply else 'dry run', sum(counts.values()), len(counts)))
    for t, n in sorted(counts.items(), key=lambda x: -x[1]):
        print('  %-16s %4d  -> %s' % (t, n, D[t][0]))
    print('\nreview (left as is):'); print('\n'.join('  ' + f for f in flags) or '  none')
    print('\nchapter titles kept plain:'); print('\n'.join('  ' + t for t in titles) or '  none')


if __name__ == '__main__':
    main()
