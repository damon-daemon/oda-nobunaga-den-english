"""Check your own disc image and create the working folders extract/ and script/.

extract/ holds the files of the disc, script/ the Japanese text (one file per event script,
same keys as tl/), so both are generated on each machine and never distributed. Run this
once after cloning, then tools/build.py.

usage: .venv/bin/python tools/setup.py [track1.bin]
"""
import hashlib, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import iso

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACT = os.path.join(ROOT, 'extract')
SCRIPT = os.path.join(ROOT, 'script')
CLEAN = os.path.join(ROOT, 'oda_nobunaga_den_track1.bin')
CLEAN_SHA1 = '4328af8bc1689e12094e27556da3826eb00cc529'
# CD audio track 2: copied next to the rebuilt track 1, never patched
AUDIO = [os.path.join(ROOT, 'oda_nobunaga_den_track2.bin')]
AUDIO_SHA1 = ['7c8508996d34d2a39fd75a8fab58e2c9b766b09b']


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        while chunk := f.read(1 << 24):
            h.update(chunk)
    return h.hexdigest()


def check_clean(path, want=CLEAN_SHA1):
    digest = sha1(path)
    if digest != want:
        sys.exit('%s: SHA-1 %s does not match the clean dump (%s)' % (path, digest, want))


def extract(disc):
    n = 0
    for name, lba, size in disc.walk():
        if name.endswith(('.DA', '.STR')):
            continue                     # CD-DA entry, Form 2 movies
        p = os.path.join(EXTRACT, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(disc.read(lba, size))
        n += 1
    return n


def export_script():
    import tl, text
    os.makedirs(os.path.join(SCRIPT, 'eex'), exist_ok=True)
    total = 0
    for name in tl.names():
        sc = tl.load(name)
        with open(os.path.join(SCRIPT, 'eex', name + '.txt'), 'w', encoding='utf-8') as f:
            for k, jp in sorted(sc.segs.items(), key=lambda i: (i[0][0], i[0][1] or 0)):
                tmpl = sc.tmpl[k[0]]
                who = ' [%s]' % tmpl[1][k[1]][1:] if tmpl[0] == 'talk' else ''
                f.write('%s %s%s\n%s\n\n' % (tl.key_str(k), text.KIND.get(sc.kind[k], hex(sc.kind[k])),
                                             who, text.jp_show(jp)))
                total += 1
    return total


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else CLEAN
    check_clean(path)
    if path == CLEAN:
        for p, want in zip(AUDIO, AUDIO_SHA1):
            check_clean(p, want)
    print('extract/: %d files' % extract(iso.Disc(path)))
    print('script/eex: %d segments' % export_script())
    import datae4, imsg
    print('script/data.txt: %d names' % datae4.export())
    print('script/imsg.txt: %d texts' % imsg.export())
    print('ready; now run tools/build.py')


if __name__ == '__main__':
    main()
